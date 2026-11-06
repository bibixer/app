"""Manual job cards accept only the bundle types offered by inventory setup."""

import unittest

from bundle_types import BUNDLE_TYPE_CHOICES, BUNDLE_TYPE_VALUES
from data_entry import validate_manual_jobcard
from form import Lump_data


class ManualBundleTypeTest(unittest.TestCase):
    def payload(self, type_value):
        return {
            "customer": "Vimal Master",
            "rows": [{"product": "VIMAL 1 2MTR", "pieces": 30, "count": 4, "type": type_value}],
        }

    def test_inventory_form_and_manual_validation_share_choices(self):
        self.assertEqual(tuple(Lump_data.bundle_type.kwargs["choices"]), BUNDLE_TYPE_CHOICES)
        for type_value in BUNDLE_TYPE_VALUES:
            with self.subTest(type_value=type_value):
                self.assertTrue(validate_manual_jobcard(self.payload(type_value)))

    def test_unlisted_type_is_rejected(self):
        for type_value in ("bundle", "Lump", "custom", "", [], None):
            with self.subTest(type_value=type_value):
                self.assertFalse(validate_manual_jobcard(self.payload(type_value)))


if __name__ == "__main__":
    unittest.main()
