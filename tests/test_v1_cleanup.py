"""Retired entry points stay retired without breaking historical job records."""

from data_entry import add_jobcard
from modes import Bundle, Jobcard, Jobmovement
from simple_workflow import RETIRED_ROUTES
from support import AppTestCase


class V1CleanupTest(AppTestCase):
    def test_old_configuration_cannot_reenable_retired_routes(self):
        for enabled in (True, False):
            self.app.config['SIMPLE_WORKFLOW'] = enabled
            for endpoint, path in RETIRED_ROUTES.items():
                for method in ('get', 'post'):
                    with self.subTest(enabled=enabled, endpoint=endpoint, method=method):
                        response = getattr(self.client, method)(path, json={'request_id': 'retired'})
                        expected = 405 if endpoint == 'submit_jobcard' and method == 'get' else 410
                        self.assertEqual(response.status_code, expected)
                        if endpoint == 'submit_jobcard' and method == 'post':
                            self.assertFalse(response.json['success'])
            self.assertEqual(self.client.get('/jobcard').location, '/manual_jobcard')
            for path in ('/manual_jobcard', '/admin_dashord', '/edit'):
                page = self.client.get(path)
                self.assertEqual(page.status_code, 200)
                self.assertNotIn('Switch to scanning', page.get_data(as_text=True))
                self.assertNotIn('href="/bale_entery"', page.get_data(as_text=True))
        self.assertEqual(Jobcard.query.count(), 0)
        self.assertEqual(Jobmovement.query.count(), 0)
        self.assertEqual(Bundle.query.count(), 0)

    def test_historical_scanned_job_still_has_editor_ledger_and_returns(self):
        bundle = self.bundle(pieces=36)
        # Low-level compatibility importer remains available for historical fixtures.
        card_id = add_jobcard(self.scan_payload(bundle), self.admin, 'historical')['jobData']['jobId']
        before = (Jobcard.query.count(), Bundle.query.count(), Jobmovement.query.count())
        for enabled in (True, False):
            self.app.config['SIMPLE_WORKFLOW'] = enabled
            for path in (f'/edit/jobcard/{card_id}', f'/jobcard/{card_id}/ledger',
                         f'/job_retun?jobcard_id={card_id}'):
                self.assertEqual(self.client.get(path).status_code, 200, path)
        self.assertEqual(before, (Jobcard.query.count(), Bundle.query.count(), Jobmovement.query.count()))
        saved = self.client.post('/summit-retune', json=self.return_payload(card_id, 10))
        self.assertTrue(saved.json['success'])
        self.assertEqual(Jobcard.query.count(), 1)
        self.assertEqual(Bundle.query.count(), 1)
        self.assertEqual(self.client.get(f'/jobcard/{card_id}/ledger').status_code, 200)
