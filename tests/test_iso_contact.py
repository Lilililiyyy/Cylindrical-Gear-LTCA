"""ISO刚度的量纲、低载分支、内齿符号与非对称Love接触协调验证。"""
from dataclasses import replace
import json
import math
from pathlib import Path
from types import SimpleNamespace
import unittest

import numpy as np

from gear_contact import Gear, GearPair, Material, contact_grid, modification_from_config
from gear_contact.iso_contact import (ISOContactSettings, iso_single_tooth_stiffness,
    build_iso_compliance, love_coupling_matrix, solve_iso_contact)


def standard_pair(internal=False):
    return GearPair(Gear(28, .0025, .025), Gear(84 if internal else 56, .0025, .025, internal=internal))


class ISOContactTests(unittest.TestCase):
    def test_spur_iso_expression_and_low_load_power(self):
        pair, material = standard_pair(), Material(207e9, .3)
        settings = ISOContactSettings(1.)
        result = iso_single_tooth_stiffness(pair, material, material, settings)
        za, zb = 28., 56.
        reciprocal = (0.04723+.15551/za+.25791/zb)*1e-9
        rack = (1+.5*(1.2-1.25))
        q = 1./pair.pinion.reference_radius_m/.025
        expected = .8*rack*(q/100000.)**.25/reciprocal
        self.assertAlmostEqual(result["single_stiffness_n_per_m2"]/expected, 1., places=13)
        larger = iso_single_tooth_stiffness(pair, material, material, replace(settings, nominal_pinion_torque_n_m=16.))
        self.assertAlmostEqual(larger["single_stiffness_n_per_m2"]/result["single_stiffness_n_per_m2"], 2., places=12)
        basis = iso_single_tooth_stiffness(pair, material, material,
            replace(settings, material_reference_youngs_modulus_pa=206e9))
        self.assertAlmostEqual(basis["single_stiffness_n_per_m2"]/result["single_stiffness_n_per_m2"], 207/206, places=12)

    def test_material_scale_and_zero_nominal_branch_are_explicit(self):
        pair, material = standard_pair(), Material(207e9, .3)
        settings = ISOContactSettings(2.)
        base = iso_single_tooth_stiffness(pair, material, material, settings)
        scaled = iso_single_tooth_stiffness(pair, Material(414e9, .3), Material(414e9, .3), settings)
        self.assertAlmostEqual(scaled["single_stiffness_n_per_m2"]/base["single_stiffness_n_per_m2"], 2., places=12)
        zero = iso_single_tooth_stiffness(pair, material, material, replace(settings, nominal_pinion_torque_n_m=0.))
        self.assertEqual(zero["low_load_factor"], 1.)
        self.assertEqual(zero["load_per_width_n_per_m"], 0.)

    def test_internal_virtual_teeth_and_actual_root_coefficients(self):
        pair = GearPair(Gear(28, .0025, .025, profile_shift=.1),
                        Gear(84, .0025, .025, profile_shift=.3, internal=True))
        result = iso_single_tooth_stiffness(pair, Material(), Material(), ISOContactSettings(5.))
        self.assertLess(result["signed_virtual_teeth_wheel"], 0.)
        self.assertAlmostEqual(result["dedendum_coeff_pinion"], 1.25)
        self.assertAlmostEqual(result["dedendum_coeff_wheel"], 1.85)
        self.assertGreater(result["single_stiffness_n_per_m2"], 0.)

    def test_normal_strip_compliance_uses_actual_line_length(self):
        beta = .3
        pair = GearPair(Gear(28, .0025, .025, helix_angle_rad=beta),
                        Gear(56, .0025, .025, helix_angle_rad=-beta))
        grid = contact_grid(pair, .3, strips=7)
        matrix, detail = build_iso_compliance(pair, grid, Material(), Material(), ISOContactSettings(5.))
        expected = math.cos(pair.base_helix_angle_rad)/(detail["single_stiffness_n_per_m2"]*grid.widths_m)
        np.testing.assert_allclose(np.diag(matrix), expected, rtol=1e-14)
        np.testing.assert_array_equal(matrix-np.diag(np.diag(matrix)), np.zeros_like(matrix))
        self.assertTrue(detail["local_contact_included"])

    def test_love_operator_has_zero_mean_without_false_reciprocity(self):
        grid = SimpleNamespace(widths_m=np.array([.001, .0015, .002]), tooth_pair_index=np.zeros(3, dtype=int))
        matrix = love_coupling_matrix(grid, Material())
        np.testing.assert_allclose(matrix.sum(axis=0), 0., atol=1e-24)
        self.assertFalse(np.allclose(matrix, matrix.T, rtol=1e-10, atol=1e-24))
        force = np.array([10., 20., 30.])
        self.assertAlmostEqual(float(np.mean(matrix@force)), 0., places=20)

    def test_uniform_single_line_mean_and_tangent_remain_iso_values(self):
        pair, material = standard_pair(), Material()
        grid = SimpleNamespace(widths_m=np.full(9, .025/9), tooth_pair_index=np.zeros(9, dtype=int))
        settings = ISOContactSettings(10.)
        matrix, _ = build_iso_compliance(pair, grid, material, material, settings)
        force = 100.
        solution, detail = solve_iso_contact(pair, grid, np.zeros(9), force, material, material, settings)
        expected_k = float(np.sum(1/np.diag(matrix)))
        self.assertAlmostEqual(solution.approach_m/(force/expected_k), 1., places=10)
        self.assertAlmostEqual(solution.tangent_stiffness_n_per_m/expected_k, 1., places=10)
        self.assertLess(solution.diagnostics["maximum_penetration_m"], 3e-12)
        self.assertFalse(solution.diagnostics["model_energy_available"])
        self.assertGreater(detail["coupling_iterations"], 0)

    def test_gapped_contact_and_zero_load_obey_unilateral_constraints(self):
        pair, material = standard_pair(), Material()
        grid = SimpleNamespace(widths_m=np.full(7, .025/7), tooth_pair_index=np.zeros(7, dtype=int))
        gap = np.array([4., 2., .4, 0., .4, 2., 4.])*1e-6
        settings = ISOContactSettings(10.)
        solution, _ = solve_iso_contact(pair, grid, gap, 100., material, material, settings)
        self.assertAlmostEqual(float(np.sum(solution.forces_n)), 100., places=11)
        self.assertTrue(np.all(solution.forces_n >= 0))
        self.assertLessEqual(solution.diagnostics["maximum_penetration_m"], 2e-12)
        self.assertLessEqual(solution.diagnostics["active_gap_error_m"], 2e-12)
        self.assertTrue(np.any(~solution.active_mask))
        zero, _ = solve_iso_contact(pair, grid, gap, 0., material, material, settings)
        np.testing.assert_array_equal(zero.forces_n, np.zeros(7))
        self.assertEqual(zero.approach_m, 0.)
        self.assertGreater(zero.tangent_stiffness_n_per_m, 0.)

    def test_helical_showcase_is_computed_from_inputs(self):
        root = next(p for p in Path(__file__).resolve().parents
                    if (p/"pyproject.toml").is_file() and (p/"gear_contact").is_dir())
        case = json.loads((root/"examples/helical_18_77_case.json").read_text(encoding="utf-8"))
        data = case["analysis"]
        g = data["pair"]
        pair = GearPair(**dict(g, pinion=Gear(**g["pinion"]), wheel=Gear(**g["wheel"])))
        mp, mw = Material(**data["material_pinion"]), Material(**data["material_wheel"])
        settings = ISOContactSettings(case["loading"]["nominal_pinion_torque_n_m"])
        grid = contact_grid(pair, data["phase_offset"], strips=9)
        gap = (modification_from_config(data["modification_pinion"]).evaluate(grid.profile_factor_pinion, grid.lead_factor_pinion)
               +modification_from_config(data["modification_wheel"]).evaluate(grid.profile_factor_wheel, grid.lead_factor_wheel))
        target = pair.normal_force_from_torque(settings.nominal_pinion_torque_n_m*case["loading"]["ltca_torque_multiplier"])
        solution, detail = solve_iso_contact(pair, grid, gap, target, mp, mw, settings)
        self.assertAlmostEqual(detail["single_stiffness_n_per_m2"]/5948512455.775998, 1., places=12)
        self.assertGreater(solution.approach_m, 1e-6)
        self.assertLess(solution.approach_m, 1.3e-6)
        self.assertAlmostEqual(float(solution.forces_n.sum()), target, places=10)

    def test_invalid_settings_and_geometry_are_not_silently_repaired(self):
        for kwargs in ({"nominal_pinion_torque_n_m": -1.}, {"nominal_pinion_torque_n_m": True},
                       {"nominal_pinion_torque_n_m": 1., "application_factor": 0.},
                       {"nominal_pinion_torque_n_m": 1., "coupling_relaxation": 1.1}):
            with self.assertRaises(ValueError):
                ISOContactSettings(**kwargs)
        invalid = SimpleNamespace(widths_m=np.array([0.]), tooth_pair_index=np.array([0]))
        with self.assertRaises(ValueError):
            love_coupling_matrix(invalid, Material())

    def test_excluded_candidates_preserve_full_love_layout_and_real_gaps(self):
        pair, material = standard_pair(), Material()
        grid = SimpleNamespace(widths_m=np.array([.003, .004, .005, .006, .007]),
                               tooth_pair_index=np.zeros(5, dtype=int))
        allowed = np.array([True, False, True, True, False])
        gaps = np.array([0., -1e-5, 0., 0., -2e-5])
        settings = ISOContactSettings(10., coupling_tolerance_m=1e-14)
        compliance, _ = build_iso_compliance(pair, grid, material, material, settings)
        operator = love_coupling_matrix(grid, material)
        full = compliance+operator
        inverse_one = np.linalg.solve(full[np.ix_(allowed, allowed)], np.ones(np.count_nonzero(allowed)))
        expected = 100.*inverse_one/inverse_one.sum()
        solution, details = solve_iso_contact(pair, grid, gaps, 100., material, material, settings, eligible=allowed)
        np.testing.assert_allclose(solution.forces_n[allowed], expected, rtol=1e-7, atol=1e-8)
        np.testing.assert_array_equal(solution.forces_n[~allowed], 0.)
        np.testing.assert_allclose(solution.residual_gaps_m,
            gaps+full@solution.forces_n-solution.approach_m, rtol=0., atol=1e-18)
        self.assertTrue(np.all(solution.residual_gaps_m[~allowed] < 0.))
        self.assertLess(solution.diagnostics["maximum_penetration_m"], 1e-14)
        self.assertEqual(details["excluded_candidates"], 2)
        with self.assertRaises(ValueError):
            solve_iso_contact(pair, grid, gaps, 100., material, material, settings, eligible=np.zeros(5, dtype=bool))


if __name__ == "__main__":
    unittest.main()
