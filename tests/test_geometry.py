"""解析几何、手性、单位缩放和接触线积分检验，不依赖外部组件。"""
import math
import unittest

import numpy as np

from gear_contact.geometry import Gear, GearPair, contact_grid


def external(beta=0.0, offset=0.0):
    return GearPair(Gear(24, 0.002, 0.025, helix_angle_rad=beta),
                    Gear(48, 0.002, 0.030, helix_angle_rad=-beta), axial_offset_m=offset)


def internal(beta=0.0):
    return GearPair(Gear(24, 0.002, 0.025, helix_angle_rad=beta),
                    Gear(72, 0.002, 0.030, helix_angle_rad=beta, internal=True))


class GeometryTests(unittest.TestCase):
    def test_standard_spur_radii_contact_ratio(self):
        pair = external()
        p, w = pair.pinion, pair.wheel
        alpha = math.radians(20)
        self.assertAlmostEqual(pair.center_distance_m, 0.072, places=13)
        self.assertAlmostEqual(pair.working_pressure_angle_rad, alpha)
        self.assertAlmostEqual(pair.base_pitch_m, math.pi * 0.002 * math.cos(alpha))
        path = math.sqrt(p.tip_radius_m**2 - p.base_radius_m**2) + math.sqrt(w.tip_radius_m**2 - w.base_radius_m**2) - pair.center_distance_m * math.sin(alpha)
        self.assertAlmostEqual(pair.transverse_contact_ratio, path / pair.base_pitch_m)
        self.assertAlmostEqual(p.tooth_thickness_m(p.reference_radius_m), math.pi * 0.002 / 2)

    def test_involute_sum_and_difference(self):
        for pair in (external(), internal()):
            grid = contact_grid(pair, 0.123, 9)
            span = pair.center_distance_m * math.sin(pair.working_pressure_angle_rad)
            measured = grid.roll_wheel_m - grid.roll_pinion_m if pair.wheel.internal else grid.roll_wheel_m + grid.roll_pinion_m
            np.testing.assert_allclose(measured, span, rtol=1e-13)
            expected = 1 / grid.radius_pinion_m + (-1 if pair.wheel.internal else 1) / grid.radius_wheel_m
            np.testing.assert_allclose(grid.curvature_per_m, expected, rtol=1e-13)
            self.assertTrue(np.all(grid.curvature_per_m > 0))

    def test_midpoint_widths_and_lead_normalization(self):
        pair = external(offset=0.010)
        grid = contact_grid(pair, 0.18, 8)
        left, right = pair.face_bounds_m
        self.assertAlmostEqual(left, -0.005)
        self.assertAlmostEqual(right, 0.0125)
        for line in np.unique(grid.tooth_pair_index):
            mask = grid.tooth_pair_index == line
            self.assertAlmostEqual(grid.widths_m[mask].sum(), right - left)
            self.assertGreater(grid.face_coordinate_m[mask].min(), left)
            self.assertLess(grid.face_coordinate_m[mask].max(), right)
        np.testing.assert_allclose(grid.lead_factor_pinion, (grid.face_coordinate_m + 0.0125) / 0.025)
        np.testing.assert_allclose(grid.lead_factor_wheel, (grid.face_coordinate_m - 0.010 + 0.015) / 0.030)
        self.assertGreater(grid.lead_factor_pinion.min(), 0)

    def test_profile_factor_uses_whole_tooth(self):
        for pair in (external(), internal()):
            grid = contact_grid(pair, 0.13, 6)
            pl, ph = pair.pinion.involute_roll_bounds_m
            wl, wh = pair.wheel.involute_roll_bounds_m
            np.testing.assert_allclose(grid.profile_factor_pinion, (grid.roll_pinion_m - pl) / (ph - pl))
            expected = (wh - grid.roll_wheel_m) / (wh - wl) if pair.wheel.internal else (grid.roll_wheel_m - wl) / (wh - wl)
            np.testing.assert_allclose(grid.profile_factor_wheel, expected)

    def test_helical_normal_curvature_and_virtual_work(self):
        pair = external(math.radians(18))
        grid = contact_grid(pair, 0.11, 11)
        cosine = math.cos(pair.base_helix_angle_rad)
        np.testing.assert_allclose(grid.radius_pinion_m, grid.roll_pinion_m / cosine)
        torque, approach = 120.0, 8e-6
        force = pair.normal_force_from_torque(torque)
        angle = pair.normal_approach_to_angular_te(approach)
        self.assertAlmostEqual(force * approach, torque * angle)
        self.assertGreater(pair.overlap_ratio, 0)

    def test_handedness_mirrors_grid(self):
        positive, negative = external(0.3), external(-0.3)
        g1, g2 = contact_grid(positive, 0.27, 7), contact_grid(negative, 0.27, 7)
        for index in np.unique(g1.tooth_pair_index):
            a, b = g1.tooth_pair_index == index, g2.tooth_pair_index == index
            np.testing.assert_allclose(g1.face_coordinate_m[a], -g2.face_coordinate_m[b][::-1], atol=1e-14)
            np.testing.assert_allclose(g1.roll_pinion_m[a], g2.roll_pinion_m[b][::-1], atol=1e-14)

    def test_helical_cycle_line_integral(self):
        pair = external(0.32, 0.004)
        lengths = [contact_grid(pair, k / 1024, 5).widths_m.sum() for k in range(1024)]
        expected = pair.face_overlap_m * pair.transverse_contact_ratio / math.cos(pair.base_helix_angle_rad)
        self.assertAlmostEqual(float(np.mean(lengths)), expected, delta=expected * 2e-5)
        self.assertAlmostEqual(contact_grid(pair, 0.137, 5).widths_m.sum(), contact_grid(pair, 0.137, 31).widths_m.sum())

    def test_actual_tip_crops_path(self):
        original = external()
        p = original.pinion
        trimmed = Gear(p.teeth, p.normal_module_m, p.face_width_m, tip_diameter_m=2 * (p.tip_radius_m - 0.0005))
        modified = GearPair(trimmed, original.wheel)
        self.assertLess(modified.transverse_contact_ratio, original.transverse_contact_ratio)
        self.assertLess(modified.contact_roll_bounds_m[1], original.contact_roll_bounds_m[1])

    def test_length_scaling(self):
        pair = external(0.25, 0.004)
        scale = 5.0
        larger = GearPair(Gear(24, 0.002 * scale, 0.025 * scale, helix_angle_rad=0.25),
                          Gear(48, 0.002 * scale, 0.030 * scale, helix_angle_rad=-0.25), axial_offset_m=0.004 * scale)
        a, b = contact_grid(pair, 0.14, 8), contact_grid(larger, 0.14, 8)
        np.testing.assert_allclose(b.widths_m, a.widths_m * scale)
        np.testing.assert_allclose(b.curvature_per_m, a.curvature_per_m / scale)
        np.testing.assert_allclose(b.profile_factor_pinion, a.profile_factor_pinion)
        self.assertAlmostEqual(pair.transverse_contact_ratio, larger.transverse_contact_ratio)

    def test_form_radii_crop_without_moving_structural_root(self):
        original = external()
        p = original.pinion
        formed = Gear(24, 0.002, 0.025,
                      root_form_diameter_m=2 * (p.base_radius_m + 0.0008),
                      tip_form_diameter_m=2 * (p.tip_radius_m - 0.0003))
        pair = GearPair(formed, original.wheel)
        self.assertEqual(formed.root_radius_m, p.root_radius_m)
        self.assertEqual(formed.tip_radius_m, p.tip_radius_m)
        self.assertLess(pair.transverse_contact_ratio, original.transverse_contact_ratio)
        grid = contact_grid(pair, 0.2, 6)
        lower, upper = formed.involute_roll_bounds_m
        np.testing.assert_allclose(grid.profile_factor_pinion, (grid.roll_pinion_m - lower) / (upper - lower))
        self.assertGreater(formed.tooth_thickness_m(formed.root_radius_m), 0)
        ring = internal().wheel
        limited = Gear(72, 0.002, 0.03, internal=True,
                       root_form_diameter_m=2 * (ring.root_radius_m - 0.0003),
                       tip_form_diameter_m=2 * (ring.tip_radius_m + 0.0003))
        self.assertEqual(limited.root_radius_m, ring.root_radius_m)
        self.assertLess(limited.involute_roll_bounds_m[1], ring.involute_roll_bounds_m[1])
        with self.assertRaises(ValueError):
            Gear(24, 0.002, 0.025, root_form_diameter_m=0.09)
        with self.assertRaises(ValueError):
            Gear(72, 0.002, 0.03, internal=True, root_form_diameter_m=0.13, tip_form_diameter_m=0.14)

    def test_base_circle_singularity_is_explicit_geometry(self):
        pair = GearPair(Gear(20, 0.002, 0.02), Gear(60, 0.002, 0.02, internal=True))
        grid = contact_grid(pair, 0.5, 5)
        self.assertTrue(grid.has_singular_curvature)
        self.assertTrue(np.any(grid.radius_pinion_m == 0))
        self.assertTrue(np.any(np.isinf(grid.curvature_per_m)))

    def test_internal_defaults_and_shifted_center_are_transparent(self):
        p, w = Gear(24, 0.002, 0.025, profile_shift=0.1), Gear(72, 0.002, 0.025, internal=True, profile_shift=0.3)
        self.assertAlmostEqual(w.tip_radius_m, w.reference_radius_m - 0.002 * (1 - 0.3))
        self.assertAlmostEqual(w.root_radius_m, w.reference_radius_m + 0.002 * (1.25 + 0.3))
        pair = GearPair(p, w)
        inverse = lambda angle: math.tan(angle) - angle
        expected = inverse(p.transverse_pressure_angle_rad) + 2 * (0.3 - 0.1) * math.tan(p.pressure_angle_rad) / (72 - 24)
        self.assertAlmostEqual(inverse(pair.working_pressure_angle_rad), expected)
        self.assertLess(w.tooth_thickness_m(w.reference_radius_m), math.pi * 0.002 / 2)

    def test_shifted_nominal_center_and_thickness(self):
        p, w = Gear(24, 0.002, 0.025, profile_shift=0.3), Gear(48, 0.002, 0.025, profile_shift=0.1)
        pair = GearPair(p, w)
        self.assertGreater(pair.center_distance_m, p.reference_radius_m + w.reference_radius_m)
        self.assertGreater(p.tooth_thickness_m(p.reference_radius_m), math.pi * 0.002 / 2)
        radii = np.linspace(p.root_radius_m, p.tip_radius_m, 31)
        self.assertTrue(np.all(np.isfinite(p.tooth_thickness_m(radii))))

    def test_input_domains(self):
        with self.assertRaises(ValueError):
            Gear(0, 0.002, 0.02)
        with self.assertRaises(ValueError):
            GearPair(Gear(24, 0.002, 0.02, helix_angle_rad=0.2), Gear(48, 0.002, 0.02, helix_angle_rad=0.2))
        with self.assertRaises(ValueError):
            external(offset=1)
        with self.assertRaises(ValueError):
            contact_grid(external(), float("nan"))
        with self.assertRaises(ValueError):
            contact_grid(external(), 0.1, strips=0)
        with self.assertRaises(ValueError):
            external().pinion.tooth_thickness_m(1)


if __name__ == "__main__":
    unittest.main()
