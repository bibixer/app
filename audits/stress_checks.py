"""Additional isolated malformed-input and concurrent-return checks."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import threading

from data_entry import add_manual_jobcard, in_move_entery
from modes import db, Jobcard, Jobmovement, User
from support import AppTestCase


class StressChecks(AppTestCase):
    def setUp(self):
        super().setUp()
        self.app.config.update(SIMPLE_WORKFLOW=True, PROPAGATE_EXCEPTIONS=False)

    def test_malformed_manual_fields_do_not_produce_server_errors(self):
        invalids = [None, True, False, [], {}, '', -1, 0, 1.5, '1', 10**100]
        for field in ('product', 'type', 'pieces', 'count'):
            for index, value in enumerate(invalids):
                payload = self.manual_payload(key=f'{field}-{index}')
                payload['rows'][0][field] = value
                with self.subTest(field=field, value=value):
                    response = self.client.post('/submit-manual-jobcard', json=payload)
                    self.assertEqual(response.status_code, 400)
        self.assertEqual(Jobcard.query.count(), 0)

    def test_malformed_returns_leave_balance_unchanged(self):
        card_id = add_manual_jobcard(self.manual_payload(), self.admin, 'job')['jobData']['jobId']
        original = self.return_payload(card_id, 1)
        for field in ('item_id', 'returned', 'name_of_product', 'type', 'entry_method', 'calculation_rows'):
            for index, value in enumerate((None, True, {}, [], -1, 'invalid', 10**100)):
                payload = deepcopy(original)
                payload['request_id'] = f'{field}-{index}'
                payload['items'][0][field] = value
                # An empty list is valid only for direct-entry calculation rows.
                if field == 'calculation_rows' and value == []:
                    continue
                with self.subTest(field=field, value=value):
                    response = self.client.post('/summit-retune', json=payload)
                    self.assertLess(response.status_code, 500)
                    self.assertFalse(response.json.get('success'))
        self.assertEqual(Jobmovement.query.filter_by(flow_type='IN').count(), 0)

    def test_twelve_simultaneous_returns_do_not_exceed_given_quantity(self):
        card_id = add_manual_jobcard(self.manual_payload(pieces=10, count=1), self.admin, 'job')['jobData']['jobId']
        payload = self.return_payload(card_id, 2)
        user_id = self.admin.id
        barrier = threading.Barrier(12)
        db.session.remove()

        def save(index):
            with self.app.app_context():
                user = db.session.get(User, user_id)
                barrier.wait(timeout=15)
                try:
                    return in_move_entery(deepcopy(payload), user, f'contender-{index}')
                finally:
                    db.session.remove()

        with ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(save, range(12)))
        self.assertEqual(sum(isinstance(result, dict) for result in results), 5)
        self.assertNotIn(500, results)
        self.assertEqual(sum(row.inflow for row in Jobmovement.query.filter_by(flow_type='IN')), 10)
