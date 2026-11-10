# BJT DC Bias Engineering Dashboard — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (recommended for this tightly coupled Lab) or superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Status:** DESIGN AND IMPLEMENTATION PLAN APPROVED; implementation and first publication completed on 2026-11-10. The owner supplied GitHub Actions evidence showing successful runs for commits `2ba86d8` and `9e72a94`. See `docs/validation.md` for test evidence and acceptance limitations; the task checkboxes below retain the historical approved plan.
**Date:** 2026-11-10 (Thailand)
**Goal:** Produce a functioning, accurate Flask Lab 02 NPN voltage-divider DC-bias dashboard, with live circuit values, model checks, and GitHub Actions CI, without expanding the handout's submission file list except the approved workflow.

**Architecture:** A pure `dc_bias.py` owns all circuit math, region checks and numeric results. Flask in `app.py` serves the page and the HTML/JSON calculation routes. `templates/index.html` holds the dashboard, precise inline SVG and its small inline presentation-only JavaScript, with styling in the handout's `static/style.css`.

**Tech Stack:** Windows Python 3.12; Flask/Jinja; HTML/CSS; inline SVG and browser Fetch API; standard-library `unittest`; Git/GitHub Actions. No SPICE, frontend frameworks or separate JavaScript packages.

**Spec:** Approved Design v1.1: `LAB02_BJT_DESIGN_v1.1_FOR_APPROVAL.md` in this review workspace and the full self-contained approved-design baseline at the end of **this file**. The packaging revision (same handout files + CI workflow only) overrides any earlier tree in the standalone draft.

## Global Constraints

- Exact target repo: `https://github.com/b6617974-dot/bjt-dc-bias-lab02`; preserve existing remote and use its authorized Git identity only.
- Exact handout files: `app.py`, `dc_bias.py`, `templates/index.html`, `static/style.css`, `tests/test_dc_bias.py`, `tests/test_web.py`, `requirements.txt`, `README.md`, `AGENTS.md`, `docs/design-note.md`, `docs/validation.md`, `docs/reflection.md`.
- **Exactly one permitted extra repo file:** `.github/workflows/tests.yml`; no separate JS, SVG, PNG, `.gitignore`, generated artifact, or extra Markdown file added to GitHub/Moodle bundle.
- HTML form field names: `vcc`, `r1`, `r2`, `rc`, `re`, `beta`, `vbe`. UI resistances in **kΩ**; engine resistances in **Ω**, currents in **A**; clear unit conversion once at route boundary.
- Default input: `12, 100, 22, 2.2, 1, 100, 0.70` in the field order above.
- Backend is the only source of numeric physics. No JavaScript recomputation, fabricated values, or AI-generated schematic artwork.
- Fixed-beta, fixed-VBE educational model; cutoff/saturation are explicitly labeled estimates; no SPICE, AC, frequency, transient, drag/drop, or parameter sweep.
- The picture and result cards must both reflect the **same backend response**; when input is pending/invalid, clearly hide or gray out obsolete values.
- Deliver A1–A7 handout acceptance first, then live UI, visual QA, CI, and fresh-clone verification. No credentials or generated environments staged for Git.
- Use **test-first** development, failing → passing tests → reviewer/diff check. Review code and verify tests before **each** task commit, and double-check the exact repo before push.

## Review Focus — tests that must not be forgotten

1. A user posts **blank, `NaN`, `Infinity`, nonnumeric string**, or whitespace field: Flask returns structured 4xx / inline error, **never 500** (Task 3 tests).
2. A user sets **zero/negative resistance, beta or VCC**: rejected with input-specific message; no misleading operating point (Task 2 + Task 3 tests).
3. A user changes parameters **twice within one request**: the old response may arrive late, but must not overwrite the latest inputs (Task 4 manual network-throttle test and script sequence guard).
4. The device is narrow or browser zoom is **200%**: SVG topology, NPN emitter arrow, value labels, and contrast remain readable and not clipped (Task 4 visual checks).
5. A cutoff/saturation input produces a **physically inconsistent estimate**: do not label it forward-active or report false accuracy (Task 2 model/region tests).

---

## File Ownership Map

| Allowed path | Role |
|---|---|
| `dc_bias.py` | Engineering input/result types; active/cutoff/saturation estimates, validation, KCL/KVL checks |
| `app.py` | Flask `GET /`, `POST /calculate`, `POST /api/calculate`; input/units; HTML/JSON formatting |
| `templates/index.html` | Form, result cards, inline SVG, accessibility and **inline** UI-only JS |
| `static/style.css` | Responsive design, scalable SVG layout, focus states |
| `tests/test_dc_bias.py` | Model reference, region, boundary and mathematical checks |
| `tests/test_web.py` | HTTP routes, validation and frontend markup contract |
| `requirements.txt` | Minimal runtime deps (Flask; Python stdlib for tests) |
| `README.md` | Environment, startup, endpoints, test command and model limits |
| `AGENTS.md` | Coding/test conventions and repo-scope constraints |
| `docs/design-note.md` | **This reviewed Design + Implementation Plan** |
| `docs/validation.md` | Numeric reference table, local/CI results, visual QA and reproducibility evidence |
| `docs/reflection.md` | Short lessons and known limitations, per handout |
| `.github/workflows/tests.yml` | **The sole approved additional file:** test CI on push/PR |

## Task 1 — Accurate Forward-Active Physics

**Files:** Create `dc_bias.py`, `tests/test_dc_bias.py`. Keep any `__pycache__` outside staging.

**Interfaces:**

- `BiasInputs(vcc_v, r1_ohm, r2_ohm, rc_ohm, re_ohm, beta, vbe_v)`: frozen dataclass, all `float` fields.
- `BiasResult(region: str, model: str, values: dict[str, float|None], checks: dict[str, bool], warnings: tuple[str,...])`: frozen dataclass.
- `calculate_bias(params: BiasInputs) -> BiasResult` pure function; result `values` keys **exactly** `VTH_V`, `RTH_OHM`, `VB_V`, `VE_V`, `VC_V`, `VCE_V`, `IB_A`, `IC_A`, `IE_A`. `region` uses `forward_active`, `cutoff_estimate`, `saturation_estimate`, `outside_model`.

- [ ] **Step 1 — Write failing reference test:** `test_reference_forward_active` creates default inputs in Ω and asserts `region == "forward_active"`, `VB_V≈1.942156728`, `VE_V≈1.242156728`, `VC_V≈9.294312078`, `VCE_V≈8.052155351`, `IC_A≈0.001229858146` with absolute tolerance `1e-8` for voltages and `1e-10` for amperes. Also `IB_A≈12.298581463e-6`, `IE_A≈0.001242156728`.
- [ ] **Step 2 — Run red:** `python -m unittest discover -s tests -p test_dc_bias.py -v` → must fail because model is not implemented.
- [ ] **Step 3 — Implement forward-active calculation** in `calculate_bias`: compute `VTH=VCC·R2/(R1+R2)`, `RTH=R1R2/(R1+R2)`, `IB=(VTH−VBE)/(RTH+(β+1)RE)`, `IC=βIB`, `IE=(β+1)IB`, `VE=IE·RE`, `VB=VE+VBE`, `VC=VCC−IC·RC`, `VCE=VC−VE`. No output rounding inside model.
- [ ] **Step 4 — Run green:** same unittest command → default reference PASS.
- [ ] **Step 5 — Add second failing math test:** `test_rc_change_lowers_vc_only_in_active` asserts increasing `RC` modestly lowers `VC` and `VCE` while `VB,VE,IC` stay fixed for a still-active candidate; run red, implement/adjust, run green.
- [ ] **Step 6 — Review/commit** only `dc_bias.py tests/test_dc_bias.py` after all engine tests pass; commit e.g. `feat(lab02): add independently verified BJT DC model`.

## Task 2 — Region Handling, Input Guardrails, Engineering Consistency

**Files:** Modify `dc_bias.py`, `tests/test_dc_bias.py`.

**Interfaces:** Keep `calculate_bias` and field names from Task 1; add `InputValidationError(ValueError)` with `.errors: dict[str,str]` in `dc_bias.py`. `calculate_bias` validates finite and allowed physical ranges even when called directly. `checks` keys `transistor_kcl`, `divider_kcl`, `collector_drop`, `emitter_drop`, `vce_identity`, `region_consistency`.

- [ ] **Step 1 — Write failing cutoff test:** with `VCC=5V,R1=100kΩ,R2=1kΩ,RC=2.2kΩ,RE=1kΩ,β=100,VBE=0.7V`, assert `region=="cutoff_estimate"`, zero `IB_A/IC_A/IE_A`, `VE_V=0`, `VC_V=5`, `VB_V≈5/101`, warning includes `estimate`.
- [ ] **Step 2 — Run red:** `python -m unittest discover -s tests -p test_dc_bias.py -v` → fails cutoff test.
- [ ] **Step 3 — Implement cutoff branch:** when `VTH≤VBE` use leakage-free approximate `VB≈VTH,VE=0,VC=VCC,VCE≈VCC`, explicit model/warning.
- [ ] **Step 4 — Run green** cutoff + baseline tests.
- [ ] **Step 5 — Write failing saturation test:** with `VCC=5V,R1=10kΩ,R2=10kΩ,RC=10kΩ,RE=1kΩ,β=100,VBE=0.7V`, assert `region=="saturation_estimate"`, `VCE_V≈0.20`, `0<IC_A≤β·IB_A`, estimate warning, and `VC_V≈VE_V+0.20`.
- [ ] **Step 6 — Run red** and then implement bounded saturation estimate: for active candidate failing `VC>VB` or `VCE>0.20`, solve `VE=RE[((VTH−VBE)/RTH)+((VCC−0.20)/RC)]/[1+RE/RTH+RE/RC]`, `IB=(VTH−VBE−VE)/RTH`, `IC=(VCC−0.20−VE)/RC`, `IE=IB+IC`, `VB=VE+VBE`, `VC=VE+0.20`; accept `saturation_estimate` only for finite, `IB>0`, `IC≥0`, `IC≤β·IB` within stated tolerance; otherwise `outside_model` with no asserted Q-point.
- [ ] **Step 7 — Run green** saturation + prior tests.
- [ ] **Step 8 — Write failing guardrail tests:** `test_reject_zero_negative_nonfinite_inputs` covers each resistance, VCC, beta, VBE and `math.nan/inf`, asserting `InputValidationError` fields. `test_self_checks` covers KCL for both Active and Saturation estimate and all keys above; require `all(result.checks.values())` for valid sample.
- [ ] **Step 9 — Run red**, then implement strict physical/finite validation, bounded tolerance consistency checks and `outside_model` fallback. Avoid overflow in equivalent-resistance arithmetic and reject unreasonable magnitudes explicitly (e.g. resistors in `[1Ω,10^12Ω]`, `VCC∈(0,10^5]V`, `VBE∈(0,10^3]V`, beta in `(0,10^6]`, all finite); document these **software safety bounds, not transistor data-sheet ratings**.
- [ ] **Step 10 — Run green:** full engineering tests; no `NaN/Infinity` returned in a valid `BiasResult`.
- [ ] **Step 11 — Review/commit** model+test diff, e.g. `feat(lab02): verify cutoff saturation and DC consistency`.

## Task 3 — Flask Backend, HTTP Contracts and No-JS Form

**Files:** Create `app.py`, `templates/index.html`, `requirements.txt`, `tests/test_web.py`.

**Interfaces:**

- `create_app() -> Flask` plus `app=create_app()` for `python -m flask --app app run`.
- `parse_inputs(raw: Mapping[str, object]) -> BiasInputs` converts `r1/r2/rc/re` from kΩ to Ω **exactly once**, collects field errors, raises `InputValidationError`.
- `present_result(result: BiasResult) -> dict[str, str]` formats server-side values for BOTH Jinja and JSON: e.g. `VB_V -> "1.942 V"`, `IC_A -> "1.230 mA"`, `IB_A -> "12.299 µA"`; `None -> "—"`. Raw numeric `values` remain in JSON for verification.
- `GET /` HTTP 200 with default inputs and computed values; `POST /calculate` HTML success 200 / inline validation failure 422; `POST /api/calculate` JSON success 200, invalid fields 422, malformed/unexpected request 400. JSON success keys `ok`, `region`, `model`, `results`, `display`, `checks`, `warnings`; invalid keys `ok=false`, `errors`.

- [ ] **Step 1 — Write failing HTTP tests** in `tests/test_web.py`: `test_get_root` checks status 200 and input names/defaults; `test_post_form_changes_result` posts changed `rc` and checks HTML result changes; `test_json_endpoint_uses_python_result` posts default and compares `results["IC_A"]` to independent reference; `test_invalid_form_and_json_return_4xx` covers blank, malformed, zero/negative, text, NaN/Infinity and asserts no 500.
- [ ] **Step 2 — Run red:** `python -m unittest discover -s tests -p test_web.py -v` → import/route/test failure expected.
- [ ] **Step 3 — Implement app routes and input parser** with Flask and tests' contracts. Use `render_template` and normal Jinja escaping; do not expose stack traces. Reject JSON arrays/malformed payloads, but keep accessible inline errors in HTML form. `requirements.txt` includes Flask only, compatible with Python 3.12.
- [ ] **Step 4 — Implement minimal functional `templates/index.html`** using the seven fields, visible outputs and ordinary submit button; do not add SVG/JS yet. Default values computed on the server, never copied from handout's illustrative screenshot.
- [ ] **Step 5 — Run green:** `python -m unittest discover -s tests -v` → both model and Flask tests PASS.
- [ ] **Step 6 — Local smoke:** start Flask on `127.0.0.1:5000`, check normal POST and invalid form in browser; server not exposed to public network.
- [ ] **Step 7 — Review/commit** only the four new files after tests, e.g. `feat(lab02): serve validated BJT calculator through Flask`.

## Task 4 — Inline High-Fidelity Circuit, Live UI and Responsive Design

**Files:** Modify `templates/index.html`, `tests/test_web.py`; create `static/style.css`.

**Interfaces:** The inline script sends the current form field names to `POST /api/calculate` after ~350ms debounce, uses `AbortController`/monotonic request counter to reject stale response, and updates **both** results and SVG text via stable `data-result-key` attributes mapping to `display` keys from Task 3. UI calculation is forbidden.

- [ ] **Step 1 — Write failing markup-contract tests:** `test_svg_and_result_bindings_exist` checks `svg[viewBox]`/`role="img"`, accessible `<title>/<desc>`, stable voltage/current `data-result-key` values on schematic + cards; `test_no_external_script` asserts no `static/app.js` reference and no external CDN/raster circuit dependency.
- [ ] **Step 2 — Run red:** `python -m unittest discover -s tests -p test_web.py -v` → SVG/UI contract tests fail.
- [ ] **Step 3 — Draw precise inline SVG** within `templates/index.html`: `R1 VCC–Base`, `R2 Base–GND`, `RC VCC–Collector`, `RE Emitter–GND`; correct NPN emitter arrow **out**, current arrows `IB` into base, `IC` into collector, `IE` out emitter; show `VCC, VB, VC, VE, VCE, IB, IC, IE` and resistance labels with backend values; use correct `viewBox` and no bitmap schematic.
- [ ] **Step 4 — Add inline presentation JS** for 350ms debounce, JSON fetch, sequential request guard, loading/invalid/network error state, manual HTML-submit fallback and reset. Assign values using safe `textContent`, not `innerHTML`; on invalid input, clear/hide previous values and display field errors. `aria-live` conveys status to assistive tech.
- [ ] **Step 5 — Create restrained responsive CSS** in `static/style.css`: modern three-area engineering dashboard on wide screens, mobile stack, keyboard focus, readable numeric badges and legend, no clipping at 200% zoom; no external image/font dependencies.
- [ ] **Step 6 — Run green:** `python -m unittest discover -s tests -v` → all automated tests PASS.
- [ ] **Step 7 — Browser QA:** verify default numbers; change `RC`/`RE` and see schematic/cards update equally; toggle JavaScript off and submit form; fast consecutive edits with throttled network do not show old result; invalid input clears stale Q-point; zoom 200%, narrow mobile viewport, arrow/topology and labels visually checked. Record observations and any fixes in `docs/validation.md` **later within existing file**.
- [ ] **Step 8 — Review/commit** only permitted files, e.g. `feat(lab02): add live SVG engineering dashboard`.

## Task 5 — CI, Reproducibility, Lab Evidence, Release Gate

**Files:** Create `.github/workflows/tests.yml` (**sole new file exception**), `README.md`, `AGENTS.md`, `docs/validation.md`, `docs/reflection.md`; update this `docs/design-note.md` with plan approvals/results only. Do not add more repo files.

**Interfaces:** GitHub Actions triggers `push` and `pull_request`, runs Python 3.12, installs `requirements.txt`, then `python -m unittest discover -s tests -v`. Minimum workflow permissions are read-only; no secrets/deploy.

- [ ] **Step 1 — Write/finalize integration checks** in existing `tests/test_web.py`: default HTML and JSON agree on formatted values, malformed API content type returns 4xx, no stale hard-coded numeric value appears on changed input, region warning is visible in both response modes.
- [ ] **Step 2 — Run red** when a new test exercises missing contract; fix only the owning file; rerun full suite to green.
- [ ] **Step 3 — Create `.github/workflows/tests.yml`** with checkout, setup Python 3.12, `python -m pip install -r requirements.txt` and unittest discovery. Verify current official action revisions before fixing version pins.
- [ ] **Step 4 — Write `README.md`/`AGENTS.md`**: clean Windows venv setup, `python -m flask --app app run`, no-JS and live usage, commands to run tests, API, units, cutoff/saturation assumptions, distinction from SPICE, packaging constraint, caution to stage **explicit paths** (because no tracked `.gitignore`).
- [ ] **Step 5 — Write `docs/validation.md`** with independent default values, test log, test cases, visual QA record, and later GitHub CI URL/commit SHA. Write `docs/reflection.md` with the student's actual experience/limitations rather than inventing learning outcomes; if owner-specific reflection is needed, leave factual prompt to the student.
- [ ] **Step 6 — Reproducibility check** from a clean clone in a separate scoped path: venv → install → `python -m unittest discover -s tests -v` → local Flask GET + POST; include stdout/status and screenshot evidence where requested by Moodle without committing extra media files.
- [ ] **Step 7 — Explicit staging review**: compare `git status`, `git diff --check`, `git diff --cached --name-only` to exactly the allowed list + workflow; audit against secrets, `.venv`, caches, screenshots, API keys; check Git remote owner `b6617974-dot`.
- [ ] **Step 8 — Review/commit/push** only after this plan has been approved and every task passed. Use precise final commit message and record SHA; push to authorized repo/branch.
- [ ] **Step 9 — Check GitHub Actions outcome** on actual push/PR and document run URL/status. A local pass alone does not mean CI passed. If Actions access requires student authorization, stop at that gate and request it.
- [ ] **Step 10 — Final acceptance** A1–A7 + E1–E3 + U1–U4 + C1–C2; no unverified "finished" claim.

## Approved Design Baseline (travels with the plan)

### Objective and constraints

The student wants Lab 02 to **look like the handout's specified submission**, while internal code and dashboard are higher quality; not a wholesale new multi-feature project. Preserve exact file names and only add the `.github/workflows/tests.yml` exception, approved 2026-11-10. Visual choice: **Modern Engineering Dashboard (B)**. Automation choice: **A (Live), B (Engineering Verification), C (GitHub CI)**. D (parameter sweep) deferred.

### Electrical model

- NPN Common Emitter voltage-divider bias only; `R1` VCC–B, `R2` B–ground, `RC` VCC–C, `RE` E–ground.
- Thevenin: `VTH=VCC·R2/(R1+R2)`, `RTH=R1R2/(R1+R2)`.
- Forward active: `IB=(VTH−VBE)/(RTH+(β+1)RE)`, `IC=βIB`, `IE=(β+1)IB`, `VE=IE·RE`, `VB=VE+VBE`, `VC=VCC−IC·RC`, `VCE=VC−VE`.
- Cutoff estimate if `VTH≤VBE`: zero transistor currents, `VE=0`, `VB≈VTH`, `VC≈VCC`, `VCE≈VCC`; **estimate** label.
- Active candidate only accepted if `IB>0`, `VC>VB`, `VCE>0.20V`; possible saturation uses fixed `VCEsat=0.20V`, `VBEsat≈VBE input`, `VE=RE[((VTH−VBE)/RTH)+((VCC−0.20)/RC)]/(1+RE/RTH+RE/RC)`, `IB=(VTH−VBE−VE)/RTH`, `IC=(VCC−0.20−VE)/RC`, `IE=IB+IC`, `VB=VE+VBE`, `VC=VE+0.20`; accept **estimate** only for finite/current-consistent states **and `VB>VC` (BC forward bias)**, else `outside_model` with no trustworthy Q-point. The BC junction guard was added after independent review identified an inconsistent low-VBE case.
- Check transistor KCL (`IE=IB+IC`), divider KCL (`(VCC−VB)/R1=VB/R2+IB`), resistor drops and `VCE=VC−VE`, region consistency. These are **internal approximation** checks, not SPICE accuracy proof.

### Reference numbers

For `VCC=12V,R1=100kΩ,R2=22kΩ,RC=2.2kΩ,RE=1kΩ,β=100,VBE=0.70V`:

| Name | Reference |
|---|---:|
| VTH | 2.163934426 V |
| RTH | 18.032786885 kΩ |
| VB / VE / VC / VCE | 1.942156728 / 1.242156728 / 9.294312078 / 8.052155351 V |
| IB / IC / IE | 12.298581463 µA / 1.229858146 mA / 1.242156728 mA |

The schematic examples in the handout use illustrative **non-authoritative** numbers; tests use these independently checked engineering references.

### Gates

- **Design:** APPROVED, including saturation estimate and one workflow-file exception.
- **This implementation plan:** APPROVED by the student on 2026-11-10.
- **Implementation, local task commits and GitHub publication:** AUTHORIZED by the student's follow-up. Only the precise handout files and the one previously approved CI workflow may be published; publication verification remains separate.
- **Evidence-based closeout:** The authorized Windows repository contained exactly thirteen tracked paths and a clean working tree after the initial publication. Eighteen Python/Flask tests passed on Windows; the owner-provided GitHub Actions screenshot showed two successful runs. Moodle submission evidence remains separate from repository files.
