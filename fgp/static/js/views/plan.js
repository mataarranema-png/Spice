// แผนการผลิตรายวัน/รายสัปดาห์
import { api, store } from '../api.js';
import { icon, esc, nf, toast, modal, field, selectOptions, readForm, confirmDialog, thaiDate } from '../ui.js';

const PRIORITY = { 1: ['mute', 'ปกติ'], 2: ['info', 'สำคัญ'], 3: ['warn', 'เร่งด่วน'], 4: ['bad', 'วิกฤต'] };

function addDays(iso, n) {
  const d = new Date(iso + 'T00:00:00');
  d.setDate(d.getDate() + n);
  return d.toISOString().slice(0, 10);
}

export default {
  title: 'แผนการผลิต',
  subtitle: 'วางแผนล่วงหน้า เทียบผลจริง และคัดลอกแผนข้ามวันได้ในคลิกเดียว',

  async render(root) {
    const from = store.date;
    const to = addDays(from, 6);
    const { items } = await api.get('/api/plans', { from, to });
    const days = Array.from({ length: 7 }, (_, i) => addDays(from, i));

    const byDay = new Map(days.map((d) => [d, items.filter((p) => p.plan_date === d)]));
    const weekTarget = items.reduce((a, p) => a + p.target_qty, 0);
    const weekActual = items.reduce((a, p) => a + p.actual_qty, 0);

    // ตารางความร้อน: เป้าต่อไลน์ต่อวัน
    const maxCell = Math.max(1, ...store.lines.map((l) =>
      Math.max(...days.map((d) => items.filter((p) => p.line_id === l.id && p.plan_date === d)
        .reduce((a, p) => a + p.target_qty, 0)))));

    root.innerHTML = `
      <div class="card">
        <div class="card-head">
          <div><h3>แผน 7 วัน</h3><p>${thaiDate(from)} ถึง ${thaiDate(to)}</p></div>
          <div class="right">
            <span class="badge info">เป้ารวม ${nf(weekTarget)} ชิ้น</span>
            <span class="badge ${weekActual >= weekTarget ? 'ok' : 'warn'}">ทำได้ ${nf(weekActual)} ชิ้น</span>
            <button class="btn sm" id="copyBtn">${icon('plan', 14)} คัดลอกแผน</button>
            ${store.can('leader') ? `<button class="btn primary sm" id="addBtn">${icon('plus', 15)} สร้างแผน</button>` : ''}
          </div>
        </div>
        <div class="table-wrap">
          <table>
            <thead><tr><th>ไลน์</th>${days.map((d) => `<th class="c">${thaiDate(d)}</th>`).join('')}
              <th class="r">รวมสัปดาห์</th></tr></thead>
            <tbody>${store.lines.map((l) => {
              const cells = days.map((d) => items.filter((p) => p.line_id === l.id && p.plan_date === d)
                .reduce((a, p) => a + p.target_qty, 0));
              return `<tr><td class="t-strong">${esc(l.code)}</td>
                ${cells.map((v) => `<td class="c mono" style="background:rgba(61,123,255,${(v / maxCell * 0.28).toFixed(3)})">
                  ${v ? nf(v) : '<span class="t-mute">—</span>'}</td>`).join('')}
                <td class="r mono t-strong">${nf(cells.reduce((a, b) => a + b, 0))}</td></tr>`;
            }).join('')}</tbody>
          </table>
        </div>
      </div>

      ${days.map((d) => {
        const rows = byDay.get(d);
        if (!rows.length) return '';
        const dayTarget = rows.reduce((a, p) => a + p.target_qty, 0);
        const dayActual = rows.reduce((a, p) => a + p.actual_qty, 0);
        return `<div class="card mt">
          <div class="card-head">
            <div><h3>${thaiDate(d)}</h3><p>${rows.length} รายการ · เป้า ${nf(dayTarget)} ชิ้น</p></div>
            <div class="right">
              <span class="badge ${dayActual >= dayTarget ? 'ok' : dayActual ? 'warn' : 'mute'}">
                ทำได้ ${nf(dayActual)} (${dayTarget ? (dayActual / dayTarget * 100).toFixed(0) : 0}%)</span>
            </div>
          </div>
          <div class="table-wrap"><table>
            <thead><tr><th>กะ</th><th>ไลน์</th><th>รุ่น</th><th class="r">เป้า</th><th class="r">ทำได้</th>
              <th class="c">ความสำเร็จ</th><th>ความสำคัญ</th><th>หมายเหตุ</th><th></th></tr></thead>
            <tbody>${rows.map((p) => `<tr>
              <td><span class="badge mute">กะ ${esc(p.shift)}</span></td>
              <td class="t-strong">${esc(p.line_code)}</td>
              <td>${esc(p.model_code)} <span class="t-mute t-sm">${esc(p.model_name)}</span></td>
              <td class="r mono">${nf(p.target_qty)}</td>
              <td class="r mono">${nf(p.actual_qty)}</td>
              <td class="c" style="min-width:130px">
                <div class="bar ${p.achievement >= 100 ? 'ok' : p.achievement >= 92 ? 'warn' : 'bad'}">
                  <i style="width:${Math.min(p.achievement, 100)}%"></i></div>
                <span class="t-sm mono t-mute">${p.achievement.toFixed(0)}%</span></td>
              <td><span class="badge ${PRIORITY[p.priority]?.[0] || 'mute'}">${PRIORITY[p.priority]?.[1] || '-'}</span></td>
              <td class="t-sm t-mute">${esc(p.note || '-')}</td>
              <td class="r">${store.can('leader') ? `
                <button class="btn icon ghost sm" data-edit="${p.id}" title="แก้ไข">${icon('edit', 15)}</button>
                <button class="btn icon ghost sm" data-del="${p.id}" title="ลบ">${icon('trash', 15)}</button>` : ''}</td>
            </tr>`).join('')}</tbody>
          </table></div>
        </div>`;
      }).join('')}

      ${items.length ? '' : `<div class="card mt"><div class="empty">${icon('plan', 42)}
        <b>ยังไม่มีแผนในช่วงนี้</b><div class="t-sm">กด "สร้างแผน" เพื่อเริ่มวางแผนการผลิต</div></div></div>`}`;

    const self = this;
    root.querySelector('#addBtn')?.addEventListener('click', () => self.planModal(null, root));
    root.querySelectorAll('[data-edit]').forEach((b) => {
      b.onclick = () => self.planModal(items.find((p) => p.id === Number(b.dataset.edit)), root);
    });
    root.querySelectorAll('[data-del]').forEach((b) => {
      b.onclick = () => confirmDialog('ลบแผนรายการนี้หรือไม่', async () => {
        await api.del(`/api/plans/${b.dataset.del}`);
        toast('ลบแผนแล้ว');
        self.render(root);
      });
    });
    root.querySelector('#copyBtn').onclick = () => {
      modal({
        title: 'คัดลอกแผนทั้งวัน',
        subtitle: 'ใช้เมื่อแผนวันใหม่เหมือนวันก่อนหน้า',
        body: `<form id="copyForm" class="grid g2">
          ${field('จากวันที่', `<input name="from" type="date" value="${store.date}">`)}
          ${field('ไปวันที่', `<input name="to" type="date" value="${addDays(store.date, 1)}">`)}
        </form>`,
        onMount(overlay, close) {
          overlay.querySelector('[data-ok]').onclick = async () => {
            const d = readForm(overlay.querySelector('#copyForm'));
            try {
              const res = await api.post('/api/plans/copy', d);
              close();
              toast(`คัดลอกแผน ${res.copied} รายการแล้ว`);
              self.render(root);
            } catch (err) { toast(err.message, 'bad'); }
          };
        },
      });
    };
  },

  planModal(plan, root) {
    const self = this;
    modal({
      title: plan ? 'แก้ไขแผนการผลิต' : 'สร้างแผนการผลิต',
      body: `<form id="planForm" class="grid g2">
        ${field('วันที่', `<input name="plan_date" type="date" value="${plan?.plan_date || store.date}">`)}
        ${field('กะ', `<select name="shift">
          <option value="A" ${plan?.shift === 'A' ? 'selected' : ''}>กะ A (เช้า)</option>
          <option value="B" ${plan?.shift === 'B' ? 'selected' : ''}>กะ B (ดึก)</option></select>`)}
        ${field('ไลน์ผลิต', `<select name="line_id">${selectOptions(store.lines, 'id',
          (l) => `${l.code} · ${l.name}`, plan?.line_id)}</select>`)}
        ${field('รุ่นสินค้า', `<select name="model_id">${selectOptions(store.models, 'id',
          (m) => `${m.code} · ${m.name}`, plan?.model_id)}</select>`)}
        ${field('เป้าหมาย (ชิ้น)', `<input name="target_qty" type="number" min="1"
          value="${plan?.target_qty || 1000}" required>`)}
        ${field('ความสำคัญ', `<select name="priority">${Object.entries(PRIORITY).map(([k, v]) =>
          `<option value="${k}" ${String(plan?.priority) === k ? 'selected' : ''}>${v[1]}</option>`).join('')}</select>`)}
        <div style="grid-column:1/-1">${field('หมายเหตุ',
          `<textarea name="note" placeholder="เช่น ส่งลูกค้าด่วน หรือ ต้องเปลี่ยนรุ่นกลางกะ">${esc(plan?.note || '')}</textarea>`)}</div>
      </form>
      <div class="mt t-sm t-mute" id="calcHint"></div>`,
      onMount(overlay, close) {
        const form = overlay.querySelector('#planForm');
        const hint = overlay.querySelector('#calcHint');
        const recalc = () => {
          const m = store.model(form.model_id.value);
          const qty = Number(form.target_qty.value || 0);
          if (!m || !qty) { hint.textContent = ''; return; }
          const minutes = (qty * m.cycle_sec) / 60;
          const hours = minutes / 60;
          hint.innerHTML = `${icon('brain', 13)} ระบบคำนวณให้: รอบผลิต ${m.cycle_sec} วินาที/ชิ้น
            ต้องใช้เวลาเดินเครื่อง <b>${hours.toFixed(1)} ชั่วโมง</b> จากกะละ ${store.shiftHours} ชั่วโมง
            ${hours > store.shiftHours ? '<span style="color:var(--bad)"> · เกินเวลาของหนึ่งกะ ควรแบ่งไลน์หรือเพิ่มกะ</span>'
              : `<span style="color:var(--ok)"> · เหลือเวลาสำรอง ${(store.shiftHours - hours).toFixed(1)} ชั่วโมง</span>`}`;
        };
        form.oninput = recalc;
        recalc();
        overlay.querySelector('[data-ok]').onclick = async () => {
          const data = readForm(form);
          try {
            if (plan) await api.put(`/api/plans/${plan.id}`, data);
            else await api.post('/api/plans', data);
            close();
            toast(plan ? 'แก้ไขแผนแล้ว' : 'สร้างแผนแล้ว');
            self.render(root);
          } catch (err) { toast(err.message, 'bad'); }
        };
      },
    });
  },
};
