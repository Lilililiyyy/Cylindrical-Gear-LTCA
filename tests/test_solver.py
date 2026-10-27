"""独立解析解、穷举主动集合及非线性平衡的求解器验证。"""
import itertools
import unittest

import numpy as np

from gear_contact.solver import solve_contact


class QuadraticLocalLaw:
    """测试用单调局部规律 h=a f²，具有可独立积分的互补能。"""
    def __init__(self, a):
        self.a = a

    def __call__(self, force):
        return self.a*force**2, 2*self.a*force

    def energy(self, force):
        return self.a*force**3/3


class ContactSolverTests(unittest.TestCase):
    def test_equal_parallel_springs(self):
        result = solve_contact(np.zeros(7), np.eye(7)/2e7, 350)
        np.testing.assert_allclose(result.forces_n, 50, rtol=1e-11)
        self.assertAlmostEqual(result.approach_m, 2.5e-6, places=13)
        self.assertAlmostEqual(result.tangent_stiffness_n_per_m/1.4e8, 1, places=12)

    def test_gap_excludes_open_cells(self):
        result = solve_contact([0, 2e-6, 10e-6], np.eye(3)/1e7, 100)
        np.testing.assert_allclose(result.forces_n, [60, 40, 0], atol=1e-8)
        self.assertAlmostEqual(result.approach_m, 6e-6, places=13)
        self.assertGreater(result.residual_gaps_m[2], 0)

    def test_random_spd_matches_exhaustive_active_sets(self):
        rng = np.random.default_rng(4937)
        for _ in range(18):
            a = rng.normal(size=(5, 5))
            c = (a.T@a+np.eye(5))*1e-8
            gaps = rng.uniform(-3e-6, 7e-6, 5)
            force = 80.0
            oracle = None
            for bits in itertools.product((False, True), repeat=5):
                mask = np.array(bits)
                if not np.any(mask):
                    continue
                block = c[np.ix_(mask, mask)]
                inv_one = np.linalg.solve(block, np.ones(np.count_nonzero(mask)))
                inv_gap = np.linalg.solve(block, gaps[mask])
                delta = (force+np.sum(inv_gap))/np.sum(inv_one)
                f = np.zeros(5)
                f[mask] = delta*inv_one-inv_gap
                residual = gaps+c@f-delta
                if np.min(f) >= -1e-8 and np.min(residual) >= -1e-13:
                    oracle = f
                    break
            self.assertIsNotNone(oracle)
            result = solve_contact(gaps, c, force)
            np.testing.assert_allclose(result.forces_n, oracle, rtol=2e-7, atol=2e-5)

    def test_nonlinear_equal_cells_and_tangent(self):
        law = QuadraticLocalLaw(2e-10)
        c = np.eye(4)*3e-8
        result = solve_contact(np.zeros(4), c, 240, local_law=law)
        np.testing.assert_allclose(result.forces_n, 60, atol=1e-7)
        expected = 3e-8*60+2e-10*60**2
        self.assertAlmostEqual(result.approach_m, expected, places=12)
        self.assertAlmostEqual(result.tangent_stiffness_n_per_m/(4/(3e-8+4e-10*60)), 1, places=10)

    def test_nonlinear_open_set_and_finite_difference_stiffness(self):
        law = QuadraticLocalLaw(4e-10)
        c = np.array([[4, 1, .3], [1, 5, .5], [.3, .5, 6]])*1e-8
        gaps = np.array([0, 2e-6, 50e-6])
        a = solve_contact(gaps, c, 120, local_law=law)
        low = solve_contact(gaps, c, 119.99, local_law=law)
        high = solve_contact(gaps, c, 120.01, local_law=law)
        finite_difference = .02/(high.approach_m-low.approach_m)
        self.assertAlmostEqual(a.tangent_stiffness_n_per_m/finite_difference, 1, places=5)
        self.assertFalse(a.active_mask[2])

    def test_zero_load_and_translation_of_gap_datum(self):
        c = np.eye(3)*1e-8
        empty = solve_contact([2e-6, 4e-6, 8e-6], c, 0)
        self.assertEqual(empty.approach_m, 2e-6)
        self.assertFalse(np.any(empty.active_mask))
        a = solve_contact([0, 1e-6, 2e-6], c, 100)
        b = solve_contact([4e-6, 5e-6, 6e-6], c, 100)
        np.testing.assert_allclose(a.forces_n, b.forces_n, atol=1e-8)
        self.assertAlmostEqual(b.approach_m-a.approach_m, 4e-6, places=13)

    def test_reject_nonphysical_compliance(self):
        for matrix in ([[1, 2], [0, 1]], [[1, 2], [2, 1]], [[0, 0], [0, 0]]):
            with self.assertRaises(ValueError):
                solve_contact([0, 0], matrix, 10)

    def test_zero_load_right_tangent_obeys_unilateral_constraint(self):
        result = solve_contact([0, 0], [[1, 2], [2, 5]], 0)
        self.assertAlmostEqual(result.tangent_stiffness_n_per_m, 1)
        class LinearLaw:
            def __call__(self, force):
                return force*2, np.full_like(force, 2.0)
        result = solve_contact([0, 0], np.eye(2), 0, local_law=LinearLaw())
        self.assertAlmostEqual(result.tangent_stiffness_n_per_m, 2/3)

    def test_nonfinite_tolerances_are_rejected(self):
        for kwargs in ({"relative_tolerance": np.inf}, {"relative_tolerance": np.nan},
                       {"absolute_gap_tolerance_m": np.nan}, {"max_iterations": 1.5},
                       {"max_iterations": True}):
            with self.assertRaises(ValueError):
                solve_contact([0, 0], [[1, 2], [2, 5]], 1, **kwargs)


if __name__ == "__main__":
    unittest.main()
