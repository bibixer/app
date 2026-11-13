"""Generate a readable report from completed load-wave evidence files."""
import json
from collections import Counter
from pathlib import Path


FILES = ['load_results.json', 'load_routes_results.json', 'load_additional_results.json',
         'load_diagnostic_results.json', 'load_product_diagnostic.json', 'load_32_workers_results.json',
         'load_integrity_results.json', 'load_recovery_diagnostic.json']
root = Path(__file__).resolve().parent
groups = [(name, json.loads((root / name).read_text())) for name in FILES if (root / name).exists()]
rows = [(name, group['server_threads'], result) for name, group in groups for result in group['results']]
requests = sum(row.get('requests', 0) for _, _, row in rows)
codes = Counter()
for _, _, row in rows:
    codes.update(row.get('statuses', {}))
failed = [row for _, _, row in rows if not row.get('passed')]
route_rows = [row for _, _, row in rows if row['name'].startswith('route:')]
application_routes = [row for row in route_rows if ':bootstrap.static:' not in row['name']]
endpoints = {row['name'].rsplit(':', 1)[0] for row in application_routes}
lines = [
    '# 1,001-client database and endpoint stress test', '',
    f'Completed evidence: {len(rows)} waves, {requests:,} HTTP requests. '
    f'{len(route_rows)} route/method waves. {len(failed)} waves had a failed invariant or server/transport error.', '',
    f'Application coverage: {len(endpoints)} distinct application endpoints and {len(application_routes)} '
    'GET/POST combinations, each with a separate 1,001-client wave. One additional Bootstrap asset lookup '
    'is included in the raw route evidence.', '',
    '## Test conditions', '',
    '- Every measured wave released 1,001 asynchronous HTTP clients from one start gate. '
    'Peak client in-flight counts and peak server handlers are recorded separately.',
    '- Main server configuration: eight Waitress handlers, matching app.py. A separate diagnostic used 32 handlers. '
    'This does not mean 1,001 simultaneous database writers; SQLite serializes writes.',
    '- Servers, main/user databases and sessions were created for each isolated wave. '
    'Printer calls were mocked. No requests targeted the live port 5000 or production entry databases.',
    '- Multiple isolated load processes shared this machine. Latencies reflect that shared load and are not a standalone production capacity benchmark.',
    '- Form CSRF was disabled in the isolated fixtures to focus on concurrency; cookie authentication and role checks remained active. '
    'These results do not replace the security audit or CSRF tests.',
    '- The harness raised Waitress connection_limit to 4,096 and backlog to 2,048. With select() mode, '
    'the first 1,001-client attempt crashed the server loop with `ValueError: filedescriptor out of range in select()`. '
    'That aborted attempt is excluded from completed-request counts. Completed runs used `asyncore_use_poll=True`. '
    'The live app has not been changed. Its default connection limit is lower, so this does not prove the unmodified live server exhibits the identical crash.',
    '- A successful route guard (400, 403, 404, 410 or redirect) is not counted as a database save. '
    'Route/method waves include empty-POST validation, missing-receipt lookup and V2-disabled legacy guards. '
    'Valid writes and final database state are exercised separately by the mutation waves.',
    '- Discrete legacy writes/edits were tested with SIMPLE_WORKFLOW=False only in temporary test instances. '
    'The live V2 workflow remains unchanged.', '',
    '## Findings', '',
    '- Initial duplicate manual-job wave: 998 HTTP 200 and three HTTP 500; exactly one job remained. '
    'Its rerun completed 1,001/1,001 without server errors. The initial run lacked exception capture, '
    'so its precise failure cause is unconfirmed; it remains an intermittent failure, not a fixed issue.',
    '- Initial distinct-product wave: all 1,001 requests redirected, but only 1,000 new products were present '
    '(1,001 total including the seed, instead of 1,002). This is a missing save, not proof of a successful save. '
    'The instrumented rerun saved all 1,001 products. The initial run did not retain form warning cookies.',
    '- A separate 32-worker distinct-product run reproduced a missing product (`LOAD-28`). '
    'Instrumentation recorded one SQLite `database is locked` exception and one misleading '
    '"Could not save item. Check for a duplicate name or alias." warning. All 1,001 responses were still HTTP 302. '
    'The database file integrity check was `ok`; this is an unsaved request under contention, not file corruption.',
    '- Return contention: 1,001 distinct requests each attempted one piece against 100 available. '
    'Exactly 100 saved and 901 were rejected; saved returns did not exceed the given quantity.',
    '- The initial batch advance-recovery wave had one HTTP 500. The final balance still reached zero '
    'with exactly one receipt; no duplicate recovery was observed. Its precise initial exception was not captured.',
    '- See the table and JSON evidence for remaining financial/account/edit invariants and any additional failures. '
    'Passing duplicates intentionally produce one database change; unique waves expect one save per request.', '',
    '## Completed waves', '',
    '| Evidence file | Scenario | Handlers peak / configured | Client peak | HTTP status counts | Seconds | p95 seconds | Final state check |',
    '| --- | --- | --- | --- | --- | --- | --- | --- |',
]
for filename, threads, row in rows:
    lines.append('| ' + ' | '.join([
        filename, row['name'], f"{row.get('peak_server_handlers', '—')} / {threads}",
        str(row.get('peak_client_inflight', '—')), json.dumps(row.get('statuses', {})),
        str(row.get('seconds', '—')), str(row.get('p95_seconds', '—')),
        ('PASS' if row.get('passed') else 'FAIL') + ': ' + json.dumps(row.get('state', row.get('setup_error', ''))),
    ]) + ' |')
lines += ['', '## Totals and reproduction', '', f'HTTP status totals: `{dict(codes)}`.', '',
          'Full JSON files contain row counts, response distributions and latency measurements. '
          'Later diagnostic files additionally contain SQLite integrity checks, exception counts and form warnings. '
          'Do not infer that unrecorded diagnostic fields were measured in earlier waves.', '',
          '```bash',
          'PYTHONPATH=tests:. .venv/bin/python audits/load_1000.py --requests 1001',
          'PYTHONPATH=tests:. .venv/bin/python audits/load_1000.py --requests 1001 --route-waves --output audits/load_routes_results.json',
          '.venv/bin/python audits/summarize_load.py', '```', '',
          'Application behavior has not been modified. These tests establish bounded observations, '
          'not proof that every possible payload or concurrency interleaving is safe.']
(root / 'LOAD_REPORT.md').write_text('\n'.join(lines) + '\n')
print(json.dumps(dict(waves=len(rows), requests=requests, route_method_waves=len(route_rows),
                      application_endpoints=len(endpoints), application_route_methods=len(application_routes),
                      failed_waves=[row['name'] for row in failed], statuses=dict(codes)), indent=2))
