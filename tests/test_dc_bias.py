"""Independent, hand-checked DC bias reference cases."""

import math
import unittest

from dc_bias import BiasInputs, InputValidationError, calculate_bias


class BiasModelTests(unittest.TestCase):
    def setUp(self):
        self.default = BiasInputs(
            vcc_v=12.0, r1_ohm=100_000.0, r2_ohm=22_000.0,
            rc_ohm=2_200.0, re_ohm=1_000.0, beta=100.0, vbe_v=0.70,
        )

    def test_reference_forward_active(self):
        point = calculate_bias(self.default)
        self.assertEqual(point.region, "forward_active")
        for key, expected in {
            "VTH_V": 2.163934426, "RTH_OHM": 18032.786885,
            "VB_V": 1.942156728, "VE_V": 1.242156728,
            "VC_V": 9.294312078, "VCE_V": 8.052155351,
        }.items():
            self.assertAlmostEqual(point.values[key], expected, delta=1e-6, msg=key)
        for key, expected in {
            "IB_A": 12.298581463e-6,
            "IC_A": 1.229858146e-3,
            "IE_A": 1.242156728e-3,
        }.items():
            self.assertAlmostEqual(point.values[key], expected, delta=1e-10, msg=key)

    def test_cutoff_estimate_has_zero_transistor_current(self):
        point = calculate_bias(BiasInputs(
            vcc_v=5, r1_ohm=100_000, r2_ohm=1_000,
            rc_ohm=2_200, re_ohm=1_000, beta=100, vbe_v=0.70,
        ))
        self.assertEqual(point.region, "cutoff_estimate")
        self.assertAlmostEqual(point.values["VB_V"], 5 / 101, places=9)
        for key in ("IB_A", "IC_A", "IE_A", "VE_V"):
            self.assertEqual(point.values[key], 0.0)
        self.assertEqual(point.values["VC_V"], 5)
        self.assertTrue(any("estimate" in w.lower() for w in point.warnings))

    def test_saturation_estimate_respects_forced_beta(self):
        point = calculate_bias(BiasInputs(
            vcc_v=5, r1_ohm=10_000, r2_ohm=10_000,
            rc_ohm=10_000, re_ohm=1_000, beta=100, vbe_v=0.70,
        ))
        self.assertEqual(point.region, "saturation_estimate")
        self.assertAlmostEqual(point.values["VCE_V"], 0.20, places=8)
        self.assertGreater(point.values["IC_A"], 0)
        self.assertLessEqual(point.values["IC_A"], 100 * point.values["IB_A"])
        self.assertAlmostEqual(
            point.values["VC_V"] - point.values["VE_V"], 0.20, places=8,
        )
        self.assertTrue(any("estimate" in w.lower() for w in point.warnings))

    def test_saturation_requires_base_collector_forward_bias(self):
        # VBE below assumed VCE(sat) makes VB < VC; calling this
        # "saturation" would violate the base-collector junction polarity.
        params = BiasInputs(
            vcc_v=5, r1_ohm=10_000, r2_ohm=10_000,
            rc_ohm=10_000, re_ohm=1_000, beta=100, vbe_v=0.10,
        )
        point = calculate_bias(params)
        self.assertEqual(point.region, "outside_model")
        self.assertIsNone(point.values["VB_V"])
        self.assertIsNone(point.values["VC_V"])
        self.assertIsNone(point.values["IC_A"])
        self.assertTrue(point.warnings)

    def test_reject_invalid_physical_or_nonfinite_inputs(self):
        base = vars(self.default).copy()
        for name, bad in (
            ("vcc_v", 0), ("vcc_v", -2),
            ("r1_ohm", 0), ("r2_ohm", -1),
            ("rc_ohm", 0), ("re_ohm", -1),
            ("beta", 0), ("beta", -5),
            ("vbe_v", 0), ("vbe_v", -0.7),
            ("vcc_v", math.nan), ("beta", math.inf),
            ("r1_ohm", 1e300),
        ):
            with self.subTest(name=name, bad=bad):
                values = dict(base, **{name: bad})
                with self.assertRaises(InputValidationError) as ctx:
                    calculate_bias(BiasInputs(**values))
                self.assertIn(name, ctx.exception.errors)

    def test_self_checks_cover_transistor_and_divider_kcl(self):
        cases = [self.default, BiasInputs(
            vcc_v=5, r1_ohm=10_000, r2_ohm=10_000,
            rc_ohm=10_000, re_ohm=1_000, beta=100, vbe_v=0.70,
        )]
        required = {
            "transistor_kcl", "divider_kcl", "collector_drop",
            "emitter_drop", "vce_identity", "region_consistency",
        }
        for params in cases:
            with self.subTest(vcc=params.vcc_v):
                point = calculate_bias(params)
                self.assertEqual(set(point.checks), required)
                self.assertTrue(all(point.checks.values()))
