import copy
import unittest
from danger_zones.field_inventory import profile_field, inventory, occurrence_year, timestamp_format, read_catalog


class FieldInventoryTests(unittest.TestCase):
    def test_profiles_missing_blank_unknown_zero_and_years_without_rewriting(self):
        rows = [{"value": None}, {"value": ""}, {}, {"value": 0}, {"value": "99"}]
        before = copy.deepcopy(rows)
        result = profile_field(rows, "value", [2024, 2024, 2025, 2025, 2025], True)
        self.assertEqual((result["present"], result["null"], result["blank"], result["missingColumn"], result["populated"]), (4, 1, 1, 1, 2))
        self.assertEqual(result["byYear"]["2025"]["populated"], 2)
        self.assertIn({"value": "99", "count": 1}, result["valueCounts"])
        self.assertIn({"value": 0, "count": 1}, result["valueCounts"])
        self.assertEqual(rows, before)

    def test_sensitive_text_values_are_not_included_by_default(self):
        result = profile_field([{"case": "secret-case-number"}], "case", [2025])
        self.assertNotIn("valueCounts", result)
        self.assertNotIn("secret-case-number", str(result))

    def test_catalog_drift_is_a_visible_error(self):
        catalog = {"version": 1, "concepts": {}, "tables": {"test": {"fields": {}}}}
        tables = {"test": {"rows": [{"NEW": 1}], "years": [2025]}}
        with self.assertRaisesRegex(ValueError, "Catalog drift"):
            inventory(catalog, tables)


    def test_year_inventory_accepts_mixed_source_formats_without_inventing_time(self):
        for value in ["2020-01-17 07:30:00 PM", "1/17/2020 7:30:00 PM", "2020-01-17", "1/17/2020"]:
            self.assertEqual(occurrence_year(value), 2020)
        self.assertEqual(timestamp_format("2020-01-17 07:30:00 PM"), "iso-date-with-12-hour-time")
        self.assertEqual(timestamp_format("1/17/2020"), "us-date-only")
        self.assertEqual(occurrence_year("invalid"), "unparsed")


    def test_committed_catalog_and_captures_validate_without_private_inputs(self):
        catalog = read_catalog()
        self.assertEqual({table["source"] for table in catalog["tables"].values()},
                         {"udot-crashes", "utah-crash-portal", "provo-police-incidents"})
        self.assertIn("person.injury_severity", catalog["concepts"])
        self.assertIn("injury.crash_severity", catalog["concepts"])
