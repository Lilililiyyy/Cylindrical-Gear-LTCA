"""单案例的载荷记账、真实参数响应及参照身份不能互相替代。"""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

PROJECT = next(p for p in Path(__file__).resolve().parents
               if (p/"pyproject.toml").is_file() and (p/"gear_contact").is_dir())
SPEC = importlib.util.spec_from_file_location("cylindrical_workflow", PROJECT/"examples/run_cylindrical_workflow.py")
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class CylindricalWorkflowTests(unittest.TestCase):
    def case(self):
        value = json.loads((PROJECT/"examples/helical_18_77_case.json").read_text(encoding="utf-8"))
        value["analysis"].update(phases=4, strips=5)
        return value

    def test_shared_nominal_torque_drives_both_rating_and_actual_ltca(self):
        case = self.case()
        first, strength, config = RUNNER.calculate_case(case)
        changed = deepcopy(case)
        changed["loading"]["nominal_pinion_torque_n_m"] *= 4
        second, rating, updated = RUNNER.calculate_case(changed)
        self.assertAlmostEqual(rating["pinion"]["contact_stress_pa"]/strength["pinion"]["contact_stress_pa"], 2., places=12)
        self.assertAlmostEqual(rating["wheel"]["root_stress_pa"]/strength["wheel"]["root_stress_pa"], 4., places=12)
        self.assertAlmostEqual(second.summary["normal_force_n"]/first.summary["normal_force_n"], 4., places=12)
        self.assertAlmostEqual(updated["torque_n_m"]/config["torque_n_m"], 4., places=12)

    def test_external_factors_are_inputs_but_frozen_own_responses_are_ignored(self):
        case = self.case()
        first, strength, _ = RUNNER.calculate_case(case)
        modified = deepcopy(case)
        modified["project_summary"] = {"normal_force_n": 1e20}
        modified["strength"]["mesh_factors"]["face_contact_factor"] *= 4
        second, rating, _ = RUNNER.calculate_case(modified)
        self.assertAlmostEqual(rating["pinion"]["contact_stress_pa"]/strength["pinion"]["contact_stress_pa"], 2., places=12)
        self.assertEqual(first.summary, second.summary)

    def test_phase_origin_is_part_of_same_input_check(self):
        case = self.case()
        changed = deepcopy(case)
        changed["analysis"]["phase_offset"] += .01
        self.assertNotEqual(RUNNER.calculation_inputs(case), RUNNER.calculation_inputs(changed))
        with self.assertRaises(ValueError):
            RUNNER.prepare_case(dict(case, analysis=dict(case["analysis"], torque_n_m=123.)))

    def test_output_guard_preserves_case_and_reference(self):
        case_path = PROJECT/"examples/helical_18_77_case.json"
        original = case_path.read_bytes()
        for output in (case_path.parent, case_path.parent/"masta_reference", case_path):
            with self.assertRaises(ValueError):
                RUNNER.run(case_path, output)
        self.assertEqual(original, case_path.read_bytes())

    def test_custom_reference_cannot_place_baseline_inside_output(self):
        payload = json.loads((PROJECT/"examples/helical_18_77_reference.json").read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root/"out").mkdir()
            baseline = root/"out/case_inputs.json"
            baseline.write_text(json.dumps(self.case()), encoding="utf-8")
            before = baseline.read_bytes()
            payload["case_file"] = "out/case_inputs.json"
            reference = root/"reference.json"
            reference.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(ValueError):
                RUNNER.run(PROJECT/"examples/helical_18_77_case.json", root/"out", reference_path=reference)
            self.assertEqual(before, baseline.read_bytes())


if __name__ == "__main__":
    unittest.main()
