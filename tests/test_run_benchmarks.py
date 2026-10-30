"""对标必须重算；参照响应、输入身份和整体通过状态相互独立。"""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from gear_contact.io import write_json

PROJECT = next(p for p in Path(__file__).resolve().parents
               if (p / "pyproject.toml").is_file() and (p / "gear_contact").is_dir())
SPEC = importlib.util.spec_from_file_location("cylindrical_benchmarks", PROJECT / "examples/run_benchmarks.py")
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class BenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.reference = self.root / "reference"
        self.reference.mkdir()
        payload = RUNNER.read_json(PROJECT / "examples/masta_reference/cases.json")
        self.case = copy.deepcopy(payload["cases"][0])
        # 测试只检查验证工具的约束，小网格不作为原始正式参照。
        self.case["config"].update(phases=4, strips=5)
        self.payload = {"schema_version": 1, "cases": [self.case]}
        self.save_reference()

    def tearDown(self):
        self.temporary.cleanup()

    def save_reference(self):
        write_json(self.reference / "cases.json", self.payload)
        write_json(self.reference / "manifest.json", {"files": {
            "cases.json": hashlib.sha256((self.reference / "cases.json").read_bytes()).hexdigest()}})

    def run_case(self, name="out", **kwargs):
        summary = RUNNER.run(self.root / name, reference_dir=self.reference, **kwargs)
        result = RUNNER.read_json(self.root / name / "case_inputs_and_results.json")[0]
        return summary, result

    def test_current_kernel_recomputes_and_models_do_not_claim_equivalence(self):
        summary, result = self.run_case()
        self.assertTrue(summary["reference_binding_verified"])
        self.assertTrue(summary["own_values_recomputed"])
        self.assertFalse(summary["reference_own_values_used"])
        self.assertTrue(summary["common_comparison_passed"])
        self.assertTrue(summary["same_inputs_as_reference"][self.case["case_id"]])
        self.assertFalse(summary["full_reference_problem_equivalent"][self.case["case_id"]])
        self.assertFalse(summary["comparison_passed"])
        self.assertFalse(summary["response_accuracy_verified"])
        self.assertTrue((self.root / "out" / self.case["case_id"] / "arrays.npz").is_file())
        self.assertTrue(result["project_summary"]["all_converged"])

    def test_frozen_project_values_never_enter_calculation(self):
        _, baseline = self.run_case("baseline")
        self.case["project_summary"] = {"normal_force_n": 1e30, "mean_normal_approach_m": 1e30}
        self.save_reference()
        _, after = self.run_case("injected")
        self.assertEqual(baseline["project_summary"], after["project_summary"])

    def test_changed_reference_only_changes_comparison_and_breaks_binding(self):
        _, baseline = self.run_case("baseline")
        self.case["reference_ltca_metrics"]["mean_normal_approach_m"] *= 3
        write_json(self.reference / "cases.json", self.payload)
        summary, after = self.run_case("tampered")
        self.assertEqual(baseline["project_summary"], after["project_summary"])
        self.assertFalse(summary["reference_binding_verified"])
        self.assertFalse(summary["common_comparison_passed"])

    def test_torque_override_really_changes_force_and_disallows_same_input_pass(self):
        _, before = self.run_case("baseline")
        changed = copy.deepcopy(self.payload)
        changed["cases"][0]["config"]["torque_n_m"] *= 2
        write_json(self.root / "changed.json", changed)
        summary, after = self.run_case("changed", cases_path=self.root / "changed.json")
        self.assertAlmostEqual(after["project_summary"]["normal_force_n"],
                               2 * before["project_summary"]["normal_force_n"], places=10)
        self.assertFalse(summary["same_inputs_as_reference"][self.case["case_id"]])
        self.assertFalse(summary["common_comparison_passed"])

    def test_material_change_cannot_pass_even_when_common_geometry_matches(self):
        _, before = self.run_case("baseline")
        changed = copy.deepcopy(self.payload)
        for name in ("material_pinion", "material_wheel"):
            changed["cases"][0]["config"][name]["youngs_modulus_pa"] *= 1.5
        write_json(self.root / "changed.json", changed)
        summary, after = self.run_case("changed", cases_path=self.root / "changed.json")
        self.assertEqual(summary["common_fields_matched"], summary["common_fields"])
        self.assertFalse(summary["same_inputs_as_reference"][self.case["case_id"]])
        self.assertFalse(summary["common_comparison_passed"])
        self.assertNotAlmostEqual(after["project_summary"]["mean_normal_approach_m"] /
                                  before["project_summary"]["mean_normal_approach_m"], 1.)

    def test_reference_directory_and_ancestors_cannot_be_outputs(self):
        original = (self.reference / "cases.json").read_bytes()
        for path in (self.reference, self.reference / "sub", self.root):
            with self.assertRaises(ValueError):
                RUNNER.run(path, reference_dir=self.reference)
        self.assertEqual(original, (self.reference / "cases.json").read_bytes())

    def test_zero_reference_and_unassessed_responses_are_explicit(self):
        row = RUNNER.comparison_row(self.case, "te_peak_to_peak_m", 1e-6, 0., "ltca")
        self.assertIsNone(row["relative_error"])
        self.assertIsNone(row["matched"])
        self.assertIsNone(row["relative_tolerance"])
        with self.assertRaises(ValueError):
            RUNNER.comparison_row(self.case, "max_pressure_pa", float("nan"), 1., "ltca")

    def test_custom_case_id_cannot_escape_output_or_overwrite_reference(self):
        self.case["case_id"] = "../reference"
        self.save_reference()
        original = (self.reference / "manifest.json").read_bytes()
        with self.assertRaises(ValueError):
            self.run_case()
        self.assertEqual(original, (self.reference / "manifest.json").read_bytes())
        self.assertFalse((self.root / "out").exists())


if __name__ == "__main__":
    unittest.main()
