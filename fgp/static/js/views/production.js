// บันทึกและตรวจสอบยอดผลิตรายชั่วโมง
import { api, store } from '../api.js';
import { icon, esc, nf, toast, modal, field, selectOptions, readForm, confirmDialog, thaiDate } from '../ui.js';
import { lineChart } from '../charts.js';

const REASONS = ['เครื่องจักรขัดข้อง', 'รอวัตถุดิบ', 'เปลี่ยนรุ่น (Change over)', 'ปรับตั้งเครื่อง',
  'ไฟฟ้าขัดข้อง', 'ขาดกำลังคน', 'QC hold', 'อื่นๆ'];

function cellClass(rec) {
  if (!rec) return '';
  if (rec.downtime_min >= 15) return 'warn';
  return '';
}

export default {
  title: 'บันทึกยอดผลิต',
  subtitle: 'กรอกยอดรายชั่วโมง ระบบคำนวณ Yield และแจ้งเตือนให้ทันที',
  autoRefresh: 60000,

  async render(root) {
    const [prod, plans] = await Promise.all([
      api.get('/api/production', { date: store.date, shift: store.shift }),
      api.get('/api/plans', { date: store.date, shift: store.shift }),
    ]);
    const hours = Array.from({ length: store.shiftHours }, (_, i) => i + 1);
    const byLine = new Map();
    prod.items.forEach((r) => {
      if (!byLine.has(r.line_id)) byLine.set(r.line_id, {});
      byLine.get(r.line_id)[r.hour] = r;
    });
    const planByLine = new Map(plans.items.map((p) => [p.line_id, p]));
    const lines = store.lines;

    const totals = lines.map((l) => {
      const recs = Object.values(byLine.get(l.id) || {});
      const ok = recs.reduce((a, r) => a + r.ok_qty, 0);
      const ng = recs.reduce((a, r) => a + r.ng_qty, 0);
      const dtm = recs.reduce((a, r) => a + r.downtime_min, 0);
      const plan = planByLine.get(l.id);
      return { line: l, ok, ng, dtm, target: plan?.target_qty || 0, model: plan?.model_code || '-',
               achievement: plan?.target_qty ? (ok / plan.target_qty) * 100 : 0 };
    });
    const grandOk = totals.reduce((a, t) => a + t.ok, 0);
    const grandNg = totals.reduce((a, t) => a + t.ng, 0);
    const grandTarget = totals.reduce((a, t) => a + t.target, 0);

    const hourTotals = hours.map((h) =>
      prod.items.filter((r) => r.hour === h).reduce((a, r) => a + r.ok_qty, 0));

    root.innerHTML = `
      <div class="card">
        <div class="card-head">
          <div><h3>บันทึกด่วน</h3><p>${thaiDate(store.date)} · กะ ${store.shift} · ใช้เวลาไม่ถึงครึ่งนาที</p></div>
          <div class="right">
            <span class="badge info">รวม ${nf(grandOk)} ชิ้น</span>
            <span class="badge ${grandNg / Math.max(grandOk + grandNg, 1) * 100 < 1.5 ? 'ok' : 'bad'}">
              NG ${nf(grandNg)} ชิ้น</span>
            <span class="badge ${grandOk >= grandTarget ? 'ok' : 'warn'}">
              เป้า ${nf(grandTarget)} ชิ้น</span>
          </div>
        </div>
        <form id="quick" class="grid" style="grid-template-columns:repeat(6,minmax(0,1fr));align-items:end;gap:12px">
          ${field('ไลน์', `<select name="line_id">${selectOptions(lines, 'id', (l) => `${l.code} · ${l.name}`)}</select>`)}
          ${field('ชั่วโมงที่', `<select name="hour">${hours.map((h) =>
            `<option value="${h}">ชั่วโมงที่ ${h}</option>`).join('')}</select>`)}
          ${field('ยอดดี (ชิ้น)', '<input name="ok_qty" type="number" min="0" value="0" required>')}
          ${field('ของเสีย (ชิ้น)', '<input name="ng_qty" type="number" min="0" value="0">')}
          ${field('เวลาหยุด (นาที)', '<input name="downtime_min" type="number" min="0" value="0">')}
          <button class="btn primary" type="submit">${icon('plus', 16)} บันทึก</button>
        </form>
        <div id="quickReason" class="hide mt">
          ${field('สาเหตุที่หยุด', `<select name="downtime_reason" form="quick">
            ${REASONS.map((r) => `<option>${r}</option>`).join('')}</select>`)}
        </div>
      </div>

      <div class="card mt">
        <div class="card-head">
          <div><h3>ตารางยอดผลิตรายชั่วโมง</h3><p>คลิกที่ช่องเพื่อแก้ไขรายละเอียด</p></div>
          <div class="right"><span class="t-sm t-mute">ตัวเลขสีส้ม = ชั่วโมงที่มีเวลาหยุดเกิน 15 นาที</span></div>
        </div>
        <div class="table-wrap">
          <table>
            <thead><tr>
              <th>ไลน์</th><th>รุ่น</th>
              ${hours.map((h) => `<th class="c">ชม.${h}</th>`).join('')}
              <th class="r">รวม</th><th class="r">NG</th><th class="r">เป้า</th><th class="c">%</th>
            </tr></thead>
            <tbody>
              ${totals.map((t) => `
                <tr>
                  <td class="t-strong">${esc(t.line.code)}</td>
                  <td class="t-mute t-sm">${esc(t.model)}</td>
                  ${hours.map((h) => {
                    const rec = (byLine.get(t.line.id) || {})[h];
                    return `<td class="c mono" style="cursor:pointer;${rec && cellClass(rec) === 'warn'
                      ? 'color:var(--warn)' : ''}" data-edit="${t.line.id}:${h}"
                      title="${rec ? `NG ${rec.ng_qty} · หยุด ${rec.downtime_min} นาที ${rec.downtime_reason || ''}` : 'ยังไม่บันทึก'}">
                      ${rec ? nf(rec.ok_qty) : '<span class="t-mute">—</span>'}</td>`;
                  }).join('')}
                  <td class="r mono t-strong">${nf(t.ok)}</td>
                  <td class="r mono" style="color:${t.ng ? 'var(--bad)' : 'inherit'}">${nf(t.ng)}</td>
                  <td class="r mono t-mute">${nf(t.target)}</td>
                  <td class="c"><span class="badge ${t.achievement >= 100 ? 'ok' : t.achievement >= 92 ? 'warn' : 'bad'}">
                    ${t.achievement.toFixed(0)}%</span></td>
                </tr>`).join('')}
              <tr style="background:var(--surface)">
                <td class="t-strong" colspan="2">รวมทุกไลน์</td>
                ${hourTotals.map((v) => `<td class="c mono t-strong">${v ? nf(v) : '—'}</td>`).join('')}
                <td class="r mono t-strong">${nf(grandOk)}</td>
                <td class="r mono t-strong">${nf(grandNg)}</td>
                <td class="r mono t-strong">${nf(grandTarget)}</td>
                <td class="c t-strong">${grandTarget ? (grandOk / grandTarget * 100).toFixed(0) : 0}%</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="card mt">
        <div class="card-head"><div><h3>จังหวะการผลิตรายชั่วโมง</h3>
          <p>เทียบยอดแต่ละชั่วโมงกับค่าเฉลี่ยเป้าหมาย</p></div></div>
        ${lineChart({
          labels: hours.map((h) => `ชม.${h}`),
          series: [
            { name: 'ยอดจริง', color: 'var(--accent-2)', values: hourTotals },
            { name: 'เป้าเฉลี่ย', color: 'var(--text-3)', dashed: true,
              values: hours.map(() => Math.round(grandTarget / store.shiftHours)) },
          ],
          height: 220,
        })}
      </div>`;

    // สาเหตุการหยุดจะโผล่มาเมื่อกรอกเวลาหยุด
    const form = root.querySelector('#quick');
    form.downtime_min.oninput = (e) => {
      root.querySelector('#quickReason').classList.toggle('hide', Number(e.target.value) <= 0);
    };
    const nowHour = Math.min(Math.max(new Date().getHours() - (store.shift === 'A' ? 7 : 19), 1), store.shiftHours);
    form.hour.value = String(nowHour);

    form.onsubmit = async (e) => {
      e.preventDefault();
      const data = readForm(form);
      const plan = planByLine.get(Number(data.line_id));
      if (!plan) { toast('ไลน์นี้ยังไม่มีแผนการผลิตของกะนี้ กรุณาสร้างแผนก่อน', 'bad'); return; }
      try {
        await api.post('/api/production', {
          ...data, rec_date: store.date, shift: store.shift, model_id: plan.model_id,
          downtime_reason: Number(data.downtime_min) > 0 ? data.downtime_reason : '',
        });
        toast(`บันทึกยอด ${nf(data.ok_qty)} ชิ้นแล้ว`);
        this.render(root);
      } catch (err) { toast(err.message, 'bad'); }
    };

    root.querySelectorAll('[data-edit]').forEach((cell) => {
      cell.onclick = () => {
        const [lineId, hour] = cell.dataset.edit.split(':').map(Number);
        const rec = (byLine.get(lineId) || {})[hour];
        const plan = planByLine.get(lineId);
        if (!plan) { toast('ไลน์นี้ยังไม่มีแผนของกะนี้', 'bad'); return; }
        this.editModal({ lineId, hour, rec, plan, root });
      };
    });
  },

  editModal({ lineId, hour, rec, plan, root }) {
    const line = store.line(lineId);
    const self = this;
    modal({
      title: `${line.code} · ชั่วโมงที่ ${hour}`,
      subtitle: `${thaiDate(store.date)} · กะ ${store.shift} · รุ่น ${plan.model_code}`,
      body: `<form id="editForm" class="grid g2">
        ${field('ยอดดี (ชิ้น)', `<input name="ok_qty" type="number" min="0" value="${rec?.ok_qty ?? 0}">`)}
        ${field('ของเสีย (ชิ้น)', `<input name="ng_qty" type="number" min="0" value="${rec?.ng_qty ?? 0}">`)}
        ${field('เวลาหยุด (นาที)', `<input name="downtime_min" type="number" min="0" value="${rec?.downtime_min ?? 0}">`)}
        ${field('กำลังคนจริง', `<input name="manpower" type="number" min="0" value="${rec?.manpower ?? line.std_manpower}">`)}
        <div style="grid-column:1/-1">${field('สาเหตุที่หยุด', `<select name="downtime_reason">
          <option value="">ไม่มี</option>
          ${REASONS.map((r) => `<option ${rec?.downtime_reason === r ? 'selected' : ''}>${r}</option>`).join('')}
        </select>`)}</div>
      </form>`,
      footer: `${rec && store.can('leader') ? `<button class="btn danger" data-del>${icon('trash', 15)} ลบ</button>` : ''}
        <div style="flex:1"></div>
        <button class="btn" data-close>ยกเลิก</button>
        <button class="btn primary" data-ok>บันทึก</button>`,
      onMount(overlay, close) {
        overlay.querySelector('[data-ok]').onclick = async () => {
          const data = readForm(overlay.querySelector('#editForm'));
          try {
            await api.post('/api/production', {
              ...data, rec_date: store.date, shift: store.shift, hour, line_id: lineId,
              model_id: plan.model_id,
            });
            close();
            toast('บันทึกแล้ว');
            self.render(root);
          } catch (err) { toast(err.message, 'bad'); }
        };
        overlay.querySelector('[data-del]')?.addEventListener('click', () => {
          close();
          confirmDialog('ต้องการลบข้อมูลชั่วโมงนี้หรือไม่', async () => {
            await api.del(`/api/production/${rec.id}`);
            toast('ลบแล้ว');
            self.render(root);
          });
        });
      },
    });
  },
};
