import { useCallback, useEffect, useRef, useState } from 'react';

const STORAGE_KEY = 'vba-academy:voice';

interface VoicePrefs {
  enabled: boolean;
  rate: number;
}

function loadPrefs(): VoicePrefs {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return { enabled: true, rate: 1, ...JSON.parse(raw) };
  } catch {
    /* ไม่มีสิทธิ์อ่าน storage ก็ใช้ค่าเริ่มต้น */
  }
  return { enabled: true, rate: 1 };
}

function savePrefs(prefs: VoicePrefs) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
  } catch {
    /* ไม่เป็นไร */
  }
}

export interface SpeechController {
  supported: boolean;
  hasThaiVoice: boolean;
  enabled: boolean;
  speaking: boolean;
  rate: number;
  setEnabled: (v: boolean) => void;
  setRate: (v: number) => void;
  speak: (text: string) => void;
  stop: () => void;
  toggle: (text: string) => void;
}

/** เลือกเสียงไทยที่ฟังดูดีที่สุดเท่าที่เครื่องมี */
function pickVoice(voices: SpeechSynthesisVoice[]): SpeechSynthesisVoice | null {
  const thai = voices.filter((v) => v.lang?.toLowerCase().startsWith('th'));
  if (thai.length) {
    const preferred = thai.find((v) => /premium|enhanced|natural|google/i.test(v.name));
    return preferred ?? thai[0];
  }
  return null;
}

export function useSpeech(): SpeechController {
  const supported =
    typeof window !== 'undefined' && 'speechSynthesis' in window && 'SpeechSynthesisUtterance' in window;

  const [prefs, setPrefs] = useState<VoicePrefs>(() => loadPrefs());
  const [speaking, setSpeaking] = useState(false);
  const [voice, setVoice] = useState<SpeechSynthesisVoice | null>(null);
  const [voicesLoaded, setVoicesLoaded] = useState(false);
  const currentRef = useRef<SpeechSynthesisUtterance | null>(null);

  useEffect(() => {
    if (!supported) return;
    const sync = () => {
      const list = window.speechSynthesis.getVoices();
      if (list.length) {
        setVoice(pickVoice(list));
        setVoicesLoaded(true);
      }
    };
    sync();
    window.speechSynthesis.addEventListener('voiceschanged', sync);
    return () => window.speechSynthesis.removeEventListener('voiceschanged', sync);
  }, [supported]);

  useEffect(() => savePrefs(prefs), [prefs]);

  const stop = useCallback(() => {
    if (!supported) return;
    window.speechSynthesis.cancel();
    currentRef.current = null;
    setSpeaking(false);
  }, [supported]);

  const speak = useCallback(
    (text: string) => {
      if (!supported || !prefs.enabled || !text.trim()) return;
      window.speechSynthesis.cancel();
      const utter = new SpeechSynthesisUtterance(text);
      utter.lang = 'th-TH';
      utter.rate = prefs.rate;
      utter.pitch = 1.08;
      if (voice) utter.voice = voice;
      utter.onend = () => {
        setSpeaking(false);
        currentRef.current = null;
      };
      utter.onerror = () => {
        setSpeaking(false);
        currentRef.current = null;
      };
      currentRef.current = utter;
      setSpeaking(true);
      // Safari/Chrome บางเวอร์ชันต้องหน่วงนิดหนึ่งหลัง cancel()
      setTimeout(() => {
        if (currentRef.current === utter) window.speechSynthesis.speak(utter);
      }, 60);
    },
    [supported, prefs.enabled, prefs.rate, voice],
  );

  const toggle = useCallback(
    (text: string) => {
      if (speaking) stop();
      else speak(text);
    },
    [speaking, speak, stop],
  );

  useEffect(() => () => {
    if (supported) window.speechSynthesis.cancel();
  }, [supported]);

  return {
    supported,
    hasThaiVoice: !!voice || !voicesLoaded,
    enabled: prefs.enabled,
    speaking,
    rate: prefs.rate,
    setEnabled: (v: boolean) => {
      if (!v) stop();
      setPrefs((p) => ({ ...p, enabled: v }));
    },
    setRate: (v: number) => setPrefs((p) => ({ ...p, rate: v })),
    speak,
    stop,
    toggle,
  };
}

/** เอฟเฟกต์เสียงสั้น ๆ ด้วย WebAudio (ไม่ต้องโหลดไฟล์) */
let audioCtx: AudioContext | null = null;

function ctx(): AudioContext | null {
  if (typeof window === 'undefined') return null;
  try {
    const Ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!Ctor) return null;
    if (!audioCtx) audioCtx = new Ctor();
    return audioCtx;
  } catch {
    return null;
  }
}

function tone(freq: number, start: number, duration: number, gain = 0.08) {
  const ac = ctx();
  if (!ac) return;
  const osc = ac.createOscillator();
  const g = ac.createGain();
  osc.type = 'sine';
  osc.frequency.value = freq;
  g.gain.setValueAtTime(0, ac.currentTime + start);
  g.gain.linearRampToValueAtTime(gain, ac.currentTime + start + 0.02);
  g.gain.exponentialRampToValueAtTime(0.0001, ac.currentTime + start + duration);
  osc.connect(g).connect(ac.destination);
  osc.start(ac.currentTime + start);
  osc.stop(ac.currentTime + start + duration + 0.02);
}

export const sfx = {
  success() {
    tone(659.25, 0, 0.16);
    tone(783.99, 0.1, 0.18);
    tone(1046.5, 0.22, 0.3);
  },
  fail() {
    tone(311.13, 0, 0.18, 0.06);
    tone(233.08, 0.12, 0.26, 0.06);
  },
  pop() {
    tone(880, 0, 0.09, 0.05);
  },
};
