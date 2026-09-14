/* ==========================================================================
   Myfxbook Earning System - กราฟทั้งหมดวาดด้วย SVG เอง ไม่ใช้ไลบรารีภายนอก
   ทุกฟังก์ชันคืนค่าเป็นสตริง HTML เพื่อประกอบร่างกับหน้าจอได้ทันที
   ========================================================================== */

const Chart = (() => {
  'use strict';

  const esc = MFE.esc;
  const V = { accent: 'var(--accent)', ok: 'var(--ok)', warn: 'var(--warn)', crit: 'var(--crit)', info: 'var(--info)', muted: 'var(--muted)' };

  /** ปัดขอบบนของแกนขึ้นเป็นเลขลงตัว เพื่อให้ป้ายกำกับอ่านง่ายเมื่อเป็นจำนวนเงิน */
  function niceMax(value) {
    if (value <= 0) return 10;
    const mag = Math.pow(10, Math.floor(Math.log10(value)));
    const norm = value / mag;
    const steps = [1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10];
    return (steps.find((st) => norm <= st) || 10) * mag;
  }

  function path(points) {
    return points.map((p, i) => (i ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1)).join(' ');
  }

  /** กราฟเส้นหลายชุด พร้อมพื้นที่ใต้เส้นของชุดแรก */
  function line(opts) {
    const W = 860, H = opts.height || 260;
    const pad = { t: 16, r: 16, b: 30, l: 46 };
    const labels = opts.labels || [];
    const series = opts.series || [];
    const iw = W - pad.l - pad.r;
    const ih = H - pad.t - pad.b;
    const all = series.flatMap((s) => s.values.filter((v) => v !== null && v !== undefined));
    // ขอบล่างของแกนต้องต่ำกว่าศูนย์ได้ ไม่งั้นช่วงที่กำไรสะสมติดลบจะถูกตัดหายไป
    const hi = niceMax(Math.max(...all, 1));
    const lowest = Math.min(...all, 0);
    const lo = lowest < 0 ? -niceMax(-lowest) : 0;
    const span = hi - lo || 1;
    const n = labels.length;
    const x = (i) => pad.l + (n <= 1 ? iw / 2 : (i * iw) / (n - 1));
    const y = (v) => pad.t + ih - ((v - lo) / span) * ih;
    const zeroY = y(0);

    let grid = '';
    const ticks = 4;
    for (let i = 0; i <= ticks; i++) {
      const val = lo + (span / ticks) * i;
      const yy = y(val);
      grid += `<line class="axis-line" x1="${pad.l}" y1="${yy.toFixed(1)}" x2="${W - pad.r}" y2="${yy.toFixed(1)}"/>`;
      grid += `<text class="axis-text" x="${pad.l - 8}" y="${(yy + 3).toFixed(1)}" text-anchor="end">${MFE.num(val)}</text>`;
    }

    if (lo < 0) {
      grid += `<line x1="${pad.l}" y1="${zeroY.toFixed(1)}" x2="${W - pad.r}" y2="${zeroY.toFixed(1)}" stroke="var(--hairline-strong)" stroke-width="1"/>`;
    }

    let xlabels = '';
    const step = Math.max(1, Math.ceil(n / 8));
    labels.forEach((lb, i) => {
      if (i % step === 0 || i === n - 1) {
        xlabels += `<text class="axis-text" x="${x(i).toFixed(1)}" y="${H - 8}" text-anchor="middle">${esc(lb)}</text>`;
      }
    });

    let body = '';
    series.forEach((s, si) => {
      const pts = [];
      s.values.forEach((v, i) => { if (v !== null && v !== undefined) pts.push([x(i), y(v)]); });
      if (!pts.length) return;
      const color = s.color || V.accent;
      if (s.area) {
        const area = path(pts) + ` L ${pts[pts.length - 1][0].toFixed(1)} ${zeroY.toFixed(1)} L ${pts[0][0].toFixed(1)} ${zeroY.toFixed(1)} Z`;
        body += `<path class="series-area" d="${area}" fill="url(#grad${si}_${opts.uid || 0})"/>`;
      }
      body += `<path class="series-line${s.dashed ? '' : ' draw'}" d="${path(pts)}" stroke="${color}"${s.dashed ? ' stroke-dasharray="5 5" opacity="0.75"' : ''}/>`;
      if (s.points !== false) {
        s.values.forEach((v, i) => {
          if (v === null || v === undefined) return;
          body += `<circle class="point" cx="${x(i).toFixed(1)}" cy="${y(v).toFixed(1)}" r="${n > 20 ? 2 : 3}" fill="${color}" stroke="var(--panel-solid)" stroke-width="1.5">
            <title>${esc(labels[i])} · ${esc(s.name)} ${MFE.num(v, s.digits || 0)}${esc(s.unit || '')}</title></circle>`;
        });
      }
    });

    const defs = series.map((s, si) => `<linearGradient id="grad${si}_${opts.uid || 0}" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="${s.color || V.accent}" stop-opacity="0.34"/>
        <stop offset="100%" stop-color="${s.color || V.accent}" stop-opacity="0"/>
      </linearGradient>`).join('');

    const legend = series.map((s) => `<span><i class="legend-swatch" style="background:${s.color || V.accent}"></i>${esc(s.name)}</span>`).join('');

    return `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(opts.title || 'กราฟเส้น')}">
      <defs>${defs}</defs>${grid}${body}${xlabels}</svg>
      <div class="chart-legend">${legend}</div>`;
  }

  /** แท่งกำไรขาดทุนรายวัน มีเส้นศูนย์กลาง แท่งขึ้นเขียว แท่งลงแดง */
  function pnl(opts) {
    const W = 860, H = opts.height || 240;
    const pad = { t: 14, r: 12, b: 30, l: 56 };
    const labels = opts.labels || [];
    const values = opts.values || [];
    const iw = W - pad.l - pad.r;
    const ih = H - pad.t - pad.b;
    const peak = Math.max(1, ...values.map((v) => Math.abs(v)));
    const max = niceMax(peak * 1.05);
    const n = labels.length || 1;
    const slot = iw / n;
    const bw = Math.max(2, Math.min(22, slot * 0.62));
    const zero = pad.t + ih / 2;
    const y = (v) => zero - (v / max) * (ih / 2);

    let grid = '';
    for (let i = -2; i <= 2; i++) {
      const val = (max / 2) * i;
      const yy = y(val);
      grid += `<line class="axis-line" x1="${pad.l}" y1="${yy.toFixed(1)}" x2="${W - pad.r}" y2="${yy.toFixed(1)}"/>`;
      grid += `<text class="axis-text" x="${pad.l - 8}" y="${(yy + 3).toFixed(1)}" text-anchor="end">${MFE.num(val)}</text>`;
    }
    grid += `<line x1="${pad.l}" y1="${zero.toFixed(1)}" x2="${W - pad.r}" y2="${zero.toFixed(1)}" stroke="var(--hairline-strong)" stroke-width="1"/>`;

    const step = Math.max(1, Math.ceil(n / 12));
    let bars = '';
    labels.forEach((lb, i) => {
      const v = values[i] || 0;
      const cx = pad.l + slot * i + slot / 2;
      const top = v >= 0 ? y(v) : zero;
      const h = Math.max(1, Math.abs(zero - y(v)));
      const color = v >= 0 ? V.ok : V.crit;
      bars += `<rect class="bar" x="${(cx - bw / 2).toFixed(1)}" y="${top.toFixed(1)}" width="${bw.toFixed(1)}" height="${h.toFixed(1)}" rx="2" fill="${color}" style="animation-delay:${Math.min(i * 12, 400)}ms">
        <title>${esc(lb)} · ${MFE.num(v, 2)}${esc(opts.unit || '')}</title></rect>`;
      if (i % step === 0 || i === n - 1) {
        bars += `<text class="axis-text" x="${cx.toFixed(1)}" y="${H - 10}" text-anchor="middle">${esc(lb)}</text>`;
      }
    });

    return `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(opts.title || 'กราฟกำไรขาดทุนรายวัน')}">${grid}${bars}</svg>
      <div class="chart-legend">
        <span><i class="legend-swatch" style="background:${V.ok}"></i>วันที่ได้กำไร</span>
        <span><i class="legend-swatch" style="background:${V.crit}"></i>วันที่ขาดทุน</span>
      </div>`;
  }

  /** แท่งแนวนอน พร้อมชื่อและค่า */
  function hbars(items, opts = {}) {
    const W = 520;
    const rowH = opts.rowH || 34;
    const H = Math.max(rowH, items.length * rowH) + 8;
    const labelW = opts.labelW || 118;
    const valueW = opts.valueW || 66;   // ต้องกว้างขึ้นเมื่อค่าที่แสดงยาวกว่าตัวเลขเปล่า
    const iw = W - labelW - valueW - 12;
    const max = Math.max(...items.map((i) => i.value), opts.max || 0, 1);
    // ป้ายที่ยาวเกินช่องจะไปทับแท่ง จึงตัดให้พอดีและเก็บข้อความเต็มไว้ใน tooltip
    const maxChars = Math.max(6, Math.floor(labelW / 7.2));
    const fit = (text) => {
      const t = String(text === null || text === undefined ? '' : text);
      return t.length > maxChars ? t.slice(0, maxChars - 1) + '…' : t;
    };

    const rows = items.map((it, i) => {
      const w = Math.max(2, (it.value / max) * iw);
      const y = i * rowH + 6;
      const color = it.color || V.accent;
      return `<g>
        <text class="axis-text" x="0" y="${y + 14}" style="fill:var(--text-2);font-size:11.5px">${esc(fit(it.label))}<title>${esc(it.label)}</title></text>
        <rect x="${labelW}" y="${y + 4}" width="${iw}" height="13" rx="6.5" fill="var(--panel-2)"/>
        <rect class="hbar" x="${labelW}" y="${y + 4}" width="${w.toFixed(1)}" height="13" rx="6.5" fill="${color}" style="animation-delay:${i * 45}ms">
          <title>${esc(it.label)} ${MFE.num(it.value, it.digits || 0)}${esc(it.unit || '')}</title></rect>
        <text class="axis-text" x="${W}" y="${y + 14}" text-anchor="end" style="fill:var(--text);font-size:11.5px">${esc(it.display || (MFE.num(it.value, it.digits || 0) + (it.unit || '')))}</text>
      </g>`;
    }).join('');

    return `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(opts.title || 'กราฟแท่งแนวนอน')}">${rows}</svg>`;
  }

  /** เกจวงกลม ใช้กับค่าเปอร์เซ็นต์ */
  function gauge(value, opts = {}) {
    const size = 104, r = 42, cx = size / 2, cy = size / 2;
    const circ = 2 * Math.PI * r;
    const pctValue = Math.max(0, Math.min(100, value || 0));
    const dash = (pctValue / 100) * circ;
    const color = opts.color || (pctValue >= (opts.good || 85) ? V.ok : pctValue >= (opts.ok || 65) ? V.warn : V.crit);
    return `<svg class="gauge" viewBox="0 0 ${size} ${size}" role="img" aria-label="${esc(opts.label || 'ค่าเปอร์เซ็นต์')} ${pctValue}%">
      <circle class="track" cx="${cx}" cy="${cy}" r="${r}"/>
      <circle class="fill" cx="${cx}" cy="${cy}" r="${r}" stroke="${color}"
        stroke-dasharray="${dash.toFixed(1)} ${circ.toFixed(1)}"/>
      <text class="gauge-value" x="${cx}" y="${cy + 2}" text-anchor="middle">${MFE.num(pctValue, opts.digits === undefined ? 0 : opts.digits)}</text>
      <text class="gauge-unit" x="${cx}" y="${cy + 17}" text-anchor="middle">${esc(opts.unit || '%')}</text>
    </svg>`;
  }

  /** เส้นเล็กในการ์ดสถิติ */
  function spark(values, opts = {}) {
    const W = 200, H = 34, pad = 3;
    const clean = values.filter((v) => v !== null && v !== undefined);
    if (clean.length < 2) return '<svg class="chart" viewBox="0 0 200 34"></svg>';
    const min = Math.min(...clean), max = Math.max(...clean);
    const span = max - min || 1;
    const x = (i) => pad + (i * (W - pad * 2)) / (values.length - 1);
    const y = (v) => H - pad - ((v - min) / span) * (H - pad * 2);
    const pts = values.map((v, i) => [x(i), y(v)]);
    const color = opts.color || V.accent;
    const uid = 'sp' + Math.random().toString(36).slice(2, 7);
    const area = path(pts) + ` L ${W - pad} ${H} L ${pad} ${H} Z`;
    return `<svg class="chart" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" aria-hidden="true">
      <defs><linearGradient id="${uid}" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="${color}" stop-opacity="0.3"/>
        <stop offset="100%" stop-color="${color}" stop-opacity="0"/>
      </linearGradient></defs>
      <path d="${area}" fill="url(#${uid})"/>
      <path d="${path(pts)}" fill="none" stroke="${color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>`;
  }

  /** โดนัทแบ่งสัดส่วน */
  function donut(segments, opts = {}) {
    const size = 132, r = 52, cx = size / 2, cy = size / 2, stroke = 16;
    const total = segments.reduce((s, x) => s + x.value, 0) || 1;
    const circ = 2 * Math.PI * r;
    let offset = 0;
    const arcs = segments.map((s, i) => {
      const len = (s.value / total) * circ;
      const el = `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${s.color}" stroke-width="${stroke}"
        stroke-dasharray="${Math.max(0, len - 2).toFixed(1)} ${(circ - len + 2).toFixed(1)}"
        stroke-dashoffset="${(-offset).toFixed(1)}" transform="rotate(-90 ${cx} ${cy})" stroke-linecap="round"
        style="animation:fade-up .6s var(--ease-out) ${i * 90}ms both">
        <title>${esc(s.label)} ${MFE.num(s.value)}</title></circle>`;
      offset += len;
      return el;
    }).join('');
    return `<svg class="chart" viewBox="0 0 ${size} ${size}" style="max-width:${size}px" role="img" aria-label="${esc(opts.label || 'สัดส่วน')}">
      <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="var(--panel-2)" stroke-width="${stroke}"/>
      ${arcs}
      <text x="${cx}" y="${cy - 2}" text-anchor="middle" class="gauge-value">${esc(opts.center || MFE.num(total))}</text>
      <text x="${cx}" y="${cy + 15}" text-anchor="middle" class="gauge-unit">${esc(opts.centerLabel || '')}</text>
    </svg>`;
  }

  return { line, pnl, hbars, gauge, spark, donut, colors: V };
})();
