"""外部参照用几何相位配准；周期原点变化不能改变谱的物理相位。"""
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from gear_contact import Gear, GearPair, analyze_pair, analyze_config, export_result, transmission_error_spectrum


class PhaseOffsetTests(unittest.TestCase):
    def test_offset_matches_actual_contact_geometry_and_periodic_response(self):
        pair = GearPair(Gear(28, .0025, .025), Gear(56, .0025, .025))
        base = analyze_pair(pair, torque_n_m=80., phases=4, strips=5)
        shifted = analyze_pair(pair, torque_n_m=80., phases=4, strips=5, phase_offset=.25)
        np.testing.assert_allclose(shifted.phase, [.25, .5, .75, 0.], atol=1e-15)
        np.testing.assert_allclose(shifted.normal_approach_m, np.roll(base.normal_approach_m, -1), rtol=1e-12)
        for actual, expected in zip(shifted.rotations, base.rotations[1:]+base.rotations[:1]):
            np.testing.assert_allclose(actual.grid.roll_pinion_m, expected.grid.roll_pinion_m, atol=1e-15)
        with tempfile.TemporaryDirectory() as temp:
            export_result(shifted, temp)
            config = json.loads((Path(temp)/"input.json").read_text(encoding="utf-8"))
            restored = analyze_config(config)
            np.testing.assert_allclose(restored.normal_approach_m, shifted.normal_approach_m, rtol=1e-12)
            self.assertEqual(config["phase_offset"], .25)

    def test_spectrum_preserves_global_phase_with_nonzero_sampling_origin(self):
        origin, expected = .036931454775936845, -.73
        phase = origin + np.arange(32)/32
        values = 4. + 2.*np.cos(2*np.pi*3*phase+expected)
        spectrum = transmission_error_spectrum(values, phase_origin=origin)
        self.assertAlmostEqual(spectrum["amplitude"][2], 2., places=12)
        self.assertAlmostEqual(spectrum["phase_rad"][2], expected, places=12)

    def test_nonfinite_phase_offset_is_rejected(self):
        pair = GearPair(Gear(28, .0025, .025), Gear(56, .0025, .025))
        for value in (float("nan"), float("inf"), True):
            with self.assertRaises(ValueError):
                analyze_pair(pair, torque_n_m=80., phases=4, strips=5, phase_offset=value)


if __name__ == "__main__":
    unittest.main()
