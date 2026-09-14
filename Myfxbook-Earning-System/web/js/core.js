/* ==========================================================================
   Myfxbook Earning System - แกนกลาง: เรียก API, จัดรูปตัวเงิน, เราเตอร์, โมดัล
   ========================================================================== */

const MFE = (() => {
  'use strict';

  /* -------------------------------------------------------------- เรียก API */

  async function request(path, options = {}) {
    const res = await fetch(path, {
      headers: { 'Content-Type': 'application/json' },
      ...options,
    });
    let data = null;
    try {
      data = await res.json();
    } catch (err) {
      throw new Error('เซิร์ฟเวอร์ตอบกลับมาไม่ถูกต้อง');
    }
    if (data && data.ok === false && data.error) throw new Error(data.error);
    if (!res.ok) throw new Error('เรียกข้อมูลไม่สำเร็จ (' + res.status + ')');
    return data;
  }

  const api = {
    get: (path) => request(path),
    post: (path, body) => request(path, { method: 'POST', body: JSON.stringify(body || {}) }),
  };

  /* ------------------------------------------------------------- ตัวช่วยทั่วไป */

  const THAI_MONTHS = ['ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.',
                       'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.'];
  const THAI_DAYS = ['อา.', 'จ.', 'อ.', 'พ.', 'พฤ.', 'ศ.', 'ส.'];

  function toDate(iso) {
    if (!iso) return null;
    const parts = String(iso).slice(0, 10).split('-').map(Number);
    if (parts.length !== 3 || parts.some(isNaN)) return null;
    return new Date(parts[0], parts[1] - 1, parts[2]);
  }

  function fmtDate(iso, withYear) {
    const d = toDate(iso);
    if (!d) return '-';
    const base = d.getDate() + ' ' + THAI_MONTHS[d.getMonth()];
    return withYear ? base + ' ' + String(d.getFullYear() + 543).slice(2) : base;
  }

  function fmtDayLabel(iso) {
    const d = toDate(iso);
    if (!d) return '-';
    return d.getDate() + '/' + (d.getMonth() + 1);
  }

  function fmtStamp(text) {
    if (!text) return 'ยังไม่มีข้อมูล';
    const clean = String(text).replace('T', ' ');
    return fmtDate(clean, true) + ' ' + clean.slice(11, 16);
  }

  function isoOf(date) {
    const p = (n) => String(n).padStart(2, '0');
    return date.getFullYear() + '-' + p(date.getMonth() + 1) + '-' + p(date.getDate());
  }

  function todayIso() { return isoOf(new Date()); }

  function num(value, digits = 0) {
    if (value === null || value === undefined || isNaN(value)) return '-';
    return Number(value).toLocaleString('en-US', {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    });
  }

  /** จำนวนเงินพร้อมสกุล ใช้ทศนิยมสองตำแหน่งเสมอเพื่อให้หลักตรงกัน */
  function money(value, currency, digits = 2) {
    if (value === null || value === undefined || isNaN(value)) return '-';
    const text = num(value, digits);
    return currency ? text + ' ' + currency : text;
  }

  /** ตัวเลขที่ต้องเห็นทันทีว่าบวกหรือลบ คืน HTML พร้อมสีและเครื่องหมาย */
  function signed(value, currency, digits = 2) {
    const v = Number(value || 0);
    const cls = v > 0 ? 'money-up' : v < 0 ? 'money-down' : 'money-flat';
    const sign = v > 0 ? '+' : '';
    return `<span class="${cls}">${sign}${num(v, digits)}${currency ? ' ' + esc(currency) : ''}</span>`;
  }

  function pct(value, digits = 1) {
    if (value === null || value === undefined || isNaN(value)) return '-';
    return num(value, digits) + '%';
  }

  function esc(text) {
    return String(text === null || text === undefined ? '' : text)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  /** ระดับสีของ drawdown ยิ่งมากยิ่งอันตราย */
  function toneDrawdown(value, warnAt = 10, critAt = 20) {
    if (value >= critAt) return 'crit';
    if (value >= warnAt) return 'warn';
    return 'ok';
  }

  /** ระดับสีตามความคืบหน้าเทียบเป้าหมาย */
  function toneGoal(actualPct, pacePct) {
    if (actualPct === null || actualPct === undefined) return 'mute';
    if (actualPct >= 100) return 'ok';
    if (actualPct >= pacePct) return 'ok';
    if (actualPct >= pacePct * 0.7) return 'warn';
    return 'crit';
  }

  const STATUS_META = {
    NONE: { label: 'ไม่มีส่วนแบ่ง', chip: 'chip-mute' },
    DUE: { label: 'ค้างจ่าย', chip: 'chip-warn' },
    PARTIAL: { label: 'จ่ายบางส่วน', chip: 'chip-info' },
    PAID: { label: 'จ่ายครบแล้ว', chip: 'chip-ok' },
  };

  function statusChip(status) {
    const meta = STATUS_META[status] || STATUS_META.NONE;
    return `<span class="chip ${meta.chip}">${meta.label}</span>`;
  }

  function h(html) {
    const t = document.createElement('template');
    t.innerHTML = html.trim();
    return t.content.firstElementChild;
  }

  /* ------------------------------------------------------------------ toast */

  function toast(title, detail, kind = '') {
    const root = document.getElementById('toasts');
    const el = h(`<div class="toast ${kind}">
      <span class="bar"></span>
      <div><strong>${esc(title)}</strong>${detail ? `<p>${esc(detail)}</p>` : ''}</div>
    </div>`);
    root.appendChild(el);
    setTimeout(() => {
      el.classList.add('out');
      setTimeout(() => el.remove(), 300);
    }, 3600);
  }

  /* ------------------------------------------------------------------ โมดัล */

  const modalRoot = () => document.getElementById('modalRoot');

  function openModal(title, bodyHtml, footHtml) {
    const root = modalRoot();
    document.getElementById('modalTitle').textContent = title;
    document.getElementById('modalBody').innerHTML = bodyHtml;
    document.getElementById('modalFoot').innerHTML = footHtml || '';
    root.hidden = false;
    document.body.style.overflow = 'hidden';
    const first = root.querySelector('input, select, textarea, button');
    if (first) setTimeout(() => first.focus(), 60);
  }

  function closeModal() {
    modalRoot().hidden = true;
    document.body.style.overflow = '';
  }

  /** อ่านค่าจากฟอร์มในโมดัลเป็นอ็อบเจ็กต์เดียว รองรับ checkbox ด้วย */
  function modalValues() {
    const out = {};
    modalRoot().querySelectorAll('[name]').forEach((el) => {
      out[el.name] = el.type === 'checkbox' ? el.checked : el.value;
    });
    return out;
  }

  /* ---------------------------------------------------------------- เราเตอร์ */

  const routes = {};

  function route(path, def) { routes[path] = def; }

  function currentPath() {
    const raw = location.hash.replace(/^#/, '') || '/';
    return raw.split('?')[0] || '/';
  }

  function queryParams() {
    const raw = location.hash.split('?')[1] || '';
    return Object.fromEntries(new URLSearchParams(raw));
  }

  function go(path) {
    if (location.hash === '#' + path) render();
    else location.hash = path;
  }

  async function render() {
    const path = currentPath();
    const def = routes[path] || routes['/'];

    document.querySelectorAll('.nav-item').forEach((el) => {
      el.classList.toggle('is-active', el.dataset.route === path);
    });
    document.getElementById('pageTitle').textContent = def.title;
    document.getElementById('pageSub').textContent = def.sub;

    const view = document.getElementById('view');
    view.innerHTML = '<div class="boot"><div class="boot-ring"></div><p>กำลังโหลดข้อมูล</p></div>';
    try {
      const node = await def.view(queryParams());
      view.innerHTML = '';
      view.appendChild(node);
      window.scrollTo({ top: 0, behavior: 'instant' in window ? 'instant' : 'auto' });
    } catch (err) {
      view.innerHTML = '';
      view.appendChild(h(`<div class="card"><div class="empty">
        <strong>โหลดข้อมูลไม่สำเร็จ</strong>
        ${esc(err.message)}<br><br>
        <button class="btn btn-primary" onclick="MFE.render()">ลองอีกครั้ง</button>
      </div></div>`));
    }
    refreshStatusBar();
  }

  async function refreshStatusBar() {
    try {
      const data = await api.get('/api/alerts');
      const n = data.counts.critical + data.counts.warn;
      const badge = document.getElementById('alertBadge');
      badge.textContent = n;
      badge.hidden = n === 0;
      document.getElementById('healthDot').className = 'pulse-dot is-live';
      const info = await api.get('/api/connect');
      document.getElementById('healthText').textContent = info.demo_mode
        ? 'โหมดสาธิต ข้อมูลตัวอย่าง'
        : info.connected ? 'เชื่อมต่อ Myfxbook แล้ว' : 'ยังไม่ได้เชื่อมต่อ Myfxbook';
      const stamp = document.getElementById('footStamp');
      if (stamp) stamp.textContent = 'ซิงก์ล่าสุด ' + fmtStamp(info.last_sync_at);
    } catch (err) {
      document.getElementById('healthDot').className = 'pulse-dot is-down';
      document.getElementById('healthText').textContent = 'ต่อเซิร์ฟเวอร์ไม่ได้';
    }
  }

  return {
    api, route, render, go, currentPath, queryParams, refreshStatusBar,
    fmtDate, fmtDayLabel, fmtStamp, isoOf, todayIso, toDate,
    num, money, signed, pct, esc, toneDrawdown, toneGoal, statusChip, h, toast,
    openModal, closeModal, modalValues,
    THAI_MONTHS, THAI_DAYS, STATUS_META,
  };
})();
