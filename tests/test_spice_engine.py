"""Tests for Lab 04 inputs, result integrity, and the real solver contract."""

import cmath
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from spice_engine import (
    FIELD_SPECS,
    SpiceError,
    _ac_data,
    _dc_data,
    _invoke,
    _load_profile,
    _netlist,
    _parse_inputs,
    _read_raw,
    simulate,
)


_DEFAULTS = {key: default for key, (_, _, default) in FIELD_SPECS.items()}
_MODEL = ".MODEL LABTEST NPN (IS=1e-14 BF=100 VAF=75 CJE=10p CJC=4p TF=.3n)\n"
_EXECUTABLE = os.environ.get("LAB04_NGSPICE") or shutil.which("ngspice")
_RAW_DC = """Title: Test ASCII Raw
Plotname: Operating Point
Flags: real
No. Variables: 7
No. Points: 1
Variables:
  0 v(vcc) voltage
  1 v(b) voltage
  2 v(c) voltage
  3 v(e) voltage
  4 i(vsenseb) current
  5 i(vsensec) current
  6 i(vsensee) current
Values:
  0 12
    1.9
    9.2
    1.2
    0.00001
    0.00119
    0.0012
"""


def _write_profile(directory, model=_MODEL, *, kind="model", name="LABTEST", pins=None):
    model_bytes = model.encode("ascii")
    (directory / "model.lib").write_bytes(model_bytes)
    profile = {
        "id": name,
        "name": "Synthetic test fixture",
        "classification": "provisional",
        "source": "Local engine regression fixture",
        "model_file": "model.lib",
        "model_name": name,
        "sha256": hashlib.sha256(model_bytes).hexdigest(),
        "kind": kind,
    }
    if pins is not None:
        profile["pins"] = pins
    path = directory / "profile.json"
    path.write_text(json.dumps(profile), encoding="utf-8")
    return path


class SpiceValidationTests(unittest.TestCase):
    def test_units_are_converted_once_and_ac_has_its_own_stimulus(self):
        tran = _parse_inputs("tran", _DEFAULTS)
        self.assertEqual(tran["rc"], 2200)
        self.assertAlmostEqual(tran["cin"], 1e-5)
        self.assertEqual(tran["amp"], .01)
        self.assertEqual(tran["freq"], 1000)
        ac = _parse_inputs("ac", _DEFAULTS)
        self.assertNotIn("amp", ac)
        self.assertNotIn("freq", ac)
        deck = _netlist("ac", ac, {"kind": "model", "model_name": "LABTEST"})
        self.assertIn("AC 1\n", deck)
        self.assertIn(".ac dec 40 10 1e6\n", deck)
        self.assertNotIn("SIN", deck)

    def test_invalid_inputs_reject_before_selecting_a_model(self):
        for key, value in (
            ("re", 0), ("cin", "-2"), ("r1", True), ("vcc", "nan"),
            ("rc", "1e400"), ("rl", []), ("amp", None), ("freq", 20),
        ):
            with self.subTest(key=key, value=value), self.assertRaises(SpiceError) as raised:
                simulate("tran", dict(_DEFAULTS, **{key: value}))
            self.assertEqual(raised.exception.code, "input")
            self.assertIn(key, raised.exception.fields)
        for analysis, inputs in (("other", _DEFAULTS), ([], _DEFAULTS), ("dc", [])):
            with self.subTest(analysis=analysis), self.assertRaises(SpiceError) as raised:
                simulate(analysis, inputs)
            self.assertEqual(raised.exception.code, "input")

    def test_profile_selection_and_model_checksum_fail_closed(self):
        with tempfile.TemporaryDirectory() as location:
            directory = Path(location)
            path = _write_profile(directory)
            self.assertEqual(_load_profile(path)[0]["model_name"], "LABTEST")
            (directory / "model.lib").write_text(_MODEL + "* updated\n", encoding="ascii")

            for invalid_profile in (None, directory / "missing.json", path):
                with self.subTest(profile=invalid_profile), self.assertRaises(SpiceError) as raised:
                    simulate("dc", _DEFAULTS, profile_path=invalid_profile)
                self.assertEqual(raised.exception.code, "profile")

    def test_invalid_declarations_and_pin_maps_are_rejected(self):
        with tempfile.TemporaryDirectory() as location:
            directory = Path(location)
            for model, kind, name, pins in (
                (_MODEL + ".MODEL LABTEST PNP (BF=50)\n", "model", "LABTEST", None),
                (_MODEL, "model", "UNKNOWN", None),
                (_MODEL + ".ac dec 30 10 1e6\n", "model", "LABTEST", None),
                (".SUBCKT TEST C B E\n.ENDS TEST\n", "subckt", "TEST", ["B", "B", "E"]),
            ):
                path = _write_profile(directory, model, kind=kind, name=name, pins=pins)
                with self.subTest(params=(kind, name, pins)), self.assertRaises(SpiceError) as raised:
                    _load_profile(path)
                self.assertEqual(raised.exception.code, "profile")

    def test_raw_rejects_wrong_analysis_missing_values_and_invalid_vectors(self):
        with tempfile.TemporaryDirectory() as location:
            path = Path(location) / "run.raw"
            path.write_text(_RAW_DC, encoding="ascii")
            self.assertEqual(_read_raw(path, "dc")[0]["v(b)"], 1.9)
            for raw in (
                _RAW_DC.replace("Operating Point", "AC Analysis"),
                _RAW_DC.replace("v(b) voltage", "v(b) current"),
                _RAW_DC.replace("v(c) voltage", "v(b) voltage"),
                _RAW_DC.replace("1.2", "nan"),
                _RAW_DC.removesuffix("    0.0012\n"),
                _RAW_DC.replace("  0 12", "  1 12"),
                _RAW_DC.replace("No. Points: 1", "No. Points: 2"),
            ):
                path.write_text(raw, encoding="ascii")
                with self.assertRaises(SpiceError) as raised:
                    _read_raw(path, "dc")
                self.assertEqual(raised.exception.code, "output")

    def test_dc_current_residual_rejects_inconsistent_results(self):
        row = {
            "v(vcc)": 12, "v(b)": 2, "v(c)": 10, "v(e)": 1,
            "i(vsenseb)": 0.00001, "i(vsensec)": .1, "i(vsensee)": .001,
        }
        with self.assertRaises(SpiceError) as raised:
            _dc_data(row, _parse_inputs("dc", _DEFAULTS))
        self.assertEqual(raised.exception.code, "output")

    def test_undefined_ac_ratio_retains_the_sample_as_a_gap(self):
        rows = [
            {"frequency": complex(10 * 10 ** (index / 40)), "v(vin)": 1 + 0j, "v(vout)": -1 + .1j}
            for index in range(201)
        ]
        rows[40]["v(vin)"] = 0j
        data, warnings = _ac_data(rows)
        self.assertIsNone(data["samples"][40]["gain_db"])
        self.assertIsNone(data["samples"][40]["phase_deg"])
        self.assertIsNotNone(data["samples"][41]["gain_db"])
        self.assertTrue(warnings)

    def test_missing_engine_and_solver_timeout_have_distinct_codes(self):
        with tempfile.TemporaryDirectory() as location:
            path = _write_profile(Path(location))
            with self.assertRaises(SpiceError) as missing:
                simulate("dc", _DEFAULTS, profile_path=path, executable=Path(location) / "missing-ngspice")
        self.assertEqual(missing.exception.code, "engine")
        with patch("spice_engine.subprocess.run", side_effect=subprocess.TimeoutExpired("ngspice", 10)):
            with self.assertRaises(SpiceError) as timeout:
                _invoke("ngspice", ["-v"], ".")
        self.assertEqual(timeout.exception.code, "timeout")


@unittest.skipUnless(_EXECUTABLE, "Set LAB04_NGSPICE or add ngspice to PATH for real solver tests.")
class RealSpiceTests(unittest.TestCase):
    def test_dc_ac_and_transient_from_real_ngspice(self):
        with tempfile.TemporaryDirectory() as location:
            directory = Path(location)
            profile = _write_profile(directory)
            evidence = directory / "evidence"

            def run(analysis, changes=None):
                return simulate(
                    analysis, {**_DEFAULTS, **(changes or {})}, profile_path=profile,
                    executable=_EXECUTABLE, evidence_dir=evidence,
                )

            dc = run("dc")
            changed = run("dc", {"re": 2})
            self.assertGreater(dc["data"]["point"]["ic_a"], changed["data"]["point"]["ic_a"])
            self.assertTrue(all(check["passed"] for check in dc["data"]["checks"].values()))
            raw_files = evidence / dc["run_id"]
            self.assertEqual({file.name for file in raw_files.iterdir()}, {"circuit.cir", "run.raw", "run.log"})
            self.assertEqual(
                dc["provenance"]["netlist_sha256"],
                hashlib.sha256((raw_files / "circuit.cir").read_bytes()).hexdigest(),
            )

            ac = run("ac")
            self.assertEqual(len(ac["data"]["samples"]), 201)
            sample = min(ac["data"]["samples"], key=lambda item: abs(1000 - item["frequency_hz"]))
            self.assertEqual(sample["frequency_hz"], 1000)
            self.assertGreater(abs(sample["phase_deg"]), 150)
            ratio = complex(sample["vout_re_v"], sample["vout_im_v"]) / complex(
                sample["vin_re_v"], sample["vin_im_v"],
            )
            self.assertAlmostEqual(sample["gain_db"], 20 * math.log10(abs(ratio)), places=9)
            self.assertAlmostEqual(math.remainder(sample["phase_deg"] - math.degrees(cmath.phase(ratio)), 360), 0)

            for amplitude, frequency in ((10, 1), (20, 1), (10, 2)):
                with self.subTest(amplitude=amplitude, frequency=frequency):
                    tran = run("tran", {"amp": amplitude, "freq": frequency})
                    rows = tran["data"]["samples"]
                    self.assertEqual(rows[-1]["time_s"], .004)
                    self.assertAlmostEqual(tran["data"]["summary"]["vin_pp_half_v"], amplitude / 1000, delta=1e-5)
                    self.assertLess(
                        max(abs(row["vin_v"] - amplitude / 1000 * math.sin(2 * math.pi * frequency * 1000 * row["time_s"]))
                            for row in rows),
                        1e-10,
                    )

    def test_subcircuit_pin_order_comes_from_the_selected_profile(self):
        wrapped = _MODEL + ".SUBCKT LABWRAP E C B\nQINNER C B E LABTEST\n.ENDS LABWRAP\n"
        with tempfile.TemporaryDirectory() as location:
            directory = Path(location)
            model_profile = _write_profile(directory)
            reference = simulate("dc", _DEFAULTS, profile_path=model_profile, executable=_EXECUTABLE)
            wrapper_profile = _write_profile(directory, wrapped, kind="subckt", name="LABWRAP", pins=["E", "C", "B"])
            subcircuit = simulate("dc", _DEFAULTS, profile_path=wrapper_profile, executable=_EXECUTABLE)
        self.assertNotEqual(reference["provenance"]["sha256"], subcircuit["provenance"]["sha256"])
        self.assertEqual(subcircuit["provenance"]["model_name"], "LABWRAP")
        for key, value in reference["data"]["point"].items():
            self.assertAlmostEqual(subcircuit["data"]["point"][key], value, places=8)
