# Safe Editorial Telegram ID discovery

Standalone, explicitly invoked diagnostic; no worker, settings, permission map,
database, files, downloads, publication or service activation. It reuses the
bounded Editorial HTTPS transport without changing that transport or its worker.

## Operator procedure

1. Keep the Editorial worker and all other consumers of this bot's updates
   stopped. Leave Operations/Incidents and the ATLAS stack alone.
2. Add the dedicated Editorial bot to the intended private group. Keep privacy
   mode enabled. Use your personal account, not anonymous admin/send-as-channel.
3. In a local interactive PowerShell terminal, run:

   ```powershell
   Set-Location 'D:\Apps\Tuburon\ATLAS'
   .\.venv\Scripts\python.exe -B -m app.editorial.discover_ids
   ```

4. Enter the dedicated token at the hidden prompt. Never paste it into a command,
   chat, file or environment variable. The tool verifies `getMe` and refuses an
   active webhook without modifying it. It displays only the verified username.
   Check that it is the Editorial bot you intended before continuing.
5. Enter a fresh identification code locally: 8–64 ASCII letters, digits, `_` or
   `-`. Do not reuse the example below. In the intended group, send one NEW text
   message addressed to the exact verified username, followed by one space and
   the exact code. Example with fictional values:

   ```text
   /identificar@ATLAS_TestEditorialBot DISCOVERY_TEST_8472
   ```

   Do not forward it, edit an existing message, send it as a caption or use an
   anonymous identity. Then return to the local terminal and press Enter.
6. Expected successful output (fictional IDs):

   ```text
   bot_username: @ATLAS_TestEditorialBot
   chat_id: -123456
   chat_type: group
   user_id: 789
   ```

   A supergroup prints `chat_type: supergroup`. No group title, person's name,
   message text, token, HTTP response or API URL is printed. These numeric IDs
   are only discovery results: the tool grants no permission or access.

## Failure behavior

- No match: keep the worker stopped, send the correctly addressed command/code
  and rerun. No pending update is discarded. Use a fresh code if sending a new
  identification message, to avoid multiple matches for the old code.
- Multiple matches: use a new code and exactly one new message; do not guess
  which identity to authorize.
- Forwarded/anonymous/channel/bot sender or edited/channel post: rejected.
- Active webhook: stop and review that bot's existing setup separately. This
  utility never deletes webhooks or calls `drop_pending_updates`.
- Full 100-update window: stop for separate backlog review. The diagnostic
  deliberately cannot paginate by advancing an offset or drain the backlog.
- API/connection/malformed-response errors: fixed sanitized error, no raw detail.
- Hidden input unavailable, redirected input/output or unexpected arguments:
  refuse before requesting a token or making a network call. Getpass's echoing
  fallback is explicitly refused. Do not run through a pipe or logging wrapper.

Success exits 0; discovery rejection/no match exits 1; terminal/configuration/API
failure exits 2; Ctrl+C exits 130. The shared transport has response bounds, so a
large pending batch may safely fail rather than exposing or dumping it.

The tool calls only `getMe`, `getWebhookInfo` and `getUpdates` with
`{"timeout":0,"limit":100}`. It never supplies an offset or `allowed_updates`,
acknowledges updates, sends a Telegram message or creates a polling loop.

The token is held only in Python memory as a `SecretStr`; it is never assigned
to `os.environ`. No child process is created, so no token-bearing environment is
passed to children. HTTP wire debugging is disabled on diagnostic connections.
Memory is not promised to be physically erased, but the references are released
at exit and no token is persisted. No Credential Manager entry is read/written.

## Offline tests

```powershell
.\.venv\Scripts\python.exe -B -m unittest tests.test_editorial_discovery
```

Tests use mocked Telegram responses and synthetic tokens; no live API,
credentials, database or services are needed. A successful discovery does not
authorize starting the worker; follow the separate isolated activation procedure
with the verified IDs and a private permission map afterwards.
