"""Job based outworker accounts keep every return linked to its job card."""

import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

from flask import Flask

from data_Process import outworker_job_ledger, get_jobcard_ledger, outworker_period_account
from modes import Jobcard, Jobmovement, ReturnBreakdown, EditLog, db
from return_reconciliation import unassigned_returns, matching_jobs, assign_return


class OutworkerJobLedgerTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        self.app = Flask(__name__)
        self.app.config.update(
            SQLALCHEMY_DATABASE_URI=f"sqlite:///{root / 'main.db'}",
            SQLALCHEMY_BINDS={"users": f"sqlite:///{root / 'users.db'}"},
        )
        db.init_app(self.app)
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        for engine in db.engines.values():
            engine.dispose()
        self.context.pop()
        self.directory.cleanup()

    def add_card(self, worker, created, quantity, product="VIMAL", type_name="lump", pieces=None, count=None):
        card = Jobcard(date=created, given_to=worker, given_by="admin", product_list=[{
            "name_of_prduct": product, "type": type_name, "qty": quantity,
            "pieces_per_bundle": pieces or quantity, "bundle_count": count or 1,
        }])
        db.session.add(card)
        db.session.flush()
        db.session.add(Jobmovement(
            date=created, jobcard=str(card.id), partculer="Given", product_name=product,
            name_of_mater=worker, enter_user="admin", type_B=type_name,
            flow_type="OUT", outflow=quantity,
        ))
        db.session.commit()
        return card

    def test_job_totals_include_later_returns_but_exclude_other_jobs(self):
        worker = "1***RAM--CITY/-"
        card = self.add_card(worker, datetime(2026, 10, 5, 9, 0), 120, pieces=30, count=4)
        return_movement = Jobmovement(
            date=datetime(2026, 11, 3, 12, 0), jobcard=str(card.id), partculer="Return",
            product_name="VIMAL", name_of_mater=worker, enter_user="admin",
            type_B="lump", flow_type="IN", inflow=50,
        )
        db.session.add(return_movement)
        db.session.flush()
        db.session.add(ReturnBreakdown(
            movement_id=return_movement.id, entry_method="calculator",
            calculation_rows=[{"pieces": 25, "count": 2}],
        ))
        db.session.commit()
        self.add_card(worker, datetime(2026, 9, 1), 70)
        self.add_card("2***OTHER--CITY/-", datetime(2026, 10, 6), 40)

        report = outworker_job_ledger(worker, date(2026, 10, 1), date(2026, 10, 31))
        self.assertEqual(report["summary"], {
            "jobs": 1, "given": 120, "returned": 50, "kept": 0, "remaining": 70,
            "open_jobs": 1, "completed_jobs": 0,
        })
        job = report["jobs"][0]
        self.assertEqual(job["id"], card.id)
        self.assertEqual(job["products"][0]["given_patterns"], [{"pieces": 30, "count": 4}])
        self.assertEqual(job["products"][0]["returns"][0]["calculation_rows"], [{"pieces": 25, "count": 2}])
        self.assertEqual([entry["balance"] for entry in job["ledger"]], [120, 70])
        self.assertEqual([entry["product_balance"] for entry in job["ledger"]], [120, 70])
        self.assertEqual(job["ledger"][0]["calculation_rows"], [{"pieces": 30, "count": 4}])
        self.assertEqual(job["last_activity"], datetime(2026, 11, 3, 12, 0))
        detail = get_jobcard_ledger(card.id)
        self.assertEqual(detail["outworker"], worker)
        self.assertEqual(detail["job"]["ledger"][1]["entered_by"], "admin")
        self.assertEqual(detail["job"]["ledger"][1]["calculation_rows"], [{"pieces": 25, "count": 2}])

    def test_job_detail_keeps_product_and_job_running_balances(self):
        worker = "1***RAM--CITY/-"
        card = self.add_card(worker, datetime(2026, 10, 5, 9, 0), 120)
        db.session.add(Jobmovement(
            date=datetime(2026, 10, 5, 9, 10), jobcard=str(card.id),
            partculer="Given", product_name="SECOND", name_of_mater=worker,
            enter_user="admin", type_B="fent", flow_type="OUT", outflow=20,
        ))
        db.session.add(Jobmovement(
            date=datetime(2026, 10, 6, 14, 30), jobcard=str(card.id),
            partculer="Return", product_name="VIMAL", name_of_mater=worker,
            enter_user="clerk", type_B="lump", flow_type="IN", inflow=30,
        ))
        db.session.commit()
        detail = get_jobcard_ledger(card.id)
        self.assertEqual(detail["job"]["remaining"], 110)
        self.assertEqual([row["balance"] for row in detail["job"]["ledger"]], [120, 140, 110])
        self.assertEqual([row["product_balance"] for row in detail["job"]["ledger"]], [120, 20, 90])
        self.assertEqual(detail["job"]["ledger"][-1]["entered_by"], "clerk")
        self.assertEqual(detail["job"]["ledger"][-1]["method"], "legacy")

    def test_empty_range_returns_zero_account(self):
        report = outworker_job_ledger("1***RAM--CITY/-", date(2026, 10, 1), date(2026, 10, 31))
        self.assertEqual(report["jobs"], [])
        self.assertEqual(report["summary"]["remaining"], 0)
        self.assertIsNone(get_jobcard_ledger(9999))

    def test_period_account_carries_older_jobs_and_excludes_later_returns(self):
        older = self.add_card("RAM", datetime(2026, 9, 10), 100)
        current = self.add_card("RAM", datetime(2026, 10, 5), 60)
        self.add_card("OTHER", datetime(2026, 10, 5), 999)
        self.add_card("RAM", datetime(2026, 11, 5), 999)
        for card, when, quantity in [
            (older, datetime(2026, 9, 20), 20),
            (older, datetime(2026, 10, 10), 30),
            (current, datetime(2026, 10, 15), 60),
            (older, datetime(2026, 11, 1), 50),
        ]:
            db.session.add(Jobmovement(
                date=when, jobcard=str(card.id), partculer="Return",
                product_name="VIMAL", name_of_mater="RAM", enter_user="admin",
                type_B="lump", flow_type="IN", inflow=quantity,
            ))
        self.add_unassigned_return("RAM", 999)
        db.session.commit()
        account = outworker_period_account("RAM", date(2026, 10, 1), date(2026, 10, 31))
        self.assertEqual(account["totals"], {
            "opening": 80, "given": 60, "returned": 90, "kept": 0, "closing": 50,
            "incomplete_jobs": 1, "pieces_left": 50,
        })
        self.assertEqual([job["id"] for job in account["outstanding_jobs"]], [older.id])
        product = account["products"][0]
        self.assertEqual(product["incomplete_jobs"], 1)
        self.assertEqual({job["id"]: job["remaining"] for job in product["jobs"]},
                         {older.id: 50, current.id: 0})
        # An empty issue-date range must still carry an older outstanding job.
        carried = outworker_period_account("RAM", date(2026, 10, 20), date(2026, 10, 31))
        self.assertEqual(carried["totals"]["opening"], 50)
        self.assertEqual(carried["totals"]["closing"], 50)

    def test_period_account_counts_jobs_once_and_keeps_product_shortages_visible(self):
        card = self.add_card("RAM", datetime(2026, 10, 1), 50)
        db.session.add_all([
            Jobmovement(date=datetime(2026, 10, 1), jobcard=str(card.id), partculer="Given",
                        product_name="SECOND", name_of_mater="RAM", enter_user="admin",
                        type_B="fent", flow_type="OUT", outflow=30),
            Jobmovement(date=datetime(2026, 10, 2), jobcard=str(card.id), partculer="Return",
                        product_name="SECOND", name_of_mater="RAM", enter_user="admin",
                        type_B="fent", flow_type="IN", inflow=40),
        ])
        db.session.commit()
        account = outworker_period_account("RAM", date(2026, 10, 1), date(2026, 10, 31))
        self.assertEqual(account["totals"]["closing"], 40)
        self.assertEqual(account["totals"]["pieces_left"], 50)
        self.assertEqual(account["totals"]["incomplete_jobs"], 1)
        self.assertEqual(len(account["products"]), 2)
        empty = outworker_period_account("UNKNOWN", date(2026, 10, 1), date(2026, 10, 31))
        self.assertEqual(empty["totals"]["closing"], 0)
        self.assertEqual(empty["outstanding_jobs"], [])

    def add_unassigned_return(self, worker, quantity=30):
        movement = Jobmovement(
            date=datetime(2026, 10, 7, 12), jobcard=None, partculer="Original return",
            product_name="VIMAL", name_of_mater=worker, enter_user="original-clerk",
            type_B="lump", flow_type="IN", inflow=quantity,
        )
        db.session.add(movement)
        db.session.commit()
        return movement

    def test_legacy_assignment_updates_only_selected_job_and_audits_link(self):
        card = self.add_card("RAM", datetime(2026, 10, 5), 120)
        other = self.add_card("RAM", datetime(2026, 10, 6), 70)
        movement = self.add_unassigned_return("RAM")
        self.assertEqual(len(unassigned_returns("RAM")), 1)
        assign_return(movement.id, card.id, SimpleNamespace(username="admin"))
        self.assertEqual(get_jobcard_ledger(card.id)["job"]["remaining"], 90)
        self.assertEqual(get_jobcard_ledger(other.id)["job"]["remaining"], 70)
        self.assertEqual(unassigned_returns("RAM"), [])
        self.assertEqual(movement.enter_user, "original-clerk")
        self.assertEqual(movement.partculer, "Original return")
        log = EditLog.query.one()
        self.assertEqual(log.old_values, {"jobcard": None})
        self.assertEqual(log.new_values, {"jobcard": str(card.id)})
        self.assertEqual(log.username, "admin")
        with self.assertRaises(ValueError):
            assign_return(movement.id, other.id, SimpleNamespace(username="another-admin"))
        self.assertEqual(EditLog.query.count(), 1)

    def test_candidates_reject_wrong_worker_product_type_date_and_low_balance(self):
        good = self.add_card("RAM", datetime(2026, 10, 5), 50)
        self.add_card("OTHER", datetime(2026, 10, 5), 100)
        wrong = self.add_card("RAM", datetime(2026, 10, 5), 100, product="OTHER")
        self.add_card("RAM", datetime(2026, 10, 5), 100, type_name="fent")
        self.add_card("RAM", datetime(2026, 10, 8), 100)
        self.add_card("RAM", datetime(2026, 10, 5), 10)
        first = self.add_unassigned_return("RAM", 30)
        second = self.add_unassigned_return("RAM", 30)
        self.assertEqual([row["id"] for row in matching_jobs(first)], [good.id])
        with self.assertRaises(ValueError):
            assign_return(first.id, wrong.id, SimpleNamespace(username="admin"))
        self.assertIsNone(first.jobcard)
        assign_return(first.id, good.id, SimpleNamespace(username="admin"))
        with self.assertRaises(ValueError):
            assign_return(second.id, good.id, SimpleNamespace(username="admin"))
        self.assertIsNone(second.jobcard)
        self.assertEqual(get_jobcard_ledger(good.id)["job"]["remaining"], 20)

    def test_older_return_cannot_use_pieces_issued_after_its_date(self):
        card = self.add_card("RAM", datetime(2026, 10, 1), 100)
        db.session.add_all([
            Jobmovement(date=datetime(2026, 10, 2), jobcard=str(card.id), partculer="Earlier return",
                        product_name="VIMAL", name_of_mater="RAM", enter_user="admin",
                        type_B="lump", flow_type="IN", inflow=80),
            Jobmovement(date=datetime(2026, 10, 10), jobcard=str(card.id), partculer="Later issue",
                        product_name="VIMAL", name_of_mater="RAM", enter_user="admin",
                        type_B="lump", flow_type="OUT", outflow=100),
        ])
        db.session.commit()
        movement = self.add_unassigned_return("RAM", 50)
        self.assertEqual(matching_jobs(movement), [])
        with self.assertRaises(ValueError):
            assign_return(movement.id, card.id, SimpleNamespace(username="admin"))


if __name__ == "__main__":
    unittest.main()
