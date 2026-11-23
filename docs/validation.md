# BJT Workbench · ตรวจรุ่นที่ใช้ OpenJellyBean

รุ่นสาธิตใช้ ngspice 47 และโมเดล OpenJellyBean 2N3904_OJ ชั่วคราว SHA-256 `c543201058bd7fd0a976fe1ca6d08baa2dd2bf3d2841745cd641861e2ffaf8c2` ผลในตารางนี้มาจาก Netlist ที่รันแยกจาก Flask โดยใช้แรงดันจาก raw และสมการในหัวข้อจุดวัดด้านล่าง กระแสอ้างอิงที่ขาภายนอกคำนวณจากแรงดันและค่าตัวต้านทาน แล้วเทียบกับตัววัด 0 V ของแอป

| กรณี | อินพุตและวิธีตรวจอิสระ | ผลอ้างอิงพร้อมหน่วย |
|---|---|---:|
| B2 | DC ค่าฐาน, หักแรงดัน V<sub>C</sub> − V<sub>E</sub>, ใช้แรงดันตกคร่อม R<sub>C</sub> หา I<sub>C</sub> | V<sub>CE</sub> 7.654527225 V, I<sub>C</sub> 1.355570564 mA |
| B3 | DC เปลี่ยนเฉพาะ R<sub>E</sub> จาก 1 เป็น 2 kΩ, ทวนกฎ KCL ก่อนปัดเศษ | V<sub>CE</sub> 8.975300477 V, I<sub>C</sub> 0.718219525 mA |
| B4 | AC ค่าฐาน 10 Hz–1 MHz, ใช้ข้อมูลเชิงซ้อน Vin และ Vout คู่เดียวกันจาก raw | 201 จุด, ที่ 1 kHz ได้ 4.895588550 dB และ −179.872035482° |
| B5 | Transient 10 mV peak / 1 kHz, วัดคาบ Vin และครึ่ง Vpp ของ Vout ในช่วง 0–4 ms | Vin 1.000 ms, Vout 17.567340821 mV |
| B6 | เปลี่ยนเป็น 20 mV peak ที่ 1 kHz แล้วคืนเป็น 10 mV peak ก่อนเปลี่ยนเป็น 2 kHz | Vout 35.134647392 และ 17.567549076 mV, Vin 1.000 และ 0.500 ms ตามลำดับ |

แรงดันอ้างอิง DC นี้มาจากผลลู่เข้าของ solver ส่วนกระแสที่อ่านจากตัวแปรภายใน Q1 กับกระแสขาภายนอกต่างกันเล็กน้อยตามเกณฑ์ลู่เข้าของ solver จึงใช้ตัววัด 0 V และแรงดันตกคร่อมตัวต้านทานเป็นจุดเทียบเดียวกัน กระแสภายนอกผ่านการตรวจ KCL ที่ระดับประมาณ 10 pA ทั้งสองรอบ

- **B1** ใช้ผล Analytical A1–A5 ในตารางด้านล่างเป็นค่าอ้างอิง เพราะ Lab 03 คำนวณด้วย β และ V<sub>BE</sub> คงที่
- **B7** การตรวจในเครื่องใช้ทั้ง divider ที่วัดได้ 5 V และตัวอย่างที่ตั้งให้ได้ 4 V เพื่อทวนกรณีหยุดเมื่อวงจรทดสอบไม่ผ่าน การทดสอบรวมไฟล์หาย, SHA-256 ไม่ตรง, ตำแหน่งไฟล์ออกนอกโฟลเดอร์, timeout, ข้อมูล raw เสีย และความพร้อมที่ผูกกับ executable และโมเดล
- **B8** หลักฐานการตรวจเบราว์เซอร์และอุปกรณ์อ้างตามรหัสรันและ Commit SHA ใน manifest ของชุดหลักฐาน
- การยืนยันด้วย Starter Kit ของผู้สอนเป็น **NOT RUN** จนกว่าจะได้รับชุดจริง การตรวจผ่าน Playwright MCP เป็น **NOT RUN** ผลเบราว์เซอร์บันทึกจาก Chromium ผ่าน Playwright Node.js

ผลที่อ่านจากเว็บและเทียบกับอ้างอิงชุดเดียวกันมีดังนี้ เกณฑ์เทียบ DC ใช้ 0.1 mV และ 0.01 mA เพื่อครอบคลุมความต่างของรอบลู่เข้าเมื่อเพิ่มตัววัด 0 V การตรวจสมการ KCL ใช้ 1 pA บวก 0.001 เท่าของขนาดกระแสตามสมการ

| กรณี | ค่าที่เห็นหรือพฤติกรรม | หลักฐานและสถานะ |
|---|---|---|
| B1 | Analytical IC ของ A1–A4 ได้ 1.230, 1.130, 1.026, 0.940 mA ตามลำดับ A5 ได้ 422 เพราะ RB = 0 | Regression ผ่าน Flask และ Chromium · PASS |
| B2 | VB 2.02604 V, VE 1.36322 V, VC 9.01774 V, VCE 7.65453 V และ IC 1.35557 mA | `browser/B2-dc.png` และ raw/log ของรอบ DC · PASS |
| B3 | RE 1 → 2 kΩ ได้ IC 1.35557 → 0.718237 mA, VCE 7.65453 → 8.97523 V ความต่างจาก Netlist แยกที่ RE = 2 kΩ ประมาณ 18 nA และ 75 µV | `browser/browser-report.json` และ raw/log สองรอบ · PASS |
| B4 | 201 จุด ที่ 1 kHz ได้ 4.89559 dB / −179.872° เทียบกับผลเชิงซ้อนใน raw ที่ความถี่เดียวกัน | `browser/390-ac.png`, CSV และ raw/log · PASS |
| B5 | Vin คาบ 1.000 ms และ Vout ครึ่ง Vpp 17.5673 mV ในช่วง 0–4 ms เส้น Vout กลับเฟสจาก Vin | `browser/390-tran.png` และ raw/log · PASS |
| B6 | ตั้ง 20 mV peak ได้ Vout ครึ่ง Vpp 35.1346 mV คืนแอมพลิจูดแล้วตั้ง 2 kHz ได้คาบ 0.500 ms และ Vout ครึ่ง Vpp 17.5675 mV | `browser/browser-report.json` และ raw/log สองรอบ · PASS |
| B7 | RE = 0 ได้ 422 กราฟ รหัสรัน และปุ่มส่งออกของผลเดิมถูกล้าง ผลทดสอบ Python ครอบคลุมไฟล์และการตั้งค่าผิด | `browser/browser-report.json` และ `tests.txt` · PASS |
| B8 | 1440 / 390 / 320 px สลับโหมด อ่านหน่วย เล่น/พัก ขยับเคอร์เซอร์ ขยายวงจร และเปิดแผงตั้งค่าได้ | `browser/browser-report.json` และภาพ Desktop/Phone · PASS |

## ผลการตรวจการรวม Lab 03–04 ด้วย onsemi

ตรวจบน Flask จริงด้วย Chromium ที่ความกว้าง 1440, 390 และ 320 px ใช้ ngspice 47 กับ onsemi 2N3904 ชั่วคราวตาม SHA-256 ในหัวข้อถัดไป ตัวเลขที่ทวนใช้ผลก่อนปัดเศษ และสคริปต์ตรวจคำนวณสมการ DC, KCL, gain และการวัดคาบแยกจากโค้ดหน้าเว็บ

| กรณี | ผลตรวจ |
|---|---|
| DC และสมการ | Voltage Divider คำนวณมือ IC 1.229858 mA และ ngspice IC 1.325516 mA พร้อมป้ายที่มา Fixed/Emitter คำนวณมือได้ 1.130000 และ 1.026340 mA ตามลำดับ อินพุตผิดได้ HTTP 422 และไม่แสดงผลเก่า |
| ค่าฐานข้ามแท็บ | เปลี่ยน RE 1 → 2 kΩ แล้วได้ IC 0.713542 mA จาก SPICE เทียบ AC ที่ 1 kHz ได้ ΔGain −5.99819 dB เปิด Transient ต่อด้วยค่าชุดเดียวกัน |
| วัดจากกราฟ | ปักจุด A เลื่อน B และซูมช่วงที่เลือกได้ คาบ Vin 1 kHz ที่วัดจากข้อมูลประมาณ 1.000 ms กรณีฐานไม่พบจุด −3 dB ในช่วง sweep เมื่อเปลี่ยน Cin เป็น 0.01 µF พบจุดตัดด้านต่ำประมาณ 576.529 Hz ในช่วงระหว่างตัวอย่างจริง 562.341–595.662 Hz |
| ออกแบบให้เข้าเป้า | Gain อย่างน้อย 6 dB และ IC ไม่เกิน 1.5 mA ได้ชุด RC 3.3 kΩ / RE 1 kΩ ที่ 7.56804 dB และ 1.32522 mA รัน DC และ AC แยกเพื่อทวนชุดที่เสนอ กรณีเป้าไม่ถึงและค่าเป้าไม่ถูกต้องแสดงสถานะตามจริง |
| สมุดทดลองและหลักฐาน | บันทึกและเปิดข้ามการโหลดหน้าใหม่ได้ อินพุตและจุดอ่าน A/B คืนมาครบพร้อมรหัสรันใหม่ ตรวจ CSV และ JSON กับผล API รวมถึง SVG และ PDF ที่มีชื่อโมเดลและสมการ |
| คำตอบล่าช้าและโมเดล | บังคับให้คำตอบรอบเก่าถึงหลังรอบใหม่แล้วตรวจว่าหน้าเว็บยังแสดงรอบล่าสุด ปฏิเสธการซ้อนกราฟเมื่อข้อมูลจำลองระบุโมเดลต่างรุ่น และยังอ่านผลคำนวณมือได้เมื่อจำลองกรณี engine ใช้งานไม่ได้ |
| การแสดงผล | การเปิดสูตรไม่ดันวางวงจรออกจากคอลัมน์เดสก์ท็อป บนมือถือเลื่อนสมการในกรอบพร้อมวงจรย่อ แถบวิเคราะห์ค้างด้านบนและกรอบตัวเลขอยู่ตำแหน่งเดิมระหว่างเลื่อนกราฟ |

ชุดทดสอบ Python ผ่าน 85 รายการ และทวน A1–A5 ของ Lab 03 บนเว็บเดิมพร้อมฟอร์มเมื่อปิด JavaScript หลักฐาน Workbench เก็บแยกจาก Git ใน `work/lab04-runtime/unified-workbench-review` และ `unified-workbench-exports` วิธีทดสอบผ่าน Playwright Node.js ใน Chromium ครอบคลุม viewport มือถือ

# Lab 04 · บันทึกตรวจรับ CE Amplifier Simulator

**วงจร** NPN CE Voltage Divider ไม่มีตัวเก็บประจุ bypass ที่ RE ใช้ VCC 12 V, R1/R2 100/22 kΩ, RC/RE/RL 2.2/1/10 kΩ, Cin/Cout 10/10 µF และ SIN 10 mV peak / 1 kHz สำหรับ Transient

**ที่มา** ngspice 47 (Windows Console), 2N3904 จาก [onsemi](https://www.onsemi.com/pub/Collateral/2N3904.SP3), SHA-256 `ba63b85c254f6fc90e1ccd89ae70b9cc9ee1ada7ba4875f3bb22f1431999d503` โมเดลชั่วคราว อุณหภูมิจาก log 27 °C การตรวจด้วย Starter Kit ผู้สอนยังเป็น **NOT RUN** เพราะยังไม่มีไฟล์ชุดนั้น

## จุดวัดและวิธีทวนแยกจากแอป

Vin วัดก่อน Cin, Vout วัดคร่อม RL หลัง Cout, Vc วัดฝั่งคอลเลกเตอร์ก่อน Cout อ้างกราวด์ร่วม กำหนด IB/IC เข้าทรานซิสเตอร์และ IE ออกจากทรานซิสเตอร์ วงจรอ้างอิงที่เขียนแยกอ่านกระแสขาของ Q1 โดยตรง ตัวเชื่อมแอปอ่านผ่านตัววัด 0 V แล้วเทียบผลกับกระแสที่คำนวณจากแรงดันตกคร่อมตัวต้านทาน

- DC ตรวจ VCE = VC − VE และกฎ KCL ที่ฐาน คอลเลกเตอร์ และอีมิตเตอร์ ค่าคลาดเคลื่อนสูงสุดของการคำนวณแยกที่จุดอ้างอิงสองรอบอยู่ประมาณ 10.43 pA เกณฑ์ของแอปใช้ 1 pA บวก 0.001 เท่าของขนาดกระแสตามสมการ ตรวจจากค่าก่อนปัดเศษ
- AC คำนวณแรงดันเชิงซ้อน H = Vout/Vin, 20 log₁₀|H| และเฟสแบบต่อเนื่อง แกนความถี่เป็น logarithmic เปรียบเทียบทุก 201 จุดกับผลอ้างอิงที่รันแยก
- Transient คำนวณครึ่งหนึ่งของ peak-to-peak จากตัวอย่างจริงทั้งหมดในช่วง 0–4 ms ตรวจคาบของ Vin และทวนเฟสแยกจากเฟสเซอร์ของคาบสุดท้าย ผลแอมพลิจูดจากตัวอย่างมีความต่างเล็กน้อยจากค่าที่ตั้งได้

$$
\begin{aligned}
V_{CE} &= V_C - V_E, \\
I_B &\approx \frac{V_{CC}-V_B}{R_1}-\frac{V_B}{R_2}, \quad
I_C \approx \frac{V_{CC}-V_C}{R_C}, \\
I_E &\approx \frac{V_E}{R_E}, \quad I_E \approx I_B+I_C.
\end{aligned}
$$

$$
H(f)=\frac{V_{out}(f)}{V_{in}(f)},\qquad
G_{\mathrm{dB}}=20\log_{10}|H(f)|,\qquad
\phi(f)=\frac{180^\circ}{\pi}\arg H(f),\qquad
\frac{V_{pp}}{2}=\frac{V_{\max}-V_{\min}}{2}.
$$

| ตัวแปร | ค่าจากการรัน ngspice โดยตรง |
|---|---:|
| DC ฐาน VB / VE / VC | 1.967953686 / 1.336383612 / 9.083865683 V |
| DC ฐาน VCE / IC | 7.747482070 V / 1.325515590 mA |
| DC เปลี่ยน RE เป็น 2 kΩ | VCE 8.990107078 V / IC 0.713541639 mA |
| AC ที่ 1 kHz | Gain 4.796525971 dB / Phase −179.870644008° |
| Transient 10 mV peak / 1 kHz | Vout ครึ่ง Vpp 17.368146006 mV / คาบ Vin 1 ms |
| Transient 20 mV peak / 1 kHz | Vout ครึ่ง Vpp 34.736220524 mV |
| Transient 10 mV peak / 2 kHz | Vout ครึ่ง Vpp 17.368373849 mV / คาบ Vin 0.5 ms |

ผล Analytical ของ Lab 03 ใช้ β และ VBE คงที่ ค่าฐานของ Lab 03 คือ IC 1.229858146 mA และ VCE 8.052155351 V สำหรับชุดอินพุต A1 จึงต้องแสดงแหล่งที่มาคนละชุดกับผล 2N3904

## B1–B8 · Flask จริงและ Chromium

ตรวจวันที่ 23 พฤศจิกายน 2569 ด้วย Python 3.12, ngspice 47 และ Playwright Node.js ใน Chromium 151.0.7922.34 คอลัมน์หลักฐานใช้ชื่อไฟล์ในชุด `Lab04_Evidence.zip` ซึ่งมี manifest ผูกกับ commit ที่ส่งตรวจ เกณฑ์เทียบเชิงตัวเลขมาจากสคริปต์อิสระในชุดเดียวกัน ค่าที่อ่านบนจอใช้เกณฑ์การปัดเศษตามหลักที่แสดง

| กรณี | วิธีตรวจและอินพุต | ค่าคาดและเกณฑ์ | สิ่งที่เห็น | หลักฐาน | สถานะ |
|---|---|---|---|---|---|
| B1 | เปิด A1–A5 ใน Lab 03 และส่งฟอร์มเดิมโดยปิด JavaScript | A1–A4 ตรงกับสมการ Analytical ตามหน่วยและหลักที่แสดง, A5 ปฏิเสธ RB = 0 | IC / VCE ของ A1 = 1.230 mA / 8.052 V, A2 = 1.130 mA / 9.514 V, A3 = 1.026 mA / 8.705 V, A4 = 0.940 mA / 8.033 V และ A5 ได้ HTTP 422 พร้อมล้างผล ฟอร์มเดิมใช้ได้ทั้งสามโหมด | `lab03/acceptance.json` | PASS |
| B2 | DC ค่าฐานจากเว็บ เทียบ Netlist อิสระและสมการ DC | ตามตารางอ้างอิง เกณฑ์เทียบ Netlist 0.1 µV และ 1 nA | VB 1.96795 V, VE 1.33638 V, VC 9.08387 V, VCE 7.74748 V, IC 1.32552 mA บนจอ | `browser/B2.png` · `1a6b01d406754bcc904a5756f0784fc4` | PASS |
| B3 | คงค่าฐาน เปลี่ยนเฉพาะ RE 1 → 2 kΩ | ตามตารางอ้างอิง ใช้เกณฑ์เดียวกับ B2 | IC 1.32552 → 0.713542 mA, VCE 7.74748 → 8.99011 V บนจอ | `browser/B3.png` · `ef07e406ceb749308d8fd108c57105de` | PASS |
| B4 | AC ค่าฐาน 10 Hz–1 MHz เทียบ H จากแรงดันเชิงซ้อนทุกจุด | 201 จุด เกณฑ์ 1 µHz, 0.000001 dB, 0.00001° (คิดเฟส modulo 360°) | ที่ 1 kHz กราฟและ CSV ได้ 4.79653 dB / −179.871° เมื่อปัดตามจอ ความต่างสูงสุดจาก Netlist อิสระ 0.0000000341 dB และ 0.00000000181° | `browser/B4.png`, `browser/B4.csv` · `c7ce1137a86644b28b975f52254b70ee` | PASS |
| B5 | Transient 10 mV peak / 1 kHz อ่านคู่ Vin/Vout ในช่วง 0–4 ms | คาบ Vin 1 ms ภายใน 0.01 µs และ Vout ครึ่ง Vpp อ้างอิง 17.368146 mV ภายใน 0.02 mV | คาบ 1.000 ms, Vout ครึ่ง Vpp 17.3681 mV บนจอ การทวนคาบสุดท้ายแยกได้เฟส −179.8707° | `browser/B5.png` · `e0c1830d65ef449cb67052f19c16da2c` | PASS |
| B6 | เปลี่ยนเป็น 20 mV peak ที่ 1 kHz แล้วคืนเป็น 10 mV peak ก่อนเปลี่ยนเป็น 2 kHz | คาบ 1.000 และ 0.500 ms ตามลำดับ และ Vout ครึ่ง Vpp อ้างอิงตามตาราง ใช้เกณฑ์ B5 | Vout ครึ่ง Vpp 34.7362 และ 17.3684 mV ตามลำดับ คาบ Vin 1.000 และ 0.500 ms | `browser/B6A.png` · `9703e8198aec4081a172f5b928e2d333`, `browser/B6F.png` · `21ba37e8b51e4d6ba68cba3a8d48af2a` | PASS |
| B7 | ตั้ง RE = 0 บนเว็บ ตรวจโมเดลผิด/หาย เครื่องมือหาย timeout และ raw ขาดด้วยชุดทดสอบ ค้างคำตอบ AC เก่าแล้วปล่อยหลัง DC แสดงผล | ส่งรหัสแยกตามสาเหตุ ล้างผลเมื่อเกิดข้อผิดพลาด และแสดงเฉพาะผลรอบล่าสุด | RE แสดงข้อความให้กรอกจำนวนจำกัดที่มากกว่าศูนย์พร้อม HTTP 422 การทดสอบจับสาเหตุแยกได้ คำตอบ AC เก่าถูกส่งถึงหน้าเว็บแล้วและ DC ยังแสดงรหัสรอบล่าสุด | `browser/B7.png`, `independent/browser_results.json`, `tests.txt` | PASS |
| B8 | เปิดเว็บที่ 1440×900 และ 390×844 สลับโหมด ซูมวงจร เล่น/พัก เลือกด้วยคีย์บอร์ด ปักจุด เทียบรอบ และส่งออก CSV | จุดบนกราฟตรงกันตามแกน แกนและป้ายอ่านได้ ไม่มีการล้นแนวนอน | ตัวตรวจอิสระอ่านภาพและวัดกรอบ SVG แล้ว แกน AC และ Transient อยู่ครบ ป้าย Cout และ Vout มีพื้นที่แยกกัน ลูกศร NPN ชี้ออกจากขาอีมิตเตอร์ | `browser/B4.png`, `browser/B8-mobile.png`, `independent/browser_results.json` และภาพก่อน/หลัง | PASS |

- ชุดทดสอบ 78 รายการรวมการเปลี่ยนไปใช้ fixture ประเภท `.SUBCKT` สามขาที่กำหนดลำดับ E,C,B ตรวจ SHA-256 และผลด้วย ngspice จริง ใช้ fixture นี้ตรวจระบบสลับชุดโดยไม่แก้ UI
- การตรวจผ่าน **Playwright MCP: NOT RUN** เนื่องจากเครื่องมือ MCP นี้ไม่พร้อมใช้งานในสภาพแวดล้อมที่ตรวจ ผล B1–B8 ข้างต้นมาจาก Playwright Node.js ใน Chromium
- Impeccable CLI 4.10.0 ตรวจเว็บก่อนและหลังปรับ ลดกรอบซ้อนในสถานะรอและแผงเครื่องมือ เหลือข้อสังเกตระดับ advisory หนึ่งรายการเรื่องตารางพื้นหลัง ตารางนี้อยู่ในพื้นที่แผนภาพวงจร ผล audit และภาพก่อน/หลังอยู่ในชุดหลักฐาน
- ยืนยันรุ่นส่งตามชุดผู้สอนเมื่อได้รับไฟล์จริงและทวน topology, ลำดับขา, สมการ และ B1–B8 อีกครั้ง การตรวจในบันทึกนี้ครอบคลุมรุ่นสาธิตที่ใช้ **onsemi 2N3904 ชั่วคราว**

# Lab 02 — Validation Record

**Date:** 2026-11-10 (Asia/Bangkok)
**Scope:** NPN voltage-divider DC operating point; pure math, real Flask HTTP routes, inline SVG UI, and repository CI.
**Status:** Python, HTTP, and Windows Chrome browser QA verified. The first two GitHub Actions runs were reported **successful** in an authenticated Actions screenshot supplied by the repository owner on 2026-11-10. Individual hosted job logs were not separately inspected.

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
| GitHub Actions / Python 3.12 | 2026-11-10; runs #1 and #2 on `main` | **Success (green checks in owner-provided screenshot)** | Workflow uses the same unittest command; individual hosted logs not inspected |

This CI result is based on the GitHub Actions run-summary screenshot, not an independent download of the hosted logs. A future push must be checked as a separate workflow run before claiming that its CI succeeded.

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

**GitHub push receipt:** `git ls-remote origin refs/heads/main` returned `2ba86d899d69af19b00a5ecd38b341d4b8bccf02` for `main` on 2026-11-10. The first commit includes exactly the twelve handout paths and the one approved Actions workflow.

**GitHub Actions receipt:** The owner's authenticated Actions page screenshot on 2026-11-10 shows two green-check workflow results under **Lab 02 - BJT DC Bias Tests**:

- Run **#1**, commit `2ba86d8` (`Lab 02: verified BJT DC bias dashboard and tests`), `main`, **success**, displayed duration **11 s**.
- Run **#2**, commit `9e72a94` (`docs: record verified push and CI access boundary`), `main`, **success**, displayed duration **12 s**.

The screenshot did not expose the complete run IDs, job-step logs, or permanent run URLs; do not invent them. Submission screenshot and the fresh 18-test Windows log were prepared **outside the Git repository** for Moodle evidence.

## 6. Supplement — 2026-11-16 local numerical hardening (separate from the 2026-11-10 browser/CI evidence)

The following is **new local evidence**, not a replacement for the historical Windows Chrome or GitHub Actions records above. The base of the independent work was pinned to GitHub `main` commit `47844638fd0fcbb3d1fccdbec139b54f4daabe12`, then changed on the local branch `lab02-correctness-lab03-v02-handoff`. The source hardening itself was first committed locally as `c9bd18b6c074266d7bea7dae55b48ee098efa88b`. It was **not pushed** via the read-only GitHub integration at this checkpoint.

| Verification | 2026-11-16 observed result | Evidence boundary |
|---|---|---|
| Original plus new `unittest` model/Flask tests | **26/26 PASS** using Python 3.12 and Flask 3.1.3 | Local run; not a fresh remote CI run |
| Independent exact-rational reference | **5,002 cases, 0 region mismatches and 0 numerical mismatches** | Deterministic bounded cases against a separate `fractions.Fraction` loop oracle, not a formal proof |
| New source/test content | Four original approved files (`dc_bias.py`, `app.py`, `tests/test_dc_bias.py`, `tests/test_web.py`) | No UI or dependency file modified by the source fix |
| Whitespace/source patch | `git diff --check` and explicit staged file check PASS | Does not substitute for hosted deployment checks |
| Independent code review | No blocking Important defect after a corrected active-region fixed-β gap | Source review and tests, not transistor measurements |

### Adversarial model cases and lessons

1. A high-impedance saturation candidate where $I_C/(\beta I_B)\approx1.955953$ must be `outside_model`; the former fixed $10^{-12}$ A comparison slack was wrong at that scale.
2. With `VCC=5 V`, `R1=1 Ω`, `R2=1000 Ω`, `RC=RE=10^8 Ω`, `β=10`, `VBE=0.7 V`, independently solved saturation gives $I_B\approx3.7900099143\times10^{-8}$ A, $I_C\approx5.0499504286\times10^{-9}$ A and $V_E\approx4.2950049571$ V. The algebraically reduced loop equations avoid harmful cancellation.
3. A paired deliberate change in $I_B$ and $I_C$ can retain $I_E=I_B+I_C$ but violate $I_C=\beta I_B$ by hundreds of times. The hardened active-region verifier now detects that corruption.
4. For extreme `R1=1 Ω`, `R2=10^12 Ω`, `VCC=24 V`, divider-node KCL roundoff reaches approximately **0.24% of a tiny branch current** because $V_{CC}\approx V_B$ in binary floating point. The ULP-scale test accepts one ULP and rejects 64 ULPs; precision limitations remain stated, not hidden behind a green check.
5. HTML and JSON format currents smaller than the fixed-three-decimal display step in scientific notation to avoid showing a nonzero value as `0.000` in the relevant unit.

**Still not verified for this local source version:** actual browser screenshots/interactive UX re-run, a new GitHub Actions job, hosted public calculator URL, physical transistor measurement, or Moodle submission. Retest these after the changes are applied to the final submission branch. Student-specific Reflection TXT is a separate owner-reviewed draft and is not presented as an already witnessed student exercise.

## 7. Lab 03 Workbench A — local build, 2026-11-16

This section records a new local build from the supplied snapshot. Examples and circuit assumptions follow the Lab 03 Instructor Draft and Engineering & Architecture Design v0.2. The circuit equations and engineering sources are in the README. Worked steps and the independent comparison are generated from the same validated inputs; the comparison uses exact rational node equations and checks values before display rounding. Fixed and single-supply Emitter require an active Q-point, including $V_C>V_B$. Divider retains the Lab 02 cutoff and saturation estimates and the original implicit-mode JSON contract.

| Lab 03 case | Circuit | Worked $I_C$ (mA) | Worked $V_{CE}$ (V) | Observed display in Chromium |
|---|---|---:|---:|---|
| A1 | Voltage Divider | 1.229858146 | 8.052155351 | 1.230 mA, 8.052 V |
| A2 | Fixed | 1.130000000 | 9.514000000 | 1.130 mA, 9.514 V |
| A3 | Emitter, $R_E=1$ kΩ | 1.026339691 | 8.705449591 | 1.026 mA, 8.705 V |
| A4 | Emitter, $R_E=2$ kΩ | 0.940099834 | 8.032778702 | 0.940 mA, 8.033 V |
| A5 | Fixed, $R_B=0$ | — | — | HTTP 422, field error in kΩ, previous output cleared |

The browser checked the unrounded A1–A4 response against these reference values and the draft tolerances of 0.01 mA and 0.02 V. Display, schematic and worked calculation updated together through Flask. Divider presented nine comparison quantities, including $V_{TH}$ and $R_{TH}$. Fixed and Emitter presented seven each.

- Python 3.12 with Flask 3.1.3 passed all 50 tests. The original independent Fraction oracle matched all 5,002 Divider cases within its tolerances. An additional 2,000 Fixed/Emitter cases matched an exact rational calculation, including the strict base–collector boundary. In the extreme Divider case with $R_1=R_C=1$ Ω and $R_2=R_E=10^{12}$ Ω, the two methods matched at $I_C\approx1.119\times10^{-8}$ mA.
- Chromium 151 against the loopback Flask server verified delayed-response handling during mode switches, clearing and recovery after a network failure, and standard form mode selection and calculation with JavaScript disabled. Keyboard focus reached the formula control and Enter opened it in all modes. The 720-pixel layout corresponding to a 1440-pixel desktop at 200% had no horizontal page overflow.
- Touch emulation at 390 × 844 verified that formula content scrolled while the schematic stayed in place for all three modes. A read-only reviewer inspected the desktop and mobile layouts. The open desktop panel leaves extra space below its schematic as the formulas continue down the other column.
- One run of 50 warm loopback POSTs per endpoint reported p95 of 3.67 ms for the original implicit-mode payload and 6.67 ms for the final explicit Emitter A4 payload, which includes worked steps and comparison. Each measurement covers a distinct workload.

This is local runtime evidence. Physical phones, transistor hardware, fresh remote CI, public deployment, and Moodle submission remain outside this run.

## 8. Lab 03 Workbench A with 14 tools — local release

The application validates form resistance in kΩ and calculates in SI. The server sends parsed form values, signed resistor drops, solution values and comparison rows. The schematic, voltage probe, sweep, inverse tool and report use those results. The circuit references remain the NPN one-supply configurations in the Lab 03 Instructor Draft and engineering design v0.2.

### Hand checks and boundaries

- **Fixed** grounds E. From the base loop, $I_B=(V_{CC}-V_{BE})/R_B$. At A2, $(12-0.70)\,\mathrm V/1000\,\mathrm{kΩ}=11.3\,\mathrm{µA}$ and $V_{CE}=12-1.13\times2.2=9.514\,\mathrm V$.
- **Emitter** adds the emitter term $I_ER_E$ in both loops. At A3 and A4, the denominators are respectively $1000+101\times1$ and $1000+101\times2$ kΩ. Increasing $R_E$ gives $I_C$ of 1.026339691 and 0.940099834 mA, and $V_{CE}$ of 8.705449591 and 8.032778702 V. For $I_C=1.00\,\mathrm{mA}$ with the A3 values, the inverse result is $R_E=130/101\,\mathrm{kΩ}$. Substitution in the forward model gives 1.00 mA and 8.50 V.
- **Divider** uses $V_{TH}=132/61\,\mathrm V$ and $R_{TH}=1100/61\,\mathrm{kΩ}$ at A1. The loaded base node independently satisfies $(V_{CC}-V_B)/R_1=V_B/R_2+I_B$. The two methods give $I_C=1.229858146\,\mathrm{mA}$ and $V_{CE}=8.052155351\,\mathrm V$. The exact boundary $V_{TH}=V_{BE}=0.825\,\mathrm V$ belongs to the cutoff estimate. A forward-active reading requires positive collector current representable by the solver.
- **Out-of-model and invalid** are distinct. A5 returns field-level validation for $R_B=0$. Fixed with $R_B=215\,\mathrm{kΩ}$ returns a failed forward-active trial condition $V_C-V_B\approx-0.262791\,\mathrm V$ and no Q-point. The probe uses stable calculated branch drops when matching a resistor terminal pair, including the regression case of approximately $1.13\times10^{-17}$ V across $R_C$.

### Runtime evidence

- The complete Python suite passed 64 tests. A deterministic independent Fraction audit covered 1,500 cases distributed evenly across all three topologies. The original 5,002-case Divider audit found zero numerical or region disagreements within its test tolerances. A separate inverse check returned accepted forward solutions for all 797 sampled in-range cases that had validated forward-active starting points.
- Actual Chromium against local Flask exercised all 14 tools, original and Thévenin diagrams, stale response handling, a deliberate network failure and recovery, keyboard navigation to a resistor input, and the original HTML submit path in all modes with JavaScript disabled.
- On simulated touch viewports 390 × 844 and 320 × 700, Fixed, Emitter and Divider each reached the end of the formula panel while keeping the reference diagram and the signed model probe visible. The main field still accepts typed textual forms that Python validates. The diagram and tools use the normalized server value, demonstrated by `1_2` on the form and `12` V on the schematic.
- The A1 sweep of $R_C$ from 5 to 12 kΩ sampled 19 forward-active points, two unavailable points, and 20 saturation estimates. The line chart breaks over the unavailable samples. The PDF generated by Chromium included the original circuit, hand and solver values for A4, the worked equations, and the record for the selected case.

The test matrix uses simulated touch and the stated educational model. Measurements stored by the program are user-entered and scoped to the current page. The release was tested locally with Flask 3.1.3 and Python 3.12. A physical phone, hardware experiment and remote release are outside this evidence.
