"""Pay returned pieces on an open job, then pay only its later unpaid returns."""

import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from data_Process import get_jobcard_ledger
from data_entry import add_manual_jobcard, in_move_entery
from modes import db, User, Jobcard, OutworkerPayroll, OutworkerPayrollJob, OutworkerRate, RequestDedup
from payroll_service import (save_rate, rate_version, payroll_preview, issue_payroll,
                             payable_job_quotes, record_advance, advance_balance)
from support import AppTestCase


class PartialPayrollTest(AppTestCase):
    def setUp(self):
        super().setUp()
        self.app.config['SIMPLE_WORKFLOW'] = True
        save_rate(self.product.id, '', '5.5', 'new', 'base-rate', self.admin)

    def card(self, returned=5, pieces=10, key='job'):
        result = add_manual_jobcard(self.manual_payload(pieces=pieces, count=1), self.admin, key)
        card_id = result['jobData']['jobId']
        if returned:
            self.add_return(card_id, returned, f'{key}-return')
        return card_id

    def add_return(self, card_id, quantity, key):
        result = in_move_entery(self.return_payload(card_id, quantity, key=key), self.admin, key)
        self.assertEqual(result['code'], 101)

    def pay(self, ids, token, deduction='0', version=None):
        preview = payroll_preview(self.worker.id, ids, deduction)
        return issue_payroll(self.worker.id, ids, deduction, version or preview['version'],
                             'Cash', '', '', token, self.admin)

    def test_installments_round_to_same_total_as_one_payment(self):
        rate = OutworkerRate.query.one()
        save_rate(self.product.id, '', '5.5555', rate_version(rate), 'fractional-rate', self.admin)
        whole = self.card(returned=3, pieces=3, key='whole')
        split = self.card(returned=0, pieces=3, key='split')
        whole_total = self.pay([whole], 'whole-payment').gross_paise
        installments = []
        for index in range(3):
            self.add_return(split, 1, f'split-return-{index}')
            installments.append(self.pay([split], f'split-payment-{index}').gross_paise)
        self.assertEqual(installments, [556, 555, 556])
        self.assertEqual(sum(installments), whole_total)

    def test_job_below_one_paisa_is_not_marked_paid_at_zero(self):
        save_rate(self.product.id, 'lump', '0.0001', 'new', 'tiny-rate', self.admin)
        card = self.card(returned=1, pieces=1)
        with self.assertRaisesRegex(ValueError, 'less than one payable paisa'):
            self.pay([card], 'zero-paisa-payment')
        self.assertEqual(OutworkerPayrollJob.query.count(), 0)

    def test_ten_piece_job_paid_in_two_batches_of_five(self):
        card_id = self.card()
        quote = payable_job_quotes(self.worker)[0]
        self.assertEqual((quote['given'], quote['returned'], quote['already_paid'],
                          quote['pieces'], quote['pending_return']), (10, 5, 0, 5, 5))
        first = self.pay([card_id], 'first-payment')
        self.assertEqual(first.gross_paise, 2750)
        job = get_jobcard_ledger(card_id)['job']
        self.assertEqual((job['status'], job['remaining'], job['paid_pieces'],
                          job['payable_pieces'], job['unpaid_pieces']), ('Open', 5, 5, 0, 5))
        self.assertEqual(payable_job_quotes(self.worker), [])
        with self.assertRaises(ValueError):
            self.pay([card_id], 'cannot-repay-first-five')
        self.add_return(card_id, 5, 'second-return')
        quote = payable_job_quotes(self.worker)[0]
        self.assertEqual((quote['returned'], quote['already_paid'], quote['pieces']), (10, 5, 5))
        self.assertIn(f'job_id={card_id}', self.client.get(f'/payroll/job/{card_id}').location)
        second = self.pay([card_id], 'second-payment')
        self.assertNotEqual(first.id, second.id)
        self.assertEqual(second.gross_paise, 2750)
        payments = OutworkerPayrollJob.query.filter_by(jobcard_id=card_id).order_by(OutworkerPayrollJob.id).all()
        self.assertEqual([payment.pieces for payment in payments], [5, 5])
        self.assertEqual(sum(payment.amount_paise for payment in payments), 5500)
        job = get_jobcard_ledger(card_id)['job']
        self.assertEqual((job['status'], job['paid_pieces'], job['unpaid_pieces']), ('Complete', 10, 0))
        self.assertEqual(len(job['payrolls']), 2)
        html = self.client.get(f'/jobcard/{card_id}/ledger').get_data(as_text=True)
        self.assertIn(f'View payroll #{first.id}', html)
        self.assertIn(f'View payroll #{second.id}', html)
        self.assertEqual(payable_job_quotes(self.worker), [])

    def test_user_selects_job_and_partial_payment_does_not_auto_pay_other_jobs(self):
        selected = self.card(key='selected')
        other = self.card(key='other')
        unreturned = self.card(returned=0, key='not-returned')
        html = self.client.get(f'/payroll?worker_id={self.worker.id}').get_data(as_text=True)
        self.assertIn('Jobs with returned or kept pieces to pay', html)
        self.assertIn('Awaiting return: 5', html)
        self.assertNotIn('each job can be paid once', html)
        self.assertNotIn(f'aria-label="Pay job {unreturned}"', html)
        self.assertEqual(OutworkerPayroll.query.count(), 0)
        preview = payroll_preview(self.worker.id, [selected], '0')
        response = self.client.post('/payroll', data={
            'action': 'pay', 'worker_id': self.worker.id, 'job_ids': str(selected),
            'deduction': '0', 'version': preview['version'], 'method': 'Cash',
            'submission_token': 'selected-payment',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(OutworkerPayrollJob.query.one().jobcard_id, selected)
        self.assertEqual([quote['id'] for quote in payable_job_quotes(self.worker)], [other])
        self.assertEqual(get_jobcard_ledger(selected)['job']['remaining'], 5)

    def test_multiple_types_only_returned_unpaid_quantities_use_their_rates(self):
        save_rate(self.product.id, 'good_cut', '5.7', 'new', 'type-rate', self.admin)
        payload = self.manual_payload(pieces=10, count=1)
        payload['rows'].append({'product': 'VIM', 'pieces': 8, 'count': 1, 'type': 'good_cut'})
        card_id = add_manual_jobcard(payload, self.admin, 'mixed-job')['jobData']['jobId']
        self.add_return(card_id, 5, 'lump-return')
        self.assertEqual(self.pay([card_id], 'lump-pay').gross_paise, 2750)
        self.assertEqual(payable_job_quotes(self.worker), [])
        # The remaining Lump line has no payable pieces; return Good Cut instead.
        data = self.return_payload(card_id, 3, index=1, key='good-cut-return')
        self.assertEqual(in_move_entery(data, self.admin, 'good-cut-return')['code'], 101)
        quote = payable_job_quotes(self.worker)[0]
        self.assertEqual([(line['type'], line['pieces']) for line in quote['lines']], [('good_cut', 3)])
        self.assertEqual(self.pay([card_id], 'good-cut-pay').gross_paise, 1710)

    def test_each_batch_can_deduct_advance_and_keeps_its_original_rate(self):
        card_id = self.card()
        record_advance(self.worker.id, '30', 'Cash', '', '', 'advance', self.admin)
        first = self.pay([card_id], 'pay-first', deduction='20')
        self.assertEqual(first.net_paise, 750)
        self.assertEqual(advance_balance(self.worker.id), 1000)
        from modes import OutworkerRate
        rate = OutworkerRate.query.one()
        save_rate(self.product.id, '', '6', rate_version(rate), 'new-rate', self.admin)
        self.add_return(card_id, 5, 'rest-return')
        second = self.pay([card_id], 'pay-rest', deduction='10')
        self.assertEqual((second.gross_paise, second.net_paise), (3000, 2000))
        self.assertEqual(advance_balance(self.worker.id), 0)
        saved = OutworkerPayrollJob.query.order_by(OutworkerPayrollJob.id).all()
        self.assertEqual([payment.lines[0]['rate'] for payment in saved], ['5.5', '6'])
        self.assertEqual(db.session.get(OutworkerPayroll, first.id).gross_paise, 2750)

    def test_new_returns_stale_preview_duplicate_tokens_and_rollback(self):
        card_id = self.card()
        preview = payroll_preview(self.worker.id, [card_id], '0')
        self.add_return(card_id, 1, 'extra-return')
        with self.assertRaises(ValueError):
            self.pay([card_id], 'stale-pay', version=preview['version'])
        self.assertEqual(OutworkerPayroll.query.count(), 0)
        with patch('payroll_service.OutworkerPayrollJob', side_effect=RuntimeError('failed allocation')):
            with self.assertRaises(RuntimeError):
                self.pay([card_id], 'retry-pay')
        self.assertEqual(OutworkerPayroll.query.count(), 0)
        self.assertEqual(payable_job_quotes(self.worker)[0]['pieces'], 6)
        self.pay([card_id], 'retry-pay')
        self.add_return(card_id, 4, 'last-return')
        with self.assertRaises(ValueError):
            self.pay([card_id], 'retry-pay')
        self.assertEqual(payable_job_quotes(self.worker)[0]['pieces'], 4)

    def test_product_rename_does_not_pay_the_first_batch_twice(self):
        card_id = self.card()
        self.pay([card_id], 'before-rename')
        self.assertEqual(self.edit('product', self.product.id, {'name': 'RENAMED PRODUCT'})[0], 'saved')
        self.add_return(card_id, 5, 'after-rename-return')
        quote = payable_job_quotes(self.worker)[0]
        self.assertEqual(quote['pieces'], 5)
        self.assertEqual(quote['lines'][0]['product'], 'RENAMED PRODUCT')
        self.pay([card_id], 'after-rename-payment')
        self.assertEqual(sum(row.pieces for row in OutworkerPayrollJob.query.all()), 10)

    def test_concurrent_payrolls_cannot_repay_either_batch(self):
        card_id = self.card()
        worker_id, user_id = self.worker.id, self.admin.id
        for batch in (1, 2):
            if batch == 2:
                self.add_return(card_id, 5, 'remaining-return')
            version = payroll_preview(worker_id, [card_id], '0')['version']
            barrier = threading.Barrier(2)
            def submit(index):
                with self.app.app_context():
                    user = db.session.get(User, user_id)
                    # Exercise reloading already-read rows after the write lock.
                    OutworkerPayrollJob.query.filter_by(jobcard_id=card_id).all()
                    barrier.wait(timeout=5)
                    try:
                        return issue_payroll(worker_id, [card_id], '0', version, 'Cash', '', '',
                                             f'batch-{batch}-tab-{index}', user).id
                    except ValueError:
                        return None
                    finally:
                        db.session.remove()
            db.session.remove()
            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(submit, range(2)))
            self.assertEqual(sum(result is not None for result in results), 1)
        self.assertEqual(OutworkerPayroll.query.count(), 2)
        self.assertEqual(sum(row.pieces for row in OutworkerPayrollJob.query.all()), 10)
