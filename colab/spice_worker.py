#!/usr/bin/env python3
"""Spice Worker — ตัวแทนเครื่องที่เอา GPU มาให้ระบบใช้ (ออกแบบมาเพื่อ Google Colab T4).

วิธีใช้ใน Colab (เซลล์เดียว):
    !curl -sSL https://<เซิร์ฟเวอร์ของคุณ>/colab/bootstrap.py -o spice_worker.py \
      && python spice_worker.py --server https://<เซิร์ฟเวอร์ของคุณ> --pair XXXX-XXXX

สคริปต์นี้จะ:
  1) จับคู่กับบัญชี Google ของคุณด้วยรหัสจับคู่ (ไม่ต้องใส่รหัสผ่านใด ๆ)
  2) รายงานสถานะการ์ดจอเข้าหน้าเว็บทุก 20 วินาที
  3) เมานต์ Google Drive ด้วย rclone โดยใช้สิทธิ์ที่คุณอนุญาตไว้แล้ว
  4) ดึงงานจากคิวมารันบน GPU แล้วส่งผลลัพธ์กลับ

ออกจากระบบ: กดหยุดเซลล์ (■) — เครื่องจะขึ้นสถานะออฟไลน์ภายในไม่กี่วินาที
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import signal
import subprocess
import sys
import threading
import time
import traceback
import urllib.request

try:
    import requests
except ImportError:  # pragma: no cover - Colab มี requests อยู่แล้วเสมอ
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "requests"], check=False)
    import requests

HEARTBEAT_SECONDS = 20
POLL_SECONDS = 3
RCLONE_MOUNT = "/content/gdrive"

_stop = threading.Event()
_model_cache: dict[str, object] = {}
# โมเดลที่โหลดค้างอยู่ใน VRAM ตอนนี้ — รายงานให้เซิร์ฟเวอร์รู้ เพื่อให้มันส่ง
# งานที่ใช้โมเดลเดียวกันมาให้เครื่องนี้ก่อน (ไม่ต้องเสียเวลาโหลดใหม่)
_warm_models: list[str] = []
MAX_WARM = 6


def mark_warm(model_id: str) -> None:
    if not model_id:
        return
    if model_id in _warm_models:
        _warm_models.remove(model_id)
    _warm_models.append(model_id)
    del _warm_models[:-MAX_WARM]


# ── ยูทิลิตี้ ─────────────────────────────────────────────────
def log(message: str, icon: str = "•") -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {icon} {message}", flush=True)


def run(cmd: list[str], timeout: int = 300) -> tuple[int, str]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return proc.returncode, (proc.stdout + proc.stderr).strip()
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        return 1, str(exc)


def pip_install(*packages: str) -> None:
    log(f"กำลังติดตั้ง: {' '.join(packages)}", "⬇")
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "-q", *packages],
        check=False,
    )


# ── ข้อมูลการ์ดจอ ────────────────────────────────────────────
def gpu_info() -> dict:
    """อ่านสเปกการ์ดจอผ่าน nvidia-smi (ไม่ต้องพึ่ง torch ตอนเริ่มต้น)."""
    info = {
        "gpu_name": "",
        "gpu_vram_mb": 0,
        "gpu_used_mb": 0,
        "gpu_util": 0,
        "driver": "",
        "runtime": f"python {platform.python_version()} / {platform.system()}",
    }
    code, out = run(
        [
            "nvidia-smi",
            "--query-gpu=name,memory.total,memory.used,utilization.gpu,driver_version",
            "--format=csv,noheader,nounits",
        ],
        timeout=20,
    )
    if code == 0 and out:
        parts = [item.strip() for item in out.splitlines()[0].split(",")]
        if len(parts) >= 5:
            info.update(
                gpu_name=parts[0],
                gpu_vram_mb=int(float(parts[1])),
                gpu_used_mb=int(float(parts[2])),
                gpu_util=int(float(parts[3])),
                driver=parts[4],
            )
    return info


def capabilities() -> list[str]:
    caps = ["text"]
    info = gpu_info()
    if info["gpu_vram_mb"] >= 8000:
        caps += ["image", "audio"]
    caps.append("embedding")
    return caps


# ── ไคลเอนต์คุยกับเซิร์ฟเวอร์ ──────────────────────────────────
class SpiceClient:
    def __init__(self, server: str, token: str = "", worker_id: str = "") -> None:
        self.server = server.rstrip("/")
        self.token = token
        self.worker_id = worker_id
        self.session = requests.Session()

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def post(self, path: str, payload: dict, timeout: int = 30) -> dict:
        resp = self.session.post(
            f"{self.server}{path}", json=payload, headers=self._headers(), timeout=timeout
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"{path} → {resp.status_code}: {resp.text[:300]}")
        return resp.json()

    def get(self, path: str, timeout: int = 30) -> dict:
        resp = self.session.get(f"{self.server}{path}", headers=self._headers(), timeout=timeout)
        if resp.status_code >= 400:
            raise RuntimeError(f"{path} → {resp.status_code}: {resp.text[:300]}")
        return resp.json()

    def register(self, pair_code: str, name: str) -> dict:
        info = gpu_info()
        data = self.post(
            "/api/v1/worker/register",
            {
                "pair_code": pair_code,
                "name": name,
                "capabilities": capabilities(),
                **{k: info[k] for k in ("gpu_name", "gpu_vram_mb", "driver", "runtime")},
            },
        )
        self.token = data["worker_token"]
        self.worker_id = data["worker_id"]
        return data

    def heartbeat(self, status: str, drive_mounted: bool) -> dict:
        info = gpu_info()
        return self.post(
            "/api/v1/worker/heartbeat",
            {
                "status": status,
                "drive_mounted": drive_mounted,
                "warm_models": list(_warm_models),
                **{k: info[k] for k in ("gpu_used_mb", "gpu_util", "gpu_name", "gpu_vram_mb")},
            },
            timeout=20,
        )

    def lease(self) -> dict | None:
        return self.post("/api/v1/worker/lease", {}, timeout=25).get("job")

    def progress(self, job_id: str, value: float, message: str = "", level: str = "info") -> None:
        try:
            self.post(
                f"/api/v1/worker/jobs/{job_id}/progress",
                {"progress": value, "message": message, "level": level},
                timeout=15,
            )
        except Exception as exc:  # รายงานความคืบหน้าล้มเหลวไม่ควรทำให้งานตาย
            log(f"ส่งความคืบหน้าไม่สำเร็จ: {exc}", "⚠")

    def complete(self, job_id: str, result: str = "", error: str = "", meta: dict | None = None) -> None:
        self.post(
            f"/api/v1/worker/jobs/{job_id}/complete",
            {"result": result, "error": error, "meta": meta or {}},
            timeout=60,
        )

    def rclone_conf(self) -> str:
        return self.get("/api/v1/worker/rclone").get("conf", "")


# ── เมานต์ Google Drive ด้วย rclone ───────────────────────────
def ensure_rclone() -> bool:
    if shutil.which("rclone"):
        return True
    log("ติดตั้ง rclone…", "⬇")
    code, out = run(["bash", "-c", "curl -sSL https://rclone.org/install.sh | sudo bash"], timeout=300)
    if shutil.which("rclone"):
        return True
    log(f"ติดตั้ง rclone ไม่สำเร็จ: {out[-200:]}", "⚠")
    return False


def mount_drive(client: SpiceClient) -> bool:
    """ดึง rclone.conf จากเซิร์ฟเวอร์ (สิทธิ์ของเจ้าของเครื่อง) แล้วเมานต์ Drive."""
    try:
        conf = client.rclone_conf()
    except Exception as exc:
        log(f"ยังเมานต์ Drive ไม่ได้ ({exc}) — ข้ามไปก่อน ระบบยังรันงานได้ปกติ", "⚠")
        return False
    if not conf.strip() or not ensure_rclone():
        return False

    conf_dir = os.path.expanduser("~/.config/rclone")
    os.makedirs(conf_dir, exist_ok=True)
    conf_path = os.path.join(conf_dir, "rclone.conf")
    with open(conf_path, "w", encoding="utf-8") as handle:
        handle.write(conf)
    os.chmod(conf_path, 0o600)

    os.makedirs(RCLONE_MOUNT, exist_ok=True)
    code, out = run(
        [
            "bash", "-c",
            f"fusermount -uz {RCLONE_MOUNT} 2>/dev/null; "
            f"nohup rclone mount gdrive: {RCLONE_MOUNT} "
            f"--vfs-cache-mode full --vfs-cache-max-size 8G --dir-cache-time 30s "
            f"--allow-non-empty --daemon > /tmp/rclone.log 2>&1",
        ],
        timeout=120,
    )
    for _ in range(20):
        if os.path.ismount(RCLONE_MOUNT) or os.listdir(RCLONE_MOUNT):
            log(f"เมานต์ Google Drive แล้วที่ {RCLONE_MOUNT}", "✅")
            return True
        time.sleep(1)
    log("เมานต์ Drive ไม่สำเร็จ — จะใช้คำสั่ง rclone copy แทนเมื่อจำเป็น", "⚠")
    return False


def resolve_path(path: str) -> str:
    """แปลง 'gdrive:folder/file' ให้เป็นพาธจริงถ้าเมานต์ไว้แล้ว."""
    if path.startswith("gdrive:"):
        return os.path.join(RCLONE_MOUNT, path.split(":", 1)[1].lstrip("/"))
    return path


def push_to_drive(local_path: str, remote: str) -> str:
    if not remote:
        return ""
    target = remote if remote.startswith("gdrive:") else f"gdrive:{remote.lstrip('/')}"
    code, out = run(["rclone", "copy", local_path, target, "--no-traverse"], timeout=600)
    return target if code == 0 else f"(อัปโหลดไม่สำเร็จ: {out[-150:]})"


# ── ตัวรันโมเดล ───────────────────────────────────────────────
def _torch():
    import torch  # noqa: PLC0415 — โหลดตอนใช้จริงเพื่อให้เริ่มเครื่องได้ไว

    return torch


def run_text(job: dict, client: SpiceClient) -> tuple[str, dict]:
    payload = job["payload"]
    repo = payload.get("repo", "Qwen/Qwen2.5-7B-Instruct")
    client.progress(job["id"], 0.1, f"เตรียมโมเดล {repo}")

    try:
        import transformers  # noqa: F401
    except ImportError:
        pip_install("transformers>=4.44", "accelerate", "sentencepiece")
    from transformers import AutoModelForCausalLM, AutoTokenizer

    torch = _torch()
    quantize = payload.get("quantize", "fp16")
    cache_key = f"text:{repo}:{quantize}"

    if cache_key not in _model_cache:
        client.progress(job["id"], 0.2, "กำลังโหลดน้ำหนักโมเดล (ครั้งแรกใช้เวลาสักครู่)")
        kwargs: dict = {"device_map": "auto"}
        if quantize == "4bit" and torch.cuda.is_available():
            try:
                import bitsandbytes  # noqa: F401
            except ImportError:
                pip_install("bitsandbytes")
            from transformers import BitsAndBytesConfig

            kwargs["quantization_config"] = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=torch.float16,
                bnb_4bit_quant_type="nf4",
            )
        else:
            kwargs["torch_dtype"] = torch.float16 if torch.cuda.is_available() else torch.float32

        tokenizer = AutoTokenizer.from_pretrained(repo)
        model = AutoModelForCausalLM.from_pretrained(repo, **kwargs)
        _model_cache[cache_key] = (tokenizer, model)

    tokenizer, model = _model_cache[cache_key]
    client.progress(job["id"], 0.5, "โมเดลพร้อม เริ่มสร้างคำตอบ")

    messages = []
    if payload.get("system"):
        messages.append({"role": "system", "content": payload["system"]})
    prompt = payload.get("prompt", "")
    if payload.get("drive_input"):
        source = resolve_path(payload["drive_input"])
        if os.path.isfile(source):
            with open(source, "r", encoding="utf-8", errors="ignore") as handle:
                prompt = f"{prompt}\n\n--- เนื้อหาไฟล์ {os.path.basename(source)} ---\n{handle.read()[:20000]}"
    messages.append({"role": "user", "content": prompt})

    try:
        text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    except (ValueError, AttributeError):
        text = "\n".join(item["content"] for item in messages)

    inputs = tokenizer(text, return_tensors="pt").to(model.device)
    started = time.time()
    with _torch().inference_mode():
        output = model.generate(
            **inputs,
            max_new_tokens=int(payload.get("max_tokens", 512)),
            temperature=float(payload.get("temperature", 0.7)) or 0.01,
            do_sample=float(payload.get("temperature", 0.7)) > 0,
            pad_token_id=tokenizer.eos_token_id,
        )
    generated = output[0][inputs["input_ids"].shape[-1] :]
    answer = tokenizer.decode(generated, skip_special_tokens=True).strip()

    elapsed = time.time() - started
    meta = {
        "tokens": int(generated.shape[-1]),
        "seconds": round(elapsed, 2),
        "tokens_per_second": round(int(generated.shape[-1]) / elapsed, 1) if elapsed else 0,
        "repo": repo,
    }
    if payload.get("drive_output"):
        out_file = "/tmp/spice_output.txt"
        with open(out_file, "w", encoding="utf-8") as handle:
            handle.write(answer)
        meta["drive_saved"] = push_to_drive(out_file, payload["drive_output"])
    return answer, meta


def run_image(job: dict, client: SpiceClient) -> tuple[str, dict]:
    payload = job["payload"]
    client.progress(job["id"], 0.1, "เตรียมโมเดลสร้างภาพ")
    try:
        import diffusers  # noqa: F401
    except ImportError:
        pip_install("diffusers", "accelerate", "transformers")
    from diffusers import AutoPipelineForText2Image

    torch = _torch()
    repo = payload.get("repo", "stabilityai/sdxl-turbo")
    cache_key = f"image:{repo}"
    if cache_key not in _model_cache:
        client.progress(job["id"], 0.3, "กำลังโหลดโมเดลภาพ")
        pipe = AutoPipelineForText2Image.from_pretrained(
            repo,
            torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
            variant="fp16" if torch.cuda.is_available() else None,
        )
        pipe = pipe.to("cuda" if torch.cuda.is_available() else "cpu")
        _model_cache[cache_key] = pipe

    pipe = _model_cache[cache_key]
    client.progress(job["id"], 0.6, "กำลังวาดภาพ")
    steps = int(payload.get("steps", 2))
    image = pipe(
        prompt=payload.get("prompt", ""),
        num_inference_steps=steps,
        guidance_scale=float(payload.get("guidance", 0.0)),
    ).images[0]

    out_path = f"/tmp/spice_{job['id']}.png"
    image.save(out_path)
    meta = {"file": out_path, "steps": steps, "repo": repo}
    if payload.get("drive_output"):
        meta["drive_saved"] = push_to_drive(out_path, payload["drive_output"])

    # ส่งกลับเป็น data URL เพื่อให้หน้าเว็บแสดงภาพได้ทันที
    import base64

    with open(out_path, "rb") as handle:
        encoded = base64.b64encode(handle.read()).decode()
    return f"data:image/png;base64,{encoded}", meta


def run_audio(job: dict, client: SpiceClient) -> tuple[str, dict]:
    payload = job["payload"]
    source = resolve_path(payload.get("drive_input", ""))
    if not source or not os.path.isfile(source):
        raise RuntimeError("งานถอดเสียงต้องระบุไฟล์ใน Drive เช่น gdrive:audio/meeting.m4a")

    client.progress(job["id"], 0.2, f"เตรียมถอดเสียง {os.path.basename(source)}")
    try:
        import transformers  # noqa: F401
    except ImportError:
        pip_install("transformers>=4.44", "accelerate")
    from transformers import pipeline

    torch = _torch()
    repo = payload.get("repo", "openai/whisper-large-v3-turbo")
    cache_key = f"audio:{repo}"
    if cache_key not in _model_cache:
        _model_cache[cache_key] = pipeline(
            "automatic-speech-recognition",
            model=repo,
            torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
            device=0 if torch.cuda.is_available() else -1,
        )

    client.progress(job["id"], 0.5, "กำลังถอดเสียง")
    result = _model_cache[cache_key](source, return_timestamps=True)
    text = result["text"].strip() if isinstance(result, dict) else str(result)
    meta = {"source": source, "repo": repo, "chars": len(text)}
    if payload.get("drive_output"):
        out_file = "/tmp/spice_transcript.txt"
        with open(out_file, "w", encoding="utf-8") as handle:
            handle.write(text)
        meta["drive_saved"] = push_to_drive(out_file, payload["drive_output"])
    return text, meta


def run_embedding(job: dict, client: SpiceClient) -> tuple[str, dict]:
    payload = job["payload"]
    client.progress(job["id"], 0.2, "เตรียมโมเดล embedding")
    try:
        import sentence_transformers  # noqa: F401
    except ImportError:
        pip_install("sentence-transformers")
    from sentence_transformers import SentenceTransformer

    repo = payload.get("repo", "BAAI/bge-m3")
    cache_key = f"embed:{repo}"
    if cache_key not in _model_cache:
        _model_cache[cache_key] = SentenceTransformer(repo)

    texts = payload.get("texts") or [payload.get("prompt", "")]
    vectors = _model_cache[cache_key].encode(texts, normalize_embeddings=True)
    client.progress(job["id"], 0.9, f"ทำเวกเตอร์เสร็จ {len(texts)} ชิ้น")
    return json.dumps(
        {"dim": int(vectors.shape[-1]), "vectors": [v.tolist() for v in vectors]},
        ensure_ascii=False,
    ), {"count": len(texts), "dim": int(vectors.shape[-1]), "repo": repo}


RUNNERS = {
    "text": run_text,
    "image": run_image,
    "audio": run_audio,
    "embedding": run_embedding,
}


# ── ลูปหลัก ───────────────────────────────────────────────────
def heartbeat_loop(client: SpiceClient, state: dict) -> None:
    while not _stop.is_set():
        try:
            client.heartbeat(state["status"], state["drive_mounted"])
        except Exception as exc:
            log(f"ส่งสัญญาณชีพไม่สำเร็จ: {exc}", "⚠")
        _stop.wait(HEARTBEAT_SECONDS)


def handle_job(client: SpiceClient, job: dict, state: dict) -> None:
    kind = job.get("kind", "text")
    log(f"รับงาน {job['id']} · {kind} · {job.get('model', '')}", "⚙")
    state["status"] = "busy"
    started = time.time()
    try:
        runner = RUNNERS.get(kind)
        if runner is None:
            raise RuntimeError(f"เครื่องนี้ยังรันงานชนิด '{kind}' ไม่ได้")
        result, meta = runner(job, client)
        mark_warm(job.get("model", ""))          # โมเดลนี้อยู่ใน VRAM แล้ว
        meta["total_seconds"] = round(time.time() - started, 2)
        meta["warm_models"] = list(_warm_models)
        client.complete(job["id"], result=result, meta=meta)
        log(f"เสร็จ {job['id']} ใน {meta['total_seconds']} วินาที", "✅")
    except Exception as exc:
        detail = f"{type(exc).__name__}: {exc}"
        log(f"งานล้มเหลว: {detail}", "❌")
        traceback.print_exc()
        if "out of memory" in detail.lower():
            # คืน VRAM ให้หมดก่อน ไม่งั้นงานที่เซิร์ฟเวอร์ส่งมาใหม่ก็จะพังซ้ำ
            log("ล้างโมเดลออกจาก VRAM เพื่อเปิดทางให้งานถัดไป", "🧹")
            _model_cache.clear()
            _warm_models.clear()
            try:
                import gc
                import torch

                gc.collect()
                torch.cuda.empty_cache()
            except Exception:
                pass
        try:
            client.complete(job["id"], error=detail[:4000])
        except Exception as inner:
            log(f"แจ้งผลล้มเหลวไม่สำเร็จ: {inner}", "⚠")
    finally:
        state["status"] = "idle"


def main() -> int:
    parser = argparse.ArgumentParser(description="Spice worker — ยืมการ์ดจอให้ระบบ")
    parser.add_argument("--server", required=True, help="URL ของเซิร์ฟเวอร์ Spice")
    parser.add_argument("--pair", required=True, help="รหัสจับคู่จากหน้าเว็บ (เช่น K7QD-2M9X)")
    parser.add_argument("--name", default="", help="ชื่อเครื่องที่จะแสดงในหน้าเว็บ")
    parser.add_argument("--no-drive", action="store_true", help="ไม่ต้องเมานต์ Google Drive")
    args = parser.parse_args()

    info = gpu_info()
    name = args.name or (f"Colab · {info['gpu_name']}" if info["gpu_name"] else "Colab CPU")

    print("═" * 64)
    print("  🌶  Spice Worker")
    print(f"  การ์ดจอ : {info['gpu_name'] or 'ไม่พบ GPU (จะทำงานบน CPU ซึ่งช้ามาก)'}")
    print(f"  VRAM    : {info['gpu_vram_mb']} MB   ไดรเวอร์: {info['driver'] or '-'}")
    print(f"  เซิร์ฟเวอร์: {args.server}")
    print("═" * 64)

    if not info["gpu_name"]:
        log("แนะนำให้เปลี่ยนเป็น GPU ก่อน: Runtime → Change runtime type → T4 GPU", "⚠")

    client = SpiceClient(args.server)
    try:
        data = client.register(args.pair, name)
    except Exception as exc:
        log(f"จับคู่ไม่สำเร็จ: {exc}", "❌")
        return 1
    log(f"จับคู่สำเร็จกับบัญชี {data.get('owner_email', '')} · เครื่อง {client.worker_id}", "🔗")

    state = {"status": "idle", "drive_mounted": False}
    if not args.no_drive:
        state["drive_mounted"] = mount_drive(client)

    threading.Thread(target=heartbeat_loop, args=(client, state), daemon=True).start()

    def shutdown(*_args):
        log("กำลังปิดเครื่องอย่างสุภาพ…", "👋")
        _stop.set()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    log("พร้อมรับงานแล้ว — กลับไปสั่งงานที่หน้าเว็บได้เลย", "🚀")
    idle_ticks = 0
    while not _stop.is_set():
        try:
            job = client.lease()
        except Exception as exc:
            log(f"ติดต่อเซิร์ฟเวอร์ไม่ได้: {exc}", "⚠")
            _stop.wait(10)
            continue

        if job:
            idle_ticks = 0
            handle_job(client, job, state)
        else:
            idle_ticks += 1
            if idle_ticks % 60 == 0:
                log("ยังว่างอยู่ รอคิวงาน…", "💤")
            _stop.wait(POLL_SECONDS)

    log("ปิดเครื่องเรียบร้อย", "✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
