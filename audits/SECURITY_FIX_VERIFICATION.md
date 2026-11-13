# Security and integrity fixes — 13 November 2026

The original findings in AUDIT_REPORT.md and LOAD_REPORT.md are historical
reproductions. The following protections are now implemented; they are not a
claim that every possible application vulnerability has been eliminated.

Deployment status: fixed in the working tree, not applied to the default instance
databases yet. A read-only inspection found no auth_id column, request fingerprint
columns or movement guard triggers there. Back up the databases and restart the
application to apply the additive upgrades and invalidate old login cookies.

| Original finding | Implemented protection |
| --- | --- |
| Public fallback login secret | Private persistent mode-0600 installation signing key, atomically published; the former public fallback and short configured secrets are rejected. |
| Deleted user ID reused | Random per-account login identity; numeric old cookies rejected. Account creation also avoids IDs retained in the user audit history. |
| Password reset retains sessions | Password changes rotate the login identity. Existing cookies must log in again. |
| Disable/enable revives sessions | Both state changes rotate the login identity; role changes also revoke old sessions. |
| SQLite foreign keys inactive | Foreign keys enabled on every main/users connection. |
| Invalid/orphan movement inserts | SQLite insert/update validation triggers enforce integer bounded nonnegative quantities, direction, fixed bundle types and valid job references. Referenced jobs cannot be deleted or renumbered. Unassigned legacy IN rows and zero-piece cancelled returns remain supported. |
| Oversized jobs break reports | Piece limits at creation/correction boundaries; exact-integer SQLite aggregate for oversized historical piece totals. Existing historical rows are not rewritten. |
| Changed-data retry reports success | Request fingerprints reject changed content with a conflict. Setup, job/return, financial, edit and account write paths have matching protections. Unverifiable legacy claims do not report success for changed/new data. |
| Lost response loses job details | Original job/return receipts saved in the same transaction; identical retries restore the receipt without duplicating the save or server CSV export. |
| Heavy-load save errors | WAL, busy timeout, serialized fresh write boundaries, larger dual database pools, retryable 503 responses and preserved retry tokens. Busy errors no longer blame duplicate names. |

Additional follow-up hardening: schema creation/upgrades serialize their inspection
and DDL, so concurrent application starts cannot assign different authentication
identities to the same legacy user. Failed upgrades roll back DDL and data.
Unique-claim races recheck the winner's payload, and an unrelated integrity error
cannot masquerade as duplicate success. Account-change fingerprints use a keyed
HMAC so password-bearing requests do not leave a fast unkeyed password digest in
the audit database. Historical return-workspace totals use exact integer sums too.

## Verification

- Normal test discovery includes the original audit expectations and the expanded
  security-hardening regression suite, including 101 concurrent identical/changed
  same-key submissions that save exactly one job.
- Security coverage includes a forced numeric-ID reuse (not just service-level
  non-reuse), fresh login after password reset, stale-cookie revocation, pooled
  foreign-key enforcement, independent movement-rule violations, migration data
  preservation, immutable retry snapshots and historical SUM overflow.
- Earlier complete load-fix evidence remains in LOAD_FIX_VERIFICATION.md. An
  earlier security rerun was interrupted by the drive disconnect. That round
  remains historical; it has now been followed by a completed 37-scenario round
  and targeted reruns. Latest accepted coverage is 37 scenarios / 37,037 requests,
  with no HTTP 5xx, transport failures, captured database errors or failed
  invariants. See [SECURITY_LOAD_VERIFICATION.md](SECURITY_LOAD_VERIFICATION.md).
- The 48 measured waves / 48,048 requests include the original 8 cutter and 2
  supplier retryable lock-timeout responses. Those failures are not hidden or
  relabeled: the read-only replay correction was then tested across all eight
  affected retry paths, all of which passed. Account-fingerprint and historical
  return-assignment follow-ups also passed. The acceptance table links every
  scenario to its actual latest evidence file.
- Fresh retained-product load evidence: `load_kept_products_verified.json` records
  two 1,001-client waves with 32 server workers, both passing with no HTTP 500,
  transport, captured application or database errors. Each wave leaves exactly
  one retained-stock record, one ₹240 recovery, 48 physical returns, 2 retained
  pieces, zero remaining pieces and 50 payable pieces.
- The first retained-product load verifier used an expired, detached worker test
  object. That harness failure is retained in `load_kept_products_results.json`;
  the verifier now reloads the worker by ID. Only the separately named verified
  result file is accepted as fresh load evidence.

Completed final verification: 238 Python cases discovered, 228 passed and 10
optional browser cases skipped in normal discovery. All 10 Firefox cases passed
separately, including retained-stock recovery through actual payroll confirmation
and lost-response receipt restoration. The 19 kept-product cases and original
security regressions are included in the full suite. The original 12 audit
regressions also passed independently. Six JavaScript programs
also passed. All mutation tests use temporary databases; printers are mocked or
output goes to temporary folders. Production data is not populated by these tests.

The final duplicate-request check also holds an unrelated SQLite writer lock
while replaying a committed job request: the original receipt still returns
without acquiring a writer lock. New requests continue to acquire the writer
lock and recheck their claim after acquiring it, so read-only replay does not
weaken first-write race protection. Original database contention attempts are
preserved separately from successful targeted reruns.

## Rollout

Restart the application to load the code and additive upgrades. Back up both
databases first. All pre-upgrade numeric-ID login cookies become invalid and
users must log in again. Keep the private `.session-secret` with installation
backups and never commit it. If APP_SECRET_KEY is configured to the former public
value, remove that override or replace it with a strong private random secret.

No production server was restarted as part of verification. Existing records are
preserved; constraints protect new/updated records, not a destructive automatic
repair of historical data. CSV export remains post-commit with failure warnings,
not a durable print-delivery queue. See KEPT_PRODUCTS.md for retained-stock
recovery usage, immutable price snapshots and correction-lock limitations.
