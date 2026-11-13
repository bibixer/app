# Pieces kept by an outworker

1. Open **Products → Product rates** (`/payroll/rates`). Choose a product and
   save its **Product value per piece**. This is independent of its manufacturing
   base/type rates. A value of zero leaves retention recovery unconfigured.
2. Open the job return page. Save actual physical returns first. Expand
   **Record pieces kept by outworker**, enter the retained quantity, review the
   amount, tick confirmation, and save. This is an explicit action, never an
   automatic charge for missing pieces that might still arrive later.
3. The app saves a separate job/product/type retention record and a linked
   recoverable advance in one database transaction. This is not a cash payment.
   Retry tokens prevent duplicate charges; stale balances/prices require review.
4. Payroll includes returned **plus kept** pieces, less anything already paid.
   Select the recovery advance to deduct it now, leave it for a later payment,
   or use the existing direct-repayment controls after receiving money.

Example: **50 given − 48 returned − 2 kept = 0 pending**. At product value ₹120,
the linked advance is ₹240. At manufacturing rate ₹5.50, 50 payable pieces earn
₹275 gross; selecting the ₹240 recovery leaves ₹35 net. If the first 48 were
already paid, only the other two become newly payable. Excess recovery beyond
the current payroll remains outstanding, never a negative payroll payment.

Job, outworker, dashboard and dated ledgers show kept quantities separately from
physical returns. Return entry cannot consume retained quantities again. Saved
price snapshots do not change if a product's current value changes later.

Administrators can correct given items, physical returns and kept-stock entries
together at `/edit/jobcard/<id>`. The editor updates the linked recovery amount,
worker account and payroll eligibility in the same transaction, with before/after
audit history and a required correction reason. Kept quantities and unit values
must remain positive; automatic cancellation/reversal is not supported.

Issued payrolls and recoveries with money already received or deducted remain
locked. Fresh version checks include kept entries, linked advances and recovery
receipts, so stale forms cannot overwrite a concurrent return or payment.

## Deployment and tests

Restart the application to load this code and its additive database upgrade.
Existing products receive a default value of zero; existing job, movement,
advance and payroll records are preserved. Back up both databases before rollout.
No production records are created by the tests.

`tests/test_kept_products.py` covers the example, partial payroll, carrying the
advance forward, immutable prices, validation, exactly-once retries, concurrent
charges, rollback, UI routes, report balances and legacy schema upgrade.

Isolated real-HTTP stress checks:

Verification completed: 220 Python checks passed, all 10 Firefox checks passed,
and both 1,001-client retained-product load waves passed with 32 server workers.
Each wave created exactly one recovery, with no captured server/database errors.
The first harness result file contains a verifier-fixture error; accepted results
are in `audits/load_kept_products_verified.json`.

```bash
PYTHONPATH=tests:. .venv/bin/python audits/load_1000.py --requests 1001 --threads 32 \
  --scenario kept_duplicate --scenario kept_competing \
  --output audits/load_kept_products_verified.json
```
