"""Summarize follow-up load evidence without replacing the original failures."""
import json
from collections import Counter
from pathlib import Path

root = Path(__file__).resolve().parent
files = ['load_fixed_results.json', 'load_final_32_results.json']
rows = [(name, row) for name in files if (root / name).exists()
        for row in json.loads((root / name).read_text())['results']]
codes = Counter()
for _, row in rows:
    codes.update(row.get('statuses', {}))
failures = [row['name'] for _, row in rows if not row.get('passed')]
total = sum(row.get('requests', 0) for _, row in rows)
lines = ['# Load fixes and verification — 13 November 2026', '',
         'This is the earlier load-only verification round. Subsequent security/session, '
         'quantity, relationship and retry-result fixes are documented in '
         '[SECURITY_FIX_VERIFICATION.md](SECURITY_FIX_VERIFICATION.md).', '',
         f'Completed follow-up evidence: {len(rows)} waves, {total:,} HTTP requests; '
         f'{len(failures)} failed waves. Each wave released 1,001 clients together.', '',
         '## Changes', '',
         '- Both SQLite databases use WAL and a 60-second busy timeout. Writer services acquire '
         'BEGIN IMMEDIATE before re-reading balances, versions and duplicate claims.',
         '- Earlier read snapshots are discarded at a clean service boundary. Pending caller corrections '
         'are flushed and kept in the same atomic transaction; they are not silently discarded.',
         '- Both database pools have 32 retained slots plus 32 overflow slots. An intermediate '
         '32-worker recovery attempt exposed exhaustion of the previous 5+10 pools; that failed '
         'attempt remains in load_fixed_32_results.json. The subsequent final recovery run passed '
         'with the corrected pool capacity.',
         '- Lock/pool exhaustion returns HTTP 503 with Retry-After and a retryable JSON flag. '
         'Setup lock errors are no longer described as duplicate-name errors. Existing claim tokens '
         'remain reusable after rollback, and return entry retains its draft/token on a retryable response.',
         '- The production Waitress entry point and load harness share poll(), eight default workers, '
         'a 2,048 connection limit and a 2,048 backlog. The diagnostic overrides only the worker count to 32.', '',
         '## Verification', '',
         '- Full Python suite: 183 discovered, 175 passed, eight optional browser cases skipped; '
         'all eight browser cases passed separately. Seven targeted database-contention checks passed, '
         'including the newly added simultaneous dual-pool capacity check.',
         '- Six JavaScript programs passed. The return-workspace program now also simulates a busy '
         'response followed by success and verifies draft preservation and reuse of the same key.',
         '- Real lock-timeout and injected busy-error tests confirm a failed claim saves no entry '
         'and a retry can save exactly once. SQLite integrity checks, saved row counts, money/piece '
         'totals and captured database exceptions are recorded for each load wave.', '',
         '| Evidence | Scenario | Requests | HTTP statuses | Database state | Result |',
         '| --- | --- | --- | --- | --- | --- |']
for filename, row in rows:
    lines.append('| ' + ' | '.join([filename, row['name'], str(row.get('requests', 0)),
                                   json.dumps(row.get('statuses', {})), json.dumps(row.get('state', {})),
                                   'PASS' if row.get('passed') else 'FAIL']) + ' |')
lines += ['', f'HTTP totals: `{dict(codes)}`. Failed waves: `{failures}`.', '',
          '## Limits and deployment', '',
          'These are isolated temporary-database tests with mocked printers and CSRF disabled for load '
          'generation. Eight-worker mutation coverage and the final 32-worker failure-specific reruns '
          'are listed above. The earlier 55-route/method baseline was not repeated in this follow-up; '
          'all mutation scenarios and normal rendered-page/browser regression checks were exercised.', '',
          'The server has not been restarted by this task. Restart the application to apply the connection '
          'policy and server settings. WAL creates SQLite -wal/-shm companion files while databases are '
          'open; backups must include committed WAL contents, preferably via SQLite backup tooling.', '',
          'This round originally covered the load-test findings only. The separate authentication/session, '
          'foreign-key, quantity-limit and request-result findings have subsequently been addressed; '
          'see SECURITY_FIX_VERIFICATION.md for their current status and evidence.', '',
          'Original LOAD_REPORT.md and its JSON evidence remain unchanged as baseline evidence. '
          'Passing follow-up waves do not guarantee success under unlimited load; persistent contention '
          'can still return an explicit retryable 503 instead of pretending a save succeeded.']
(root / 'LOAD_FIX_VERIFICATION.md').write_text('\n'.join(lines) + '\n')
print(json.dumps(dict(waves=len(rows), requests=total, failed_waves=failures, statuses=dict(codes)), indent=2))
