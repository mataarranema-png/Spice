/* ==========================================================================
   FGP Production Suite - กราฟทั้งหมดวาดด้วย SVG เอง ไม่ใช้ไลบรารีภายนอก
   ทุกฟังก์ชันคืนค่าเป็นสตริง HTML เพื่อประกอบร่างกับหน้าจอได้ทันที
   ========================================================================== */

const Chart = (() => {
  'use strict';

  const esc = FGP.esc;
  const V = { accent: 'var(--accent)', ok: 'var(--ok)', warn: 'var(--warn)', crit: 'var(--crit)', info: 'var(--info)', muted: 'var(--muted)' };

  function niceMax(value) {
    if (value <= 0) return 10;
    const mag = Math.pow(10, Math.floor(Math.log10(value)));
    const norm = value / mag;
    const step = norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 5 ? 5 : 10;
    return step * mag * 1.08;
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
    const max = niceMax(Math.max(...all, 1));
    const n = labels.length;
    const x = (i) => pad.l + (n <= 1 ? iw / 2 : (i * iw) / (n - 1));
    const y = (v) => pad.t + ih - (v / max) * ih;

    let grid = '';
    const ticks = 4;
    for (let i = 0; i <= ticks; i++) {
      const val = (max / ticks) * i;
      const yy = y(val);
      grid += `<line class="axis-line" x1="${pad.l}" y1="${yy.toFixed(1)}" x2="${W - pad.r}" y2="${yy.toFixed(1)}"/>`;
      grid += `<text class="axis-text" x="${pad.l - 8}" y="${(yy + 3).toFixed(1)}" text-anchor="end">${FGP.num(val)}</text>`;
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
        const area = path(pts) + ` L ${pts[pts.length - 1][0].toFixed(1)} ${pad.t + ih} L ${pts[0][0].toFixed(1)} ${pad.t + ih} Z`;
        body += `<path class="series-area" d="${area}" fill="url(#grad${si}_${opts.uid || 0})"/>`;
      }
      body += `<path class="series-line${s.dashed ? '' : ' draw'}" d="${path(pts)}" stroke="${color}"${s.dashed ? ' stroke-dasharray="5 5" opacity="0.75"' : ''}/>`;
      if (s.points !== false) {
        s.values.forEach((v, i) => {
          if (v === null || v === undefined) return;
          body += `<circle class="point" cx="${x(i).toFixed(1)}" cy="${y(v).toFixed(1)}" r="${n > 20 ? 2 : 3}" fill="${color}" stroke="var(--panel-solid)" stroke-width="1.5">
            <title>${esc(labels[i])} · ${esc(s.name)} ${FGP.num(v, s.digits || 0)}${esc(s.unit || '')}</title></circle>`;
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

  /** แท่งแนวตั้ง เปรียบเทียบสองชุด เช่น แผนกับผลจริง */
  function columns(opts) {
    const W = 860, H = opts.height || 250;
    const pad = { t: 16, r: 12, b: 32, l: 46 };
    const labels = opts.labels || [];
    const a = opts.plan || [];
    const b = opts.actual || [];
    const iw = W - pad.l - pad.r;
    const ih = H - pad.t - pad.b;
    const max = niceMax(Math.max(...a, ...b, 1));
    const n = labels.length || 1;
    const slot = iw / n;
    const bw = Math.min(26, slot * 0.34);
    const y = (v) => pad.t + ih - (v / max) * ih;

    let grid = '';
    for (let i = 0; i <= 4; i++) {
      const val = (max / 4) * i;
      const yy = y(val);
      grid += `<line class="axis-line" x1="${pad.l}" y1="${yy.toFixed(1)}" x2="${W - pad.r}" y2="${yy.toFixed(1)}"/>`;
      grid += `<text class="axis-text" x="${pad.l - 8}" y="${(yy + 3).toFixed(1)}" text-anchor="end">${FGP.num(val)}</text>`;
    }

    let bars = '';
    labels.forEach((lb, i) => {
      const cx = pad.l + slot * i + slot / 2;
      const pv = a[i] || 0;
      const av = b[i] || 0;
      const ph = Math.max(0, pad.t + ih - y(pv));
      const ah = Math.max(0, pad.t + ih - y(av));
      const ratio = pv ? (av / pv) * 100 : 0;
      const color = av === 0 ? V.muted : ratio >= 95 ? V.ok : ratio >= 85 ? V.warn : V.crit;
      bars += `<rect class="bar" x="${(cx - bw - 2).toFixed(1)}" y="${y(pv).toFixed(1)}" width="${bw}" height="${ph.toFixed(1)}" rx="3" fill="var(--hairline-strong)" style="animation-delay:${i * 25}ms">
        <title>${esc(lb)} · แผน ${FGP.num(pv)}</title></rect>`;
      bars += `<rect class="bar" x="${(cx + 2).toFixed(1)}" y="${y(av).toFixed(1)}" width="${bw}" height="${ah.toFixed(1)}" rx="3" fill="${color}" style="animation-delay:${i * 25 + 60}ms">
        <title>${esc(lb)} · ผลจริง ${FGP.num(av)} (${ratio.toFixed(0)}%)</title></rect>`;
      const step = Math.max(1, Math.ceil(n / 10));
      if (i % step === 0 || i === n - 1) {
        bars += `<text class="axis-text" x="${cx.toFixed(1)}" y="${H - 10}" text-anchor="middle">${esc(lb)}</text>`;
      }
    });

    return `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(opts.title || 'กราฟแท่ง')}">${grid}${bars}</svg>
      <div class="chart-legend">
        <span><i class="legend-swatch" style="background:var(--hairline-strong)"></i>แผน</span>
        <span><i class="legend-swatch" style="background:${V.ok}"></i>ผลจริง ถึงเป้า</span>
        <span><i class="legend-swatch" style="background:${V.crit}"></i>ผลจริง ต่ำกว่าเป้า</span>
      </div>`;
  }

  /** แท่งแนวนอน พร้อมชื่อและค่า */
  function hbars(items, opts = {}) {
    const W = 520;
    const rowH = opts.rowH || 34;
    const H = Math.max(rowH, items.length * rowH) + 8;
    const labelW = opts.labelW || 118;
    const valueW = 66;
    const iw = W - labelW - valueW - 12;
    const max = Math.max(...items.map((i) => i.value), opts.max || 0, 1);

    const rows = items.map((it, i) => {
      const w = Math.max(2, (it.value / max) * iw);
      const y = i * rowH + 6;
      const color = it.color || V.accent;
      return `<g>
        <text class="axis-text" x="0" y="${y + 14}" style="fill:var(--text-2);font-size:11.5px">${esc(it.label)}</text>
        <rect x="${labelW}" y="${y + 4}" width="${iw}" height="13" rx="6.5" fill="var(--panel-2)"/>
        <rect class="hbar" x="${labelW}" y="${y + 4}" width="${w.toFixed(1)}" height="13" rx="6.5" fill="${color}" style="animation-delay:${i * 45}ms">
          <title>${esc(it.label)} ${FGP.num(it.value, it.digits || 0)}${esc(it.unit || '')}</title></rect>
        <text class="axis-text" x="${W}" y="${y + 14}" text-anchor="end" style="fill:var(--text);font-size:11.5px">${esc(it.display || (FGP.num(it.value, it.digits || 0) + (it.unit || '')))}</text>
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
      <text class="gauge-value" x="${cx}" y="${cy + 2}" text-anchor="middle">${FGP.num(pctValue, opts.digits === undefined ? 0 : opts.digits)}</text>
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
        <title>${esc(s.label)} ${FGP.num(s.value)}</title></circle>`;
      offset += len;
      return el;
    }).join('');
    return `<svg class="chart" viewBox="0 0 ${size} ${size}" style="max-width:${size}px" role="img" aria-label="${esc(opts.label || 'สัดส่วน')}">
      <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="var(--panel-2)" stroke-width="${stroke}"/>
      ${arcs}
      <text x="${cx}" y="${cy - 2}" text-anchor="middle" class="gauge-value">${esc(opts.center || FGP.num(total))}</text>
      <text x="${cx}" y="${cy + 15}" text-anchor="middle" class="gauge-unit">${esc(opts.centerLabel || '')}</text>
    </svg>`;
  }

  return { line, columns, hbars, gauge, spark, donut, colors: V };
})();
