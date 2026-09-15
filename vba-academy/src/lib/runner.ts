import { Interpreter } from '../vba/interpreter';
import { VbaSyntaxError } from '../vba/lexer';
import {
  Workbook,
  Worksheet,
  addressToRC,
  computeDisplayValue,
  type CellStyle,
  type CellValue,
} from '../vba/workbook';
import type { CheckContext, Lesson } from '../content/types';

export interface TaskResult {
  label: string;
  passed: boolean;
}

export interface LessonRunResult {
  ok: boolean;
  error?: { message: string; line: number };
  output: string[];
  messages: string[];
  tasks: TaskResult[];
  allPassed: boolean;
}

export function createWorkbook(lesson?: Lesson): Workbook {
  const wb = new Workbook(['Sheet1', 'Sheet2']);
  if (lesson?.seed) {
    const start = addressToRC(lesson.seedAt ?? 'A1') ?? { row: 1, col: 1 };
    lesson.seed.forEach((row, r) => {
      row.forEach((raw, c) => {
        if (raw === '') return;
        const asNumber = Number(raw);
        const value: CellValue = raw !== '' && !Number.isNaN(asNumber) ? asNumber : raw;
        wb.sheets[0].setValue(start.row + r, start.col + c, value);
      });
    });
  }
  return wb;
}

export function buildContext(
  wb: Workbook,
  code: string,
  output: string[],
  messages: string[],
): CheckContext {
  const sheet: Worksheet = wb.sheets[0];
  const at = (addr: string) => addressToRC(addr) ?? { row: 1, col: 1 };
  return {
    wb,
    sheet,
    output,
    messages,
    code,
    value: (addr: string) => {
      const { row, col } = at(addr);
      return computeDisplayValue(sheet, row, col);
    },
    style: (addr: string): CellStyle => {
      const { row, col } = at(addr);
      return sheet.peek(row, col)?.style ?? {};
    },
    printed: (t: string) => output.some((o) => o.includes(t)),
    said: (t: string) => messages.some((m) => m.includes(t)),
    codeHas: (re: RegExp) => re.test(code),
  };
}

export interface RunOptions {
  onStep?: (line: number) => Promise<void> | void;
  onChange?: () => void;
  onMsgBox?: (text: string, title: string) => Promise<void>;
  onInputBox?: (prompt: string, title: string, def: string) => Promise<string | null>;
  procName?: string;
}

export async function runLesson(
  code: string,
  lesson: Lesson | undefined,
  wb: Workbook,
  options: RunOptions = {},
): Promise<LessonRunResult> {
  const output: string[] = [];
  const messages: string[] = [];

  let interpreter: Interpreter;
  try {
    interpreter = new Interpreter(code, wb, {
      onStep: options.onStep,
      onChange: options.onChange,
      onPrint: (t) => output.push(t),
      onMsgBox: async (text, title) => {
        messages.push(text);
        if (options.onMsgBox) await options.onMsgBox(text, title);
      },
      onInputBox: options.onInputBox,
    });
  } catch (err) {
    const line = err instanceof VbaSyntaxError ? err.line : 0;
    return {
      ok: false,
      error: { message: (err as Error).message, line },
      output,
      messages,
      tasks: (lesson?.tasks ?? []).map((t) => ({ label: t.label, passed: false })),
      allPassed: false,
    };
  }

  const result = await interpreter.run(options.procName);
  const ctx = buildContext(wb, code, output, messages);
  const tasks = (lesson?.tasks ?? []).map((t) => {
    let passed = false;
    try {
      passed = result.ok && t.check(ctx);
    } catch {
      passed = false;
    }
    return { label: t.label, passed };
  });

  return {
    ok: result.ok,
    error: result.error,
    output,
    messages,
    tasks,
    allPassed: result.ok && tasks.length > 0 && tasks.every((t) => t.passed),
  };
}

export function listSubs(code: string): string[] {
  try {
    const wb = new Workbook(['tmp']);
    const interp = new Interpreter(code, wb, {});
    return interp.runnableSubs.map((p) => p.raw);
  } catch {
    return [];
  }
}
