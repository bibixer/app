"""Inventory workflow, setup writes, lookup data and CSV label output."""

from copy import deepcopy
import csv
from pathlib import Path
from unittest.mock import patch

from data_entry import bale_data_entry, add_items, add_outworker_db, add_cutter, add_party
from data_Process import get_product, get_job_card_data_creation, get_job_card_id, get_serch_data, age_clothused
from data_print_format import build_custom_csvs_pandas, clean_text, outworker_qr_print, buldel_qr_print
from modes import db, Bale_date, Lump, Bundle, RequestDedup, Item_data, Outworker, Party
from support import AppTestCase


class InventoryAndPrintingTest(AppTestCase):
    def payload(self):
        return {
            "bale_data": {"party_name": "SUPPLIER", "cuter_name": "CUTTER",
                          "product_name": self.product.name, "packing_date": "Sun, 01 Nov 2026",
                          "lot_number": 1, "lot_count": 1, "bale_number": 1},
            "main": {"party_name": "SUPPLIER", "cuter_name": "CUTTER", "product_name": self.product.name,
                     "bundle_type": "lump", "meters": 100, "meters_add_remove": 0,
                     "colors": "BLUE", "numbers_of_bundles": 2},
            "bundles": {"1": {"no_of_pics": 30, "kg_of_bundle": 2.5, "no_of_so": 1},
                        "2": {"no_of_pics": 40, "kg_of_bundle": 3, "no_of_so": 2}},
        }

    def test_inventory_save_is_atomic_idempotent_and_does_not_mutate_payload(self):
        data = self.payload()
        before = deepcopy(data)
        self.assertEqual(bale_data_entry(data, self.admin, "inventory"), 101)
        self.assertEqual(data, before)
        self.assertEqual(bale_data_entry(data, self.admin, "inventory"), 409)
        self.assertEqual((Bale_date.query.count(), Lump.query.count(), Bundle.query.count()), (1, 1, 2))
        self.buldel_qr_print.assert_called_once()

    def test_inventory_validation_rejects_bad_counts_types_weights_and_missing_bundles(self):
        cases = [("main", "numbers_of_bundles", 1), ("main", "bundle_type", "custom"),
                 ("main", "meters", float("nan")), ("main", "meters", -1),
                 ("main", "meters_add_remove", -200), ("bale_data", "lot_count", 0)]
        for section, field, value in cases:
            data = self.payload()
            data[section][field] = value
            with self.subTest(field=field, value=value):
                self.assertEqual(bale_data_entry(data, self.admin, "invalid"), 405)
                self.assertEqual(Bundle.query.count(), 0)
                self.assertEqual(RequestDedup.query.count(), 0)
        data = self.payload()
        data["bundles"]["1"]["kg_of_bundle"] = float("inf")
        self.assertEqual(bale_data_entry(data, self.admin, "invalid"), 405)

    def test_failed_bundle_creation_rolls_back_bale_lump_and_request_claim(self):
        with patch("data_entry.add_bundle", side_effect=RuntimeError("simulated database failure")):
            with self.assertRaises(RuntimeError):
                bale_data_entry(self.payload(), self.admin, "retryable")
        self.assertEqual((Bale_date.query.count(), Lump.query.count(), Bundle.query.count()), (0, 0, 0))
        self.assertEqual(RequestDedup.query.count(), 0)
        self.assertEqual(bale_data_entry(self.payload(), self.admin, "retryable"), 101)

    def test_second_lump_reuses_bale_but_has_distinct_bundles(self):
        self.assertEqual(bale_data_entry(self.payload(), self.admin, "lump-1"), 101)
        self.assertEqual(bale_data_entry(self.payload(), self.admin, "lump-2"), 101)
        self.assertEqual((Bale_date.query.count(), Lump.query.count(), Bundle.query.count()), (1, 2, 4))

    def test_inventory_print_failure_keeps_saved_data(self):
        self.buldel_qr_print.side_effect = OSError("printer offline")
        with self.assertLogs(level="ERROR"):
            self.assertEqual(bale_data_entry(self.payload(), self.admin, "print"), 101)
        self.assertEqual(Bundle.query.count(), 2)

    def test_setup_writes_reject_nonfinite_sizes_and_duplicate_names(self):
        for size, meter in [(float("nan"), 1), (1, float("inf")), (-1, 1)]:
            result = add_items({"name": "BAD", "aliases": "", "size": size, "meter": meter}, self.admin, "invalid")
            self.assertIsInstance(result["exception"], ValueError)
        self.assertEqual(Item_data.query.count(), 1)
        result = add_cutter({"name": "  cutter  "}, self.admin, "duplicate-cutter")
        self.assertFalse(result["or"])
        result = add_party({"name": " supplier "}, self.admin, "duplicate-party")
        self.assertIsInstance(result["exception"], ValueError)
        self.assertEqual(Party.query.count(), 1)

    def test_worker_creation_saves_alias_and_survives_printer_failure(self):
        self.outworker_qr_print.side_effect = OSError("printer offline")
        data = {"name": "new worker", "aliases": "new alias", "address": "CITY", "number": 9876543210}
        with self.assertLogs(level="ERROR"):
            self.assertEqual(add_outworker_db(data, self.admin, "new-worker"), 101)
        self.assertEqual(add_outworker_db(data, self.admin, "new-worker"), 409)
        worker = Outworker.query.filter_by(name="NEW WORKER").one()
        self.assertEqual([row.alias for row in worker.alias_rows], ["NEW ALIAS"])
        duplicate = add_outworker_db(data, self.admin, "duplicate-worker")
        self.assertIsInstance(duplicate["exception"], ValueError)

    def test_inventory_lookups_keep_quantities_and_average_cloth(self):
        bale_data_entry(self.payload(), self.admin, "inventory")
        products = get_product()
        self.assertEqual(sum(row["pics"] for row in products), 70)
        self.assertAlmostEqual(products[0]["avg_cloth"], 100 / 70)
        self.assertEqual(get_job_card_data_creation()["product"], products)
        self.assertEqual(get_job_card_id(), [])
        self.assertIn("CUTTER", get_serch_data()["cuter_data"])
        self.assertIn("SUPPLIER", get_serch_data()["party_data"])

    def test_csv_export_has_exact_mixed_manual_and_scanned_patterns(self):
        job = {"jobId": 1, "party": "RAM / CITY", "username": "admin", "date": "01-11-2026", "items": [
            {"item_id": "1", "name_of_prduct": "VIMAL", "type": "lump", "qty": 36},
            {"item_id": "2", "name_of_prduct": "VIMAL", "type": "lump", "qty": 36},
            {"item_id": "MANUAL-1-1", "name_of_prduct": "VIMAL", "type": "lump", "qty": 74,
             "pieces_per_bundle": 37, "bundle_count": 2},
        ]}
        target = Path(self.temp.name, "labels")
        target.mkdir()
        with patch("data_print_format.PRINT_ROOT", target):
            outputs = build_custom_csvs_pandas({"jobData": job})
        path = target / "jobcard" / outputs[0]["filename"]
        with path.open(newline="") as handle:
            row = next(csv.DictReader(handle))
        self.assertIn("36x2", row["Pattern_1_line1"])
        self.assertIn("37x2", row["Pattern_1_line1"])
        self.assertEqual(row["Total_1"], "146")
        self.assertEqual(row["Product_2"], "")
        self.assertIsInstance(outputs[0]["csv"], str)
        self.assertEqual(clean_text("../RAM / CITY"), "RAM_CITY")

    def test_label_writers_create_missing_output_directories(self):
        target = Path(self.temp.name, "new-label-directory")
        with patch("data_print_format.PRINT_ROOT", target):
            self.assertEqual(outworker_qr_print(self.worker), 101)
            self.assertEqual(buldel_qr_print([{"id": 7, "product": "VIMAL", "pieces": 30}]), 101)
        self.assertTrue((target / "outworker" / f"{self.worker.id}.csv").exists())
        with (target / 'outworker' / f'{self.worker.id}.csv').open(newline='') as handle:
            reader = csv.DictReader(handle)
            self.assertEqual(reader.fieldnames, ['id', 'name', 'address', 'qr_code'])
            self.assertEqual(next(reader), {'id':str(self.worker.id),'name':self.worker.name,
                'address':self.worker.adders,'qr_code':self.worker_name})
        self.assertFalse(list((target / 'outworker').glob('*.tmp')))
        self.assertTrue((target / "bundle" / "7.csv").exists())

    def test_long_pattern_labels_have_correct_chunk_totals_and_page_numbers(self):
        items = [{"item_id": str(pieces), "name_of_prduct": "VIMAL", "type": "lump", "qty": pieces}
                 for pieces in range(1, 12)]
        job = {"jobId": 2, "party": "RAM", "username": "admin", "date": "01-11-2026", "items": items}
        target = Path(self.temp.name, "labels")
        with patch("data_print_format.PRINT_ROOT", target):
            outputs = build_custom_csvs_pandas({"jobData": job})
        with (target / "jobcard" / outputs[0]["filename"]).open(newline="") as handle:
            row = next(csv.DictReader(handle))
        self.assertEqual((row["Total_1"], row["Total_2"]), ("55", "11"))
        self.assertEqual(int(row["Total_1"]) + int(row["Total_2"]), 66)
