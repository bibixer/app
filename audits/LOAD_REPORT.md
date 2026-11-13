# 1,001-client database and endpoint stress test

Follow-up: this report preserves the original test evidence. See
[SECURITY_FIX_VERIFICATION.md](SECURITY_FIX_VERIFICATION.md) for implemented fixes
and [SECURITY_LOAD_VERIFICATION.md](SECURITY_LOAD_VERIFICATION.md) for the final
37-scenario acceptance results after targeted reruns. The fixes are in the working
tree; back up and restart the app to upgrade the existing instance databases.

Completed evidence: 97 waves, 97,097 HTTP requests. 56 route/method waves. 4 waves had a failed invariant or server/transport error.

Application coverage: 35 distinct application endpoints and 55 GET/POST combinations, each with a separate 1,001-client wave. One additional Bootstrap asset lookup is included in the raw route evidence.

## Test conditions

- Every measured wave released 1,001 asynchronous HTTP clients from one start gate. Peak client in-flight counts and peak server handlers are recorded separately.
- Main server configuration: eight Waitress handlers, matching app.py. A separate diagnostic used 32 handlers. This does not mean 1,001 simultaneous database writers; SQLite serializes writes.
- Servers, main/user databases and sessions were created for each isolated wave. Printer calls were mocked. No requests targeted the live port 5000 or production entry databases.
- Multiple isolated load processes shared this machine. Latencies reflect that shared load and are not a standalone production capacity benchmark.
- Form CSRF was disabled in the isolated fixtures to focus on concurrency; cookie authentication and role checks remained active. These results do not replace the security audit or CSRF tests.
- The harness raised Waitress connection_limit to 4,096 and backlog to 2,048. With select() mode, the first 1,001-client attempt crashed the server loop with `ValueError: filedescriptor out of range in select()`. That aborted attempt is excluded from completed-request counts. Completed runs used `asyncore_use_poll=True`. The live app has not been changed. Its default connection limit is lower, so this does not prove the unmodified live server exhibits the identical crash.
- A successful route guard (400, 403, 404, 410 or redirect) is not counted as a database save. Route/method waves include empty-POST validation, missing-receipt lookup and V2-disabled legacy guards. Valid writes and final database state are exercised separately by the mutation waves.
- Discrete legacy writes/edits were tested with SIMPLE_WORKFLOW=False only in temporary test instances. The live V2 workflow remains unchanged.

## Findings

- Initial duplicate manual-job wave: 998 HTTP 200 and three HTTP 500; exactly one job remained. Its rerun completed 1,001/1,001 without server errors. The initial run lacked exception capture, so its precise failure cause is unconfirmed; it remains an intermittent failure, not a fixed issue.
- Initial distinct-product wave: all 1,001 requests redirected, but only 1,000 new products were present (1,001 total including the seed, instead of 1,002). This is a missing save, not proof of a successful save. The instrumented rerun saved all 1,001 products. The initial run did not retain form warning cookies.
- A separate 32-worker distinct-product run reproduced a missing product (`LOAD-28`). Instrumentation recorded one SQLite `database is locked` exception and one misleading "Could not save item. Check for a duplicate name or alias." warning. All 1,001 responses were still HTTP 302. The database file integrity check was `ok`; this is an unsaved request under contention, not file corruption.
- Return contention: 1,001 distinct requests each attempted one piece against 100 available. Exactly 100 saved and 901 were rejected; saved returns did not exceed the given quantity.
- The initial batch advance-recovery wave had one HTTP 500. The final balance still reached zero with exactly one receipt; no duplicate recovery was observed. Its precise initial exception was not captured.
- See the table and JSON evidence for remaining financial/account/edit invariants and any additional failures. Passing duplicates intentionally produce one database change; unique waves expect one save per request.

## Completed waves

| Evidence file | Scenario | Handlers peak / configured | Client peak | HTTP status counts | Seconds | p95 seconds | Final state check |
| --- | --- | --- | --- | --- | --- | --- | --- |
| load_results.json | manual_duplicate | 8 / 8 | 1001 | {"200": 998, "500": 3} | 27.981 | 26.918 | FAIL: {"rows": 1, "expected": 1} |
| load_results.json | manual_unique | 8 / 8 | 1001 | {"200": 1001} | 16.656 | 15.141 | PASS: {"rows": 1001, "expected": 1001} |
| load_results.json | return_duplicate | 8 / 8 | 1001 | {"200": 1001} | 12.09 | 10.698 | PASS: {"returned": 1, "rows": 1, "expected": 1} |
| load_results.json | return_competing | 8 / 8 | 1001 | {"200": 100, "400": 901} | 21.359 | 19.699 | PASS: {"returned": 100, "rows": 100, "expected": 100} |
| load_results.json | product_duplicate | 8 / 8 | 1001 | {"302": 1001} | 7.808 | 6.693 | PASS: {"rows": 2, "expected": 2} |
| load_results.json | product_unique | 8 / 8 | 1001 | {"302": 1001} | 25.575 | 23.195 | FAIL: {"rows": 1001, "expected": 1002} |
| load_results.json | outworker_duplicate | 8 / 8 | 1001 | {"302": 1001} | 9.327 | 8.203 | PASS: {"rows": 2, "expected": 2} |
| load_results.json | outworker_unique | 8 / 8 | 1001 | {"302": 1001} | 26.018 | 23.367 | PASS: {"rows": 1002, "expected": 1002} |
| load_results.json | user_create | 8 / 8 | 1001 | {"302": 1001} | 12.295 | 10.976 | PASS: {"rows": 3, "expected": 3} |
| load_results.json | user_update | 8 / 8 | 1001 | {"302": 1001} | 11.406 | 10.261 | PASS: {"state_ok": true, "audit_rows": 1, "expected_audit_rows": 1} |
| load_results.json | user_disable | 8 / 8 | 1001 | {"302": 1001} | 12.929 | 11.576 | PASS: {"state_ok": true, "audit_rows": 1, "expected_audit_rows": 1} |
| load_results.json | user_enable | 8 / 8 | 1001 | {"302": 1001} | 12.369 | 11.091 | PASS: {"state_ok": true, "audit_rows": 1, "expected_audit_rows": 1} |
| load_results.json | user_delete | 8 / 8 | 1001 | {"302": 1001} | 13.658 | 12.526 | PASS: {"state_ok": true, "audit_rows": 1, "expected_audit_rows": 1} |
| load_results.json | rates | 8 / 8 | 1001 | {"200": 1000, "302": 1} | 18.981 | 17.528 | PASS: {"rows": 1, "expected": 1} |
| load_results.json | advance_duplicate | 8 / 8 | 1001 | {"302": 1, "200": 1000} | 29.065 | 27.233 | PASS: {"rows": 1, "expected": 1} |
| load_results.json | advance_unique | 8 / 8 | 1001 | {"302": 1001} | 14.322 | 12.92 | PASS: {"rows": 1001, "expected": 1001} |
| load_results.json | recover_single | 8 / 8 | 1001 | {"302": 1, "200": 1000} | 32.449 | 30.066 | PASS: {"balance": 0, "receipts": 1} |
| load_results.json | recover_batch | 8 / 8 | 1001 | {"200": 999, "302": 1, "500": 1} | 36.121 | 33.492 | FAIL: {"balance": 0, "receipts": 1} |
| load_results.json | payroll | 8 / 8 | 1001 | {"200": 1000, "302": 1} | 45.859 | 42.671 | PASS: {"rows": 1, "expected": 1} |
| load_results.json | edit_product | 8 / 8 | 1001 | {"302": 1001} | 14.333 | 12.741 | PASS: {"rows": 1, "expected": 1} |
| load_results.json | edit_outworker | 8 / 8 | 1001 | {"302": 1001} | 13.819 | 12.582 | PASS: {"rows": 1, "expected": 1} |
| load_results.json | edit_jobcard | 8 / 8 | 1001 | {"302": 1001} | 20.225 | 18.631 | PASS: {"rows": 1, "expected": 1} |
| load_results.json | legacy_scan | 8 / 8 | 1001 | {"409": 1000, "200": 1} | 13.216 | 11.995 | PASS: {"rows": 1, "expected": 1} |
| load_results.json | legacy_inventory | 8 / 8 | 1001 | {"302": 1001} | 9.486 | 8.242 | PASS: {"rows": 1, "expected": 1} |
| load_results.json | legacy_cutter | 8 / 8 | 1001 | {"302": 1001} | 9.372 | 8.18 | PASS: {"rows": 2, "expected": 2} |
| load_results.json | legacy_supplier | 8 / 8 | 1001 | {"302": 1001} | 14.634 | 13.466 | PASS: {"rows": 2, "expected": 2} |
| load_results.json | route_sweep | 8 / 8 | 1001 | {"404": 56, "200": 472, "302": 139, "410": 278, "400": 56} | 9.475 | 8.932 | PASS: {"rows": 1, "expected": 1} |
| load_routes_results.json | route:bootstrap.static:GET | 6 / 8 | 1001 | {"404": 1001} | 3.218 | 2.944 | PASS: {"rows": 1, "expected": 1} |
| load_routes_results.json | route:payroll_rates:GET | 8 / 8 | 1001 | {"200": 1001} | 10.027 | 9.536 | PASS: {"rows": 1, "expected": 1} |
| load_routes_results.json | route:payroll_rates:POST | 8 / 8 | 1001 | {"200": 1001} | 9.549 | 9.058 | PASS: {"rows": 1, "expected": 1} |
| load_routes_results.json | route:outworker_payroll:GET | 8 / 8 | 1001 | {"200": 1001} | 14.043 | 12.717 | PASS: {"rows": 1, "expected": 1} |
| load_routes_results.json | route:outworker_payroll:POST | 8 / 8 | 1001 | {"200": 1001} | 14.445 | 13.138 | PASS: {"rows": 1, "expected": 1} |
| load_routes_results.json | route:payroll_for_job:GET | 8 / 8 | 1001 | {"302": 1001} | 7.302 | 6.394 | PASS: {"rows": 1, "expected": 1} |
| load_routes_results.json | route:payroll_receipt:GET | 8 / 8 | 1001 | {"404": 1001} | 5.476 | 5.338 | PASS: {"rows": 1, "expected": 1} |
| load_routes_results.json | route:manage_users:GET | 8 / 8 | 1001 | {"200": 1001} | 10.006 | 8.848 | PASS: {"rows": 1, "expected": 1} |
| load_routes_results.json | route:manage_users:POST | 8 / 8 | 1001 | {"200": 1001} | 9.92 | 9.354 | PASS: {"rows": 1, "expected": 1} |
| load_routes_results.json | route:bale_entery:GET | 8 / 8 | 1001 | {"410": 1001} | 6.398 | 6.299 | PASS: {"rows": 1, "expected": 1} |
| load_routes_results.json | route:bale_entery:POST | 8 / 8 | 1001 | {"410": 1001} | 6.126 | 6.035 | PASS: {"rows": 1, "expected": 1} |
| load_routes_results.json | route:lump_home:GET | 8 / 8 | 1001 | {"410": 1001} | 7.304 | 6.58 | PASS: {"rows": 1, "expected": 1} |
| load_routes_results.json | route:lump_home:POST | 8 / 8 | 1001 | {"410": 1001} | 6.915 | 5.753 | PASS: {"rows": 1, "expected": 1} |
| load_routes_results.json | route:bundle_entery:GET | 8 / 8 | 1001 | {"410": 1001} | 7.359 | 6.566 | PASS: {"rows": 1, "expected": 1} |
| load_routes_results.json | route:bundle_entery:POST | 8 / 8 | 1001 | {"410": 1001} | 6.777 | 6.042 | PASS: {"rows": 1, "expected": 1} |
| load_routes_results.json | route:job_card:GET | 8 / 8 | 1001 | {"302": 1001} | 5.203 | 4.589 | PASS: {"rows": 1, "expected": 1} |
| load_routes_results.json | route:job_card:POST | 8 / 8 | 1001 | {"302": 1001} | 4.91 | 4.098 | PASS: {"rows": 1, "expected": 1} |
| load_routes_results.json | route:manual_job_card:GET | 8 / 8 | 1001 | {"200": 1001} | 15.41 | 14.403 | PASS: {"rows": 1, "expected": 1} |
| load_routes_results.json | route:submit_manual_jobcard:POST | 8 / 8 | 1001 | {"400": 1001} | 5.587 | 4.41 | PASS: {"rows": 1, "expected": 1} |
| load_routes_results.json | route:add_item:GET | 8 / 8 | 1001 | {"200": 1001} | 15.272 | 14.225 | PASS: {"rows": 1, "expected": 1} |
| load_routes_results.json | route:add_item:POST | 8 / 8 | 1001 | {"200": 1001} | 14.444 | 13.342 | PASS: {"rows": 1, "expected": 1} |
| load_routes_results.json | route:add_suppy:GET | 8 / 8 | 1001 | {"410": 1001} | 6.331 | 5.612 | PASS: {"rows": 1, "expected": 1} |
| load_routes_results.json | route:add_suppy:POST | 8 / 8 | 1001 | {"410": 1001} | 6.984 | 6.261 | PASS: {"rows": 1, "expected": 1} |
| load_routes_results.json | route:add_outworker:GET | 8 / 8 | 1001 | {"200": 1001} | 10.075 | 9.373 | PASS: {"rows": 1, "expected": 1} |
| load_routes_results.json | route:add_outworker:POST | 8 / 8 | 1001 | {"200": 1001} | 10.918 | 10.263 | PASS: {"rows": 1, "expected": 1} |
| load_routes_results.json | route:add_cuter:GET | 8 / 8 | 1001 | {"410": 1001} | 6.728 | 5.694 | PASS: {"rows": 1, "expected": 1} |
| load_routes_results.json | route:add_cuter:POST | 8 / 8 | 1001 | {"410": 1001} | 6.312 | 5.427 | PASS: {"rows": 1, "expected": 1} |
| load_routes_results.json | route:submit_jobcard:POST | 1 / 8 | 1001 | {"410": 1001} | 2.469 | 1.912 | PASS: {"rows": 1, "expected": 1} |
| load_routes_results.json | route:retune_product:GET | 8 / 8 | 1001 | {"200": 1001} | 9.801 | 8.846 | PASS: {"rows": 1, "expected": 1} |
| load_routes_results.json | route:retune_product:POST | 8 / 8 | 1001 | {"200": 1001} | 9.266 | 8.373 | PASS: {"rows": 1, "expected": 1} |
| load_routes_results.json | route:outworker_returns:GET | 8 / 8 | 1001 | {"200": 1001} | 9.223 | 8.226 | PASS: {"rows": 1, "expected": 1} |
| load_routes_results.json | route:job_retun:GET | 8 / 8 | 1001 | {"302": 1001} | 5.287 | 4.502 | PASS: {"rows": 1, "expected": 1} |
| load_routes_results.json | route:job_retun:POST | 8 / 8 | 1001 | {"302": 1001} | 4.563 | 4.198 | PASS: {"rows": 1, "expected": 1} |
| load_routes_results.json | route:jobcard_ledger_lookup:GET | 8 / 8 | 1001 | {"200": 1001} | 6.257 | 6.157 | PASS: {"rows": 1, "expected": 1} |
| load_routes_results.json | route:jobcard_ledger:GET | 8 / 8 | 1001 | {"200": 1001} | 15.316 | 13.922 | PASS: {"rows": 1, "expected": 1} |
| load_routes_results.json | route:summit_retune:POST | 8 / 8 | 1001 | {"400": 1001} | 5.481 | 4.874 | PASS: {"rows": 1, "expected": 1} |
| load_routes_results.json | route:admin_dashord:GET | 8 / 8 | 1001 | {"200": 1001} | 20.336 | 19.323 | PASS: {"rows": 1, "expected": 1} |
| load_routes_results.json | route:admin_dashord:POST | 8 / 8 | 1001 | {"200": 1001} | 19.48 | 18.303 | PASS: {"rows": 1, "expected": 1} |
| load_routes_results.json | route:dashboard_movements:GET | 8 / 8 | 1001 | {"200": 1001} | 19.557 | 18.318 | PASS: {"rows": 1, "expected": 1} |
| load_routes_results.json | route:cutter_report:GET | 8 / 8 | 1001 | {"410": 1001} | 6.453 | 5.69 | PASS: {"rows": 1, "expected": 1} |
| load_routes_results.json | route:cutter_report:POST | 8 / 8 | 1001 | {"410": 1001} | 6.799 | 6.032 | PASS: {"rows": 1, "expected": 1} |
| load_routes_results.json | route:outworker_report:GET | 8 / 8 | 1001 | {"200": 1001} | 9.203 | 8.687 | PASS: {"rows": 1, "expected": 1} |
| load_routes_results.json | route:outworker_report:POST | 8 / 8 | 1001 | {"200": 1001} | 9.864 | 9.063 | PASS: {"rows": 1, "expected": 1} |
| load_routes_results.json | route:product_report:GET | 8 / 8 | 1001 | {"410": 1001} | 7.035 | 6.086 | PASS: {"rows": 1, "expected": 1} |
| load_routes_results.json | route:product_report:POST | 8 / 8 | 1001 | {"410": 1001} | 6.043 | 5.95 | PASS: {"rows": 1, "expected": 1} |
| load_routes_results.json | route:home:GET | 8 / 8 | 1001 | {"302": 1001} | 4.44 | 4.357 | PASS: {"rows": 1, "expected": 1} |
| load_routes_results.json | route:login:GET | 8 / 8 | 1001 | {"200": 1001} | 8.057 | 7.758 | PASS: {"rows": 1, "expected": 1} |
| load_routes_results.json | route:login:POST | 8 / 8 | 1001 | {"200": 1001} | 9.098 | 7.953 | PASS: {"rows": 1, "expected": 1} |
| load_routes_results.json | route:logout:GET | 8 / 8 | 1001 | {"302": 1001} | 4.322 | 4.224 | PASS: {"rows": 1, "expected": 1} |
| load_routes_results.json | route:find_edit:GET | 8 / 8 | 1001 | {"410": 1001} | 5.912 | 5.825 | PASS: {"rows": 1, "expected": 1} |
| load_routes_results.json | route:find_edit:POST | 8 / 8 | 1001 | {"410": 1001} | 6.301 | 5.895 | PASS: {"rows": 1, "expected": 1} |
| load_routes_results.json | route:edit_index:GET | 8 / 8 | 1001 | {"200": 1001} | 6.213 | 6.094 | PASS: {"rows": 1, "expected": 1} |
| load_routes_results.json | route:edit_search:GET | 1 / 8 | 1001 | {"410": 1001} | 2.431 | 2.223 | PASS: {"rows": 1, "expected": 1} |
| load_routes_results.json | route:edit_entry:GET | 8 / 8 | 1001 | {"200": 1001} | 25.913 | 25.141 | PASS: {"rows": 1, "expected": 1} |
| load_routes_results.json | route:edit_entry:POST | 8 / 8 | 1001 | {"200": 1001} | 26.714 | 25.944 | PASS: {"rows": 1, "expected": 1} |
| load_routes_results.json | route:edit_logs:GET | 8 / 8 | 1001 | {"200": 1001} | 6.846 | 6.753 | PASS: {"rows": 1, "expected": 1} |
| load_additional_results.json | rate_remove | 8 / 8 | 1001 | {"200": 1000, "302": 1} | 18.877 | 17.249 | PASS: {"rows": 0, "expected": 0} |
| load_additional_results.json | assign_return | 8 / 8 | 1001 | {"200": 1001} | 29.316 | 27.409 | PASS: {"jobcard": "1", "audit_rows": 1} |
| load_additional_results.json | legacy_edit_bale | 8 / 8 | 1001 | {"302": 1001} | 12.627 | 11.101 | PASS: {"rows": 1, "expected": 1} |
| load_additional_results.json | legacy_edit_lump | 8 / 8 | 1001 | {"302": 1001} | 12.699 | 10.725 | PASS: {"rows": 1, "expected": 1} |
| load_additional_results.json | legacy_edit_bundle | 8 / 8 | 1001 | {"302": 1001} | 11.167 | 9.903 | PASS: {"rows": 1, "expected": 1} |
| load_additional_results.json | legacy_edit_cutter | 8 / 8 | 1001 | {"302": 1001} | 10.687 | 9.604 | PASS: {"rows": 1, "expected": 1} |
| load_additional_results.json | legacy_edit_party | 8 / 8 | 1001 | {"302": 1001} | 10.326 | 9.355 | PASS: {"rows": 1, "expected": 1} |
| load_diagnostic_results.json | manual_duplicate | 8 / 8 | 1001 | {"200": 1001} | 6.769 | 5.791 | PASS: {"rows": 1, "expected": 1} |
| load_product_diagnostic.json | product_unique | 8 / 8 | 1001 | {"302": 1001} | 36.788 | 33.75 | PASS: {"rows": 1002, "expected": 1002, "missing": []} |
| load_32_workers_results.json | manual_duplicate | 32 / 32 | 1001 | {"200": 1001} | 7.11 | 6.263 | PASS: {"rows": 1, "expected": 1} |
| load_32_workers_results.json | product_unique | 32 / 32 | 1001 | {"302": 1001} | 29.914 | 27.429 | FAIL: {"rows": 1001, "expected": 1002, "missing": ["LOAD-28"]} |
| load_integrity_results.json | alias_collision | 8 / 8 | 1001 | {"302": 1001} | 13.32 | 12.012 | PASS: {"products": 2, "expected": 2, "ambiguous_aliases": 0} |
| load_integrity_results.json | payroll | 8 / 8 | 1001 | {"302": 1, "200": 1000} | 42.678 | 39.776 | PASS: {"payrolls": 1, "paid_pieces": 10, "gross_paise": 5500, "advance_remaining_paise": 10000} |
| load_recovery_diagnostic.json | recover_batch | 8 / 8 | 1001 | {"200": 1000, "302": 1} | 38.909 | 36.401 | PASS: {"balance": 0, "receipts": 1} |

## Totals and reproduction

HTTP status totals: `{'200': 41602, '500': 4, '400': 2959, '302': 31178, '409': 1000, '404': 2058, '410': 18296}`.

Full JSON files contain row counts, response distributions and latency measurements. Later diagnostic files additionally contain SQLite integrity checks, exception counts and form warnings. Do not infer that unrecorded diagnostic fields were measured in earlier waves.

```bash
PYTHONPATH=tests:. .venv/bin/python audits/load_1000.py --requests 1001
PYTHONPATH=tests:. .venv/bin/python audits/load_1000.py --requests 1001 --route-waves --output audits/load_routes_results.json
.venv/bin/python audits/summarize_load.py
```

Application behavior has not been modified. These tests establish bounded observations, not proof that every possible payload or concurrency interleaving is safe.
