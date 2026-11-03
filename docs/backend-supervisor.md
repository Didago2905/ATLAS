# Canonical development backend supervisor

The supervisor is integrated with the canonical launcher. Incidents is disabled
by default in a fresh checkout; each deployment explicitly enrolls its dedicated
credential and enables delivery in private local configuration. The local
integration has been verified, including automatic delivery of a real report.
No credential, report content or local runtime state is versioned.

## Entry point and ownership

`devtools/launcher/terminal.bat` remains the canonical launcher and existing
Windows sign-in target. Only its backend-pane command changed to:

```powershell
python -B -m app.dev_launcher
```

Vite and Cloudflare/Operations pane commands are unchanged. No additional Windows
startup task, service or schedule is installed. Alternative launchers and direct
manual Uvicorn execution do not start Incidents.

The versioned `app/dev_launcher.py` owns its own FastAPI child and optional
Incidents child. It refuses startup if port 8001 is occupied. After creating
FastAPI it checks that the listening PID belongs to its own cleanup job, not an
unrelated server that won a port-binding race. It never adopts or kills an
existing listener. Backend command remains the project interpreter running
`-m uvicorn app.main:app --host 0.0.0.0 --port 8001` from the repository root.

With `TELEGRAM_INCIDENTS_ENABLED=false`, only FastAPI starts. No Credential Manager
lookup or worker launch occurs. FastAPI receives an empty dedicated-token variable
and disabled Incidents flag, overriding `.env` too. The supervisor does not import
`app.main`, create tables, run migrations or access report contents itself.

With explicit enablement, after backend readiness the supervisor reads
only the dedicated Credential Manager entry and starts continuous
`python -B -m app.workers.incident_notifications`. Destination and attempt policy
come from dedicated settings; Operations configuration is never read. The token
is copied into only the worker child's environment, never its arguments, backend
environment, global `os.environ`, repository files or logs. Native environment
buffers are cleared after creation. Python strings cannot be guaranteed to be
physically wiped from memory; same-account malware/local administrators are
outside this protection boundary.

## Singleton and restart policy

Every enabled worker CLI, including `--once`, holds a nonblocking OS file lock
adjacent to the canonical SQLite file for its entire lifetime. Path/case aliases
resolve to the same file. A second worker exits 3 before claiming reports. The
lock releases on process exit/crash; its small runtime file remains and is
Git-ignored. File presence does NOT imply a live worker. Do not delete a lock file
while contenders exist. The database file itself is not changed by locking.

The supervisor allows at most three worker restarts after the initial launch,
with 5, 30 and 120 second delays. It never resets database delivery attempts.
Credentials are reloaded on each start so future rotation needs no prompt at
every ATLAS startup. Exit 0 (clean/disabled), 2 (configuration), 3 (duplicate) and
4 (schema) are not restarted. Missing credentials, startup failures, or exhausted
restart budget leave FastAPI running. Backend exit ends this supervisor session
and stops its worker. No sent report is requeued.

## Windows cleanup

`app/core/windows_children.py` creates each owned child suspended, assigns it to
an outer kill-on-close Job Object and isolated subtree Job, then resumes it.
Cleanup handles are non-inheritable. Abrupt supervisor death closes the handles
and kills owned descendants. A failed worker launcher also closes only that
worker's subtree before restart, reaping surviving interpreter descendants without
terminating FastAPI. No cleanup targets global process names or unrelated PIDs.

Children share the backend console in separate process groups. Supervisor
Ctrl+C/SIGTERM/Ctrl+Break requests shutdown; it sends targeted Ctrl+Break to owned
worker/backend groups, waits at most 90 seconds total, then closes the jobs. The
worker now handles SIGBREAK gracefully. Do not replace this with
`CREATE_NO_WINDOW`, which removes the console needed for group signaling.
Job cleanup handles terminal close, hard termination and grace timeout. Existing
database leases recover uncertain in-flight attempts after crashes.

Modern Windows with nested Job Objects is required. Failure to establish cleanup
aborts startup; there is no detached-process fallback. Closing only a frontend or
Cloudflare pane does not end the backend session. Closing/stopping the supervised
backend pane does.

## Credential enrollment

`app/core/incidents_credentials.py` uses exactly one Generic Credential:
`ATLAS/Incidents/BotToken`, persisted for the current Windows user on this machine.
It never enumerates entries or reads Operations credentials. On a new deployment, enroll once in a local terminal:

```powershell
.\.venv\Scripts\python.exe -B -m app.core.incidents_credentials enroll
```

Input is hidden; noninteractive enrollment is refused. It makes no network calls
and does not enable delivery. The same command can replace a rotated token. The
existing sign-in launcher must use the same Windows account. Missing/invalid
credentials yield fixed status messages and leave FastAPI available. Do not enable
HTTP wire/debug logging.

## Setup and verification

The narrowly allowlisted launcher source and its Operations/QR dependencies are
versioned. Private configuration, generated QR, tunnel runtime and logs stay
ignored. `devtools` uses Python namespace packages; no package initializer is
required. Install the already-used dependencies with:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
cd frontend
npm ci
```

The canonical batch currently targets `D:\Apps\Tuburon\ATLAS`. A checkout at a
different location needs its local batch paths adjusted. Windows Terminal (`wt`),
`cloudflared` on PATH and the project virtual environment are prerequisites.
Existing Operations behavior additionally requires a private `devtools/config.json`
with `telegram.bot_token` and `telegram.chat_id`; obtain those through the existing
Operations setup. Never commit that file or substitute Incidents credentials.
Do not execute the Operations module as a configuration test: it sends messages.

For Incidents, enroll the dedicated credential through the hidden-input command
above. Put only nonsecret settings in the private local environment/`.env`:
`TELEGRAM_INCIDENTS_ENABLED=true` and the dedicated numeric
`TELEGRAM_INCIDENTS_CHAT_ID`. Keep the token out of `.env`; the supervisor loads it
from Credential Manager into only the worker environment. Credentials must be
enrolled separately under the Windows account used to launch ATLAS.

Before enabling a new deployment, verify the intended database backup, delivery
migration, destination and pending backlog. Existing sent reports stay excluded.
Do not run the full `terminal.bat` while its other panes are already active.
Do not register another Windows startup mechanism; keep the existing sign-in
entry pointing at the canonical batch.

Focused tests use fake credentials and temporary SQLite databases. Windows Job
tests create only disposable sleeping processes:

```powershell
.\.venv\Scripts\python.exe -B -m unittest tests.test_dev_launcher tests.test_incident_notifications tests.test_issue_reports
```

Local verification covered backend handoff, shared database ownership, live
singleton rejection, API/catalog/proxy health and automatic delivery of a new
real report without worker restart. Vite, Cloudflare and Operations were left
running. Disposable tests cover graceful shutdown requests, owner-death cleanup,
worker failure isolation and bounded restarts. Actual next-sign-in and physical
Windows Terminal/ConPTY closure were not exercised against the live stack.
