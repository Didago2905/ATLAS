# Editorial persistent worker and existing Windows startup

Editorial is disabled by default in a fresh checkout. A separately approved
local activation has verified dedicated Credential Manager loading, permanent
SQLite/media storage, supervisor ownership and recovery of the existing draft
and preview through `/vista`. Runtime configuration, numeric IDs, credentials
and artwork remain private and unversioned. Automated tests use fake credentials
and temporary storage. Editorial only receives artwork, prepares drafts and
previews; there is no publication capability or publication setting to enable.

## Credential enrollment

From a LOCAL interactive terminal, under the Windows account that launches ATLAS:

```powershell
Set-Location 'D:\Apps\Tuburon\ATLAS'
.\.venv\Scripts\python.exe -B -m app.core.editorial_credentials enroll
```

Enter the dedicated Editorial token at the hidden prompt. The entry is the
current user's machine-persistent Generic Credential `ATLAS/Editorial/BotToken`.
It is separate from `ATLAS/Incidents/BotToken` and Operations. Re-run enrollment
for token rotation. No token is accepted in arguments or configuration, and no
token is placed in the parent, supervisor, backend or worker environment. Hidden
input fallback is refused. Enrollment does not call Telegram or enable the worker.

The Editorial worker reads this exact entry directly after validating its own
database/schema, permissions and singleton. The supervisor does not read it.
Missing/invalid credentials exit 2 before polling, leaving FastAPI/Incidents up.
Only ABI definitions are reused from the Incidents credential module; its entry
and enrollment/loading functions are not invoked. Credentials in local process
memory remain subject to the normal same-user/admin OS security boundary.

## Durable private location

The base `D:\Apps\Tuburon\ATLAS\data\editorial\` is created but remains disabled.
It is Git-ignored, outside public/static/frontend roots and independent of TEMP.

```text
data/editorial/
  settings.json                 nonsecret local startup settings
  permissions.json              numeric user IDs and permissions
  storage/
    editorial.sqlite3           ONLY the six Editorial tables
    media/                      original artwork and real JPEG previews
    copy-receipt.json           optional verified-transfer receipt
```

Restrict filesystem access to the intended Windows account/admins and back up
the DB, media, permissions and nonsecret settings together privately. Git is not
a backup for these files. The DB is never `atlas.db`; the worker rejects that
path and any database containing unrelated tables. No automatic migration runs.

## Preserve the existing Leviatán draft: COPY, not move

Do this only in a separate approved activation window. Stop the standalone
Editorial test worker first, leaving FastAPI, Incidents, Vite and Cloudflare alone.
Identify its exact source DB and media directory; do not guess the newest TEMP
folder or bulk-copy TEMP. The copy command also refuses a source worker lock.

In PowerShell at the repository root:

```powershell
$editorialSourceDb = Read-Host 'Exact existing Editorial SQLite file'
$editorialSourceMedia = Read-Host 'Exact existing private media directory'
.\.venv\Scripts\python.exe -B -m app.editorial.storage --source-database $editorialSourceDb --source-media $editorialSourceMedia --destination 'D:\Apps\Tuburon\ATLAS\data\editorial\storage'
if ($LASTEXITCODE -ne 0) { throw 'Copy failed; stop and inspect privately' }
```

Destination must NOT exist. The tool:

1. Acquires only the source Editorial lock; opens its SQLite file read-only.
2. Validates integrity, foreign keys and Editorial-only tables.
3. Uses the SQLite online backup API from a consistent read snapshot, including
   WAL-visible records. Does not copy a bare active DB file or reset any state.
4. Compares every row of every Editorial table, preserving cursor, original
   Telegram group/operator references, versions, prompts and pending replies.
5. Copies every referenced original and preview; verifies source SHA-256/size,
   byte-identical copies, decodability and preview dimensions.
6. Checks destination schema and records table counts, DB size and SHA-256.
7. Renames only the NEW verified staging directory into the destination.

Source files are never moved or deleted. On failure, destination staging is
retained for private inspection and activation stops. Existing destinations are
never overwritten. Source and destination trees must be separate. Unreferenced
or temporary source files are not needed for recorded drafts and are not copied;
retain the entire original directory until the transfer is accepted.

Review `copy-receipt.json` privately, then test `/vista` against the destination
in an approved session before considering removal of the original. Do not run
two workers on source/destination copies of the same Telegram bot: their locks
protect separate DB paths, not bot-global polling. No reset of the update cursor
or automatic replay is part of the copy. Interrupted `sending` replies remain
uncertain on startup, as in Milestone 1; `/vista` can request a new response.

If there is NO existing draft to preserve, explicitly migrate a new dedicated
database instead. Do not create/migrate a fresh DB over the copied draft.

## Local configuration, without secrets

After verified copy, create `data/editorial/settings.json` containing JSON values
for `enabled` (initially false), `chat_id` (verified numeric group ID), and, if
needed, `database_url`, `media_root`, `permissions_file`, `download_limit_bytes`.
The durable paths above are defaults. Do not put tokens or secret fields in it;
unknown fields are rejected with private validation inputs suppressed.

Create/review `permissions.json` mapping the ONE initial operator's numeric ID
to `["artwork.submit"]` (or explicitly reviewed additional preparation permissions).
Use the same verified group/operator as the preserved draft. Do not embed IDs in
Python source. These files remain local and Git-ignored. A template can be
created in the later activation window without printing IDs or any token:

```powershell
$editorialGroupId = [long](Read-Host 'Verified Editorial group chat_id')
$editorialUserId = [long](Read-Host 'Verified operator user_id')
if ($editorialGroupId -ge 0 -or $editorialUserId -le 0) { throw 'Invalid numeric IDs' }
@{enabled=$false; chat_id=$editorialGroupId} | ConvertTo-Json | Set-Content -LiteralPath 'data/editorial/settings.json' -Encoding utf8
$editorialGrants = @{}
$editorialGrants[[string]$editorialUserId] = @('artwork.submit')
$editorialGrants | ConvertTo-Json | Set-Content -LiteralPath 'data/editorial/permissions.json' -Encoding utf8
```

Environment overrides the file, allowing `ATLAS_EDITORIAL_ENABLED=false` as a
process-local disable. `ATLAS_EDITORIAL_CONFIG_FILE` can select another private
nonsecret JSON file. The repository `.env` is not read by Editorial. Permissions
reload each worker cycle; other configuration changes apply at the next session.
Retire temporary environment overrides before supervised activation, or they may
take precedence over the durable settings.

## Supervisor and Windows lifecycle

`terminal.bat` is unchanged: existing three panes, existing sign-in mechanism.
Backend pane runs `app.dev_launcher`. After its OWN FastAPI listener becomes
ready, the supervisor can start one Editorial child if nonsecret configuration
explicitly enables it. It also manages Incidents under its existing policy.

Editorial has an independent maximum of 3 restarts, delayed 5/30/120 seconds.
Clean exit, configuration/credential error, duplicate worker or schema status
(0/2/3/4) stops Editorial without automatic restart. Unexpected exit 1 uses only
Editorial's budget. Database attempts/cursor are never reset. Editorial failures
do not restart FastAPI or Incidents. Disabled mode never loads its credential.

All children use the existing suspended-create/Windows Job ownership and
individual process groups. Shutdown requests Ctrl+Break for owned children;
the total grace remains 90 seconds, then Job cleanup reaps remaining descendants.
Backend exit ends its supervisor session and stops both dedicated workers.
Unexpected supervisor death invokes existing kill-on-close Jobs. No fourth pane,
new Windows startup task/service or change to Cloudflare/Operations is added.
Both token environment names are removed from Editorial's inherited environment;
the Incidents token keeps its existing child-only injection behavior.

## Separate operator-approved activation window

1. Verify the existing live stack/process ownership; stop only any old standalone
   Editorial worker, then complete verified copy and retain the source.
2. Enroll the dedicated credential locally under the sign-in account.
3. Review group/permissions and durable paths; keep publication unavailable.
4. Set `enabled=true` in the private settings only when ready. Do not start an
   additional worker or rerun all `terminal.bat` panes alongside the live stack.
5. With separate approval, hand off ONLY the backend pane to the new supervisor
   (or use the next planned normal ATLAS startup). Do not disrupt the other panes.
6. Verify one backend/Incidents/Editorial session, separate database ownership,
   and `/vista` of the preserved draft. Verify no extra bot consumer is running.
7. Later Windows sign-in reuses this same launcher/config/Credential Manager
   account. No token prompt is needed. Actual sign-in/Terminal-close activation
   remains untested against live services in this implementation step.

## Focused offline tests

```powershell
.\.venv\Scripts\python.exe -B -m unittest tests.test_editorial_integration tests.test_editorial tests.test_editorial_discovery tests.test_dev_launcher tests.test_incident_notifications
```

Only temporary databases/media, fake WinCred APIs and mocked Telegram. Native
Windows Job tests own disposable sleeping processes, never the live services.
