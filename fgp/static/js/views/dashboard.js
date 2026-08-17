// แดชบอร์ดภาพรวมของแผนก
import { api, store } from '../api.js';
import { icon, esc, nf, pct, deltaChip, thaiDate, relTime, toast } from '../ui.js';
import { lineChart, barChart, ringGauge, sparkline, rankBars } from '../charts.js';

const RISK = { green: ['ok', 'ตามแผน'], amber: ['warn', 'ต้องเฝ้าดู'], red: ['bad', 'เสี่ยงไม่ถึงเป้า'] };

function kpiCard({ label, iconName, value, unit = '', sub, spark, accent = false }) {
  return `<div class="card kpi ${accent ? 'accent' : ''}">
    <div class="label">${icon(iconName, 15)} ${esc(label)}</div>
    <div class="value num">${value}<span style="font-size:15px;color:var(--text-3);margin-left:5px">${esc(unit)}</span></div>
    <div class="sub">${sub}</div>
    ${spark ? `<div class="spark">${spark}</div>` : ''}
  </div>`;
}

export default {
  title: 'แดชบอร์ด',
  subtitle: 'ภาพรวมการผลิตแบบสด อัปเดตอัตโนมัติทุก 45 วินาที',
  autoRefresh: 45000,

  async render(root) {
    const d = await api.get('/api/dashboard', { date: store.date, shift: store.shift });
    const k = d.kpi;
    const trend = d.trend || [];
    const okSeries = trend.map((t) => t.ok);
    const hourly = d.hourly || [];

    const advice = (d.advice || []).map((a) => `
      <div class="tip ${a.severity}">
        <div class="tip-ico">${icon(a.icon, 17)}</div>
        <div style="min-width:0">
          <b>${esc(a.title)}</b>
          <p>${esc(a.detail)}</p>
          <div class="act">${icon('bolt', 12)} ${esc(a.action)}</div>
        </div>
      </div>`).join('') || `<p class="t-mute t-sm">ยังไม่พบสัญญาณผิดปกติ ทุกไลน์เดินตามแผน</p>`;

    root.innerHTML = `
      <div class="grid g4">
        ${kpiCard({
          label: 'ยอดผลิตวันนี้', iconName: 'box', value: nf(k.ok), unit: 'ชิ้น',
          sub: `${deltaChip(k.vs_yesterday)} เทียบเมื่อวาน`,
          spark: sparkline(okSeries), accent: true,
        })}
        ${kpiCard({
          label: 'เทียบเป้าหมาย', iconName: 'capacity', value: k.achievement.toFixed(1), unit: '%',
          sub: `เป้า ${nf(k.target)} ชิ้น · คาดจบวัน ${nf(d.projected_total)} ชิ้น`,
          spark: `<div class="bar ${k.achievement >= 100 ? 'ok' : k.achievement >= 92 ? 'warn' : 'bad'}"
                    style="margin-top:12px"><i style="width:${Math.min(k.achievement, 100)}%"></i></div>`,
        })}
        ${kpiCard({
          label: 'คุณภาพ (Yield)', iconName: 'check', value: k.yield.toFixed(2), unit: '%',
          sub: `ของเสีย ${nf(k.ng)} ชิ้น จาก ${nf(k.ok + k.ng)} ชิ้น`,
          spark: sparkline(trend.map((t) => t.yield || 0), { color: 'var(--ok)' }),
        })}
        ${kpiCard({
          label: 'เวลาหยุดเครื่อง', iconName: 'stop', value: nf(k.downtime), unit: 'นาที',
          sub: `เฉลี่ย ${nf(k.downtime / Math.max(store.lines.length, 1), 1)} นาที/ไลน์`,
          spark: sparkline(trend.map((t) => t.dtm || 0), { color: 'var(--warn)' }),
        })}
      </div>

      <div class="grid g-2-1 mt">
        <div class="card">
          <div class="card-head">
            <div><h3>ยอดผลิตสะสมรายชั่วโมง</h3>
              <p>${thaiDate(d.date)} · กะ ${d.shift} · เส้นประคือเป้าสะสม</p></div>
            <div class="right legend">
              <span><i style="background:var(--accent-2)"></i>ยอดจริง</span>
              <span><i style="background:var(--text-3)"></i>เป้าสะสม</span>
            </div>
          </div>
          ${hourly.length ? lineChart({
            labels: hourly.map((h) => `ชม.${h.hour}`),
            series: [
              { name: 'ยอดสะสม', color: 'var(--accent-2)', values: hourly.map((h) => h.cumulative) },
              { name: 'เป้าสะสม', color: 'var(--text-3)', values: hourly.map((h) => h.target_cumulative), dashed: true },
            ],
            height: 260,
          }) : `<div class="empty">${icon('clock', 40)}<b>ยังไม่มีการบันทึกยอดในกะนี้</b>
                <div class="t-sm">เริ่มบันทึกได้ที่เมนู "บันทึกยอดผลิต"</div></div>`}
        </div>

        <div class="card" style="display:flex;flex-direction:column;align-items:center;justify-content:center;gap:14px">
          <div class="card-head" style="width:100%"><h3>OEE ของกะ</h3></div>
          ${ringGauge(d.oee.oee, { label: 'OEE', sub: `เกณฑ์แผนก 85%`, size: 168 })}
          <div style="width:100%" class="stack">
            ${[['เวลาเดินเครื่อง', d.oee.availability], ['ความเร็วผลิต', d.oee.performance],
               ['คุณภาพ', d.oee.quality]].map(([n, v]) => `
              <div>
                <div class="row" style="justify-content:space-between;margin-bottom:4px">
                  <span class="t-sm t-mute">${n}</span>
                  <b class="mono t-sm">${v.toFixed(1)}%</b>
                </div>
                <div class="bar ${v >= 90 ? 'ok' : v >= 75 ? 'warn' : 'bad'}">
                  <i style="width:${Math.min(v, 100)}%"></i></div>
              </div>`).join('')}
          </div>
        </div>
      </div>

      <div class="grid g-2-1 mt">
        <div class="card">
          <div class="card-head">
            <div><h3>พยากรณ์จบกะรายไลน์</h3>
              <p>คำนวณจากอัตราการผลิตถ่วงน้ำหนักและแนวโน้มล่าสุด</p></div>
            <div class="right"><span class="badge info">${icon('brain', 12)} อัจฉริยะ</span></div>
          </div>
          <div class="table-wrap">
            <table>
              <thead><tr>
                <th>ไลน์</th><th>รุ่น</th><th class="r">เป้า</th><th class="r">ทำได้</th>
                <th class="r">อัตรา/ชม.</th><th class="r">คาดจบกะ</th><th class="c">ความมั่นใจ</th><th>สถานะ</th>
              </tr></thead>
              <tbody>${d.forecast.length ? d.forecast.map((f) => `
                <tr>
                  <td class="t-strong">${esc(f.line_code)}</td>
                  <td class="t-mute t-sm">${esc(f.model_code)}</td>
                  <td class="r mono">${nf(f.target)}</td>
                  <td class="r mono">${nf(f.actual)}</td>
                  <td class="r mono">${nf(f.rate_per_hour, 0)}
                    ${f.trend ? `<span class="t-sm" style="color:var(--${f.trend > 0 ? 'ok' : 'bad'})">
                      ${f.trend > 0 ? '↑' : '↓'}</span>` : ''}</td>
                  <td class="r mono t-strong">${nf(f.projected)}</td>
                  <td class="c"><span class="badge mute">${f.confidence}%</span></td>
                  <td><span class="badge ${RISK[f.risk][0]}"><span class="dot"></span>
                    คาดจบ ${f.achievement.toFixed(0)}% · ${RISK[f.risk][1]}</span></td>
                </tr>`).join('') : `<tr><td colspan="8" class="c t-mute" style="padding:30px">
                  ยังไม่มีแผนการผลิตของกะนี้</td></tr>`}
              </tbody>
            </table>
          </div>
        </div>

        <div class="card">
          <div class="card-head"><h3>อันดับไลน์วันนี้</h3></div>
          ${d.lines.length ? rankBars(d.lines, { valueKey: 'ok', labelKey: 'code', targetKey: 'target' })
            : `<p class="t-mute t-sm">ยังไม่มีข้อมูล</p>`}
          <div class="card-head mt" style="margin-bottom:10px"><h3>กำลังคนกะนี้</h3></div>
          <div class="row" style="justify-content:space-between">
            <div><div class="value num" style="font-size:26px;font-weight:700">
              ${d.manpower.available}<span class="t-mute" style="font-size:14px"> / ${d.manpower.required} คน</span></div>
              <span class="t-sm t-mute">ครอบคลุม ${pct(d.manpower.coverage)}</span></div>
            <span class="badge ${d.manpower.gap >= 0 ? 'ok' : 'bad'}">
              ${d.manpower.gap >= 0 ? `เหลือ ${d.manpower.gap}` : `ขาด ${Math.abs(d.manpower.gap)}`} คน</span>
          </div>
          <div class="bar ${d.manpower.coverage >= 100 ? 'ok' : 'bad'} mt">
            <i style="width:${Math.min(d.manpower.coverage, 100)}%"></i></div>
        </div>
      </div>

      <div class="grid g-1-2 mt">
        <div class="card">
          <div class="card-head">
            <div><h3>ข้อเสนอแนะอัจฉริยะ</h3><p>เรียงตามความเร่งด่วน</p></div>
            <div class="right"><a class="btn sm ghost" href="#/smart">ดูทั้งหมด</a></div>
          </div>
          <div class="scroll-y">${advice}</div>
        </div>

        <div class="card">
          <div class="card-head">
            <div><h3>แนวโน้ม 14 วัน</h3><p>ยอดจริงเทียบเป้าหมายรายวัน</p></div>
          </div>
          ${trend.length ? barChart({
            labels: trend.map((t) => t.d.slice(8) + '/' + t.d.slice(5, 7)),
            values: trend.map((t) => t.ok),
            targets: trend.map((t) => t.target),
            height: 240,
          }) : ''}
          <div class="legend mt">
            <span><i style="background:var(--ok)"></i>ถึงเป้า</span>
            <span><i style="background:var(--warn)"></i>ใกล้เป้า</span>
            <span><i style="background:var(--bad)"></i>ต่ำกว่าเป้า</span>
            <span><i style="background:var(--line)"></i>เป้าหมาย</span>
          </div>
        </div>
      </div>

      <div class="card mt">
        <div class="card-head">
          <div><h3>การแจ้งเตือนที่ยังไม่รับทราบ</h3>
            <p>ระบบสร้างอัตโนมัติเมื่อพบความเสี่ยง</p></div>
          <div class="right">
            <span class="badge ${d.alerts.length ? 'bad' : 'ok'}">${d.alerts.length} รายการ</span>
            <button class="btn sm" id="scanBtn">${icon('refresh', 14)} สแกนใหม่</button>
          </div>
        </div>
        <div class="stack">${d.alerts.length ? d.alerts.map((a) => `
          <div class="tip ${a.severity === 'high' ? 'high' : 'medium'}">
            <div class="tip-ico">${icon(a.kind, 17)}</div>
            <div style="min-width:0;flex:1">
              <b>${esc(a.title)}</b>
              <p>${esc(a.detail)}</p>
              <div class="act">${relTime(a.created_at)}</div>
            </div>
            <button class="btn sm" data-ack="${a.id}">${icon('check', 14)} รับทราบ</button>
          </div>`).join('') : `<p class="t-mute t-sm">ไม่มีการแจ้งเตือนค้างอยู่</p>`}
        </div>
      </div>`;

    root.querySelector('#scanBtn').onclick = async (e) => {
      e.target.disabled = true;
      const res = await api.post('/api/alerts/refresh', {});
      toast(res.created ? `พบความเสี่ยงใหม่ ${res.created} รายการ` : 'สแกนแล้ว ไม่พบความเสี่ยงใหม่',
        res.created ? 'bad' : 'ok');
      this.render(root);
    };
    root.querySelectorAll('[data-ack]').forEach((btn) => {
      btn.onclick = async () => {
        await api.post(`/api/alerts/${btn.dataset.ack}/ack`, {});
        toast('รับทราบแล้ว');
        this.render(root);
      };
    });
  },
};
