import { parse } from './parser';
import { VbaSyntaxError } from './lexer';
import type { CaseTest, Expr, ProcDecl, Program, Stmt } from './ast';
import {
  CellsAccessor,
  isObject,
  longToCss,
  MethodObj,
  RangeObj,
  SheetObj,
  SheetsCollection,
  toBool,
  toNumber,
  toPrimitive,
  toText,
  VbaArray,
  VbaRuntimeError,
  WorkbookObj,
  type HostBridge,
  type VbaObject,
  type VbaValue,
} from './objects';
import { MAX_COLS, MAX_ROWS, Workbook, parseRangeAddress, type RangeSpec } from './workbook';

export interface RunHost {
  /** เรียกก่อนรันแต่ละคำสั่ง — ใช้ไฮไลต์บรรทัด, หน่วงเวลา, และยกเลิกการรัน */
  onStep?: (line: number) => Promise<void> | void;
  onChange?: () => void;
  onPrint?: (text: string) => void;
  onMsgBox?: (text: string, title: string) => Promise<void>;
  onInputBox?: (prompt: string, title: string, def: string) => Promise<string | null>;
  onSelect?: (sheetName: string, spec: RangeSpec) => void;
}

class ExitSignal {
  constructor(public what: 'for' | 'do' | 'sub' | 'function' | 'while') {}
}

interface Scope {
  vars: Map<string, VbaValue>;
  consts: Set<string>;
}

const VB_CONSTANTS: Record<string, VbaValue> = {
  vbcrlf: '\n',
  vbnewline: '\n',
  vblf: '\n',
  vbcr: '\n',
  vbtab: '\t',
  vbnullstring: '',
  vbok: 1,
  vbcancel: 2,
  vbyes: 6,
  vbno: 7,
  vbokonly: 0,
  vbokcancel: 1,
  vbyesno: 4,
  vbyesnocancel: 3,
  vbinformation: 64,
  vbexclamation: 48,
  vbcritical: 16,
  vbquestion: 32,
  vbblack: 0,
  vbred: 255,
  vbgreen: 65280,
  vbblue: 16711680,
  vbyellow: 65535,
  vbmagenta: 16711935,
  vbcyan: 16776960,
  vbwhite: 16777215,
  xlup: -4162,
  xldown: -4121,
  xltoright: -4161,
  xltoleft: -4159,
  xlnone: -4142,
  xlcenter: -4108,
  xlleft: -4131,
  xlright: -4152,
  xlcontinuous: 1,
  xlthin: 2,
  xlmedium: -4138,
  vbnullchar: '\0',
};

export interface RunResult {
  ok: boolean;
  error?: { message: string; line: number };
  output: string[];
}

export class Interpreter {
  private program: Program;
  private globals: Scope = { vars: new Map(), consts: new Set() };
  private scopes: Scope[] = [];
  private withStack: VbaValue[] = [];
  private steps = 0;
  private maxSteps = 2_000_000;
  private onErrorResumeNext = false;
  private host: RunHost;
  private bridge: HostBridge;
  output: string[] = [];

  constructor(source: string, private book: Workbook, host: RunHost = {}) {
    this.program = parse(source);
    this.host = host;
    this.bridge = {
      notifyChange: () => host.onChange?.(),
      print: (t) => {
        this.output.push(t);
        host.onPrint?.(t);
      },
      select: (name, spec) => host.onSelect?.(name, spec),
    };
  }

  get procedures(): ProcDecl[] {
    return this.program.procs;
  }

  /** รายชื่อ Sub ที่เรียกได้ (ไม่รับพารามิเตอร์บังคับ) */
  get runnableSubs(): ProcDecl[] {
    return this.program.procs.filter(
      (p) => p.kind === 'sub' && p.params.every((x) => x.optional || x.defaultValue),
    );
  }

  async run(procName?: string): Promise<RunResult> {
    this.output = [];
    this.steps = 0;
    try {
      // รันคำสั่งระดับโมดูล (ถ้ามี)
      if (this.program.moduleBody.length) {
        this.scopes = [this.globals];
        await this.execBlock(this.program.moduleBody);
      }

      const target =
        (procName && this.program.procs.find((p) => p.name === procName.toLowerCase())) ||
        this.runnableSubs[0] ||
        this.program.procs[0];

      if (target) {
        await this.callProc(target, []);
      } else if (!this.program.moduleBody.length) {
        throw new VbaRuntimeError('ยังไม่มี Sub ให้รันเลย ลองเขียน Sub แล้วใส่โค้ดข้างในดูนะ', 1);
      }
      return { ok: true, output: this.output };
    } catch (err) {
      if (err instanceof ExitSignal) return { ok: true, output: this.output };
      const line =
        err instanceof VbaRuntimeError || err instanceof VbaSyntaxError ? err.line : 0;
      return {
        ok: false,
        error: { message: (err as Error).message, line },
        output: this.output,
      };
    }
  }

  private get scope(): Scope {
    return this.scopes[this.scopes.length - 1] ?? this.globals;
  }

  private async callProc(proc: ProcDecl, args: VbaValue[]): Promise<VbaValue> {
    if (this.scopes.length > 60) {
      throw new VbaRuntimeError('เรียกฟังก์ชันซ้อนกันลึกเกินไป (Stack overflow)', proc.line);
    }
    const scope: Scope = { vars: new Map(), consts: new Set() };
    proc.params.forEach((p, i) => {
      let v = args[i];
      if (v === undefined) {
        v = p.defaultValue ? null : null;
      }
      scope.vars.set(p.name, v ?? null);
    });
    if (proc.kind === 'function') scope.vars.set(proc.name, null);

    this.scopes.push(scope);
    try {
      // ค่าเริ่มต้นของพารามิเตอร์ที่มี default
      for (let i = 0; i < proc.params.length; i++) {
        const p = proc.params[i];
        if (args[i] === undefined && p.defaultValue) {
          scope.vars.set(p.name, await this.evaluate(p.defaultValue));
        }
      }
      await this.execBlock(proc.body);
    } catch (err) {
      if (!(err instanceof ExitSignal) || (err.what !== 'sub' && err.what !== 'function')) throw err;
    } finally {
      this.scopes.pop();
    }
    return proc.kind === 'function' ? scope.vars.get(proc.name) ?? null : null;
  }

  private async execBlock(stmts: Stmt[]) {
    for (const stmt of stmts) {
      await this.execStatement(stmt);
    }
  }

  private async tick(line: number) {
    this.steps++;
    if (this.steps > this.maxSteps) {
      throw new VbaRuntimeError(
        'โค้ดวนนานเกินไป — น่าจะติด Infinite Loop ลองเช็กเงื่อนไขการวนซ้ำดูนะ',
        line,
      );
    }
    if (this.host.onStep) await this.host.onStep(line);
  }

  private async execStatement(stmt: Stmt): Promise<void> {
    await this.tick(stmt.line);
    try {
      await this.execStatementInner(stmt);
    } catch (err) {
      if (err instanceof ExitSignal) throw err;
      if (this.onErrorResumeNext && err instanceof VbaRuntimeError) return;
      if (err instanceof VbaRuntimeError && !err.line) err.line = stmt.line;
      throw err;
    }
  }

  private async execStatementInner(stmt: Stmt): Promise<void> {
    switch (stmt.kind) {
      case 'noop':
        return;

      case 'onError':
        this.onErrorResumeNext = stmt.mode === 'resumeNext';
        return;

      case 'dim':
      case 'redim': {
        for (const v of stmt.vars) {
          if (v.dims && v.dims.length) {
            const d = v.dims[0];
            const lower = d.lower ? toNumber(await this.evaluate(d.lower)) : 0;
            const upper = toNumber(await this.evaluate(d.upper));
            const existing = stmt.kind === 'redim' && (stmt as { preserve: boolean }).preserve
              ? this.lookup(v.name)
              : null;
            const arr = new VbaArray(lower, upper, defaultForType(v.type));
            if (existing instanceof VbaArray) {
              for (let i = 0; i < Math.min(existing.data.length, arr.data.length); i++) {
                arr.data[i] = existing.data[i];
              }
            }
            this.scope.vars.set(v.name, arr);
          } else {
            this.scope.vars.set(v.name, defaultForType(v.type));
          }
        }
        return;
      }

      case 'const': {
        this.scope.vars.set(stmt.name, await this.evaluate(stmt.value));
        this.scope.consts.add(stmt.name);
        return;
      }

      case 'assign': {
        const value = await this.evaluate(stmt.value);
        await this.assign(stmt.target, value);
        return;
      }

      case 'exprStmt': {
        const result = await this.evaluate(stmt.expr, true);
        if (result instanceof MethodObj) result.callSelf([]);
        return;
      }

      case 'if': {
        for (const branch of stmt.branches) {
          if (toBool(await this.evaluate(branch.cond))) {
            await this.execBlock(branch.body);
            return;
          }
        }
        if (stmt.elseBody) await this.execBlock(stmt.elseBody);
        return;
      }

      case 'for': {
        const from = toNumber(await this.evaluate(stmt.from));
        const to = toNumber(await this.evaluate(stmt.to));
        const step = stmt.step ? toNumber(await this.evaluate(stmt.step)) : 1;
        if (step === 0) throw new VbaRuntimeError('Step เป็น 0 ไม่ได้ เพราะจะวนไม่จบ', stmt.line);
        for (let i = from; step > 0 ? i <= to : i >= to; i += step) {
          this.setVar(stmt.varName, i);
          try {
            await this.execBlock(stmt.body);
          } catch (err) {
            if (err instanceof ExitSignal && err.what === 'for') return;
            throw err;
          }
          const current = this.lookup(stmt.varName);
          if (typeof current === 'number' && current !== i) i = current;
          await this.tick(stmt.line);
        }
        return;
      }

      case 'forEach': {
        const coll = await this.evaluate(stmt.coll);
        const items = collectionItems(coll);
        for (const item of items) {
          this.setVar(stmt.varName, item);
          try {
            await this.execBlock(stmt.body);
          } catch (err) {
            if (err instanceof ExitSignal && err.what === 'for') return;
            throw err;
          }
          await this.tick(stmt.line);
        }
        return;
      }

      case 'do': {
        for (;;) {
          if (stmt.pre) {
            const v = toBool(await this.evaluate(stmt.pre.cond));
            if (stmt.pre.type === 'while' ? !v : v) return;
          }
          try {
            await this.execBlock(stmt.body);
          } catch (err) {
            if (err instanceof ExitSignal && err.what === 'do') return;
            throw err;
          }
          if (stmt.post) {
            const v = toBool(await this.evaluate(stmt.post.cond));
            if (stmt.post.type === 'while' ? !v : v) return;
          }
          await this.tick(stmt.line);
        }
      }

      case 'while': {
        while (toBool(await this.evaluate(stmt.cond))) {
          try {
            await this.execBlock(stmt.body);
          } catch (err) {
            if (err instanceof ExitSignal && (err.what === 'while' || err.what === 'do')) return;
            throw err;
          }
          await this.tick(stmt.line);
        }
        return;
      }

      case 'select': {
        const subject = await this.evaluate(stmt.subject);
        for (const c of stmt.cases) {
          for (const test of c.tests) {
            if (await this.caseMatches(subject, test)) {
              await this.execBlock(c.body);
              return;
            }
          }
        }
        if (stmt.elseBody) await this.execBlock(stmt.elseBody);
        return;
      }

      case 'with': {
        const subject = await this.evaluate(stmt.subject);
        this.withStack.push(subject);
        try {
          await this.execBlock(stmt.body);
        } finally {
          this.withStack.pop();
        }
        return;
      }

      case 'exit':
        throw new ExitSignal(stmt.what);
    }
  }

  private async caseMatches(subject: VbaValue, test: CaseTest): Promise<boolean> {
    if (test.kind === 'value') {
      return looseEquals(subject, await this.evaluate(test.expr));
    }
    if (test.kind === 'range') {
      const a = toNumber(await this.evaluate(test.from));
      const b = toNumber(await this.evaluate(test.to));
      const s = toPrimitive(subject);
      if (typeof s === 'string' && Number.isNaN(Number(s))) {
        const sa = toText(await this.evaluate(test.from));
        const sb = toText(await this.evaluate(test.to));
        return s >= sa && s <= sb;
      }
      const n = toNumber(subject);
      return n >= a && n <= b;
    }
    const right = await this.evaluate(test.expr);
    return compare(test.op, subject, right);
  }

  private setVar(name: string, value: VbaValue) {
    const scope = this.scope;
    if (scope.vars.has(name)) {
      scope.vars.set(name, value);
      return;
    }
    if (this.globals.vars.has(name)) {
      this.globals.vars.set(name, value);
      return;
    }
    scope.vars.set(name, value);
  }

  private lookup(name: string): VbaValue | undefined {
    const scope = this.scope;
    if (scope.vars.has(name)) return scope.vars.get(name);
    if (this.globals.vars.has(name)) return this.globals.vars.get(name);
    return undefined;
  }

  private async assign(target: Expr, value: VbaValue): Promise<void> {
    if (target.kind === 'ident') {
      if (this.scope.consts.has(target.name)) {
        throw new VbaRuntimeError(`"${target.raw}" เป็นค่าคงที่ (Const) เปลี่ยนค่าไม่ได้`, target.line);
      }
      const existing = this.lookup(target.name);
      if (existing === undefined) {
        // ตัวแปรที่ยังไม่ประกาศ — สร้างให้เลย (เหมือน VBA ที่ไม่ได้ใส่ Option Explicit)
        this.scope.vars.set(target.name, value);
        return;
      }
      if (isObject(existing) && existing instanceof RangeObj && !isObject(value)) {
        existing.setMember('value', value);
        return;
      }
      this.setVar(target.name, value);
      return;
    }

    if (target.kind === 'member' || target.kind === 'withMember') {
      const obj =
        target.kind === 'member'
          ? await this.evaluate(target.obj)
          : this.currentWith(target.line);
      if (!isObject(obj)) {
        throw new VbaRuntimeError(`ตรงนี้ไม่ใช่ออบเจ็กต์ เลยกำหนดค่า .${target.raw} ไม่ได้`, target.line);
      }
      try {
        obj.setMember(target.name, value);
      } catch (err) {
        if (err instanceof VbaRuntimeError) {
          err.line = err.line || target.line;
          err.message = err.message.replace(target.name, target.raw);
        }
        throw err;
      }
      return;
    }

    if (target.kind === 'call') {
      const calleeExpr = target.callee;
      const args = await this.evalArgs(target.args);

      // อาร์เรย์
      if (calleeExpr.kind === 'ident') {
        const existing = this.lookup(calleeExpr.name);
        if (existing instanceof VbaArray) {
          existing.set(toNumber(args[0]), value);
          return;
        }
      }

      const callee = await this.evaluate(calleeExpr);
      if (callee instanceof VbaArray) {
        callee.set(toNumber(args[0]), value);
        return;
      }
      if (isObject(callee) && callee.callSelf) {
        const result = callee.callSelf(args);
        if (isObject(result)) {
          result.setMember('value', value);
          return;
        }
      }
      throw new VbaRuntimeError('กำหนดค่าให้สิ่งนี้ไม่ได้', target.line);
    }

    throw new VbaRuntimeError('ฝั่งซ้ายของ = ต้องเป็นตัวแปรหรือคุณสมบัติของออบเจ็กต์', target.line);
  }

  private currentWith(line: number): VbaValue {
    if (!this.withStack.length) {
      throw new VbaRuntimeError('ใช้ "." แบบย่อได้เฉพาะในบล็อก With ... End With เท่านั้น', line);
    }
    return this.withStack[this.withStack.length - 1];
  }

  private async evalArgs(args: Expr[]): Promise<VbaValue[]> {
    const out: VbaValue[] = [];
    for (const a of args) {
      out.push(a.kind === 'empty' ? null : await this.evaluate(a));
    }
    return out;
  }

  async evaluate(expr: Expr, asStatement = false): Promise<VbaValue> {
    switch (expr.kind) {
      case 'num':
        return expr.value;
      case 'str':
        return expr.value;
      case 'bool':
        return expr.value;
      case 'nothing':
      case 'empty':
        return null;

      case 'ident': {
        const local = this.lookup(expr.name);
        if (local !== undefined) return local;
        const konst = VB_CONSTANTS[expr.name];
        if (konst !== undefined) return konst;
        const global = this.globalObject(expr.name);
        if (global !== undefined) return global;
        const proc = this.program.procs.find((p) => p.name === expr.name);
        if (proc) return await this.callProc(proc, []);
        if (BUILTIN_NAMES.has(expr.name)) {
          return await this.callBuiltin(expr.name, [], expr.line, asStatement);
        }
        throw new VbaRuntimeError(
          `ไม่รู้จัก "${expr.raw}" — สะกดถูกไหม หรือยังไม่ได้ประกาศด้วย Dim?`,
          expr.line,
        );
      }

      case 'withMember': {
        const obj = this.currentWith(expr.line);
        if (!isObject(obj)) throw new VbaRuntimeError('With ต้องใช้กับออบเจ็กต์', expr.line);
        return this.readMember(obj, expr.name, expr.raw, expr.line);
      }

      case 'member': {
        const obj = await this.evaluate(expr.obj);
        if (!isObject(obj)) {
          throw new VbaRuntimeError(
            `"${exprToText(expr.obj)}" ไม่ใช่ออบเจ็กต์ เลยอ่าน .${expr.raw} ไม่ได้`,
            expr.line,
          );
        }
        return this.readMember(obj, expr.name, expr.raw, expr.line);
      }

      case 'unary': {
        if (expr.op === 'not') {
          const v = await this.evaluate(expr.expr);
          const p = toPrimitive(v);
          if (typeof p === 'number' && !Number.isInteger(p)) return !toBool(v);
          return typeof p === 'number' ? ~p : !toBool(v);
        }
        const n = toNumber(await this.evaluate(expr.expr));
        return expr.op === '-' ? -n : n;
      }

      case 'binary':
        return this.evalBinary(expr);

      case 'call': {
        const calleeExpr = expr.callee;

        // ฟังก์ชันที่ผู้ใช้เขียนเอง
        if (calleeExpr.kind === 'ident') {
          const local = this.lookup(calleeExpr.name);
          if (local instanceof VbaArray) {
            const args = await this.evalArgs(expr.args);
            return local.get(toNumber(args[0]));
          }
          const proc = this.program.procs.find((p) => p.name === calleeExpr.name);
          if (proc) {
            const args = await this.evalArgs(expr.args);
            return await this.callProc(proc, args);
          }
          if (local === undefined && BUILTIN_NAMES.has(calleeExpr.name)) {
            const args = await this.evalArgs(expr.args);
            return await this.callBuiltin(calleeExpr.name, args, expr.line, asStatement);
          }
        }

        const callee = await this.evaluate(calleeExpr);
        const args = await this.evalArgs(expr.args);
        if (callee instanceof VbaArray) return callee.get(toNumber(args[0]));
        if (isObject(callee) && callee.callSelf) return callee.callSelf(args);
        throw new VbaRuntimeError(`เรียกใช้ "${exprToText(calleeExpr)}" แบบฟังก์ชันไม่ได้`, expr.line);
      }
    }
  }

  private readMember(obj: VbaObject, name: string, raw: string, line: number): VbaValue {
    try {
      return obj.getMember(name);
    } catch (err) {
      if (err instanceof VbaRuntimeError) {
        err.line = err.line || line;
        if (!err.message.includes(raw)) {
          err.message = err.message.replace(name, raw);
        }
      }
      throw err;
    }
  }

  private async evalBinary(expr: Expr & { kind: 'binary' }): Promise<VbaValue> {
    const op = expr.op;

    if (op === 'and' || op === 'or' || op === 'xor') {
      const l = await this.evaluate(expr.left);
      const r = await this.evaluate(expr.right);
      const lp = toPrimitive(l);
      const rp = toPrimitive(r);
      if (typeof lp === 'number' && typeof rp === 'number' && Number.isInteger(lp) && Number.isInteger(rp)) {
        if (lp !== 0 && lp !== -1) {
          if (op === 'and') return lp & rp;
          if (op === 'or') return lp | rp;
          return lp ^ rp;
        }
      }
      const a = toBool(l);
      const b = toBool(r);
      if (op === 'and') return a && b;
      if (op === 'or') return a || b;
      return a !== b;
    }

    const left = await this.evaluate(expr.left);
    const right = await this.evaluate(expr.right);

    switch (op) {
      case '&':
        return toText(left) + toText(right);
      case '+': {
        const lp = toPrimitive(left);
        const rp = toPrimitive(right);
        if (typeof lp === 'string' && typeof rp === 'string') {
          const ln = Number(lp);
          const rn = Number(rp);
          if (lp !== '' && rp !== '' && !Number.isNaN(ln) && !Number.isNaN(rn)) return ln + rn;
          return lp + rp;
        }
        return toNumber(left) + toNumber(right);
      }
      case '-':
        return toNumber(left) - toNumber(right);
      case '*':
        return toNumber(left) * toNumber(right);
      case '/': {
        const d = toNumber(right);
        if (d === 0) throw new VbaRuntimeError('หารด้วยศูนย์ไม่ได้ (Division by zero)', expr.line);
        return toNumber(left) / d;
      }
      case '\\': {
        const d = toNumber(right);
        if (d === 0) throw new VbaRuntimeError('หารด้วยศูนย์ไม่ได้ (Division by zero)', expr.line);
        return Math.trunc(toNumber(left) / d);
      }
      case 'mod': {
        const d = toNumber(right);
        if (d === 0) throw new VbaRuntimeError('Mod ด้วยศูนย์ไม่ได้', expr.line);
        return toNumber(left) % d;
      }
      case '^':
        return Math.pow(toNumber(left), toNumber(right));
      case 'like':
        return likeMatch(toText(left), toText(right));
      case 'is':
        return left === right || (left === null && right === null);
      default:
        return compare(op, left, right);
    }
  }

  private globalObject(name: string): VbaValue | undefined {
    const host = this.bridge;
    switch (name) {
      case 'range':
        return new MethodObj('range', (args) =>
          new SheetObj(this.book.active, this.book, host).rangeFrom(args),
        );
      case 'cells':
        return new CellsAccessor(this.book.active, host, this.book);
      case 'rows':
        return new MethodObj('rows', (args) => {
          const i = toNumber(args[0] ?? 1);
          return new RangeObj(this.book.active, { row: i, col: 1, rows: 1, cols: MAX_COLS }, host, this.book);
        });
      case 'columns':
        return new MethodObj('columns', (args) => {
          const a = args[0];
          const i = typeof a === 'string' ? colToNum(a) : toNumber(a ?? 1);
          return new RangeObj(this.book.active, { row: 1, col: i, rows: MAX_ROWS, cols: 1 }, host, this.book);
        });
      case 'worksheets':
      case 'sheets':
        return new SheetsCollection(this.book, host);
      case 'activesheet':
        return new SheetObj(this.book.active, this.book, host);
      case 'thisworkbook':
      case 'activeworkbook':
        return new WorkbookObj(this.book, host);
      case 'application':
        return new ApplicationObj(this.book, host);
      case 'worksheetfunction':
        return new WorksheetFunctionObj();
      case 'debug':
        return new DebugObj(host);
      case 'selection':
        return new RangeObj(this.book.active, { row: 1, col: 1, rows: 1, cols: 1 }, host, this.book);
      default:
        return undefined;
    }
  }

  private async callBuiltin(
    name: string,
    args: VbaValue[],
    line: number,
    asStatement: boolean,
  ): Promise<VbaValue> {
    try {
      return await runBuiltin(name, args, {
        line,
        asStatement,
        host: this.host,
        bridge: this.bridge,
        book: this.book,
      });
    } catch (err) {
      if (err instanceof VbaRuntimeError && !err.line) err.line = line;
      throw err;
    }
  }
}

// ---------- ออบเจ็กต์ระดับ Application ----------

class ApplicationObj implements VbaObject {
  __obj = true as const;
  typeName = 'Application';
  constructor(private book: Workbook, private host: HostBridge) {}
  getMember(name: string): VbaValue {
    switch (name) {
      case 'worksheetfunction':
        return new WorksheetFunctionObj();
      case 'activesheet':
        return new SheetObj(this.book.active, this.book, this.host);
      case 'screenupdating':
      case 'displayalerts':
      case 'enableevents':
        return true;
      case 'calculation':
        return -4105;
      case 'wait':
      case 'calculate':
        return new MethodObj(name, () => null);
      default:
        return new MethodObj(name, () => null);
    }
  }
  setMember(): void {
    /* ScreenUpdating ฯลฯ — รับไว้เฉย ๆ */
  }
}

class DebugObj implements VbaObject {
  __obj = true as const;
  typeName = 'Debug';
  constructor(private host: HostBridge) {}
  getMember(name: string): VbaValue {
    if (name === 'print') {
      return new MethodObj('print', (args) => {
        this.host.print(args.map((a) => toText(a)).join(' '));
        return null;
      });
    }
    if (name === 'assert') return new MethodObj('assert', () => null);
    throw new VbaRuntimeError(`Debug ไม่มีเมธอด ${name}`);
  }
  setMember(): void {
    throw new VbaRuntimeError('กำหนดค่าให้ Debug ไม่ได้');
  }
}

class WorksheetFunctionObj implements VbaObject {
  __obj = true as const;
  typeName = 'WorksheetFunction';
  getMember(name: string): VbaValue {
    return new MethodObj(name, (args) => worksheetFunction(name, args));
  }
  setMember(): void {
    throw new VbaRuntimeError('กำหนดค่าให้ WorksheetFunction ไม่ได้');
  }
}

function numbersFrom(args: VbaValue[]): number[] {
  const out: number[] = [];
  const visit = (v: VbaValue) => {
    if (v === null || v === undefined) return;
    if (v instanceof VbaArray) {
      v.data.forEach(visit);
      return;
    }
    if (v instanceof RangeObj) {
      if (v.spec.rows * v.spec.cols > 1) {
        v.items().forEach(visit);
        return;
      }
    } else if (isObject(v) && v.items) {
      v.items().forEach(visit);
      return;
    }
    const p = toPrimitive(v);
    if (p === null || p === '') return;
    const n = Number(p);
    if (!Number.isNaN(n)) out.push(n);
  };
  args.forEach(visit);
  return out;
}

function worksheetFunction(name: string, args: VbaValue[]): VbaValue {
  const nums = numbersFrom(args);
  switch (name) {
    case 'sum':
      return nums.reduce((a, b) => a + b, 0);
    case 'average':
      if (!nums.length) throw new VbaRuntimeError('AVERAGE ต้องมีตัวเลขอย่างน้อย 1 ตัว');
      return nums.reduce((a, b) => a + b, 0) / nums.length;
    case 'max':
      return nums.length ? Math.max(...nums) : 0;
    case 'min':
      return nums.length ? Math.min(...nums) : 0;
    case 'count':
      return nums.length;
    case 'counta': {
      let c = 0;
      const visit = (v: VbaValue) => {
        if (v instanceof RangeObj) {
          if (v.spec.rows * v.spec.cols > 1) {
            v.items().forEach(visit);
            return;
          }
        } else if (isObject(v) && v.items) {
          v.items().forEach(visit);
          return;
        }
        const p = toPrimitive(v);
        if (p !== null && p !== '') c++;
      };
      args.forEach(visit);
      return c;
    }
    case 'round': {
      const f = Math.pow(10, toNumber(args[1] ?? 0));
      return Math.round(toNumber(args[0]) * f) / f;
    }
    case 'roundup': {
      const f = Math.pow(10, toNumber(args[1] ?? 0));
      return Math.ceil(toNumber(args[0]) * f) / f;
    }
    case 'rounddown': {
      const f = Math.pow(10, toNumber(args[1] ?? 0));
      return Math.floor(toNumber(args[0]) * f) / f;
    }
    case 'proper':
      return toText(args[0])
        .toLowerCase()
        .replace(/(^|\s)(\S)/g, (_m, a, b) => a + b.toUpperCase());
    case 'trim':
      return toText(args[0]).trim().replace(/\s+/g, ' ');
    case 'large': {
      const k = toNumber(args[1] ?? 1);
      return [...nums].sort((a, b) => b - a)[k - 1] ?? 0;
    }
    case 'small': {
      const k = toNumber(args[1] ?? 1);
      return [...nums].sort((a, b) => a - b)[k - 1] ?? 0;
    }
    default:
      throw new VbaRuntimeError(`WorksheetFunction.${name} ยังไม่รองรับในสนามซ้อมนี้`);
  }
}

// ---------- ฟังก์ชันในตัวของ VBA ----------

interface BuiltinCtx {
  line: number;
  asStatement: boolean;
  host: RunHost;
  bridge: HostBridge;
  book: Workbook;
}

const BUILTIN_NAMES = new Set([
  'msgbox', 'inputbox', 'len', 'left', 'right', 'mid', 'ucase', 'lcase', 'trim',
  'ltrim', 'rtrim', 'instr', 'instrrev', 'replace', 'split', 'join', 'cstr', 'cint',
  'clng', 'cdbl', 'csng', 'cbool', 'val', 'abs', 'int', 'fix', 'round', 'sqr', 'rnd',
  'randomize', 'now', 'date', 'time', 'year', 'month', 'day', 'hour', 'minute', 'second',
  'weekday', 'dateadd', 'datediff', 'format', 'isnumeric', 'isempty', 'isnull', 'isarray',
  'isdate', 'array', 'ubound', 'lbound', 'chr', 'asc', 'space', 'string', 'strreverse',
  'rgb', 'iif', 'typename', 'sgn', 'exp', 'log', 'timer', 'strcomp', 'cdate',
]);

async function runBuiltin(
  name: string,
  args: VbaValue[],
  ctx: BuiltinCtx,
): Promise<VbaValue> {
  const a = (i: number) => args[i];
  switch (name) {
    case 'msgbox': {
      const text = toText(a(0));
      const title = args.length > 2 ? toText(a(2)) : 'Microsoft Excel';
      if (ctx.host.onMsgBox) await ctx.host.onMsgBox(text, title);
      else ctx.bridge.print(`[MsgBox] ${text}`);
      return 1;
    }
    case 'inputbox': {
      const prompt = toText(a(0));
      const title = args.length > 1 ? toText(a(1)) : 'Microsoft Excel';
      const def = args.length > 2 ? toText(a(2)) : '';
      if (!ctx.host.onInputBox) return def;
      const result = await ctx.host.onInputBox(prompt, title, def);
      return result ?? '';
    }
    case 'len':
      return toText(a(0)).length;
    case 'left':
      return toText(a(0)).slice(0, Math.max(0, toNumber(a(1))));
    case 'right': {
      const n = Math.max(0, toNumber(a(1)));
      const s = toText(a(0));
      return n === 0 ? '' : s.slice(Math.max(0, s.length - n));
    }
    case 'mid': {
      const s = toText(a(0));
      const start = Math.max(1, toNumber(a(1)));
      if (args.length < 3 || a(2) === null) return s.slice(start - 1);
      return s.substr(start - 1, Math.max(0, toNumber(a(2))));
    }
    case 'ucase':
      return toText(a(0)).toUpperCase();
    case 'lcase':
      return toText(a(0)).toLowerCase();
    case 'trim':
      return toText(a(0)).trim();
    case 'ltrim':
      return toText(a(0)).replace(/^\s+/, '');
    case 'rtrim':
      return toText(a(0)).replace(/\s+$/, '');
    case 'instr': {
      // InStr([start,] haystack, needle)
      let start = 1;
      let hay: string;
      let needle: string;
      if (args.length >= 3 && typeof toPrimitive(a(0)) === 'number') {
        start = toNumber(a(0));
        hay = toText(a(1));
        needle = toText(a(2));
      } else {
        hay = toText(a(0));
        needle = toText(a(1));
      }
      return hay.indexOf(needle, Math.max(0, start - 1)) + 1;
    }
    case 'instrrev':
      return toText(a(0)).lastIndexOf(toText(a(1))) + 1;
    case 'replace':
      return toText(a(0)).split(toText(a(1))).join(toText(a(2)));
    case 'split': {
      const sep = args.length > 1 ? toText(a(1)) : ' ';
      const parts = toText(a(0)).split(sep);
      const arr = new VbaArray(0, parts.length - 1);
      parts.forEach((p, i) => (arr.data[i] = p));
      return arr;
    }
    case 'join': {
      const arr = a(0);
      const sep = args.length > 1 ? toText(a(1)) : ' ';
      const items = arr instanceof VbaArray ? arr.data : collectionItems(arr);
      return items.map((x) => toText(x)).join(sep);
    }
    case 'cstr':
      return toText(a(0));
    case 'cint':
    case 'clng': {
      const n = toNumber(a(0));
      // VBA ปัดแบบ banker's rounding
      const floor = Math.floor(n);
      const diff = n - floor;
      if (Math.abs(diff - 0.5) < 1e-9) return floor % 2 === 0 ? floor : floor + 1;
      return Math.round(n);
    }
    case 'cdbl':
    case 'csng':
    case 'val': {
      if (name === 'val') {
        const m = /^\s*[-+]?(\d+(\.\d*)?|\.\d+)/.exec(toText(a(0)));
        return m ? Number(m[0]) : 0;
      }
      return toNumber(a(0));
    }
    case 'cbool':
      return toBool(a(0));
    case 'cdate':
      return toText(a(0));
    case 'abs':
      return Math.abs(toNumber(a(0)));
    case 'int':
      return Math.floor(toNumber(a(0)));
    case 'fix':
      return Math.trunc(toNumber(a(0)));
    case 'sgn':
      return Math.sign(toNumber(a(0)));
    case 'exp':
      return Math.exp(toNumber(a(0)));
    case 'log':
      return Math.log(toNumber(a(0)));
    case 'round': {
      const digits = args.length > 1 ? toNumber(a(1)) : 0;
      const f = Math.pow(10, digits);
      const v = toNumber(a(0)) * f;
      const floor = Math.floor(v);
      const diff = v - floor;
      const rounded =
        Math.abs(diff - 0.5) < 1e-9 ? (floor % 2 === 0 ? floor : floor + 1) : Math.round(v);
      return rounded / f;
    }
    case 'sqr': {
      const n = toNumber(a(0));
      if (n < 0) throw new VbaRuntimeError('Sqr ของเลขติดลบไม่ได้');
      return Math.sqrt(n);
    }
    case 'rnd':
      return Math.random();
    case 'randomize':
      return null;
    case 'timer':
      return Math.floor(Date.now() / 1000) % 86400;
    case 'now':
      return formatDate(new Date(), 'dd/mm/yyyy hh:nn:ss');
    case 'date':
      return formatDate(new Date(), 'dd/mm/yyyy');
    case 'time':
      return formatDate(new Date(), 'hh:nn:ss');
    case 'year':
      return parseDateLike(a(0)).getFullYear();
    case 'month':
      return parseDateLike(a(0)).getMonth() + 1;
    case 'day':
      return parseDateLike(a(0)).getDate();
    case 'hour':
      return parseDateLike(a(0)).getHours();
    case 'minute':
      return parseDateLike(a(0)).getMinutes();
    case 'second':
      return parseDateLike(a(0)).getSeconds();
    case 'weekday':
      return parseDateLike(a(0)).getDay() + 1;
    case 'dateadd': {
      const interval = toText(a(0)).toLowerCase();
      const n = toNumber(a(1));
      const d = parseDateLike(a(2));
      const copy = new Date(d.getTime());
      if (interval === 'd') copy.setDate(copy.getDate() + n);
      else if (interval === 'm') copy.setMonth(copy.getMonth() + n);
      else if (interval === 'yyyy') copy.setFullYear(copy.getFullYear() + n);
      else if (interval === 'h') copy.setHours(copy.getHours() + n);
      else copy.setDate(copy.getDate() + n);
      return formatDate(copy, 'dd/mm/yyyy');
    }
    case 'datediff': {
      const d1 = parseDateLike(a(1));
      const d2 = parseDateLike(a(2));
      return Math.round((d2.getTime() - d1.getTime()) / 86400000);
    }
    case 'format':
      return formatValue(a(0), args.length > 1 ? toText(a(1)) : '');
    case 'isnumeric': {
      const p = toPrimitive(a(0));
      if (p === null || p === '') return false;
      if (typeof p === 'number') return true;
      return !Number.isNaN(Number(String(p).trim()));
    }
    case 'isempty': {
      const v = a(0);
      if (v === null || v === undefined) return true;
      const p = toPrimitive(v);
      return p === null || p === '';
    }
    case 'isnull':
      return a(0) === null;
    case 'isarray':
      return a(0) instanceof VbaArray;
    case 'isdate':
      return !Number.isNaN(parseDateLike(a(0)).getTime());
    case 'array': {
      const arr = new VbaArray(0, args.length - 1);
      args.forEach((v, i) => (arr.data[i] = v));
      return arr;
    }
    case 'ubound': {
      const v = a(0);
      if (v instanceof VbaArray) return v.upper;
      throw new VbaRuntimeError('UBound ใช้กับอาร์เรย์เท่านั้น');
    }
    case 'lbound': {
      const v = a(0);
      if (v instanceof VbaArray) return v.lower;
      throw new VbaRuntimeError('LBound ใช้กับอาร์เรย์เท่านั้น');
    }
    case 'chr':
      return String.fromCharCode(toNumber(a(0)));
    case 'asc':
      return toText(a(0)).charCodeAt(0) || 0;
    case 'space':
      return ' '.repeat(Math.max(0, toNumber(a(0))));
    case 'string':
      return toText(a(1)).charAt(0).repeat(Math.max(0, toNumber(a(0))));
    case 'strreverse':
      return [...toText(a(0))].reverse().join('');
    case 'strcomp': {
      const x = toText(a(0));
      const y = toText(a(1));
      return x === y ? 0 : x < y ? -1 : 1;
    }
    case 'rgb': {
      const r = Math.min(255, Math.max(0, toNumber(a(0))));
      const g = Math.min(255, Math.max(0, toNumber(a(1))));
      const b = Math.min(255, Math.max(0, toNumber(a(2))));
      return r + g * 256 + b * 65536;
    }
    case 'iif':
      return toBool(a(0)) ? a(1) ?? null : a(2) ?? null;
    case 'typename': {
      const v = a(0);
      if (v === null) return 'Empty';
      if (v instanceof VbaArray) return 'Variant()';
      if (isObject(v)) return v.typeName;
      if (typeof v === 'number') return Number.isInteger(v) ? 'Long' : 'Double';
      if (typeof v === 'boolean') return 'Boolean';
      return 'String';
    }
    default:
      throw new VbaRuntimeError(`ยังไม่รองรับฟังก์ชัน "${name}" ในสนามซ้อมนี้`, ctx.line);
  }
}

function parseDateLike(v: VbaValue | undefined): Date {
  const p = toPrimitive(v);
  if (p === null || p === '') return new Date();
  if (typeof p === 'number') return new Date(Date.UTC(1899, 11, 30) + p * 86400000);
  const text = String(p);
  const m = /^(\d{1,2})\/(\d{1,2})\/(\d{4})/.exec(text);
  if (m) return new Date(Number(m[3]), Number(m[2]) - 1, Number(m[1]));
  const d = new Date(text);
  return Number.isNaN(d.getTime()) ? new Date() : d;
}

function pad(n: number, len = 2) {
  return String(n).padStart(len, '0');
}

function formatDate(d: Date, fmt: string): string {
  return fmt
    .replace(/yyyy/gi, String(d.getFullYear()))
    .replace(/mm/g, pad(d.getMonth() + 1))
    .replace(/dd/gi, pad(d.getDate()))
    .replace(/hh/gi, pad(d.getHours()))
    .replace(/nn/gi, pad(d.getMinutes()))
    .replace(/ss/gi, pad(d.getSeconds()));
}

function formatValue(v: VbaValue | undefined, fmt: string): string {
  const p = toPrimitive(v);
  if (!fmt) return toText(v);
  const lower = fmt.toLowerCase();
  if (typeof p === 'number' || (typeof p === 'string' && p !== '' && !Number.isNaN(Number(p)))) {
    const n = Number(p);
    if (lower.includes('%')) {
      const decimals = (/0\.(0+)%/.exec(lower)?.[1].length) ?? 0;
      return `${(n * 100).toFixed(decimals)}%`;
    }
    if (lower.includes('#,##0')) {
      const decimals = (/#,##0\.(0+)/.exec(lower)?.[1].length) ?? 0;
      return n.toLocaleString('en-US', {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      });
    }
    const decMatch = /^0\.(0+)$/.exec(lower);
    if (decMatch) return n.toFixed(decMatch[1].length);
    if (lower === '0') return String(Math.round(n));
    if (/currency|บาท/.test(lower)) return `฿${n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }
  if (/[dmyhns]/.test(lower) && /[/\-: ]/.test(fmt)) {
    return formatDate(parseDateLike(v), fmt);
  }
  return toText(v);
}

function defaultForType(type?: string): VbaValue {
  switch ((type ?? '').toLowerCase()) {
    case 'integer':
    case 'long':
    case 'double':
    case 'single':
      return 0;
    case 'string':
      return '';
    case 'boolean':
      return false;
    default:
      return null;
  }
}

function collectionItems(v: VbaValue): VbaValue[] {
  if (v instanceof VbaArray) return [...v.data];
  if (Array.isArray(v)) return v;
  if (isObject(v) && v.items) return v.items();
  throw new VbaRuntimeError('For Each ต้องใช้กับอาร์เรย์หรือช่วงเซลล์');
}

function looseEquals(a: VbaValue, b: VbaValue): boolean {
  const pa = toPrimitive(a);
  const pb = toPrimitive(b);
  if (typeof pa === 'string' || typeof pb === 'string') {
    if (typeof pa === 'number' || typeof pb === 'number') {
      const na = Number(pa);
      const nb = Number(pb);
      if (!Number.isNaN(na) && !Number.isNaN(nb)) return na === nb;
    }
    return String(pa ?? '') === String(pb ?? '');
  }
  return pa === pb;
}

function compare(op: string, left: VbaValue, right: VbaValue): boolean {
  const lp = toPrimitive(left);
  const rp = toPrimitive(right);
  let a: number | string;
  let b: number | string;
  const bothNumeric =
    (typeof lp === 'number' || typeof lp === 'boolean' || lp === null || (typeof lp === 'string' && lp !== '' && !Number.isNaN(Number(lp)))) &&
    (typeof rp === 'number' || typeof rp === 'boolean' || rp === null || (typeof rp === 'string' && rp !== '' && !Number.isNaN(Number(rp))));

  if (bothNumeric) {
    a = toNumber(left);
    b = toNumber(right);
  } else {
    a = typeof lp === 'boolean' ? (lp ? 'True' : 'False') : String(lp ?? '');
    b = typeof rp === 'boolean' ? (rp ? 'True' : 'False') : String(rp ?? '');
  }

  switch (op) {
    case '=': return a === b;
    case '<>': return a !== b;
    case '<': return a < b;
    case '>': return a > b;
    case '<=': return a <= b;
    case '>=': return a >= b;
    default: throw new VbaRuntimeError(`ตัวดำเนินการ "${op}" ไม่รู้จัก`);
  }
}

function likeMatch(value: string, pattern: string): boolean {
  let regex = '';
  for (const ch of pattern) {
    if (ch === '*') regex += '.*';
    else if (ch === '?') regex += '.';
    else if (ch === '#') regex += '\\d';
    else regex += ch.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }
  return new RegExp(`^${regex}$`, 'i').test(value);
}

function colToNum(letters: string): number {
  let n = 0;
  for (const ch of letters.toUpperCase()) n = n * 26 + (ch.charCodeAt(0) - 64);
  return n;
}

function exprToText(expr: Expr): string {
  switch (expr.kind) {
    case 'ident': return expr.raw;
    case 'member': return `${exprToText(expr.obj)}.${expr.raw}`;
    case 'withMember': return `.${expr.raw}`;
    case 'call': return `${exprToText(expr.callee)}(...)`;
    case 'str': return `"${expr.value}"`;
    case 'num': return String(expr.value);
    default: return 'นิพจน์';
  }
}

export { parseRangeAddress, longToCss };
export { VbaSyntaxError } from './lexer';
export { VbaRuntimeError } from './objects';
