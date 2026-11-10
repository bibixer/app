import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from modes import db, User, Outworker, OutworkerAdvanceReceipt, OutworkerPayroll
from payroll_service import (record_advance, receive_selected_advances, receive_advance,
    advance_entries, advance_balance, browser_payroll_snapshot)
from support import AppTestCase


class SelectedAdvanceReceiptsTest(AppTestCase):
    def setUp(self):
        super().setUp()
        self.a = record_advance(self.worker.id, '100', 'Cash', '', '', 'a', self.admin).id
        self.b = record_advance(self.worker.id, '200', 'Cash', '', '', 'b', self.admin).id
        self.snapshot = browser_payroll_snapshot(self.worker, [], advance_entries(self.worker.id), 30000)

    def receive(self, ids, total='300', token='batch'):
        return receive_selected_advances(self.worker.id, ids, self.snapshot, total,
            'Cash', 'REC-1', 'Money received', token, self.admin)

    def test_selected_one_leaves_other_available(self):
        self.receive([self.b], '200')
        self.assertEqual([row['remaining_paise'] for row in advance_entries(self.worker.id)], [10000, 0])
        self.assertEqual(OutworkerAdvanceReceipt.query.one().advance_id, self.b)
        self.assertEqual(OutworkerPayroll.query.count(), 0)

    def test_all_with_duplicate_ids_is_one_receipt_per_advance(self):
        self.receive([self.a, self.a, self.b])
        self.assertEqual(OutworkerAdvanceReceipt.query.count(), 2)
        self.assertEqual(advance_balance(self.worker.id), 0)
        with self.assertRaises(ValueError):
            self.receive([self.a, self.b])
        self.assertEqual(OutworkerAdvanceReceipt.query.count(), 2)

    def test_selected_partly_recovered_advance_receives_only_remaining(self):
        receive_advance(self.worker.id, self.a, '25', 10000, 'Cash', '', '', 'partial', self.admin)
        self.snapshot = browser_payroll_snapshot(self.worker, [], advance_entries(self.worker.id), 27500)
        self.receive([self.a, self.b], '275')
        self.assertEqual(sum(row.amount_paise for row in OutworkerAdvanceReceipt.query.all()), 30000)
        self.assertEqual(advance_balance(self.worker.id), 0)

    def test_failed_commit_rolls_back_all_receipts_and_claim(self):
        with patch.object(db.session, 'commit', side_effect=RuntimeError('disk failure')):
            with self.assertRaises(RuntimeError):
                self.receive([self.a, self.b])
        self.assertEqual(OutworkerAdvanceReceipt.query.count(), 0)
        self.assertEqual(advance_balance(self.worker.id), 30000)
        self.receive([self.a, self.b])
        self.assertEqual(OutworkerAdvanceReceipt.query.count(), 2)

    def test_foreign_or_invalid_advances_cannot_partially_save_batch(self):
        worker = Outworker(name='OTHER', adders='CITY', number=555, enter_user='admin')
        db.session.add(worker)
        db.session.commit()
        foreign = record_advance(worker.id, '100', 'Cash', '', '', 'foreign', self.admin).id
        for ids in ([], [self.a, foreign], [self.a, 'bad'], [99999999]):
            with self.assertRaises(ValueError):
                self.receive(ids)
        self.assertEqual(OutworkerAdvanceReceipt.query.count(), 0)

    def test_concurrent_batch_receipts_cannot_double_recover(self):
        worker_id, user_id, ids, snapshot = self.worker.id, self.admin.id, [self.a, self.b], self.snapshot
        barrier = threading.Barrier(2)
        def submit(index):
            with self.app.app_context():
                user = db.session.get(User, user_id)
                advance_entries(worker_id)
                barrier.wait(timeout=5)
                try:
                    receive_selected_advances(worker_id, ids, snapshot, '300', 'Cash', '', '', f'batch-{index}', user)
                    return True
                except ValueError:
                    return False
                finally:
                    db.session.remove()
        db.session.remove()
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(submit, range(2)))
        self.assertEqual(sum(results), 1)
        self.assertEqual(OutworkerAdvanceReceipt.query.count(), 2)
        self.assertEqual(advance_balance(worker_id), 0)
