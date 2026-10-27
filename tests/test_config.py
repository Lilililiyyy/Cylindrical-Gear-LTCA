"""参数输入、测量曲面及可复现配置的独立接口检查。"""
import unittest
from dataclasses import asdict

import numpy as np

from gear_contact import (Gear, GearPair, SurfaceModification, MeasuredSurface,
                          CompositeModification, analyze_pair, analyze_config, modification_from_config)
from gear_contact.io import json_value


class ConfigurationTests(unittest.TestCase):
    def test_exported_configuration_replays_composite_measurement(self):
        pair = GearPair(Gear(28, .0025, .025), Gear(56, .0025, .025))
        surface = CompositeModification((SurfaceModification(lead_crown_m=3e-6),
                                          MeasuredSurface([0, 1], [0, 1], [[0, 1e-6], [-1e-6, 0]])))
        a = analyze_pair(pair, torque_n_m=80, modification_pinion=surface, phases=4, strips=5)
        config = json_value({"pair": pair, **a.inputs})
        b = analyze_config(config)
        np.testing.assert_array_equal(a.normal_approach_m, b.normal_approach_m)
        self.assertEqual(a.summary["max_pressure_pa"], b.summary["max_pressure_pa"])

    def test_explicit_kinds_and_unknown_fields(self):
        curve = modification_from_config({"kind": "curve", "coordinates": [0, 1],
                                           "removal_m": [0, 2e-6], "axis": "lead"})
        self.assertAlmostEqual(curve.evaluate(.5, .5), 1e-6)
        for value in ({"kind": "unknown"}, {"invented_parameter": 1},
                      {"kind": "composite", "components": [], "extra": 1}):
            with self.assertRaises(ValueError):
                modification_from_config(value)

    def test_json_cannot_silently_recreate_external_callbacks(self):
        pair = GearPair(Gear(28, .0025, .025), Gear(56, .0025, .025))
        config = {"pair": asdict(pair), "torque_n_m": 80, "external_compliance_provider": True}
        with self.assertRaises(ValueError):
            analyze_config(config)


if __name__ == "__main__":
    unittest.main()
