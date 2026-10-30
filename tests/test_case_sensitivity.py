"""敏感性分析必须保留原案例输入，并真实重算附加扰动。"""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from gear_contact import analyze_config, modification_from_config

PROJECT = next(p for p in Path(__file__).resolve().parents
               if (p/"pyproject.toml").is_file() and (p/"gear_contact").is_dir())
SPEC = importlib.util.spec_from_file_location("case_sensitivity", PROJECT/"examples/case_sensitivity.py")
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class CaseSensitivityTests(unittest.TestCase):
    def case(self):
        case = json.loads((PROJECT/"examples/helical_18_77_case.json").read_text(encoding="utf-8"))
        case["analysis"].update(phases=4, strips=5, misalignment_m=.2e-6)
        return case

    def test_original_inputs_and_boundary_are_preserved_and_added_surface_is_exact(self):
        case = self.case()
        before = deepcopy(case)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            summary = RUNNER.run_case_sensitivity(case, output)
            self.assertEqual(case, before)
            configs = [json.loads((output/item["config_file"]).read_text(encoding="utf-8"))
                       for item in summary["scenarios"]]
            original, shifted, crowned = configs
            for key in ("pair", "material_pinion", "material_wheel", "torque_n_m", "iso_settings",
                        "extended_contact_settings", "modification_wheel", "phase_offset"):
                self.assertEqual(original[key], shifted[key])
                self.assertEqual(original[key], crowned[key])
            self.assertEqual(original["modification_pinion"], shifted["modification_pinion"])
            self.assertEqual(crowned["modification_pinion"]["components"][0], original["modification_pinion"])
            self.assertAlmostEqual(shifted["misalignment_m"]-original["misalignment_m"], 1e-6)
            self.assertEqual(crowned["misalignment_m"], shifted["misalignment_m"])
            lead = np.array([0., .25, .5, .75, 1.])
            base_surface = modification_from_config(original["modification_pinion"])
            added_surface = modification_from_config(crowned["modification_pinion"])
            np.testing.assert_allclose(added_surface.evaluate(np.full(5, .5), lead)
                -base_surface.evaluate(np.full(5, .5), lead), .5e-6*(2*lead-1)**2, rtol=1e-13, atol=1e-20)
            self.assertFalse(summary["strength_evaluated"])
            self.assertFalse(summary["masta_comparison_performed"])

    def test_saved_config_recomputes_endpoint_metric_and_perturbation_changes_response(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            summary = RUNNER.run_case_sensitivity(self.case(), output)
            self.assertEqual(summary["scenario_count"], 3)
            self.assertEqual(summary["display_cycles"], 3)
            first, shifted, crowned = summary["scenarios"]
            self.assertNotEqual(first["te_peak_to_peak_m"], shifted["te_peak_to_peak_m"])
            self.assertNotEqual(shifted["max_endpoint_pressure_pa"], crowned["max_endpoint_pressure_pa"])
            for row in summary["scenarios"]:
                config = json.loads((output/row["config_file"]).read_text(encoding="utf-8"))
                result = analyze_config(config)
                self.assertAlmostEqual(row["te_peak_to_peak_m"], float(np.ptp(result.normal_approach_m)), places=16)
                endpoint_maximum = max(float(np.max(r.endpoint_pressure["pressure_pa"])) for r in result.rotations)
                self.assertAlmostEqual(row["max_endpoint_pressure_pa"], endpoint_maximum, places=4)
                self.assertTrue((output/row["ltca_directory"]/"arrays.npz").is_file())
                self.assertAlmostEqual(row["normal_force_n"], first["normal_force_n"], places=12)

    def test_missing_endpoint_model_is_rejected_before_writing_results(self):
        case = self.case()
        case["analysis"].pop("extended_contact_settings")
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)/"results"
            with self.assertRaises(ValueError):
                RUNNER.run_case_sensitivity(case, output)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
