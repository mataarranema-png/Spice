// ตัวเชื่อมกับ API ฝั่งเซิร์ฟเวอร์
const cache = new Map();

async function request(method, path, body, opts = {}) {
  const res = await fetch(path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
    credentials: 'same-origin',
  });
  if (res.status === 401 && !opts.quiet) {
    window.dispatchEvent(new CustomEvent('fgp:unauthorized'));
  }
  const text = await res.text();
  let data = {};
  try { data = text ? JSON.parse(text) : {}; } catch { data = { error: 'อ่านคำตอบจากเซิร์ฟเวอร์ไม่ได้' }; }
  if (!res.ok) throw new Error(data.error || `เกิดข้อผิดพลาด (${res.status})`);
  return data;
}

export const api = {
  get: (path, params) => {
    const qs = params ? '?' + new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')
    ) : '';
    return request('GET', path + qs);
  },
  post: (path, body) => request('POST', path, body || {}),
  put: (path, body) => request('PUT', path, body || {}),
  del: (path) => request('DELETE', path, {}),
  quietGet: (path) => request('GET', path, null, { quiet: true }),

  // แคชสั้นๆ สำหรับข้อมูลหลักที่ไม่ค่อยเปลี่ยน
  async cached(path, ttl = 60000) {
    const hit = cache.get(path);
    if (hit && Date.now() - hit.at < ttl) return hit.data;
    const data = await request('GET', path);
    cache.set(path, { at: Date.now(), data });
    return data;
  },
  clearCache: () => cache.clear(),
};

// สถานะที่ใช้ร่วมกันทั้งแอป
export const store = {
  user: null,
  lines: [],
  models: [],
  leaders: [],
  today: new Date().toISOString().slice(0, 10),
  shift: 'A',
  date: new Date().toISOString().slice(0, 10),
  shiftHours: 8,

  async bootstrap() {
    const data = await api.get('/api/bootstrap');
    this.user = data.user;
    this.lines = data.lines;
    this.models = data.models;
    this.leaders = data.leaders;
    this.today = data.today;
    this.shiftHours = data.shift_hours;
    if (!this._touched) { this.date = data.today; this.shift = data.shift; }
    return data;
  },

  setFilter(date, shift) {
    this._touched = true;
    if (date) this.date = date;
    if (shift) this.shift = shift;
  },

  line(id) { return this.lines.find((l) => l.id === Number(id)); },
  model(id) { return this.models.find((m) => m.id === Number(id)); },
  can(role) {
    const rank = { viewer: 0, operator: 1, leader: 2, manager: 3, admin: 4 };
    return (rank[this.user?.role] ?? -1) >= rank[role];
  },
};
