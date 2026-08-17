// ศูนย์วิเคราะห์อัจฉริยะ: คำแนะนำ ความผิดปกติ พาเรโต และพยากรณ์
import { api, store } from '../api.js';
import { icon, esc, nf, pct, toast, thaiDate } from '../ui.js';
import { paretoChart, lineChart, ringGauge } from '../charts.js';

const SEV = { high: ['bad', 'เร่งด่วน'], medium: ['warn', 'ควรดู'], low: ['mute', 'เฝ้าระวัง'] };

export default {
  title: 'ศูนย์วิเคราะห์อัจฉริยะ',
  subtitle: 'ทุกคำแนะนำคำนวณจากข้อมูลจริงและอธิบายที่มาได้เสมอ',
  autoRefresh: 90000,

  async render(root) {
    const q = { date: store.date, shift: store.shift };
    const [advisor, anomaly, pareto, forecast, oee] = await Promise.all([
      api.get('/api/smart/advisor', q),
      api.get('/api/smart/anomaly', { days: 14 }),
      api.get('/api/smart/pareto', { days: 7 }),
      api.get('/api/smart/forecast', q),
      api.get('/api/smart/oee', q),
    ]);

    const high = advisor.items.filter((t) => t.severity === 'high');
    const totalDown = pareto.items.reduce((a, r) => a + r.minutes, 0);

    root.innerHTML = `
      <div class="grid g4">
        <div class="card kpi accent">
          <div class="label">${icon('brain', 15)} คำแนะนำทั้งหมด</div>
          <div class="value num">${advisor.items.length}</div>
          <div class="sub">เร่งด่วน ${high.length} เรื่อง</div></div>
        <div class="card kpi"><div class="label">${icon('anomaly', 15)} ความผิดปกติ 14 วัน</div>
          <div class="value num" style="color:${anomaly.items.length ? 'var(--warn)' : 'var(--ok)'}">
            ${anomaly.items.length}</div>
          <div class="sub">ตรวจด้วยค่า z-score รายไลน์</div></div>
        <div class="card kpi"><div class="label">${icon('stop', 15)} เวลาหยุด 7 วัน</div>
          <div class="value num">${nf(totalDown)}<span style="font-size:15px"> นาที</span></div>
          <div class="sub">${pareto.items[0] ? `สาเหตุหลัก: ${esc(pareto.items[0].reason)}` : 'ไม่มีการหยุด'}</div></div>
        <div class="card kpi"><div class="label">${icon('oee', 15)} OEE กะนี้</div>
          <div class="value num">${oee.oee.toFixed(1)}<span style="font-size:15px">%</span></div>
          <div class="sub">A ${oee.availability.toFixed(0)} · P ${oee.performance.toFixed(0)} · Q ${oee.quality.toFixed(0)}</div></div>
      </div>

      <div class="grid g-2-1 mt">
        <div class="card">
          <div class="card-head">
            <div><h3>สิ่งที่ควรทำตอนนี้</h3><p>เรียงจากผลกระทบมากไปน้อย</p></div>
            <div class="right"><button class="btn sm" id="alertBtn">${icon('refresh', 14)} บันทึกเป็นการแจ้งเตือน</button></div>
          </div>
          <div class="scroll-y" style="max-height:560px">
            ${advisor.items.length ? advisor.items.map((t) => `
              <div class="tip ${t.severity}">
                <div class="tip-ico">${icon(t.icon, 17)}</div>
                <div style="min-width:0">
                  <div class="row" style="gap:8px;margin-bottom:3px">
                    <b>${esc(t.title)}</b>
                    <span class="badge ${SEV[t.severity]?.[0] || 'mute'}">${SEV[t.severity]?.[1] || ''}</span>
                    ${t.line !== '-' ? `<span class="chip">${esc(t.line)}</span>` : ''}
                  </div>
                  <p>${esc(t.detail)}</p>
                  <div class="act">${icon('bolt', 12)} ${esc(t.action)}</div>
                </div>
              </div>`).join('')
              : `<div class="empty">${icon('check', 40)}<b>ทุกอย่างอยู่ในเกณฑ์</b>
                 <div class="t-sm">ไม่มีเรื่องที่ต้องรีบจัดการในกะนี้</div></div>`}
          </div>
        </div>

        <div class="card" style="display:flex;flex-direction:column;align-items:center;gap:14px">
          <div class="card-head" style="width:100%">
            <div><h3>ความแม่นของพยากรณ์</h3><p>เฉลี่ยความมั่นใจทุกไลน์</p></div></div>
          ${ringGauge(forecast.items.length
            ? forecast.items.reduce((a, f) => a + f.confidence, 0) / forecast.items.length : 0,
            { label: 'ความมั่นใจ', size: 158, sub: `${forecast.items.length} ไลน์` })}
          <div class="stack" style="width:100%">
            ${forecast.items.map((f) => `
              <div class="row" style="justify-content:space-between">
                <span class="t-sm"><b>${esc(f.line_code)}</b>
                  <span class="t-mute"> คาด ${nf(f.projected)} ชิ้น</span></span>
                <span class="badge ${f.risk === 'green' ? 'ok' : f.risk === 'amber' ? 'warn' : 'bad'}">
                  ${f.achievement.toFixed(0)}%</span>
              </div>`).join('') || '<p class="t-sm t-mute">ยังไม่มีแผนของกะนี้</p>'}
          </div>
        </div>
      </div>

      <div class="card mt">
        <div class="card-head">
          <div><h3>พาเรโตสาเหตุการหยุดเครื่อง (7 วัน)</h3>
            <p>แก้สองอันดับแรกได้ ก็ลดเวลาหยุดไปแล้วเกินครึ่ง</p></div>
        </div>
        ${pareto.items.length ? paretoChart(pareto.items) : `<div class="empty">${icon('check', 40)}
          <b>ไม่มีการหยุดเครื่องใน 7 วันที่ผ่านมา</b></div>`}
        ${pareto.items.length ? `<div class="table-wrap mt"><table>
          <thead><tr><th>สาเหตุ</th><th class="r">จำนวนครั้ง</th><th class="r">รวมเวลา</th>
            <th class="r">สัดส่วน</th><th class="r">สะสม</th></tr></thead>
          <tbody>${pareto.items.map((r) => `<tr>
            <td class="t-strong">${esc(r.reason)}</td>
            <td class="r mono">${nf(r.times)}</td>
            <td class="r mono">${nf(r.minutes)} นาที</td>
            <td class="r mono">${pct(r.share)}</td>
            <td class="r mono t-mute">${pct(r.cumulative)}</td>
          </tr>`).join('')}</tbody></table></div>` : ''}
      </div>

      <div class="card mt">
        <div class="card-head">
          <div><h3>ความผิดปกติที่ระบบตรวจพบ</h3>
            <p>เทียบกับพฤติกรรมปกติของแต่ละไลน์ ไม่ใช้เกณฑ์ตายตัว</p></div>
          <div class="right"><span class="badge info">${icon('anomaly', 12)} z-score ≥ 2.2</span></div>
        </div>
        ${anomaly.items.length ? `<div class="table-wrap"><table>
          <thead><tr><th>วันที่</th><th>ไลน์</th><th>ประเภท</th><th>รายละเอียด</th>
            <th class="r">คะแนนความผิดปกติ</th><th>ระดับ</th></tr></thead>
          <tbody>${anomaly.items.map((a) => `<tr>
            <td class="t-sm">${thaiDate(a.date)} <span class="t-mute">กะ ${esc(a.shift)} ชม.${a.hour}</span></td>
            <td class="t-strong">${esc(a.line_code)}</td>
            <td>${esc(a.title)}</td>
            <td class="t-sm t-mute">${esc(a.detail)}</td>
            <td class="r mono">${a.score.toFixed(1)}σ</td>
            <td><span class="badge ${a.severity === 'high' ? 'bad' : 'warn'}">
              ${a.severity === 'high' ? 'สูง' : 'ปานกลาง'}</span></td>
          </tr>`).join('')}</tbody></table></div>`
          : `<div class="empty">${icon('check', 40)}<b>ไม่พบความผิดปกติ</b>
             <div class="t-sm">ทุกไลน์ผลิตอยู่ในช่วงปกติของตัวเอง</div></div>`}
      </div>

      <div class="card mt">
        <div class="card-head"><div><h3>อัตราการผลิตที่ต้องทำให้ได้</h3>
          <p>เทียบอัตราปัจจุบันกับอัตราที่ต้องทำในเวลาที่เหลือ</p></div></div>
        ${forecast.items.length ? lineChart({
          labels: forecast.items.map((f) => f.line_code),
          series: [
            { name: 'อัตราปัจจุบัน', color: 'var(--accent-2)', values: forecast.items.map((f) => f.rate_per_hour) },
            { name: 'อัตราที่ต้องทำ', color: 'var(--bad)', dashed: true, values: forecast.items.map((f) => f.need_rate) },
          ],
          height: 230, area: false,
        }) : ''}
        <div class="legend mt">
          <span><i style="background:var(--accent-2)"></i>อัตราที่ทำได้จริงตอนนี้ (ชิ้น/ชม.)</span>
          <span><i style="background:var(--bad)"></i>อัตราที่ต้องทำเพื่อให้ถึงเป้า</span>
        </div>
      </div>`;

    root.querySelector('#alertBtn').onclick = async (e) => {
      e.target.disabled = true;
      const res = await api.post('/api/alerts/refresh', {});
      toast(res.created ? `บันทึกการแจ้งเตือนใหม่ ${res.created} รายการ` : 'ไม่มีเรื่องใหม่ที่ต้องแจ้ง');
      e.target.disabled = false;
    };
  },
};
