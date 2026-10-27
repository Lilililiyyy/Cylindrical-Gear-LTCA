"""修形量、插值方向、测量越界和复合曲面的解析检验。"""
import unittest

import numpy as np

from gear_contact.surfaces import SurfaceModification, MeasuredCurve, MeasuredSurface, CompositeModification


class SurfaceTests(unittest.TestCase):
    def test_crown_is_edge_removal(self):
        surface = SurfaceModification(profile_crown_m=8e-6, lead_crown_m=12e-6)
        self.assertEqual(float(surface.evaluate(0.5, 0.5)), 0)
        self.assertAlmostEqual(float(surface.evaluate(0, 0)), 20e-6)
        self.assertAlmostEqual(float(surface.evaluate(0.5, 1)), 12e-6)

    def test_slope_directions_and_bias(self):
        positive = SurfaceModification(lead_slope_m=10e-6)
        negative = SurfaceModification(lead_slope_m=-10e-6)
        np.testing.assert_allclose(positive.evaluate(0.5, [0, 1]), [0, 10e-6])
        np.testing.assert_allclose(negative.evaluate(0.5, [0, 1]), [10e-6, 0])
        twist = SurfaceModification(bias_m=6e-6)
        np.testing.assert_allclose(twist.evaluate([0, 0, 1, 1], [0, 1, 0, 1]), [6e-6, 0, 0, 6e-6])

    def test_tip_root_and_end_transitions(self):
        surface = SurfaceModification(tip_relief_m=8e-6, tip_start=0.8, root_relief_m=4e-6, root_end=0.2, end_relief_m=3e-6, end_fraction=0.1)
        np.testing.assert_allclose(surface.evaluate([0, 0.2, 0.8, 0.9, 1], 0.5), [4e-6, 0, 0, 2e-6, 8e-6], atol=1e-18)
        np.testing.assert_allclose(surface.evaluate(0.5, [0, 0.05, 0.1, 0.9, 1]), [3e-6, 0.75e-6, 0, 0, 3e-6], atol=1e-18)

    def test_curve_linear_interpolation_and_sign(self):
        curve = MeasuredCurve([0, 0.3, 1], [-2e-6, 1e-6, 8e-6])
        np.testing.assert_allclose(curve.evaluate([0, 0.2, 0.6, 1], 0.4), [-2e-6, 0, 4e-6, 8e-6], atol=1e-18)
        lead = MeasuredCurve([0, 1], [0, 8e-6], axis="lead")
        np.testing.assert_allclose(lead.evaluate([0, 0.5], 0.25), [2e-6, 2e-6])

    def test_curve_bounds_are_explicit(self):
        curve = MeasuredCurve([0.2, 0.8], [2e-6, 8e-6])
        with self.assertRaises(ValueError):
            curve.evaluate(0.1, 0.5)
        clipped = MeasuredCurve([0.2, 0.8], [2e-6, 8e-6], bounds="clip")
        extrapolated = MeasuredCurve([0.2, 0.8], [2e-6, 8e-6], bounds="extrapolate")
        np.testing.assert_allclose(clipped.evaluate([0, 1], 0.5), [2e-6, 8e-6])
        np.testing.assert_allclose(extrapolated.evaluate([0, 1], 0.5), [0, 10e-6], atol=1e-18)

    def test_bilinear_surface_exact_polynomial(self):
        p, l = np.array([0, 0.4, 1]), np.array([0, 0.7, 1])
        function = lambda p, l: (2 + 3 * p - 4 * l + 7 * p * l) * 1e-6
        surface = MeasuredSurface(p, l, function(p[:, None], l[None, :]))
        q, r = np.array([0.1, 0.4, 0.8]), np.array([0.2, 0.5, 0.9])
        np.testing.assert_allclose(surface.evaluate(q, r), function(q, r), atol=1e-18)
        self.assertAlmostEqual(float(surface.evaluate(1, 1)), function(1, 1))

    def test_surface_bounds_and_composition(self):
        surface = MeasuredSurface([0.2, 0.8], [0.1, 0.9], [[0, 1e-6], [2e-6, 3e-6]])
        with self.assertRaises(ValueError):
            surface.evaluate(0, 0.5)
        clipped = MeasuredSurface([0.2, 0.8], [0.1, 0.9], [[0, 1e-6], [2e-6, 3e-6]], bounds="clip")
        self.assertEqual(float(clipped.evaluate(0, 0)), 0)
        base = SurfaceModification(lead_crown_m=8e-6)
        residual = MeasuredCurve([0, 1], [1e-6, 3e-6])
        compound = CompositeModification((base, residual))
        self.assertAlmostEqual(float(compound.evaluate(0.5, 0.5)), 2e-6)
        np.testing.assert_allclose(CompositeModification(()).evaluate([0, 1], 0.5), [0, 0])

    def test_validation_and_broadcast(self):
        surface = SurfaceModification(profile_crown_m=1e-6)
        self.assertEqual(surface.evaluate(np.array([0, 0.5, 1])[:, None], [0, 1]).shape, (3, 2))
        for invalid in (-0.01, 1.01, float("nan")):
            with self.assertRaises(ValueError):
                surface.evaluate(invalid, 0.5)
        with self.assertRaises(ValueError):
            SurfaceModification(lead_crown_m=-1)
        with self.assertRaises(ValueError):
            MeasuredCurve([0, 0], [0, 1])
        with self.assertRaises(ValueError):
            MeasuredSurface([0, 1], [0, 1], [[0, 1]])


if __name__ == "__main__":
    unittest.main()
