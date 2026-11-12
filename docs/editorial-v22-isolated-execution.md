# Commercial execution: isolated post-commit boundary

Production execution remains disabled. The normal worker has no execution scope,
environment switch, or dispatcher enabling writes. Final authenticated confirmation
queues a request; approval alone is never reported as application.

## Transactions and authorization

Requests live in the existing private Interview.history.execution_requests map;
no schema migration is required. They bind the operator/chat, exact saved case and
revision, approval UUID, target identity, baseline/patch digest, catalog path digest,
expected changes, originating response and a 15-minute expiration. Saved-case and
legacy navigation preserve this map.

The Telegram inbox transaction commits and its Session closes before execution.
The executor claims the request in a separate short transaction, closes it, then
calls the existing transactional applicator. Its attached-source transaction
revalidates proposal/revision, ownership, complete baseline, patches and SQL values.
Additional guards recheck the immutable request binding, lease, expiration and a
fresh authorization loader before writes and commit. Both beer.edit and
beer.commercial.apply remain mandatory; no permissions are granted here.

## Isolation

Tests explicitly create a sealed in-memory capability using an actual standard
library TemporaryDirectory, two distinct existing SQLite files and their exact
canonical paths/device/inode identities. Every use revalidates this allowlist;
hardlinks and the repository's databases are rejected. Filename checks alone do
not authorize execution. Receipt schema setup is explicit and isolated, never
automatic. This is an internal trusted-test capability, not a security boundary
against arbitrary Python code with filesystem access.

## States and recovery

- pending: approved, no application established.
- executing: claimed with a 60-second lease and incremented attempt count.
- applied: actual persisted receipt has been read and verified.
- conflict: terminal SQL baseline conflict; requires fresh review.
- expired: terminal approval expiration before application.
- failed: sanitized error code plus explicit retryable flag.

Retryable execution failures have a 30-second backoff and at most three application
attempts. Revoked grants, invalid proposals/bindings and inconsistent receipts are
terminal. No retry changes delivery attempts or permissions. There is no automatic
production retry loop. A trusted isolated caller can invoke execute_request again
after restart using a new capability for the same temporary files.

Every recovery first checks the catalog-local, atomically committed application
receipt. It verifies identity, authorization reference, digest, exact changes and
application time within the approval interval. This reconciles a crash after SQL
commit without reapplying, even if authorization later expires or is revoked.
Before-commit failures roll back through the existing applicator. Expired leases
can be reclaimed; stale executors cannot replace a newer lease with a failure.

Only verified receipts can replace a still-pending Telegram response with success.
Already delivered history is preserved; /recibo22 reads persisted receipt data.
No exception text, credentials or transport payload is stored in request errors.

## Remaining rollout decisions

Production capability/configuration, a separately reviewed dispatcher, retention
and bounded archival of request JSON, real migrations for receipt storage, operator
grant policy and operational monitoring remain outside this increment. No live
catalog, Editorial storage, Telegram, Museum or Tap List is touched by these tests.
