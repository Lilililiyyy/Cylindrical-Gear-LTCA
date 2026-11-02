"""通用接触图回归：实际啮合域、中心有限支撑、端点分支和原数据身份。"""
import hashlib
from pathlib import Path
import tempfile
import unittest

import numpy as np
from gear_contact import Gear, GearPair, analyze_pair, export_result
from gear_contact.contact_display import (contact_pass_data, load_plot_result,
    contact_pressure_colormap, plot_contact_pass_comparison)


class ContactDisplayTests(unittest.TestCase):
    def result(self, **kwargs):
        pair = GearPair(Gear(28, .0025, .025, helix_angle_rad=np.deg2rad(15)),
                        Gear(56, .0025, .025, helix_angle_rad=-np.deg2rad(15)))
        return analyze_pair(pair, torque_n_m=80, phases=16, strips=9, **kwargs)

    def test_actual_meshing_range_and_finite_cell_support_preserve_raw_values(self):
        result = self.result()
        before = [r.pressure_pa.copy() for r in result.rotations]
        data = contact_pass_data(result)
        self.assertGreater(result.pair.contact_roll_bounds_m[0], .006)
        self.assertEqual(result.pair.pinion.involute_roll_bounds_m[0], 0)
        np.testing.assert_array_equal(data['roll_distance_m'][[0, -1]], result.pair.contact_roll_bounds_m)
        self.assertGreater(np.isfinite(data['pressure_pa_x_y']).mean(), .98)
        boundary = data['boundary_display_samples']
        self.assertTrue(np.all(boundary[:, 0] >= -1e-12))
        self.assertTrue(np.all(boundary[:, 0] <= .025+1e-12))
        self.assertTrue(np.all(boundary[:, 1] >= result.pair.contact_roll_bounds_m[0]-1e-12))
        self.assertTrue(np.all(boundary[:, 1] <= result.pair.contact_roll_bounds_m[1]+1e-12))
        self.assertTrue(np.all(np.isin(boundary[:, 2], data['samples'][:, 2])))
        for left, rotation in zip(before, result.rotations):
            np.testing.assert_array_equal(left, rotation.pressure_pa)
        full = contact_pass_data(result, roll_distance_m=np.linspace(0., result.pair.contact_roll_bounds_m[1], 121))
        self.assertTrue(np.all(np.isnan(full['pressure_pa_x_y'][:, :30])))

    def test_endpoint_view_and_saved_view_keep_the_same_arrays(self):
        result = self.result(elastic_mode='iso_love', local_contact=False,
            iso_settings={'nominal_pinion_torque_n_m': 80},
            extended_contact_settings={'face_extension_factor': .14, 'roll_extension_factor': .4})
        data = contact_pass_data(result)
        self.assertEqual(len(data['boundary_display_samples']), 0)
        self.assertTrue(np.any(data['samples'][:, 3:5]))
        self.assertFalse(np.any(data['ordinary_samples'][:, 3:5]))
        with tempfile.TemporaryDirectory() as folder:
            export_result(result, folder)
            view = load_plot_result(folder)
            self.assertTrue(view.plot_only)
            saved = contact_pass_data(view)
            for key in ('samples', 'pressure_pa_x_y', 'boundary_display_samples'):
                np.testing.assert_array_equal(data[key], saved[key])
            file = Path(folder)/'arrays.npz'
            file.write_bytes(file.read_bytes()+b'changed')
            with self.assertRaises(ValueError):
                load_plot_result(folder)

    def test_shared_style_and_comparison_do_not_modify_exports(self):
        result = self.result()
        cmap = contact_pressure_colormap()
        np.testing.assert_array_equal(cmap(0.)[:3], (0., 0., 1.))
        np.testing.assert_array_equal(cmap(1.)[:3], (1., 0., 0.))
        with tempfile.TemporaryDirectory() as folder:
            export_result(result, Path(folder)/'raw')
            file = Path(folder)/'raw/arrays.npz'
            before = hashlib.sha256(file.read_bytes()).hexdigest()
            view = load_plot_result(file.parent)
            record = plot_contact_pass_comparison({'方案一': view, '方案二': view}, Path(folder)/'plots')
            self.assertFalse(record['raw_results_modified'])
            self.assertEqual(before, hashlib.sha256(file.read_bytes()).hexdigest())
            self.assertTrue((Path(folder)/'plots/07_contact_pass_comparison.png').is_file())


if __name__ == '__main__':
    unittest.main()
