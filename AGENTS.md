# Lab 02 Repository Conventions

This is a bounded student laboratory exercise, **not a general electronics simulation platform**.

## File and submission contract

The only tracked paths permitted for this exercise are:

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

Keep the active, cutoff and saturation assumptions explicit. If a model is not physically consistent, return `outside_model`, not a false numerical Q-point. Passing equation checks is not proof of SPICE-equivalent accuracy.

## Required validation

1. Run `python -m unittest discover -s tests -v` and retain the error-free results.
2. Review default numeric reference and cutoff/saturation cases in `docs/validation.md`.
3. For interface edits, confirm that the SVG and result cards use the same server result, invalid input clears old outputs, the non-JavaScript form works, and the diagram is readable on narrow screens.
4. Run `git diff --check` and compare the exact staged file list with the contract above.
5. Never add secrets, tokens, personal data or executable deployment workflows.

The student owns the final submission and personal reflection; do not invent observations, lab measurements or personal learning experiences.
