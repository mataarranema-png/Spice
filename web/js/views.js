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

        <div class="card card--brain">
          <div class="card-head"><h3>🧠 ความพร้อมของระบบ</h3></div>
          <div class="stack" style="gap:0.7rem">
            <div class="row row--between">
              <span class="small muted">โมเดลที่พร้อมรันทันที</span>
              <strong class="small">${(stats.warm_labels || []).length}</strong>
            </div>
            ${(stats.warm_labels || []).length ? `
              <div class="row row--wrap" style="gap:0.3rem">
                ${stats.warm_labels.map((label) =>
                  `<span class="pill pill--online" style="font-size:0.7rem">⚡ ${Spice.esc(label)}</span>`).join("")}
              </div>
              <div class="tiny dim">โมเดลเหล่านี้ค้างอยู่ใน VRAM แล้ว งานที่ใช้มันจะเริ่มได้ทันทีโดยไม่ต้องรอโหลด</div>`
              : `<div class="tiny dim">ยังไม่มีโมเดลค้างใน VRAM — งานแรกของแต่ละโมเดลจะใช้เวลาโหลดก่อน</div>`}
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
            <div class="row row--between">
              <span class="small muted">ตอบจากแคช (ไม่ใช้ GPU)</span>
              <strong>${stats.cache?.hits || 0} ครั้ง</strong>
            </div>
            ${stats.cache?.saved_seconds ? `
              <div class="tiny dim">ประหยัดเวลาการ์ดจอไปแล้วราว ${Spice.duration(stats.cache.saved_seconds)}</div>` : ""}
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
        ${(worker.capabilities || []).map((cap) =>
          `<span class="tag">${Spice.esc(Spice.KIND_LABEL[cap] || cap)}</span>`).join("")}
        <span class="tag">ทำไปแล้ว ${worker.jobs_done} งาน</span>
      </div>

      ${(worker.warm_labels || []).length ? `
        <div style="margin-top:0.8rem">
          <div class="tiny dim" style="margin-bottom:0.3rem">
            ⚡ โมเดลที่ค้างอยู่ใน VRAM — งานที่ใช้โมเดลเหล่านี้จะถูกส่งมาที่เครื่องนี้ก่อน
          </div>
          <div class="row row--wrap" style="gap:0.3rem">
            ${worker.warm_labels.map((label) =>
              `<span class="pill pill--online" style="font-size:0.7rem">${Spice.esc(label)}</span>`).join("")}
          </div>
        </div>` : ""}

      ${worker.life && worker.status !== "offline" ? `
        <div style="margin-top:0.8rem">
          <div class="row row--between tiny" style="margin-bottom:0.3rem">
            <span class="${worker.life.running_out ? "" : "dim"}"
                  style="${worker.life.running_out ? "color:var(--warn)" : ""}">
              ⏳ อายุที่เหลือโดยประมาณ</span>
            <span class="dim">${Spice.lifeLeft(worker.life.remaining_seconds)}</span>
          </div>
          <div class="bar ${worker.life.running_out ? "" : "bar--mint"}">
            <i style="width:${Math.round(
              100 * worker.life.remaining_seconds / Math.max(1, worker.life.lifetime_seconds))}%"></i>
          </div>
          <div class="tiny dim" style="margin-top:0.3rem">${Spice.esc(worker.life_note || "")}</div>
        </div>` : ""}

      ${worker.quarantined ? `
        <div class="notice" style="margin-top:0.8rem">
          ⏸ เครื่องนี้พังติดกันหลายงาน ระบบจึงพักไว้ชั่วคราวเพื่อไม่ให้ดูดงานทั้งคิวไปทำพัง
          — จะกลับมารับงานเองอัตโนมัติ
        </div>` : ""}

      <div class="row row--between" style="margin-top:1rem">
        <span class="tiny dim">สัญญาณล่าสุด ${Spice.ago(worker.last_seen_at)}${
          worker.jobs_failed ? ` · ล้มเหลว ${worker.jobs_failed} งาน` : ""}</span>
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
Spice.KIND_LABEL = { text: "ข้อความ", image: "รูปภาพ", audio: "เสียง", embedding: "เวกเตอร์" };

Spice.views.studio = async function () {
  const data = await Spice.get("/api/v1/models");
  Spice.state.models = data.models;
  if (Spice.state.selectedModel !== "auto" &&
      !data.models.find((m) => m.id === Spice.state.selectedModel)) {
    Spice.state.selectedModel = "auto";
  }
  Spice.state.selectedModel = Spice.state.selectedModel || "auto";

  return `
    <div class="view-head">
      <h2>✦ สั่งงาน AI</h2>
      <p class="small dim">พิมพ์สิ่งที่อยากได้เป็นภาษาคน — ระบบจะเลือกโมเดล ตั้งค่า และวางลำดับงานให้เอง</p>
    </div>

    <div class="card card--brain">
      <div class="card-head">
        <h3>🧠 บอกมาว่าอยากได้อะไร</h3>
        <span class="pill pill--brand" id="mode-pill">โหมดอัตโนมัติ</span>
      </div>

      <textarea id="f-prompt" rows="4" style="margin-bottom:0.8rem"
        placeholder="เช่น: ถอดเสียงไฟล์ประชุมใน Drive แล้วสรุปเป็นข้อ ๆ พร้อมสิ่งที่ต้องทำต่อ"></textarea>

      <div class="grid grid--2" style="gap:0.7rem;margin-bottom:0.9rem">
        <label class="field" style="margin:0">
          <span>ไฟล์ต้นทางใน Drive (ถ้ามี)</span>
          <input type="text" id="f-in" placeholder="gdrive:audio/meeting.m4a">
        </label>
        <label class="field" style="margin:0">
          <span>บันทึกผลลงโฟลเดอร์ Drive (ถ้าต้องการ)</span>
          <input type="text" id="f-out" placeholder="gdrive:spice/outputs">
        </label>
      </div>

      <div class="row row--between row--wrap" style="gap:0.6rem">
        <span class="tiny dim" id="run-hint">ระบบจะอ่านคำสั่งแล้วตัดสินใจให้ — กด “ดูแผนก่อน” เพื่อตรวจก่อนรันได้</span>
        <div class="row row--wrap" style="gap:0.5rem">
          <button class="btn btn--sm" onclick="Spice.previewPlan()">🔍 ดูแผนก่อน</button>
          <button class="btn btn--sm" onclick="Spice.submitVote()"
                  title="ถามซ้ำหลายรอบแล้วดูว่าคำตอบไหนสอดคล้องกันที่สุด">🗳 ถาม 3 รอบแล้วโหวต</button>
          <button class="btn btn--primary btn--lg" id="run-btn" onclick="Spice.submitJob()">✦ รันเลย</button>
        </div>
      </div>
    </div>

    <div id="plan-slot"></div>
    <div id="live-job"></div>

    <details class="card">
      <summary class="row row--between" style="cursor:pointer;user-select:none;list-style:none">
        <span><strong>🗂 งานชุด</strong>
          <span class="tiny dim">— สั่งครั้งเดียว ทำหลายรายการพร้อมกันทุกเครื่อง</span></span>
      </summary>
      <div style="padding-top:1.1rem">
        <label class="field">
          <span>คำสั่ง — ใส่ <code>{{item}}</code> ตรงที่จะให้แทนแต่ละรายการ</span>
          <textarea id="b-prompt" rows="2"
            placeholder="สรุปหัวข้อนี้เป็น 3 ข้อ: {{item}}"></textarea>
        </label>
        <label class="field">
          <span>รายการ (บรรทัดละหนึ่งอย่าง)</span>
          <textarea id="b-items" rows="4" placeholder="เศรษฐกิจไทย&#10;พลังงานสะอาด&#10;การศึกษา"></textarea>
        </label>
        <div class="row row--between row--wrap" style="gap:0.6rem">
          <label class="row" style="gap:0.4rem;font-size:0.85rem;color:var(--text-soft)">
            <input type="checkbox" id="b-drive" style="width:auto">
            แต่ละบรรทัดเป็นไฟล์ใน Drive
          </label>
          <button class="btn btn--primary" onclick="Spice.submitBatch()">ส่งทั้งชุด</button>
        </div>
        <div id="batch-slot" style="margin-top:1rem"></div>
      </div>
    </details>

    <details class="card" id="manual-box" ${Spice.state.selectedModel === "auto" ? "" : "open"}>
      <summary class="row row--between" style="cursor:pointer;user-select:none;list-style:none">
        <span><strong>⚙ เลือกโมเดลเอง</strong>
          <span class="tiny dim">— ถ้าอยากคุมทุกอย่างด้วยตัวเอง</span></span>
        <span class="tiny dim">${data.best_vram_mb ? `VRAM สูงสุดที่มี ${Spice.gb(data.best_vram_mb)}` : "ยังไม่มีเครื่องออนไลน์"}</span>
      </summary>

      <div style="padding-top:1.1rem">
        <div class="grid grid--2" style="gap:0.6rem">
          <div class="model-card ${Spice.state.selectedModel === "auto" ? "selected" : ""}"
               data-model="auto" onclick="Spice.pickModel('auto')">
            <div class="row row--between" style="gap:0.5rem">
              <div class="model-card__name">🧠 ให้ระบบเลือกให้ (แนะนำ)</div>
              <span class="tag">อัตโนมัติ</span>
            </div>
            <div class="model-card__blurb">อ่านคำสั่ง ดูภาษา ดูชนิดงาน แล้วจับคู่กับ VRAM ที่มีอยู่จริง</div>
          </div>
          ${data.models.map((model) => `
            <div class="model-card ${model.id === Spice.state.selectedModel ? "selected" : ""}"
                 data-model="${model.id}" onclick="Spice.pickModel('${model.id}')">
              <div class="row row--between" style="gap:0.5rem">
                <div class="model-card__name">${Spice.esc(model.label)}</div>
                <span class="tag">${Spice.KIND_LABEL[model.kind] || model.kind}</span>
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

        <div class="grid grid--2" style="gap:0.9rem;margin-top:1.1rem">
          <label class="field" style="margin:0">
            <span>คำสั่งระบบ (บอกบุคลิก/กติกาให้โมเดล)</span>
            <textarea id="f-system" rows="2" placeholder="คุณคือผู้ช่วยที่ตอบเป็นภาษาไทย กระชับ ตรงประเด็น"></textarea>
          </label>
          <div>
            <label class="field">
              <span>ความยาวคำตอบสูงสุด · <b id="v-tokens">768</b> โทเคน</span>
              <input type="range" id="f-tokens" min="64" max="4096" step="64" value="768"
                     oninput="document.getElementById('v-tokens').textContent=this.value">
            </label>
            <label class="field" style="margin:0">
              <span>ความสร้างสรรค์ · <b id="v-temp">0.6</b></span>
              <input type="range" id="f-temp" min="0" max="1.5" step="0.05" value="0.6"
                     oninput="document.getElementById('v-temp').textContent=this.value">
            </label>
          </div>
        </div>

        <label class="field" style="margin:0.9rem 0 0">
          <span>ลำดับความสำคัญ (1 = ด่วนที่สุด)</span>
          <select id="f-priority">
            <option value="1">1 · ด่วนมาก แซงทุกงาน</option>
            <option value="5" selected>5 · ปกติ</option>
            <option value="9">9 · ทำตอนว่าง</option>
          </select>
        </label>
      </div>
    </details>`;
};

Spice.pickModel = function (modelId) {
  Spice.state.selectedModel = modelId;
  document.querySelectorAll(".model-card").forEach((card) => {
    card.classList.toggle("selected", card.dataset.model === modelId);
  });
  const pill = document.getElementById("mode-pill");
  const hint = document.getElementById("run-hint");
  if (!pill) return;

  if (modelId === "auto") {
    pill.className = "pill pill--brand";
    pill.textContent = "โหมดอัตโนมัติ";
    if (hint) hint.textContent = "ระบบจะอ่านคำสั่งแล้วตัดสินใจให้ — กด “ดูแผนก่อน” เพื่อตรวจก่อนรันได้";
    return;
  }
  const model = Spice.state.models.find((m) => m.id === modelId);
  pill.className = "pill pill--info";
  pill.textContent = "เลือกเอง";
  if (hint && model) {
    hint.textContent = model.runnable_now
      ? `จะรัน ${model.label} ตามที่คุณเลือก`
      : `⚠ ยังไม่มีเครื่องที่ VRAM ถึง ${Spice.gb(model.vram_mb)} — งานจะรอในคิว`;
  }
};

/* ── แผนที่สมองคิดไว้ ──────────────────────────────────────── */
Spice.previewPlan = async function () {
  const prompt = document.getElementById("f-prompt").value.trim();
  const driveIn = document.getElementById("f-in").value.trim();
  if (!prompt && !driveIn) {
    return Spice.toast("บอกมาก่อนว่าอยากได้อะไร", "warn");
  }
  const slot = document.getElementById("plan-slot");
  slot.innerHTML = `<div class="card row" style="gap:0.6rem"><span class="spinner"></span>
    <span class="small muted">กำลังคิดแผน…</span></div>`;
  try {
    const plan = await Spice.post("/api/v1/plan", {
      prompt, drive_input: driveIn,
      drive_output: document.getElementById("f-out").value.trim(),
    });
    Spice.state.plan = plan;
    slot.innerHTML = Spice.renderPlan(plan);
  } catch (error) {
    slot.innerHTML = `<div class="card">${Spice.empty("⚠️", "คิดแผนไม่สำเร็จ", Spice.esc(error.message))}</div>`;
  }
};

Spice.renderPlan = function (plan) {
  const intent = plan.intent || {};
  const chip = (label) => `<span class="tag">${Spice.esc(label)}</span>`;
  return `
    <div class="card card--plan page-enter">
      <div class="card-head">
        <h3>🧠 แผนที่ระบบคิดไว้</h3>
        <div class="row" style="gap:0.4rem">
          <span class="pill pill--info">≈ ${Spice.duration(plan.eta_seconds)}</span>
          <button class="btn btn--primary btn--sm" onclick="Spice.submitJob()">รันตามแผนนี้ →</button>
        </div>
      </div>

      <p class="small" style="margin-bottom:1rem">${Spice.esc(plan.reason)}</p>

      <div class="row row--wrap" style="gap:0.35rem;margin-bottom:1rem">
        ${chip(`ภาษา: ${{ th: "ไทย", en: "อังกฤษ", mixed: "ผสม" }[intent.language] || intent.language}`)}
        ${chip(`ชนิดงาน: ${Spice.KIND_LABEL[intent.kind] || intent.kind}`)}
        ${intent.kind === "text" ? chip(`ความยาว: ${{ short: "สั้น", standard: "ปกติ", long: "ยาว" }[intent.length] || intent.length}`) : ""}
        ${intent.kind === "text" ? chip(`ความสร้างสรรค์ ${intent.temperature}`) : ""}
        ${plan.uses_vault ? `<span class="pill pill--online" style="font-size:0.72rem">🧠 ใช้คลังความรู้</span>` : ""}
      </div>

      <div class="steps-flow">
        ${plan.steps.map((step, index) => `
          <div class="step-node">
            <div class="step-node__num">${index + 1}</div>
            <div class="grow" style="min-width:0">
              <div class="row row--between" style="gap:0.5rem">
                <strong class="small">${Spice.esc(step.title)}</strong>
                ${step.warm
                  ? `<span class="pill pill--online" style="font-size:0.7rem">⚡ โหลดไว้แล้ว</span>`
                  : ""}
              </div>
              <div class="tiny dim">
                ${Spice.esc(step.model_label || step.model)} ·
                ${Spice.KIND_LABEL[step.kind] || step.kind} ·
                ${Spice.gb(step.vram_mb)}
                ${step.use_previous ? " · รับผลจากขั้นก่อนหน้า" : ""}
                ${step.drive_output ? ` · บันทึกไป ${Spice.esc(step.drive_output)}` : ""}
              </div>
            </div>
          </div>`).join('<div class="step-arrow">↓</div>')}
      </div>

      ${(plan.vault_hits || []).length ? `
        <div style="margin-top:1rem">
          <div class="tiny dim" style="margin-bottom:0.35rem">เอกสารที่จะดึงมาเป็นบริบท</div>
          <div class="row row--wrap" style="gap:0.3rem">
            ${plan.vault_hits.map((hit) =>
              `<span class="tag">${Spice.esc(hit.title)} · ${Math.round(hit.score * 100)}%</span>`).join("")}
          </div>
        </div>` : ""}

      ${(plan.warnings || []).length ? `
        <div class="notice" style="margin-top:1rem">
          ${plan.warnings.map((warning) => `<div>⚠ ${Spice.esc(warning)}</div>`).join("")}
        </div>` : ""}

      ${(intent.signals || []).length ? `
        <details style="margin-top:0.9rem">
          <summary class="tiny dim" style="cursor:pointer">ระบบอ่านคำสั่งได้ว่าอย่างไร</summary>
          <ul class="tiny dim" style="margin:0.45rem 0 0;padding-left:1.1rem">
            ${intent.signals.map((signal) => `<li>${Spice.esc(signal)}</li>`).join("")}
          </ul>
        </details>` : ""}
    </div>`;
};

Spice.submitJob = async function () {
  const button = document.getElementById("run-btn");
  const prompt = document.getElementById("f-prompt").value.trim();
  const driveIn = document.getElementById("f-in").value.trim();
  if (!prompt && !driveIn) {
    Spice.toast("ใส่คำสั่งหรือระบุไฟล์ใน Drive อย่างน้อยหนึ่งอย่าง", "warn");
    return;
  }

  const manual = Spice.state.selectedModel !== "auto";
  button.disabled = true;
  button.innerHTML = `<span class="spinner"></span> กำลังส่ง…`;
  try {
    const body = {
      model: Spice.state.selectedModel || "auto",
      prompt,
      drive_input: driveIn,
      drive_output: document.getElementById("f-out").value.trim(),
      system: (document.getElementById("f-system") || {}).value?.trim() || "",
      priority: Number((document.getElementById("f-priority") || {}).value || 5),
    };
    if (manual) {
      body.max_tokens = Number(document.getElementById("f-tokens").value);
      body.temperature = Number(document.getElementById("f-temp").value);
    }
    const result = await Spice.post("/api/v1/jobs", body);
    Spice.state.watchJob = result.job_id;
    document.getElementById("plan-slot").innerHTML = "";

    if (result.hint) Spice.toast(result.hint, "warn", 6000);
    else if (result.auto) {
      Spice.toast(`เลือก ${result.model} ให้แล้ว · คาดว่าเสร็จใน ${Spice.duration(result.eta_seconds)}`, "ok");
    } else Spice.toast("ส่งงานเข้าคิวแล้ว", "ok");

    await Spice.renderLiveJob(result.job_id);
  } catch (error) {
    Spice.toast(error.message, "error");
  } finally {
    button.disabled = false;
    button.innerHTML = "✦ รันเลย";
  }
};

Spice.renderLiveJob = async function (jobId) {
  const slot = document.getElementById("live-job");
  if (!slot) return;
  const { job, log, worker } = await Spice.get(`/api/v1/jobs/${jobId}`);
  const status = Spice.JOB_STATUS[job.status] || Spice.JOB_STATUS.queued;
  const pending = job.status === "queued" || job.status === "running";
  const plan = job.plan || {};

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
        ${job.duration !== undefined ? `<span>ใช้เวลา ${Spice.duration(job.duration)}</span>`
          : (pending && job.eta_seconds ? `<span>คาดว่า ≈ ${Spice.duration(job.eta_seconds)}</span>` : "")}
        ${job.chain_left ? `<span class="pill pill--info" style="font-size:0.7rem">เหลืออีก ${job.chain_left} ขั้น</span>` : ""}
        ${job.attempt > 1 ? `<span class="pill pill--busy" style="font-size:0.7rem">ลองใหม่ครั้งที่ ${job.attempt}</span>` : ""}
      </div>
      ${plan.reason && !plan.manual
        ? `<p class="tiny dim" style="margin:-0.4rem 0 0.9rem">🧠 ${Spice.esc(plan.reason)}</p>` : ""}
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
        ${job.from_cache ? `<span class="tag" title="ตอบจากผลลัพธ์เดิม ไม่ได้ใช้ GPU">⚡ แคช</span>` : ""}
        <div class="job__body">
          <div class="job__title">${Spice.esc(job.title)}</div>
          <div class="job__meta">
            ${Spice.esc(job.model)} · ${Spice.ago(job.created_at)}
            ${job.duration !== undefined ? ` · ${Spice.duration(job.duration)}` : ""}
            ${job.status === "queued" && job.eta_seconds ? ` · คาดว่า ≈ ${Spice.duration(job.eta_seconds)}` : ""}
            ${job.chain_left ? ` · เหลืออีก ${job.chain_left} ขั้น` : ""}
            ${job.parent_id ? " · ต่อจากงานก่อนหน้า" : ""}
            ${job.attempt > 1 ? ` · ลองใหม่ครั้งที่ ${job.attempt}` : ""}
            ${(job.repairs || []).length ? ` · ซ่อมผลลัพธ์ ${job.repairs.length} ครั้ง` : ""}
            ${job.continued ? ` · เขียนต่อจากของเดิม ${job.continued} รอบ` : ""}
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

    ${(job.plan && job.plan.reason && !job.plan.manual) ? `
      <div class="card--plan card" style="padding:0.9rem 1rem;margin-bottom:1rem">
        <div class="tiny dim" style="margin-bottom:0.3rem">🧠 ระบบตัดสินใจอย่างไร</div>
        <div class="small">${Spice.esc(job.plan.reason)}</div>
        ${(job.plan.steps || []).length > 1 ? `
          <div class="tiny dim" style="margin-top:0.5rem">
            ลูกโซ่ ${job.plan.steps.length} ขั้น:
            ${job.plan.steps.map((step, index) =>
              `${index + 1}. ${Spice.esc(step.title)}`).join(" → ")}
          </div>` : ""}
        ${(job.plan.warnings || []).length ? `
          <div class="tiny" style="margin-top:0.5rem;color:var(--warn)">
            ${job.plan.warnings.map((warning) => `⚠ ${Spice.esc(warning)}`).join("<br>")}
          </div>` : ""}
      </div>` : ""}

    ${job.attempt > 1 ? `
      <div class="notice" style="margin-bottom:1rem">
        🔁 งานนี้ล้มเพราะหน่วยความจำ GPU ไม่พอ ระบบจึงลดขนาดโมเดลแล้วลองใหม่ให้อัตโนมัติ
        (ครั้งที่ ${job.attempt})
      </div>` : ""}

    ${(job.repairs || []).length ? `
      <div class="notice" style="margin-bottom:1rem">
        <strong>🩹 ด่านตรวจคุณภาพสั่งทำใหม่ ${job.repairs.length} ครั้ง</strong>
        ${job.repairs.map((repair) => `<div>• ${Spice.esc(repair.detail)}</div>`).join("")}
      </div>` : ""}

    ${job.from_cache ? `
      <div class="notice" style="margin-bottom:1rem">
        ⚡ คำตอบนี้มาจากผลลัพธ์ที่เคยคำนวณไว้แล้ว — ไม่ได้ใช้การ์ดจอเลย
      </div>` : ""}

    ${job.continued ? `
      <div class="notice" style="margin-bottom:1rem">
        <strong>♻️ งานนี้ถูกเขียนต่อจากของเดิม ${job.continued} รอบ</strong>
        <div>เครื่องที่ทำอยู่หลุดกลางทาง ระบบจึงเก็บข้อความที่เขียนไปแล้ว
          ${job.kept_chars.toLocaleString()} ตัวอักษรไว้ แล้วสั่งให้เครื่องถัดไปเขียนต่อ
          แทนที่จะทิ้งทั้งหมดแล้วเริ่มใหม่</div>
      </div>` : ""}

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


/* ═══ คลังโมเดล (Hugging Face) ═════════════════════════════ */
Spice.views.hub = async function () {
  const [mine, presets] = await Promise.all([
    Spice.get("/api/v1/hub/models"),
    Spice.get("/api/v1/hub/presets"),
  ]);
  Spice.state.hubBudget = mine.vram_budget_mb;

  return `
    <div class="view-head">
      <h2>📦 คลังโมเดล</h2>
      <p class="small dim">
        ดึงโมเดลไหนก็ได้จาก Hugging Face มาใช้ — ระบบจะประเมินให้ก่อนว่าการ์ดจอของคุณรันไหวไหม
      </p>
    </div>

    <div class="card card--brain">
      <div class="card-head">
        <h3>🔎 ค้นหาบน Hugging Face</h3>
        ${mine.vram_budget_mb
          ? `<span class="pill pill--info">การ์ดที่มีตอนนี้ ${Spice.gb(mine.vram_budget_mb)}</span>`
          : `<span class="pill pill--offline">ยังไม่มีเครื่องออนไลน์</span>`}
      </div>

      <div class="row row--wrap" style="gap:0.5rem;margin-bottom:0.9rem">
        <input type="text" id="hub-q" class="grow" style="min-width:240px"
               placeholder="เช่น abliterated, dolphin, typhoon, qwen coder…"
               onkeydown="if(event.key==='Enter')Spice.hubSearch()">
        <select id="hub-kind" style="width:auto">
          <option value="">ทุกชนิด</option>
          <option value="text">ข้อความ</option>
          <option value="image">รูปภาพ</option>
          <option value="audio">เสียง</option>
          <option value="embedding">เวกเตอร์</option>
        </select>
        <button class="btn btn--primary" onclick="Spice.hubSearch()">ค้นหา</button>
      </div>

      <div class="row row--wrap" style="gap:0.35rem;margin-bottom:0.9rem">
        <span class="tiny dim" style="align-self:center">ค้นบ่อย:</span>
        ${["abliterated", "uncensored", "dolphin", "typhoon", "qwen coder", "sdxl"]
          .map((term) => `<span class="tag" style="cursor:pointer"
             onclick="document.getElementById('hub-q').value='${term}';Spice.hubSearch()">${term}</span>`).join("")}
      </div>

      <details>
        <summary class="small muted" style="cursor:pointer">
          หรือวางชื่อ/ลิงก์โมเดลตรง ๆ
        </summary>
        <div class="row row--wrap" style="gap:0.5rem;margin-top:0.7rem">
          <input type="text" id="hub-repo" class="grow" style="min-width:260px"
                 placeholder="owner/model-name หรือ https://huggingface.co/...">
          <select id="hub-quant" style="width:auto">
            <option value="">เลือกการบีบอัดให้อัตโนมัติ</option>
            <option value="fp16">fp16 (เต็มความละเอียด)</option>
            <option value="8bit">8bit (ประหยัดครึ่งหนึ่ง)</option>
            <option value="4bit">4bit (เล็กที่สุด)</option>
          </select>
          <button class="btn" onclick="Spice.hubAdd(document.getElementById('hub-repo').value)">
            เพิ่มเข้าคลัง
          </button>
        </div>
      </details>

      <div id="hub-results" style="margin-top:1rem"></div>
    </div>

    <div class="card">
      <div class="card-head">
        <h3>⭐ ชุดแนะนำ</h3>
        <span class="tiny dim">กดเพิ่มได้ทันที ไม่ต้องค้นเอง</span>
      </div>
      <div class="stack" style="gap:1.2rem">
        ${presets.groups.map((group) => `
          <div>
            <div style="font-weight:650;font-size:0.92rem">${Spice.esc(group.group)}</div>
            <div class="tiny dim" style="margin-bottom:0.55rem">${Spice.esc(group.note)}</div>
            <div class="grid grid--2" style="gap:0.5rem">
              ${group.models.map((model) => `
                <div class="model-card" style="cursor:default">
                  <div class="row row--between" style="gap:0.5rem">
                    <div class="model-card__name" style="font-size:0.86rem;word-break:break-all">
                      ${Spice.esc(model.repo)}
                    </div>
                    ${model.already_added
                      ? `<span class="pill pill--online" style="font-size:0.7rem">มีแล้ว</span>`
                      : `<button class="btn btn--sm" onclick="Spice.hubAdd('${Spice.esc(model.repo)}')">+ เพิ่ม</button>`}
                  </div>
                  <div class="model-card__blurb" style="margin-bottom:0">${Spice.esc(model.why)}</div>
                </div>`).join("")}
            </div>
          </div>`).join("")}
      </div>
    </div>

    <div class="card">
      <div class="card-head">
        <h3>🗂 โมเดลในคลังของคุณ</h3>
        <span class="tiny dim">${mine.models.length} ตัว (นอกเหนือจาก ${mine.builtin.length} ตัวที่มีมาให้)</span>
      </div>
      ${mine.models.length
        ? `<div class="stack" style="gap:0.6rem">${mine.models.map(Spice.renderCustomModel).join("")}</div>`
        : Spice.empty("📦", "ยังไม่ได้เพิ่มโมเดลเอง", "ค้นหาด้านบน หรือกดเพิ่มจากชุดแนะนำ")}
    </div>

    <div class="card">
      <div class="card-head">
        <h3>🔑 โทเคน Hugging Face</h3>
        ${mine.has_hf_token
          ? `<span class="pill pill--online"><span class="dot"></span>ตั้งค่าแล้ว</span>`
          : `<span class="pill pill--offline">ยังไม่ได้ตั้ง</span>`}
      </div>
      <p class="small">
        จำเป็นเฉพาะกับโมเดลที่ต้องกดยอมรับเงื่อนไขก่อน (เช่นตระกูล Llama ของ Meta) หรือโมเดลส่วนตัวของคุณเอง
        สร้างได้ที่ <a href="https://huggingface.co/settings/tokens" target="_blank" rel="noopener">huggingface.co/settings/tokens</a>
        (สิทธิ์ read ก็พอ)
      </p>
      <div class="row row--wrap" style="gap:0.5rem">
        <input type="text" id="hf-token" class="grow" style="min-width:240px"
               placeholder="hf_xxxxxxxxxxxxxxxxxxxx">
        <button class="btn btn--primary" onclick="Spice.saveHfToken()">บันทึก</button>
        ${mine.has_hf_token ? `<button class="btn btn--danger" onclick="Spice.saveHfToken(true)">ลบออก</button>` : ""}
      </div>
      <p class="tiny dim" style="margin:0.8rem 0 0">
        เก็บแบบเข้ารหัสในฐานข้อมูล และจะถูกส่งให้เฉพาะเครื่องที่คุณจับคู่ไว้เท่านั้น เพื่อใช้ดาวน์โหลดโมเดล
      </p>
    </div>`;
};

Spice.renderCustomModel = function (model) {
  return `
    <div class="model-card" style="cursor:default">
      <div class="row row--between row--wrap" style="gap:0.5rem">
        <div style="min-width:0">
          <div class="model-card__name">${Spice.esc(model.label)}</div>
          <a class="tiny" href="${Spice.esc(model.url)}" target="_blank" rel="noopener"
             style="word-break:break-all">${Spice.esc(model.repo)} ↗</a>
        </div>
        <div class="row" style="gap:0.4rem">
          ${model.fits
            ? `<span class="pill pill--online" style="font-size:0.7rem">รันได้บนเครื่องที่มี</span>`
            : `<span class="pill pill--busy" style="font-size:0.7rem">VRAM อาจไม่พอ</span>`}
          <button class="btn btn--sm btn--danger" onclick="Spice.hubRemove('${model.id}')">ลบ</button>
        </div>
      </div>
      <div class="row row--wrap" style="gap:0.3rem;margin-top:0.5rem">
        <span class="tag">${Spice.KIND_LABEL[model.kind] || model.kind}</span>
        ${model.params_b ? `<span class="tag">${model.params_b}B พารามิเตอร์</span>` : ""}
        <span class="tag">${Spice.esc(model.quantize)}</span>
        <span class="tag">ต้องใช้ ~${Spice.gb(model.vram_mb)}</span>
        ${model.trust_remote_code ? `<span class="pill pill--danger" style="font-size:0.7rem">⚠ trust_remote_code</span>` : ""}
        ${model.gated ? `<span class="tag">ต้องขอสิทธิ์</span>` : ""}
      </div>
    </div>`;
};

Spice.hubSearch = async function () {
  const query = document.getElementById("hub-q").value.trim();
  const kind = document.getElementById("hub-kind").value;
  const slot = document.getElementById("hub-results");
  if (!query) return Spice.toast("ใส่คำค้นก่อน", "warn");

  slot.innerHTML = Spice.skeleton(3);
  try {
    const data = await Spice.get(
      `/api/v1/hub/search?q=${encodeURIComponent(query)}&kind=${kind}&limit=24`);
    slot.innerHTML = data.results.length
      ? `<div class="stack" style="gap:0.5rem">${data.results.map(Spice.renderHubResult).join("")}</div>`
      : Spice.empty("🔎", "ไม่พบโมเดลที่ตรงกับคำค้น", "ลองคำอื่น หรือวางชื่อโมเดลตรง ๆ ด้านบน");
  } catch (error) {
    slot.innerHTML = Spice.empty("⚠️", "ค้นหาไม่สำเร็จ", Spice.esc(error.message));
  }
};

Spice.renderHubResult = function (model) {
  const number = (value) => value >= 1000 ? `${Math.round(value / 1000)}k` : value;
  return `
    <div class="model-card" style="cursor:default">
      <div class="row row--between row--wrap" style="gap:0.5rem">
        <div style="min-width:0">
          <div class="model-card__name" style="word-break:break-all">${Spice.esc(model.repo)}</div>
          <div class="tiny dim">
            ⬇ ${number(model.downloads)} · ♥ ${number(model.likes)}
            ${model.params_b ? ` · ${model.params_b}B` : " · ไม่ทราบขนาด"}
            · ${Spice.KIND_LABEL[model.kind] || model.kind}
          </div>
        </div>
        ${model.unsupported
          ? `<span class="pill pill--danger" style="font-size:0.7rem">ใช้กับระบบนี้ไม่ได้</span>`
          : model.already_added
            ? `<span class="pill pill--online" style="font-size:0.7rem">มีแล้ว</span>`
            : `<button class="btn btn--sm btn--primary"
                 onclick="Spice.hubAdd('${Spice.esc(model.repo)}')">+ เพิ่ม</button>`}
      </div>

      ${model.unsupported
        ? `<div class="tiny" style="color:var(--warn);margin-top:0.4rem">${Spice.esc(model.unsupported)}</div>`
        : `<div class="row row--wrap" style="gap:0.3rem;margin-top:0.5rem">
             ${["fp16", "8bit", "4bit"].map((option) => {
               const need = model.vram_by_quantize[option];
               const ok = Spice.state.hubBudget && need && need <= Spice.state.hubBudget;
               return `<span class="tag" style="${ok ? "color:var(--accent)" : ""}">
                 ${option} ${need ? Spice.gb(need) : "?"}${ok ? " ✓" : ""}</span>`;
             }).join("")}
             ${model.gated ? `<span class="tag">ต้องขอสิทธิ์ก่อน</span>` : ""}
             <a class="tag" href="${Spice.esc(model.url)}" target="_blank" rel="noopener">ดูบน HF ↗</a>
           </div>`}
    </div>`;
};

Spice.hubAdd = async function (repo) {
  if (!repo || !repo.trim()) return Spice.toast("ใส่ชื่อโมเดลก่อน", "warn");
  const quantize = (document.getElementById("hub-quant") || {}).value || "";
  Spice.toast(`กำลังตรวจสอบ ${repo}…`, "info", 2500);
  try {
    const body = await Spice.post("/api/v1/hub/models", { repo: repo.trim(), quantize });
    Spice.toast(`เพิ่ม ${body.model.label} เข้าคลังแล้ว`, "ok");
    (body.warnings || []).forEach((warning) => Spice.toast(warning, "warn", 8000));
    Spice.render();
  } catch (error) {
    Spice.toast(error.message, "error", 9000);
  }
};

Spice.hubRemove = async function (modelId) {
  try {
    await Spice.del(`/api/v1/hub/models/${modelId}`);
    Spice.toast("ลบออกจากคลังแล้ว", "ok");
    Spice.render();
  } catch (error) {
    Spice.toast(error.message, "error");
  }
};

Spice.saveHfToken = async function (clear = false) {
  const field = document.getElementById("hf-token");
  const token = clear ? "" : field.value.trim();
  if (!clear && !token) return Spice.toast("วางโทเคนก่อน", "warn");
  try {
    await Spice.api("/api/v1/hub/token", { method: "PUT", body: { token } });
    Spice.toast(clear ? "ลบโทเคนแล้ว" : "บันทึกโทเคนแล้ว", "ok");
    Spice.render();
  } catch (error) {
    Spice.toast(error.message, "error");
  }
};


/* ═══ แชท (บทสนทนาต่อเนื่อง) ════════════════════════════════ */
Spice.views.chat = async function () {
  const [list, models] = await Promise.all([
    Spice.get("/api/v1/threads"),
    Spice.get("/api/v1/models"),
  ]);
  Spice.state.threads = list.threads;
  Spice.state.models = models.models;

  const active = Spice.state.activeThread &&
    list.threads.find((thread) => thread.id === Spice.state.activeThread)
      ? Spice.state.activeThread : (list.threads[0]?.id || null);
  Spice.state.activeThread = active;

  return `
    <div class="chat-shell">
      <aside class="chat-list card card--flush">
        <div class="row row--between" style="padding:0.9rem 1rem;border-bottom:1px solid var(--border)">
          <strong class="small">บทสนทนา</strong>
          <button class="btn btn--sm btn--primary" onclick="Spice.newThread()">+ ใหม่</button>
        </div>
        <div id="thread-list">
          ${list.threads.length
            ? list.threads.map((thread) => `
                <div class="thread-row ${thread.id === active ? "active" : ""}"
                     onclick="Spice.openThread('${thread.id}')">
                  <div class="small" style="font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
                    ${Spice.esc(thread.title)}
                  </div>
                  <div class="tiny dim" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
                    ${thread.turns} ข้อความ · ${Spice.ago(thread.updated_at)}
                  </div>
                </div>`).join("")
            : `<div class="empty" style="padding:1.6rem 1rem">
                 <div class="empty__icon">💬</div>
                 <div class="small dim">ยังไม่มีบทสนทนา</div>
               </div>`}
        </div>
      </aside>

      <section class="chat-main card card--flush" id="chat-main">
        ${active ? Spice.skeleton(3) : `
          <div class="empty" style="margin:auto">
            <div class="empty__icon">💬</div>
            <div class="empty__title">เริ่มบทสนทนาใหม่</div>
            <div class="small">คุยต่อเนื่องได้หลายรอบ โมเดลจะจำเรื่องที่คุยไปแล้ว</div>
            <button class="btn btn--primary" style="margin-top:1rem" onclick="Spice.newThread()">
              + เริ่มคุย
            </button>
          </div>`}
      </section>
    </div>`;
};

Spice.newThread = async function () {
  const body = await Spice.post("/api/v1/threads", { model: "auto" });
  Spice.state.activeThread = body.id;
  await Spice.render();
};

Spice.openThread = async function (threadId) {
  Spice.state.activeThread = threadId;
  document.querySelectorAll(".thread-row").forEach((row) => row.classList.remove("active"));
  const slot = document.getElementById("chat-main");
  if (!slot) return Spice.render();
  slot.innerHTML = Spice.skeleton(3);

  const data = await Spice.get(`/api/v1/threads/${threadId}`);
  Spice.state.pendingJob = data.pending?.id || null;

  slot.innerHTML = `
    <div class="row row--between" style="padding:0.85rem 1.1rem;border-bottom:1px solid var(--border)">
      <div style="min-width:0">
        <div class="small" style="font-weight:650;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
          ${Spice.esc(data.thread.title)}
        </div>
        <div class="tiny dim">
          ${data.thread.model === "auto" ? "เลือกโมเดลอัตโนมัติทุกข้อความ" : Spice.esc(data.thread.model)}
          ${data.thread.use_vault ? " · ใช้คลังความรู้" : ""}
          ${data.thread.has_memory ? " · 🧠 ย่อรอบเก่าเป็นความจำแล้ว" : ""}
        </div>
      </div>
      <button class="btn btn--sm btn--danger" onclick="Spice.deleteThread('${threadId}')">ลบ</button>
    </div>

    <div class="chat-scroll" id="chat-scroll">
      ${data.messages.map(Spice.renderBubble).join("")}
      <div id="chat-live"></div>
    </div>

    <div class="chat-compose">
      <textarea id="chat-input" rows="1" placeholder="พิมพ์ข้อความ… (Enter ส่ง · Shift+Enter ขึ้นบรรทัดใหม่)"
        oninput="this.style.height='auto';this.style.height=Math.min(this.scrollHeight,160)+'px'"
        onkeydown="if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();Spice.sendChat()}"></textarea>
      <button class="btn btn--primary" id="chat-send" onclick="Spice.sendChat()">ส่ง</button>
    </div>`;

  Spice.scrollChat();
  if (data.pending) Spice.showLiveBubble(data.pending.result || "");
  document.getElementById("chat-input")?.focus();
};

Spice.renderBubble = function (message) {
  const mine = message.role === "user";
  return `
    <div class="bubble-row ${mine ? "mine" : ""}">
      <div class="bubble ${mine ? "bubble--mine" : ""}">${Spice.esc(message.content)}</div>
    </div>`;
};

Spice.showLiveBubble = function (text) {
  const slot = document.getElementById("chat-live");
  if (!slot) return;
  slot.innerHTML = `
    <div class="bubble-row">
      <div class="bubble bubble--live">${Spice.esc(text)}<span class="caret"></span></div>
    </div>`;
  Spice.scrollChat();
};

Spice.scrollChat = function () {
  const box = document.getElementById("chat-scroll");
  if (box) box.scrollTop = box.scrollHeight;
};

Spice.sendChat = async function () {
  const field = document.getElementById("chat-input");
  const button = document.getElementById("chat-send");
  const content = field.value.trim();
  if (!content || !Spice.state.activeThread) return;

  field.value = "";
  field.style.height = "auto";
  button.disabled = true;
  // ต้องแทรกก่อนช่องคำตอบสด ไม่งั้นฟองข้อความจะสลับลำดับกัน
  document.getElementById("chat-live").insertAdjacentHTML(
    "beforebegin", Spice.renderBubble({ role: "user", content }));
  Spice.showLiveBubble("");
  Spice.state.liveText = "";

  try {
    const body = await Spice.post(
      `/api/v1/threads/${Spice.state.activeThread}/messages`, { content });
    Spice.state.pendingJob = body.job_id;
    if (body.from_cache) {
      Spice.toast("ตอบจากผลลัพธ์ที่เคยคำนวณไว้ — ไม่ได้ใช้ GPU", "ok");
      Spice.openThread(Spice.state.activeThread);
    }
  } catch (error) {
    Spice.toast(error.message, "error");
    document.getElementById("chat-live").innerHTML = "";
  } finally {
    button.disabled = false;
  }
};

Spice.deleteThread = async function (threadId) {
  await Spice.del(`/api/v1/threads/${threadId}`);
  if (Spice.state.activeThread === threadId) Spice.state.activeThread = null;
  Spice.toast("ลบบทสนทนาแล้ว", "ok");
  Spice.render();
};


/* ═══ สถิติเชิงลึก + งานตั้งเวลา ═══════════════════════════ */
Spice.views.insights = async function () {
  const [data, schedules, lessons] = await Promise.all([
    Spice.get("/api/v1/insights?days=7"),
    Spice.get("/api/v1/schedules"),
    Spice.get("/api/v1/lessons"),
  ]);

  const tile = (label, value, unit, icon) => `
    <div class="card stat">
      <div class="stat__icon">${icon}</div>
      <div class="stat__label">${label}</div>
      <div class="stat__value">${value}${unit ? `<small>${unit}</small>` : ""}</div>
    </div>`;

  return `
    <div class="view-head">
      <h2>📊 สถิติและงานอัตโนมัติ</h2>
      <p class="small dim">เวลาการ์ดจอหมดไปกับอะไร ระบบช่วยประหยัดไปเท่าไหร่ และมีอะไรทำเองอยู่บ้าง</p>
    </div>

    <div class="grid grid--4">
      ${tile("เวลาการ์ดจอที่ใช้ไป", Spice.duration(data.gpu_seconds), "", "⏱")}
      ${tile("งานทั้งหมด", data.jobs, ` / ล้มเหลว ${data.failed}`, "☰")}
      ${tile("ประหยัดด้วยแคช", Spice.duration(data.cache.saved_seconds), "", "⚡")}
      ${tile("ระบบซ่อมผลลัพธ์เอง", data.repaired_jobs, " งาน", "🩹")}
    </div>

    <div class="grid grid--split">
      <div class="card">
        <div class="card-head">
          <h3>⏱ เวลาการ์ดจอแยกตามโมเดล</h3>
          <span class="tiny dim">7 วันล่าสุด</span>
        </div>
        ${data.by_model.length ? `
          <div class="stack" style="gap:0.85rem">
            ${data.by_model.map((entry) => `
              <div>
                <div class="row row--between tiny" style="margin-bottom:0.3rem">
                  <span style="font-weight:600">${Spice.esc(entry.label)}</span>
                  <span class="dim">${entry.runs} งาน · ${Spice.duration(entry.seconds)}
                    (เฉลี่ย ${Spice.duration(entry.avg_seconds)})</span>
                </div>
                <div class="bar"><i style="width:${Math.round(entry.share * 100)}%"></i></div>
              </div>`).join("")}
          </div>` : Spice.empty("⏱", "ยังไม่มีงานที่รันจริงใน 7 วันนี้")}

        ${data.slowest.length ? `
          <div style="margin-top:1.2rem">
            <div class="tiny dim" style="margin-bottom:0.45rem">งานที่กินเวลามากที่สุด</div>
            ${data.slowest.map((job) => `
              <div class="row row--between tiny" style="padding:0.25rem 0">
                <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:70%">
                  ${Spice.esc(job.title)}</span>
                <span class="dim">${Spice.duration(job.seconds)}</span>
              </div>`).join("")}
          </div>` : ""}
      </div>

      <div class="stack">
        <div class="card">
          <div class="card-head"><h3>🩺 สุขภาพของเครื่อง</h3></div>
          ${data.workers.length ? `
            <div class="stack" style="gap:0.7rem">
              ${data.workers.map((entry) => `
                <div class="row row--between">
                  <div style="min-width:0">
                    <div class="small" style="font-weight:600">${Spice.esc(entry.name)}</div>
                    <div class="tiny dim">
                      สำเร็จ ${entry.jobs_done} · ล้มเหลว ${entry.jobs_failed}
                      ${entry.success_rate !== null ? ` · ${Math.round(entry.success_rate * 100)}%` : ""}
                    </div>
                  </div>
                  ${entry.quarantined
                    ? `<span class="pill pill--danger" style="font-size:0.7rem">พักอยู่</span>`
                    : `<span class="pill pill--online" style="font-size:0.7rem">ปกติ</span>`}
                </div>`).join("")}
            </div>` : Spice.empty("🩺", "ยังไม่มีเครื่องในระบบ")}
        </div>

        <div class="card">
          <div class="card-head"><h3>⚡ แคช</h3></div>
          <div class="stack" style="gap:0.55rem">
            <div class="row row--between"><span class="small muted">คำตอบที่เก็บไว้</span>
              <strong>${data.cache.entries}</strong></div>
            <div class="row row--between"><span class="small muted">ใช้ซ้ำไปแล้ว</span>
              <strong>${data.cache.hits} ครั้ง</strong></div>
            <div class="row row--between"><span class="small muted">งานที่ตอบจากแคช</span>
              <strong>${data.cached_jobs}</strong></div>
          </div>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-head">
        <h3>🔎 บทเรียนที่ระบบจำไว้</h3>
        <span class="tiny dim">
          ${lessons.total_kinds ? `รู้จักปัญหา ${lessons.total_kinds} แบบ · พิสูจน์แล้วว่าแก้ได้ ${lessons.proven.length} แบบ`
                                : "ยังไม่เคยเจอปัญหา"}
        </span>
      </div>
      ${lessons.patterns.length ? `
        <p class="small dim" style="margin-bottom:0.9rem">
          ระบบย่อ error เป็นลายนิ้วมือ (ตัดตัวเลขและพาธทิ้ง) แล้วจำว่าวิธีแก้ไหนได้ผลจริง
          — วิธีที่แก้แล้วยังพังอยู่จะถูกเลิกใช้ไปเอง
        </p>
        <div class="stack" style="gap:0.5rem">
          ${lessons.patterns.map((item) => {
            const rate = item.success_rate;
            const badge = rate === null
              ? `<span class="tag">ยังไม่ได้ลองแก้</span>`
              : rate >= 0.5
                ? `<span class="pill pill--online" style="font-size:0.7rem">แก้ได้ ${Math.round(rate * 100)}%</span>`
                : `<span class="pill pill--danger" style="font-size:0.7rem">ยังแก้ไม่ได้</span>`;
            return `
              <div class="card" style="padding:0.75rem 0.95rem">
                <div class="row row--between row--wrap" style="gap:0.5rem">
                  <div style="min-width:0">
                    <div class="small" style="font-weight:600">
                      ${Spice.esc(Spice.PROBLEM_LABEL[item.kind] || item.kind)}
                      <span class="dim" style="font-weight:400"> · เจอ ${item.occurrences} ครั้ง</span>
                    </div>
                    <div class="tiny dim">วิธีแก้: ${Spice.esc(item.remedy)}</div>
                  </div>
                  ${badge}
                </div>
                <div class="tiny dim mono" style="margin-top:0.4rem;opacity:0.65;
                     overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
                  ${Spice.esc(item.sample)}
                </div>
              </div>`;
          }).join("")}
        </div>`
        : Spice.empty("🔎", "ยังไม่เคยเจอปัญหา",
            "เมื่อมีงานล้มเหลว ระบบจะจำอาการและวิธีแก้ที่ได้ผลไว้ให้เอง")}
    </div>

    <div class="card">
      <div class="card-head">
        <h3>⏰ งานตั้งเวลา</h3>
        <button class="btn btn--sm btn--primary" onclick="Spice.newSchedule()">+ ตั้งเวลาใหม่</button>
      </div>
      ${schedules.schedules.length ? `
        <div class="stack" style="gap:0.5rem">
          ${schedules.schedules.map((item) => `
            <div class="row row--between row--wrap" style="gap:0.6rem;padding:0.6rem 0;border-bottom:1px solid var(--border)">
              <div style="min-width:0;flex:1">
                <div class="small" style="font-weight:600">${Spice.esc(item.title)}</div>
                <div class="tiny dim">
                  ทุก ${Spice.interval(item.every_minutes)}
                  ${item.every_minutes >= 1440 ? ` เวลา ${String(item.at_hour).padStart(2, "0")}:${String(item.at_minute).padStart(2, "0")}` : ""}
                  · ทำไปแล้ว ${item.runs} ครั้ง
                  ${item.enabled ? ` · อีก ${Spice.interval(Math.max(0, item.next_run_in_minutes))}` : ""}
                </div>
              </div>
              <div class="row" style="gap:0.35rem">
                <span class="pill ${item.enabled ? "pill--online" : "pill--offline"}" style="font-size:0.7rem">
                  ${item.enabled ? "เปิดอยู่" : "ปิดอยู่"}</span>
                <button class="btn btn--sm" onclick="Spice.runSchedule('${item.id}')">รันเลย</button>
                <button class="btn btn--sm btn--ghost" onclick="Spice.toggleSchedule('${item.id}')">
                  ${item.enabled ? "ปิด" : "เปิด"}</button>
                <button class="btn btn--sm btn--danger" onclick="Spice.deleteSchedule('${item.id}')">ลบ</button>
              </div>
            </div>`).join("")}
        </div>`
        : Spice.empty("⏰", "ยังไม่มีงานตั้งเวลา",
            "เช่น “สรุปไฟล์ประชุมใน Drive ทุกเช้า 8 โมง” — ตั้งครั้งเดียวแล้วระบบทำเองทุกวัน")}
    </div>`;
};

Spice.interval = function (minutes) {
  if (minutes < 60) return `${minutes} นาที`;
  if (minutes < 1440) return `${Math.round(minutes / 60)} ชั่วโมง`;
  const days = Math.round(minutes / 1440);
  return days === 1 ? "วัน" : `${days} วัน`;
};

Spice.newSchedule = function () {
  Spice.modal(`
    <h3>⏰ ตั้งเวลาให้ระบบทำเอง</h3>
    <p class="small">สั่งครั้งเดียว แล้วระบบจะทำซ้ำให้ตามรอบที่ตั้งไว้</p>
    <label class="field">
      <span>ชื่องาน</span>
      <input type="text" id="s-title" placeholder="สรุปไฟล์ประชุมประจำวัน">
    </label>
    <label class="field">
      <span>คำสั่ง</span>
      <textarea id="s-prompt" rows="3" placeholder="สรุปไฟล์ประชุมล่าสุดเป็นข้อ ๆ พร้อมสิ่งที่ต้องทำต่อ"></textarea>
    </label>
    <div class="grid grid--2" style="gap:0.8rem">
      <label class="field" style="margin:0">
        <span>ทำซ้ำทุก</span>
        <select id="s-every">
          <option value="60">ชั่วโมง</option>
          <option value="360">6 ชั่วโมง</option>
          <option value="1440" selected>วัน</option>
          <option value="10080">สัปดาห์</option>
        </select>
      </label>
      <label class="field" style="margin:0">
        <span>เวลา (สำหรับรอบวัน/สัปดาห์)</span>
        <input type="text" id="s-at" value="08:00" placeholder="08:00">
      </label>
    </div>
    <div class="grid grid--2" style="gap:0.8rem">
      <label class="field" style="margin:0">
        <span>ไฟล์ต้นทางใน Drive (ถ้ามี)</span>
        <input type="text" id="s-in" placeholder="gdrive:audio/meeting.m4a">
      </label>
      <label class="field" style="margin:0">
        <span>บันทึกผลลง Drive (ถ้าต้องการ)</span>
        <input type="text" id="s-out" placeholder="gdrive:spice/daily">
      </label>
    </div>
    <div class="row row--between" style="margin-top:1.2rem">
      <button class="btn btn--sm" data-modal-close>ยกเลิก</button>
      <button class="btn btn--primary btn--sm" onclick="Spice.saveSchedule()">ตั้งเวลา</button>
    </div>`);
};

Spice.saveSchedule = async function () {
  const prompt = document.getElementById("s-prompt").value.trim();
  if (!prompt) return Spice.toast("ใส่คำสั่งก่อน", "warn");
  const [hour, minute] = (document.getElementById("s-at").value || "08:00").split(":");
  try {
    const body = await Spice.post("/api/v1/schedules", {
      title: document.getElementById("s-title").value.trim(),
      prompt,
      model: Spice.state.selectedModel || "auto",
      every_minutes: Number(document.getElementById("s-every").value),
      at_hour: Math.min(23, Math.max(0, Number(hour) || 8)),
      at_minute: Math.min(59, Math.max(0, Number(minute) || 0)),
      drive_input: document.getElementById("s-in").value.trim(),
      drive_output: document.getElementById("s-out").value.trim(),
    });
    Spice.closeModal();
    Spice.toast(`ตั้งเวลาแล้ว · รอบแรกอีก ${Spice.interval(body.next_run_in_minutes)}`, "ok");
    Spice.render();
  } catch (error) {
    Spice.toast(error.message, "error");
  }
};

Spice.runSchedule = async function (scheduleId) {
  await Spice.post(`/api/v1/schedules/${scheduleId}/run`);
  Spice.toast("ส่งเข้าคิวแล้ว", "ok");
  Spice.render();
};

Spice.toggleSchedule = async function (scheduleId) {
  const body = await Spice.post(`/api/v1/schedules/${scheduleId}/toggle`);
  Spice.toast(body.enabled ? "เปิดใช้งานแล้ว" : "ปิดไว้แล้ว", "ok");
  Spice.render();
};

Spice.deleteSchedule = async function (scheduleId) {
  await Spice.del(`/api/v1/schedules/${scheduleId}`);
  Spice.toast("ลบงานตั้งเวลาแล้ว", "ok");
  Spice.render();
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


/* ── งานชุด ─────────────────────────────────────────────── */
Spice.submitBatch = async function () {
  const prompt = document.getElementById("b-prompt").value.trim();
  const items = document.getElementById("b-items").value
    .split("\n").map((line) => line.trim()).filter(Boolean);
  if (!prompt) return Spice.toast("ใส่คำสั่งก่อน", "warn");
  if (!items.length) return Spice.toast("ใส่รายการอย่างน้อยหนึ่งบรรทัด", "warn");

  try {
    const body = await Spice.post("/api/v1/batches", {
      prompt, items,
      model: Spice.state.selectedModel || "auto",
      as_drive_files: document.getElementById("b-drive").checked,
    });
    Spice.state.watchBatch = body.batch_id;
    Spice.toast(
      `แตกเป็น ${body.total} งาน กระจายให้ ${body.workers || 0} เครื่อง · คาดว่า ${Spice.duration(body.eta_seconds)}`,
      "ok", 6000);
    Spice.renderBatch(body.batch_id);
  } catch (error) {
    Spice.toast(error.message, "error", 8000);
  }
};

Spice.renderBatch = async function (batchId) {
  const slot = document.getElementById("batch-slot");
  if (!slot) return;
  const { batch, jobs } = await Spice.get(`/api/v1/batches/${batchId}`);

  slot.innerHTML = `
    <div class="card" style="padding:1rem">
      <div class="card-head" style="margin-bottom:0.7rem">
        <h3 style="font-size:0.95rem">${Spice.esc(batch.title)}</h3>
        <span class="pill ${batch.finished ? "pill--online" : "pill--busy"}">
          ${batch.done}/${batch.total} เสร็จ${batch.failed ? ` · ${batch.failed} ล้มเหลว` : ""}
        </span>
      </div>
      <div class="bar" style="margin-bottom:0.8rem">
        <i style="width:${Math.round(batch.progress * 100)}%"></i>
      </div>
      <div class="stack" style="gap:0.3rem;max-height:220px;overflow-y:auto">
        ${jobs.map((job) => {
          const status = Spice.JOB_STATUS[job.status] || Spice.JOB_STATUS.queued;
          return `<div class="row" style="gap:0.5rem">
            <span class="pill ${status.pill}" style="min-width:76px;justify-content:center;font-size:0.7rem">
              ${status.label}</span>
            <span class="small" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">
              ${Spice.esc(job.title)}</span>
            ${job.from_cache ? `<span class="tag">แคช</span>` : ""}
          </div>`;
        }).join("")}
      </div>
      ${batch.finished ? `
        <button class="btn btn--sm btn--primary btn--block" style="margin-top:0.8rem"
                onclick="Spice.exportBatch('${batchId}')">📋 คัดลอกผลทั้งชุด</button>` : ""}
    </div>`;
};

Spice.exportBatch = async function (batchId) {
  const body = await Spice.get(`/api/v1/batches/${batchId}/export`);
  try {
    await navigator.clipboard.writeText(body.markdown);
    Spice.toast(`คัดลอกผล ${body.count} รายการแล้ว`, "ok");
  } catch {
    Spice.modal(`<h3>ผลลัพธ์ทั้งชุด</h3>
      ${Spice.codeBlock(body.markdown, "batch-export")}
      <div class="row row--between" style="margin-top:1rem">
        <span class="tiny dim">${body.count} รายการ</span>
        <button class="btn btn--sm" data-modal-close>ปิด</button>
      </div>`);
  }
};


/* ── โหวตหาคำตอบที่น่าเชื่อถือที่สุด ────────────────────────── */
Spice.submitVote = async function () {
  const prompt = document.getElementById("f-prompt").value.trim();
  if (!prompt) return Spice.toast("ใส่คำถามก่อน", "warn");

  try {
    const body = await Spice.post("/api/v1/votes", {
      prompt, model: Spice.state.selectedModel || "auto", votes: 3,
    });
    Spice.state.watchVote = body.vote_group;
    Spice.toast(`ถาม ${body.votes} รอบด้วย ${body.model} แล้วจะเทียบคำตอบให้`, "ok");
    Spice.renderVote(body.vote_group);
  } catch (error) {
    Spice.toast(error.message, "error");
  }
};

Spice.renderVote = async function (group) {
  const slot = document.getElementById("plan-slot");
  if (!slot) return;
  const data = await Spice.get(`/api/v1/votes/${group}`);
  const verdict = data.verdict || {};
  const done = data.finished >= data.total;

  slot.innerHTML = `
    <div class="card card--plan page-enter">
      <div class="card-head">
        <h3>🗳 โหวตคำตอบ</h3>
        <span class="pill ${done ? "pill--online" : "pill--busy"}">
          ${data.finished}/${data.total} รอบเสร็จแล้ว
        </span>
      </div>
      <p class="small" style="margin-bottom:0.9rem">${Spice.esc(data.summary)}</p>

      ${verdict.answer ? `
        <div class="tiny dim" style="margin-bottom:0.3rem">คำตอบที่สอดคล้องกับพวกมากที่สุด</div>
        <div class="result" style="margin-bottom:1rem">${Spice.esc(verdict.answer)}</div>` : ""}

      <details>
        <summary class="small muted" style="cursor:pointer">ดูคำตอบทุกรอบ (${data.total})</summary>
        <div class="stack" style="gap:0.5rem;margin-top:0.7rem">
          ${data.answers.map((entry, index) => {
            const status = Spice.JOB_STATUS[entry.status] || Spice.JOB_STATUS.queued;
            const isWinner = index === verdict.winner_index;
            return `
              <div class="card" style="padding:0.7rem 0.9rem;${isWinner ? "border-color:var(--accent)" : ""}">
                <div class="row row--between" style="margin-bottom:0.3rem">
                  <span class="tiny dim">รอบที่ ${index + 1} · ความสร้างสรรค์ ${entry.temperature ?? "—"}</span>
                  <span class="pill ${status.pill}" style="font-size:0.68rem">
                    ${isWinner ? "⭐ " : ""}${status.label}</span>
                </div>
                <div class="small">${Spice.esc((entry.result || "").slice(0, 300)) || "<span class='dim'>ยังไม่เสร็จ</span>"}</div>
              </div>`;
          }).join("")}
        </div>
      </details>
    </div>`;
};
