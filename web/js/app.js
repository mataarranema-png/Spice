/* Spice · ตัวควบคุมหน้าเว็บ — เส้นทาง, การอัปเดตสด, การเชื่อมเครื่อง */

const ROUTES = {
  overview: { title: "ภาพรวม",              crumb: "สรุปสถานะระบบทั้งหมด" },
  studio:   { title: "สั่งงาน AI",           crumb: "เลือกโมเดลแล้วส่งงานเข้าคิว" },
  chat:     { title: "แชท",                  crumb: "คุยต่อเนื่องโดยโมเดลจำบริบทเดิมได้" },
  jobs:     { title: "งานทั้งหมด",           crumb: "ประวัติและผลลัพธ์ของทุกงาน" },
  gpu:      { title: "เครื่อง GPU",          crumb: "การ์ดจอที่ยืมมาและสถานะสด" },
  drive:    { title: "Drive & rclone",      crumb: "เชื่อม Google Drive เข้ากับเครื่องที่ยืมมา" },
  hub:      { title: "คลังโมเดล",            crumb: "ดึงโมเดลจาก Hugging Face มาใช้เองได้ทุกตัว" },
  insights: { title: "สถิติ & ตั้งเวลา",     crumb: "เวลาการ์ดจอหมดไปกับอะไร และงานที่ระบบทำเอง" },
  vault:    { title: "คลังความรู้",          crumb: "ค้นหาเอกสารด้วยความหมาย" },
  settings: { title: "ตั้งค่า",              crumb: "บัญชี สิทธิ์ และการแสดงผล" },
};

/* ── เส้นทาง ───────────────────────────────────────────────── */
Spice.go = function (route) {
  if (!ROUTES[route]) route = "overview";
  Spice.state.route = route;
  location.hash = route;

  document.querySelectorAll(".nav-item").forEach((item) => {
    item.classList.toggle("active", item.dataset.route === route);
  });
  document.getElementById("page-title").textContent = ROUTES[route].title;
  document.getElementById("page-crumb").textContent = ROUTES[route].crumb;
  document.getElementById("sidebar").classList.remove("open");
  document.querySelector(".scrim")?.remove();

  Spice.render();
};

Spice.render = async function () {
  const slot = document.getElementById("view");
  const route = Spice.state.route;
  slot.innerHTML = `<div class="card">${Spice.skeleton(4)}</div>`;
  try {
    slot.innerHTML = await Spice.views[route]();
    slot.classList.remove("page-enter");
    void slot.offsetWidth;          // บังคับให้เบราว์เซอร์เล่นแอนิเมชันซ้ำ
    slot.classList.add("page-enter");
    Spice.afterRender(route);
  } catch (error) {
    slot.innerHTML = `<div class="card">${Spice.empty("⚠️", "โหลดหน้านี้ไม่สำเร็จ", Spice.esc(error.message))}</div>`;
  }
};

/* งานที่ต้องทำหลังวาดหน้าเสร็จ */
Spice.afterRender = function (route) {
  if (route === "studio") {
    Spice.pickModel(Spice.state.selectedModel || "auto");
    if (Spice.state.pendingDriveInput) {
      document.getElementById("f-in").value = Spice.state.pendingDriveInput;
      Spice.state.pendingDriveInput = null;
    }
    if (Spice.state.pendingPrompt) {
      document.getElementById("f-prompt").value = Spice.state.pendingPrompt;
      Spice.state.pendingPrompt = null;
    }
    if (Spice.state.watchJob) Spice.renderLiveJob(Spice.state.watchJob);
  }
  if (route === "drive" && document.getElementById("drive-files")) {
    Spice.browseDrive();
  }
  if (route === "chat" && Spice.state.activeThread) {
    Spice.openThread(Spice.state.activeThread);
  }
  Spice.updateBadges();
};

/* วาดหน้าปัจจุบันใหม่แบบเบา ๆ (ใช้เมื่อมีเหตุการณ์สดเข้ามา) */
Spice.refresh = function () {
  clearTimeout(Spice._refreshTimer);
  Spice._refreshTimer = setTimeout(() => Spice.render(), 220);
};

Spice.updateBadges = function () {
  const online = Spice.state.summary?.online || 0;
  const active = (Spice.state.stats?.jobs_queued || 0) + (Spice.state.stats?.jobs_running || 0);
  const set = (id, value) => {
    const node = document.getElementById(id);
    if (!node) return;
    node.textContent = value;
    node.classList.toggle("hidden", !value);
  };
  set("badge-gpu", online);
  set("badge-jobs", active);
};

/* ── อัปเดตสดผ่าน SSE ──────────────────────────────────────── */
Spice.connectStream = function () {
  const pill = document.getElementById("live-pill");
  const source = new EventSource("/api/v1/stream");

  source.addEventListener("hello", () => {
    pill.className = "pill pill--online";
    pill.innerHTML = `<span class="dot dot--pulse"></span> อัปเดตสด`;
  });

  source.addEventListener("schedule", (event) => {
    const data = JSON.parse(event.data);
    Spice.toast("งานตั้งเวลาถึงกำหนด — ส่งเข้าคิวแล้ว", "info");
    if (["overview", "jobs", "insights"].includes(Spice.state.route)) Spice.refresh();
  });

  source.addEventListener("batch", () => {
    if (["overview", "jobs"].includes(Spice.state.route)) Spice.refresh();
  });

  source.addEventListener("thread", (event) => {
    const data = JSON.parse(event.data);
    if (Spice.state.route === "chat" && Spice.state.activeThread === data.thread_id) {
      Spice.state.pendingJob = null;
      Spice.state.liveText = "";
      Spice.openThread(data.thread_id);
    }
  });

  source.addEventListener("worker", (event) => {
    const data = JSON.parse(event.data);
    if (data.action === "joined") {
      Spice.toast(`เครื่องใหม่เข้าร่วมแล้ว: ${data.gpu_name || "GPU"} 🎉`, "ok");
      Spice.closeModal();
      Spice.refresh();
    } else if (data.action === "beat") {
      Spice.patchWorker(data);
    } else {
      Spice.refresh();
    }
  });

  source.addEventListener("job", (event) => {
    const data = JSON.parse(event.data);

    // คำตอบไหลมาทีละท่อน — ต่อเข้าฟองแชทหรือกล่องผลลัพธ์ทันที
    if (data.action === "token") {
      if (Spice.state.route === "chat" && Spice.state.pendingJob === data.job_id) {
        Spice.state.liveText = (Spice.state.liveText || "") + data.delta;
        Spice.showLiveBubble(Spice.state.liveText);
      } else if (Spice.state.route === "studio" && Spice.state.watchJob === data.job_id) {
        const box = document.querySelector("#live-job .result");
        if (box) {
          box.textContent += data.delta;
          box.scrollTop = box.scrollHeight;
        } else {
          Spice.renderLiveJob(data.job_id);
        }
      }
      return;         // สตรีมมาถี่มาก อย่าไปวาดหน้าใหม่ทั้งหน้า
    }

    if (data.action === "repaired") {
      Spice.toast(data.message, "warn", 8000);
    }

    // การโหวตกำลังทยอยเสร็จ — อัปเดตกล่องผลโหวตไปเรื่อย ๆ
    if (Spice.state.watchVote && Spice.state.route === "studio" &&
        ["finished", "queued"].includes(data.action)) {
      Spice.renderVote(Spice.state.watchVote);
    }

    if (data.action === "chained") {
      Spice.toast(`ขั้นที่ ${data.step}/${data.total} เริ่มแล้ว: ${data.title}`, "info");
      // ลูกโซ่เดินต่อ — ให้หน้าจอตามไปดูงานขั้นถัดไปแทน
      if (Spice.state.watchJob === data.parent_id) Spice.state.watchJob = data.job_id;
    }
    if (data.action === "recovered") {
      Spice.toast(data.message, "warn", 7000);
    }
    if (data.action === "finished") {
      if (data.from_cache) {
        Spice.toast("ตอบจากผลลัพธ์ที่เคยคำนวณไว้ — ไม่ได้ใช้ GPU", "ok");
      } else {
        Spice.toast(
          data.status === "done" ? `งานเสร็จแล้ว (${Spice.duration(data.duration)})` : "งานล้มเหลว — เปิดดูบันทึกได้",
          data.status === "done" ? "ok" : "error"
        );
      }
      if (Spice.state.route === "chat" && Spice.state.pendingJob === data.job_id) {
        Spice.state.pendingJob = null;
        Spice.state.liveText = "";
        Spice.openThread(Spice.state.activeThread);
        return;
      }
    }
    if (Spice.state.watchJob && data.job_id === Spice.state.watchJob && Spice.state.route === "studio") {
      Spice.renderLiveJob(Spice.state.watchJob);
    } else if (["jobs", "overview"].includes(Spice.state.route)) {
      Spice.refresh();
    }
    if (Spice.state.openJob === data.job_id && document.querySelector(".modal")) {
      Spice.openJob(data.job_id);
    }
  });

  source.onerror = () => {
    pill.className = "pill pill--offline";
    pill.innerHTML = `<span class="dot"></span> กำลังเชื่อมต่อใหม่…`;
    // EventSource ต่อใหม่ให้เองอยู่แล้ว จึงไม่ต้องปิดทิ้ง
  };

  Spice._stream = source;
};

/* อัปเดตตัวเลข GPU แบบไม่ต้องวาดหน้าใหม่ทั้งหน้า */
Spice.patchWorker = function (worker) {
  const index = Spice.state.workers.findIndex((item) => item.id === worker.id);
  if (index >= 0) Spice.state.workers[index] = { ...Spice.state.workers[index], ...worker };
  else Spice.state.workers.push(worker);

  if (Spice.state.route === "gpu") {
    const cards = document.querySelectorAll(".gpu-card");
    if (cards.length !== Spice.state.workers.length) return Spice.refresh();
    document.querySelector("#view .grid--2").innerHTML =
      Spice.state.workers.map(Spice.renderWorkerCard).join("");
  }
};

/* ── เชื่อมเครื่อง Colab ───────────────────────────────────── */
Spice.connectFlow = async function () {
  Spice.modal(`<div class="center" style="padding:1.4rem"><div class="spinner" style="margin:0 auto 0.8rem"></div>
    <div class="small muted">กำลังสร้างรหัสจับคู่…</div></div>`);
  try {
    const pair = await Spice.post("/api/v1/workers/pair", { label: "เครื่องใหม่" });
    const snippet = await Spice.get(
      `/api/v1/connect-snippet?pair_code=${encodeURIComponent(pair.pair_code)}`);
    Spice.state.connectTargets = snippet.targets;

    Spice.modal(`
      <h3>⚡ เชื่อมเครื่องเข้าระบบ</h3>
      <p class="small">เลือกว่าจะยืมการ์ดจอจากที่ไหน — หน้านี้จะรู้เองเมื่อเครื่องเข้าร่วมสำเร็จ</p>

      <div class="card" style="background:var(--brand-soft);border-color:rgba(255,138,61,0.25);margin-bottom:1.1rem">
        <div class="row row--between row--wrap" style="gap:0.8rem">
          <div>
            <div class="tiny dim">รหัสจับคู่ของคุณ</div>
            <div class="mono" style="font-size:1.7rem;font-weight:700;letter-spacing:0.12em;color:var(--brand)">
              ${pair.pair_code}
            </div>
          </div>
          <div class="center">
            <div class="tiny dim">หมดอายุใน</div>
            <div class="mono" id="pair-countdown" style="font-size:1.1rem;font-weight:600">15:00</div>
          </div>
        </div>
      </div>

      <div class="row row--wrap" style="gap:0.4rem;margin-bottom:1rem">
        ${snippet.targets.map((target, index) => `
          <button class="btn btn--sm ${index === 0 ? "btn--primary" : ""}"
                  data-target="${target.id}" onclick="Spice.pickTarget('${target.id}')">
            ${target.icon} ${Spice.esc(target.label)}
          </button>`).join("")}
      </div>

      <div id="target-panel"></div>

      <div class="row" style="gap:0.5rem;margin-top:1rem">
        <a class="btn btn--sm" id="target-link" href="https://colab.research.google.com/#create=true"
           target="_blank" rel="noopener">เปิด Google Colab ↗</a>
        <span class="grow"></span>
        <span class="row tiny dim"><span class="spinner"></span> กำลังรอเครื่องเข้าร่วม…</span>
      </div>

      <div class="tiny dim" style="margin-top:1rem;padding-top:0.8rem;border-top:1px solid var(--border)">
        รหัสนี้ใช้ได้ครั้งเดียว และผูกเครื่องเข้ากับบัญชีของคุณเท่านั้น
        เครื่องที่เชื่อมแล้วจะเข้าถึง Google Drive ของคุณผ่าน rclone ได้ —
        ใช้กับเครื่องที่คุณควบคุมเองเท่านั้น
      </div>

      <div class="row row--between" style="margin-top:1rem">
        <button class="btn btn--sm btn--ghost" onclick="Spice.connectFlow()">ขอรหัสใหม่</button>
        <button class="btn btn--sm" data-modal-close>ปิดหน้าต่าง</button>
      </div>`, {
      onOpen: () => {
        Spice.pickTarget(snippet.targets[0].id);
        Spice.startCountdown(pair.expires_in);
      },
    });
  } catch (error) {
    Spice.closeModal();
    Spice.toast(error.message, "error");
  }
};

Spice.pickTarget = function (targetId) {
  const target = (Spice.state.connectTargets || []).find((item) => item.id === targetId);
  if (!target) return;

  document.querySelectorAll("[data-target]").forEach((button) => {
    button.classList.toggle("btn--primary", button.dataset.target === targetId);
  });

  document.getElementById("target-panel").innerHTML = `
    <div class="tiny dim" style="margin-bottom:0.6rem">${Spice.esc(target.blurb)}</div>
    <ol class="small" style="padding-left:1.2rem;margin:0 0 0.8rem">
      ${target.steps.map((step) => `<li style="margin-bottom:0.3rem">${Spice.esc(step)}</li>`).join("")}
    </ol>
    ${Spice.codeBlock(target.command, `cmd-${target.id}`)}
    ${target.note ? `<div class="tiny dim" style="margin-top:0.6rem">💡 ${Spice.esc(target.note)}</div>` : ""}`;

  const link = document.getElementById("target-link");
  if (target.id === "colab") {
    link.href = "https://colab.research.google.com/#create=true";
    link.textContent = "เปิด Google Colab ↗";
    link.classList.remove("hidden");
  } else {
    link.classList.add("hidden");
  }
};

Spice.startCountdown = function (seconds) {
  clearInterval(Spice._countdown);
  const node = document.getElementById("pair-countdown");
  let left = seconds;
  Spice._countdown = setInterval(() => {
    left -= 1;
    if (!document.getElementById("pair-countdown")) return clearInterval(Spice._countdown);
    if (left <= 0) {
      clearInterval(Spice._countdown);
      node.textContent = "หมดอายุ";
      node.style.color = "var(--danger)";
      return;
    }
    const minutes = String(Math.floor(left / 60)).padStart(2, "0");
    node.textContent = `${minutes}:${String(left % 60).padStart(2, "0")}`;
  }, 1000);
};

Spice.revokeWorker = async function (workerId, name) {
  Spice.modal(`
    <h3>ถอดเครื่องออกจากระบบ?</h3>
    <p class="small">เครื่อง <strong>${Spice.esc(name)}</strong> จะใช้โทเคนเดิมไม่ได้อีก
       และจะเข้าถึง Google Drive ของคุณไม่ได้ทันที หากต้องการใช้อีกครั้งต้องจับคู่ใหม่</p>
    <div class="row row--between" style="margin-top:1.2rem">
      <button class="btn btn--sm" data-modal-close>ยกเลิก</button>
      <button class="btn btn--danger btn--sm" id="confirm-revoke">ยืนยันถอดเครื่อง</button>
    </div>`, {
    onOpen: (slot) => {
      slot.querySelector("#confirm-revoke").onclick = async () => {
        try {
          await Spice.del(`/api/v1/workers/${workerId}`);
          Spice.toast("ถอดเครื่องเรียบร้อย", "ok");
        } catch (error) {
          Spice.toast(error.message, "error");
        }
        Spice.closeModal();
        Spice.render();
      };
    },
  });
};

/* ── ธีมและบัญชี ───────────────────────────────────────────── */
Spice.toggleTheme = function () {
  const next = document.documentElement.dataset.theme === "light" ? "dark" : "light";
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem("spice-theme", next); } catch {}
};

Spice.logout = async function () {
  await Spice.post("/auth/logout");
  location.href = "/";
};

/* ── เริ่มทำงาน ────────────────────────────────────────────── */
Spice.boot = async function () {
  try {
    const saved = localStorage.getItem("spice-theme");
    if (saved) document.documentElement.dataset.theme = saved;
  } catch {}

  try {
    Spice.state.me = await Spice.get("/api/v1/me");
  } catch {
    location.href = "/";
    return;
  }

  const me = Spice.state.me;
  document.getElementById("user-name").textContent = me.name || me.email;
  document.getElementById("user-role").textContent =
    me.role === "owner" ? "เจ้าของระบบ" : "สมาชิก";
  const avatar = document.getElementById("user-avatar");
  if (me.picture) {
    avatar.outerHTML = `<img class="avatar" id="user-avatar" src="${Spice.esc(me.picture)}" alt="">`;
  } else {
    avatar.textContent = (me.name || me.email)[0].toUpperCase();
  }

  document.querySelectorAll(".nav-item").forEach((item) => {
    item.onclick = () => Spice.go(item.dataset.route);
  });
  document.getElementById("theme-btn").onclick = Spice.toggleTheme;
  document.getElementById("logout-btn").onclick = Spice.logout;
  document.getElementById("quick-run").onclick = () => Spice.go("studio");
  document.getElementById("menu-btn").onclick = () => {
    const sidebar = document.getElementById("sidebar");
    sidebar.classList.add("open");
    const scrim = document.createElement("div");
    scrim.className = "scrim";
    scrim.onclick = () => { sidebar.classList.remove("open"); scrim.remove(); };
    document.body.appendChild(scrim);
  };

  window.addEventListener("hashchange", () => {
    const route = location.hash.slice(1);
    if (route && route !== Spice.state.route) Spice.go(route);
  });

  Spice.connectStream();
  Spice.go(location.hash.slice(1) || "overview");

  // กันเหนียว: รีเฟรชเบา ๆ ทุก 30 วินาที เผื่อ SSE หลุดโดยไม่รู้ตัว
  setInterval(() => {
    if (["overview", "gpu"].includes(Spice.state.route) && !document.querySelector(".modal")) {
      Spice.render();
    }
  }, 30000);
};

document.addEventListener("DOMContentLoaded", Spice.boot);
