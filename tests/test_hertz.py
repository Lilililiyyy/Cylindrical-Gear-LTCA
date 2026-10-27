"""独立核验 Hertz 压力积分、局部能量、导数、尺度和适用域。"""
import unittest

import numpy as np

from gear_contact.elasticity import Material
from gear_contact.hertz import (effective_modulus_pa, hertz_line_contact,
                                local_line_approach, local_line_complementary_energy)


class HertzTests(unittest.TestCase):
    def setUp(self):
        self.steel = Material(210e9, 0.3)
        self.other = Material(110e9, 0.27)

    def test_pressure_integral_and_standard_modulus(self):
        q = np.array([1e4, 5e4, 1e5])
        curvature = 120.0
        result = hertz_line_contact(q, curvature, self.steel, self.other)
        inverse_e = ((1 - 0.3**2) / 210e9 + (1 - 0.27**2) / 110e9)
        self.assertAlmostEqual(effective_modulus_pa(self.steel, self.other) * inverse_e, 1)
        # x=b sinθ 后积分被积函数光滑，可独立还原给定法向线载荷。
        theta = np.linspace(-np.pi / 2, np.pi / 2, 20001)
        for load, half_width, pressure in zip(q, result.half_width_m, result.maximum_pressure_pa):
            recovered = np.trapz(pressure * half_width * np.cos(theta)**2, theta)
            self.assertAlmostEqual(recovered / load, 1, places=12)

    def test_material_exchange_and_sqrt_load_scaling(self):
        a = hertz_line_contact(2e4, 100, self.steel, self.other)
        b = hertz_line_contact(8e4, 100, self.other, self.steel)
        self.assertAlmostEqual(float(b.half_width_m / a.half_width_m), 2)
        self.assertAlmostEqual(float(b.maximum_pressure_pa / a.maximum_pressure_pa), 2)

    def test_independent_dimensioned_example(self):
        # 两相同材料圆柱：R₁=10mm、R₂=20mm、q=30kN/m。
        # 先以手算定义的 E*=E/[2(1−ν²)] 生成独立标量预期值。
        e_star = 210e9 / (2 * (1 - 0.3**2))
        half_width = (4 * 30000 / (np.pi * e_star * 150))**0.5
        result = hertz_line_contact(30000, 150, self.steel, self.steel)
        self.assertAlmostEqual(float(result.half_width_m / half_width), 1)
        self.assertAlmostEqual(float(result.maximum_pressure_pa * np.pi * half_width / 60000), 1)

    def test_local_derivative_and_energy_gradient(self):
        force = np.array([2.0, 10.0, 90.0])
        kwargs = dict(widths_m=0.002, radius_pinion_m=0.01, radius_wheel_m=0.03,
                      material_pinion=self.steel, material_wheel=self.other,
                      reference_lengths_m=(0.005, 0.008))
        approach, derivative = local_line_approach(force, **kwargs)
        step = force * 1e-5
        plus = local_line_approach(force + step, **kwargs)[0]
        minus = local_line_approach(force - step, **kwargs)[0]
        np.testing.assert_allclose((plus - minus) / (2 * step), derivative, rtol=2e-9)
        e_plus = local_line_complementary_energy(force + step, **kwargs)
        e_minus = local_line_complementary_energy(force - step, **kwargs)
        np.testing.assert_allclose((e_plus - e_minus) / (2 * step), approach, rtol=2e-9)
        self.assertTrue(np.all(derivative > 0))

    def test_zero_force_limit(self):
        h, dh = local_line_approach([0, 1e-20], 0.002, 0.01, 0.02)
        self.assertEqual(h[0], 0)
        self.assertTrue(np.isposinf(dh[0]))
        self.assertGreater(h[1], 0)
        self.assertEqual(float(local_line_complementary_energy(0, 0.002, 0.01, 0.02)), 0)
        zero = hertz_line_contact(0, 100)
        self.assertEqual(zero.half_width_m, 0)
        self.assertEqual(zero.maximum_pressure_pa, 0)

    def test_line_partition_and_geometry_similarity(self):
        h, dh = local_line_approach(60.0, 0.004, 0.01, 0.02)
        split_h, split_dh = local_line_approach(30.0, 0.002, 0.01, 0.02)
        self.assertAlmostEqual(float(split_h / h), 1)
        self.assertAlmostEqual(float(split_dh / dh), 2)
        # 全部长度 ×s、力 ×s²，对应压力保持不变且位移 ×s。
        scale = 3
        scaled = local_line_approach(60 * scale**2, 0.004 * scale,
                                     0.01 * scale, 0.02 * scale)[0]
        self.assertAlmostEqual(float(scaled / h), scale)

    def test_internal_curvature_and_reference_depth_are_explicit(self):
        external = hertz_line_contact(3e4, 1 / 0.01 + 1 / 0.03)
        internal = hertz_line_contact(3e4, 1 / 0.01 - 1 / 0.03)
        self.assertGreater(internal.half_width_m, external.half_width_m)
        h1 = local_line_approach(20, 0.003, 0.01, 0.03, curvature_per_m=1 / 0.01 - 1 / 0.03)[0]
        h2 = local_line_approach(20, 0.003, 0.01, 0.03, curvature_per_m=1 / 0.01 - 1 / 0.03,
                                 reference_lengths_m=(0.005, 0.01))[0]
        self.assertGreater(h1, h2)

    def test_invalid_geometry_material_and_large_contact(self):
        for e, nu in ((0, 0.3), (210e9, 0.5), (np.inf, 0.3)):
            with self.assertRaises(ValueError):
                Material(e, nu)
        with self.assertRaises(ValueError):
            hertz_line_contact(100, -1)
        with self.assertRaises(ValueError):
            hertz_line_contact(-100, 10)
        with self.assertRaisesRegex(ValueError, "适用域"):
            local_line_approach(1e9, 0.001, 0.01, 0.02)


if __name__ == "__main__":
    unittest.main()
