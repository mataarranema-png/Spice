import type { Workbook, Worksheet, CellValue, CellStyle } from '../vba/workbook';

export interface CheckContext {
  wb: Workbook;
  sheet: Worksheet;
  output: string[];
  messages: string[];
  code: string;
  value: (addr: string) => CellValue;
  style: (addr: string) => CellStyle;
  printed: (text: string) => boolean;
  said: (text: string) => boolean;
  codeHas: (re: RegExp) => boolean;
}

export interface Task {
  label: string;
  check: (ctx: CheckContext) => boolean;
}

export interface Lesson {
  id: string;
  level: string;
  title: string;
  emoji: string;
  goal: string;
  /** บทพากย์เสียงภาษาไทย */
  narration: string;
  theory: string[];
  syntax?: { code: string; note: string }[];
  starter: string;
  solution: string;
  hints: string[];
  seed?: string[][];
  seedAt?: string;
  tasks: Task[];
  xp: number;
}

export interface Level {
  id: string;
  title: string;
  emoji: string;
  subtitle: string;
  accent: string;
}
