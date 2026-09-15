import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { LESSONS, LEVELS } from './content/lessons';
import { BADGES, TOTAL_XP, useProgress } from './lib/progress';
import { sfx, useSpeech } from './lib/speech';
import { createWorkbook, runLesson, type TaskResult } from './lib/runner';
import type { Workbook } from './vba/workbook';
import { SheetGrid } from './components/SheetGrid';
import { CodeEditor } from './components/CodeEditor';
import { Sidebar } from './components/Sidebar';
import { LessonPanel } from './components/LessonPanel';
import { Celebration, DialogHost, type DialogRequest } from './components/Dialogs';

type ConsoleLine = { kind: 'out' | 'err' | 'ok' | 'msg'; text: string };

class RunCancelled extends Error {}

export default function App() {
  const { progress, complete, setLastLesson, saveCode, reset } = useProgress();
  const speech = useSpeech();

  const [lessonId, setLessonId] = useState(() => {
    const saved = progress.lastLesson;
    return LESSONS.some((l) => l.id === saved) ? saved : LESSONS[0].id;
  });

  const lesson = useMemo(() => LESSONS.find((l) => l.id === lessonId) ?? LESSONS[0], [lessonId]);
  const level = useMemo(() => LEVELS.find((l) => l.id === lesson.level) ?? LEVELS[0], [lesson]);

  const [code, setCode] = useState(() => progress.code[lesson.id] ?? lesson.starter);
  const [workbook, setWorkbook] = useState<Workbook>(() => createWorkbook(lesson));
  const [version, setVersion] = useState(0);
  const [activeSheet, setActiveSheet] = useState(0);
  const [tab, setTab] = useState<'learn' | 'tasks'>('learn');
  const [tasks, setTasks] = useState<TaskResult[]>([]);
  const [lines, setLines] = useState<ConsoleLine[]>([]);
  const [errorLine, setErrorLine] = useState<number | null>(null);
  const [currentLine, setCurrentLine] = useState<number | null>(null);
  const [running, setRunning] = useState(false);
  const [slowMode, setSlowMode] = useState(false);
  const [hintIndex, setHintIndex] = useState(0);
  const [celebrate, setCelebrate] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [dialog, setDialog] = useState<DialogRequest | null>(null);

  const runIdRef = useRef(0);
  const cancelRef = useRef(false);
  const autoSpokenRef = useRef<string | null>(null);

  const isCompleted = progress.completed.includes(lesson.id);

  // เปลี่ยนบทเรียน → รีเซ็ตทุกอย่าง
  useEffect(() => {
    cancelRef.current = true;
    setCode(progress.code[lesson.id] ?? lesson.starter);
    setWorkbook(createWorkbook(lesson));
    setVersion((v) => v + 1);
    setActiveSheet(0);
    setTasks([]);
    setLines([]);
    setErrorLine(null);
    setCurrentLine(null);
    setHintIndex(0);
    setTab('learn');
    setLastLesson(lesson.id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lesson.id]);

  // อ่านบทพากย์อัตโนมัติเมื่อเข้าบทเรียนใหม่
  useEffect(() => {
    if (!speech.enabled || !speech.supported) return;
    if (autoSpokenRef.current === lesson.id) return;
    autoSpokenRef.current = lesson.id;
    const t = setTimeout(() => speech.speak(lesson.narration), 400);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lesson.id, speech.enabled, speech.supported]);

  useEffect(() => {
    const t = setTimeout(() => saveCode(lesson.id, code), 600);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [code, lesson.id]);

  const pushLine = useCallback((line: ConsoleLine) => {
    setLines((prev) => [...prev.slice(-120), line]);
  }, []);

  const handleRun = useCallback(async () => {
    if (running) return;
    speech.stop();
    const myRun = ++runIdRef.current;
    cancelRef.current = false;
    setRunning(true);
    setLines([]);
    setErrorLine(null);
    setCurrentLine(null);

    const wb = createWorkbook(lesson);
    setWorkbook(wb);
    setVersion((v) => v + 1);

    const result = await runLesson(code, lesson, wb, {
      onChange: () => setVersion((v) => v + 1),
      onStep: slowMode
        ? async (line) => {
            if (cancelRef.current || runIdRef.current !== myRun) throw new RunCancelled('ยกเลิกการรัน');
            setCurrentLine(line);
            await new Promise((r) => setTimeout(r, 90));
          }
        : (line) => {
            if (cancelRef.current || runIdRef.current !== myRun) throw new RunCancelled('ยกเลิกการรัน');
            setCurrentLine(line);
          },
      onMsgBox: (textValue, title) =>
        new Promise<void>((resolve) => {
          setDialog({
            kind: 'msgbox',
            text: textValue,
            title,
            resolve: () => {
              setDialog(null);
              resolve();
            },
          });
        }),
      onInputBox: (prompt, title, def) =>
        new Promise<string | null>((resolve) => {
          setDialog({
            kind: 'inputbox',
            prompt,
            title,
            def,
            resolve: (value) => {
              setDialog(null);
              resolve(value);
            },
          });
        }),
    });

    if (runIdRef.current !== myRun) return;

    setRunning(false);
    setCurrentLine(null);
    setVersion((v) => v + 1);
    setTasks(result.tasks);

    result.output.forEach((o) => pushLine({ kind: 'out', text: o }));
    result.messages.forEach((m) => pushLine({ kind: 'msg', text: `MsgBox: ${m}` }));

    if (!result.ok) {
      const message = result.error?.message ?? 'เกิดข้อผิดพลาด';
      if (message.includes('ยกเลิกการรัน')) {
        pushLine({ kind: 'err', text: '⏹ หยุดการทำงานแล้ว' });
        return;
      }
      setErrorLine(result.error?.line ?? null);
      pushLine({
        kind: 'err',
        text: `❌ บรรทัด ${result.error?.line ?? '?'}: ${message}`,
      });
      setTab('tasks');
      sfx.fail();
      return;
    }

    pushLine({ kind: 'ok', text: '▶ รันโค้ดสำเร็จ ไม่มีข้อผิดพลาด' });
    setTab('tasks');

    if (result.allPassed) {
      sfx.success();
      const firstTime = !progress.completed.includes(lesson.id);
      complete(lesson.id, lesson.xp);
      setCelebrate(true);
      setToast(
        firstTime
          ? `เยี่ยมมาก! ผ่านบท "${lesson.title}" ได้ +${lesson.xp} XP 🎉`
          : `ผ่านอีกรอบแล้ว เก่งมาก! 🎉`,
      );
      if (speech.enabled) {
        speech.speak(firstTime ? 'เยี่ยมมากค่ะ! ผ่านบทนี้แล้ว ไปบทต่อไปกันเลย' : 'ถูกต้องแล้วค่ะ เก่งมาก');
      }
      setTimeout(() => setCelebrate(false), 3200);
      setTimeout(() => setToast(null), 5200);
    } else {
      const passed = result.tasks.filter((t) => t.passed).length;
      pushLine({
        kind: 'msg',
        text: `📋 ภารกิจผ่าน ${passed}/${result.tasks.length} ข้อ — ดูรายการทางซ้ายว่าข้อไหนยังไม่ผ่าน`,
      });
      sfx.pop();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [code, lesson, running, slowMode, speech.enabled]);

  const handleStop = () => {
    cancelRef.current = true;
    runIdRef.current++;
    setRunning(false);
    setCurrentLine(null);
    setDialog(null);
    pushLine({ kind: 'err', text: '⏹ หยุดการทำงานแล้ว' });
  };

  const goRelative = (delta: number) => {
    const idx = LESSONS.findIndex((l) => l.id === lesson.id);
    const next = LESSONS[idx + delta];
    if (next) setLessonId(next.id);
  };

  const lessonIndex = LESSONS.findIndex((l) => l.id === lesson.id);
  const xpPercent = Math.min(100, Math.round((progress.xp / TOTAL_XP) * 100));

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark" aria-hidden>
            🐣
          </div>
          <div className="brand-text">
            <h1>VBA Academy</h1>
            <p>เรียน VBA สนุก ๆ จาก 0 ถึงมือโปร</p>
          </div>
        </div>

        <div className="topbar-spacer" />

        <div className="xp-wrap">
          <div className="xp-bar" role="progressbar" aria-valuenow={xpPercent} aria-valuemin={0} aria-valuemax={100}>
            <div className="xp-fill" style={{ width: `${xpPercent}%` }} />
          </div>
          <span className="xp-label">
            ⭐ {progress.xp} XP · {progress.completed.length}/{LESSONS.length} บท
          </span>
        </div>

        {speech.supported && (
          <>
            <button
              className={`pill-btn ${speech.enabled ? 'on' : 'off'}`}
              type="button"
              onClick={() => speech.setEnabled(!speech.enabled)}
              title="เปิด/ปิดเสียงบรรยาย"
            >
              {speech.enabled ? '🔊 เสียงเปิด' : '🔇 เสียงปิด'}
            </button>
            <select
              className="speed-select"
              value={speech.rate}
              onChange={(e) => speech.setRate(Number(e.target.value))}
              aria-label="ความเร็วเสียงบรรยาย"
              title="ความเร็วเสียงบรรยาย"
            >
              <option value={0.8}>🐢 ช้า</option>
              <option value={1}>🚶 ปกติ</option>
              <option value={1.25}>🐇 เร็ว</option>
            </select>
          </>
        )}
      </header>

      <main className="layout">
        <Sidebar currentId={lesson.id} completed={progress.completed} onPick={setLessonId} />

        <section className="card">
          <LessonPanel
            lesson={lesson}
            level={level}
            tab={tab}
            onTab={setTab}
            tasks={tasks}
            hintIndex={hintIndex}
            onHint={() => setHintIndex((i) => Math.min(i + 1, lesson.hints.length))}
            completed={isCompleted}
          />

          <div className="card-body" style={{ paddingTop: 0 }}>
            <div className="buddy">
              <div className={`buddy-avatar ${speech.speaking ? 'talking' : ''}`} aria-hidden>
                {speech.speaking ? '🗣️' : '🐣'}
              </div>
              <div className="buddy-text">
                <b>น้องสไปซ์</b> พร้อมสอนแล้ว! กด “ฟังคำอธิบาย” เพื่อให้พี่เล่าบทเรียนนี้ให้ฟัง
                {speech.supported ? '' : ' (เบราว์เซอร์นี้ยังไม่รองรับเสียงอ่าน ลองใช้ Chrome หรือ Edge นะ)'}
                <div className="speak-row">
                  <button
                    className={`mini-btn ${speech.speaking ? 'on' : ''}`}
                    type="button"
                    onClick={() => speech.toggle(lesson.narration)}
                    disabled={!speech.supported || !speech.enabled}
                  >
                    {speech.speaking ? '⏹ หยุดเสียง' : '🎧 ฟังคำอธิบาย'}
                  </button>
                  <button className="mini-btn" type="button" onClick={() => goRelative(-1)} disabled={lessonIndex === 0}>
                    ← บทก่อนหน้า
                  </button>
                  <button
                    className="mini-btn"
                    type="button"
                    onClick={() => goRelative(1)}
                    disabled={lessonIndex >= LESSONS.length - 1}
                  >
                    บทถัดไป →
                  </button>
                </div>
                <div className="badge-row">
                  {BADGES.map((b) => {
                    const earned = b.earned(progress);
                    return (
                      <span className={`badge ${earned ? 'earned' : ''}`} key={b.id} title={earned ? 'ได้รับแล้ว' : 'ยังไม่ได้รับ'}>
                        {b.emoji} {b.label}
                      </span>
                    );
                  })}
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="card col-right">
          <div className="card-head">
            <span aria-hidden>⌨️</span>
            <h2>เขียนโค้ด แล้วกดรัน</h2>
            <div style={{ flex: 1 }} />
            <label className="mini-btn" style={{ cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={slowMode}
                onChange={(e) => setSlowMode(e.target.checked)}
                style={{ marginRight: 6 }}
              />
              🐢 ดูทีละบรรทัด
            </label>
          </div>

          <div className="card-body">
            <CodeEditor
              value={code}
              onChange={setCode}
              errorLine={errorLine}
              currentLine={currentLine}
              disabled={running}
            />

            <div className="toolbar">
              <button className="btn btn-run" type="button" onClick={handleRun} disabled={running}>
                {running ? '⏳ กำลังรัน...' : '▶ รันโค้ด'}
              </button>
              {running && (
                <button className="btn btn-ghost" type="button" onClick={handleStop}>
                  ⏹ หยุด
                </button>
              )}
              <button
                className="btn btn-ghost"
                type="button"
                onClick={() => {
                  setCode(lesson.starter);
                  setWorkbook(createWorkbook(lesson));
                  setVersion((v) => v + 1);
                  setTasks([]);
                  setLines([]);
                  setErrorLine(null);
                }}
                disabled={running}
              >
                ♻️ เริ่มใหม่
              </button>
              <button
                className="btn btn-warn"
                type="button"
                onClick={() => {
                  setCode(lesson.solution);
                  setLines([{ kind: 'msg', text: '📗 ใส่เฉลยให้แล้ว ลองอ่านทีละบรรทัดแล้วกดรันดูนะ' }]);
                }}
                disabled={running}
              >
                📗 ดูเฉลย
              </button>
            </div>

            <div style={{ marginTop: 14 }}>
              <SheetGrid
                workbook={workbook}
                version={version}
                activeSheet={activeSheet}
                onSelectSheet={setActiveSheet}
              />
            </div>

            <div style={{ marginTop: 14 }}>
              <div style={{ fontSize: 12.5, fontWeight: 700, marginBottom: 6 }}>🖥️ หน้าต่างผลลัพธ์</div>
              <div className="console">
                {lines.length === 0 ? (
                  <div className="empty">ยังไม่มีผลลัพธ์ — กด ▶ รันโค้ด เพื่อเริ่มเลย</div>
                ) : (
                  lines.map((l, i) => (
                    <div
                      key={i}
                      className={
                        l.kind === 'err' ? 'line-err' : l.kind === 'ok' ? 'line-ok' : l.kind === 'msg' ? 'line-msg' : ''
                      }
                    >
                      {l.text}
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </section>
      </main>

      <div className="footer-note">
        ทำด้วย 💗 สำหรับคนอยากเขียน VBA เป็น · ความคืบหน้าถูกเก็บไว้ในเครื่องคุณเอง ·{' '}
        <button
          className="mini-btn"
          type="button"
          onClick={() => {
            if (confirm('ล้างความคืบหน้าทั้งหมดและเริ่มใหม่ตั้งแต่ต้น?')) {
              reset();
              setLessonId(LESSONS[0].id);
            }
          }}
        >
          ล้างความคืบหน้า
        </button>
      </div>

      <DialogHost request={dialog} />
      <Celebration show={celebrate} />
      {toast && (
        <div className="win-toast">
          <span style={{ fontSize: 26 }} aria-hidden>
            🎉
          </span>
          <span>{toast}</span>
        </div>
      )}
    </div>
  );
}
