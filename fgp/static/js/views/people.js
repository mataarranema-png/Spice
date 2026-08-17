// ทะเบียนพนักงานและตารางทักษะ (Skill Matrix)
import { api, store } from '../api.js';
import { icon, esc, nf, toast, modal, field, readForm } from '../ui.js';

const LEVEL_TEXT = ['ยังทำไม่ได้', 'ฝึกงาน', 'ทำงานได้เอง', 'ชำนาญ', 'สอนคนอื่นได้'];
const LEVEL_COLOR = ['transparent', 'rgba(61,123,255,.18)', 'rgba(61,123,255,.38)',
  'rgba(61,123,255,.62)', 'rgba(47,212,160,.72)'];

export default {
  title: 'พนักงาน & ทักษะ',
  subtitle: 'ทะเบียนกำลังคนของแผนกและตารางทักษะรายไลน์',
  hideFilter: true,

  async render(root, opts = {}) {
    const search = opts.search ?? this._search ?? '';
    const shift = opts.shift ?? this._shift ?? '';
    this._search = search;
    this._shift = shift;

    const [emps, matrix] = await Promise.all([
      api.get('/api/employees', { q: search, shift }),
      api.get('/api/skill-matrix'),
    ]);

    const total = emps.items.length;
    const byShift = { A: 0, B: 0 };
    emps.items.forEach((e) => { byShift[e.shift] = (byShift[e.shift] || 0) + 1; });
    const multi = emps.items.filter((e) => e.skills.filter((s) => s.level >= 2).length >= 3).length;

    root.innerHTML = `
      <div class="grid g4">
        <div class="card kpi"><div class="label">${icon('people', 15)} พนักงานทั้งหมด</div>
          <div class="value num">${total}</div><div class="sub">ที่ยังทำงานอยู่</div></div>
        <div class="card kpi"><div class="label">${icon('clock', 15)} กะ A / กะ B</div>
          <div class="value num" style="font-size:28px">${byShift.A || 0} / ${byShift.B || 0}</div>
          <div class="sub">แบ่งตามกะประจำ</div></div>
        <div class="card kpi accent"><div class="label">${icon('bolt', 15)} คนที่สลับไลน์ได้</div>
          <div class="value num">${multi}</div>
          <div class="sub">ทำได้เองตั้งแต่ 3 ไลน์ขึ้นไป</div></div>
        <div class="card kpi"><div class="label">${icon('capacity', 15)} ไลน์ที่เสี่ยงขาดคน</div>
          <div class="value num" style="color:${matrix.coverage.some((c) => c.can_run < 6) ? 'var(--bad)' : 'var(--ok)'}">
            ${matrix.coverage.filter((c) => c.can_run < 6).length}</div>
          <div class="sub">มีคนทำได้เองน้อยกว่า 6 คน</div></div>
      </div>

      <div class="card mt">
        <div class="card-head">
          <div><h3>ความครอบคลุมทักษะรายไลน์</h3>
            <p>จำนวนคนที่ทำงานไลน์นั้นได้เอง (ระดับ 2 ขึ้นไป)</p></div>
        </div>
        <div class="grid g4">
          ${matrix.coverage.map((c) => `
            <div class="card flat" style="padding:14px">
              <div class="row" style="justify-content:space-between">
                <b>${esc(c.code)}</b>
                <span class="badge ${c.can_run >= 10 ? 'ok' : c.can_run >= 6 ? 'warn' : 'bad'}">
                  ${c.can_run} คน</span>
              </div>
              <div class="bar ${c.can_run >= 10 ? 'ok' : c.can_run >= 6 ? 'warn' : 'bad'} mt">
                <i style="width:${Math.min(c.can_run / 16 * 100, 100)}%"></i></div>
              <div class="t-sm t-mute" style="margin-top:6px">
                ชำนาญสูงสุด ${c.experts} คน · กำลังฝึก ${c.trainees} คน</div>
            </div>`).join('')}
        </div>
      </div>

      <div class="card mt">
        <div class="card-head">
          <div><h3>ตารางทักษะ</h3><p>คลิกที่ช่องเพื่อปรับระดับทักษะ</p></div>
          <div class="right">
            <input id="q" placeholder="ค้นหาชื่อหรือรหัสพนักงาน" value="${esc(search)}" style="width:230px">
            <select id="shiftSel" style="width:120px">
              <option value="">ทุกกะ</option>
              <option value="A" ${shift === 'A' ? 'selected' : ''}>กะ A</option>
              <option value="B" ${shift === 'B' ? 'selected' : ''}>กะ B</option>
            </select>
            ${store.can('leader') ? `<button class="btn primary sm" id="addBtn">${icon('plus', 15)} เพิ่มพนักงาน</button>` : ''}
          </div>
        </div>
        <div class="table-wrap" style="max-height:620px;overflow-y:auto">
          <table>
            <thead><tr>
              <th>รหัส</th><th>ชื่อ</th><th>ตำแหน่ง</th><th class="c">กะ</th>
              ${matrix.lines.map((l) => `<th class="c">${esc(l.code.replace('FGP-', ''))}</th>`).join('')}
              <th class="c">เฉลี่ย</th>
            </tr></thead>
            <tbody>${emps.items.map((e) => {
              const row = matrix.employees.find((m) => m.id === e.id);
              const levels = row ? row.levels : matrix.lines.map(() => 0);
              return `<tr>
                <td class="mono t-sm">${esc(e.emp_code)}</td>
                <td class="t-strong">${esc(e.name)}</td>
                <td class="t-sm t-mute">${esc(e.position)}</td>
                <td class="c"><span class="badge mute">${esc(e.shift)}</span></td>
                ${levels.map((lv, i) => `<td class="c" style="cursor:pointer;background:${LEVEL_COLOR[lv]}"
                  data-skill="${e.id}:${matrix.lines[i].id}:${lv}"
                  title="${esc(e.name)} · ${esc(matrix.lines[i].code)} · ${LEVEL_TEXT[lv]}">
                  <span class="mono t-sm">${lv || '·'}</span></td>`).join('')}
                <td class="c mono t-strong">${e.skill_avg || '·'}</td>
              </tr>`;
            }).join('')}</tbody>
          </table>
        </div>
        <div class="legend mt">
          ${LEVEL_TEXT.map((t, i) => `<span><i style="background:${LEVEL_COLOR[i] === 'transparent'
            ? 'var(--surface-2)' : LEVEL_COLOR[i]};width:12px;height:12px;border-radius:3px"></i>${i} · ${t}</span>`).join('')}
        </div>
      </div>`;

    const self = this;
    let timer;
    root.querySelector('#q').oninput = (e) => {
      clearTimeout(timer);
      timer = setTimeout(() => self.render(root, { search: e.target.value, shift }), 350);
    };
    root.querySelector('#shiftSel').onchange = (e) =>
      self.render(root, { search, shift: e.target.value });
    root.querySelector('#addBtn')?.addEventListener('click', () => self.employeeModal(root));

    if (store.can('leader')) {
      root.querySelectorAll('[data-skill]').forEach((cell) => {
        cell.onclick = async () => {
          const [eid, lid, lv] = cell.dataset.skill.split(':').map(Number);
          const next = (lv + 1) % 5;
          try {
            await api.post(`/api/employees/${eid}/skill`, { line_id: lid, level: next });
            cell.dataset.skill = `${eid}:${lid}:${next}`;
            cell.style.background = LEVEL_COLOR[next];
            cell.querySelector('span').textContent = next || '·';
            toast(`ปรับเป็นระดับ ${next} · ${LEVEL_TEXT[next]}`);
          } catch (err) { toast(err.message, 'bad'); }
        };
      });
    }
  },

  employeeModal(root) {
    const self = this;
    modal({
      title: 'เพิ่มพนักงาน',
      body: `<form id="empForm" class="grid g2">
        ${field('รหัสพนักงาน', '<input name="emp_code" required placeholder="FGP-2065">')}
        ${field('ชื่อ-นามสกุล', '<input name="name" required>')}
        ${field('ตำแหน่ง', `<select name="position">
          <option>Operator</option><option>Senior Operator</option><option>Leader</option>
          <option>Technician</option><option>QC</option></select>`)}
        ${field('กะประจำ', '<select name="shift"><option value="A">กะ A</option><option value="B">กะ B</option></select>')}
        <div style="grid-column:1/-1">${field('หมายเหตุ', '<input name="note" placeholder="เช่น ข้อจำกัดด้านสุขภาพ">')}</div>
      </form>`,
      onMount(overlay, close) {
        overlay.querySelector('[data-ok]').onclick = async () => {
          try {
            await api.post('/api/employees', readForm(overlay.querySelector('#empForm')));
            close();
            toast('เพิ่มพนักงานแล้ว');
            self.render(root);
          } catch (err) { toast(err.message, 'bad'); }
        };
      },
    });
  },
};
