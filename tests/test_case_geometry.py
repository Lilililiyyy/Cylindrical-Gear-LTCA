"""几何展示需保持实际尺度、内外啮合方向及输入／展示边界。"""
import importlib.util
import math
from pathlib import Path
import unittest

import numpy as np

from gear_contact import Gear, GearPair

PROJECT = next(p for p in Path(__file__).resolve().parents
               if (p / "pyproject.toml").is_file() and (p / "gear_contact").is_dir())
SPEC = importlib.util.spec_from_file_location("case_geometry_plotting", PROJECT / "examples/case_geometry_plotting.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class GeometryDisplayTests(unittest.TestCase):
    def test_outline_closes_and_preserves_actual_root_tip_and_length_scaling(self):
        gear = Gear(24, .002, .024, profile_shift=.15)
        first = MODULE.tooth_outline(gear)
        scale = 1.7
        second = MODULE.tooth_outline(Gear(24, .002*scale, .024*scale, profile_shift=.15))
        np.testing.assert_array_equal(first["xy_m"][0], first["xy_m"][-1])
        radii = np.linalg.norm(first["xy_m"], axis=1)
        self.assertAlmostEqual(radii.min(), gear.root_radius_m)
        self.assertAlmostEqual(radii.max(), gear.tip_radius_m)
        np.testing.assert_allclose(second["xy_m"], first["xy_m"]*scale, rtol=1e-13, atol=1e-15)
        np.testing.assert_array_equal(first["tooth_index"], second["tooth_index"])

    def test_display_phase_aligns_the_selected_involute_flanks_for_external_and_internal(self):
        for internal in (False, True):
            pair = GearPair(Gear(28, .0025, .025), Gear(84 if internal else 56, .0025, .025, internal=internal))
            phases = MODULE.display_phases(pair)
            working = [g.base_radius_m/math.cos(pair.working_pressure_angle_rad) for g in (pair.pinion, pair.wheel)]
            points = []
            for index, (role, gear, radius) in enumerate(zip(("pinion", "wheel"), (pair.pinion, pair.wheel), working)):
                half = gear.tooth_thickness_m(radius)/(2*radius)
                sign = -1 if internal and role == "wheel" else 1
                angle = phases[f"{role}_phase_rad"] + sign*half
                points.append(np.array([radius*math.cos(angle)+(pair.center_distance_m if index else 0.), radius*math.sin(angle)]))
            np.testing.assert_allclose(points[0], points[1], atol=1e-14)
            np.testing.assert_allclose(points[0], phases["pitch_point_m"], atol=1e-14)


if __name__ == "__main__":
    unittest.main()
