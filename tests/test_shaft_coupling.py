"""解析梁解、刚性极限、空间载荷平衡和导出复算验收。"""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from gear_contact import (LinearBearing, Material, Shaft, ShaftSegment,
                          analyze_config, build_structural_compliance, export_result, solve_shaft)
from gear_contact.hertz import local_line_approach


EXAMPLE = Path(__file__).resolve().parents[1] / "examples/shaft_bearing_case.json"


def case():
    """加载可复算输入，缩短单元测试相位循环。"""
    data = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    data.update(phases=6, strips=9)
    return data


class ShaftCouplingTests(unittest.TestCase):
    def test_simply_supported_stepped_shaft_closed_form(self):
        a, b = .045, .075
        d_a, d_b = .025, .032
        k_a, k_b, k_z = 3e8, 2e8, 1.2e8
        material = Material()
        shaft = Shaft((ShaftSegment(a, d_a, material), ShaftSegment(b, d_b, material)),
                      (LinearBearing(0, (k_a, k_a, k_z)), LinearBearing(2, (k_b, k_b, 0))),
                      gear_node=1, torque_node=2)
        load = np.array([720., -300., 210., 0., 0., 45.])
        response = solve_shaft(shaft, load)
        e, g = material.youngs_modulus_pa, material.shear_modulus_pa
        nu = material.poisson_ratio
        kappa = 6 * (1 + nu) / (7 + 6 * nu)
        area_a, area_b = np.pi * np.array([d_a, d_b])**2 / 4
        i_a, i_b = np.pi * np.array([d_a, d_b])**4 / 64
        left, right = b / (a + b), a / (a + b)
        # 单位载荷法积分两段弯矩、剪力，并计入两支承沉降。
        bending = left**2 * a**3 / (3 * e * i_a) + right**2 * b**3 / (3 * e * i_b)
        shear = left**2 * a / (kappa * g * area_a) + right**2 * b / (kappa * g * area_b)
        settlement = left**2 / k_a + right**2 / k_b
        expected = np.r_[load[:2] * (bending + shear + settlement), load[2] * (1 / k_z + a / (e * area_a))]
        np.testing.assert_allclose(response["translation_m"][1], expected, rtol=1e-12)
        np.testing.assert_allclose(response["bearing_reactions_n"], [
            [-left * load[0], -left * load[1], -load[2]],
            [-right * load[0], -right * load[1], 0.]], atol=1e-9)
        self.assertAlmostEqual(response["rotation_rad"][1, 2], load[5] * b / (2 * g * i_b), places=13)
        self.assertEqual(response["torque_reaction_n_m"], -load[5])
        np.testing.assert_allclose(response["moment_balance_n_m"], 0, atol=1e-10)

    def test_rigid_limit_recovers_original_contact(self):
        data = case()
        reference = copy.deepcopy(data)
        reference.pop("shaft_system")
        reference = analyze_config(reference)
        for shaft in data["shaft_system"].values():
            for segment in shaft["segments"]:
                segment["material"] = {"youngs_modulus_pa": 210e19}
            for bearing in shaft["bearings"]:
                bearing["stiffness_n_per_m"] = [value * 1e10 for value in bearing["stiffness_n_per_m"]]
        stiff = analyze_config(data)
        self.assertLess(stiff.summary["max_abs_shaft_normal_displacement_m"], 1e-13)
        np.testing.assert_allclose(stiff.normal_approach_m, reference.normal_approach_m, atol=1e-13, rtol=0)
        np.testing.assert_allclose(stiff.mesh_stiffness_n_per_m, reference.mesh_stiffness_n_per_m, rtol=1e-7)
        for actual, original in zip(stiff.rotations, reference.rotations):
            np.testing.assert_allclose(actual.solution.forces_n, original.solution.forces_n, atol=1e-6)
            np.testing.assert_array_equal(actual.solution.active_mask, original.solution.active_mask)

    def test_helical_support_changes_load_and_closes_contact_equation(self):
        data = case()
        result = analyze_config(data)
        data.pop("shaft_system")
        fixed = analyze_config(data)
        self.assertTrue(result.summary["all_converged"])
        self.assertGreater(result.summary["max_abs_load_centroid_offset_m"], 1e-4)
        self.assertGreater(max(np.max(np.abs(a.solution.forces_n - b.solution.forces_n))
                               for a, b in zip(result.rotations, fixed.rotations)), 10.)
        pair = result.pair
        beta = pair.base_helix_angle_rad
        for rotation in result.rotations:
            f = rotation.solution.forces_n
            diagnostic = rotation.elastic_diagnostics["shaft_bearing"]
            pinion, wheel = diagnostic["pinion"], diagnostic["wheel"]
            np.testing.assert_allclose(pinion["gear_force_n"] + wheel["gear_force_n"], 0, atol=1e-10)
            self.assertAlmostEqual(pinion["gear_force_n"][2], f.sum() * np.sin(beta), places=9)
            self.assertAlmostEqual(pinion["gear_moment_n_m"][2], -data["torque_n_m"], places=9)
            self.assertAlmostEqual(wheel["gear_moment_n_m"][2],
                                   -f.sum() * pair.wheel.base_radius_m * np.cos(beta), places=9)
            for shaft in (pinion, wheel):
                np.testing.assert_allclose(shaft["force_balance_n"], 0, atol=1e-8)
                np.testing.assert_allclose(shaft["moment_balance_n_m"], 0, atol=1e-9)
            c, _ = build_structural_compliance(pair, rotation.grid)
            g = rotation.grid
            h, _ = local_line_approach(f, g.widths_m, g.radius_pinion_m, g.radius_wheel_m,
                                       curvature_per_m=g.curvature_per_m)
            gap = rotation.gaps_m + c @ f + h + diagnostic["normal_displacement_m"] - rotation.solution.approach_m
            np.testing.assert_allclose(gap, rotation.solution.residual_gaps_m, atol=5e-15, rtol=0)

    def test_internal_mesh_reverses_wheel_torque_sign(self):
        data = case()
        data["pair"]["wheel"].update(teeth=84, helix_angle_rad=.22, internal=True)
        result = analyze_config(data)
        for rotation in result.rotations:
            diagnostic = rotation.elastic_diagnostics["shaft_bearing"]
            self.assertAlmostEqual(diagnostic["pinion"]["gear_moment_n_m"][2], -80., places=9)
            self.assertAlmostEqual(diagnostic["wheel"]["gear_moment_n_m"][2], 240., places=9)

    def test_exported_inputs_reproduce_coupled_result(self):
        data = case()
        result = analyze_config(data)
        with tempfile.TemporaryDirectory() as directory:
            export_result(result, directory)
            directory = Path(directory)
            repeated = analyze_config(json.loads((directory / "input.json").read_text(encoding="utf-8")))
            np.testing.assert_array_equal(repeated.normal_approach_m, result.normal_approach_m)
            with np.load(directory / "arrays.npz", allow_pickle=False) as arrays:
                expected = np.concatenate([r.elastic_diagnostics["shaft_bearing"]["normal_displacement_m"]
                                           for r in repeated.rotations])
                np.testing.assert_array_equal(arrays["shaft_normal_displacement_m"], expected)

    def test_reject_underconstrained_shaft_and_incompatible_elasticity(self):
        data = case()
        data["shaft_system"]["pinion"]["bearings"][0]["stiffness_n_per_m"][2] = 0
        with self.assertRaisesRegex(ValueError, "轴向定位"):
            analyze_config(data)
        data = case()
        data.update(elastic_mode="iso_love", local_contact=False, iso_settings={"nominal_pinion_torque_n_m": 80})
        with self.assertRaisesRegex(ValueError, "轴系耦合"):
            analyze_config(data)


if __name__ == "__main__":
    unittest.main()
