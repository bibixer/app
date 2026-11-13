"""The navigation lookup opens a job card ledger by its printed number."""

import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from app import create_app
from modes import Jobcard, Jobmovement, Outworker, User, db


class JobcardLedgerLookupTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        self.previous_database = os.environ.get("DATABASE_URI")
        self.previous_users_database = os.environ.get("USERS_DATABASE_URI")
        os.environ["DATABASE_URI"] = f"sqlite:///{root / 'main.db'}"
        os.environ["USERS_DATABASE_URI"] = f"sqlite:///{root / 'users.db'}"
        self.app = create_app({"SIMPLE_WORKFLOW": False})
        self.app.config["WTF_CSRF_ENABLED"] = False
        with self.app.app_context():
            user = User("admin", "test-password", 1)
            db.session.add(user)
            db.session.add(Jobcard(
                date=datetime(2026, 10, 5), given_to="RAM", given_by="admin",
                product_list=[],
            ))
            db.session.commit()
            self.user_id = user.id
            self.auth_id = user.get_id()
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session["_user_id"] = self.auth_id
            session["_fresh"] = True

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            for engine in db.engines.values():
                engine.dispose()
        for name, value in (("DATABASE_URI", self.previous_database),
                            ("USERS_DATABASE_URI", self.previous_users_database)):
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        self.directory.cleanup()

    def test_lookup_and_navigation(self):
        response = self.client.get("/jobcard/ledger")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("Open a job card ledger", html)
        self.assertIn("Job Ledger", html)
        self.assertIn("Job card ledger", html)

        response = self.client.get("/jobcard/ledger?jobcard_id=1")
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.location.endswith("/jobcard/1/ledger"))
        self.assertEqual(self.client.get(response.location).status_code, 200)

    def test_unknown_or_invalid_number_stays_on_lookup(self):
        for value, message in (("999", "was not found"), ("0", "valid job card number"),
                               ("abc", "valid job card number")):
            with self.subTest(value=value):
                response = self.client.get("/jobcard/ledger", query_string={"jobcard_id": value})
                self.assertEqual(response.status_code, 200)
                self.assertIn(message, response.get_data(as_text=True))

    def test_worker_report_can_link_an_older_return(self):
        worker = "1***RAM--CITY/-"
        with self.app.app_context():
            db.session.add(Outworker(id=1, name="RAM", adders="CITY", number=1, enter_user="admin"))
            card = db.session.get(Jobcard, 1)
            card.given_to = worker
            for flow, quantity, card_number in [("OUT", 100, "1"), ("IN", 20, None)]:
                row = Jobmovement(
                    date=datetime(2026, 10, 6), jobcard=card_number, partculer="Original entry",
                    product_name="VIMAL", name_of_mater=worker, enter_user="clerk",
                    type_B="lump", flow_type=flow,
                    outflow=quantity if flow == "OUT" else 0,
                    inflow=quantity if flow == "IN" else 0,
                )
                db.session.add(row)
            db.session.commit()
            return_id = row.id
        filters = {"name": worker, "date_from": "2026-10-01", "date_to": "2026-10-31"}
        response = self.client.post("/outworker_report", data=filters)
        self.assertEqual(response.status_code, 200)
        self.assertIn("Older returns awaiting a job card", response.get_data(as_text=True))
        self.assertIn("Product account & carried balance", response.get_data(as_text=True))
        self.assertIn("Balance c/f", response.get_data(as_text=True))
        self.assertIn("Incomplete jobs · remaining by job card", response.get_data(as_text=True))
        response = self.client.post("/outworker_report", data={
            **filters, "action": "assign_return", "movement_id": return_id, "card_id": 1,
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn("Return linked to the job card", response.get_data(as_text=True))
        with self.app.app_context():
            self.assertEqual(db.session.get(Jobmovement, return_id).jobcard, "1")


if __name__ == "__main__":
    unittest.main()
