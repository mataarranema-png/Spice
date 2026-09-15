# 🐣 VBA Academy — เรียน VBA แบบ interactive จาก 0 ถึงมือโปร

เว็บสอน VBA ภาษาไทย ที่มี **Excel จำลอง** ให้ลองเขียนโค้ดจริง ๆ ในเบราว์เซอร์
พร้อม **เสียงบรรยายภาษาไทย** และ UI น่ารักแบบเกม

## มีอะไรบ้าง

- **32 บทเรียน 6 ด่าน** — ตั้งแต่ Sub แรก จนถึง Dashboard ยอดขายระดับใช้งานจริง
- **VBA Interpreter เขียนเอง** — รันโค้ด VBA จริงในเบราว์เซอร์ ไม่ต้องติดตั้ง Excel
  - Sub/Function, Dim, If/ElseIf, Select Case, For/For Each/Do/While, With, อาร์เรย์, ฟังก์ชันเรียกซ้ำ
  - Object model: `Range`, `Cells`, `Offset`, `End(xlUp)`, `Font`, `Interior`, `Borders`, `Worksheets`, `WorksheetFunction`
  - ฟังก์ชันในตัวกว่า 60 ตัว และตัวคำนวณสูตร Excel (SUM, AVERAGE, IF, COUNTIF, SUMIF, ...)
  - ข้อความ error เป็นภาษาไทยพร้อมเลขบรรทัด และตัวตัดวงจร Infinite Loop
- **ตาราง Excel จำลอง** — แสดงค่า สูตร สี ตัวหนา รูปแบบตัวเลข หลายชีต พร้อมไฮไลต์เซลล์ที่เพิ่งเปลี่ยน
- **ตรวจภารกิจอัตโนมัติ** — แต่ละบทมีเช็กลิสต์ที่ตรวจผลจริงในชีต ไม่ใช่แค่เทียบข้อความ
- **เสียงสอนภาษาไทย** ผ่าน Web Speech API (ปรับความเร็ว/ปิดได้) + เอฟเฟกต์เสียงจาก WebAudio
- **ระบบ XP, เหรียญตรา, บันทึกความคืบหน้า** ลง localStorage
- โหมด **ดูทีละบรรทัด** เพื่อดูโค้ดทำงานแบบช้า ๆ, ปุ่มคำใบ้, ปุ่มดูเฉลย

## รันในเครื่อง

```bash
npm install
npm run dev
```

## ทดสอบ

```bash
# ทดสอบ interpreter (29 เคส)
npx esbuild tests/engine.test.ts --bundle --platform=node --format=esm --outfile=/tmp/t.mjs && node /tmp/t.mjs

# ตรวจว่าเฉลยทุกบทผ่านภารกิจจริง (32 บท)
npx esbuild tests/lessons.test.ts --bundle --platform=node --format=esm --outfile=/tmp/l.mjs && node /tmp/l.mjs
```

## โครงสร้าง

```
src/vba/        lexer → parser → interpreter + Excel object model
src/content/    หลักสูตร 32 บท (เนื้อหา, บทพากย์, โจทย์, เฉลย, ตัวตรวจ)
src/lib/        ตัวรันบทเรียน, เสียงพูด, ความคืบหน้า, syntax highlight
src/components/ ตาราง Excel, ตัวแก้ไขโค้ด, แผงบทเรียน, กล่องข้อความ
```

Deploy: Vercel (Vite static build)

## ทดสอบในเบราว์เซอร์ (ไม่บังคับ)

```bash
npm install -D playwright   # ติดตั้งเฉพาะตอนอยากรัน e2e
npx vite preview --port 4173 &
node tests/browser-check.mjs
```

## Deploy

ดูวิธีที่ `../vercel-deploy/README.md` — แนะนำให้เชื่อม repo กับ Vercel โดยตั้ง
Root Directory เป็น `vba-academy` แล้วปล่อยให้ auto-detect เป็น Vite
