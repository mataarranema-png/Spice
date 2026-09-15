// โมเดล Excel จำลอง: Workbook / Worksheet / Cell + เครื่องมือแปลงที่อยู่เซลล์

export type CellValue = string | number | boolean | null;

export interface CellStyle {
  bold?: boolean;
  italic?: boolean;
  underline?: boolean;
  fill?: string | null;
  fontColor?: string | null;
  fontSize?: number | null;
  align?: 'left' | 'center' | 'right' | null;
  numberFormat?: string | null;
  border?: boolean;
}

export interface Cell {
  value: CellValue;
  formula?: string | null;
  style: CellStyle;
}

export const MAX_ROWS = 200;
export const MAX_COLS = 26;

export function emptyCell(): Cell {
  return { value: null, formula: null, style: {} };
}

export function colLetter(col: number): string {
  let n = col;
  let s = '';
  while (n > 0) {
    const rem = (n - 1) % 26;
    s = String.fromCharCode(65 + rem) + s;
    n = Math.floor((n - 1) / 26);
  }
  return s || 'A';
}

export function colNumber(letters: string): number {
  let n = 0;
  for (const ch of letters.toUpperCase()) {
    n = n * 26 + (ch.charCodeAt(0) - 64);
  }
  return n;
}

export function cellKey(row: number, col: number) {
  return `${row}:${col}`;
}

export function addressToRC(address: string): { row: number; col: number } | null {
  const m = /^\$?([A-Za-z]{1,3})\$?(\d{1,5})$/.exec(address.trim());
  if (!m) return null;
  return { col: colNumber(m[1]), row: Number(m[2]) };
}

export interface RangeSpec {
  row: number;
  col: number;
  rows: number;
  cols: number;
}

export function parseRangeAddress(address: string): RangeSpec | null {
  const parts = address.split(':');
  if (parts.length === 1) {
    const rc = addressToRC(parts[0]);
    if (!rc) return null;
    return { row: rc.row, col: rc.col, rows: 1, cols: 1 };
  }
  if (parts.length === 2) {
    const a = addressToRC(parts[0]);
    const b = addressToRC(parts[1]);
    if (!a || !b) return null;
    const row = Math.min(a.row, b.row);
    const col = Math.min(a.col, b.col);
    return {
      row,
      col,
      rows: Math.abs(a.row - b.row) + 1,
      cols: Math.abs(a.col - b.col) + 1,
    };
  }
  return null;
}

export function formatAddress(spec: RangeSpec, absolute = true): string {
  const s = absolute ? '$' : '';
  const start = `${s}${colLetter(spec.col)}${s}${spec.row}`;
  if (spec.rows === 1 && spec.cols === 1) return start;
  const end = `${s}${colLetter(spec.col + spec.cols - 1)}${s}${spec.row + spec.rows - 1}`;
  return `${start}:${end}`;
}

export class Worksheet {
  name: string;
  cells = new Map<string, Cell>();
  colWidths = new Map<number, number>();

  constructor(name: string) {
    this.name = name;
  }

  getCell(row: number, col: number): Cell {
    const key = cellKey(row, col);
    let cell = this.cells.get(key);
    if (!cell) {
      cell = emptyCell();
      this.cells.set(key, cell);
    }
    return cell;
  }

  peek(row: number, col: number): Cell | undefined {
    return this.cells.get(cellKey(row, col));
  }

  getValue(row: number, col: number): CellValue {
    return this.peek(row, col)?.value ?? null;
  }

  setValue(row: number, col: number, value: CellValue) {
    const cell = this.getCell(row, col);
    if (typeof value === 'string' && value.startsWith('=')) {
      cell.formula = value;
      cell.value = null;
    } else {
      cell.formula = null;
      cell.value = value;
    }
  }

  clearCell(row: number, col: number, contentsOnly = false) {
    if (contentsOnly) {
      const cell = this.peek(row, col);
      if (cell) {
        cell.value = null;
        cell.formula = null;
      }
      return;
    }
    this.cells.delete(cellKey(row, col));
  }

  usedBounds(): { minRow: number; minCol: number; maxRow: number; maxCol: number } | null {
    let minRow = Infinity, minCol = Infinity, maxRow = 0, maxCol = 0;
    let any = false;
    for (const [key, cell] of this.cells) {
      const hasContent =
        cell.value !== null && cell.value !== '' ? true : !!cell.formula || hasStyle(cell.style);
      if (!hasContent) continue;
      const [r, c] = key.split(':').map(Number);
      any = true;
      minRow = Math.min(minRow, r);
      minCol = Math.min(minCol, c);
      maxRow = Math.max(maxRow, r);
      maxCol = Math.max(maxCol, c);
    }
    if (!any) return null;
    return { minRow, minCol, maxRow, maxCol };
  }

  clone(): Worksheet {
    const sheet = new Worksheet(this.name);
    for (const [key, cell] of this.cells) {
      sheet.cells.set(key, {
        value: cell.value,
        formula: cell.formula ?? null,
        style: { ...cell.style },
      });
    }
    sheet.colWidths = new Map(this.colWidths);
    return sheet;
  }
}

function hasStyle(style: CellStyle) {
  return Object.values(style).some((v) => v !== undefined && v !== null && v !== false);
}

export class Workbook {
  sheets: Worksheet[] = [];
  activeIndex = 0;

  constructor(sheetNames: string[] = ['Sheet1']) {
    this.sheets = sheetNames.map((n) => new Worksheet(n));
  }

  get active(): Worksheet {
    return this.sheets[this.activeIndex] ?? this.sheets[0];
  }

  byName(name: string): Worksheet | undefined {
    return this.sheets.find((s) => s.name.toLowerCase() === name.toLowerCase());
  }

  byIndex(index: number): Worksheet | undefined {
    return this.sheets[index - 1];
  }

  clone(): Workbook {
    const wb = new Workbook([]);
    wb.sheets = this.sheets.map((s) => s.clone());
    wb.activeIndex = this.activeIndex;
    return wb;
  }
}

// ---------- ตัวคำนวณสูตรอย่างง่าย ----------

export function computeDisplayValue(sheet: Worksheet, row: number, col: number, depth = 0): CellValue {
  const cell = sheet.peek(row, col);
  if (!cell) return null;
  if (!cell.formula) return cell.value;
  if (depth > 12) return '#REF!';
  try {
    return evaluateFormula(sheet, cell.formula.slice(1), depth + 1);
  } catch {
    return '#ERROR!';
  }
}

function collectRange(sheet: Worksheet, spec: RangeSpec, depth: number): CellValue[] {
  const out: CellValue[] = [];
  for (let r = spec.row; r < spec.row + spec.rows; r++) {
    for (let c = spec.col; c < spec.col + spec.cols; c++) {
      out.push(computeDisplayValue(sheet, r, c, depth));
    }
  }
  return out;
}

const FORMULA_FUNCS: Record<string, (args: CellValue[][]) => CellValue> = {
  SUM: (args) => flatNums(args).reduce((a, b) => a + b, 0),
  AVERAGE: (args) => {
    const nums = flatNums(args);
    return nums.length ? nums.reduce((a, b) => a + b, 0) / nums.length : 0;
  },
  COUNT: (args) => flatNums(args).length,
  COUNTA: (args) => args.flat().filter((v) => v !== null && v !== '').length,
  MAX: (args) => {
    const nums = flatNums(args);
    return nums.length ? Math.max(...nums) : 0;
  },
  MIN: (args) => {
    const nums = flatNums(args);
    return nums.length ? Math.min(...nums) : 0;
  },
  ROUND: (args) => {
    const n = num(args[0]?.[0]);
    const d = num(args[1]?.[0]);
    const f = Math.pow(10, d);
    return Math.round(n * f) / f;
  },
  ABS: (args) => Math.abs(num(args[0]?.[0])),
  INT: (args) => Math.floor(num(args[0]?.[0])),
  IF: (args) => {
    const cond = args[0]?.[0];
    const truthy = typeof cond === 'boolean' ? cond : num(cond) !== 0;
    return truthy ? args[1]?.[0] ?? true : args[2]?.[0] ?? false;
  },
  LEN: (args) => String(args[0]?.[0] ?? '').length,
  UPPER: (args) => String(args[0]?.[0] ?? '').toUpperCase(),
  LOWER: (args) => String(args[0]?.[0] ?? '').toLowerCase(),
  CONCATENATE: (args) => args.flat().map((v) => (v === null ? '' : String(v))).join(''),
  SUMIF: (args) => {
    const range = args[0] ?? [];
    const criterion = args[1]?.[0] ?? '';
    const sumRange = args[2] ?? range;
    let total = 0;
    range.forEach((v, i) => {
      if (matchCriterion(v, criterion)) total += num(sumRange[i] ?? 0);
    });
    return total;
  },
  COUNTIF: (args) => {
    const range = args[0] ?? [];
    const criterion = args[1]?.[0] ?? '';
    return range.filter((v) => matchCriterion(v, criterion)).length;
  },
};

function matchCriterion(value: CellValue, criterion: CellValue): boolean {
  const text = String(criterion ?? '');
  const m = /^(>=|<=|<>|>|<|=)(.*)$/.exec(text);
  if (m) {
    const right = m[2].trim();
    const a = num(value);
    const b = Number(right);
    if (!Number.isNaN(b)) {
      switch (m[1]) {
        case '>': return a > b;
        case '<': return a < b;
        case '>=': return a >= b;
        case '<=': return a <= b;
        case '<>': return a !== b;
        default: return a === b;
      }
    }
    return m[1] === '<>' ? String(value ?? '') !== right : String(value ?? '') === right;
  }
  return String(value ?? '').toLowerCase() === text.toLowerCase();
}

function flatNums(args: CellValue[][]): number[] {
  return args
    .flat()
    .filter((v) => v !== null && v !== '' && !Number.isNaN(Number(v)))
    .map((v) => Number(v));
}

function num(v: CellValue | undefined): number {
  if (v === null || v === undefined || v === '') return 0;
  if (typeof v === 'boolean') return v ? 1 : 0;
  const n = Number(v);
  return Number.isNaN(n) ? 0 : n;
}

/** ตัวประเมินสูตรเล็ก ๆ รองรับ ref, ช่วง, ฟังก์ชันพื้นฐาน และเลขคณิต */
export function evaluateFormula(sheet: Worksheet, src: string, depth = 0): CellValue {
  let i = 0;
  const text = src;

  function skipWs() {
    while (i < text.length && /\s/.test(text[i])) i++;
  }

  function parseExpression(): CellValue {
    let left = parseComparisonOperand();
    skipWs();
    const opMatch = /^(<=|>=|<>|=|<|>)/.exec(text.slice(i));
    if (opMatch) {
      i += opMatch[0].length;
      const right = parseComparisonOperand();
      const a = typeof left === 'string' || typeof right === 'string' ? String(left ?? '') : num(left);
      const b = typeof left === 'string' || typeof right === 'string' ? String(right ?? '') : num(right);
      switch (opMatch[0]) {
        case '=': return a === b;
        case '<>': return a !== b;
        case '<': return a < b;
        case '>': return a > b;
        case '<=': return a <= b;
        case '>=': return a >= b;
      }
    }
    return left;
  }

  function parseComparisonOperand(): CellValue {
    let left = parseTerm();
    for (;;) {
      skipWs();
      const ch = text[i];
      if (ch === '+' || ch === '-') {
        i++;
        const right = parseTerm();
        left = ch === '+' ? num(left) + num(right) : num(left) - num(right);
        continue;
      }
      if (ch === '&') {
        i++;
        const right = parseTerm();
        left = `${left ?? ''}${right ?? ''}`;
        continue;
      }
      break;
    }
    return left;
  }

  function parseTerm(): CellValue {
    let left = parsePower();
    for (;;) {
      skipWs();
      const ch = text[i];
      if (ch === '*' || ch === '/') {
        i++;
        const right = parsePower();
        left = ch === '*' ? num(left) * num(right) : num(right) === 0 ? '#DIV/0!' : num(left) / num(right);
        continue;
      }
      break;
    }
    return left;
  }

  function parsePower(): CellValue {
    const base = parseUnary();
    skipWs();
    if (text[i] === '^') {
      i++;
      return Math.pow(num(base), num(parseUnary()));
    }
    return base;
  }

  function parseUnary(): CellValue {
    skipWs();
    if (text[i] === '-') {
      i++;
      return -num(parseUnary());
    }
    if (text[i] === '+') {
      i++;
      return parseUnary();
    }
    return parseAtom();
  }

  function parseArgument(): CellValue[] {
    skipWs();
    const start = i;
    const rangeMatch = /^\$?[A-Za-z]{1,3}\$?\d{1,5}:\$?[A-Za-z]{1,3}\$?\d{1,5}/.exec(text.slice(i));
    if (rangeMatch) {
      const after = text[i + rangeMatch[0].length];
      if (after === undefined || after === ',' || after === ')' || /\s/.test(after)) {
        i += rangeMatch[0].length;
        const spec = parseRangeAddress(rangeMatch[0].replace(/\$/g, ''));
        if (spec) return collectRange(sheet, spec, depth);
      }
      i = start;
    }
    return [parseExpression()];
  }

  function parseAtom(): CellValue {
    skipWs();
    const ch = text[i];

    if (ch === '(') {
      i++;
      const v = parseExpression();
      skipWs();
      if (text[i] === ')') i++;
      return v;
    }

    if (ch === '"') {
      i++;
      let buf = '';
      while (i < text.length) {
        if (text[i] === '"') {
          if (text[i + 1] === '"') {
            buf += '"';
            i += 2;
            continue;
          }
          i++;
          break;
        }
        buf += text[i++];
      }
      return buf;
    }

    const funcMatch = /^([A-Za-z][A-Za-z0-9_.]*)\s*\(/.exec(text.slice(i));
    if (funcMatch) {
      const name = funcMatch[1].toUpperCase();
      i += funcMatch[0].length;
      const args: CellValue[][] = [];
      skipWs();
      if (text[i] === ')') {
        i++;
      } else {
        for (;;) {
          args.push(parseArgument());
          skipWs();
          if (text[i] === ',') {
            i++;
            continue;
          }
          if (text[i] === ')') {
            i++;
          }
          break;
        }
      }
      const fn = FORMULA_FUNCS[name];
      if (!fn) return '#NAME?';
      return fn(args);
    }

    const refMatch = /^\$?([A-Za-z]{1,3})\$?(\d{1,5})/.exec(text.slice(i));
    if (refMatch) {
      i += refMatch[0].length;
      return computeDisplayValue(sheet, Number(refMatch[2]), colNumber(refMatch[1]), depth);
    }

    const numMatch = /^\d+(\.\d+)?([eE][+-]?\d+)?/.exec(text.slice(i));
    if (numMatch) {
      i += numMatch[0].length;
      return Number(numMatch[0]);
    }

    const boolMatch = /^(TRUE|FALSE)\b/i.exec(text.slice(i));
    if (boolMatch) {
      i += boolMatch[0].length;
      return boolMatch[0].toUpperCase() === 'TRUE';
    }

    throw new Error('สูตรไม่ถูกต้อง');
  }

  const result = parseExpression();
  return result;
}

export function formatCellValue(value: CellValue, style?: CellStyle): string {
  if (value === null || value === undefined) return '';
  if (typeof value === 'boolean') return value ? 'TRUE' : 'FALSE';
  if (typeof value === 'number') {
    const fmt = style?.numberFormat;
    if (fmt) {
      if (/0\.00/.test(fmt)) return value.toFixed(2);
      if (/#,##0/.test(fmt)) return value.toLocaleString('en-US');
      if (/0%/.test(fmt)) return `${Math.round(value * 100)}%`;
    }
    if (Number.isInteger(value)) return String(value);
    return String(Math.round(value * 1e10) / 1e10);
  }
  return String(value);
}
