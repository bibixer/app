# V1 cleanup

The application now exposes only the manual job workflow: products and rates,
outworkers, job issue, returns and kept pieces, payroll and advances, ledgers,
account management, and audit history.

Removed the old bale/lump/bundle entry screens, scanned job issue handler,
cutter/supplier setup screens, their reports and finder, the old dashboard
branch, and V1 navigation. Also removed 23 dedicated templates/static assets,
eight unused form classes, eight unused report readers, and commented bootstrap
code. The shared dashboard stylesheet remains because the current dashboard
uses it.

Retired URLs return HTTP 410, including write requests. `/jobcard` redirects to
`/manual_jobcard`. Setting `SIMPLE_WORKFLOW=False` no longer re-enables V1 routes
or navigation. This compatibility setting still controls legacy restricted
account permissions; it does not grant administrator access.

## Historical compatibility deliberately retained

No database tables or records were removed. Legacy models and relationship
handling are still needed to read and edit existing scanned jobs safely. Their
low-level import/fixture helpers remain covered by regression tests, but are
not exposed as entry screens or HTTP write APIs. Existing returns, kept-piece
recovery, payroll snapshots, audit records, and permissions are preserved.

## Recovery

Before removing source files, a source-only backup was created at:

`/tmp/bh-v1-cleanup.ZEnZ88/source-before-cleanup.tar.gz`

It includes every deleted file and the affected source/template files before
cleanup, without database contents or secrets. `/tmp` is temporary storage;
copy this archive to durable storage if long-term recovery is required.

Regression coverage includes retired routes under both configuration values,
historical scanned job editing/ledgers/returns, current manual workflows,
database integrity, concurrent writes, security, payroll, and browser flows.

Verification on 18 November 2026:

- Full discovery: 294 tests, 28 optional browser tests skipped. The only failure
  was a stale assertion for the old navigation label. After updating it to check
  the current ledger link and label, all three ledger lookup tests passed.
- Five focused cleanup/page-resource tests passed, including JavaScript and CSS
  availability checks.
- Six real Firefox flows passed: old job URL redirect, aliases in job editing,
  manual keyboard entry, product rate switching, inline return preview, and
  combined given/return/kept corrections.
- `git diff --check` passed.
