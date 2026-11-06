"""Return history keeps the entered calculation instead of only its total."""

import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from flask import Flask

from data_Process import get_jobcard_return_data
from data_entry import in_move_entery
from modes import Jobcard, Jobmovement, ReturnBreakdown, db


class ReturnBreakdownTest(unittest.TestCase):
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
        card = Jobcard(date=datetime.now(), given_to="Vimal Master", given_by="admin", product_list=[])
        db.session.add(card)
        db.session.flush()
        self.card_id = card.id
        db.session.add(Jobmovement(
            date=datetime.now(), jobcard=str(card.id), partculer="Given",
            product_name="VIMAL 1 2MTR", name_of_mater="Vimal Master",
            enter_user="admin", type_B="lump", flow_type="OUT", outflow=200,
        ))
        db.session.commit()
        self.user = SimpleNamespace(username="admin")

    def tearDown(self):
        db.session.remove()
        for engine in db.engines.values():
            engine.dispose()
        self.context.pop()
        self.directory.cleanup()

    def payload(self, quantity, method, rows):
        return {
            "jobcard_id": self.card_id,
            "name": "Vimal Master",
            "items": [{
                "item_id": 1, "name_of_product": "VIMAL_1_2MTR", "type": "lump",
                "returned": quantity, "entry_method": method, "calculation_rows": rows,
            }],
        }

    def test_calculator_direct_and_completed_history(self):
        rows = [{"pieces": 30, "count": 4}, {"pieces": 25, "count": 2}]
        self.assertEqual(in_move_entery(self.payload(170, "calculator", rows), self.user, "calc-1")["code"], 101)
        active = get_jobcard_return_data(self.card_id)["items"]
        self.assertEqual(active[0]["issued"], 30)
        self.assertEqual(active[0]["given"]["total"], 200)
        self.assertEqual(active[0]["given"]["calculation_rows"], [])
        self.assertEqual(active[0]["history"][0]["calculation_rows"], rows)

        self.assertEqual(in_move_entery(self.payload(30, "direct", []), self.user, "direct-1")["code"], 101)
        result = get_jobcard_return_data(self.card_id)
        self.assertEqual(result["items"], [])
        history = result["completed_items"][0]["history"]
        self.assertEqual([entry["entry_method"] for entry in history], ["calculator", "direct"])
        self.assertEqual([entry["returned"] for entry in history], [170, 30])
        self.assertEqual(ReturnBreakdown.query.count(), 2)

    def test_rejects_calculation_that_does_not_match_total(self):
        result = in_move_entery(
            self.payload(120, "calculator", [{"pieces": 30, "count": 3}]),
            self.user, "bad-calc",
        )
        self.assertEqual(result, 405)
        self.assertEqual(ReturnBreakdown.query.count(), 0)
        self.assertEqual(get_jobcard_return_data(self.card_id)["items"][0]["issued"], 200)

    def test_older_return_keeps_total_without_inventing_calculation(self):
        db.session.add(Jobmovement(
            date=datetime.now(), jobcard=str(self.card_id),
            partculer=f"Return card {self.card_id} 20X1", product_name="VIMAL 1 2MTR",
            name_of_mater="Vimal Master", enter_user="admin", type_B="lump",
            flow_type="IN", inflow=20,
        ))
        db.session.commit()
        item = get_jobcard_return_data(self.card_id)["items"][0]
        self.assertEqual(item["issued"], 180)
        self.assertEqual(item["history"][0]["entry_method"], "legacy")
        self.assertEqual(item["history"][0]["calculation_rows"], [])

    def test_manual_job_card_given_patterns_are_shown(self):
        card = db.session.get(Jobcard, self.card_id)
        card.product_list = [
            {"name_of_prduct": "VIMAL 1 2MTR", "type": "lump", "qty": 120,
             "pieces_per_bundle": 30, "bundle_count": 4},
            {"name_of_prduct": "VIMAL 1 2MTR", "type": "lump", "qty": 80,
             "pieces_per_bundle": 40, "bundle_count": 2},
        ]
        db.session.commit()
        given = get_jobcard_return_data(self.card_id)["items"][0]["given"]
        self.assertEqual(given["total"], 200)
        self.assertEqual(given["calculation_rows"], [
            {"pieces": 30, "count": 4}, {"pieces": 40, "count": 2},
        ])

    def test_scanned_bundles_group_by_size(self):
        card = db.session.get(Jobcard, self.card_id)
        card.product_list = [
            {"name_of_prduct": "VIMAL 1 2MTR", "type": "lump", "qty": 50}
            for _ in range(4)
        ]
        db.session.commit()
        given = get_jobcard_return_data(self.card_id)["items"][0]["given"]
        self.assertEqual(given["calculation_rows"], [{"pieces": 50, "count": 4}])

    def test_inconsistent_given_breakdown_does_not_claim_exact_pattern(self):
        card = db.session.get(Jobcard, self.card_id)
        card.product_list = [{"name_of_prduct": "VIMAL 1 2MTR", "type": "lump", "qty": 50}]
        db.session.commit()
        given = get_jobcard_return_data(self.card_id)["items"][0]["given"]
        self.assertEqual(given["total"], 200)
        self.assertEqual(given["calculation_rows"], [])


if __name__ == "__main__":
    unittest.main()
