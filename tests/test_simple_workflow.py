"""V2 is manual-only; old inventory URLs cannot write and users have real roles."""

from app import create_app
from data_entry import add_outworker_db
from modes import db, User, UserAccessLog, Jobcard, Jobmovement, Bundle, Item_data, Outworker
from simple_workflow import job_overview, user_version
from support import AppTestCase


class SimpleWorkflowTest(AppTestCase):
    def setUp(self):
        super().setUp()
        self.app.config['SIMPLE_WORKFLOW'] = True

    def test_factory_defaults_to_v2_and_old_urls_cannot_write(self):
        default_app = create_app()
        self.assertTrue(default_app.config['SIMPLE_WORKFLOW'])
        with default_app.app_context():
            db.session.remove()
            for engine in db.engines.values():
                engine.dispose()
        for path in ('/bale_entery', '/lumpentry', '/bundle_entery', '/add_cutter',
                     '/add_suppy', '/cutter_report', '/product_report', '/find_edit',
                     '/submit-jobcard', '/edit/bale/1', '/edit/lump/1',
                     '/edit/bundle/1', '/edit/cutter/1', '/edit/party/1'):
            for method in ('get', 'post'):
                with self.subTest(path=path, method=method):
                    response = getattr(self.client, method)(path, json={'request_id': 'disabled'})
                    self.assertEqual(response.status_code, 405 if path == '/submit-jobcard' and method == 'get' else 410)
        self.assertEqual(Jobcard.query.count(), 0)
        self.assertEqual(Bundle.query.count(), 0)
        for entity in ('bale', 'lump', 'bundle', 'cutter', 'party'):
            self.assertEqual(self.client.get('/edit/search', query_string={'type': entity}).status_code, 410)
        self.assertEqual(self.client.get('/edit/movement/1').status_code, 403)

    def test_navigation_and_edit_center_only_offer_core_workflows(self):
        for path in ('/admin_dashord', '/manual_jobcard', '/edit', '/users', '/add_items', '/retune_product'):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                html = response.get_data(as_text=True)
                for forbidden in ('href="/bale_entery"', 'href="/jobcard"',
                                  'href="/add_cutter"', 'href="/add_suppy"',
                                  'href="/find_edit"', 'href="/product_report"',
                                  'Switch to scanning'):
                    self.assertNotIn(forbidden, html)
        html = self.client.get('/edit').get_data(as_text=True)
        for kind in ('bale', 'lump', 'bundle', 'cutter', 'party', 'movement'):
            self.assertNotIn(f'<option value="{kind}"', html)
        self.assertEqual(self.client.get('/jobcard').location, '/manual_jobcard')

    def test_operator_assigns_and_returns_manual_job_with_csv_but_no_qr(self):
        self.login_as(self.operator)
        self.assertEqual(self.client.get('/').location, '/manual_jobcard')
        self.assertEqual(self.client.get('/jobcard').location, '/manual_jobcard')
        self.assertEqual(self.client.get('/manual_jobcard').status_code, 200)
        payload = self.manual_payload()
        response = self.client.post('/submit-manual-jobcard', json=payload)
        self.assertEqual(response.status_code, 200)
        card_id = response.json['jobData']['jobId']
        self.assertTrue(self.client.post('/submit-manual-jobcard', json=payload).json['duplicate'])
        response = self.client.post('/summit-retune', json=self.return_payload(card_id, 50))
        self.assertTrue(response.json['success'])
        self.assertEqual(self.client.get(f'/jobcard/{card_id}/ledger').status_code, 200)
        self.assertEqual(self.client.get(f'/job_retun?jobcard_id={card_id}').status_code, 200)
        self.assertEqual(Jobcard.query.one().given_by, self.operator.username)
        self.assertEqual(Bundle.query.count(), 0)
        self.assertEqual(job_overview()['pending'], 70)
        self.assertEqual(job_overview()['open_jobs'], 1)
        remaining = self.return_payload(card_id, 70, key='return-rest')
        self.assertTrue(self.client.post('/summit-retune', json=remaining).json['success'])
        self.assertEqual(job_overview()['pending'], 0)
        self.assertEqual(job_overview()['open_jobs'], 0)
        self.job_cade_print.assert_called_once()
        self.outworker_qr_print.assert_not_called()
        self.buldel_qr_print.assert_not_called()

    def test_outworker_creation_does_not_print(self):
        result = add_outworker_db({'name': 'NEW WORKER', 'address': 'CITY',
                                  'number': 456, 'aliases': 'NEW'}, self.admin, 'worker-v2')
        self.assertEqual(result, 101)
        self.assertEqual(Outworker.query.count(), 2)
        self.outworker_qr_print.assert_not_called()

    def test_product_only_needs_name_alias_then_opens_rates(self):
        response = self.client.post('/add_items', data={
            'name': 'NEW PRODUCT', 'aliases': 'NP', 'submission_token': 'product-v2',
        })
        product = Item_data.query.filter_by(name='NEW PRODUCT').one()
        self.assertEqual(response.status_code, 302)
        self.assertIn(f'/payroll/rates?product_id={product.id}', response.location)
        self.assertEqual([row.alias for row in product.alias_rows], ['NP'])
        self.assertNotIn('name="meter"', self.client.get('/add_items').get_data(as_text=True))
        self.assertEqual(self.client.get(response.location).status_code, 200)

    def test_operator_cannot_manage_setup_roles_payments_or_corrections(self):
        self.login_as(self.operator)
        for path in ('/users', '/add_items', '/add_outworver', '/payroll/rates',
                     '/payroll', '/edit', '/edit/product/1', '/admin_dashord'):
            for method in ('get', 'post'):
                response = getattr(self.client, method)(path, data={
                    'action': 'create', 'username': 'intruder', 'password': 'password123',
                    'role': '1', 'submission_token': 'forbidden',
                })
                self.assertEqual(response.status_code, 405 if path == '/edit' and method == 'post' else 302, path)
        self.assertEqual(User.query.count(), 2)

    def test_admin_creates_account_updates_role_and_audits_without_passwords(self):
        values = {'action': 'create', 'username': 'NewUser', 'password': 'password123',
                  'role': '2', 'submission_token': 'create-user'}
        self.assertEqual(self.client.post('/users', data=values).status_code, 302)
        self.assertEqual(self.client.post('/users', data=values).status_code, 302)
        user = User.query.filter_by(username='newuser').one()
        self.assertTrue(user.check_password('password123'))
        self.assertEqual(UserAccessLog.query.count(), 1)
        update = {'action': 'update', 'user_id': str(user.id), 'role': '1',
                  'version': user_version(user), 'submission_token': 'promote-user', 'password': ''}
        self.assertEqual(self.client.post('/users', data=update).status_code, 302)
        self.assertEqual(user.role, 1)
        self.assertEqual(UserAccessLog.query.count(), 2)
        # A stale form cannot undo a subsequent account change.
        update.update(role='2', submission_token='stale-user')
        self.assertEqual(self.client.post('/users', data=update).status_code, 200)
        self.assertEqual(user.role, 1)
        html = self.client.get('/users').get_data(as_text=True)
        self.assertNotIn('password123', html)
        self.assertNotIn(user.password, html)
        self.assertIn('Account change history', html)

    def test_admin_cannot_demote_self_and_invalid_forms_do_not_save(self):
        data = {'action': 'update', 'user_id': str(self.admin.id), 'role': '2',
                'version': user_version(self.admin), 'submission_token': 'demote-self'}
        self.assertEqual(self.client.post('/users', data=data).status_code, 200)
        self.assertEqual(self.admin.role, 1)
        for values in ({'role': '7', 'password': 'password123'},
                       {'role': '2', 'password': 'short'}):
            values.update(action='create', username='invalid', submission_token='invalid')
            self.assertEqual(self.client.post('/users', data=values).status_code, 200)
        self.assertEqual(self.client.post('/users', data={
            'action': 'create', 'username': 'missing-token', 'password': 'password123', 'role': '2',
        }).status_code, 200)
        self.assertEqual(User.query.count(), 2)
        self.assertEqual(UserAccessLog.query.count(), 0)

    def test_role_changes_apply_to_existing_sessions_and_missing_csrf_is_rejected(self):
        self.app.config['WTF_CSRF_ENABLED'] = True
        values = {'action': 'create', 'username': 'csrf-missing', 'password': 'password123',
                  'role': '1', 'submission_token': 'csrf-missing'}
        self.assertEqual(self.client.post('/users', data=values).status_code, 200)
        self.assertEqual(User.query.count(), 2)
        self.app.config['WTF_CSRF_ENABLED'] = False
        values = {'action': 'update', 'user_id': str(self.operator.id), 'role': '1',
                  'version': user_version(self.operator), 'submission_token': 'promote-operator'}
        self.assertEqual(self.client.post('/users', data=values).status_code, 302)
        self.login_as(self.operator)
        self.assertEqual(self.client.get('/users').status_code, 200)
        self.login_as(self.admin)
        values.update(role='2', version=user_version(self.operator), submission_token='demote-operator')
        self.assertEqual(self.client.post('/users', data=values).status_code, 302)
        self.login_as(self.operator)
        self.assertEqual(self.client.get('/users').status_code, 302)
