// แกนหลักของแอป: เข้าสู่ระบบ, โครงหน้าจอ, เส้นทาง, รีเฟรชอัตโนมัติ
import { api, store } from './api.js';
import { icon, esc, toast, modal, field } from './ui.js';

import dashboard from './views/dashboard.js';
import production from './views/production.js';
import plan from './views/plan.js';
import booking from './views/booking.js';
import capacity from './views/capacity.js';
import tasks from './views/tasks.js';
import smart from './views/smart.js';
import people from './views/people.js';
import reports from './views/reports.js';
import settings from './views/settings.js';
import andon from './views/andon.js';

const VIEWS = { dashboard, production, plan, booking, capacity, tasks, smart, people, reports, settings, andon };

const NAV = [
  { group: 'ภาพรวม' },
  { id: 'dashboard', label: 'แดชบอร์ด', icon: 'dashboard' },
  { id: 'andon', label: 'จอ Andon', icon: 'monitor' },
  { group: 'การผลิต' },
  { id: 'production', label: 'บันทึกยอดผลิต', icon: 'chart' },
  { id: 'plan', label: 'แผนการผลิต', icon: 'plan' },
  { id: 'capacity', label: 'กำลังการผลิต', icon: 'capacity' },
  { group: 'กำลังคน' },
  { id: 'booking', label: 'จองคิวคน', icon: 'booking' },
  { id: 'people', label: 'พนักงาน & ทักษะ', icon: 'people' },
  { id: 'tasks', label: 'กระจายงาน Leader', icon: 'task', badgeKey: 'tasks' },
  { group: 'ระบบอัจฉริยะ' },
  { id: 'smart', label: 'ศูนย์วิเคราะห์', icon: 'brain' },
  { id: 'reports', label: 'รายงาน & Export', icon: 'report' },
  { id: 'settings', label: 'ตั้งค่าระบบ', icon: 'settings', role: 'manager' },
];

const app = document.getElementById('app');
let currentView = null;
let refreshTimer = null;
const badges = {};

// ------------------------------------------------------------------ ธีม

function initTheme() {
  const saved = localStorage.getItem('fgp-theme') || 'dark';
  document.documentElement.dataset.theme = saved;
}

function toggleTheme() {
  const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
  document.documentElement.dataset.theme = next;
  localStorage.setItem('fgp-theme', next);
  document.querySelector('[data-theme-btn]')?.replaceChildren(
    ...htmlToNodes(icon(next === 'dark' ? 'sun' : 'moon', 17)));
}

function htmlToNodes(html) {
  const t = document.createElement('template');
  t.innerHTML = html;
  return [...t.content.childNodes];
}

// -------------------------------------------------------------- เข้าสู่ระบบ

function renderLogin(message = '') {
  document.body.className = '';
  app.innerHTML = `
    <div class="login-wrap">
      <form class="login" id="loginForm">
        <div class="brand">
          <div class="brand-mark">FGP</div>
          <div class="brand-text"><b>FGP Production System</b><span>PANASONIC · แผนก FGP</span></div>
        </div>
        <h2>เข้าสู่ระบบ</h2>
        <p class="lead">ระบบบริหารการผลิตของแผนก FGP รวมยอดผลิต แผนงาน กำลังคน และการวิเคราะห์ไว้ที่เดียว</p>
        <div id="loginErr">${message ? `<div class="err">${esc(message)}</div>` : ''}</div>
        ${field('ชื่อผู้ใช้', '<input name="username" autocomplete="username" required placeholder="เช่น leader1">')}
        ${field('รหัสผ่าน', '<input name="password" type="password" autocomplete="current-password" required placeholder="••••••••">')}
        <button class="btn primary" type="submit">${icon('bolt', 17)} เข้าสู่ระบบ</button>
        <div class="hint">
          บัญชีตัวอย่างสำหรับทดลองใช้<br>
          <code>admin / Admin@123</code> · ผู้ดูแลระบบ<br>
          <code>manager / Manager@123</code> · หัวหน้าแผนก<br>
          <code>leader1 / Leader@123</code> · หัวหน้าไลน์<br>
          <code>operator / Operator@123</code> · พนักงานบันทึกยอด
        </div>
      </form>
    </div>`;

  document.getElementById('loginForm').onsubmit = async (e) => {
    e.preventDefault();
    const btn = e.target.querySelector('button');
    btn.disabled = true;
    btn.innerHTML = 'กำลังตรวจสอบ...';
    try {
      await api.post('/api/auth/login', {
        username: e.target.username.value.trim(),
        password: e.target.password.value,
      });
      api.clearCache();
      await boot();
    } catch (err) {
      document.getElementById('loginErr').innerHTML = `<div class="err">${esc(err.message)}</div>`;
      btn.disabled = false;
      btn.innerHTML = `${icon('bolt', 17)} เข้าสู่ระบบ`;
    }
  };
}

// ------------------------------------------------------------- โครงหน้าจอ

function navHtml() {
  return NAV.map((n) => {
    if (n.group) return `<div class="nav-group">${esc(n.group)}</div>`;
    if (n.role && !store.can(n.role)) return '';
    const badge = badges[n.badgeKey] ? `<span class="nav-badge">${badges[n.badgeKey]}</span>` : '';
    return `<a class="nav-item" href="#/${n.id}" data-nav="${n.id}">
      ${icon(n.icon)}<span>${esc(n.label)}</span>${badge}</a>`;
  }).join('');
}

function renderShell() {
  const u = store.user;
  const initials = (u.name || 'U').trim().slice(0, 2);
  app.innerHTML = `
    <div class="shell">
      <aside class="sidebar" id="sidebar">
        <div class="brand">
          <div class="brand-mark">FGP</div>
          <div class="brand-text"><b>FGP Production</b><span>PANASONIC</span></div>
        </div>
        <nav class="nav" id="nav">${navHtml()}</nav>
        <div class="sidebar-foot">
          <div class="user-chip">
            <div class="avatar">${esc(initials)}</div>
            <div style="min-width:0">
              <b>${esc(u.name)}</b>
              <span>${esc({ admin: 'ผู้ดูแลระบบ', manager: 'หัวหน้าแผนก', leader: 'หัวหน้าไลน์',
                operator: 'พนักงาน', viewer: 'ผู้ชม' }[u.role] || u.role)}</span>
            </div>
            <button class="btn icon ghost" id="logoutBtn" title="ออกจากระบบ"
              style="margin-left:auto">${icon('logout', 17)}</button>
          </div>
        </div>
      </aside>

      <div class="main">
        <header class="topbar">
          <button class="btn icon ghost menu-btn" id="menuBtn">${icon('menu', 18)}</button>
          <div class="page-title"><h1 id="pageTitle">แดชบอร์ด</h1><p id="pageSub"></p></div>
          <div class="topbar-spacer"></div>
          <div class="row" id="globalFilter">
            <input type="date" id="fDate" value="${store.date}" style="width:150px">
            <div class="seg" id="fShift">
              <button data-shift="A" class="${store.shift === 'A' ? 'on' : ''}">กะ A</button>
              <button data-shift="B" class="${store.shift === 'B' ? 'on' : ''}">กะ B</button>
            </div>
          </div>
          <div class="clock"><span class="pulse"></span><span id="clock"></span></div>
          <button class="btn icon ghost" data-theme-btn title="สลับธีม">
            ${icon(document.documentElement.dataset.theme === 'dark' ? 'sun' : 'moon', 17)}</button>
        </header>
        <main id="viewRoot" class="view"></main>
      </div>
    </div>`;

  document.getElementById('logoutBtn').onclick = async () => {
    await api.post('/api/auth/logout');
    store.user = null;
    renderLogin('ออกจากระบบเรียบร้อย');
  };
  document.querySelector('[data-theme-btn]').onclick = toggleTheme;
  document.getElementById('menuBtn').onclick = () => {
    document.getElementById('sidebar').classList.toggle('open');
  };
  document.getElementById('fDate').onchange = (e) => {
    store.setFilter(e.target.value, null);
    route();
  };
  document.getElementById('fShift').onclick = (e) => {
    const btn = e.target.closest('[data-shift]');
    if (!btn) return;
    store.setFilter(null, btn.dataset.shift);
    document.querySelectorAll('#fShift button').forEach((b) => b.classList.toggle('on', b === btn));
    route();
  };
  document.getElementById('nav').onclick = () => {
    document.getElementById('sidebar').classList.remove('open');
  };

  tick();
  setInterval(tick, 1000);
}

function tick() {
  const el = document.getElementById('clock');
  if (el) el.textContent = new Date().toLocaleTimeString('th-TH', { hour12: false });
}

// ---------------------------------------------------------------- เส้นทาง

async function route() {
  const id = (location.hash.replace('#/', '') || 'dashboard').split('?')[0];
  const view = VIEWS[id] || VIEWS.dashboard;

  if (id === 'andon') {
    document.body.classList.add('andon-mode');
    await view.render(app);
    return;
  }
  document.body.classList.remove('andon-mode');
  if (!document.getElementById('viewRoot')) renderShell();

  document.querySelectorAll('[data-nav]').forEach((a) =>
    a.classList.toggle('active', a.dataset.nav === id));
  document.getElementById('pageTitle').textContent = view.title;
  document.getElementById('pageSub').textContent = view.subtitle || '';
  document.getElementById('globalFilter').classList.toggle('hide', view.hideFilter === true);

  const root = document.getElementById('viewRoot');
  root.innerHTML = `<div class="skeleton" style="height:150px"></div>
    <div class="grid g2 mt"><div class="skeleton" style="height:260px"></div>
    <div class="skeleton" style="height:260px"></div></div>`;
  currentView = view;

  try {
    await view.render(root);
  } catch (err) {
    root.innerHTML = `<div class="card"><div class="empty">${icon('alert', 42)}
      <b>โหลดหน้านี้ไม่สำเร็จ</b><div class="t-sm">${esc(err.message)}</div></div></div>`;
  }
  refreshBadges();

  clearInterval(refreshTimer);
  if (view.autoRefresh) {
    refreshTimer = setInterval(() => {
      if (document.hidden) return;
      view.render(root).catch(() => {});
    }, view.autoRefresh);
  }
}

async function refreshBadges() {
  try {
    const { items } = await api.get('/api/tasks', { status: 'open' });
    badges.tasks = items.length || 0;
    const nav = document.getElementById('nav');
    if (nav) {
      const active = document.querySelector('.nav-item.active')?.dataset.nav;
      nav.innerHTML = navHtml();
      nav.querySelectorAll('[data-nav]').forEach((a) =>
        a.classList.toggle('active', a.dataset.nav === active));
    }
  } catch { /* ไม่สำคัญพอที่จะรบกวนผู้ใช้ */ }
}

// ------------------------------------------------------------------ เริ่ม

async function boot() {
  try {
    await store.bootstrap();
    renderShell();
    await route();
  } catch (err) {
    renderLogin(err.message.includes('เข้าสู่ระบบ') ? '' : '');
  }
}

window.addEventListener('hashchange', route);
window.addEventListener('fgp:unauthorized', () => {
  if (store.user) {
    store.user = null;
    renderLogin('เซสชันหมดอายุ กรุณาเข้าสู่ระบบอีกครั้ง');
  }
});
window.addEventListener('error', (e) => {
  if (e.message?.includes('ResizeObserver')) return;
});

// ปุ่มลัด: กด g แล้วตามด้วยตัวเลข เพื่อสลับหน้า
let lastKey = '';
document.addEventListener('keydown', (e) => {
  if (e.target.matches('input,select,textarea')) return;
  const pages = ['dashboard', 'production', 'plan', 'booking', 'capacity', 'tasks', 'smart', 'people', 'reports'];
  if (lastKey === 'g' && /^[1-9]$/.test(e.key) && pages[+e.key - 1]) {
    location.hash = '#/' + pages[+e.key - 1];
  }
  lastKey = e.key;
});

initTheme();
boot();

export { modal, toast };
