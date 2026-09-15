import { useState } from 'react';
import { LESSONS, LEVELS } from '../content/lessons';

interface Props {
  currentId: string;
  completed: string[];
  onPick: (id: string) => void;
}

export function Sidebar({ currentId, completed, onPick }: Props) {
  const currentLevel = LESSONS.find((l) => l.id === currentId)?.level ?? LEVELS[0].id;
  const [open, setOpen] = useState<Record<string, boolean>>({ [currentLevel]: true });

  return (
    <aside className="card col-left">
      <div className="card-head">
        <span aria-hidden>🗺️</span>
        <h2>แผนที่การเรียน</h2>
      </div>
      <div>
        {LEVELS.map((level) => {
          const lessons = LESSONS.filter((l) => l.level === level.id);
          const done = lessons.filter((l) => completed.includes(l.id)).length;
          const isOpen = open[level.id] ?? false;
          return (
            <div className="level-group" key={level.id}>
              <button
                className="level-head"
                type="button"
                onClick={() => setOpen((o) => ({ ...o, [level.id]: !isOpen }))}
                aria-expanded={isOpen}
              >
                <span className="level-emoji" style={{ background: level.accent }} aria-hidden>
                  {level.emoji}
                </span>
                <span className="level-title">
                  <strong>{level.title}</strong>
                  <span>{level.subtitle}</span>
                </span>
                <span className="level-progress">
                  {done}/{lessons.length}
                </span>
              </button>
              {isOpen && (
                <div className="lesson-list">
                  {lessons.map((lesson, idx) => {
                    const isDone = completed.includes(lesson.id);
                    return (
                      <button
                        key={lesson.id}
                        type="button"
                        className={`lesson-item ${lesson.id === currentId ? 'active' : ''}`}
                        onClick={() => onPick(lesson.id)}
                      >
                        <span className={`lesson-dot ${isDone ? 'done' : ''}`} aria-hidden>
                          {isDone ? '✓' : idx + 1}
                        </span>
                        <span style={{ flex: 1, minWidth: 0 }}>
                          {lesson.emoji} {lesson.title}
                        </span>
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </aside>
  );
}
