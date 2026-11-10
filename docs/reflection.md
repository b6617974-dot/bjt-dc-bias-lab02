# Lab 02 — Reflection

## What the exercise demonstrates

The voltage-divider network provides the base bias of an NPN transistor. Replacing R1 and R2 with a Thévenin equivalent makes the DC calculation shorter and exposes how supply voltage, resistor values, the assumed VBE and β affect the operating point.

The worked default example gives approximately **VB=1.942 V**, **VE=1.242 V**, **VC=9.294 V**, **VCE=8.052 V** and **IC=1.230 mA**. The calculation is most useful when the transistor is in forward-active operation and its assumptions are stated.

## Improvements within the required Lab files

- Separated circuit calculations from the Flask web interface so the equations can be tested without opening a browser.
- Displayed the same server-calculated voltage and current values on both the SVG circuit and the result cards.
- Added automatic KCL/KVL checks to catch internally inconsistent calculations.
- Clearly distinguished forward-active operation from cutoff/saturation **estimates**.
- Kept the standard HTML form working with JavaScript disabled.
- Added repeatable tests and the explicitly approved GitHub Actions workflow.

## Important limitations

The model uses constant β and VBE. Actual devices vary with temperature, manufacturing spread and collector-emitter voltage. The saturation estimate assumes a fixed VCE(sat)=0.20 V, while cutoff neglects leakage. As a result, the displayed values are **educational estimates**, not circuit measurements or a substitute for transistor characteristic curves/SPICE.

## Key takeaway and next experiment

The main lesson is that a plausible numerical answer is not enough: the assumed transistor region and the current/voltage relationships must also agree. Automatic KCL/KVL checks make those relationships visible, while the updated circuit diagram helps connect each calculated number to its physical node or branch.

A meaningful next experiment would compare these predicted DC values with SPICE or a measured circuit using an actual transistor model. That comparison has **not** been performed in this Lab and is not represented as completed experimental work.
