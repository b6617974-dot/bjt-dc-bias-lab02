# Lab 04 · บันทึกการทำงาน

- AI ช่วยผสาน Lab 03 และ Lab 04 จัดหน้าจอและเชื่อมผลจริงจาก Flask กับ ngspice
- AI เขียน Netlist แยกเพื่อทวนสมการและแหล่งข้อมูลของกราฟ แล้วตรวจการแสดงผลบนจอคอมและมือถือ
- การทดลองชี้ให้เห็นว่า DC bias จาก β และ V<sub>BE</sub> คงที่ให้ค่าอ้างอิงคนละแบบกับการรันโมเดลทรานซิสเตอร์ใน ngspice จึงต้องบันทึกชื่อโมเดลและรหัสรันพร้อมผล
- นักศึกษาตรวจด้วยตนเองใน Lab 04 … [เติมสิ่งที่ตรวจจริงก่อนส่ง]

## แนวคำตอบปิด Lab 04

1. Python แปลงอินพุตเป็น SI แล้วสร้าง Netlist ตามวงจรและ analysis ที่เลือก ส่ง Netlist ให้ ngspice แบบ batch อ่าน raw กับ log ตรวจชนิดข้อมูลและหน่วย แล้วคืนผลพร้อมรหัสรันให้หน้าเว็บ
2. `.ac` อ่านอัตราส่วนเชิงซ้อน Vout/Vin รอบจุดทำงานขณะเปลี่ยนความถี่ ส่วน `.tran` อ่านแรงดัน Vin/Vout ตามเวลาโดยใช้แอมพลิจูดและความถี่ที่กำหนดใน SIN
3. ถ้าเปลี่ยน Amplitude ให้ดูว่าเลือก Transient และรหัสรันเปลี่ยน จากนั้นไล่ค่าจากช่อง mV peak ไปยังคำขอ การแปลงเป็น V peak บรรทัด SIN ใน Netlist และช่วงเวลาของ Vin/Vout ในผลรอบเดียวกัน ค่า Amplitude ของ SIN ใช้ใน Transient
4. Impeccable ใช้ตรวจการจัดวาง ขนาดป้าย หน่วย และการโต้ตอบ ให้สมการ topology จุดวัด และที่มาผลคงตามข้อกำหนดของวงจรและ solver
5. อ่าน Vin และ Vout เชิงซ้อนที่ความถี่เดียวกันจาก raw ของรุ่นและรหัสรันที่ระบุ คิด 20 log₁₀|Vout/Vin| และมุมของอัตราส่วน แล้วเทียบกับเคอร์เซอร์และ CSV จากรอบเดียวกัน

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
