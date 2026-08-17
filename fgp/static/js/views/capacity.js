// กำลังการผลิต: คอขวด ภาระงานล่วงหน้า และข้อเสนอย้ายงาน
import { api, store } from '../api.js';
import { icon, esc, nf, pct, toast, thaiDate } from '../ui.js';
import { barChart, ringGauge } from '../charts.js';

const STATUS = { overload: ['bad', 'เกินกำลัง'], tight: ['warn', 'ตึงมาก'], ok: ['ok', 'รับไหว'] };

export default {
  title: 'กำลังการผลิต',
  subtitle: 'ดูว่าไลน์ไหนเป็นคอขวด และควรย้ายงานไปที่ใด',
  autoRefresh: 90000,

  async render(root) {
    const data = await api.get('/api/smart/capacity', { date: store.date, shift: store.shift });
    const bn = data.bottleneck;
    const mp = data.manpower;
    const outlook = data.outlook;
    const avgUtil = bn.items.length
      ? bn.items.reduce((a, i) => a + i.utilization, 0) / bn.items.length : 0;

    root.innerHTML = `
      <div class="grid g4">
        <div class="card kpi"><div class="label">${icon('capacity', 15)} การใช้กำลังเฉลี่ย</div>
          <div class="value num">${avgUtil.toFixed(1)}<span style="font-size:15px">%</span></div>
          <div class="sub">${bn.items.length} ไลน์ในกะ ${store.shift}</div></div>
        <div class="card kpi"><div class="label">${icon('alert', 15)} ไลน์ที่เกินกำลัง</div>
          <div class="value num" style="color:${bn.overloaded.length ? 'var(--bad)' : 'var(--ok)'}">
            ${bn.overloaded.length}</div>
          <div class="sub">${bn.overloaded.map((o) => o.line_code).join(', ') || 'ไม่มี ทุกไลน์รับไหว'}</div></div>
        <div class="card kpi"><div class="label">${icon('people', 15)} กำลังคน</div>
          <div class="value num">${mp.available}<span style="font-size:15px">/${mp.required}</span></div>
          <div class="sub">${mp.gap >= 0 ? `เพียงพอ เหลือ ${mp.gap} คน` : `ขาด ${Math.abs(mp.gap)} คน`}</div></div>
        <div class="card kpi"><div class="label">${icon('bolt', 15)} จุดคอขวด</div>
          <div class="value num" style="font-size:26px">${esc(bn.constraint?.line_code || '-')}</div>
          <div class="sub">${bn.constraint ? `ใช้กำลัง ${pct(bn.constraint.utilization)}` : 'ยังไม่มีแผนของกะนี้'}</div></div>
      </div>

      <div class="grid g-2-1 mt">
        <div class="card">
          <div class="card-head">
            <div><h3>ภาระงานเทียบเวลาที่มีจริง</h3>
              <p>เวลาที่ต้องใช้ผลิตตามแผน เทียบเวลาของกะหลังหักเวลาหยุดเครื่อง</p></div>
          </div>
          ${bn.items.length ? `<div class="stack">${bn.items.map((i) => `
            <div>
              <div class="row" style="justify-content:space-between;margin-bottom:6px">
                <div><b>${esc(i.line_code)}</b>
                  <span class="t-sm t-mute" style="margin-left:8px">${esc(i.model_code)} · เป้า ${nf(i.target)} ชิ้น</span></div>
                <div class="row" style="gap:8px">
                  <span class="mono t-sm t-mute">${nf(i.load_min)} / ${nf(i.available_min)} นาที</span>
                  <span class="badge ${STATUS[i.status][0]}">${pct(i.utilization)} ${STATUS[i.status][1]}</span>
                </div>
              </div>
              <div class="bar ${i.status === 'overload' ? 'bad' : i.status === 'tight' ? 'warn' : 'ok'}">
                <i style="width:${Math.min(i.utilization, 100)}%"></i></div>
              <div class="t-sm t-mute" style="margin-top:4px">
                ${i.headroom >= 0 ? `เหลือเวลาว่าง ${nf(i.headroom)} นาที` : `ขาดเวลา ${nf(Math.abs(i.headroom))} นาที`}
                ${i.downtime_min ? ` · หยุดเครื่องไปแล้ว ${nf(i.downtime_min)} นาที` : ''}
              </div>
            </div>`).join('')}</div>`
            : `<div class="empty">${icon('capacity', 40)}<b>ยังไม่มีแผนของกะนี้</b></div>`}
        </div>

        <div class="card" style="display:flex;flex-direction:column;align-items:center;gap:12px">
          <div class="card-head" style="width:100%"><h3>ความครอบคลุมกำลังคน</h3></div>
          ${ringGauge(Math.min(mp.coverage, 150), { label: 'ครอบคลุม', max: 150, size: 160,
            sub: `${mp.available} จาก ${mp.required} คน` })}
          <div class="stack" style="width:100%">
            <div class="row" style="justify-content:space-between">
              <span class="t-sm t-mute">จองคิวไว้แล้ว</span><b class="mono">${mp.booked} คน</b></div>
            <div class="row" style="justify-content:space-between">
              <span class="t-sm t-mute">ไลน์ที่ต้องเดิน</span><b class="mono">${mp.lines} ไลน์</b></div>
          </div>
          ${mp.gap < 0 ? `<a class="btn primary sm" href="#/booking" style="width:100%">
            ${icon('booking', 15)} เปิดคิวจองคนเพิ่ม</a>` : ''}
        </div>
      </div>

      <div class="card mt">
        <div class="card-head">
          <div><h3>ข้อเสนอย้ายงานระหว่างไลน์</h3>
            <p>ระบบจับคู่ไลน์ที่ล้นกับไลน์ที่ยังมีเวลาว่าง</p></div>
          <div class="right"><span class="badge info">${icon('brain', 12)} อัจฉริยะ</span></div>
        </div>
        ${bn.moves?.length ? `<div class="stack">${bn.moves.map((m) => `
          <div class="tip medium">
            <div class="tip-ico">${icon('shuffle', 17)}</div>
            <div>
              <b>ย้าย ${nf(m.qty)} ชิ้น (${esc(m.model_code)}) จาก ${esc(m.from)} ไป ${esc(m.to)}</b>
              <p>${esc(m.reason)}</p>
              <div class="act">${icon('bolt', 12)} ปรับแผนแล้วแจ้ง leader ทั้งสองไลน์</div>
            </div>
          </div>`).join('')}</div>`
          : `<p class="t-mute t-sm">ตอนนี้ไม่มีไลน์ที่ต้องย้ายงาน ภาระงานสมดุลดีอยู่แล้ว</p>`}
      </div>

      <div class="card mt">
        <div class="card-head">
          <div><h3>ภาระงานล่วงหน้า 7 วัน</h3>
            <p>เทียบความต้องการผลิตกับกำลังที่มีทั้งแผนก</p></div>
        </div>
        ${barChart({
          labels: outlook.map((o) => `${o.weekday} ${o.date.slice(8)}`),
          values: outlook.map((o) => o.demand_min),
          targets: outlook.map((o) => o.capacity_min),
          height: 250,
          formatter: (v) => nf(v / 60, 0) + 'ชม',
        })}
        <div class="table-wrap mt">
          <table>
            <thead><tr><th>วันที่</th><th class="r">เป้าผลิต (ชิ้น)</th><th class="r">เวลาที่ต้องใช้</th>
              <th class="r">กำลังที่มี</th><th class="c">การใช้กำลัง</th><th>สถานะ</th></tr></thead>
            <tbody>${outlook.map((o) => `<tr>
              <td>${thaiDate(o.date)} <span class="t-mute t-sm">(${o.weekday})</span></td>
              <td class="r mono">${nf(o.target_qty)}</td>
              <td class="r mono">${nf(o.demand_min / 60, 1)} ชม.</td>
              <td class="r mono t-mute">${nf(o.capacity_min / 60, 0)} ชม.</td>
              <td class="c" style="min-width:120px">
                <div class="bar ${o.utilization > 100 ? 'bad' : o.utilization > 85 ? 'warn' : 'ok'}">
                  <i style="width:${Math.min(o.utilization, 100)}%"></i></div>
                <span class="t-sm mono t-mute">${pct(o.utilization)}</span></td>
              <td><span class="badge ${o.utilization > 100 ? 'bad' : o.utilization > 85 ? 'warn' : 'ok'}">
                ${o.utilization > 100 ? 'ต้องเพิ่มกะหรือ OT' : o.utilization > 85 ? 'ตึง' : 'รับไหว'}</span></td>
            </tr>`).join('')}</tbody>
          </table>
        </div>
      </div>`;
  },
};
