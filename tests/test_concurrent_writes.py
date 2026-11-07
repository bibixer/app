"""Real simultaneous SQLite transactions, rather than sequential duplicate calls."""

from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import threading

from data_entry import add_jobcard, add_manual_jobcard, in_move_entery, bale_data_entry
from jobcard_edit import jobcard_edit_context
from modes import db, User, Bundle, Jobcard, Jobmovement, Lump, EditLog
from support import AppTestCase


class ConcurrentWritesTest(AppTestCase):
    def parallel(self, operation, preload=None):
        user_id = self.admin.id
        barrier = threading.Barrier(2)
        db.session.remove()
        def run(index):
            with self.app.app_context():
                user = db.session.get(User, user_id)
                held_reference = preload() if preload else None
                barrier.wait(timeout=5)
                try:
                    return operation(index, user)
                finally:
                    db.session.remove()
        with ThreadPoolExecutor(max_workers=2) as executor:
            return list(executor.map(run, range(2)))

    def test_two_requests_cannot_issue_the_same_preloaded_bundle(self):
        bundle = self.bundle()
        bundle_id = bundle.id
        payload = self.scan_payload(bundle)
        results = self.parallel(lambda index, user: add_jobcard(deepcopy(payload), user, f"scan-{index}"),
                                preload=lambda: db.session.get(Bundle, bundle_id))
        self.assertEqual(sum(isinstance(result, dict) for result in results), 1)
        self.assertIn(403, results)
        self.assertEqual(Jobcard.query.count(), 1)
        self.assertEqual(Jobmovement.query.count(), 1)

    def test_same_manual_submission_creates_exactly_one_job(self):
        payload = self.manual_payload()
        results = self.parallel(lambda index, user: add_manual_jobcard(deepcopy(payload), user, "same-manual"))
        self.assertEqual(sum(isinstance(result, dict) for result in results), 1)
        self.assertIn(409, results)
        self.assertEqual(Jobcard.query.count(), 1)

    def test_simultaneous_returns_cannot_consume_the_same_remaining_pieces(self):
        card_id = add_manual_jobcard(self.manual_payload(), self.admin, "manual")["jobData"]["jobId"]
        payload = self.return_payload(card_id, 80)
        results = self.parallel(lambda index, user: in_move_entery(deepcopy(payload), user, f"return-{index}"))
        self.assertEqual(sum(isinstance(result, dict) for result in results), 1)
        self.assertIn(4033, results)
        self.assertEqual(Jobmovement.query.filter_by(flow_type="IN").one().inflow, 80)

    def test_same_inventory_submission_creates_one_lump(self):
        from test_inventory_and_printing import InventoryAndPrintingTest
        payload = InventoryAndPrintingTest.payload(self)
        results = self.parallel(lambda index, user: bale_data_entry(deepcopy(payload), user, "inventory"))
        self.assertEqual(sorted(results), [101, 409])
        self.assertEqual(Lump.query.count(), 1)
        self.assertEqual(Bundle.query.count(), 2)

    def test_competing_job_corrections_do_not_overwrite_each_other(self):
        card_id = add_manual_jobcard(self.manual_payload(), self.admin, "manual")["jobData"]["jobId"]
        context = jobcard_edit_context(card_id)
        given_id = context["given"][0]["id"]
        results = self.parallel(lambda index, user: self.job_edit(
            card_id, {f"line_{given_id}_pieces": 31 + index}, token=f"edit-{index}", version=context["version"]))
        self.assertEqual(sorted(result[0] for result in results), ["conflict", "saved"])
        self.assertEqual(EditLog.query.filter_by(entity_type="jobcard").count(), 1)
