"""验证响应回归会真实求解、拒绝无效契约，并能捕获被故意改变的响应。"""
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

PROJECT = next(p for p in Path(__file__).resolve().parents
               if (p / "pyproject.toml").is_file() and (p / "gear_contact").is_dir())
SPEC = importlib.util.spec_from_file_location("response_regression_tests", PROJECT / "examples/response_regression.py")
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class ResponseRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.shipped = json.loads((PROJECT / "examples/response_baseline.json").read_text(encoding="utf-8"))

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.path = self.root / "baseline.json"
        self.baseline = copy.deepcopy(self.shipped)
        case = copy.deepcopy(self.baseline["cases"][-1])
        # 仅为验证工具的低分辨率夹具；不替换已发布的原提交正式基线。
        case["case_id"] = "small_coupled_fixture"
        case["config"].update(phases=4, strips=5)
        case["config_sha256"] = RUNNER.canonical_sha256(case["config"])
        self.result = RUNNER.analyze_config(copy.deepcopy(case["config"]))
        case["response"] = RUNNER.response_values(self.result)
        self.baseline["cases"] = [case]
        self.case = case
        self.save()

    def tearDown(self):
        self.temporary.cleanup()

    def save(self):
        self.path.write_text(json.dumps(self.baseline, ensure_ascii=False, allow_nan=False), encoding="utf-8")

    def run_case(self, name="out"):
        return RUNNER.run(self.root / name, baseline_path=self.path)

    def test_shipped_baseline_has_original_identity_and_both_model_families(self):
        RUNNER.validate_baseline(self.shipped)
        self.assertEqual(self.shipped["source"]["commit"], "1fa166a1b8ae3c3d37f53418b4ecbc5edf9635a2")
        self.assertEqual(len(self.shipped["cases"]), 10)
        self.assertEqual({c["config"]["elastic_mode"] for c in self.shipped["cases"]}, {"iso_love", "coupled"})
        self.assertTrue(all(c["config"]["phases"] == 32 for c in self.shipped["cases"]))

    def test_recomputed_fixture_passes_and_exports_original_arrays_without_refresh(self):
        before = hashlib.sha256(self.path.read_bytes()).hexdigest()
        with patch.object(RUNNER, "analyze_config", wraps=RUNNER.analyze_config) as solve:
            report = self.run_case()
        solve.assert_called_once()
        self.assertEqual(solve.call_args.args[0], self.case["config"])
        self.assertTrue(report["response_regression_passed"])
        self.assertTrue(report["complete_baseline_checked"])
        self.assertFalse(report["reference_problem_equivalence_assessed"])
        self.assertFalse(report["physical_or_experimental_validation"])
        self.assertEqual(before, hashlib.sha256(self.path.read_bytes()).hexdigest())
        target = self.root / "out" / self.case["case_id"]
        self.assertTrue((target / "arrays.npz").is_file())
        self.assertTrue((target / "input.json").is_file())
        with np.load(target / "arrays.npz", allow_pickle=False) as arrays:
            np.testing.assert_array_equal(arrays["normal_approach_m"], self.result.normal_approach_m)

    def test_changed_baseline_response_fails_but_cannot_change_solver_output(self):
        self.assertTrue(self.run_case("before")["response_regression_passed"])
        self.case["response"]["mean_normal_approach_m"] *= 1.1
        self.case["response"]["normal_approach_m"][0] *= 1.1
        self.save()
        report = self.run_case("after")
        self.assertFalse(report["response_regression_passed"])
        first = self.root / "before" / self.case["case_id"] / "arrays.npz"
        second = self.root / "after" / self.case["case_id"] / "arrays.npz"
        with np.load(first, allow_pickle=False) as a, np.load(second, allow_pickle=False) as b:
            self.assertEqual(set(a.files), set(b.files))
            for name in a.files:
                np.testing.assert_array_equal(a[name], b[name], err_msg=name)

    def test_changed_current_response_is_detected_and_cli_can_fail(self):
        altered = copy.deepcopy(self.result)
        altered.mesh_stiffness_n_per_m[1] *= 1.01
        with patch.object(RUNNER, "analyze_config", return_value=altered):
            report = self.run_case()
            with contextlib.redirect_stdout(io.StringIO()):
                status = RUNNER.main(["--output", str(self.root / "cli"), "--baseline", str(self.path), "--require-match"])
        self.assertFalse(report["response_regression_passed"])
        self.assertEqual(status, 2)
        failed = [r["field"] for r in report["cases"][0]["differences"] if not r["passed"]]
        self.assertIn("mesh_stiffness_n_per_m", failed)

    def test_near_zero_response_uses_absolute_tolerance(self):
        expected = copy.deepcopy(self.case["response"])
        actual = copy.deepcopy(expected)
        expected["te_peak_to_peak_m"] = 0.
        for difference, passes in ((1e-12, True), (3e-12, False)):
            actual["te_peak_to_peak_m"] = difference
            rows = RUNNER.compare_response(actual, expected, self.baseline["tolerances"], self.case["config"])
            row = next(r for r in rows if r["field"] == "te_peak_to_peak_m")
            self.assertEqual(row["passed"], passes)

    def test_activity_and_tooth_indices_are_compared_exactly(self):
        for name in ("active_mask", "tooth_pair_index"):
            actual = copy.deepcopy(self.case["response"])
            actual[name][0] = not actual[name][0] if name == "active_mask" else actual[name][0] + 1
            rows = RUNNER.compare_response(actual, self.case["response"], self.baseline["tolerances"], self.case["config"])
            row = next(r for r in rows if r["field"] == name)
            self.assertFalse(row["passed"])
            self.assertEqual(row["mismatch_indices"], [[0]])

    def test_missing_fields_shapes_units_and_tolerances_are_rejected(self):
        mutations = [
            lambda b: b["cases"][0]["response"].pop("normal_approach_m"),
            lambda b: b["cases"][0]["response"]["normal_approach_m"].pop(),
            lambda b: b["cases"][0]["response"]["active_mask"].__setitem__(0, 1),
            lambda b: b["tolerances"].pop("max_pressure_pa"),
            lambda b: b["tolerances"]["max_pressure_pa"].update(unit="MPa"),
            lambda b: b["tolerances"]["max_pressure_pa"].update(absolute=-1.),
            lambda b: b["tolerances"]["max_pressure_pa"].update(relative=float("inf")),
            lambda b: b["tolerances"]["max_pressure_pa"].update(absolute=True),
            lambda b: b["cases"][0]["response"].update(te_peak_to_peak_m=None),
            lambda b: b["cases"][0]["response"].update(te_peak_to_peak_m=float("nan")),
            lambda b: b.pop("environment"),
            lambda b: b["source"].pop("kernel_sha256"),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                baseline = copy.deepcopy(self.baseline)
                mutate(baseline)
                with self.assertRaises(ValueError):
                    RUNNER.validate_baseline(baseline)

    def test_changed_input_identity_fails_before_solver_runs(self):
        self.case["config"]["torque_n_m"] *= 2
        self.save()
        with patch.object(RUNNER, "analyze_config") as solve:
            with self.assertRaises(ValueError):
                self.run_case()
            solve.assert_not_called()

    def test_nonfinite_current_response_is_a_failure_without_null_substitution(self):
        altered = copy.deepcopy(self.result)
        altered.normal_approach_m[0] = np.nan
        with patch.object(RUNNER, "analyze_config", return_value=altered):
            report = self.run_case()
        self.assertFalse(report["response_regression_passed"])
        self.assertIn("非有限", report["cases"][0]["error"])
        self.assertFalse((self.root / "out" / self.case["case_id"] / "response.json").exists())

    def test_unknown_duplicate_or_empty_selection_and_output_overlap_fail(self):
        for ids in ([], ["unknown"], [self.case["case_id"], self.case["case_id"]]):
            with self.assertRaises(ValueError):
                RUNNER.run(self.root / "selected", baseline_path=self.path, case_ids=ids)
        for output in (self.root, self.path):
            with self.assertRaises(ValueError):
                RUNNER.run(output, baseline_path=self.path)

    def test_partial_selection_is_labelled_as_partial(self):
        other = copy.deepcopy(self.case)
        other["case_id"] = "second_case"
        self.baseline["cases"].append(other)
        self.save()
        report = RUNNER.run(self.root / "selected", baseline_path=self.path, case_ids=[self.case["case_id"]])
        self.assertTrue(report["response_regression_passed"])
        self.assertFalse(report["complete_baseline_checked"])
        self.assertEqual(report["case_count"], 1)

    def test_nonempty_output_cannot_overwrite_existing_success(self):
        self.assertTrue(self.run_case()["response_regression_passed"])
        output = self.root / "out"
        before = {str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in output.rglob("*") if p.is_file()}
        with patch.object(RUNNER, "analyze_config") as solve:
            with self.assertRaises(ValueError):
                self.run_case()
            solve.assert_not_called()
        after = {str(p.relative_to(output)): hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in output.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_solver_failure_keeps_requested_input_without_old_arrays(self):
        with patch.object(RUNNER, "analyze_config", side_effect=RuntimeError("主动集合未收敛")):
            report = self.run_case()
        self.assertFalse(report["response_regression_passed"])
        target = self.root / "out" / self.case["case_id"]
        requested = json.loads((target / "requested_input.json").read_text(encoding="utf-8"))
        self.assertEqual(requested, self.case["config"])
        self.assertEqual(report["cases"][0]["config_sha256"], RUNNER.canonical_sha256(requested))
        self.assertFalse((target / "arrays.npz").exists())

    def test_finite_operands_with_overflowing_tolerance_cannot_pass(self):
        tolerances = copy.deepcopy(self.baseline["tolerances"])
        tolerances["max_pressure_pa"]["relative"] = 1e308
        with self.assertRaises(ValueError):
            RUNNER.compare_response(self.case["response"], self.case["response"], tolerances, self.case["config"])


if __name__ == "__main__":
    unittest.main()
