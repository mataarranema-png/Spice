/* ==========================================================================
   Myfxbook Earning System - การกระทำทั้งหมด การผูกเส้นทาง และการเริ่มโปรแกรม
   ========================================================================== */

const Actions = (() => {
  'use strict';

  const { api, esc, num, toast, openModal, closeModal, modalValues, render, go } = MFE;

  /** ครอบการเรียก API ที่เปลี่ยนข้อมูล: กันกดซ้ำ แจ้งผล แล้ววาดหน้าใหม่ */
  async function run(fn, okTitle, opts = {}) {
    const btn = opts.button;
    if (btn) { btn.disabled = true; btn.classList.add('is-loading'); }
    try {
      const res = await fn();
      if (opts.closeModal !== false) closeModal();
      toast(okTitle, (res && res.message) || '', 'ok');
      await render();
      return res;
    } catch (err) {
      toast('ทำรายการไม่สำเร็จ', err.message, 'err');
      return null;
    } finally {
      if (btn) { btn.disabled = false; btn.classList.remove('is-loading'); }
    }
  }

  /* ------------------------------------------------------------ เชื่อมต่อ */

  function login() {
    openModal('เข้าสู่ระบบ Myfxbook', `
      <div class="form-grid">
        <label class="field full"><span>อีเมลที่ใช้กับ Myfxbook</span>
          <input name="email" type="email" autocomplete="username" placeholder="you@example.com"></label>
        <label class="field full"><span>รหัสผ่าน</span>
          <input name="password" type="password" autocomplete="current-password"></label>
      </div>
      <p class="alert-hint">รหัสผ่านถูกส่งไปที่ Myfxbook เพื่อขอ session เท่านั้น ระบบไม่บันทึกรหัสผ่านลงเครื่อง</p>`,
      `<button class="btn btn-ghost" onclick="MFE.closeModal()">ยกเลิก</button>
       <button class="btn btn-primary" onclick="Actions.doLogin(this)">เข้าสู่ระบบ</button>`);
  }

  function doLogin(btn) {
    const v = modalValues();
    if (!v.email || !v.password) { toast('กรอกข้อมูลไม่ครบ', 'ต้องมีทั้งอีเมลและรหัสผ่าน', 'err'); return; }
    return run(() => api.post('/api/connect/login', v), 'เชื่อมต่อ Myfxbook แล้ว', { button: btn });
  }

  function logout() {
    return run(() => api.post('/api/connect/logout', {}), 'ออกจากระบบแล้ว');
  }

  function setDemo(on) {
    return run(() => api.post('/api/connect/demo', { demo: on }), 'เปลี่ยนโหมดแล้ว');
  }

  async function syncNow(btn) {
    toast('กำลังซิงก์ข้อมูล', 'ดึงพอร์ตและกำไรรายวันจาก Myfxbook', '');
    return run(() => api.post('/api/sync', {}), 'ซิงก์เสร็จแล้ว', { button: btn });
  }

  /* --------------------------------------------------------- เงื่อนไขพอร์ต */

  async function editRule(accountId) {
    let data;
    try {
      data = await api.get('/api/accounts/' + accountId);
    } catch (err) {
      toast('เปิดเงื่อนไขไม่ได้', err.message, 'err');
      return;
    }
    const a = data.account;
    const r = a.rule || { label: 'ส่วนแบ่งกำไร', share_pct: 30, use_hwm: true, min_profit: 0, fixed_fee: 0, active: true };
    openModal('เงื่อนไขส่วนแบ่ง · ' + a.name, `
      <div class="form-grid">
        <label class="field full"><span>ชื่อเงื่อนไข</span>
          <input name="label" value="${esc(r.label)}" maxlength="60"></label>
        <label class="field"><span>ส่วนแบ่งกำไร (%)</span>
          <input name="share_pct" type="number" step="0.5" min="0" max="100" value="${r.share_pct}"></label>
        <label class="field"><span>กำไรขั้นต่ำที่เริ่มคิด (${esc(a.currency)})</span>
          <input name="min_profit" type="number" step="1" min="0" value="${r.min_profit}"></label>
        <label class="field"><span>ค่าธรรมเนียมคงที่ต่อรอบ (${esc(a.currency)})</span>
          <input name="fixed_fee" type="number" step="1" min="0" value="${r.fixed_fee}"></label>
      </div>
      <label class="check" style="margin-top:12px">
        <input type="checkbox" name="use_hwm" ${r.use_hwm ? 'checked' : ''}>
        <span>ใช้ High-Water Mark (คิดส่วนแบ่งเฉพาะกำไรที่ทำจุดสูงสุดใหม่)</span></label>
      <label class="check" style="margin-top:8px">
        <input type="checkbox" name="active" ${r.active ? 'checked' : ''}>
        <span>คิดส่วนแบ่งพอร์ตนี้อยู่</span></label>
      <p class="alert-hint">บันทึกแล้วระบบจะคิดรายได้ของพอร์ตนี้ใหม่ทั้งเส้นเวลา</p>`,
      `<button class="btn btn-ghost" onclick="MFE.closeModal()">ยกเลิก</button>
       <button class="btn btn-primary" onclick="Actions.saveRule(${accountId}, this)">บันทึกและคิดใหม่</button>`);
  }

  function saveRule(accountId, btn) {
    return run(() => api.post('/api/accounts/' + accountId + '/rule', modalValues()),
               'บันทึกเงื่อนไขแล้ว', { button: btn });
  }

  function toggleTrack(accountId, tracked) {
    return run(() => api.post('/api/accounts/' + accountId + '/track', { tracked }),
               tracked ? 'กลับมาติดตามพอร์ตนี้แล้ว' : 'หยุดติดตามพอร์ตนี้แล้ว');
  }

  async function refreshIntel(btn) {
    if (btn) { btn.disabled = true; btn.classList.add('is-loading'); }
    try {
      await api.get('/api/intelligence?force=1');
      toast('คำนวณใหม่แล้ว', 'จำลองเส้นทางใหม่จากข้อมูลล่าสุด', 'ok');
      await render();
    } catch (err) {
      toast('คำนวณไม่สำเร็จ', err.message, 'err');
    } finally {
      if (btn) { btn.disabled = false; btn.classList.remove('is-loading'); }
    }
  }

  function planCapital() {
    const el = document.getElementById('capTarget');
    const value = Number(el && el.value);
    if (!value || value < 0) { toast('ใส่ตัวเลขก่อน', 'ระบุรายได้ต่อเดือนที่ต้องการ', 'err'); return; }
    go('/revenue?target=' + value);
  }

  function recompute(btn) {
    return run(() => api.post('/api/earnings/recompute', {}), 'คิดรายได้ใหม่แล้ว', { button: btn });
  }

  /* ------------------------------------------------------------ จ่ายเงิน */

  async function payFor(accountId, periodKey, amount, currency) {
    let list = [];
    try {
      const data = await api.get('/api/accounts');
      list = data.accounts;
    } catch (err) { /* เลือกพอร์ตไม่ได้ก็ยังบันทึกแบบไม่ผูกพอร์ตได้ */ }

    const options = ['<option value="">ไม่ผูกกับพอร์ตใดพอร์ตหนึ่ง</option>']
      .concat(list.map((a) => `<option value="${a.id}" ${a.id === accountId ? 'selected' : ''}>${esc(a.name)} (${esc(a.currency)})</option>`))
      .join('');

    openModal('บันทึกการจ่ายเงิน', `
      <div class="form-grid">
        <label class="field full"><span>พอร์ต</span><select name="account_id">${options}</select></label>
        <label class="field"><span>รอบที่จ่าย</span>
          <input name="period_key" value="${esc(periodKey || '')}" placeholder="เช่น 2026-03"></label>
        <label class="field"><span>วันที่จ่าย</span>
          <input name="paid_at" type="date" value="${MFE.todayIso()}"></label>
        <label class="field"><span>จำนวนเงิน</span>
          <input name="amount" type="number" step="0.01" min="0" value="${amount > 0 ? amount : ''}"></label>
        <label class="field"><span>สกุลเงิน</span>
          <input name="currency" value="${esc(currency || '')}" maxlength="5" placeholder="ตามสกุลของพอร์ต"></label>
        <label class="field"><span>ช่องทาง</span>
          <input name="method" value="โอนธนาคาร" maxlength="40"></label>
        <label class="field"><span>ผู้รับเงิน</span>
          <input name="payee" maxlength="80" placeholder="ชื่อผู้รับ"></label>
        <label class="field full"><span>หมายเหตุ</span>
          <input name="note" maxlength="200" placeholder="เลขอ้างอิงการโอน หรือรายละเอียดอื่น"></label>
      </div>`,
      `<button class="btn btn-ghost" onclick="MFE.closeModal()">ยกเลิก</button>
       <button class="btn btn-primary" onclick="Actions.savePayout(this)">บันทึกการจ่าย</button>`);
  }

  function savePayout(btn) {
    const v = modalValues();
    if (!Number(v.amount)) { toast('ยังกรอกไม่ครบ', 'ต้องระบุจำนวนเงินที่มากกว่า 0', 'err'); return; }
    return run(() => api.post('/api/payouts', v), 'บันทึกการจ่ายเงินแล้ว', { button: btn });
  }

  function deletePayout(id) {
    openModal('ยืนยันการลบ', '<p>ต้องการลบรายการจ่ายเงินนี้ออกจากสมุดจ่ายใช่หรือไม่ ยอดค้างจ่ายจะกลับมาเป็นเหมือนเดิม</p>',
      `<button class="btn btn-ghost" onclick="MFE.closeModal()">ยกเลิก</button>
       <button class="btn btn-danger" onclick="Actions.doDeletePayout(${id}, this)">ลบรายการ</button>`);
  }

  function doDeletePayout(id, btn) {
    return run(() => api.post('/api/payouts/' + id + '/delete', {}), 'ลบรายการแล้ว', { button: btn });
  }

  /* ------------------------------------------------------------ เป้าหมาย */

  function editGoal(periodKey, target, note) {
    openModal('ตั้งเป้าหมายรายได้', `
      <div class="form-grid">
        <label class="field"><span>รอบ</span>
          <input name="period_key" value="${esc(periodKey)}" placeholder="เช่น 2026-03"></label>
        <label class="field"><span>เป้าหมาย (สกุลกลาง)</span>
          <input name="target" type="number" step="10" min="0" value="${target || ''}"></label>
        <label class="field full"><span>หมายเหตุ</span>
          <input name="note" value="${esc(note || '')}" maxlength="160"></label>
      </div>
      <p class="alert-hint">เป้าหมายเทียบกับรายได้ส่วนแบ่งที่คิดได้จริงในรอบนั้น ไม่ใช่กำไรของพอร์ต</p>`,
      `<button class="btn btn-ghost" onclick="MFE.closeModal()">ยกเลิก</button>
       <button class="btn btn-primary" onclick="Actions.saveGoal(this)">บันทึกเป้าหมาย</button>`);
  }

  function saveGoal(btn) {
    return run(() => api.post('/api/goals', modalValues()), 'บันทึกเป้าหมายแล้ว', { button: btn });
  }

  /* -------------------------------------------------------------- ตั้งค่า */

  function saveSettings(btn) {
    const card = btn.closest('.card');
    const body = {};
    card.querySelectorAll('[name]').forEach((el) => {
      body[el.name] = el.type === 'checkbox' ? (el.checked ? '1' : '0') : el.value;
    });
    return run(() => api.post('/api/settings', body), 'บันทึกการตั้งค่าแล้ว',
               { button: btn, closeModal: false });
  }

  function editRate(code, rate) {
    openModal(code ? 'แก้อัตราแลกเปลี่ยน ' + code : 'เพิ่มสกุลเงิน', `
      <div class="form-grid">
        <label class="field"><span>รหัสสกุลเงิน</span>
          <input name="code" value="${esc(code)}" maxlength="5" placeholder="เช่น THB" ${code ? 'readonly' : ''}></label>
        <label class="field"><span>1 หน่วย เท่ากับกี่ USD</span>
          <input name="to_usd" type="number" step="0.000001" min="0" value="${rate || ''}"></label>
      </div>
      <p class="alert-hint">เช่น 1 บาท ประมาณ 0.0275 USD ค่านี้ใช้รวมยอดข้ามสกุลเงินเท่านั้น ไม่กระทบข้อมูลการเทรด</p>`,
      `<button class="btn btn-ghost" onclick="MFE.closeModal()">ยกเลิก</button>
       <button class="btn btn-primary" onclick="Actions.saveRate(this)">บันทึก</button>`);
  }

  function saveRate(btn) {
    return run(() => api.post('/api/fx', modalValues()), 'บันทึกอัตราแลกเปลี่ยนแล้ว', { button: btn });
  }

  /* ------------------------------------------------------------ แจ้งเตือน */

  function ackAlert(key) {
    return run(() => api.post('/api/alerts/ack', { key, actor: 'ผู้ใช้' }), 'รับทราบแล้ว');
  }

  function unackAlert(key) {
    return run(() => api.post('/api/alerts/unack', { key }), 'ยกเลิกการรับทราบแล้ว');
  }

  return {
    login, doLogin, logout, setDemo, syncNow,
    editRule, saveRule, toggleTrack, recompute, refreshIntel, planCapital,
    payFor, savePayout, deletePayout, doDeletePayout,
    editGoal, saveGoal, saveSettings, editRate, saveRate,
    ackAlert, unackAlert,
  };
})();


/* ======================================================== ผูกเส้นทางของหน้า */

MFE.route('/', { title: 'ภาพรวมรายได้', sub: 'ผลการเทรดและส่วนแบ่งของทุกพอร์ตในที่เดียว', view: Views.overview });
MFE.route('/accounts', { title: 'พอร์ตเทรด', sub: 'ตั้งเงื่อนไขส่วนแบ่งและเลือกพอร์ตที่จะติดตาม', view: Views.accounts });
MFE.route('/account', { title: 'รายละเอียดพอร์ต', sub: 'เส้นยอดเงิน ส่วนแบ่งรายรอบ และประวัติการจ่าย', view: Views.accountDetail });
MFE.route('/earnings', { title: 'รายได้ส่วนแบ่ง', sub: 'คิดตามรอบด้วยหลัก High-Water Mark', view: Views.earnings });
MFE.route('/payouts', { title: 'การจ่ายเงิน', sub: 'ยอดค้างจ่ายและสมุดบันทึกการจ่ายจริง', view: Views.payouts });
MFE.route('/goals', { title: 'เป้าหมายรายได้', sub: 'ตั้งเป้าแต่ละรอบแล้วดูความคืบหน้า', view: Views.goals });
MFE.route('/connect', { title: 'เชื่อมต่อและตั้งค่า', sub: 'บัญชี Myfxbook อัตราแลกเปลี่ยน และเกณฑ์การแจ้งเตือน', view: Views.connect });
MFE.route('/revenue', { title: 'เครื่องหาเงิน', sub: 'เงินที่ควรได้แต่ยังไม่ได้ คิดจากข้อมูลจริงในระบบ', view: Views.revenue });
MFE.route('/intel', { title: 'ศูนย์วิเคราะห์อัจฉริยะ', sub: 'พยากรณ์รายได้ วัดความเสี่ยง และจับพอร์ตที่ซ่อนระเบิด', view: Views.intel });
MFE.route('/alerts', { title: 'การแจ้งเตือน', sub: 'ความเสี่ยงของพอร์ตและงานที่ค้างอยู่', view: Views.alerts });


/* ============================================================ เริ่มโปรแกรม */

(function boot() {
  'use strict';

  // ธีม: จำค่าที่ผู้ใช้เลือกไว้ในเครื่อง ถ้าอ่านไม่ได้ก็ใช้ธีมมืดตามค่าเริ่มต้น
  const THEME_KEY = 'mfe-theme';
  try {
    const saved = localStorage.getItem(THEME_KEY);
    if (saved) document.documentElement.dataset.theme = saved;
  } catch (err) { /* โหมดส่วนตัวของเบราว์เซอร์อ่านค่าไม่ได้ ไม่ใช่เรื่องใหญ่ */ }

  document.getElementById('themeBtn').addEventListener('click', () => {
    const next = document.documentElement.dataset.theme === 'light' ? 'dark' : 'light';
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem(THEME_KEY, next); } catch (err) { /* ข้ามไป */ }
  });

  document.getElementById('refreshBtn').addEventListener('click', () => MFE.render());
  document.getElementById('syncBtn').addEventListener('click', (e) => Actions.syncNow(e.currentTarget));

  // เมนูด้านข้างบนจอเล็ก
  const sidebar = document.getElementById('sidebar');
  const scrim = document.getElementById('scrim');
  const openNav = () => { sidebar.classList.add('is-open'); scrim.hidden = false; };
  const closeNav = () => { sidebar.classList.remove('is-open'); scrim.hidden = true; };
  document.getElementById('navToggle').addEventListener('click', openNav);
  document.getElementById('navClose').addEventListener('click', closeNav);
  scrim.addEventListener('click', closeNav);
  document.getElementById('nav').addEventListener('click', (e) => {
    if (e.target.closest('.nav-item')) closeNav();
  });

  // ปิดโมดัลด้วยปุ่มกากบาท พื้นหลัง หรือปุ่ม Escape
  document.getElementById('modalRoot').addEventListener('click', (e) => {
    if (e.target.dataset.close) MFE.closeModal();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') MFE.closeModal();
  });

  // นาฬิกาบนแถบบน
  const clock = document.getElementById('clock');
  const tick = () => {
    const d = new Date();
    const p = (n) => String(n).padStart(2, '0');
    clock.textContent = MFE.fmtDate(MFE.isoOf(d), true) + ' · ' + p(d.getHours()) + ':' + p(d.getMinutes());
  };
  tick();
  setInterval(tick, 20000);

  window.addEventListener('hashchange', () => MFE.render());
  MFE.render();
})();
