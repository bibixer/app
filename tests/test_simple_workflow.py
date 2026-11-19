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

    def test_bh_favicon_is_available_on_app_pages_and_login(self):
        icon='/static/images/bh-nav-logo.png?v=20261115-favicon'
        for path in ('/manual_jobcard','/admin_dashord','/users'):
            response=self.client.get(path)
            self.assertEqual(response.status_code,200)
            self.assertIn(f'rel="icon" type="image/png" href="{icon}"',response.get_data(as_text=True))
        response=self.client.get(icon)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.mimetype,'image/png')
        self.assertTrue(response.get_data().startswith(b'\x89PNG\r\n\x1a\n'))
        response.close()
        self.client.get('/logout')
        self.assertIn(icon,self.client.get('/login').get_data(as_text=True))

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

    def test_outworker_edit_link_preselects_outworkers_and_invalid_types_fall_back(self):
        import re
        page = self.client.get('/add_outworver').get_data(as_text=True)
        self.assertIn('href="/edit?type=outworker"', page)
        for query, expected in (('?type=outworker','outworker'), ('','product'),
                                ('?type=unknown','product'), ('?type=movement','product'),
                                ('?type=bale','product')):
            with self.subTest(query=query):
                page = self.client.get('/edit'+query).get_data(as_text=True)
                self.assertEqual(re.findall(r'<option value="([^"]+)"\s+selected',page), [expected])

    def test_outworker_form_creates_worker_without_alias_field(self):
        page = self.client.get('/add_outworver').get_data(as_text=True)
        self.assertIn('class="legacy-login"',page)
        self.assertIn('style/login.css',page)
        self.assertIn('outworker-setup-title',page)
        self.assertNotIn('name="aliases"',page)
        self.assertNotIn('Master aliases',page)
        response = self.client.post('/add_outworver',data={
            'name':'FORM WORKER','address':'CITY','number':'9876543210',
            'submission_token':'outworker-no-alias-field'})
        self.assertEqual(response.status_code,302)
        self.assertIsNotNone(Outworker.query.filter_by(name='FORM WORKER').first())

    def test_outworker_creation_exports_csv_once_in_simple_workflow(self):
        result = add_outworker_db({'name': 'NEW WORKER', 'address': 'CITY',
                                  'number': '9876543210', 'aliases': 'NEW'}, self.admin, 'worker-v2')
        self.assertEqual(result, 101)
        self.assertEqual(Outworker.query.count(), 2)
        self.outworker_qr_print.assert_called_once()
        result = add_outworker_db({'name': 'NEW WORKER', 'address': 'CITY',
                                  'number': '9876543210', 'aliases': 'NEW'}, self.admin, 'worker-v2')
        self.assertEqual(result, 409)
        self.outworker_qr_print.assert_called_once()

    def test_outworker_form_writes_original_csv_in_configured_server_folder(self):
        import csv
        from pathlib import Path
        from unittest.mock import patch
        from data_print_format import outworker_qr_print
        self.app.config['LABEL_PRINT_ROOT'] = self.temp.name
        payload = {'name':'CSV WORKER', 'address':'BH GARMENTS', 'number':'9876543210',
                   'submission_token':'form-csv'}
        with patch('data_entry.outworker_qr_print', wraps=outworker_qr_print) as exporter:
            self.assertEqual(self.client.post('/add_outworver',data=payload).status_code,302)
            self.assertEqual(self.client.post('/add_outworver',data=payload).status_code,302)
            exporter.assert_called_once()
        worker = Outworker.query.filter_by(name='CSV WORKER').one()
        with (Path(self.temp.name)/'outworker'/f'{worker.id}.csv').open(newline='') as stream:
            reader = csv.DictReader(stream)
            self.assertEqual(reader.fieldnames,['id','name','address','qr_code'])
            self.assertEqual(next(reader),{'id':str(worker.id),'name':'CSV WORKER',
                'address':'BH GARMENTS','qr_code':f'{worker.id}***CSV WORKER--BH GARMENTS/-'})

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

    def test_admin_creates_admin_account_and_audits_without_passwords(self):
        values = {'action': 'create', 'username': 'NewUser', 'password': 'password123',
                  'role': '1', 'submission_token': 'create-user'}
        self.assertEqual(self.client.post('/users', data=values).status_code, 302)
        self.assertEqual(self.client.post('/users', data=values).status_code, 302)
        user = User.query.filter_by(username='newuser').one()
        self.assertTrue(user.check_password('password123'))
        self.assertEqual(user.role,1)
        self.assertEqual(UserAccessLog.query.count(), 1)
        update = {'action': 'update', 'user_id': str(user.id), 'role': '1',
                  'version': user_version(user), 'submission_token': 'reset-user', 'password': 'updated-password123'}
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
        values.update(action='set_active', active='0', version=user_version(self.operator), submission_token='disable-former-operator')
        self.assertEqual(self.client.post('/users', data=values).status_code, 302)
        self.login_as(self.operator)
        self.assertEqual(self.client.get('/users').status_code, 302)

    def test_retired_role_cannot_be_created_or_assigned_and_legacy_access_is_preserved(self):
        page=self.client.get('/users').get_data(as_text=True)
        self.assertNotIn('<select name="role"',page)
        self.assertNotIn('>Operator<',page)
        self.assertIn('Grant Administrator access',page)
        response=self.client.post('/users',data={'action':'create','username':'retired-role',
            'password':'password123','role':'2','submission_token':'retired-create'})
        self.assertEqual(response.status_code,200)
        self.assertIsNone(User.query.filter_by(username='retired-role').first())
        self.assertEqual(self.operator.role,2)
        response=self.client.post('/users',data={'action':'update','user_id':self.operator.id,
            'role':'2','version':user_version(self.operator),'password':'updated-password123',
            'submission_token':'legacy-reset'})
        self.assertEqual(response.status_code,302)
        self.assertEqual(self.operator.role,2)
        response=self.client.post('/users',data={'action':'update','user_id':self.operator.id,
            'role':'2','grant_admin':'1','version':user_version(self.operator),
            'submission_token':'explicit-upgrade'})
        self.assertEqual(response.status_code,302)
        self.assertEqual(self.operator.role,1)
        response=self.client.post('/users',data={'action':'update','user_id':self.operator.id,
            'role':'2','version':user_version(self.operator),'submission_token':'retired-demotion'})
        self.assertEqual(response.status_code,200)
        self.assertEqual(self.operator.role,1)
