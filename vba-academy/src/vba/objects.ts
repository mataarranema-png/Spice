import {
  computeDisplayValue,
  formatAddress,
  parseRangeAddress,
  Workbook,
  Worksheet,
  type CellValue,
  type RangeSpec,
  MAX_COLS,
  MAX_ROWS,
} from './workbook';

export class VbaRuntimeError extends Error {
  line: number;
  constructor(message: string, line = 0) {
    super(message);
    this.name = 'VbaRuntimeError';
    this.line = line;
  }
}

export type VbaValue =
  | number
  | string
  | boolean
  | null
  | VbaObject
  | VbaArray
  | VbaValue[];

export interface VbaObject {
  __obj: true;
  typeName: string;
  getMember(name: string): VbaValue;
  setMember(name: string, value: VbaValue): void;
  callSelf?(args: VbaValue[]): VbaValue;
  items?(): VbaValue[];
  defaultValue?(): VbaValue;
}

export class VbaArray {
  __obj = true as const;
  typeName = 'Array';
  data: VbaValue[];
  lower: number;
  constructor(lower: number, upper: number, fill: VbaValue = null) {
    this.lower = lower;
    this.data = new Array(Math.max(0, upper - lower + 1)).fill(fill);
  }
  get upper() {
    return this.lower + this.data.length - 1;
  }
  get(index: number): VbaValue {
    const i = index - this.lower;
    if (i < 0 || i >= this.data.length) {
      throw new VbaRuntimeError(`ดัชนีอาร์เรย์ ${index} อยู่นอกช่วง (${this.lower} ถึง ${this.upper})`);
    }
    return this.data[i];
  }
  set(index: number, value: VbaValue) {
    const i = index - this.lower;
    if (i < 0 || i >= this.data.length) {
      throw new VbaRuntimeError(`ดัชนีอาร์เรย์ ${index} อยู่นอกช่วง (${this.lower} ถึง ${this.upper})`);
    }
    this.data[i] = value;
  }
  getMember(name: string): VbaValue {
    if (name === 'length' || name === 'count') return this.data.length;
    throw new VbaRuntimeError(`อาร์เรย์ไม่มีสมาชิกชื่อ ${name}`);
  }
  setMember(): void {
    throw new VbaRuntimeError('กำหนดค่าให้สมาชิกของอาร์เรย์ไม่ได้');
  }
  items(): VbaValue[] {
    return [...this.data];
  }
}

export function isObject(v: VbaValue): v is VbaObject {
  return typeof v === 'object' && v !== null && (v as VbaObject).__obj === true;
}

/** แปลง Long สี VBA (BGR) เป็น CSS hex */
export function longToCss(value: number): string {
  const n = Math.max(0, Math.floor(value));
  const r = n & 0xff;
  const g = (n >> 8) & 0xff;
  const b = (n >> 16) & 0xff;
  return `#${[r, g, b].map((x) => x.toString(16).padStart(2, '0')).join('')}`;
}

export function cssToLong(css: string | null | undefined): number {
  if (!css) return 16777215; // ขาว
  const m = /^#?([0-9a-f]{6})$/i.exec(css.trim());
  if (!m) return 16777215;
  const r = parseInt(m[1].slice(0, 2), 16);
  const g = parseInt(m[1].slice(2, 4), 16);
  const b = parseInt(m[1].slice(4, 6), 16);
  return r + g * 256 + b * 65536;
}

export interface HostBridge {
  notifyChange(): void;
  print(text: string): void;
  select(sheetName: string, spec: RangeSpec): void;
}

function clampSpec(spec: RangeSpec, line = 0): RangeSpec {
  if (spec.row < 1 || spec.col < 1) {
    throw new VbaRuntimeError('แถวและคอลัมน์ต้องเริ่มที่ 1 ขึ้นไป', line);
  }
  if (spec.row + spec.rows - 1 > MAX_ROWS || spec.col + spec.cols - 1 > MAX_COLS) {
    throw new VbaRuntimeError(
      `ชีตจำลองมีแค่ ${MAX_ROWS} แถว × ${MAX_COLS} คอลัมน์ (A-Z) นะ`,
      line,
    );
  }
  return spec;
}

// ---------- Range ----------

export class RangeObj implements VbaObject {
  __obj = true as const;
  typeName = 'Range';
  constructor(
    public sheet: Worksheet,
    public spec: RangeSpec,
    public host: HostBridge,
    public book: Workbook,
  ) {
    clampSpec(spec);
  }

  private cells(): { row: number; col: number }[] {
    const out: { row: number; col: number }[] = [];
    for (let r = this.spec.row; r < this.spec.row + this.spec.rows; r++) {
      for (let c = this.spec.col; c < this.spec.col + this.spec.cols; c++) {
        out.push({ row: r, col: c });
      }
    }
    return out;
  }

  first() {
    return { row: this.spec.row, col: this.spec.col };
  }

  defaultValue(): VbaValue {
    return this.getMember('value');
  }

  getMember(name: string): VbaValue {
    const { row, col } = this.first();
    switch (name) {
      case 'value':
      case 'value2':
      case 'text': {
        const v = computeDisplayValue(this.sheet, row, col);
        if (name === 'text') return v === null ? '' : String(v);
        return v as VbaValue;
      }
      case 'formula': {
        const cell = this.sheet.peek(row, col);
        if (cell?.formula) return cell.formula;
        const v = cell?.value ?? null;
        return v === null ? '' : (v as VbaValue);
      }
      case 'row':
        return row;
      case 'column':
        return col;
      case 'rows':
        return new RangeCollection(this, 'rows');
      case 'columns':
        return new RangeCollection(this, 'columns');
      case 'cells':
        return new CellsAccessor(this.sheet, this.host, this.book, this.spec);
      case 'count':
        return this.spec.rows * this.spec.cols;
      case 'address':
        return formatAddress(this.spec);
      case 'font':
        return new FontObj(this);
      case 'interior':
        return new InteriorObj(this);
      case 'borders':
        return new BordersObj(this);
      case 'worksheet':
        return new SheetObj(this.sheet, this.book, this.host);
      case 'entirerow':
        return new RangeObj(
          this.sheet,
          { row: this.spec.row, col: 1, rows: this.spec.rows, cols: MAX_COLS },
          this.host,
          this.book,
        );
      case 'entirecolumn':
        return new RangeObj(
          this.sheet,
          { row: 1, col: this.spec.col, rows: MAX_ROWS, cols: this.spec.cols },
          this.host,
          this.book,
        );
      case 'horizontalalignment':
        return this.sheet.peek(row, col)?.style.align ?? 'left';
      case 'numberformat':
        return this.sheet.peek(row, col)?.style.numberFormat ?? 'General';
      case 'offset':
      case 'resize':
      case 'select':
      case 'clear':
      case 'clearcontents':
      case 'copy':
      case 'end':
      case 'autofit':
      case 'activate':
      case 'merge':
      case 'sort':
        return new MethodObj(name, (args) => this.invoke(name, args));
      default:
        throw new VbaRuntimeError(`Range ไม่มีคุณสมบัติชื่อ "${name}"`);
    }
  }

  invoke(name: string, args: VbaValue[]): VbaValue {
    switch (name) {
      case 'offset': {
        const dr = toNumber(args[0] ?? 0);
        const dc = toNumber(args[1] ?? 0);
        return new RangeObj(
          this.sheet,
          { ...this.spec, row: this.spec.row + dr, col: this.spec.col + dc },
          this.host,
          this.book,
        );
      }
      case 'resize': {
        const rows = args[0] === null || args[0] === undefined ? this.spec.rows : toNumber(args[0]);
        const cols = args[1] === null || args[1] === undefined ? this.spec.cols : toNumber(args[1]);
        return new RangeObj(this.sheet, { ...this.spec, rows, cols }, this.host, this.book);
      }
      case 'select':
      case 'activate':
        this.host.select(this.sheet.name, this.spec);
        return null;
      case 'clear':
        for (const { row, col } of this.cells()) this.sheet.clearCell(row, col, false);
        this.host.notifyChange();
        return null;
      case 'clearcontents':
        for (const { row, col } of this.cells()) this.sheet.clearCell(row, col, true);
        this.host.notifyChange();
        return null;
      case 'autofit':
      case 'copy':
      case 'merge':
      case 'sort':
        return null;
      case 'end': {
        // ประมาณ xlDown/xlUp/xlToRight/xlToLeft ด้วยค่าคงที่
        const dir = toNumber(args[0] ?? -4121);
        return this.endOf(dir);
      }
      default:
        throw new VbaRuntimeError(`Range ไม่มีเมธอดชื่อ "${name}"`);
    }
  }

  private endOf(dir: number): RangeObj {
    let { row, col } = this.first();
    const has = (r: number, c: number) => {
      const v = this.sheet.getValue(r, c);
      return v !== null && v !== '';
    };
    const stepMap: Record<number, [number, number]> = {
      [-4121]: [1, 0], // xlDown
      [-4162]: [-1, 0], // xlUp
      [-4161]: [0, 1], // xlToRight
      [-4159]: [0, -1], // xlToLeft
    };
    const [dr, dc] = stepMap[dir] ?? [1, 0];
    if (!has(row + dr, col + dc)) {
      while (row + dr >= 1 && col + dc >= 1 && row + dr <= MAX_ROWS && col + dc <= MAX_COLS) {
        row += dr;
        col += dc;
        if (has(row, col)) break;
      }
    } else {
      while (has(row + dr, col + dc)) {
        row += dr;
        col += dc;
      }
    }
    return new RangeObj(
      this.sheet,
      { row: Math.max(1, row), col: Math.max(1, col), rows: 1, cols: 1 },
      this.host,
      this.book,
    );
  }

  setMember(name: string, value: VbaValue) {
    switch (name) {
      case 'value':
      case 'value2':
      case 'formula': {
        for (const { row, col } of this.cells()) {
          this.sheet.setValue(row, col, toCellValue(value));
        }
        this.host.notifyChange();
        return;
      }
      case 'numberformat': {
        for (const { row, col } of this.cells()) {
          this.sheet.getCell(row, col).style.numberFormat = String(value ?? '');
        }
        this.host.notifyChange();
        return;
      }
      case 'horizontalalignment': {
        const map: Record<number, 'left' | 'center' | 'right'> = {
          [-4131]: 'left',
          [-4108]: 'center',
          [-4152]: 'right',
        };
        const align = typeof value === 'number' ? map[value] ?? 'left' : (String(value) as 'left');
        for (const { row, col } of this.cells()) {
          this.sheet.getCell(row, col).style.align = align;
        }
        this.host.notifyChange();
        return;
      }
      case 'columnwidth': {
        for (let c = this.spec.col; c < this.spec.col + this.spec.cols; c++) {
          this.sheet.colWidths.set(c, Math.max(40, toNumber(value) * 8));
        }
        this.host.notifyChange();
        return;
      }
      default:
        throw new VbaRuntimeError(`กำหนดค่า Range.${name} ไม่ได้`);
    }
  }

  callSelf(args: VbaValue[]): VbaValue {
    // Range("A1")(2) หรือ rng(1, 2)
    if (args.length === 1) {
      const idx = toNumber(args[0]);
      const r = Math.floor((idx - 1) / this.spec.cols);
      const c = (idx - 1) % this.spec.cols;
      return new RangeObj(
        this.sheet,
        { row: this.spec.row + r, col: this.spec.col + c, rows: 1, cols: 1 },
        this.host,
        this.book,
      );
    }
    const r = toNumber(args[0]);
    const c = toNumber(args[1]);
    return new RangeObj(
      this.sheet,
      { row: this.spec.row + r - 1, col: this.spec.col + c - 1, rows: 1, cols: 1 },
      this.host,
      this.book,
    );
  }

  items(): VbaValue[] {
    return this.cells().map(
      ({ row, col }) => new RangeObj(this.sheet, { row, col, rows: 1, cols: 1 }, this.host, this.book),
    );
  }

  applyStyle(mutate: (style: import('./workbook').CellStyle) => void) {
    for (const { row, col } of this.cells()) {
      mutate(this.sheet.getCell(row, col).style);
    }
    this.host.notifyChange();
  }
}

class RangeCollection implements VbaObject {
  __obj = true as const;
  typeName = 'RangeCollection';
  constructor(private range: RangeObj, private axis: 'rows' | 'columns') {}

  getMember(name: string): VbaValue {
    if (name === 'count') {
      return this.axis === 'rows' ? this.range.spec.rows : this.range.spec.cols;
    }
    throw new VbaRuntimeError(`${this.axis} ไม่มีคุณสมบัติ ${name}`);
  }
  setMember(): void {
    throw new VbaRuntimeError('กำหนดค่าตรงนี้ไม่ได้');
  }
  callSelf(args: VbaValue[]): VbaValue {
    const i = toNumber(args[0]);
    const s = this.range.spec;
    const spec =
      this.axis === 'rows'
        ? { row: s.row + i - 1, col: s.col, rows: 1, cols: s.cols }
        : { row: s.row, col: s.col + i - 1, rows: s.rows, cols: 1 };
    return new RangeObj(this.range.sheet, spec, this.range.host, this.range.book);
  }
  items(): VbaValue[] {
    const s = this.range.spec;
    const out: VbaValue[] = [];
    if (this.axis === 'rows') {
      for (let r = 0; r < s.rows; r++) {
        out.push(new RangeObj(this.range.sheet, { row: s.row + r, col: s.col, rows: 1, cols: s.cols }, this.range.host, this.range.book));
      }
    } else {
      for (let c = 0; c < s.cols; c++) {
        out.push(new RangeObj(this.range.sheet, { row: s.row, col: s.col + c, rows: s.rows, cols: 1 }, this.range.host, this.range.book));
      }
    }
    return out;
  }
}

export class MethodObj implements VbaObject {
  __obj = true as const;
  typeName = 'Method';
  constructor(public name: string, private fn: (args: VbaValue[]) => VbaValue) {}
  getMember(name: string): VbaValue {
    const result = this.fn([]);
    if (isObject(result)) return result.getMember(name);
    throw new VbaRuntimeError(`เรียก ${this.name}.${name} ไม่ได้`);
  }
  setMember(name: string, value: VbaValue): void {
    const result = this.fn([]);
    if (isObject(result)) {
      result.setMember(name, value);
      return;
    }
    throw new VbaRuntimeError(`กำหนดค่า ${this.name}.${name} ไม่ได้`);
  }
  callSelf(args: VbaValue[]): VbaValue {
    return this.fn(args);
  }
  defaultValue(): VbaValue {
    const result = this.fn([]);
    return isObject(result) && result.defaultValue ? result.defaultValue() : result;
  }
}

class FontObj implements VbaObject {
  __obj = true as const;
  typeName = 'Font';
  constructor(private range: RangeObj) {}
  getMember(name: string): VbaValue {
    const { row, col } = this.range.first();
    const style = this.range.sheet.peek(row, col)?.style ?? {};
    switch (name) {
      case 'bold': return !!style.bold;
      case 'italic': return !!style.italic;
      case 'underline': return !!style.underline;
      case 'size': return style.fontSize ?? 11;
      case 'color': return cssToLong(style.fontColor ?? '#1f2937');
      case 'name': return 'Calibri';
      default: throw new VbaRuntimeError(`Font ไม่มีคุณสมบัติ ${name}`);
    }
  }
  setMember(name: string, value: VbaValue): void {
    switch (name) {
      case 'bold': this.range.applyStyle((s) => (s.bold = toBool(value))); return;
      case 'italic': this.range.applyStyle((s) => (s.italic = toBool(value))); return;
      case 'underline': this.range.applyStyle((s) => (s.underline = toBool(value))); return;
      case 'size': this.range.applyStyle((s) => (s.fontSize = toNumber(value))); return;
      case 'color':
      case 'colorindex':
        this.range.applyStyle((s) => (s.fontColor = longToCss(toNumber(value))));
        return;
      case 'name': return;
      default: throw new VbaRuntimeError(`กำหนดค่า Font.${name} ไม่ได้`);
    }
  }
}

class InteriorObj implements VbaObject {
  __obj = true as const;
  typeName = 'Interior';
  constructor(private range: RangeObj) {}
  getMember(name: string): VbaValue {
    const { row, col } = this.range.first();
    const style = this.range.sheet.peek(row, col)?.style ?? {};
    if (name === 'color' || name === 'colorindex') return cssToLong(style.fill ?? '#ffffff');
    throw new VbaRuntimeError(`Interior ไม่มีคุณสมบัติ ${name}`);
  }
  setMember(name: string, value: VbaValue): void {
    if (name === 'color' || name === 'colorindex') {
      const n = toNumber(value);
      this.range.applyStyle((s) => (s.fill = n === -4142 ? null : longToCss(n)));
      return;
    }
    if (name === 'pattern') return;
    throw new VbaRuntimeError(`กำหนดค่า Interior.${name} ไม่ได้`);
  }
}

class BordersObj implements VbaObject {
  __obj = true as const;
  typeName = 'Borders';
  constructor(private range: RangeObj) {}
  getMember(name: string): VbaValue {
    if (name === 'linestyle' || name === 'weight') return 1;
    throw new VbaRuntimeError(`Borders ไม่มีคุณสมบัติ ${name}`);
  }
  setMember(name: string, value: VbaValue): void {
    if (name === 'linestyle') {
      const on = toNumber(value) !== -4142;
      this.range.applyStyle((s) => (s.border = on));
      return;
    }
    if (name === 'weight' || name === 'color') return;
    throw new VbaRuntimeError(`กำหนดค่า Borders.${name} ไม่ได้`);
  }
  callSelf(): VbaValue {
    return this;
  }
}

export class CellsAccessor implements VbaObject {
  __obj = true as const;
  typeName = 'Cells';
  constructor(
    private sheet: Worksheet,
    private host: HostBridge,
    private book: Workbook,
    private base?: RangeSpec,
  ) {}

  private origin() {
    return this.base ?? { row: 1, col: 1, rows: MAX_ROWS, cols: MAX_COLS };
  }

  callSelf(args: VbaValue[]): VbaValue {
    const o = this.origin();
    if (args.length === 0) {
      return new RangeObj(this.sheet, o, this.host, this.book);
    }
    if (args.length === 1) {
      const idx = toNumber(args[0]);
      const r = Math.floor((idx - 1) / o.cols);
      const c = (idx - 1) % o.cols;
      return new RangeObj(this.sheet, { row: o.row + r, col: o.col + c, rows: 1, cols: 1 }, this.host, this.book);
    }
    const r = toNumber(args[0]);
    const c = typeof args[1] === 'string' ? colLetterToNum(args[1]) : toNumber(args[1]);
    return new RangeObj(
      this.sheet,
      { row: o.row + r - 1, col: o.col + c - 1, rows: 1, cols: 1 },
      this.host,
      this.book,
    );
  }

  getMember(name: string): VbaValue {
    if (name === 'count') {
      const o = this.origin();
      return o.rows * o.cols;
    }
    const all = new RangeObj(this.sheet, this.origin(), this.host, this.book);
    return all.getMember(name);
  }

  setMember(name: string, value: VbaValue): void {
    const all = new RangeObj(this.sheet, this.origin(), this.host, this.book);
    all.setMember(name, value);
  }
}

function colLetterToNum(letters: string): number {
  let n = 0;
  for (const ch of letters.toUpperCase()) n = n * 26 + (ch.charCodeAt(0) - 64);
  return n;
}

// ---------- Worksheet ----------

export class SheetObj implements VbaObject {
  __obj = true as const;
  typeName = 'Worksheet';
  constructor(public sheet: Worksheet, public book: Workbook, public host: HostBridge) {}

  getMember(name: string): VbaValue {
    switch (name) {
      case 'name':
        return this.sheet.name;
      case 'cells':
        return new CellsAccessor(this.sheet, this.host, this.book);
      case 'range':
        return new MethodObj('range', (args) => this.rangeFrom(args));
      case 'rows':
        return new MethodObj('rows', (args) => {
          const i = toNumber(args[0] ?? 1);
          return new RangeObj(this.sheet, { row: i, col: 1, rows: 1, cols: MAX_COLS }, this.host, this.book);
        });
      case 'columns':
        return new MethodObj('columns', (args) => {
          const a = args[0];
          const i = typeof a === 'string' ? colLetterToNum(a) : toNumber(a ?? 1);
          return new RangeObj(this.sheet, { row: 1, col: i, rows: MAX_ROWS, cols: 1 }, this.host, this.book);
        });
      case 'usedrange': {
        const b = this.sheet.usedBounds();
        const spec = b
          ? { row: b.minRow, col: b.minCol, rows: b.maxRow - b.minRow + 1, cols: b.maxCol - b.minCol + 1 }
          : { row: 1, col: 1, rows: 1, cols: 1 };
        return new RangeObj(this.sheet, spec, this.host, this.book);
      }
      case 'index':
        return this.book.sheets.indexOf(this.sheet) + 1;
      case 'activate':
      case 'select':
        return new MethodObj(name, () => {
          this.book.activeIndex = this.book.sheets.indexOf(this.sheet);
          this.host.notifyChange();
          return null;
        });
      default:
        throw new VbaRuntimeError(`Worksheet ไม่มีคุณสมบัติ "${name}"`);
    }
  }

  rangeFrom(args: VbaValue[]): VbaValue {
    if (args.length >= 2 && isObject(args[0]) && isObject(args[1])) {
      const a = args[0] as RangeObj;
      const b = args[1] as RangeObj;
      const row = Math.min(a.spec.row, b.spec.row);
      const col = Math.min(a.spec.col, b.spec.col);
      return new RangeObj(
        this.sheet,
        {
          row,
          col,
          rows: Math.max(a.spec.row + a.spec.rows, b.spec.row + b.spec.rows) - row,
          cols: Math.max(a.spec.col + a.spec.cols, b.spec.col + b.spec.cols) - col,
        },
        this.host,
        this.book,
      );
    }
    const addr = String(toPrimitive(args[0]) ?? '');
    const spec = parseRangeAddress(addr);
    if (!spec) throw new VbaRuntimeError(`ที่อยู่เซลล์ "${addr}" ไม่ถูกต้อง (ตัวอย่างที่ถูก: "A1" หรือ "A1:C10")`);
    return new RangeObj(this.sheet, spec, this.host, this.book);
  }

  setMember(name: string, value: VbaValue): void {
    if (name === 'name') {
      this.sheet.name = String(toPrimitive(value) ?? '');
      this.host.notifyChange();
      return;
    }
    throw new VbaRuntimeError(`กำหนดค่า Worksheet.${name} ไม่ได้`);
  }
}

export class SheetsCollection implements VbaObject {
  __obj = true as const;
  typeName = 'Sheets';
  constructor(private book: Workbook, private host: HostBridge) {}
  callSelf(args: VbaValue[]): VbaValue {
    const key = toPrimitive(args[0]);
    const sheet =
      typeof key === 'number' ? this.book.byIndex(key) : this.book.byName(String(key ?? ''));
    if (!sheet) throw new VbaRuntimeError(`ไม่พบชีต "${key}"`);
    return new SheetObj(sheet, this.book, this.host);
  }
  getMember(name: string): VbaValue {
    if (name === 'count') return this.book.sheets.length;
    if (name === 'add') return new MethodObj('add', () => {
      const ws = new Worksheet(`Sheet${this.book.sheets.length + 1}`);
      this.book.sheets.push(ws);
      this.host.notifyChange();
      return new SheetObj(ws, this.book, this.host);
    });
    throw new VbaRuntimeError(`Sheets ไม่มีคุณสมบัติ ${name}`);
  }
  setMember(): void {
    throw new VbaRuntimeError('กำหนดค่าให้ Sheets ไม่ได้');
  }
  items(): VbaValue[] {
    return this.book.sheets.map((s) => new SheetObj(s, this.book, this.host));
  }
}

export class WorkbookObj implements VbaObject {
  __obj = true as const;
  typeName = 'Workbook';
  constructor(private book: Workbook, private host: HostBridge) {}
  getMember(name: string): VbaValue {
    switch (name) {
      case 'worksheets':
      case 'sheets':
        return new SheetsCollection(this.book, this.host);
      case 'name':
        return 'VBA-Academy.xlsm';
      case 'activesheet':
        return new SheetObj(this.book.active, this.book, this.host);
      case 'save':
      case 'close':
        return new MethodObj(name, () => null);
      default:
        throw new VbaRuntimeError(`Workbook ไม่มีคุณสมบัติ ${name}`);
    }
  }
  setMember(): void {
    throw new VbaRuntimeError('กำหนดค่าให้ Workbook ไม่ได้');
  }
}

// ---------- helpers ----------

export function toPrimitive(v: VbaValue | undefined): CellValue {
  if (v === undefined) return null;
  if (isObject(v)) {
    if (v.defaultValue) return toPrimitive(v.defaultValue());
    throw new VbaRuntimeError(`ใช้ออบเจ็กต์ ${v.typeName} เป็นค่าตรง ๆ ไม่ได้`);
  }
  if (Array.isArray(v)) return v.length ? toPrimitive(v[0] as VbaValue) : null;
  return v as CellValue;
}

export function toNumber(v: VbaValue | undefined): number {
  const p = toPrimitive(v);
  if (p === null || p === '') return 0;
  if (typeof p === 'boolean') return p ? -1 : 0;
  const n = Number(p);
  if (Number.isNaN(n)) {
    throw new VbaRuntimeError(`แปลง "${p}" เป็นตัวเลขไม่ได้ (Type mismatch)`);
  }
  return n;
}

export function toBool(v: VbaValue | undefined): boolean {
  const p = toPrimitive(v);
  if (typeof p === 'boolean') return p;
  if (p === null || p === '') return false;
  if (typeof p === 'number') return p !== 0;
  const n = Number(p);
  return Number.isNaN(n) ? p.length > 0 : n !== 0;
}

export function toText(v: VbaValue | undefined): string {
  const p = toPrimitive(v);
  if (p === null) return '';
  if (typeof p === 'boolean') return p ? 'True' : 'False';
  if (typeof p === 'number') {
    if (Number.isInteger(p)) return String(p);
    return String(Math.round(p * 1e10) / 1e10);
  }
  return String(p);
}

export function toCellValue(v: VbaValue | undefined): CellValue {
  return toPrimitive(v);
}
