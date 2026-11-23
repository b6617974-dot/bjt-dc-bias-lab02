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
    check_setup,
    design_search,
    setup_status,
    simulate,
    verified_setup_status,
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

    def test_setup_status_rejects_invalid_profiles_without_starting_solver(self):
        with tempfile.TemporaryDirectory() as location, patch("spice_engine._invoke") as invoke:
            directory = Path(location)
            path = _write_profile(directory)
            executable = directory / "missing-ngspice"
            original = json.loads(path.read_text(encoding="utf-8"))

            def status():
                return setup_status(profile_path=path, executable=executable)

            actual = status()
            self.assertEqual(actual["engine"], {"status": "unavailable", "resolution": None, "code": "engine_missing"})
            self.assertEqual(actual["profile"]["sha256"], original["sha256"])
            self.assertNotIn("model_file", actual["profile"])
            self.assertNotIn(str(directory), json.dumps(actual))
            for filename in ("../model.lib", "sub/model.lib", "..\\model.lib", "C:\\model.lib", str(directory / "model.lib")):
                with self.subTest(filename=filename):
                    path.write_text(json.dumps(dict(original, model_file=filename)), encoding="utf-8")
                    self.assertEqual(status()["profile"]["code"], "model_path")
            path.write_text(json.dumps(dict(original, model_file="absent.lib")), encoding="utf-8")
            self.assertEqual(status()["profile"]["code"], "model_missing")
            path.write_text(json.dumps(dict(original, sha256="0" * 64)), encoding="utf-8")
            self.assertEqual(status()["profile"]["code"], "model_checksum")
            child = _write_profile(directory, ".SUBCKT TEST C B E\n.ENDS TEST\n", kind="subckt", name="TEST", pins=["B", "B", "E"])
            self.assertEqual(child, path)
            self.assertEqual(status()["profile"]["code"], "model_pins")
            path.write_text(" " * (64 * 1024 + 1), encoding="utf-8")
            self.assertEqual(status()["profile"]["code"], "profile_invalid")
            path.write_text(json.dumps(original), encoding="utf-8")
            (directory / "model.lib").write_bytes(b"*" * (1024 * 1024 + 1))
            self.assertEqual(status()["profile"]["code"], "model_too_large")
            invoke.assert_not_called()

    def test_hosted_receipt_is_sanitized_and_bound_to_its_model_and_mode_checks(self):
        profile = {"status": "available", "name": "Fixture", "sha256": "f" * 64,
                   "kind": "subckt", "model_name": "LABTEST", "pins": ["C", "B", "E"],
                   "classification": "provisional"}
        steps = [{"id": "version", "status": "PASS", "version": "47"}]
        steps.extend({"id": stage, "status": "PASS", "run_id": str(i) * 32}
                     for i, stage in enumerate(("divider", "dc", "ac", "tran")))
        steps[1]["value_v"] = 5.0
        steps[1]["file"] = "private-path"
        report = {"ok": True, "profile": profile, "engine_version": "47", "steps": steps,
                  "executable": "/private-engine-path"}
        with tempfile.TemporaryDirectory() as location, patch(
            "spice_engine._solver_path", side_effect=lambda path: path or "/private-engine-path"
        ):
            path = Path(location) / "report.json"
            path.write_text(json.dumps(report), encoding="utf-8")
            verified = verified_setup_status(path, profile)
            self.assertEqual(verified["source"], "build")
            self.assertEqual([step["id"] for step in verified["steps"]], ["version", "divider", "dc", "ac", "tran"])
            self.assertNotIn("private-path", json.dumps(verified))
            self.assertNotIn("private-engine-path", json.dumps(verified))
            self.assertIsNone(verified_setup_status(path, profile, executable="/different-engine"))
            self.assertIsNone(verified_setup_status(path, dict(profile, pins=["B", "C", "E"])))
            self.assertIsNone(verified_setup_status(path, dict(profile, sha256="a" * 64)))
            for field, value in (("status", "FAIL"), ("run_id", "not-a-run-id"), ("value_v", 4.9)):
                with self.subTest(field=field):
                    changed = [steps[0], dict(steps[1], **{field: value}), *steps[2:]]
                    path.write_text(json.dumps(dict(report, steps=changed)), encoding="utf-8")
                    self.assertIsNone(verified_setup_status(path, profile))

    def test_setup_rejects_a_model_symlink_that_resolves_outside_its_profile_folder(self):
        with tempfile.TemporaryDirectory() as location:
            outer = Path(location)
            directory = outer / "profile"
            directory.mkdir()
            profile = _write_profile(directory)
            original_model = directory / "model.lib"
            outside = original_model.rename(outer / "model.lib")
            try:
                original_model.symlink_to(outside)
            except (NotImplementedError, OSError) as error:
                self.skipTest(f"Symbolic links are unavailable: {type(error).__name__}")
            result = setup_status(profile_path=profile)
            self.assertEqual(result["profile"], {"status": "unavailable", "code": "model_path"})

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


class DesignSearchTests(unittest.TestCase):
    def setUp(self):
        self.inputs = {key: value for key, value in _DEFAULTS.items() if key not in {"amp", "freq"}}
        self.provenance = {
            "ngspice_version": "test-version", "sha256": "0" * 64, "model_name": "LABTEST",
            "name": "Design search fixture", "classification": "provisional",
        }
        self.dc = {
            "provenance": self.provenance, "run_id": "dc-fixture", "warnings": [],
            "data": {"point": {"vb_v": 2, "ve_v": 1.2, "vc_v": 8, "ib_a": 1e-5, "ic_a": 0.001}},
        }
        self.ac = {
            "provenance": self.provenance, "run_id": "ac-fixture", "warnings": [],
            "data": {"samples": [{"frequency_hz": 1000, "gain_db": 5}]},
        }

    def test_invalid_target_or_input_are_rejected_before_the_solver(self):
        for inputs, gain, cap, field in (
            (self.inputs, "5", 1.5, "target_gain_db"),
            (self.inputs, math.inf, 1.5, "target_gain_db"),
            (self.inputs, False, 1.5, "target_gain_db"),
            (self.inputs, 5, 0, "max_ic_ma"),
            (dict(self.inputs, re=0), 5, 1.5, "re"),
        ):
            with self.subTest(field=field), self.assertRaises(SpiceError) as raised:
                design_search(inputs, gain, cap)
            self.assertEqual(raised.exception.code, "input")
            self.assertIn(field, raised.exception.fields)

    def test_completed_pair_is_retained_but_timeout_is_marked_partial(self):
        timeout = SpiceError("timeout", "Budget expired.")
        with (
            tempfile.TemporaryDirectory() as location,
            patch("spice_engine._solver_path", return_value="controlled-test"),
            patch("spice_engine._run_simulation", side_effect=[self.dc, self.ac, timeout]) as run,
        ):
            result = design_search(self.inputs, 6, 1.5, profile_path=_write_profile(Path(location)))
        self.assertTrue(result["partial"])
        self.assertEqual((result["evaluated"], result["total"], result["eligible"]), (1, 9, 1))
        candidate, = result["candidates"]
        self.assertFalse(candidate["passed"])
        self.assertEqual((candidate["gain_db"], candidate["ic_ma"]), (5, 1))
        self.assertEqual((candidate["dc_run_id"], candidate["ac_run_id"]), ("dc-fixture", "ac-fixture"))
        self.assertEqual([call.args[0] for call in run.call_args_list], ["dc", "ac", "dc"])
        self.assertEqual(len({call.kwargs["deadline"] for call in run.call_args_list}), 1)
        self.assertIs(run.call_args_list[0].args[2], run.call_args_list[1].args[2])

    def test_bad_bias_excludes_candidates_without_running_ac(self):
        dc = dict(self.dc, data={"point": {**self.dc["data"]["point"], "vc_v": 1}})
        with (
            tempfile.TemporaryDirectory() as location,
            patch("spice_engine._solver_path", return_value="controlled-test"),
            patch("spice_engine._run_simulation", return_value=dc) as run,
        ):
            result = design_search(self.inputs, 4, 1.5, profile_path=_write_profile(Path(location)))
        self.assertEqual((result["evaluated"], result["total"], result["eligible"]), (9, 9, 0))
        self.assertFalse(result["partial"])
        self.assertEqual(result["candidates"], [])
        self.assertTrue(all(call.args[0] == "dc" for call in run.call_args_list))

    def test_missing_frequency_and_changed_solver_abort_the_search(self):
        for ac, code in (
            (dict(self.ac, data={"samples": [{"frequency_hz": 999, "gain_db": 5}]}), "output"),
            (dict(self.ac, provenance=dict(self.provenance, ngspice_version="different")), "engine"),
        ):
            with (
                self.subTest(code=code),
                tempfile.TemporaryDirectory() as location,
                patch("spice_engine._solver_path", return_value="controlled-test"),
                patch("spice_engine._run_simulation", side_effect=[self.dc, ac]),
                self.assertRaises(SpiceError) as raised,
            ):
                design_search(self.inputs, 4, 1.5, profile_path=_write_profile(Path(location)))
            self.assertEqual(raised.exception.code, code)


@unittest.skipUnless(_EXECUTABLE, "Set LAB04_NGSPICE or add ngspice to PATH for real solver tests.")
class RealSpiceTests(unittest.TestCase):
    def test_setup_uses_real_divider_and_default_ce_and_preserves_no_model_state(self):
        with tempfile.TemporaryDirectory() as location:
            directory = Path(location)
            report = check_setup(executable=_EXECUTABLE, profile_path=_write_profile(directory), evidence_dir=directory)
            self.assertTrue(report["ok"])
            receipts = [step["run_id"] for step in report["steps"][1:]]
            self.assertEqual(len(set(receipts)), 4)
            self.assertEqual([step["status"] for step in report["steps"]], ["PASS"] * 5)
            self.assertAlmostEqual(report["steps"][1]["value_v"], 5.0)
            for run_id in receipts:
                self.assertTrue((directory / run_id / "run.raw").is_file())
                self.assertTrue((directory / run_id / "circuit.cir").is_file())
            no_model = check_setup(executable=_EXECUTABLE)
            self.assertEqual(no_model["profile"]["code"], "profile_unconfigured")
            self.assertEqual([step["status"] for step in no_model["steps"]], ["PASS", "PASS", "NOT RUN", "NOT RUN", "NOT RUN"])
            self.assertFalse(no_model["ok"])

    def test_setup_reports_first_solver_failure_and_does_not_claim_later_steps(self):
        with tempfile.TemporaryDirectory() as location, patch(
            "spice_engine._run_simulation", side_effect=SpiceError("timeout", "test fixture")
        ) as engine:
            report = check_setup(executable=_EXECUTABLE, profile_path=_write_profile(Path(location)))
        self.assertFalse(report["ok"])
        self.assertEqual([step["status"] for step in report["steps"]], ["PASS", "PASS", "FAIL", "NOT RUN", "NOT RUN"])
        self.assertEqual(report["steps"][2]["code"], "timeout")
        engine.assert_called_once()

    def test_setup_rejects_a_real_but_incorrect_divider_reading(self):
        incorrect = """Fixture: differs from the reference supply
VSUPPLY in 0 DC 8
RUPPER in out 1k
RLOWER out 0 1k
.op
.save v(out)
.end
"""
        with patch("spice_engine._CHECK_DIVIDER", incorrect), patch("spice_engine._run_simulation") as engine:
            report = check_setup(executable=_EXECUTABLE)
        self.assertFalse(report["ok"])
        self.assertEqual(report["steps"][1]["code"], "divider_voltage")
        self.assertAlmostEqual(report["steps"][1]["value_v"], 4.0)
        self.assertEqual([step["status"] for step in report["steps"]], ["PASS", "FAIL", "NOT RUN", "NOT RUN", "NOT RUN"])
        engine.assert_not_called()

    def test_design_candidate_matches_independent_dc_and_ac_requests(self):
        inputs = {key: value for key, value in _DEFAULTS.items() if key not in {"amp", "freq"}}
        with tempfile.TemporaryDirectory() as location:
            profile = _write_profile(Path(location))
            evidence = Path(location) / "evidence"
            search = design_search(inputs, 4, 2, profile_path=profile, executable=_EXECUTABLE, evidence_dir=evidence)
            self.assertEqual(search["total"], 9)
            self.assertGreaterEqual(search["evaluated"], 1)
            self.assertEqual(search["frequency_hz"], 1000)
            self.assertGreaterEqual(len(search["candidates"]), 1)
            self.assertLessEqual(len(search["candidates"]), 3)
            candidate = search["candidates"][0]
            self.assertTrue(candidate["passed"])
            values = dict(inputs, rc=candidate["rc_kohm"], re=candidate["re_kohm"])
            dc = simulate("dc", values, profile_path=profile, executable=_EXECUTABLE)
            ac = simulate("ac", values, profile_path=profile, executable=_EXECUTABLE)
            at_target = next(row for row in ac["data"]["samples"] if row["frequency_hz"] == search["frequency_hz"])
            self.assertAlmostEqual(candidate["ic_ma"], dc["data"]["point"]["ic_a"] * 1000)
            self.assertAlmostEqual(candidate["gain_db"], at_target["gain_db"])
            self.assertEqual(candidate["model_sha256"], dc["provenance"]["sha256"])
            for key in ("dc_run_id", "ac_run_id"):
                self.assertTrue((evidence / candidate[key] / "run.raw").is_file())

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
