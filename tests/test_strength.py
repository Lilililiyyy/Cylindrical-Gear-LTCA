"""显式因子应力组合的量纲、载荷标度与许用值基准验证。"""
from dataclasses import replace
import math
import json
from pathlib import Path
import unittest

from gear_contact import Gear, GearPair, Material
from gear_contact.strength import GearRatingFactors, MeshRatingFactors, StressLimits, evaluate_iso6336_explicit_factors


def fixture():
    pair = GearPair(Gear(24, .002, .02), Gear(48, .002, .02))
    mesh = MeshRatingFactors(application_factor=1.25, dynamic_factor=1.1, additional_load_factor=1.,
        face_contact_factor=1.2, transverse_contact_factor=1.05, face_bending_factor=1.15,
        transverse_bending_factor=1.08, contact_ratio_factor=.9, helix_contact_factor=1.,
        helix_bending_factor=1., root_contact_ratio_factor=1., deep_tooth_factor=1.)
    pinion = GearRatingFactors(2.4, 1.7, 1., 1.03, .02)
    wheel = GearRatingFactors(2.2, 1.8, 1., 1.01, .02)
    return pair, dict(nominal_pinion_torque_n_m=12., face_width_m=.02, mesh_factors=mesh,
        pinion_factors=pinion, wheel_factors=wheel,
        pinion_limits=StressLimits(1.2e9, 4e8), wheel_limits=StressLimits(1.1e9, 3.8e8))


class ExplicitFactorStrengthTests(unittest.TestCase):
    def test_masta_chain_matches_fourteen_fields(self):
        root = next(p for p in Path(__file__).resolve().parents
                    if (p/"pyproject.toml").is_file() and (p/"gear_contact").is_dir())
        reference = json.loads((root/"examples/masta_reference/strength_reference.json").read_text(encoding="utf-8-sig"))
        cases = json.loads((root/"examples/masta_reference/cases.json").read_text(encoding="utf-8-sig"))["cases"]
        geometry = next(c for c in cases if c["case_id"] == reference["case_id"])["config"]["pair"]
        pair = GearPair(**dict(geometry, pinion=Gear(**geometry["pinion"]), wheel=Gear(**geometry["wheel"])))
        args = dict(reference["inputs"])
        args["mesh_factors"] = MeshRatingFactors(**args["mesh_factors"])
        for role in ("pinion", "wheel"):
            args[role+"_factors"] = GearRatingFactors(**args[role+"_factors"])
            args[role+"_limits"] = StressLimits(**args[role+"_limits"])
            args["material_"+role] = Material(**args["material_"+role])
        result = evaluate_iso6336_explicit_factors(pair, **args)
        self.assertEqual(len(reference["reference_values"]), 14)
        self.assertFalse(reference["scope"]["independent_factor_prediction"])
        for field, expected in reference["reference_values"].items():
            actual = result
            for name in field.split("."):
                actual = actual[name]
            self.assertAlmostEqual(actual/expected, 1., places=11, msg=field)

    def test_hand_calculated_si_chain_and_limits(self):
        pair, args = fixture()
        result = evaluate_iso6336_explicit_factors(pair, **args)
        ft = 2*12/.048
        zh = math.sqrt(2/(math.cos(math.radians(20))**2*math.tan(math.radians(20))))
        ze = math.sqrt(210e9/(2*math.pi*(1-.3**2)))
        h0 = zh*ze*.9*math.sqrt(ft/(.02*.048)*1.5)
        f0 = ft/(.02*.002)*2.4*1.7
        self.assertAlmostEqual(result["nominal_tangential_force_n"], 500.)
        self.assertAlmostEqual(result["nominal_contact_stress_pa"]/h0, 1., places=13)
        self.assertAlmostEqual(result["pinion"]["nominal_root_stress_pa"], f0, places=7)
        self.assertAlmostEqual(result["pinion"]["contact_stress_pa"]/h0,
                               1.03*math.sqrt(1.25*1.1*1.2*1.05), places=13)
        self.assertAlmostEqual(result["pinion"]["root_stress_pa"]/f0, 1.25*1.1*1.15*1.08, places=13)
        self.assertAlmostEqual(result["pinion"]["contact_safety_factor"]*result["pinion"]["contact_stress_pa"], 1.2e9, places=5)
        self.assertAlmostEqual(result["wheel"]["bending_safety_factor"]*result["wheel"]["root_stress_pa"], 3.8e8, places=5)

    def test_torque_scales_contact_as_square_root_and_root_linearly(self):
        pair, args = fixture()
        first = evaluate_iso6336_explicit_factors(pair, **args)
        args["nominal_pinion_torque_n_m"] *= 4
        second = evaluate_iso6336_explicit_factors(pair, **args)
        for role in ("pinion", "wheel"):
            self.assertAlmostEqual(second[role]["contact_stress_pa"]/first[role]["contact_stress_pa"], 2.)
            self.assertAlmostEqual(second[role]["root_stress_pa"]/first[role]["root_stress_pa"], 4.)
            self.assertAlmostEqual(second[role]["contact_safety_factor"]/first[role]["contact_safety_factor"], .5)

    def test_material_changes_only_elastic_contact_term_with_fixed_factors(self):
        pair, args = fixture()
        first = evaluate_iso6336_explicit_factors(pair, **args)
        args.update(material_pinion=Material(840e9, .3), material_wheel=Material(840e9, .3))
        second = evaluate_iso6336_explicit_factors(pair, **args)
        self.assertAlmostEqual(second["pinion"]["contact_stress_pa"]/first["pinion"]["contact_stress_pa"], 2.)
        self.assertEqual(second["pinion"]["root_stress_pa"], first["pinion"]["root_stress_pa"])

    def test_internal_ratio_and_separate_root_widths(self):
        _, args = fixture()
        pair = GearPair(Gear(24, .002, .02), Gear(72, .002, .02, internal=True))
        args["wheel_factors"] = replace(args["pinion_factors"], root_stress_face_width_m=.024)
        result = evaluate_iso6336_explicit_factors(pair, **args)
        self.assertEqual(result["signed_ratio"], -3.)
        self.assertTrue(math.isfinite(result["nominal_contact_stress_pa"]))
        self.assertAlmostEqual(result["wheel"]["nominal_root_stress_pa"]/result["pinion"]["nominal_root_stress_pa"], .02/.024)

    def test_zero_load_and_missing_limits_do_not_invent_safety(self):
        pair, args = fixture()
        args["nominal_pinion_torque_n_m"] = 0.
        zero = evaluate_iso6336_explicit_factors(pair, **args)
        self.assertEqual(zero["pinion"]["contact_stress_pa"], 0.)
        self.assertEqual(zero["wheel"]["root_stress_pa"], 0.)
        self.assertIsNone(zero["pinion"]["contact_safety_factor"])
        args.update(nominal_pinion_torque_n_m=12., pinion_limits=None)
        result = evaluate_iso6336_explicit_factors(pair, **args)
        self.assertIsNone(result["pinion"]["bending_safety_factor"])

    def test_invalid_factors_and_width_rejected(self):
        pair, args = fixture()
        for value in (0., -1., float("nan"), True):
            with self.assertRaises(ValueError):
                replace(args["mesh_factors"], contact_ratio_factor=value)
        with self.assertRaises(ValueError):
            StressLimits(0., 4e8)
        with self.assertRaises(ValueError):
            evaluate_iso6336_explicit_factors(pair, **dict(args, face_width_m=.03))
        with self.assertRaises(ValueError):
            evaluate_iso6336_explicit_factors(pair, **dict(args, nominal_pinion_torque_n_m=-1.))


if __name__ == "__main__":
    unittest.main()
