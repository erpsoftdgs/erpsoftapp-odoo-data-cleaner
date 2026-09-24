import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd

from engine.odoo_data_engine import (
    CUSTOMER_SCHEMA,
    VENDOR_SCHEMA,
    infer_is_company,
    process_file,
    rule_based_clean,
)


class InferIsCompanyTests(unittest.TestCase):
    def test_only_ltd_or_plc_markers_infer_company(self):
        self.assertTrue(infer_is_company("Acme Ltd"))
        self.assertTrue(infer_is_company("ACME LTD."))
        self.assertTrue(infer_is_company("Example PLC"))
        self.assertTrue(infer_is_company("Example Plc Trading"))
        self.assertTrue(infer_is_company("Example Co."))
        self.assertTrue(infer_is_company("Example Co"))
        self.assertTrue(infer_is_company("Example IT"))
        self.assertTrue(infer_is_company("Example LP"))
    def test_unmarked_names_default_to_not_company(self):
        for name in ("Ada Lovelace", "Adaora", "Marketing Services", "Walk-in Customer", ""):
            with self.subTest(name=name):
                self.assertFalse(infer_is_company(name))
        self.assertFalse(infer_is_company(None))

    def test_absent_source_field_is_inferred_from_name(self):
        raw = pd.DataFrame({
            "Name": ["Ada Lovelace", "Acme Ltd", "Example PLC", "Marketing Services"],
        })

        cleaned = rule_based_clean(raw, "customer")

        self.assertEqual(
            cleaned["Is a Company"].tolist(),
            [False, True, True, False],
        )

    def test_existing_source_field_is_respected_and_blanks_default_false(self):
        raw = pd.DataFrame({
            "Name": ["Acme Ltd", "Ada Lovelace", "Unknown"],
            "Is a Company": ["False", "Yes", None],
        })

        cleaned = rule_based_clean(raw, "customer")

        self.assertEqual(cleaned["Is a Company"].tolist(), [False, True, False])

    def test_company_field_is_customer_only(self):
        self.assertIs(CUSTOMER_SCHEMA["Is a Company"]["default"], False)
        self.assertNotIn("Is a Company", VENDOR_SCHEMA)

    def test_vendor_cleaning_does_not_add_company_field(self):
        raw = pd.DataFrame({"Vendor Name": ["Acme Ltd", "Ada Lovelace"]})

        cleaned = rule_based_clean(raw, "vendor")

        self.assertNotIn("Is a Company", cleaned.columns)

    def test_vendor_pipeline_export_omits_company_field(self):
        with TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "vendors.csv"
            output = Path(temp_dir) / "odoo_ready.xlsx"
            source.write_text("Vendor Name\nAcme Ltd\nAda Lovelace\n", encoding="utf-8")

            with (
                patch("engine.odoo_data_engine.anthropic.Anthropic", return_value=None),
                patch("engine.odoo_data_engine.ai_normalise_structure", side_effect=lambda df, *_: df),
                patch(
                    "engine.odoo_data_engine.ai_map_columns",
                    return_value=({"Vendor Name": "Vendor Name"}, {"needs_address_split": [], "needs_field_clean": []}),
                ),
            ):
                result = process_file(source, "vendor", output_path=output)

            self.assertEqual(result["status"], "success")
            exported = pd.read_excel(output, sheet_name="Cleaned")
            self.assertNotIn("Is a Company", exported.columns)

    def test_pipeline_stops_without_workbook_when_mapping_is_empty(self):
        with TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "customers.csv"
            output = Path(temp_dir) / "odoo_ready.xlsx"
            source.write_text("Client Label\nAcme Ltd\n", encoding="utf-8")

            with (
                patch("engine.odoo_data_engine.anthropic.Anthropic", return_value=None),
                patch("engine.odoo_data_engine.ai_normalise_structure", side_effect=lambda df, *_: df),
                patch(
                    "engine.odoo_data_engine.ai_map_columns",
                    return_value=({}, {"needs_address_split": [], "needs_field_clean": []}),
                ),
            ):
                result = process_file(source, "customer", output_path=output)

            self.assertEqual(result["status"], "error")
            self.assertIn("did not map any source column", result["message"])
            self.assertFalse(output.exists())

    def test_pipeline_preserves_other_data_when_name_is_unmapped(self):
        with TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "customers.csv"
            output = Path(temp_dir) / "odoo_ready.xlsx"
            source.write_text("Phone\n08012345678\n", encoding="utf-8")

            with (
                patch("engine.odoo_data_engine.anthropic.Anthropic", return_value=None),
                patch("engine.odoo_data_engine.ai_normalise_structure", side_effect=lambda df, *_: df),
                patch(
                    "engine.odoo_data_engine.ai_map_columns",
                    return_value=({"Phone": "Phone"}, {"needs_address_split": [], "needs_field_clean": []}),
                ),
            ):
                result = process_file(source, "customer", output_path=output)

            self.assertEqual(result["status"], "partial")
            self.assertEqual(result["stats"]["missing_mandatory_field"], 1)
            self.assertTrue(output.exists())
            exported = pd.read_excel(output, sheet_name="Data", dtype={"Phone": str})
            self.assertEqual(exported.loc[0, "Phone"], "08012345678")
            errors = pd.read_excel(output, sheet_name="Errors")
            self.assertEqual(errors.loc[0, "_reason_code"], "missing_mandatory_field")

    def test_pipeline_stops_when_all_mapped_source_values_are_empty(self):
        with TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "customers.csv"
            output = Path(temp_dir) / "odoo_ready.xlsx"
            # NBSP survives CSV parsing but is stripped by the engine input cleanup.\n            source.write_text("Name,Phone\n\u00a0,\u00a0\n", encoding="utf-8")

            with (
                patch("engine.odoo_data_engine.anthropic.Anthropic", return_value=None),
                patch("engine.odoo_data_engine.ai_normalise_structure", side_effect=lambda df, *_: df),
                patch(
                    "engine.odoo_data_engine.ai_map_columns",
                    return_value=({"Name": "Name", "Phone": "Phone"}, {"needs_address_split": [], "needs_field_clean": []}),
                ),
            ):
                result = process_file(source, "customer", output_path=output)

            self.assertEqual(result["status"], "error")
            self.assertIn("source values mapped to Odoo fields are empty", result["message"])
            self.assertFalse(output.exists())

    def test_pipeline_exports_inferred_company_flags(self):
        with TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "customers.csv"
            output = Path(temp_dir) / "odoo_ready.xlsx"
            source.write_text(
                "Name\nAda Lovelace\nAcme Ltd\nExample PLC\nMarketing Services\n",
                encoding="utf-8",
            )

            with (
                patch("engine.odoo_data_engine.anthropic.Anthropic", return_value=None),
                patch("engine.odoo_data_engine.ai_normalise_structure", side_effect=lambda df, *_: df),
                patch(
                    "engine.odoo_data_engine.ai_map_columns",
                    return_value=({"Name": "Name"}, {"needs_address_split": [], "needs_field_clean": []}),
                ),
            ):
                result = process_file(source, "customer", output_path=output)

            self.assertEqual(result["status"], "success")
            self.assertEqual(result["stats"]["clean"], 4)
            exported = pd.read_excel(output, sheet_name="Cleaned")
            self.assertEqual(
                exported["Is a Company"].tolist(),
                [False, True, True, False],
            )


if __name__ == "__main__":
    unittest.main()
