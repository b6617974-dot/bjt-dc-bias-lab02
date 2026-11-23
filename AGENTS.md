# Lab 04 Repository Conventions

This is a bounded student laboratory exercise, **not a general electronics simulation platform**.

## File and submission contract

The Lab 04 branch preserves the Lab 03 file contract and adds the following exercise files:

- `spice_engine.py` and `tests/test_spice_engine.py`
- `templates/spice.html`, `static/spice.css`, and `static/spice.js`

The preceding labs use these paths:

- `app.py`
- `dc_bias.py`
- `templates/index.html`
- `static/style.css`
- `tests/test_dc_bias.py`
- `tests/test_web.py`
- `requirements.txt`
- `README.md`
- `AGENTS.md`
- `docs/design-note.md`
- `docs/validation.md`
- `docs/reflection.md`
- `.github/workflows/tests.yml` (**the single extra file explicitly approved by the student**)

Do not commit extra source files, generated HTML/image assets, screenshots, caches, virtual environments, or local test harnesses. There is intentionally no tracked `.gitignore`; stage **specific paths only**.

## Engineering separation

- `dc_bias.py`: pure NPN voltage-divider DC math, SI units, region approximations, KCL/KVL and input checks. No Flask or display markup.
- `app.py`: validate HTTP input, convert kΩ to Ω exactly once, format results once for HTML and JSON.
- `templates/index.html`: accessible layout, precise **inline SVG**, and presentation-only inline JavaScript; never calculate transistor physics here.
- `static/style.css`: responsive presentation without external JS, image, CSS or font dependencies.
- `spice_engine.py`: validate CE inputs, select the server-side model, construct the approved circuit, run ngspice, and return checked quantities in SI.
- `templates/spice.html` and its local assets: render the validated solver data and identify the source, model, units, and run.

Keep the active, cutoff and saturation assumptions explicit. If a model is not physically consistent, return `outside_model`, not a false numerical Q-point. Passing equation checks is not proof of SPICE-equivalent accuracy.

## Required validation

1. Run `python -m unittest discover -s tests -v` and retain the error-free results.
2. Review default numeric reference and cutoff/saturation cases in `docs/validation.md`.
3. For interface edits, confirm that the SVG and result cards use the same server result, invalid input clears old outputs, the non-JavaScript form works, and the diagram is readable on narrow screens.
4. Run `git diff --check` and compare the exact staged file list with the contract above.
5. Never add secrets, tokens, personal data or executable deployment workflows.

The student owns the final submission and personal reflection; do not invent observations, lab measurements or personal learning experiences.
