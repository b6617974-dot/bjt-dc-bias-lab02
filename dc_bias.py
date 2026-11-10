"""Pure educational NPN voltage-divider DC bias calculations.

Inputs to this module are SI units (ohms, volts, dimensionless beta).
HTTP handling and display formatting belong to app.py.
"""

from dataclasses import dataclass, replace
from math import isclose, isfinite


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


def validate_bias_inputs(params: BiasInputs) -> None:
    bounds = {
        "vcc_v": (0.0, 1e5), "vbe_v": (0.0, 1e3),
        "beta": (0.0, 1e6),
        "r1_ohm": (1.0, 1e12), "r2_ohm": (1.0, 1e12),
        "rc_ohm": (1.0, 1e12), "re_ohm": (1.0, 1e12),
    }
    errors = {}
    for name, (lower, upper) in bounds.items():
        value = getattr(params, name)
        if not isinstance(value, (int, float)) or not isfinite(value):
            errors[name] = "Enter a finite number."
        elif (value < lower if lower == 1.0 else value <= lower) or value > upper:
            errors[name] = f"Must be {'at least' if lower else 'greater than'} {lower:g} and at most {upper:g}."
    if errors:
        raise InputValidationError(errors)


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
    current_close = lambda a, b: isclose(a, b, rel_tol=1e-8, abs_tol=1e-12)
    voltage_close = lambda a, b: isclose(a, b, rel_tol=1e-8, abs_tol=1e-9)
    region_ok = {
        "forward_active": ib > 0 and vc > vb and vce > 0.20,
        "cutoff_estimate": v["VTH_V"] <= params.vbe_v and ib == ic == ie == 0,
        "saturation_estimate": (ib > 0 and ic >= 0
                                and ic <= params.beta * ib + 1e-12
                                and vb > vc
                                and voltage_close(vce, 0.20)),
    }.get(result.region, False)
    checks = {
        "transistor_kcl": current_close(ie, ib + ic),
        "divider_kcl": current_close(
            (params.vcc_v - vb) / params.r1_ohm, vb / params.r2_ohm + ib,
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


def calculate_bias(params: BiasInputs) -> BiasResult:
    """Calculate DC bias using a fixed-beta educational approximation."""
    validate_bias_inputs(params)
    vth = params.vcc_v * params.r2_ohm / (params.r1_ohm + params.r2_ohm)
    rth = (params.r1_ohm * params.r2_ohm) / (params.r1_ohm + params.r2_ohm)
    if vth <= params.vbe_v:
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
    ib = (vth - params.vbe_v) / (rth + (params.beta + 1) * params.re_ohm)
    ic = params.beta * ib
    ie = (params.beta + 1) * ib
    ve = ie * params.re_ohm
    vb = ve + params.vbe_v
    vc = params.vcc_v - ic * params.rc_ohm
    if vc <= vb or (vc - ve) <= 0.20:
        ve_sat = params.re_ohm * (
            (vth - params.vbe_v) / rth + (params.vcc_v - 0.20) / params.rc_ohm
        ) / (1 + params.re_ohm / rth + params.re_ohm / params.rc_ohm)
        ib_sat = (vth - params.vbe_v - ve_sat) / rth
        ic_sat = (params.vcc_v - 0.20 - ve_sat) / params.rc_ohm
        ie_sat = ib_sat + ic_sat
        if (all(map(isfinite, (ve_sat, ib_sat, ic_sat, ie_sat)))
                and params.vbe_v > 0.20
                and ib_sat > 0 and ic_sat >= 0
                and ic_sat <= params.beta * ib_sat + 1e-12):
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
        return _verify_result(params, BiasResult(
            region="outside_model", model="No consistent DC bias estimate",
            values={
                "VTH_V": vth, "RTH_OHM": rth,
                **{name: None for name in (
                    "VB_V", "VE_V", "VC_V", "VCE_V", "IB_A", "IC_A", "IE_A"
                )},
            },
            checks={},
            warnings=("Outside the forward-active and bounded saturation approximations.",),
        ))
    return _verify_result(params, BiasResult(
        region="forward_active",
        model="Fixed-beta forward-active approximation",
        values={
            "VTH_V": vth, "RTH_OHM": rth,
            "VB_V": vb, "VE_V": ve, "VC_V": vc, "VCE_V": vc - ve,
            "IB_A": ib, "IC_A": ic, "IE_A": ie,
        },
        checks={}, warnings=(),
    ))
