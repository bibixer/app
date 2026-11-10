from datetime import datetime

from data_entry import add_manual_jobcard, in_move_entery
from modes import db, Outworker, OutworkerPayroll, OutworkerAdvanceRecovery
from payroll_service import (record_advance, save_rate, payroll_preview, issue_payroll,
                             advance_entries, advance_balance)
from support import AppTestCase


class IndividualAdvanceTest(AppTestCase):
    def setUp(self):
        super().setUp()
        save_rate(self.product.id, '', '100', 'new', 'rate', self.admin)
        self.a = record_advance(self.worker.id, '100', 'Cash', 'A', '', 'a', self.admin).id
        self.b = record_advance(self.worker.id, '200', 'UPI', 'B', '', 'b', self.admin).id
        result = add_manual_jobcard(self.manual_payload(pieces=10, count=1), self.admin, 'card')
        self.card = result['jobData']['jobId']
        in_move_entery(self.return_payload(self.card, 10), self.admin, 'returned')

    def pay(self, ids, key='pay'):
        quote = payroll_preview(self.worker.id, [self.card], '0', advance_ids=ids)
        return issue_payroll(self.worker.id, [self.card], '0', quote['version'], 'Cash', '', '', key,
                             self.admin, advance_ids=ids)

    def test_select_only_second_leaves_first_untouched(self):
        payment = self.pay([self.b])
        self.assertEqual(payment.deduction_paise, 20000)
        self.assertEqual({row['id']: row['remaining_paise'] for row in advance_entries(self.worker.id)},
                         {self.a: 10000, self.b: 0})
        recovery = OutworkerAdvanceRecovery.query.one()
        self.assertEqual((recovery.advance_id, recovery.amount_paise), (self.b, 20000))
        self.assertEqual(advance_balance(self.worker.id), 10000)
        receipt = self.client.get(f'/payroll/{payment.id}').get_data(as_text=True)
        self.assertIn('Advances recovered in this payroll', receipt)
        self.assertIn(f'Advance #{self.b}', receipt)

    def test_all_caps_to_payroll_and_keeps_partial_advance(self):
        from payroll_service import rate_version
        from modes import OutworkerRate
        rate = OutworkerRate.query.one()
        save_rate(self.product.id, '', '15', rate_version(rate), 'smaller-rate', self.admin)
        quote = payroll_preview(self.worker.id, [self.card], '0', advance_ids=[self.b, self.a])
        self.assertEqual(quote['advance_recoveries'], [
            {'advance_id': self.a, 'amount_paise': 10000},
            {'advance_id': self.b, 'amount_paise': 5000},
        ])
        self.pay([self.a, self.b])
        self.assertEqual([row['remaining_paise'] for row in advance_entries(self.worker.id)], [0, 15000])
        result = add_manual_jobcard(self.manual_payload(pieces=10, count=1), self.admin, 'next-card')
        next_id = result['jobData']['jobId']
        in_move_entery(self.return_payload(next_id, 10), self.admin, 'next-return')
        with self.assertRaises(ValueError):
            payroll_preview(self.worker.id, [next_id], '0', advance_ids=[self.a])
        quote = payroll_preview(self.worker.id, [next_id], '0', advance_ids=[self.b])
        self.assertEqual(quote['deduction_paise'], 15000)

    def test_all_none_and_duplicates(self):
        for ids, expected in (([], 0), ([self.a], 10000), ([self.a, self.b], 30000), ([self.b, self.b], 20000)):
            self.assertEqual(payroll_preview(self.worker.id, [self.card], '0', advance_ids=ids)['deduction_paise'], expected)
        self.pay([])
        self.assertEqual(OutworkerAdvanceRecovery.query.count(), 0)
        self.assertEqual(advance_balance(self.worker.id), 30000)

    def test_foreign_invalid_and_stale_selection_rejected(self):
        worker = Outworker(name='OTHER', adders='CITY', number=555, enter_user='admin')
        db.session.add(worker)
        db.session.commit()
        foreign = record_advance(worker.id, '100', 'Cash', '', '', 'foreign', self.admin).id
        for ids in ([foreign], ['bad'], ['99999999']):
            with self.assertRaises(ValueError):
                payroll_preview(self.worker.id, [self.card], '0', advance_ids=ids)
        quote = payroll_preview(self.worker.id, [self.card], '0', advance_ids=[self.a])
        with self.assertRaises(ValueError):
            issue_payroll(self.worker.id, [self.card], '0', quote['version'], 'Cash', '', '', 'tampered',
                          self.admin, advance_ids=[self.b])
        self.assertEqual(OutworkerPayroll.query.count(), 0)

    def test_historical_deductions_use_oldest_first_without_changing_receipts(self):
        old = OutworkerPayroll(worker_id=self.worker.id, worker_name=self.worker_name,
            gross_paise=15000, deduction_paise=15000, net_paise=0, paid_at=datetime.now(),
            method='Cash', reference='', note='', recorded_by='admin')
        db.session.add(old)
        db.session.commit()
        entries = advance_entries(self.worker.id)
        self.assertEqual([row['remaining_paise'] for row in entries], [0, 15000])
        with self.assertRaises(ValueError):
            payroll_preview(self.worker.id, [self.card], '0', advance_ids=[self.a])
        self.pay([self.b])
        self.assertEqual(advance_balance(self.worker.id), 0)
        self.assertEqual([row['remaining_paise'] for row in advance_entries(self.worker.id)], [0, 0])
        self.assertEqual(db.session.get(OutworkerPayroll, old.id).deduction_paise, 15000)

    def test_http_selection_survives_preview_and_confirmation(self):
        payload = {'worker_id': self.worker.id, 'job_ids': str(self.card), 'advance_selection':'1',
                   'advance_ids':str(self.b), 'action':'preview', 'submission_token':'preview'}
        html = self.client.post('/payroll', data=payload).get_data(as_text=True)
        self.assertIn('Select all advances', html)
        self.assertIn(f'type="hidden" name="advance_ids" value="{self.b}"', html)
        quote = payroll_preview(self.worker.id, [self.card], '0', advance_ids=[self.b])
        payload.update(action='pay', deduction='200.00', version=quote['version'], method='Cash', submission_token='http-pay')
        response = self.client.post('/payroll', data=payload)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(OutworkerAdvanceRecovery.query.one().advance_id, self.b)
