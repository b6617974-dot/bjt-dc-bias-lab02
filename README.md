# Lab 02 — BJT DC Bias Calculator

An interactive Flask application for the **DC operating point of an NPN common-emitter transistor with voltage-divider bias**. The laboratory's seven input parameters, calculation module, HTML template, CSS and tests are preserved; the implementation adds an accurate inline circuit schematic, real-time feedback, electrical consistency checks and one GitHub Actions workflow.

## 1. Run the application

Install **Python 3.12** or later. From this repository's folder:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m flask --app app run
```

Open `http://127.0.0.1:5000/`. On Linux/macOS, use `source .venv/bin/activate` instead of the PowerShell activation command. If PowerShell prevents activation, run `.\.venv\Scripts\python.exe` directly for the install and Flask commands.

The page calculates a default operating point immediately. Editing any input updates both the numeric cards and the vector circuit after a short delay (~350 ms). **Calculate operating point** also submits the form normally when JavaScript is unavailable. **Reset** restores the example values.

## 2. Inputs and output units

| UI name | Meaning | Unit | Default |
|---|---|---|---:|
| VCC | Supply voltage | V | 12 |
| R1 | Divider resistor, VCC to base | kΩ | 100 |
| R2 | Divider resistor, base to ground | kΩ | 22 |
| RC | Collector resistor | kΩ | 2.2 |
| RE | Emitter resistor | kΩ | 1 |
| β | Fixed current gain | dimensionless | 100 |
| VBE | Assumed base-emitter voltage | V | 0.70 |

The Python calculation engine accepts resistance in **Ω** and current in **A**. The Flask layer converts the four kΩ inputs to Ω once and formats the result for display. It reports $V_B,V_E,V_C,V_{CE},I_B,I_C,I_E,V_{TH},R_{TH}$.

## 3. Method and engineering limits

The divider is replaced by its Thévenin equivalent:

$$
V_{TH}=\frac{V_{CC}R_2}{R_1+R_2},\qquad
R_{TH}=\frac{R_1R_2}{R_1+R_2}
$$

In forward-active operation:

$$
I_B=\frac{V_{TH}-V_{BE}}{R_{TH}+(\beta+1)R_E},\quad
I_C=\beta I_B,\quad I_E=(\beta+1)I_B
$$

$$
V_E=I_ER_E,\qquad V_B=V_E+V_{BE},\qquad
V_C=V_{CC}-I_CR_C,\qquad V_{CE}=V_C-V_E
$$

The program distinguishes:

- **Forward active:** a consistent operating point under fixed-β, fixed-VBE assumptions.
- **Cutoff estimate:** zero transistor current and negligible leakage when the divider cannot forward-bias the base.
- **Saturation estimate:** a bounded approximate solution using $V_{CE(sat)}=0.20\,V$ and the supplied VBE. The base-collector junction must also be forward-biased ($V_B > V_C$); otherwise the program declines to report a saturation Q-point.
- **Outside model:** no consistent Q-point can be asserted within those approximations.

Automatic checks evaluate transistor KCL, divider KCL, collector/emitter resistor drops, $V_{CE}=V_C-V_E$, and region consistency. A **PASS** verifies the internal equations, **not** actual transistor behavior. This is **not SPICE**, a measured circuit, an AC amplifier model or a device-curve analysis.

Inputs must be finite and physically positive; intentionally broad numeric software bounds prevent invalid or unreasonable computations but are **not component ratings**.

## 4. Run the tests

```powershell
python -m unittest discover -s tests -v
```

Tests cover independent default numeric references, active/cutoff/saturation models, invalid values, KCL/KVL, real Flask HTML/JSON routes, form fallback, and equivalence between schematic labels and result cards. The approved GitHub Actions workflow runs the same command on Python 3.12 after each push or pull request.

### HTTP interface

| Method | Path | Function |
|---|---|---|
| GET | `/` | Render the form and default calculated result |
| POST | `/calculate` | Recalculate via standard HTML form; show errors inline |
| POST | `/api/calculate` | Receive JSON inputs, return JSON outputs |

Example API request:

```json
{"vcc":"12","r1":"100","r2":"22","rc":"2.2","re":"1","beta":"100","vbe":"0.70"}
```

A successful response contains `ok`, `region`, `model`, raw SI-unit `results`, human-readable `display`, `checks`, and `warnings`. Invalid inputs return a structured 4xx response with field-specific `errors`; they do not produce a fabricated operating point.

## 5. Submission file discipline

Only the handout's named files and the approved `.github/workflows/tests.yml` are committed. The circuit SVG and the live-update JavaScript are **inside** `templates/index.html`; no external JS or image asset is needed. Local `.venv`, generated caches, browser screenshots and temporary test scripts **must not be staged**. Use explicit file names when running `git add`.

Further details: [Design](docs/design-note.md), [Validation](docs/validation.md), [Reflection](docs/reflection.md).

### Moodle submission (Lab 02 handout)

Submit the **repository URL and final commit SHA** through Moodle. Include a **screenshot of the working Flask page with a successful DC bias calculation** and the **automated test log** as evidence. The handout also expects code review, design/planning work and a student-owned reflection. Keep screenshots and test logs outside the tracked source-code tree unless a separately authorized submission method explicitly requires them.
