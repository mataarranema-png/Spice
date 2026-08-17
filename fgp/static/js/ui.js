// เครื่องมือสร้างหน้าจอ: ไอคอน, จัดรูปแบบตัวเลข, toast, modal
export const icons = {
  dashboard: 'M4 13h6V4H4v9Zm0 7h6v-5H4v5Zm9 0h7v-9h-7v9Zm0-16v5h7V4h-7Z',
  chart: 'M4 20V10m5 10V4m5 16v-7m5 7V8',
  plan: 'M8 2v3m8-3v3M3 9h18M5 5h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Z',
  people: 'M16 20v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 10a4 4 0 1 0 0-8 4 4 0 0 0 0 8Zm13 10v-2a4 4 0 0 0-3-3.87M16 2.13a4 4 0 0 1 0 7.75',
  booking: 'M9 11l3 3 8-8M20 12v7a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h9',
  capacity: 'M3 3v18h18M7 15l4-4 3 3 5-6',
  task: 'M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2M9 5a2 2 0 0 0 2 2h2a2 2 0 0 0 2-2M9 5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2m-6 9 2 2 4-4',
  brain: 'M12 2a3 3 0 0 0-3 3 3 3 0 0 0-3 3v1a3 3 0 0 0 0 6v1a3 3 0 0 0 3 3 3 3 0 0 0 6 0 3 3 0 0 0 3-3v-1a3 3 0 0 0 0-6V8a3 3 0 0 0-3-3 3 3 0 0 0-3-3Z',
  report: 'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6Zm0 0v6h6M9 15h6M9 11h3',
  settings: 'M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm7.4-3a7.4 7.4 0 0 0-.1-1.2l2-1.6-2-3.4-2.4 1a7.5 7.5 0 0 0-2-1.2l-.4-2.6h-4l-.4 2.6c-.7.3-1.4.7-2 1.2l-2.4-1-2 3.4 2 1.6a7.4 7.4 0 0 0 0 2.4l-2 1.6 2 3.4 2.4-1c.6.5 1.3.9 2 1.2l.4 2.6h4l.4-2.6c.7-.3 1.4-.7 2-1.2l2.4 1 2-3.4-2-1.6c.1-.4.1-.8.1-1.2Z',
  monitor: 'M3 4h18v12H3zM8 20h8m-4-4v4',
  alert: 'M12 9v4m0 4h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z',
  watch: 'M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7-10-7-10-7Zm10 3a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z',
  trend: 'M22 17l-8.5-8.5-5 5L2 7',
  shuffle: 'M16 3h5v5M4 20 21 3M21 16v5h-5M15 15l6 6M4 4l5 5',
  stop: 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20ZM5 5l14 14',
  oee: 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Zm0-16v6l4 2',
  anomaly: 'M3 12h4l3 8 4-16 3 8h4',
  logout: 'M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4m7 14 5-5-5-5m5 5H9',
  plus: 'M12 5v14M5 12h14',
  check: 'M20 6 9 17l-5-5',
  x: 'M18 6 6 18M6 6l12 12',
  trash: 'M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2m3 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6',
  edit: 'M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7m-2-9 3 3L12 18H9v-3l9.5-9.5Z',
  download: 'M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3',
  refresh: 'M23 4v6h-6M1 20v-6h6M3.5 9a9 9 0 0 1 14.9-3.4L23 10M1 14l4.6 4.4A9 9 0 0 0 20.5 15',
  sun: 'M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10Zm0-15v2m0 18v2M4.2 4.2l1.4 1.4m12.8 12.8 1.4 1.4M2 12h2m18 0h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4',
  moon: 'M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8Z',
  menu: 'M3 6h18M3 12h18M3 18h18',
  bolt: 'M13 2 3 14h9l-1 8 10-12h-9l1-8Z',
  clock: 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20Zm0-16v6l4 2',
  box: 'M21 8v8a2 2 0 0 1-1 1.7l-7 4a2 2 0 0 1-2 0l-7-4A2 2 0 0 1 3 16V8a2 2 0 0 1 1-1.7l7-4a2 2 0 0 1 2 0l7 4A2 2 0 0 1 21 8Zm-18 .5 9 5 9-5m-9 5V22',
  search: 'M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16Zm10 2-4.3-4.3',
};

export function icon(name, size = 18) {
  const d = icons[name] || icons.box;
  return `<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none"
    stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"
    aria-hidden="true"><path d="${d}"/></svg>`;
}

export const esc = (s) => String(s ?? '').replace(/[&<>"']/g,
  (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

export const nf = (v, d = 0) => Number(v ?? 0).toLocaleString('th-TH',
  { minimumFractionDigits: d, maximumFractionDigits: d });

export const pct = (v) => `${Number(v ?? 0).toFixed(1)}%`;

export function statusOf(value, good = 100, warn = 92) {
  if (value >= good) return 'ok';
  if (value >= warn) return 'warn';
  return 'bad';
}

export function deltaChip(value, suffix = '') {
  const cls = value > 0 ? 'up' : value < 0 ? 'down' : 'flat';
  const sign = value > 0 ? '▲' : value < 0 ? '▼' : '•';
  return `<span class="delta ${cls}">${sign} ${nf(Math.abs(value))}${suffix}</span>`;
}

export function thaiDate(iso) {
  if (!iso) return '-';
  const d = new Date(iso + (iso.length === 10 ? 'T00:00:00' : ''));
  return d.toLocaleDateString('th-TH', { day: 'numeric', month: 'short', year: '2-digit' });
}

export function relTime(ts) {
  if (!ts) return '';
  const diff = (Date.now() - new Date(ts.replace(' ', 'T')).getTime()) / 60000;
  if (diff < 1) return 'เมื่อครู่';
  if (diff < 60) return `${Math.floor(diff)} นาทีที่แล้ว`;
  if (diff < 1440) return `${Math.floor(diff / 60)} ชั่วโมงที่แล้ว`;
  return `${Math.floor(diff / 1440)} วันที่แล้ว`;
}

// ----------------------------------------------------------------- toast

export function toast(message, kind = 'ok') {
  let box = document.querySelector('.toasts');
  if (!box) {
    box = document.createElement('div');
    box.className = 'toasts';
    document.body.appendChild(box);
  }
  const el = document.createElement('div');
  el.className = `toast ${kind}`;
  el.innerHTML = `<span class="dot2"></span><span>${esc(message)}</span>`;
  box.appendChild(el);
  setTimeout(() => {
    el.classList.add('out');
    setTimeout(() => el.remove(), 300);
  }, 3200);
}

// ----------------------------------------------------------------- modal

export function modal({ title, subtitle = '', body, footer, wide = false, onMount }) {
  const overlay = document.createElement('div');
  overlay.className = 'overlay';
  overlay.innerHTML = `
    <div class="modal ${wide ? 'wide' : ''}" role="dialog" aria-modal="true">
      <div class="modal-head">
        <div><h3>${esc(title)}</h3>${subtitle ? `<p>${esc(subtitle)}</p>` : ''}</div>
        <div class="right" style="margin-left:auto">
          <button class="btn icon ghost" data-close aria-label="ปิด">${icon('x', 16)}</button>
        </div>
      </div>
      <div class="modal-body">${body}</div>
      ${footer === null ? '' : `<div class="modal-foot">${footer || `
        <button class="btn" data-close>ยกเลิก</button>
        <button class="btn primary" data-ok>บันทึก</button>`}</div>`}
    </div>`;
  document.body.appendChild(overlay);
  const close = () => { overlay.remove(); document.removeEventListener('keydown', onKey); };
  const onKey = (e) => { if (e.key === 'Escape') close(); };
  document.addEventListener('keydown', onKey);
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay || e.target.closest('[data-close]')) close();
  });
  overlay.querySelector('input,select,textarea')?.focus();
  if (onMount) onMount(overlay, close);
  return { overlay, close };
}

export function confirmDialog(message, onYes, { danger = true, okText = 'ยืนยัน' } = {}) {
  modal({
    title: 'ยืนยันการทำรายการ',
    body: `<p style="font-size:14px;line-height:1.7;color:var(--text-2)">${esc(message)}</p>`,
    footer: `<button class="btn" data-close>ยกเลิก</button>
             <button class="btn ${danger ? 'danger' : 'primary'}" data-ok>${esc(okText)}</button>`,
    onMount(overlay, close) {
      overlay.querySelector('[data-ok]').onclick = async () => { close(); await onYes(); };
    },
  });
}

// ------------------------------------------------------------ ฟอร์มช่วย

export function field(label, inputHtml) {
  return `<div class="field"><label>${esc(label)}</label>${inputHtml}</div>`;
}

export function selectOptions(items, valueKey, labelFn, selected) {
  return items.map((it) => `<option value="${it[valueKey]}"
    ${String(it[valueKey]) === String(selected) ? 'selected' : ''}>${esc(labelFn(it))}</option>`).join('');
}

export function readForm(root) {
  const out = {};
  root.querySelectorAll('[name]').forEach((el) => {
    if (el.type === 'checkbox') out[el.name] = el.checked ? 1 : 0;
    else out[el.name] = el.value;
  });
  return out;
}

export function emptyState(text, sub = '') {
  return `<div class="empty">${icon('box', 42)}<b>${esc(text)}</b>
    ${sub ? `<div class="t-sm">${esc(sub)}</div>` : ''}</div>`;
}

export function skeleton(height = 120) {
  return `<div class="skeleton" style="height:${height}px"></div>`;
}
