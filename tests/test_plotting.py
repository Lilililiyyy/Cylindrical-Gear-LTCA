"""检查图表使用的物理单位与原始离散接触数据一致。"""
import csv
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

import numpy as np

from gear_contact.analysis import analyze_pair
from gear_contact.geometry import Gear, GearPair
from gear_contact.plotting import (analysis_metrics, plot_analysis, plot_comparison,
                                   _contact_field, _instantaneous_contact_field)
from gear_contact.surfaces import SurfaceModification


class PlottingDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pair = GearPair(Gear(28, .0025, .025), Gear(56, .0025, .025))
        cls.result = analyze_pair(pair, torque_n_m=80., phases=4, strips=3, local_contact=False)

    def test_metric_units_follow_computed_arrays(self):
        values = analysis_metrics(self.result)
        self.assertAlmostEqual(values["te_peak_to_peak_um"],
                               np.ptp(self.result.normal_approach_m) * 1e6)
        self.assertAlmostEqual(values["normal_force_n"],
                               self.result.pair.normal_force_from_torque(80.))
        self.assertGreater(values["maximum_pressure_mpa"], 0)

    def test_plot_exports_original_cells_and_response_units(self):
        with tempfile.TemporaryDirectory(prefix="gear_contact_plot_") as folder:
            files = plot_analysis(self.result, folder)
            self.assertTrue(all(Path(file).is_file() for file in files))
            self.assertEqual(sum(Path(file).suffix == ".svg" for file in files), 4)
            self.assertTrue((Path(folder) / "contact_envelope.svg").is_file())
            with (Path(folder) / "contact_pattern_source.csv").open(encoding="utf-8-sig", newline="") as stream:
                source = list(csv.DictReader(stream))
            self.assertEqual(len({row["phase"] for row in source}), 1)
            self.assertEqual(len({row["tooth_pair_index"] for row in source}), 1)
            with (Path(folder) / "plot_contact_data.csv").open(encoding="utf-8-sig", newline="") as stream:
                cells = list(csv.DictReader(stream))
            self.assertEqual(len(cells), sum(len(r.grid.widths_m) for r in self.result.rotations))
            first = self.result.rotations[0]
            self.assertAlmostEqual(float(cells[0]["line_load_N_per_mm"]),
                                   first.line_load_n_per_m[0] / 1000)
            self.assertAlmostEqual(float(cells[0]["pressure_MPa"]), first.pressure_pa[0] / 1e6)
            self.assertAlmostEqual(float(cells[0]["face_coordinate_mm"]),
                                   first.grid.face_coordinate_m[0] * 1000)
            compare = plot_comparison({"基准": self.result}, Path(folder) / "comparison")
            self.assertTrue(all(Path(file).is_file() for file in compare))

    def test_zero_load_does_not_draw_a_fabricated_contact_patch(self):
        result = analyze_pair(self.result.pair, torque_n_m=0., phases=4, strips=3, local_contact=False)
        with tempfile.TemporaryDirectory(prefix="gear_contact_zero_plot_") as folder:
            plot_analysis(result, folder)
            svg = (Path(folder) / "contact_pattern.svg").read_text(encoding="utf-8")
            self.assertIn("本工况无承载单元", svg)
            with (Path(folder) / "plot_contact_data.csv").open(encoding="utf-8-sig", newline="") as stream:
                cells = list(csv.DictReader(stream))
            self.assertTrue(all(row["active_contact"] == "0" for row in cells))
            self.assertTrue(all(float(row["force_N"]) == 0 for row in cells))

    def test_contact_field_masks_inactive_holes_and_unsampled_edges(self):
        # 已知中心为分离区，边界采样点只覆盖实际绘图域的内矩形。
        x, y = np.meshgrid(np.array([-.5, 0., .5]) * 1e-3,
                           np.array([.5, 1., 1.5]) * 1e-3)
        active = np.ones(9, dtype=bool)
        active[4] = False
        rotation = SimpleNamespace(grid=SimpleNamespace(face_coordinate_m=x.ravel(), roll_pinion_m=y.ravel()),
                                   solution=SimpleNamespace(active_mask=active),
                                   pressure_pa=np.where(active, 100e6, 0.),
                                   line_load_n_per_m=np.where(active, 50e3, 0.))
        result = SimpleNamespace(rotations=[rotation],
                                 pair=SimpleNamespace(face_bounds_m=(-.001, .001), contact_roll_bounds_m=(0., .002)))
        xx, yy, values = _contact_field(result, samples=(81, 81))
        self.assertTrue(values.mask[40, 40].all(), "中心分离孔洞不应被插值填满")
        self.assertTrue(values.mask[:, 0].all(), "不能向采样凸包外推")
        self.assertTrue(values.mask[0].all())
        self.assertGreater(values.count(), 0)
        self.assertGreaterEqual(values.min(), 0.)
        self.assertLessEqual(values[:, :, 0].max(), 100. + 1e-10)
        self.assertLessEqual(values[:, :, 1].max(), 50. + 1e-10)

    def test_low_load_single_strip_contact_remains_visible(self):
        result = analyze_pair(self.result.pair, torque_n_m=.01, phases=8, strips=9,
                              modification_pinion=SurfaceModification(lead_crown_m=20e-6))
        self.assertTrue(any(np.any(r.solution.active_mask) for r in result.rotations))
        self.assertGreater(_contact_field(result)[2].count(), 0)

    def test_helical_contact_field_keeps_pressure_range(self):
        beta = np.deg2rad(20.)
        pair = GearPair(Gear(28, .0025, .025, helix_angle_rad=beta),
                        Gear(56, .0025, .025, helix_angle_rad=-beta))
        result = analyze_pair(pair, torque_n_m=80., phases=8, strips=5)
        original = [r.pressure_pa.copy() for r in result.rotations]
        values = _contact_field(result)[2]
        self.assertGreater(values.count(), 0)
        self.assertLessEqual(values[:, :, 0].max(), max(p.max() for p in original) * 1e-6 + 1e-10)
        for rotation, pressure in zip(result.rotations, original):
            np.testing.assert_array_equal(rotation.pressure_pa, pressure)

    def test_instantaneous_pressure_recovers_single_tooth_load(self):
        # 相位 0 有两条接触线；必须只积分选中齿对，不能把其他齿对叠到图上。
        for tooth in np.unique(self.result.rotations[0].grid.tooth_pair_index):
            field = _instantaneous_contact_field(self.result, phase_index=0, tooth_pair_index=int(tooth),
                                                  samples=(201, 2001))
            integrated = np.trapz(np.trapz(field["pressure_pa"], field["across_m"], axis=0), field["along_m"])
            self.assertAlmostEqual(integrated / field["tooth_pair_force_n"], 1., delta=2e-4)
            self.assertAlmostEqual(np.trapz(field["line_load_n_per_m"], field["along_m"]),
                                   field["tooth_pair_force_n"], places=8)
            self.assertTrue(np.all(field["pressure_pa"][[0, -1]] == 0))

    def test_instantaneous_field_preserves_hertz_width_and_peak_at_solver_nodes(self):
        field = _instantaneous_contact_field(self.result)
        rotation = self.result.rotations[0]
        indices = field["selected"]
        s = rotation.grid.face_coordinate_m[indices] / np.cos(self.result.pair.base_helix_angle_rad)
        positions = np.searchsorted(field["along_m"], s)
        np.testing.assert_allclose(field["half_width_m"][positions], rotation.half_width_m[indices], rtol=1e-12)
        np.testing.assert_allclose(field["pressure_pa"][len(field["across_m"]) // 2, positions],
                                   rotation.pressure_pa[indices], rtol=1e-12)
        # 对称性来自局部 Hertz 截面；不通过强制椭圆外轮廓来生成图形。
        np.testing.assert_allclose(field["pressure_pa"], field["pressure_pa"][::-1], rtol=1e-10, atol=1e-5)

    def test_instantaneous_zero_load_and_invalid_selection(self):
        zero = analyze_pair(self.result.pair, torque_n_m=0., phases=4, strips=3, local_contact=False)
        self.assertTrue(np.all(_instantaneous_contact_field(zero)["pressure_pa"] == 0))
        with self.assertRaises(ValueError):
            _instantaneous_contact_field(self.result, phase_index=-1)
        with self.assertRaises(ValueError):
            _instantaneous_contact_field(self.result, tooth_pair_index=999)


if __name__ == "__main__":
    unittest.main()
