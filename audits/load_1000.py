"""Isolated real-HTTP load waves. Never points at the running/production app.

PYTHONPATH=tests:. .venv/bin/python audits/load_1000.py --requests 1001
"""
import argparse
import asyncio
from collections import Counter
from datetime import datetime
import json
import logging
from http.cookies import SimpleCookie
from pathlib import Path
import threading
import time
from urllib.parse import urlencode

from itsdangerous import URLSafeTimedSerializer
from sqlalchemy import text, event
from waitress import create_server

from support import AppTestCase
from app import SERVER_OPTIONS
from data_entry import add_manual_jobcard, in_move_entery
from edit_service import edit_context
from modes import (db, User, UserAccessLog, Item_data, Outworker, Jobcard, Jobmovement,
                   OutworkerRate, OutworkerAdvance, OutworkerAdvanceReceipt,
                   OutworkerPayroll, OutworkerPayrollJob, ItemAlias, Cuter, Party, Lump, Bundle, Bale_date, EditLog)
from payroll_service import (save_rate, record_advance, advance_balance, advance_entries,
                             browser_payroll_snapshot, payroll_preview, rate_version, issue_payroll)
from simple_workflow import user_version
from test_inventory_and_printing import InventoryAndPrintingTest


class ErrorCapture(logging.Handler):
    def __init__(self):
        super().__init__(logging.ERROR)
        self.kinds = Counter()
        self.examples = []

    def emit(self, record):
        if record.exc_info:
            error = record.exc_info[1]
            self.kinds[type(error).__name__] += 1
            if len(self.examples) < 3:
                self.examples.append(str(error).split('\n')[0][:300])


class Meter:
    def __init__(self, app):
        self.app, self.active, self.peak = app, 0, 0
        self.lock = threading.Lock()

    def __call__(self, environ, start_response):
        with self.lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
        try:
            # Flask returns a materialized response iterable on these routes.
            return self.app(environ, start_response)
        finally:
            with self.lock:
                self.active -= 1


def configure(f, name, count):
    """Return request factory and a final-state assertion for one fresh fixture."""
    f.app.config.update(SIMPLE_WORKFLOW=True, PROPAGATE_EXCEPTIONS=False)
    admin, worker, product = f.admin.id, f.worker.id, f.product.id

    def form(path, data, unique=False):
        return lambda i: ('POST', path, {**data, 'submission_token': f'load-{i}' if unique else 'load'}, False)

    def check(model, expected, filters=None):
        return lambda: (model.query.filter_by(**(filters or {})).count() == expected,
                        {'rows': model.query.filter_by(**(filters or {})).count(), 'expected': expected})

    if name in ('kept_duplicate', 'kept_competing'):
        from kept_products import save_product_value
        from modes import JobKeptProduct
        save_product_value(product, '120', 0, 'seed-value', f.admin)
        save_rate(product, '', '5.5', 'new', 'seed-rate', f.admin)
        card = add_manual_jobcard(f.manual_payload(pieces=50, count=1), f.admin, 'seed-job')['jobData']['jobId']
        in_move_entery(f.return_payload(card, 48), f.admin, 'seed-return')
        payload = dict(product_id=product, bundle_type='lump', pieces='2', expected_value='12000',
                       expected_remaining='2', confirmed='yes', note='Load test retention')
        def verify_kept():
            from data_Process import get_jobcard_ledger
            from payroll_service import payable_job_quotes
            quotes = payable_job_quotes(db.session.get(Outworker, worker))
            rows = JobKeptProduct.query.count()
            advances = OutworkerAdvance.query.count()
            job = get_jobcard_ledger(card)['job']
            balance = advance_balance(worker)
            state = dict(kept_records=rows, advances=advances, amount_to_recover_paise=balance,
                         returned=job['returned'], kept=job['kept'], remaining=job['remaining'],
                         payable=sum(row['pieces'] for row in quotes))
            return (rows == advances == 1 and balance == 24000 and job['returned'] == 48
                    and job['kept'] == 2 and job['remaining'] == 0 and state['payable'] == 50), state
        return form(f'/jobcard/{card}/kept', payload, unique=name == 'kept_competing'), verify_kept

    if name.startswith('manual_'):
        unique = name.endswith('unique')
        return (lambda i: ('POST', '/submit-manual-jobcard', f.manual_payload(key=f'load-{i}' if unique else 'load'), True)), check(Jobcard, count if unique else 1)

    if name.startswith('return_'):
        card = add_manual_jobcard(f.manual_payload(pieces=100, count=1), f.admin, 'seed')['jobData']['jobId']
        payload = f.return_payload(card, 1)
        def request(i):
            return 'POST', '/summit-retune', {**payload, 'request_id': 'load' if name.endswith('duplicate') else f'load-{i}'}, True
        expected = 1 if name.endswith('duplicate') else 100
        def verify():
            rows = Jobmovement.query.filter_by(flow_type='IN').all()
            total = sum(row.inflow for row in rows)
            return total == expected and len(rows) == expected, {'returned': total, 'rows': len(rows), 'expected': expected}
        return request, verify

    if name == 'alias_collision':
        def request(i):
            data = dict(name='RACE-ALIAS' if i % 2 else 'RACE-NAME',
                        aliases='' if i % 2 else 'RACE-ALIAS', submission_token=f'load-{i}')
            return 'POST', '/add_items', data, False
        def verify():
            products = Item_data.query.count()
            ambiguous = db.session.query(ItemAlias.id).join(Item_data, Item_data.name == ItemAlias.alias).count()
            return products == 2 and ambiguous == 0, {'products': products, 'expected': 2, 'ambiguous_aliases': ambiguous}
        return request, verify

    if name.startswith('product_'):
        unique = name.endswith('unique')
        def request(i):
            return 'POST', '/add_items', dict(name=f'LOAD-{i}' if unique else 'LOAD', aliases='', submission_token=f'load-{i}' if unique else 'load'), False
        def verify():
            names = {row.name for row in Item_data.query.all()}
            expected = 1 + (count if unique else 1)
            return len(names) == expected, {'rows': len(names), 'expected': expected,
                'missing': [f'LOAD-{i}' for i in range(count) if f'LOAD-{i}' not in names][:20] if unique else []}
        return request, verify

    if name.startswith('outworker_'):
        unique = name.endswith('unique')
        def request(i):
            return 'POST', '/add_outworver', dict(name=f'LOAD-{i}' if unique else 'LOAD', address='CITY', number=456, aliases='', submission_token=f'load-{i}' if unique else 'load'), False
        return request, check(Outworker, 1 + (count if unique else 1))

    if name.startswith('user_'):
        action = name.removeprefix('user_')
        if action == 'create':
            return form('/users', dict(action='create', username='load-user', password='load-password', role=2)), check(User, 3)
        target = f.operator
        if action == 'enable':
            target.is_active = False
            db.session.commit()
        data = dict(user_id=target.id, version=user_version(target))
        if action in ('disable', 'enable'):
            data.update(action='set_active', active='0' if action == 'disable' else '1')
        elif action == 'delete':
            data.update(action='delete')
        else:
            data.update(action='update', role=1, password='')
        def verify():
            user = db.session.get(User, target.id)
            ok = user is None if action == 'delete' else (user.is_active == (action == 'enable') if action in ('disable', 'enable') else user.role == 1)
            logs = UserAccessLog.query.count()
            return ok and logs == 1, {'state_ok': ok, 'audit_rows': logs, 'expected_audit_rows': 1}
        return form('/users', data), verify

    if name == 'rates':
        return form('/payroll/rates', dict(product_id=product, bundle_type='', rate='5.50', version='new', action='save'), True), check(OutworkerRate, 1)

    if name == 'rate_remove':
        save_rate(product, '', '5.50', 'new', 'seed-rate', f.admin)
        version = rate_version(OutworkerRate.query.one())
        return form('/payroll/rates', dict(product_id=product, bundle_type='', version=version, action='remove'), True), check(OutworkerRate, 0)

    if name == 'assign_return':
        card = add_manual_jobcard(f.manual_payload(pieces=10, count=1), f.admin, 'seed')['jobData']['jobId']
        movement = Jobmovement(date=datetime.now(), jobcard=None, partculer='legacy return', product_name=f.product.name,
                               name_of_mater=f.worker_name, enter_user='admin', type_B='lump', flow_type='IN', inflow=5)
        db.session.add(movement)
        db.session.commit()
        movement_id = movement.id
        data = dict(action='assign_return', name=f.worker_name, movement_id=movement_id, card_id=card,
                    date_from=datetime.now().date().isoformat(), date_to=datetime.now().date().isoformat())
        return form('/outworker_report', data, True), lambda: (
            db.session.get(Jobmovement, movement_id).jobcard == str(card) and EditLog.query.count() == 1,
            {'jobcard': db.session.get(Jobmovement, movement_id).jobcard, 'audit_rows': EditLog.query.count()})

    if name.startswith('advance_'):
        unique = name.endswith('unique')
        return form('/payroll', dict(action='advance', worker_id=worker, amount='1', method='Cash'), unique), check(OutworkerAdvance, count if unique else 1)

    if name in ('recover_single', 'recover_batch', 'payroll'):
        advance = record_advance(worker, '100', 'Cash', '', '', 'seed-advance', f.admin)
        if name == 'recover_single':
            data = dict(action='recover_advance', worker_id=worker, advance_choice=f'{advance.id}:10000', amount='100', method='Cash')
            return form('/payroll', data, True), lambda: (advance_balance(worker) == 0 and OutworkerAdvanceReceipt.query.count() == 1, {'balance': advance_balance(worker), 'receipts': OutworkerAdvanceReceipt.query.count()})
        snapshot = browser_payroll_snapshot(f.worker, [], advance_entries(worker), 10000)
        if name == 'recover_batch':
            signed = URLSafeTimedSerializer(f.app.secret_key, salt='payroll-browser-review').dumps(snapshot)
            data = dict(action='recover_selected_advances', worker_id=worker, advance_ids=[advance.id], deduction='100', client_snapshot=signed, method='Cash')
            return form('/payroll', data, True), lambda: (advance_balance(worker) == 0 and OutworkerAdvanceReceipt.query.count() == 1, {'balance': advance_balance(worker), 'receipts': OutworkerAdvanceReceipt.query.count()})
        save_rate(product, '', '5.50', 'new', 'seed-rate', f.admin)
        card = add_manual_jobcard(f.manual_payload(pieces=10, count=1), f.admin, 'seed-job')['jobData']['jobId']
        in_move_entery(f.return_payload(card, 10), f.admin, 'seed-return')
        preview = payroll_preview(worker, [card], '0')
        def verify():
            payments = OutworkerPayroll.query.all()
            pieces = sum(row.pieces for row in OutworkerPayrollJob.query.all())
            gross = sum(row.gross_paise for row in payments)
            return len(payments) == 1 and pieces == 10 and gross == 5500, {
                'payrolls': len(payments), 'paid_pieces': pieces, 'gross_paise': gross,
                'advance_remaining_paise': advance_balance(worker)}
        return form('/payroll', dict(action='pay', worker_id=worker, job_ids=[card], deduction='0', version=preview['version'], method='Cash'), True), verify

    if name.startswith('edit_') or name.startswith('legacy_edit_'):
        legacy = name.startswith('legacy_edit_')
        kind = name.removeprefix('legacy_edit_' if legacy else 'edit_')
        target_id = product if kind == 'product' else worker
        if legacy:
            f.app.config['SIMPLE_WORKFLOW'] = False
            if kind in ('bale', 'lump', 'bundle'):
                bundle = f.bundle()
                lump = db.session.get(Lump, bundle.lump_id)
                target_id = {'bale': lump.bale_id, 'lump': lump.id, 'bundle': bundle.id}[kind]
            else:
                target_id = f.cutter.id if kind == 'cutter' else f.party.id
        if kind == 'jobcard':
            target_id = add_manual_jobcard(f.manual_payload(), f.admin, 'seed')['jobData']['jobId']
        context = edit_context(kind, target_id)
        data = {field['name']: field['value'] if field['value'] is not None else '' for field in context['fields']}
        data.update(version=context['version'])
        if kind == 'product':
            data['aliases'] = 'LOAD ALIAS'
        elif kind == 'outworker':
            data['adders'] = 'NEW CITY'
        elif kind == 'jobcard':
            data.update(given_by='CORRECTED', edit_reason='Load audit', edit_lines='')
        elif kind in ('cutter', 'party'):
            data['name'] = 'CORRECTED'
        elif kind == 'bundle':
            data['color'] = 'GREEN'
        elif kind == 'lump':
            data['meters'] = 101
        elif kind == 'bale':
            data['lot_number'] = 2
        return form(f'/edit/{kind}/{target_id}', data, True), check(EditLog, 1, {'entity_type': kind})

    if name in ('legacy_scan', 'legacy_inventory', 'legacy_cutter', 'legacy_supplier'):
        f.app.config['SIMPLE_WORKFLOW'] = False
        if name == 'legacy_scan':
            payload = f.scan_payload(f.bundle())
            return (lambda i: ('POST', '/submit-jobcard', {**payload, 'request_id': f'load-{i}'}, True)), check(Jobcard, 1)
        if name == 'legacy_inventory':
            payload = InventoryAndPrintingTest.payload(f)
            cookie = dict(bale_data=payload['bale_data'], bundle_data=payload['main'], bundles=payload['bundles'], current_bundle=3, current_lump=2, sno=2, lump_workflow_id='load', sno_lump=0)
            f.load_session.update(cookie)
            return (lambda i: ('GET', '/bundle_entery', None, False)), check(Lump, 1)
        path, model = ('/add_cutter', Cuter) if name == 'legacy_cutter' else ('/add_suppy', Party)
        return form(path, dict(name='LOAD')), check(model, 2)

    if name == 'route_sweep' or name.startswith('route:'):
        # Every registered non-static route, with real IDs for dynamic paths.
        card = add_manual_jobcard(f.manual_payload(), f.admin, 'seed')['jobData']['jobId']
        paths = []
        for rule in f.app.url_map.iter_rules():
            if rule.endpoint == 'static':
                continue
            args = {key: ('product' if key == 'entity_type' else card if key == 'jobcard_id' else 1) for key in rule.arguments}
            from flask import url_for
            with f.app.test_request_context():
                path = url_for(rule.endpoint, **args)
            for method in ('GET', 'POST'):
                if method not in rule.methods:
                    continue
                if name.startswith('route:') and name != f'route:{rule.endpoint}:{method}':
                    continue
                paths.append((method, path, None, False))
        f.sweep_paths = paths
        return (lambda i: paths[i % len(paths)]), check(Jobcard, 1)
    raise ValueError(name)


async def wave(port, cookie, factory, count, signer):
    gate = asyncio.Event()
    pending, peak = 0, 0

    async def request(index):
        nonlocal pending, peak
        await gate.wait()
        pending += 1
        peak = max(peak, pending)
        start = time.perf_counter()
        writer = None
        try:
            method, path, data, as_json = factory(index)
            body = (json.dumps(data).encode() if as_json else urlencode(data, doseq=True).encode()) if data is not None else b''
            reader, writer = await asyncio.wait_for(asyncio.open_connection('127.0.0.1', port, limit=2**22), 120)
            content_type = 'application/json' if as_json else 'application/x-www-form-urlencoded'
            headers = f'{method} {path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nCookie: session={cookie}\r\nConnection: close\r\nContent-Type: {content_type}\r\nContent-Length: {len(body)}\r\n\r\n'.encode()
            writer.write(headers + body)
            await writer.drain()
            response = await asyncio.wait_for(reader.read(), 180)
            code = int(response.split(b' ', 2)[1])
            messages = []
            for header in response.split(b'\r\n\r\n', 1)[0].split(b'\r\n')[1:]:
                if header.lower().startswith(b'set-cookie:'):
                    cookies = SimpleCookie()
                    cookies.load(header.split(b':', 1)[1].decode())
                    if 'session' in cookies and cookies['session'].value:
                        session = signer.loads(cookies['session'].value)
                        messages = [message[:300] for category, message in session.get('_flashes', []) if category in ('danger', 'warning')]
            return code, time.perf_counter() - start, None, messages
        except Exception as error:
            return 'transport', time.perf_counter() - start, type(error).__name__ + ': ' + str(error), []
        finally:
            if writer:
                writer.close()
                await writer.wait_closed()
            pending -= 1

    tasks = [asyncio.create_task(request(i)) for i in range(count)]
    await asyncio.sleep(0)
    gate.set()
    results = await asyncio.gather(*tasks)
    return results, peak


def run(name, count, threads):
    f = AppTestCase()
    f.setUp()
    server = None
    capture = ErrorCapture()
    logging.getLogger().addHandler(capture)
    database_errors = Counter()
    try:
        f.load_session = {'_user_id': f.admin.get_id(), '_fresh': True}
        factory, verify = configure(f, name, count)
        def capture_database_error(context):
            error = context.original_exception
            if type(error).__name__ != 'IntegrityError':
                database_errors[str(error).split('\n')[0][:160]] += 1
        for engine in db.engines.values():
            event.listen(engine, 'handle_error', capture_database_error)
        signer = f.app.session_interface.get_signing_serializer(f.app)
        cookie = signer.dumps(f.load_session)
        meter = Meter(f.app)
        db.session.remove()
        server_options = {**SERVER_OPTIONS, 'threads': threads, 'channel_timeout': 240}
        server = create_server(meter, host='127.0.0.1', port=0, **server_options)
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        start = time.perf_counter()
        responses, peak = asyncio.run(wave(server.effective_port, cookie, factory, count, signer))
        elapsed = time.perf_counter() - start
        db.session.remove()
        ok, state = verify()
        integrity = db.session.execute(text('PRAGMA integrity_check')).scalar()
        database_checks = {}
        for bind_name, engine in db.engines.items():
            with engine.connect() as connection:
                database_checks[bind_name or 'main'] = {
                    'integrity': connection.exec_driver_sql('PRAGMA integrity_check').scalar(),
                    'foreign_keys_enabled': connection.exec_driver_sql('PRAGMA foreign_keys').scalar() == 1,
                    'foreign_key_violations': len(connection.exec_driver_sql('PRAGMA foreign_key_check').all()),
                }
        statuses = dict(Counter(str(row[0]) for row in responses))
        latencies = sorted(row[1] for row in responses)
        result = dict(name=name, requests=count, statuses=statuses,
                      peak_client_inflight=peak, peak_server_handlers=meter.peak,
                      seconds=round(elapsed, 3), requests_per_second=round(count / elapsed, 1),
                      p50_seconds=round(latencies[count // 2], 3),
                      p95_seconds=round(latencies[int(count * .95)], 3),
                      max_seconds=round(latencies[-1], 3), database_invariant_ok=ok, state=state,
                      sqlite_integrity=integrity, exception_counts=dict(capture.kinds),
                      database_checks=database_checks,
                      database_error_counts=dict(database_errors),
                      exception_examples=capture.examples,
                      form_warning_counts=dict(Counter(message for row in responses for message in row[3])),
                      errors=[row[2] for row in responses if row[2]][:3])
        result['passed'] = (ok and integrity == 'ok'
                            and not capture.kinds and not database_errors
                            and all(check['integrity'] == 'ok' and check['foreign_keys_enabled']
                                    and check['foreign_key_violations'] == 0 for check in database_checks.values())
                            and all(isinstance(row[0], int) and 200 <= row[0] < 500 and row[2] is None
                                    for row in responses))
        if hasattr(f, 'sweep_paths'):
            result['routes'] = [list(row[:2]) for row in f.sweep_paths]
        return result
    finally:
        if server:
            server.close()
            # Each test server owns its own dispatcher map.
            server.task_dispatcher.shutdown()
        f.doCleanups()
        logging.getLogger().removeHandler(capture)


SCENARIOS = ['manual_duplicate', 'manual_unique', 'return_duplicate', 'return_competing',
             'product_duplicate', 'product_unique', 'outworker_duplicate', 'outworker_unique',
             'user_create', 'user_update', 'user_disable', 'user_enable', 'user_delete',
             'rates', 'advance_duplicate', 'advance_unique', 'recover_single', 'recover_batch',
             'payroll', 'edit_product', 'edit_outworker', 'edit_jobcard', 'legacy_scan',
             'legacy_inventory', 'legacy_cutter', 'legacy_supplier', 'route_sweep']
SCENARIOS += ['alias_collision', 'rate_remove', 'assign_return', 'legacy_edit_bale', 'legacy_edit_lump',
              'legacy_edit_bundle', 'legacy_edit_cutter', 'legacy_edit_party']
SCENARIOS += ['kept_duplicate', 'kept_competing']

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--requests', type=int, default=1001)
    parser.add_argument('--threads', type=int, default=8)
    parser.add_argument('--scenario', choices=SCENARIOS, action='append')
    parser.add_argument('--output', default='audits/load_results.json')
    parser.add_argument('--route-waves', action='store_true',
                        help='Run a separate full-size wave for every non-static route/method.')
    args = parser.parse_args()
    if args.requests < 1 or args.threads < 1:
        parser.error('Requests and threads must be positive.')
    logging.disable(logging.NOTSET)
    logging.getLogger().handlers.clear()
    logging.getLogger().setLevel(logging.ERROR)
    results = []
    scenarios = args.scenario or SCENARIOS
    if args.route_waves:
        fixture = AppTestCase()
        fixture.setUp()
        try:
            scenarios = [f'route:{rule.endpoint}:{method}'
                         for rule in fixture.app.url_map.iter_rules() if rule.endpoint != 'static'
                         for method in ('GET', 'POST') if method in rule.methods]
        finally:
            fixture.doCleanups()
    for scenario in scenarios:
        try:
            result = run(scenario, args.requests, args.threads)
        except Exception as error:
            result = dict(name=scenario, passed=False, setup_error=repr(error))
        results.append(result)
        print(json.dumps(result), flush=True)
        Path(args.output).write_text(json.dumps(dict(requests_per_wave=args.requests,
            server_threads=args.threads, results=results), indent=2) + '\n')
