"""Notification markup and server fallback keep messages safe and correctly typed."""
from support import AppTestCase


class NotificationTest(AppTestCase):
    def test_shared_notification_assets_and_region_on_every_page(self):
        for path in ('/manual_jobcard', '/retune_product', '/payroll', '/payroll/rates',
                     '/edit', '/edit-logs', '/admin_dashord', '/users', '/add_outworver'):
            with self.subTest(path=path):
                page = self.client.get(path).get_data(as_text=True)
                self.assertEqual(page.count('id="appNotifications"'), 1)
                self.assertIn('js/notifications.js', page)
                self.assertIn('style/notifications.css', page)
        self.client.get('/logout')
        self.assertIn('id="appNotifications"', self.client.get('/login').get_data(as_text=True))

    def test_flash_category_preserved_once_escaped_and_available_without_js(self):
        with self.client.session_transaction() as session:
            session['_flashes'] = [('success', 'Saved <script>unsafe()</script>'), ('danger', 'Could not save')]
        page = self.client.get('/edit').get_data(as_text=True)
        self.assertEqual(page.count('Saved &lt;script&gt;unsafe()&lt;/script&gt;'), 1)
        self.assertIn('data-app-notice="success" role="status"', page)
        self.assertIn('data-app-notice="danger" role="alert"', page)
        self.assertNotIn('<script>unsafe()</script>', page)
        self.assertNotIn('Could not save', self.client.get('/edit').get_data(as_text=True))

    def test_success_after_redirect_and_form_errors_have_popup_sources(self):
        response = self.client.post('/add_items', data={
            'name':'NOTIFICATION PRODUCT', 'aliases':'NP', 'submission_token':'notice-save'}, follow_redirects=True)
        self.assertIn('data-app-notice="success"', response.get_data(as_text=True))
        page = self.client.post('/add_outworver', data={
            'name':'', 'address':'', 'number':'', 'submission_token':'invalid-notice'}).get_data(as_text=True)
        self.assertIn('data-app-notice="error" role="alert"', page)
        self.assertIn('This field is required.', page)

    def test_error_pages_include_feedback_and_keep_protocol_status(self):
        response = self.client.get('/not-a-real-page')
        self.assertEqual(response.status_code, 404)
        self.assertIn('id="appNotifications"', response.get_data(as_text=True))
        self.assertIn('role="alert"', response.get_data(as_text=True))
        response = self.client.post('/edit')
        self.assertEqual(response.status_code, 405)
        self.assertIn('GET', response.headers['Allow'])
        self.assertIn('id="appNotifications"', response.get_data(as_text=True))
        response = self.client.get('/jobcard/99999/ledger')
        self.assertEqual(response.status_code, 404)
        self.assertIn('role="alert"', response.get_data(as_text=True))
