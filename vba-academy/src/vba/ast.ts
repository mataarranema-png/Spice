export interface Pos { line: number }

export type Expr =
  | { kind: 'num'; value: number; line: number }
  | { kind: 'str'; value: string; line: number }
  | { kind: 'bool'; value: boolean; line: number }
  | { kind: 'nothing'; line: number }
  | { kind: 'empty'; line: number }
  | { kind: 'ident'; name: string; raw: string; line: number }
  | { kind: 'member'; obj: Expr; name: string; raw: string; line: number }
  | { kind: 'withMember'; name: string; raw: string; line: number }
  | { kind: 'call'; callee: Expr; args: Expr[]; line: number }
  | { kind: 'unary'; op: string; expr: Expr; line: number }
  | { kind: 'binary'; op: string; left: Expr; right: Expr; line: number };

export interface VarDecl {
  name: string;
  raw: string;
  dims?: { lower?: Expr; upper: Expr }[];
  type?: string;
}

export type CaseTest =
  | { kind: 'value'; expr: Expr }
  | { kind: 'range'; from: Expr; to: Expr }
  | { kind: 'compare'; op: string; expr: Expr };

export type Stmt =
  | { kind: 'dim'; vars: VarDecl[]; line: number }
  | { kind: 'redim'; preserve: boolean; vars: VarDecl[]; line: number }
  | { kind: 'const'; name: string; raw: string; value: Expr; line: number }
  | { kind: 'assign'; target: Expr; value: Expr; line: number }
  | { kind: 'exprStmt'; expr: Expr; line: number }
  | { kind: 'if'; branches: { cond: Expr; body: Stmt[] }[]; elseBody: Stmt[] | null; line: number }
  | { kind: 'for'; varName: string; raw: string; from: Expr; to: Expr; step: Expr | null; body: Stmt[]; line: number }
  | { kind: 'forEach'; varName: string; raw: string; coll: Expr; body: Stmt[]; line: number }
  | {
      kind: 'do';
      pre: { type: 'while' | 'until'; cond: Expr } | null;
      post: { type: 'while' | 'until'; cond: Expr } | null;
      body: Stmt[];
      line: number;
    }
  | { kind: 'while'; cond: Expr; body: Stmt[]; line: number }
  | {
      kind: 'select';
      subject: Expr;
      cases: { tests: CaseTest[]; body: Stmt[] }[];
      elseBody: Stmt[] | null;
      line: number;
    }
  | { kind: 'with'; subject: Expr; body: Stmt[]; line: number }
  | { kind: 'exit'; what: 'for' | 'do' | 'sub' | 'function' | 'while'; line: number }
  | { kind: 'onError'; mode: 'resumeNext' | 'goto0'; line: number }
  | { kind: 'noop'; line: number };

export interface Param {
  name: string;
  raw: string;
  byVal: boolean;
  optional: boolean;
  defaultValue: Expr | null;
  isArray: boolean;
}

export interface ProcDecl {
  kind: 'sub' | 'function';
  name: string;
  raw: string;
  params: Param[];
  body: Stmt[];
  line: number;
}

export interface Program {
  procs: ProcDecl[];
  moduleBody: Stmt[];
}
