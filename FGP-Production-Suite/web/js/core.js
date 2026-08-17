/* ==========================================================================
   FGP Production Suite - แกนกลาง: เรียก API, ตัวช่วย, เราเตอร์, โมดัล, toast
   ========================================================================== */

const FGP = (() => {
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
    if (!res.ok && data && data.error) throw new Error(data.error);
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
    return THAI_DAYS[d.getDay()] + ' ' + d.getDate() + '/' + (d.getMonth() + 1);
  }

  function isoOf(date) {
    const p = (n) => String(n).padStart(2, '0');
    return date.getFullYear() + '-' + p(date.getMonth() + 1) + '-' + p(date.getDate());
  }

  function todayIso() { return isoOf(new Date()); }

  function shiftDays(iso, days) {
    const d = toDate(iso) || new Date();
    d.setDate(d.getDate() + days);
    return isoOf(d);
  }

  function num(value, digits = 0) {
    if (value === null || value === undefined || isNaN(value)) return '-';
    return Number(value).toLocaleString('en-US', {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    });
  }

  function hhmm(value) {
    const h = Math.floor(value);
    const m = Math.round((value - h) * 60);
    return String(h).padStart(2, '0') + ':' + String(m).padStart(2, '0');
  }

  function esc(text) {
    return String(text === null || text === undefined ? '' : text)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function initials(name) {
    const clean = String(name || '').trim();
    if (!clean) return '?';
    return clean.charAt(0);
  }

  /** ระดับสีตามเปอร์เซ็นต์ ยิ่งมากยิ่งดี */
  function toneHigh(v, good = 95, ok = 85) {
    if (v === null || v === undefined) return 'mute';
    if (v >= good) return 'ok';
    if (v >= ok) return 'warn';
    return 'crit';
  }

  /** ระดับสีตามเปอร์เซ็นต์ ยิ่งมากยิ่งอันตราย เช่น การใช้งานเครื่อง */
  function toneLoad(v, warnAt = 80, critAt = 92) {
    if (v >= critAt) return 'crit';
    if (v >= warnAt) return 'warn';
    return 'ok';
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

  /* ---------------------------------------------------------------- เราเตอร์ */

  const routes = {};
  let currentRoute = '/';

  function route(path, def) { routes[path] = def; }

  function currentPath() {
    const raw = location.hash.replace(/^#/, '') || '/';
    return raw.split('?')[0] || '/';
  }

  function queryParams() {
    const raw = location.hash.split('?')[1] || '';
    return Object.fromEntries(new URLSearchParams(raw));
  }

  async function render() {
    const path = currentPath();
    const def = routes[path] || routes['/'];
    currentRoute = path;

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
      view.scrollTop = 0;
      window.scrollTo({ top: 0, behavior: 'instant' in window ? 'instant' : 'auto' });
    } catch (err) {
      view.innerHTML = '';
      view.appendChild(h(`<div class="card"><div class="empty">
        <strong>โหลดข้อมูลไม่สำเร็จ</strong>
        ${esc(err.message)}<br><br>
        <button class="btn btn-primary" onclick="FGP.render()">ลองอีกครั้ง</button>
      </div></div>`));
    }
    refreshAlertBadge();
  }

  async function refreshAlertBadge() {
    try {
      const data = await api.get('/api/alerts');
      const n = data.counts.critical + data.counts.warn;
      const badge = document.getElementById('alertBadge');
      badge.textContent = n;
      badge.hidden = n === 0;
      const dot = document.getElementById('healthDot');
      dot.className = 'pulse-dot is-live';
      document.getElementById('healthText').textContent = 'ระบบทำงานปกติ';
    } catch (err) {
      const dot = document.getElementById('healthDot');
      dot.className = 'pulse-dot is-down';
      document.getElementById('healthText').textContent = 'ต่อเซิร์ฟเวอร์ไม่ได้';
    }
  }

  return {
    api, route, render, currentPath, queryParams, refreshAlertBadge,
    fmtDate, fmtDayLabel, isoOf, todayIso, shiftDays, toDate,
    num, hhmm, esc, initials, toneHigh, toneLoad, h, toast,
    openModal, closeModal,
    THAI_MONTHS, THAI_DAYS,
  };
})();
