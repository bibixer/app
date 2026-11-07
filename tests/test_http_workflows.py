"""Authentication, API responses, browser form guards and inventory drafts."""

from unittest.mock import patch

from data_entry import add_manual_jobcard
from modes import db, Jobcard, Jobmovement, Bundle, Item_data, RequestDedup
from support import AppTestCase


class HttpWorkflowTest(AppTestCase):
    endpoints = ("/submit-jobcard", "/submit-manual-jobcard", "/summit-retune")

    def test_write_apis_reject_missing_invalid_or_non_json_submissions(self):
        for path in self.endpoints:
            for data in (None, [], {}, {"request_id": ""}, {"request_id": True}, {"request_id": "x" * 129}):
                with self.subTest(path=path, data=data):
                    response = self.client.post(path, json=data)
                    self.assertEqual(response.status_code, 400)
                    self.assertFalse(response.json["success"])
                    self.assertFalse(response.json.get("duplicate", False))
            response = self.client.post(path, data="{broken", content_type="application/json")
            self.assertEqual(response.status_code, 400)
        self.assertEqual(RequestDedup.query.count(), 0)

    def test_write_apis_return_json_for_login_and_admin_failures(self):
        self.login_as(self.operator)
        for path in self.endpoints:
            response = self.client.post(path, json={"request_id": "unauthorized"})
            self.assertEqual(response.status_code, 403)
            self.assertFalse(response.json["success"])
        with self.client.session_transaction() as session:
            session.clear()
        for path in self.endpoints:
            response = self.client.post(path, json={"request_id": "anonymous"})
            self.assertEqual(response.status_code, 401)
            self.assertEqual(response.json["code"], 401)
        self.assertEqual(Jobcard.query.count(), 0)

    def test_manual_save_return_and_duplicate_retries_end_to_end(self):
        payload = self.manual_payload()
        response = self.client.post("/submit-manual-jobcard", json=payload)
        self.assertEqual(response.status_code, 200)
        card_id = response.json["jobData"]["jobId"]
        self.assertTrue(self.client.post("/submit-manual-jobcard", json=payload).json["duplicate"])
        data = self.return_payload(card_id, 120)
        response = self.client.post("/summit-retune", json=data)
        self.assertTrue(response.json["success"])
        self.assertTrue(self.client.post("/summit-retune", json=data).json["duplicate"])
        self.assertEqual(Jobmovement.query.filter_by(flow_type="IN").count(), 1)
        self.assertEqual(self.client.get(f"/job_retun?jobcard_id={card_id}").status_code, 200)

    def test_scan_api_reports_changed_bundle_as_conflict(self):
        data = self.scan_payload(self.bundle())
        self.assertTrue(self.client.post("/submit-jobcard", json=data).json["success"])
        data["request_id"] = "other-tab"
        response = self.client.post("/submit-jobcard", json=data)
        self.assertEqual(response.status_code, 409)
        self.assertFalse(response.json["success"])

    def test_unexpected_database_failure_is_json_and_can_be_retried(self):
        self.app.config["PROPAGATE_EXCEPTIONS"] = False
        data = self.scan_payload(self.bundle())
        with patch("data_entry.add_job_movemet_out", side_effect=RuntimeError("simulated fault")):
            with self.assertLogs(self.app.logger, level="ERROR"):
                response = self.client.post("/submit-jobcard", json=data)
        self.assertEqual(response.status_code, 500)
        self.assertFalse(response.json["success"])
        self.assertEqual(Jobcard.query.count(), 0)
        self.assertEqual(Bundle.query.one().status, "READY")
        self.assertTrue(self.client.post("/submit-jobcard", json=data).json["success"])

    def test_login_valid_invalid_empty_and_logout(self):
        with self.client.session_transaction() as session:
            session.clear()
        for values in ({}, {"user_name": "admin", "password": "wrong"}):
            self.assertEqual(self.client.post("/login", data=values).status_code, 200)
            with self.client.session_transaction() as session:
                self.assertNotIn("_user_id", session)
        self.assertEqual(self.client.post("/login", data={"user_name": " ADMIN ", "password": "test-password"}).status_code, 302)
        self.assertEqual(self.client.get("/logout").status_code, 302)
        with self.client.session_transaction() as session:
            self.assertNotIn("_user_id", session)

    def test_missing_form_submission_token_is_not_silently_regenerated(self):
        response = self.client.post("/add_items", data={"name": "SHOULD NOT SAVE", "size": 1, "meter": 1})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Item_data.query.count(), 1)

    def test_failed_inventory_save_preserves_draft_and_does_not_claim_success(self):
        from test_inventory_and_printing import InventoryAndPrintingTest
        data = InventoryAndPrintingTest.payload(self)
        with self.client.session_transaction() as session:
            session.update(bale_data=data["bale_data"], bundle_data=data["main"], bundles=data["bundles"],
                           current_bundle=3, current_lump=2, sno=2, lump_workflow_id="draft")
        with patch("route.bale_data_entry", return_value=405):
            response = self.client.get("/bundle_entery")
        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as session:
            self.assertEqual(session["bundles"], data["bundles"])
            self.assertEqual(session["current_lump"], 1)
            self.assertIn("not saved", session["_flashes"][-1][1])
            self.assertTrue(session["inventory_save_failed"])

    def test_extreme_record_ids_return_validation_errors_not_server_errors(self):
        huge = "9" * 80
        for path in (f"/jobcard/ledger?jobcard_id={huge}", f"/jobcard/{huge}/ledger",
                     f"/job_retun?jobcard_id={huge}", f"/edit/product/{huge}",
                     f"/edit/jobcard/{huge}", f"/payroll?worker_id={huge}",
                     f"/payroll/rates?product_id={huge}", f"/payroll/{huge}"):
            with self.subTest(path=path):
                self.assertLess(self.client.get(path).status_code, 500)
