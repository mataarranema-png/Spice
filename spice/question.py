"""คำถาม และ *บัญชีคำถาม* ที่ทำให้ระบบถามซ้ำไม่ได้.

ปัญหาที่สเปคชี้ไว้ตรง ๆ: ถ้าปล่อยให้ AI ถามว่า "มีคำถามอะไรอีกไหม?"
มันจะได้ "แล้วทำไม? แล้วทำไม? แล้วทำไม?" ซึ่งเด็กสามขวบทำได้ฟรี.
ทางแก้ไม่ใช่ prompt ที่ฉลาดขึ้น แต่คือ *กลไกบังคับความใหม่*:

1. signature ตรงกันเป๊ะ  -> ปฏิเสธทันที (hard filter)
2. คล้ายของเดิมมาก       -> คะแนน novelty ต่ำ ถูกคำถามอื่นแซง (soft filter)

การวัดความคล้ายใช้ character 4-gram ไม่ใช่ word shingle — เพราะภาษาไทย
ไม่เว้นวรรคระหว่างคำ การตัดด้วย whitespace จะพังทันที.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from .types import QuestionLevel, stable_id

_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w฀-๿]+", re.UNICODE)
NGRAM = 4


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFC", text).lower()
    text = _PUNCT.sub(" ", text)
    return _WS.sub(" ", text).strip()


def shingles(text: str, n: int = NGRAM) -> frozenset[str]:
    """char n-gram ของข้อความที่ normalize แล้ว (รองรับไทย/อังกฤษเท่ากัน)."""
    s = normalize(text).replace(" ", "")
    if len(s) <= n:
        return frozenset({s}) if s else frozenset()
    return frozenset(s[i : i + n] for i in range(len(s) - n + 1))


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if not inter:
        return 0.0
    return inter / len(a | b)


@dataclass
class Question:
    text: str
    level: QuestionLevel
    strategy: str
    targets: tuple[str, ...] = ()          # node ids
    epoch: int = 0
    depth: int = 0
    parent: str | None = None
    scores: dict[str, float] = field(default_factory=dict)
    forced: bool = False                    # มาจาก residual: ข้ามการคัดเลือก
    probe: str = ""                         # ชนิดของหัววัด (ชื่อรากของยุทธวิธี)
                                            # `object_probe~m3.221` กับ `object_probe`
                                            # คือหัววัดเดียวกัน แค่คนละรุ่น
    subject: str = ""                       # สิ่งที่คำถามนี้พูดถึง ตามที่
                                            # ยุทธวิธี *รู้อยู่แล้ว* ตอนสร้าง —
                                            # ดีกว่าเดาย้อนจากข้อความที่ render แล้ว

    @property
    def id(self) -> str:
        return stable_id(self.signature)

    @property
    def signature(self) -> str:
        return normalize(self.text)

    @property
    def concept(self) -> str:
        """ลายเซ็นเชิง *แนวคิด*: (ระดับ, หัววัด, เป้าหมาย).

        ความใหม่เชิงคำอย่างเดียวไม่พอ — คำถามสองข้อที่ใช้หัววัดเดียวกัน
        กับ node เดียวกันที่ระดับเดียวกัน คือคำถามเดียวกัน ต่อให้เรียบเรียง
        คนละสำนวน  การกลายพันธุ์ของแม่แบบทำให้ระบบผลิตคำถามแบบนั้นได้
        ไม่จำกัด แล้วหลอกตัวเองว่ากำลังสำรวจอยู่.
        """
        probe = self.probe or self.strategy
        return f"{int(self.level)}|{probe}|{'+'.join(sorted(self.targets))}"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "text": self.text,
            "level": int(self.level),
            "strategy": self.strategy,
            "targets": list(self.targets),
            "epoch": self.epoch,
            "depth": self.depth,
            "parent": self.parent,
            "scores": self.scores,
            "forced": self.forced,
            "subject": self.subject,
            "probe": self.probe,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Question":
        return cls(
            text=d["text"],
            level=QuestionLevel(d["level"]),
            strategy=d["strategy"],
            targets=tuple(d.get("targets", ())),
            epoch=d.get("epoch", 0),
            depth=d.get("depth", 0),
            parent=d.get("parent"),
            scores=dict(d.get("scores", {})),
            forced=d.get("forced", False),
            subject=d.get("subject", ""),
            probe=d.get("probe", ""),
        )


class QuestionLedger:
    """ความจำของคำถามทั้งหมดที่เคยถูกถาม — และเครื่องวัดความใหม่."""

    def __init__(self, capacity: int = 4000) -> None:
        self.capacity = capacity
        self._signatures: set[str] = set()
        self._order: list[str] = []
        self._shingles: dict[str, frozenset[str]] = {}
        self._concepts: set[str] = set()
        self.level_counts: dict[int, int] = {int(l): 0 for l in QuestionLevel}

    def __len__(self) -> int:
        return len(self._signatures)

    def seen(self, q: Question | str) -> bool:
        sig = q.signature if isinstance(q, Question) else normalize(q)
        return sig in self._signatures

    def seen_concept(self, q: Question) -> bool:
        """เคยเอาหัววัดชนิดนี้ ที่ระดับนี้ ไปจิ้ม node นี้แล้วหรือยัง."""
        return bool(q.targets) and q.concept in self._concepts

    def novelty(self, q: Question | str) -> float:
        """1.0 = ไม่เคยมีอะไรใกล้เคียง, 0.0 = ซ้ำเป๊ะ."""
        text = q.text if isinstance(q, Question) else q
        sig = normalize(text)
        if sig in self._signatures:
            return 0.0
        sh = shingles(text)
        if not sh or not self._shingles:
            return 1.0
        worst = 0.0
        for other in self._shingles.values():
            sim = jaccard(sh, other)
            if sim > worst:
                worst = sim
                if worst >= 0.995:
                    break
        return max(0.0, 1.0 - worst)

    def level_rarity(self, level: QuestionLevel) -> float:
        """โบนัสให้ระดับคำถามที่ระบบแทบไม่เคยใช้.

        นี่คือแรงผลักให้ก้นหอยไต่ขึ้นไปหา META / ONTOLOGY / SELF_REFERENCE
        แทนที่จะวนอยู่ที่ระดับ OBJECT ตลอดกาล.
        """
        total = sum(self.level_counts.values())
        if total == 0:
            return 1.0
        share = self.level_counts.get(int(level), 0) / total
        return max(0.0, 1.0 - share * len(QuestionLevel) / 2.0)

    def record(self, q: Question) -> None:
        sig = q.signature
        if sig in self._signatures:
            return
        self._signatures.add(sig)
        self._concepts.add(q.concept)
        self._order.append(sig)
        self._shingles[sig] = shingles(q.text)
        self.level_counts[int(q.level)] = self.level_counts.get(int(q.level), 0) + 1
        while len(self._order) > self.capacity:
            old = self._order.pop(0)
            self._signatures.discard(old)
            self._shingles.pop(old, None)

    def to_dict(self) -> dict:
        return {
            "capacity": self.capacity,
            "order": self._order,
            "concepts": sorted(self._concepts),
            "level_counts": self.level_counts,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "QuestionLedger":
        led = cls(capacity=d.get("capacity", 4000))
        for sig in d.get("order", ()):
            led._signatures.add(sig)
            led._order.append(sig)
            led._shingles[sig] = shingles(sig)
        led._concepts = set(d.get("concepts", ()))
        led.level_counts = {int(k): v for k, v in d.get("level_counts", {}).items()}
        for l in QuestionLevel:
            led.level_counts.setdefault(int(l), 0)
        return led
