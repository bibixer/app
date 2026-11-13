"""Regression coverage for audited authentication, integrity and retry weaknesses."""
import stat
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from pathlib import Path
from unittest.mock import patch

from flask import Flask
from sqlalchemy import create_engine, event, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Query

import audits.security_regressions as original_audit
from installation_secret import installation_secret
from modes import db, Jobcard, Jobmovement, ItemAlias, RequestDedup, User, UserAccessLog
from data_entry import add_manual_jobcard, RequestConflict, claim_write
from payroll_service import record_advance
from schema_updates import ensure_security_schema
from simple_workflow import save_user_access
from piece_totals import piece_sum
from validation import MAX_PIECES, MAX_DATABASE_INTEGER
from app import create_app


class SecurityHardeningTest(original_audit.SecurityRegressions):
    # The original audit checks are inherited so normal discovery runs them too.
    def test_installation_key_is_private_persistent_and_unique(self):
        app = Flask('secret-test')
        app.config['SQLALCHEMY_BINDS'] = {'users': f'sqlite:///{self.temp.name}/private/users.db'}
        first = installation_secret(app)
        self.assertEqual(first, installation_secret(app))
        path = Path(self.temp.name, 'private', '.session-secret')
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        app.config['SQLALCHEMY_BINDS']['users'] = f'sqlite:///{self.temp.name}/other/users.db'
        self.assertNotEqual(first, installation_secret(app))
        for invalid in ['short', '8BYkEfBA6O6donzWlSihBXox7C0sKR6b']:
            app.config['SECRET_KEY'] = invalid
            with self.assertRaises(ValueError):
                installation_secret(app)

    def test_legacy_numeric_login_cookie_is_rejected_even_if_signed(self):
        with self.client.session_transaction() as session:
            session['_user_id'] = str(self.admin.id)
        self.assertEqual(self.client.get('/users').status_code, 302)

    def test_password_reset_allows_fresh_login_only(self):
        self.login_as(self.operator)
        self.change_user(self.operator, 'update', 'reset', role='2', password='new-password')
        self.assertEqual(self.client.get('/manual_jobcard').status_code, 302)
        self.assertEqual(self.client.post('/login', data=dict(user_name='operator', password='new-password')).status_code, 302)
        self.assertEqual(self.client.get('/manual_jobcard').status_code, 200)

    def test_role_change_revokes_old_session(self):
        self.login_as(self.operator)
        self.change_user(self.operator, 'update', 'promote', role='1', password='')
        self.assertEqual(self.client.get('/users').status_code, 302)

    def test_session_nonce_blocks_even_forced_numeric_id_reuse(self):
        self.login_as(self.operator)
        reused_id = self.operator.id
        db.session.delete(self.operator)
        db.session.flush()
        replacement = User('forced-replacement', 'test-password', 1)
        replacement.id = reused_id
        db.session.add(replacement)
        db.session.commit()
        self.assertEqual(self.client.get('/users').status_code, 302)

    def test_database_rules_independently_reject_invalid_movements(self):
        card_id = add_manual_jobcard(self.manual_payload(), self.admin, 'seed')['jobData']['jobId']
        for change in [dict(outflow=-1), dict(outflow=MAX_PIECES + 1), dict(outflow=1.5),
                       dict(jobcard='999999'), dict(jobcard=None), dict(type_B='unknown'),
                       dict(flow_type='BAD'), dict(inflow=2)]:
            with self.subTest(change=change):
                values = dict(date=datetime.now(), jobcard=str(card_id), bundle=None,
                              partculer='security test', product_name=self.product.name,
                              name_of_mater=self.worker_name, enter_user='admin', type_B='lump',
                              flow_type='OUT', outflow=1, inflow=0)
                values.update(change)
                db.session.add(Jobmovement(**values))
                with self.assertRaises(IntegrityError):
                    db.session.flush()
                db.session.rollback()
        movement = Jobmovement.query.one()
        movement.outflow = -1
        with self.assertRaises(IntegrityError):
            db.session.flush()
        db.session.rollback()
        db.session.delete(db.session.get(Jobcard, card_id))
        with self.assertRaises(IntegrityError):
            db.session.flush()
        db.session.rollback()

    def test_foreign_keys_are_on_for_every_pooled_connection_and_reject_orphans(self):
        for engine in db.engines.values():
            with engine.connect() as connection:
                self.assertEqual(connection.exec_driver_sql('PRAGMA foreign_keys').scalar(), 1)
                self.assertEqual(connection.exec_driver_sql('PRAGMA foreign_key_check').all(), [])
        db.session.add(ItemAlias(item_id=999999, alias='ORPHAN'))
        with self.assertRaises(IntegrityError):
            db.session.flush()
        db.session.rollback()

    def test_piece_limit_is_validated_before_claiming_key(self):
        invalid = self.manual_payload(pieces=MAX_PIECES + 1, count=1)
        self.assertEqual(self.client.post('/submit-manual-jobcard', json=invalid).status_code, 400)
        self.assertEqual(RequestDedup.query.count(), 0)
        valid = self.manual_payload(pieces=MAX_PIECES, count=1)
        self.assertEqual(self.client.post('/submit-manual-jobcard', json=valid).status_code, 200)

    def test_job_edit_cannot_exceed_total_piece_limit_across_rows(self):
        payload = self.manual_payload()
        payload['rows'].append(dict(payload['rows'][0]))
        card_id = add_manual_jobcard(payload, self.admin, 'two-lines')['jobData']['jobId']
        from jobcard_edit import jobcard_edit_context
        rows = jobcard_edit_context(card_id)['given']
        changes = {}
        for row in rows:
            changes[f'line_{row["id"]}_pieces'] = MAX_PIECES
            changes[f'line_{row["id"]}_count'] = 1
        self.assertEqual(self.job_edit(card_id, changes)[0], 'invalid')
        self.assertEqual(sum(row.outflow for row in Jobmovement.query.all()), 240)

    def test_retry_snapshot_is_original_and_does_not_repeat_csv_export(self):
        payload = self.manual_payload()
        first = self.client.post('/submit-manual-jobcard', json=payload).json
        card_id = first['jobData']['jobId']
        original = first['jobData']
        context = __import__('jobcard_edit').jobcard_edit_context(card_id)
        given = context['given'][0]
        self.assertEqual(self.job_edit(card_id, {f'line_{given["id"]}_pieces': 20})[0], 'saved')
        retry = self.client.post('/submit-manual-jobcard', json=payload).json
        self.assertEqual(retry['jobData'], original)
        self.assertTrue(retry['duplicate'])
        self.assertEqual(Jobcard.query.count(), 1)
        self.assertEqual(self.job_cade_print.call_count, 1)

    def test_scan_and_return_retries_restore_receipts_and_reject_changes(self):
        self.app.config['SIMPLE_WORKFLOW'] = False
        payload = self.scan_payload(self.bundle())
        first = self.client.post('/submit-jobcard', json=payload)
        self.assertEqual(first.status_code, 200)
        retry = self.client.post('/submit-jobcard', json=payload)
        self.assertEqual(retry.json['jobData'], first.json['jobData'])
        payload['items'][0]['qty'] = 35
        self.assertEqual(self.client.post('/submit-jobcard', json=payload).status_code, 409)
        payload = self.return_payload(first.json['jobData']['jobId'], 10)
        first_return = self.client.post('/summit-retune', json=payload)
        self.assertEqual(first_return.status_code, 200)
        retry = self.client.post('/summit-retune', json=payload)
        self.assertEqual(retry.json['jobData'], first_return.json['jobData'])
        payload['items'][0]['returned'] = 9
        self.assertEqual(self.client.post('/summit-retune', json=payload).status_code, 409)

    def test_advance_and_account_retries_cannot_silently_change_data(self):
        record_advance(self.worker.id, '100', 'Cash', '', '', 'advance-key', self.admin)
        with self.assertRaises(RequestConflict):
            record_advance(self.worker.id, '200', 'Cash', '', '', 'advance-key', self.admin)
        values = dict(action='create', username='new-user', password='test-password', role='2')
        save_user_access(values, 'account-key', self.admin.id)
        values['role'] = '1'
        with self.assertRaises(ValueError):
            save_user_access(values, 'account-key', self.admin.id)
        self.assertEqual(User.query.filter_by(username='new-user').one().role, 2)

    def test_legacy_unverifiable_request_is_not_reported_as_success(self):
        from data_entry import _request_key
        db.session.add(RequestDedup(request_key=_request_key('legacy', 'add_manual_jobcard', 'admin'),
                                    endpoint='add_manual_jobcard', username='admin', created_at=datetime.now()))
        db.session.commit()
        response = self.client.post('/submit-manual-jobcard', json=self.manual_payload(key='legacy'))
        self.assertEqual(response.status_code, 409)
        self.assertFalse(response.json['success'])

    def test_concurrent_changed_and_identical_retries_save_only_one_job(self):
        cookie = self.client.get_cookie(self.app.config['SESSION_COOKIE_NAME']).value
        gate = Event()
        def submit(index):
            gate.wait()
            client = self.app.test_client()
            client.set_cookie(self.app.config['SESSION_COOKIE_NAME'], cookie)
            response = client.post('/submit-manual-jobcard', json=self.manual_payload(pieces=30 + index % 2))
            return response.status_code, response.json
        with ThreadPoolExecutor(max_workers=16) as pool:
            futures = [pool.submit(submit, index) for index in range(101)]
            gate.set()
            results = [future.result(timeout=60) for future in futures]
        statuses = {status for status, _ in results}
        self.assertEqual(statuses, {200, 409})
        receipts = [body['jobData'] for status, body in results if status == 200]
        self.assertTrue(all(receipt == receipts[0] for receipt in receipts))
        self.assertEqual(Jobcard.query.count(), 1)
        self.assertEqual(Jobmovement.query.count(), 1)
        self.job_cade_print.assert_called_once()

    def test_unique_claim_race_rechecks_winning_payload(self):
        payload = self.manual_payload()
        add_manual_jobcard(payload, self.admin, 'manual-1')
        payload['rows'][0]['pieces'] = 99
        original_first = Query.first
        observed = []
        def hide_first_claim(query):
            if query.column_descriptions[0].get('entity') is RequestDedup:
                observed.append(True)
                if len(observed) <= 2:
                    return None  # Simulate a competing claim committed after this read.
            return original_first(query)
        with patch.object(Query, 'first', new=hide_first_claim):
            with self.assertRaises(RequestConflict):
                claim_write('manual-1', 'add_manual_jobcard', self.admin, payload)
        self.assertEqual(len(observed), 3)
        self.assertEqual(Jobcard.query.count(), 1)

    def test_unrelated_claim_integrity_failure_is_not_duplicate_success(self):
        failure = IntegrityError('INSERT', {}, Exception('unrelated integrity failure'))
        with patch('data_entry.db.session.flush', side_effect=failure):
            with self.assertRaises(IntegrityError):
                claim_write('new-claim', 'add_manual_jobcard', self.admin, self.manual_payload())
        self.assertEqual(RequestDedup.query.count(), 0)

    def test_account_retry_fingerprint_does_not_store_fast_password_digest(self):
        import hashlib
        import hmac
        import json
        values = dict(action='create', username='new-account', password='new-account-password', role='2')
        save_user_access(values, 'account-fingerprint', self.admin.id)
        payload = json.dumps(values, sort_keys=True, default=str).encode()
        fingerprint = UserAccessLog.query.one().payload_hash
        self.assertNotEqual(fingerprint, hashlib.sha256(payload).hexdigest())
        self.assertEqual(fingerprint, hmac.new(self.app.secret_key.encode(), payload, hashlib.sha256).hexdigest())
        self.assertIn('already saved', save_user_access(values, 'account-fingerprint', self.admin.id))

    def test_historical_oversized_rows_remain_readable_without_sum_overflow(self):
        # Simulate rows already present before the additive upgrade, not an allowed new write.
        db.session.remove()
        with db.engine.begin() as connection:
            connection.exec_driver_sql('DROP TRIGGER validate_movement_insert')
            for index in range(2):
                connection.exec_driver_sql('''INSERT INTO JobcardData
                    (date,given_to,given_by,product_list) VALUES ('2026-11-13','RAM','admin','[]')''')
                card_id = connection.exec_driver_sql('SELECT max(id) FROM JobcardData').scalar()
                connection.exec_driver_sql('''INSERT INTO JobmovementData
                    (date,jobcard,partculer,product_name,name_of_mater,enter_user,type_B,flow_type,outflow,inflow)
                    VALUES ('2026-11-13',?,'legacy','VIMAL 1 2MTR','RAM','admin','lump','OUT',?,0)''',
                                           (str(card_id), MAX_DATABASE_INTEGER))
        ensure_security_schema(db.engine, db.engines['users'])
        self.assertEqual(db.session.query(piece_sum(Jobmovement.outflow)).scalar(), 2 * MAX_DATABASE_INTEGER)
        self.assertEqual(self.client.get('/admin_dashord').status_code, 200)
        self.assertEqual(Jobmovement.query.count(), 2)

    def test_existing_schema_upgrade_preserves_users_and_claims(self):
        main = create_engine('sqlite:///:memory:')
        users = create_engine('sqlite:///:memory:')
        try:
            with users.begin() as c:
                c.exec_driver_sql('CREATE TABLE users(id INTEGER PRIMARY KEY, username TEXT, password TEXT, role INTEGER)')
                c.exec_driver_sql("INSERT INTO users VALUES(7,'legacy','hash',1)")
                c.exec_driver_sql('CREATE TABLE user_access_log(id INTEGER PRIMARY KEY)')
            # Copy current ledger schema, but use an old-format request table.
            Jobcard.__table__.create(main)
            Jobmovement.__table__.create(main)
            with main.begin() as c:
                c.exec_driver_sql('CREATE TABLE request_dedup(id INTEGER PRIMARY KEY, request_key TEXT)')
                c.exec_driver_sql("INSERT INTO request_dedup VALUES(1,'old-key')")
            ensure_security_schema(main, users)
            ensure_security_schema(main, users)
            with users.connect() as c:
                row = c.exec_driver_sql('SELECT id,username,password,role,auth_id FROM users').one()
                self.assertEqual(tuple(row[:4]), (7,'legacy','hash',1))
                self.assertEqual(len(row.auth_id), 64)
            with main.connect() as c:
                self.assertEqual(c.exec_driver_sql('SELECT request_key,payload_hash,receipt FROM request_dedup').one(),
                                 ('old-key',None,None))
        finally:
            main.dispose()
            users.dispose()

    def test_concurrent_app_starts_preserve_legacy_user_identity(self):
        root = Path(self.temp.name) / 'parallel-start'
        root.mkdir()
        user_url = f'sqlite:///{root / "users.db"}'
        main_url = f'sqlite:///{root / "main.db"}'
        engine = create_engine(user_url)
        with engine.begin() as connection:
            connection.exec_driver_sql('''CREATE TABLE users(
                id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL, role INTEGER NOT NULL)''')
            connection.exec_driver_sql("INSERT INTO users VALUES(7,'legacy','saved-hash',1)")
        engine.dispose()
        gate = Event()
        def start(_):
            gate.wait()
            app = create_app({'SQLALCHEMY_DATABASE_URI': main_url,
                              'SQLALCHEMY_BINDS': {'users': user_url}, 'TESTING': True})
            try:
                with app.app_context():
                    user = User.query.one()
                    result = (app.secret_key, user.auth_id, user.id, user.password,
                              inspect(db.engine).has_table('JobmovementData'))
                    db.session.remove()
                    return result
            finally:
                with app.app_context():
                    for database in db.engines.values():
                        database.dispose()
        with ThreadPoolExecutor(max_workers=2) as pool:
            pending = [pool.submit(start, index) for index in range(2)]
            gate.set()
            results = [future.result(timeout=30) for future in pending]
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[0][2:], (7, 'saved-hash', True))

    def test_failed_security_upgrade_rolls_back_auth_identity_and_ddl(self):
        main = create_engine('sqlite:///:memory:')
        users = create_engine('sqlite:///:memory:')
        try:
            with users.begin() as connection:
                connection.exec_driver_sql('CREATE TABLE users(id INTEGER PRIMARY KEY, username TEXT)')
                connection.exec_driver_sql("INSERT INTO users VALUES(7,'legacy')")
                connection.exec_driver_sql('CREATE TABLE user_access_log(id INTEGER PRIMARY KEY)')
            def fail(connection, cursor, statement, parameters, context, many):
                if statement.startswith('CREATE UNIQUE INDEX'):
                    raise RuntimeError('simulated upgrade failure')
            event.listen(users, 'before_cursor_execute', fail)
            try:
                with self.assertRaises(RuntimeError):
                    ensure_security_schema(main, users)
            finally:
                event.remove(users, 'before_cursor_execute', fail)
            with users.connect() as connection:
                self.assertEqual(connection.exec_driver_sql('SELECT * FROM users').all(), [(7,'legacy')])
                self.assertNotIn('auth_id', {column['name'] for column in inspect(connection).get_columns('users')})
        finally:
            main.dispose()
            users.dispose()
