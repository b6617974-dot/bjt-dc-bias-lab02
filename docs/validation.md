# Lab 02 — Validation Record

**Date:** 2026-11-10 (Asia/Bangkok)
**Scope:** NPN voltage-divider DC operating point; pure math, real Flask HTTP routes, inline SVG UI, and repository CI.
**Status:** Python, HTTP, and Windows Chrome browser QA verified. The GitHub-hosted Actions status must be recorded **after the actual push**, not inferred from local tests.

## 1. Independent default reference

Inputs: `VCC=12 V`, `R1=100 kΩ`, `R2=22 kΩ`, `RC=2.2 kΩ`, `RE=1 kΩ`, `β=100`, `VBE=0.70 V`.

The reference is calculated from the equations in `README.md` and compared against unrounded Python values, with appropriate absolute tolerances.

| Quantity | Reference (unrounded) | Display from Flask |
|---|---:|---:|
| VTH | 2.163934426 V | 2.164 V |
| RTH | 18.032786885 kΩ | 18.033 kΩ |
| VB | 1.942156728 V | 1.942 V |
| VE | 1.242156728 V | 1.242 V |
| VC | 9.294312078 V | 9.294 V |
| VCE | 8.052155351 V | 8.052 V |
| IB | 12.298581463 µA | 12.299 µA |
| IC | 1.229858146 mA | 1.230 mA |
| IE | 1.242156728 mA | 1.242 mA |

Expected region: `forward_active`. All six internal equation checks are true.

### Engineering identities checked

1. Transistor KCL: `IE = IB + IC`.
2. Loaded divider KCL: `(VCC − VB)/R1 = VB/R2 + IB`.
3. Collector resistor: `VC = VCC − IC·RC`.
4. Emitter resistor: `VE = IE·RE`.
5. Q-point voltage: `VCE = VC − VE`.
6. Operating region constraints match the approximate model.

The checks validate **self-consistency**, not an independent SPICE or hardware measurement.

## 2. Region and input-boundary cases

| Scenario | Input change from default | Expected label | Observed examples |
|---|---|---|---|
| Forward active | None | `forward_active` | IC = 1.230 mA, VCE = 8.052 V |
| Cutoff estimate | VCC=5, R1=100, R2=1 | `cutoff_estimate` | IB=IC=IE=0, VC=5.000 V |
| Saturation estimate | VCC=5, R1=10, R2=10, RC=10 | `saturation_estimate` | VCE=0.200 V, IC=0.415 mA |
| Outside-model boundary | VCC=5, R1=10, R2=10, RC=10, VBE=0.10 | `outside_model` | VB/VC/IC withheld; invalid saturation junction polarity |
| Invalid | Zero/negative resistor, β, VCC, blank, text, NaN, Infinity | HTTP 422 | Per-field message; no stale Q-point |
| Malformed API request | JSON array, invalid JSON, wrong media type | HTTP 400 | `{"ok":false,"errors":...}` |

The cutoff and saturation labels include an explicit estimation warning. A saturation estimate additionally requires `VB > VC` (forward-biased base–collector junction). `outside_model` deliberately omits unreliable operating-point values.

## 3. Automated test evidence

Command, from the repository root with Flask installed:

```text
python -m unittest discover -s tests -v
```

| Environment | Date | Result | Coverage |
|---|---|---|---|
| Local development / Python 3.12 | 2026-11-10 | **18 tests PASS** | DC math, saturation boundary, reset fallback, validation, Flask HTML/JSON, UI binding contracts |
| Authorized Windows / Python 3.12 / isolated virtual environment | 2026-11-10 | **18 tests PASS** after final physics review and file transfer | Model/web suite, including both new regression cases |
| GitHub Actions / Python 3.12 | Pending first push | **Not yet verified** | Same unittest command |

No test should be recorded as CI-passed until a real workflow run completes successfully.

## 4. Actual-browser QA (Chrome on Windows)

Windows Chrome was run via Playwright against Flask listening only on `127.0.0.1`. The browser QA harness and screenshots were placed in Windows **temporary storage outside the Git repository**.

| Check | Observation |
|---|---|
| Default desktop | 1440px screenshot shows the complete circuit, controls, result cards and consistency panel |
| RC changed from 2.2 to 3.3 kΩ | Both SVG and result card show VC=7.941 V from the live API |
| Invalid VCC blank | HTTP validation error displayed; prior SVG and card operating values cleared |
| Reset | Initial parameters restored, VC=9.294 V recomputed |
| Fast edits + throttled network | A late prior response did not overwrite the newest RC=2.7 kΩ result |
| Narrow screen 390px | Panels stack; circuit maintains fixed aspect ratio with horizontal scroll and a swipe instruction |
| 200% zoom | No warped circuit symbols; the SVG remains scrollable for full inspection |
| JavaScript disabled | Ordinary HTML POST still calculated VC=7.941 V for RC=3.3 kΩ; Reset navigates to the original 2.2 kΩ example |
| Browser exceptions | No uncaught JavaScript exception was reported |
| Raster dependence | None: circuit is inline SVG; no external scripts or image files |

The **emitter arrow points outward** for NPN, with R1 connected from VCC to base, R2 from base to ground, RC from VCC to collector, and RE from emitter to ground. Current arrows show conventional IB, IC and IE. The rendered SVG was additionally exported at 1680px width and inspected for text overlap, topology, arrow direction and image sharpness.

## 5. Reproducibility and submission audit

Reproducible on Windows PowerShell from a clean repository clone:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m flask --app app run
```

Only the handout's twelve named files plus the one owner-approved GitHub Actions workflow may be tracked. Review `git diff --cached --name-only` and `git status --short`; never stage `.venv`, Python caches, temporary browser tests or screenshots.

**Final push / Actions receipt:** To be filled after verifying the actual GitHub commit and CI run.
