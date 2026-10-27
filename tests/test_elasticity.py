"""由闭式梁解、能量互易和空间网格性质独立核验结构柔度。"""
from types import SimpleNamespace
import unittest

import numpy as np

from gear_contact.elasticity import Material, build_structural_compliance


class RectangularTooth:
    """仅用于闭式核验的恒截面径向悬臂，不借用渐开线公式。"""
    def __init__(self, *, internal=False, thickness=0.003, scale=1):
        self.internal = internal
        self.root_radius_m = (0.03 if internal else 0.02) * scale
        self.tip_radius_m = (0.02 if internal else 0.03) * scale
        self.base_radius_m = 0.015 * scale
        self.thickness = thickness * scale

    def tooth_thickness_m(self, radius):
        return np.full_like(np.asarray(radius, dtype=float), self.thickness)


def beam_case(count=5, *, internal=False, scale=1, helix=0.0):
    a = RectangularTooth(scale=scale)
    b = RectangularTooth(internal=internal, scale=scale)
    pair = SimpleNamespace(pinion=a, wheel=b, base_helix_angle_rad=helix)
    radius = 0.025 * scale
    grid = SimpleNamespace(
        widths_m=np.full(count, 0.012 * scale / count / np.cos(helix)),
        face_coordinate_m=((np.arange(count) + 0.5) / count - 0.5) * 0.012 * scale,
        tooth_pair_index=np.zeros(count, dtype=int),
        roll_pinion_m=np.full(count, np.sqrt(radius**2 - a.base_radius_m**2)),
        roll_wheel_m=np.full(count, np.sqrt(radius**2 - b.base_radius_m**2)),
    )
    return pair, grid


class ElasticityTests(unittest.TestCase):
    def setUp(self):
        self.material = Material(210e9, 0.3)

    def test_rectangular_cantilever_closed_form(self):
        pair, grid = beam_case(count=3)
        matrix, diagnostics = build_structural_compliance(pair, grid, self.material,
                                                         self.material, mode="independent")
        height, thickness = 0.005, 0.003
        width = 0.012 / 3
        cos_alpha = 0.015 / 0.025
        e, g = 210e9, 210e9 / 2.6
        area, inertia = width * thickness, width * thickness**3 / 12
        expected = (cos_alpha**2 * (height**3 / (3 * e * inertia)
                                    + height / ((5 / 6) * g * area))
                    + (1 - cos_alpha**2) * height / (e * area))
        np.testing.assert_allclose(matrix, np.eye(3) * 2 * expected, rtol=2e-14, atol=0)
        self.assertFalse(diagnostics["local_contact_included"])

    def test_inner_tooth_points_inward(self):
        ext, grid_ext = beam_case(internal=False)
        inner, grid_inner = beam_case(internal=True)
        a = build_structural_compliance(ext, grid_ext, mode="independent")[0]
        b = build_structural_compliance(inner, grid_inner, mode="independent")[0]
        np.testing.assert_allclose(a, b, rtol=3e-14)

    def test_symmetry_positive_energy_and_reciprocity(self):
        pair, grid = beam_case(count=7)
        # 非均匀接触高度可检验不同形函数组成的耦合能。
        radius = np.linspace(0.023, 0.027, 7)
        grid.roll_pinion_m = np.sqrt(radius**2 - pair.pinion.base_radius_m**2)
        matrix, _ = build_structural_compliance(pair, grid)
        np.testing.assert_allclose(matrix, matrix.T, rtol=0, atol=1e-23)
        self.assertTrue(np.all(np.linalg.eigvalsh(matrix) > 0))
        rng = np.random.default_rng(11)
        force_a, force_b = rng.normal(size=(2, 7))
        self.assertAlmostEqual(float(force_a @ matrix @ force_b),
                               float(force_b @ matrix @ force_a), places=20)
        self.assertGreater(float(force_a @ matrix @ force_a), 0)

    def test_coupling_preserves_uniform_mode_and_reduces_gradient_energy(self):
        pair, grid = beam_case(count=9)
        independent = build_structural_compliance(pair, grid, mode="independent")[0]
        coupled = build_structural_compliance(pair, grid, mode="coupled")[0]
        uniform = np.ones(9)
        np.testing.assert_allclose(coupled @ uniform, independent @ uniform, rtol=1e-12)
        alternating = np.array([1, -1, 1, -1, 1, -1, 1, -1, 1.0])
        self.assertLess(alternating @ coupled @ alternating,
                        alternating @ independent @ alternating)
        self.assertGreater(coupled[0, 1], 0)

    def test_load_partition_is_mesh_independent_for_uniform_tooth(self):
        displacements = []
        for count in (3, 7, 17):
            pair, grid = beam_case(count=count)
            matrix, _ = build_structural_compliance(pair, grid)
            displacement = matrix @ np.full(count, 1000 / count)
            np.testing.assert_allclose(displacement, np.full(count, displacement.mean()), rtol=1e-11)
            displacements.append(displacement.mean())
        np.testing.assert_allclose(displacements, np.full(3, displacements[0]), rtol=1e-11)

    def test_material_and_geometric_scaling(self):
        pair, grid = beam_case(count=5)
        base = build_structural_compliance(pair, grid)[0]
        stiff = Material(420e9, 0.3)
        doubled_e = build_structural_compliance(pair, grid, stiff, stiff)[0]
        np.testing.assert_allclose(doubled_e, base / 2, rtol=1e-13)
        scaled_pair, scaled_grid = beam_case(count=5, scale=3)
        scaled = build_structural_compliance(scaled_pair, scaled_grid)[0]
        np.testing.assert_allclose(scaled, base / 3, rtol=1e-12)

    def test_different_teeth_are_not_coupled(self):
        pair, grid = beam_case(count=6)
        grid.tooth_pair_index[3:] = 1
        matrix, _ = build_structural_compliance(pair, grid)
        np.testing.assert_array_equal(matrix[:3, 3:], np.zeros((3, 3)))

    def test_helix_projection_and_invalid_inputs(self):
        pair_a, grid_a = beam_case(count=4)
        pair_b, grid_b = beam_case(count=4, helix=0.3)
        a = build_structural_compliance(pair_a, grid_a, mode="independent")[0]
        b = build_structural_compliance(pair_b, grid_b, mode="independent")[0]
        np.testing.assert_allclose(b, a * np.cos(0.3)**2, rtol=1e-14)
        with self.assertRaises(ValueError):
            build_structural_compliance(pair_a, grid_a, mode="invalid")
        grid_a.widths_m[0] = 0
        with self.assertRaises(ValueError):
            build_structural_compliance(pair_a, grid_a)

    def test_involute_sections_quadrature_and_positive_energy(self):
        from gear_contact.geometry import Gear, GearPair, contact_grid

        for internal, beta in ((False, 0.3), (True, 0.25)):
            pair = GearPair(
                Gear(24, 0.002, 0.025, helix_angle_rad=beta),
                Gear(72, 0.002, 0.030, internal=internal,
                     helix_angle_rad=beta if internal else -beta), axial_offset_m=0.001)
            for phase in (0.0, 0.37, 0.81):
                grid = contact_grid(pair, phase, strips=7)
                coarse = build_structural_compliance(pair, grid, quadrature_points=16)[0]
                fine = build_structural_compliance(pair, grid, quadrature_points=64)[0]
                relative = np.linalg.norm(coarse - fine) / np.linalg.norm(fine)
                self.assertLess(relative, 2e-6)
                self.assertTrue(np.all(np.linalg.eigvalsh(fine) > 0))


if __name__ == "__main__":
    unittest.main()
