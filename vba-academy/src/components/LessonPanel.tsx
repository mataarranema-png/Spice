import type { Lesson, Level } from '../content/types';
import type { TaskResult } from '../lib/runner';

interface Props {
  lesson: Lesson;
  level: Level;
  tab: 'learn' | 'tasks';
  onTab: (tab: 'learn' | 'tasks') => void;
  tasks: TaskResult[];
  hintIndex: number;
  onHint: () => void;
  completed: boolean;
}

/** แปลง markdown แบบเบา ๆ (**หนา** และ `โค้ด`) ให้เป็น React nodes */
function renderRich(textInput: string, keyBase: string) {
  const parts: React.ReactNode[] = [];
  const regex = /(\*\*[^*]+\*\*|`[^`]+`)/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = regex.exec(textInput)) !== null) {
    if (m.index > last) parts.push(textInput.slice(last, m.index));
    const token = m[0];
    if (token.startsWith('**')) {
      parts.push(<strong key={`${keyBase}-b${i++}`}>{token.slice(2, -2)}</strong>);
    } else {
      parts.push(<code key={`${keyBase}-c${i++}`}>{token.slice(1, -1)}</code>);
    }
    last = m.index + token.length;
  }
  if (last < textInput.length) parts.push(textInput.slice(last));
  return parts;
}

export function LessonPanel({
  lesson,
  level,
  tab,
  onTab,
  tasks,
  hintIndex,
  onHint,
  completed,
}: Props) {
  const passedCount = tasks.filter((t) => t.passed).length;

  return (
    <>
      <div className="lesson-hero">
        <span className="lesson-kicker" style={{ background: level.accent }}>
          {level.emoji} {level.title}
        </span>
        <h2>
          {lesson.emoji} {lesson.title}
          {completed && <span title="ผ่านแล้ว"> ✅</span>}
        </h2>
        <p className="lesson-goal">🎯 {lesson.goal}</p>
      </div>

      <div className="tabs">
        <button className={`tab ${tab === 'learn' ? 'active' : ''}`} onClick={() => onTab('learn')} type="button">
          📖 เรียนรู้
        </button>
        <button className={`tab ${tab === 'tasks' ? 'active' : ''}`} onClick={() => onTab('tasks')} type="button">
          ✅ ภารกิจ {tasks.length > 0 && `(${passedCount}/${tasks.length})`}
        </button>
      </div>

      <div className="card-body">
        {tab === 'learn' ? (
          <div className="theory">
            {lesson.theory.map((p, i) => (
              <p key={i}>{renderRich(p, `t${i}`)}</p>
            ))}
            {lesson.syntax?.map((s, i) => (
              <div className="syntax-box" key={i}>
                <pre>{s.code}</pre>
                <div className="syntax-note">
                  <span aria-hidden>💡</span>
                  <span>{s.note}</span>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <>
            <ul className="task-list">
              {lesson.tasks.map((t, i) => {
                const result = tasks[i];
                const passed = !!result?.passed;
                return (
                  <li className={`task ${passed ? 'pass' : ''}`} key={i}>
                    <span className="task-check" aria-hidden>
                      {passed ? '✓' : ''}
                    </span>
                    <span>{renderRich(t.label, `k${i}`)}</span>
                  </li>
                );
              })}
            </ul>

            {lesson.hints.length > 0 && (
              <>
                <div className="speak-row">
                  <button className="mini-btn" type="button" onClick={onHint} disabled={hintIndex >= lesson.hints.length}>
                    💡 ขอคำใบ้ ({Math.min(hintIndex, lesson.hints.length)}/{lesson.hints.length})
                  </button>
                </div>
                {lesson.hints.slice(0, hintIndex).map((h, i) => (
                  <div className="hint-box" key={i}>
                    <strong>คำใบ้ {i + 1}:</strong> {renderRich(h, `h${i}`)}
                  </div>
                ))}
              </>
            )}
          </>
        )}
      </div>
    </>
  );
}
