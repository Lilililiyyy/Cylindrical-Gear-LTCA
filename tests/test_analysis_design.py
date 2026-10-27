"""接入、整体相似律、周期统计、谱定义和多工况设计的独立验收。"""
from dataclasses import replace
import json
import math
from pathlib import Path
import tempfile
import unittest

import numpy as np

from gear_contact import (Gear, GearPair, SurfaceModification, analyze_pair,
                          transmission_error_spectrum, OperatingPoint, compare_designs,
                          sweep_parameter, export_result, Material)


def pair(scale=1, beta=0, internal=False):
    return GearPair(Gear(28, .0025*scale, .025*scale, helix_angle_rad=beta),
                    Gear(84 if internal else 56, .0025*scale, .025*scale,
                         helix_angle_rad=beta if internal else -beta, internal=internal))


class AnalysisDesignTests(unittest.TestCase):
    def test_structural_override_recovers_parallel_spring_solution(self):
        stiffness = 4e7
        result = analyze_pair(pair(), torque_n_m=80, phases=4, strips=5, local_contact=False,
                              compliance_provider=lambda p, g: np.eye(len(g))/stiffness)
        force = result.summary["normal_force_n"]
        for rotation in result.rotations:
            count = len(rotation.grid)
            self.assertAlmostEqual(rotation.solution.approach_m/(force/(stiffness*count)), 1, places=10)
            np.testing.assert_allclose(rotation.solution.forces_n, force/count, rtol=1e-10)

    def test_full_chain_external_internal_and_helical(self):
        for internal, beta in ((False, 0), (True, 0), (False, .3), (True, .3)):
            with self.subTest(internal=internal, beta=beta):
                result = analyze_pair(pair(beta=beta, internal=internal), torque_n_m=80,
                                      modification_pinion=SurfaceModification(lead_crown_m=5e-6),
                                      misalignment_m=3e-6, phases=4, strips=5)
                self.assertTrue(result.summary["all_converged"])
                self.assertLess(result.summary["max_force_residual_n"], 1e-8)
                self.assertLess(result.summary["max_gap_residual_m"], 3e-12)
                self.assertTrue(np.all(result.mesh_stiffness_n_per_m > 0))
                for r in result.rotations:
                    self.assertTrue(np.all(np.isfinite(r.pressure_pa)))
                    self.assertTrue(np.all(r.solution.forces_n >= 0))

    def test_geometrical_similarity_including_hertz(self):
        # 长度×s、扭矩×s³保持应力和应变不变，因此位移×s、刚度×s。
        a = analyze_pair(pair(), torque_n_m=80, phases=4, strips=5,
                         modification_pinion=SurfaceModification(lead_crown_m=5e-6))
        b = analyze_pair(pair(2), torque_n_m=80*8, phases=4, strips=5,
                         modification_pinion=SurfaceModification(lead_crown_m=10e-6))
        np.testing.assert_allclose(b.normal_approach_m, a.normal_approach_m*2, rtol=2e-6)
        np.testing.assert_allclose(b.angular_te_rad, a.angular_te_rad, rtol=2e-6)
        np.testing.assert_allclose(b.mesh_stiffness_n_per_m, a.mesh_stiffness_n_per_m*2, rtol=2e-6)
        self.assertAlmostEqual(b.summary["max_pressure_pa"]/a.summary["max_pressure_pa"], 1, places=5)

    def test_spectrum_known_phase_and_nyquist(self):
        phase = np.arange(32)/32
        signal = 4+2*np.cos(2*np.pi*3*phase+2.4)+.7*np.cos(2*np.pi*16*phase)
        result = transmission_error_spectrum(signal, 16)
        self.assertAlmostEqual(result["mean"], 4)
        self.assertAlmostEqual(result["amplitude"][2], 2)
        self.assertAlmostEqual(result["phase_rad"][2], 2.4)
        self.assertAlmostEqual(result["amplitude"][-1], .7)
        self.assertTrue(np.isnan(result["phase_rad"][0]))

    def test_design_study_and_explicit_pressure_constraint(self):
        designs = {"基准": SurfaceModification(), "鼓形": SurfaceModification(lead_crown_m=4e-6)}
        points = [OperatingPoint("轻载", 40), OperatingPoint("失准", 80, 6e-6)]
        study = compare_designs(pair(), designs, operating_points=points, phases=4, strips=5)
        self.assertEqual(len(study.rows), 4)
        self.assertTrue(study.pareto_names)
        self.assertEqual(len(study.to_dict()["design_summary"]), 2)
        impossible = compare_designs(pair(), designs, operating_points=points,
                                     pressure_limit_pa=1, phases=4, strips=5)
        self.assertEqual(impossible.pareto_names, [])
        self.assertTrue(all(not s["feasible"] for s in impossible.design_summary))

    def test_parameter_sweep_and_export_round_trip(self):
        study = sweep_parameter(pair(), "lead_crown_m", [0, 4e-6], torque_n_m=80, phases=4, strips=5)
        self.assertEqual(len(study.rows), 2)
        result = next(iter(next(iter(study.results.values())).values()))
        with tempfile.TemporaryDirectory() as directory:
            manifest = export_result(result, directory)
            folder = Path(directory)
            for name in manifest["files"]:
                self.assertTrue((folder/name).is_file())
            with np.load(folder/"arrays.npz", allow_pickle=False) as saved:
                np.testing.assert_array_equal(saved["normal_approach_m"], result.normal_approach_m)
                for i, r in enumerate(result.rotations):
                    begin, end = saved["cell_offsets"][i:i+2]
                    np.testing.assert_array_equal(saved["forces_n"][begin:end], r.solution.forces_n)
            inputs = json.loads((folder/"input.json").read_text(encoding="utf-8"))
            self.assertEqual(inputs["torque_n_m"], 80)

    def test_no_load_and_invalid_controls(self):
        result = analyze_pair(pair(), torque_n_m=0, phases=4, strips=5)
        self.assertEqual(result.summary["max_pressure_pa"], 0)
        for options in ({"torque_n_m": -1}, {"torque_n_m": 1, "phases": True},
                        {"torque_n_m": 1, "strips": 1}):
            with self.assertRaises(ValueError):
                analyze_pair(pair(), **options)


if __name__ == "__main__":
    unittest.main()
