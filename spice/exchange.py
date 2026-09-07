"""ให้ใครก็ได้เป็นตัวสืบค้น — ผ่านไฟล์ ไม่ต้องมีคีย์ ไม่ต้องมีเครือข่าย.

`ClaudeInvestigator` ต้องมี API key ซึ่งไม่ใช่ทุกที่จะมี แต่ปัญหาจริงของ
ระบบนี้คือ *คำตอบกลวง* ไม่ใช่ *ไม่มีคีย์* — และคนที่ตอบได้ดีอาจเป็นมนุษย์
ที่รู้เรื่องนั้นจริง เซสชัน LLM ที่เปิดอยู่แล้ว หรือผลการทดลองจริงก็ได้

โปรโตคอลมีสองจังหวะ:

    spice propose --out questions.json     # ก้นหอยบอกว่ารอบนี้อยากรู้อะไร
    (ใครก็ได้เติมช่อง answer ลงไปในไฟล์)
    spice absorb  --in  questions.json     # ก้นหอยรับคำตอบไปหมุนต่อ

คำถามที่ไม่มีใครตอบจะตกไปให้ตัวสืบค้นในตัวจัดการ ก้นหอยจึงไม่หยุดหมุน
เพราะมีคนตอบไม่ครบ.
"""

from __future__ import annotations

import json
from pathlib import Path

from .graph import KnowledgeGraph
from .investigator import canonical_label
from .spiral import Spiral
from .types import EdgeSpec, EpistemicStatus, Finding, NodeSpec, QuestionLevel, Relation

INSTRUCTIONS = (
    "เติมช่อง answer ของแต่ละคำถาม แล้วส่งไฟล์นี้กลับด้วย `spice absorb`\n"
    "กติกาที่ห้ามละเมิด:\n"
    "  1. `residual` ต้องไม่ว่าง — มันคือคำตอบของ 'คำตอบนี้อธิบายอะไรไม่ได้?'\n"
    "     ถ้าคิดว่าคำตอบสมบูรณ์แล้ว แปลว่ายังมองไม่เห็นขอบของมัน ให้ระบุขอบนั้น\n"
    "  2. `residual` ต้องเฉพาะเจาะจง ไม่ใช่ 'ยังต้องศึกษาเพิ่มเติม'\n"
    "  3. `label` ของ node ต้องเป็นแนวคิดสั้น ๆ ไม่เกิน 64 ตัวอักษร ไม่ใช่ประโยค\n"
    "  4. ไม่มั่นใจให้ลด confidence และตั้ง status เป็น UNCERTAIN/UNKNOWN\n"
    "     ความไม่รู้ที่ถูกทำเครื่องหมายไว้ตรง ๆ มีค่ากับระบบนี้มากกว่าคำตอบที่ฟังดูดี\n"
    "  5. ถ้าคำตอบขัดแย้งกับสิ่งที่มีในกราฟ ให้ระบุใน contradicts\n"
    "  ข้อไหนไม่อยากตอบ ปล่อยว่างไว้ได้ ระบบจะใช้ตัวสืบค้นในตัวแทน"
)

STATUSES = [s.value for s in EpistemicStatus]
RELATIONS = [r.value for r in Relation]


def _context(graph: KnowledgeGraph, q) -> dict:
    target = graph.node(q.targets[0]) if q.targets else None
    nearby: list[str] = []
    if target is not None:
        nearby = [
            graph.nodes[n].label
            for n in list(graph.neighbors(target.id, 1))[:8]
            if n in graph.nodes
        ]
    return {
        "target": target.label if target else None,
        "target_status": target.status.value if target else None,
        "target_open_residuals": list(target.residuals) if target else [],
        "nearby_concepts": nearby,
    }


def dump(spiral: Spiral, path: str | Path) -> Path:
    """เลือกคำถามของรอบถัดไป แล้วเขียนออกไปให้คนอื่นตอบ."""
    proposed = spiral.propose()
    payload = {
        "epoch": spiral.epoch,
        "instructions": INSTRUCTIONS,
        "enums": {"status": STATUSES, "relation": RELATIONS},
        "questions": [
            {
                "id": s.question.id,
                "text": s.question.text,
                "level": int(s.question.level),
                "level_th": s.question.level.th,
                "strategy": s.question.strategy,
                "scores": {k: round(v, 3) for k, v in s.question.scores.items()},
                **_context(spiral.graph, s.question),
                "answer": {
                    "answer": "",
                    "confidence": 0.5,
                    "new_nodes": [],
                    "new_edges": [],
                    "residual": "",
                    "contradicts": [],
                },
            }
            for s in proposed
        ],
    }
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def _finding(entry: dict) -> Finding | None:
    a = entry.get("answer") or {}
    text = str(a.get("answer", "")).strip()
    residual = str(a.get("residual", "")).strip()
    if not text or not residual:
        return None          # ตอบไม่ครบ = ยังไม่ถือว่าตอบ
    nodes = [
        NodeSpec(
            label=canonical_label(str(n["label"])),
            status=_enum(EpistemicStatus, n.get("status"), EpistemicStatus.PARTIALLY_KNOWN),
            confidence=_clamp(n.get("confidence", 0.4)),
            level=QuestionLevel(max(0, min(5, int(n.get("level", 0))))),
            tags=("exchange",),
        )
        for n in a.get("new_nodes", ())
        if str(n.get("label", "")).strip()
    ]
    edges = [
        EdgeSpec(
            source=canonical_label(str(e["source"])),
            target=canonical_label(str(e["target"])),
            relation=_enum(Relation, e.get("relation"), Relation.UNKNOWN_LINK),
        )
        for e in a.get("new_edges", ())
        if str(e.get("source", "")).strip() and str(e.get("target", "")).strip()
    ]
    return Finding(
        answer=text,
        confidence=_clamp(a.get("confidence", 0.5)),
        new_nodes=nodes,
        new_edges=edges,
        residual=residual,
        contradicts=[canonical_label(str(c)) for c in a.get("contradicts", ()) if str(c).strip()],
        cost=1.0,
        source="exchange",
    )


def load(spiral: Spiral, path: str | Path):
    """อ่านคำตอบกลับเข้ามาปิดรอบที่ `dump()` เปิดค้างไว้."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    findings: dict[str, Finding] = {}
    for entry in data.get("questions", ()):
        f = _finding(entry)
        if f is not None:
            findings[entry["id"]] = f
    return spiral.absorb(findings), len(findings)


def _clamp(v) -> float:
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return 0.4


def _enum(cls, value, default):
    try:
        return cls(str(value))
    except ValueError:
        return default
