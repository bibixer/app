"""Only admins correct job cards; underlying movements remain system-managed."""

from data_entry import add_manual_jobcard, add_jobcard, in_move_entery
from data_Process import get_jobcard_return_data
from edit_service import edit_context, search_entries, save_entry
from jobcard_edit import jobcard_edit_context
from modes import db, Jobcard, Jobmovement, Bundle, ReturnBreakdown, EditLog
from support import AppTestCase


class JobcardEditTest(AppTestCase):
    def manual_card(self, returned=30):
        card_id = add_manual_jobcard(self.manual_payload(), self.admin, "manual")["jobData"]["jobId"]
        if returned:
            self.assertEqual(in_move_entery(self.return_payload(card_id, returned), self.admin, "return")["code"], 101)
        return card_id

    def test_given_and_return_corrections_update_balances_and_log_original_values(self):
        card_id = self.manual_card()
        context = jobcard_edit_context(card_id)
        given, returned = context["given"][0], context["returns"][0]
        self.assertEqual(self.job_edit(card_id, {f'line_{given["id"]}_pieces': 40,
                                               f'line_{returned["id"]}_quantity': 20})[0], "saved")
        item = get_jobcard_return_data(card_id)["items"][0]
        self.assertEqual(item["given"]["total"], 160)
        self.assertEqual(item["issued"], 140)
        card_log = EditLog.query.filter_by(entity_type="jobcard").one()
        self.assertEqual(card_log.username, "admin")
        self.assertEqual(card_log.old_values["movements"][0]["outflow"], 120)
        self.assertEqual(card_log.new_values["movements"][0]["outflow"], 160)
        self.assertEqual(EditLog.query.filter_by(entity_type="movement").count(), 2)

    def test_cancelling_incorrect_return_restores_given_balance(self):
        card_id = self.manual_card(returned=120)
        row = jobcard_edit_context(card_id)["returns"][0]
        self.assertEqual(self.job_edit(card_id, {f'line_{row["id"]}_quantity': 0})[0], "saved")
        item = get_jobcard_return_data(card_id)["items"][0]
        self.assertEqual(item["issued"], 120)
        self.assertEqual(Jobmovement.query.filter_by(flow_type="IN").one().inflow, 0)
        self.assertTrue(EditLog.query.filter_by(entity_type="movement").first())

    def test_product_and_type_can_be_corrected_together_for_given_and_returns(self):
        card_id = self.manual_card()
        context = jobcard_edit_context(card_id)
        changes = {f'line_{row["id"]}_type': "good_cut" for row in context["given"] + context["returns"]}
        self.assertEqual(self.job_edit(card_id, changes)[0], "saved")
        self.assertEqual({row.type_B for row in Jobmovement.query.all()}, {"good_cut"})
        self.assertEqual(Jobcard.query.one().product_list[0]["type"], "good_cut")

    def test_scanned_job_edit_updates_its_stock_bundle_automatically(self):
        bundle = self.bundle()
        card_id = add_jobcard(self.scan_payload(bundle), self.admin, "scan")["jobData"]["jobId"]
        row = jobcard_edit_context(card_id)["given"][0]
        self.assertEqual(self.job_edit(card_id, {f'line_{row["id"]}_pieces': 40,
                                               f'line_{row["id"]}_kg': "3.2",
                                               f'line_{row["id"]}_color': "RED"})[0], "saved")
        stock = db.session.get(Bundle, bundle.id)
        self.assertEqual((stock.pieces, stock.kg, stock.color, stock.status), (40, 3.2, "RED", "GIVEN"))
        self.assertEqual(Jobmovement.query.one().outflow, 40)
        self.assertEqual(Jobcard.query.one().product_list[0]["qty"], 40)

    def test_return_quantity_correction_clears_stale_calculation_but_logs_it(self):
        card_id = self.manual_card(returned=0)
        payload = self.return_payload(card_id, 60)
        payload["items"][0].update(entry_method="calculator", calculation_rows=[{"pieces": 30, "count": 2}])
        in_move_entery(payload, self.admin, "calculator")
        row = jobcard_edit_context(card_id)["returns"][0]
        self.assertEqual(self.job_edit(card_id, {f'line_{row["id"]}_quantity': 50})[0], "saved")
        self.assertEqual(ReturnBreakdown.query.one().calculation_rows, [])
        log = EditLog.query.filter_by(entity_type="return_breakdown").one()
        self.assertEqual(log.old_values["calculation_rows"], [{"pieces": 30, "count": 2}])

    def test_new_return_while_editor_is_open_causes_conflict(self):
        card_id = self.manual_card(returned=0)
        version = jobcard_edit_context(card_id)["version"]
        in_move_entery(self.return_payload(card_id, 20), self.admin, "new-return")
        self.assertEqual(self.job_edit(card_id, version=version)[0], "conflict")
        self.assertEqual(get_jobcard_return_data(card_id)["items"][0]["issued"], 100)

    def test_repeat_save_is_idempotent_and_non_admin_service_call_is_rejected(self):
        card_id = self.manual_card()
        self.assertEqual(self.job_edit(card_id)[0], "saved")
        log_count = EditLog.query.count()
        self.assertEqual(self.job_edit(card_id)[0], "duplicate")
        self.assertEqual(EditLog.query.count(), log_count)
        self.assertEqual(self.job_edit(card_id, username="operator", token="operator")[0], "invalid")

    def test_movement_edit_get_post_search_and_service_are_blocked(self):
        card_id = self.manual_card()
        movement = Jobmovement.query.first()
        for method in (self.client.get, self.client.post):
            response = method(f"/edit/movement/{movement.id}")
            self.assertEqual(response.status_code, 403)
            self.assertIn("managed by the app", response.get_data(as_text=True))
        self.assertIsNone(edit_context("movement", movement.id))
        self.assertIsNone(search_entries("movement"))
        self.assertEqual(save_entry("movement", movement.id, {}, "", "", "admin")[0], "invalid")
        self.assertNotIn('<option value="movement"', self.client.get("/edit").get_data(as_text=True))
        self.assertEqual(self.client.get(f"/edit/jobcard/{card_id}").status_code, 200)
        self.login_as(self.operator)
        self.assertEqual(self.client.get(f"/edit/jobcard/{card_id}").status_code, 302)

    def test_issued_payroll_cannot_be_changed_by_job_corrections(self):
        from payroll_service import save_rate, payroll_preview, issue_payroll
        card_id = self.manual_card(returned=120)
        save_rate(self.product.id, "", "5.5", "new", "rate", self.admin)
        preview = payroll_preview(self.worker.id, [card_id], "0")
        issue_payroll(self.worker.id, [card_id], "0", preview["version"], "Cash", "", "", "pay", self.admin)
        self.assertEqual(self.job_edit(card_id)[0], "invalid")
        html = self.client.get(f"/edit/jobcard/{card_id}").get_data(as_text=True)
        self.assertIn('class="edit-fields" disabled', html)
        self.assertIn("paid quantities are locked", html)

    def test_browser_date_format_does_not_change_unedited_timestamp_precision(self):
        card_id = self.manual_card()
        card = db.session.get(Jobcard, card_id)
        old_date = card.date
        old_movements = {row.id: row.date for row in Jobmovement.query.all()}
        context = jobcard_edit_context(card_id)
        self.assertNotIn(".", context["fields"][0]["value"])
        self.assertEqual(self.job_edit(card_id)[0], "saved")
        self.assertEqual(db.session.get(Jobcard, card_id).date, old_date)
        self.assertEqual({row.id: row.date for row in Jobmovement.query.all()}, old_movements)

    def test_cancelled_wrong_type_history_does_not_block_completed_payroll(self):
        from payroll_service import save_rate, completed_job_quotes
        from data_Process import get_jobcard_ledger
        card_id = self.manual_card()
        context = jobcard_edit_context(card_id)
        given, returned = context["given"][0], context["returns"][0]
        self.assertEqual(self.job_edit(card_id, {f'line_{given["id"]}_type': "good_cut",
                                               f'line_{returned["id"]}_quantity': 0})[0], "saved")
        cancelled = get_jobcard_ledger(card_id)["job"]["ledger"][-1]
        self.assertEqual((cancelled["flow_type"], cancelled["returned"]), ("IN", 0))
        html = self.client.get(f"/jobcard/{card_id}/ledger").get_data(as_text=True)
        self.assertIn("Return cancelled", html)
        in_move_entery(self.return_payload(card_id, 120), self.admin, "correct-return")
        save_rate(self.product.id, "", "5.5", "new", "rate", self.admin)
        quotes = completed_job_quotes(self.worker)
        self.assertEqual(len(quotes), 1)
        self.assertEqual(quotes[0]["gross_paise"], 66000)

    def test_return_dates_cannot_create_a_negative_historical_balance(self):
        card_id = self.manual_card()
        returned = jobcard_edit_context(card_id)["returns"][0]
        self.assertEqual(self.job_edit(card_id, {f'line_{returned["id"]}_date': "2000-01-01T00:00:00"})[0], "invalid")

    def test_non_admin_cannot_post_return_corrections_to_the_job_page(self):
        card_id = self.manual_card()
        returned = jobcard_edit_context(card_id)["returns"][0]
        self.login_as(self.operator)
        response = self.client.post(f"/edit/jobcard/{card_id}", data={
            "edit_lines": "1", f'line_{returned["id"]}_quantity': "0",
            "edit_reason": "Attempt to restore return",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(db.session.get(Jobmovement, returned["id"]).inflow, 30)
        self.assertEqual(EditLog.query.count(), 0)
