"""案例验收必须读实际求解数组，快速模式不能冒充正式验收。"""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from gear_contact import analyze_config, analyze_pair

PROJECT = next(p for p in Path(__file__).resolve().parents
               if (p / "pyproject.toml").is_file() and (p / "gear_contact").is_dir())
SPEC = importlib.util.spec_from_file_location("case_validation_runner", PROJECT / "examples/validate_cases.py")
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class CaseValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.folder = tempfile.TemporaryDirectory()
        cls.output = Path(cls.folder.name)
        cls.record = RUNNER.run(cls.output, quick=True)

    @classmethod
    def tearDownClass(cls):
        cls.folder.cleanup()

    def test_quick_reports_scope_and_preserves_recomputable_inputs(self):
        self.assertTrue(self.record["all_checks_passed"])
        self.assertIsNone(self.record["formal_acceptance_passed"])
        self.assertFalse(self.record["resolution"]["performed"])
        self.assertGreaterEqual(self.record["case_count"], 11)
        inputs = json.loads((self.output / "nondefault/input.json").read_text(encoding="utf-8"))
        result = analyze_config(inputs)
        with np.load(self.output / "nondefault/arrays.npz", allow_pickle=False) as saved:
            np.testing.assert_allclose(result.normal_approach_m, saved["normal_approach_m"], rtol=1e-12)
        self.assertEqual(inputs["pair"]["pinion"]["teeth"], 25)
        self.assertNotEqual(inputs["material_pinion"], inputs["material_wheel"])

    def test_tampered_force_is_detected_without_trusting_diagnostics(self):
        result = analyze_pair(RUNNER.standard_pair(), torque_n_m=80, phases=4, strips=5)
        self.assertTrue(RUNNER.check_result(result)["passed"])
        result.rotations[0].solution.forces_n[0] += 1.
        self.assertTrue(result.rotations[0].solution.diagnostics["converged"])
        check = RUNNER.check_result(result)
        self.assertFalse(check["passed"])
        self.assertFalse(check["checks"]["force_balance"])

    def test_cross_case_checks_cover_both_similarity_laws_and_mirror(self):
        checks = {item["check"]: item for item in self.record["cross_case_checks"]}
        self.assertEqual(set(checks), {"zero_load", "misalignment_mirror", "material_load_similarity", "geometry_similarity"})
        self.assertTrue(all(item["passed"] for item in checks.values()))
        for case in self.record["cases"]:
            self.assertTrue((self.output / case["case"] / "arrays.npz").is_file())
            self.assertTrue((self.output / case["case"] / "validation.json").is_file())


if __name__ == "__main__":
    unittest.main()
