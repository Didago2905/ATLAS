# Editorial V2.1 — Persistent interview foundation

Preparation only: no publication, catalog reads, availability/featured changes,
slot assignment, or calls to upload/publishing services. Existing permission and
credential configuration is unchanged.

## Storage and explicit upgrade

Storage schema 2 adds `editorial_proposals` (immutable, uniquely numbered JSON
snapshots per draft) and `editorial_interviews` (current question, revision token,
bounded back history). Contract version is `2.1`, separate from database version.
Every accepted answer/navigation transition and image receipt has an atomic
snapshot in the same transaction as the existing durable inbox/outbox. Invalid
answers and stale buttons cannot advance it. `/resumen` does not change proposals
or interview progress. It bypasses the durable inbox/outbox entirely: no Update,
Reply, cursor change or draft initialization is stored. Its polling offset and
bounded duplicate suppression exist only in memory. Summary delivery is best effort;
a failed response is not automatically retried, and an unacknowledged summary may
be answered again after restart. Other commands retain durable recovery rules.

The explicit migration validates the complete old schema before adding either
table. It changes only the cursor schema version; old draft/image versions, assets,
reply history, update cursor and files are preserved. Partial schemas fail closed.
The worker does not migrate automatically and refuses schema 1 on a future start.
The storage-copy utility supports either full schema without upgrading its source.

No live migration or service restart is part of this implementation. A later,
operator-approved maintenance step must stop Editorial, make a verified private
backup and run (from the repository, using the configured Editorial path):

```powershell
.\.venv\Scripts\python.exe -B -m app.migrations.editorial --database D:\Apps\Tuburon\ATLAS\data\editorial\storage\editorial.sqlite3
```

Do not run against atlas.db. CLI rejects that filename/private-path violations
and takes the same Editorial singleton lock. Test the backup copy first. Restart
only after verification/approval. An older worker must not run against the upgraded
database; code rollback needs the matching pre-upgrade Editorial backup, with an
explicit decision about any newer interview data (never restore automatically).

## Operator flow

- Existing `/obra`, attachment validation, private originals, actual image preview,
  operation classification and `/vista` remain available. Legacy assets acquire
  no invented role or subject. `/vista` remains the image preview.
- `/entrevista` starts from a selected operation or offers permitted operations.
  It also works before an image exists. Destinations are explicitly selected;
  operation permissions are checked on each modification.
- Buttons choose destinations, collection, future activation intent, artwork role
  and subject. Reply directly to the bot's question for short text or numbers;
  Telegram privacy mode stays enabled. Text is projected only from bounded replies,
  not ordinary group conversation. Use **Omitir** to leave fields missing, including
  required fields; the proposal then remains incomplete. **Atrás** revisits a step.
- `/resumen` reads current proposal/validation; legacy/no-proposal drafts receive an
  invitation to start an interview, without initializing anything. `/corregir` selects a field to edit,
  `/continuar` resumes, `/cancelar` closes without deleting the proposal; resume
  restores it. Summaries shorten long field values for Telegram; full values remain
  in private immutable snapshots.
- `/obra` can receive another independent asset. Explicitly assign each received
  image to beer card, board, or label and select beer/brewery/multiple/unknown as
  its subject. Replacing one role preserves the other roles and all older revisions.
  A brewery board never supplies a beer name automatically.
- Museo has optional title/year/collection and a separate semantic product interview.
  It never copies operational beer data into semantic products. Entered semantic
  fields retain `unknown` confidence; this milestone has no verification/approval.

## Contract and limits

`Proposal` rejects extra fields, including operational availability/featured/slot
flags. Targets: beer_create, beer_update, beer_artwork, museum, constrained by
operation. Existing beer IDs are manually supplied positive integers, **unverified**
without catalog access. `valid` means preparation fields pass validation, not that
publication is approved or a target exists.

Beer name/brewery/style are required for creation; incomplete drafts use null.
Optional origin/color/description/ABV/IBU and exactly five nullable prices are
supported. Zero is preserved distinctly from missing. ABV 0–100, IBU 0–2000;
prices finite 0–1,000,000, numeric booleans rejected. Text limits match catalog
identity bounds; description 800 characters for short Telegram responses. Images
reuse existing validation, 15 MiB configurable transport limit and shared optimizer.
No second image pipeline.

Museum semantic data is a proposed typed contract, not the serialized public
Museum record: publication will need its existing nested metadata serializer and
confidence/evidence validation. The contract accepts up to 20 products and bounded
collaborators, but the minimal chat interview currently edits **one** product's name,
style, brewery and origin. Rich confidence/evidence/collaborator and multiple-product
editing, artwork removal, approval, target lookup, concurrent publication checks,
publication journaling and operational mutations remain future work.

## Controlled operation corrections

Once a proposal or interview exists, every legacy `op:` or `start:` operation
selector is rejected, even when its image revision is current. Use `/corregir`
→ **Cambiar operación**, select the operation and confirm it. Both the selection
and confirmation use the current proposal/interview revision, active draft state
and operation permission; permission is checked again when confirming. Changing
operation preserves entered metadata and artwork roles in a new immutable snapshot,
clears publication targets and asks the operator to select compatible targets again.
It does not reinterpret or rewrite legacy image versions. Existing V1-only operation
selectors remain usable until an interview is created.
