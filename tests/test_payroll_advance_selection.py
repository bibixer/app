"""Selection-based advance recovery preserves the explicit payment review."""
from data_entry import add_manual_jobcard, in_move_entery
from modes import OutworkerPayroll
from payroll_service import record_advance, save_rate, payroll_preview, advance_balance
from support import AppTestCase


class AdvanceSelectionTest(AppTestCase):
    def setUp(self):
        super().setUp()
        save_rate(self.product.id, '', '5.50', 'new', 'selection-rate', self.admin)
        self.advance_id = record_advance(self.worker.id, '100', 'Cash', 'A1', '', 'selection-advance', self.admin).id
        result = add_manual_jobcard(self.manual_payload(pieces=10, count=1), self.admin, 'selection-job')
        self.card_id = result['jobData']['jobId']
        in_move_entery(self.return_payload(self.card_id, 5), self.admin, 'selection-return')

    def preview(self, mode):
        return self.client.post('/payroll', data={
            'action': 'preview', 'worker_id': self.worker.id, 'job_ids': str(self.card_id),
            'advance_selection': '1',
            'advance_ids': [str(self.advance_id)] if mode == 'available' else ([] if mode == 'none' else ['invalid']),
            'submission_token': 'selection-preview',
        })

    def test_checkbox_replaces_dropdown_and_requested_page_flow(self):
        html = self.client.get(f'/payroll?worker_id={self.worker.id}').get_data(as_text=True)
        self.assertIn('name="advance_selection"', html)
        selection_form = html.split('id="payrollSelectionForm"', 1)[1].split('</form>', 1)[0]
        self.assertNotIn('name="deduction"', selection_form)
        self.assertIn('type="checkbox" name="advance_ids"', html)
        self.assertNotIn('<select id="advanceDeductionMode"', html)
        self.assertIn('<strong>₹100.00</strong>', html)
        anchors = ['id="payrollWorkerForm"', 'id="payroll-jobs"',
                   'id="advance-entry"', 'id="payroll-account-totals"', 'id="payment-ledger"']
        positions = [html.index(anchor) for anchor in anchors]
        self.assertEqual(positions, sorted(positions))

    def test_selected_available_caps_to_gross_and_requires_confirmation(self):
        html = self.preview('available').get_data(as_text=True)
        self.assertIn('name="deduction" value="27.50"', html)
        self.assertIn(f'name="advance_ids" value="{self.advance_id}" checked', html)
        self.assertIn('₹72.50', html)
        self.assertEqual(OutworkerPayroll.query.count(), 0)
        self.assertEqual(advance_balance(self.worker.id), 10000)
        quote = payroll_preview(self.worker.id, [self.card_id], 'available')
        response = self.client.post('/payroll', data={
            'action': 'pay', 'worker_id': self.worker.id, 'job_ids': str(self.card_id),
            'deduction': '27.50', 'version': quote['version'], 'method': 'Cash',
            'submission_token': 'selection-payment',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(OutworkerPayroll.query.one().net_paise, 0)
        self.assertEqual(advance_balance(self.worker.id), 7250)

    def test_carry_forward_and_invalid_choice(self):
        html = self.preview('none').get_data(as_text=True)
        self.assertIn('name="deduction" value="0.00"', html)
        self.assertIn('₹100.00', html)
        invalid = self.preview('anything').get_data(as_text=True)
        self.assertIn('Select available advances', invalid)
        self.assertNotIn('id="payroll-preview"', invalid)
        self.assertEqual(advance_balance(self.worker.id), 10000)

    def test_available_below_gross_and_zero_balance(self):
        in_move_entery(self.return_payload(self.card_id, 5), self.admin, 'selection-return-rest')
        # 10 x 5.50 = 55.00, still below the original advance.
        self.assertEqual(payroll_preview(self.worker.id, [self.card_id], 'available')['deduction_paise'], 5500)
        from payroll_service import issue_payroll
        quote = payroll_preview(self.worker.id, [self.card_id], 'available')
        issue_payroll(self.worker.id, [self.card_id], '55.00', quote['version'], 'Cash', '', '', 'first', self.admin)
        second = add_manual_jobcard(self.manual_payload(pieces=20, count=1), self.admin, 'second-job')
        second_id = second['jobData']['jobId']
        in_move_entery(self.return_payload(second_id, 20), self.admin, 'second-return')
        quote = payroll_preview(self.worker.id, [second_id], 'available')
        self.assertEqual((quote['gross_paise'], quote['deduction_paise'], quote['net_paise']), (11000, 4500, 6500))
        issue_payroll(self.worker.id, [second_id], '45.00', quote['version'], 'Cash', '', '', 'second', self.admin)
        html = self.client.get(f'/payroll?worker_id={self.worker.id}').get_data(as_text=True)
        self.assertIn('No advance available', html)
        self.assertEqual(advance_balance(self.worker.id), 0)
