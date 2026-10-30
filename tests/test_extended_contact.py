"""延伸接触的材料坐标、N/N+1布局、镜像和参数保护。"""
import unittest

import numpy as np

from gear_contact import Gear, GearPair
from gear_contact.extended_contact import ExtendedContactSettings, extended_contact_grid


def pair(beta=-.3, *, internal=False, scale=1.):
    return GearPair(Gear(28, .0025*scale, .025*scale, helix_angle_rad=beta),
        Gear(84 if internal else 56, .0025*scale, .025*scale,
             helix_angle_rad=beta if internal else -beta, internal=internal))


class ExtendedContactTests(unittest.TestCase):
    def test_layout_and_ordinary_intercept_use_current_geometric_phase(self):
        p = pair()
        phase = .173
        result = extended_contact_grid(p, phase, 11, settings=ExtendedContactSettings(.15))
        self.assertEqual(len(result.line_offsets), len(result.endpoints.line_offsets))
        np.testing.assert_array_equal(np.diff(result.line_offsets), 11)
        np.testing.assert_array_equal(np.diff(result.endpoints.line_offsets), 12)
        self.assertTrue(np.all(result.grid.widths_m > 0))
        ordinary = ~(result.centre_extended_pinion | result.centre_extended_wheel)
        q = result.grid.roll_pinion_m[ordinary]
        z = result.grid.face_coordinate_m[ordinary]
        intercept = q-np.tan(p.base_helix_angle_rad)*z
        origin = p.contact_roll_bounds_m[0]+(phase+.5)*p.base_pitch_m
        expected = origin+result.grid.tooth_pair_index[ordinary]*p.base_pitch_m
        np.testing.assert_allclose(intercept, expected, rtol=0, atol=1e-13)
        np.testing.assert_array_equal(result.gap_correction_m[ordinary], 0.)
        for name in ("profile_factor_pinion", "profile_factor_wheel", "lead_factor_pinion", "lead_factor_wheel"):
            values = getattr(result.grid, name)
            self.assertTrue(np.all((values >= 0)&(values <= 1)))

    def test_handedness_mirrors_material_coordinates(self):
        positive, negative = pair(.3), pair(-.3)
        settings = ExtendedContactSettings(.15)
        a = extended_contact_grid(positive, .173, 11, settings=settings)
        b = extended_contact_grid(negative, .173, 11, settings=settings)
        for index in np.unique(a.grid.tooth_pair_index):
            ma, mb = a.grid.tooth_pair_index == index, b.grid.tooth_pair_index == index
            np.testing.assert_allclose(a.grid.face_coordinate_m[ma], -b.grid.face_coordinate_m[mb][::-1], atol=1e-12)
            np.testing.assert_allclose(a.grid.roll_pinion_m[ma], b.grid.roll_pinion_m[mb][::-1], atol=1e-12)
            np.testing.assert_allclose(a.gap_correction_m[ma], b.gap_correction_m[mb][::-1], atol=1e-12)

    def test_internal_partner_roll_and_curvature_keep_difference_sign(self):
        p = pair(internal=True)
        result = extended_contact_grid(p, .217, 9, settings=ExtendedContactSettings(.15))
        ordinary = ~(result.centre_extended_pinion | result.centre_extended_wheel)
        span = p.center_distance_m*np.sin(p.working_pressure_angle_rad)
        np.testing.assert_allclose(result.grid.roll_wheel_m[ordinary]-result.grid.roll_pinion_m[ordinary], span, atol=1e-13)
        actual = 1/result.grid.radius_pinion_m-1/result.grid.radius_wheel_m
        np.testing.assert_allclose(result.grid.curvature_per_m, actual, rtol=1e-13)

    def test_length_similarity_keeps_factors_and_scales_correction(self):
        p, large = pair(), pair(scale=2.)
        settings = ExtendedContactSettings(.15, root_tolerance_policy="dimensionless_refined")
        a = extended_contact_grid(p, .173, 11, settings=settings)
        b = extended_contact_grid(large, .173, 11, settings=settings)
        np.testing.assert_array_equal(a.line_offsets, b.line_offsets)
        np.testing.assert_allclose(b.grid.roll_pinion_m, a.grid.roll_pinion_m*2, atol=1e-11)
        np.testing.assert_allclose(b.grid.widths_m, a.grid.widths_m*2, atol=1e-11)
        np.testing.assert_allclose(b.gap_correction_m, a.gap_correction_m*2, atol=1e-11)
        np.testing.assert_allclose(b.grid.profile_factor_pinion, a.grid.profile_factor_pinion, atol=1e-9)

    def test_spur_default_and_invalid_configuration_are_explicit(self):
        result = extended_contact_grid(pair(0.), .17, 7, settings=ExtendedContactSettings())
        self.assertGreater(len(result.grid.widths_m), 0)
        with self.assertRaises(ValueError):
            extended_contact_grid(pair(), .17, 7, settings=ExtendedContactSettings())
        with self.assertRaises(ValueError):
            ExtendedContactSettings(face_extension_factor=0.)
        with self.assertRaises(ValueError):
            extended_contact_grid(pair(), float("nan"), 7, settings=ExtendedContactSettings(.1))
        with self.assertRaises(ValueError):
            extended_contact_grid(pair(), .17, True, settings=ExtendedContactSettings(.1))


if __name__ == "__main__":
    unittest.main()
