/* ==========================================================================
   FGP Production Suite - หน้าจอทั้งหมด
   แต่ละหน้าเป็นฟังก์ชัน async ที่คืนค่า DOM element หนึ่งก้อน
   ========================================================================== */

const Views = (() => {
  'use strict';

  const { api, esc, num, h, hhmm, fmtDate, fmtDayLabel, toneHigh, toneLoad, todayIso, shiftDays } = FGP;
  let REF = null; // ข้อมูลอ้างอิง: รุ่น, คน, เครื่อง

  async function reference() {
    if (!REF) REF = await api.get('/api/reference');
    return REF;
  }

  /* ------------------------------------------------------------ ชิ้นส่วนร่วม */

  function stat(o) {
    return `<div class="stat tone-${o.tone || 'accent'}">
      <div class="stat-top">
        <span class="stat-label">${esc(o.label)}</span>
        ${o.delta !== undefined && o.delta !== null ? deltaChip(o.delta, o.deltaUnit) : ''}
      </div>
      <div class="stat-value">${esc(o.value)}${o.unit ? `<span class="unit">${esc(o.unit)}</span>` : ''}</div>
      ${o.note ? `<p class="stat-note">${o.note}</p>` : ''}
      ${o.spark ? `<div class="stat-spark">${o.spark}</div>` : ''}
      ${o.meter !== undefined ? `<div class="meter ${o.meterTone || ''}" style="margin-top:10px"><span style="width:${Math.min(100, Math.max(0, o.meter))}%"></span></div>` : ''}
    </div>`;
  }

  function deltaChip(delta, unit) {
    const cls = delta > 0 ? 'up' : delta < 0 ? 'down' : 'flat';
    const sign = delta > 0 ? '▲' : delta < 0 ? '▼' : '•';
    return `<span class="delta ${cls}">${sign} ${num(Math.abs(delta), 1)}${esc(unit || '')}</span>`;
  }

  function achievementChip(v) {
    if (v === null || v === undefined) return '<span class="chip chip-mute">ยังไม่มีผล</span>';
    const t = toneHigh(v, 98, 90);
    return `<span class="chip chip-${t}"><i class="dot"></i>${num(v, 1)}%</span>`;
  }

  function riskChip(job) {
    if (job.risk === 'LATE') return '<span class="chip chip-crit"><i class="dot"></i>เสี่ยงเลยกำหนด</span>';
    if (job.risk === 'WATCH') return '<span class="chip chip-warn"><i class="dot"></i>ต้องเฝ้าดู</span>';
    return '<span class="chip chip-ok"><i class="dot"></i>ตามแผน</span>';
  }

  function stageRail(idx, count) {
    let out = '<div class="stage-rail">';
    for (let i = 0; i < count; i++) {
      const cls = i < idx ? 'done' : i === idx ? 'current' : '';
      out += `<span class="stage-node ${cls}"></span>`;
    }
    return out + '</div>';
  }

  function emptyBox(title, detail) {
    return `<div class="empty"><strong>${esc(title)}</strong>${esc(detail || '')}</div>`;
  }

  /** การ์ด % Achievement ที่นับเฉพาะกะที่เริ่มผลิตแล้ว ช่วงที่เป็นแผนล่วงหน้าจึงไม่ขึ้น 0% */
  function gapAware(s) {
    if (!s.shifts_started) {
      return stat({
        label: '% Achievement', value: 'ยังไม่มีผล', tone: 'info',
        note: 'ช่วงนี้เป็นแผนล่วงหน้า ยังไม่มีกะไหนผลิต',
      });
    }
    const v = s.achievement_started;
    return stat({
      label: '% Achievement', value: num(v, 1), unit: '%',
      tone: toneHigh(v, 98, 90), meter: v, meterTone: toneHigh(v, 98, 90),
      note: `นับเฉพาะ ${s.shifts_started} จาก ${s.shifts_total} กะที่เริ่มแล้ว`,
    });
  }

  /* ================================================================ ภาพรวม */

  async function overview() {
    const d = await api.get('/api/overview');
    const c = d.cards;
    const kpiOut = d.kpi_series.map((s) => s.output);
    const kpiOee = d.kpi_series.map((s) => s.oee);

    const alertStrip = d.alerts.length
      ? `<div class="card" style="padding:14px">
          <div class="card-head" style="margin-bottom:10px">
            <div><h2>เรื่องที่ต้องตัดสินใจวันนี้</h2>
            <p>ระบบอ่านจากข้อมูลจริงในระบบ ไม่ใช่ค่าที่ตั้งไว้ล่วงหน้า</p></div>
            <a class="btn btn-sm btn-ghost" href="#/alerts">ดูทั้งหมด ${d.alert_counts.critical + d.alert_counts.warn + d.alert_counts.info} เรื่อง</a>
          </div>
          <div class="stack" style="gap:9px">${d.alerts.map(alertRow).join('')}</div>
        </div>`
      : `<div class="card">${emptyBox('ไม่มีเรื่องเร่งด่วน', 'ทุกอย่างอยู่ในเกณฑ์ที่ตั้งไว้')}</div>`;

    const html = `<div class="page stack">

      <div class="grid g-6">
        ${stat({
          label: 'ผลผลิตวันนี้', value: num(c.output_today), unit: 'ชิ้น', tone: 'accent',
          note: `แผนทั้งวัน ${num(c.plan_today)} ชิ้น`,
          meter: c.plan_today ? (c.output_today / c.plan_today) * 100 : 0,
          meterTone: 'ok',
        })}
        ${stat({
          label: '% ทำได้เทียบแผน', value: num(c.achievement_today, 1), unit: '%',
          tone: toneHigh(c.achievement_today, 95, 80),
          note: `นับเฉพาะ ${c.shifts_started} จาก ${c.shifts_total} กะที่เริ่มแล้ว`,
        })}
        ${stat({
          label: 'งานที่ยังไม่ปิด', value: num(c.wip_open), unit: 'ใบ',
          tone: c.wip_late ? 'crit' : 'info',
          note: `เสี่ยงเลยกำหนด ${num(c.wip_late)} ใบ`,
        })}
        ${stat({
          label: 'Chamber ถูกใช้ไป', value: num(c.chamber_util, 0), unit: '%',
          tone: toneLoad(c.chamber_util),
          note: `เหลือว่างอีก ${num(c.chamber_free, 1)} ชั่วโมง`,
          meter: c.chamber_util, meterTone: toneLoad(c.chamber_util),
        })}
        ${stat({
          label: 'OEE วันนี้', value: num(c.oee, 1), unit: '%',
          tone: toneHigh(c.oee, 75, 60),
          spark: Chart.spark(kpiOee, { color: 'var(--accent)' }),
        })}
        ${stat({
          label: 'ภาระงานเฉลี่ยของคน', value: num(c.avg_load, 0), unit: '%',
          tone: toneLoad(c.avg_load, 70, 110),
          note: `งานล้น ${c.over_people} คน · ว่าง ${c.free_people} คน`,
        })}
      </div>

      ${alertStrip}

      <div class="grid g-2-1">
        <div class="card">
          <div class="card-head">
            <div><h2>แผนผลิตเทียบผลจริง 7 วันหลังสุด</h2>
            <p>แท่งจางคือแผน แท่งทึบคือของที่ทำได้จริง</p></div>
            <a class="btn btn-sm btn-ghost" href="#/plan">เปิดหน้าแผนผลิต</a>
          </div>
          ${Chart.columns({
            labels: d.trend.map((t) => fmtDayLabel(t.date)),
            plan: d.trend.map((t) => t.plan),
            actual: d.trend.map((t) => t.actual),
            height: 250,
          })}
        </div>

        <div class="card">
          <div class="card-head"><div><h2>งานค้างตามขั้นตอน</h2><p>รวม ${num(c.wip_open)} ใบที่ยังเดินอยู่</p></div></div>
          <div style="display:grid;place-items:center;padding:4px 0 12px">
            ${Chart.donut(
              d.lanes.map((l, i) => ({
                label: l.stage, value: l.count,
                color: ['var(--accent)', 'var(--info)', 'var(--warn)', 'var(--ok)', 'var(--crit)'][i % 5],
              })),
              { center: num(c.wip_open), centerLabel: 'ใบงาน' }
            )}
          </div>
          <div class="stack" style="gap:6px">
            ${d.lanes.map((l, i) => `<div class="kv">
              <span><i class="dot" style="display:inline-block;margin-right:7px;background:${['var(--accent)', 'var(--info)', 'var(--warn)', 'var(--ok)', 'var(--crit)'][i % 5]}"></i>${esc(l.stage)}</span>
              <span>${num(l.count)}${l.late ? ` <span style="color:var(--crit)">· ช้า ${l.late}</span>` : ''}</span>
            </div>`).join('')}
          </div>
        </div>
      </div>

      <div class="grid g-3">
        <div class="card">
          <div class="card-head"><div><h3>การใช้เครื่องวันนี้</h3><p>คิดจากเวลาเปิดให้จองจริง</p></div></div>
          ${Chart.hbars(d.machine_types.map((t) => ({
            label: t.label, value: t.utilization, unit: '%',
            color: t.utilization >= 92 ? 'var(--crit)' : t.utilization >= 80 ? 'var(--warn)' : 'var(--ok)',
          })), { labelW: 96, max: 100 })}
          <a class="btn btn-sm btn-ghost" href="#/capacity" style="margin-top:6px">ไปหน้าจองเครื่อง</a>
        </div>

        <div class="card">
          <div class="card-head"><div><h3>ผลผลิตตามรุ่น</h3><p>นับเฉพาะ 7 วันที่ผลิตจบแล้ว ไม่รวมวันนี้</p></div></div>
          ${Chart.hbars(d.models.map((m) => ({
            label: m.model, value: m.achievement, unit: '%',
            display: num(m.achievement, 0) + '%',
            color: m.achievement >= 98 ? 'var(--ok)' : m.achievement >= 90 ? 'var(--warn)' : 'var(--crit)',
          })), { labelW: 96, max: 110 })}
        </div>

        <div class="card">
          <div class="card-head"><div><h3>ภาระงานรายทีม</h3><p>เฉลี่ยจากคนในทีม</p></div></div>
          <div class="stack" style="gap:12px">
            ${d.teams.map((t) => `<div>
              <div class="row" style="justify-content:space-between;margin-bottom:5px">
                <span class="strong">${esc(t.team)}</span>
                <span class="mono" style="font-size:12.5px">${num(t.load, 0)}%</span>
              </div>
              <div class="meter ${toneLoad(t.load, 70, 110)}"><span style="width:${Math.min(100, t.load)}%"></span></div>
              <p class="stat-note">หัวหน้า ${esc(t.leader || '-')} · งานในมือ ${t.jobs} ใบ</p>
            </div>`).join('')}
          </div>
          <a class="btn btn-sm btn-ghost" href="#/leader" style="margin-top:12px">เปิด Leader Control Tower</a>
        </div>
      </div>

      <div class="card">
        <div class="card-head">
          <div><h2>งานที่ต้องดูก่อนใคร</h2><p>เรียงตามวันครบกำหนดและวันที่ค้างอยู่ขั้นเดิม</p></div>
          <a class="btn btn-sm btn-ghost" href="#/wip">เปิดหน้าติดตามงาน</a>
        </div>
        <div class="table-wrap">
          <table>
            <thead><tr>
              <th>เลขที่งาน</th><th>รุ่น</th><th>ขั้นตอน</th><th>ผู้รับผิดชอบ</th>
              <th class="t-right">ค้างมา</th><th class="t-right">ครบกำหนด</th><th class="t-right">คาดเสร็จ</th><th>สถานะ</th>
            </tr></thead>
            <tbody>
              ${d.hot_jobs.map((j) => `<tr onclick="FGPActions.openJob(${j.id})" style="cursor:pointer">
                <td class="mono strong">${esc(j.job_no)}</td>
                <td class="mono">${esc(j.model)}</td>
                <td>${esc(j.stage)}</td>
                <td>${esc(j.owner || '-')}<span class="muted"> · ${esc(j.team || '-')}</span></td>
                <td class="num">${j.stage_days} วัน</td>
                <td class="num">${fmtDate(j.due_date)}</td>
                <td class="num">${fmtDate(j.eta)}</td>
                <td>${riskChip(j)}</td>
              </tr>`).join('')}
            </tbody>
          </table>
        </div>
      </div>
    </div>`;

    return h(html);
  }

  /* ============================================================== แผนผลิต */

  async function plan(params) {
    const to = params.to || todayIso();
    const days = Number(params.days || 7);
    const from = params.from || shiftDays(to, -(days - 1));
    const d = await api.get(`/api/plan?from=${from}&to=${to}`);
    const ref = await reference();
    const s = d.summary;
    const includesToday = d.to >= todayIso();

    // ถ้าช่วงที่ดูรวมวันนี้ด้วย ให้ตัดวันนี้ออกจากการเทียบรายรุ่น
    // เพราะวันที่ยังผลิตไม่จบจะทำให้ทุกรุ่นดูตกเป้าทั้งที่ยังไม่ถึงเวลา
    const modelSource = includesToday
      ? (() => {
          const acc = {};
          d.items.filter((it) => it.date !== todayIso() && it.actual !== null).forEach((it) => {
            const m = acc[it.model] || (acc[it.model] = { model: it.model, plan: 0, actual: 0 });
            m.plan += it.plan;
            m.actual += it.actual;
          });
          return Object.values(acc)
            .map((m) => ({ ...m, achievement: m.plan ? Math.round((m.actual / m.plan) * 1000) / 10 : 0 }))
            .sort((a, b) => b.plan - a.plan);
        })()
      : d.models;

    const modelRows = modelSource.map((m) => ({
      label: m.model, value: m.achievement, unit: '%',
      display: num(m.achievement, 0) + '%',
      color: m.achievement >= 98 ? 'var(--ok)' : m.achievement >= 90 ? 'var(--warn)' : 'var(--crit)',
    }));

    const html = `<div class="page stack">
      <div class="card">
        <div class="card-head">
          <div><h2>ช่วงเวลาที่กำลังดู</h2><p>${fmtDate(d.from, true)} ถึง ${fmtDate(d.to, true)}</p></div>
          <div class="card-tools">
            <div class="seg">
              ${[7, 14, 30].map((n) => `<button class="${n === days ? 'is-on' : ''}" onclick="FGPActions.planRange(${n})">${n} วัน</button>`).join('')}
              <button class="${params.future ? 'is-on' : ''}" onclick="FGPActions.planFuture()">แผนล่วงหน้า</button>
            </div>
            <button class="btn btn-sm btn-primary" onclick="FGPActions.newPlan()">+ เพิ่มแผนผลิต</button>
          </div>
        </div>
        <div class="grid g-4">
          ${stat({
            label: 'แผนรวมทั้งช่วง', value: num(s.plan), unit: 'ชิ้น', tone: 'info',
            note: `${s.shifts_total} กะ · ยังไม่ถึงคิวผลิต ${num(s.plan - s.plan_started)} ชิ้น`,
          })}
          ${stat({
            label: 'ผลจริงรวม', value: num(s.actual_started), unit: 'ชิ้น', tone: 'accent',
            note: `จากแผน ${num(s.plan_started)} ชิ้นของกะที่เริ่มแล้ว`,
          })}
          ${gapAware(s)}
          ${stat({
            label: 'ส่วนต่างจากแผน',
            value: s.shifts_started ? (s.actual_started - s.plan_started >= 0 ? '+' : '') + num(s.actual_started - s.plan_started) : '-',
            unit: s.shifts_started ? 'ชิ้น' : '',
            tone: !s.shifts_started ? 'info' : s.actual_started >= s.plan_started ? 'ok' : 'crit',
            note: !s.shifts_started ? 'ยังไม่มีกะไหนเริ่มผลิต'
              : s.actual_started >= s.plan_started ? 'ทำได้มากกว่าแผน' : 'ยังขาดจากแผนของกะที่ผ่านมา',
          })}
        </div>
      </div>

      <div class="card">
        <div class="card-head"><div><h2>แผนกับผลจริงรายวัน</h2>
        <p>สีของแท่งผลจริงบอกทันทีว่าวันไหนหลุดเป้า</p></div></div>
        ${Chart.columns({
          labels: d.days.map((x) => fmtDayLabel(x.date)),
          plan: d.days.map((x) => x.plan),
          actual: d.days.map((x) => x.actual),
          height: 280,
        })}
      </div>

      <div class="grid g-2">
        <div class="card">
          <div class="card-head"><div><h3>สรุปรายสัปดาห์</h3><p>นับสัปดาห์เริ่มวันจันทร์</p></div></div>
          <div class="table-wrap">
            <table style="min-width:auto">
              <thead><tr><th>สัปดาห์ที่เริ่ม</th><th class="t-right">แผน</th><th class="t-right">ผลจริง</th><th class="t-right">%</th></tr></thead>
              <tbody>
                ${d.weeks.map((w) => `<tr>
                  <td>${fmtDate(w.week_start, true)}</td>
                  <td class="num">${num(w.plan)}</td>
                  <td class="num">${w.has_actual ? num(w.actual) : '<span class="muted">รอผลิต</span>'}</td>
                  <td class="t-right">${achievementChip(w.achievement)}</td>
                </tr>`).join('') || '<tr><td colspan="4">' + emptyBox('ยังไม่มีข้อมูล', '') + '</td></tr>'}
              </tbody>
            </table>
          </div>
        </div>

        <div class="card">
          <div class="card-head"><div><h3>ผลงานตามรุ่น</h3>
          <p>${includesToday ? 'นับเฉพาะวันที่ผลิตจบแล้ว ไม่รวมวันนี้' : 'เทียบผลจริงกับแผนของรุ่นนั้นในช่วงนี้'}</p></div></div>
          ${modelRows.length ? Chart.hbars(modelRows, { labelW: 104, max: 110 }) : emptyBox('ยังไม่มีข้อมูลรุ่น', '')}
        </div>
      </div>

      <div class="card">
        <div class="card-head">
          <div><h2>ตารางแผนผลิต</h2><p>กดที่ช่องผลจริงเพื่อบันทึกตัวเลขของวันนั้นได้เลย</p></div>
          <input type="date" id="planJump" value="${to}" onchange="FGPActions.planJump(this.value)" style="width:auto">
        </div>
        <div class="table-wrap" style="max-height:560px;overflow-y:auto">
          <table>
            <thead><tr>
              <th>วันที่</th><th>รุ่น</th><th>ไลน์</th><th>กะ</th>
              <th class="t-right">แผน</th><th class="t-right">ผลจริง</th><th class="t-right">ส่วนต่าง</th><th class="t-right">%</th><th></th>
            </tr></thead>
            <tbody>
              ${d.items.map((it) => `<tr>
                <td class="nowrap">${fmtDate(it.date)}</td>
                <td class="mono strong">${esc(it.model)}</td>
                <td class="muted">${esc(it.line)}</td>
                <td>${esc(it.shift)}</td>
                <td class="num">${num(it.plan)}</td>
                <td class="num">${it.actual === null ? '<span class="muted">รอบันทึก</span>' : num(it.actual)}</td>
                <td class="num" style="color:${it.gap === null ? 'var(--muted)' : it.gap >= 0 ? 'var(--ok)' : 'var(--crit)'}">
                  ${it.gap === null ? '-' : (it.gap >= 0 ? '+' : '') + num(it.gap)}</td>
                <td class="t-right">${achievementChip(it.achievement)}</td>
                <td class="t-right"><button class="btn btn-sm btn-ghost" onclick="FGPActions.editActual(${it.id}, '${esc(it.model)}', '${esc(it.shift)}', ${it.plan}, ${it.actual === null ? 'null' : it.actual})">บันทึกผล</button></td>
              </tr>`).join('') || '<tr><td colspan="9">' + emptyBox('ไม่มีแผนในช่วงนี้', 'ลองเปลี่ยนช่วงวันที่ หรือเพิ่มแผนใหม่') + '</td></tr>'}
            </tbody>
          </table>
        </div>
      </div>
    </div>`;

    const node = h(html);
    node._models = ref.models;
    return node;
  }

  /* ============================================================ จองเครื่อง */

  async function capacity(params) {
    const date = params.date || todayIso();
    const type = params.type || '';
    const d = await api.get(`/api/capacity?date=${date}${type ? '&type=' + encodeURIComponent(type) : ''}`);
    const ref = await reference();
    window.__capData = d; // ใช้ตอนกดดูรายละเอียดคิวจอง

    const openH = Math.min(...d.machines.map((m) => m.open_hour), 8);
    const closeH = Math.max(...d.machines.map((m) => m.close_hour), 20);
    const span = closeH - openH || 12;

    const ruler = [];
    for (let hr = openH; hr <= closeH; hr += 2) {
      ruler.push(`<span style="left:${((hr - openH) / span) * 100}%">${String(hr).padStart(2, '0')}:00</span>`);
    }

    const rows = d.machines.map((m) => {
      const slots = m.bookings.map((b) => {
        const left = ((b.start - openH) / span) * 100;
        const width = ((b.end - b.start) / span) * 100;
        return `<div class="slot" style="left:${left}%;width:calc(${width}% - 2px)"
          title="${esc(b.owner)} · ${esc(b.purpose || 'ไม่ระบุงาน')} · ${hhmm(b.start)} ถึง ${hhmm(b.end)}"
          onclick="FGPActions.bookingInfo(${b.id})">
          ${hhmm(b.start)} ${esc(b.owner.split(' ')[0])}</div>`;
      }).join('');

      const statusChip = m.status === 'READY'
        ? `<span class="chip chip-${toneLoad(m.utilization)}"><i class="dot"></i>${num(m.utilization, 0)}%</span>`
        : '<span class="chip chip-crit"><i class="dot"></i>ปิดซ่อม</span>';

      const nextFree = m.status !== 'READY'
        ? '<span class="muted">ยังไม่พร้อมใช้</span>'
        : m.next_free
          ? `ว่าง ${hhmm(m.next_free.start)} ถึง ${hhmm(m.next_free.end)}`
          : '<span style="color:var(--crit)">เต็มทั้งวัน</span>';

      return `<div class="machine-row">
        <div class="machine-id">
          <strong>${esc(m.code)}</strong>
          <span>${esc(m.name)}</span>
        </div>
        <div>
          <div class="track ${m.status === 'READY' ? '' : 'is-down'}">
            ${slots || (m.status === 'READY' ? '<div class="track-free-label">ว่างทั้งวัน</div>' : '<div class="track-free-label">ปิดซ่อมบำรุง</div>')}
          </div>
          <div class="row" style="gap:8px;margin-top:5px;font-size:11.5px">
            ${statusChip}
            <span class="muted">${nextFree}</span>
            <span class="spacer"></span>
            <button class="btn btn-sm btn-ghost" onclick="FGPActions.book(${m.id}, '${date}')" ${m.status === 'READY' ? '' : 'disabled'}>จองเครื่องนี้</button>
          </div>
        </div>
      </div>`;
    }).join('');

    const html = `<div class="page stack">
      <div class="card">
        <div class="card-head">
          <div><h2>ตารางเครื่องวันที่ ${fmtDate(date, true)}</h2>
          <p>ดูได้ทันทีว่าเครื่องไหนว่างช่วงไหน และจองต่อได้เลย</p></div>
          <div class="card-tools">
            <button class="btn btn-sm btn-ghost" onclick="FGPActions.capDate('${shiftDays(date, -1)}')">‹ วันก่อน</button>
            <input type="date" value="${date}" onchange="FGPActions.capDate(this.value)" style="width:auto">
            <button class="btn btn-sm btn-ghost" onclick="FGPActions.capDate('${shiftDays(date, 1)}')">วันถัดไป ›</button>
            <button class="btn btn-sm btn-primary" onclick="FGPActions.book(0, '${date}')">+ จองคิวใหม่</button>
          </div>
        </div>
        <div class="grid g-4">
          ${d.types.map((t) => stat({
            label: t.label, value: num(t.utilization, 0), unit: '% ถูกใช้',
            tone: toneLoad(t.utilization),
            note: `เครื่อง ${t.machines} ตัว${t.down ? ` · ปิดซ่อม ${t.down}` : ''} · ว่างอีก ${num(t.free_hours, 1)} ชม.`,
            meter: t.utilization, meterTone: toneLoad(t.utilization),
          })).join('')}
        </div>
      </div>

      <div class="card">
        <div class="card-head">
          <div><h2>ผังเวลาการใช้เครื่อง</h2><p>แถบสีคือคิวที่ถูกจองแล้ว กดที่แถบเพื่อดูรายละเอียดหรือยกเลิก</p></div>
          <div class="seg">
            <button class="${type === '' ? 'is-on' : ''}" onclick="FGPActions.capType('')">ทั้งหมด</button>
            ${Object.entries(ref.machine_types).map(([k, v]) =>
              `<button class="${type === k ? 'is-on' : ''}" onclick="FGPActions.capType('${k}')">${esc(v)}</button>`).join('')}
          </div>
        </div>
        <div class="timeline-head">
          <span class="muted" style="font-size:11.5px">เครื่อง</span>
          <div class="hour-ruler">${ruler.join('')}</div>
        </div>
        ${rows || emptyBox('ไม่มีเครื่องในกลุ่มนี้', 'ลองเลือกกลุ่มอื่น')}
      </div>

      <div class="card">
        <div class="card-head"><div><h3>ช่วงว่างที่จองได้</h3><p>ระบบคำนวณจากคิวที่มีอยู่จริง ณ ตอนนี้</p></div></div>
        <div class="table-wrap">
          <table>
            <thead><tr><th>เครื่อง</th><th>ประเภท</th><th>ที่ตั้ง</th><th>ช่วงที่ยังว่าง</th><th class="t-right">ชั่วโมงว่าง</th></tr></thead>
            <tbody>
              ${d.machines.filter((m) => m.status === 'READY').map((m) => `<tr>
                <td class="mono strong">${esc(m.code)}</td>
                <td>${esc(m.type_label)}</td>
                <td class="muted">${esc(m.location)}</td>
                <td>${m.free_slots.length
                  ? `<div class="pill-row">${m.free_slots.map((s) => `<span class="chip chip-accent">${hhmm(s.start)} - ${hhmm(s.end)}</span>`).join('')}</div>`
                  : '<span class="chip chip-crit">เต็มทั้งวัน</span>'}</td>
                <td class="num">${num(m.free_hours, 1)}</td>
              </tr>`).join('')}
            </tbody>
          </table>
        </div>
      </div>
    </div>`;

    return h(html);
  }

  /* =============================================================== WIP */

  async function wip(params) {
    const d = await api.get('/api/wip');
    const ref = await reference();
    const view = params.view || 'lane';
    const s = d.summary;

    const lanes = d.lanes.map((l) => `<div class="lane">
      <div class="lane-head">
        <h3>${esc(l.stage)}</h3>
        <span class="lane-count">${l.count}</span>
      </div>
      <div class="lane-bar" style="background:${l.late ? 'var(--crit)' : 'var(--accent)'}"></div>
      <p class="stat-note" style="margin:0">ค้างเฉลี่ย ${num(l.avg_days, 1)} วัน${l.late ? ` · ช้า ${l.late} ใบ` : ''}</p>
      ${l.jobs.length ? l.jobs.map((j, i) => `<div class="job-card ${j.risk === 'LATE' ? 'is-late' : ''}" style="animation-delay:${i * 40}ms" onclick="FGPActions.openJob(${j.id})">
        <div class="job-no">${esc(j.job_no)}</div>
        <div class="job-meta">
          <span>${esc(j.model)}</span><span>·</span><span>${num(j.qty)} ชิ้น</span>
        </div>
        <div class="job-meta">${esc(j.owner || 'ยังไม่มอบหมาย')}</div>
        <div class="job-foot">
          <span class="chip chip-${j.stage_days >= 4 ? 'crit' : j.stage_days >= 2 ? 'warn' : 'mute'}">ค้าง ${j.stage_days} วัน</span>
          ${j.priority === 'URGENT' ? '<span class="chip chip-crit">ด่วน</span>' : ''}
          ${j.risk === 'LATE' ? '<span class="chip chip-crit" title="คาดว่าจะเสร็จหลังวันครบกำหนด">เลยกำหนด</span>' : ''}
        </div>
      </div>`).join('') : '<p class="lane-empty">ไม่มีงานค้างขั้นนี้</p>'}
    </div>`).join('');

    const table = `<div class="table-wrap">
      <table>
        <thead><tr>
          <th>เลขที่งาน</th><th>รุ่น</th><th>ลูกค้า</th><th class="t-right">จำนวน</th>
          <th>ขั้นตอน</th><th>ผู้รับผิดชอบ</th><th class="t-right">อายุงาน</th>
          <th class="t-right">ค้างขั้นนี้</th><th class="t-right">ครบกำหนด</th><th class="t-right">คาดเสร็จ</th><th>สถานะ</th>
        </tr></thead>
        <tbody>
          ${d.jobs.map((j) => `<tr onclick="FGPActions.openJob(${j.id})" style="cursor:pointer">
            <td class="mono strong">${esc(j.job_no)}${j.priority === 'URGENT' ? ' <span class="chip chip-crit">ด่วน</span>' : ''}</td>
            <td class="mono">${esc(j.model)}</td>
            <td class="muted">${esc(j.customer)}</td>
            <td class="num">${num(j.qty)}</td>
            <td>${esc(j.stage)}</td>
            <td>${esc(j.owner || '-')}<span class="muted"> · ${esc(j.team || '-')}</span></td>
            <td class="num">${j.age_days} วัน</td>
            <td class="num" style="color:${j.stage_days >= 4 ? 'var(--crit)' : j.stage_days >= 2 ? 'var(--warn)' : 'inherit'}">${j.stage_days} วัน</td>
            <td class="num">${fmtDate(j.due_date)}</td>
            <td class="num">${fmtDate(j.eta)}</td>
            <td>${riskChip(j)}</td>
          </tr>`).join('')}
        </tbody>
      </table>
    </div>`;

    const html = `<div class="page stack">
      <div class="grid g-4">
        ${stat({ label: 'งานที่ยังเดินอยู่', value: num(s.open), unit: 'ใบ', tone: 'accent' })}
        ${stat({ label: 'เสี่ยงส่งไม่ทัน', value: num(s.late), unit: 'ใบ', tone: s.late ? 'crit' : 'ok', note: 'คำนวณจากขั้นตอนที่เหลือ' })}
        ${stat({ label: 'งานด่วน', value: num(s.urgent), unit: 'ใบ', tone: 'warn' })}
        ${stat({ label: 'ค้างขั้นเดิมเกิน 3 วัน', value: num(s.stuck), unit: 'ใบ', tone: s.stuck ? 'warn' : 'ok', note: `อายุงานเฉลี่ย ${num(s.avg_age, 1)} วัน` })}
      </div>

      <div class="card">
        <div class="card-head">
          <div><h2>เส้นทางการไหลของงาน</h2>
          <p>งานทุกใบเดินจากซ้ายไปขวา กดที่การ์ดเพื่อดูประวัติและสั่งงานต่อ</p></div>
          <div class="seg">
            <button class="${view === 'lane' ? 'is-on' : ''}" onclick="FGPActions.wipView('lane')">มุมมองสายงาน</button>
            <button class="${view === 'table' ? 'is-on' : ''}" onclick="FGPActions.wipView('table')">มุมมองตาราง</button>
          </div>
        </div>
        ${view === 'lane' ? `<div class="lanes">${lanes}</div>` : table}
      </div>
    </div>`;

    const node = h(html);
    node._members = ref.members;
    return node;
  }

  /* =============================================================== KPI */

  async function kpi(params) {
    const days = Number(params.days || 14);
    const d = await api.get(`/api/kpi?days=${days}`);
    if (!d.today) return h(`<div class="card">${emptyBox('ยังไม่มีข้อมูล KPI', '')}</div>`);
    const t = d.today, a = d.avg, dl = d.delta;
    const labels = d.series.map((x) => fmtDayLabel(x.date));

    const html = `<div class="page stack">
      <div class="card">
        <div class="card-head">
          <div><h2>ตัวชี้วัดการผลิตวันนี้</h2><p>ข้อมูลวันที่ ${fmtDate(t.date, true)} · เทียบกับค่าเฉลี่ย ${d.series.length} วัน</p></div>
          <div class="seg">
            ${[7, 14, 30].map((n) => `<button class="${n === days ? 'is-on' : ''}" onclick="FGPActions.kpiRange(${n})">${n} วัน</button>`).join('')}
          </div>
        </div>
        <div class="grid g-3" style="align-items:stretch">
          <div class="card" style="box-shadow:none;background:var(--panel-2)">
            <div class="gauge-wrap">
              ${Chart.gauge(t.oee, { label: 'OEE', good: 75, ok: 60, digits: 1 })}
              <div>
                <p class="stat-label">OEE</p>
                <p class="stat-note" style="margin-top:6px">Availability ${num(t.utilization, 0)}%<br>
                Performance ${num(t.performance, 0)}%<br>Quality ${num(t.yield, 1)}%</p>
                <p class="stat-note">ค่าเฉลี่ยช่วงนี้ ${num(a.oee, 1)}%</p>
              </div>
            </div>
          </div>
          <div class="card" style="box-shadow:none;background:var(--panel-2)">
            <div class="gauge-wrap">
              ${Chart.gauge(t.yield, { label: 'Yield', good: 98, ok: 96, digits: 2 })}
              <div>
                <p class="stat-label">Yield</p>
                <p class="stat-note" style="margin-top:6px">ของดี ${num(t.output)} ชิ้น<br>เฉลี่ยช่วงนี้ ${num(a.yield, 2)}%</p>
              </div>
            </div>
          </div>
          <div class="card" style="box-shadow:none;background:var(--panel-2)">
            <div class="gauge-wrap">
              ${Chart.gauge(t.utilization, { label: 'Utilization', good: 90, ok: 80 })}
              <div>
                <p class="stat-label">Utilization</p>
                <p class="stat-note" style="margin-top:6px">เดินเครื่องจริงเทียบเวลาที่วางแผน<br>เฉลี่ยช่วงนี้ ${num(a.utilization, 1)}%</p>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="grid g-4">
        ${stat({
          label: 'Output วันนี้', value: num(t.output), unit: 'ชิ้น', tone: 'accent',
          delta: dl.output, note: `เป้า ${num(t.target)} ชิ้น`,
          spark: Chart.spark(d.series.map((x) => x.output)),
        })}
        ${stat({
          label: 'Productivity', value: num(t.productivity, 1), unit: 'ชิ้น/คน-ชม.',
          tone: 'info', delta: dl.productivity,
          note: `กำลังคน ${t.manpower} คน`,
          spark: Chart.spark(d.series.map((x) => x.productivity), { color: 'var(--info)' }),
        })}
        ${stat({
          label: 'OT วันนี้', value: num(t.ot_hours, 1), unit: 'ชั่วโมง',
          tone: t.ot_hours > a.ot_hours ? 'warn' : 'ok', delta: dl.ot_hours,
          note: `เฉลี่ยช่วงนี้ ${num(a.ot_hours, 1)} ชั่วโมง`,
          spark: Chart.spark(d.series.map((x) => x.ot_hours), { color: 'var(--warn)' }),
        })}
        ${stat({
          label: '% ทำได้เทียบเป้า', value: num(t.achievement, 1), unit: '%',
          tone: toneHigh(t.achievement, 98, 90), delta: dl.achievement,
          note: t.date === todayIso() ? 'เทียบกับเป้าทั้งวัน วันนี้ยังผลิตไม่จบ' : `เป้า ${num(t.target)} ชิ้น`,
          meter: t.achievement, meterTone: toneHigh(t.achievement, 98, 90),
        })}
      </div>

      <div class="grid g-2">
        <div class="card">
          <div class="card-head"><div><h3>Output เทียบเป้า</h3><p>เส้นประคือเป้าที่ตั้งไว้ในแต่ละวัน</p></div></div>
          ${Chart.line({
            uid: 1, labels,
            series: [
              { name: 'Output จริง', values: d.series.map((x) => x.output), color: 'var(--accent)', area: true },
              { name: 'เป้า', values: d.series.map((x) => x.target), color: 'var(--muted)', dashed: true, points: false },
            ],
            height: 250,
          })}
        </div>
        <div class="card">
          <div class="card-head"><div><h3>OEE กับ Yield</h3><p>ดูว่าคุณภาพหรือเวลาเดินเครื่องเป็นตัวฉุด</p></div></div>
          ${Chart.line({
            uid: 2, labels,
            series: [
              { name: 'OEE %', values: d.series.map((x) => x.oee), color: 'var(--info)', area: true, digits: 1, unit: '%' },
              { name: 'Yield %', values: d.series.map((x) => x.yield), color: 'var(--ok)', digits: 2, unit: '%' },
            ],
            height: 250,
          })}
        </div>
      </div>

      <div class="grid g-2">
        <div class="card">
          <div class="card-head"><div><h3>ชั่วโมง OT กับกำลังคน</h3><p>OT ที่พุ่งขึ้นมักตามมาด้วย Yield ที่ตก</p></div></div>
          ${Chart.line({
            uid: 3, labels,
            series: [
              { name: 'OT ชั่วโมง', values: d.series.map((x) => x.ot_hours), color: 'var(--warn)', area: true, digits: 1 },
              { name: 'กำลังคน', values: d.series.map((x) => x.manpower), color: 'var(--accent)' },
            ],
            height: 230,
          })}
        </div>
        <div class="card">
          <div class="card-head"><div><h3>ตารางค่ารายวัน</h3><p>ตัวเลขเต็มไว้ทำรายงานส่งผู้จัดการ</p></div></div>
          <div class="table-wrap" style="max-height:290px;overflow-y:auto">
            <table>
              <thead><tr><th>วันที่</th><th class="t-right">Output</th><th class="t-right">%</th>
              <th class="t-right">OT</th><th class="t-right">Util</th><th class="t-right">Yield</th><th class="t-right">OEE</th></tr></thead>
              <tbody>
                ${[...d.series].reverse().map((x) => `<tr>
                  <td class="nowrap">${fmtDate(x.date)}</td>
                  <td class="num">${num(x.output)}</td>
                  <td class="num" style="color:${x.achievement >= 98 ? 'var(--ok)' : x.achievement >= 90 ? 'var(--warn)' : 'var(--crit)'}">${num(x.achievement, 1)}</td>
                  <td class="num">${num(x.ot_hours, 1)}</td>
                  <td class="num">${num(x.utilization, 1)}</td>
                  <td class="num">${num(x.yield, 2)}</td>
                  <td class="num strong">${num(x.oee, 1)}</td>
                </tr>`).join('')}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>`;

    return h(html);
  }

  /* ============================================================== Leader */

  async function leader() {
    const d = await api.get('/api/team');
    const s = d.summary;

    const stateChip = (p) => {
      if (p.state === 'OVER') return '<span class="chip chip-crit"><i class="dot"></i>งานล้น</span>';
      if (p.state === 'BUSY') return '<span class="chip chip-warn"><i class="dot"></i>งานแน่น</span>';
      if (p.state === 'FREE') return '<span class="chip chip-ok"><i class="dot"></i>ว่าง รับงานได้</span>';
      return '<span class="chip chip-mute"><i class="dot"></i>พอดี</span>';
    };

    const byTeam = {};
    d.people.forEach((p) => { (byTeam[p.team] = byTeam[p.team] || []).push(p); });

    const teamBlocks = Object.entries(byTeam).map(([team, people]) => {
      const meta = d.teams.find((t) => t.team === team) || {};
      return `<div class="card">
        <div class="card-head">
          <div><h3>${esc(team)}</h3><p>หัวหน้าทีม ${esc(meta.leader || '-')} · ${people.length} คน · งานในมือ ${meta.jobs || 0} ใบ</p></div>
          <span class="chip chip-${toneLoad(meta.load || 0, 70, 110)}">ภาระเฉลี่ย ${num(meta.load, 0)}%</span>
        </div>
        <div class="stack" style="gap:9px">
          ${people.map((p) => `<div class="person">
            <div class="avatar">${esc(FGP.initials(p.name))}</div>
            <div style="min-width:0">
              <div class="person-name">${esc(p.name)} <span class="muted" style="font-weight:400">${esc(p.role)}</span></div>
              <div class="person-meta">ถนัด ${esc(p.skill)} · งาน ${p.jobs} ใบ${p.urgent ? ` · ด่วน ${p.urgent}` : ''}${p.late ? ` · เสี่ยงช้า ${p.late}` : ''} · จองเครื่องวันนี้ ${num(p.booked_hours, 1)} ชม.</div>
            </div>
            <div class="person-load">
              <div class="row" style="justify-content:flex-end;gap:8px">
                ${stateChip(p)}
                <span class="load-figure">${num(p.load, 0)}%</span>
              </div>
              <div class="meter ${toneLoad(p.load, 70, 110)}"><span style="width:${Math.min(100, p.load)}%"></span></div>
            </div>
          </div>`).join('')}
        </div>
      </div>`;
    }).join('');

    const suggestions = d.suggestions.length
      ? d.suggestions.map((m) => `<div class="alert-item level-warn">
          <div class="alert-mark">⇄</div>
          <div>
            <div class="alert-title">โยกงาน ${esc(m.job_no)} จาก ${esc(m.from_name)} ไปให้ ${esc(m.to_name)}</div>
            <div class="alert-detail">${esc(m.from_name)} อยู่ที่ ${num(m.from_load, 0)}% ส่วน ${esc(m.to_name)} อยู่ที่ ${num(m.to_load, 0)}% และถนัด ${esc(m.skill)} เหมือนกัน</div>
            ${m.cross_team ? '<div class="alert-hint">เป็นการยืมคนข้ามทีม ควรบอกหัวหน้าอีกทีมก่อน</div>' : ''}
          </div>
          <div class="alert-actions">
            <button class="btn btn-sm btn-primary" onclick="FGPActions.doAssign(${m.job_id}, ${m.to_id})">อนุมัติการโยก</button>
            <button class="btn btn-sm btn-ghost" onclick="FGPActions.openJob(${m.job_id})">ดูใบงาน</button>
          </div>
        </div>`).join('')
      : emptyBox('ตอนนี้ภาระงานสมดุลดี', 'ยังไม่มีใครล้นจนต้องโยกงาน');

    const html = `<div class="page stack">
      <div class="grid g-4">
        ${stat({ label: 'กำลังคนทั้งฝ่าย', value: num(s.headcount), unit: 'คน', tone: 'accent' })}
        ${stat({ label: 'คนที่งานล้น', value: num(s.over), unit: 'คน', tone: s.over ? 'crit' : 'ok', note: 'เกิน 110% ของกำลังที่รับไหว' })}
        ${stat({ label: 'คนที่ยังว่าง', value: num(s.free), unit: 'คน', tone: 'ok', note: 'ต่ำกว่า 40% รับงานเพิ่มได้' })}
        ${stat({ label: 'ภาระงานเฉลี่ย', value: num(s.avg_load, 0), unit: '%', tone: toneLoad(s.avg_load, 70, 110), meter: s.avg_load, meterTone: toneLoad(s.avg_load, 70, 110) })}
      </div>

      <div class="card">
        <div class="card-head">
          <div><h2>คำแนะนำการโยกงาน</h2>
          <p>ระบบจับคู่คนที่ล้นกับคนที่ว่างและถนัดงานแบบเดียวกัน หัวหน้าเป็นคนกดอนุมัติเอง</p></div>
        </div>
        <div class="stack" style="gap:10px">${suggestions}</div>
      </div>

      <div class="grid g-2">${teamBlocks}</div>

      <div class="card">
        <div class="card-head"><div><h2>มอบหมายงานเอง</h2><p>เลือกใบงานแล้วเลือกคนที่จะรับผิดชอบ</p></div>
        <button class="btn btn-primary btn-sm" onclick="FGPActions.assignPicker()">เปิดหน้าต่างมอบหมายงาน</button></div>
        <p class="muted" style="font-size:13px">การโยกงานทุกครั้งถูกบันทึกไว้ในประวัติของใบงานนั้น เปิดดูย้อนหลังได้จากหน้าติดตามงาน</p>
      </div>
    </div>`;

    return h(html);
  }

  /* ============================================================== Alerts */

  function alertRow(a) {
    const icon = a.level === 'critical' ? '!' : a.level === 'warn' ? '△' : 'i';
    return `<div class="alert-item level-${a.level} ${a.acked ? 'is-acked' : ''}">
      <div class="alert-mark">${icon}</div>
      <div>
        <div class="alert-title">${esc(a.title)}</div>
        <div class="alert-detail">${esc(a.detail)}</div>
        ${a.hint ? `<div class="alert-hint">${esc(a.hint)}</div>` : ''}
      </div>
      <div class="alert-actions">
        <a class="btn btn-sm btn-ghost" href="${esc(a.action)}">ไปจัดการ</a>
        <button class="btn btn-sm ${a.acked ? 'btn-ghost' : ''}" onclick="FGPActions.ack('${esc(a.key)}', ${a.acked ? 'true' : 'false'})">
          ${a.acked ? 'เอากลับมา' : 'รับทราบแล้ว'}</button>
      </div>
    </div>`;
  }

  async function alerts() {
    const d = await api.get('/api/alerts');
    const c = d.counts;
    const groups = [
      { key: 'critical', title: 'ต้องแก้วันนี้', note: 'กระทบแผนหรือกำหนดส่งแน่นอน' },
      { key: 'warn', title: 'ต้องเฝ้าดู', note: 'ยังพอมีเวลา แต่ปล่อยไว้จะกลายเป็นปัญหา' },
      { key: 'info', title: 'ไว้ปรับปรุง', note: 'ไม่เร่งด่วน แต่ควรรู้ไว้' },
    ];

    const html = `<div class="page stack">
      <div class="grid g-4">
        ${stat({ label: 'เรื่องเร่งด่วน', value: num(c.critical), unit: 'เรื่อง', tone: c.critical ? 'crit' : 'ok' })}
        ${stat({ label: 'เรื่องที่ต้องเฝ้าดู', value: num(c.warn), unit: 'เรื่อง', tone: c.warn ? 'warn' : 'ok' })}
        ${stat({ label: 'เรื่องไว้ปรับปรุง', value: num(c.info), unit: 'เรื่อง', tone: 'info' })}
        ${stat({ label: 'รับทราบแล้ววันนี้', value: num(c.acked), unit: 'เรื่อง', tone: 'ok', note: 'ตัวนับเริ่มใหม่ทุกวัน' })}
      </div>

      ${groups.map((g) => {
        const list = d.alerts.filter((a) => a.level === g.key && !a.acked);
        return `<div class="card">
          <div class="card-head"><div><h2>${esc(g.title)}</h2><p>${esc(g.note)}</p></div>
          <span class="chip chip-${g.key === 'critical' ? 'crit' : g.key === 'warn' ? 'warn' : 'info'}">${list.length} เรื่อง</span></div>
          <div class="stack" style="gap:10px">
            ${list.length ? list.map(alertRow).join('') : emptyBox('ไม่มีเรื่องในกลุ่มนี้', 'ระบบตรวจข้อมูลล่าสุดแล้ว')}
          </div>
        </div>`;
      }).join('')}

      ${d.alerts.some((a) => a.acked) ? `<div class="card">
        <div class="card-head"><div><h2>รับทราบแล้ว</h2><p>ซ่อนจากรายการหลักจนถึงสิ้นวัน</p></div></div>
        <div class="stack" style="gap:10px">${d.alerts.filter((a) => a.acked).map(alertRow).join('')}</div>
      </div>` : ''}
    </div>`;

    return h(html);
  }

  return { overview, plan, capacity, wip, kpi, leader, alerts, reference, alertRow, stat, emptyBox };
})();
