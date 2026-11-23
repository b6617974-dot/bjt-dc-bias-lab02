"""Run the Lab 04 reference circuit in ngspice and validate its ASCII results."""

import cmath
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from uuid import uuid4


FIELD_SPECS = {
    "vcc": ("VCC", "V", 12),
    "r1": ("R1", "kΩ", 100),
    "r2": ("R2", "kΩ", 22),
    "rc": ("RC", "kΩ", 2.2),
    "re": ("RE", "kΩ", 1),
    "rl": ("RL", "kΩ", 10),
    "cin": ("Cin", "µF", 10),
    "cout": ("Cout", "µF", 10),
    "amp": ("Vin", "mV peak", 10),
    "freq": ("f", "kHz", 1),
}
_SCALE = {"V": 1, "kΩ": 1000, "µF": 1e-6, "mV peak": 1e-3, "kHz": 1000}
_PLOTS = {"dc": "operating point", "ac": "ac analysis", "tran": "transient analysis"}
_VECTORS = {
    "dc": {
        "v(vcc)": "voltage", "v(b)": "voltage", "v(c)": "voltage", "v(e)": "voltage",
        "i(vsenseb)": "current", "i(vsensec)": "current", "i(vsensee)": "current",
    },
    "ac": {"frequency": "frequency", "v(vin)": "voltage", "v(vout)": "voltage"},
    "tran": {"time": "time", "v(vin)": "voltage", "v(vout)": "voltage"},
}
_UNITS = {
    "dc": {
        "vb_v": "V", "ve_v": "V", "vc_v": "V", "vce_v": "V",
        "ib_a": "A", "ic_a": "A", "ie_a": "A",
    },
    "ac": {
        "frequency_hz": "Hz", "gain_db": "dB", "phase_deg": "°",
        "vin_re_v": "V", "vin_im_v": "V", "vout_re_v": "V", "vout_im_v": "V",
    },
    "tran": {
        "time_s": "s", "vin_v": "V", "vout_v": "V",
        "vin_pp_half_v": "V", "vout_pp_half_v": "V",
    },
}
_MAX_POINTS = 20_000
_MAX_RAW_BYTES = 8 * 1024 * 1024
_TIMEOUT = 10
_ABS_CURRENT_TOLERANCE = 1e-12
_REL_CURRENT_TOLERANCE = 1e-3
_SPICE_NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*")
_FATAL_LOG = re.compile(
    r"(?im)^\s*(?:error(?:\s|:)|fatal(?:\s|:)|timestep too small)|\bsimulation(?:s)? aborted\b"
)


class SpiceError(Exception):
    """A failure whose code and safe message can be rendered by the web app."""

    def __init__(self, code, message, fields=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.fields = fields or {}


def _parse_inputs(analysis, inputs):
    if not isinstance(analysis, str) or analysis not in _PLOTS:
        raise SpiceError("input", "Select DC, AC, or Transient.")
    if not isinstance(inputs, dict):
        raise SpiceError("input", "Send numeric inputs for the selected analysis.")

    fields = FIELD_SPECS if analysis == "tran" else tuple(FIELD_SPECS)[:-2]
    values, errors = {}, {}
    for key in fields:
        value = inputs.get(key)
        try:
            if type(value) not in (int, float, str):
                raise ValueError
            result = float(value) * _SCALE[FIELD_SPECS[key][1]]
            if not math.isfinite(result) or result <= 0:
                raise ValueError
        except (ValueError, OverflowError):
            errors[key] = "Enter a finite number greater than zero."
            continue
        if key == "freq" and not 1 <= result <= 10_000:
            errors[key] = "Enter 0.001–10 kHz."
        else:
            values[key] = result
    if errors:
        raise SpiceError("input", "Check the highlighted inputs.", errors)
    return values


def _load_profile(profile_path):
    if not profile_path:
        raise SpiceError("profile", "The server has not selected a transistor model.")
    profile_path = Path(profile_path)
    try:
        profile = json.loads(profile_path.read_text(encoding="utf-8-sig"))
        required = ("id", "name", "classification", "source", "model_file", "model_name", "sha256", "kind")
        if not isinstance(profile, dict) or any(
            not isinstance(profile.get(key), str) or not profile[key].strip() for key in required
        ):
            raise ValueError("profile fields are missing or blank")
        if profile["classification"] not in ("provisional", "instructor"):
            raise ValueError("unknown model classification")
        name = profile["model_name"]
        if not _SPICE_NAME.fullmatch(name) or not re.fullmatch(r"[a-fA-F0-9]{64}", profile["sha256"]):
            raise ValueError("invalid model name or SHA-256")
        model_file = profile_path.parent / profile["model_file"]
        model_bytes = model_file.read_bytes()
        if hashlib.sha256(model_bytes).hexdigest() != profile["sha256"].lower():
            raise ValueError("the model file does not match its SHA-256")
        model = model_bytes.decode("ascii")
        _validate_model(profile, model)
    except (OSError, ValueError) as exc:
        message = str(exc) if type(exc) is ValueError else "could not read the configured profile or model file"
        raise SpiceError("profile", f"Model unavailable: {message}.") from exc
    return profile, model_bytes


def _validate_model(profile, model):
    """Accept self-contained model definitions, never a second circuit deck."""
    name = profile["model_name"].lower()
    kind = profile["kind"]
    if kind not in ("model", "subckt"):
        raise ValueError("the configured model format is unsupported")

    declarations = 0
    inside = False
    continuation = False
    for raw in model.splitlines():
        statement = raw.strip()
        if not statement or statement.startswith("*"):
            continue
        if statement.startswith("+"):
            if not continuation:
                raise ValueError("unexpected model continuation")
            continue
        parts = statement.lower().split()
        if not parts:
            continue
        command = parts[0]
        continuation = command != ".ends"
        if command == ".model" and len(parts) >= 3:
            if kind == "model" and parts[1] == name:
                if parts[2].split("(")[0] != "npn":
                    raise ValueError("the selected model must be NPN")
                declarations += 1
        elif kind == "subckt" and command == ".subckt" and len(parts) >= 2 and not inside:
            inside = True
            if parts[1] == name:
                if len(parts) != 5 or len(set(parts[2:])) != 3:
                    raise ValueError("the selected subcircuit must have three distinct terminals")
                declarations += 1
        elif kind == "subckt" and command == ".ends" and inside:
            inside = False
        elif not (kind == "subckt" and inside and not command.startswith(".")):
            raise ValueError("the model must contain only self-contained device definitions")
    pins = profile.get("pins")
    if kind == "subckt" and (
        not isinstance(pins, list) or len(pins) != 3 or any(type(pin) is not str for pin in pins)
        or set(pins) != set("BCE")
    ):
        raise ValueError("the subcircuit profile must map B, C and E exactly once")
    if inside or declarations != 1:
        raise ValueError("the named NPN model or subcircuit was not declared exactly once")


def _tran_stop(freq):
    return max(0.004, 4 / freq)


def _netlist(analysis, values, profile):
    if profile["kind"] == "subckt":
        nodes = " ".join(f"q{pin.lower()}" for pin in profile["pins"])
        transistor = f"XQ1 {nodes} {profile['model_name']}"
    else:
        transistor = f"Q1 qc qb qe {profile['model_name']}"

    if analysis == "dc":
        source, directive = "VIN vin 0 DC 0", ".op"
    elif analysis == "ac":
        source, directive = "VIN vin 0 DC 0 AC 1", ".ac dec 40 10 1e6"
    else:
        stop = _tran_stop(values["freq"])
        step = min(1 / values["freq"] / 100, stop / 400)
        source = f"VIN vin 0 SIN(0 {values['amp']:.17g} {values['freq']:.17g})"
        directive = f".tran {step:.17g} {stop:.17g} 0 {step:.17g}"

    vectors = " ".join(name for name in _VECTORS[analysis] if name not in ("time", "frequency"))
    lines = [
        "Lab 04 CE voltage divider",
        ".include model.inc",
        f"VCC vcc 0 DC {values['vcc']:.17g}",
        source,
        f"R1 vcc b {values['r1']:.17g}",
        f"R2 b 0 {values['r2']:.17g}",
        f"RC vcc c {values['rc']:.17g}",
        f"RE e 0 {values['re']:.17g}",
        f"RL vout 0 {values['rl']:.17g}",
        f"CIN vin b {values['cin']:.17g}",
        f"COUT c vout {values['cout']:.17g}",
        "VSENSEB b qb 0",
        "VSENSEC c qc 0",
        "VSENSEE qe e 0",
        transistor,
        directive,
        f".save {vectors}",
        ".end",
    ]
    return "\n".join(lines) + "\n"


def _read_raw(raw_path, analysis):
    """Read one real or complex ASCII plot and validate all vector samples."""
    try:
        if raw_path.stat().st_size > _MAX_RAW_BYTES:
            raise ValueError("oversized raw file")
        header, marker, vectors_and_values = raw_path.read_text(encoding="ascii").partition("\nVariables:\n")
        vector_lines, value_marker, values = vectors_and_values.partition("\nValues:\n")
        if not marker or not value_marker:
            raise ValueError("missing ASCII raw sections")

        metadata = {}
        required = {"plotname", "flags", "no. variables", "no. points"}
        for line in header.splitlines():
            key, _, item = line.partition(":")
            key = key.strip().lower()
            if key in required:
                if key in metadata:
                    raise ValueError("duplicate raw header")
                metadata[key] = item.strip().lower()
        if required.difference(metadata) or metadata["plotname"] != _PLOTS[analysis]:
            raise ValueError("unexpected plot type")
        complex_values = analysis == "ac"
        flags = set(metadata["flags"].split())
        if flags.intersection(("real", "complex")) != {"complex" if complex_values else "real"}:
            raise ValueError("unexpected plot number format")

        vector_count, point_count = int(metadata["no. variables"]), int(metadata["no. points"])
        expected = _VECTORS[analysis]
        if vector_count != len(expected):
            raise ValueError("unexpected vector count")
        if not (1 <= point_count <= _MAX_POINTS) or (point_count == 1) != (analysis == "dc"):
            raise ValueError("unexpected point count")
        names = []
        for index, line in enumerate(vector_lines.splitlines()):
            parts = line.lower().split()
            if len(parts) < 3:
                raise ValueError("incomplete vector definition")
            position, name, unit, *attributes = parts
            if int(position) != index or expected.get(name) != unit:
                raise ValueError("unexpected vector definition")
            if attributes and not (name == "frequency" and attributes == ["grid=3"]):
                raise ValueError("unexpected vector attributes")
            names.append(name)
        if len(names) != vector_count or set(names) != set(expected):
            raise ValueError("missing or repeated vector")

        tokens = values.split()
        width = vector_count + 1
        if len(tokens) != point_count * width:
            raise ValueError("incomplete raw data")
        rows = []
        for index in range(point_count):
            entry = tokens[index * width : (index + 1) * width]
            if int(entry[0]) != index:
                raise ValueError("invalid point index")
            numbers = []
            for token in entry[1:]:
                if complex_values:
                    real, imaginary = map(float, token.split(","))
                    if not math.isfinite(real) or not math.isfinite(imaginary):
                        raise ValueError("nonfinite raw point")
                    numbers.append(complex(real, imaginary))
                else:
                    value = float(token)
                    if not math.isfinite(value):
                        raise ValueError("nonfinite raw point")
                    numbers.append(value)
            rows.append(dict(zip(names, numbers)))
    except (OSError, ValueError) as exc:
        raise SpiceError("output", "ngspice did not provide a complete result for this analysis.") from exc
    return rows


def _dc_data(row, values):
    vb, vc, ve, supply = (row[node] for node in ("v(b)", "v(c)", "v(e)", "v(vcc)"))
    ib, ic, ie = (row[name] for name in ("i(vsenseb)", "i(vsensec)", "i(vsensee)"))
    if not math.isclose(supply, values["vcc"], rel_tol=1e-9, abs_tol=1e-12):
        raise SpiceError("output", "The DC supply in the result does not match this run.")
    point = {"vb_v": vb, "ve_v": ve, "vc_v": vc, "vce_v": vc - ve, "ib_a": ib, "ic_a": ic, "ie_a": ie}
    if not math.isfinite(point["vce_v"]):
        raise SpiceError("output", "The collector–emitter voltage is outside the numeric range.")
    conditions = {
        "base": ((supply - vb) / values["r1"], -vb / values["r2"], -ib),
        "collector": ((supply - vc) / values["rc"], -ic),
        "emitter": (ve / values["re"], -ie),
        "transistor": (ib, ic, -ie),
    }
    checks = {}
    for name, terms in conditions.items():
        scale = sum(abs(term) for term in terms)
        residual = sum(terms)
        tolerance = _ABS_CURRENT_TOLERANCE + _REL_CURRENT_TOLERANCE * scale
        if not math.isfinite(residual) or not math.isfinite(tolerance) or abs(residual) > tolerance:
            raise SpiceError("output", f"The {name} current check failed for this DC result.")
        checks[name] = {"residual_a": residual, "tolerance_a": tolerance, "passed": True}
    warnings = []
    if not (vc > vb > ve and ib > 0 and ic > 0):
        warnings.append("The DC bias is outside the expected forward-active amplifier conditions.")
    return {"point": point, "checks": checks}, warnings


def _log_magnitude(value):
    scale = max(abs(value.real), abs(value.imag))
    return math.log10(scale) + math.log10(math.hypot(value.real / scale, value.imag / scale))


def _ac_data(rows):
    samples, warnings = [], []
    previous_phase = None
    previous_frequency = 0.0
    gaps = 0
    for row in rows:
        # ngspice writes its scale as a complex slot in the AC plot.
        frequency = row["frequency"].real
        if frequency <= previous_frequency:
            raise SpiceError("output", "AC frequencies must be positive and strictly increasing.")
        previous_frequency = frequency
        vin, vout = row["v(vin)"], row["v(vout)"]
        gain = phase = None
        if vin and vout:
            # Log magnitudes and angles of Vout/Vin without forming an overflowing quotient.
            gain = 20 * (_log_magnitude(vout) - _log_magnitude(vin))
            phase = math.degrees(cmath.phase(vout) - cmath.phase(vin))
            reference = previous_phase if previous_phase is not None else 0
            phase += 360 * round((reference - phase) / 360)
        if phase is None:
            gaps += 1
        previous_phase = phase
        samples.append({
            "frequency_hz": frequency, "gain_db": gain, "phase_deg": phase,
            "vin_re_v": vin.real, "vin_im_v": vin.imag, "vout_re_v": vout.real, "vout_im_v": vout.imag,
        })
    if (
        len(samples) != 201 or not math.isclose(samples[0]["frequency_hz"], 10, rel_tol=1e-9)
        or not math.isclose(samples[-1]["frequency_hz"], 1e6, rel_tol=1e-9)
    ):
        raise SpiceError("output", "AC output does not cover the requested sweep.")
    if gaps:
        warnings.append("Gain and phase are unavailable at frequencies where the voltage ratio is undefined.")
    return {"samples": samples}, warnings


def _tran_data(rows, values):
    stop = _tran_stop(values["freq"])
    if rows[0]["time"] != 0 or not math.isclose(rows[-1]["time"], stop, rel_tol=1e-9, abs_tol=1e-12):
        raise SpiceError("output", "Transient output does not cover the requested time window.")
    times = [row["time"] for row in rows]
    if any(right <= left for left, right in zip(times, times[1:])):
        raise SpiceError("output", "Transient output times must be strictly increasing.")
    samples = [
        {"time_s": row["time"], "vin_v": row["v(vin)"], "vout_v": row["v(vout)"]}
        for row in rows
    ]
    summary = {}
    for label, vector in (("vin", "v(vin)"), ("vout", "v(vout)")):
        readings = [row[vector] for row in rows]
        summary[f"{label}_pp_half_v"] = max(readings) / 2 - min(readings) / 2
    return {"samples": samples, "summary": summary}, []


def _invoke(executable, args, directory):
    env = dict(os.environ, SPICE_ASCIIRAWFILE="1")
    try:
        return subprocess.run(
            [executable, *args], cwd=directory, env=env, shell=False, timeout=_TIMEOUT,
            capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise SpiceError("timeout", "ngspice exceeded the 10-second time limit.") from exc
    except OSError as exc:
        raise SpiceError("engine", "The server could not start ngspice.") from exc


def _save_evidence(directory, evidence_dir, run_id):
    destination = Path(evidence_dir) / run_id
    destination.mkdir(parents=True)
    for name in ("circuit.cir", "run.raw", "run.log"):
        artifact = directory / name
        if artifact.is_file():
            shutil.copyfile(artifact, destination / name)


def simulate(analysis, inputs, *, profile_path=None, executable=None, evidence_dir=None):
    """Validate form values, run the selected model, and return one result in SI."""
    values = _parse_inputs(analysis, inputs)
    profile, model_bytes = _load_profile(profile_path)
    program = shutil.which(str(executable) if executable else "ngspice")
    if not program:
        raise SpiceError("engine", "ngspice was not found. Check the server configuration.")
    program = str(Path(program).resolve())
    run_id = uuid4().hex
    deck = _netlist(analysis, values, profile).encode("ascii")
    try:
        with tempfile.TemporaryDirectory(prefix="lab04-") as location:
            directory = Path(location)
            (directory / "model.inc").write_bytes(model_bytes)
            (directory / "circuit.cir").write_bytes(deck)
            version = _invoke(program, ["-v"], directory)
            match = re.search(r"\bngspice-([\w.+-]+)", version.stdout + version.stderr, re.IGNORECASE)
            if version.returncode or not match:
                raise SpiceError("engine", "The configured command did not report an ngspice version.")

            try:
                result = _invoke(program, ["-n", "-b", "-o", "run.log", "-r", "run.raw", "circuit.cir"], directory)
                log_path = directory / "run.log"
                if result.returncode:
                    raise SpiceError("solver", "ngspice could not complete this simulation.")
                if not log_path.is_file():
                    raise SpiceError("output", "ngspice did not provide a run log.")
                log = log_path.read_text(encoding="utf-8", errors="replace")
                if _FATAL_LOG.search(log + "\n" + result.stderr):
                    raise SpiceError("solver", "ngspice reported an error during simulation.")
                rows = _read_raw(directory / "run.raw", analysis)
                if analysis == "dc":
                    data, warnings = _dc_data(rows[0], values)
                elif analysis == "ac":
                    data, warnings = _ac_data(rows)
                else:
                    data, warnings = _tran_data(rows, values)
                if re.search(r"(?im)^\s*warning(?:\s|:)", log):
                    warnings.append("ngspice reported warnings. Check the run log for details.")
            except SpiceError:
                if evidence_dir:
                    try:
                        _save_evidence(directory, evidence_dir, run_id)
                    except OSError:
                        pass  # Preserve the primary simulation error.
                raise
            if evidence_dir:
                _save_evidence(directory, evidence_dir, run_id)
    except OSError as exc:
        raise SpiceError("output", "The server could not read or save the simulation files.") from exc

    provenance = {key: profile[key] for key in ("id", "name", "classification", "model_name", "source")}
    return {
        "ok": True, "analysis": analysis, "run_id": run_id, "inputs_si": values,
        "provenance": {
            **provenance, "sha256": profile["sha256"].lower(), "ngspice_version": match[1],
            "netlist_sha256": hashlib.sha256(deck).hexdigest(),
        },
        "units": _UNITS[analysis].copy(), "data": data, "warnings": warnings,
    }
