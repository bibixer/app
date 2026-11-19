from uuid import uuid4

from sqlalchemy import create_engine

from modes import Item_data, Outworker, OutworkerAdvance
from schema_updates import ensure_outworker_contact_number
from support import AppTestCase


class InputValidationTest(AppTestCase):
    def setUp(self):
        super().setUp()
        self.app.config.update(SIMPLE_WORKFLOW=True, LABEL_PRINT_ROOT=self.temp.name)

    def submit(self, path, **fields):
        return self.client.post(path, data={**fields, "submission_token": uuid4().hex})

    def test_product_name_rejects_hidden_characters_without_clearing_form(self):
        for name, alias in [("\u200b", "DRAFT ALIAS"), ("NEW\u200b PRODUCT", "DRAFT ALIAS"),
                            ("Draft Product", "VIM"), ("Draft Product", "INVISIBLE\u2060ALIAS")]:
            with self.subTest(name=name, alias=alias):
                response = self.submit("/add_items", name=name, aliases=alias)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(Item_data.query.count(), 1)
                self.assertIn(alias, response.get_data(as_text=True))
        response = self.submit("/add_items", name="  नया\tप्रोडक्ट  ", aliases="")
        self.assertEqual(response.status_code, 302)
        self.assertIsNotNone(Item_data.query.filter_by(name="नया प्रोडक्ट").first())

    def test_mobile_number_validation_and_leading_zero(self):
        for number in ("12345", "12345 67890", "+1234567890", "1e9", "0000000000"):
            with self.subTest(number=number):
                response = self.submit("/add_outworver", name="Draft Worker", address="City", number=number)
                self.assertEqual(response.status_code, 200)
                self.assertIn("Draft Worker", response.get_data(as_text=True))
                self.assertEqual(Outworker.query.count(), 1)
        response = self.submit("/add_outworver", name="Draft Worker", address="City", number="0123456789")
        self.assertEqual(response.status_code, 302)
        worker = Outworker.query.filter_by(name="DRAFT WORKER").one()
        self.assertEqual(worker.mobile, "0123456789")
        self.assertEqual(self.worker.mobile, "123")
        self.assertIn('value="0123456789"', self.client.get(
            f"/edit/outworker/{worker.id}").get_data(as_text=True))
        self.assertEqual(self.edit("outworker", self.worker.id, {"adders": "NEW CITY"})[0], "saved")

    def test_legacy_mobile_schema_upgrade_keeps_existing_values(self):
        engine = create_engine(f"sqlite:///{self.temp.name}/old-contacts.db")
        self.addCleanup(engine.dispose)
        with engine.begin() as connection:
            connection.exec_driver_sql("CREATE TABLE OutworkData (id INTEGER PRIMARY KEY, number INTEGER NOT NULL)")
            connection.exec_driver_sql("INSERT INTO OutworkData (number) VALUES (123)")
        ensure_outworker_contact_number(engine)
        ensure_outworker_contact_number(engine)
        with engine.connect() as connection:
            self.assertEqual(connection.exec_driver_sql(
                "SELECT number, contact_number FROM OutworkData").one(), (123, None))

    def test_report_resolves_case_spacing_aliases_and_ids(self):
        for name in ("  rAm   CiTy  ", "RAM\u00a0CITY", f" {self.worker.id} ", self.worker_name.lower()):
            with self.subTest(name=name):
                response = self.client.post("/outworker_report", data={
                    "name": name, "date_from": "2026-11-01", "date_to": "2026-11-30",
                })
                self.assertIn('aria-label="Selected outworker"', response.get_data(as_text=True))

    def test_advances_accept_only_plain_decimals(self):
        for amount in ("1e3", "1_000", "1 000", "1,000", "１２.５０", "12.345", "NaN"):
            with self.subTest(amount=amount):
                response = self.client.post("/payroll", headers={"Accept": "application/json"}, data={
                    "action": "advance", "worker_id": self.worker.id, "amount": amount,
                    "method": "Cash", "submission_token": uuid4().hex,
                })
                self.assertEqual(response.status_code, 400)
                self.assertEqual(OutworkerAdvance.query.count(), 0)
        response = self.submit("/payroll", action="advance", worker_id=self.worker.id,
                               amount=" 42.50 ", method="Cash")
        self.assertEqual(response.status_code, 302)
        self.assertEqual(OutworkerAdvance.query.one().amount_paise, 4250)
