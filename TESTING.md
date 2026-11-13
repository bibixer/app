# Application tests

Kept-product recovery: `tests/test_kept_products.py` verifies physically returned
versus retained pieces, product-value setup, payroll eligibility, recoverable
advances, partial prior payments, duplicate/race protection and additive migration.
Usage and rollout are documented in `KEPT_PRODUCTS.md`.

Security and integrity hardening (13 November 2026): normal test discovery now
includes the original security audit regressions in `test_security_hardening.py`.
Coverage includes private persistent signing keys, session revocation, forced
numeric user-ID reuse, active SQLite foreign keys, movement validation triggers,
quantity limits, exact historical totals, additive upgrades, receipt replay, and
101 concurrent identical/changed-payload retries. See
`audits/SECURITY_FIX_VERIFICATION.md` for rollout notes and fresh load evidence.

Recheck the authentication, integrity, upgrade and contention reproductions:

```bash
PYTHONPATH=tests:. .venv/bin/python -m unittest test_security_hardening test_database_contention test_schema_updates -v
```

The full isolated mutation load rerun uses 37 scenario waves and validates both
databases' integrity, enabled foreign keys and lack of foreign-key violations:

```bash
PYTHONPATH=tests:. .venv/bin/python audits/load_1000.py --requests 1001 --threads 32 --output audits/load_security_complete_results.json
```

The mixed `route_sweep` wave distributes its requests across registered routes;
it is not a separate 1,001-request wave per route. Use `--route-waves` when that
separate per-route diagnostic is required.

SQLite load fixes (13 November 2026): `database_writes.py` configures WAL, writer
lock waiting and clean write boundaries for both databases. Contention tests in
`test_database_contention.py` cover real lock timeouts, reusable retry keys,
retryable API/form errors and dual-pool capacity. The Waitress settings are shared
with the load harness through `app.SERVER_OPTIONS`.

Committed request replays now take a read-only fast path in `data_entry.py`.
First submissions still acquire the writer lock and repeat their claim check.
Contention tests verify an existing receipt can replay while an unrelated writer
holds SQLite's writer lock, and concurrent different payloads still conflict.

Follow-up load evidence and remaining scope limits are recorded in
`audits/LOAD_FIX_VERIFICATION.md`. Reproduce the isolated mutation waves with:

```bash
PYTHONPATH=tests:. .venv/bin/python audits/load_1000.py --requests 1001 --output audits/load_fixed_results.json
```

Run the unit, database, API and rendered-page tests from the app directory:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

Every database fixture uses a temporary SQLite database, including the separate user database. Printer calls are mocked in write tests; CSV export tests write to a temporary directory. No production entries are created or changed.

The app defaults to the V2 manual-only workflow (`SIMPLE_WORKFLOW=True`). `test_simple_workflow.py` verifies disabled inventory routes, simplified navigation/product setup, operator job assignment and returns, manual-job CSV export, disabled outworker QR printing, and administrator account/role changes. Older fixtures explicitly enable the legacy workflow to keep historical data services and correction safeguards covered; they do not enable those workflows in the running app.

## What is covered

| Feature | Test files |
| --- | --- |
| Product/master aliases, numeric master IDs and ambiguous names | `test_aliases_and_edits.py` |
| Scanned and manual jobs, strict quantities, canonical products, transaction rollback | `test_jobcard_writes.py` |
| Bale, lump and bundle workflow, setup, lookup data and CSV labels | `test_inventory_and_printing.py` |
| Admin job corrections, restored return balances, automatic stock updates and audit history | `test_jobcard_edit.py` |
| Concurrent inventory saves, bundle allocation, returns and edit conflicts | `test_concurrent_writes.py` |
| Login, admin permissions, malformed requests, retries and retained inventory drafts | `test_http_workflows.py` |
| Job ledgers, period balances, products, incomplete jobs and older return assignment | `test_outworker_job_ledger.py` |
| Piece rates, type overrides, advances, payroll, paid-record locks and concurrent payments | `test_payroll.py` |
| Individual advance selection, partial recovery, historical FIFO balances, selected IDs on confirmation and immutable receipt links | `test_individual_advances.py`, `test_payroll_advance_selection.py` |
| Money received back directly, partial/full advance repayment, receipt ledger, stale forms, duplicate/concurrent saves, payroll-vs-repayment races and rollback | `test_advance_receipts.py`, `gjs tests/js/test_advance_receipt.js` |
| Advance-only checkbox selection without jobs: signed confirmation, selected/all advances, atomic batch receipts, duplicates, partial balances and concurrent recovery | `test_selected_advance_receipts.py`, `test_payroll_frontend.py`, `gjs tests/js/test_payroll_calculator.js` |
| Browser-only payroll calculations and review popup; live advance selection, close/back, signed page-load snapshot, tamper rejection and stale-rate/advance checks on payment | `test_payroll_frontend.py`, `gjs tests/js/test_payroll_calculator.js` |
| Partial-job payments, later returns, selected jobs, per-type paid quantities, retries and concurrent installments | `test_partial_payroll.py` |
| Existing payroll database upgrade, preserved receipts and transactional rollback | `test_schema_updates.py` |
| Dashboard lifetime/product piece totals, older unlinked returns and per-job pending balances | `test_dashboard_totals.py` |
| Wednesday–Tuesday weekly inflow/outflow, opening and closing balances, product pies and issue dates | `test_weekly_dashboard.py` |
| Exact From/To ranges, detailed movement ledgers, outworker return workspace, payroll context and label CSV export | `test_range_and_return_workspace.py` |
| Return calculator breakdown and original given patterns | `test_return_breakdown.py` |
| Fixed bundle types, page shells, navigation lookup and template compilation | `test_manual_bundle_types.py`, `test_ui_pages.py`, `test_jobcard_ledger_lookup.py` |

## Real browser tests

Firefox and geckodriver are needed for these optional tests. They start a temporary app on a random local port, with a temporary database and a fresh browser profile. They cover Enter/Backspace navigation, aliases, Type selection, job correction, partial-job payroll in two installments, calculator shortcuts, print expansion and phone layouts.

Run `gjs tests/js/test_payroll_advances.js` to check individual ticks, Select all, Clear all and partial-selection state without a browser. Advance-to-payroll links are stored in the additive `outworker_advance_recovery` table (created at app startup). Earlier aggregate-only payroll deductions are attributed oldest-first for remaining advance balances; existing receipts are not rewritten.

Direct repayments are stored separately in the additive `outworker_advance_receipt` table, created at app startup. Each receipt belongs to one worker and advance, and records amount, method, reference, notes, time and recorder. Both direct receipts and payroll deductions reduce the same outstanding advance; direct receipts do not count as payroll payments. Writes use the shared transaction lock plus request deduplication and a remaining-balance check.

```bash
BH_RUN_BROWSER_TESTS=1 .venv/bin/python -m unittest discover -s tests -p test_browser_flows.py -v
```

Set `BH_GECKODRIVER` and `BH_FIREFOX_BINARY` if the executables are outside the normal search paths. In a container that cannot start Firefox's sandbox, browser tests also accept `BH_BROWSER_DISABLE_SANDBOX=1`; this affects only the temporary test browser.

All cases use `unittest` from Python's standard library. No additional Python testing packages are required.

## Manual job label output

Saving a manual job exports the existing two-products-per-page label CSV format into `to_print/jobcard`. Set the server environment variable `LABEL_PRINT_ROOT` to change the root; job label files are placed in its `jobcard` subfolder. The external CSV label application watches that folder and prints the labels. CSV files are published atomically after the job commits, and duplicate job-save retries do not export another copy. If export fails, the job stays saved and the UI reports the export failure.

## Local JavaScript checks

When `gjs` (SpiderMonkey) is installed, run `gjs tests/js/test_return_workspace.js` from the app directory. These tests exercise the actual return scripts without a browser or network: saved-balance notifications, other-job draft preservation, message origin/source checks, receipt-print failures, and balance updates without a layout-height change. Full browser checks remain available with the Firefox command above.
