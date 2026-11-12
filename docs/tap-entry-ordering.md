# Tap entry ordering — explicit migration required

Default Tap mode keeps featured beers first, ordered by tap_position then ID.
Nonfeatured entries with tap_entered_at are newest first; equal times use position
then ID. Legacy null timestamps follow in their previous position order. No dates
are backfilled. Name, style and ABV modes are unchanged; TapGrid still selects at
most 16 after sorting and pads empty cells at the end.

tap_entered_at is a nullable UTC DateTime, exposed read-only in BeerResponse, not
accepted in BeerCreate/BeerUpdate. Naive UTC serialization is interpreted as UTC
by the frontend. Invalid/missing dates fall back to legacy ordering.

An entry means is_available=true AND is_deleted=false AND tap_position non-null.
Existing service paths are retained:

- Create with an explicit position enters Tap; create without one does not.
- PUT is_available=true assigns the first free position if necessary.
- PUT false removes the position.
- PATCH availability changes only the flag; no position is automatically assigned.

Each outside -> inside transition records a fresh time, including reactivation.
Already-inside activation, commercial updates and featured toggles do not stamp.
Leaving retains the last entry time until the next actual entry. Deleted beers
remain outside Tap. Existing allocation rules, position validation and featured
JSON behavior are not redesigned.

SQLite BEGIN IMMEDIATE serializes all existing create/activation service paths
before reading state or counting eligible beers. A seventeenth eligible row is
rejected with the existing capacity error, including PATCH/create with retained
or explicit positions. Already-open SQLite write transactions are rejected rather
than committing a caller's unrelated work. Current capacity is not an automatic
cleanup of historical overflow, and direct SQL writes remain outside this API.

## Deployment — not performed by this implementation

Operational sequence and recovery checkpoints:
[Production deployment runbook](tap-entry-deployment-runbook.md).

The running backend must not be restarted onto this ORM until the explicit catalog
migration has been approved and completed. create_all does not alter existing
tables. Without migration, ORM reads will fail on the missing column.

After a fresh verified backup and a separately authorized backend pause, run from
the repository using its venv:

```powershell
.\.venv\Scripts\python.exe -B -m app.migrations.tap_entry --database <approved-catalog-path>
```

The migration requires an existing SQLite file and beer table. It adds only a
nullable DATETIME column with no default, under BEGIN IMMEDIATE; it never recreates
the table or writes historical rows. Rerunning validates the existing column and
does nothing. Historical nullable BOOLEAN/TEXT schemas are supported without
trying to repair unrelated ORM/schema differences. Incompatible existing columns
fail and roll back. There is no automatic startup migration.

Verify original rows/values, null entry timestamps, other schemas, integrity and
foreign keys, then restart only through the existing approved workflow. Revalidate
physical identities for the commercial capability if a database is replaced.
Rehearse on a disposable copy first. No production migration, configuration change,
service restart or Telegram operation is authorized by this implementation phase.

The browser needs fresh catalog data. Backend SQL ordering remains positional;
the default frontend comparator owns the entry ordering. Existing BeerDetail
navigation snapshots may retain an older list until reopening/reloading.
