"""Login animation is authorized by authentication, not by clicking submit."""
from modes import db
from support import AppTestCase


class LoginAnimationTest(AppTestCase):
    def setUp(self):
        super().setUp()
        self.client.get('/logout')
        self.headers = {'Accept':'application/json'}

    def test_json_login_success_sets_real_session_and_local_destination(self):
        response = self.client.post('/login', data={'user_name':' ADMIN ', 'password':'test-password'}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {'success':True, 'redirect':'/'})
        self.assertIn('no-store', response.headers['Cache-Control'])
        with self.client.session_transaction() as session:
            self.assertEqual(session['_user_id'], self.admin.get_id())

    def test_rejected_logins_never_authenticate_or_supply_destination(self):
        for values, expected in [({},422), ({'user_name':'admin','password':'wrong'},401),
                                 ({'user_name':'unknown','password':'wrong'},401)]:
            with self.subTest(values=values):
                response = self.client.post('/login', data=values, headers=self.headers)
                self.assertEqual(response.status_code,expected)
                self.assertFalse(response.json['success'])
                self.assertNotIn('redirect',response.json)
                with self.client.session_transaction() as session:
                    self.assertNotIn('_user_id',session)

    def test_disabled_and_csrf_failures_remain_enforced(self):
        self.admin.is_active=False
        db.session.commit()
        values={'user_name':'admin','password':'test-password'}
        self.assertEqual(self.client.post('/login',data=values,headers=self.headers).status_code,403)
        self.admin.is_active=True
        db.session.commit()
        self.app.config['WTF_CSRF_ENABLED']=True
        response=self.client.post('/login',data=values,headers=self.headers)
        self.assertEqual(response.status_code,400)
        self.assertIn('expired',response.json['message'])
        with self.client.session_transaction() as session:
            self.assertNotIn('_user_id',session)

    def test_native_fallback_errors_disable_transition_but_success_redirects(self):
        response=self.client.post('/login',data={'user_name':'admin','password':'wrong'})
        self.assertEqual(response.status_code,200)
        self.assertIn('no-page-motion',response.get_data(as_text=True))
        self.assertIn('display:none!important',response.get_data(as_text=True))
        self.assertEqual(self.client.post('/login',data={'user_name':'admin','password':'test-password'}).status_code,302)
