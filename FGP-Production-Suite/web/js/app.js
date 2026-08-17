/* ==========================================================================
   FGP Production Suite - การทำงานของหน้าจอ: เส้นทาง ปุ่มกด ฟอร์ม และธีม
   ========================================================================== */

(() => {
  'use strict';

  const { api, esc, num, hhmm, fmtDate, todayIso } = FGP;

  /* ------------------------------------------------------------- เส้นทางหน้า */

  FGP.route('/', { title: 'ภาพรวมทั้งฝ่าย', sub: 'สรุปทุกอย่างที่ต้องรู้ในหน้าจอเดียว', view: Views.overview });
  FGP.route('/plan', { title: 'แผนผลิต Plan vs Actual', sub: 'แผนรายวัน รายสัปดาห์ และเปอร์เซ็นต์ที่ทำได้จริง', view: Views.plan });
  FGP.route('/capacity', { title: 'จองคิวเครื่องและ Chamber', sub: 'ดูว่าเครื่องว่างเมื่อไร แล้วจองได้ทันที', view: Views.capacity });
  FGP.route('/wip', { title: 'ติดตามงาน WIP', sub: 'งานอยู่ขั้นไหน อยู่กับใคร ค้างกี่วัน คาดเสร็จเมื่อไร', view: Views.wip });
  FGP.route('/kpi', { title: 'KPI การผลิต', sub: 'Output Productivity OT Utilization Yield และ OEE', view: Views.kpi });
  FGP.route('/leader', { title: 'Leader Control Tower', sub: 'ใครว่าง ใครล้น และโยกงานได้จากหน้านี้', view: Views.leader });
  FGP.route('/alerts', { title: 'การแจ้งเตือนเชิงธุรกิจ', sub: 'ระบบอ่านข้อมูลจริงแล้วบอกว่าอะไรกำลังจะเป็นปัญหา', view: Views.alerts });

  /* --------------------------------------------------------------- ตัวช่วย */

  function goto(path) {
    if (location.hash === '#' + path) FGP.render();
    else location.hash = path;
  }

  function setQuery(patch) {
    const path = FGP.currentPath();
    const q = { ...FGP.queryParams(), ...patch };
    Object.keys(q).forEach((k) => { if (q[k] === '' || q[k] === null || q[k] === undefined) delete q[k]; });
    const qs = new URLSearchParams(q).toString();
    goto(path + (qs ? '?' + qs : ''));
  }

  async function run(promise, okMsg) {
    try {
      const res = await promise;
      if (res && res.ok === false) throw new Error(res.error || 'ทำรายการไม่สำเร็จ');
      if (okMsg) FGP.toast(okMsg, '', 'ok');
      return res;
    } catch (err) {
      FGP.toast('ทำรายการไม่สำเร็จ', err.message, 'err');
      throw err;
    }
  }

  /* ------------------------------------------------------- คำสั่งที่ปุ่มเรียกใช้ */

  const A = {
    /* --- แผนผลิต --- */
    planRange(n) {
      const to = todayIso();
      setQuery({ days: n, from: FGP.shiftDays(to, -(n - 1)), to, future: '' });
    },
    planFuture() {
      const from = todayIso();
      setQuery({ days: 7, from, to: FGP.shiftDays(from, 7), future: '1' });
    },
    planJump(date) {
      const days = Number(FGP.queryParams().days || 7);
      setQuery({ from: FGP.shiftDays(date, -(days - 1)), to: date });
    },

    editActual(id, model, shift, planQty, actual) {
      FGP.openModal(
        'บันทึกผลผลิตจริง',
        `<div class="stack" style="gap:14px">
          <div class="kv"><span>รุ่น</span><span>${esc(model)}</span></div>
          <div class="kv"><span>กะ</span><span>${esc(shift)}</span></div>
          <div class="kv"><span>แผนที่ตั้งไว้</span><span>${num(planQty)} ชิ้น</span></div>
          <div class="field">
            <label for="actualInput">ผลิตได้จริงกี่ชิ้น</label>
            <input type="number" id="actualInput" min="0" step="1" value="${actual === null ? '' : actual}" placeholder="ใส่ตัวเลข">
          </div>
          <p class="stat-note">ตัวเลขนี้จะไปคิด % Achievement และการแจ้งเตือนทันที</p>
        </div>`,
        `<button class="btn btn-ghost" onclick="FGP.closeModal()">ยกเลิก</button>
         <button class="btn btn-primary" onclick="FGPActions.saveActual(${id})">บันทึก</button>`
      );
    },
    async saveActual(id) {
      const value = Number(document.getElementById('actualInput').value);
      if (isNaN(value) || value < 0) return FGP.toast('ตัวเลขไม่ถูกต้อง', 'ใส่จำนวนที่เป็นศูนย์หรือมากกว่า', 'err');
      await run(api.post(`/api/plan/${id}/actual`, { actual: value }), 'บันทึกผลผลิตแล้ว');
      FGP.closeModal();
      FGP.render();
    },

    async newPlan() {
      const ref = await Views.reference();
      FGP.openModal(
        'เพิ่มแผนผลิต',
        `<div class="form-grid">
          <div class="field"><label for="pDate">วันที่ผลิต</label>
            <input type="date" id="pDate" value="${todayIso()}"></div>
          <div class="field"><label for="pShift">กะ</label>
            <select id="pShift"><option>กะเช้า</option><option>กะดึก</option></select></div>
          <div class="field full"><label for="pModel">รุ่นที่ผลิต</label>
            <select id="pModel">${ref.models.map((m) => `<option value="${m.id}">${esc(m.code)} · ${esc(m.name)} (${esc(m.line)})</option>`).join('')}</select></div>
          <div class="field full"><label for="pQty">จำนวนตามแผน</label>
            <input type="number" id="pQty" min="1" step="1" placeholder="เช่น 1000"></div>
        </div>
        <p class="stat-note" style="margin-top:10px">ถ้ามีแผนของรุ่นและกะเดียวกันในวันนั้นอยู่แล้ว ระบบจะทับตัวเลขเดิมให้</p>`,
        `<button class="btn btn-ghost" onclick="FGP.closeModal()">ยกเลิก</button>
         <button class="btn btn-primary" onclick="FGPActions.savePlan()">บันทึกแผน</button>`
      );
    },
    async savePlan() {
      const body = {
        date: document.getElementById('pDate').value,
        shift: document.getElementById('pShift').value,
        model_id: Number(document.getElementById('pModel').value),
        plan_qty: Number(document.getElementById('pQty').value),
      };
      if (!body.plan_qty || body.plan_qty <= 0) return FGP.toast('ใส่จำนวนแผนก่อน', 'ต้องมากกว่าศูนย์', 'err');
      const res = await run(api.post('/api/plan', body));
      FGP.toast(res.updated ? 'อัปเดตแผนเดิมแล้ว' : 'เพิ่มแผนใหม่แล้ว', '', 'ok');
      FGP.closeModal();
      FGP.render();
    },

    /* --- จองเครื่อง --- */
    capDate(date) { setQuery({ date }); },
    capType(type) { setQuery({ type }); },

    async book(machineId, date) {
      const ref = await Views.reference();
      const usable = ref.machines.filter((m) => m.status === 'READY');
      FGP.openModal(
        'จองคิวเครื่อง',
        `<div class="form-grid">
          <div class="field full"><label for="bMachine">เครื่องที่ต้องการ</label>
            <select id="bMachine">${usable.map((m) => `<option value="${m.id}" ${m.id === machineId ? 'selected' : ''}>${esc(m.code)} · ${esc(m.name)}</option>`).join('')}</select></div>
          <div class="field"><label for="bDate">วันที่</label>
            <input type="date" id="bDate" value="${date || todayIso()}"></div>
          <div class="field"><label for="bJob">เลขที่งาน (ถ้ามี)</label>
            <input type="text" id="bJob" placeholder="เช่น FGP-2608-101"></div>
          <div class="field"><label for="bStart">เริ่มเวลา</label>
            <select id="bStart">${hourOptions(8)}</select></div>
          <div class="field"><label for="bEnd">ถึงเวลา</label>
            <select id="bEnd">${hourOptions(10)}</select></div>
          <div class="field full"><label for="bOwner">ผู้จอง</label>
            <select id="bOwner">${ref.members.map((m) => `<option value="${esc(m.name)}" data-team="${esc(m.team)}">${esc(m.name)} · ${esc(m.team)}</option>`).join('')}</select></div>
          <div class="field full"><label for="bPurpose">งานที่จะทำ</label>
            <input type="text" id="bPurpose" placeholder="เช่น Temp Cycle 85C/85RH"></div>
        </div>
        <p class="stat-note" style="margin-top:10px">ถ้าช่วงเวลาชนกับคิวเดิม ระบบจะบอกว่าชนกับใครและเวลาไหน</p>`,
        `<button class="btn btn-ghost" onclick="FGP.closeModal()">ยกเลิก</button>
         <button class="btn btn-primary" onclick="FGPActions.saveBooking()">จองคิวนี้</button>`
      );
    },
    async saveBooking() {
      const ownerSel = document.getElementById('bOwner');
      const body = {
        machine_id: Number(document.getElementById('bMachine').value),
        date: document.getElementById('bDate').value,
        start_hour: Number(document.getElementById('bStart').value),
        end_hour: Number(document.getElementById('bEnd').value),
        owner: ownerSel.value,
        team: ownerSel.selectedOptions[0] ? ownerSel.selectedOptions[0].dataset.team : '',
        job_no: document.getElementById('bJob').value,
        purpose: document.getElementById('bPurpose').value,
      };
      await run(api.post('/api/bookings', body), 'จองคิวเรียบร้อย');
      FGP.closeModal();
      setQuery({ date: body.date });
      FGP.render();
    },

    bookingInfo(id) {
      const data = window.__capData;
      if (!data) return;
      let found = null, machine = null;
      data.machines.forEach((m) => m.bookings.forEach((b) => { if (b.id === id) { found = b; machine = m; } }));
      if (!found) return;
      FGP.openModal(
        'คิวจอง ' + machine.code,
        `<div class="stack" style="gap:2px">
          <div class="kv"><span>เครื่อง</span><span>${esc(machine.code)} · ${esc(machine.name)}</span></div>
          <div class="kv"><span>วันที่</span><span>${fmtDate(data.date, true)}</span></div>
          <div class="kv"><span>ช่วงเวลา</span><span>${hhmm(found.start)} ถึง ${hhmm(found.end)} (${num(found.end - found.start, 1)} ชม.)</span></div>
          <div class="kv"><span>ผู้จอง</span><span>${esc(found.owner)}${found.team ? ' · ' + esc(found.team) : ''}</span></div>
          <div class="kv"><span>เลขที่งาน</span><span>${esc(found.job_no || '-')}</span></div>
          <div class="kv"><span>งานที่ทำ</span><span>${esc(found.purpose || '-')}</span></div>
        </div>`,
        `<button class="btn btn-ghost" onclick="FGP.closeModal()">ปิด</button>
         <button class="btn btn-danger" onclick="FGPActions.cancelBooking(${id})">ยกเลิกคิวนี้</button>`
      );
    },
    async cancelBooking(id) {
      await run(api.post(`/api/bookings/${id}/cancel`, {}), 'ยกเลิกคิวแล้ว เครื่องว่างช่วงนั้นทันที');
      FGP.closeModal();
      FGP.render();
    },

    /* --- WIP --- */
    wipView(view) { setQuery({ view }); },

    async openJob(id) {
      const j = await api.get('/api/wip/' + id);
      if (j.ok === false) return FGP.toast('เปิดใบงานไม่ได้', j.error, 'err');
      const ref = await Views.reference();
      const stages = ref.stages;

      FGP.openModal(
        'ใบงาน ' + j.job_no,
        `<div class="stack" style="gap:16px">
          <div>
            <div class="row" style="gap:8px">
              ${j.priority === 'URGENT' ? '<span class="chip chip-crit">งานด่วน</span>' : '<span class="chip chip-mute">งานปกติ</span>'}
              <span class="chip chip-accent">${esc(j.stage)}</span>
              <span class="chip chip-${j.risk === 'LATE' ? 'crit' : j.risk === 'WATCH' ? 'warn' : 'ok'}">
                ${j.risk === 'LATE' ? 'เสี่ยงเลยกำหนด' : j.risk === 'WATCH' ? 'ต้องเฝ้าดู' : 'ตามแผน'}</span>
            </div>
            ${(() => {
              let rail = '<div class="stage-rail">';
              for (let i = 0; i < stages.length; i++) {
                rail += `<span class="stage-node ${i < j.stage_index ? 'done' : i === j.stage_index ? 'current' : ''}"></span>`;
              }
              return rail + '</div>';
            })()}
            <div class="row" style="justify-content:space-between;font-size:11px;color:var(--muted)">
              <span>${esc(stages[0])}</span><span>${esc(stages[stages.length - 1])}</span>
            </div>
          </div>

          <div class="stack" style="gap:0">
            <div class="kv"><span>รุ่น</span><span>${esc(j.model)}</span></div>
            <div class="kv"><span>ลูกค้า</span><span>${esc(j.customer)}</span></div>
            <div class="kv"><span>จำนวน</span><span>${num(j.qty)} ชิ้น</span></div>
            <div class="kv"><span>ผู้รับผิดชอบ</span><span>${esc(j.owner || 'ยังไม่มอบหมาย')} ${j.team ? '· ' + esc(j.team) : ''}</span></div>
            <div class="kv"><span>เปิดงานเมื่อ</span><span>${fmtDate(j.started_at, true)} (${j.age_days} วันที่แล้ว)</span></div>
            <div class="kv"><span>ค้างขั้นตอนนี้</span><span>${j.stage_days} วัน</span></div>
            <div class="kv"><span>ครบกำหนด</span><span>${fmtDate(j.due_date, true)} ${j.due_in_days < 0 ? `(เลยมา ${-j.due_in_days} วัน)` : `(อีก ${j.due_in_days} วัน)`}</span></div>
            <div class="kv"><span>คาดว่าเสร็จ</span><span>${fmtDate(j.eta, true)}</span></div>
          </div>

          ${j.bookings.length ? `<div>
            <p class="stat-label" style="margin-bottom:6px">คิวเครื่องของงานนี้</p>
            <div class="pill-row">${j.bookings.map((b) => `<span class="chip chip-accent">${esc(b.machine)} · ${fmtDate(b.date)} ${hhmm(b.start)}-${hhmm(b.end)}</span>`).join('')}</div>
          </div>` : ''}

          <div>
            <p class="stat-label" style="margin-bottom:6px">มอบหมายให้คนอื่น</p>
            <div class="row" style="gap:8px">
              <select id="jOwner" style="flex:1">
                ${ref.members.map((m) => `<option value="${m.id}" ${m.id === j.owner_id ? 'selected' : ''}>${esc(m.name)} · ${esc(m.team)} · ถนัด ${esc(m.skill)}</option>`).join('')}
              </select>
              <button class="btn btn-sm" onclick="FGPActions.doAssign(${j.id}, null)">โยกงาน</button>
            </div>
          </div>

          <div>
            <p class="stat-label" style="margin-bottom:8px">ประวัติการเดินงาน</p>
            <div class="timeline-log">
              ${j.events.map((e) => `<div class="log-item">
                <span class="log-dot"></span>
                <div><div class="log-text">${esc(e.detail)}</div>
                <div class="log-time">${esc(e.ts)} · โดย ${esc(e.actor)}</div></div>
              </div>`).join('')}
            </div>
          </div>
        </div>`,
        `<button class="btn btn-ghost" onclick="FGP.closeModal()">ปิด</button>
         <button class="btn btn-primary" onclick="FGPActions.advance(${j.id})">
           ${j.stage_index >= stages.length - 2 ? 'ปิดงานนี้' : 'ส่งต่อขั้นถัดไป'}</button>`
      );
    },

    async advance(id) {
      const res = await run(api.post(`/api/wip/${id}/advance`, {}));
      FGP.toast(res.closed ? 'ปิดงานเรียบร้อย' : 'ส่งงานไปขั้น ' + res.stage + ' แล้ว', '', 'ok');
      FGP.closeModal();
      FGP.render();
    },

    async doAssign(jobId, memberId) {
      const target = memberId || Number((document.getElementById('jOwner') || {}).value || 0);
      if (!target) return FGP.toast('เลือกคนก่อน', '', 'err');
      const res = await run(api.post(`/api/wip/${jobId}/assign`, { member_id: target }));
      FGP.toast('โยกงานให้ ' + res.owner + ' แล้ว', 'ทีม ' + res.team, 'ok');
      FGP.closeModal();
      FGP.render();
    },

    async assignPicker() {
      const [wipData, ref] = await Promise.all([api.get('/api/wip'), Views.reference()]);
      FGP.openModal(
        'มอบหมายงาน',
        `<div class="form-grid">
          <div class="field full"><label for="aJob">ใบงาน</label>
            <select id="aJob">${wipData.jobs.map((j) => `<option value="${j.id}">${esc(j.job_no)} · ${esc(j.stage)} · ครบกำหนด ${fmtDate(j.due_date)}</option>`).join('')}</select></div>
          <div class="field full"><label for="jOwner">มอบให้</label>
            <select id="jOwner">${ref.members.map((m) => `<option value="${m.id}">${esc(m.name)} · ${esc(m.team)} · ถนัด ${esc(m.skill)}</option>`).join('')}</select></div>
        </div>`,
        `<button class="btn btn-ghost" onclick="FGP.closeModal()">ยกเลิก</button>
         <button class="btn btn-primary" onclick="FGPActions.doAssign(Number(document.getElementById('aJob').value), null)">มอบหมาย</button>`
      );
    },

    /* --- KPI --- */
    kpiRange(days) { setQuery({ days }); },

    /* --- Alert --- */
    async ack(key, isAcked) {
      const url = isAcked ? '/api/alerts/unack' : '/api/alerts/ack';
      await run(api.post(url, { key }), isAcked ? 'เอากลับมาที่รายการหลักแล้ว' : 'รับทราบแล้ว');
      FGP.render();
    },
  };

  function hourOptions(selected) {
    let out = '';
    for (let hr = 6; hr <= 22; hr += 0.5) {
      out += `<option value="${hr}" ${hr === selected ? 'selected' : ''}>${hhmm(hr)}</option>`;
    }
    return out;
  }

  window.FGPActions = A;

  /* ------------------------------------------------------------- ธีมและเวลา */

  const THEME_KEY = 'fgp-theme';

  function applyTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    try { localStorage.setItem(THEME_KEY, theme); } catch (e) { /* โหมดส่วนตัวของเบราว์เซอร์ */ }
    document.getElementById('themeBtn').textContent = theme === 'dark' ? '◐' : '◑';
  }

  function initTheme() {
    let saved = null;
    try { saved = localStorage.getItem(THEME_KEY); } catch (e) { /* ไม่เป็นไร */ }
    applyTheme(saved || 'dark');
  }

  function tickClock() {
    const now = new Date();
    const p = (n) => String(n).padStart(2, '0');
    const el = document.getElementById('clock');
    if (el) {
      el.textContent = FGP.THAI_DAYS[now.getDay()] + ' ' + now.getDate() + ' ' +
        FGP.THAI_MONTHS[now.getMonth()] + ' ' + (now.getFullYear() + 543) + ' · ' +
        p(now.getHours()) + ':' + p(now.getMinutes());
    }
    const stamp = document.getElementById('footStamp');
    if (stamp) stamp.textContent = 'ข้อมูลล่าสุด ' + p(now.getHours()) + ':' + p(now.getMinutes()) + ':' + p(now.getSeconds());
  }

  /* ------------------------------------------------------------------ เริ่มต้น */

  function initNav() {
    const sidebar = document.getElementById('sidebar');
    const scrim = document.getElementById('scrim');
    const open = () => { sidebar.classList.add('is-open'); scrim.hidden = false; };
    const close = () => { sidebar.classList.remove('is-open'); scrim.hidden = true; };
    document.getElementById('navToggle').addEventListener('click', open);
    document.getElementById('navClose').addEventListener('click', close);
    scrim.addEventListener('click', close);
    document.getElementById('nav').addEventListener('click', (e) => {
      if (e.target.closest('.nav-item')) close();
    });
  }

  function initModal() {
    document.getElementById('modalRoot').addEventListener('click', (e) => {
      if (e.target.dataset.close) FGP.closeModal();
    });
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') FGP.closeModal();
      if (e.key === 'r' && (e.metaKey || e.ctrlKey) === false && e.target === document.body) FGP.render();
    });
  }

  function initRefresh() {
    const btn = document.getElementById('refreshBtn');
    btn.addEventListener('click', async () => {
      btn.classList.add('is-loading');
      await FGP.render();
      setTimeout(() => btn.classList.remove('is-loading'), 620);
    });
  }

  window.addEventListener('hashchange', FGP.render);

  document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    initNav();
    initModal();
    initRefresh();
    document.getElementById('themeBtn').addEventListener('click', () => {
      const next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
      applyTheme(next);
    });
    tickClock();
    setInterval(tickClock, 1000);
    setInterval(FGP.refreshAlertBadge, 60000);
    FGP.render();
  });
})();
