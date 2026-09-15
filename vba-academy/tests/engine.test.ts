import { Interpreter } from '../src/vba/interpreter';
import { Workbook, computeDisplayValue } from '../src/vba/workbook';

let pass = 0;
let fail = 0;

async function run(code: string) {
  const wb = new Workbook(['Sheet1', 'Sheet2']);
  const out: string[] = [];
  const interp = new Interpreter(code, wb, {
    onPrint: (t) => out.push(t),
    onMsgBox: async (t) => { out.push(`MSG:${t}`); },
    onInputBox: async (_p, _t, d) => d || '42',
  });
  const result = await interp.run();
  return { wb, out, result };
}

async function check(name: string, code: string, verify: (ctx: { wb: Workbook; out: string[]; result: any }) => boolean | string) {
  try {
    const ctx = await run(code);
    if (!ctx.result.ok) {
      console.log(`❌ ${name}: runtime error @${ctx.result.error.line}: ${ctx.result.error.message}`);
      fail++;
      return;
    }
    const v = verify(ctx);
    if (v === true) { pass++; console.log(`✅ ${name}`); }
    else { fail++; console.log(`❌ ${name}: ${v === false ? 'assertion failed' : v}`); }
  } catch (e) {
    fail++;
    console.log(`❌ ${name}: threw ${(e as Error).message}`);
  }
}

async function checkError(name: string, code: string, expectPart: string) {
  try {
    const ctx = await run(code);
    if (ctx.result.ok) { fail++; console.log(`❌ ${name}: คาดว่าจะ error แต่ผ่านเฉย`); return; }
    if (!ctx.result.error.message.includes(expectPart)) {
      fail++; console.log(`❌ ${name}: ข้อความ error ไม่ตรง -> ${ctx.result.error.message}`); return;
    }
    pass++; console.log(`✅ ${name} (error @${ctx.result.error.line}: ${ctx.result.error.message})`);
  } catch (e) {
    fail++; console.log(`❌ ${name}: threw ${(e as Error).message}`);
  }
}

const val = (wb: Workbook, addr: string) => {
  const m = /^([A-Z]+)(\d+)$/.exec(addr)!;
  let col = 0;
  for (const ch of m[1]) col = col * 26 + (ch.charCodeAt(0) - 64);
  return computeDisplayValue(wb.sheets[0], Number(m[2]), col);
};

async function main() {
  await check('เขียนค่าลงเซลล์', `
Sub Test()
  Range("A1").Value = "สวัสดี"
  Cells(2, 1).Value = 42
End Sub`, ({ wb }) => val(wb, 'A1') === 'สวัสดี' && val(wb, 'A2') === 42);

  await check('ตัวแปรและเลขคณิต', `
Sub Test()
  Dim x As Integer, y As Double
  x = 7
  y = x * 2 + 1
  Range("B1").Value = y
  Range("B2").Value = 10 \\ 3
  Range("B3").Value = 10 Mod 3
  Range("B4").Value = 2 ^ 10
End Sub`, ({ wb }) => val(wb, 'B1') === 15 && val(wb, 'B2') === 3 && val(wb, 'B3') === 1 && val(wb, 'B4') === 1024);

  await check('For loop', `
Sub Test()
  Dim i As Integer
  For i = 1 To 5
    Cells(i, 3).Value = i * i
  Next i
End Sub`, ({ wb }) => val(wb, 'C1') === 1 && val(wb, 'C5') === 25);

  await check('For Step ย้อนกลับ', `
Sub Test()
  Dim total As Long, i As Integer
  For i = 10 To 1 Step -2
    total = total + i
  Next i
  Range("D1").Value = total
End Sub`, ({ wb }) => val(wb, 'D1') === 30);

  await check('If / ElseIf / Else', `
Sub Test()
  Dim score As Integer
  score = 75
  If score >= 80 Then
    Range("E1").Value = "A"
  ElseIf score >= 70 Then
    Range("E1").Value = "B"
  Else
    Range("E1").Value = "C"
  End If
  If score > 0 Then Range("E2").Value = "บวก"
End Sub`, ({ wb }) => val(wb, 'E1') === 'B' && val(wb, 'E2') === 'บวก');

  await check('Do While + Exit Do', `
Sub Test()
  Dim n As Integer
  n = 0
  Do While n < 100
    n = n + 7
    If n > 30 Then Exit Do
  Loop
  Range("F1").Value = n
End Sub`, ({ wb }) => val(wb, 'F1') === 35);

  await check('Do Until ... Loop', `
Sub Test()
  Dim n As Integer
  n = 1
  Do
    n = n * 2
  Loop Until n >= 64
  Range("F2").Value = n
End Sub`, ({ wb }) => val(wb, 'F2') === 64);

  await check('Select Case', `
Sub Test()
  Dim g As Integer
  g = 85
  Select Case g
    Case Is >= 90
      Range("G1").Value = "เยี่ยม"
    Case 80 To 89
      Range("G1").Value = "ดี"
    Case Else
      Range("G1").Value = "สู้ต่อ"
  End Select
End Sub`, ({ wb }) => val(wb, 'G1') === 'ดี');

  await check('For Each กับ Range', `
Sub Test()
  Dim c As Range
  Range("A10").Value = 1
  Range("A11").Value = 2
  Range("A12").Value = 3
  Dim s As Long
  For Each c In Range("A10:A12")
    s = s + c.Value
  Next c
  Range("B10").Value = s
End Sub`, ({ wb }) => val(wb, 'B10') === 6);

  await check('With block + Font/Interior', `
Sub Test()
  With Range("H1")
    .Value = "หัวตาราง"
    .Font.Bold = True
    .Font.Size = 14
    .Interior.Color = RGB(255, 200, 0)
  End With
End Sub`, ({ wb }) => {
    const cell = wb.sheets[0].peek(1, 8)!;
    return cell.style.bold === true && cell.style.fontSize === 14 && cell.style.fill === '#ffc800';
  });

  await check('Function ที่ผู้ใช้เขียนเอง', `
Function AddTwo(a As Double, b As Double) As Double
  AddTwo = a + b
End Function

Sub Test()
  Range("I1").Value = AddTwo(3, 4)
End Sub`, ({ wb }) => val(wb, 'I1') === 7);

  await check('เรียก Sub ย่อยแบบไม่มีวงเล็บ', `
Sub Helper(target As String, v As Integer)
  Range(target).Value = v * 3
End Sub

Sub Test()
  Helper "J1", 5
  Call Helper("J2", 6)
End Sub`, ({ wb }) => val(wb, 'J1') === 15 && val(wb, 'J2') === 18);

  await check('สตริงฟังก์ชัน', `
Sub Test()
  Range("K1").Value = UCase("abc") & "-" & Left("Thailand", 4) & "-" & Len("VBA")
  Range("K2").Value = Trim("  hi  ") & Mid("abcdef", 2, 3) & Right("12345", 2)
  Range("K3").Value = InStr("hello world", "world")
  Range("K4").Value = Replace("a-b-c", "-", "+")
End Sub`, ({ wb }) =>
    val(wb, 'K1') === 'ABC-Thai-3' && val(wb, 'K2') === 'hibcd45' && val(wb, 'K3') === 7 && val(wb, 'K4') === 'a+b+c');

  await check('อาร์เรย์ + UBound', `
Sub Test()
  Dim arr(1 To 3) As Integer
  arr(1) = 10
  arr(2) = 20
  arr(3) = 30
  Dim i As Integer, t As Integer
  For i = LBound(arr) To UBound(arr)
    t = t + arr(i)
  Next i
  Range("L1").Value = t
  Dim names As Variant
  names = Array("ann", "bee", "cat")
  Range("L2").Value = names(1) & "/" & UBound(names)
End Sub`, ({ wb }) => val(wb, 'L1') === 60 && val(wb, 'L2') === 'bee/2');

  await check('Split และ Join', `
Sub Test()
  Dim parts As Variant
  parts = Split("a,b,c", ",")
  Range("M1").Value = Join(parts, "-") & UBound(parts)
End Sub`, ({ wb }) => val(wb, 'M1') === 'a-b-c2');

  await check('WorksheetFunction.Sum บนช่วง', `
Sub Test()
  Range("N1").Value = 5
  Range("N2").Value = 15
  Range("N3").Value = 30
  Range("O1").Value = Application.WorksheetFunction.Sum(Range("N1:N3"))
  Range("O2").Value = WorksheetFunction.Max(Range("N1:N3"))
End Sub`, ({ wb }) => val(wb, 'O1') === 50 && val(wb, 'O2') === 30);

  await check('สูตร Excel ในเซลล์', `
Sub Test()
  Range("P1").Value = 10
  Range("P2").Value = 20
  Range("P3").Formula = "=SUM(P1:P2)*2"
End Sub`, ({ wb }) => val(wb, 'P3') === 60);

  await check('Cells.Offset และ End(xlUp)', `
Sub Test()
  Range("Q1").Value = "a"
  Range("Q2").Value = "b"
  Range("Q3").Value = "c"
  Range("R1").Value = Cells(1, 17).Offset(2, 0).Value
  Range("R2").Value = Cells(200, 17).End(xlUp).Row
End Sub`, ({ wb }) => val(wb, 'R1') === 'c' && val(wb, 'R2') === 3);

  await check('MsgBox และ Debug.Print', `
Sub Test()
  MsgBox "สวัสดีชาว VBA"
  Debug.Print "ค่า = " & 10 * 2
End Sub`, ({ out }) => out.includes('MSG:สวัสดีชาว VBA') && out.includes('ค่า = 20'));

  await check('Worksheets("Sheet2")', `
Sub Test()
  Worksheets("Sheet2").Range("A1").Value = "ชีตสอง"
  Range("S1").Value = Worksheets("Sheet2").Range("A1").Value
  Range("S2").Value = Worksheets.Count
End Sub`, ({ wb }) => wb.sheets[1].getValue(1, 1) === 'ชีตสอง' && val(wb, 'S2') === 2);

  await check('UsedRange + Rows.Count', `
Sub Test()
  Range("A20").Value = 1
  Range("C22").Value = 2
  Range("T1").Value = ActiveSheet.UsedRange.Rows.Count
End Sub`, ({ wb }) => val(wb, 'T1') === 3);

  await checkError('ตรวจจับ infinite loop', `
Sub Test()
  Do While True
  Loop
End Sub`, 'Infinite Loop');

  await check('ฟังก์ชันเรียกซ้ำ (recursive)', `
Function Fact(n As Integer) As Double
  If n <= 1 Then
    Fact = 1
  Else
    Fact = n * Fact(n - 1)
  End If
End Function

Sub Test()
  Range("U1").Value = Fact(6)
End Sub`, ({ wb }) => val(wb, 'U1') === 720);

  await check('คอมเมนต์และบรรทัดต่อ', `
Sub Test()
  ' นี่คือคอมเมนต์
  Dim total As Long
  total = 1 + _
          2 + 3
  Range("V1").Value = total ' ท้ายบรรทัด
End Sub`, ({ wb }) => val(wb, 'V1') === 6);

  await check('IIf, Format, IsNumeric', `
Sub Test()
  Range("W1").Value = IIf(5 > 3, "ใช่", "ไม่")
  Range("W2").Value = Format(0.4567, "0.00")
  Range("W3").Value = IsNumeric("123")
  Range("W4").Value = Format(1234567, "#,##0")
End Sub`, ({ wb }) => val(wb, 'W1') === 'ใช่' && val(wb, 'W2') === '0.46' && val(wb, 'W3') === true && val(wb, 'W4') === '1,234,567');

  await check('InputBox', `
Sub Test()
  Dim n As String
  n = InputBox("ชื่ออะไร", "ถาม", "แมว")
  Range("X1").Value = n
End Sub`, ({ wb }) => val(wb, 'X1') === 'แมว');

  await check('ClearContents', `
Sub Test()
  Range("Y1").Value = 99
  Range("Y1:Y3").ClearContents
  Range("Y5").Value = IsEmpty(Range("Y1").Value)
End Sub`, ({ wb }) => val(wb, 'Y5') === true);

  await checkError('ข้อความ error ภาษาไทยเมื่อหารศูนย์', `
Sub Test()
  Dim a As Integer
  a = 5 / 0
End Sub`, 'หารด้วยศูนย์');

  await checkError('บอกบรรทัดที่ผิดพลาด', `
Sub Test()
  Range("A1").Value = 1
  Range("A2").Valuee = 2
End Sub`, 'Valuee');

  console.log(`\n📊 ผ่าน ${pass} / ล้มเหลว ${fail}`);
}

main();
