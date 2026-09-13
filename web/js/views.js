/* Spice · หน้าจอทั้งหมดของแผงควบคุม */

Spice.views = {};

/* ═══ ภาพรวม ═══════════════════════════════════════════════ */
Spice.views.overview = async function () {
  const [stats, workersData, jobsData] = await Promise.all([
    Spice.get("/api/v1/stats"),
    Spice.get("/api/v1/workers"),
    Spice.get("/api/v1/jobs?limit=6"),
  ]);
  Spice.state.stats = stats;
  Spice.state.workers = workersData.workers;
  Spice.state.summary = workersData.summary;
  Spice.state.jobs = jobsData.jobs;

  const online = workersData.summary.online;
  const tile = (label, value, unit, icon) => `
    <div class="card stat">
      <div class="stat__icon">${icon}</div>
      <div class="stat__label">${label}</div>
      <div class="stat__value">${value}${unit ? `<small>${unit}</small>` : ""}</div>
    </div>`;

  const connectBanner = online === 0 ? `
    <div class="card" style="border-color:rgba(255,138,61,0.3);background:var(--brand-soft)">
      <div class="row row--wrap row--between">
        <div style="max-width:640px">
          <h3>⚡ ยังไม่มีการ์ดจอในระบบ</h3>
          <p class="small" style="margin:0.4rem 0 0">
            เชื่อม Google Colab เข้ามาเพื่อยืมการ์ดจอ Tesla T4 มาใช้ฟรี —
            ใช้เวลาไม่ถึงหนึ่งนาที และวางคำสั่งแค่บรรทัดเดียว
          </p>
        </div>
        <button class="btn btn--primary" onclick="Spice.connectFlow()">เชื่อมเครื่อง Colab</button>
      </div>
    </div>` : "";

  return `
    <div class="view-head">
      <h2>สวัสดี ${Spice.esc((Spice.state.me?.name || "").split(" ")[0] || "")} 👋</h2>
      <p class="small dim">ภาพรวมของระบบทั้งหมดในที่เดียว — อัปเดตสดอัตโนมัติ</p>
    </div>

    ${connectBanner}

    <div class="grid grid--4">
      ${tile("การ์ดจอออนไลน์", online, ` / ${workersData.summary.total} เครื่อง`, "⚡")}
      ${tile("VRAM รวม", Spice.gb(workersData.summary.vram_total_mb), "", "▤")}
      ${tile("งานในคิว", stats.jobs_queued, stats.jobs_running ? ` +${stats.jobs_running} กำลังรัน` : "", "◷")}
      ${tile("งานสำเร็จ", stats.jobs_done, ` / ${stats.jobs_total}`, "✓")}
    </div>

    <div class="grid grid--split">
      <div class="card card--flush">
        <div class="card-head" style="padding:1.2rem 1.3rem 0;margin-bottom:0.8rem">
          <h3>☰ งานล่าสุด</h3>
          <button class="btn btn--sm btn--ghost" onclick="Spice.go('jobs')">ดูทั้งหมด →</button>
        </div>
        <div id="recent-jobs">${Spice.renderJobList(jobsData.jobs)}</div>
      </div>

      <div class="stack">
        <div class="card">
          <div class="card-head"><h3>⚡ เครื่องที่ยืมมา</h3>
            <button class="btn btn--sm" onclick="Spice.connectFlow()">+ เพิ่ม</button>
          </div>
          <div class="stack" style="gap:0.7rem">
            ${workersData.workers.length
              ? workersData.workers.slice(0, 3).map(Spice.renderWorkerMini).join("")
              : `<p class="small dim" style="margin:0">ยังไม่มีเครื่องในระบบ</p>`}
          </div>
        </div>

        <div class="card">
          <div class="card-head"><h3>⏱ ประสิทธิภาพ</h3></div>
          <div class="stack" style="gap:0.85rem">
            <div class="row row--between">
              <span class="small muted">เวลาเฉลี่ยต่องาน</span>
              <strong>${Spice.duration(stats.avg_seconds)}</strong>
            </div>
            <div class="row row--between">
              <span class="small muted">งานใน 24 ชั่วโมง</span>
              <strong>${stats.jobs_24h}</strong>
            </div>
            <div class="row row--between">
              <span class="small muted">เอกสารในคลังความรู้</span>
              <strong>${stats.vault_docs}</strong>
            </div>
          </div>
        </div>
      </div>
    </div>`;
};

/* ═══ เครื่อง GPU ══════════════════════════════════════════ */
Spice.views.gpu = async function () {
  const data = await Spice.get("/api/v1/workers");
  Spice.state.workers = data.workers;
  Spice.state.summary = data.summary;

  return `
    <div class="view-head row row--between row--wrap">
      <div>
        <h2>⚡ เครื่อง GPU ที่ยืมมา</h2>
        <p class="small dim">
          ออนไลน์ ${data.summary.online} จาก ${data.summary.total} เครื่อง ·
          VRAM รวม ${Spice.gb(data.summary.vram_total_mb)} ·
          ทำงานสะสม ${data.summary.jobs_done} งาน
        </p>
      </div>
      <button class="btn btn--primary" onclick="Spice.connectFlow()">+ เชื่อมเครื่องใหม่</button>
    </div>

    ${data.workers.length
      ? `<div class="grid grid--2">${data.workers.map(Spice.renderWorkerCard).join("")}</div>`
      : `<div class="card">${Spice.empty("⚡", "ยังไม่มีเครื่องในระบบ",
          `กด “เชื่อมเครื่องใหม่” เพื่อรับรหัสจับคู่ แล้วนำไปวางใน Google Colab`)}</div>`}

    <div class="card">
      <div class="card-head"><h3>💡 เคล็ดลับการยืมการ์ดจอ</h3></div>
      <div class="grid grid--2" style="gap:0.9rem">
        <div><strong class="small">เลือก T4 ก่อนเสมอ</strong>
          <p class="tiny dim" style="margin:0.2rem 0 0">ใน Colab: Runtime → Change runtime type → T4 GPU. บัญชีฟรีได้ประมาณ 16GB VRAM ซึ่งพอสำหรับโมเดล 7B แบบ 4bit</p></div>
        <div><strong class="small">เชื่อมหลายเครื่องพร้อมกันได้</strong>
          <p class="tiny dim" style="margin:0.2rem 0 0">เปิด Colab หลายบัญชี/หลายแท็บแล้วจับคู่ทีละเครื่อง ระบบจะกระจายงานในคิวให้เองอัตโนมัติ</p></div>
        <div><strong class="small">อย่าปิดแท็บ Colab</strong>
          <p class="tiny dim" style="margin:0.2rem 0 0">เซลล์ต้องรันค้างไว้ ถ้าปิดหรือ Colab ตัดการเชื่อมต่อ เครื่องจะขึ้นออฟไลน์ภายใน 75 วินาที และงานที่ค้างจะถูกโยนกลับเข้าคิว</p></div>
        <div><strong class="small">โหลดโมเดลครั้งแรกจะช้า</strong>
          <p class="tiny dim" style="margin:0.2rem 0 0">รอบแรกต้องดาวน์โหลดน้ำหนักโมเดล รอบถัดไปจะเร็วขึ้นมากเพราะเก็บไว้ในหน่วยความจำแล้ว</p></div>
      </div>
    </div>`;
};

Spice.renderWorkerCard = function (worker) {
  const status = Spice.WORKER_STATUS[worker.status] || Spice.WORKER_STATUS.offline;
  const vramPct = worker.vram_pct || 0;
  return `
    <div class="card gpu-card" data-status="${worker.status}">
      <div class="card-head" style="margin-bottom:0.9rem">
        <div style="min-width:0">
          <h3 style="overflow:hidden;text-overflow:ellipsis">${Spice.esc(worker.name)}</h3>
          <div class="tiny dim">${Spice.esc(worker.gpu_name)} · ${Spice.gb(worker.gpu_vram_mb)}</div>
        </div>
        <span class="pill ${status.pill}">
          <span class="dot ${status.pulse ? "dot--pulse" : ""}"></span>${status.label}
        </span>
      </div>

      <div class="stack" style="gap:0.75rem">
        <div>
          <div class="row row--between tiny muted" style="margin-bottom:0.3rem">
            <span>หน่วยความจำ VRAM</span>
            <span>${Spice.gb(worker.gpu_used_mb)} / ${Spice.gb(worker.gpu_vram_mb)}</span>
          </div>
          <div class="bar"><i style="width:${vramPct}%"></i></div>
        </div>
        <div>
          <div class="row row--between tiny muted" style="margin-bottom:0.3rem">
            <span>การใช้งาน GPU</span><span>${worker.gpu_util}%</span>
          </div>
          <div class="bar bar--mint"><i style="width:${worker.gpu_util}%"></i></div>
        </div>
      </div>

      <div class="row row--wrap" style="gap:0.4rem;margin-top:0.9rem">
        ${worker.drive_mounted ? `<span class="tag">🗄️ เมานต์ Drive แล้ว</span>` : ""}
        ${(worker.capabilities || []).map((cap) => `<span class="tag">${Spice.esc(cap)}</span>`).join("")}
        <span class="tag">ทำไปแล้ว ${worker.jobs_done} งาน</span>
      </div>

      <div class="row row--between" style="margin-top:1rem">
        <span class="tiny dim">สัญญาณล่าสุด ${Spice.ago(worker.last_seen_at)}</span>
        <button class="btn btn--sm btn--danger" onclick="Spice.revokeWorker('${worker.id}','${Spice.esc(worker.name)}')">
          ถอดเครื่อง
        </button>
      </div>
    </div>`;
};

Spice.renderWorkerMini = function (worker) {
  const status = Spice.WORKER_STATUS[worker.status] || Spice.WORKER_STATUS.offline;
  return `
    <div class="row" style="gap:0.65rem">
      <span class="pill ${status.pill}" style="padding:0.15rem 0.45rem">
        <span class="dot ${status.pulse ? "dot--pulse" : ""}"></span>
      </span>
      <div class="grow" style="min-width:0">
        <div class="small" style="font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
          ${Spice.esc(worker.gpu_name)}
        </div>
        <div class="tiny dim">${Spice.gb(worker.gpu_used_mb)} / ${Spice.gb(worker.gpu_vram_mb)} · ใช้งาน ${worker.gpu_util}%</div>
      </div>
    </div>`;
};

/* ═══ สั่งงาน AI ═══════════════════════════════════════════ */
Spice.views.studio = async function () {
  const data = await Spice.get("/api/v1/models");
  Spice.state.models = data.models;
  const selected = Spice.state.selectedModel && data.models.find((m) => m.id === Spice.state.selectedModel)
    ? Spice.state.selectedModel
    : data.models[0].id;
  Spice.state.selectedModel = selected;

  const KIND_LABEL = { text: "ข้อความ", image: "รูปภาพ", audio: "เสียง", embedding: "เวกเตอร์" };

  return `
    <div class="view-head">
      <h2>✦ สั่งงาน AI</h2>
      <p class="small dim">เลือกโมเดล พิมพ์สิ่งที่อยากได้ แล้วกดรัน — งานจะถูกส่งไปยังการ์ดจอที่ว่างอยู่</p>
    </div>

    <div class="grid grid--split-wide">
      <div class="card">
        <div class="card-head">
          <h3>เลือกโมเดล</h3>
          <span class="tiny dim">${data.best_vram_mb ? `VRAM สูงสุดที่มี ${Spice.gb(data.best_vram_mb)}` : "ยังไม่มีเครื่องออนไลน์"}</span>
        </div>
        <div class="stack" style="gap:0.6rem">
          ${data.models.map((model) => `
            <div class="model-card ${model.id === selected ? "selected" : ""}"
                 data-model="${model.id}" onclick="Spice.pickModel('${model.id}')">
              <div class="row row--between" style="gap:0.5rem">
                <div class="model-card__name">${Spice.esc(model.label)}</div>
                <span class="tag">${KIND_LABEL[model.kind] || model.kind}</span>
              </div>
              <div class="model-card__blurb">${Spice.esc(model.blurb)}</div>
              <div class="row row--wrap" style="gap:0.3rem">
                ${model.tags.map((tag) => `<span class="tag">${Spice.esc(tag)}</span>`).join("")}
                <span class="tag">ต้องใช้ ${Spice.gb(model.vram_mb)}</span>
                ${model.runnable_now
                  ? `<span class="pill pill--online" style="padding:0.08rem 0.45rem;font-size:0.7rem">รันได้เลย</span>`
                  : `<span class="pill pill--offline" style="padding:0.08rem 0.45rem;font-size:0.7rem">ยังไม่มีเครื่องที่ไหว</span>`}
              </div>
            </div>`).join("")}
        </div>
      </div>

      <div class="stack">
        <div class="card">
          <label class="field">
            <span>คำสั่งของคุณ</span>
            <textarea id="f-prompt" rows="7" placeholder="เช่น: สรุปเอกสารนี้เป็นข้อ ๆ ภาษาไทย แล้วเสนอ 3 ขั้นตอนถัดไป"></textarea>
          </label>

          <details style="margin-bottom:0.9rem">
            <summary class="small muted" style="cursor:pointer;user-select:none">⚙ ตัวเลือกขั้นสูง</summary>
            <div style="padding-top:0.9rem">
              <label class="field">
                <span>คำสั่งระบบ (บอกบุคลิก/กติกาให้โมเดล)</span>
                <textarea id="f-system" rows="2" placeholder="คุณคือผู้ช่วยที่ตอบเป็นภาษาไทย กระชับ ตรงประเด็น"></textarea>
              </label>
              <div class="grid grid--2" style="gap:0.9rem">
                <label class="field">
                  <span>ความยาวคำตอบสูงสุด · <b id="v-tokens">512</b> โทเคน</span>
                  <input type="range" id="f-tokens" min="64" max="4096" step="64" value="512"
                         oninput="document.getElementById('v-tokens').textContent=this.value">
                </label>
                <label class="field">
                  <span>ความสร้างสรรค์ · <b id="v-temp">0.7</b></span>
                  <input type="range" id="f-temp" min="0" max="1.5" step="0.05" value="0.7"
                         oninput="document.getElementById('v-temp').textContent=this.value">
                </label>
                <label class="field">
                  <span>ไฟล์ต้นทางใน Drive</span>
                  <input type="text" id="f-in" placeholder="gdrive:docs/รายงาน.txt">
                </label>
                <label class="field">
                  <span>บันทึกผลลงโฟลเดอร์ Drive</span>
                  <input type="text" id="f-out" placeholder="gdrive:spice/outputs">
                </label>
              </div>
              <label class="field" style="margin:0">
                <span>ลำดับความสำคัญ (1 = ด่วนที่สุด)</span>
                <select id="f-priority">
                  <option value="1">1 · ด่วนมาก แซงทุกงาน</option>
                  <option value="5" selected>5 · ปกติ</option>
                  <option value="9">9 · ทำตอนว่าง</option>
                </select>
              </label>
            </div>
          </details>

          <div class="row row--between row--wrap">
            <span class="tiny dim" id="run-hint"></span>
            <button class="btn btn--primary btn--lg" id="run-btn" onclick="Spice.submitJob()">
              ✦ ส่งเข้าคิวรัน
            </button>
          </div>
        </div>

        <div id="live-job"></div>
      </div>
    </div>`;
};

Spice.pickModel = function (modelId) {
  Spice.state.selectedModel = modelId;
  document.querySelectorAll(".model-card").forEach((card) => {
    card.classList.toggle("selected", card.dataset.model === modelId);
  });
  const model = Spice.state.models.find((m) => m.id === modelId);
  const hint = document.getElementById("run-hint");
  if (hint && model) {
    hint.textContent = model.runnable_now
      ? `พร้อมรัน ${model.label} บนเครื่องที่ออนไลน์อยู่`
      : `⚠ ยังไม่มีเครื่องที่ VRAM ถึง ${Spice.gb(model.vram_mb)} — งานจะรอในคิวจนกว่าจะมีเครื่องที่ไหว`;
  }
};

Spice.submitJob = async function () {
  const button = document.getElementById("run-btn");
  const prompt = document.getElementById("f-prompt").value.trim();
  const driveIn = document.getElementById("f-in").value.trim();
  if (!prompt && !driveIn) {
    Spice.toast("ใส่คำสั่งหรือระบุไฟล์ใน Drive อย่างน้อยหนึ่งอย่าง", "warn");
    return;
  }

  button.disabled = true;
  button.innerHTML = `<span class="spinner"></span> กำลังส่ง…`;
  try {
    const body = {
      model: Spice.state.selectedModel,
      prompt,
      system: document.getElementById("f-system").value.trim(),
      max_tokens: Number(document.getElementById("f-tokens").value),
      temperature: Number(document.getElementById("f-temp").value),
      priority: Number(document.getElementById("f-priority").value),
      drive_input: driveIn,
      drive_output: document.getElementById("f-out").value.trim(),
    };
    const result = await Spice.post("/api/v1/jobs", body);
    Spice.state.watchJob = result.job_id;
    Spice.toast(result.hint || "ส่งงานเข้าคิวแล้ว", result.hint ? "warn" : "ok");
    await Spice.renderLiveJob(result.job_id);
  } catch (error) {
    Spice.toast(error.message, "error");
  } finally {
    button.disabled = false;
    button.innerHTML = "✦ ส่งเข้าคิวรัน";
  }
};

Spice.renderLiveJob = async function (jobId) {
  const slot = document.getElementById("live-job");
  if (!slot) return;
  const { job, log, worker } = await Spice.get(`/api/v1/jobs/${jobId}`);
  const status = Spice.JOB_STATUS[job.status] || Spice.JOB_STATUS.queued;
  const pending = job.status === "queued" || job.status === "running";

  slot.innerHTML = `
    <div class="card">
      <div class="card-head">
        <h3>${status.icon} ${Spice.esc(job.title)}</h3>
        <span class="pill ${status.pill}">
          <span class="dot ${pending ? "dot--pulse" : ""}"></span>${status.label}
        </span>
      </div>
      <div class="bar ${job.status === "queued" ? "bar--indeterminate" : ""}" style="margin-bottom:0.9rem">
        <i style="width:${Math.round((job.progress || 0) * 100)}%"></i>
      </div>
      <div class="row row--wrap tiny dim" style="gap:0.9rem;margin-bottom:0.9rem">
        <span>โมเดล ${Spice.esc(job.model)}</span>
        ${worker ? `<span>เครื่อง ${Spice.esc(worker.name)}</span>` : `<span>ยังไม่มีเครื่องรับงาน</span>`}
        ${job.duration !== undefined ? `<span>ใช้เวลา ${Spice.duration(job.duration)}</span>` : ""}
      </div>
      ${job.result ? `<div class="result">${Spice.renderResult(job)}</div>` : ""}
      ${job.error ? `<div class="result" style="color:var(--danger)">${Spice.esc(job.error)}</div>` : ""}
      <details ${pending ? "open" : ""} style="margin-top:0.8rem">
        <summary class="small muted" style="cursor:pointer">บันทึกการทำงาน (${log.length})</summary>
        <div class="log" style="margin-top:0.6rem">${Spice.renderLog(log)}</div>
      </details>
    </div>`;
};

Spice.renderResult = function (job) {
  if (job.kind === "image" && job.result.startsWith("data:image")) {
    return `<img src="${job.result}" alt="ผลลัพธ์ที่โมเดลสร้าง">`;
  }
  return Spice.esc(job.result);
};

Spice.renderLog = (log) =>
  log.length
    ? log.map((entry) => `
        <div class="log__line" data-level="${entry.level}">
          <span class="log__time">${Spice.clock(entry.ts)}</span>
          <span>${Spice.esc(entry.message)}</span>
        </div>`).join("")
    : `<div class="dim tiny">ยังไม่มีบันทึก</div>`;

/* ═══ งานทั้งหมด ═══════════════════════════════════════════ */
Spice.views.jobs = async function () {
  const data = await Spice.get("/api/v1/jobs?limit=100");
  Spice.state.jobs = data.jobs;
  const counts = data.counts || {};
  const chip = (key, label) =>
    `<span class="pill ${key ? (Spice.JOB_STATUS[key]?.pill || "") : "pill--brand"}"
      style="cursor:pointer" onclick="Spice.filterJobs('${key}')">${label} ${key ? (counts[key] || 0) : data.jobs.length}</span>`;

  return `
    <div class="view-head">
      <h2>☰ งานทั้งหมด</h2>
      <p class="small dim">กดที่รายการเพื่อดูผลลัพธ์และบันทึกการทำงานแบบเต็ม</p>
    </div>
    <div class="row row--wrap" style="gap:0.45rem">
      ${chip("", "ทั้งหมด")}${chip("queued", "รอคิว")}${chip("running", "กำลังรัน")}
      ${chip("done", "เสร็จแล้ว")}${chip("failed", "ล้มเหลว")}
    </div>
    <div class="card card--flush" id="jobs-list">${Spice.renderJobList(data.jobs)}</div>`;
};

Spice.filterJobs = function (status) {
  const jobs = status ? Spice.state.jobs.filter((job) => job.status === status) : Spice.state.jobs;
  document.getElementById("jobs-list").innerHTML = Spice.renderJobList(jobs);
};

Spice.renderJobList = function (jobs) {
  if (!jobs.length) {
    return Spice.empty("☰", "ยังไม่มีงานในรายการนี้", "ไปที่หน้า “สั่งงาน AI” เพื่อเริ่มงานแรก");
  }
  return jobs.map((job) => {
    const status = Spice.JOB_STATUS[job.status] || Spice.JOB_STATUS.queued;
    const pending = job.status === "running" || job.status === "queued";
    return `
      <div class="job" onclick="Spice.openJob('${job.id}')">
        <span class="pill ${status.pill}" style="min-width:86px;justify-content:center">
          <span class="dot ${pending ? "dot--pulse" : ""}"></span>${status.label}
        </span>
        <div class="job__body">
          <div class="job__title">${Spice.esc(job.title)}</div>
          <div class="job__meta">
            ${Spice.esc(job.model)} · ${Spice.ago(job.created_at)}
            ${job.duration !== undefined ? ` · ${Spice.duration(job.duration)}` : ""}
          </div>
          ${job.status === "running"
            ? `<div class="bar" style="margin-top:0.4rem"><i style="width:${Math.round(job.progress * 100)}%"></i></div>`
            : ""}
        </div>
        <span class="dim">›</span>
      </div>`;
  }).join("");
};

Spice.openJob = async function (jobId) {
  const { job, log, worker } = await Spice.get(`/api/v1/jobs/${jobId}`);
  const status = Spice.JOB_STATUS[job.status] || Spice.JOB_STATUS.queued;
  const canCancel = job.status === "queued" || job.status === "running";
  Spice.state.openJob = jobId;

  Spice.modal(`
    <div class="card-head">
      <div style="min-width:0">
        <h3>${status.icon} ${Spice.esc(job.title)}</h3>
        <div class="tiny dim">${job.id} · ${Spice.esc(job.model)}</div>
      </div>
      <span class="pill ${status.pill}">${status.label}</span>
    </div>

    <div class="bar" style="margin-bottom:1rem"><i style="width:${Math.round((job.progress || 0) * 100)}%"></i></div>

    <div class="grid grid--3" style="gap:0.7rem;margin-bottom:1rem">
      <div><div class="tiny dim">เครื่องที่รัน</div><strong class="small">${worker ? Spice.esc(worker.name) : "—"}</strong></div>
      <div><div class="tiny dim">ใช้เวลา</div><strong class="small">${Spice.duration(job.duration)}</strong></div>
      <div><div class="tiny dim">ส่งเมื่อ</div><strong class="small">${Spice.ago(job.created_at)}</strong></div>
    </div>

    ${job.payload?.prompt ? `
      <div class="tiny dim" style="margin-bottom:0.3rem">คำสั่งที่ส่งไป</div>
      <div class="code" style="margin-bottom:1rem;max-height:150px;overflow:auto;padding-right:1rem">${Spice.esc(job.payload.prompt)}</div>` : ""}

    ${job.result ? `
      <div class="tiny dim" style="margin-bottom:0.3rem">ผลลัพธ์</div>
      <div class="result" style="margin-bottom:1rem">${Spice.renderResult(job)}</div>` : ""}

    ${job.error ? `
      <div class="tiny dim" style="margin-bottom:0.3rem">ข้อผิดพลาด</div>
      <div class="result" style="color:var(--danger);margin-bottom:1rem">${Spice.esc(job.error)}</div>` : ""}

    <div class="tiny dim" style="margin-bottom:0.3rem">บันทึกการทำงาน</div>
    <div class="log">${Spice.renderLog(log)}</div>

    <div class="row row--between" style="margin-top:1.2rem">
      ${canCancel
        ? `<button class="btn btn--danger btn--sm" onclick="Spice.cancelJob('${job.id}')">ยกเลิกงานนี้</button>`
        : `<span class="tiny dim">งานจบแล้ว</span>`}
      <button class="btn btn--sm" data-modal-close>ปิด</button>
    </div>`);
};

Spice.cancelJob = async function (jobId) {
  try {
    await Spice.post(`/api/v1/jobs/${jobId}/cancel`);
    Spice.toast("ยกเลิกงานแล้ว", "ok");
    Spice.closeModal();
    Spice.refresh();
  } catch (error) {
    Spice.toast(error.message, "error");
  }
};

/* ═══ Drive & rclone ═══════════════════════════════════════ */
Spice.views.drive = async function () {
  const status = await Spice.get("/api/v1/drive/status");
  Spice.state.drive = status;

  if (!status.connected || !status.has_drive_scope) {
    return `
      <div class="view-head"><h2>🗄️ Google Drive &amp; rclone</h2></div>
      <div class="card">
        ${Spice.empty("🔗", "ยังไม่ได้เชื่อม Google Drive",
          `ให้สิทธิ์เข้าถึง Drive เพื่อให้ระบบสร้างไฟล์ตั้งค่า rclone ให้อัตโนมัติ<br>
           เครื่อง Colab จะเมานต์ไดรฟ์ของคุณได้เองโดยไม่ต้องพิมพ์คำสั่งใด ๆ`)}
        <div class="center">
          <a class="btn btn--primary" href="/auth/google/login?drive=1&next=/app">เชื่อม Google Drive</a>
        </div>
      </div>`;
  }

  const quota = status.quota || {};
  const preview = await Spice.get("/api/v1/drive/rclone/preview").catch(() => null);

  return `
    <div class="view-head">
      <h2>🗄️ Google Drive &amp; rclone</h2>
      <p class="small dim">เชื่อมแล้วในชื่อ ${Spice.esc(status.drive_user || "")} · remote ชื่อ <code>${status.rclone_remote}</code></p>
    </div>

    <div class="grid grid--2">
      <div class="card">
        <div class="card-head"><h3>พื้นที่เก็บข้อมูล</h3>
          <span class="pill pill--online"><span class="dot"></span>เชื่อมแล้ว</span>
        </div>
        ${quota.unlimited
          ? `<div class="stat__value">ไม่จำกัด<small>ใช้ไป ${quota.usage_gb} GB</small></div>`
          : `<div class="stat__value">${quota.usage_gb} <small>/ ${quota.limit_gb} GB</small></div>
             <div class="bar" style="margin-top:0.7rem"><i style="width:${quota.used_pct || 0}%"></i></div>
             <div class="tiny dim" style="margin-top:0.4rem">ใช้ไปแล้ว ${quota.used_pct || 0}% ของพื้นที่ทั้งหมด</div>`}
      </div>

      <div class="card">
        <div class="card-head"><h3>ไฟล์ตั้งค่า rclone</h3></div>
        <p class="small">ระบบสร้างให้จากสิทธิ์ที่คุณอนุญาตไว้แล้ว — เครื่อง Colab ดึงไปใช้เองอัตโนมัติ ไม่ต้องรัน <code>rclone config</code></p>
        <div class="row row--wrap" style="gap:0.5rem">
          <a class="btn btn--primary btn--sm" href="/api/v1/drive/rclone.conf">⬇ ดาวน์โหลด rclone.conf</a>
          <button class="btn btn--sm" onclick="Spice.showRcloneConf()">ดูการตั้งค่า</button>
        </div>
        <p class="tiny dim" style="margin:0.8rem 0 0">
          ⚠️ ไฟล์นี้มีโทเคนเข้าถึง Drive ของคุณ อย่าแชร์ให้ใคร และอย่าอัปโหลดขึ้นที่สาธารณะ
        </p>
      </div>
    </div>

    ${preview ? `
      <div class="card">
        <div class="card-head"><h3>⌘ คำสั่งที่ใช้บ่อย</h3></div>
        <div class="stack" style="gap:0.8rem">
          ${preview.commands.map((item) => `
            <div>
              <div class="small" style="font-weight:600;margin-bottom:0.3rem">${Spice.esc(item.label)}</div>
              ${Spice.codeBlock(item.cmd)}
            </div>`).join("")}
        </div>
      </div>` : ""}

    <div class="card">
      <div class="card-head">
        <h3>📁 ไฟล์ใน Drive</h3>
        <div class="row" style="gap:0.4rem">
          <input type="text" id="drive-q" placeholder="ค้นหาไฟล์…" style="width:220px"
                 onkeydown="if(event.key==='Enter')Spice.browseDrive()">
          <button class="btn btn--sm" onclick="Spice.browseDrive()">ค้นหา</button>
        </div>
      </div>
      <div id="drive-files">${Spice.skeleton(3)}</div>
    </div>`;
};

Spice.browseDrive = async function () {
  const slot = document.getElementById("drive-files");
  const query = (document.getElementById("drive-q") || {}).value || "";
  slot.innerHTML = Spice.skeleton(3);
  try {
    const data = await Spice.get(`/api/v1/drive/files?q=${encodeURIComponent(query)}&limit=25`);
    slot.innerHTML = data.files.length
      ? data.files.map((file) => `
          <div class="job" style="cursor:default">
            <span style="font-size:1.1rem">${file.is_folder ? "📁" : "📄"}</span>
            <div class="job__body">
              <div class="job__title">${Spice.esc(file.name)}</div>
              <div class="job__meta">${file.size_mb ? file.size_mb + " MB · " : ""}${Spice.esc(file.rclone_path)}</div>
            </div>
            <button class="btn btn--sm btn--ghost" onclick="Spice.useInStudio('${Spice.esc(file.rclone_path)}')">ใช้ในงาน</button>
          </div>`).join("")
      : Spice.empty("📁", "ไม่พบไฟล์", "ลองเปลี่ยนคำค้นหา");
  } catch (error) {
    slot.innerHTML = Spice.empty("⚠️", "อ่านรายการไฟล์ไม่สำเร็จ", Spice.esc(error.message));
  }
};

Spice.useInStudio = function (rclonePath) {
  Spice.state.pendingDriveInput = rclonePath;
  Spice.toast(`จะใช้ ${rclonePath} เป็นไฟล์ต้นทาง`, "ok");
  Spice.go("studio");
};

Spice.showRcloneConf = async function () {
  const preview = await Spice.get("/api/v1/drive/rclone/preview");
  Spice.modal(`
    <h3>ไฟล์ตั้งค่า rclone ของคุณ</h3>
    <p class="small">ปิดบังส่วนที่เป็นความลับไว้ — กดดาวน์โหลดเพื่อเอาไฟล์จริง</p>
    ${Spice.codeBlock(preview.config_masked)}
    <div class="row row--between" style="margin-top:1rem">
      <a class="btn btn--primary btn--sm" href="/api/v1/drive/rclone.conf">⬇ ดาวน์โหลดไฟล์จริง</a>
      <button class="btn btn--sm" data-modal-close>ปิด</button>
    </div>`);
};

/* ═══ คลังความรู้ ══════════════════════════════════════════ */
Spice.views.vault = async function () {
  const data = await Spice.get("/api/v1/vault/collections");
  return `
    <div class="view-head">
      <h2>🧠 คลังความรู้ (Vault)</h2>
      <p class="small dim">เก็บเอกสารไว้ค้นแบบใกล้เคียง รองรับภาษาไทยที่ไม่เว้นวรรค — ใช้ได้ทันทีโดยไม่ต้องมี GPU</p>
    </div>

    <div class="grid grid--split-wide">
      <div class="card">
        <div class="card-head"><h3>เพิ่มเอกสาร</h3></div>
        <label class="field">
          <span>ชื่อเรื่อง (ไม่ใส่ก็ได้)</span>
          <input type="text" id="v-title" placeholder="บันทึกประชุมทีม 12 ก.ย.">
        </label>
        <label class="field">
          <span>เนื้อหา</span>
          <textarea id="v-text" rows="6" placeholder="วางข้อความที่อยากให้ระบบจำไว้…"></textarea>
        </label>
        <label class="field">
          <span>หมวดหมู่</span>
          <input type="text" id="v-collection" value="default" placeholder="default">
        </label>
        <button class="btn btn--primary btn--block" onclick="Spice.addDoc()">+ เพิ่มเข้าคลัง</button>

        ${data.collections.length ? `
          <div style="margin-top:1.2rem">
            <div class="tiny dim" style="margin-bottom:0.45rem">หมวดหมู่ที่มีอยู่</div>
            <div class="row row--wrap" style="gap:0.35rem">
              ${data.collections.map((item) =>
                `<span class="tag">${Spice.esc(item.collection)} · ${item.docs}</span>`).join("")}
            </div>
          </div>` : ""}
      </div>

      <div class="card">
        <div class="card-head">
          <h3>ค้นหาความรู้</h3>
          <span class="tag" title="ค้นด้วยความคล้ายของตัวอักษร — จะกลายเป็นค้นเชิงความหมายเต็มรูปแบบเมื่อทำ embedding ด้วยโมเดล BGE-M3">โหมดในเครื่อง</span>
        </div>
        <div class="row" style="gap:0.5rem;margin-bottom:1rem">
          <input type="text" id="v-query" class="grow" placeholder="ถามเป็นภาษาคนได้เลย…"
                 onkeydown="if(event.key==='Enter')Spice.searchVault()">
          <button class="btn btn--primary" onclick="Spice.searchVault()">ค้นหา</button>
        </div>
        <div id="vault-results">${Spice.empty("🔎", "พิมพ์คำค้นเพื่อเริ่มค้นหา")}</div>
      </div>
    </div>`;
};

Spice.addDoc = async function () {
  const text = document.getElementById("v-text").value.trim();
  if (!text) return Spice.toast("ใส่เนื้อหาก่อนนะ", "warn");
  try {
    await Spice.post("/api/v1/vault/docs", {
      text,
      title: document.getElementById("v-title").value.trim(),
      collection: document.getElementById("v-collection").value.trim() || "default",
    });
    document.getElementById("v-text").value = "";
    document.getElementById("v-title").value = "";
    Spice.toast("เพิ่มเข้าคลังแล้ว", "ok");
    Spice.refresh();
  } catch (error) {
    Spice.toast(error.message, "error");
  }
};

Spice.searchVault = async function () {
  const query = document.getElementById("v-query").value.trim();
  const slot = document.getElementById("vault-results");
  if (!query) return;
  slot.innerHTML = Spice.skeleton(2);
  try {
    const data = await Spice.post("/api/v1/vault/search", { query, top_k: 8 });
    slot.innerHTML = data.hits.length
      ? data.hits.map((hit) => `
          <div class="card" style="margin-bottom:0.6rem;padding:0.9rem 1rem">
            <div class="row row--between" style="gap:0.5rem;margin-bottom:0.3rem">
              <strong class="small">${Spice.esc(hit.title)}</strong>
              <span class="tag">ความใกล้เคียง ${Math.round(Math.max(0, hit.score) * 100)}%</span>
            </div>
            <p class="small dim" style="margin:0">${Spice.esc(hit.text.slice(0, 220))}${hit.text.length > 220 ? "…" : ""}</p>
            <div class="row row--between" style="margin-top:0.5rem">
              <span class="tag">${Spice.esc(hit.collection)}</span>
              <button class="btn btn--sm btn--ghost" onclick="Spice.deleteDoc('${hit.id}')">ลบ</button>
            </div>
          </div>`).join("")
      : Spice.empty("🔎", "ไม่พบเอกสารที่ใกล้เคียง", "ลองใช้คำอื่น หรือเพิ่มเอกสารเข้าคลังก่อน");
  } catch (error) {
    slot.innerHTML = Spice.empty("⚠️", "ค้นหาไม่สำเร็จ", Spice.esc(error.message));
  }
};

Spice.deleteDoc = async function (docId) {
  await Spice.del(`/api/v1/vault/docs/${docId}`);
  Spice.toast("ลบเอกสารแล้ว", "ok");
  Spice.searchVault();
};

/* ═══ ตั้งค่า ══════════════════════════════════════════════ */
Spice.views.settings = async function () {
  const me = Spice.state.me;
  const initial = (me.name || me.email)[0].toUpperCase();
  return `
    <div class="view-head"><h2>⚙ ตั้งค่า</h2></div>

    <div class="card">
      <div class="card-head"><h3>บัญชีของคุณ</h3></div>
      <div class="row" style="gap:1rem">
        ${me.picture
          ? `<img class="avatar" style="width:52px;height:52px" src="${Spice.esc(me.picture)}" alt="">`
          : `<div class="avatar" style="width:52px;height:52px;font-size:1.2rem">${initial}</div>`}
        <div>
          <div style="font-weight:650">${Spice.esc(me.name)}</div>
          <div class="small dim">${Spice.esc(me.email)}</div>
          <div class="row" style="gap:0.35rem;margin-top:0.35rem">
            <span class="tag">สิทธิ์: ${me.role === "owner" ? "เจ้าของระบบ" : "สมาชิก"}</span>
            <span class="tag">เข้าร่วม ${Spice.ago(me.member_since)}</span>
          </div>
        </div>
      </div>
    </div>

    <div class="grid grid--2">
      <div class="card">
        <div class="card-head"><h3>สิทธิ์ Google</h3></div>
        <div class="stack" style="gap:0.6rem">
          <div class="row row--between">
            <span class="small muted">เชื่อม Google Drive</span>
            ${me.drive_connected
              ? `<span class="pill pill--online"><span class="dot"></span>เชื่อมแล้ว</span>`
              : `<span class="pill pill--offline">ยังไม่เชื่อม</span>`}
          </div>
          <div class="row row--between">
            <span class="small muted">โทเคนยังใช้ได้</span>
            <span class="tag">${me.drive_token_fresh ? "ใช่ (ต่ออายุอัตโนมัติ)" : "จะต่ออายุเมื่อใช้งานครั้งถัดไป"}</span>
          </div>
          <div class="tiny dim">${(me.drive_scopes || []).map((s) => s.split("/").pop()).join(" · ") || "—"}</div>
          <a class="btn btn--sm" href="/auth/google/login?drive=1&next=/app">ให้สิทธิ์ใหม่อีกครั้ง</a>
        </div>
      </div>

      <div class="card">
        <div class="card-head"><h3>ลักษณะหน้าจอ</h3></div>
        <div class="row row--between">
          <span class="small muted">ธีมสีของแอป</span>
          <button class="btn btn--sm" onclick="Spice.toggleTheme()">สลับสว่าง / มืด</button>
        </div>
        <div class="row row--between" style="margin-top:0.8rem">
          <span class="small muted">เอกสาร API ทั้งหมด</span>
          <a class="btn btn--sm btn--ghost" href="/docs" target="_blank" rel="noopener">เปิด /docs ↗</a>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-head"><h3>ออกจากระบบ</h3></div>
      <div class="row row--between row--wrap">
        <p class="small" style="margin:0">เครื่อง GPU ที่เชื่อมไว้จะยังทำงานต่อจนกว่าคุณจะถอดออกเอง</p>
        <button class="btn btn--danger btn--sm" onclick="Spice.logout()">ออกจากระบบ</button>
      </div>
    </div>`;
};
