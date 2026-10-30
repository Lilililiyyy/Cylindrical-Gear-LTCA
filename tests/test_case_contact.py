"""同案例接触对标必须保留物理相位、中心/端点布局及原载荷。"""
import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

import numpy as np

from gear_contact import analyze_config

PROJECT = next(p for p in Path(__file__).resolve().parents
               if (p/"pyproject.toml").is_file() and (p/"gear_contact").is_dir())
SPEC = importlib.util.spec_from_file_location("case_contact_plotting", PROJECT/"examples/case_contact_plotting.py")
PLOT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PLOT)


class CaseContactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        reference = PROJECT/"examples/masta_reference"
        cls.metadata = json.loads((reference/"showcase_contact.json").read_text(encoding="utf-8"))
        with np.load(reference/"showcase_contact.npz", allow_pickle=False) as arrays:
            cls.arrays = {k: arrays[k].copy() for k in arrays.files}
        case = next(c for c in json.loads((reference/"cases.json").read_text(encoding="utf-8"))["cases"]
                    if c["case_id"] == cls.metadata["case_id"])
        config = copy.deepcopy(case["config"])
        config.update(strips=9, phase_offset=cls.metadata["phase_registration"]["phase_offset"])
        cls.extended_config = copy.deepcopy(config)
        config.pop("iso_settings", None)
        config.pop("extended_contact_settings", None)
        config.update(elastic_mode="coupled", local_contact=True)
        cls.result = analyze_config(config)
        cls.prepared = PLOT.prepare_case_contact(cls.result, cls.metadata, cls.arrays)

    def test_geometric_phase_and_actual_tooth_are_preserved(self):
        metrics = self.prepared["metrics"]
        self.assertEqual(metrics["source_pinion_tooth_id"], 14)
        self.assertEqual(metrics["source_wheel_tooth_id"], 62)
        self.assertEqual(metrics["project_tooth_pair_index"], 0)
        self.assertLess(metrics["maximum_phase_registration_error_cycles"], 1e-12)
        self.assertLess(metrics["source_ordinary_length_anchor_spread_m"], 1e-12)
        self.assertEqual(self.prepared["cycle"].shape, (32, 11))
        np.testing.assert_array_equal(self.prepared["cycle"][:, 0], np.arange(32)/32)
        self.assertLess(self.prepared["cycle"][-1, 1], self.prepared["cycle"][0, 1])

    def test_source_endpoint_band_does_not_get_rescaled_to_original_strip_force(self):
        data = self.prepared
        es, cs = data["endpoint_slice"], data["centre_slice"]
        self.assertEqual(len(data["source_peak_pa"]), 41)
        self.assertEqual(len(self.arrays["centre_force_n"][cs]), 40)
        np.testing.assert_array_equal(data["source_peak_pa"], self.arrays["endpoint_pressure_pa"][es])
        np.testing.assert_array_equal(data["source_half_width_m"], self.arrays["endpoint_half_width_m"][es])
        metrics = data["metrics"]
        self.assertAlmostEqual(metrics["reference_tooth_force_n"], 104.67288786127492, places=9)
        self.assertAlmostEqual(metrics["reference_endpoint_peak_pressure_pa"], 186548549.52368718, places=4)
        self.assertAlmostEqual(metrics["reference_hertz_band_integral_n"], 104.67002170506565, places=8)
        self.assertNotEqual(metrics["reference_tooth_force_n"], metrics["reference_hertz_band_integral_n"])
        self.assertLessEqual(float(data["source_pressure_pa"].max()), metrics["reference_endpoint_peak_pressure_pa"])

    def test_selected_material_tooth_has_same_ordinary_line_intercept(self):
        data = self.prepared
        cs = data["centre_slice"]
        normal = ~(self.arrays["centre_extended_pinion"][cs] | self.arrays["centre_extended_wheel"][cs])
        slope = np.tan(self.result.pair.base_helix_angle_rad)
        intercept = (self.arrays["centre_roll_pinion_m"][cs][normal]
                     - slope*self.arrays["centre_face_coordinate_m"][cs][normal])
        own = self.result.rotations[data["rotation_index"]].grid
        selected = data["own_mask"]
        own_intercept = own.roll_pinion_m[selected]-slope*own.face_coordinate_m[selected]
        np.testing.assert_allclose(own_intercept, np.mean(intercept), rtol=0., atol=1e-12)

    def test_project_band_keeps_original_cell_force_and_zero_half_width_is_zero(self):
        data = self.prepared
        metric = data["metrics"]
        self.assertAlmostEqual(metric["project_hertz_band_integral_n"], metric["project_tooth_force_n"], places=9)
        self.assertEqual(data["project_pressure_pa"].shape[0], len(data["project_force_n"]))
        pressure = PLOT._band_values(np.array([0., 10.]), np.array([0., 2e-6]), np.linspace(-3e-6, 3e-6, 20))
        self.assertTrue(np.all(pressure[0] == 0.))
        self.assertTrue(np.all(np.isfinite(pressure)))

    def test_wrong_phase_is_rejected_without_realigning_by_response(self):
        result = copy.copy(self.result)
        result.phase = (self.result.phase+.1) % 1
        with self.assertRaises(ValueError):
            PLOT.prepare_case_contact(result, self.metadata, self.arrays)

    def test_preparation_leaves_original_reference_arrays_unchanged(self):
        before = {k: v.copy() for k, v in self.arrays.items()}
        PLOT.prepare_case_contact(self.result, self.metadata, self.arrays)
        for key in before:
            np.testing.assert_array_equal(before[key], self.arrays[key])

    def test_extended_line_uses_true_length_and_keeps_endpoint_and_centre_values_separate(self):
        # 前两点为普通域，末点沿曲线延伸；face/cos不能代表末段真实线长。
        cosine = .8
        geometry = SimpleNamespace(line_offsets=np.array([0, 3]),
            centre_extended_pinion=np.array([False, False, True]),
            centre_extended_wheel=np.zeros(3, dtype=bool),
            endpoints=SimpleNamespace(line_offsets=np.array([0, 4]),
                face_coordinate_m=np.array([0., .0032, .0064, .0066]),
                extended_pinion=np.array([False, False, False, True]),
                extended_wheel=np.zeros(4, dtype=bool)))
        peak = np.array([0., 12., 25., 0.])
        half = np.array([0., 1e-6, 1.5e-6, 0.])
        endpoints = {"pressure_pa": peak, "half_width_m": half,
            "line_load_n_per_m": np.pi/2*peak*half}
        rotation = SimpleNamespace(grid=SimpleNamespace(tooth_pair_index=np.zeros(3, int),
            face_coordinate_m=np.array([.0016, .0048, .005]), widths_m=np.full(3, .004)),
            pressure_pa=np.array([10., 20., 30.]), half_width_m=np.full(3, 1e-6),
            line_load_n_per_m=np.array([1., 2., 3.]), solution=SimpleNamespace(forces_n=np.array([.004, .008, .012])),
            contact_geometry_data=geometry, endpoint_pressure=endpoints)
        prepared = PLOT._project_line_samples(rotation, 0, cosine)
        np.testing.assert_allclose(prepared["edges_m"], [0., .004, .008, .012], atol=1e-16)
        self.assertGreater(abs(prepared["intervals_m"][-1].mean()-.005/cosine), .003)
        np.testing.assert_array_equal(prepared["peak_pa"], [10., 20., 30.])
        np.testing.assert_array_equal(prepared["endpoints"]["pressure_pa"], peak)
        self.assertLess(prepared["ordinary_anchor_spread_m"], 1e-16)
        rotation.endpoint_pressure = dict(endpoints, pressure_pa=peak[:-1])
        with self.assertRaises(ValueError):
            PLOT._project_line_samples(rotation, 0, cosine)

    def test_extended_line_without_ordinary_anchor_is_rejected(self):
        rotation = SimpleNamespace(grid=SimpleNamespace(tooth_pair_index=np.zeros(2, int),
            face_coordinate_m=np.array([.001, .002]), widths_m=np.full(2, .004)),
            contact_geometry_data=SimpleNamespace(line_offsets=np.array([0, 2]),
                centre_extended_pinion=np.ones(2, dtype=bool), centre_extended_wheel=np.zeros(2, dtype=bool),
                endpoints=SimpleNamespace(line_offsets=np.array([0, 3]),
                    face_coordinate_m=np.array([0., .001, .002]),
                    extended_pinion=np.ones(3, dtype=bool), extended_wheel=np.zeros(3, dtype=bool))),
            endpoint_pressure=None)
        with self.assertRaises(ValueError):
            PLOT._project_line_samples(rotation, 0, .8)

    def test_endpoint_cycle_peak_is_used_without_overwriting_centre_diagnostics(self):
        result = copy.copy(self.result)
        result.rotations = list(self.result.rotations)
        rotation = copy.copy(result.rotations[0])
        ids = rotation.grid.tooth_pair_index
        offsets = np.r_[0, np.flatnonzero(np.diff(ids))+1, len(ids)]
        endpoint_offsets = np.r_[0, np.cumsum(np.diff(offsets)+1)]
        endpoint_faces = np.concatenate([np.r_[
            rotation.grid.face_coordinate_m[a]-rotation.grid.widths_m[a]*np.cos(result.pair.base_helix_angle_rad)/2,
            rotation.grid.face_coordinate_m[a:b]+rotation.grid.widths_m[a:b]*np.cos(result.pair.base_helix_angle_rad)/2]
            for a, b in zip(offsets[:-1], offsets[1:])])
        rotation.contact_geometry_data = SimpleNamespace(line_offsets=offsets,
            centre_extended_pinion=np.zeros(len(ids), dtype=bool),
            centre_extended_wheel=np.zeros(len(ids), dtype=bool),
            endpoints=SimpleNamespace(line_offsets=endpoint_offsets, face_coordinate_m=endpoint_faces,
                extended_pinion=np.zeros(len(endpoint_faces), dtype=bool),
                extended_wheel=np.zeros(len(endpoint_faces), dtype=bool)))
        count = int(endpoint_offsets[-1])
        rotation.endpoint_pressure = {"pressure_pa": np.full(count, 15e6),
            "half_width_m": np.full(count, 1e-6),
            "line_load_n_per_m": np.full(count, np.pi/2*15.)}
        result.rotations[0] = rotation
        prepared = PLOT.prepare_case_contact(result, self.metadata, self.arrays)
        metric = prepared["metrics"]
        self.assertEqual(prepared["cycle"][0, 8], 15e6)
        self.assertEqual(metric["project_endpoint_peak_pressure_pa"], 15e6)
        self.assertEqual(metric["project_band_evaluation"], "endpoints")
        self.assertEqual(metric["project_cell_peak_pressure_pa"], self.prepared["metrics"]["project_cell_peak_pressure_pa"])
        self.assertAlmostEqual(metric["project_cell_hertz_band_integral_n"], metric["project_tooth_force_n"], places=9)
        self.assertNotAlmostEqual(metric["project_hertz_band_integral_n"], metric["project_tooth_force_n"], places=3)

    def test_coarse_extended_cells_crossing_transition_use_independent_endpoints(self):
        result = analyze_config(self.extended_config)
        prepared = PLOT.prepare_case_contact(result, self.metadata, self.arrays)
        self.assertEqual(prepared["metrics"]["project_band_evaluation"], "endpoints")
        self.assertLess(prepared["metrics"]["project_ordinary_length_anchor_spread_m"], 1e-12)
        self.assertAlmostEqual(prepared["metrics"]["project_cell_hertz_band_integral_n"],
                               prepared["metrics"]["project_tooth_force_n"], places=9)

    def test_three_period_display_preserves_original_values_and_physical_phase_at_seams(self):
        original = self.prepared["cycle"]
        before = original.copy()
        displayed = PLOT.repeat_cycle_for_display(original)
        count = len(original)
        self.assertEqual(displayed.shape, (3*count+1, 11))
        np.testing.assert_array_equal(displayed[:, 0], np.arange(3*count+1)/count)
        for period in range(3):
            np.testing.assert_array_equal(displayed[period*count:(period+1)*count, 1:], original[:, 1:])
            np.testing.assert_array_equal(displayed[period*count, 1:], original[0, 1:])
        np.testing.assert_array_equal(displayed[-1, 1:], original[0, 1:])
        np.testing.assert_array_equal(original, before)
        self.assertEqual(displayed[-1, 0], 3.)

    def test_periodic_display_rejects_partial_nonuniform_or_nonfinite_cycle(self):
        original = self.prepared["cycle"]
        for periods in (0, -1, 1.5, True):
            with self.assertRaises(ValueError):
                PLOT.repeat_cycle_for_display(original, periods)
        for changed in (original[:-1], original[::2][1:], original[:1]):
            with self.assertRaises(ValueError):
                PLOT.repeat_cycle_for_display(changed)
        changed = original.copy()
        changed[1, 3] = np.nan
        with self.assertRaises(ValueError):
            PLOT.repeat_cycle_for_display(changed)


if __name__ == "__main__":
    unittest.main()
