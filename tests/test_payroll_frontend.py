import json
import re
from pathlib import Path
from unittest.mock import patch

from data_entry import add_manual_jobcard, in_move_entery
from modes import OutworkerPayroll, OutworkerAdvanceRecovery, OutworkerRate, OutworkerAdvanceReceipt
from payroll_service import record_advance, save_rate, rate_version, advance_balance, receive_advance
from support import AppTestCase


class FrontendPayrollTest(AppTestCase):
    def setUp(self):
        super().setUp()
        save_rate(self.product.id, '', '5.5555', 'new', 'rate', self.admin)
        self.advance = record_advance(self.worker.id, '10', 'Cash', '', '', 'advance', self.admin).id
        result = add_manual_jobcard(self.manual_payload(pieces=3, count=1), self.admin, 'job')
        self.card = result['jobData']['jobId']
        in_move_entery(self.return_payload(self.card, 3), self.admin, 'return')
        with patch('payroll_routes.payroll_preview', side_effect=AssertionError('No preview request on page load')):
            html = self.client.get(f'/payroll?worker_id={self.worker.id}').get_data(as_text=True)
        self.assertIn('<dialog class="panel review payroll-review-dialog"', html)
        self.assertIn('id="payrollReviewClose"', html)
        self.assertIn('id="payrollModalAdvancesHeading"', html)
        self.assertIn('data-payroll-advance', html)
        self.snapshot = re.search(r'name="client_snapshot" value="([^"]+)"', html).group(1)
        self.client_data = json.loads(re.search(r'id="payrollClientData" type="application/json">(.*?)</script>', html).group(1))

    def pay(self, **changes):
        payload = {'action':'pay', 'worker_id':self.worker.id, 'job_ids':str(self.card),
                   'advance_selection':'1', 'advance_ids':str(self.advance),
                   'deduction':'10.00', 'client_snapshot':self.snapshot,
                   'method':'Cash', 'submission_token':'client-pay'}
        payload.update(changes)
        return self.client.post('/payroll', data=payload)

    def test_loaded_data_and_signed_confirmation(self):
        self.assertEqual(self.client_data['jobs'][0]['gross_paise'], 1667)
        response = self.pay()
        self.assertEqual(response.status_code, 302)
        payment = OutworkerPayroll.query.one()
        self.assertEqual((payment.gross_paise, payment.deduction_paise, payment.net_paise), (1667, 1000, 667))
        self.assertEqual(OutworkerAdvanceRecovery.query.one().advance_id, self.advance)
        self.pay()
        self.assertEqual(OutworkerPayroll.query.count(), 1)

    def test_advance_only_confirmation_receives_money_without_payroll(self):
        response = self.pay(action='recover_selected_advances', job_ids=[])
        self.assertEqual(response.status_code, 302)
        self.assertEqual(OutworkerPayroll.query.count(), 0)
        self.assertEqual(OutworkerAdvanceRecovery.query.count(), 0)
        self.assertEqual(OutworkerAdvanceReceipt.query.one().amount_paise, 1000)
        self.assertEqual(advance_balance(self.worker.id), 0)
        self.pay(action='recover_selected_advances', job_ids=[])
        self.assertEqual(OutworkerAdvanceReceipt.query.count(), 1)

    def test_full_repayment_receipt_and_failed_export_recovery(self):
        self.app.config['LABEL_PRINT_ROOT'] = self.temp.name
        another = record_advance(self.worker.id, '500', 'Cash', '', '', 'second-advance', self.admin)
        account = self.client.get(f'/payroll?worker_id={self.worker.id}').get_data(as_text=True)
        snapshot = re.search(r'name="client_snapshot" value="([^"]+)"', account)[1]
        with self.assertLogs(level='ERROR'), patch('payroll_service.payroll_bill_csv', side_effect=OSError):
            response = self.pay(advance_ids=[self.advance, another.id], deduction='0', repayment='510',
                                client_snapshot=snapshot)
        self.assertEqual(response.status_code, 302)
        payroll = OutworkerPayroll.query.one()
        path = Path(self.temp.name) / 'payroll' / f'payroll_{payroll.id}.csv'
        self.assertFalse(path.exists())
        self.client.get(response.location)
        receipt = self.client.get(response.location).get_data(as_text=True)
        self.assertIn('₹510.00', receipt)
        self.assertIn('₹493.33', receipt)
        self.assertEqual(self.client.post(response.location, data={'submission_token':'export'}).status_code, 302)
        self.assertEqual(path.read_bytes().decode('utf-8'), payroll.receipt_archive['csv'])
        self.assertEqual(OutworkerPayroll.query.count(), 1)
        self.assertEqual(OutworkerAdvanceReceipt.query.count(), 2)

    def test_advance_only_rejects_jobs_bad_total_and_tampered_snapshot(self):
        for changes in ({'job_ids':str(self.card)}, {'job_ids':[], 'deduction':'9.00'},
                        {'job_ids':[], 'client_snapshot':self.snapshot+'bad'}, {'job_ids':[], 'advance_ids':[]}):
            response = self.pay(action='recover_selected_advances', **changes)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(OutworkerAdvanceReceipt.query.count(), 0)
            self.assertEqual(OutworkerPayroll.query.count(), 0)

    def test_advance_only_rejects_changed_outstanding_balance(self):
        receive_advance(self.worker.id, self.advance, '1', 1000, 'Cash', '', '', 'partial', self.admin)
        html = self.pay(action='recover_selected_advances', job_ids=[]).get_data(as_text=True)
        self.assertIn('Advance balances changed', html)
        self.assertEqual(OutworkerAdvanceReceipt.query.count(), 1)
        self.assertEqual(advance_balance(self.worker.id), 900)

    def test_modified_token_or_wrong_amount_cannot_save(self):
        for changes in ({'client_snapshot':self.snapshot+'bad'}, {'deduction':'9.00'}):
            response = self.pay(**changes)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(OutworkerPayroll.query.count(), 0)

    def test_changed_rate_rejected_at_confirmation(self):
        rate = OutworkerRate.query.one()
        save_rate(self.product.id, '', '6', rate_version(rate), 'new-rate', self.admin)
        html = self.pay().get_data(as_text=True)
        self.assertIn('Calculate the payroll again', html)
        self.assertEqual(OutworkerPayroll.query.count(), 0)

    def test_changed_advance_or_expired_review_rejected(self):
        record_advance(self.worker.id, '1', 'Cash', '', '', 'another', self.admin)
        self.assertIn('Calculate the payroll again', self.pay().get_data(as_text=True))
        from itsdangerous import SignatureExpired
        with patch('payroll_routes.URLSafeTimedSerializer') as serializer:
            serializer.return_value.loads.side_effect = SignatureExpired('expired')
            serializer.return_value.dumps.return_value = 'fresh-snapshot'
            self.assertIn('review expired', self.pay().get_data(as_text=True))
        self.assertEqual(OutworkerPayroll.query.count(), 0)
