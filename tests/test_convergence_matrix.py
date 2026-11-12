"""多工况离散矩阵的门禁、失败留存和原数组复算验证。"""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from gear_contact import analyze_config

PROJECT = next(p for p in Path(__file__).resolve().parents
               if (p / "pyproject.toml").is_file() and (p / "gear_contact").is_dir())
SPEC = importlib.util.spec_from_file_location("convergence_matrix_runner", PROJECT / "examples/check_convergence_matrix.py")
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class ConvergenceMatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.output = Path(cls.temporary.name)
        cls.report = RUNNER.run(cls.output, cases=["combined_spur", "iso_love_18_77"], quick=True)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_quick_never_claims_formal_convergence_and_both_axes_exist(self):
        self.assertTrue(self.report["completed"])
        self.assertTrue(self.report["numerical_checks_passed"])
        self.assertIsNone(self.report["formal_convergence_passed"])
        self.assertEqual(RUNNER.exit_code(self.report, require_convergence=True), 2)
        for case in self.report["cases"]:
            self.assertIsNone(case["formal_convergence_passed"])
            for axis in case["axes"].values():
                self.assertIsNone(axis["formal_convergence_passed"])
                self.assertEqual(len(axis["levels"]), 3)
                self.assertEqual(len(axis["comparisons"]), 2)
                for row in axis["levels"]:
                    for name in ("requested_input.json", "input.json", "arrays.npz", "validation.json", "diagnostics.json"):
                        self.assertTrue((self.output / row["path"] / name).is_file())
        false_green = dict(self.report, formal_convergence_passed=True)
        self.assertEqual(RUNNER.exit_code(false_green, require_convergence=True), 2)

    def test_saved_real_arrays_recompute_inputs_and_separate_endpoint_peak(self):
        for case in self.report["cases"]:
            row = case["axes"]["space"]["levels"][1]
            folder = self.output / row["path"]
            config = json.loads((folder / "input.json").read_text(encoding="utf-8"))
            result = analyze_config(config)
            self.assertTrue(RUNNER.check_result(result)["passed"])
            with np.load(folder / "arrays.npz", allow_pickle=False) as arrays:
                np.testing.assert_allclose(arrays["normal_approach_m"], result.normal_approach_m, rtol=1e-12)
                np.testing.assert_allclose(arrays["forces_n"],
                    np.concatenate([r.solution.forces_n for r in result.rotations]), rtol=1e-12)
                actual = RUNNER.metrics_from_arrays(arrays, require_endpoints=case["endpoint_pressure_required"])
                self.assertEqual(actual, row["metrics"])
                self.assertAlmostEqual(actual["max_center_pressure_pa"],
                    max(float(r.pressure_pa.max()) for r in result.rotations))
                if case["endpoint_pressure_required"]:
                    self.assertAlmostEqual(actual["max_endpoint_pressure_pa"],
                        max(float(r.endpoint_pressure["pressure_pa"].max()) for r in result.rotations))
                else:
                    self.assertIsNone(actual["max_endpoint_pressure_pa"])

    def test_missing_endpoint_data_is_not_silently_zero(self):
        row = self.report["cases"][1]["axes"]["space"]["levels"][1]
        with np.load(self.output / row["path"] / "arrays.npz", allow_pickle=False) as original:
            arrays = {name: original[name].copy() for name in original.files}
        arrays.pop("endpoint_pressure_pa")
        with self.assertRaisesRegex(ValueError, "端点"):
            RUNNER.metrics_from_arrays(arrays, require_endpoints=True)
        a, b = dict(row["metrics"]), dict(row["metrics"])
        b["max_endpoint_pressure_pa"] = None
        comparison = RUNNER.compare_metrics(a, b)
        self.assertFalse(comparison["passed"])
        self.assertFalse(comparison["metrics"]["max_endpoint_pressure_pa"]["passed"])

    def test_near_zero_uses_absolute_plus_relative_tolerance(self):
        metric = {name: 0. for name in RUNNER.DEFAULT_ABSOLUTE_TOLERANCES}
        metric["max_endpoint_pressure_pa"] = None
        close = dict(metric, te_peak_to_peak_m=5e-11)
        far = dict(metric, te_peak_to_peak_m=5e-9)
        self.assertTrue(RUNNER.compare_metrics(metric, close)["passed"])
        self.assertFalse(RUNNER.compare_metrics(metric, far)["passed"])
        original = RUNNER.compare_metrics(metric, metric)["metrics"]["te_peak_to_peak_m"]
        self.assertIsNone(original["relative_difference"])
        self.assertEqual(original["allowed_difference"], 1e-10)

    def test_invalid_levels_and_nonfinite_tolerances_reject_before_output(self):
        invalid = ({"space_levels": [11, 21]}, {"phase_levels": [16, 16, 64]},
                   {"space_levels": [11, 41, 21]}, {"phase_levels": [2, 4, float("inf")]},
                   {"space_levels": [True, 3, 5]}, {"fixed_phases": 2.5},
                   {"relative_tolerance": float("nan")}, {"relative_tolerance": float("inf")},
                   {"absolute_tolerances": {"max_center_pressure_pa": -1}},
                   {"absolute_tolerances": {"max_center_pressure_pa": float("inf")}},
                   {"cases": []}, {"cases": ["combined_spur", "combined_spur"]})
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "must_not_exist"
            for options in invalid:
                with self.subTest(options=options), self.assertRaises(ValueError):
                    RUNNER.run(output, **options)
            self.assertFalse(output.exists())

    def test_failure_keeps_requested_input_and_continues_other_cases(self):
        calls = []

        def fail_first(config):
            calls.append(deepcopy(config))
            if len(calls) == 1:
                raise RuntimeError("测试注入的单级求解失败")
            return analyze_config(config)

        with tempfile.TemporaryDirectory() as folder, patch.object(RUNNER, "analyze_config", side_effect=fail_first):
            report = RUNNER.run(folder, cases=["low_load", "edge_misalignment"], quick=True)
            failed = report["cases"][0]["axes"]["space"]["levels"][0]
            self.assertFalse(report["numerical_checks_passed"])
            self.assertTrue(report["completed"])
            self.assertEqual(RUNNER.exit_code(report, require_convergence=True), 1)
            self.assertTrue((Path(folder) / failed["path"] / "failure.json").is_file())
            saved = json.loads((Path(folder) / failed["path"] / "requested_input.json").read_text(encoding="utf-8"))
            self.assertEqual(saved, calls[0])
            self.assertTrue(report["cases"][1]["numerical_checks_passed"])
            self.assertTrue(all(row["edge_loading_observed"]
                for axis in report["cases"][1]["axes"].values() for row in axis["levels"]))

    def test_formal_nonconvergence_is_false_and_require_convergence_fails(self):
        strict = {name: 1e-30 for name in RUNNER.DEFAULT_ABSOLUTE_TOLERANCES}
        with tempfile.TemporaryDirectory() as folder:
            report = RUNNER.run(folder, cases=["combined_spur"], space_levels=[3, 5, 7],
                phase_levels=[2, 4, 8], fixed_phases=4, fixed_strips=5,
                relative_tolerance=1e-12, absolute_tolerances=strict)
            self.assertTrue(report["numerical_checks_passed"])
            self.assertFalse(report["formal_convergence_passed"])
            self.assertEqual(RUNNER.exit_code(report, require_convergence=True), 2)
            saved = json.loads((Path(folder) / "convergence_matrix.json").read_text(encoding="utf-8"))
            self.assertFalse(saved["formal_convergence_passed"])

    def test_real_cli_quick_require_convergence_returns_nonzero(self):
        with tempfile.TemporaryDirectory() as folder:
            process = subprocess.run([sys.executable, "-B", str(PROJECT / "examples/check_convergence_matrix.py"),
                "--output", folder, "--cases", "combined_spur", "--quick", "--require-convergence"],
                cwd=PROJECT, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
            self.assertEqual(process.returncode, 2, process.stdout + process.stderr)
            self.assertIsNone(json.loads((Path(folder) / "convergence_matrix.json").read_text(encoding="utf-8"))[
                "formal_convergence_passed"])


if __name__ == "__main__":
    unittest.main()
