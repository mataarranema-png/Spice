const KEYWORDS = [
  'Sub', 'End', 'Function', 'Dim', 'As', 'Set', 'Const', 'If', 'Then', 'ElseIf', 'Else',
  'For', 'To', 'Step', 'Next', 'Each', 'In', 'Do', 'Loop', 'While', 'Until', 'Wend',
  'Select', 'Case', 'Is', 'With', 'Exit', 'Call', 'And', 'Or', 'Not', 'Xor', 'Mod',
  'True', 'False', 'Nothing', 'Empty', 'ReDim', 'Preserve', 'Option', 'Explicit',
  'Public', 'Private', 'On', 'Error', 'Resume', 'ByVal', 'ByRef', 'Optional', 'New',
  'Integer', 'Long', 'Double', 'Single', 'String', 'Boolean', 'Variant', 'Object', 'Date',
];

const OBJECTS = [
  'Range', 'Cells', 'Worksheets', 'Sheets', 'ActiveSheet', 'ThisWorkbook', 'ActiveWorkbook',
  'Application', 'WorksheetFunction', 'Debug', 'Selection', 'Rows', 'Columns', 'UsedRange',
  'Value', 'Formula', 'Font', 'Interior', 'Borders', 'Bold', 'Italic', 'Color', 'Size',
  'Offset', 'Resize', 'Count', 'Row', 'Column', 'Address', 'NumberFormat', 'ScreenUpdating',
];

const FUNCTIONS = [
  'MsgBox', 'InputBox', 'Len', 'Left', 'Right', 'Mid', 'UCase', 'LCase', 'Trim', 'InStr',
  'Replace', 'Split', 'Join', 'CStr', 'CInt', 'CLng', 'CDbl', 'Val', 'Abs', 'Int', 'Round',
  'Sqr', 'Rnd', 'Now', 'Date', 'Format', 'IsNumeric', 'IsEmpty', 'Array', 'UBound', 'LBound',
  'Chr', 'Asc', 'RGB', 'IIf', 'TypeName', 'StrReverse', 'Print', 'Sum', 'Average', 'Max', 'Min',
];

const KW_SET = new Set(KEYWORDS.map((k) => k.toLowerCase()));
const OBJ_SET = new Set(OBJECTS.map((k) => k.toLowerCase()));
const FN_SET = new Set(FUNCTIONS.map((k) => k.toLowerCase()));

function escapeHtml(s: string) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/** แปลงโค้ด VBA เป็น HTML ที่ไฮไลต์แล้ว (escape เรียบร้อย) */
export function highlightVba(code: string): string {
  return code
    .split('\n')
    .map((line) => highlightLine(line))
    .join('\n');
}

function highlightLine(line: string): string {
  let out = '';
  let i = 0;

  while (i < line.length) {
    const ch = line[i];

    if (ch === "'") {
      out += `<span class="tok-com">${escapeHtml(line.slice(i))}</span>`;
      return out;
    }

    if (ch === '"') {
      let j = i + 1;
      while (j < line.length) {
        if (line[j] === '"') {
          if (line[j + 1] === '"') j += 2;
          else {
            j++;
            break;
          }
        } else j++;
      }
      out += `<span class="tok-str">${escapeHtml(line.slice(i, j))}</span>`;
      i = j;
      continue;
    }

    if (/[0-9]/.test(ch) && !/[A-Za-z_฀-๿]/.test(line[i - 1] ?? ' ')) {
      let j = i;
      while (j < line.length && /[0-9.]/.test(line[j])) j++;
      out += `<span class="tok-num">${escapeHtml(line.slice(i, j))}</span>`;
      i = j;
      continue;
    }

    if (/[A-Za-z_฀-๿]/.test(ch)) {
      let j = i;
      while (j < line.length && /[A-Za-z0-9_฀-๿]/.test(line[j])) j++;
      const word = line.slice(i, j);
      const lower = word.toLowerCase();
      const safe = escapeHtml(word);
      if (KW_SET.has(lower)) out += `<span class="tok-kw">${safe}</span>`;
      else if (OBJ_SET.has(lower)) out += `<span class="tok-obj">${safe}</span>`;
      else if (FN_SET.has(lower)) out += `<span class="tok-fn">${safe}</span>`;
      else out += safe;
      i = j;
      continue;
    }

    out += escapeHtml(ch);
    i++;
  }

  return out;
}
