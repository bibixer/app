"""Payroll shares job-card master lookup; payment actions still use explicit IDs."""
from urllib.parse import urlencode
from datetime import datetime
import re

from support import AppTestCase
from modes import db, Outworker, OutworkerAdvance, OutworkerPayroll


class PayrollLookupTest(AppTestCase):
    def test_ledger_defaults_newest_first_with_original_running_balances(self):
        for day, amount in ((1, 10000), (2, 20000)):
            db.session.add(OutworkerAdvance(worker_id=self.worker.id, worker_name=self.worker_name,
                amount_paise=amount, paid_at=datetime(2026, 11, day), method='Cash',
                reference='', note='', recorded_by='admin'))
        db.session.add(OutworkerPayroll(worker_id=self.worker.id, worker_name=self.worker_name,
            gross_paise=10000, deduction_paise=5000, net_paise=5000,
            paid_at=datetime(2026, 11, 3), method='Cash', reference='', note='', recorded_by='admin'))
        db.session.commit()
        html = self.client.get(f'/payroll?worker_id={self.worker.id}').get_data(as_text=True)
        ledger = html.split('<tbody id="payrollLedgerRows">', 1)[1].split('</tbody>', 1)[0]
        rows = re.findall(r'<tr data-ledger-order="(\d+)">(.*?)</tr>', ledger, re.S)
        self.assertEqual([index for index, row in rows], ['2', '1', '0'])
        balances = [re.findall(r'<td class="number">(.*?)</td>', row)[4] for index, row in rows]
        self.assertEqual(balances, ['₹250.00', '₹300.00', '₹100.00'])
        self.assertIn('<option value="newest" selected>Newest first', html)
        self.assertIn('<option value="oldest">Oldest first', html)
        from payroll_service import payment_account
        self.assertEqual([event['balance_paise'] for event in payment_account(self.worker.id)['events']],
                         [10000, 30000, 25000])

    def test_name_alias_id_and_full_name_open_same_account(self):
        for value in ('RAM', ' ram   city ', str(self.worker.id), self.worker_name):
            with self.subTest(value=value):
                response = self.client.get('/payroll?' + urlencode({'worker_name': value}))
                self.assertEqual(response.status_code, 200)
                html = response.get_data(as_text=True)
                self.assertIn(f'name="worker_id" value="{self.worker.id}"', html)
                self.assertIn('Jobs with returned or kept pieces to pay', html)

    def test_unknown_blank_and_ambiguous_names_do_not_open_or_create(self):
        db.session.add(Outworker(name='RAM', adders='OTHER', number=555, enter_user='admin'))
        db.session.commit()
        for value in ('RAM', 'unknown', '', '99999999'):
            with self.subTest(value=value):
                html = self.client.get('/payroll?' + urlencode({
                    'worker_name': value, 'worker_id': self.worker.id,
                })).get_data(as_text=True)
                self.assertIn('Select an existing outworker by name, alias or ID.', html)
                self.assertNotIn('Jobs with returned or kept pieces to pay', html)
        self.assertEqual(Outworker.query.count(), 2)
        self.assertEqual(OutworkerAdvance.query.count(), 0)
        self.assertEqual(OutworkerPayroll.query.count(), 0)

    def test_existing_id_links_and_lookup_markup(self):
        html = self.client.get(f'/payroll?worker_id={self.worker.id}').get_data(as_text=True)
        self.assertIn('id="payrollWorker"', html)
        self.assertIn('name="worker_name"', html)
        self.assertIn('RAM CITY', html)
        self.assertIn('payroll-worker.js', html)
        self.assertNotIn('<select name="worker_id"', html)
        self.assertIn('Jobs with returned or kept pieces to pay', html)

    def test_lookup_does_not_replace_post_payment_worker_id(self):
        response = self.client.post('/payroll?worker_name=RAM', data={
            'action': 'advance', 'amount': '10', 'method': 'Cash',
            'submission_token': 'lookup-cannot-pay',
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('Select an existing outworker.', response.get_data(as_text=True))
        self.assertEqual(OutworkerAdvance.query.count(), 0)

    def test_operator_cannot_access_payroll_lookup(self):
        self.login_as(self.operator)
        response = self.client.get('/payroll?worker_name=RAM')
        self.assertEqual(response.status_code, 302)
        self.assertNotIn('Jobs with returned or kept pieces to pay', response.get_data(as_text=True))
