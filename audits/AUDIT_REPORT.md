# Application audit — 12 November 2026

Follow-up: these are the original findings. Implemented corrections and current
verification are documented in [SECURITY_FIX_VERIFICATION.md](SECURITY_FIX_VERIFICATION.md).
All ten listed findings have source fixes and passing targeted checks. Deployment
still requires backing up the databases and restarting the application.

Scope: current Flask V2 application, authentication, account lifecycle, data entry,
SQLite constraints, retries, concurrent writes, returns, payroll/advances, reporting,
rendered templates and existing JavaScript checks. This is a targeted audit, not a
claim that every possible weakness has been found. Production entry databases were
not used by the tests; fixtures use temporary databases and mocked printer calls.

## Confirmed findings

| Priority | Finding | Evidence and impact | Recommended correction |
| --- | --- | --- | --- |
| Critical | Repository fallback signing secret permits admin impersonation | `app.py:12` uses a fixed secret when `APP_SECRET_KEY` is unset. A cookie signed using that fallback and an existing admin ID opened `/users` with HTTP 200 without login. Confirmed in the default test configuration; a separately configured strong production secret mitigates this finding. | Require an external unpredictable secret, rotate existing secrets and invalidate existing sessions. |
| Critical | Deleted user ID reuse lets an old cookie become a different account | Delete the highest-ID operator (#2), create an administrator, then replay the operator cookie. SQLite assigned #2 to the administrator; `/users` returned 200 to the old operator session. `User.id` is the login identity and has no generation identifier. | Use immutable random authentication identities/session generations; invalidate identities on deletion. Prevent ID reuse as additional protection. |
| High | Password reset does not revoke existing sessions | A logged-in operator continued opening `/manual_jobcard` after an administrator reset the password. | Rotate a per-user session generation on password reset; validate it on each request. |
| High | Disabled sessions become valid again when account is enabled | Disable an operator, enable it, then reuse the original cookie: access succeeds without a new login. Disabling blocks requests while disabled but does not permanently revoke the cookie. | Rotate authentication generation when disabling; require a fresh login after enabling. |
| High — integrity | Declared SQLite foreign keys are inactive | `PRAGMA foreign_keys` returned 0 on the application connection. Declared relationships on alias/payroll tables therefore do not guarantee references exist. | Enable foreign-key enforcement on every connection, including after migrations. Check and repair existing orphan data before enabling it. |
| High — integrity | Movement ledger lacks database rules for quantities and job references | In an isolated transaction, inserting a negative OUT movement referencing a nonexistent job and product succeeded. `JobmovementData.jobcard` is text without a foreign key; quantity/flow/type checks are absent. This demonstrates missing database protection, not a demonstrated bypass of normal HTTP entry validation. | Add typed references and CHECK constraints through a migration; retain application validation and transaction-level balance checks. Preserve/reconcile supported legacy unassigned returns. |
| Medium | Accepted quantities can make the dashboard unavailable | Two jobs each containing `2**63 - 1` pieces are individually accepted. `/admin_dashord` then returns 500 with SQLite `integer overflow` during aggregate calculations. | Enforce realistic application quantity limits and safe aggregate limits. Include JavaScript's exact-integer limit in client/server validation. |
| Medium | Reusing a retry key for changed data silently reports success | Save a manual job, change pieces from 30 to 99 and resubmit with the same key. Response is HTTP 200, `success=true, duplicate=true`; the changed quantity is not saved. | Store a canonical request digest with the claim; return a conflict if a key is reused with different content. |
| Medium | Lost-response retries cannot recover the saved job/print screen | An identical successful retry returns only a duplicate message, without the original `jobData`/job ID. The manual UI's duplicate branch returns before rendering the job and leaves submission disabled. The entry remains saved, but its immediate result/printing flow cannot recover. | Save or reconstruct the original successful result for identical retries; allow the client to render the saved job. |

## Existing protections that passed

- Existing Python suite: 176 tests discovered, 168 passed and 8 optional browser
  tests skipped in the initial run; no failures.
- Six JavaScript test programs passed: advance receipts, advance selection,
  payroll calculator, ledger ordering, worker lookup, embedded return workspace.
- Real Firefox checks: seven scenarios passed in the complete browser run.
  The partial-payroll scenario initially failed because its selectors still
  expected the obsolete `#payroll-preview` section. Updated that test to use
  `#payroll-local-review` and `#payrollLocalConfirm`; its targeted rerun passed,
  including both partial payments. All eight scenarios were thus verified,
  with no full browser-suite rerun after the test-selector-only correction.
- Added stress checks passed: 44 malformed manual-row field cases, 41 malformed
  return field cases, and a 12-thread return race.
- In the 12-thread race, each request tried to return 2 pieces against a job of 10.
  Exactly five saves succeeded, the saved total stayed 10, and no request returned
  an internal save error.
- Existing tests cover same-token manual/inventory deduplication, concurrent
  allocation of one bundle, competing edits, simultaneous partial payrolls,
  payroll-versus-advance-repayment races, rollback and stale review rejection.
- Direct account disable/deletion blocks access on the following request when
  the account remains disabled/deleted. The flaws above concern later reuse.
- Malformed bundle types are rejected with HTTP 400. Initial code-review concern
  about unhashable bundle types did not reproduce.

## Audit reproductions

`security_regressions.py` expresses secure behavior: known defects intentionally
fail assertions. It is outside the normal `tests/` discovery tree so the existing
suite remains unchanged. `stress_checks.py` contains additional passing stress and
validation checks. Application behavior has not been changed by this audit.

```bash
.venv/bin/python -m unittest discover -s tests -v
PYTHONPATH=tests:. .venv/bin/python -m unittest discover -s audits -p stress_checks.py -v
PYTHONPATH=tests:. .venv/bin/python -m unittest discover -s audits -p security_regressions.py -v
for script in tests/js/test_*.js; do gjs "$script" || break; done
BH_RUN_BROWSER_TESTS=1 .venv/bin/python -m unittest discover -s tests -p test_browser_flows.py -v
```

Audit expectations: 12 checks; nine failures correspond to the nine findings,
three pass (disable, delete, malformed type). The fallback-secret reproduction
skips if a custom environment secret is configured.

## Limits and further review

- Browser checks initially could not open their temporary local test server in
  the sandbox. They completed with the necessary local-server permission as
  described above. That setup failure was environmental, not an application bug.
- Concurrency evidence applies to the configured SQLite engine and tested
  contention levels, not every database backend or arbitrary server load.
- Request claims rely on SQLite's single writer lock to serialize balance reads.
  A move to another database needs explicit locking/atomic updates and rerun races.
- Code review found no login throttling or configured request body limit. These
  are hardening gaps; this audit did not perform a denial-of-service attack.
- Network response loss was checked via duplicate HTTP requests, not a real
  network fault injector. Printer hardware, external CSV watchers, backups,
  reverse proxy settings, live deployment secret and TLS were not verified.
- No production fixes were applied. Address critical account issues first, then
  session revocation, database migrations and retry/quantity behavior.
