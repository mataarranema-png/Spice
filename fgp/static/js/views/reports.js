// รายงานสรุปและส่งออกไฟล์ CSV
import { api, store } from '../api.js';
import { icon, esc, nf, pct, thaiDate } from '../ui.js';
import { barChart, paretoChart, rankBars, lineChart } from '../charts.js';

function addDays(iso, n) {
  const d = new Date(iso + 'T00:00:00');
  d.setDate(d.getDate() + n);
  return d.toISOString().slice(0, 10);
}

export default {
  title: 'รายงาน & Export',
  subtitle: 'สรุปผลตามช่วงเวลา พิมพ์ได้ทันที หรือส่งออกเป็นไฟล์ Excel',
  hideFilter: true,

  async render(root, range) {
    const from = range?.from ?? this._from ?? addDays(store.today, -6);
    const to = range?.to ?? this._to ?? store.today;
    this._from = from;
    this._to = to;

    const r = await api.get('/api/reports/summary', { from, to });
    const t = r.totals;

    root.innerHTML = `
      <div class="card">
        <div class="card-head">
          <div><h3>ช่วงเวลาที่ต้องการดู</h3><p>${thaiDate(from)} ถึง ${thaiDate(to)}</p></div>
          <div class="right">
            <input type="date" id="rFrom" value="${from}" style="width:150px">
            <span class="t-mute">ถึง</span>
            <input type="date" id="rTo" value="${to}" style="width:150px">
            <div class="seg" id="quick">
              <button data-days="7">7 วัน</button>
              <button data-days="14">14 วัน</button>
              <button data-days="30">30 วัน</button>
            </div>
            <a class="btn primary sm" href="/api/export/production.csv?from=${from}&to=${to}">
              ${icon('download', 15)} ดาวน์โหลด CSV</a>
            <button class="btn sm" onclick="window.print()">${icon('report', 15)} พิมพ์</button>
          </div>
        </div>
        <div class="grid g4">
          <div class="card kpi flat"><div class="label">ยอดผลิตรวม</div>
            <div class="value num">${nf(t.ok)}</div><div class="sub">ชิ้น</div></div>
          <div class="card kpi flat"><div class="label">เทียบเป้า</div>
            <div class="value num">${pct(t.achievement)}</div>
            <div class="sub">เป้า ${nf(t.target)} ชิ้น</div></div>
          <div class="card kpi flat"><div class="label">คุณภาพเฉลี่ย</div>
            <div class="value num">${pct(t.yield)}</div>
            <div class="sub">ของเสีย ${nf(t.ng)} ชิ้น</div></div>
          <div class="card kpi flat"><div class="label">เวลาหยุดรวม</div>
            <div class="value num">${nf(t.downtime)}</div><div class="sub">นาที</div></div>
        </div>
      </div>

      <div class="card mt">
        <div class="card-head"><div><h3>ยอดผลิตรายวันเทียบเป้า</h3>
          <p>สีเขียวคือถึงเป้า สีแดงคือต่ำกว่าเป้า</p></div></div>
        ${r.by_day.length ? barChart({
          labels: r.by_day.map((d) => d.d.slice(8) + '/' + d.d.slice(5, 7)),
          values: r.by_day.map((d) => d.ok),
          targets: r.by_day.map((d) => d.target),
          height: 250,
        }) : `<div class="empty">${icon('report', 40)}<b>ไม่มีข้อมูลในช่วงนี้</b></div>`}
      </div>

      <div class="grid g2 mt">
        <div class="card">
          <div class="card-head"><div><h3>สรุปตามไลน์</h3></div></div>
          ${r.by_line.length ? rankBars(r.by_line, { valueKey: 'ok', labelKey: 'code' }) : ''}
          <div class="table-wrap mt"><table>
            <thead><tr><th>ไลน์</th><th class="r">ยอดดี</th><th class="r">ของเสีย</th>
              <th class="r">Yield</th><th class="r">เวลาหยุด</th></tr></thead>
            <tbody>${r.by_line.map((l) => `<tr>
              <td class="t-strong">${esc(l.code)}</td>
              <td class="r mono">${nf(l.ok)}</td>
              <td class="r mono">${nf(l.ng)}</td>
              <td class="r"><span class="badge ${l.yield >= 99 ? 'ok' : l.yield >= 97 ? 'warn' : 'bad'}">
                ${pct(l.yield)}</span></td>
              <td class="r mono t-mute">${nf(l.dtm)} น.</td>
            </tr>`).join('')}</tbody></table></div>
        </div>

        <div class="card">
          <div class="card-head"><div><h3>สรุปตามรุ่นสินค้า</h3></div></div>
          <div class="table-wrap"><table>
            <thead><tr><th>รุ่น</th><th>ชื่อ</th><th class="r">ยอดดี</th>
              <th class="r">ของเสีย</th><th class="r">Yield</th></tr></thead>
            <tbody>${r.by_model.map((m) => `<tr>
              <td class="t-strong">${esc(m.code)}</td>
              <td class="t-sm t-mute">${esc(m.name)}</td>
              <td class="r mono">${nf(m.ok)}</td>
              <td class="r mono">${nf(m.ng)}</td>
              <td class="r"><span class="badge ${m.yield >= 99 ? 'ok' : m.yield >= 97 ? 'warn' : 'bad'}">
                ${pct(m.yield)}</span></td>
            </tr>`).join('') || '<tr><td colspan="5" class="c t-mute">ไม่มีข้อมูล</td></tr>'}</tbody>
          </table></div>
        </div>
      </div>

      <div class="card mt">
        <div class="card-head"><div><h3>แนวโน้มคุณภาพและความสำเร็จ</h3>
          <p>เส้นเดียวกันสองมุมมอง ดูว่าเร่งยอดแล้วคุณภาพตกหรือไม่</p></div></div>
        ${r.by_day.length ? lineChart({
          labels: r.by_day.map((d) => d.d.slice(8) + '/' + d.d.slice(5, 7)),
          series: [
            { name: 'ความสำเร็จ %', color: 'var(--accent-2)', values: r.by_day.map((d) => d.achievement) },
            { name: 'Yield %', color: 'var(--ok)', values: r.by_day.map((d) => d.yield) },
          ],
          height: 230, area: false, formatter: (v) => v.toFixed(0) + '%',
        }) : ''}
        <div class="legend mt">
          <span><i style="background:var(--accent-2)"></i>ความสำเร็จเทียบเป้า</span>
          <span><i style="background:var(--ok)"></i>คุณภาพ (Yield)</span>
        </div>
      </div>

      <div class="card mt">
        <div class="card-head"><div><h3>พาเรโตสาเหตุการหยุดเครื่อง</h3></div></div>
        ${r.pareto.length ? paretoChart(r.pareto) : `<div class="empty">${icon('check', 40)}
          <b>ไม่มีการหยุดเครื่องในช่วงนี้</b></div>`}
      </div>`;

    const self = this;
    const reload = () => self.render(root, {
      from: root.querySelector('#rFrom').value,
      to: root.querySelector('#rTo').value,
    });
    root.querySelector('#rFrom').onchange = reload;
    root.querySelector('#rTo').onchange = reload;
    root.querySelector('#quick').onclick = (e) => {
      const b = e.target.closest('[data-days]');
      if (!b) return;
      self.render(root, { from: addDays(store.today, -(Number(b.dataset.days) - 1)), to: store.today });
    };
  },
};
