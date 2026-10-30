"""ISO综合刚度接入时的载荷层级、切线及延伸数据导出验证。"""
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from gear_contact import Gear, GearPair, ISOContactSettings, analyze_pair, analyze_config, export_result


class ISOAnalysisTests(unittest.TestCase):
    def test_integrated_tangent_uses_fixed_nominal_case_stiffness(self):
        pair = GearPair(Gear(28, .0025, .025), Gear(56, .0025, .025))
        options = dict(elastic_mode="iso_love", local_contact=False,
                       iso_settings=ISOContactSettings(80.), phases=4, strips=7, phase_offset=.13)
        base = analyze_pair(pair, torque_n_m=80., **options)
        plus = analyze_pair(pair, torque_n_m=80.08, **options)
        minus = analyze_pair(pair, torque_n_m=79.92, **options)
        delta_force = plus.summary["normal_force_n"]-minus.summary["normal_force_n"]
        numerical = delta_force/(plus.normal_approach_m-minus.normal_approach_m)
        np.testing.assert_allclose(base.mesh_stiffness_n_per_m, numerical, rtol=1e-7)

    def test_iso_cannot_duplicate_local_contact_or_guess_nominal_load(self):
        pair = GearPair(Gear(28, .0025, .025), Gear(56, .0025, .025))
        with self.assertRaises(ValueError):
            analyze_pair(pair, torque_n_m=80., elastic_mode="iso", iso_settings=ISOContactSettings(80.))
        with self.assertRaises(ValueError):
            analyze_pair(pair, torque_n_m=80., elastic_mode="iso", local_contact=False)

    def test_zero_load_iso_does_not_evaluate_unloaded_singular_hertz_curvature(self):
        pair = GearPair(Gear(20, .002, .02), Gear(60, .002, .02, internal=True))
        result = analyze_pair(pair, torque_n_m=0., phases=2, strips=5,
            elastic_mode="iso", local_contact=False, iso_settings=ISOContactSettings(0.))
        self.assertEqual(result.summary["max_pressure_pa"], 0.)
        self.assertTrue(all(np.all(r.solution.forces_n == 0.) for r in result.rotations))

    def test_extended_config_roundtrip_keeps_complete_centres_endpoints_and_flags(self):
        project = next(p for p in Path(__file__).resolve().parents
                       if (p/"pyproject.toml").is_file() and (p/"gear_contact").is_dir())
        case = json.loads((project/"examples/helical_18_77_case.json").read_text(encoding="utf-8"))
        config = dict(case["analysis"], phases=4, strips=7,
                      torque_n_m=case["loading"]["nominal_pinion_torque_n_m"]*case["loading"]["ltca_torque_multiplier"])
        config["iso_settings"] = dict(config["iso_settings"],
            nominal_pinion_torque_n_m=case["loading"]["nominal_pinion_torque_n_m"])
        result = analyze_config(config)
        with tempfile.TemporaryDirectory() as temp:
            export_result(result, temp)
            actual = analyze_config(json.loads((Path(temp)/"input.json").read_text(encoding="utf-8")))
            np.testing.assert_allclose(actual.normal_approach_m, result.normal_approach_m, rtol=1e-11)
            with np.load(Path(temp)/"arrays.npz", allow_pickle=False) as arrays:
                nc = np.diff(arrays["line_cell_offsets"])
                ne = np.diff(arrays["line_endpoint_offsets"])
                np.testing.assert_array_equal(ne, nc+1)
                self.assertEqual(len(arrays["eligible"]), len(arrays["forces_n"]))
                self.assertEqual(len(arrays["endpoint_pressure_pa"]), arrays["line_endpoint_offsets"][-1])
                self.assertTrue(np.all(arrays["forces_n"][~arrays["eligible"]] == 0))
                self.assertGreater(np.count_nonzero(arrays["extended_pinion"] | arrays["extended_wheel"]), 0)
            self.assertTrue((Path(temp)/"endpoint_cells.csv").is_file())
            header = (Path(temp)/"contact_cells.csv").read_text(encoding="utf-8-sig").splitlines()[0]
            self.assertIn("eligible", header)
            self.assertIn("extended_pinion", header)


if __name__ == "__main__":
    unittest.main()
