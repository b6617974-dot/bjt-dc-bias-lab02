# ENG29 2121 Lab 03 โปรแกรมไบอัสทรานซิสเตอร์ BJT

โปรแกรม Flask คำนวณจุดทำงาน DC ของทรานซิสเตอร์ NPN ใน **Fixed Bias**, **Emitter Bias** แบบแหล่งจ่ายเดียว และ **Voltage Divider Bias** หน้าจอ Workbench A แสดงวงจร ผลคำนวณ สมการแทนค่า และตารางเทียบกับค่าอ้างอิงจากสมการโหนด

## วิธีติดตั้งและเปิดโปรแกรม

ต้องการ Python 3.12 ขึ้นไป เปิด PowerShell ในโฟลเดอร์ที่มี `app.py` หลังแตก ZIP หรือรับซอร์สจาก GitHub

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m flask --app app run --host 127.0.0.1 --port 8780
```

เปิด [โปรแกรมไบอัสทรานซิสเตอร์ BJT](http://127.0.0.1:8780/) ในเบราว์เซอร์บนเครื่องที่รัน Flask รักษาหน้าต่าง PowerShell ไว้ขณะใช้งาน แล้วกด `Ctrl+C` เมื่อต้องการหยุดเซิร์ฟเวอร์ บน macOS หรือ Linux ใช้ `.venv/bin/python` แทน `.\.venv\Scripts\python.exe`

## วิธีใช้งานและทำการทดลอง

1. เลือกวงจรหรือชุดโจทย์ A1–A5 ซึ่งอิงใบงานฉบับร่าง กรอกตัวต้านทานเป็น kΩ แรงดันเป็น V และ β เป็นจำนวนไร้หน่วย
2. กด **คำนวณ** แล้วเปิด **ดูสูตรและผลเทียบทั้งหมด** เพื่อดูสมการ หน่วย ผลโปรแกรม และผลอ้างอิง แผงสูตรมีรูปวงจรประกอบ บนมือถือให้เลื่อนในกรอบสูตร
3. สำหรับ A3 → A4 เลือก Emitter Bias คง V<sub>CC</sub> = 12 V, R<sub>B</sub> = 1,000 kΩ, R<sub>C</sub> = 2.2 kΩ, β = 100 และ V<sub>BE</sub> = 0.70 V เปลี่ยนเฉพาะ R<sub>E</sub> จาก 1 เป็น 2 kΩ แล้วกดคำนวณอีกครั้ง ค่า I<sub>C</sub> ตามแบบจำลองลดจาก 1.026 เป็น 0.940 mA
4. เครื่องมือบนวงจรมีโพรบแรงดันและการเน้นเส้นทางตามสมการ ส่วนแผงทดลองมีการเทียบกรณี กวาดค่าพารามิเตอร์ และหา R<sub>E</sub> จากเป้าหมาย I<sub>C</sub> ค่าที่กรอกว่ามาจากการวัดและกรณีอ้างอิงอยู่ในหน้าที่เปิดอยู่จนกว่าจะโหลดหน้าใหม่ รายงานเลือกพิมพ์เป็น PDF จากเบราว์เซอร์ได้

เมื่อปิด JavaScript ให้เลือกวงจร กด **Apply mode** แล้วกรอกค่าและกด **Calculate** ฟอร์มจะส่งไปยัง Flask โดยตรง

## สมการและเส้นทางข้อมูล

### Fixed Bias

ขา E ต่อกราวด์โดยตรง

```math
V_E=0,\qquad I_B=\frac{V_{CC}-V_{BE}}{R_B}
```

### Emitter Bias

สมการรอบฐานรวมแรงดันตกคร่อม R<sub>E</sub>

```math
I_B=\frac{V_{CC}-V_{BE}}{R_B+(\beta+1)R_E}
```

### Voltage Divider Bias

แทนเครือข่าย R<sub>1</sub> และ R<sub>2</sub> ด้านฐานด้วยวงจรเทียบเท่า Thévenin

```math
\begin{aligned}
V_{TH}&=\frac{V_{CC}R_2}{R_1+R_2},\qquad
R_{TH}=\frac{R_1R_2}{R_1+R_2} \\
I_B&=\frac{V_{TH}-V_{BE}}{R_{TH}+(\beta+1)R_E}
\end{aligned}
```

### จุดทำงานในเขต Forward Active

ใช้ความสัมพันธ์ของกระแสและแรงดันต่อไปนี้ สำหรับวงจรที่มี R<sub>E</sub> ให้ใช้ V<sub>E</sub> = I<sub>E</sub>R<sub>E</sub> ส่วน Fixed Bias ใช้ V<sub>E</sub> = 0

```math
\begin{aligned}
I_C&=\beta I_B, & I_E&=I_B+I_C \\
V_B&=V_E+V_{BE}, & V_C&=V_{CC}-I_CR_C \\
V_{CE}&=V_C-V_E
\end{aligned}
```

แบบจำลองตรวจว่า I<sub>B</sub> และ I<sub>C</sub> เป็นบวก, V<sub>C</sub> > V<sub>B</sub> และ V<sub>CE</sub> > 0.20 V ส่วน Cutoff และ Saturation ของ Divider เป็นค่าประมาณตามแบบจำลองของใบงาน

### การแปลงหน่วยและเลือกโมเดล

ฟอร์มและ API รับฟิลด์ `re` เป็น kΩ `parse_inputs` ใน `app.py` แปลงเป็น `re_ohm` ด้วยการคูณ 1,000 แล้วให้ `calculate_by_mode` ใน `dc_bias.py` เลือก `calculate_emitter_bias` เมื่อ `mode=emitter` หน้าเว็บอัปเดตจากผลคำนวณรอบล่าสุด รายละเอียดการทวนสมการและกรณีทดสอบอยู่ใน [เอกสารตรวจสอบ](docs/validation.md)

## วิธีรันชุดทดสอบ

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

ชุดทดสอบครอบคลุมผลทั้งสามโหมด การตรวจฟอร์มและ API แรงดันตกคร่อม จุดขอบเขตการทำงาน และการคำนวณทดลองย้อนกลับ โปรแกรมใช้ β และ VBE คงที่ ผลโพรบเป็นค่าจากแบบจำลอง ตัวเลขที่กรอกในช่องค่าที่วัดต้องมาจากการวัดของผู้ใช้

## บทบาทของ AI และนักศึกษา

Codex ช่วยวางแผน เขียนและตรวจโค้ด Flask/Python สร้างหน้าจอและเครื่องมือ ทวนสมการจากค่าอ้างอิงอิสระ และรันชุดทดสอบกับเบราว์เซอร์จริง ผล A1–A5 ระบุผู้รันและวิธีตรวจในเอกสาร Word นักศึกษาตรวจรับงานและบันทึกกรณีที่ตนทวนด้วยตัวเองในเอกสารเดียวกัน

ก่อน Commit ให้ตรวจ `git diff` และ `git diff --staged` เลือกเฉพาะไฟล์ของโครงการ เก็บ `.venv`, `.env`, credentials และภาพหลักฐานไว้นอก Git หลักฐานส่งงานอ้างถึง Commit SHA ของรุ่นที่ใช้ตรวจ

แหล่งอ้างอิงสมการ [Georgia Tech ECE 3050 The BJT Bias Equation](https://leachlegacy.ece.gatech.edu/ece3050/notes/bjt/bjtbias.pdf#page=1)
