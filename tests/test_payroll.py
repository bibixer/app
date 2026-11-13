"""Returned pieces can be paid in batches; quantities and advances cannot be reused."""

import os
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from app import create_app
from edit_service import edit_context, save_entry
from modes import (db, User, Outworker, Item_data, Jobcard, Jobmovement, OutworkerRate,
                   OutworkerAdvance, OutworkerPayroll, OutworkerPayrollJob, EditLog)
from payroll_service import (worker_label, rate_version, save_rate, record_advance, advance_balance,
                             completed_job_quotes, payroll_preview, issue_payroll, payment_account,
                             parse_money)


class PayrollTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        self.previous = {name: os.environ.get(name) for name in ("DATABASE_URI", "USERS_DATABASE_URI")}
        os.environ["DATABASE_URI"] = f"sqlite:///{root / 'main.db'}"
        os.environ["USERS_DATABASE_URI"] = f"sqlite:///{root / 'users.db'}"
        self.app = create_app({"SIMPLE_WORKFLOW": False})
        self.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        self.context = self.app.app_context()
        self.context.push()
        self.user = User("admin", "test-password", 1)
        self.worker = Outworker(name="RAM", adders="CITY", number=1, enter_user="admin")
        self.product = Item_data(name="VIMAL 1 2MTR", meters=1, size=1, enter_user="admin")
        db.session.add_all([self.user, self.worker, self.product])
        db.session.commit()
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session["_user_id"] = self.user.get_id()
            session["_fresh"] = True

    def tearDown(self):
        db.session.remove()
        for engine in db.engines.values():
            engine.dispose()
        self.context.pop()
        for name, value in self.previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        self.directory.cleanup()

    def rate(self, value="5.50", type_name="", token="rate"):
        row = OutworkerRate.query.filter_by(product_id=self.product.id, bundle_type=type_name).first()
        save_rate(self.product.id, type_name, value, rate_version(row), token, self.user)

    def card(self, patterns=(("lump", 100, 100),)):
        card = Jobcard(date=datetime(2026, 11, 1), given_to=worker_label(self.worker),
                       given_by="admin", product_list=[])
        db.session.add(card)
        db.session.flush()
        for type_name, given, returned in patterns:
            for flow, quantity in [("OUT", given), ("IN", returned)]:
                if quantity:
                    db.session.add(Jobmovement(
                        date=datetime(2026, 11, 2), jobcard=str(card.id), partculer=flow,
                        product_name=self.product.name, name_of_mater=worker_label(self.worker),
                        enter_user="admin", type_B=type_name, flow_type=flow,
                        outflow=quantity if flow == "OUT" else 0,
                        inflow=quantity if flow == "IN" else 0,
                    ))
        db.session.commit()
        return card

    def pay(self, card_ids, deduction="0", token="pay", version=None):
        preview = payroll_preview(self.worker.id, card_ids, deduction)
        return issue_payroll(self.worker.id, card_ids, deduction, version or preview["version"],
                             "Cash", "receipt-1", "", token, self.user)

    def test_base_type_override_advance_deduction_and_immutable_receipt(self):
        self.rate()
        self.rate("5.70", "good_cut", "override")
        card = self.card((("lump", 100, 100), ("good_cut", 50, 50)))
        record_advance(self.worker.id, "200", "Cash", "A1", "Advance", "advance", self.user)
        preview = payroll_preview(self.worker.id, [card.id], "150")
        self.assertEqual(preview["gross_paise"], 83500)
        self.assertEqual(preview["net_paise"], 68500)
        self.assertEqual(preview["remaining_advance_paise"], 5000)
        payroll = self.pay([card.id], "150")
        self.assertEqual(advance_balance(self.worker.id), 5000)
        saved = OutworkerPayrollJob.query.one()
        self.assertEqual({line["type"]: line["rate"] for line in saved.lines},
                         {"lump": "5.5", "good_cut": "5.7"})
        self.rate("9.00", token="new-rate")
        self.assertEqual(db.session.get(OutworkerPayroll, payroll.id).gross_paise, 83500)
        self.assertEqual(completed_job_quotes(self.worker), [])
        ledger = payment_account(self.worker.id)
        self.assertEqual([event["balance_paise"] for event in ledger["events"]], [20000, 5000])
        response = self.client.get(f"/payroll/{payroll.id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn("₹5.7", response.get_data(as_text=True))

    def test_rate_rounding_validation_and_audit(self):
        self.rate("5.5555")
        card = self.card((("lump", 3, 3),))
        self.assertEqual(payroll_preview(self.worker.id, [card.id], "0")["gross_paise"], 1667)
        self.assertEqual(EditLog.query.filter_by(entity_type="outworker_rate").count(), 1)
        for amount in ("NaN", "Infinity", "-1", "1.001", "999999999999"):
            with self.subTest(amount=amount), self.assertRaises(ValueError):
                parse_money(amount)
        with self.assertRaises(ValueError):
            save_rate(self.product.id, "unlisted", "5", "new", "invalid-rate", self.user)
        with self.assertRaises(ValueError):
            save_rate(self.product.id, "", "7", "new", "stale-rate", self.user)
        row = OutworkerRate.query.one()
        save_rate(self.product.id, "", "", rate_version(row), "remove", self.user, remove=True)
        with self.assertRaises(ValueError):
            payroll_preview(self.worker.id, [card.id], "0")

    def test_accepts_partial_but_rejects_mismatched_and_already_paid_jobs(self):
        self.rate()
        partial = self.card((("lump", 100, 99),))
        # Net total is zero, but one type is over-returned and another is short.
        mismatched = self.card((("lump", 100, 90), ("good_cut", 50, 60)))
        quote = payroll_preview(self.worker.id, [partial.id], '0')
        self.assertEqual(quote['pieces'], 99)
        self.assertEqual(quote['jobs'][0]['pending_return'], 1)
        with self.assertRaises(ValueError):
            self.pay([mismatched.id], token=f"pay-{mismatched.id}")
        complete = self.card()
        self.pay([complete.id])
        for token in ("pay", "another-browser"):
            with self.assertRaises(ValueError):
                self.pay([complete.id], token=token)
        self.assertEqual(OutworkerPayroll.query.count(), 1)
        self.assertEqual(OutworkerPayrollJob.query.count(), 1)

    def test_advances_are_idempotent_and_deductions_are_limited(self):
        self.rate()
        card = self.card()
        record_advance(self.worker.id, "700", "Cash", "", "", "advance", self.user)
        with self.assertRaises(ValueError):
            record_advance(self.worker.id, "700", "Cash", "", "", "advance", self.user)
        self.assertEqual(OutworkerAdvance.query.count(), 1)
        for deduction in ("701", "551", "-1", "0.001"):
            with self.assertRaises(ValueError):
                payroll_preview(self.worker.id, [card.id], deduction)
        self.pay([card.id], "550")
        self.assertEqual(OutworkerPayroll.query.one().net_paise, 0)
        self.assertEqual(advance_balance(self.worker.id), 15000)

    def test_stale_rate_or_advance_requires_new_preview(self):
        self.rate()
        card = self.card()
        preview = payroll_preview(self.worker.id, [card.id], "0")
        self.rate("6", token="rate-change")
        with self.assertRaises(ValueError):
            self.pay([card.id], version=preview["version"])
        preview = payroll_preview(self.worker.id, [card.id], "0")
        record_advance(self.worker.id, "10", "Cash", "", "", "advance", self.user)
        with self.assertRaises(ValueError):
            self.pay([card.id], version=preview["version"])
        self.assertEqual(OutworkerPayroll.query.count(), 0)

    def test_concurrent_payrolls_cannot_reuse_advance(self):
        self.rate()
        cards = [self.card(), self.card()]
        record_advance(self.worker.id, "100", "Cash", "", "", "advance", self.user)
        worker_id, user_id = self.worker.id, self.user.id
        card_ids = [card.id for card in cards]
        previews = [payroll_preview(worker_id, [card.id], "100") for card in cards]
        barrier = threading.Barrier(2)

        def submit(index):
            with self.app.app_context():
                user = db.session.get(User, user_id)
                barrier.wait(timeout=5)
                try:
                    result = issue_payroll(worker_id, [card_ids[index]], "100", previews[index]["version"],
                                           "Cash", "", "", f"parallel-{index}", user)
                    return result.id
                except ValueError:
                    return None
                finally:
                    db.session.remove()

        db.session.remove()
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(submit, range(2)))
        self.assertEqual(sum(result is not None for result in results), 1)
        self.assertEqual(OutworkerPayroll.query.count(), 1)
        self.assertEqual(advance_balance(worker_id), 0)

    def test_concurrent_saves_cannot_pay_the_same_job_twice(self):
        self.rate()
        card_id = self.card().id
        worker_id, user_id = self.worker.id, self.user.id
        version = payroll_preview(worker_id, [card_id], "0")["version"]
        barrier = threading.Barrier(2)

        def submit(index):
            with self.app.app_context():
                user = db.session.get(User, user_id)
                barrier.wait(timeout=5)
                try:
                    return issue_payroll(worker_id, [card_id], "0", version,
                                         "Cash", "", "", f"same-job-{index}", user).id
                except ValueError:
                    return None
                finally:
                    db.session.remove()

        db.session.remove()
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(submit, range(2)))
        self.assertEqual(sum(result is not None for result in results), 1)
        self.assertEqual(OutworkerPayroll.query.count(), 1)
        self.assertEqual(OutworkerPayrollJob.query.count(), 1)

    def test_jobs_from_another_outworker_cannot_be_included(self):
        self.rate()
        card = self.card()
        other = Outworker(name="OTHER", adders="CITY", number=2, enter_user="admin")
        db.session.add(other)
        db.session.commit()
        with self.assertRaises(ValueError):
            payroll_preview(other.id, [card.id], "0")
        self.assertEqual(OutworkerPayroll.query.count(), 0)

    def test_http_rates_preview_payment_navigation_and_admin_access(self):
        response = self.client.get("/payroll/rates")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Base rate", response.get_data(as_text=True))
        response = self.client.post("/payroll/rates", data={
            "product_id": self.product.id, "bundle_type": "", "rate": "5.5", "version": "new",
            "submission_token": "http-rate", "action": "save",
        })
        self.assertEqual(response.status_code, 302)
        card = self.card()
        response = self.client.get(f"/payroll/job/{card.id}")
        self.assertEqual(response.status_code, 302)
        self.assertIn("worker_id=", response.location)
        response = self.client.post("/payroll", data={
            "worker_id": self.worker.id, "action": "advance", "amount": "100", "method": "Cash",
            "submission_token": "http-advance",
        })
        self.assertEqual(response.status_code, 302)
        response = self.client.post("/payroll", data={
            "worker_id": self.worker.id, "job_ids": card.id, "action": "preview", "deduction": "50",
            "submission_token": "http-pay",
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn("Final payment", response.get_data(as_text=True))
        preview = payroll_preview(self.worker.id, [card.id], "50")
        response = self.client.post("/payroll", data={
            "worker_id": self.worker.id, "job_ids": card.id, "action": "pay", "deduction": "50",
            "version": preview["version"], "method": "Cash", "submission_token": "http-pay",
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith("/payroll/1"))
        self.assertEqual(self.client.get(response.location).status_code, 200)
        self.assertEqual(self.client.get(f"/jobcard/{card.id}/ledger").status_code, 200)
        self.assertIn("View payroll #", self.client.get(f"/jobcard/{card.id}/ledger").get_data(as_text=True))
        response = self.client.get(f"/payroll?worker_id={self.worker.id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Payroll #1", response.get_data(as_text=True))
        self.app.config["WTF_CSRF_ENABLED"] = True
        advance_count = OutworkerAdvance.query.count()
        response = self.client.post("/payroll", data={
            "worker_id": self.worker.id, "action": "advance", "amount": "100", "method": "Cash",
            "submission_token": "no-csrf",
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn("This form expired", response.get_data(as_text=True))
        self.assertEqual(OutworkerAdvance.query.count(), advance_count)
        self.assertEqual(OutworkerPayroll.query.count(), 1)
        self.user.role = 2
        db.session.commit()
        self.assertEqual(self.client.get("/payroll").status_code, 302)
        self.assertEqual(self.client.get("/payroll/rates").status_code, 302)
        self.assertEqual(self.client.get("/payroll/1").status_code, 403)

    def test_paid_movement_edit_is_rejected(self):
        self.rate()
        card = self.card()
        self.pay([card.id])
        movement = Jobmovement.query.filter_by(jobcard=str(card.id), flow_type="OUT").one()
        self.assertIsNone(edit_context("movement", movement.id))
        values = {field: str(getattr(movement, field) or "") for field in (
            "jobcard", "bundle", "partculer", "product_name", "name_of_mater", "type_B", "flow_type")}
        values.update(date=movement.date.isoformat(), outflow="101", inflow="0")
        status, message = save_entry("movement", movement.id, values, "unused", "paid-edit", "admin")
        self.assertEqual(status, "invalid")
        self.assertIn("system-managed", message)
        self.assertEqual(db.session.get(Jobmovement, movement.id).outflow, 100)


if __name__ == "__main__":
    unittest.main()
