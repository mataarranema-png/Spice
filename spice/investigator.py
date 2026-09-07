"""ตัวสืบค้น — ขั้น E (Experiment/Enquiry) ของก้นหอย.

สัญญาที่ทุก investigator ต้องรักษาไว้มีข้อเดียว แต่เป็นข้อที่ทั้งระบบ
แขวนอยู่บนมัน:

    **ทุกคำตอบต้องมาพร้อม `residual`**

`residual` คือคำตอบของ "คำตอบนี้อธิบายอะไรไม่ได้?"  ถ้า investigator
ไม่คืนค่านี้ เครื่องยนต์จะสังเคราะห์ให้เอง (ดู `_ensure_residual`)
เพราะการปล่อยให้คำตอบเป็นปลายทาง = การฆ่าก้นหอย.
"""

from __future__ import annotations

import random
import re
from typing import Protocol

from .graph import KnowledgeGraph
from .question import Question
from .types import EdgeSpec, EpistemicStatus, Finding, NodeSpec, QuestionLevel, Relation


class Investigator(Protocol):
    name: str

    def investigate(self, q: Question, graph: KnowledgeGraph) -> Finding: ...


# ------------------------------------------------------------------ helpers

_RESIDUAL_TEMPLATES_TH = (
    "เงื่อนไขขอบที่คำอธิบายนี้ใช้ไม่ได้",
    "กรณีที่คำตอบนี้กลายเป็นวงกลม (นิยามตัวเองด้วยตัวเอง)",
    "สิ่งที่คำตอบนี้อธิบาย *ว่าอะไรเกิดขึ้น* แต่ไม่อธิบาย *ว่าทำไมต้องเป็นแบบนั้น*",
    "ระดับของคำอธิบายที่ถูกข้ามไป",
    "บทบาทของผู้สังเกตในคำตอบนี้",
    "สิ่งที่คำตอบนี้สมมติว่าคงที่ ทั้งที่มันอาจเปลี่ยน",
)


def ensure_residual(finding: Finding, q: Question, rng: random.Random) -> Finding:
    """กติกาเหล็ก: ไม่มีคำตอบไหนได้รับอนุญาตให้เป็นปลายทาง."""
    if finding.residual and finding.residual.strip():
        return finding
    finding.residual = rng.choice(_RESIDUAL_TEMPLATES_TH)
    return finding


# คำนำหน้าที่ระบบเองเป็นคนเติม — ต้องถอดออกก่อนตั้งชื่อ node ใหม่
# มิฉะนั้นชื่อจะซ้อนกันไปเรื่อย ๆ จนกลายเป็นขยะ
_SELF_ADDED_PREFIXES = (
    "ในกรณีที่สุดขั้วที่สุด ", "ถ้ามองย้อนกลับด้าน ",
    "โดยไม่ใช้คำศัพท์เดิมเลย ", "ถ้าจำกัดให้ตอบด้วยสิ่งที่วัดได้เท่านั้น ",
    "In the most extreme case, ", "Read in reverse, ",
    "Without reusing any of the existing vocabulary, ",
    "Restricted to measurable terms only, ",
)

_STOPWORDS = {
    "อะไร", "ทำไม", "อย่างไร", "หรือไม่", "ไหม", "และ", "ที่", "ของ", "ใน",
    "เป็น", "คือ", "ได้", "ให้", "กับ", "จาก", "มัน", "เรา", "นี้", "นั้น",
    "what", "why", "how", "the", "a", "an", "of", "is", "are", "and", "to",
    "in", "it", "we", "that", "this",
}


_PARENTHETICAL = re.compile(r"\s*[(（][^)）]*[)）]")
_BRACKETED = re.compile(r"^\s*\[[^\]]*\]\s*")
MAX_LABEL = 64


def canonical_label(text: str, limit: int = MAX_LABEL) -> str:
    """ทำให้ข้อความเป็นชื่อ node ที่สั้น สะอาด และไม่ซ้อนตัวเอง.

    ถ้าไม่ทำขั้นนี้ กราฟจะโตด้วยสตริงที่ยาวขึ้นเรื่อย ๆ แทนที่จะโตด้วย
    แนวคิดใหม่ — ซึ่งคือ "แล้วทำไม? แล้วทำไม?" ในคราบของโครงสร้างข้อมูล.
    """
    t = _BRACKETED.sub("", text)
    t = _PARENTHETICAL.sub("", t).strip(" \t\n\"'“”—-")
    for pre in _SELF_ADDED_PREFIXES:
        if t.startswith(pre):
            t = t[len(pre):].lstrip()
    t = re.sub(r"\s+", " ", t)
    if len(t) <= limit:
        return t or "สิ่งนั้น"
    cut = t[:limit]
    if " " in cut[limit // 2 :]:
        cut = cut[: cut.rfind(" ")]
    return cut.rstrip(" ,;:") + "…"


def keyphrase(text: str, fallback: str = "สิ่งนั้น") -> str:
    """ดึงวลีหลักจากข้อความ — หยาบแต่พอสำหรับสร้าง label ของ node."""
    text = canonical_label(text, limit=200)
    cleaned = re.sub(r"[\"'?!.,;:()\[\]{}]", " ", text)
    parts = [p for p in cleaned.split() if p and p.lower() not in _STOPWORDS]
    if not parts:
        return fallback
    return " ".join(parts[:4])[:64]


# ------------------------------------------------------------------ offline

class ReflectiveInvestigator:
    """ตัวสืบค้นแบบออฟไลน์ ไม่ใช้เครือข่าย ผลลัพธ์คงที่ตาม seed.

    มันไม่ได้ *รู้* อะไรเกี่ยวกับโลก — และไม่แกล้งทำเป็นรู้.  สิ่งที่มันทำ
    คือจำลอง "การสืบค้นที่ให้ผลไม่สมบูรณ์เสมอ": แตกเป้าหมายออกเป็นชิ้นส่วน
    ผลิตเส้นเชื่อมใหม่ บางครั้งผลิตความขัดแย้ง และคืน residual ทุกครั้ง.
    มีไว้เพื่อสองอย่าง — ทดสอบพลวัตของก้นหอยได้โดยไม่ต้องมีเครือข่าย
    และเป็นฐานให้ผู้ใช้เสียบ investigator จริง (LLM / ฐานข้อมูล / เครื่องมือวัด)
    เข้ามาแทนที่ผ่าน Protocol เดียวกัน.
    """

    name = "reflective"

    #  แง่มุมที่ใช้แตกเป้าหมายออกเป็น node ลูก — ไล่จากรูปธรรมไปนามธรรม
    _ASPECTS = (
        ("โครงสร้างของ", QuestionLevel.OBJECT, Relation.DEPENDS_ON),
        ("กระบวนการที่ผลิต", QuestionLevel.MECHANISM, Relation.CAUSES),
        ("เงื่อนไขที่จำเป็นต่อ", QuestionLevel.MECHANISM, Relation.DEPENDS_ON),
        ("ข้อสมมติเบื้องหลัง", QuestionLevel.ASSUMPTION, Relation.PRESUPPOSES),
        ("เกณฑ์ที่ใช้ตัดสิน", QuestionLevel.META, Relation.ABSTRACTS),
        ("สถานะเชิงภววิทยาของ", QuestionLevel.ONTOLOGY, Relation.ABSTRACTS),
        ("ข้อจำกัดในการสังเกต", QuestionLevel.SELF_REFERENCE, Relation.EXPLAINS),
    )

    def __init__(self, rng: random.Random | None = None) -> None:
        self.rng = rng or random.Random(0)

    def investigate(self, q: Question, graph: KnowledgeGraph) -> Finding:
        rng = self.rng
        subject = self._subject(q, graph)

        n_children = 1 + (1 if q.level >= QuestionLevel.ASSUMPTION else 0)
        aspects = rng.sample(self._ASPECTS, min(n_children + 1, len(self._ASPECTS)))

        new_nodes: list[NodeSpec] = []
        new_edges: list[EdgeSpec] = []
        for prefix, level, rel in aspects[:n_children]:
            label = canonical_label(f"{prefix}{subject}")
            new_nodes.append(
                NodeSpec(
                    label=label,
                    status=rng.choice(
                        (
                            EpistemicStatus.PARTIALLY_KNOWN,
                            EpistemicStatus.UNCERTAIN,
                            EpistemicStatus.UNKNOWN,
                        )
                    ),
                    confidence=round(rng.uniform(0.15, 0.65), 3),
                    level=level,
                    tags=(f"L{int(q.level)}", q.strategy.split("~")[0][:24]),
                )
            )
            new_edges.append(EdgeSpec(label, subject, rel))

        contradicts: list[str] = []
        # ยิ่งถามลึก ยิ่งเจอความขัดแย้งบ่อยขึ้น — นั่นคือสิ่งที่ควรเกิด
        p_contra = 0.12 + 0.10 * q.level.reflexivity
        if new_nodes and rng.random() < p_contra:
            rival = graph.frontier(6)
            rival = [n for n in rival if n.label != subject]
            if rival:
                other = rng.choice(rival)
                new_edges.append(
                    EdgeSpec(new_nodes[0].label, other.label, Relation.CONTRADICTS)
                )
                contradicts.append(other.label)

        answer = self._compose_answer(q, subject, new_nodes)
        confidence = round(
            max(0.05, min(0.9, rng.uniform(0.25, 0.8) - 0.08 * int(q.level))), 3
        )
        finding = Finding(
            answer=answer,
            confidence=confidence,
            new_nodes=new_nodes,
            new_edges=new_edges,
            residual=self._residual(q, subject, aspects),
            contradicts=contradicts,
            cost=1.0 + 0.2 * int(q.level),
            source=self.name,
        )
        return ensure_residual(finding, q, rng)

    # -- ภายใน --

    def _subject(self, q: Question, graph: KnowledgeGraph) -> str:
        for tid in q.targets:
            node = graph.node(tid)
            if node is not None:
                return self._root(node.label)
        if q.subject:
            return self._root(q.subject)
        return keyphrase(q.text)

    def _root(self, label: str) -> str:
        """ถอดแง่มุมที่ซ้อนกันเกินหนึ่งชั้นออก.

        "ข้อสมมติเบื้องหลังกลไกของโครงสร้างของก้นหอย" ไม่ได้ลึกกว่า
        "ข้อสมมติเบื้องหลังก้นหอย" — มันแค่ยาวกว่า.  อนุญาตให้ซ้อนได้
        ชั้นเดียว แล้วยุบกลับหาแก่น.
        """
        label = canonical_label(label)
        prefixes = tuple(p for p, _, _ in self._ASPECTS)
        depth = 0
        cur = label
        while True:
            for pre in prefixes:
                if cur.startswith(pre) and len(cur) > len(pre):
                    cur = cur[len(pre):]
                    depth += 1
                    break
            else:
                break
        if depth <= 1:
            return label
        return cur or label

    def _compose_answer(self, q: Question, subject: str, nodes: list[NodeSpec]) -> str:
        if not nodes:
            return f"ยังไม่มีคำอธิบายที่ยืนได้สำหรับ {subject}"
        parts = ", ".join(n.label for n in nodes)
        by_level = {
            QuestionLevel.OBJECT: "อธิบายได้บางส่วนผ่าน",
            QuestionLevel.MECHANISM: "กลไกที่พอมองเห็นได้คือ",
            QuestionLevel.ASSUMPTION: "คำตอบนี้ตั้งอยู่บน",
            QuestionLevel.META: "รูปแบบของคำตอบถูกกำหนดโดย",
            QuestionLevel.ONTOLOGY: "สถานะการมีอยู่ของมันขึ้นกับ",
            QuestionLevel.SELF_REFERENCE: "สิ่งที่จำกัดคำตอบนี้คือ",
        }[q.level]
        return f"{subject}: {by_level} {parts}"

    def _residual(self, q: Question, subject: str, aspects) -> str:
        untouched = [a for a in self._ASPECTS if a not in aspects]
        if untouched:
            prefix, _, _ = self.rng.choice(untouched)
            return canonical_label(f"{prefix}{subject}")
        return self.rng.choice(_RESIDUAL_TEMPLATES_TH)


class CompositeInvestigator:
    """ลองตัวแรกก่อน ถ้าล้มเหลวค่อยถอยไปตัวถัดไป.

    ใช้คู่กับ investigator ที่ต้องพึ่งเครือข่าย: ก้นหอยต้องหมุนต่อได้
    แม้เครื่องมือชิ้นหนึ่งพัง — และการที่มันพังเป็น *ข้อมูล* ที่ SelfModel
    จะหยิบไปทำเป็นคำถามระดับ SELF_REFERENCE ต่อ.
    """

    def __init__(self, *investigators: Investigator) -> None:
        if not investigators:
            raise ValueError("ต้องมี investigator อย่างน้อยหนึ่งตัว")
        self.investigators = list(investigators)
        self.name = "+".join(i.name for i in investigators)
        self.failures: list[str] = []

    def investigate(self, q: Question, graph: KnowledgeGraph) -> Finding:
        last: Exception | None = None
        for inv in self.investigators:
            try:
                return inv.investigate(q, graph)
            except Exception as exc:  # noqa: BLE001 - ความล้มเหลวคือข้อมูล
                last = exc
                self.failures.append(f"{inv.name}: {type(exc).__name__}: {exc}")
        raise RuntimeError(f"investigator ทุกตัวล้มเหลว: {last}")
