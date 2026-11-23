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
from time import monotonic
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
_MAX_PROFILE_BYTES = 64 * 1024
_MAX_MODEL_BYTES = 1024 * 1024
_TIMEOUT = 10
_CHECK_TIMEOUT = 20
_CHECK_STEPS = ("version", "divider", *_PLOTS)
_CHECK_DIVIDER = """Lab 04 setup check: equal-resistance divider
VSUPPLY in 0 DC 10
RUPPER in out 1k
RLOWER out 0 1k
.op
.save v(out)
.end
"""
_DESIGN_FREQUENCY_HZ = 1000
_DESIGN_STEPS = (1.0, 0.67, 1.5)
_ABS_CURRENT_TOLERANCE = 1e-12
_REL_CURRENT_TOLERANCE = 1e-3
_SPICE_NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*")
_NGSPICE_VERSION = re.compile(r"[A-Za-z0-9_.+-]{1,64}")
_FATAL_LOG = re.compile(
    r"(?im)^\s*(?:error(?:\s|:)|fatal(?:\s|:)|timestep too small)|\bsimulation(?:s)? aborted\b"
)


class SpiceError(Exception):
    """A failure whose code and safe message can be rendered by the web app."""

    def __init__(self, code, message, fields=None, *, reason=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.fields = fields or {}
        self.reason = reason or code


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


def _profile_error(reason, message):
    return SpiceError("profile", message, reason=reason)


def _bounded_read(path, limit):
    if not path.is_file():
        raise OSError("not a regular file")
    with path.open("rb") as stream:
        return stream.read(limit + 1)


def _unique_fields(pairs):
    fields = dict(pairs)
    if len(fields) != len(pairs):
        raise ValueError("duplicate profile field")
    return fields


def _load_profile(profile_path):
    if not profile_path:
        raise _profile_error("profile_unconfigured", "The server has not selected a transistor model.")
    try:
        profile_path = Path(profile_path).resolve(strict=True)
        content = _bounded_read(profile_path, _MAX_PROFILE_BYTES)
        if len(content) > _MAX_PROFILE_BYTES:
            raise ValueError("oversized profile")
        profile = json.loads(content.decode("utf-8-sig"), object_pairs_hook=_unique_fields)
    except FileNotFoundError as exc:
        raise _profile_error("profile_missing", "The configured profile file was not found.") from exc
    except (OSError, ValueError, RuntimeError) as exc:
        raise _profile_error("profile_invalid", "The configured profile could not be read as a valid JSON object.") from exc

    required = ("id", "name", "classification", "source", "model_file", "model_name", "sha256", "kind")
    if not isinstance(profile, dict) or any(
        not isinstance(profile.get(key), str) or not profile[key].strip() for key in required
    ) or profile["classification"] not in ("provisional", "instructor"):
        raise _profile_error("profile_invalid", "The profile is missing fields or has an unknown classification.")
    if not _SPICE_NAME.fullmatch(profile["model_name"]) or not re.fullmatch(r"[a-fA-F0-9]{64}", profile["sha256"]):
        raise _profile_error("profile_invalid", "Check the model name and the 64-character SHA-256.")

    filename = profile["model_file"]
    if filename.endswith((" ", ".")) or re.search(r"[:/\\\x00-\x1f]", filename):
        raise _profile_error("model_path", "Use a model filename in the same folder as the profile.")
    try:
        model_file = (profile_path.parent / filename).resolve()
    except (OSError, ValueError, RuntimeError) as exc:
        raise _profile_error("model_path", "The model filename could not be resolved safely.") from exc
    if model_file.parent != profile_path.parent:
        raise _profile_error("model_path", "The model must resolve inside the profile folder.")
    try:
        model_bytes = _bounded_read(model_file, _MAX_MODEL_BYTES)
    except OSError as exc:
        raise _profile_error("model_missing", "The model file is missing or could not be read.") from exc
    if len(model_bytes) > _MAX_MODEL_BYTES:
        raise _profile_error("model_too_large", "The model file exceeds the 1 MiB limit.")
    if hashlib.sha256(model_bytes).hexdigest() != profile["sha256"].lower():
        raise _profile_error("model_checksum", "The model file does not match the profile SHA-256.")
    try:
        model = model_bytes.decode("ascii")
    except UnicodeDecodeError as exc:
        raise _profile_error("model_format", "The model file must be ASCII SPICE text.") from exc
    _validate_model(profile, model)
    return profile, model_bytes


def _validate_model(profile, model):
    """Accept self-contained model definitions, never a second circuit deck."""
    name = profile["model_name"].lower()
    kind = profile["kind"]
    if kind not in ("model", "subckt"):
        raise _profile_error("model_format", "The configured model format is unsupported.")

    declarations = 0
    inside = False
    continuation = False
    for raw in model.splitlines():
        statement = raw.strip()
        if not statement or statement.startswith("*"):
            continue
        if statement.startswith("+"):
            if not continuation:
                raise _profile_error("model_declaration", "The model has an unexpected continuation line.")
            continue
        parts = statement.lower().split()
        if not parts:
            continue
        command = parts[0]
        continuation = command != ".ends"
        if command == ".model" and len(parts) >= 3:
            if kind == "model" and parts[1] == name:
                if parts[2].split("(")[0] != "npn":
                    raise _profile_error("model_declaration", "The selected model must be NPN.")
                declarations += 1
        elif kind == "subckt" and command == ".subckt" and len(parts) >= 2 and not inside:
            inside = True
            if parts[1] == name:
                if len(parts) != 5 or len(set(parts[2:])) != 3:
                    raise _profile_error("model_declaration", "The selected subcircuit must have three distinct terminals.")
                declarations += 1
        elif kind == "subckt" and command == ".ends" and inside:
            inside = False
        elif not (kind == "subckt" and inside and not command.startswith(".")):
            raise _profile_error("model_declaration", "The model must contain only self-contained device definitions.")
    pins = profile.get("pins")
    if kind == "subckt" and (
        not isinstance(pins, list) or len(pins) != 3 or any(type(pin) is not str for pin in pins)
        or set(pins) != set("BCE")
    ):
        raise _profile_error("model_pins", "The subcircuit profile must map B, C and E exactly once.")
    if inside or declarations != 1:
        raise _profile_error("model_declaration", "The named NPN model or subcircuit must be declared exactly once.")


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


def _read_raw(raw_path, analysis, *, vectors=None):
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
        expected = _VECTORS[analysis] if vectors is None else vectors
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


def _forward_active(point):
    return point["vc_v"] > point["vb_v"] > point["ve_v"] and point["ib_a"] > 0 and point["ic_a"] > 0


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
    if not _forward_active(point):
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


def _invoke(executable, args, directory, *, deadline=None):
    env = dict(os.environ, SPICE_ASCIIRAWFILE="1")
    timeout = _TIMEOUT
    if deadline is not None:
        timeout = min(timeout, deadline - monotonic())
        if timeout <= 0:
            raise SpiceError("timeout", "The ngspice operation reached its time limit.")
    try:
        return subprocess.run(
            [executable, *args], cwd=directory, env=env, shell=False, timeout=timeout,
            capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
        )
    except subprocess.TimeoutExpired as exc:
        message = ("ngspice exceeded the 10-second time limit." if deadline is None
                   else "The ngspice operation reached its time limit.")
        raise SpiceError("timeout", message) from exc
    except OSError as exc:
        raise SpiceError("engine", "The server could not start ngspice.") from exc


def _save_evidence(directory, evidence_dir, run_id):
    destination = Path(evidence_dir) / run_id
    destination.mkdir(parents=True)
    for name in ("circuit.cir", "run.raw", "run.log"):
        artifact = directory / name
        if artifact.is_file():
            shutil.copyfile(artifact, destination / name)


def _solver_path(executable):
    program = shutil.which(str(executable) if executable else "ngspice")
    if not program:
        raise SpiceError("engine", "ngspice was not found. Check the server configuration.",
                         reason="engine_missing")
    try:
        return str(Path(program).resolve())
    except (OSError, RuntimeError) as exc:
        raise SpiceError("engine", "The configured ngspice executable could not be resolved.") from exc


def _probe_version(program, directory, *, deadline=None):
    version = _invoke(program, ["-v"], directory, deadline=deadline)
    match = re.search(rf"\bngspice-({_NGSPICE_VERSION.pattern})(?=\s|$)", version.stdout + version.stderr, re.IGNORECASE)
    if version.returncode or not match:
        raise SpiceError("engine", "The configured command did not report an ngspice version.")
    return match[1]


def _run_batch(program, directory, *, deadline=None):
    result = _invoke(
        program, ["-n", "-b", "-o", "run.log", "-r", "run.raw", "circuit.cir"],
        directory, deadline=deadline,
    )
    if result.returncode:
        raise SpiceError("solver", "ngspice could not complete this simulation.")
    try:
        log = _bounded_read(directory / "run.log", _MAX_RAW_BYTES)
    except OSError as exc:
        raise SpiceError("output", "ngspice did not provide a readable run log.") from exc
    if len(log) > _MAX_RAW_BYTES:
        raise SpiceError("output", "The ngspice run log exceeded the size limit.")
    log = log.decode("utf-8", errors="replace")
    if _FATAL_LOG.search(log + "\n" + result.stderr):
        raise SpiceError("solver", "ngspice reported an error during simulation.")
    return log


def _profile_metadata(profile):
    fields = {key: profile[key] for key in ("name", "classification", "kind", "model_name")}
    if profile["kind"] == "subckt":
        fields["pins"] = profile["pins"].copy()
    return dict(fields, sha256=profile["sha256"].lower())


def setup_status(*, profile_path=None, executable=None):
    """Report configuration availability without launching a process."""
    engine = {"status": "available", "resolution": "configured" if executable else "path", "code": None}
    try:
        _solver_path(executable)
    except SpiceError as error:
        engine = {"status": "unavailable", "resolution": None, "code": error.reason}
    try:
        profile, _ = _load_profile(profile_path)
    except SpiceError as error:
        model = {"status": "unavailable", "code": error.reason}
    else:
        model = {"status": "available", **_profile_metadata(profile)}
    return {"engine": engine, "profile": model}


def check_setup(*, profile_path=None, executable=None, evidence_dir=None):
    """Check the executable and a fixed reference circuit under one deadline."""
    deadline = monotonic() + _CHECK_TIMEOUT
    steps = {step: {"id": step, "status": "NOT RUN"} for step in _CHECK_STEPS}
    report = {"ok": False, "steps": list(steps.values())}
    stage = "version"
    try:
        program = _solver_path(executable)
        divider_id = uuid4().hex
        with tempfile.TemporaryDirectory(prefix="lab04-check-") as location:
            directory = Path(location)
            version = _probe_version(program, directory, deadline=deadline)
            steps[stage].update(status="PASS", version=version)
            report["engine_version"] = version

            stage = "divider"
            (directory / "circuit.cir").write_bytes(_CHECK_DIVIDER.encode("ascii"))
            _run_batch(program, directory, deadline=deadline)
            divider = _read_raw(directory / "run.raw", "dc", vectors={"v(out)": "voltage"})[0]["v(out)"]
            if evidence_dir:
                _save_evidence(directory, evidence_dir, divider_id)
            steps[stage].update(value_v=divider, run_id=divider_id)
            if not math.isclose(divider, 5.0, rel_tol=0, abs_tol=1e-6):
                raise SpiceError("output", "The reference divider did not measure 5 V.", reason="divider_voltage")
            steps[stage]["status"] = "PASS"
    except SpiceError as error:
        steps[stage].update(status="FAIL", code=error.reason)
        return report
    except OSError:
        steps[stage].update(status="FAIL", code="output")
        return report

    try:
        profile, model_bytes = _load_profile(profile_path)
    except SpiceError as error:
        report["profile"] = {"status": "unavailable", "code": error.reason}
        for stage in _PLOTS:
            steps[stage]["code"] = error.reason
        return report

    report["profile"] = {"status": "available", **_profile_metadata(profile)}
    defaults = {key: field[2] for key, field in FIELD_SPECS.items()}
    for stage in _PLOTS:
        try:
            result = _run_simulation(stage, _parse_inputs(stage, defaults), profile, model_bytes, program,
                                     evidence_dir=evidence_dir, deadline=deadline)
            if result["provenance"]["ngspice_version"] != version:
                raise SpiceError("engine", "The executable version changed during the check.")
        except SpiceError as error:
            steps[stage].update(status="FAIL", code=error.reason)
            return report
        steps[stage].update(status="PASS", run_id=result["run_id"])
    report["ok"] = True
    return report


def verified_setup_status(path, active_profile, *, executable=None):
    """Return the image build receipt for its pinned executable and model."""
    if not path or active_profile.get("status") != "available":
        return None
    try:
        content = _bounded_read(Path(path), _MAX_PROFILE_BYTES)
        if len(content) > _MAX_PROFILE_BYTES:
            return None
        report = json.loads(content, object_pairs_hook=_unique_fields)
    except (OSError, ValueError, RuntimeError):
        return None

    if not isinstance(report, dict) or report.get("ok") is not True:
        return None
    try:
        if report.get("executable") != _solver_path(executable):
            return None
    except SpiceError:
        return None
    profile = report.get("profile")
    identity = ("sha256", "model_name", "kind", "pins", "classification")
    if not isinstance(profile, dict) or any(profile.get(key) != active_profile.get(key) for key in identity):
        return None
    version, steps = report.get("engine_version"), report.get("steps")
    if not isinstance(version, str) or not _NGSPICE_VERSION.fullmatch(version):
        return None
    if not isinstance(steps, list) or len(steps) != len(_CHECK_STEPS) or any(
        not isinstance(step, dict) or step.get("id") != expected or step.get("status") != "PASS"
        for expected, step in zip(_CHECK_STEPS, steps)
    ):
        return None
    if steps[0].get("version") != version:
        return None
    voltage = steps[1].get("value_v")
    if type(voltage) not in (int, float) or not 4.999999 <= voltage <= 5.000001:
        return None
    run_ids = [step.get("run_id") for step in steps[1:]]
    if any(not isinstance(run_id, str) or not re.fullmatch(r"[a-f0-9]{32}", run_id) for run_id in run_ids):
        return None
    if len(set(run_ids)) != len(run_ids):
        return None

    safe_steps = [{"id": "version", "status": "PASS", "version": version}]
    safe_steps.extend({"id": stage, "status": "PASS", "run_id": run_id} for stage, run_id in zip(_CHECK_STEPS[1:], run_ids))
    safe_steps[1]["value_v"] = voltage
    return {"source": "build", "engine_version": version, "steps": safe_steps}


def simulate(analysis, inputs, *, profile_path=None, executable=None, evidence_dir=None):
    """Validate form values, run the selected model, and return one result in SI."""
    values = _parse_inputs(analysis, inputs)
    profile, model_bytes = _load_profile(profile_path)
    return _run_simulation(analysis, values, profile, model_bytes, _solver_path(executable), evidence_dir=evidence_dir)


def _run_simulation(analysis, values, profile, model_bytes, program, *, evidence_dir, deadline=None):
    run_id = uuid4().hex
    deck = _netlist(analysis, values, profile).encode("ascii")
    try:
        with tempfile.TemporaryDirectory(prefix="lab04-") as location:
            directory = Path(location)
            (directory / "model.inc").write_bytes(model_bytes)
            (directory / "circuit.cir").write_bytes(deck)
            version = _probe_version(program, directory, deadline=deadline)

            try:
                log = _run_batch(program, directory, deadline=deadline)
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

    provenance = {key: profile[key] for key in ("id", "name", "classification", "model_name", "source", "kind")}
    if profile["kind"] == "subckt":
        provenance["pins"] = profile["pins"].copy()
    return {
        "ok": True, "analysis": analysis, "run_id": run_id, "inputs_si": values,
        "provenance": {
            **provenance, "sha256": profile["sha256"].lower(), "ngspice_version": version,
            "netlist_sha256": hashlib.sha256(deck).hexdigest(),
        },
        "units": _UNITS[analysis].copy(), "data": data, "warnings": warnings,
    }


def _design_target(value, key, *, positive=False):
    try:
        number = float(value) if type(value) in (int, float) else math.nan
    except OverflowError:
        number = math.nan
    if not math.isfinite(number) or (positive and number <= 0):
        message = "Enter a finite number greater than zero." if positive else "Enter a finite gain in dB."
        raise SpiceError("input", "Check the design targets.", {key: message})
    return number


def _design_points(values):
    # The unchanged circuit is checked first. The finite grid only changes RC and RE.
    choices = {}
    for key in ("rc", "re"):
        choices[key] = list(dict.fromkeys(
            adjusted for factor in _DESIGN_STEPS
            if math.isfinite(adjusted := values[key] * factor) and adjusted > 0
        ))
    return [(rc, re) for rc in choices["rc"] for re in choices["re"]]


def design_search(inputs, target_gain_db, max_ic_ma, *, profile_path=None, executable=None, evidence_dir=None):
    """Rank a bounded set of RC and RE pairs using the actual .op and .ac measurements."""
    values = _parse_inputs("dc", inputs)
    if inputs.keys() != values.keys():
        raise SpiceError("input", "Send only the eight Voltage Divider circuit inputs.")
    gain_target = _design_target(target_gain_db, "target_gain_db")
    current_cap = _design_target(max_ic_ma, "max_ic_ma", positive=True)
    points = _design_points(values)
    deadline = monotonic() + _TIMEOUT
    profile, model_bytes = _load_profile(profile_path)
    program = _solver_path(executable)
    version = None

    def run(analysis, candidate_values):
        nonlocal version
        result = _run_simulation(
            analysis, candidate_values, profile, model_bytes, program, evidence_dir=evidence_dir, deadline=deadline,
        )
        current_version = result["provenance"]["ngspice_version"]
        if version is not None and current_version != version:
            raise SpiceError("engine", "The ngspice version changed during the design search.")
        version = current_version
        return result

    evaluated, ranked = 0, []
    for rc, re in points:
        candidate_values = dict(values, rc=rc, re=re)
        try:
            dc = run("dc", candidate_values)
            point = dc["data"]["point"]
            if not _forward_active(point):
                evaluated += 1
                continue
            ac = run("ac", candidate_values)
        except SpiceError as error:
            if error.code != "timeout" or not evaluated:
                raise
            break

        sample = next((
            row for row in ac["data"]["samples"]
            if math.isclose(row["frequency_hz"], _DESIGN_FREQUENCY_HZ, rel_tol=1e-9)
        ), None)
        if sample is None:
            raise SpiceError("output", "The ngspice design result has no sample at 1 kHz.")
        evaluated += 1
        gain = sample["gain_db"]
        if gain is None:
            continue
        current = point["ic_a"] * 1000
        if not math.isfinite(current):
            raise SpiceError("output", "The collector current is outside the numeric display range.")
        # Express both constraint misses on a dB scale before comparing the worst miss.
        gain_gap = max(0.0, gain_target - gain)
        current_gap = max(0.0, 20 * (math.log10(current) - math.log10(current_cap)))
        passed = gain >= gain_target and current <= current_cap
        movement = abs(math.log10(rc) - math.log10(values["rc"])) + abs(math.log10(re) - math.log10(values["re"]))
        score = (not passed, max(gain_gap, current_gap), min(gain_gap, current_gap), movement)
        ranked.append((score, {
            "rc_kohm": rc / 1000, "re_kohm": re / 1000, "ic_ma": current, "gain_db": gain,
            "passed": passed, "dc_run_id": dc["run_id"], "ac_run_id": ac["run_id"],
            "model_sha256": dc["provenance"]["sha256"], "model_name": dc["provenance"]["model_name"],
            "model_label": dc["provenance"]["name"], "model_classification": dc["provenance"]["classification"],
            "ngspice_version": version,
            "warnings": list(dict.fromkeys(dc["warnings"] + ac["warnings"])),
        }))

    ranked.sort(key=lambda item: item[0])
    return {
        "ok": True, "frequency_hz": _DESIGN_FREQUENCY_HZ, "target_gain_db": gain_target, "max_ic_ma": current_cap,
        "model_name": profile["model_name"], "model_label": profile["name"],
        "model_classification": profile["classification"], "model_sha256": profile["sha256"].lower(),
        "ngspice_version": version,
        "evaluated": evaluated, "total": len(points), "eligible": len(ranked), "partial": evaluated < len(points),
        "candidates": [candidate for _, candidate in ranked[:3]],
    }
