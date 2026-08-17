// จอ Andon สำหรับจอใหญ่หน้าไลน์ ตัวหนังสือใหญ่ อ่านได้จากระยะไกล
import { api, store } from '../api.js';
import { icon, esc, nf, thaiDate } from '../ui.js';

let timer = null;

const RISK = { green: 'green', amber: 'amber', red: 'red' };
const RISK_TEXT = { green: 'ตามแผน', amber: 'ต้องเร่ง', red: 'ต่ำกว่าเป้า' };

export default {
  title: 'จอ Andon',
  subtitle: '',

  async render(host) {
    const d = await api.get('/api/andon', { date: store.date, shift: store.shift });
    const totalTarget = d.lines.reduce((a, l) => a + l.target, 0);
    const totalActual = d.lines.reduce((a, l) => a + l.actual, 0);
    const totalProjected = d.lines.reduce((a, l) => a + l.projected, 0);
    const overall = totalTarget ? (totalActual / totalTarget) * 100 : 0;

    host.innerHTML = `
      <div class="andon">
        <div class="andon-head">
          <div class="brand-mark" style="width:52px;height:52px;font-size:17px">FGP</div>
          <div>
            <h1>FGP PRODUCTION ANDON</h1>
            <div class="t-mute">${thaiDate(d.date)} · กะ ${esc(d.shift)} · อัปเดตทุก 20 วินาที</div>
          </div>
          <div style="flex:1"></div>
          <div style="text-align:right">
            <div class="t-mute t-sm">ยอดรวมทั้งแผนก</div>
            <div class="num" style="font-size:38px;font-weight:800">${nf(totalActual)}
              <span style="font-size:20px;color:var(--text-3)">/ ${nf(totalTarget)}</span></div>
            <div class="badge ${overall >= 100 ? 'ok' : overall >= 92 ? 'warn' : 'bad'}"
              style="font-size:14px;padding:5px 12px">ทำได้แล้ว ${overall.toFixed(1)}% ของเป้า</div>
          </div>
          <div style="text-align:right;padding-left:24px;border-left:1px solid var(--line)">
            <div class="t-mute t-sm">OEE</div>
            <div class="num" style="font-size:38px;font-weight:800;color:${
              d.oee.oee >= 85 ? 'var(--ok)' : d.oee.oee >= 65 ? 'var(--warn)' : 'var(--bad)'}">
              ${d.oee.oee.toFixed(1)}<span style="font-size:20px">%</span></div>
            <div class="t-sm t-mute">คาดจบกะ ${nf(totalProjected)} ชิ้น</div>
          </div>
          <div class="row" style="padding-left:20px">
            <button class="btn icon" id="fsBtn" title="เต็มจอ">${icon('monitor', 18)}</button>
            <a class="btn icon" href="#/dashboard" title="กลับหน้าหลัก">${icon('x', 18)}</a>
          </div>
        </div>

        <div class="andon-grid">
          ${d.lines.length ? d.lines.map((l) => `
            <div class="andon-card ${RISK[l.risk]}">
              <div class="row" style="justify-content:space-between">
                <span class="code">${esc(l.line_code)}</span>
                <span class="badge ${l.risk === 'green' ? 'ok' : l.risk === 'amber' ? 'warn' : 'bad'}"
                  style="font-size:13px;padding:4px 11px"><span class="dot"></span>${RISK_TEXT[l.risk]}</span>
              </div>
              <div class="t-mute t-sm" style="margin-top:4px">${esc(l.model_code)} · ${esc(l.line_name)}</div>
              <div class="big">${nf(l.actual)}</div>
              <div class="t-mute">ทำได้แล้ว ${nf(l.target ? l.actual / l.target * 100 : 0, 0)}%
                ของเป้า ${nf(l.target)} ชิ้น · ผ่านไป ${l.hours_done}/${store.shiftHours} ชั่วโมง</div>
              <div class="bar ${l.risk === 'green' ? 'ok' : l.risk === 'amber' ? 'warn' : 'bad'}"
                style="height:10px;margin-top:14px">
                <i style="width:${Math.min(l.target ? l.actual / l.target * 100 : 0, 100)}%"></i></div>
              <div class="row" style="justify-content:space-between;margin-top:14px">
                <div><div class="t-mute t-sm">อัตราตอนนี้</div>
                  <b class="num" style="font-size:21px">${nf(l.rate_per_hour, 0)}</b>
                  <span class="t-sm t-mute">/ชม.</span></div>
                <div style="text-align:center"><div class="t-mute t-sm">ต้องทำให้ได้</div>
                  <b class="num" style="font-size:21px;color:${
                    l.need_rate > l.rate_per_hour ? 'var(--bad)' : 'var(--ok)'}">${nf(l.need_rate, 0)}</b>
                  <span class="t-sm t-mute">/ชม.</span></div>
                <div style="text-align:right"><div class="t-mute t-sm">คาดจบกะ (${l.achievement.toFixed(0)}%)</div>
                  <b class="num" style="font-size:21px">${nf(l.projected)}</b></div>
              </div>
            </div>`).join('')
            : `<div class="card"><div class="empty">${icon('monitor', 44)}
               <b>ยังไม่มีแผนการผลิตของกะนี้</b></div></div>`}
        </div>

        ${d.advice.length ? `<div class="card mt">
          <div class="card-head"><h3 style="font-size:17px">${icon('alert', 18)} เรื่องด่วนที่ต้องจัดการ</h3></div>
          <div class="stack">${d.advice.map((a) => `
            <div class="tip high">
              <div class="tip-ico">${icon(a.icon, 18)}</div>
              <div><b style="font-size:15px">${esc(a.title)}</b>
                <p style="font-size:13.5px">${esc(a.detail)}</p>
                <div class="act">${esc(a.action)}</div></div>
            </div>`).join('')}</div>
        </div>` : ''}
      </div>`;

    host.querySelector('#fsBtn').onclick = () => {
      if (document.fullscreenElement) document.exitFullscreen();
      else document.documentElement.requestFullscreen?.();
    };

    clearInterval(timer);
    timer = setInterval(() => {
      if (location.hash !== '#/andon') { clearInterval(timer); return; }
      if (!document.hidden) this.render(host).catch(() => {});
    }, 20000);
  },
};
