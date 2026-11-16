"""Pure educational NPN DC bias calculations.

Inputs to this module are SI units (ohms, volts, dimensionless beta).
HTTP handling and display formatting belong to app.py.
"""

from dataclasses import dataclass, replace
from fractions import Fraction
from math import isclose, isfinite, ulp
from typing import Literal


Mode = Literal["divider", "fixed", "emitter"]
RESISTANCE_BOUNDS_OHM = (1.0, 1e12)
CURRENT_UNDERFLOW_WARNING = "Positive bias current underflow at this scale; no reliable Q-point."
VOLTAGE_RESOLUTION_WARNING = "The forward-active voltage margin is below numerical resolution; no reliable Q-point."


@dataclass(frozen=True)
class BiasInputs:
    vcc_v: float
    r1_ohm: float
    r2_ohm: float
    rc_ohm: float
    re_ohm: float
    beta: float
    vbe_v: float


@dataclass(frozen=True)
class FixedBiasInputs:
    vcc_v: float
    rb_ohm: float
    rc_ohm: float
    beta: float
    vbe_v: float


@dataclass(frozen=True)
class EmitterBiasInputs:
    vcc_v: float
    rb_ohm: float
    rc_ohm: float
    re_ohm: float
    beta: float
    vbe_v: float


@dataclass(frozen=True)
class BiasResult:
    region: str
    model: str
    values: dict[str, float | None]
    checks: dict[str, bool]
    warnings: tuple[str, ...]


class InputValidationError(ValueError):
    """Fields that are unsafe or outside the educational model's bounds."""

    def __init__(self, errors: dict[str, str]):
        super().__init__("Invalid BJT DC bias inputs")
        self.errors = errors


class InverseDesignError(ValueError):
    """An emitter-current target lies outside the supported circuit model."""

    def __init__(self, code: str, bounds_a: tuple[Fraction, Fraction] | None = None):
        super().__init__(code)
        self.code = code
        self.bounds_a = bounds_a


def _validate_inputs(
    params: BiasInputs | FixedBiasInputs | EmitterBiasInputs, resistors: tuple[str, ...],
) -> None:
    bounds = {
        "vcc_v": (0.0, 1e5), "vbe_v": (0.0, 1e3),
        "beta": (0.0, 1e6),
        **dict.fromkeys(resistors, RESISTANCE_BOUNDS_OHM),
    }
    errors = {}
    for name, (lower, upper) in bounds.items():
        value = getattr(params, name)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            errors[name] = "Enter a finite number."
        elif isinstance(value, float) and not isfinite(value):
            errors[name] = "Enter a finite number."
        elif (value < lower if lower == 1.0 else value <= lower) or value > upper:
            errors[name] = f"Must be {'at least' if lower else 'greater than'} {lower:g} and at most {upper:g}."
    if errors:
        raise InputValidationError(errors)


def validate_bias_inputs(params: BiasInputs) -> None:
    _validate_inputs(params, ("r1_ohm", "r2_ohm", "rc_ohm", "re_ohm"))


def validate_fixed_bias_inputs(params: FixedBiasInputs) -> None:
    _validate_inputs(params, ("rb_ohm", "rc_ohm"))


def validate_emitter_bias_inputs(params: EmitterBiasInputs) -> None:
    _validate_inputs(params, ("rb_ohm", "rc_ohm", "re_ohm"))


def _verify_result(params: BiasInputs, result: BiasResult) -> BiasResult:
    """Independently check KCL, resistor drops and region consistency."""
    v = result.values
    names = (
        "transistor_kcl", "divider_kcl", "collector_drop",
        "emitter_drop", "vce_identity", "region_consistency",
    )
    if result.region == "outside_model":
        return replace(result, checks=dict.fromkeys(names, False))

    vb, ve, vc, vce = (v[key] for key in ("VB_V", "VE_V", "VC_V", "VCE_V"))
    ib, ic, ie = (v[key] for key in ("IB_A", "IC_A", "IE_A"))
    # Comparing currents by a fixed 1e-12 A epsilon can hide large
    # relative Kirchhoff errors in high-impedance educational examples.
    current_close = lambda a, b: isclose(a, b, rel_tol=1e-8, abs_tol=0.0)
    voltage_close = lambda a, b: isclose(a, b, rel_tol=1e-8, abs_tol=1e-9)
    divider_source = (params.vcc_v - vb) / params.r1_ohm
    divider_load = vb / params.r2_ohm + ib
    # When VCC and VB nearly coincide, their subtraction is quantized at
    # their voltage ULP, not at a fixed current scale. This is a bound on
    # *floating-point representation error*, not a blanket 1e-12 A pass.
    divider_roundoff = 8 * (
        (ulp(params.vcc_v) + ulp(vb)) / params.r1_ohm
        + ulp(vb) / params.r2_ohm
    )
    region_ok = {
        "forward_active": (
            ib > 0 and ic > 0 and vc > vb and vce > 0.20
            # A balanced transistor KCL alone cannot prove fixed-beta:
            # changing IB and IC in opposite directions leaves IE unchanged.
            and current_close(ic, params.beta * ib)
        ),
        "cutoff_estimate": v["VTH_V"] <= params.vbe_v and ib == ic == ie == 0,
        "saturation_estimate": (ib > 0 and ic >= 0
                                and (ic <= params.beta * ib or isclose(
                                    ic, params.beta * ib,
                                    rel_tol=1e-10, abs_tol=0.0,
                                ))
                                and vb > vc
                                and voltage_close(vce, 0.20)),
    }.get(result.region, False)
    checks = {
        "transistor_kcl": current_close(ie, ib + ic),
        "divider_kcl": isclose(
            divider_source, divider_load,
            rel_tol=1e-8, abs_tol=divider_roundoff,
        ),
        "collector_drop": voltage_close(vc, params.vcc_v - ic * params.rc_ohm),
        "emitter_drop": voltage_close(ve, ie * params.re_ohm),
        "vce_identity": voltage_close(vce, vc - ve),
        "region_consistency": region_ok,
    }
    if not all(checks.values()):
        invalid_values = {key: (value if key in ("VTH_V", "RTH_OHM") else None)
                          for key, value in v.items()}
        return BiasResult(
            region="outside_model", model="Engineering consistency check failed",
            values=invalid_values, checks=checks,
            warnings=result.warnings + ("Model consistency failed; no reliable Q-point.",),
        )
    return replace(result, checks=checks)


def _divider_unavailable(params: BiasInputs, vth: float, rth: float, warning: str) -> BiasResult:
    return _verify_result(params, BiasResult(
        region="outside_model", model="No consistent DC bias estimate",
        values={"VTH_V": vth, "RTH_OHM": rth, **dict.fromkeys(
            ("VB_V", "VE_V", "VC_V", "VCE_V", "IB_A", "IC_A", "IE_A"),
        )},
        checks={}, warnings=(warning,),
    ))


def _active_voltage_margins(values):
    return values["VC_V"] - values["VB_V"], values["VCE_V"] - 0.20


def _resolve_active_voltage(params, values):
    margins = _active_voltage_margins(values)
    active = min(margins) > 0
    if min(map(abs, margins)) > 8 * ulp(params.vcc_v):
        return values, active
    # Resolve a close sign with the independent nodal solution before rounding voltages.
    reference = calculate_reference(params, "forward_active")
    exact_active = "IC_A" in reference
    if exact_active and not active:
        values = {key: float(reference[key]) for key in values}
    return values, exact_active


def calculate_bias(params: BiasInputs) -> BiasResult:
    """Calculate DC bias using a fixed-beta educational approximation."""
    validate_bias_inputs(params)
    vth = params.vcc_v * params.r2_ohm / (params.r1_ohm + params.r2_ohm)
    rth = (params.r1_ohm * params.r2_ohm) / (params.r1_ohm + params.r2_ohm)
    base_headroom = vth - params.vbe_v
    cutoff = base_headroom <= 0
    if abs(base_headroom) <= 8 * max(ulp(vth), ulp(params.vbe_v)):
        exact_vth = calculate_reference(params, "forward_active", active_trial=True)["VTH_V"]
        exact_headroom = exact_vth - Fraction(str(params.vbe_v))
        cutoff = exact_headroom <= 0
        base_headroom, vth = float(exact_headroom), float(exact_vth)
    if cutoff:
        return _verify_result(params, BiasResult(
            region="cutoff_estimate", model="Cutoff estimate (leakage neglected)",
            values={
                "VTH_V": vth, "RTH_OHM": rth,
                "VB_V": vth, "VE_V": 0.0, "VC_V": params.vcc_v,
                "VCE_V": params.vcc_v, "IB_A": 0.0, "IC_A": 0.0,
                "IE_A": 0.0,
            },
            checks={}, warnings=("Cutoff estimate: leakage and breakdown are not modeled.",),
        ))
    ib = base_headroom / (rth + (params.beta + 1) * params.re_ohm)
    ic = params.beta * ib
    if ib == 0 or ic == 0:
        return _divider_unavailable(params, vth, rth, CURRENT_UNDERFLOW_WARNING)
    ie = (params.beta + 1) * ib
    ve = ie * params.re_ohm
    vb = ve + params.vbe_v
    vc = params.vcc_v - ic * params.rc_ohm
    candidate, active = _resolve_active_voltage(params, {
        "VB_V": vb, "VE_V": ve, "VC_V": vc, "VCE_V": vc - ve,
        "IB_A": ib, "IC_A": ic, "IE_A": ie,
    })
    if active and min(_active_voltage_margins(candidate)) <= 0:
        return _divider_unavailable(params, vth, rth, VOLTAGE_RESOLUTION_WARNING)
    if not active:
        # Solve the coupled base/collector/emitter loops algebraically.
        # In particular, IB = (VTH-VBE-VE)/RTH loses significant digits
        # when VE is nearly VTH-VBE (very large RE/RC ratios).
        collector_headroom = params.vcc_v - 0.20
        denominator = (
            rth * params.rc_ohm
            + params.re_ohm * (rth + params.rc_ohm)
        )
        ib_sat = (
            base_headroom * params.rc_ohm
            + params.re_ohm * (base_headroom - collector_headroom)
        ) / denominator
        ic_sat = (
            collector_headroom * rth
            + params.re_ohm * (collector_headroom - base_headroom)
        ) / denominator
        ie_sat = (
            base_headroom * params.rc_ohm + collector_headroom * rth
        ) / denominator
        ve_sat = ie_sat * params.re_ohm
        if (all(map(isfinite, (ve_sat, ib_sat, ic_sat, ie_sat)))
                and params.vbe_v > 0.20
                and ib_sat > 0 and ic_sat >= 0
                and (ic_sat <= params.beta * ib_sat or isclose(
                    ic_sat, params.beta * ib_sat,
                    rel_tol=1e-10, abs_tol=0.0,
                ))):
            return _verify_result(params, BiasResult(
                region="saturation_estimate",
                model="Saturation estimate: fixed VCE(sat)=0.20 V, fixed VBE",
                values={
                    "VTH_V": vth, "RTH_OHM": rth,
                    "VB_V": ve_sat + params.vbe_v, "VE_V": ve_sat,
                    "VC_V": ve_sat + 0.20, "VCE_V": 0.20,
                    "IB_A": ib_sat, "IC_A": ic_sat, "IE_A": ie_sat,
                },
                checks={},
                warnings=("Saturation estimate only; not a SPICE or device-curve solution.",),
            ))
        return _divider_unavailable(params, vth, rth, "Outside the forward-active and bounded saturation approximations.")
    return _verify_result(params, BiasResult(
        region="forward_active",
        model="Fixed-beta forward-active approximation",
        values={"VTH_V": vth, "RTH_OHM": rth, **candidate},
        checks={}, warnings=(),
    ))


def _within_roundoff(left: float, right: float, *terms: float) -> bool:
    tolerance = 1e-10 * max(abs(left), abs(right)) + 8 * sum(ulp(term) for term in terms)
    return abs(left - right) <= tolerance


def _active_checks(
    params: FixedBiasInputs | EmitterBiasInputs, values: dict[str, float],
) -> dict[str, bool]:
    vb, ve, vc, vce = (values[key] for key in ("VB_V", "VE_V", "VC_V", "VCE_V"))
    ib, ic, ie = (values[key] for key in ("IB_A", "IC_A", "IE_A"))
    emitter = isinstance(params, EmitterBiasInputs)
    vbe = vb - ve
    rb_drop = ib * params.rb_ohm
    rc_drop = ic * params.rc_ohm
    re_drop = ie * params.re_ohm if emitter else 0.0
    base_terms = (rb_drop, vbe, re_drop) if emitter else (rb_drop, vbe)
    collector_terms = (rc_drop, vce, re_drop) if emitter else (rc_drop, vce)
    vcc = params.vcc_v
    return {
        "transistor_kcl": _within_roundoff(ie, ib + ic, ie, ib, ic),
        "base_kvl": (
            _within_roundoff(vbe, params.vbe_v, vb, ve, params.vbe_v)
            and _within_roundoff(vcc, sum(base_terms), vcc, *base_terms)
        ),
        "collector_kvl": _within_roundoff(vcc, sum(collector_terms), vcc, *collector_terms),
        "collector_drop": _within_roundoff(vc, vcc - rc_drop, vc, vcc, rc_drop),
        **({"emitter_drop": _within_roundoff(ve, re_drop, ve, re_drop)}
           if emitter else {"emitter_ground": ve == 0.0}),
        "vce_identity": _within_roundoff(vce, vc - ve, vce, vc, ve),
        "region_consistency": (
            ib > 0.0 and ic > 0.0 and vc > vb and vce > 0.20
            and isclose(ic, params.beta * ib, rel_tol=1e-8, abs_tol=0.0)
        ),
    }


def _active_base_current(params: FixedBiasInputs | EmitterBiasInputs, re_ohm: float) -> float:
    return (params.vcc_v - params.vbe_v) / (params.rb_ohm + (params.beta + 1.0) * re_ohm)


def _calculate_active_bias(
    params: FixedBiasInputs | EmitterBiasInputs, re_ohm: float,
) -> BiasResult:
    ib = _active_base_current(params, re_ohm)
    ic = params.beta * ib
    ie = ib + ic
    ve = ie * re_ohm
    vb = ve + params.vbe_v
    vc = params.vcc_v - ic * params.rc_ohm
    candidate = {
        "VB_V": vb, "VE_V": ve, "VC_V": vc, "VCE_V": vc - ve,
        "IB_A": ib, "IC_A": ic, "IE_A": ie,
    }
    candidate, active = _resolve_active_voltage(params, candidate)
    checks = _active_checks(params, candidate)
    checks["region_consistency"] = checks["region_consistency"] and active
    values = {**candidate, "VTH_V": None, "RTH_OHM": None}
    if not all(checks.values()):
        if params.vcc_v > params.vbe_v and (candidate["IB_A"] == 0 or candidate["IC_A"] == 0):
            warning = CURRENT_UNDERFLOW_WARNING
        elif active and min(_active_voltage_margins(candidate)) <= 0:
            warning = VOLTAGE_RESOLUTION_WARNING
        elif not checks["region_consistency"]:
            warning = "Forward-active bias requires positive IB and IC, VC > VB, and VCE > 0.20 V."
        else:
            warning = "Engineering consistency check failed; no reliable Q-point."
        return BiasResult(
            "outside_model", "No consistent DC bias estimate",
            dict.fromkeys(values), dict.fromkeys(checks, False), (warning,),
        )
    return BiasResult(
        "forward_active", "Fixed-beta forward-active approximation", values, checks, (),
    )


def calculate_fixed_bias(params: FixedBiasInputs) -> BiasResult:
    """Calculate forward-active bias with the emitter grounded."""
    validate_fixed_bias_inputs(params)
    return _calculate_active_bias(params, 0.0)


def calculate_emitter_bias(params: EmitterBiasInputs) -> BiasResult:
    """Calculate forward-active bias with one supply and an emitter resistor."""
    validate_emitter_bias_inputs(params)
    return _calculate_active_bias(params, params.re_ohm)


def calculate_by_mode(
    mode: Mode, params: BiasInputs | FixedBiasInputs | EmitterBiasInputs,
) -> BiasResult:
    """Dispatch matching typed inputs to the circuit's solver."""
    if mode == "divider" and isinstance(params, BiasInputs):
        return calculate_bias(params)
    if mode == "fixed" and isinstance(params, FixedBiasInputs):
        return calculate_fixed_bias(params)
    if mode == "emitter" and isinstance(params, EmitterBiasInputs):
        return calculate_emitter_bias(params)
    raise InputValidationError({"mode": "Choose a supported mode with matching circuit inputs."})


def emitter_resistance_for_current(params: EmitterBiasInputs, target_a: Fraction) -> Fraction:
    """Find RE in ohms for a positive target. The caller checks the forward result."""
    validate_emitter_bias_inputs(params)
    if target_a <= 0:
        raise InverseDesignError("target")
    drive = Fraction(str(params.vcc_v)) - Fraction(str(params.vbe_v))
    if drive <= 0:
        raise InverseDesignError("drive")
    beta = Fraction(str(params.beta))
    rb = Fraction(str(params.rb_ohm))
    low_re, high_re = map(Fraction, RESISTANCE_BOUNDS_OHM)
    low_a = beta * drive / (rb + (beta + 1) * high_re)
    high_a = beta * drive / (rb + (beta + 1) * low_re)
    if not low_a <= target_a <= high_a:
        below = target_a < low_a
        boundary_re = high_re if below else low_re
        machine_boundary = params.beta * _active_base_current(params, float(boundary_re))
        boundary_a = (min(low_a, Fraction(machine_boundary)) if below else
                      max(high_a, Fraction(machine_boundary)))
        # Include a forward boundary readout after rounding and the display-unit round trip.
        excess = boundary_a - target_a if below else target_a - boundary_a
        if excess > 2 * Fraction(ulp(machine_boundary)):
            raise InverseDesignError("range", (low_a, high_a))
    re = (beta * drive / target_a - rb) / (beta + 1)
    return min(high_re, max(low_re, re))


def calculate_reference(
    params: BiasInputs | FixedBiasInputs | EmitterBiasInputs, region: str,
    *, active_trial: bool = False,
) -> dict[str, Fraction]:
    """Solve a circuit branch in exact decimals. Active trials may fail its region gates."""
    vcc = Fraction(str(params.vcc_v))
    rc = Fraction(str(params.rc_ohm))
    vbe = Fraction(str(params.vbe_v))
    beta = Fraction(str(params.beta))
    re = Fraction(str(getattr(params, "re_ohm", 0)))
    values = {}

    if isinstance(params, BiasInputs):
        upper = Fraction(str(params.r1_ohm))
        lower = Fraction(str(params.r2_ohm))
        lower_conductance = 1 / lower
        vth = vcc * lower / (upper + lower)
        rth = upper * lower / (upper + lower)
        values.update(VTH_V=vth, RTH_OHM=rth)
    else:
        upper = Fraction(str(params.rb_ohm))
        lower_conductance = Fraction(0)

    if region == "cutoff_estimate" and isinstance(params, BiasInputs):
        if vth > vbe:
            return values
        ib = ic = ve = Fraction(0)
        vb, vc = vth, vcc
    elif region == "saturation_estimate" and isinstance(params, BiasInputs):
        # Solve the emitter-node current balance with a fixed VCE(sat).
        vcesat = Fraction(1, 5)
        ve = ((vth - vbe) / rth + (vcc - vcesat) / rc) / (1 / rth + 1 / rc + 1 / re)
        ib = (vth - vbe - ve) / rth
        ic = (vcc - vcesat - ve) / rc
        vb, vc = ve + vbe, ve + vcesat
        if ib <= 0 or ic < 0 or ic > beta * ib or vb <= vc:
            return values
    elif region == "forward_active":
        if re:
            # KCL at the original base node, without a rounded Thévenin reduction.
            emitter_conductance = 1 / ((beta + 1) * re)
            vb = (vcc / upper + vbe * emitter_conductance) / (1 / upper + lower_conductance + emitter_conductance)
        else:
            vb = vbe
        ve = vb - vbe
        ib = (vcc - vb) / upper - vb * lower_conductance
        ic = beta * ib
        vc = vcc - ic * rc
        if not active_trial and (ib <= 0 or ic <= 0 or vc <= vb or vc - ve <= Fraction(1, 5)):
            return values
    else:
        return values

    values.update(VB_V=vb, VE_V=ve, VC_V=vc, VCE_V=vc-ve, IB_A=ib, IC_A=ic, IE_A=ib+ic)
    return values
