"""Original audit reproductions, now expected to pass after hardening.

PYTHONPATH=tests:. .venv/bin/python -m unittest discover -s audits -p security_regressions.py -v
All checks use temporary databases and mocked printers from AppTestCase.
"""

from datetime import datetime

from flask import Flask
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from modes import db, Jobmovement, User
from simple_workflow import save_user_access, user_version
from support import AppTestCase


class SecurityRegressions(AppTestCase):
    def setUp(self):
        super().setUp()
        self.app.config['SIMPLE_WORKFLOW'] = True

    def change_user(self, user, action, token, **extra):
        return save_user_access(dict(action=action, user_id=str(user.id),
                                     version=user_version(user), **extra), token, self.admin.id)

    def test_disabled_user_is_blocked_on_next_request(self):
        self.login_as(self.operator)
        self.change_user(self.operator, 'set_active', 'disable', active='0')
        self.assertEqual(self.client.get('/manual_jobcard').status_code, 302)

    def test_deleted_user_is_blocked_on_next_request(self):
        self.login_as(self.operator)
        self.change_user(self.operator, 'delete', 'delete')
        self.assertEqual(self.client.get('/manual_jobcard').status_code, 302)

    def test_reenable_does_not_restore_an_old_login_cookie(self):
        self.login_as(self.operator)
        self.change_user(self.operator, 'set_active', 'disable', active='0')
        self.change_user(self.operator, 'set_active', 'enable', active='1')
        self.assertEqual(self.client.get('/manual_jobcard').status_code, 302,
                         'A disabled session must require a fresh login after reenabling.')

    def test_deleted_account_cookie_cannot_become_a_new_admin(self):
        self.login_as(self.operator)
        previous_id = self.operator.id
        self.change_user(self.operator, 'delete', 'delete')
        save_user_access(dict(action='create', username='replacement-admin',
                              password='temporary-password', role='1'), 'create', self.admin.id)
        replacement = User.query.filter_by(username='replacement-admin').one()
        self.assertEqual(self.client.get('/users').status_code, 302,
                         f'Old account #{previous_id} cookie authenticated as new account #{replacement.id}.')

    def test_password_change_revokes_other_login_sessions(self):
        self.login_as(self.operator)
        self.change_user(self.operator, 'update', 'password', role='2', password='replacement-password')
        self.assertEqual(self.client.get('/manual_jobcard').status_code, 302)

    def test_known_fallback_key_cannot_forge_admin_cookie(self):
        fallback = '8BYkEfBA6O6donzWlSihBXox7C0sKR6b'
        self.assertNotEqual(self.app.secret_key, fallback)
        attacker_app = Flask('audit-cookie-signer')
        attacker_app.secret_key = fallback
        signer = attacker_app.session_interface.get_signing_serializer(attacker_app)
        self.client.set_cookie(self.app.config['SESSION_COOKIE_NAME'],
                               signer.dumps({'_user_id': self.admin.get_id(), '_fresh': True}))
        self.assertEqual(self.client.get('/users').status_code, 302)

    def test_unhashable_bundle_type_returns_400_not_500(self):
        payload = self.manual_payload()
        payload['rows'][0]['type'] = []
        self.app.config['PROPAGATE_EXCEPTIONS'] = False
        response = self.client.post('/submit-manual-jobcard', json=payload)
        self.assertEqual(response.status_code, 400)

    def test_retry_token_cannot_silently_accept_changed_payload(self):
        payload = self.manual_payload()
        self.assertEqual(self.client.post('/submit-manual-jobcard', json=payload).status_code, 200)
        payload['rows'][0]['pieces'] = 99
        response = self.client.post('/submit-manual-jobcard', json=payload)
        self.assertEqual(response.status_code, 409,
                         'Reusing an idempotency token for different data must report a conflict.')

    def test_network_retry_returns_original_saved_job_for_printing(self):
        payload = self.manual_payload()
        first = self.client.post('/submit-manual-jobcard', json=payload)
        self.assertTrue(first.json['success'])
        retry = self.client.post('/submit-manual-jobcard', json=payload)
        self.assertTrue(retry.json['success'])
        self.assertEqual(retry.json.get('jobData', {}).get('jobId'), first.json['jobData']['jobId'],
                         'After a lost response the client needs the saved job ID to render/print it.')

    def test_database_rejects_negative_or_orphan_movement(self):
        invalid = Jobmovement(date=datetime.now(), jobcard='999999', partculer='audit',
                              product_name='MISSING', name_of_mater='MISSING', enter_user='audit',
                              type_B='invalid', flow_type='OUT', outflow=-10, inflow=0)
        try:
            db.session.add(invalid)
            with self.assertRaises(IntegrityError):
                db.session.flush()
        finally:
            db.session.rollback()

    def test_sqlite_enforces_declared_foreign_keys(self):
        enabled = db.session.execute(text('PRAGMA foreign_keys')).scalar()
        self.assertEqual(enabled, 1, 'Declared foreign keys are inactive on this connection.')

    def test_excessive_jobs_are_rejected_without_breaking_dashboard(self):
        from validation import MAX_DATABASE_INTEGER
        for index in range(2):
            payload = self.manual_payload(pieces=MAX_DATABASE_INTEGER, count=1, key=f'large-{index}')
            self.assertEqual(self.client.post('/submit-manual-jobcard', json=payload).status_code, 400)
        self.app.config['PROPAGATE_EXCEPTIONS'] = False
        self.assertEqual(self.client.get('/admin_dashord').status_code, 200)
