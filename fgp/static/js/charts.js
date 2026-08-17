// กราฟ SVG เขียนเอง ไม่พึ่งไลบรารีภายนอก ทำงานได้แม้ไม่มีอินเทอร์เน็ต
import { nf } from './ui.js';

const uid = () => 'c' + Math.random().toString(36).slice(2, 9);
const PAD = { l: 44, r: 16, t: 16, b: 26 };

function scale(v, min, max, from, to) {
  if (max === min) return (from + to) / 2;
  return from + ((v - min) / (max - min)) * (to - from);
}

function niceMax(v) {
  if (v <= 0) return 10;
  const mag = 10 ** Math.floor(Math.log10(v));
  return Math.ceil(v / mag * 2) / 2 * mag;
}

function smoothPath(points) {
  if (points.length < 2) return points.length ? `M${points[0][0]},${points[0][1]}` : '';
  let d = `M${points[0][0]},${points[0][1]}`;
  for (let i = 0; i < points.length - 1; i++) {
    const [x0, y0] = points[i];
    const [x1, y1] = points[i + 1];
    const cx = (x0 + x1) / 2;
    d += ` C${cx},${y0} ${cx},${y1} ${x1},${y1}`;
  }
  return d;
}

/** กราฟเส้น รองรับหลายชุดข้อมูล + พื้นที่ใต้เส้น */
export function lineChart({ labels = [], series = [], height = 240, width = 820, area = true,
                            yLabel = '', formatter = nf }) {
  const H = height, W = width;
  const all = series.flatMap((s) => s.values).filter((v) => v != null);
  const max = niceMax(Math.max(1, ...all));
  const min = 0;
  const x = (i) => scale(i, 0, Math.max(labels.length - 1, 1), PAD.l, W - PAD.r);
  const y = (v) => scale(v, min, max, H - PAD.b, PAD.t);
  const ticks = 4;

  let svg = `<svg class="chart" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet"
    role="img" aria-label="กราฟเส้น${yLabel ? ' ' + yLabel : ''}">`;
  svg += '<defs>';
  series.forEach((s, i) => {
    s._id = uid();
    svg += `<linearGradient id="${s._id}" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="${s.color}" stop-opacity=".33"/>
      <stop offset="100%" stop-color="${s.color}" stop-opacity="0"/></linearGradient>`;
  });
  svg += '</defs>';

  for (let t = 0; t <= ticks; t++) {
    const v = min + (max - min) * (t / ticks);
    svg += `<line class="grid-line" x1="${PAD.l}" x2="${W - PAD.r}" y1="${y(v)}" y2="${y(v)}"/>
      <text class="axis" x="${PAD.l - 8}" y="${y(v) + 3.5}" text-anchor="end">${formatter(v)}</text>`;
  }

  const step = Math.ceil(labels.length / 12) || 1;
  labels.forEach((l, i) => {
    if (i % step) return;
    svg += `<text class="axis" x="${x(i)}" y="${H - 8}" text-anchor="middle">${l}</text>`;
  });

  series.forEach((s) => {
    const pts = s.values.map((v, i) => [x(i), y(v ?? 0)]);
    const path = smoothPath(pts);
    if (area && path) {
      svg += `<path d="${path} L${x(s.values.length - 1)},${y(min)} L${x(0)},${y(min)} Z"
        fill="url(#${s._id})"/>`;
    }
    svg += `<path d="${path}" fill="none" stroke="${s.color}" stroke-width="2.4"
      stroke-linecap="round" stroke-linejoin="round"
      ${s.dashed ? 'stroke-dasharray="6 5"' : ''}/>`;
    pts.forEach((p, i) => {
      svg += `<circle class="dot" cx="${p[0]}" cy="${p[1]}" r="3.2" fill="${s.color}"
        stroke="var(--bg)" stroke-width="1.6"><title>${labels[i] || ''} · ${s.name}: ${nf(s.values[i])}</title></circle>`;
    });
  });

  return svg + '</svg>';
}

/** แท่งเทียบเป้า: แท่งจริงซ้อนบนแท่งเป้าจางๆ */
export function barChart({ labels = [], values = [], targets = null, height = 240, width = 820,
                           color = 'var(--accent)', formatter = nf }) {
  const H = height, W = width;
  const max = niceMax(Math.max(1, ...values, ...(targets || [])));
  const y = (v) => scale(v, 0, max, H - PAD.b, PAD.t);
  const band = (W - PAD.l - PAD.r) / Math.max(labels.length, 1);
  const bw = Math.min(band * 0.56, 42);

  let svg = `<svg class="chart" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet" role="img">`;
  for (let t = 0; t <= 4; t++) {
    const v = max * (t / 4);
    svg += `<line class="grid-line" x1="${PAD.l}" x2="${W - PAD.r}" y1="${y(v)}" y2="${y(v)}"/>
      <text class="axis" x="${PAD.l - 8}" y="${y(v) + 3.5}" text-anchor="end">${formatter(v)}</text>`;
  }
  labels.forEach((l, i) => {
    const cx = PAD.l + band * i + band / 2;
    if (targets) {
      const tv = targets[i] || 0;
      svg += `<rect x="${cx - bw / 2 - 4}" y="${y(tv)}" width="${bw + 8}" height="${Math.max(H - PAD.b - y(tv), 0)}"
        rx="5" fill="var(--line)"><title>เป้า ${nf(tv)}</title></rect>`;
    }
    const v = values[i] || 0;
    const ratio = targets && targets[i] ? v / targets[i] : 1;
    const fill = !targets ? color : ratio >= 1 ? 'var(--ok)' : ratio >= .92 ? 'var(--warn)' : 'var(--bad)';
    svg += `<rect x="${cx - bw / 2}" y="${y(v)}" width="${bw}" height="${Math.max(H - PAD.b - y(v), 1)}"
      rx="5" fill="${fill}" opacity=".92"><title>${l}: ${nf(v)}</title></rect>
      <text class="axis" x="${cx}" y="${H - 8}" text-anchor="middle">${l}</text>`;
  });
  return svg + '</svg>';
}

/** เกจวงแหวน ใช้กับ OEE และอัตราความสำเร็จ */
export function ringGauge(value, { size = 160, label = '', sub = '', max = 100, thickness = 12 } = {}) {
  const r = (size - thickness) / 2;
  const c = 2 * Math.PI * r;
  const ratio = Math.max(0, Math.min(value / max, 1));
  const color = value >= 85 ? 'var(--ok)' : value >= 65 ? 'var(--warn)' : 'var(--bad)';
  const id = uid();
  return `<svg viewBox="0 0 ${size} ${size}" width="${size}" height="${size}" role="img"
      aria-label="${label} ${value}%">
    <defs><linearGradient id="${id}" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="${color}" stop-opacity=".65"/>
      <stop offset="100%" stop-color="${color}"/></linearGradient></defs>
    <circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none"
      stroke="var(--surface-2)" stroke-width="${thickness}"/>
    <circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="url(#${id})"
      stroke-width="${thickness}" stroke-linecap="round" stroke-dasharray="${c}"
      stroke-dashoffset="${c * (1 - ratio)}" transform="rotate(-90 ${size / 2} ${size / 2})"
      style="transition:stroke-dashoffset 1.1s cubic-bezier(.22,.61,.36,1)"/>
    <text x="50%" y="47%" text-anchor="middle" fill="var(--text)"
      style="font-family:var(--num);font-size:${size * .21}px;font-weight:700">${value.toFixed(1)}</text>
    <text x="50%" y="62%" text-anchor="middle" fill="var(--text-3)"
      style="font-size:${size * .085}px">${label}</text>
    ${sub ? `<text x="50%" y="74%" text-anchor="middle" fill="var(--text-3)"
      style="font-size:${size * .075}px">${sub}</text>` : ''}
  </svg>`;
}

/** เส้นเล็กในการ์ด KPI */
export function sparkline(values, { color = 'var(--accent-2)', width = 240, height = 34 } = {}) {
  if (!values.length) return '';
  const max = Math.max(...values), min = Math.min(...values);
  const pts = values.map((v, i) => [
    scale(i, 0, Math.max(values.length - 1, 1), 2, width - 2),
    scale(v, min, max === min ? min + 1 : max, height - 3, 3),
  ]);
  const id = uid();
  const d = smoothPath(pts);
  return `<svg class="chart" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none">
    <defs><linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="${color}" stop-opacity=".4"/>
      <stop offset="100%" stop-color="${color}" stop-opacity="0"/></linearGradient></defs>
    <path d="${d} L${width - 2},${height} L2,${height} Z" fill="url(#${id})"/>
    <path d="${d}" fill="none" stroke="${color}" stroke-width="2" stroke-linecap="round"/>
    <circle cx="${pts.at(-1)[0]}" cy="${pts.at(-1)[1]}" r="3" fill="${color}"/>
  </svg>`;
}

/** พาเรโต: แท่งเรียงมากไปน้อย + เส้นสะสม */
export function paretoChart(items, { height = 250, width = 820 } = {}) {
  if (!items.length) return '';
  const H = height, W = width;
  const P = { l: 44, r: 42, t: 16, b: 54 };
  const max = niceMax(Math.max(...items.map((i) => i.minutes)));
  const band = (W - P.l - P.r) / items.length;
  const bw = Math.min(band * 0.58, 52);
  const y = (v) => scale(v, 0, max, H - P.b, P.t);
  const yc = (v) => scale(v, 0, 100, H - P.b, P.t);

  let svg = `<svg class="chart" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet" role="img">`;
  for (let t = 0; t <= 4; t++) {
    const v = max * (t / 4);
    svg += `<line class="grid-line" x1="${P.l}" x2="${W - P.r}" y1="${y(v)}" y2="${y(v)}"/>
      <text class="axis" x="${P.l - 8}" y="${y(v) + 3.5}" text-anchor="end">${nf(v)}</text>
      <text class="axis" x="${W - P.r + 8}" y="${yc(100 * t / 4) + 3.5}">${100 * t / 4}%</text>`;
  }
  const pts = [];
  items.forEach((it, i) => {
    const cx = P.l + band * i + band / 2;
    svg += `<rect x="${cx - bw / 2}" y="${y(it.minutes)}" width="${bw}"
      height="${Math.max(H - P.b - y(it.minutes), 1)}" rx="5"
      fill="${i === 0 ? 'var(--bad)' : i === 1 ? 'var(--warn)' : 'var(--accent)'}" opacity=".9">
      <title>${it.reason}: ${nf(it.minutes)} นาที (${it.share}%)</title></rect>`;
    const words = String(it.reason).split(' ');
    svg += `<text class="axis" x="${cx}" y="${H - 32}" text-anchor="middle">${words[0] || ''}</text>
      <text class="axis" x="${cx}" y="${H - 20}" text-anchor="middle">${words.slice(1).join(' ')}</text>`;
    pts.push([cx, yc(it.cumulative)]);
  });
  svg += `<path d="${smoothPath(pts)}" fill="none" stroke="var(--violet)" stroke-width="2.2"
    stroke-dasharray="5 4"/>`;
  pts.forEach((p, i) => {
    svg += `<circle cx="${p[0]}" cy="${p[1]}" r="3.4" fill="var(--violet)">
      <title>สะสม ${items[i].cumulative}%</title></circle>`;
  });
  return svg + '</svg>';
}

/** แถบแนวนอนสำหรับจัดอันดับไลน์ */
export function rankBars(items, { valueKey = 'ok', labelKey = 'code', targetKey = null } = {}) {
  const max = Math.max(1, ...items.map((i) => Math.max(i[valueKey], targetKey ? i[targetKey] : 0)));
  return `<div class="stack">${items.map((it) => {
    const v = it[valueKey] || 0;
    const t = targetKey ? it[targetKey] || 0 : 0;
    const ratio = t ? (v / t) * 100 : 100;
    const cls = ratio >= 100 ? 'ok' : ratio >= 92 ? 'warn' : 'bad';
    return `<div>
      <div class="row" style="justify-content:space-between;margin-bottom:5px">
        <b style="font-size:13px">${it[labelKey]}</b>
        <span class="mono t-sm t-mute">${nf(v)}${t ? ` / ${nf(t)}` : ''}
          <b style="color:var(--${cls === 'ok' ? 'ok' : cls === 'warn' ? 'warn' : 'bad'})">
            ${t ? ratio.toFixed(0) + '%' : ''}</b></span>
      </div>
      <div class="bar ${cls}"><i style="width:${Math.min((v / max) * 100, 100)}%"></i></div>
    </div>`;
  }).join('')}</div>`;
}
