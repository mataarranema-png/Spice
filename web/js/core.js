/* Spice · แกนกลางฝั่งหน้าเว็บ — เรียก API, แจ้งเตือน, ตัวช่วยจัดรูปแบบ */

const Spice = {
  state: {
    me: null,
    workers: [],
    summary: {},
    jobs: [],
    models: [],
    stats: {},
    drive: null,
    route: "overview",
  },
};

/* ── เรียก API ─────────────────────────────────────────────── */
Spice.api = async function (path, options = {}) {
  const config = { headers: {}, credentials: "same-origin", ...options };
  if (config.body !== undefined && typeof config.body !== "string") {
    config.headers["Content-Type"] = "application/json";
    config.body = JSON.stringify(config.body);
    config.method = config.method || "POST";
  }
  const resp = await fetch(path, config);

  if (resp.status === 401) {
    location.href = "/";
    throw new Error("เซสชันหมดอายุ");
  }
  const isJson = (resp.headers.get("content-type") || "").includes("application/json");
  const data = isJson ? await resp.json() : await resp.text();
  if (!resp.ok) {
    const detail = (data && data.detail) || data || `HTTP ${resp.status}`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data;
};

Spice.get = (path) => Spice.api(path);
Spice.post = (path, body = {}) => Spice.api(path, { body });
Spice.del = (path) => Spice.api(path, { method: "DELETE" });

/* ── แจ้งเตือน ─────────────────────────────────────────────── */
Spice.toast = function (message, kind = "info", ms = 4200) {
  const icons = { info: "ℹ️", ok: "✅", warn: "⚠️", error: "❌" };
  const node = document.createElement("div");
  node.className = `toast toast--${kind}`;
  node.innerHTML = `<span>${icons[kind] || "ℹ️"}</span><span class="grow">${Spice.esc(message)}</span>`;
  document.getElementById("toasts").appendChild(node);
  setTimeout(() => {
    node.classList.add("out");
    setTimeout(() => node.remove(), 260);
  }, ms);
};

/* ── โมดัล ─────────────────────────────────────────────────── */
Spice.modal = function (html, { onOpen } = {}) {
  const slot = document.getElementById("modal-slot");
  slot.innerHTML = `<div class="overlay" data-close="1"><div class="modal">${html}</div></div>`;
  const overlay = slot.firstElementChild;
  overlay.addEventListener("click", (event) => {
    if (event.target.dataset.close) Spice.closeModal();
  });
  slot.querySelectorAll("[data-modal-close]").forEach((btn) => {
    btn.onclick = Spice.closeModal;
  });
  document.addEventListener("keydown", Spice._escClose);
  if (onOpen) onOpen(slot);
  return slot;
};
Spice.closeModal = function () {
  document.getElementById("modal-slot").innerHTML = "";
  document.removeEventListener("keydown", Spice._escClose);
};
Spice._escClose = (event) => {
  if (event.key === "Escape") Spice.closeModal();
};

/* ── ตัวช่วยจัดรูปแบบ ──────────────────────────────────────── */
Spice.esc = (value) =>
  String(value ?? "").replace(/[&<>"']/g, (char) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char])
  );

Spice.ago = function (timestamp) {
  if (!timestamp) return "—";
  const seconds = Math.max(0, Date.now() / 1000 - timestamp);
  if (seconds < 10) return "เมื่อครู่";
  if (seconds < 60) return `${Math.floor(seconds)} วินาทีที่แล้ว`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)} นาทีที่แล้ว`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} ชั่วโมงที่แล้ว`;
  return `${Math.floor(seconds / 86400)} วันที่แล้ว`;
};

Spice.clock = (timestamp) =>
  new Date(timestamp * 1000).toLocaleTimeString("th-TH", { hour12: false });

Spice.gb = function (mb) {
  if (!mb) return "—";
  return mb >= 1024 ? `${(mb / 1024).toFixed(1)} GB` : `${mb} MB`;
};

Spice.duration = function (seconds) {
  if (seconds === undefined || seconds === null) return "—";
  if (seconds < 60) return `${seconds.toFixed(1)} วิ`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes} นาที ${Math.round(seconds % 60)} วิ`;
};

Spice.JOB_STATUS = {
  queued:    { label: "รอคิว",   pill: "pill--info",    icon: "◷" },
  running:   { label: "กำลังรัน", pill: "pill--busy",    icon: "◐" },
  done:      { label: "เสร็จแล้ว", pill: "pill--online",  icon: "✓" },
  failed:    { label: "ล้มเหลว",  pill: "pill--danger",  icon: "✕" },
  cancelled: { label: "ยกเลิก",   pill: "pill--offline", icon: "—" },
};

Spice.PROBLEM_LABEL = {
  out_of_memory:   "หน่วยความจำ GPU ไม่พอ",
  needs_auth:      "โมเดลต้องขอสิทธิ์ก่อน",
  missing_package: "เครื่องขาดไลบรารี",
  disk_full:       "ดิสก์ของเครื่องเต็ม",
  device_fault:    "การ์ดจอของเครื่องมีปัญหา",
  missing_file:    "หาไฟล์ต้นทางไม่เจอ",
  network:         "เครือข่ายของเครื่องมีปัญหา",
  unknown:         "ปัญหาที่ยังไม่รู้จัก",
};

Spice.WORKER_STATUS = {
  idle:    { label: "ว่าง · พร้อมรับงาน", pill: "pill--online",  pulse: true },
  busy:    { label: "กำลังรันงาน",        pill: "pill--busy",    pulse: true },
  paused:  { label: "พักอยู่ · พังติดกัน", pill: "pill--danger",  pulse: false },
  offline: { label: "ออฟไลน์",            pill: "pill--offline", pulse: false },
};

/* ── บล็อกโค้ดพร้อมปุ่มคัดลอก ──────────────────────────────── */
Spice.codeBlock = function (text, id) {
  const key = id || `code-${Math.random().toString(36).slice(2, 8)}`;
  return `<div class="code" id="${key}">${Spice.esc(text)}<button class="code__copy"
     onclick="Spice.copy('${key}', this)">คัดลอก</button></div>`;
};

Spice.copy = async function (elementId, button) {
  const node = document.getElementById(elementId);
  const text = node.childNodes[0].textContent.trim();
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    // เบราว์เซอร์บางตัวห้ามใช้ clipboard API เมื่อไม่ได้อยู่บน https
    const helper = document.createElement("textarea");
    helper.value = text;
    document.body.appendChild(helper);
    helper.select();
    document.execCommand("copy");
    helper.remove();
  }
  button.textContent = "คัดลอกแล้ว ✓";
  button.classList.add("ok");
  setTimeout(() => {
    button.textContent = "คัดลอก";
    button.classList.remove("ok");
  }, 1800);
};

Spice.empty = (icon, title, hint = "") => `
  <div class="empty">
    <div class="empty__icon">${icon}</div>
    <div class="empty__title">${Spice.esc(title)}</div>
    ${hint ? `<div class="small">${hint}</div>` : ""}
  </div>`;

Spice.skeleton = (rows = 3) =>
  Array.from({ length: rows }, () => `<div class="skeleton" style="height:64px"></div>`).join("");


/* อายุที่เหลือของเครื่องที่ยืมมา — อ่านง่ายกว่าวินาทีดิบ ๆ */
Spice.lifeLeft = function (seconds) {
  if (seconds > 86400) return `${Math.round(seconds / 86400)} วัน`;
  if (seconds > 3600) return `${(seconds / 3600).toFixed(1)} ชั่วโมง`;
  if (seconds > 60) return `${Math.round(seconds / 60)} นาที`;
  return "ใกล้หมดแล้ว";
};
