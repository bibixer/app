"""Isolated application fixtures. Tests never use the production databases or printers."""

import os
import tempfile
import unittest
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from flask import g

from app import create_app
from modes import (db, User, Item_data, ItemAlias, Outworker, OutworkerAlias,
                   Cuter, Party, Bale_date, Lump, Bundle)
from master_aliases import master_full_name


class AppTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="bh-tests-")
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        environment = patch.dict(os.environ, {
            "DATABASE_URI": f"sqlite:///{root / 'main.db'}",
            "USERS_DATABASE_URI": f"sqlite:///{root / 'users.db'}",
        })
        environment.start()
        self.addCleanup(environment.stop)
        self.app = create_app({"SIMPLE_WORKFLOW": False})
        self.app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
        @self.app.before_request
        def clear_test_login_cache():
            # Service tests hold an outer app context across otherwise independent requests.
            g.pop("_login_user", None)
        self.context = self.app.app_context()
        self.context.push()
        self.addCleanup(self.close_database)
        for name in ("job_cade_print", "outworker_qr_print", "buldel_qr_print", "job_return_print"):
            printer = patch(f"data_entry.{name}", return_value=101)
            setattr(self, name, printer.start())
            self.addCleanup(printer.stop)
        self.admin = User("admin", "test-password", 1)
        self.operator = User("operator", "operator-password", 2)
        self.product = Item_data(name="VIMAL 1 2MTR", size=2, meters=1.5, enter_user="admin")
        self.worker = Outworker(name="RAM", adders="CITY", number=123, enter_user="admin")
        self.cutter = Cuter(name="CUTTER", enter_user="admin")
        self.party = Party(name="SUPPLIER", enter_user="admin")
        db.session.add_all([self.admin, self.operator, self.product, self.worker, self.cutter, self.party])
        db.session.flush()
        db.session.add_all([
            ItemAlias(item_id=self.product.id, alias="VIM"),
            OutworkerAlias(worker_id=self.worker.id, alias="RAM CITY"),
        ])
        db.session.commit()
        self.client = self.app.test_client()
        self.login_as(self.admin)

    def close_database(self):
        db.session.remove()
        for engine in db.engines.values():
            engine.dispose()
        self.context.pop()

    def login_as(self, user):
        with self.client.session_transaction() as session:
            session.clear()
            session["_user_id"] = user.get_id()
            session["_fresh"] = True

    @property
    def worker_name(self):
        return master_full_name(self.worker)

    def bundle(self, pieces=36, product=None, type_name="lump"):
        now = datetime(2026, 11, 1, 10)
        bale = Bale_date(part_name=self.party.name, lot_number=1, lot_count=1, bale_number=1,
                         bale_date=now, enter_user="admin", cut_by=self.cutter.name,
                         product=product or self.product.name)
        db.session.add(bale)
        db.session.flush()
        lump = Lump(entry_datetime=now, bale_id=bale.id, enter_user="admin", cut_by=self.cutter.name,
                    bundle_type=type_name, product=product or self.product.name, meters=100,
                    meters_add_remove=0, color="BLUE", number_of_bundlie=1)
        db.session.add(lump)
        db.session.flush()
        bundle = Bundle(entry_datetime=now, lump_id=lump.id, product=product or self.product.name,
                        color="BLUE", pieces=pieces, kg=2.5, type_B=type_name, s_no=1, status="READY")
        db.session.add(bundle)
        db.session.commit()
        return bundle

    def scan_payload(self, *bundles, key="scan-1"):
        return {"customer": self.worker_name, "request_id": key, "items": [{
            "item_id": str(bundle.id), "name_of_prduct": bundle.product, "qty": bundle.pieces,
            "kg": bundle.kg, "type": bundle.type_B,
        } for bundle in bundles]}

    def manual_payload(self, product="VIM", pieces=30, count=4, key="manual-1"):
        return {"customer": "RAM CITY", "request_id": key,
                "rows": [{"product": product, "pieces": pieces, "count": count, "type": "lump"}]}

    def return_payload(self, card_id, quantity, index=0, key="return-1"):
        from data_Process import get_jobcard_return_data
        item = get_jobcard_return_data(card_id)["items"][index]
        return {"jobcard_id": card_id, "name": self.worker_name, "request_id": key, "items": [{
            "item_id": item["item_id"], "name_of_product": item["name"], "type": item["colour"],
            "returned": quantity, "entry_method": "direct", "calculation_rows": [],
        }]}

    def edit(self, entity_type, entity_id, changes, token="edit-1", version=None):
        from edit_service import edit_context, save_entry
        context = edit_context(entity_type, entity_id)
        values = {field["name"]: field["value"] if field["value"] is not None else ""
                  for field in context["fields"]}
        values.update(deepcopy(changes))
        return save_entry(entity_type, entity_id, values, version or context["version"], token, "admin")

    def job_edit(self, card_id, changes=None, token="job-edit", version=None, username="admin"):
        from jobcard_edit import jobcard_edit_context, save_jobcard_edit
        context = jobcard_edit_context(card_id)
        values = {field["name"]: field["value"] for field in context["fields"]}
        values.update(edit_lines="1", edit_reason="Correcting an entry")
        for row in context["given"] + context["returns"]:
            for field in ("product", "type", "date", "quantity", "pieces", "count", "kg", "color"):
                if field in row:
                    values[f'line_{row["id"]}_{field}'] = row[field]
        for row in context.get('kept', []):
            for field in ('product', 'pieces', 'value', 'date', 'note'):
                values[f'kept_{row["id"]}_{field}'] = row[field]
            values[f'kept_{row["id"]}_type'] = row['bundle_type']
        values.update(changes or {})
        return save_jobcard_edit(card_id, values, version or context["version"], token, username)
