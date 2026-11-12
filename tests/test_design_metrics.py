"""验证中心/端点压力的真实计算、方案筛选与绘图采用同一定义。"""
from __future__ import annotations

import copy
import csv
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from gear_contact import Gear, GearPair, SurfaceModification
from gear_contact.design import (DesignStudy, OperatingPoint, compare_designs,
                                 robust_design_search, sweep_parameter)
from gear_contact.plotting import plot_design_study


PROJECT = next(path for path in Path(__file__).resolve().parents
               if (path / "pyproject.toml").is_file() and (path / "gear_contact").is_dir())


class DesignPressureMetricTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pair = GearPair(Gear(28, .0025, .025), Gear(56, .0025, .025))
        cls.options = dict(phases=4, strips=5, elastic_mode="iso_love", local_contact=False,
                           iso_settings={"nominal_pinion_torque_n_m": 80.},
                           extended_contact_settings={})
        cls.designs = {"基准": SurfaceModification(),
                       "偏斜": SurfaceModification(lead_slope_m=3e-6)}

    def test_real_center_default_and_endpoint_preserve_original_summary(self):
        options = dict(self.options, torque_n_m=80., pressure_limit_pa=737e6)
        default = compare_designs(self.pair, self.designs, **options)
        center = compare_designs(self.pair, self.designs, pressure_metric="center", **options)
        endpoint = compare_designs(self.pair, self.designs, pressure_metric="endpoint", **options)
        self.assertEqual(default.to_dict(), center.to_dict())
        for row in endpoint.rows:
            result = endpoint.results[row["design"]][row["operating_point"]]
            center_result = center.results[row["design"]][row["operating_point"]]
            expected = max(float(np.max(rotation.endpoint_pressure["pressure_pa"]))
                           for rotation in result.rotations)
            self.assertEqual(row["max_pressure_mpa"], expected * 1e-6)
            self.assertEqual(result.summary, center_result.summary)
            self.assertGreater(expected, result.summary["max_pressure_pa"])
            for actual, original in zip(result.rotations, center_result.rotations):
                np.testing.assert_array_equal(actual.pressure_pa, original.pressure_pa)
                np.testing.assert_array_equal(actual.solution.forces_n, original.solution.forces_n)
        self.assertTrue(all(row["feasible"] for row in center.design_summary))
        self.assertEqual({row["design"] for row in endpoint.design_summary if row["feasible"]}, {"基准"})
        metadata = endpoint.to_dict()
        self.assertIn("端点", metadata["pressure_definition"])
        self.assertEqual(metadata["units"]["max_pressure_mpa"], "MPa")
        self.assertEqual(metadata["units"]["pressure_limit_pa"], "Pa")
        self.assertEqual(DesignStudy({}, [], [], []).pressure_metric, "center")

    def test_real_missing_endpoints_are_rejected_and_real_zero_load_is_zero(self):
        options = dict(self.options)
        options.pop("extended_contact_settings")
        with self.assertRaisesRegex(ValueError, "端点压力"):
            compare_designs(self.pair, {"基准": SurfaceModification()}, torque_n_m=80.,
                            pressure_metric="endpoint", **options)
        zero = compare_designs(self.pair, {"无载": SurfaceModification()}, torque_n_m=0.,
                               pressure_metric="endpoint", **self.options)
        self.assertEqual(zero.rows[0]["max_pressure_mpa"], 0.)

    @staticmethod
    def mock_analysis(pair, *, modification_pinion, torque_n_m, **kwargs):
        """只用于指标路由：两方案的中心/端点排序相反，摘要端点值故意失配。"""
        center, endpoint = ((10., 30.) if modification_pinion.lead_crown_m == 0. else (20., 15.))
        scale = torque_n_m / 2.
        return SimpleNamespace(
            phase=np.array([0., .5]),
            rotations=[SimpleNamespace(endpoint_pressure={"pressure_pa": np.array([.8, 1.]) * endpoint * scale * 1e6})
                       for _ in range(2)],
            summary={"te_peak_to_peak_m": scale * 1e-6, "max_pressure_pa": center * scale * 1e6,
                     "max_endpoint_pressure_pa": 9999e6, "mean_mesh_stiffness_n_per_m": 1e8,
                     "max_abs_load_centroid_offset_m": 0., "mean_contact_fraction": 1.,
                     "max_force_residual_n": 0., "max_gap_residual_m": 0.})

    def mock_study(self, metric, *, reverse=False, limit=None):
        designs = {"A": SurfaceModification(), "B": SurfaceModification(lead_crown_m=1e-6)}
        points = [OperatingPoint("低载", 1.), OperatingPoint("高载", 2.)]
        if reverse:
            designs = dict(reversed(list(designs.items())))
            points.reverse()
        with patch("gear_contact.design.analyze_pair", side_effect=self.mock_analysis):
            return compare_designs(self.pair, designs, operating_points=points,
                                   pressure_metric=metric, pressure_limit_pa=limit)

    def test_reversed_metric_controls_worst_feasibility_and_pareto(self):
        center = self.mock_study("center", limit=25e6)
        endpoint = self.mock_study("endpoint", limit=25e6)
        self.assertEqual(center.pareto_names, ["A"])
        self.assertEqual(endpoint.pareto_names, ["B"])
        self.assertEqual([row["worst_pressure_mpa"] for row in center.design_summary], [10., 20.])
        self.assertEqual([row["worst_pressure_mpa"] for row in endpoint.design_summary], [30., 15.])
        self.assertEqual([row["feasible"] for row in center.design_summary], [True, True])
        self.assertEqual([row["feasible"] for row in endpoint.design_summary], [False, True])
        self.assertEqual([row["max_pressure_mpa"] for row in endpoint.rows], [15., 30., 7.5, 15.])
        self.assertEqual(self.mock_study("endpoint").pareto_names, ["B"])

    def test_candidate_and_operating_point_reordering_preserves_decisions(self):
        for metric in ("center", "endpoint"):
            original = self.mock_study(metric, limit=25e6)
            reordered = self.mock_study(metric, reverse=True, limit=25e6)
            self.assertEqual(set(original.pareto_names), set(reordered.pareto_names))
            self.assertEqual({row["design"]: row for row in original.design_summary},
                             {row["design"]: row for row in reordered.design_summary})
            self.assertEqual({(row["design"], row["operating_point"]): row for row in original.rows},
                             {(row["design"], row["operating_point"]): row for row in reordered.rows})

    def test_wrappers_route_endpoint_metric_and_default_center(self):
        candidates = {"A": SurfaceModification(), "B": SurfaceModification(lead_crown_m=1e-6)}
        points = [OperatingPoint("高载", 2.)]
        with patch("gear_contact.design.analyze_pair", side_effect=self.mock_analysis):
            robust = robust_design_search(self.pair, candidates, points, pressure_metric="endpoint")
            sweep = sweep_parameter(self.pair, "lead_crown_m", [0., 1e-6],
                                    operating_points=points, pressure_metric="endpoint")
            sweep_default = sweep_parameter(self.pair, "lead_crown_m", [0., 1e-6], operating_points=points)
        self.assertEqual(robust.pareto_names, ["B"])
        self.assertEqual(sweep.pareto_names, ["lead_crown_m=1e-06"])
        self.assertEqual(sweep_default.pareto_names, ["lead_crown_m=0"])
        self.assertEqual([row["worst_pressure_mpa"] for row in sweep.design_summary], [30., 15.])

    def test_unknown_metric_is_rejected_before_solving_in_all_entry_points(self):
        with patch("gear_contact.design.analyze_pair") as solve:
            for metric in ("maximum", None, [], True):
                with self.subTest(metric=metric):
                    with self.assertRaisesRegex(ValueError, "pressure_metric"):
                        compare_designs(self.pair, self.designs, torque_n_m=1., pressure_metric=metric)
                    with self.assertRaisesRegex(ValueError, "pressure_metric"):
                        robust_design_search(self.pair, self.designs, [OperatingPoint("载荷", 1.)],
                                             pressure_metric=metric)
                    with self.assertRaisesRegex(ValueError, "pressure_metric"):
                        sweep_parameter(self.pair, "lead_crown_m", [0.], torque_n_m=1., pressure_metric=metric)
            solve.assert_not_called()

    def test_endpoint_requires_all_phases_and_finite_nonempty_arrays(self):
        base = self.mock_analysis(self.pair, modification_pinion=SurfaceModification(), torque_n_m=2.)
        cases = []
        for payload in (None, {}, {"pressure_pa": [float("nan")]},
                        {"pressure_pa": [float("inf")]}, {"pressure_pa": []},
                        {"pressure_pa": [[1.]]}, {"pressure_pa": [-1.]},
                        {"pressure_pa": ["无效"]}):
            result = copy.deepcopy(base)
            result.rotations[1].endpoint_pressure = payload
            cases.append(result)
        partial = copy.deepcopy(base)
        partial.rotations.pop()
        cases.append(partial)
        for index, result in enumerate(cases):
            with self.subTest(index=index), patch("gear_contact.design.analyze_pair", return_value=result):
                with self.assertRaisesRegex(ValueError, "端点压力"):
                    compare_designs(self.pair, {"A": SurfaceModification()}, torque_n_m=2., pressure_metric="endpoint")

    def test_plot_scatter_csv_labels_and_pareto_use_selected_metric(self):
        output_root = PROJECT / "output" / "test_design_metrics"
        output_root.mkdir(parents=True, exist_ok=True)
        for metric, expected in (("center", [10., 20.]), ("endpoint", [30., 15.])):
            study = self.mock_study(metric, limit=25e6)
            captured = {}

            def capture_figure(fig, output, name):
                """检查实际Matplotlib散点和标注，CSV仍由真实导出函数写出。"""
                axes = fig.axes[0]
                captured["pressure"] = [float(collection.get_offsets()[0, 1]) for collection in axes.collections]
                captured["ylabel"] = axes.get_ylabel()
                captured["annotations"] = [text.get_text() for text in axes.texts]
                return []

            with tempfile.TemporaryDirectory(dir=output_root) as directory:
                with patch("gear_contact.plotting._save", side_effect=capture_figure), \
                     patch("gear_contact.plotting.analysis_metrics", side_effect=AssertionError("不能重算中心压力")):
                    files = plot_design_study(study, directory)
                with Path(files[0]).open(encoding="utf-8-sig", newline="") as stream:
                    rows = list(csv.DictReader(stream))
                self.assertEqual(captured["pressure"], expected)
                self.assertEqual([float(row["worst_pressure_MPa"]) for row in rows], expected)
                self.assertTrue(all(row["pressure_metric"] == metric and row["pressure_unit"] == "MPa" for row in rows))
                self.assertEqual([row["design"] for row in rows if row["pareto"] == "True"], study.pareto_names)
                self.assertIn("中心" if metric == "center" else "端点", captured["ylabel"])
                self.assertEqual([name + "（Pareto）" for name in study.pareto_names],
                                 [label for label in captured["annotations"] if "Pareto" in label])


if __name__ == "__main__":
    unittest.main()
