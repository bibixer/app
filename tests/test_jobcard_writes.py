"""Issue/return correctness, malformed submissions and transactional failures."""

from copy import deepcopy
from unittest.mock import patch

from data_entry import (add_jobcard, add_manual_jobcard, validate_payload_structure,
                        validate_manual_jobcard, in_move_entery)
from data_Process import get_jobcard_return_data, get_jobcard_ledger
from modes import db, Jobcard, Jobmovement, Bundle, ItemAlias, RequestDedup, ReturnBreakdown
from support import AppTestCase


class JobcardWriteTest(AppTestCase):
    def test_scanning_saves_one_card_and_marks_bundles_given(self):
        bundle = self.bundle()
        data = self.scan_payload(bundle)
        result = add_jobcard(data, self.admin, data["request_id"])
        self.assertEqual(result["code"], 101)
        self.assertEqual(Jobcard.query.count(), 1)
        self.assertEqual(Jobmovement.query.one().outflow, 36)
        self.assertEqual(db.session.get(Bundle, bundle.id).status, "GIVEN")
        self.assertEqual(add_jobcard(data, self.admin, data["request_id"]), 409)
        self.assertEqual(add_jobcard(data, self.admin, "different-request"), 403)
        self.assertEqual(Jobmovement.query.count(), 1)
        self.job_cade_print.assert_called_once()

    def test_same_bundle_with_leading_zero_id_cannot_be_issued_twice(self):
        data = self.scan_payload(self.bundle())
        data["items"].append({**data["items"][0], "item_id": "01"})
        result = add_jobcard(data, self.admin, "duplicate-bundle")
        self.assertIn(result, (403, 405))
        self.assertEqual(Jobcard.query.count(), 0)
        self.assertEqual(Bundle.query.one().status, "READY")

    def test_scan_rejects_fractions_booleans_nonfinite_weight_and_bad_ids(self):
        data = self.scan_payload(self.bundle(pieces=1))
        invalid = [("qty", 1.9), ("qty", True), ("qty", float("nan")),
                   ("kg", float("nan")), ("kg", float("inf")), ("kg", True),
                   ("item_id", "²"), ("item_id", "0"), ("item_id", "9" * 100)]
        for field, value in invalid:
            payload = deepcopy(data)
            payload["items"][0][field] = value
            with self.subTest(field=field, value=value):
                self.assertFalse(validate_payload_structure(payload))
                self.assertEqual(add_jobcard(payload, self.admin, "bad-scan"), 405)
        self.assertEqual(Jobcard.query.count(), 0)

    def test_manual_aliases_save_canonical_names_and_exact_patterns(self):
        data = self.manual_payload()
        before = deepcopy(data)
        result = add_manual_jobcard(data, self.admin, data["request_id"])
        self.assertEqual(result["code"], 101)
        self.assertEqual(data, before)
        card = Jobcard.query.one()
        self.assertEqual(card.given_to, self.worker_name)
        self.assertEqual(card.product_list[0]["name_of_prduct"], self.product.name)
        self.assertEqual(card.product_list[0]["qty"], 120)
        self.assertEqual(Jobmovement.query.one().product_name, self.product.name)
        self.assertEqual(Bundle.query.count(), 0)
        self.assertEqual(ItemAlias.query.count(), 1)
        self.assertEqual(add_manual_jobcard(data, self.admin, data["request_id"]), 409)

    def test_manual_unknown_product_or_master_cannot_create_data(self):
        for customer, product, expected in [("RAM CITY", "20", 406), ("unknown", "VIM", 401)]:
            data = self.manual_payload(product=product)
            data["customer"] = customer
            self.assertEqual(add_manual_jobcard(data, self.admin, "invalid"), expected)
        self.assertEqual(Jobcard.query.count(), 0)
        self.assertEqual(RequestDedup.query.count(), 0)

    def test_manual_rejects_values_that_cannot_fit_database_quantities(self):
        for pieces, count in [(True, 1), (1, True), (1, 501), (2**63, 1), (2**62, 4)]:
            with self.subTest(pieces=pieces, count=count):
                self.assertFalse(validate_manual_jobcard(self.manual_payload(pieces=pieces, count=count)))

    def test_return_preserves_real_product_underscores_and_does_not_mutate_payload(self):
        self.product.name = "VIMAL_X"
        db.session.commit()
        card_id = add_manual_jobcard(self.manual_payload(), self.admin, "manual")["jobData"]["jobId"]
        data = self.return_payload(card_id, 30)
        before = deepcopy(data)
        self.assertEqual(in_move_entery(data, self.admin, "return")["code"], 101)
        self.assertEqual(data, before)
        movement = Jobmovement.query.filter_by(flow_type="IN").one()
        self.assertEqual(movement.product_name, "VIMAL_X")
        self.assertEqual(get_jobcard_return_data(card_id)["items"][0]["issued"], 90)
        self.assertEqual(get_jobcard_ledger(card_id)["job"]["products"][0]["name"], "VIMAL_X")

    def test_return_rejects_coerced_row_ids_and_duplicate_lines(self):
        card_id = add_manual_jobcard(self.manual_payload(), self.admin, "manual")["jobData"]["jobId"]
        data = self.return_payload(card_id, 10)
        for value in (True, 1.9, None, [], "²"):
            payload = deepcopy(data)
            payload["items"][0]["item_id"] = value
            with self.subTest(value=value):
                self.assertEqual(in_move_entery(payload, self.admin, "invalid-return"), 405)
        data["items"].append(deepcopy(data["items"][0]))
        self.assertEqual(in_move_entery(data, self.admin, "duplicate-line"), 405)
        self.assertEqual(ReturnBreakdown.query.count(), 0)

    def test_write_failure_rolls_back_the_claim_card_and_inventory(self):
        bundle = self.bundle()
        data = self.scan_payload(bundle)
        with patch("data_entry.add_job_movemet_out", side_effect=RuntimeError("simulated failure")):
            with self.assertRaises(RuntimeError):
                add_jobcard(data, self.admin, "retryable")
        # A rolled back failure must permit retrying the same request key.
        self.assertEqual(Jobcard.query.count(), 0)
        self.assertEqual(RequestDedup.query.count(), 0)
        self.assertEqual(add_jobcard(data, self.admin, "retryable")["code"], 101)

    def test_print_failure_does_not_undo_a_saved_job_or_allow_duplicates(self):
        self.job_cade_print.side_effect = OSError("printer offline")
        with self.assertLogs(level="ERROR"):
            result = add_manual_jobcard(self.manual_payload(), self.admin, "print-failure")
        self.assertEqual(result["code"], 101)
        self.assertEqual(Jobcard.query.count(), 1)
        self.assertEqual(add_manual_jobcard(self.manual_payload(), self.admin, "print-failure"), 409)

    def test_return_failure_rolls_back_every_row_and_allows_retry(self):
        card_id = add_manual_jobcard(self.manual_payload(), self.admin, "manual")["jobData"]["jobId"]
        data = self.return_payload(card_id, 30)
        with patch("data_entry.ReturnBreakdown", side_effect=RuntimeError("simulated failure")):
            with self.assertLogs(level="ERROR"):
                self.assertEqual(in_move_entery(data, self.admin, "retryable-return"), 500)
        self.assertEqual(Jobmovement.query.filter_by(flow_type="IN").count(), 0)
        self.assertEqual(in_move_entery(data, self.admin, "retryable-return")["code"], 101)
