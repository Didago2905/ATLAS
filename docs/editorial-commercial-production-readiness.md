# Commercial production readiness (not activated)

The existing Editorial process may execute a newly confirmed commercial update
after its inbox transaction closes. No dispatcher, timer, consumer or startup scan
is added. Default settings leave commercial_execution.enabled false. Existing
isolated execution and its path guards remain unchanged.

## Future activation prerequisites

Obtain separate operational approval first. Back up both SQLite databases using
consistent backups; verify integrity and receipts, and document recovery. Prepare
the existing editorial_commercial_applications table explicitly in the catalog
with a separately approved additive migration. Startup validates it and never
creates it. Verify write permissions, journal/locking behavior and backup recovery.

The private Editorial settings accept a nested commercial_execution object:

```json
{
  "enabled": false,
  "activation_id": null,
  "not_before": null,
  "editorial": null,
  "catalog": null
}
```

Before future enablement, configure a newly generated UUID activation_id, an aware
UTC ISO timestamp not_before, and two exact file targets. Each target is an object
with canonical absolute path, numeric device (stat.st_dev) and inode (stat.st_ino).
These must be recorded from the approved existing files, not inferred from their
names. Both files must already exist, be distinct and private, with no hardlinks.
The Editorial engine and catalog_database_url must match these identities exactly.
Replacement/restoration requires a fresh identity review and activation UUID.
No credentials belong in this configuration.

Only a complete explicit capability allows the production branch of the existing
applicator. Its isolated guard still handles all calls lacking that capability.
File identities are revalidated before execution and inside transaction guards.
The worker loads current permissions for each guard; beer.edit and
beer.commercial.apply are required in addition to the existing bot access grant.
No grants or real configuration are changed by this increment.

Restart of the existing worker through the normal supervisor is a future approved
operational step. Do not start a second consumer. Use /rapido22 for one confirmed
existing beer and one price, conserve it, then /aplicar22 and final confirmation.
Reviews made before activation must be reviewed again. New requests bind the
activation UUID, approval timestamp, exact proposal/revision and commercial digest.
Old requests lacking this binding, from another activation or predating not_before
are rejected. No historical queue is automatically replayed.

## Explicit recovery

The confirmation response includes the request UUID. After interruption, an
authorized owner can send `/recuperar22 <request UUID>` in the authorized group.
This selects only that owner's exact request, commits/closes the inbox transaction,
then invokes the same executor. Wrong owner, grants, activation or target fails
closed. Current grants are checked before receipt reconciliation. A matching
persisted receipt is reconciled without another write, including after approval
expiry; expiry/revision checks prevent new application when no receipt exists.
Existing lease, backoff and three-attempt limits remain in force. An active lease
requires waiting, not forcing a second attempt. No timer retries the request.

Only an actually verified catalog receipt produces an application-success response.
If receipt verification is unavailable, stop and inspect before another attempt.
/recibo22 remains the read-only receipt view for the last reviewed authorization.
Turning enablement off blocks execution/recovery; preserved data is not requeued.

## Limits

This prepares code only: no production receipt migration, configuration changes,
grants, backup creation, Telegram calls or restarts are performed. The capability
is internal trusted Python state, not a sandbox against malicious local code.
Tests use disposable databases exclusively. Production filesystem/SQLite locking
and the controlled SQL -> public catalog -> BeerDetail check still need an approved
rollout rehearsal. No price update changes availability, Tap slots or Museum.
