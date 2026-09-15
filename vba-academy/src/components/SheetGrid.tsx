import { useEffect, useMemo, useRef, useState } from 'react';
import {
  colLetter,
  computeDisplayValue,
  formatCellValue,
  type Workbook,
} from '../vba/workbook';

interface Props {
  workbook: Workbook;
  version: number;
  activeSheet: number;
  onSelectSheet: (index: number) => void;
  highlight?: { row: number; col: number } | null;
}

const VISIBLE_ROWS = 22;
const VISIBLE_COLS = 10;

export function SheetGrid({ workbook, version, activeSheet, onSelectSheet, highlight }: Props) {
  const sheet = workbook.sheets[activeSheet] ?? workbook.sheets[0];
  const [selected, setSelected] = useState({ row: 1, col: 1 });
  const prevValues = useRef(new Map<string, string>());
  const [touched, setTouched] = useState<Set<string>>(new Set());

  const bounds = sheet.usedBounds();
  const rowCount = Math.max(VISIBLE_ROWS, (bounds?.maxRow ?? 0) + 3);
  const colCount = Math.max(VISIBLE_COLS, (bounds?.maxCol ?? 0) + 2);

  const cells = useMemo(() => {
    const grid: { key: string; row: number; col: number; display: string; numeric: boolean }[][] = [];
    for (let r = 1; r <= rowCount; r++) {
      const rowArr: { key: string; row: number; col: number; display: string; numeric: boolean }[] = [];
      for (let c = 1; c <= colCount; c++) {
        const raw = computeDisplayValue(sheet, r, c);
        const style = sheet.peek(r, c)?.style;
        rowArr.push({
          key: `${r}:${c}`,
          row: r,
          col: c,
          display: formatCellValue(raw, style),
          numeric: typeof raw === 'number',
        });
      }
      grid.push(rowArr);
    }
    return grid;
    // version บังคับให้คำนวณใหม่เมื่อ VBA แก้ชีต
  }, [sheet, rowCount, colCount, version]);

  // ไฮไลต์เซลล์ที่เพิ่งเปลี่ยนค่า
  useEffect(() => {
    const changed = new Set<string>();
    const next = new Map<string, string>();
    for (const row of cells) {
      for (const cell of row) {
        const id = `${activeSheet}:${cell.key}`;
        next.set(id, cell.display);
        const before = prevValues.current.get(id);
        if (before !== undefined && before !== cell.display) changed.add(cell.key);
      }
    }
    prevValues.current = next;
    if (changed.size) {
      setTouched(changed);
      const t = setTimeout(() => setTouched(new Set()), 850);
      return () => clearTimeout(t);
    }
  }, [cells, activeSheet]);

  const selectedRaw = computeDisplayValue(sheet, selected.row, selected.col);
  const selectedCell = sheet.peek(selected.row, selected.col);
  const formulaText = selectedCell?.formula
    ? selectedCell.formula
    : selectedRaw === null
      ? ''
      : String(selectedRaw);

  return (
    <div className="sheet-frame">
      <div className="sheet-toolbar">
        <span>📗 VBA-Academy.xlsm</span>
        <span style={{ opacity: 0.75 }}>— สนามซ้อม Excel จำลอง</span>
      </div>

      <div className="formula-bar">
        <span className="addr">
          {colLetter(selected.col)}
          {selected.row}
        </span>
        <span aria-hidden>fx</span>
        <span className="val">{formulaText}</span>
      </div>

      <div className="grid-scroll">
        <table className="sheet">
          <thead>
            <tr>
              <th className="corner" />
              {Array.from({ length: colCount }, (_, i) => (
                <th key={i}>{colLetter(i + 1)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {cells.map((row, rIdx) => (
              <tr key={rIdx}>
                <td className="rowhead">{rIdx + 1}</td>
                {row.map((cell) => {
                  const style = sheet.peek(cell.row, cell.col)?.style ?? {};
                  const isSelected = selected.row === cell.row && selected.col === cell.col;
                  const isRunHighlight = highlight?.row === cell.row && highlight?.col === cell.col;
                  return (
                    <td
                      key={cell.key}
                      className={[
                        cell.numeric ? 'numeric' : '',
                        isSelected || isRunHighlight ? 'selected' : '',
                        touched.has(cell.key) ? 'touched' : '',
                      ]
                        .filter(Boolean)
                        .join(' ')}
                      onClick={() => setSelected({ row: cell.row, col: cell.col })}
                      style={{
                        background: style.fill ?? undefined,
                        border: style.border ? '1px solid #8aa0a8' : undefined,
                      }}
                    >
                      <div
                        className="cell"
                        style={{
                          fontWeight: style.bold ? 700 : undefined,
                          fontStyle: style.italic ? 'italic' : undefined,
                          textDecoration: style.underline ? 'underline' : undefined,
                          color: style.fontColor ?? undefined,
                          fontSize: style.fontSize ? `${Math.min(20, style.fontSize)}px` : undefined,
                          justifyContent:
                            style.align === 'center'
                              ? 'center'
                              : style.align === 'right'
                                ? 'flex-end'
                                : undefined,
                        }}
                      >
                        {cell.display}
                      </div>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="sheet-tabs">
        {workbook.sheets.map((s, i) => (
          <button
            key={s.name + i}
            className={`sheet-tab ${i === activeSheet ? 'active' : ''}`}
            onClick={() => onSelectSheet(i)}
            type="button"
          >
            {s.name}
          </button>
        ))}
      </div>
    </div>
  );
}
