/* ==========================================================================
   Myfxbook Earning System - หน้าจอทั้งหมด
   แต่ละหน้าเป็นฟังก์ชัน async ที่คืนค่า DOM element หนึ่งก้อน
   ========================================================================== */

const Views = (() => {
  'use strict';

  const { api, esc, num, money, signed, pct, h, fmtDate, fmtDayLabel, fmtStamp,
          toneDrawdown, toneGoal, statusChip } = MFE;

  /* ------------------------------------------------------------ ชิ้นส่วนร่วม */

  function stat(o) {
    return `<div class="stat tone-${o.tone || 'accent'}">
      <div class="stat-top">
        <span class="stat-label">${esc(o.label)}</span>
        ${o.chip || ''}
      </div>
      <div class="stat-value${o.compact ? ' is-compact' : ''}">${o.html || esc(o.value)}${o.unit ? `<span class="unit">${esc(o.unit)}</span>` : ''}</div>
      ${o.note ? `<p class="stat-note">${o.note}</p>` : ''}
      ${o.spark ? `<div class="stat-spark">${o.spark}</div>` : ''}
      ${o.meter !== undefined ? `<div class="meter ${o.meterTone || ''}" style="margin-top:10px"><span style="width:${Math.min(100, Math.max(0, o.meter))}%"></span></div>` : ''}
    </div>`;
  }

  function emptyBox(title, detail) {
    return `<div class="empty"><strong>${esc(title)}</strong>${esc(detail || '')}</div>`;
  }

  function ddChip(value, warnAt, critAt) {
    const tone = toneDrawdown(value, warnAt || 10, critAt || 20);
    return `<span class="chip chip-${tone}"><i class="dot"></i>${num(value, 2)}%</span>`;
  }

  function demoBanner(data) {
    if (!data.demo_mode) return '';
    return `<div class="card notice-card">
      <div>
        <strong>กำลังใช้โหมดสาธิต</strong>
        <p class="tiny">ตัวเลขทั้งหมดมาจากพอร์ตตัวอย่างที่สร้างไว้ในเครื่อง ใช้ลองระบบได้เต็มรูปแบบ
        เมื่อพร้อมใช้ข้อมูลจริงให้ไปที่หน้าเชื่อมต่อแล้วเข้าสู่ระบบ Myfxbook</p>
      </div>
      <a class="btn btn-primary btn-sm" href="#/connect">ไปหน้าเชื่อมต่อ</a>
    </div>`;
  }

  /* ==================================================================== ภาพรวม */

  async function overview() {
    const d = await api.get('/api/overview?days=120');
    const k = d.kpi;
    const cur = d.base_currency;

    const labels = d.series.map((p) => fmtDayLabel(p.day));
    const cumChart = d.series.length
      ? Chart.line({
          labels,
          height: 250,
          series: [{ name: 'กำไรสะสม (' + cur + ')', color: Chart.colors.accent, digits: 2, values: d.series.map((p) => p.cum) }],
          title: 'กำไรสะสมของทุกพอร์ต',
        })
      : emptyBox('ยังไม่มีข้อมูลรายวัน', 'กดซิงก์ที่หน้าเชื่อมต่อเพื่อดึงผลการเทรด');

    const pnlChart = d.series.length
      ? Chart.pnl({
          labels: labels.slice(-45),
          values: d.series.slice(-45).map((p) => p.profit),
          unit: ' ' + cur,
          height: 220,
          title: 'กำไรขาดทุนรายวัน',
        })
      : '';

    const topChart = d.top.length && d.top.some((t) => t.earning_base > 0)
      ? Chart.hbars(d.top.map((t) => ({
          label: t.name, value: t.earning_base, digits: 2, unit: ' ' + cur,
        })), { title: 'รายได้ส่วนแบ่งรายพอร์ตในรอบนี้' })
      : emptyBox('รอบนี้ยังไม่มีรายได้ส่วนแบ่ง', 'พอร์ตต้องทำกำไรเหนือจุดสูงสุดเดิมก่อนจึงจะเริ่มคิดส่วนแบ่ง');

    const goalMeter = k.target > 0 ? Math.min(100, (k.earning_period / k.target) * 100) : 0;
    const goalTone = toneGoal(k.target_pct, k.pace_pct);

    const accRows = d.accounts.map((a) => `<tr onclick="MFE.go('/account?id=${a.id}')" style="cursor:pointer">
      <td><strong>${esc(a.name)}</strong><span class="tiny muted"> · ${esc(a.broker || a.platform || 'ไม่ระบุโบรก')}</span></td>
      <td class="t-right mono">${money(a.balance, a.currency)}</td>
      <td class="t-right mono">${signed(a.profit, a.currency)}</td>
      <td class="t-right mono">${signed(a.gain_pct, '%', 2)}</td>
      <td class="t-right">${ddChip(a.drawdown_pct)}</td>
    </tr>`).join('');

    const html = `<div class="page stack">
      ${demoBanner(d)}

      <div class="grid g-4">
        ${stat({
          label: 'เงินในพอร์ตรวม', tone: 'accent',
          value: money(k.equity_total), unit: cur,
          note: `${num(k.accounts_n)} พอร์ตที่ติดตามอยู่`,
        })}
        ${stat({
          label: 'กำไรสะสมของทุกพอร์ต', tone: k.profit_total >= 0 ? 'ok' : 'crit',
          html: signed(k.profit_total), unit: cur,
          note: 'นับรวมทุกวันที่มีข้อมูลในระบบ',
        })}
        ${stat({
          label: 'รายได้ส่วนแบ่ง ' + esc(d.period.label), tone: goalTone === 'mute' ? 'info' : goalTone,
          value: money(k.earning_period), unit: cur,
          note: k.target > 0
            ? `เป้าหมาย ${money(k.target)} ${esc(cur)} · ทำได้ ${pct(k.target_pct)} เวลาผ่านไป ${pct(k.pace_pct)}`
            : 'ยังไม่ได้ตั้งเป้าหมายของรอบนี้',
          meter: goalMeter, meterTone: goalTone === 'mute' ? '' : goalTone,
        })}
        ${stat({
          label: 'รายได้ค้างจ่าย', tone: k.outstanding > 0 ? 'warn' : 'ok',
          value: money(k.outstanding), unit: cur,
          note: `คิดส่วนแบ่งสะสม ${money(k.earning_all)} · จ่ายแล้ว ${money(k.paid_all)}`,
        })}
      </div>

      <div class="card">
        <div class="card-head">
          <div><h2>เส้นทางกำไรของทุกพอร์ต</h2><p>แปลงเป็น ${esc(cur)} ด้วยอัตราแลกเปลี่ยนที่ตั้งไว้ · ย้อนหลัง 120 วัน</p></div>
          <div class="card-tools"><a class="btn btn-ghost btn-sm" href="#/earnings">ดูรายได้รายรอบ</a></div>
        </div>
        ${cumChart}
      </div>

      <div class="grid g-2-1">
        <div class="card">
          <div class="card-head"><div><h2>กำไรขาดทุนรายวัน</h2><p>45 วันทำการล่าสุด</p></div></div>
          ${pnlChart || emptyBox('ยังไม่มีข้อมูลรายวัน', '')}
        </div>
        <div class="card">
          <div class="card-head"><div><h2>รายได้รอบนี้</h2><p>${esc(d.period.label)}</p></div></div>
          ${topChart}
        </div>
      </div>

      <div class="card">
        <div class="card-head">
          <div><h2>พอร์ตที่ติดตามอยู่</h2><p>กดที่แถวเพื่อดูรายละเอียดและเงื่อนไขส่วนแบ่ง</p></div>
          <div class="card-tools"><a class="btn btn-ghost btn-sm" href="#/accounts">จัดการพอร์ต</a></div>
        </div>
        ${d.accounts.length ? `<div class="table-wrap"><table>
          <thead><tr>
            <th>พอร์ต</th><th class="t-right">ยอดเงิน</th><th class="t-right">กำไรสะสม</th>
            <th class="t-right">% กำไร</th><th class="t-right">Drawdown สูงสุด</th>
          </tr></thead>
          <tbody>${accRows}</tbody>
        </table></div>` : emptyBox('ยังไม่มีพอร์ตที่ติดตาม', 'เชื่อมต่อ Myfxbook แล้วกดซิงก์')}
      </div>
    </div>`;

    return h(html);
  }

  /* =================================================================== พอร์ต */

  async function accounts() {
    const d = await api.get('/api/accounts');
    const cur = d.base_currency;

    const rows = d.accounts.map((a) => {
      const rule = a.rule || { share_pct: 0, use_hwm: false, active: false };
      return `<tr class="${a.tracked ? '' : 'is-muted'}">
        <td>
          <strong>${esc(a.name)}</strong>
          ${a.is_demo ? '<span class="chip chip-mute">บัญชีทดลอง</span>' : ''}
          <div class="tiny muted">${esc(a.broker || '-')} · ${esc(a.platform || '-')} · เลขที่ ${esc(a.account_no || '-')}</div>
        </td>
        <td class="t-right mono">${money(a.balance, a.currency)}</td>
        <td class="t-right mono">${signed(a.profit, a.currency)}</td>
        <td class="t-right mono">${signed(a.gain_pct, '%', 2)}</td>
        <td class="t-right">${ddChip(a.drawdown_pct)}</td>
        <td style="width:130px">${a.spark.length ? Chart.spark(a.spark) : '<span class="tiny muted">-</span>'}</td>
        <td class="t-right">
          ${rule.active
            ? `<span class="chip chip-accent">${num(rule.share_pct, 0)}%</span>
               ${rule.use_hwm ? '<span class="chip chip-info">HWM</span>' : ''}`
            : '<span class="chip chip-mute">ปิดอยู่</span>'}
        </td>
        <td class="t-right mono">${money(a.ledger.outstanding, a.currency)}</td>
        <td class="t-right nowrap">
          <button class="btn btn-sm btn-ghost" onclick="Actions.editRule(${a.id})">เงื่อนไข</button>
          <a class="btn btn-sm btn-ghost" href="#/account?id=${a.id}">ดู</a>
          <button class="btn btn-sm btn-ghost" onclick="Actions.toggleTrack(${a.id}, ${a.tracked ? 'false' : 'true'})">
            ${a.tracked ? 'หยุดติดตาม' : 'ติดตาม'}
          </button>
        </td>
      </tr>`;
    }).join('');

    const tracked = d.accounts.filter((a) => a.tracked);
    const totalOutstanding = tracked.reduce((s, a) => s + a.ledger_base.outstanding, 0);
    const totalAccrued = tracked.reduce((s, a) => s + a.ledger_base.accrued, 0);

    const html = `<div class="page stack">
      <div class="grid g-3">
        ${stat({ label: 'พอร์ตทั้งหมด', value: num(d.accounts.length), unit: 'พอร์ต', tone: 'info',
                 note: `ติดตามอยู่ ${num(tracked.length)} พอร์ต` })}
        ${stat({ label: 'รายได้ส่วนแบ่งสะสม', value: money(totalAccrued), unit: cur, tone: 'accent',
                 note: 'นับทุกรอบที่คิดไว้แล้ว' })}
        ${stat({ label: 'ค้างจ่ายรวม', value: money(totalOutstanding), unit: cur,
                 tone: totalOutstanding > 0 ? 'warn' : 'ok', note: 'ยอดที่ยังไม่ได้บันทึกการจ่าย' })}
      </div>

      <div class="card">
        <div class="card-head">
          <div><h2>พอร์ตและเงื่อนไขส่วนแบ่ง</h2>
          <p>ยอดในคอลัมน์เงินเป็นสกุลของพอร์ตเอง ส่วนยอดรวมด้านบนแปลงเป็น ${esc(cur)} แล้ว</p></div>
          <div class="card-tools">
            <button class="btn btn-sm btn-primary" onclick="Actions.syncNow()">ซิงก์ข้อมูล</button>
          </div>
        </div>
        ${d.accounts.length ? `<div class="table-wrap"><table>
          <thead><tr>
            <th>พอร์ต</th><th class="t-right">ยอดเงิน</th><th class="t-right">กำไรสะสม</th>
            <th class="t-right">% กำไร</th><th class="t-right">Drawdown</th><th>14 วันล่าสุด</th>
            <th class="t-right">ส่วนแบ่ง</th><th class="t-right">ค้างจ่าย</th><th></th>
          </tr></thead>
          <tbody>${rows}</tbody>
        </table></div>` : emptyBox('ยังไม่มีพอร์ตในระบบ', 'ไปที่หน้าเชื่อมต่อเพื่อเข้าสู่ระบบ Myfxbook แล้วกดซิงก์')}
      </div>
    </div>`;

    return h(html);
  }

  /* ------------------------------------------------------- รายละเอียดพอร์ต */

  async function accountDetail(params) {
    const id = Number(params.id || 0);
    if (!id) return h(`<div class="card">${emptyBox('ไม่ได้ระบุพอร์ต', 'กลับไปเลือกพอร์ตจากหน้ารายการ')}</div>`);
    const d = await api.get('/api/accounts/' + id + '?days=240');
    const a = d.account;
    const rule = a.rule || {};

    const labels = d.daily.map((r) => fmtDayLabel(r.day));
    const equityChart = d.daily.length
      ? Chart.line({
          labels, height: 250,
          series: [{ name: 'ยอดเงินในพอร์ต (' + a.currency + ')', color: Chart.colors.accent, digits: 2,
                     values: d.daily.map((r) => r.balance) }],
          title: 'เส้นยอดเงินในพอร์ต',
        })
      : emptyBox('ยังไม่มีข้อมูลรายวันของพอร์ตนี้', '');

    const pnlChart = d.daily.length
      ? Chart.pnl({ labels: labels.slice(-45), values: d.daily.slice(-45).map((r) => r.profit),
                    unit: ' ' + a.currency, height: 210 })
      : '';

    const accrualRows = d.accruals.map((k) => `<tr>
      <td><strong>${esc(k.label)}</strong><div class="tiny muted">${fmtDate(k.start_day, true)} - ${fmtDate(k.end_day, true)}</div></td>
      <td class="t-right mono">${signed(k.gross, a.currency)}</td>
      <td class="t-right mono">${money(k.base, a.currency)}</td>
      <td class="t-right mono tiny">${money(k.hwm_before)} → ${money(k.hwm_after)}</td>
      <td class="t-right mono">${num(k.share_pct, 0)}%</td>
      <td class="t-right mono"><strong>${money(k.earning, a.currency)}</strong></td>
      <td class="t-right mono">${money(k.paid, a.currency)}</td>
      <td class="t-right">${statusChip(k.status)}</td>
      <td class="t-right">${k.earning - k.paid > 0.009
        ? `<button class="btn btn-sm btn-ghost" onclick="Actions.payFor(${a.id}, '${esc(k.period_key)}', ${(k.earning - k.paid).toFixed(2)}, '${esc(a.currency)}')">บันทึกจ่าย</button>`
        : ''}</td>
    </tr>`).join('');

    const payoutRows = d.payouts.map((p) => `<tr>
      <td>${fmtDate(p.paid_at, true)}</td>
      <td>${esc(p.period_key || '-')}</td>
      <td class="t-right mono">${money(p.amount, p.currency)}</td>
      <td>${esc(p.method)}</td>
      <td>${esc(p.payee || '-')}</td>
      <td class="tiny muted">${esc(p.note || '')}</td>
    </tr>`).join('');

    const html = `<div class="page stack">
      <div class="card">
        <div class="card-head">
          <div>
            <h2>${esc(a.name)}</h2>
            <p>${esc(a.broker || '-')} · ${esc(a.platform || '-')} · เลขที่ ${esc(a.account_no || '-')} ·
               สกุลเงิน ${esc(a.currency)} · เริ่มเทรด ${fmtDate(a.first_trade_at, true)}</p>
          </div>
          <div class="card-tools">
            <button class="btn btn-sm btn-ghost" onclick="Actions.editRule(${a.id})">แก้เงื่อนไขส่วนแบ่ง</button>
            <a class="btn btn-sm btn-ghost" href="#/accounts">กลับไปรายการพอร์ต</a>
          </div>
        </div>
        <div class="grid g-4">
          ${stat({ label: 'ยอดเงินล่าสุด', value: money(a.balance, a.currency), tone: 'accent',
                   note: 'อัปเดต ' + fmtStamp(a.last_update) })}
          ${stat({ label: 'กำไรสะสม', html: signed(a.profit, a.currency), tone: a.profit >= 0 ? 'ok' : 'crit',
                   note: 'คิดเป็น ' + pct(a.gain_pct, 2) + ' ของเงินตั้งต้น' })}
          ${stat({ label: 'Drawdown สูงสุด', value: pct(a.drawdown_pct, 2),
                   tone: toneDrawdown(a.drawdown_pct), note: 'วัดจากจุดสูงสุดของเส้นยอดเงิน' })}
          ${stat({ label: 'ค้างจ่ายของพอร์ตนี้', value: money(a.ledger.outstanding, a.currency),
                   tone: a.ledger.outstanding > 0 ? 'warn' : 'ok',
                   note: `คิดแล้ว ${money(a.ledger.accrued)} · จ่ายแล้ว ${money(a.ledger.paid)}` })}
        </div>
      </div>

      <div class="card">
        <div class="card-head">
          <div><h2>เงื่อนไขส่วนแบ่งที่ใช้อยู่</h2><p>${esc(rule.label || 'ยังไม่ได้ตั้งเงื่อนไข')}</p></div>
        </div>
        <div class="kv-list">
          <div class="kv"><span>ส่วนแบ่งกำไร</span><strong>${rule.share_pct !== undefined ? num(rule.share_pct, 2) + '%' : '-'}</strong></div>
          <div class="kv"><span>High-Water Mark</span><strong>${rule.use_hwm ? 'เปิดใช้' : 'ไม่ใช้'}</strong></div>
          <div class="kv"><span>กำไรขั้นต่ำที่เริ่มคิด</span><strong>${money(rule.min_profit || 0, a.currency)}</strong></div>
          <div class="kv"><span>ค่าธรรมเนียมคงที่ต่อรอบ</span><strong>${money(rule.fixed_fee || 0, a.currency)}</strong></div>
          <div class="kv"><span>สถานะ</span><strong>${rule.active ? 'คิดส่วนแบ่งอยู่' : 'หยุดคิดชั่วคราว'}</strong></div>
          <div class="kv"><span>แก้ไขล่าสุด</span><strong>${fmtStamp(rule.updated_at)}</strong></div>
        </div>
      </div>

      <div class="card">
        <div class="card-head"><div><h2>เส้นยอดเงินในพอร์ต</h2><p>ย้อนหลังไม่เกิน 240 วัน</p></div></div>
        ${equityChart}
      </div>

      ${pnlChart ? `<div class="card">
        <div class="card-head"><div><h2>กำไรขาดทุนรายวัน</h2><p>45 วันทำการล่าสุด</p></div></div>
        ${pnlChart}
      </div>` : ''}

      <div class="card">
        <div class="card-head">
          <div><h2>ส่วนแบ่งรายรอบ</h2>
          <p>คอลัมน์ HWM แสดงจุดสูงสุดก่อนและหลังรอบนั้น ส่วนแบ่งคิดเฉพาะกำไรที่ทำจุดสูงสุดใหม่</p></div>
        </div>
        ${d.accruals.length ? `<div class="table-wrap"><table>
          <thead><tr>
            <th>รอบ</th><th class="t-right">กำไรในรอบ</th><th class="t-right">ฐานคิดส่วนแบ่ง</th>
            <th class="t-right">HWM ก่อน → หลัง</th><th class="t-right">อัตรา</th><th class="t-right">รายได้</th>
            <th class="t-right">จ่ายแล้ว</th><th class="t-right">สถานะ</th><th></th>
          </tr></thead>
          <tbody>${accrualRows}</tbody>
        </table></div>` : emptyBox('ยังไม่ได้คิดส่วนแบ่งของพอร์ตนี้', 'กดคิดรายได้ใหม่ที่หน้ารายได้ส่วนแบ่ง')}
      </div>

      <div class="card">
        <div class="card-head">
          <div><h2>ประวัติการจ่ายเงินของพอร์ตนี้</h2><p>${num(d.payouts.length)} รายการ</p></div>
          <div class="card-tools">
            <button class="btn btn-sm btn-primary" onclick="Actions.payFor(${a.id}, '', 0, '${esc(a.currency)}')">+ บันทึกการจ่าย</button>
          </div>
        </div>
        ${d.payouts.length ? `<div class="table-wrap"><table>
          <thead><tr><th>วันที่จ่าย</th><th>รอบ</th><th class="t-right">จำนวน</th><th>ช่องทาง</th><th>ผู้รับ</th><th>หมายเหตุ</th></tr></thead>
          <tbody>${payoutRows}</tbody>
        </table></div>` : emptyBox('ยังไม่มีการจ่ายเงินของพอร์ตนี้', '')}
      </div>
    </div>`;

    return h(html);
  }

  /* ================================================================= รายได้ */

  async function earnings(params) {
    const qs = params.period ? '?period=' + encodeURIComponent(params.period) : '';
    const d = await api.get('/api/earnings' + qs);
    const cur = d.base_currency;
    const t = d.totals;

    const rows = d.items.map((it) => `<tr>
      <td><strong>${esc(it.name)}</strong>${it.owner ? `<div class="tiny muted">${esc(it.owner)}</div>` : ''}</td>
      <td class="t-right mono">${signed(it.gross, it.currency)}</td>
      <td class="t-right mono">${money(it.base, it.currency)}</td>
      <td class="t-right mono tiny">${money(it.hwm_before)} → ${money(it.hwm_after)}</td>
      <td class="t-right mono">${num(it.share_pct, 0)}%</td>
      <td class="t-right mono"><strong>${money(it.earning, it.currency)}</strong></td>
      <td class="t-right mono">${money(it.paid, it.currency)}</td>
      <td class="t-right mono">${it.due > 0.009 ? `<span class="money-down">${money(it.due, it.currency)}</span>` : '-'}</td>
      <td class="t-right">${statusChip(it.status)}</td>
      <td class="t-right nowrap">
        ${it.due > 0.009 ? `<button class="btn btn-sm btn-ghost" onclick="Actions.payFor(${it.account_id}, '${esc(d.selected)}', ${it.due.toFixed(2)}, '${esc(it.currency)}')">บันทึกจ่าย</button>` : ''}
        <a class="btn btn-sm btn-ghost" href="#/account?id=${it.account_id}">ดูพอร์ต</a>
      </td>
    </tr>`).join('');

    const historyChart = d.history.length > 1
      ? Chart.line({
          labels: d.history.map((x) => x.label), height: 220,
          series: [{ name: 'รายได้ส่วนแบ่ง (' + cur + ')', color: Chart.colors.ok, digits: 2,
                     values: d.history.map((x) => x.earning) }],
          title: 'รายได้ส่วนแบ่งย้อนหลัง',
        })
      : emptyBox('ยังมีข้อมูลไม่พอวาดกราฟ', 'ต้องมีอย่างน้อยสองรอบ');

    const options = d.periods.map((p) =>
      `<option value="${esc(p.key)}" ${p.key === d.selected ? 'selected' : ''}>${esc(p.label)}</option>`).join('');

    const html = `<div class="page stack">
      <div class="card">
        <div class="card-head">
          <div><h2>รายได้ส่วนแบ่งรอบ ${esc(d.selected_label)}</h2>
          <p>รอบคิดส่วนแบ่งตั้งไว้แบบ${d.period_kind === 'WEEK' ? 'รายสัปดาห์' : 'รายเดือน'} · เปลี่ยนได้ที่หน้าตั้งค่า</p></div>
          <div class="card-tools">
            <select class="field-inline" onchange="MFE.go('/earnings?period=' + this.value)">${options}</select>
            <button class="btn btn-sm btn-ghost" onclick="Actions.recompute()">คิดรายได้ใหม่</button>
            <a class="btn btn-sm btn-ghost" href="/api/export?kind=earnings">ส่งออก CSV</a>
          </div>
        </div>
        <div class="grid g-4">
          ${stat({ label: 'กำไรรวมในรอบ', html: signed(t.gross), unit: cur,
                   tone: t.gross >= 0 ? 'ok' : 'crit', note: 'ผลการเทรดก่อนคิดส่วนแบ่ง' })}
          ${stat({ label: 'ฐานที่คิดส่วนแบ่งได้', value: money(t.base), unit: cur, tone: 'info',
                   note: 'เฉพาะกำไรที่ทำจุดสูงสุดใหม่' })}
          ${stat({ label: 'รายได้ส่วนแบ่ง', value: money(t.earning), unit: cur, tone: 'accent',
                   note: `${num(d.items.length)} พอร์ตในรอบนี้` })}
          ${stat({ label: 'จ่ายแล้วในรอบนี้', value: money(t.paid), unit: cur,
                   tone: t.earning - t.paid > 0 ? 'warn' : 'ok',
                   note: `ค้างอีก ${money(t.earning - t.paid)} ${esc(cur)}` })}
        </div>
      </div>

      <div class="card">
        <div class="card-head">
          <div><h2>รายละเอียดรายพอร์ต</h2>
          <p>ฐานคิดส่วนแบ่งคือกำไรส่วนที่เหนือ High-Water Mark เดิมเท่านั้น</p></div>
        </div>
        ${d.items.length ? `<div class="table-wrap"><table>
          <thead><tr>
            <th>พอร์ต</th><th class="t-right">กำไรในรอบ</th><th class="t-right">ฐานคิด</th>
            <th class="t-right">HWM ก่อน → หลัง</th><th class="t-right">อัตรา</th><th class="t-right">รายได้</th>
            <th class="t-right">จ่ายแล้ว</th><th class="t-right">ค้าง</th><th class="t-right">สถานะ</th><th></th>
          </tr></thead>
          <tbody>${rows}</tbody>
        </table></div>` : emptyBox('รอบนี้ยังไม่มีข้อมูล', 'ลองเลือกรอบอื่น หรือกดคิดรายได้ใหม่')}
      </div>

      <div class="card">
        <div class="card-head"><div><h2>แนวโน้มรายได้</h2><p>ย้อนหลังไม่เกิน 12 รอบ</p></div></div>
        ${historyChart}
      </div>
    </div>`;

    return h(html);
  }

  /* ============================================================ การจ่ายเงิน */

  async function payouts() {
    const d = await api.get('/api/payouts');
    const cur = d.base_currency;

    const dueRows = d.due.map((x) => `<tr>
      <td><strong>${esc(x.name)}</strong></td>
      <td>${esc(x.period_label)}</td>
      <td class="t-right mono">${money(x.earning, x.currency)}</td>
      <td class="t-right mono">${money(x.paid, x.currency)}</td>
      <td class="t-right mono"><strong class="money-down">${money(x.due, x.currency)}</strong></td>
      <td class="t-right">
        <button class="btn btn-sm btn-primary" onclick="Actions.payFor(${x.account_id}, '${esc(x.period_key)}', ${x.due.toFixed(2)}, '${esc(x.currency)}')">บันทึกจ่าย</button>
      </td>
    </tr>`).join('');

    const rows = d.payouts.map((p) => `<tr>
      <td>${fmtDate(p.paid_at, true)}</td>
      <td><strong>${esc(p.account_name)}</strong></td>
      <td>${esc(p.period_label)}</td>
      <td class="t-right mono">${money(p.amount, p.currency)}</td>
      <td class="t-right mono tiny muted">${money(p.amount_base, cur)}</td>
      <td>${esc(p.method)}</td>
      <td>${esc(p.payee || '-')}</td>
      <td class="tiny muted">${esc(p.note || '')}</td>
      <td class="t-right"><button class="btn btn-sm btn-danger" onclick="Actions.deletePayout(${p.id})">ลบ</button></td>
    </tr>`).join('');

    const html = `<div class="page stack">
      <div class="grid g-3">
        ${stat({ label: 'ค้างจ่ายรวม', value: money(d.total_due), unit: cur,
                 tone: d.total_due > 0 ? 'warn' : 'ok', note: `${num(d.due.length)} รอบที่ยังจ่ายไม่ครบ` })}
        ${stat({ label: 'จ่ายไปแล้วทั้งหมด', value: money(d.total_paid), unit: cur, tone: 'accent',
                 note: `${num(d.payouts.length)} รายการในสมุดจ่าย` })}
        ${stat({ label: 'สมุดจ่ายเงิน', value: num(d.payouts.length), unit: 'รายการ', tone: 'info',
                 note: 'บันทึกเองได้ ไม่ผูกกับการถอนเงินจริงของโบรก' })}
      </div>

      <div class="card">
        <div class="card-head">
          <div><h2>รอบที่ยังค้างจ่าย</h2><p>คิดส่วนแบ่งไว้แล้วแต่ยังบันทึกการจ่ายไม่ครบ</p></div>
          <div class="card-tools">
            <button class="btn btn-sm btn-primary" onclick="Actions.payFor(0, '', 0, '')">+ บันทึกการจ่าย</button>
          </div>
        </div>
        ${d.due.length ? `<div class="table-wrap"><table>
          <thead><tr><th>พอร์ต</th><th>รอบ</th><th class="t-right">รายได้</th><th class="t-right">จ่ายแล้ว</th><th class="t-right">ค้าง</th><th></th></tr></thead>
          <tbody>${dueRows}</tbody>
        </table></div>` : emptyBox('ไม่มีรายการค้างจ่าย', 'ทุกรอบที่คิดส่วนแบ่งไว้ถูกบันทึกการจ่ายครบแล้ว')}
      </div>

      <div class="card">
        <div class="card-head">
          <div><h2>สมุดจ่ายเงิน</h2><p>เรียงจากรายการล่าสุด</p></div>
          <div class="card-tools"><a class="btn btn-ghost btn-sm" href="/api/export?kind=payouts">ส่งออก CSV</a></div>
        </div>
        ${d.payouts.length ? `<div class="table-wrap"><table>
          <thead><tr>
            <th>วันที่จ่าย</th><th>พอร์ต</th><th>รอบ</th><th class="t-right">จำนวน</th>
            <th class="t-right">เทียบ ${esc(cur)}</th><th>ช่องทาง</th><th>ผู้รับ</th><th>หมายเหตุ</th><th></th>
          </tr></thead>
          <tbody>${rows}</tbody>
        </table></div>` : emptyBox('ยังไม่มีการจ่ายเงิน', 'กดปุ่มบันทึกการจ่ายเมื่อโอนเงินให้ผู้รับแล้ว')}
      </div>
    </div>`;

    return h(html);
  }

  /* ================================================================ เป้าหมาย */

  async function goals() {
    const d = await api.get('/api/goals');
    const cur = d.base_currency;
    const current = d.items.find((x) => x.period_key === d.current) || null;

    const rows = d.items.map((g) => {
      const tone = g.target > 0 ? toneGoal(g.pct, 100) : 'mute';
      return `<tr class="${g.period_key === d.current ? 'is-current' : ''}">
        <td><strong>${esc(g.label)}</strong>${g.period_key === d.current ? '<span class="chip chip-accent">รอบปัจจุบัน</span>' : ''}</td>
        <td class="t-right mono">${g.target > 0 ? money(g.target, cur) : '-'}</td>
        <td class="t-right mono">${money(g.actual, cur)}</td>
        <td class="t-right mono">${g.target > 0 ? signed(g.diff, cur) : '-'}</td>
        <td style="min-width:160px">
          ${g.target > 0
            ? `<div class="meter ${tone}"><span style="width:${Math.min(100, Math.max(0, g.pct || 0))}%"></span></div>
               <span class="tiny muted">${pct(g.pct)}</span>`
            : '<span class="tiny muted">ยังไม่ตั้งเป้า</span>'}
        </td>
        <td class="tiny muted">${esc(g.note || '')}</td>
        <td class="t-right"><button class="btn btn-sm btn-ghost" onclick="Actions.editGoal('${esc(g.period_key)}', ${g.target}, '${esc(g.note || '')}')">ตั้งเป้า</button></td>
      </tr>`;
    }).join('');

    const html = `<div class="page stack">
      <div class="grid g-2-1">
        <div class="card">
          <div class="card-head">
            <div><h2>เป้าหมายรายได้แต่ละรอบ</h2><p>เป้าหมายเป็นสกุล ${esc(cur)} เทียบกับรายได้ส่วนแบ่งที่คิดได้จริง</p></div>
            <div class="card-tools">
              <button class="btn btn-sm btn-primary" onclick="Actions.editGoal('${esc(d.current)}', 0, '')">ตั้งเป้ารอบปัจจุบัน</button>
            </div>
          </div>
          ${d.items.length ? `<div class="table-wrap"><table>
            <thead><tr><th>รอบ</th><th class="t-right">เป้าหมาย</th><th class="t-right">ทำได้จริง</th>
            <th class="t-right">ส่วนต่าง</th><th>ความคืบหน้า</th><th>หมายเหตุ</th><th></th></tr></thead>
            <tbody>${rows}</tbody>
          </table></div>` : emptyBox('ยังไม่มีรอบให้ตั้งเป้า', 'ซิงก์ข้อมูลแล้วคิดรายได้ก่อน')}
        </div>

        <div class="card">
          <div class="card-head"><div><h2>รอบปัจจุบัน</h2><p>${esc(current ? current.label : '-')}</p></div></div>
          <div class="gauge-wrap">
            ${Chart.gauge(current && current.target > 0 ? Math.min(100, current.pct) : 0,
                          { label: 'ความคืบหน้าเทียบเป้าหมาย', digits: 1 })}
          </div>
          <div class="kv-list">
            <div class="kv"><span>เป้าหมาย</span><strong>${current && current.target > 0 ? money(current.target, cur) : 'ยังไม่ตั้ง'}</strong></div>
            <div class="kv"><span>ทำได้แล้ว</span><strong>${money(current ? current.actual : 0, cur)}</strong></div>
            <div class="kv"><span>ส่วนต่าง</span><strong>${current && current.target > 0 ? signed(current.diff, cur) : '-'}</strong></div>
          </div>
        </div>
      </div>
    </div>`;

    return h(html);
  }

  /* =============================================================== เชื่อมต่อ */

  async function connect() {
    const d = await api.get('/api/connect');
    const s = d.settings;

    const logRows = d.logs.map((l) => `<div class="log-item">
      <span class="log-dot ${l.ok ? 'ok' : 'crit'}"></span>
      <div class="log-text">
        <strong>${l.ok ? 'ซิงก์สำเร็จ' : 'ซิงก์ไม่สำเร็จ'} · ${esc(l.mode === 'DEMO' ? 'โหมดสาธิต' : 'ข้อมูลจริง')}</strong>
        <p>${esc(l.detail || '-')}${l.ok ? ` · ${num(l.accounts_n)} พอร์ต ${num(l.days_n)} วัน` : ''}</p>
      </div>
      <span class="log-time">${fmtStamp(l.finished_at || l.started_at)}</span>
    </div>`).join('');

    const rateRows = d.rates.map((r) => `<tr>
      <td class="mono"><strong>${esc(r.code)}</strong></td>
      <td class="t-right mono">${num(r.to_usd, 6)}</td>
      <td class="tiny muted">${fmtStamp(r.updated_at)}</td>
      <td class="t-right"><button class="btn btn-sm btn-ghost" onclick="Actions.editRate('${esc(r.code)}', ${r.to_usd})">แก้ไข</button></td>
    </tr>`).join('');

    const html = `<div class="page stack">
      <div class="grid g-2">
        <div class="card">
          <div class="card-head">
            <div><h2>การเชื่อมต่อ Myfxbook</h2>
            <p>รหัสผ่านไม่ถูกบันทึกลงเครื่อง ระบบเก็บเฉพาะ session ที่ Myfxbook ส่งกลับมา</p></div>
          </div>
          <div class="kv-list">
            <div class="kv"><span>โหมดการทำงาน</span><strong>${d.demo_mode ? 'โหมดสาธิต' : 'ข้อมูลจริงจาก Myfxbook'}</strong></div>
            <div class="kv"><span>สถานะการเข้าสู่ระบบ</span><strong>${d.connected ? 'เชื่อมต่อแล้ว' : 'ยังไม่ได้เข้าสู่ระบบ'}</strong></div>
            <div class="kv"><span>บัญชีที่ใช้</span><strong>${esc(d.email || '-')}</strong></div>
            <div class="kv"><span>เข้าสู่ระบบเมื่อ</span><strong>${fmtStamp(d.session_at)}</strong></div>
            <div class="kv"><span>ซิงก์ล่าสุด</span><strong>${fmtStamp(d.last_sync_at)}</strong></div>
            <div class="kv"><span>พอร์ตในระบบ</span><strong>${num(d.accounts_total)} พอร์ต (ติดตาม ${num(d.accounts_tracked)})</strong></div>
          </div>
          <div class="pill-row" style="margin-top:14px">
            ${d.connected
              ? `<button class="btn btn-ghost" onclick="Actions.logout()">ออกจากระบบ Myfxbook</button>`
              : `<button class="btn btn-primary" onclick="Actions.login()">เข้าสู่ระบบ Myfxbook</button>`}
            <button class="btn btn-ghost" onclick="Actions.setDemo(${d.demo_mode ? 'false' : 'true'})">
              ${d.demo_mode ? 'เปลี่ยนไปใช้ข้อมูลจริง' : 'กลับไปโหมดสาธิต'}
            </button>
            <button class="btn btn-primary" onclick="Actions.syncNow()">ซิงก์ข้อมูลเดี๋ยวนี้</button>
          </div>
          ${!d.demo_mode && !d.connected
            ? `<p class="alert-hint">อยู่ในโหมดข้อมูลจริงแต่ยังไม่ได้เข้าสู่ระบบ การซิงก์จะยังทำไม่ได้</p>` : ''}
        </div>

        <div class="card">
          <div class="card-head"><div><h2>ตั้งค่าระบบ</h2><p>มีผลกับการคิดรายได้และการแจ้งเตือนทั้งหมด</p></div></div>
          <div class="form-grid">
            <label class="field"><span>สกุลเงินกลางที่ใช้สรุปยอด</span>
              <input name="base_currency" value="${esc(s.base_currency)}" maxlength="5"></label>
            <label class="field"><span>รอบคิดส่วนแบ่ง</span>
              <select name="period_kind">
                <option value="MONTH" ${s.period_kind === 'MONTH' ? 'selected' : ''}>รายเดือน</option>
                <option value="WEEK" ${s.period_kind === 'WEEK' ? 'selected' : ''}>รายสัปดาห์</option>
              </select></label>
            <label class="field"><span>ส่วนแบ่งเริ่มต้นของพอร์ตใหม่ (%)</span>
              <input name="default_share_pct" type="number" step="0.5" min="0" max="100" value="${esc(s.default_share_pct)}"></label>
            <label class="field"><span>เตือนเมื่อ Drawdown เกิน (%)</span>
              <input name="dd_warn_pct" type="number" step="1" min="0" max="100" value="${esc(s.dd_warn_pct)}"></label>
            <label class="field"><span>เตือนระดับวิกฤตเมื่อเกิน (%)</span>
              <input name="dd_crit_pct" type="number" step="1" min="0" max="100" value="${esc(s.dd_crit_pct)}"></label>
            <label class="field"><span>เตือนเมื่อไม่ได้ซิงก์เกิน (ชั่วโมง)</span>
              <input name="stale_sync_hours" type="number" step="1" min="1" max="720" value="${esc(s.stale_sync_hours)}"></label>
          </div>
          <label class="check" style="margin-top:10px">
            <input type="checkbox" name="default_hwm" ${s.default_hwm === '1' ? 'checked' : ''}>
            <span>พอร์ตใหม่ให้ใช้ High-Water Mark โดยอัตโนมัติ</span>
          </label>
          <div class="pill-row" style="margin-top:14px">
            <button class="btn btn-primary" onclick="Actions.saveSettings(this)">บันทึกการตั้งค่า</button>
            <span class="tiny muted">เปลี่ยนรอบคิดส่วนแบ่งแล้วระบบจะคิดรายได้ใหม่ให้ทั้งหมด</span>
          </div>
        </div>
      </div>

      <div class="grid g-2">
        <div class="card">
          <div class="card-head">
            <div><h2>อัตราแลกเปลี่ยน</h2><p>ใช้แปลงยอดของพอร์ตต่างสกุลให้รวมกันได้ ค่าเทียบเป็น 1 หน่วย → USD</p></div>
            <div class="card-tools"><button class="btn btn-sm btn-ghost" onclick="Actions.editRate('', 0)">+ เพิ่มสกุลเงิน</button></div>
          </div>
          <div class="table-wrap"><table>
            <thead><tr><th>สกุลเงิน</th><th class="t-right">เทียบ USD</th><th>อัปเดตเมื่อ</th><th></th></tr></thead>
            <tbody>${rateRows}</tbody>
          </table></div>
        </div>

        <div class="card">
          <div class="card-head"><div><h2>ประวัติการซิงก์</h2><p>12 ครั้งล่าสุด</p></div></div>
          ${d.logs.length ? `<div class="timeline-log">${logRows}</div>` : emptyBox('ยังไม่เคยซิงก์', '')}
        </div>
      </div>
    </div>`;

    return h(html);
  }


  /* ========================================================= ศูนย์วิเคราะห์ */

  function metricRow(label, value, hint) {
    return `<div class="kv"><span>${esc(label)}${hint ? `<i class="hint" title="${esc(hint)}">?</i>` : ''}</span>
      <strong>${value}</strong></div>`;
  }

  function gradeChip(health) {
    if (health.score === null) return '<span class="chip chip-mute">ข้อมูลไม่พอ</span>';
    return `<span class="chip chip-${health.tone}"><i class="dot"></i>${health.score} · ${esc(health.grade)}</span>`;
  }

  async function intel() {
    const d = await api.get('/api/intelligence');
    const cur = d.base_currency;
    const f = d.forecast;

    /* ---- กราฟพัด: ช่วงที่รายได้น่าจะไปจบ ---- */
    let fanChart;
    if (f.enough && f.fan.length > 1) {
      const labels = f.fan.map((x) => (x.d === 0 ? 'วันนี้' : '+' + x.d));
      fanChart = Chart.line({
        labels, height: 260,
        series: [
          { name: 'ดีกว่าคาด (P90)', color: Chart.colors.ok, digits: 2, dashed: true,
            points: false, values: f.fan.map((x) => x.p90) },
          { name: 'ค่ากลาง (P50)', color: Chart.colors.accent, digits: 2, area: true,
            points: false, values: f.fan.map((x) => x.p50) },
          { name: 'แย่กว่าคาด (P10)', color: Chart.colors.crit, digits: 2, dashed: true,
            points: false, values: f.fan.map((x) => x.p10) },
        ],
        title: 'ช่วงรายได้ที่เป็นไปได้ถึงสิ้นรอบ',
      });
    } else {
      fanChart = emptyBox('ยังพยากรณ์ไม่ได้', f.reason || 'ต้องมีข้อมูลรายวันอย่างน้อย 20 วัน');
    }

    /* ---- ธงเตือนจากผลวิเคราะห์ ---- */
    const flagHtml = d.flags.length
      ? d.flags.map((fl) => `<div class="alert-item level-${fl.level === 'critical' ? 'critical' : fl.level}">
          <span class="alert-mark"></span>
          <div>
            <div class="alert-title">${esc(fl.title)}</div>
            <p class="alert-detail">${esc(fl.detail)}</p>
          </div>
          <div class="alert-actions">
            ${fl.account_id ? `<a class="btn btn-sm btn-ghost" href="#/account?id=${fl.account_id}">ดูพอร์ต</a>` : ''}
          </div>
        </div>`).join('')
      : emptyBox('ไม่พบเรื่องที่ต้องกังวล', 'ทุกพอร์ตผ่านเกณฑ์ความเสี่ยงที่ตรวจได้');

    /* ---- การ์ดรายพอร์ต ---- */
    const cards = d.accounts.map((a) => {
      const r = a.risk;
      const hd = a.hidden;
      const rec = a.recovery;
      if (!r.enough) {
        return `<div class="card">
          <div class="card-head"><div><h2>${esc(a.name)}</h2><p>มีข้อมูลเพียง ${num(r.days)} วัน</p></div></div>
          ${emptyBox('ข้อมูลยังไม่พอวิเคราะห์', 'ต้องมีอย่างน้อย 20 วันทำการ')}
        </div>`;
      }
      const hitSignals = (hd.signals || []).filter((s) => s.hit);
      return `<div class="card">
        <div class="card-head">
          <div><h2>${esc(a.name)}</h2><p>${num(r.days)} วันทำการ · สกุล ${esc(a.currency)}</p></div>
          <div class="card-tools">${gradeChip(a.health)}
            <a class="btn btn-sm btn-ghost" href="#/account?id=${a.id}">ดูพอร์ต</a></div>
        </div>

        <div class="intel-grid">
          <div>
            <p class="section-label">ผลตอบแทนต่อความเสี่ยง</p>
            <div class="kv-list">
              ${metricRow('Sharpe', r.sharpe === null ? '-' : num(r.sharpe, 2),
                          'ผลตอบแทนต่อหนึ่งหน่วยความผันผวน ยิ่งสูงยิ่งดี เกิน 1 ถือว่าใช้ได้')}
              ${metricRow('Sortino', r.sortino === null ? '-' : num(r.sortino, 2),
                          'เหมือน Sharpe แต่นับเฉพาะความผันผวนฝั่งขาดทุน')}
              ${metricRow('Calmar', r.calmar === null ? '-' : num(r.calmar, 2),
                          'ผลตอบแทนต่อปีหารด้วยขาดทุนสะสมที่ลึกที่สุด')}
              ${metricRow('ผลตอบแทนต่อปี', pct(r.annual_return_pct, 2))}
              ${metricRow('ความผันผวนต่อปี', pct(r.volatility_pct, 2))}
            </div>
          </div>
          <div>
            <p class="section-label">ความเสียหายที่ต้องรับได้</p>
            <div class="kv-list">
              ${metricRow('ขาดทุนสะสมลึกสุด', pct(r.max_dd_pct, 2))}
              ${metricRow('จมน้ำนานสุด', num(r.longest_underwater) + ' วัน',
                          'จำนวนวันทำการที่ยาวที่สุดที่พอร์ตยังไม่กลับไปแตะจุดสูงสุดเดิม')}
              ${metricRow('VaR 95% ต่อวัน', money(r.var95_money, a.currency),
                          'วันแย่ระดับ 1 ใน 20 คาดว่าจะเสียประมาณเท่านี้')}
              ${metricRow('ถ้าแย่กว่านั้น', money(r.cvar95_money, a.currency),
                          'ค่าเฉลี่ยของวันที่แย่กว่า VaR หรือ Expected Shortfall')}
              ${metricRow('วันแย่ที่สุดที่เคยเจอ', `<span class="money-down">${num(r.worst_day, 2)}</span>`)}
            </div>
          </div>
          <div>
            <p class="section-label">นิสัยการเทรด</p>
            <div class="kv-list">
              ${metricRow('อัตราชนะ', pct(r.win_rate_pct, 1))}
              ${metricRow('Profit Factor', r.profit_factor === null ? '-' : num(r.profit_factor, 2),
                          'กำไรรวมหารด้วยขาดทุนรวม ต่ำกว่า 1 คือขาดทุน')}
              ${metricRow('วันชนะเฉลี่ย', `<span class="money-up">${num(r.avg_win, 2)}</span>`)}
              ${metricRow('วันแพ้เฉลี่ย', `<span class="money-down">${num(r.avg_loss, 2)}</span>`)}
              ${metricRow('ความเสี่ยงซ่อนเร้น',
                          hd.enough ? `<span class="chip chip-${hd.level}">${hd.score} / 100</span>` : '-',
                          'คะแนนจากการตรวจลายเซ็นกลยุทธ์แบบ martingale และ grid')}
            </div>
          </div>
        </div>

        ${hitSignals.length ? `<div class="signal-box">
          <p class="section-label">สัญญาณที่ตรวจพบ</p>
          ${hitSignals.map((s) => `<div class="signal"><span class="signal-dot"></span>
            <div><strong>${esc(s.label)}</strong><p>${esc(s.detail)}</p></div></div>`).join('')}
        </div>` : ''}

        ${rec.under_water ? `<div class="signal-box">
          <p class="section-label">โอกาสกลับมาสร้างรายได้</p>
          <p class="tiny muted">ต้องทำกำไรอีก ${money(rec.gap, a.currency)} จึงจะพ้นจุดสูงสุดเดิมและเริ่มคิดส่วนแบ่งได้อีกครั้ง</p>
          <div class="prob-row">
            ${[[30, rec.prob_30], [60, rec.prob_60], [90, rec.prob_90]].map(([dn, p]) => `
              <div class="prob">
                <span class="prob-label">ภายใน ${dn} วัน</span>
                <div class="meter ${p >= 60 ? 'ok' : p >= 30 ? 'warn' : 'crit'}"><span style="width:${p}%"></span></div>
                <span class="prob-value">${pct(p, 1)}</span>
              </div>`).join('')}
          </div>
          ${rec.median_days ? `<p class="tiny muted">เฉพาะเส้นทางที่กลับมาได้สำเร็จ ใช้เวลากลางประมาณ ${num(rec.median_days)} วันทำการ</p>` : ''}
        </div>` : ''}

        ${a.health.reasons.length ? `<div class="reason-list">
          ${a.health.reasons.map((x) => `<span class="reason tone-${x.tone}">${esc(x.text)}</span>`).join('')}
        </div>` : ''}
      </div>`;
    }).join('');

    const probTone = f.enough && f.prob_hit_target !== null
      ? (f.prob_hit_target >= 65 ? 'ok' : f.prob_hit_target >= 35 ? 'warn' : 'crit') : 'info';

    const html = `<div class="page stack">
      <div class="card">
        <div class="card-head">
          <div><h2>พยากรณ์รายได้สิ้นรอบ ${esc(f.period_label || '')}</h2>
          <p>${f.enough
              ? `จำลอง ${num(f.runs)} เส้นทางจากผลตอบแทนจริงของ ${num(f.accounts_n)} พอร์ต ·
                 เหลืออีก ${num(f.days_left)} วันทำการ · ทุกเส้นทางคิดผ่านกติกา High-Water Mark เดิม`
              : esc(f.reason || '')}</p></div>
          <div class="card-tools">
            <button class="btn btn-sm btn-ghost" onclick="Actions.refreshIntel(this)">คำนวณใหม่</button>
          </div>
        </div>
        ${f.enough ? `<div class="grid g-4">
          ${stat({ label: 'คิดได้แล้ววันนี้', value: money(f.current), unit: cur, tone: 'info',
                   note: 'ยอดนี้ยังไม่แน่นอนจนกว่าจะปิดรอบ' })}
          ${stat({ label: 'ค่ากลางที่คาดว่าจะได้', value: money(f.p50), unit: cur, tone: 'accent',
                   note: `ครึ่งหนึ่งของเส้นทางจบสูงกว่านี้ · เฉลี่ย ${money(f.mean)}` })}
          ${stat({ label: 'ช่วงที่น่าจะเกิด 80%', value: money(f.p10) + ' - ' + money(f.p90), tone: 'info', compact: true,
                   note: `แย่สุด P10 ถึงดีสุด P90 หน่วยเป็น ${esc(cur)}` })}
          ${stat({ label: 'โอกาสถึงเป้าหมาย',
                   value: f.prob_hit_target === null ? 'ยังไม่ตั้งเป้า' : pct(f.prob_hit_target, 1),
                   tone: probTone,
                   note: f.target > 0 ? `เป้า ${money(f.target)} ${esc(cur)}` : 'ตั้งเป้าได้ที่หน้าเป้าหมายรายได้',
                   meter: f.prob_hit_target === null ? undefined : f.prob_hit_target,
                   meterTone: probTone })}
        </div>` : ''}
        ${fanChart}
        ${f.enough && f.prob_below_current >= 10 ? `<p class="alert-hint">
          มีโอกาส ${pct(f.prob_below_current, 1)} ที่รายได้สิ้นรอบจะต่ำกว่ายอดที่คิดได้วันนี้
          ถ้าจ่ายตามยอดปัจจุบันไปก่อนแล้วพอร์ตขาดทุนต่อ จะจ่ายเกินเฉลี่ย ${money(f.avg_overpay, cur)}
          และต้องไปตามเก็บคืนภายหลัง</p>` : ''}
      </div>

      <div class="card">
        <div class="card-head">
          <div><h2>เรื่องที่ต้องรู้</h2><p>สรุปจากการวิเคราะห์ เรียงตามความรุนแรง</p></div>
        </div>
        ${flagHtml}
      </div>

      ${cards}
    </div>`;

    return h(html);
  }


  /* ======================================================= เครื่องหาเงิน */

  const EFFORT_CHIP = {
    'ทำได้ทันที': 'chip-ok',
    'ต้องเจรจา': 'chip-warn',
    'ต้องตกลงกับเจ้าของเงิน': 'chip-warn',
    'แก้ได้เอง แต่ควรบอกเจ้าของเงิน': 'chip-info',
    'ต้องตัดสินใจ': 'chip-crit',
    'ควรทบทวน': 'chip-warn',
  };

  async function revenue(params) {
    const qs = params.target ? '?target=' + encodeURIComponent(params.target) : '';
    const d = await api.get('/api/revenue' + qs);
    const cur = d.base_currency;
    const opp = d.opportunities;
    const rec = d.receivables;
    const cap = d.capital;

    /* ---- รายการโอกาส คือพระเอกของหน้านี้ ---- */
    const oppHtml = opp.items.length
      ? opp.items.map((o) => `<div class="opp">
          <div class="opp-amount ${o.amount > 0 ? '' : 'is-none'}">
            ${o.amount > 0 ? money(o.amount) : '-'}
            ${o.amount > 0 ? `<span class="opp-unit">${esc(cur)}</span>` : ''}
          </div>
          <div class="opp-body">
            <div class="opp-head">
              <strong>${esc(o.title)}</strong>
              <span class="chip ${EFFORT_CHIP[o.effort] || 'chip-mute'}">${esc(o.effort)}</span>
            </div>
            <p>${esc(o.detail)}</p>
          </div>
          <div class="opp-go"><a class="btn btn-sm btn-ghost" href="#${esc(o.route)}">ไปจัดการ</a></div>
        </div>`).join('')
      : emptyBox('ยังไม่พบเงินที่ตกหล่น', 'เก็บครบ เงื่อนไขเหมาะสม และทุกพอร์ตสร้างรายได้อยู่');

    /* ---- เงินค้างเก็บแยกตามอายุ ---- */
    const agingBars = rec.buckets.some((b) => b.total > 0)
      ? Chart.hbars(rec.buckets.map((b) => ({
          label: b.label, value: b.total, digits: 2, unit: ' ' + cur,
          display: money(b.total) + ' · ' + b.count + ' รอบ',
        })), { title: 'เงินค้างเก็บแยกตามอายุ', labelW: 96, valueW: 118 })
      : emptyBox('ไม่มีเงินค้างเก็บ', 'เก็บครบทุกรอบแล้ว');

    const recRows = rec.items.slice(0, 12).map((i) => `<tr>
      <td><strong>${esc(i.name)}</strong></td>
      <td>${esc(i.period_label)}</td>
      <td class="t-right mono">${money(i.outstanding, i.currency)}</td>
      <td class="t-right">
        <span class="chip ${i.age_days > 90 ? 'chip-crit' : i.age_days > 30 ? 'chip-warn' : 'chip-mute'}">
          ${num(i.age_days)} วัน</span>
      </td>
      <td class="t-right">
        <button class="btn btn-sm btn-primary"
          onclick="Actions.payFor(${i.account_id}, '${esc(i.period_key)}', ${i.outstanding.toFixed(2)}, '${esc(i.currency)}')">
          บันทึกเก็บแล้ว</button>
      </td>
    </tr>`).join('');

    /* ---- ประสิทธิภาพรายพอร์ต ---- */
    const effRows = d.efficiency.map((e) => `<tr>
      <td><strong>${esc(e.name)}</strong><div class="tiny muted">มีข้อมูล ${num(e.months, 1)} เดือน</div></td>
      <td class="t-right mono">${money(e.balance_base)}</td>
      <td class="t-right mono">${money(e.earned_base)}</td>
      <td class="t-right mono">${e.per_month === null ? '-' : money(e.per_month)}</td>
      <td class="t-right mono">${e.yield_per_1k === null ? '-' : num(e.yield_per_1k, 2)}</td>
      <td class="t-right mono">${e.earn_per_risk === null ? '-'
          : `<span class="${e.earn_per_risk < 1 ? 'money-down' : ''}">${num(e.earn_per_risk, 2)}</span>`}</td>
      <td class="t-right">${ddChip(e.drawdown_pct)}</td>
    </tr>`).join('');

    /* ---- เปรียบเทียบรอบเก็บเงิน ---- */
    const bill = d.billing;
    const billBetter = bill.better === 'WEEK' ? 'รายสัปดาห์' : 'รายเดือน';
    const billCurrent = bill.current_kind === 'WEEK' ? 'รายสัปดาห์' : 'รายเดือน';

    const html = `<div class="page stack">
      <div class="grid g-4">
        ${stat({ label: 'เก็บได้ทันที ไม่ต้องเจรจา', value: money(opp.total_now), unit: cur,
                 tone: opp.total_now > 0 ? 'ok' : 'info',
                 note: 'เงินที่คิดส่วนแบ่งไว้แล้วและยังไม่ได้เก็บ' })}
        ${stat({ label: 'ได้เพิ่มถ้าเจรจาสำเร็จ', value: money(opp.total_negotiable), unit: cur,
                 tone: 'warn', note: 'ต้องคุยกับเจ้าของเงินก่อน ไม่ใช่เปลี่ยนเองได้' })}
        ${stat({ label: 'รายได้ต่อเดือนตอนนี้',
                 value: cap.enough ? money(cap.current_monthly) : '-', unit: cur, tone: 'accent',
                 note: cap.enough ? `จากทุนที่บริหารอยู่ ${money(cap.current_capital)} ${esc(cur)}` : '' })}
        ${stat({ label: 'ทุนที่ต้องเพิ่มเพื่อถึงเป้า',
                 value: cap.enough && cap.capital_gap !== null
                        ? (cap.capital_gap > 0 ? money(cap.capital_gap) : 'ถึงแล้ว') : '-',
                 unit: cap.enough && cap.capital_gap > 0 ? cur : '',
                 tone: cap.enough && cap.capital_gap > 0 ? 'warn' : 'ok',
                 note: cap.enough ? `เป้า ${money(cap.target_monthly)} ${esc(cur)} ต่อเดือน` : '' })}
      </div>

      <div class="card">
        <div class="card-head">
          <div><h2>เงินที่ทิ้งไว้บนโต๊ะ</h2>
          <p>เรียงตามจำนวนเงิน คิดจากข้อมูลจริงในระบบทั้งหมด ไม่ใช่การคาดเดา</p></div>
        </div>
        ${oppHtml}
        <p class="alert-hint">อัตราส่วนแบ่งและรอบเก็บเงินเป็นเงื่อนไขในสัญญา
          ตัวเลขในหน้านี้มีไว้ใช้เป็นข้อมูลประกอบการเจรจากับเจ้าของเงิน
          การเปลี่ยนโดยไม่บอกเจ้าของเงินคือการผิดสัญญา</p>
      </div>

      <div class="grid g-2-1">
        <div class="card">
          <div class="card-head">
            <div><h2>เงินค้างเก็บ</h2>
            <p>รวม ${money(rec.total, cur)} · เกิน 30 วัน ${money(rec.overdue_total, cur)}
               · ค้างนานสุด ${num(rec.oldest_days)} วัน</p></div>
            <div class="card-tools"><a class="btn btn-sm btn-ghost" href="#/payouts">ไปหน้าจ่ายเงิน</a></div>
          </div>
          ${rec.items.length ? `<div class="table-wrap"><table>
            <thead><tr><th>พอร์ต</th><th>รอบ</th><th class="t-right">ค้าง</th>
            <th class="t-right">อายุหนี้</th><th></th></tr></thead>
            <tbody>${recRows}</tbody>
          </table></div>
          ${rec.items.length > 12 ? `<p class="tiny muted">แสดง 12 รายการแรกจากทั้งหมด ${num(rec.items.length)} รายการ</p>` : ''}`
          : emptyBox('ไม่มีเงินค้างเก็บ', 'เก็บครบทุกรอบแล้ว')}
        </div>

        <div class="card">
          <div class="card-head"><div><h2>อายุหนี้</h2><p>ยิ่งเก่ายิ่งเก็บยาก</p></div></div>
          ${agingBars}
        </div>
      </div>

      <div class="card">
        <div class="card-head">
          <div><h2>พอร์ตไหนคุ้มที่จะทุ่มเวลาให้</h2>
          <p>รายได้ต่อทุนหนึ่งพันหน่วยต่อเดือน และรายได้ต่อหนึ่งหน่วยความเสี่ยงที่ต้องแบก</p></div>
        </div>
        <div class="table-wrap"><table>
          <thead><tr>
            <th>พอร์ต</th><th class="t-right">ทุน (${esc(cur)})</th><th class="t-right">รายได้สะสม</th>
            <th class="t-right">ต่อเดือน</th><th class="t-right">ต่อทุน 1,000</th>
            <th class="t-right">ต่อความเสี่ยง</th><th class="t-right">Drawdown</th>
          </tr></thead>
          <tbody>${effRows}</tbody>
        </table></div>
        <p class="tiny muted">คอลัมน์ต่อความเสี่ยงคือรายได้ต่อเดือนหารด้วยเปอร์เซ็นต์ขาดทุนสะสมที่ลึกที่สุด
          ค่าต่ำแปลว่าได้เงินน้อยเมื่อเทียบกับความเสียหายที่เคยต้องรับ</p>
      </div>

      <div class="grid g-2">
        <div class="card">
          <div class="card-head">
            <div><h2>อยากได้เท่านี้ต่อเดือน ต้องมีทุนเท่าไร</h2>
            <p>คิดจากผลงานจริงของพอร์ตที่มีอยู่ ไม่ใช่ตัวเลขในฝัน</p></div>
          </div>
          ${cap.enough ? `
          <div class="form-grid">
            <label class="field"><span>อยากได้ต่อเดือน (${esc(cur)})</span>
              <input id="capTarget" type="number" step="100" min="0" value="${cap.target_monthly}"></label>
            <div class="field"><span>&nbsp;</span>
              <button class="btn btn-primary" onclick="Actions.planCapital()">คำนวณ</button></div>
          </div>
          <div class="kv-list" style="margin-top:12px">
            <div class="kv"><span>ตามผลงานค่ากลาง</span><strong>${money(cap.capital_median, cur)}</strong></div>
            <div class="kv"><span>ถ้าผลงานเท่าพอร์ตที่ดีที่สุด</span><strong>${money(cap.capital_optimistic, cur)}</strong></div>
            <div class="kv"><span>ถ้าผลงานเท่าพอร์ตที่แย่ที่สุด</span><strong>${money(cap.capital_pessimistic, cur)}</strong></div>
            <div class="kv"><span>ทุนที่บริหารอยู่ตอนนี้</span><strong>${money(cap.current_capital, cur)}</strong></div>
            <div class="kv"><span>ต้องระดมเพิ่ม</span><strong>${cap.capital_gap > 0
                ? `<span class="money-down">${money(cap.capital_gap, cur)}</span>`
                : '<span class="money-up">ถึงแล้ว</span>'}</strong></div>
          </div>
          <p class="tiny muted">ฐานคิด: พอร์ตที่มีอยู่สร้างรายได้ส่วนแบ่งเฉลี่ย
            ${num(cap.median_yield_per_1k, 2)} ${esc(cur)} ต่อทุน 1,000 ${esc(cur)} ต่อเดือน
            จาก ${num(cap.accounts_n)} พอร์ต ตัวเลขนี้ไม่ใช่การรับประกัน
            ผลงานในอดีตไม่ได้บอกว่าอนาคตจะเป็นแบบเดียวกัน</p>
          ` : emptyBox('ข้อมูลยังไม่พอวางแผน', 'ต้องมีพอร์ตที่เคยสร้างรายได้อย่างน้อยหนึ่งพอร์ต')}
        </div>

        <div class="card">
          <div class="card-head">
            <div><h2>รอบเก็บเงินและความเป็นธรรม</h2><p>ผลย้อนหลังจริงจากข้อมูลทั้งหมดที่มี</p></div>
          </div>
          <div class="kv-list">
            <div class="kv"><span>เก็บรายเดือน</span><strong>${money(bill.monthly, cur)}</strong></div>
            <div class="kv"><span>เก็บรายสัปดาห์</span><strong>${money(bill.weekly, cur)}</strong></div>
            <div class="kv"><span>ตอนนี้ใช้รอบ</span><strong>${billCurrent}</strong></div>
            <div class="kv"><span>รอบที่ให้มากกว่า</span><strong>${billBetter}</strong></div>
          </div>
          ${bill.gain > 0
            ? `<p class="alert-hint">เปลี่ยนเป็นรอบ${billBetter}จะเก็บได้เพิ่ม ${money(bill.gain, cur)}
               จากข้อมูลย้อนหลัง แต่เป็นเงื่อนไขในสัญญาที่ต้องตกลงกับเจ้าของเงินก่อน</p>`
            : `<p class="alert-hint">รอบที่ใช้อยู่ให้ผลดีที่สุดแล้วสำหรับข้อมูลชุดนี้ ไม่ต้องเปลี่ยน</p>`}

          <div class="fair-box">
            <p class="section-label">ต้นทุนของความเป็นธรรม</p>
            <p class="tiny">การใช้ High-Water Mark ทำให้เก็บได้น้อยลง
              <strong class="money-down">${money(d.drag.hwm_cost, cur)}</strong>
              เมื่อเทียบกับการคิดส่วนแบ่งทุกรอบที่มีกำไร</p>
            <p class="tiny muted">นี่ไม่ใช่เงินที่หายไป แต่คือเงินที่เจ้าของพอร์ตไม่ต้องจ่ายซ้ำสำหรับกำไรก้อนเดิม
              ใช้เป็นจุดขายตอนเสนองานได้ เพราะผู้จัดการพอร์ตจำนวนมากไม่ให้ข้อนี้</p>
          </div>
        </div>
      </div>
    </div>`;

    return h(html);
  }

  /* =============================================================== แจ้งเตือน */

  async function alerts() {
    const d = await api.get('/api/alerts');
    const items = d.items.map((a) => `<div class="alert-item level-${a.level} ${a.acked ? 'is-acked' : ''}">
      <span class="alert-mark"></span>
      <div>
        <div class="alert-title">${esc(a.title)}</div>
        <p class="alert-detail">${esc(a.detail)}</p>
        ${a.acked ? `<p class="alert-hint">รับทราบแล้วโดย ${esc(a.acked_by)}</p>` : ''}
      </div>
      <div class="alert-actions">
        <a class="btn btn-sm btn-ghost" href="#${esc(a.route)}">ไปที่หน้าเกี่ยวข้อง</a>
        ${a.acked
          ? `<button class="btn btn-sm btn-ghost" onclick="Actions.unackAlert('${esc(a.key)}')">ยกเลิกรับทราบ</button>`
          : `<button class="btn btn-sm btn-primary" onclick="Actions.ackAlert('${esc(a.key)}')">รับทราบ</button>`}
      </div>
    </div>`).join('');

    const html = `<div class="page stack">
      <div class="grid g-3">
        ${stat({ label: 'เรื่องวิกฤต', value: num(d.counts.critical), unit: 'เรื่อง', tone: 'crit',
                 note: 'ต้องจัดการทันที' })}
        ${stat({ label: 'เรื่องที่ต้องเฝ้าดู', value: num(d.counts.warn), unit: 'เรื่อง', tone: 'warn',
                 note: 'ยังไม่วิกฤตแต่ควรตรวจสอบ' })}
        ${stat({ label: 'ข้อมูลแจ้งให้ทราบ', value: num(d.counts.info), unit: 'เรื่อง', tone: 'info',
                 note: 'ไม่ต้องรีบแก้ไข' })}
      </div>
      <div class="card">
        <div class="card-head"><div><h2>รายการแจ้งเตือน</h2><p>เรียงตามความสำคัญ รายการที่รับทราบแล้วจะถูกย้ายลงล่าง</p></div></div>
        ${d.items.length ? items : emptyBox('ไม่มีการแจ้งเตือน', 'ทุกพอร์ตอยู่ในเกณฑ์ที่ตั้งไว้')}
      </div>
    </div>`;

    return h(html);
  }

  return { overview, accounts, accountDetail, earnings, payouts, goals, connect, alerts, intel, revenue };
})();
