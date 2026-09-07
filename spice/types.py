"""ชนิดข้อมูลพื้นฐานของก้นหอย (core value types for the spiral).

ทุกอย่างในระบบนี้ตั้งอยู่บนความคิดเดียว: *สถานะทางญาณวิทยา* (epistemic
status) ไม่ใช่ boolean.  ความรู้ไม่ได้มีแค่ "จริง/เท็จ" แต่มี "ยังไม่รู้",
"รู้ครึ่งเดียว", "ขัดแย้งกันเอง" — และสามอย่างหลังนี่แหละคือ *แหล่งกำเนิด
คำถาม*.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum, IntEnum


class EpistemicStatus(Enum):
    """สถานะของ node ในกราฟความรู้."""

    KNOWN = "KNOWN"
    PARTIALLY_KNOWN = "PARTIALLY_KNOWN"
    UNCERTAIN = "UNCERTAIN"
    UNKNOWN = "UNKNOWN"
    CONTRADICTED = "CONTRADICTED"

    @property
    def uncertainty(self) -> float:
        """ค่าความไม่แน่นอนพื้นฐาน 0..1 ที่สถานะนี้พกมาด้วย."""
        return _STATUS_UNCERTAINTY[self]

    @property
    def is_question_source(self) -> bool:
        """UNKNOWN / CONTRADICTED / UNCERTAIN คือปากก้นหอย."""
        return self in _QUESTION_SOURCES


_STATUS_UNCERTAINTY: dict[EpistemicStatus, float] = {
    EpistemicStatus.KNOWN: 0.05,
    EpistemicStatus.PARTIALLY_KNOWN: 0.45,
    EpistemicStatus.UNCERTAIN: 0.70,
    EpistemicStatus.UNKNOWN: 1.00,
    # ความขัดแย้งไม่ใช่ "ไม่รู้" — มันคือรู้สองอย่างที่อยู่ด้วยกันไม่ได้
    # ซึ่งให้ข้อมูลมากกว่าความว่างเปล่า จึงต่ำกว่า UNKNOWN เล็กน้อย
    EpistemicStatus.CONTRADICTED: 0.85,
}

_QUESTION_SOURCES = frozenset(
    {
        EpistemicStatus.UNKNOWN,
        EpistemicStatus.UNCERTAIN,
        EpistemicStatus.CONTRADICTED,
        EpistemicStatus.PARTIALLY_KNOWN,
    }
)


class Relation(Enum):
    """ชนิดของเส้นเชื่อมในกราฟความรู้."""

    CAUSES = "causes"
    DEPENDS_ON = "depends_on"
    EXPLAINS = "explains"
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    PRESUPPOSES = "presupposes"
    ABSTRACTS = "abstracts"
    ANALOGOUS_TO = "analogous_to"
    UNKNOWN_LINK = "unknown_link"
    GENERATED_BY = "generated_by"

    @property
    def is_explanatory(self) -> bool:
        return self in (Relation.EXPLAINS, Relation.CAUSES, Relation.ABSTRACTS)

    @property
    def is_symmetric(self) -> bool:
        return self in (
            Relation.CONTRADICTS,
            Relation.ANALOGOUS_TO,
            Relation.UNKNOWN_LINK,
        )


class QuestionLevel(IntEnum):
    """ระดับของคำถาม — ยิ่งสูงยิ่งถามถึงตัวผู้ถามเอง.

    ระดับไม่ได้เรียงตาม "ยาก" แต่เรียงตาม *ระยะห่างจากวัตถุ*:
    ระดับ 0 ถามถึงโลก, ระดับ 5 ถามถึงระบบที่กำลังถามอยู่.
    """

    OBJECT = 0
    MECHANISM = 1
    ASSUMPTION = 2
    META = 3
    ONTOLOGY = 4
    SELF_REFERENCE = 5

    @property
    def th(self) -> str:
        return _LEVEL_TH[self]

    @property
    def reflexivity(self) -> float:
        """0..1 — ระดับนี้พับกลับมาหาตัวระบบมากแค่ไหน."""
        return self.value / QuestionLevel.SELF_REFERENCE.value


_LEVEL_TH: dict[QuestionLevel, str] = {
    QuestionLevel.OBJECT: "วัตถุ",
    QuestionLevel.MECHANISM: "กลไก",
    QuestionLevel.ASSUMPTION: "ข้อสมมติ",
    QuestionLevel.META: "อภิคำถาม",
    QuestionLevel.ONTOLOGY: "ภววิทยา",
    QuestionLevel.SELF_REFERENCE: "อ้างถึงตัวเอง",
}


def stable_id(*parts: str, size: int = 6) -> str:
    """id ที่คงที่ข้ามการรัน — เพื่อให้ label เดิม map ไป node เดิมเสมอ."""
    h = hashlib.blake2s("\x1f".join(parts).encode("utf-8"), digest_size=size)
    return h.hexdigest()


@dataclass(frozen=True)
class NodeSpec:
    """ข้อเสนอให้สร้าง node — ผลลัพธ์จากการสืบค้น ยังไม่ผูกกับกราฟ."""

    label: str
    status: EpistemicStatus = EpistemicStatus.PARTIALLY_KNOWN
    confidence: float = 0.4
    level: QuestionLevel = QuestionLevel.OBJECT
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class EdgeSpec:
    """ข้อเสนอให้สร้างเส้นเชื่อม โดยอ้าง label (ไม่ใช่ id)."""

    source: str
    target: str
    relation: Relation = Relation.UNKNOWN_LINK
    weight: float = 1.0


@dataclass
class Finding:
    """สิ่งที่ได้กลับมาจากการสืบค้นหนึ่งครั้ง.

    `residual` คือหัวใจของทั้งระบบ: มันคือคำตอบของคำถาม
    "คำตอบนี้อธิบายอะไรไม่ได้?"  ถ้า residual ว่าง ก้นหอยจะตาย —
    เครื่องยนต์จึงบังคับให้ investigator ทุกตัวต้องคืนค่านี้เสมอ.
    """

    answer: str
    confidence: float = 0.5
    new_nodes: list[NodeSpec] = field(default_factory=list)
    new_edges: list[EdgeSpec] = field(default_factory=list)
    residual: str = ""
    contradicts: list[str] = field(default_factory=list)
    cost: float = 1.0
    source: str = "unknown"
