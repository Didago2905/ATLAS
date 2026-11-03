# Issue Reporter: persistence and submission

Reports are stored independently of Telegram. There are no public report
read/list/attachment routes. The Phase 3A standalone sender is disabled by default;
see [incident-notifications.md](incident-notifications.md) for migration and activation.

## API

`POST /public/issue-reports` (browser path `/api/public/issue-reports` through the
existing proxy) accepts `multipart/form-data` with exactly:

- `report`: JSON string, at most 32 KiB UTF-8.
- `screenshot`: optional single file. Filenames and declared MIME types are not
  trusted or stored; actual decoded image format determines acceptance.

Example `report`:

```json
{
  "schema_version": 1,
  "categories": ["Tap List", "Otro"],
  "description": "La lista no aparece al abrir la página.",
  "diagnostic_consent": false,
  "idempotency_key": "f630c3e9-90fc-4bd5-9a67-9746140daef8"
}
```

Categories are `Tap List`, `Museo`, `Información de cerveza`,
`Interacción / visualización`, and `Otro`: 1–5 unique values. Description is
trimmed before enforcing 20–2000 characters. The idempotency key must be UUID v4.
Unknown JSON fields (including nested diagnostic fields) are rejected. Boolean
consent is required. When false, diagnostics must be absent or null; supplied
diagnostic data is rejected rather than silently stored. The frontend omits it.

When consent is true, optional `diagnostics` follows the Phase 1 schema in
`app/schemas/issue_report.py`: schemaVersion, timestamp, timezone/offset, public
ATLAS pathname, approximate browser/OS, viewport/screen/visualViewport, pixel
ratio, orientation, online hint, and network information. Unsupported values
remain null. All numbers/strings are bounded and nonfinite numbers are rejected.
Only `/`, `/museum`, and `/beer/<numeric ID>` routes are accepted; no query/hash,
arbitrary paths, request payloads, console output, tokens or storage dumps.

New storage returns HTTP **201**; an identical retry returns **200**, both with:

```json
{
  "report_id": "f630c3e9-90fc-4bd5-9a67-9746140daef8",
  "stored_at": "2026-11-02T12:00:00Z"
}
```

The response is sent only after the SQLAlchemy transaction commits. Neither the
idempotency key nor report ID grants public read access. Responses contain no
report content. Successful receipts use `Cache-Control: no-store`.

Errors: 400 invalid/oversized multipart fields; 409 key reused with different
content; 413 whole request/file/pixel/dimension limit; 415 unsupported encoding
or image; 422 invalid report schema/consent; 429 abuse limit with `Retry-After`;
503 storage temporarily unavailable. Validation errors do not echo inputs.

## Persistence and retries

`issue_reports` is a new table registered before existing startup `create_all`.
It uses the existing configured SQLAlchemy database; this does not change the
database engine, existing tables, or Museum storage. Importing the model alone
does not create tables. Startup creates the new table in the configured database.

Each row contains a random UUID, server UTC creation time, categories, trimmed
description, explicit consent, report schema version, optional validated snapshot,
optional normalized JPEG blob/MIME, unique idempotency key, SHA-256 payload digest,
and `notification_state = pending`. UTC database timestamps are stored without
tzinfo for consistency with existing models, and returned explicitly as UTC.

The report and screenshot commit atomically. No original screenshot, original
filename, raw IP, user-agent header, or credential is stored. Screenshot pixels
are converted to a fresh JPEG canvas after EXIF orientation; metadata/profiles
are discarded. Images are flattened onto white and reduced to at most 2048px on
the longest edge. This can change screenshot appearance/quality.

Idempotency compares canonical validated JSON (sorted categories and trimmed
description) plus SHA-256 of original screenshot bytes. Re-encoding/replacing a
file is different content. A unique database constraint prevents duplicate rows
even across processes. A losing insert rolls back and returns the winner's
receipt, or 409 for different content. Storage errors return 503 with no report
contents in application logs; a same-key retry can recover an ambiguous commit.

The browser retains the key, exact snapshot, file and draft in memory after
network/server errors or timeout. It generates a new key when submitting edited
content or starting another report. After an ambiguous failure, retry unchanged
content to avoid creating another report. Reloading/leaving Home loses the draft
and key. No browser persistence or automatic background retry is implemented.

## Limits and deployment requirements

- Whole multipart body: **5 MiB + 64 KiB**, enforced while reading even without a
  Content-Length header and before multipart parsing. JSON field: **32 KiB**;
  diagnostic schema: bounded fields plus **16 KiB** serialized cap.
- Screenshot source: **5 MiB**, nonempty JPEG/PNG/WebP, one frame, **20 megapixels**,
  each dimension **1–16384px**. Normalized JPEG storage: at most **3 MiB**.
- Process-local limiter: by default **6 attempts/client per 600 seconds** and
  **60 attempts globally per minute**, including invalid attempts and retries.
  Client tracking is bounded to 4096 live keys; capacity exhaustion rejects new
  clients. Raw client identifiers remain only in short-lived process memory.
- Settings: `ISSUE_REPORT_RATE_LIMIT`, `ISSUE_REPORT_RATE_WINDOW_SECONDS`, and
  `ISSUE_REPORT_GLOBAL_PER_MINUTE`. Shared venue Wi-Fi shares a client quota.
- The limiter resets on restart and is independent in each worker/host. Use a
  shared reverse-proxy/gateway limit before scaling workers; it is not a fleet
  limiter or complete DDoS protection. Configure proxy body/read timeouts,
  request/concurrency limits, TLS, and the same or tighter body limit.
- The application does not parse `X-Forwarded-For`. ASGI client identity may be
  rewritten by the server's proxy middleware: configure explicitly trusted proxy
  addresses. Without trusted forwarding, all users may share the proxy's quota;
  trusting arbitrary forwarding permits spoofed identities.
- Verify `DATABASE_URL` points to a durable volume and SQLite has appropriate
  locking and filesystem support. Back up before rollout, verify new-table
  creation rights and startup behavior, and test backup restoration/redeployment.
  Neither startup `create_all` nor this feature proves production persistence.
- Keep the database and backups outside publicly served directories, restrict
  filesystem/database access, monitor disk growth and rejected requests, and
  configure encryption/backups according to deployment requirements. Screenshots
  live in the database, so backups contain report data.
- Establish and operate retention/deletion before production (suggested starting
  policy: screenshots 30 days; reports/diagnostics 90 days, with backup expiry).
  This phase provides no cleanup scheduler or admin dashboard. Preserve dedupe
  keys/digests through the supported retry window when deleting old content.
- Existing runtime upload dependencies are reused; no dependencies were added.
  Authentication and admin endpoints are unchanged. Reports are intentionally
  public submissions; CORS is not an anti-bot mechanism.

## Focused verification

Backend tests use a temporary file-backed SQLite database with independent
sessions and no import of `app.main` (which creates real tables):

```powershell
.\.venv\Scripts\python.exe -B -m unittest tests.test_issue_reports -v
```

Frontend tests exercise Chromium/WebKit against intercepted report responses:

```powershell
cd frontend
npx playwright test tests/issue-reporter.spec.ts --workers=1 --retries=0
npx eslint src/components/IssueReporter.jsx src/api/issueReports.js src/diagnostics/issueSnapshot.js
```

Real iPhone Safari keyboard/file-picker/VoiceOver behavior and the deployed
proxy/database lifecycle still require deployment/device verification.

## Phase 3A Telegram delivery

The standalone worker, explicit additive SQLite migration, safe text formatter,
and mocked transport tests are documented in
[incident-notifications.md](incident-notifications.md). Run that migration before
rolling out the new report model against an existing Phase 2 table. Delivery is
disabled by default and is never started by the API. Reports remain stored during
Telegram outages; Operations notifications are independent and unchanged.
