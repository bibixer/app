"""Aliases, search, edit audit trails and propagation of related records."""

from data_entry import add_jobcard, add_manual_jobcard, in_move_entery, add_items, add_outworker_db
from edit_service import edit_context, audit_logs, search_entries, save_entry
from item_aliases import (normalize_name, parse_aliases, resolve_item_name, item_name_mapping,
                          item_name_suggestions, validate_names)
from master_aliases import (resolve_master_name, master_name_mapping, master_name_options,
                            validate_master_aliases)
from modes import db, Item_data, ItemAlias, Outworker, OutworkerAlias, Jobcard, Jobmovement, Bundle, Lump, Bale_date, EditLog
from support import AppTestCase


class AliasAndEditTest(AppTestCase):
    def test_product_aliases_normalize_without_creating_other_products(self):
        self.assertEqual(normalize_name("  vimal   1 2mtr "), self.product.name)
        self.assertEqual(parse_aliases("vim, VIM\n other alias"), ["VIM", "OTHER ALIAS"])
        self.assertEqual(resolve_item_name("vim"), self.product.name)
        self.assertEqual(item_name_mapping()["VIM"], self.product.name)
        self.assertIn("VIM", item_name_suggestions())
        self.assertIsNone(resolve_item_name("20"))
        self.assertEqual(Item_data.query.count(), 1)

    def test_alias_conflicts_are_checked_in_both_directions(self):
        with self.assertRaises(ValueError):
            validate_names("OTHER", [self.product.name])
        with self.assertRaises(ValueError):
            validate_names("VIM", [])
        with self.assertRaises(ValueError):
            validate_names("OTHER", ["OTHER"])
        for aliases in (["1"], [self.worker_name], ["RAM"]):
            with self.assertRaises(ValueError):
                validate_master_aliases("NEW MASTER", aliases)
        bad = add_items({"name": "VIM", "aliases": "", "size": 1, "meter": 1}, self.admin, "conflict")
        self.assertIsInstance(bad["exception"], ValueError)
        self.assertEqual(Item_data.query.count(), 1)

    def test_master_id_takes_priority_and_ambiguous_names_are_not_guessed(self):
        other = Outworker(name="RAM", adders="OTHER CITY", number=2, enter_user="admin")
        db.session.add(other)
        db.session.commit()
        self.assertIsNone(resolve_master_name("RAM"))
        self.assertEqual(resolve_master_name(str(self.worker.id)), self.worker_name)
        self.assertEqual(resolve_master_name("ram city"), self.worker_name)
        self.assertEqual(master_name_mapping()[str(self.worker.id)], self.worker_name)
        self.assertIn(str(self.worker.id), [row["value"] for row in master_name_options()])
        self.assertNotIn("RAM", [row["value"] for row in master_name_options()])

    def test_legacy_names_with_extra_spaces_can_still_be_resolved(self):
        self.product.name = "VIMAL   1 2MTR"
        db.session.commit()
        self.assertEqual(resolve_item_name(self.product.name), self.product.name)

    def test_product_rename_updates_stock_jobs_and_movements_with_logs(self):
        bundle = self.bundle()
        add_jobcard(self.scan_payload(bundle), self.admin, "issue")
        status, fields = self.edit("product", self.product.id, {"name": "NEW PRODUCT", "aliases": "VIM, NEW ALIAS"})
        self.assertEqual(status, "saved")
        self.assertIn("name", fields)
        self.assertEqual(Bundle.query.one().product, "NEW PRODUCT")
        self.assertEqual(Lump.query.one().product, "NEW PRODUCT")
        self.assertEqual(Bale_date.query.one().product, "NEW PRODUCT")
        self.assertEqual(Jobmovement.query.one().product_name, "NEW PRODUCT")
        self.assertEqual(Jobcard.query.one().product_list[0]["name_of_prduct"], "NEW PRODUCT")
        self.assertEqual(resolve_item_name("new alias"), "NEW PRODUCT")
        self.assertGreaterEqual(len(audit_logs()), 5)

    def test_outworker_rename_keeps_job_and_return_links(self):
        card_id = add_manual_jobcard(self.manual_payload(), self.admin, "manual")["jobData"]["jobId"]
        in_move_entery(self.return_payload(card_id, 30), self.admin, "return")
        self.assertEqual(self.edit("outworker", self.worker.id, {"name": "NEW WORKER", "adders": "NEW CITY"})[0], "saved")
        card = db.session.get(Jobcard, card_id)
        self.assertEqual(card.given_to, self.worker_name)
        self.assertTrue(all(row.name_of_mater == self.worker_name for row in Jobmovement.query.all()))
        self.assertEqual(resolve_master_name("RAM CITY"), self.worker_name)

    def test_edit_conflicts_and_repeat_submission_do_not_create_extra_logs(self):
        version = edit_context("product", self.product.id)["version"]
        self.assertEqual(self.edit("product", self.product.id, {"size": "3"}, version=version)[0], "saved")
        self.assertEqual(self.edit("product", self.product.id, {"size": "4"}, token="stale", version=version)[0], "conflict")
        self.assertEqual(self.edit("product", self.product.id, {"size": "4"})[0], "conflict")
        self.assertEqual(self.edit("product", self.product.id, {"size": "3"})[0], "duplicate")
        self.assertEqual(Item_data.query.one().size, 3)
        self.assertEqual(EditLog.query.filter_by(entity_type="product").count(), 1)

    def test_edit_rejects_nonfinite_numbers_and_invalid_bundle_type(self):
        for value in ("nan", "inf", "-inf"):
            with self.subTest(value=value):
                self.assertEqual(self.edit("product", self.product.id, {"meters": value}, token=value)[0], "invalid")
        bundle = self.bundle()
        self.assertEqual(self.edit("bundle", bundle.id, {"type_B": "not-a-type"}, token="type")[0], "invalid")

    def test_job_edit_cannot_exceed_issued_quantity_or_choose_unknown_worker(self):
        card_id = add_manual_jobcard(self.manual_payload(), self.admin, "manual")["jobData"]["jobId"]
        in_move_entery(self.return_payload(card_id, 30), self.admin, "return")
        movement = Jobmovement.query.filter_by(flow_type="IN").one()
        for change in ({f"line_{movement.id}_quantity": "121"}, {"given_to": "OTHER"}):
            with self.subTest(change=change):
                self.assertEqual(self.job_edit(card_id, change, token=str(change))[0], "invalid")
        self.assertEqual(db.session.get(Jobmovement, movement.id).inflow, 30)

    def test_manual_movement_edit_updates_original_job_quantities(self):
        card_id = add_manual_jobcard(self.manual_payload(), self.admin, "manual")["jobData"]["jobId"]
        movement = Jobmovement.query.filter_by(flow_type="OUT").one()
        self.assertEqual(self.job_edit(card_id, {f"line_{movement.id}_pieces": "25"})[0], "saved")
        item = db.session.get(Jobcard, card_id).product_list[0]
        self.assertEqual(item["qty"], 100)
        self.assertEqual(item["pieces_per_bundle"] * item["bundle_count"], 100)

    def test_job_transfer_moves_existing_returns_with_the_job(self):
        card_id = add_manual_jobcard(self.manual_payload(), self.admin, "manual")["jobData"]["jobId"]
        in_move_entery(self.return_payload(card_id, 30), self.admin, "return")
        other = Outworker(name="OTHER", adders="CITY", number=2, enter_user="admin")
        db.session.add(other)
        db.session.commit()
        full_name = f"{other.id}***OTHER--CITY/-"
        self.assertEqual(self.edit("jobcard", card_id, {"given_to": full_name})[0], "saved")
        self.assertEqual({row.name_of_mater for row in Jobmovement.query.all()}, {full_name})

    def test_issued_bundle_cannot_be_made_ready_for_a_second_job(self):
        bundle = self.bundle()
        add_jobcard(self.scan_payload(bundle), self.admin, "issue")
        self.assertEqual(self.edit("bundle", bundle.id, {"status": "READY"})[0], "invalid")
        self.assertEqual(db.session.get(Bundle, bundle.id).status, "GIVEN")

    def test_search_supports_aliases_ids_literal_wildcards_and_bounded_paging(self):
        self.assertEqual(search_entries("product", "vim")["total"], 1)
        self.assertEqual(search_entries("outworker", "ram city")["total"], 1)
        self.assertEqual(search_entries("product", "%")["total"], 0)
        self.assertEqual(search_entries("product", "_")["total"], 0)
        self.assertIsNone(search_entries("not-an-entity"))
        result = search_entries("product", page="bad", page_size=0)
        self.assertEqual(result["page"], 1)
        self.assertEqual(len(result["items"]), 1)

    def test_empty_edit_token_is_rejected_and_noop_is_not_logged(self):
        context = edit_context("product", self.product.id)
        values = {field["name"]: field["value"] for field in context["fields"]}
        self.assertEqual(save_entry("product", self.product.id, values, context["version"], "", "admin")[0], "invalid")
        self.assertEqual(self.edit("product", self.product.id, {})[0], "saved")
        self.assertEqual(EditLog.query.count(), 0)

    def test_lump_and_bale_corrections_sync_through_to_issued_jobs(self):
        other = Item_data(name="OTHER PRODUCT", size=1, meters=1, enter_user="admin")
        db.session.add(other)
        db.session.commit()
        for entity in ("lump", "bale"):
            bundle = self.bundle()
            card_id = add_jobcard(self.scan_payload(bundle), self.admin, f"issue-{entity}")["jobData"]["jobId"]
            lump = db.session.get(Lump, bundle.lump_id)
            entity_id = lump.id if entity == "lump" else lump.bale_id
            self.assertEqual(self.edit(entity, entity_id, {"product": other.name}, token=entity)[0], "saved")
            self.assertEqual(db.session.get(Bundle, bundle.id).product, other.name)
            self.assertEqual(Jobmovement.query.filter_by(jobcard=str(card_id)).one().product_name, other.name)
            self.assertEqual(db.session.get(Jobcard, card_id).product_list[0]["name_of_prduct"], other.name)

    def test_parent_correction_that_orphans_returns_rolls_back_all_cascades(self):
        bundle = self.bundle()
        card_id = add_jobcard(self.scan_payload(bundle), self.admin, "issue")["jobData"]["jobId"]
        in_move_entery(self.return_payload(card_id, 20), self.admin, "return")
        other = Item_data(name="OTHER PRODUCT", size=1, meters=1, enter_user="admin")
        db.session.add(other)
        db.session.commit()
        self.assertEqual(self.edit("lump", bundle.lump_id, {"product": other.name})[0], "invalid")
        self.assertEqual(db.session.get(Bundle, bundle.id).product, self.product.name)
        self.assertEqual(db.session.get(Lump, bundle.lump_id).product, self.product.name)
        self.assertEqual(EditLog.query.count(), 0)
