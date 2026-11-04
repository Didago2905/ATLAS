# Editorial milestone 1: private drafts only

Editorial is disabled by default. The backend supervisor can own it as a separate
child, without adding a visible terminal pane. Nothing is added to FastAPI
routers, Operations, Incidents, Beer, Tap List or Museum. Importing its models
does not import the live database engine. There is no publication command,
approval action, slot update, event banner, OCR or artwork classification model.

## Shared image processing

`museum_upload_service.prepare_artwork()` is a small side-effect-free adapter to
the existing `_prepare()` pipeline. Its existing public upload behavior is
unchanged. Editorial reuses decoding, 25 MiB/50 megapixel validation, EXIF
orientation, ICC conversion, transparency handling and JPEG derivatives. The
800x1000 bounding-box derivative is the actual private preview. There is no
second optimization pipeline and no call to `upload_artwork()` or `_publish()`.
The existing `_stage()` helper writes private files atomically on their own
filesystem. Sources retain their received bytes and metadata; do not expose them.

The independently configurable Telegram transport cap defaults to 15 MiB. This
is not an application-wide image limit. Increasing it does not increase ATLAS's
25 MiB/50 megapixel decoder limits or Telegram's own download capabilities.
Both declared size and actual streamed size are bounded. Format is determined
by decoding, never the original filename or supplied MIME type.

## Storage and migration

Six dedicated tables live in the explicitly configured SQLite database:

- `editorial_cursor`: next Telegram offset and schema version 1.
- `editorial_updates`: allowlisted authorized inputs, processing state/attempts.
- `editorial_assets`: content digest, source extension/size and preview dimensions.
- `editorial_drafts`: one resumable conversation per numeric chat/user pair.
- `editorial_versions`: immutable asset/source-kind/operation snapshots.
- `editorial_replies`: durable text/photo response intents and Telegram receipts.

`python -B -m app.migrations.editorial --database <explicit-file> --create`
allows intentional fresh storage. Without `--create`, the file must exist.
The migration creates only its own tables under `BEGIN IMMEDIATE`, checks types,
nullability, primary/unique/foreign keys and schema version, then commits.
Repeating it validates without rebuilding. Partial/incompatible Editorial tables
are rejected transactionally. Existing unrelated tables are left alone. The
worker checks the schema and never migrates automatically.

Private media contains `{sha256}.{extension}` and `{sha256}.preview.jpg` under
the configured root. Original filenames, arbitrary paths and Telegram download
URLs are not stored. Paths under frontend/static/build or their ancestors are
rejected. Default `data/editorial/` and the separate worker lock are Git-ignored.
Protect the directory and database with OS permissions and include both in
private backups. There is no public retrieval route.

## Authorization and conversation

`/obra` (also `/obra@BotUsername`) requires `artwork.submit`. Any authorized
staff member can initiate it and upload the designer's file; the designer need
not interact with the bot. The bot requests an attachment with ForceReply, so
privacy mode can stay enabled. Respond directly to that prompt, as its owner,
inside the configured numeric group. Anonymous/send-as-chat, bot, forwarded,
foreign group and unauthorized actor inputs cannot attach or change a draft.

Documents are preferred. Photos are accepted and explicitly marked as
Telegram-compressed. The received bytes are preserved; photo bytes cannot be
called the designer's uncompressed original. Albums are rejected with an
instruction to submit one image, without clearing the existing draft.

The bot sends the real optimized preview with operation buttons:

| Human selection | Additional preparation permission |
| --- | --- |
| New beer | `beer.create` |
| Existing beer artwork | `artwork.submit` |
| Beer information correction | `beer.edit` |
| Board for Museum | `artwork.submit` |
| Event/promotion preparation | `event.prepare` |

Permissions accumulate per user; no exclusive job titles. Only these milestone
permissions are accepted. Future publication/approval and permission management
remain unimplemented. Buttons are filtered, and every selected operation is
checked again server-side. A callback references a draft ID and revision; old
buttons or another person's draft cannot modify the current revision.

Selecting an operation creates an immutable version and marks the draft
`classified`, NOT approved or ready to publish. Beer identity, metadata, approval
and final confirmation are intentionally not collected yet. Replacing the image
retains old versions and clears the current selection. `/vista` reads the current
preview. `/cancelar` closes the conversation without deleting its history;
`/obra` resumes it. Restarting does not lose the draft or its version.

## Recovery and transport

The update batch and cursor commit together before any download or conversation
effect. Unique update IDs and transactional processing prevent repeated updates
from creating repeated effects. Only supported fields from authorized users are
persisted; unrelated group content is discarded. The receiver is single-instance
per canonical database using `.editorial-worker.lock`, independent of the
Incidents lock. State transitions serialize with SQLite `BEGIN IMMEDIATE`.
Network/image processing does not hold a database write lock.

Downloads have at most three processing attempts; then the bot requests a fresh
reply and retains the existing draft. Transport-limit and invalid-image failures
are immediately actionable replacements, not silent draft resets.

Response intents commit before Telegram sends. Interrupted/ambiguous sends
become `uncertain` and are NOT automatically resent. `/obra` or `/vista` creates a
new response intent for the same draft. Restart recovers persisted inbox work
and marks interrupted sends uncertain. Text/photo response duplication is still
possible if a human explicitly requests it after an unknown remote outcome;
there is no catalog publication to duplicate.

Assets are written before their database references. Crashes can leave complete
unreferenced files or staging leftovers, never a published Museum entry. Cleanup
and retention are not automated in this milestone. Missing files/storage errors
stop safely or mark a response uncertain; they never invoke publication recovery.

HTTPS uses a fixed Telegram host, bounded replies/streaming and timeouts, with no
redirects or arbitrary URL input. Transport exceptions contain fixed messages,
not tokens, response bodies or token-bearing URLs. No credentials are read from
Operations/Incidents. The worker loads only `ATLAS/Editorial/BotToken` from Windows Credential Manager
inside its own process. The token is not loaded by the supervisor or read from
environment variables/configuration files. See [editorial-persistent-worker.md](editorial-persistent-worker.md).
Do not enable HTTP wire/debug logging.

## Dedicated configuration

Nonsecret settings load from `data/editorial/settings.json` when present, with
environment overrides. The repository `.env` and other bots are never read:

| Setting | Default |
| --- | --- |
| `ATLAS_EDITORIAL_ENABLED` | `false` |
| `ATLAS_EDITORIAL_DATABASE_URL` | dedicated `data/editorial/storage/editorial.sqlite3` |
| `ATLAS_EDITORIAL_MEDIA_ROOT` | `data/editorial/storage/media` |
| `ATLAS_EDITORIAL_CHAT_ID` | unset; negative numeric group ID |
| `ATLAS_EDITORIAL_PERMISSIONS_FILE` | private `data/editorial/permissions.json` |
| Token | Credential Manager only: `ATLAS/Editorial/BotToken` |
| `ATLAS_EDITORIAL_DOWNLOAD_LIMIT_BYTES` | `15728640` (15 MiB) |

The permissions file is a bounded JSON object mapping canonical numeric user-ID
strings to lists such as `["artwork.submit", "beer.create"]`. Numeric IDs are
required; usernames/display names never grant access. Duplicate IDs and unknown
permissions fail closed. The worker reloads the map each cycle, so revocations
do not require restart. Keep it outside the repository and public folders.

## Offline verification

```powershell
.\.venv\Scripts\python.exe -B -m unittest tests.test_editorial tests.test_museum_uploads
```

Tests use temporary SQLite/media, fake credentials/transports and synthetic
images. They never import `app.main` or connect to the configured live database.
No real Telegram call is needed. Existing Museum tests verify the unchanged
shared pipeline and public upload behavior.

## Persistent integration and activation

See [editorial-persistent-worker.md](editorial-persistent-worker.md) for the
separately approved enrollment, verified copy from temporary storage, durable
configuration and controlled first supervised startup. Do not use the earlier
token-in-environment bootstrap; it is no longer used by the worker. Discovery
remains an independent hidden-input diagnostic and is not changed by integration.
No actual activation, credential enrollment or transfer of real drafts was
performed while implementing this integration.

A subsequent, separately approved local rollout verified permanent storage,
direct Credential Manager loading, supervised startup and real `/vista` recovery
after the backend handoff. That local enablement is not part of repository
defaults; all runtime data and configuration remain excluded from Git.
