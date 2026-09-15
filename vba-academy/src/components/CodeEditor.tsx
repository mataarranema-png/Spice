import { useEffect, useMemo, useRef } from 'react';
import { highlightVba } from '../lib/highlight';

interface Props {
  value: string;
  onChange: (value: string) => void;
  errorLine?: number | null;
  currentLine?: number | null;
  disabled?: boolean;
}

export function CodeEditor({ value, onChange, errorLine, currentLine, disabled }: Props) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const preRef = useRef<HTMLPreElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const lines = useMemo(() => value.split('\n'), [value]);
  const html = useMemo(() => highlightVba(value) + '\n', [value]);

  // ให้ textarea สูงเท่าเนื้อหาจริง เพื่อให้เลื่อนพร้อมกันทั้งบล็อก
  useEffect(() => {
    const ta = textareaRef.current;
    const pre = preRef.current;
    if (ta && pre) ta.style.height = `${pre.scrollHeight}px`;
  }, [html]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    const ta = e.currentTarget;
    if (e.key === 'Tab') {
      e.preventDefault();
      const start = ta.selectionStart;
      const end = ta.selectionEnd;
      const next = `${value.slice(0, start)}  ${value.slice(end)}`;
      onChange(next);
      requestAnimationFrame(() => {
        ta.selectionStart = ta.selectionEnd = start + 2;
      });
      return;
    }
    if (e.key === 'Enter') {
      // คงระดับย่อหน้าเดิมให้อัตโนมัติ
      const start = ta.selectionStart;
      const lineStart = value.lastIndexOf('\n', start - 1) + 1;
      const indentMatch = /^[ \t]*/.exec(value.slice(lineStart, start));
      const indent = indentMatch ? indentMatch[0] : '';
      if (indent) {
        e.preventDefault();
        const next = `${value.slice(0, start)}\n${indent}${value.slice(ta.selectionEnd)}`;
        onChange(next);
        requestAnimationFrame(() => {
          ta.selectionStart = ta.selectionEnd = start + 1 + indent.length;
        });
      }
    }
  };

  return (
    <div className="editor-wrap">
      <div
        className="editor-scroll"
        ref={scrollRef}
        onScroll={(e) => {
          const el = e.currentTarget;
          if (preRef.current) preRef.current.style.transform = `translateX(-${el.scrollLeft}px)`;
        }}
      >
        <div className="gutter" aria-hidden>
          {lines.map((_, i) => (
            <div
              key={i}
              className={errorLine === i + 1 ? 'err' : currentLine === i + 1 ? 'cur' : ''}
            >
              {errorLine === i + 1 ? '✖' : currentLine === i + 1 ? '▶' : i + 1}
            </div>
          ))}
        </div>
        <div className="editor-area">
          <pre ref={preRef} aria-hidden dangerouslySetInnerHTML={{ __html: html }} />
          <textarea
            ref={textareaRef}
            className="code"
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={handleKeyDown}
            spellCheck={false}
            autoCapitalize="off"
            autoCorrect="off"
            disabled={disabled}
            aria-label="ช่องเขียนโค้ด VBA"
          />
        </div>
      </div>
    </div>
  );
}
