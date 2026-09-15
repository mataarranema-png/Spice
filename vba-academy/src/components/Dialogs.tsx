import { useEffect, useRef, useState } from 'react';

export interface MsgBoxRequest {
  kind: 'msgbox';
  text: string;
  title: string;
  resolve: () => void;
}

export interface InputBoxRequest {
  kind: 'inputbox';
  prompt: string;
  title: string;
  def: string;
  resolve: (value: string | null) => void;
}

export type DialogRequest = MsgBoxRequest | InputBoxRequest;

export function DialogHost({ request }: { request: DialogRequest | null }) {
  const [draft, setDraft] = useState('');
  const okRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (request?.kind === 'inputbox') setDraft(request.def);
    if (request) setTimeout(() => okRef.current?.focus(), 30);
  }, [request]);

  useEffect(() => {
    if (!request) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        if (request.kind === 'msgbox') request.resolve();
        else request.resolve(draft);
      }
      if (e.key === 'Escape' && request.kind === 'inputbox') request.resolve(null);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [request, draft]);

  if (!request) return null;

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true">
      <div className="msgbox">
        <div className="msgbox-title">{request.title}</div>
        {request.kind === 'msgbox' ? (
          <div className="msgbox-body">
            <span style={{ fontSize: 26 }} aria-hidden>
              💬
            </span>
            <span>{request.text}</span>
          </div>
        ) : (
          <div className="msgbox-body" style={{ flexDirection: 'column', gap: 10 }}>
            <span>{request.prompt}</span>
            <input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              aria-label="ช่องกรอกค่า"
              autoFocus
            />
          </div>
        )}
        <div className="msgbox-foot">
          <button
            ref={okRef}
            className="msgbox-btn"
            type="button"
            onClick={() => (request.kind === 'msgbox' ? request.resolve() : request.resolve(draft))}
          >
            ตกลง
          </button>
          {request.kind === 'inputbox' && (
            <button className="msgbox-btn" type="button" onClick={() => request.resolve(null)}>
              ยกเลิก
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export function Celebration({ show }: { show: boolean }) {
  const pieces = useRef(
    Array.from({ length: 70 }, (_, i) => ({
      id: i,
      left: Math.random() * 100,
      delay: Math.random() * 0.6,
      duration: 2.2 + Math.random() * 1.6,
      color: ['#ff8fab', '#ffd166', '#9ce6c4', '#a6dcf5', '#cdb4f6', '#ffb38a'][i % 6],
      rotate: Math.random() * 360,
    })),
  );

  if (!show) return null;

  return (
    <div className="celebrate" aria-hidden>
      {pieces.current.map((p) => (
        <span
          key={p.id}
          className="confetti"
          style={{
            left: `${p.left}%`,
            background: p.color,
            animationDelay: `${p.delay}s`,
            animationDuration: `${p.duration}s`,
            transform: `rotate(${p.rotate}deg)`,
          }}
        />
      ))}
    </div>
  );
}
