import { Token, tokenize, VbaSyntaxError } from './lexer';
import type { CaseTest, Expr, Param, ProcDecl, Program, Stmt, VarDecl } from './ast';

const TYPE_KEYWORDS = new Set([
  'integer', 'long', 'double', 'single', 'string', 'boolean', 'variant',
  'object', 'date', 'range', 'worksheet', 'workbook',
]);

export function parse(source: string): Program {
  const tokens = tokenize(source);
  return new Parser(tokens).parseProgram();
}

class Parser {
  private pos = 0;
  constructor(private tokens: Token[]) {}

  private get cur(): Token {
    return this.tokens[this.pos];
  }

  private peek(offset = 1): Token {
    return this.tokens[Math.min(this.pos + offset, this.tokens.length - 1)];
  }

  private advance(): Token {
    const t = this.tokens[this.pos];
    if (t.type !== 'eof') this.pos++;
    return t;
  }

  private at(type: Token['type'], value?: string): boolean {
    return this.cur.type === type && (value === undefined || this.cur.value === value);
  }

  private atKeyword(...values: string[]): boolean {
    return this.cur.type === 'keyword' && values.includes(this.cur.value);
  }

  private eat(type: Token['type'], value?: string): boolean {
    if (this.at(type, value)) {
      this.advance();
      return true;
    }
    return false;
  }

  private expect(type: Token['type'], value?: string): Token {
    if (!this.at(type, value)) {
      throw new VbaSyntaxError(
        `คาดว่าจะเจอ "${value ?? type}" แต่เจอ "${this.cur.raw || this.cur.value || 'จบบรรทัด'}" แทน`,
        this.cur.line,
      );
    }
    return this.advance();
  }

  private skipNewlines() {
    while (this.at('newline')) this.advance();
  }

  private endOfStatement() {
    if (this.at('eof')) return;
    if (this.at('newline')) {
      this.advance();
      return;
    }
    throw new VbaSyntaxError(
      `ไม่เข้าใจส่วนที่เขียนต่อท้าย: "${this.cur.raw || this.cur.value}"`,
      this.cur.line,
    );
  }

  parseProgram(): Program {
    const procs: ProcDecl[] = [];
    const moduleBody: Stmt[] = [];

    this.skipNewlines();
    while (!this.at('eof')) {
      // ตัวขยายขอบเขต
      if (this.atKeyword('public', 'private')) this.advance();

      if (this.atKeyword('option')) {
        while (!this.at('newline') && !this.at('eof')) this.advance();
        this.skipNewlines();
        continue;
      }

      if (this.atKeyword('sub', 'function')) {
        procs.push(this.parseProc());
      } else {
        const stmt = this.parseStatement();
        if (stmt) moduleBody.push(stmt);
      }
      this.skipNewlines();
    }

    return { procs, moduleBody };
  }

  private parseProc(): ProcDecl {
    const startToken = this.advance(); // sub | function
    const kind = startToken.value === 'sub' ? 'sub' : 'function';
    const nameToken = this.cur;
    if (nameToken.type !== 'ident' && nameToken.type !== 'keyword') {
      throw new VbaSyntaxError('ต้องตั้งชื่อ Sub/Function ด้วยนะ', nameToken.line);
    }
    this.advance();

    const params: Param[] = [];
    if (this.eat('op', '(')) {
      while (!this.at('op', ')')) {
        params.push(this.parseParam());
        if (!this.eat('op', ',')) break;
      }
      this.expect('op', ')');
    }
    // ชนิดค่าที่คืน: As Double
    if (this.atKeyword('as')) {
      this.advance();
      this.parseTypeName();
    }
    this.endOfStatement();

    const body = this.parseBlock(() => this.atEndOf(kind));
    this.expect('keyword', 'end');
    this.advance(); // sub | function
    if (!this.at('eof')) this.endOfStatement();

    return {
      kind,
      name: nameToken.value.replace(/[$%&!#@]$/, ''),
      raw: nameToken.raw,
      params,
      body,
      line: startToken.line,
    };
  }

  private atEndOf(kind: string) {
    return (
      this.atKeyword('end') &&
      this.peek().type === 'keyword' &&
      this.peek().value === kind
    );
  }

  private parseParam(): Param {
    let byVal = true;
    let optional = false;
    if (this.atKeyword('optional')) {
      optional = true;
      this.advance();
    }
    if (this.atKeyword('byval')) {
      byVal = true;
      this.advance();
    } else if (this.atKeyword('byref')) {
      byVal = false;
      this.advance();
    }
    const nameToken = this.advance();
    let isArray = false;
    if (this.at('op', '(') && this.peek().type === 'op' && this.peek().value === ')') {
      this.advance();
      this.advance();
      isArray = true;
    }
    if (this.atKeyword('as')) {
      this.advance();
      this.parseTypeName();
    }
    let defaultValue: Expr | null = null;
    if (this.eat('op', '=')) defaultValue = this.parseExpr();

    return {
      name: nameToken.value.replace(/[$%&!#@]$/, ''),
      raw: nameToken.raw,
      byVal,
      optional,
      defaultValue,
      isArray,
    };
  }

  private parseTypeName(): string {
    const t = this.advance();
    let name = t.value;
    // เช่น Excel.Range
    while (this.at('op', '.')) {
      this.advance();
      name = this.advance().value;
    }
    return name;
  }

  private parseBlock(isEnd: () => boolean): Stmt[] {
    const body: Stmt[] = [];
    this.skipNewlines();
    while (!this.at('eof') && !isEnd()) {
      const stmt = this.parseStatement();
      if (stmt) body.push(stmt);
      this.skipNewlines();
    }
    if (this.at('eof') && !isEnd()) {
      throw new VbaSyntaxError('โค้ดจบก่อนที่จะปิดบล็อก (ลืมใส่ End If / Next / Loop หรือเปล่า?)', this.cur.line);
    }
    return body;
  }

  private parseStatement(): Stmt | null {
    const t = this.cur;
    const line = t.line;

    if (this.at('newline')) {
      this.advance();
      return null;
    }

    if (t.type === 'keyword') {
      switch (t.value) {
        case 'public':
        case 'private':
          this.advance();
          return this.parseStatement();
        case 'dim':
          return this.parseDim();
        case 'redim':
          return this.parseReDim();
        case 'const':
          return this.parseConst();
        case 'set':
        case 'let':
          this.advance();
          return this.parseAssignOrCall();
        case 'if':
          return this.parseIf();
        case 'for':
          return this.parseFor();
        case 'do':
          return this.parseDo();
        case 'while':
          return this.parseWhile();
        case 'select':
          return this.parseSelect();
        case 'with':
          return this.parseWith();
        case 'exit':
          return this.parseExit();
        case 'call': {
          this.advance();
          const expr = this.parseExpr();
          this.endOfStatement();
          return { kind: 'exprStmt', expr, line };
        }
        case 'on':
          return this.parseOnError();
        case 'end':
          throw new VbaSyntaxError('เจอ End ที่ไม่มีบล็อกให้ปิด', line);
      }
    }

    return this.parseAssignOrCall();
  }

  private parseDim(): Stmt {
    const line = this.advance().line;
    const vars = this.parseVarDecls();
    this.endOfStatement();
    return { kind: 'dim', vars, line };
  }

  private parseReDim(): Stmt {
    const line = this.advance().line;
    let preserve = false;
    if (this.atKeyword('preserve')) {
      preserve = true;
      this.advance();
    }
    const vars = this.parseVarDecls();
    this.endOfStatement();
    return { kind: 'redim', preserve, vars, line };
  }

  private parseVarDecls(): VarDecl[] {
    const vars: VarDecl[] = [];
    do {
      const nameToken = this.advance();
      if (nameToken.type !== 'ident' && nameToken.type !== 'keyword') {
        throw new VbaSyntaxError('ชื่อตัวแปรไม่ถูกต้อง', nameToken.line);
      }
      const decl: VarDecl = {
        name: nameToken.value.replace(/[$%&!#@]$/, ''),
        raw: nameToken.raw,
      };
      if (this.at('op', '(')) {
        this.advance();
        decl.dims = [];
        if (!this.at('op', ')')) {
          do {
            const first = this.parseExpr();
            if (this.atKeyword('to')) {
              this.advance();
              decl.dims.push({ lower: first, upper: this.parseExpr() });
            } else {
              decl.dims.push({ upper: first });
            }
          } while (this.eat('op', ','));
        }
        this.expect('op', ')');
      }
      if (this.atKeyword('as')) {
        this.advance();
        if (this.atKeyword('new')) this.advance();
        decl.type = this.parseTypeName();
      }
      vars.push(decl);
    } while (this.eat('op', ','));
    return vars;
  }

  private parseConst(): Stmt {
    const line = this.advance().line;
    const nameToken = this.advance();
    if (this.atKeyword('as')) {
      this.advance();
      this.parseTypeName();
    }
    this.expect('op', '=');
    const value = this.parseExpr();
    this.endOfStatement();
    return {
      kind: 'const',
      name: nameToken.value.replace(/[$%&!#@]$/, ''),
      raw: nameToken.raw,
      value,
      line,
    };
  }

  private parseAssignOrCall(): Stmt {
    const line = this.cur.line;
    const start = this.pos;

    // ลองอ่านฝั่งซ้ายแบบ "เป้าหมาย" ก่อน (ไม่กิน "=" เพราะจะกลายเป็นการเปรียบเทียบ)
    let target: Expr | null = null;
    try {
      target = this.parsePostfix();
    } catch {
      target = null;
    }

    if (target && this.at('op', '=') && this.isAssignable(target)) {
      this.advance();
      const value = this.parseExpr();
      this.endOfStatement();
      return { kind: 'assign', target, value, line };
    }

    this.pos = start;

    // คำสั่งเรียกแบบไม่มีวงเล็บ: MsgBox "hi"  /  Debug.Print x
    const callee = this.parseCallTarget();
    if (this.at('newline') || this.at('eof')) {
      this.endOfStatement();
      return { kind: 'exprStmt', expr: callee, line };
    }
    if (this.at('op', '(')) {
      this.pos = start;
      const expr = this.parseExpr();
      this.endOfStatement();
      return { kind: 'exprStmt', expr, line };
    }
    if (!this.isCallableTarget(callee)) {
      throw new VbaSyntaxError(
        `ไม่เข้าใจคำสั่งตรง "${this.cur.raw || this.cur.value}"`,
        this.cur.line,
      );
    }
    const args: Expr[] = [];
    do {
      if (this.at('op', ',')) {
        args.push({ kind: 'empty', line });
        continue;
      }
      if (this.at('newline') || this.at('eof')) break;
      args.push(this.parseExpr());
    } while (this.eat('op', ','));
    this.endOfStatement();
    return { kind: 'exprStmt', expr: { kind: 'call', callee, args, line }, line };
  }

  private isAssignable(expr: Expr) {
    return (
      expr.kind === 'ident' ||
      expr.kind === 'member' ||
      expr.kind === 'withMember' ||
      expr.kind === 'call'
    );
  }

  private isCallableTarget(expr: Expr) {
    return expr.kind === 'ident' || expr.kind === 'member' || expr.kind === 'withMember';
  }

  /** อ่าน callee ของการเรียกแบบไม่มีวงเล็บ (หยุดก่อนถึง argument) */
  private parseCallTarget(): Expr {
    const line = this.cur.line;
    let node: Expr;
    if (this.at('op', '.')) {
      this.advance();
      const n = this.advance();
      node = { kind: 'withMember', name: n.value, raw: n.raw, line };
    } else {
      const n = this.advance();
      node = { kind: 'ident', name: n.value, raw: n.raw, line };
    }
    while (this.at('op', '.')) {
      this.advance();
      const n = this.advance();
      node = { kind: 'member', obj: node, name: n.value, raw: n.raw, line };
    }
    return node;
  }

  private parseIf(): Stmt {
    const line = this.advance().line; // if
    const cond = this.parseExpr();
    this.expect('keyword', 'then');

    // แบบบรรทัดเดียว: If x > 1 Then y = 2 [Else z = 3]
    if (!this.at('newline') && !this.at('eof')) {
      const body: Stmt[] = [];
      const thenStmt = this.parseInlineStatement();
      if (thenStmt) body.push(thenStmt);
      let elseBody: Stmt[] | null = null;
      if (this.atKeyword('else')) {
        this.advance();
        elseBody = [];
        const elseStmt = this.parseInlineStatement();
        if (elseStmt) elseBody.push(elseStmt);
      }
      if (this.at('newline')) this.advance();
      return { kind: 'if', branches: [{ cond, body }], elseBody, line };
    }

    this.endOfStatement();
    const branches: { cond: Expr; body: Stmt[] }[] = [];
    let elseBody: Stmt[] | null = null;
    let currentCond = cond;

    for (;;) {
      const body = this.parseBlock(
        () => this.atKeyword('elseif', 'else') || this.atEndOfBlock('if'),
      );
      branches.push({ cond: currentCond, body });

      if (this.atKeyword('elseif')) {
        this.advance();
        currentCond = this.parseExpr();
        this.expect('keyword', 'then');
        this.endOfStatement();
        continue;
      }
      if (this.atKeyword('else')) {
        this.advance();
        this.endOfStatement();
        elseBody = this.parseBlock(() => this.atEndOfBlock('if'));
      }
      break;
    }

    this.expect('keyword', 'end');
    this.expect('keyword', 'if');
    this.endOfStatement();
    return { kind: 'if', branches, elseBody, line };
  }

  private parseInlineStatement(): Stmt | null {
    // คำสั่งเดี่ยวหลัง Then / Else (ไม่กิน newline)
    const saved = this.pos;
    try {
      return this.parseStatement();
    } catch (err) {
      this.pos = saved;
      throw err;
    }
  }

  private atEndOfBlock(kind: string) {
    return (
      this.atKeyword('end') && this.peek().type === 'keyword' && this.peek().value === kind
    );
  }

  private parseFor(): Stmt {
    const line = this.advance().line; // for

    if (this.atKeyword('each')) {
      this.advance();
      const nameToken = this.advance();
      this.expect('keyword', 'in');
      const coll = this.parseExpr();
      this.endOfStatement();
      const body = this.parseBlock(() => this.atKeyword('next'));
      this.expect('keyword', 'next');
      if (this.cur.type === 'ident') this.advance();
      this.endOfStatement();
      return {
        kind: 'forEach',
        varName: nameToken.value.replace(/[$%&!#@]$/, ''),
        raw: nameToken.raw,
        coll,
        body,
        line,
      };
    }

    const nameToken = this.advance();
    if (this.atKeyword('as')) {
      this.advance();
      this.parseTypeName();
    }
    this.expect('op', '=');
    const from = this.parseExpr();
    this.expect('keyword', 'to');
    const to = this.parseExpr();
    let step: Expr | null = null;
    if (this.atKeyword('step')) {
      this.advance();
      step = this.parseExpr();
    }
    this.endOfStatement();
    const body = this.parseBlock(() => this.atKeyword('next'));
    this.expect('keyword', 'next');
    while (this.cur.type === 'ident') {
      this.advance();
      if (!this.eat('op', ',')) break;
    }
    this.endOfStatement();
    return {
      kind: 'for',
      varName: nameToken.value.replace(/[$%&!#@]$/, ''),
      raw: nameToken.raw,
      from,
      to,
      step,
      body,
      line,
    };
  }

  private parseDo(): Stmt {
    const line = this.advance().line; // do
    let pre: { type: 'while' | 'until'; cond: Expr } | null = null;
    if (this.atKeyword('while', 'until')) {
      const type = this.advance().value as 'while' | 'until';
      pre = { type, cond: this.parseExpr() };
    }
    this.endOfStatement();
    const body = this.parseBlock(() => this.atKeyword('loop'));
    this.expect('keyword', 'loop');
    let post: { type: 'while' | 'until'; cond: Expr } | null = null;
    if (this.atKeyword('while', 'until')) {
      const type = this.advance().value as 'while' | 'until';
      post = { type, cond: this.parseExpr() };
    }
    this.endOfStatement();
    return { kind: 'do', pre, post, body, line };
  }

  private parseWhile(): Stmt {
    const line = this.advance().line;
    const cond = this.parseExpr();
    this.endOfStatement();
    const body = this.parseBlock(() => this.atKeyword('wend'));
    this.expect('keyword', 'wend');
    this.endOfStatement();
    return { kind: 'while', cond, body, line };
  }

  private parseSelect(): Stmt {
    const line = this.advance().line; // select
    this.expect('keyword', 'case');
    const subject = this.parseExpr();
    this.endOfStatement();
    this.skipNewlines();

    const cases: { tests: CaseTest[]; body: Stmt[] }[] = [];
    let elseBody: Stmt[] | null = null;

    while (this.atKeyword('case')) {
      this.advance();
      if (this.atKeyword('else')) {
        this.advance();
        this.endOfStatement();
        elseBody = this.parseBlock(() => this.atEndOfBlock('select') || this.atKeyword('case'));
        break;
      }
      const tests: CaseTest[] = [];
      do {
        if (this.atKeyword('is')) {
          this.advance();
          const op = this.advance().value;
          tests.push({ kind: 'compare', op, expr: this.parseExpr() });
        } else {
          const first = this.parseExpr();
          if (this.atKeyword('to')) {
            this.advance();
            tests.push({ kind: 'range', from: first, to: this.parseExpr() });
          } else {
            tests.push({ kind: 'value', expr: first });
          }
        }
      } while (this.eat('op', ','));
      this.endOfStatement();
      const body = this.parseBlock(() => this.atKeyword('case') || this.atEndOfBlock('select'));
      cases.push({ tests, body });
    }

    this.expect('keyword', 'end');
    this.expect('keyword', 'select');
    this.endOfStatement();
    return { kind: 'select', subject, cases, elseBody, line };
  }

  private parseWith(): Stmt {
    const line = this.advance().line;
    const subject = this.parseExpr();
    this.endOfStatement();
    const body = this.parseBlock(() => this.atEndOfBlock('with'));
    this.expect('keyword', 'end');
    this.expect('keyword', 'with');
    this.endOfStatement();
    return { kind: 'with', subject, body, line };
  }

  private parseExit(): Stmt {
    const line = this.advance().line;
    const what = this.advance().value;
    this.endOfStatement();
    if (what === 'for' || what === 'do' || what === 'sub' || what === 'function' || what === 'while') {
      return { kind: 'exit', what, line };
    }
    throw new VbaSyntaxError(`Exit ${what} ยังไม่รองรับ`, line);
  }

  private parseOnError(): Stmt {
    const line = this.advance().line; // on
    this.expect('keyword', 'error');
    if (this.atKeyword('resume')) {
      this.advance();
      if (this.cur.type === 'ident' || this.cur.type === 'keyword') this.advance();
      this.endOfStatement();
      return { kind: 'onError', mode: 'resumeNext', line };
    }
    if (this.atKeyword('goto')) {
      this.advance();
      this.advance();
      this.endOfStatement();
      return { kind: 'onError', mode: 'goto0', line };
    }
    while (!this.at('newline') && !this.at('eof')) this.advance();
    this.endOfStatement();
    return { kind: 'noop', line };
  }

  // ---------- expressions ----------

  parseExpr(): Expr {
    return this.parseOr();
  }

  private parseOr(): Expr {
    let left = this.parseAnd();
    while (this.atKeyword('or', 'xor')) {
      const op = this.advance();
      const right = this.parseAnd();
      left = { kind: 'binary', op: op.value, left, right, line: op.line };
    }
    return left;
  }

  private parseAnd(): Expr {
    let left = this.parseNot();
    while (this.atKeyword('and')) {
      const op = this.advance();
      const right = this.parseNot();
      left = { kind: 'binary', op: 'and', left, right, line: op.line };
    }
    return left;
  }

  private parseNot(): Expr {
    if (this.atKeyword('not')) {
      const op = this.advance();
      return { kind: 'unary', op: 'not', expr: this.parseNot(), line: op.line };
    }
    return this.parseComparison();
  }

  private parseComparison(): Expr {
    let left = this.parseConcat();
    while (
      (this.cur.type === 'op' && ['=', '<>', '<', '>', '<=', '>='].includes(this.cur.value)) ||
      this.atKeyword('like', 'is')
    ) {
      const op = this.advance();
      const right = this.parseConcat();
      left = { kind: 'binary', op: op.value, left, right, line: op.line };
    }
    return left;
  }

  private parseConcat(): Expr {
    let left = this.parseAdditive();
    while (this.at('op', '&')) {
      const op = this.advance();
      const right = this.parseAdditive();
      left = { kind: 'binary', op: '&', left, right, line: op.line };
    }
    return left;
  }

  private parseAdditive(): Expr {
    let left = this.parseMultiplicative();
    while (this.at('op', '+') || this.at('op', '-')) {
      const op = this.advance();
      const right = this.parseMultiplicative();
      left = { kind: 'binary', op: op.value, left, right, line: op.line };
    }
    return left;
  }

  private parseMultiplicative(): Expr {
    let left = this.parseIntDiv();
    while (this.at('op', '*') || this.at('op', '/') || this.atKeyword('mod')) {
      const op = this.advance();
      const right = this.parseIntDiv();
      left = { kind: 'binary', op: op.value, left, right, line: op.line };
    }
    return left;
  }

  private parseIntDiv(): Expr {
    let left = this.parseUnary();
    while (this.at('op', '\\')) {
      const op = this.advance();
      const right = this.parseUnary();
      left = { kind: 'binary', op: '\\', left, right, line: op.line };
    }
    return left;
  }

  private parseUnary(): Expr {
    if (this.at('op', '-') || this.at('op', '+')) {
      const op = this.advance();
      return { kind: 'unary', op: op.value, expr: this.parseUnary(), line: op.line };
    }
    return this.parsePower();
  }

  private parsePower(): Expr {
    const base = this.parsePostfix();
    if (this.at('op', '^')) {
      const op = this.advance();
      const exp = this.parseUnary();
      return { kind: 'binary', op: '^', left: base, right: exp, line: op.line };
    }
    return base;
  }

  private parsePostfix(): Expr {
    let node = this.parsePrimary();
    for (;;) {
      if (this.at('op', '.')) {
        this.advance();
        const n = this.advance();
        node = { kind: 'member', obj: node, name: n.value, raw: n.raw, line: n.line };
        continue;
      }
      if (this.at('op', '(')) {
        const line = this.cur.line;
        this.advance();
        const args: Expr[] = [];
        if (!this.at('op', ')')) {
          do {
            if (this.at('op', ',')) {
              args.push({ kind: 'empty', line });
              continue;
            }
            // named argument: Title:="x"
            if (
              (this.cur.type === 'ident' || this.cur.type === 'keyword') &&
              this.peek().type === 'op' &&
              this.peek().value === ':='
            ) {
              this.advance();
              this.advance();
            }
            args.push(this.parseExpr());
          } while (this.eat('op', ','));
        }
        this.expect('op', ')');
        node = { kind: 'call', callee: node, args, line };
        continue;
      }
      break;
    }
    return node;
  }

  private parsePrimary(): Expr {
    const t = this.cur;
    const line = t.line;

    if (t.type === 'number') {
      this.advance();
      return { kind: 'num', value: Number(t.value), line };
    }
    if (t.type === 'string') {
      this.advance();
      return { kind: 'str', value: t.value, line };
    }
    if (t.type === 'op' && t.value === '(') {
      this.advance();
      const inner = this.parseExpr();
      this.expect('op', ')');
      return inner;
    }
    if (t.type === 'op' && t.value === '.') {
      this.advance();
      const n = this.advance();
      return { kind: 'withMember', name: n.value, raw: n.raw, line };
    }
    if (t.type === 'keyword') {
      if (t.value === 'true' || t.value === 'false') {
        this.advance();
        return { kind: 'bool', value: t.value === 'true', line };
      }
      if (t.value === 'nothing') {
        this.advance();
        return { kind: 'nothing', line };
      }
      if (t.value === 'empty' || t.value === 'null') {
        this.advance();
        return { kind: 'empty', line };
      }
      if (t.value === 'new') {
        this.advance();
        return this.parsePrimary();
      }
      if (TYPE_KEYWORDS.has(t.value)) {
        // เช่น Range("A1") ที่ตัวศัพท์จับเป็นคีย์เวิร์ด
        this.advance();
        return { kind: 'ident', name: t.value, raw: t.raw, line };
      }
    }
    if (t.type === 'ident') {
      this.advance();
      return { kind: 'ident', name: t.value.replace(/[$%&!#@]$/, ''), raw: t.raw, line };
    }

    throw new VbaSyntaxError(
      `ไม่เข้าใจตรงนี้: "${t.raw || t.value || 'จบบรรทัด'}"`,
      line,
    );
  }
}
