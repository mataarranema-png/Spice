// Lexer สำหรับภาษา VBA (ชุดคำสั่งย่อยที่ใช้สอน)

export type TokenType =
  | 'number'
  | 'string'
  | 'ident'
  | 'keyword'
  | 'op'
  | 'newline'
  | 'eof';

export interface Token {
  type: TokenType;
  value: string;
  /** ตัวพิมพ์เดิมก่อน normalize (ใช้กับ ident) */
  raw: string;
  line: number;
  col: number;
}

const KEYWORDS = new Set(
  [
    'sub', 'end', 'function', 'dim', 'as', 'set', 'let', 'const',
    'if', 'then', 'elseif', 'else', 'for', 'to', 'step', 'next', 'each', 'in',
    'do', 'loop', 'while', 'until', 'wend', 'select', 'case', 'is',
    'with', 'exit', 'call', 'and', 'or', 'not', 'xor', 'mod', 'true', 'false',
    'nothing', 'empty', 'null', 'new', 'byval', 'byref', 'optional', 'preserve',
    'redim', 'option', 'explicit', 'public', 'private', 'on', 'error', 'resume',
    'goto', 'integer', 'long', 'double', 'single', 'string', 'boolean', 'variant',
    'object', 'date', 'range', 'worksheet', 'workbook', 'like',
  ],
);

const THREE_CHAR_OPS: string[] = [];
const TWO_CHAR_OPS = ['<=', '>=', '<>', ':='];
const ONE_CHAR_OPS = '+-*/\\^&=<>(),.:'.split('');

export class VbaSyntaxError extends Error {
  line: number;
  constructor(message: string, line: number) {
    super(message);
    this.name = 'VbaSyntaxError';
    this.line = line;
  }
}

export function tokenize(source: string): Token[] {
  const tokens: Token[] = [];
  // ทำให้บรรทัดต่อเนื่องด้วย " _" รวมเป็นบรรทัดเดียว แต่คงจำนวนบรรทัดไว้
  const rawLines = source.replace(/\r\n?/g, '\n').split('\n');

  let lineNo = 0;
  let pendingLine = '';
  let pendingLineNo = 1;

  const flush = (text: string, ln: number) => {
    lexLine(text, ln, tokens);
  };

  for (const rawLine of rawLines) {
    lineNo++;
    const trimmedEnd = rawLine.replace(/\s+$/, '');
    if (/(^|\s)_$/.test(trimmedEnd)) {
      if (!pendingLine) pendingLineNo = lineNo;
      pendingLine += trimmedEnd.replace(/_$/, ' ');
      continue;
    }
    const full = pendingLine + rawLine;
    const ln = pendingLine ? pendingLineNo : lineNo;
    pendingLine = '';
    flush(full, ln);
  }
  if (pendingLine) flush(pendingLine, pendingLineNo);

  tokens.push({ type: 'eof', value: '', raw: '', line: lineNo + 1, col: 0 });
  return tokens;
}

function lexLine(text: string, line: number, out: Token[]) {
  let i = 0;
  const startCount = out.length;

  while (i < text.length) {
    const ch = text[i];

    // ช่องว่าง
    if (ch === ' ' || ch === '\t') {
      i++;
      continue;
    }

    // คอมเมนต์
    if (ch === "'") break;
    if (/^rem(\s|$)/i.test(text.slice(i)) && isStatementStart(out, startCount)) break;

    // ตัวคั่นคำสั่งในบรรทัดเดียว
    if (ch === ':' && !isLabelColon(text, i)) {
      out.push({ type: 'newline', value: ':', raw: ':', line, col: i });
      i++;
      continue;
    }

    // ตัวเลข
    if (/[0-9]/.test(ch) || (ch === '.' && /[0-9]/.test(text[i + 1] ?? ''))) {
      let j = i;
      while (j < text.length && /[0-9]/.test(text[j])) j++;
      if (text[j] === '.') {
        j++;
        while (j < text.length && /[0-9]/.test(text[j])) j++;
      }
      if (/[eE]/.test(text[j] ?? '') && /[0-9+-]/.test(text[j + 1] ?? '')) {
        j += 2;
        while (j < text.length && /[0-9]/.test(text[j])) j++;
      }
      out.push({ type: 'number', value: text.slice(i, j), raw: text.slice(i, j), line, col: i });
      i = j;
      continue;
    }

    // เลขฐานสิบหก &H
    if (ch === '&' && /[hH]/.test(text[i + 1] ?? '')) {
      let j = i + 2;
      while (j < text.length && /[0-9a-fA-F]/.test(text[j])) j++;
      const hex = text.slice(i + 2, j);
      out.push({
        type: 'number',
        value: String(parseInt(hex, 16)),
        raw: text.slice(i, j),
        line,
        col: i,
      });
      i = j;
      continue;
    }

    // สตริง
    if (ch === '"') {
      let j = i + 1;
      let buf = '';
      let closed = false;
      while (j < text.length) {
        if (text[j] === '"') {
          if (text[j + 1] === '"') {
            buf += '"';
            j += 2;
            continue;
          }
          closed = true;
          j++;
          break;
        }
        buf += text[j];
        j++;
      }
      if (!closed) throw new VbaSyntaxError('ลืมปิดเครื่องหมายคำพูด (")', line);
      out.push({ type: 'string', value: buf, raw: text.slice(i, j), line, col: i });
      i = j;
      continue;
    }

    // วันที่ #1/1/2024#
    if (ch === '#') {
      const end = text.indexOf('#', i + 1);
      if (end > 0) {
        out.push({ type: 'string', value: text.slice(i + 1, end), raw: text.slice(i, end + 1), line, col: i });
        i = end + 1;
        continue;
      }
    }

    // ตัวระบุ / คีย์เวิร์ด
    if (/[A-Za-z_฀-๿]/.test(ch)) {
      let j = i;
      while (j < text.length && /[A-Za-z0-9_฀-๿]/.test(text[j])) j++;
      const raw = text.slice(i, j);
      // ตัวระบุชนิด เช่น name$ , n%
      if (/[$%&!#@]/.test(text[j] ?? '') && !(text[j] === '&' && /[hH]/.test(text[j + 1] ?? ''))) j++;
      const word = raw.toLowerCase();
      out.push({
        type: KEYWORDS.has(word) ? 'keyword' : 'ident',
        value: word,
        raw,
        line,
        col: i,
      });
      i = j;
      continue;
    }

    // ตัวดำเนินการ
    const three = text.slice(i, i + 3);
    if (THREE_CHAR_OPS.includes(three)) {
      out.push({ type: 'op', value: three, raw: three, line, col: i });
      i += 3;
      continue;
    }
    const two = text.slice(i, i + 2);
    if (TWO_CHAR_OPS.includes(two)) {
      out.push({ type: 'op', value: two, raw: two, line, col: i });
      i += 2;
      continue;
    }
    if (ONE_CHAR_OPS.includes(ch)) {
      out.push({ type: 'op', value: ch, raw: ch, line, col: i });
      i++;
      continue;
    }

    throw new VbaSyntaxError(`เจอตัวอักษรที่ไม่รู้จัก: "${ch}"`, line);
  }

  if (out.length > startCount) {
    const last = out[out.length - 1];
    out.push({ type: 'newline', value: '\n', raw: '', line, col: last.col + 1 });
  }
}

function isStatementStart(out: Token[], startCount: number) {
  if (out.length === startCount) return true;
  const last = out[out.length - 1];
  return last.type === 'newline';
}

/** ":=" คือ named argument, ส่วน ":" เดี่ยวคือคั่นคำสั่ง */
function isLabelColon(text: string, i: number) {
  return text[i + 1] === '=';
}
