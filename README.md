# ENG29 2121 Lab 03–04 · BJT Workbench

ใช้ **DC Bias** สำหรับ Fixed, Emitter และ Voltage Divider พร้อมสมการคำนวณมือ ใช้ **AC** และ **Transient** เมื่อต่อวงจร NPN Common-Emitter แบบแบ่งแรงดันและไม่มี emitter bypass capacitor การจำลองใช้ Flask เรียก ngspice และแสดงชื่อโมเดล หน่วย และรหัสรันกำกับข้อมูลทุกชุด

- **เปิดจากเบราว์เซอร์** ใช้ [BJT Workbench บน Vercel](https://bjt-workbench-lab04.vercel.app/spice) เซิร์ฟเวอร์จัดการ Flask และ ngspice ให้ รุ่นออนไลน์ใช้โมเดลสาธิต OpenJellyBean 2N3904_OJ
- **เปิดบนเครื่องเพื่อใช้ Starter Kit ของผู้สอน** ทำตามขั้นตอนด้านล่างแล้วเปิด [BJT Workbench ในเครื่อง](http://127.0.0.1:8780/spice) รุ่นนี้ให้สร้างและตรวจโปรไฟล์ของชุดที่ได้รับมา

## เตรียม ngspice และโมเดล

### เปิดครั้งแรกบน Windows

จากโฟลเดอร์ที่มี `app.py` สร้าง Python environment และเปิด Flask ได้ตั้งแต่ก่อนติดตั้ง ngspice

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m flask --app app run --host 127.0.0.1 --port 8780
```

1. เปิด [/spice](http://127.0.0.1:8780/spice) แล้วกาง **ตั้งค่า ngspice** ถ้ายังไม่มีเครื่องมือ ให้ดาวน์โหลดแพ็กเกจ Windows 64-bit แบบ `.7z` จากผู้พัฒนาและแตกไฟล์ด้วย 7-Zip ลงโฟลเดอร์ที่เขียนได้ เช่น `C:/tools` [ดาวน์โหลด ngspice](https://ngspice.sourceforge.io/download.html)
2. สำหรับสาธิต ให้ใช้ `deploy/profile.json` ที่มีอยู่ หรือฝึกสร้างโปรไฟล์โดยเลือก `deploy/2n3904-oj.lib` ในแผงตั้งค่า ใส่ชื่อแสดงและแหล่งที่มา แล้วดาวน์โหลด `profile.json` เก็บข้างสำเนาไฟล์โมเดลนอก Git
3. หยุด Flask ด้วย `Ctrl+C` ตั้งค่าด้านล่างใน PowerShell เดิม แล้วเปิด Flask ใหม่ แทนพาธ executable ด้วยตำแหน่งที่แตกไฟล์ ถ้า `ngspice -v` ใช้ได้จาก `PATH` อยู่แล้ว ให้ข้ามการตั้ง `LAB04_NGSPICE` และเรียก `ngspice -v` โดยตรง
4. กลับไปที่ **ตั้งค่า ngspice** แล้วกด **ทดสอบความพร้อม** ตรวจว่าขั้นเวอร์ชัน วงจรแบ่งแรงดัน 5 V และ DC, AC, Transient ขึ้น `PASS`

```powershell
$env:LAB04_SPICE_PROFILE = (Resolve-Path 'deploy/profile.json').Path
$env:LAB04_NGSPICE = 'C:/tools/Spice64/bin/ngspice_con.exe'
& $env:LAB04_NGSPICE -v
.\.venv\Scripts\python.exe -m flask --app app run --host 127.0.0.1 --port 8780
```

ถ้าสร้างโปรไฟล์เอง ให้แทนพาธ `deploy/profile.json` ด้วยไฟล์ที่ดาวน์โหลดไว้ บน macOS/Linux ให้ติดตั้งด้วย Homebrew หรือตัวจัดการแพ็กเกจของระบบ ทดสอบ `ngspice -v` ตั้ง `export LAB04_SPICE_PROFILE="$PWD/deploy/profile.json"` และใช้ `.venv/bin/python` ในคำสั่งติดตั้งและรัน

### เปลี่ยนเป็นโมเดลของผู้สอน

- เมื่อได้ **โมเดลที่ผู้สอนยืนยัน** ให้เปิดแผงตั้งค่า เลือกไฟล์โมเดล ตั้งประเภทชุดผู้สอน กรอกแหล่งที่มา และเลือกชื่อ declaration เว็บอ่านไฟล์ในเบราว์เซอร์เพื่อสร้าง `profile.json` และ SHA-256 จัดเก็บโปรไฟล์ข้างไฟล์โมเดล ตั้ง `LAB04_SPICE_PROFILE` ไปยังโปรไฟล์นั้น เปิด Flask ใหม่ และกดตรวจอีกครั้ง
- สำหรับ `.SUBCKT` สามขา ให้กรอก B/C/E ตามลำดับจริงจากเอกสารของโมเดล สำหรับ `.cir` หรือ Starter Adapter ที่มีวงจรทั้งชุด ให้ทวน topology, หน่วย, โหนดและเวกเตอร์ก่อนเชื่อม ทดสอบทั้งสาม analysis ด้วยชุดนั้นก่อนใช้อ้างอิงส่งตรวจ
- ดู [ตารางตรวจ Starter Kit จากใบงาน §04](docs/validation.md#starter-kit) เพื่อเทียบสิ่งที่ได้รับจากผู้สอนกับวงจรและผลรุ่นสาธิต
- ตั้ง `LAB04_EVIDENCE_DIR` เป็นไดเรกทอรีภายนอก Git เฉพาะช่วงเก็บหลักฐาน เพื่อเก็บ Netlist, raw และ log แยกตามรหัสรัน การคำนวณตามปกติใช้ไดเรกทอรีชั่วคราว
- AC ใช้ small-signal excitation ของตัวเอง ส่วนความถี่และแอมพลิจูดของ SIN ใช้กับ Transient ช่วงความถี่สัญญาณสำหรับ Transient คือ 1 Hz–10 kHz เพื่อจำกัดขนาดข้อมูลตามช่วงเวลาและ time step
- ถ้าติดตั้ง ngspice ไม่สำเร็จ ให้ใช้ [รุ่นออนไลน์](https://bjt-workbench-lab04.vercel.app/spice) สำหรับการสาธิต หรือใช้โหมดคำนวณมือ DC Bias ขณะตรวจตำแหน่ง executable หากชื่อโมเดลหรือ SHA-256 ไม่ตรง ให้ทวนไฟล์กับต้นทางก่อนสร้างโปรไฟล์ใหม่
- ตรวจซ้ำจากโฟลเดอร์โครงการด้วย `.\.venv\Scripts\python.exe -m unittest discover -s tests -v` บน Windows หรือ `.venv/bin/python -m unittest discover -s tests -v` บน macOS/Linux ตั้งค่า ngspice และโมเดลไว้ก่อนเพื่อให้การทดสอบที่เรียก solver จริงทำงานครบ เทียบค่ากับ [บันทึกการตรวจ](docs/validation.md)

### โมเดลสาธิตและการเผยแพร่

ชุดสาธิตใช้ OpenJellyBean 0.6.0 โมเดล `2N3904_OJ` ภายใต้สัญญาอนุญาต MIT ไฟล์พร้อมประกาศลิขสิทธิ์อยู่ใน `deploy/2n3904-oj.lib` โดยมี SHA-256 `c543201058bd7fd0a976fe1ca6d08baa2dd2bf3d2841745cd641861e2ffaf8c2` ผลการตรวจด้วยชุดผู้สอนจะมีเมื่อได้รับชุดจริง [ต้นทาง OpenJellyBean](https://github.com/xdylanm/openjellybean/tree/0d0d9b659b202368dc419f8276bacb1e39694915)

`Dockerfile.vercel` สร้าง ngspice 47 และรันการตรวจ 5 V, DC, AC, Transient ระหว่างสร้างรุ่น ใช้ Container Runtime และตั้ง `PORT=8080` ผลตรวจในแผงของรุ่นออนไลน์ผูกกับโมเดลที่ตรวจตอนสร้างรุ่น ส่วนเบราว์เซอร์เรียก API เพื่อจำลองแต่ละรอบ [คู่มือ Container Runtime](https://vercel.com/docs/functions/runtimes/container)

## ใช้ BJT Workbench เหมือนเป็นการทดลองเดียว

1. เปิด `/spice` ในแท็บ **DC Bias** เลือก Fixed, Emitter หรือ Voltage Divider แล้วดูกราฟจุดทำงานและสมการแทนค่า สมมติฐาน β และ VBE อยู่ในแผงคำนวณมือ ผลของ Voltage Divider จาก ngspice แสดงพร้อมชื่อโมเดลและ V<sub>CE</sub>, I<sub>C</sub> สำหรับเทียบกับผลคำนวณมือ
2. ที่ Voltage Divider กด **เทียบกับค่าฐาน** แล้วแก้ค่า เช่น RE 1 → 2 kΩ ใช้ **AC** และ **Transient** ต่อจากฟอร์มเดิม ระบบรันค่าฐานของแท็บนั้นตามต้องการ ตรวจรุ่นโมเดล และวาดเส้นทับบนช่วงแกนของรอบปัจจุบัน
3. เปิด **วัดจากกราฟ** เพื่อปัก A แล้วเลื่อน B อ่านส่วนต่าง ซูมช่วง A–B หรือกดวัดอัตโนมัติ AC ใช้ Gain ใกล้ 1 kHz เป็นระดับอ้างอิง −3 dB และแจ้งเมื่อช่วง sweep ไม่พบจุดตัด Transient วัดคาบ Vin จากจุดข้ามศูนย์ขาขึ้นสองจุดท้ายที่ข้อมูลคร่อม
4. เปิด **ออกแบบให้เข้าเป้า** ใส่ Gain ขั้นต่ำที่ 1 kHz และเพดาน IC โปรแกรมลองได้ถึงเก้าคู่ใกล้ค่า RC/RE ปัจจุบัน โดยใช้ผล DC และ AC ของ ngspice และแสดงได้ถึงสามทางเลือกพร้อมรหัสรัน ผลครอบคลุมชุดค่าที่ระบบลองจริง
5. เปิด **เก็บผลและเปิดกลับมาทดลอง** เพื่อบันทึกชื่อ โน้ต อินพุต แท็บ และจุดอ่านในเบราว์เซอร์เดียวกัน การเปิดรอบที่เก็บจะคำนวณใหม่และได้รหัสรันใหม่ เลือกดาวน์โหลด CSV, หลักฐาน JSON, กราฟ SVG หรือพิมพ์ PDF ได้ตามผลที่มี

## Lab 03 · โปรแกรมไบอัสทรานซิสเตอร์ BJT

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
