# Phase 3A: durable Incidents notifications

The outbound worker is disabled by default. It is independent of report
submission, FastAPI/Uvicorn startup, Cloudflare and the existing Operations bot.
It does not import `devtools`, download files, poll updates, expose report-reading
routes, or send screenshots. No Telegram SDK or dependency was added.

## Configuration

Server-only settings use the existing configuration patterns. For the canonical
Windows supervisor, enroll the token in Credential Manager, not `.env`; only
nonsecret enablement/destination settings belong in local configuration. The
supervisor injects the token into the worker process environment only:

| Setting | Default | Meaning |
| --- | --- | --- |
| `TELEGRAM_INCIDENTS_ENABLED` | `false` | Explicit delivery opt-in |
| `TELEGRAM_INCIDENTS_BOT_TOKEN` | unset | Dedicated Incidents bot credential |
| `TELEGRAM_INCIDENTS_CHAT_ID` | unset | Dedicated numeric private destination |
| `TELEGRAM_INCIDENTS_MAX_ATTEMPTS` | `6` | Persisted attempt limit, 1–20 |

Token and destination use `SecretStr` so settings representations mask them.
Credentials are never copied from Operations, sent to Vite, or stored in reports.
Neither missing credentials nor enabled-but-incomplete credentials prevent API
imports or report saving. Validation happens only in the standalone worker.

Disabled mode logs a fixed status, claims nothing, connects to neither database
nor Telegram, and exits 0. Incomplete/invalid enabled configuration logs a fixed,
sanitized operational error and exits 2 without claiming reports. Credentials,
chat identifiers, raw responses, transport exception strings and bot API URLs are
never logged by the sender/worker. Do not enable HTTP wire/debug logging.

## Explicit SQLite migration

`app.models.issue_report` defines the fresh schema. Existing `create_all()` does
not add its delivery columns to a Phase 2 table. The worker checks the schema and
refuses to run against an unmigrated database; it never migrates automatically.

Plan a short maintenance window for the model rollout. Stop report writers and
the worker under operator control, take and verify a private SQLite backup, then
run this from the repository root using the intended environment:

```powershell
.\.venv\Scripts\python.exe -B -m app.migrations.issue_report_delivery --database "D:\path\to\atlas.sqlite3"
```

For intentional fresh storage only, add `--create`. The database path is required
so the command never silently selects the development database. The local integration has applied this migration; a fresh or existing deployment
must still verify its own database schema before enabling delivery.

The migration uses `BEGIN IMMEDIATE`, validates the known Phase 2/current column
types, nullability, primary key, idempotency uniqueness and delivery index, then
adds only missing known columns. Unknown/incompatible schema is rejected before
commit. SQLite DDL is explicitly transactional; an interrupted/failed operation
rolls back. Concurrent and repeated migration invocations are safe. The table is
never dropped or rebuilt; original report values, state strings and screenshot
blobs remain unchanged. Compatible partial additive schemas can be completed.

Added columns:

- `notification_attempts`: not null, default 0.
- `notification_next_attempt_at`: nullable UTC scheduling/cooldown time.
- `notification_lease_expires_at`, `notification_lease_token`: nullable lease.
- `notification_sent_at`, `telegram_message_id`: nullable successful receipt.
- `notification_error_code`: nullable fixed allowlisted code, at most 40 chars.
- `notification_destination`: not null, default logical destination `incidents`.

Index `ix_issue_reports_delivery` covers state, destination, next-attempt time
and lease expiry. Existing pending rows receive defaults and become eligible
when delivery is explicitly enabled. Other historical state values are preserved
and skipped unless they are the worker's known pending/sending states.

Decide whether the pre-activation backlog may be forwarded before enabling the
worker, particularly reports collected before the new frontend privacy notice.
Holding older reports requires an explicitly reviewed, targeted database action;
this migration does not silently change their states or consent.

Rollback: on migration failure, its transaction rolls back. For application
rollback after success, disable/stop this worker and revert code while leaving
the additive columns in place; the Phase 2 model can ignore them. Avoid dropping
columns or recreating the live table. Restoring the verified pre-migration backup
requires stopping all writers and reconciling reports created since that backup.

## Standalone lifecycle

After migration and deliberate configuration, start exactly one supervised worker
from the repository root:

```powershell
.\.venv\Scripts\python.exe -B -m app.workers.incident_notifications
```

For an explicit single eligible attempt, add `--once`. An enabled command can
send a real notification: do not use it as a harmless configuration probe.
No worker is started by `app.main`, request handlers, Uvicorn workers, or the
Cloudflare launcher. SIGINT/SIGTERM request a graceful stop: finish the bounded
current attempt and acknowledge it, then claim nothing else. Hard termination
leaves a lease to be recovered after expiry.

The development deployment uses the canonical backend-pane supervisor; see
[backend-supervisor.md](backend-supervisor.md). Do not create another Windows
startup task or service. Use the project interpreter and the same persistent
database. Allow at least 90 seconds for graceful shutdown, including possible
database-lock waits.
Exit 0 means disabled, clean stop, or completed `--once`; exit 2 means credential
or destination configuration needs attention; exit 3 means the database already
has a worker, and exit 4 means the schema requires migration. Exit 1 is an
unexpected/database failure. Only unexpected exits use the supervisor's bounded
restart budget; do not automatically restart exits 0, 2, 3 or 4.
Do not launch one instance per API process. Database fencing is a safety net,
not a reason to increase sender concurrency.

## Delivery behavior

The worker claims one eligible `pending` report or an expired `sending` lease
under `BEGIN IMMEDIATE`, increments attempts, assigns a random ownership token,
sets a 120-second lease, and commits before HTTP. It selects only screenshot
presence and at most 501 source description characters, never screenshot bytes.
The HTTP call runs outside any database transaction.

Acknowledgement uses a conditional update matching report, sending state, lease
token and unexpired lease. An obsolete or expired owner cannot overwrite another
attempt's result. Successful Telegram JSON must include a positive integer
`message_id`; success records it and the UTC sent time, sets `sent`, and clears
lease/error/scheduling data. Unexpected acknowledgement/storage failure leaves a
recoverable lease instead of deleting the report.

Transient errors schedule `pending` with exponential delays starting at 30s,
capped at 30 minutes, plus up to 20% jitter. HTTP 429 never retries earlier than
Telegram's validated `retry_after`; the persisted cooldown also pauses other
reports for this destination across worker restarts. A malformed flood delay
requires operator attention rather than an aggressive retry. Even a final-attempt
429 preserves its destination cooldown while that report remains failed.

401/404, 403, and group migration responses are permanent configuration failures:
the current report becomes `failed`, and the worker exits 2 without claiming the
rest. It does not automatically retarget a migrated group or use Operations.
Other rejected payloads become failed without retry. 5xx, timeouts, malformed
success responses and uncertain transport outcomes retry within the attempt cap.
Each claim consumes an attempt, including a process crash before sending. Expired
leases at the cap become failed without another send. Attempts never reset on
restart. No Telegram error deletes a report or attachment.

The transport uses a fixed verified HTTPS endpoint, 5s connection timeout, 15s
socket/read timeout, 30s caller deadline (including stalled DNS), and 32 KiB response
cap. Expired I/O cannot reconnect later to issue a new request. Plain text is sent
with link previews disabled and no Markdown/HTML parser or redirects.

Exactly-once delivery is not guaranteed. Telegram may accept a message and lose
the response, or the process may crash after sending but before acknowledgement.
Those cases may produce a duplicate on retry; every message contains the full
report UUID for correlation. `delivery_unknown` identifies ambiguous failures.
Operator requeue after failures/exhaustion must be deliberate, targeted and aware
of this ambiguity; fixing credentials alone does not reset failed rows.

All delivery timestamps are naive UTC in SQLite, matching the existing model;
notification text labels UTC explicitly. Keep host time synchronized. Changing
the private destination configuration retargets future pending attempts for the
logical `incidents` destination; review that change and membership before restart.

## Payload and privacy

Spanish notifications contain full report UUID, server UTC timestamp, categories,
at most 500 description characters, a truncation indicator when needed, consented
coarse diagnostics, and screenshot presence. Control/bidi characters and URLs are
sanitized; no AI summarization is performed. Unknown diagnostic fields are never
serialized. Without consent, no device snapshot fields are formatted.

The complete description and screenshot stay in ATLAS. No attachment, private
download URL or report-reading endpoint is sent. The updated frontend notice
discloses the limited summary and conditional diagnostics. There is no new
dashboard or public report access. The message remains below 4096 characters.

Synthetic example:

```text
Nuevo reporte de ATLAS
Reporte: 11111111-1111-4111-8111-111111111111
Fecha UTC: 2026-11-02T12:00:00Z
Categorías: Tap List

Descripción:
La lista de prueba no aparece al abrir la página.

Diagnóstico autorizado: sección /; Safari 18.0; iOS/iPadOS; ventana 390×844; con conexión

Captura: sí, privada en ATLAS
```

## Verification and activation

Focused backend tests use only temporary file-backed SQLite and fake Telegram/
HTTPS connections; they never import `app.main`, migrate the real `atlas.db`, or
contact Telegram:

```powershell
.\.venv\Scripts\python.exe -B -m unittest tests.test_incident_notifications tests.test_issue_reports -v
```

Frontend checks intercept submission responses:

```powershell
cd frontend
npx eslint src/components/IssueReporter.jsx
npx playwright test tests/issue-reporter.spec.ts --grep "submission sends|reporter validates" --workers=1 --retries=0
```

Before real activation, an operator must create the dedicated Incidents bot and
private group, verify identity/membership/sending permissions, securely set its
dedicated credentials, confirm backlog policy, back up and migrate the intended
database, deploy the privacy notice and model together, and configure supervision.
Then deliberately enable delivery and authorize a controlled real send. No bot,
group, environment configuration, existing service, or real destination was
changed during Phase 3A implementation.

Production still needs durable database volumes, backup/restore verification,
report/screenshot retention and deletion, capacity monitoring, restricted secrets
and backups, and monitoring of failed/configuration-error delivery. Preserve the
existing Phase 2 API abuse controls. None of these operational properties is
proven merely by the migration or passing isolated tests.
