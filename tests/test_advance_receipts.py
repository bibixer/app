import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from data_entry import add_manual_jobcard, in_move_entery
from modes import db, User, Outworker, OutworkerAdvanceReceipt, OutworkerPayroll
from payroll_service import (record_advance, receive_advance, advance_balance, advance_entries,
                             payment_account, save_rate, payroll_preview, issue_payroll)
from support import AppTestCase


class AdvanceReceiptTest(AppTestCase):
    def setUp(self):
        super().setUp()
        self.advance = record_advance(self.worker.id, '300', 'Cash', '', '', 'advance', self.admin).id

    def receive(self, amount='100', remaining=30000, token='receive'):
        return receive_advance(self.worker.id, self.advance, amount, remaining, 'Cash', 'REC-1',
                               'Money returned', token, self.admin)

    def card(self):
        save_rate(self.product.id, '', '20', 'new', 'rate', self.admin)
        result = add_manual_jobcard(self.manual_payload(pieces=10, count=1), self.admin, 'job')
        card = result['jobData']['jobId']
        in_move_entery(self.return_payload(card, 10), self.admin, 'returned')
        return card

    def test_partial_receipt_then_payroll_only_recovers_rest(self):
        receipt = self.receive()
        self.assertEqual((receipt.amount_paise, receipt.recorded_by, receipt.reference), (10000, 'admin', 'REC-1'))
        self.assertEqual(advance_balance(self.worker.id), 20000)
        self.assertEqual(advance_entries(self.worker.id)[0]['remaining_paise'], 20000)
        card = self.card()
        quote = payroll_preview(self.worker.id, [card], '0', advance_ids=[self.advance])
        self.assertEqual(quote['deduction_paise'], 20000)
        issue_payroll(self.worker.id, [card], '200', quote['version'], 'Cash', '', '', 'pay', self.admin,
                      advance_ids=[self.advance])
        self.assertEqual(advance_balance(self.worker.id), 0)
        with self.assertRaises(ValueError):
            self.receive('1', 0, 'again')

    def test_full_direct_receipt_needs_no_job_and_ledger_distinguishes_money_in(self):
        self.receive('300')
        account = payment_account(self.worker.id)
        self.assertEqual((account['advance_paise'], account['direct_recovery_paise'],
                          account['net_paise'], account['deduction_paise']), (0, 30000, 0, 0))
        event = account['events'][-1]
        self.assertEqual((event['kind'], event['advance_id'], event['balance_paise']), ('Recovery', self.advance, 0))
        html = self.client.get(f'/payroll?worker_id={self.worker.id}').get_data(as_text=True)
        self.assertIn('Received back · Advance #', html)
        self.assertIn('Received ₹300.00', html)
        self.assertEqual(OutworkerPayroll.query.count(), 0)

    def test_validation_stale_balance_and_duplicate_request(self):
        for amount in ('0', '-1', '301', 'NaN', '1.001'):
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                self.receive(amount)
        self.receive()
        for remaining, token in ((30000, 'other-tab'), (20000, 'receive')):
            with self.assertRaises(ValueError):
                self.receive('100', remaining, token)
        self.assertEqual(OutworkerAdvanceReceipt.query.count(), 1)
        self.assertEqual(advance_balance(self.worker.id), 20000)

    def test_historical_payroll_and_selected_direct_repayment_keep_balances(self):
        second = record_advance(self.worker.id, '200', 'Cash', '', '', 'second-advance', self.admin).id
        db.session.add(OutworkerPayroll(worker_id=self.worker.id, worker_name=self.worker_name,
            gross_paise=35000, deduction_paise=35000, net_paise=0, paid_at=datetime.now(),
            method='Cash', reference='', note='', recorded_by='admin'))
        db.session.commit()
        self.assertEqual([row['remaining_paise'] for row in advance_entries(self.worker.id)], [0, 15000])
        receive_advance(self.worker.id, second, '100', 15000, 'Cash', '', '', 'legacy-direct', self.admin)
        self.assertEqual([row['remaining_paise'] for row in advance_entries(self.worker.id)], [0, 5000])
        self.assertEqual(advance_balance(self.worker.id), 5000)

    def test_other_worker_advance_and_payroll_stale_quote_rejected(self):
        other = Outworker(name='OTHER', adders='CITY', number=1234, enter_user='admin')
        db.session.add(other)
        db.session.commit()
        with self.assertRaises(ValueError):
            receive_advance(other.id, self.advance, '1', 30000, 'Cash', '', '', 'foreign', self.admin)
        card = self.card()
        quote = payroll_preview(self.worker.id, [card], '0', advance_ids=[self.advance])
        self.receive()
        with self.assertRaises(ValueError):
            issue_payroll(self.worker.id, [card], '200', quote['version'], 'Cash', '', '', 'stale-pay',
                          self.admin, advance_ids=[self.advance])
        self.assertEqual(OutworkerPayroll.query.count(), 0)

    def test_http_permissions_and_stale_form(self):
        payload = {'action':'recover_advance', 'worker_id':self.worker.id,
                   'advance_choice':f'{self.advance}:30000', 'amount':'100', 'method':'UPI',
                   'reference':'UPI-1', 'submission_token':'http-receive'}
        self.login_as(self.operator)
        self.assertEqual(self.client.post('/payroll', data=payload).status_code, 302)
        self.assertEqual(OutworkerAdvanceReceipt.query.count(), 0)
        self.login_as(self.admin)
        self.assertEqual(self.client.post('/payroll', data=payload).status_code, 302)
        payload['submission_token'] = 'http-stale'
        html = self.client.post('/payroll', data=payload).get_data(as_text=True)
        self.assertIn('balance changed', html)
        self.assertEqual(OutworkerAdvanceReceipt.query.count(), 1)

    def test_failed_commit_rolls_back_receipt_and_retry_claim(self):
        with patch.object(db.session, 'commit', side_effect=RuntimeError('disk failure')):
            with self.assertRaises(RuntimeError):
                self.receive()
        self.assertEqual(OutworkerAdvanceReceipt.query.count(), 0)
        self.assertEqual(advance_balance(self.worker.id), 30000)
        self.receive()
        self.assertEqual(advance_balance(self.worker.id), 20000)

    def test_concurrent_partial_receipts_cannot_save_same_snapshot_twice(self):
        worker_id, user_id, advance_id = self.worker.id, self.admin.id, self.advance
        barrier = threading.Barrier(2)
        def submit(index):
            with self.app.app_context():
                user = db.session.get(User, user_id)
                advance_entries(worker_id)
                barrier.wait(timeout=5)
                try:
                    return receive_advance(worker_id, advance_id, '100', 30000, 'Cash', '', '',
                                           f'concurrent-{index}', user).id
                except ValueError:
                    return None
                finally:
                    db.session.remove()
        db.session.remove()
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(submit, range(2)))
        self.assertEqual(sum(value is not None for value in results), 1)
        self.assertEqual(advance_balance(worker_id), 20000)

    def test_payroll_and_receipt_race_cannot_recover_twice(self):
        card = self.card()
        worker_id, user_id, advance_id = self.worker.id, self.admin.id, self.advance
        version = payroll_preview(worker_id, [card], '0', advance_ids=[advance_id])['version']
        barrier = threading.Barrier(2)
        def submit(index):
            with self.app.app_context():
                user = db.session.get(User, user_id)
                barrier.wait(timeout=5)
                try:
                    if index:
                        receive_advance(worker_id, advance_id, '100', 30000, 'Cash', '', '', 'race-receipt', user)
                    else:
                        issue_payroll(worker_id, [card], '200', version, 'Cash', '', '', 'race-pay', user,
                                      advance_ids=[advance_id])
                    return True
                except ValueError:
                    return False
                finally:
                    db.session.remove()
        db.session.remove()
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(submit, range(2)))
        self.assertEqual(sum(results), 1)
        self.assertIn(advance_balance(worker_id), (10000, 20000))
