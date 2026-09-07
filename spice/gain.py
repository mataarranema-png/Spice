"""การวัด *ความประหลาดใจ* — สิ่งที่ควรเป็นรางวัลจริงของคำถามหนึ่งข้อ.

เดิมระบบให้เครดิตยุทธวิธีตาม "เพิ่ม node ได้กี่ตัว" ซึ่งเป็นตัวชี้วัดที่
ตัวสืบค้นผลิตให้ฟรี ๆ อยู่แล้ว วิวัฒนาการจึงไปเข้าหาปริมาณ ไม่ใช่ความรู้

คำถามที่ดีมีนิยามเดียวที่ตรวจสอบได้: **มันเปลี่ยนแบบจำลอง**
โมดูลนี้จึงถ่ายภาพย่านรอบเป้าหมายไว้ก่อนสืบค้น แล้ววัดสี่อย่างหลังจากนั้น:

    revision  — ความเชื่อ *ที่มีอยู่ก่อนแล้ว* ขยับไปเท่าไร  (สัญญาณที่ลึกที่สุด)
    freshness — เศษที่ได้มาใหม่จริง หรือเป็นเศษเดิมที่วนกลับมา
    structure — โครงสร้างใหม่ที่งอกในย่านนั้น
    conflict  — ความขัดแย้งที่ถูกเปิดโปงเพิ่ม

`freshness` มีไว้แก้พฤติกรรมที่สังเกตเห็นจริงในรัน 150 รอบ: ระบบผลิตเศษ
เดิมซ้ำ ๆ ("โครงสร้างของก้นหอย" ซ้ำ 23 รอบ) SelfModel จับได้และบ่น แต่
fitness ไม่เคยลงโทษ ยุทธวิธีที่ผลิตเศษซ้ำจึงอยู่รอดสบาย ๆ
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from .graph import KnowledgeGraph
from .question import jaccard, shingles
from .types import EpistemicStatus, Relation

# น้ำหนัก: การแก้ความเชื่อเดิมสำคัญกว่าการกองความรู้ใหม่
W_REVISION = 0.34
W_FRESHNESS = 0.26
W_STRUCTURE = 0.22
W_CONFLICT = 0.18


@dataclass(frozen=True)
class Region:
    """ภาพนิ่งของย่านหนึ่งในกราฟ ก่อนที่คำถามจะไปแตะมัน."""

    node_ids: frozenset[str]
    uncertainty: dict[str, float]
    edge_keys: frozenset[tuple[str, str, str]]
    contradictions: int

    @property
    def size(self) -> int:
        return len(self.node_ids)


def snapshot(graph: KnowledgeGraph, targets: Iterable[str], radius: int = 1) -> Region:
    ids: set[str] = set()
    for t in targets:
        if t in graph.nodes:
            ids.add(t)
            ids |= graph.neighbors(t, radius)
    ids &= set(graph.nodes)
    return Region(
        node_ids=frozenset(ids),
        uncertainty={i: graph.nodes[i].uncertainty for i in ids},
        edge_keys=frozenset(
            e.key for e in graph.edges.values() if e.source in ids or e.target in ids
        ),
        contradictions=sum(
            1
            for e in graph.edges.values()
            if e.relation is Relation.CONTRADICTS and (e.source in ids or e.target in ids)
        ),
    )


@dataclass
class Gain:
    revision: float = 0.0
    freshness: float = 0.0
    structure: float = 0.0
    conflict: float = 0.0
    detail: dict = field(default_factory=dict)

    @property
    def total(self) -> float:
        return max(
            0.0,
            min(
                1.0,
                W_REVISION * self.revision
                + W_FRESHNESS * self.freshness
                + W_STRUCTURE * self.structure
                + W_CONFLICT * self.conflict,
            ),
        )

    def to_dict(self) -> dict:
        return {
            "revision": round(self.revision, 4),
            "freshness": round(self.freshness, 4),
            "structure": round(self.structure, 4),
            "conflict": round(self.conflict, 4),
            "total": round(self.total, 4),
        }


def residual_freshness(residual: str, known: Iterable[str]) -> float:
    """เศษนี้ใหม่จริง หรือเป็นเศษเดิมที่พูดใหม่?

    เทียบกับเศษ *ทุกอัน* ที่กราฟถืออยู่แล้ว ไม่ใช่แค่ของ node เป้าหมาย —
    เพราะการย้ายเศษเดิมไปแขวนไว้กับ node อื่นไม่ใช่การค้นพบอะไรเลย.
    """
    text = (residual or "").strip()
    if not text:
        return 0.0
    sh = shingles(text)
    if not sh:
        return 0.0
    worst = 0.0
    for other in known:
        sim = jaccard(sh, shingles(other))
        if sim > worst:
            worst = sim
            if worst >= 0.98:
                return 0.0
    return max(0.0, 1.0 - worst)


def measure(
    before: Region,
    graph: KnowledgeGraph,
    targets: Iterable[str],
    residual: str,
    known_residuals: Iterable[str],
    radius: int = 1,
) -> Gain:
    after = snapshot(graph, targets, radius)

    # 1. ความเชื่อเดิมขยับไปเท่าไร — เฉพาะ node ที่มีอยู่ *ก่อน* คำถามนี้
    shared = before.node_ids & after.node_ids
    if shared:
        moved = sum(
            abs(before.uncertainty[i] - after.uncertainty[i]) for i in shared
        ) / len(shared)
        # การขยับ 0.15 ต่อ node ถือว่ามากแล้วสำหรับคำถามข้อเดียว
        revision = min(1.0, moved / 0.15)
    else:
        # ไม่มีอะไรอยู่ก่อนให้แก้ = คำถามนี้ไปแตะที่ว่างเปล่า
        revision = 0.0

    # 2. เศษใหม่จริงไหม
    freshness = residual_freshness(residual, known_residuals)

    # 3. โครงสร้างที่งอกในย่านนั้น
    new_nodes = len(after.node_ids - before.node_ids)
    new_edges = len(after.edge_keys - before.edge_keys)
    structure = min(1.0, (new_nodes + 0.5 * new_edges) / 4.0)

    # 4. ความขัดแย้งที่ถูกเปิดโปงเพิ่ม
    conflict = min(1.0, max(0, after.contradictions - before.contradictions) / 1.0)

    return Gain(
        revision=revision,
        freshness=freshness,
        structure=structure,
        conflict=conflict,
        detail={"new_nodes": new_nodes, "new_edges": new_edges, "region": after.size},
    )


def all_residuals(graph: KnowledgeGraph, limit: int = 400) -> list[str]:
    """เศษทุกอันที่กราฟถืออยู่ — ทั้งที่แขวนกับ node และที่กลายเป็น node แล้ว."""
    out: list[str] = []
    for n in graph.nodes.values():
        out.extend(n.residuals)
        if "residual" in n.tags:
            out.append(n.label)
        if len(out) >= limit:
            break
    return out[:limit]
