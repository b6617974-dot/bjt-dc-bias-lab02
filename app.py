"""Flask transport and formatting for the Lab 02 DC-bias model."""

from collections.abc import Mapping
from math import isfinite

from flask import Flask, jsonify, render_template, request

from dc_bias import (
    BiasInputs, BiasResult, InputValidationError, calculate_bias,
    validate_bias_inputs,
)


DEFAULT_FORM = {
    "vcc": "12", "r1": "100", "r2": "22", "rc": "2.2",
    "re": "1", "beta": "100", "vbe": "0.70",
}
FIELD_LABELS = {
    "vcc": ("VCC", "V"), "r1": ("R1", "kΩ"),
    "r2": ("R2", "kΩ"), "rc": ("RC", "kΩ"),
    "re": ("RE", "kΩ"), "beta": ("β", ""),
    "vbe": ("VBE", "V"),
}
ENGINE_FIELD_NAMES = {
    "vcc_v": "vcc", "r1_ohm": "r1", "r2_ohm": "r2",
    "rc_ohm": "rc", "re_ohm": "re", "beta": "beta", "vbe_v": "vbe",
}
RESULT_LABELS = {
    "VB_V": "Base voltage (VB)", "VE_V": "Emitter voltage (VE)",
    "VC_V": "Collector voltage (VC)", "VCE_V": "Collector-emitter (VCE)",
    "IB_A": "Base current (IB)", "IC_A": "Collector current (IC)",
    "IE_A": "Emitter current (IE)",
    "VTH_V": "Thevenin voltage (VTH)", "RTH_OHM": "Thevenin resistance (RTH)",
}


def parse_inputs(raw: Mapping[str, object]) -> BiasInputs:
    """Parse human input and convert resistance from kΩ to Ω once."""
    errors: dict[str, str] = {}
    vals: dict[str, float] = {}
    for name in DEFAULT_FORM:
        item = raw.get(name, None)
        try:
            value = float(str(item).strip()) if item is not None else float("nan")
            if not isfinite(value):
                raise ValueError("non-finite")
        except (TypeError, ValueError, OverflowError):
            errors[name] = "Enter a finite numeric value."
            continue
        vals[name] = value
    if errors:
        raise InputValidationError(errors)
    args = BiasInputs(
        vcc_v=vals["vcc"], r1_ohm=vals["r1"] * 1000,
        r2_ohm=vals["r2"] * 1000, rc_ohm=vals["rc"] * 1000,
        re_ohm=vals["re"] * 1000, beta=vals["beta"], vbe_v=vals["vbe"],
    )
    try:
        validate_bias_inputs(args)
        return args
    except InputValidationError as exc:
        raise InputValidationError({ENGINE_FIELD_NAMES.get(key, key): msg
                                    for key, msg in exc.errors.items()}) from exc


def present_result(result: BiasResult) -> dict[str, str]:
    display = {}
    for key, value in result.values.items():
        if value is None:
            display[key] = "—"
        elif key == "IB_A":
            display[key] = f"{value * 1e6:.3f} µA"
        elif key in ("IC_A", "IE_A"):
            display[key] = f"{value * 1e3:.3f} mA"
        elif key == "RTH_OHM":
            display[key] = f"{value / 1e3:.3f} kΩ"
        else:
            display[key] = f"{value:.3f} V"
    return display


def _response_data(result: BiasResult) -> dict:
    return {
        "ok": True, "region": result.region, "model": result.model,
        "results": result.values, "display": present_result(result),
        "checks": result.checks, "warnings": result.warnings,
    }


def create_app() -> Flask:
    application = Flask(__name__)

    def render_form(values: dict, errors: dict | None = None, status: int = 200):
        try:
            point = calculate_bias(parse_inputs(values)) if errors is None else None
        except InputValidationError as exc:
            point = None
            errors = exc.errors
            status = 422
        return render_template(
            "index.html", form=values, fields=FIELD_LABELS,
            default_form=DEFAULT_FORM,
            result_labels=RESULT_LABELS, point=point,
            display=present_result(point) if point else {},
            errors=errors or {},
        ), status

    @application.get("/")
    def index():
        return render_form(DEFAULT_FORM.copy())

    @application.post("/calculate")
    def calculate_html():
        return render_form({name: request.form.get(name, "") for name in DEFAULT_FORM})

    @application.post("/api/calculate")
    def calculate_json():
        if not request.is_json:
            return jsonify(ok=False, errors={"request": "Expected JSON object."}), 400
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return jsonify(ok=False, errors={"request": "Malformed JSON object."}), 400
        try:
            point = calculate_bias(parse_inputs(payload))
            return jsonify(_response_data(point)), 200
        except InputValidationError as exc:
            return jsonify(ok=False, errors=exc.errors), 422

    return application


app = create_app()
