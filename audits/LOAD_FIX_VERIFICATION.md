# Load fixes and verification — 13 November 2026

This is the earlier load-only verification round. Subsequent security/session,
quantity, relationship and retry-result fixes are documented in
[SECURITY_FIX_VERIFICATION.md](SECURITY_FIX_VERIFICATION.md).

Completed follow-up evidence: 38 waves, 38,038 HTTP requests; 0 failed waves. Each wave released 1,001 clients together.

## Changes

- Both SQLite databases use WAL and a 60-second busy timeout. Writer services acquire BEGIN IMMEDIATE before re-reading balances, versions and duplicate claims.
- Earlier read snapshots are discarded at a clean service boundary. Pending caller corrections are flushed and kept in the same atomic transaction; they are not silently discarded.
- Both database pools have 32 retained slots plus 32 overflow slots. An intermediate 32-worker recovery attempt exposed exhaustion of the previous 5+10 pools; that failed attempt remains in load_fixed_32_results.json. The subsequent final recovery run passed with the corrected pool capacity.
- Lock/pool exhaustion returns HTTP 503 with Retry-After and a retryable JSON flag. Setup lock errors are no longer described as duplicate-name errors. Existing claim tokens remain reusable after rollback, and return entry retains its draft/token on a retryable response.
- The production Waitress entry point and load harness share poll(), eight default workers, a 2,048 connection limit and a 2,048 backlog. The diagnostic overrides only the worker count to 32.

## Verification

- Full Python suite: 183 discovered, 175 passed, eight optional browser cases skipped; all eight browser cases passed separately. Seven targeted database-contention checks passed, including the newly added simultaneous dual-pool capacity check.
- Six JavaScript programs passed. The return-workspace program now also simulates a busy response followed by success and verifies draft preservation and reuse of the same key.
- Real lock-timeout and injected busy-error tests confirm a failed claim saves no entry and a retry can save exactly once. SQLite integrity checks, saved row counts, money/piece totals and captured database exceptions are recorded for each load wave.

| Evidence | Scenario | Requests | HTTP statuses | Database state | Result |
| --- | --- | --- | --- | --- | --- |
| load_fixed_results.json | manual_duplicate | 1001 | {"200": 1001} | {"rows": 1, "expected": 1} | PASS |
| load_fixed_results.json | manual_unique | 1001 | {"200": 1001} | {"rows": 1001, "expected": 1001} | PASS |
| load_fixed_results.json | return_duplicate | 1001 | {"200": 1001} | {"returned": 1, "rows": 1, "expected": 1} | PASS |
| load_fixed_results.json | return_competing | 1001 | {"200": 100, "400": 901} | {"returned": 100, "rows": 100, "expected": 100} | PASS |
| load_fixed_results.json | product_duplicate | 1001 | {"302": 1001} | {"rows": 2, "expected": 2, "missing": []} | PASS |
| load_fixed_results.json | product_unique | 1001 | {"302": 1001} | {"rows": 1002, "expected": 1002, "missing": []} | PASS |
| load_fixed_results.json | outworker_duplicate | 1001 | {"302": 1001} | {"rows": 2, "expected": 2} | PASS |
| load_fixed_results.json | outworker_unique | 1001 | {"302": 1001} | {"rows": 1002, "expected": 1002} | PASS |
| load_fixed_results.json | user_create | 1001 | {"302": 1001} | {"rows": 3, "expected": 3} | PASS |
| load_fixed_results.json | user_update | 1001 | {"302": 1001} | {"state_ok": true, "audit_rows": 1, "expected_audit_rows": 1} | PASS |
| load_fixed_results.json | user_disable | 1001 | {"302": 1001} | {"state_ok": true, "audit_rows": 1, "expected_audit_rows": 1} | PASS |
| load_fixed_results.json | user_enable | 1001 | {"302": 1001} | {"state_ok": true, "audit_rows": 1, "expected_audit_rows": 1} | PASS |
| load_fixed_results.json | user_delete | 1001 | {"302": 1001} | {"state_ok": true, "audit_rows": 1, "expected_audit_rows": 1} | PASS |
| load_fixed_results.json | rates | 1001 | {"200": 1000, "302": 1} | {"rows": 1, "expected": 1} | PASS |
| load_fixed_results.json | advance_duplicate | 1001 | {"302": 1, "200": 1000} | {"rows": 1, "expected": 1} | PASS |
| load_fixed_results.json | advance_unique | 1001 | {"302": 1001} | {"rows": 1001, "expected": 1001} | PASS |
| load_fixed_results.json | recover_single | 1001 | {"200": 1000, "302": 1} | {"balance": 0, "receipts": 1} | PASS |
| load_fixed_results.json | recover_batch | 1001 | {"302": 1, "200": 1000} | {"balance": 0, "receipts": 1} | PASS |
| load_fixed_results.json | payroll | 1001 | {"200": 1000, "302": 1} | {"payrolls": 1, "paid_pieces": 10, "gross_paise": 5500, "advance_remaining_paise": 10000} | PASS |
| load_fixed_results.json | edit_product | 1001 | {"302": 1001} | {"rows": 1, "expected": 1} | PASS |
| load_fixed_results.json | edit_outworker | 1001 | {"302": 1001} | {"rows": 1, "expected": 1} | PASS |
| load_fixed_results.json | edit_jobcard | 1001 | {"302": 1001} | {"rows": 1, "expected": 1} | PASS |
| load_fixed_results.json | legacy_scan | 1001 | {"200": 1, "409": 1000} | {"rows": 1, "expected": 1} | PASS |
| load_fixed_results.json | legacy_inventory | 1001 | {"302": 1001} | {"rows": 1, "expected": 1} | PASS |
| load_fixed_results.json | legacy_cutter | 1001 | {"302": 1001} | {"rows": 2, "expected": 2} | PASS |
| load_fixed_results.json | legacy_supplier | 1001 | {"302": 1001} | {"rows": 2, "expected": 2} | PASS |
| load_fixed_results.json | route_sweep | 1001 | {"404": 36, "200": 482, "302": 126, "410": 321, "400": 36} | {"rows": 1, "expected": 1} | PASS |
| load_fixed_results.json | alias_collision | 1001 | {"302": 1001} | {"products": 2, "expected": 2, "ambiguous_aliases": 0} | PASS |
| load_fixed_results.json | rate_remove | 1001 | {"302": 1, "200": 1000} | {"rows": 0, "expected": 0} | PASS |
| load_fixed_results.json | assign_return | 1001 | {"200": 1001} | {"jobcard": "1", "audit_rows": 1} | PASS |
| load_fixed_results.json | legacy_edit_bale | 1001 | {"302": 1001} | {"rows": 1, "expected": 1} | PASS |
| load_fixed_results.json | legacy_edit_lump | 1001 | {"302": 1001} | {"rows": 1, "expected": 1} | PASS |
| load_fixed_results.json | legacy_edit_bundle | 1001 | {"302": 1001} | {"rows": 1, "expected": 1} | PASS |
| load_fixed_results.json | legacy_edit_cutter | 1001 | {"302": 1001} | {"rows": 1, "expected": 1} | PASS |
| load_fixed_results.json | legacy_edit_party | 1001 | {"302": 1001} | {"rows": 1, "expected": 1} | PASS |
| load_final_32_results.json | product_unique | 1001 | {"302": 1001} | {"rows": 1002, "expected": 1002, "missing": []} | PASS |
| load_final_32_results.json | manual_duplicate | 1001 | {"200": 1001} | {"rows": 1, "expected": 1} | PASS |
| load_final_32_results.json | recover_batch | 1001 | {"302": 1, "200": 1000} | {"balance": 0, "receipts": 1} | PASS |

HTTP totals: `{'200': 12588, '400': 937, '302': 23156, '409': 1000, '404': 36, '410': 321}`. Failed waves: `[]`.

## Limits and deployment

These are isolated temporary-database tests with mocked printers and CSRF disabled for load generation. Eight-worker mutation coverage and the final 32-worker failure-specific reruns are listed above. The earlier 55-route/method baseline was not repeated in this follow-up; all mutation scenarios and normal rendered-page/browser regression checks were exercised.

The server has not been restarted by this task. Restart the application to apply the connection policy and server settings. WAL creates SQLite -wal/-shm companion files while databases are open; backups must include committed WAL contents, preferably via SQLite backup tooling.

This round originally covered the load-test findings only. The separate authentication/session, foreign-key, quantity-limit and request-result findings have subsequently been addressed; see SECURITY_FIX_VERIFICATION.md for their current status and evidence.

Original LOAD_REPORT.md and its JSON evidence remain unchanged as baseline evidence. Passing follow-up waves do not guarantee success under unlimited load; persistent contention can still return an explicit retryable 503 instead of pretending a save succeeded.
