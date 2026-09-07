"""การให้คะแนนคำถาม และการเลือก Q*.

    Q* = argmax_Q ( w_u·U_Q + w_c·C_Q + w_n·N_Q )

โดย U = ความไม่รู้ในบริเวณเป้าหมาย, C = แรงดันจากความขัดแย้ง,
N = ความใหม่ (ถ่วงด้วยความหายากของ *ระดับ* คำถาม).

น้ำหนัก w ไม่ใช่ค่าคงที่ที่มนุษย์ตั้ง — มันถูกไต่เขา (hill-climb) จาก
ผลตอบแทนจริงของแต่ละ epoch ใน `evolution.py` ระบบจึงเรียนรู้เองว่า
ตอนนี้ควรวิ่งไล่ความไม่รู้ ความขัดแย้ง หรือความแปลกใหม่.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .graph import KnowledgeGraph
from .question import Question, QuestionLedger, jaccard, shingles
from .types import QuestionLevel


@dataclass
class Weights:
    u: float = 0.34
    c: float = 0.33
    n: float = 0.33

    def normalized(self) -> "Weights":
        total = self.u + self.c + self.n
        if total <= 0:
            return Weights()
        return Weights(self.u / total, self.c / total, self.n / total)

    def to_dict(self) -> dict:
        return {"u": self.u, "c": self.c, "n": self.n}

    @classmethod
    def from_dict(cls, d: dict) -> "Weights":
        return cls(u=d.get("u", 0.34), c=d.get("c", 0.33), n=d.get("n", 0.33))


@dataclass
class Scored:
    question: Question
    u: float
    c: float
    n: float
    total: float


def score_question(
    q: Question, graph: KnowledgeGraph, ledger: QuestionLedger, weights: Weights
) -> Scored:
    w = weights.normalized()

    if q.targets:
        u = sum(graph.local_uncertainty(t) for t in q.targets) / len(q.targets)
        c = max(graph.local_contradiction(t) for t in q.targets)
    else:
        # คำถามที่ไม่มีเป้าหมายในกราฟคือคำถามถึงตัวระบบเอง:
        # ตามนิยาม มันอยู่ในบริเวณที่ระบบยังไม่ได้ทำแผนที่ไว้เลย
        u = 0.9
        c = graph.stats()["contradictions"] and 0.5 or 0.2

    novelty = ledger.novelty(q)
    rarity = ledger.level_rarity(q.level)
    n = novelty * (0.6 + 0.4 * rarity)

    # คำถามที่พับกลับมาหาตัวระบบได้ค่า C เพิ่ม: ความขัดแย้งที่อันตรายที่สุด
    # คือความขัดแย้งระหว่างระบบกับภาพที่มันมีต่อตัวเอง
    c = min(1.0, c + 0.25 * q.level.reflexivity)

    total = w.u * u + w.c * c + w.n * n
    q.scores = {"u": u, "c": c, "n": n, "total": total}
    return Scored(q, u, c, n, total)


def select(
    candidates: list[Question],
    graph: KnowledgeGraph,
    ledger: QuestionLedger,
    weights: Weights,
    *,
    k: int = 3,
    min_novelty: float = 0.35,
    diversity: float = 0.55,
) -> list[Scored]:
    """คัดเลือก Q* แบบ maximal-marginal-relevance.

    ตัวกรองสองชั้น ตรงกับที่ `question.py` อธิบายไว้:
      1. เคยถามเป๊ะ ๆ หรือความใหม่ต่ำกว่าเกณฑ์ -> ตัดทิ้ง
      2. คล้ายคำถามที่เพิ่งถูกเลือกใน epoch เดียวกัน -> ตัดทิ้ง
    ชั้นที่สองสำคัญไม่แพ้ชั้นแรก: ไม่งั้นระบบจะเลือกคำถามเดียวกัน
    ที่พูดคนละสำนวน k ตัวใน epoch เดียว แล้วนึกว่าตัวเองขยัน.
    """
    pool: list[Scored] = []
    seen_sig: set[str] = set()
    for q in candidates:
        if q.signature in seen_sig or ledger.seen(q):
            continue
        seen_sig.add(q.signature)
        s = score_question(q, graph, ledger, weights)
        if s.n < min_novelty and not q.forced:
            continue
        pool.append(s)

    pool.sort(key=lambda s: -s.total)

    chosen: list[Scored] = []
    chosen_shingles: list[frozenset[str]] = []
    for s in pool:
        if len(chosen) >= k:
            break
        sh = shingles(s.question.text)
        if any(jaccard(sh, prev) > diversity for prev in chosen_shingles):
            continue
        chosen.append(s)
        chosen_shingles.append(sh)
    return chosen


def epoch_reward(before: dict, after: dict, novelty_mean: float) -> float:
    """ผลตอบแทนของหนึ่ง epoch — ใช้ปรับน้ำหนักและวัด fitness ของ strategy.

    จงใจให้รางวัลกับการ *เปิด* ความไม่รู้ใหม่ ไม่ใช่แค่การปิดของเดิม:
    ระบบที่ถูกให้รางวัลกับความมั่นใจอย่างเดียวจะหยุดถามทันทีที่มันพอใจ.
    """
    grew = (after["nodes"] - before["nodes"]) / max(1, before["nodes"])
    resolved = before["mean_uncertainty"] - after["mean_uncertainty"]
    surfaced = (after["contradictions"] - before["contradictions"]) * 0.1
    opened = (after["unexplained"] - before["unexplained"]) * 0.02
    return (
        0.30 * min(1.0, grew)
        + 0.30 * max(-1.0, min(1.0, resolved * 4))
        + 0.25 * min(1.0, surfaced)
        + 0.15 * novelty_mean
        + 0.05 * min(1.0, max(0.0, opened))
    )
