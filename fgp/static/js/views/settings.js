// ตั้งค่าระบบ: ไลน์ รุ่นสินค้า ผู้ใช้ และประวัติการใช้งาน
import { api, store } from '../api.js';
import { icon, esc, nf, toast, modal, field, selectOptions, readForm, relTime } from '../ui.js';

const ROLES = { admin: 'ผู้ดูแลระบบ', manager: 'หัวหน้าแผนก', leader: 'หัวหน้าไลน์',
  operator: 'พนักงานบันทึกยอด', viewer: 'ผู้ชมอย่างเดียว' };

export default {
  title: 'ตั้งค่าระบบ',
  subtitle: 'ข้อมูลหลักของแผนก สิทธิ์ผู้ใช้ และประวัติการแก้ไข',
  hideFilter: true,

  async render(root, opts = {}) {
    const tab = opts.tab ?? this._tab ?? 'lines';
    this._tab = tab;

    root.innerHTML = `
      <div class="card">
        <div class="card-head">
          <div><h3>ข้อมูลหลักของระบบ</h3><p>แก้ที่นี่แล้วมีผลกับทุกหน้าทันที</p></div>
          <div class="right">
            <div class="seg" id="tabs">
              <button data-tab="lines" class="${tab === 'lines' ? 'on' : ''}">ไลน์ผลิต</button>
              <button data-tab="models" class="${tab === 'models' ? 'on' : ''}">รุ่นสินค้า</button>
              <button data-tab="users" class="${tab === 'users' ? 'on' : ''}">ผู้ใช้งาน</button>
              <button data-tab="audit" class="${tab === 'audit' ? 'on' : ''}">ประวัติ</button>
            </div>
          </div>
        </div>
        <div id="tabBody">${'<div class="skeleton" style="height:220px"></div>'}</div>
      </div>

      <div class="card mt">
        <div class="card-head"><div><h3>บัญชีของฉัน</h3>
          <p>${esc(store.user.name)} · ${esc(ROLES[store.user.role] || store.user.role)}</p></div></div>
        <form id="pwForm" class="grid g3" style="align-items:end">
          ${field('รหัสผ่านเดิม', '<input name="current" type="password" required>')}
          ${field('รหัสผ่านใหม่', '<input name="password" type="password" minlength="6" required>')}
          <button class="btn primary" type="submit">${icon('check', 15)} เปลี่ยนรหัสผ่าน</button>
        </form>
      </div>

      <div class="card mt">
        <div class="card-head"><div><h3>เกี่ยวกับระบบ</h3></div></div>
        <div class="grid g3">
          <div><span class="t-sm t-mute">เก็บข้อมูลที่</span><div class="mono t-sm">data/fgp.db (SQLite)</div></div>
          <div><span class="t-sm t-mute">สำรองข้อมูล</span><div class="t-sm">คัดลอกโฟลเดอร์ data ทั้งโฟลเดอร์</div></div>
          <div><span class="t-sm t-mute">ปุ่มลัด</span><div class="t-sm">กด g แล้วตามด้วยเลข 1-9 เพื่อสลับหน้า</div></div>
        </div>
      </div>`;

    const self = this;
    root.querySelector('#tabs').onclick = (e) => {
      const b = e.target.closest('[data-tab]');
      if (b) self.render(root, { tab: b.dataset.tab });
    };
    root.querySelector('#pwForm').onsubmit = async (e) => {
      e.preventDefault();
      try {
        await api.post('/api/me/password', readForm(e.target));
        e.target.reset();
        toast('เปลี่ยนรหัสผ่านแล้ว');
      } catch (err) { toast(err.message, 'bad'); }
    };

    const body = root.querySelector('#tabBody');
    if (tab === 'lines') await this.linesTab(body, root);
    else if (tab === 'models') await this.modelsTab(body, root);
    else if (tab === 'users') await this.usersTab(body, root);
    else await this.auditTab(body);
  },

  async linesTab(body, root) {
    const { items } = await api.get('/api/lines');
    body.innerHTML = `
      <div class="row mb end">
        <button class="btn primary sm" id="addLine">${icon('plus', 15)} เพิ่มไลน์</button></div>
      <div class="table-wrap"><table>
        <thead><tr><th>รหัส</th><th>ชื่อไลน์</th><th class="r">กำลังคนมาตรฐาน</th>
          <th class="r">รอบผลิต (วินาที)</th><th>หัวหน้าไลน์</th><th class="c">สถานะ</th><th></th></tr></thead>
        <tbody>${items.map((l) => `<tr>
          <td class="t-strong">${esc(l.code)}</td>
          <td>${esc(l.name)}</td>
          <td class="r mono">${l.std_manpower}</td>
          <td class="r mono">${l.std_cycle_sec}</td>
          <td class="t-sm t-mute">${esc(l.leader_name || 'ยังไม่กำหนด')}</td>
          <td class="c"><span class="badge ${l.active ? 'ok' : 'mute'}">${l.active ? 'ใช้งาน' : 'ปิด'}</span></td>
          <td class="r"><button class="btn icon ghost sm" data-line="${l.id}">${icon('edit', 15)}</button></td>
        </tr>`).join('')}</tbody></table></div>`;

    const self = this;
    const open = (line) => modal({
      title: line ? `แก้ไข ${line.code}` : 'เพิ่มไลน์ผลิต',
      body: `<form id="lineForm" class="grid g2">
        ${line ? '' : field('รหัสไลน์', '<input name="code" required placeholder="FGP-06">')}
        ${field('ชื่อไลน์', `<input name="name" required value="${esc(line?.name || '')}">`)}
        ${field('กำลังคนมาตรฐาน', `<input name="std_manpower" type="number" min="1" value="${line?.std_manpower || 8}">`)}
        ${field('รอบผลิต (วินาที/ชิ้น)', `<input name="std_cycle_sec" type="number" step="0.1" value="${line?.std_cycle_sec || 30}">`)}
        ${field('หัวหน้าไลน์', `<select name="leader_id"><option value="">ยังไม่กำหนด</option>
          ${selectOptions(store.leaders, 'id', (u) => u.name, line?.leader_id)}</select>`)}
      </form>`,
      onMount(overlay, close) {
        overlay.querySelector('[data-ok]').onclick = async () => {
          const data = readForm(overlay.querySelector('#lineForm'));
          try {
            if (line) await api.put(`/api/lines/${line.id}`, data);
            else await api.post('/api/lines', data);
            close();
            toast('บันทึกแล้ว');
            api.clearCache();
            await store.bootstrap();
            self.render(root, { tab: 'lines' });
          } catch (err) { toast(err.message, 'bad'); }
        };
      },
    });
    body.querySelector('#addLine').onclick = () => open(null);
    body.querySelectorAll('[data-line]').forEach((b) => {
      b.onclick = () => open(items.find((l) => l.id === Number(b.dataset.line)));
    });
  },

  async modelsTab(body, root) {
    const { items } = await api.get('/api/models');
    body.innerHTML = `
      <div class="row mb end">
        <button class="btn primary sm" id="addModel">${icon('plus', 15)} เพิ่มรุ่น</button></div>
      <div class="table-wrap"><table>
        <thead><tr><th>รหัสรุ่น</th><th>ชื่อ</th><th class="r">รอบผลิต</th>
          <th class="r">กำลังคน</th><th class="r">เป้า Yield</th><th class="r">กำลังผลิต/กะ</th><th></th></tr></thead>
        <tbody>${items.map((m) => `<tr>
          <td class="t-strong">${esc(m.code)}</td>
          <td>${esc(m.name)}</td>
          <td class="r mono">${m.cycle_sec} วิ</td>
          <td class="r mono">${m.std_manpower}</td>
          <td class="r mono">${m.target_yield}%</td>
          <td class="r mono t-mute">${nf(8 * 3600 / m.cycle_sec)} ชิ้น</td>
          <td class="r"><button class="btn icon ghost sm" data-model="${m.id}">${icon('edit', 15)}</button></td>
        </tr>`).join('')}</tbody></table></div>`;

    const self = this;
    const open = (m) => modal({
      title: m ? `แก้ไข ${m.code}` : 'เพิ่มรุ่นสินค้า',
      body: `<form id="mForm" class="grid g2">
        ${m ? '' : field('รหัสรุ่น', '<input name="code" required placeholder="FG-E500">')}
        ${field('ชื่อรุ่น', `<input name="name" required value="${esc(m?.name || '')}">`)}
        ${field('รอบผลิต (วินาที/ชิ้น)', `<input name="cycle_sec" type="number" step="0.1" value="${m?.cycle_sec || 30}">`)}
        ${field('กำลังคนมาตรฐาน', `<input name="std_manpower" type="number" min="1" value="${m?.std_manpower || 8}">`)}
        ${field('เป้าหมาย Yield (%)', `<input name="target_yield" type="number" step="0.1" value="${m?.target_yield || 99}">`)}
      </form>`,
      onMount(overlay, close) {
        overlay.querySelector('[data-ok]').onclick = async () => {
          const data = readForm(overlay.querySelector('#mForm'));
          try {
            if (m) await api.put(`/api/models/${m.id}`, data);
            else await api.post('/api/models', data);
            close();
            toast('บันทึกแล้ว');
            api.clearCache();
            await store.bootstrap();
            self.render(root, { tab: 'models' });
          } catch (err) { toast(err.message, 'bad'); }
        };
      },
    });
    body.querySelector('#addModel').onclick = () => open(null);
    body.querySelectorAll('[data-model]').forEach((b) => {
      b.onclick = () => open(items.find((x) => x.id === Number(b.dataset.model)));
    });
  },

  async usersTab(body, root) {
    if (!store.can('admin')) {
      body.innerHTML = `<div class="empty">${icon('settings', 40)}<b>เฉพาะผู้ดูแลระบบ</b>
        <div class="t-sm">ส่วนนี้เปิดให้เฉพาะบัญชีระดับผู้ดูแลระบบ</div></div>`;
      return;
    }
    const { items } = await api.get('/api/users');
    body.innerHTML = `
      <div class="row mb end"><button class="btn primary sm" id="addUser">${icon('plus', 15)} เพิ่มผู้ใช้</button></div>
      <div class="table-wrap"><table>
        <thead><tr><th>ชื่อผู้ใช้</th><th>ชื่อ-นามสกุล</th><th>สิทธิ์</th>
          <th>รหัสพนักงาน</th><th class="c">สถานะ</th><th></th></tr></thead>
        <tbody>${items.map((u) => `<tr>
          <td class="mono t-strong">${esc(u.username)}</td>
          <td>${esc(u.name)}</td>
          <td><span class="badge info">${esc(ROLES[u.role] || u.role)}</span></td>
          <td class="t-sm t-mute">${esc(u.emp_code || '-')}</td>
          <td class="c"><span class="badge ${u.active ? 'ok' : 'mute'}">${u.active ? 'ใช้งาน' : 'ปิด'}</span></td>
          <td class="r"><button class="btn icon ghost sm" data-user="${u.id}">${icon('edit', 15)}</button></td>
        </tr>`).join('')}</tbody></table></div>`;

    const self = this;
    const open = (u) => modal({
      title: u ? `แก้ไข ${u.username}` : 'เพิ่มผู้ใช้งาน',
      body: `<form id="uForm" class="grid g2">
        ${u ? '' : field('ชื่อผู้ใช้', '<input name="username" required placeholder="leader3">')}
        ${field('ชื่อ-นามสกุล', `<input name="name" required value="${esc(u?.name || '')}">`)}
        ${field('สิทธิ์', `<select name="role">${Object.entries(ROLES).map(([k, v]) =>
          `<option value="${k}" ${u?.role === k ? 'selected' : ''}>${v}</option>`).join('')}</select>`)}
        ${u ? '' : field('รหัสพนักงาน', '<input name="emp_code" placeholder="FGP-103">')}
        ${field(u ? 'ตั้งรหัสผ่านใหม่ (เว้นว่างถ้าไม่เปลี่ยน)' : 'รหัสผ่าน',
          `<input name="password" type="password" ${u ? '' : 'required'} minlength="6">`)}
        ${u ? field('สถานะ', `<select name="active"><option value="1" ${u.active ? 'selected' : ''}>ใช้งาน</option>
          <option value="0" ${!u.active ? 'selected' : ''}>ปิดการใช้งาน</option></select>`) : ''}
      </form>`,
      onMount(overlay, close) {
        overlay.querySelector('[data-ok]').onclick = async () => {
          const data = readForm(overlay.querySelector('#uForm'));
          if (u && !data.password) delete data.password;
          try {
            if (u) await api.put(`/api/users/${u.id}`, data);
            else await api.post('/api/users', data);
            close();
            toast('บันทึกแล้ว');
            self.render(root, { tab: 'users' });
          } catch (err) { toast(err.message, 'bad'); }
        };
      },
    });
    body.querySelector('#addUser').onclick = () => open(null);
    body.querySelectorAll('[data-user]').forEach((b) => {
      b.onclick = () => open(items.find((u) => u.id === Number(b.dataset.user)));
    });
  },

  async auditTab(body) {
    const { items } = await api.get('/api/audit');
    body.innerHTML = `<div class="table-wrap scroll-y"><table>
      <thead><tr><th>เวลา</th><th>ผู้ใช้</th><th>การทำงาน</th><th>อ้างอิง</th><th>รายละเอียด</th></tr></thead>
      <tbody>${items.map((a) => `<tr>
        <td class="t-sm t-mute">${relTime(a.created_at)}</td>
        <td>${esc(a.name || '-')}</td>
        <td class="mono t-sm">${esc(a.action)}</td>
        <td class="t-sm t-mute">${esc(a.target || '-')}</td>
        <td class="t-sm t-mute">${esc(a.detail || '-')}</td>
      </tr>`).join('') || '<tr><td colspan="5" class="c t-mute">ยังไม่มีประวัติ</td></tr>'}</tbody>
    </table></div>`;
  },
};
