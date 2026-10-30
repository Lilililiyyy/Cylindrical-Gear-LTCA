"""端点插值布局、曲率分支及18/77对标采样的附加压力验证。"""
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

import numpy as np

from gear_contact import Material
from gear_contact.contact_pressure import endpoint_line_loads, extended_endpoint_pressure


def layout(widths, centre_offsets, endpoint_offsets, curvature):
    return SimpleNamespace(grid=SimpleNamespace(widths_m=np.asarray(widths, dtype=float)),
        line_offsets=np.asarray(centre_offsets, dtype=int),
        endpoints=SimpleNamespace(line_offsets=np.asarray(endpoint_offsets, dtype=int),
                                  curvature_per_m=np.asarray(curvature, dtype=float)))


class ContactPressureTests(unittest.TestCase):
    def test_nonuniform_linear_load_uses_centres_midpoints_not_cell_boundaries(self):
        widths = np.array([1., 3., 2.])
        centres = np.cumsum(widths)-widths/2
        loads = 2*centres+1
        before = loads.copy()
        endpoints = endpoint_line_loads(widths, loads)
        np.testing.assert_allclose(endpoints, [1., 4., 8.5, 13.], rtol=0., atol=1e-14)
        self.assertNotEqual(endpoints[1], 3.)
        np.testing.assert_array_equal(loads, before)

    def test_endpoint_extrapolation_clips_negative_and_single_strip_has_two_values(self):
        np.testing.assert_array_equal(endpoint_line_loads([1., 1.], [0., 1.]), [0., .5, 1.5])
        np.testing.assert_array_equal(endpoint_line_loads([.003], [42.]), [42., 42.])
        with self.assertRaises(ValueError):
            endpoint_line_loads([], [])
        with self.assertRaises(ValueError):
            endpoint_line_loads([0., 1.], [1., 1.])

    def test_multiple_lines_keep_separate_n_plus_one_layout_and_hertz_load(self):
        extended = layout([.001, .002, .003], [0, 2, 3], [0, 3, 5], np.full(5, 100.))
        forces = np.array([10., 20., 60.])
        result = extended_endpoint_pressure(extended, forces)
        np.testing.assert_allclose(result["line_load_n_per_m"], [10000., 10000., 10000., 20000., 20000.])
        np.testing.assert_allclose(np.pi/2*result["pressure_pa"]*result["half_width_m"],
                                   result["line_load_n_per_m"], rtol=1e-13)
        self.assertEqual(len(result["pressure_pa"]), 5)
        np.testing.assert_array_equal(forces, [10., 20., 60.])

    def test_zero_load_does_not_repair_or_evaluate_singular_curvature(self):
        extended = layout([.001, .001], [0, 2], [0, 3], [np.nan, 0., -np.inf])
        before = extended.endpoints.curvature_per_m.copy()
        zero = extended_endpoint_pressure(extended, [0., 0.])
        np.testing.assert_array_equal(zero["pressure_pa"], np.zeros(3))
        np.testing.assert_array_equal(zero["half_width_m"], np.zeros(3))
        np.testing.assert_array_equal(extended.endpoints.curvature_per_m, before)
        with self.assertRaises(ValueError):
            extended_endpoint_pressure(extended, [1., 1.])

    def test_invalid_line_layout_cannot_be_silently_flattened(self):
        extended = layout([.001, .001], [0, 2], [0, 2], [100., 100.])
        with self.assertRaises(ValueError):
            extended_endpoint_pressure(extended, [1., 1.])

    def test_actual_18_77_endpoint_postprocessing_matches_same_sampling_definition(self):
        root = next(p for p in Path(__file__).resolve().parents
                    if (p/"pyproject.toml").is_file() and (p/"gear_contact").is_dir())
        reference = root/"examples/masta_reference"
        with np.load(reference/"showcase_contact.npz", allow_pickle=False) as values:
            line_end = int(values["rotation_line_offsets"][1])
            centre_end = int(values["centre_offsets"][line_end])
            endpoint_end = int(values["endpoint_offsets"][line_end])
            extended = layout(values["centre_width_m"][:centre_end], values["centre_offsets"][:line_end+1],
                values["endpoint_offsets"][:line_end+1], values["endpoint_curvature_per_m"][:endpoint_end])
            forces = values["centre_force_n"][:centre_end]
            result = extended_endpoint_pressure(extended, forces, Material(207e9, .3), Material(207e9, .3))
            np.testing.assert_allclose(result["line_load_n_per_m"], values["endpoint_line_load_n_per_m"][:endpoint_end],
                                       rtol=2e-12, atol=1e-8)
            np.testing.assert_allclose(result["pressure_pa"], values["endpoint_pressure_pa"][:endpoint_end],
                                       rtol=2e-12, atol=1e-4)
            np.testing.assert_allclose(result["half_width_m"], values["endpoint_half_width_m"][:endpoint_end],
                                       rtol=2e-12, atol=1e-14)


if __name__ == "__main__":
    unittest.main()
