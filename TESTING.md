# Application tests

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
| Partial-job payments, later returns, selected jobs, per-type paid quantities, retries and concurrent installments | `test_partial_payroll.py` |
| Existing payroll database upgrade, preserved receipts and transactional rollback | `test_schema_updates.py` |
| Dashboard lifetime/product piece totals, older unlinked returns and per-job pending balances | `test_dashboard_totals.py` |
| Wednesday–Tuesday weekly inflow/outflow, opening and closing balances, product pies and issue dates | `test_weekly_dashboard.py` |
| Exact From/To ranges, detailed movement ledgers, outworker return workspace, payroll context and label CSV export | `test_range_and_return_workspace.py` |
| Return calculator breakdown and original given patterns | `test_return_breakdown.py` |
| Fixed bundle types, page shells, navigation lookup and template compilation | `test_manual_bundle_types.py`, `test_ui_pages.py`, `test_jobcard_ledger_lookup.py` |

## Real browser tests

Firefox and geckodriver are needed for these optional tests. They start a temporary app on a random local port, with a temporary database and a fresh browser profile. They cover Enter/Backspace navigation, aliases, Type selection, job correction, partial-job payroll in two installments, calculator shortcuts, print expansion and phone layouts.

```bash
BH_RUN_BROWSER_TESTS=1 .venv/bin/python -m unittest discover -s tests -p test_browser_flows.py -v
```

Set `BH_GECKODRIVER` and `BH_FIREFOX_BINARY` if the executables are outside the normal search paths. In a container that cannot start Firefox's sandbox, browser tests also accept `BH_BROWSER_DISABLE_SANDBOX=1`; this affects only the temporary test browser.

All cases use `unittest` from Python's standard library. No additional Python testing packages are required.

## Manual job label output

Saving a manual job exports the existing two-products-per-page label CSV format into `to_print/jobcard`. Set the server environment variable `LABEL_PRINT_ROOT` to change the root; job label files are placed in its `jobcard` subfolder. The external CSV label application watches that folder and prints the labels. CSV files are published atomically after the job commits, and duplicate job-save retries do not export another copy. If export fails, the job stays saved and the UI reports the export failure.
