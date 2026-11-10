# Editorial V2.2: Carta identity only

`/carta22` is an explicit opt-in entry point, separate from `/obra` and the
V2.1 interview. It uses the existing `artwork.submit` grant, group restriction,
durable inbox/outbox, and one-draft-per-chat-and-operator policy. An active
draft must be cancelled explicitly before starting a different case. Existing
assets and proposal revisions are retained, never assigned to the new case.

## Configuration (not activated by this change)

The dedicated Editorial settings accept optional `catalog_database_url`, or
`ATLAS_EDITORIAL_CATALOG_DATABASE_URL`. Supply an explicit existing SQLite file
URL for the operational catalog. No general ATLAS configuration, `.env`, engine
or credentials are imported. Without this option `/carta22` creates no case.
The reader uses SQLite `mode=ro`, query-only mode and a SELECT authorizer.
Do not point tests at operational storage.

## Flow

1. `/carta22` creates a data-only, incomplete V2.2 proposal and asks for a name
   using ForceReply. Unsolicited group messages and replies to old prompts cannot
   answer the question.
2. Exact/case-accent-normalized full-name lookup returns at most three records.
   Unavailable beers remain eligible; soft-deleted beers are excluded. Each
   candidate shows its name, brewery, style and availability. No fuzzy or Museum
   lookup occurs.
3. Confirm a numbered candidate, search again, or cancel. Selection re-reads the
   offered ID and checks its original identity/availability/deletion flags.
   Missing or changed records require a new search and confirmation.
4. Confirmation appends an immutable proposal revision containing the SQL ID,
   identity snapshot, bound fingerprint and human update reference. It creates
   no proposed commercial action or approval. `/vista`, `/continuar` and the
   read-only `/resumen` show the result; `/cancelar` closes the case.

Interview state and offered candidates live in the existing Interview JSON
envelope. Callbacks bind case UUID, interaction version and content revision;
another operator cannot use the owner's buttons. Restart recovery reuses the
persisted offered set and still revalidates the selected record. No schema
change is required. Catalog errors are sanitized and preserve the draft.

This increment does not edit commercial fields, ingest images, link Museum
artwork, approve publication or execute catalog changes. Catalog rows lacking
valid name/brewery/style cannot be confirmed. Identity may change after this
read-only confirmation; any future publishing flow must revalidate the stored
fingerprint against its own transaction snapshot.
