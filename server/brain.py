"""สมองของ Spice — อ่านคำสั่งภาษาคน แล้วตัดสินใจแทนผู้ใช้.

ทำสามอย่าง โดยไม่ต้องเรียกโมเดลใด ๆ (เร็ว ทำนายผลได้ และเทสต์ได้):

1. **อ่านเจตนา** — ภาษาอะไร งานชนิดไหน ยาวแค่ไหน ควรสร้างสรรค์หรือเป๊ะ
2. **เลือกโมเดลและพารามิเตอร์** — ให้พอดีกับ VRAM ที่มีอยู่จริงตอนนั้น
   พร้อมบอกเหตุผลเป็นภาษาคน
3. **วางแผนเป็นลูกโซ่** — งานที่ต้องทำหลายต่อ เช่น ถอดเสียง → สรุป → เก็บลง Drive
   จะถูกแตกเป็นขั้น ๆ ให้อัตโนมัติ

ทุกการตัดสินใจมี `reason` กำกับเสมอ เพราะระบบที่ฉลาดแต่ไม่บอกว่าคิดยังไง
คือระบบที่เชื่อถือไม่ได้.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field, asdict

from . import catalog

# ── สัญญาณที่ใช้อ่านเจตนา ────────────────────────────────────
THAI_RANGE = re.compile(r"[฀-๿]")

AUDIO_EXT = {".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac", ".wma", ".opus",
             ".mp4", ".mov", ".mkv", ".webm", ".avi"}
DOC_EXT = {".txt", ".md", ".csv", ".json", ".log", ".srt", ".vtt", ".html", ".xml", ".py"}

KEYWORDS: dict[str, tuple[str, ...]] = {
    "draw": (
        "วาดรูป", "วาดภาพ", "สร้างภาพ", "สร้างรูป", "ออกแบบภาพ", "ทำภาพ", "ภาพประกอบ",
        "โลโก้", "ภาพปก", "รูปปก", "generate image", "draw ", "picture of", "poster",
        "illustration", "logo", "artwork", "photo of",
    ),
    "transcribe": (
        "ถอดเสียง", "ถอดเทป", "ถอดคำพูด", "ทำซับ", "ซับไตเติล", "คำบรรยาย", "ถอดข้อความจากเสียง",
        "transcribe", "transcription", "subtitle", "speech to text",
    ),
    "code": (
        "เขียนโค้ด", "เขียนสคริปต์", "เขียนฟังก์ชัน", "โค้ด", "สคริปต์", "ฟังก์ชัน", "ดีบัก",
        "แก้บั๊ก", "แก้บัค", "regex", "sql", "python", "javascript", "typescript", "bash",
        "docker", "api", "function", "script", "debug", "refactor", "stack trace",
        "error:", "exception", "compile",
    ),
    "summarize": (
        "สรุป", "ย่อความ", "ย่อให้", "ใจความสำคัญ", "ประเด็นหลัก", "tldr", "tl;dr",
        "summarize", "summary", "key points", "recap",
    ),
    "translate": (
        "แปลเป็น", "แปลให้", "แปลข้อความ", "แปลบทความ", "แปลไทย", "แปลอังกฤษ",
        "translate", "translation", "เป็นภาษาอังกฤษ", "เป็นภาษาไทย",
    ),
    "creative": (
        "แต่งกลอน", "แต่งเพลง", "เขียนนิยาย", "เรื่องสั้น", "ไอเดีย", "ระดมสมอง", "คิดชื่อ",
        "ตั้งชื่อ", "แคปชัน", "สโลแกน", "โฆษณา", "brainstorm", "ideas", "slogan",
        "caption", "story", "poem", "creative",
    ),
    "embed": (
        "ทำเวกเตอร์", "ทำ embedding", "ทำดัชนี", "จัดทำดัชนี", "embedding", "vectorize", "index this",
    ),
    "analyze": (
        "วิเคราะห์", "เปรียบเทียบ", "ข้อดีข้อเสีย", "ประเมิน", "ตรวจสอบ", "หาสาเหตุ",
        "analyze", "compare", "evaluate", "pros and cons", "review",
    ),
    "longform": (
        "เขียนบทความ", "เขียนรายงาน", "เรียงความ", "บล็อก", "เขียนยาว", "ละเอียด",
        "อย่างละเอียด", "ครบถ้วน", "essay", "article", "blog post", "in detail",
        "comprehensive", "long form",
    ),
    "short": (
        "สั้น ๆ", "สั้นๆ", "กระชับ", "ย่อ ๆ", "หนึ่งประโยค", "บรรทัดเดียว", "ข้อเดียว",
        "briefly", "one sentence", "in short", "concise",
    ),
    "question": (
        "คืออะไร", "ยังไง", "อย่างไร", "ทำไม", "เมื่อไหร่", "ที่ไหน", "ใคร", "ไหม", "หรือเปล่า",
        "what is", "how do", "how to", "why ", "when ", "where ", "who ",
    ),
    "save_drive": (
        "บันทึกลง drive", "เซฟลง drive", "เก็บลง drive", "อัปโหลดขึ้น drive",
        "save to drive", "upload to drive",
    ),
}

# งานที่ต้องคิดเป็นขั้นเป็นตอน ควรใช้โมเดลตัวใหญ่
HEAVY_TASKS = {"code", "analyze"}
# งานตรงไปตรงมา โมเดลเล็กก็เอาอยู่ เร็วกว่ามาก
LIGHT_TASKS = {"summarize", "translate", "chat"}


@dataclass
class Intent:
    kind: str = "text"          # text | image | audio | embedding
    task: str = "chat"          # chat | code | summarize | translate | creative | transcribe | draw | embed | analyze
    language: str = "th"        # th | en | mixed
    length: str = "standard"    # short | standard | long
    max_tokens: int = 512
    temperature: float = 0.6
    wants_context: bool = False
    signals: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Step:
    """หนึ่งขั้นในลูกโซ่งาน."""

    kind: str
    model: str
    title: str
    prompt: str = ""
    use_previous: bool = False   # เอาผลลัพธ์ของขั้นก่อนหน้ามาต่อท้ายคำสั่ง
    drive_input: str = ""
    drive_output: str = ""
    max_tokens: int = 512
    temperature: float = 0.6

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Plan:
    steps: list[Step]
    reason: str
    intent: Intent
    eta_seconds: float = 0
    warnings: list[str] = field(default_factory=list)
    uses_vault: bool = False
    downgraded: bool = False

    def as_dict(self) -> dict:
        return {
            "steps": [step.as_dict() for step in self.steps],
            "reason": self.reason,
            "intent": self.intent.as_dict(),
            "eta_seconds": round(self.eta_seconds, 1),
            "warnings": self.warnings,
            "uses_vault": self.uses_vault,
            "downgraded": self.downgraded,
        }


# ── ขั้นที่ 1 · อ่านเจตนา ─────────────────────────────────────
def detect_language(text: str) -> str:
    thai = len(THAI_RANGE.findall(text))
    letters = len(re.findall(r"[A-Za-z฀-๿]", text))
    if not letters:
        return "th"
    ratio = thai / letters
    # เกณฑ์ฝั่งไทยตั้งไว้ค่อนข้างต่ำ เพราะคนไทยมักพิมพ์ไทยปนศัพท์เทคนิคอังกฤษ
    # เช่น "ช่วย refactor ฟังก์ชัน handleSubmit ให้หน่อย" ซึ่งควรถือเป็นภาษาไทย
    if ratio >= 0.4:
        return "th"
    if ratio < 0.15:
        return "en"
    return "mixed"


def _hits(text: str, bucket: str) -> bool:
    return any(word in text for word in KEYWORDS[bucket])


def analyze(prompt: str, drive_input: str = "") -> Intent:
    """อ่านคำสั่งดิบ ๆ แล้วสรุปว่าผู้ใช้ต้องการอะไร."""
    text = f"{prompt} {drive_input}".lower()
    extension = os.path.splitext(drive_input)[1].lower() if drive_input else ""
    signals: list[str] = []

    # ชนิดของงาน — ไฟล์เสียงเป็นหลักฐานที่หนักแน่นกว่าคำพูด
    if extension in AUDIO_EXT:
        kind, task = "audio", "transcribe"
        signals.append(f"ไฟล์ต้นทางเป็นสื่อเสียง/วิดีโอ ({extension})")
    elif _hits(text, "transcribe"):
        kind, task = "audio", "transcribe"
        signals.append("พบคำที่สื่อถึงการถอดเสียง")
    elif _hits(text, "draw"):
        kind, task = "image", "draw"
        signals.append("พบคำที่สื่อถึงการสร้างภาพ")
    elif _hits(text, "embed"):
        kind, task = "embedding", "embed"
        signals.append("พบคำที่สื่อถึงการทำเวกเตอร์")
    else:
        kind = "text"
        if _hits(text, "code"):
            task = "code"
            signals.append("เป็นงานเขียน/แก้โค้ด")
        elif _hits(text, "analyze"):
            task = "analyze"
            signals.append("เป็นงานวิเคราะห์เปรียบเทียบ")
        elif _hits(text, "translate"):
            task = "translate"
            signals.append("เป็นงานแปลภาษา")
        elif _hits(text, "summarize"):
            task = "summarize"
            signals.append("เป็นงานสรุปความ")
        elif _hits(text, "creative"):
            task = "creative"
            signals.append("เป็นงานสร้างสรรค์")
        else:
            task = "chat"

    # ความยาวคำตอบที่เหมาะสม
    if _hits(text, "short"):
        length, max_tokens = "short", 256
        signals.append("ผู้ใช้ขอคำตอบสั้น")
    elif _hits(text, "longform") or len(prompt) > 1200:
        length, max_tokens = "long", 2048
        signals.append("เป็นงานเขียนยาวหรือคำสั่งยาวมาก")
    else:
        length, max_tokens = "standard", 768

    if task == "code":
        max_tokens = max(max_tokens, 1536)     # โค้ดถูกตัดกลางคันแล้วใช้ไม่ได้เลย
    if task == "transcribe":
        max_tokens = 4096

    # อุณหภูมิ: งานที่ต้องถูกต้องให้เป๊ะ งานสร้างสรรค์ให้หลากหลาย
    temperature = {
        "code": 0.2, "translate": 0.3, "summarize": 0.35, "analyze": 0.4,
        "transcribe": 0.0, "embed": 0.0, "draw": 0.9, "creative": 0.95,
    }.get(task, 0.6)

    # ควรดึงความรู้จากคลังมาช่วยไหม — คำถามลอย ๆ ที่ไม่มีไฟล์แนบคือเป้าหมายหลัก
    wants_context = (
        kind == "text"
        and not drive_input
        and (_hits(text, "question") or task in {"chat", "analyze"})
    )
    if wants_context:
        signals.append("เป็นคำถามที่อาจมีคำตอบอยู่ในคลังความรู้")

    return Intent(
        kind=kind, task=task, language=detect_language(prompt), length=length,
        max_tokens=max_tokens, temperature=temperature,
        wants_context=wants_context, signals=signals,
    )


# ── ขั้นที่ 2 · เลือกโมเดลให้พอดีกับเครื่องที่มีอยู่จริง ───────
def _candidates(kind: str) -> list[dict]:
    return [model for model in catalog.MODELS if model["kind"] == kind]


def pick_model(intent: Intent, capacity: dict) -> tuple[str, str, list[str]]:
    """คืน (model_id, เหตุผล, คำเตือน) โดยดูทั้งเจตนาและ VRAM ที่ว่างอยู่จริง."""
    best_vram = capacity.get("best_vram_mb", 0)
    warm: set[str] = set(capacity.get("warm", ()))
    warnings: list[str] = []
    pool = _candidates(intent.kind)

    if intent.kind != "text":
        model = pool[0]
        reason = f"งานชนิด “{intent.kind}” มีโมเดลเฉพาะทางอยู่ตัวเดียวคือ {model['label']}"
        if best_vram and best_vram < model["vram_mb"]:
            warnings.append(
                f"เครื่องที่ออนไลน์มี VRAM {best_vram} MB ซึ่งน้อยกว่าที่ {model['label']} "
                f"ต้องใช้ ({model['vram_mb']} MB) — งานจะรอจนกว่าจะมีเครื่องที่ไหว"
            )
        return model["id"], reason, warnings

    # เรียงจากตัวที่ "อยากได้ที่สุด" ลงมา ตามลักษณะงานและภาษา
    if intent.task in HEAVY_TASKS or intent.length == "long":
        # ตัวใหญ่ก่อนเสมอ ส่วนตัวสำรองเลือกตามภาษาของคำสั่ง
        backup = (
            ["typhoon2-3b-instruct", "llama-3.2-3b-instruct"]
            if intent.language == "th"
            else ["llama-3.2-3b-instruct", "typhoon2-3b-instruct"]
        )
        ranked = ["qwen2.5-7b-instruct", *backup]
        why = "งานนี้ต้องใช้ความสามารถในการให้เหตุผลสูง จึงเลือกโมเดลตัวใหญ่ที่สุดก่อน"
    elif intent.language == "th":
        ranked = ["typhoon2-3b-instruct", "qwen2.5-7b-instruct", "llama-3.2-3b-instruct"]
        why = "คำสั่งเป็นภาษาไทยและเป็นงานตรงไปตรงมา จึงเลือกโมเดลไทยตัวเล็กที่ตอบไวกว่า"
    else:
        ranked = ["llama-3.2-3b-instruct", "qwen2.5-7b-instruct", "typhoon2-3b-instruct"]
        why = "คำสั่งเป็นภาษาอังกฤษและไม่ซับซ้อน จึงเลือกโมเดลเบาที่ตอบไว"

    # เครื่องที่โหลดโมเดลค้างไว้แล้วเริ่มงานได้ทันที — ได้เปรียบมากพอที่จะสลับอันดับ
    warm_choice = next((mid for mid in ranked if mid in warm), None)
    if warm_choice and warm_choice != ranked[0]:
        first = catalog.get(ranked[0])
        if not (intent.task in HEAVY_TASKS and warm_choice != ranked[0]):
            ranked = [warm_choice] + [mid for mid in ranked if mid != warm_choice]
            why = (
                f"{catalog.get(warm_choice)['label']} ถูกโหลดค้างไว้ในเครื่องอยู่แล้ว "
                f"จึงเริ่มงานได้ทันทีโดยไม่ต้องรอโหลดใหม่ (เร็วกว่า {first['label']} มากในรอบแรก)"
            )

    if best_vram:
        fitting = [mid for mid in ranked if catalog.get(mid)["vram_mb"] <= best_vram]
        if not fitting:
            smallest = min(pool, key=lambda m: m["vram_mb"])
            warnings.append(
                f"ไม่มีเครื่องไหน VRAM ถึงเลย ({best_vram} MB) — เลือก {smallest['label']} "
                f"ซึ่งเล็กที่สุด งานจะรอในคิวจนกว่าจะมีเครื่องที่ไหว"
            )
            return smallest["id"], why, warnings
        if fitting[0] != ranked[0]:
            wanted = catalog.get(ranked[0])
            picked = catalog.get(fitting[0])
            warnings.append(
                f"อยากใช้ {wanted['label']} แต่ VRAM ที่มี ({best_vram} MB) ไม่พอ "
                f"จึงลดมาใช้ {picked['label']} แทน"
            )
        ranked = fitting

    chosen = catalog.get(ranked[0])
    return ranked[0], f"{why} → เลือก {chosen['label']}", warnings


# ── ขั้นที่ 3 · ประเมินเวลา ───────────────────────────────────
def estimate_seconds(model_id: str, history: dict[str, float], warm: set[str],
                     queue_ahead: int = 0) -> float:
    """ประเมินเวลาที่จะได้ผลลัพธ์ จากสถิติจริงของผู้ใช้ + ค่าโหลดโมเดลครั้งแรก."""
    model = catalog.get(model_id)
    if model is None:
        return 0.0

    measured = history.get(model_id)
    if measured:
        run_seconds = measured
    else:
        # ยังไม่เคยรัน — ประเมินหยาบ ๆ จากขนาดโมเดลและชนิดงาน
        base = {"text": 12.0, "image": 8.0, "audio": 25.0, "embedding": 5.0}[model["kind"]]
        run_seconds = base * (1 + model["vram_mb"] / 16000)

    # โมเดลที่ยังไม่ถูกโหลด ต้องเสียเวลาดาวน์โหลด/ย้ายเข้า VRAM ก่อน
    cold_start = 0.0 if model_id in warm else 25.0 + model["vram_mb"] / 220.0
    return run_seconds + cold_start + queue_ahead * (run_seconds + 2)


# ── ขั้นที่ 4 · วางแผนทั้งงาน ────────────────────────────────
def build_plan(
    prompt: str,
    drive_input: str = "",
    drive_output: str = "",
    capacity: dict | None = None,
    history: dict[str, float] | None = None,
    vault_available: int = 0,
) -> Plan:
    """แปลงคำสั่งภาษาคนหนึ่งประโยค ให้เป็นแผนงานที่ระบบรันได้จริง."""
    capacity = capacity or {}
    history = history or {}
    warm = set(capacity.get("warm", ()))
    intent = analyze(prompt, drive_input)
    text = f"{prompt} {drive_input}".lower()

    model_id, reason, warnings = pick_model(intent, capacity)
    steps: list[Step] = []

    wants_summary = _hits(text, "summarize") or _hits(text, "analyze")
    wants_save = bool(drive_output) or _hits(text, "save_drive")

    if intent.kind == "audio":
        # ถอดเสียงก่อนเสมอ แล้วค่อยต่อขั้นสรุปถ้าผู้ใช้ขอมาด้วย
        steps.append(Step(
            kind="audio", model=model_id, title="ถอดเสียงเป็นข้อความ",
            prompt=prompt, drive_input=drive_input,
            drive_output="" if wants_summary else (drive_output or ""),
            max_tokens=intent.max_tokens, temperature=0.0,
        ))
        if wants_summary:
            follow_intent = analyze("สรุปใจความสำคัญ")
            follow_model, follow_reason, follow_warn = pick_model(follow_intent, capacity)
            warnings += follow_warn
            steps.append(Step(
                kind="text", model=follow_model, title="สรุปสิ่งที่ถอดเสียงได้",
                prompt=(
                    "สรุปใจความสำคัญของบทถอดเสียงต่อไปนี้เป็นภาษาไทย "
                    "แยกเป็นหัวข้อ และปิดท้ายด้วยสิ่งที่ต้องทำต่อ"
                ),
                use_previous=True, drive_output=drive_output or "",
                max_tokens=1024, temperature=0.35,
            ))
            reason = (
                "ไฟล์ต้นทางเป็นสื่อเสียง และคำสั่งขอให้สรุปด้วย "
                "จึงวางเป็นลูกโซ่สองขั้น: ถอดเสียงก่อน แล้วส่งบทถอดเสียงต่อให้โมเดลภาษาสรุป"
            )
    else:
        steps.append(Step(
            kind=intent.kind, model=model_id, title=prompt.strip()[:60] or "งานใหม่",
            prompt=prompt, drive_input=drive_input, drive_output=drive_output or "",
            max_tokens=intent.max_tokens, temperature=intent.temperature,
        ))

    if wants_save and not any(step.drive_output for step in steps):
        steps[-1].drive_output = drive_output or "gdrive:spice/outputs"
        warnings.append(f"จะบันทึกผลลัพธ์ไปที่ {steps[-1].drive_output} ให้อัตโนมัติ")

    uses_vault = bool(intent.wants_context and vault_available)
    if uses_vault:
        reason += " · จะดึงเอกสารที่เกี่ยวข้องจากคลังความรู้มาเป็นบริบทให้ด้วย"

    eta = 0.0
    running_warm = set(warm)
    for index, step in enumerate(steps):
        eta += estimate_seconds(step.model, history, running_warm,
                                queue_ahead=capacity.get("queue_ahead", 0) if index == 0 else 0)
        running_warm.add(step.model)   # ขั้นถัดไปเจอโมเดลที่เพิ่งโหลดไปแล้ว

    if not capacity.get("online"):
        warnings.append("ยังไม่มีเครื่อง GPU ออนไลน์ — งานจะรอในคิวจนกว่าจะเชื่อมเครื่อง")

    return Plan(
        steps=steps, reason=reason, intent=intent, eta_seconds=eta,
        warnings=warnings, uses_vault=uses_vault,
        downgraded=any("ไม่พอ" in warning or "ไม่มีเครื่องไหน" in warning for warning in warnings),
    )


# ── กู้สถานการณ์: หาโมเดลเล็กกว่าเมื่อ VRAM ไม่พอ ─────────────
OOM_MARKERS = (
    "out of memory", "cuda oom", "outofmemoryerror", "not enough memory",
    "no space left on device", "allocate", "memory error",
)


def is_out_of_memory(error: str) -> bool:
    lowered = (error or "").lower()
    return any(marker in lowered for marker in OOM_MARKERS)


def smaller_alternative(model_id: str) -> str | None:
    """โมเดลชนิดเดียวกันที่เล็กกว่าตัวปัจจุบันมากที่สุดเท่าที่ยังมี."""
    model = catalog.get(model_id)
    if model is None:
        return None
    smaller = [
        item for item in _candidates(model["kind"]) if item["vram_mb"] < model["vram_mb"]
    ]
    if not smaller:
        return None
    return max(smaller, key=lambda item: item["vram_mb"])["id"]
