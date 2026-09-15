import { useCallback, useEffect, useState } from 'react';
import { LESSONS } from '../content/lessons';

const KEY = 'vba-academy:progress';

export interface Progress {
  completed: string[];
  xp: number;
  lastLesson: string;
  code: Record<string, string>;
}

const EMPTY: Progress = { completed: [], xp: 0, lastLesson: LESSONS[0].id, code: {} };

function load(): Progress {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return EMPTY;
    const parsed = JSON.parse(raw) as Partial<Progress>;
    return {
      completed: Array.isArray(parsed.completed) ? parsed.completed : [],
      xp: typeof parsed.xp === 'number' ? parsed.xp : 0,
      lastLesson: typeof parsed.lastLesson === 'string' ? parsed.lastLesson : LESSONS[0].id,
      code: parsed.code && typeof parsed.code === 'object' ? parsed.code : {},
    };
  } catch {
    return EMPTY;
  }
}

function save(p: Progress) {
  try {
    localStorage.setItem(KEY, JSON.stringify(p));
  } catch {
    /* โหมดส่วนตัวอาจเขียนไม่ได้ ไม่เป็นไร */
  }
}

export const TOTAL_XP = LESSONS.reduce((sum, l) => sum + l.xp, 0);

export interface BadgeDef {
  id: string;
  label: string;
  emoji: string;
  earned: (p: Progress) => boolean;
}

export const BADGES: BadgeDef[] = [
  { id: 'first', label: 'ก้าวแรก', emoji: '🐣', earned: (p) => p.completed.length >= 1 },
  { id: 'five', label: 'ติดลม', emoji: '🚀', earned: (p) => p.completed.length >= 5 },
  { id: 'looper', label: 'นักวนซ้ำ', emoji: '🌀', earned: (p) => p.completed.some((id) => id.startsWith('l4')) },
  { id: 'artist', label: 'นักแต่งตาราง', emoji: '🎨', earned: (p) => p.completed.includes('l5-1') },
  { id: 'half', label: 'ครึ่งทางแล้ว', emoji: '⭐', earned: (p) => p.completed.length >= Math.ceil(LESSONS.length / 2) },
  { id: 'pro', label: 'มือโปร', emoji: '🏆', earned: (p) => p.completed.includes('l6-6') },
  { id: 'all', label: 'จบหลักสูตร', emoji: '👑', earned: (p) => p.completed.length >= LESSONS.length },
];

export function useProgress() {
  const [progress, setProgress] = useState<Progress>(() => load());

  useEffect(() => save(progress), [progress]);

  const complete = useCallback((lessonId: string, xp: number) => {
    setProgress((p) => {
      if (p.completed.includes(lessonId)) return p;
      return { ...p, completed: [...p.completed, lessonId], xp: p.xp + xp };
    });
  }, []);

  const setLastLesson = useCallback((lessonId: string) => {
    setProgress((p) => (p.lastLesson === lessonId ? p : { ...p, lastLesson: lessonId }));
  }, []);

  const saveCode = useCallback((lessonId: string, code: string) => {
    setProgress((p) => ({ ...p, code: { ...p.code, [lessonId]: code } }));
  }, []);

  const reset = useCallback(() => setProgress({ ...EMPTY, code: {} }), []);

  return { progress, complete, setLastLesson, saveCode, reset };
}
