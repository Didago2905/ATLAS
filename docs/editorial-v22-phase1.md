# Editorial V2.2 — Phase 1 foundation

This increment introduces pure contracts and editing utilities, not the complete
Telegram V2.2 experience. No catalog/Museum reader, vocabulary matcher, publication,
approval, Tap activation, service restart or live migration is included.

## Contracts and compatibility

`proposal.validate_proposal(payload)` dispatches by `schema_version`. The original
`Proposal` class remains the 2.1 validator, including its historical default for a
missing version. `Proposal22` requires an explicit `2.2`; unknown versions fail
without echoing the payload. Validation never upgrades or rewrites stored data.

The 2.2 contract has a stable case UUID, intake origin, content revision and:

- `beers`: new candidates, confirmed-existing assertions, or unresolved identities.
- `artworks`: stable IDs, private asset/Museum sources, independent roles and Museum
  metadata, represented subjects, and separate `used_for` beer identity references.
- `actions`: commercial changes, operational card replacement, Museum registration,
  existing Museum reuse and proposed artwork/beer relationships. No action executes.
- `vocabulary`: raw operator input (including whitespace), lookup key, candidates,
  field-specific provenance, decision and interaction reference. No lookup,
  normalization or fuzzy matching is performed here.
- `readiness`: incomplete, technically_valid or prepared_for_review.

Existing beer assertions require a positive SQL ID, identity snapshot, fingerprint
and explicit human interaction reference. The fingerprint binds the beer ID to the
exact snapshot, including optional source record version. `assert_identity_current`
compares an in-memory current snapshot/ID. This phase cannot independently prove a
reference exists or an interaction happened; Phase 2 must obtain them from trusted
readers and authorized interactions, never treat text similarity as verification.

Museum sources require a UUID and accept an optional expected hash. Private assets
use existing 32-hex identifiers. Structural validation rejects dangling references,
duplicate IDs/sources and incompatible actions. One artwork may have multiple roles
and uses; brewery-only representation does not create represented beer subjects.
Empty semantic products and unknown subjects remain valid for historical works.

## Sparse patches

`patches.CommercialPatch` accepts only the eight commercial scalar fields and the
five known price keys. Every supplied field has a discriminated intention:

| Intention | In-memory application |
|---|---|
| Missing | Preserve current data |
| keep / skip / unknown | Preserve current data |
| set | Replace only the specified field/key; explicit numeric zero is retained |
| clear | Require a trusted caller's explicit `allow_clear` path |

Explicit null is not an intention and is rejected. Clearing name, brewery or style
is not supported. Clearing an optional scalar sets null; clearing a price removes
only that presentation. No-op price patches do not materialize an empty price object.

`apply_commercial_patch(original, patch, allow_clear=frozenset(...))` deep-copies the
input and never calls the operational update service. Existing other price keys,
images, availability and featured fields are preserved. The trusted caller owns
the clear policy; it is not a permission granted by the submitted patch.

`correct_patch_field` validates one interview answer. keep/skip/unknown preserve
previously entered intentions as well. Changing/removing an intended change needs
an explicit correction; an omitted answer cannot discard it.

Prices are strict finite numeric values in 0–1,000,000; ABV 0–100 and IBU 0–2000.
Numeric booleans and strings are rejected in patches. These bounds are preparation
validation, not restaurant approval or automatic publication policy.

## Isolated navigation

`navigation_v22` is independent of the legacy handler. Stable paths contain object
UUIDs rather than list positions. Reconciliation removes history entries that no
longer exist after a branch/subject correction. Invalid current paths fall back to
a valid historical question or the first valid path.

`NavigationState.interaction_version` changes on navigation/resume/correction.
`Proposal22.revision` changes only when content changes or an explicit preparation
transition is accepted. A callback must match case, interaction version, content
revision and a currently valid path. An answer must match the current field.

The state roundtrips as JSON. The existing SQLite schema can store an envelope in
`Interview.history`, with `Interview.step="v2.2"` and its existing integer revision
used for the interaction version. A temporary-database test exercises this layout.
No production adapter creates these records automatically in this phase. No schema
or migration code is changed.

The existing 2.1 state machine is intentionally retained, including its legacy
navigation/content coupling and omission semantics. Existing interviews are not
forced into the new engine. Phase 2 must add a deliberate versioned interaction
adapter rather than changing interpretation of historical history arrays.

## Readiness and runtime boundary

Structural validity does not mean complete, approved or published.
`assess_readiness` checks preparation requirements; `prepare_for_review` requires
an explicit interaction and expected current revision. It records a closure bound
to that content fingerprint. Editing content invalidates the closure and reopens
the proposal. None of these utilities approve or publish anything.

The running Telegram command set still creates/resumes 2.1 interviews. Read-only
`/resumen` supports both versions. The legacy editor rejects 2.2 or unsupported
contracts before image downloads or draft mutations; inbox/outbox records may still
record the rejection. Existing proposal snapshots and assets remain untouched.

## Verification

Run from the repository, using isolated fixtures and fake transport:

```powershell
.\.venv\Scripts\python.exe -B -m unittest tests.test_editorial tests.test_editorial_interview tests.test_editorial_integration tests.test_editorial_discovery tests.test_editorial_v22 -q
git diff --check
```

Remaining work: trusted read-only identity/artwork adapters, vocabulary suggestions,
visual candidate confirmation, the image-first Telegram UI, compact correction
menus and explicit operator flow for closing a case. No runtime activation is
authorized by this increment. Rollback must retain a reader for any 2.2 records
created later; old 2.1-only code cannot safely edit them.
