"""HTTP validation and presentation for the ENG29 2121 BJT bias lab."""

from collections.abc import Mapping
from dataclasses import replace
from fractions import Fraction
from math import isclose, isfinite, ulp
from os import getenv

from flask import Flask, jsonify, render_template, request

from dc_bias import (
    BiasInputs, BiasResult, EmitterBiasInputs, FixedBiasInputs, InputValidationError,
    InverseDesignError, RESISTANCE_BOUNDS_OHM,
    calculate_by_mode, calculate_reference, emitter_resistance_for_current, validate_bias_inputs,
    validate_emitter_bias_inputs, validate_fixed_bias_inputs,
)
from spice_engine import FIELD_SPECS as SPICE_FIELDS, SpiceError, simulate


DEFAULT_FORM = {
    "vcc": "12", "r1": "100", "r2": "22", "rc": "2.2",
    "re": "1", "beta": "100", "vbe": "0.70",
}
MODES = {"divider": "Voltage Divider Bias", "fixed": "Fixed Bias", "emitter": "Emitter Bias"}
COMMON_DEFAULTS = {"vcc": "12", "rc": "2.2", "beta": "100", "vbe": "0.70"}
MODE_DEFAULTS = {
    "divider": DEFAULT_FORM,
    "fixed": dict(COMMON_DEFAULTS, rb="1000"),
    "emitter": dict(COMMON_DEFAULTS, rb="1000", re="1"),
}
PRESETS = {
    "A1": {"mode":"divider", "label":"Divider", "inputs":DEFAULT_FORM.copy()},
    "A2": {"mode":"fixed", "label":"Fixed", "inputs":MODE_DEFAULTS["fixed"].copy()},
    "A3": {"mode":"emitter", "label":"RE 1 kΩ", "inputs":MODE_DEFAULTS["emitter"].copy()},
    "A4": {"mode":"emitter", "label":"RE 2 kΩ", "inputs":dict(MODE_DEFAULTS["emitter"], re="2")},
    "A5": {"mode":"fixed", "label":"RB 0 kΩ", "inputs":dict(MODE_DEFAULTS["fixed"], rb="0")},
}
RESISTANCE_FORM_BOUNDS = tuple(bound / 1000 for bound in RESISTANCE_BOUNDS_OHM)
SWEEP_POINTS = 41
FIELD_LABELS = {
    "vcc": ("VCC", "V"), "r1": ("R1", "kΩ"),
    "r2": ("R2", "kΩ"), "rb": ("RB", "kΩ"), "rc": ("RC", "kΩ"),
    "re": ("RE", "kΩ"), "beta": ("β", ""), "vbe": ("VBE", "V"),
}
ENGINE_FIELD_NAMES = {
    "vcc_v": "vcc", "r1_ohm": "r1", "r2_ohm": "r2", "rb_ohm": "rb",
    "rc_ohm": "rc", "re_ohm": "re", "beta": "beta", "vbe_v": "vbe",
}
INPUT_TYPES = {
    "divider": (BiasInputs, validate_bias_inputs),
    "fixed": (FixedBiasInputs, validate_fixed_bias_inputs),
    "emitter": (EmitterBiasInputs, validate_emitter_bias_inputs),
}
RESULT_LABELS = {
    "VB_V": "Base voltage (VB)", "VE_V": "Emitter voltage (VE)",
    "VC_V": "Collector voltage (VC)", "VCE_V": "Collector-emitter (VCE)",
    "IB_A": "Base current (IB)", "IC_A": "Collector current (IC)",
    "IE_A": "Emitter current (IE)",
    "VTH_V": "Thévenin voltage (VTH)", "RTH_OHM": "Thévenin resistance (RTH)",
}
SYMBOLS = {
    "VB_V": "V_B", "VE_V": "V_E", "VC_V": "V_C", "VCE_V": "V_CE",
    "IB_A": "I_B", "IC_A": "I_C", "IE_A": "I_E", "VTH_V": "V_TH", "RTH_OHM": "R_TH",
}
CHECK_LABELS = {
    "transistor_kcl": "Transistor KCL", "divider_kcl": "Loaded base-node KCL",
    "base_kvl": "Base-loop KVL and VBE", "collector_kvl": "Collector-loop KVL",
    "collector_drop": "Collector resistor drop", "emitter_ground": "Emitter ground",
    "emitter_drop": "Emitter resistor drop", "vce_identity": "VCE voltage identity",
    "region_consistency": "Operating-region consistency",
}
LEGACY_CHECKS = ("transistor_kcl", "divider_kcl", "collector_drop", "emitter_drop", "vce_identity", "region_consistency")
MODE_CHECKS = {
    "divider": LEGACY_CHECKS,
    "fixed": ("transistor_kcl", "base_kvl", "collector_kvl", "collector_drop", "emitter_ground", "vce_identity", "region_consistency"),
    "emitter": ("transistor_kcl", "base_kvl", "collector_kvl", "collector_drop", "emitter_drop", "vce_identity", "region_consistency"),
}
COMPARISON_ORDER = ("IC_A", "VCE_V", "VB_V", "VE_V", "VC_V", "IB_A", "IE_A", "VTH_V", "RTH_OHM")


def select_mode(values):
    if "mode" not in values:
        return "divider"
    mode = values["mode"]
    if not isinstance(mode, str) or mode not in MODES:
        raise InputValidationError({"mode": "Choose a supported bias circuit."})
    return mode


def parse_inputs(raw: Mapping[str, object], mode="divider", *, form_units=False):
    """Parse the selected form and convert kΩ to Ω at the HTTP boundary."""
    errors = {}
    values = {}
    for name in MODE_DEFAULTS[mode]:
        item = raw.get(name)
        try:
            value = float(str(item).strip()) if item is not None else float("nan")
            if not isfinite(value):
                raise ValueError("non-finite value")
        except (TypeError, ValueError, OverflowError):
            errors[name] = "Enter a finite numeric value."
        else:
            values[name] = value
    if errors:
        raise InputValidationError(errors)
    input_type, validate = INPUT_TYPES[mode]
    params = input_type(**{
        si: values[name] * 1000 if si.endswith("_ohm") else values[name]
        for si, name in ENGINE_FIELD_NAMES.items() if name in values
    })
    try:
        validate(params)
    except InputValidationError as error:
        messages = {}
        for key, reason in error.errors.items():
            if form_units and key.endswith("_ohm"):
                lower, upper = RESISTANCE_FORM_BOUNDS
                reason = f"Choose a resistance from {lower:g} to {upper:g} kΩ."
            messages[ENGINE_FIELD_NAMES.get(key, key)] = reason
        raise InputValidationError(messages) from error
    return params


def _schematic_inputs(form):
    labels = {}
    for name, raw in form.items():
        text = raw.strip()
        try:
            value = float(text)
        except ValueError:
            labels[name] = "—"
            continue
        if not isfinite(value) or value <= 0:
            labels[name] = "—"
        elif len(text) <= 7 and text.isascii() and "_" not in text:
            labels[name] = text
        else:
            compact = f"{value:.4g}"
            labels[name] = compact if len(compact) <= 7 else f"{value:.2e}"
    return labels


def format_result(key, value):
    if value is None:
        return "—"
    value = float(value)
    if key.endswith("_A"):
        scale, unit = (1e6, "µA") if key == "IB_A" else (1e3, "mA")
        scaled = value * scale
        number = f"{scaled:.3e}" if scaled != 0 and abs(scaled) < 0.0005 else f"{scaled:.3f}"
        return f"{number} {unit}"
    if key == "RTH_OHM":
        return f"{value / 1000:.3f} kΩ"
    return f"{value:.3f} V"


def present_result(result: BiasResult) -> dict[str, str]:
    return {key: format_result(key, value) for key, value in result.values.items()}


def _response_data(result: BiasResult) -> dict:
    return {
        "ok": True, "region": result.region, "model": result.model,
        "results": result.values, "display": present_result(result),
        "checks": result.checks, "warnings": result.warnings,
    }


def _calculation_steps(params, point, ref):
    """Substitute the independent reference values into the circuit equations."""
    steps = []

    def number(value):
        return f"{float(value):.10g}"

    def step(id, formula, substitution, key=None, result=""):
        steps.append({
            "id": id, "formula": formula, "substitution": substitution,
            "result": format_result(key, ref[key]) if key else result,
        })

    vcc, vbe, beta = params.vcc_v, params.vbe_v, params.beta
    rc = params.rc_ohm / 1000
    re = getattr(params, "re_ohm", 0) / 1000
    divider = isinstance(params, BiasInputs)
    if divider:
        r1, r2 = params.r1_ohm / 1000, params.r2_ohm / 1000
        step("vth", "V_TH = V_CC × R₂ / (R₁ + R₂)",
             f"{number(vcc)} V × {number(r2)} kΩ / [({number(r1)} + {number(r2)}) kΩ]", "VTH_V")
        step("rth", "R_TH = R₁ × R₂ / (R₁ + R₂)",
             f"({number(r1)} kΩ × {number(r2)} kΩ) / [({number(r1)} + {number(r2)}) kΩ]", "RTH_OHM")
    if "IC_A" not in ref:
        return steps

    ib, ic, ie = (ref[key] * 1000 for key in ("IB_A", "IC_A", "IE_A"))
    vb, ve, vc, vce = (ref[key] for key in ("VB_V", "VE_V", "VC_V", "VCE_V"))
    source = ref["VTH_V"] if divider else vcc
    resistance = ref["RTH_OHM"] / 1000 if divider else params.rb_ohm / 1000
    voltage_symbol, resistance_symbol = ("V_TH", "R_TH") if divider else ("V_CC", "R_B")
    base_terms = f"{number(ib)} mA × {number(resistance)} kΩ + {number(vbe)} V"
    emitter_term = f" + {number(ie)} mA × {number(re)} kΩ" if re else ""

    if point.region == "cutoff_estimate":
        step("cutoff_condition", "V_TH ≤ V_BE", f"{number(source)} V ≤ {number(vbe)} V",
             result="Cutoff estimate; base-emitter conduction and leakage are omitted.")
        step("cutoff_currents", "I_B = I_C = I_E = 0", "Open transistor approximation in DC.", "IC_A")
        step("cutoff_nodes", "V_B = V_TH, V_E = 0, V_C = V_CC",
             f"V_B = {number(vb)} V, V_E = 0 V, V_C = {number(vc)} V")
    else:
        step("base_kvl", f"{voltage_symbol} = I_B × {resistance_symbol} + V_BE" + (" + I_E × R_E" if re else ""),
             f"{number(source)} V = {base_terms}{emitter_term}", result="Loop balance")
        if point.region == "saturation_estimate":
            step("saturation_constraint", "V_CE = 0.20 V; V_C = V_E + V_CE",
                 "Fixed VCE(sat) educational approximation.", "VCE_V")
            step("saturation_emitter", "V_E = [(V_TH − V_BE)/R_TH + (V_CC − V_CE)/R_C] / [1/R_TH + 1/R_C + 1/R_E]",
                 f"[({number(source)} − {number(vbe)})/{number(resistance)} + ({number(vcc)} − 0.20)/{number(rc)}] "
                 f"/ [1/{number(resistance)} + 1/{number(rc)} + 1/{number(re)}] using V and kΩ", "VE_V")
            step("ib", "I_B = (V_TH − V_BE − V_E) / R_TH",
                 f"({number(source)} − {number(vbe)} − {number(ve)}) V / ({number(resistance)} kΩ)", "IB_A")
            step("ic", "I_C = (V_CC − V_CE − V_E) / R_C",
                 f"({number(vcc)} − 0.20 − {number(ve)}) V / ({number(rc)} kΩ)", "IC_A")
        else:
            factor = " + (β + 1) × R_E" if re else ""
            denominator = f"{number(resistance)}"
            if re:
                denominator += f" + ({number(beta)} + 1) × {number(re)}"
            step("ib", f"I_B = ({voltage_symbol} − V_BE) / [{resistance_symbol}{factor}]",
                 f"({number(source)} − {number(vbe)}) V / [({denominator}) kΩ]", "IB_A")
            step("ic", "I_C = β × I_B", f"{number(beta)} × {number(ib)} mA", "IC_A")
        step("transistor_kcl", "I_E = I_B + I_C", f"({number(ib)} + {number(ic)}) mA", "IE_A")
        step("ve", "V_E = I_E × R_E" if re else "V_E = 0 V",
             f"{number(ie)} mA × {number(re)} kΩ" if re else "Emitter is wired directly to ground.", "VE_V")
        step("vb", "V_B = V_E + V_BE", f"({number(ve)} + {number(vbe)}) V", "VB_V")
        step("vbe_identity", "V_B − V_E = V_BE",
             f"({number(vb)} − {number(ve)}) V", result=f"{number(vbe)} V")
        step("vc", "V_C = V_CC − I_C × R_C", f"{number(vcc)} V − {number(ic)} mA × {number(rc)} kΩ", "VC_V")
    step("vce", "V_CE = V_C − V_E", f"({number(vc)} − {number(ve)}) V", "VCE_V")
    if divider:
        step("divider_kcl", "(V_CC − V_B)/R₁ = V_B/R₂ + I_B",
             f"({number(vcc)} − {number(vb)}) V / {number(r1)} kΩ = "
             f"{number(vb)} V / {number(r2)} kΩ + {number(ib)} mA", result="Loaded base-node balance")
    step("collector_kvl", "V_CC = I_C × R_C + V_CE" + (" + I_E × R_E" if re else ""),
         f"{number(vcc)} V = {number(ic)} mA × {number(rc)} kΩ + {number(vce)} V{emitter_term}", result="Loop balance")
    if point.region == "forward_active":
        step("active_region", "I_B > 0; V_CB = V_C − V_B > 0; V_CE > 0.20 V",
             f"I_B = {format_result('IB_A', ref['IB_A'])}, V_CB = {number(vc-vb)} V, V_CE = {number(vce)} V",
             result="Forward-active approximation")
    elif point.region == "saturation_estimate":
        step("saturation_check", "I_B > 0; 0 ≤ I_C ≤ βI_B; V_B > V_C",
             f"I_C = {number(ic)} mA, βI_B = {number(beta*ib)} mA, V_B − V_C = {number(vb-vc)} V",
             result="Bounded saturation estimate")
    return steps


def _quantity_comparison(params, key, manual, calculated):
    if manual is None or calculated is None:
        return "unavailable"
    # Use current-relative precision and account for subtraction at voltage resolution.
    voltage_floor = 8 * max(ulp(params.vcc_v), ulp(params.vbe_v), ulp(manual), ulp(calculated)) if key.endswith("_V") else 0
    return "match" if isclose(manual, calculated, rel_tol=1e-8, abs_tol=voltage_floor) else "different"


def _reference_agrees(params, point):
    ref = calculate_reference(params, point.region)
    return all(_quantity_comparison(params, key, float(ref[key]) if key in ref else None, point.values[key]) == "match"
               for key in COMPARISON_ORDER
               if isinstance(params, BiasInputs) or key not in ("VTH_V", "RTH_OHM"))


def build_calculation(params, point):
    if point is None:
        return {"state": "unavailable", "reason": "Waiting for valid current inputs.", "steps": [], "comparison": []}

    ref = calculate_reference(params, point.region)
    comparison = []
    for key in COMPARISON_ORDER:
        if not isinstance(params, BiasInputs) and key in ("VTH_V", "RTH_OHM"):
            continue
        exact, calculated = ref.get(key), point.values[key]
        manual = float(exact) if exact is not None else None
        state = _quantity_comparison(params, key, manual, calculated)
        comparison.append({
            "key": key, "label": SYMBOLS[key], "state": state,
            "manual": format_result(key, manual), "actual": format_result(key, calculated),
            "manual_raw": manual, "actual_raw": calculated,
        })
    if any(row["state"] == "different" for row in comparison):
        state, reason = "different", "The unrounded reference and solver values differ beyond the numerical tolerance."
    elif any(row["state"] == "unavailable" for row in comparison):
        state, reason = "unavailable", "No valid comparison is available for every operating-point quantity in this model state."
    else:
        state, reason = "match", "The unrounded reference and solver values agree within numerical tolerance."
    return {"state": state, "reason": reason, "steps": _calculation_steps(params, point, ref), "comparison": comparison}


def _trial_diagnostics(params):
    trial = calculate_reference(params, "forward_active", active_trial=True)
    limits = (
        ("ib", trial["IB_A"] * 1_000_000, 0, "µA"),
        ("ic", trial["IC_A"] * 1000, 0, "mA"),
        ("vcb", trial["VC_V"] - trial["VB_V"], 0, "V"),
        ("vce", trial["VCE_V"], Fraction(1, 5), "V"),
    )
    return [{"key": key, "lhs": float(value), "operator": ">", "rhs": float(limit), "unit": unit, "pass": False}
            for key, value, limit, unit in limits if value <= limit]


def _branch_drops(params, values):
    drops = {"RC": values["IC_A"] * params.rc_ohm}
    if isinstance(params, BiasInputs):
        rth_drop = values["IB_A"] * values["RTH_OHM"]
        # VCC − VTH uses the resistor ratio so a tiny headroom survives rounding.
        r1_drop = params.vcc_v * params.r1_ohm / (params.r1_ohm + params.r2_ohm) + rth_drop
        drops.update(R1=r1_drop, R2=values["VB_V"], RTH=rth_drop)
    else:
        drops["RB"] = values["IB_A"] * params.rb_ohm
    if not isinstance(params, FixedBiasInputs):
        drops["RE"] = values["IE_A"] * params.re_ohm
    return drops


def _view_state(point, params, mode, form, errors):
    if point is None:
        data = {
            "ok": not errors, "region": "invalid" if errors else "pending",
            "model": "Input validation failed." if errors else "Enter values and calculate the selected circuit.",
            "results": {}, "display": {}, "checks": {}, "warnings": [],
        }
    else:
        data = _response_data(point)
    verification = []
    for key in MODE_CHECKS[mode]:
        value = data["checks"].get(key)
        if data["region"] == "outside_model":
            value = False if key == "region_consistency" else None
        verification.append({
            "key": key, "label": CHECK_LABELS[key],
            "state": "na" if value is None else "pass" if value else "fail",
        })
    calculation = build_calculation(params, point)
    diagnostics = _trial_diagnostics(params) if data["region"] == "outside_model" else []
    drops = _branch_drops(params, point.values) if calculation["state"] == "match" else {}
    state = dict(data, mode=mode, inputs=form, schematic_inputs=_schematic_inputs(form), errors=errors,
                 verification=verification, calculation=calculation, diagnostics=diagnostics, drops=drops)
    if point is not None:
        state["input_values"] = {
            name: getattr(params, si) / 1000 if si.endswith("_ohm") else getattr(params, si)
            for si, name in ENGINE_FIELD_NAMES.items() if name in MODE_DEFAULTS[mode]
        }
    return state


def _positive_number(value):
    try:
        number = float(str(value).strip())
    except (ValueError, OverflowError):
        return None
    return number if isfinite(number) and number > 0 else None


def _tool_payload():
    payload = request.get_json(silent=True)
    return payload if isinstance(payload, dict) and isinstance(payload.get("inputs"), dict) else None


def _tool_error(code, errors, *, status=422, **details):
    return jsonify(ok=False, code=code, errors=errors, **details), status


def create_app() -> Flask:
    application = Flask(__name__)
    application.config.update(
        LAB04_SPICE_PROFILE=getenv("LAB04_SPICE_PROFILE"),
        LAB04_NGSPICE=getenv("LAB04_NGSPICE"),
        LAB04_EVIDENCE_DIR=getenv("LAB04_EVIDENCE_DIR"),
    )

    def render_form(mode, values, *, calculate=True, errors=None):
        point = params = None
        if calculate:
            try:
                params = parse_inputs(values, mode, form_units=True)
                point = calculate_by_mode(mode, params)
            except InputValidationError as error:
                errors = error.errors
        state = _view_state(point, params, mode, values, errors or {})
        return render_template(
            "index.html", mode=mode, modes=MODES, form=values,
            fields={key: FIELD_LABELS[key] for key in MODE_DEFAULTS[mode]},
            all_fields=FIELD_LABELS, mode_defaults=MODE_DEFAULTS,
            mode_fields={name: list(defaults) for name, defaults in MODE_DEFAULTS.items()},
            schematic_inputs=state["schematic_inputs"],
            result_labels=RESULT_LABELS, state=state, presets=PRESETS,
            resistance_bounds=RESISTANCE_FORM_BOUNDS,
        ), 422 if errors else 200

    @application.get("/")
    def index():
        if "mode" not in request.args:
            return render_form("divider", DEFAULT_FORM.copy())
        try:
            if len(request.args.getlist("mode")) != 1:
                raise InputValidationError({"mode": "Choose exactly one bias circuit."})
            mode = select_mode(request.args)
        except InputValidationError as error:
            return render_form("divider", DEFAULT_FORM.copy(), calculate=False, errors=error.errors)
        return render_form(mode, MODE_DEFAULTS[mode].copy(), calculate=False)

    @application.post("/calculate")
    def calculate_html():
        try:
            if len(request.form.getlist("mode")) > 1:
                raise InputValidationError({"mode": "Choose exactly one bias circuit."})
            mode = select_mode(request.form)
        except InputValidationError as error:
            return render_form("divider", DEFAULT_FORM.copy(), calculate=False, errors=error.errors)
        return render_form(mode, {name: request.form.get(name, "") for name in MODE_DEFAULTS[mode]})

    @application.post("/api/calculate")
    def calculate_json():
        if not request.is_json:
            return jsonify(ok=False, errors={"request": "Expected JSON object."}), 400
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify(ok=False, errors={"request": "Malformed JSON object."}), 400
        mode = None
        try:
            mode = select_mode(payload)
            params = parse_inputs(payload, mode, form_units="mode" in payload)
            point = calculate_by_mode(mode, params)
        except InputValidationError as error:
            failure = {"ok": False, "errors": error.errors}
            if "mode" in payload and mode is not None:
                failure["mode"] = mode
            return jsonify(failure), 422
        if "mode" not in payload:
            return jsonify(_response_data(point))
        values = {name: str(payload[name]).strip() for name in MODE_DEFAULTS[mode]}
        return jsonify(_view_state(point, params, mode, values, {}))

    @application.get("/spice")
    def spice_workbench():
        return render_template("spice.html", field_specs=SPICE_FIELDS)

    @application.post("/api/spice")
    def simulate_spice():
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict) or set(payload) != {"analysis", "inputs"}:
            return jsonify(ok=False, code="request", message="ส่ง analysis และ inputs เป็น JSON",
                           fields={}), 400
        try:
            result = simulate(
                payload["analysis"], payload["inputs"],
                profile_path=application.config["LAB04_SPICE_PROFILE"],
                executable=application.config["LAB04_NGSPICE"],
                evidence_dir=application.config["LAB04_EVIDENCE_DIR"],
            )
        except SpiceError as error:
            status = {"input": 422, "profile": 503, "engine": 503, "timeout": 504,
                      "solver": 502, "output": 502}.get(error.code, 500)
            return jsonify(ok=False, code=error.code, message=error.message,
                           fields=error.fields or {}), status
        return jsonify(result)

    @application.post("/api/sweep")
    def sweep_json():
        payload = _tool_payload()
        if payload is None:
            return _tool_error("request", {"request": "Expected a JSON object with circuit inputs."}, status=400)
        try:
            mode = select_mode({"mode":payload.get("mode")})
        except InputValidationError as error:
            return _tool_error("mode", error.errors)
        parameter = payload.get("parameter")
        if not isinstance(parameter, str) or parameter not in MODE_DEFAULTS[mode]:
            return _tool_error("parameter", {"parameter":"Choose a parameter for this circuit."})
        start, end = _positive_number(payload.get("start")), _positive_number(payload.get("end"))
        if start is None or end is None or start >= end:
            return _tool_error("range", {"range":"Enter positive finite bounds with end greater than start."})
        try:
            seed = dict(payload["inputs"], **{parameter:MODE_DEFAULTS[mode][parameter]})
            base = parse_inputs(seed, mode, form_units=True)
        except InputValidationError as error:
            return _tool_error("inputs", error.errors)
        attribute = next(key for key, name in ENGINE_FIELD_NAMES.items() if name == parameter)
        scale = 1000 if attribute.endswith("_ohm") else 1
        points = []
        for index in range(SWEEP_POINTS):
            value = end if index == SWEEP_POINTS - 1 else start + (end - start) * (index / (SWEEP_POINTS - 1))
            sample = replace(base, **{attribute:value * scale})
            results = {}
            try:
                point = calculate_by_mode(mode, sample)
            except InputValidationError:
                region = "invalid"
            else:
                region = point.region
                if region != "outside_model":
                    if _reference_agrees(sample, point):
                        results = {key: point.values[key] for key in ("IC_A", "VCE_V")}
                    else:
                        region = "mismatch"
            points.append({"value": value, "region": region, "results": results})
        return jsonify(ok=True, points=points)

    @application.post("/api/inverse")
    def inverse_json():
        payload = _tool_payload()
        if payload is None:
            return _tool_error("request", {"request": "Expected a JSON object with circuit inputs."}, status=400)
        if payload.get("mode") != "emitter":
            return _tool_error("mode", {"mode":"Finding RE from IC is available for Emitter Bias only."})
        target_ma = _positive_number(payload.get("target_ic_ma"))
        if target_ma is None or target_ma / 1000 == 0:
            return _tool_error("target", {"target_ic_ma":"Enter a positive finite target that is representable in amperes."})
        try:
            params = parse_inputs(dict(payload["inputs"], re=MODE_DEFAULTS["emitter"]["re"]), "emitter", form_units=True)
        except InputValidationError as error:
            return _tool_error("inputs", error.errors)
        try:
            re_ohm = emitter_resistance_for_current(params, Fraction(str(target_ma)) / 1000)
        except InverseDesignError as error:
            if error.code == "range":
                low, high = (float(bound * 1000) for bound in error.bounds_a)
                return _tool_error("range", {"target_ic_ma":f"Choose a target from {low:.7g} to {high:.7g} mA."},
                                   target_range_ma=[low, high])
            return _tool_error(error.code, {"target_ic_ma":"A positive base current requires VCC greater than VBE."})

        re_kohm = float(re_ohm / 1000)
        solved = replace(params, re_ohm=re_kohm * 1000)
        point = calculate_by_mode("emitter", solved)
        if point.region != "forward_active":
            return _tool_error("region", {"target_ic_ma":"The solution fails the Forward Active region checks."})
        if not isclose(point.values["IC_A"], target_ma / 1000, rel_tol=1e-8) or not _reference_agrees(solved, point):
            return _tool_error("verify", {"target_ic_ma":"The forward model could not verify this current at the calculated RE."})
        return jsonify(ok=True, re_kohm=re_kohm, results=point.values, region=point.region)

    return application


app = create_app()
