"""กราฟความรู้ — โครงสร้าง ไม่ใช่ข้อความกอง ๆ กัน.

กราฟนี้ไม่ได้มีไว้ "เก็บคำตอบ" แต่มีไว้ *ชี้ตำแหน่งของความไม่รู้*.
ทุก query ที่สำคัญในไฟล์นี้ (frontier, unexplained, contradiction_pairs,
structural_holes) คืนค่าเป็น "ที่ที่ควรถาม" ไม่ใช่ "ที่ที่รู้แล้ว".
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Iterable, Iterator

from .types import EpistemicStatus, QuestionLevel, Relation, stable_id


@dataclass
class Node:
    id: str
    label: str
    status: EpistemicStatus = EpistemicStatus.UNKNOWN
    confidence: float = 0.0
    level: QuestionLevel = QuestionLevel.OBJECT
    tags: set[str] = field(default_factory=set)
    provenance: str = "seed"
    created_epoch: int = 0
    visits: int = 0
    residuals: list[str] = field(default_factory=list)

    @property
    def uncertainty(self) -> float:
        """ความไม่แน่นอนรวม: สถานะ × (1 - ความมั่นใจ) ถ่วงเข้าหากัน."""
        base = self.status.uncertainty
        return max(0.0, min(1.0, 0.65 * base + 0.35 * (1.0 - self.confidence)))

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "status": self.status.value,
            "confidence": self.confidence,
            "level": int(self.level),
            "tags": sorted(self.tags),
            "provenance": self.provenance,
            "created_epoch": self.created_epoch,
            "visits": self.visits,
            "residuals": self.residuals,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Node":
        return cls(
            id=d["id"],
            label=d["label"],
            status=EpistemicStatus(d["status"]),
            confidence=d["confidence"],
            level=QuestionLevel(d["level"]),
            tags=set(d.get("tags", ())),
            provenance=d.get("provenance", "seed"),
            created_epoch=d.get("created_epoch", 0),
            visits=d.get("visits", 0),
            residuals=list(d.get("residuals", ())),
        )


@dataclass
class Edge:
    source: str
    target: str
    relation: Relation = Relation.UNKNOWN_LINK
    weight: float = 1.0
    provenance: str = "seed"
    created_epoch: int = 0

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.source, self.target, self.relation.value)

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "target": self.target,
            "relation": self.relation.value,
            "weight": self.weight,
            "provenance": self.provenance,
            "created_epoch": self.created_epoch,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Edge":
        return cls(
            source=d["source"],
            target=d["target"],
            relation=Relation(d["relation"]),
            weight=d.get("weight", 1.0),
            provenance=d.get("provenance", "seed"),
            created_epoch=d.get("created_epoch", 0),
        )


class KnowledgeGraph:
    def __init__(self) -> None:
        self.nodes: dict[str, Node] = {}
        self.edges: dict[tuple[str, str, str], Edge] = {}
        self._out: dict[str, set[str]] = defaultdict(set)
        self._in: dict[str, set[str]] = defaultdict(set)

    # ---------- การสร้าง ----------

    def add_node(
        self,
        label: str,
        *,
        status: EpistemicStatus = EpistemicStatus.UNKNOWN,
        confidence: float = 0.0,
        level: QuestionLevel = QuestionLevel.OBJECT,
        tags: Iterable[str] = (),
        provenance: str = "seed",
        epoch: int = 0,
    ) -> Node:
        """เพิ่ม node หรือ *ผสาน* เข้ากับ node เดิมที่ label ตรงกัน.

        การผสานเลือกสถานะที่ให้ข้อมูลมากกว่าเสมอ ยกเว้น CONTRADICTED
        ซึ่งชนะทุกอย่าง — เพราะความขัดแย้งที่ถูกกลบคือความรู้ที่หายไป.
        """
        label = label.strip()
        nid = stable_id(label)
        existing = self.nodes.get(nid)
        if existing is None:
            node = Node(
                id=nid,
                label=label,
                status=status,
                confidence=confidence,
                level=level,
                tags=set(tags),
                provenance=provenance,
                created_epoch=epoch,
            )
            self.nodes[nid] = node
            return node

        existing.tags.update(tags)
        if status is EpistemicStatus.CONTRADICTED:
            existing.status = status
        elif existing.status is not EpistemicStatus.CONTRADICTED:
            if status.uncertainty < existing.status.uncertainty:
                existing.status = status
        existing.confidence = max(existing.confidence, confidence)
        existing.level = QuestionLevel(max(int(existing.level), int(level)))
        return existing

    def add_edge(
        self,
        source_label: str,
        target_label: str,
        relation: Relation = Relation.UNKNOWN_LINK,
        *,
        weight: float = 1.0,
        provenance: str = "seed",
        epoch: int = 0,
    ) -> Edge | None:
        src = self.nodes.get(stable_id(source_label.strip()))
        dst = self.nodes.get(stable_id(target_label.strip()))
        if src is None or dst is None or src.id == dst.id:
            return None
        edge = Edge(src.id, dst.id, relation, weight, provenance, epoch)
        if edge.key in self.edges:
            kept = self.edges[edge.key]
            kept.weight = max(kept.weight, weight)
            return kept
        self.edges[edge.key] = edge
        self._out[src.id].add(dst.id)
        self._in[dst.id].add(src.id)
        if relation is Relation.CONTRADICTS:
            src.status = EpistemicStatus.CONTRADICTED
            dst.status = EpistemicStatus.CONTRADICTED
        return edge

    # ---------- การอ่าน ----------

    def node(self, nid: str) -> Node | None:
        return self.nodes.get(nid)

    def by_label(self, label: str) -> Node | None:
        return self.nodes.get(stable_id(label.strip()))

    def __len__(self) -> int:
        return len(self.nodes)

    def __iter__(self) -> Iterator[Node]:
        return iter(self.nodes.values())

    def edges_of(self, nid: str) -> list[Edge]:
        return [e for e in self.edges.values() if e.source == nid or e.target == nid]

    def neighbors(self, nid: str, radius: int = 1) -> set[str]:
        seen = {nid}
        frontier = {nid}
        for _ in range(radius):
            nxt: set[str] = set()
            for cur in frontier:
                nxt |= self._out[cur] | self._in[cur]
            nxt -= seen
            if not nxt:
                break
            seen |= nxt
            frontier = nxt
        return seen - {nid}

    def path_exists(self, a: str, b: str, max_depth: int = 4) -> bool:
        if a == b:
            return True
        seen = {a}
        q: deque[tuple[str, int]] = deque([(a, 0)])
        while q:
            cur, d = q.popleft()
            if d >= max_depth:
                continue
            for nxt in self._out[cur] | self._in[cur]:
                if nxt == b:
                    return True
                if nxt not in seen:
                    seen.add(nxt)
                    q.append((nxt, d + 1))
        return False

    # ---------- คำถามอยู่ตรงนี้ ----------

    def frontier(self, k: int = 12) -> list[Node]:
        """node ที่ไม่แน่นอนที่สุดและถูกเยี่ยมน้อยที่สุด."""
        return sorted(
            self.nodes.values(),
            key=lambda n: (-(n.uncertainty), n.visits, n.label),
        )[:k]

    def unexplained(self) -> list[Node]:
        """node ที่ไม่มีอะไรมาอธิบายมันเลย — ไม่มีเส้น EXPLAINS/CAUSES เข้า."""
        explained = {
            e.target for e in self.edges.values() if e.relation.is_explanatory
        }
        return [n for n in self.nodes.values() if n.id not in explained]

    def contradiction_pairs(self) -> list[tuple[Node, Node]]:
        out: list[tuple[Node, Node]] = []
        seen: set[frozenset[str]] = set()
        for e in self.edges.values():
            if e.relation is not Relation.CONTRADICTS:
                continue
            key = frozenset((e.source, e.target))
            if key in seen:
                continue
            seen.add(key)
            a, b = self.nodes.get(e.source), self.nodes.get(e.target)
            if a and b:
                out.append((a, b))
        return out

    def structural_holes(self, limit: int = 8) -> list[tuple[Node, Node]]:
        """คู่ node ที่ "ควรเกี่ยวกัน" แต่ไม่มีเส้นทางถึงกัน.

        นี่คือเครื่องยนต์ความใหม่: คำถามที่น่าสนใจที่สุดมักไม่ได้อยู่ใน
        node ใด node หนึ่ง แต่อยู่ใน *ช่องว่างระหว่าง* สองอย่างที่ไม่มีใคร
        เคยลากเส้นเชื่อม.
        """
        ranked = sorted(
            self.nodes.values(), key=lambda n: (-n.uncertainty, n.label)
        )[: max(2, limit * 3)]
        out: list[tuple[Node, Node]] = []
        for i, a in enumerate(ranked):
            for b in ranked[i + 1 :]:
                if a.tags & b.tags or a.level == b.level:
                    if not self.path_exists(a.id, b.id, max_depth=3):
                        out.append((a, b))
                        if len(out) >= limit:
                            return out
        return out

    def open_residuals(self, limit: int = 12) -> list[tuple[Node, str]]:
        out: list[tuple[Node, str]] = []
        for n in self.nodes.values():
            for r in n.residuals:
                out.append((n, r))
        out.sort(key=lambda t: -t[0].uncertainty)
        return out[:limit]

    # ---------- สรุปสภาพ ----------

    def local_uncertainty(self, nid: str, radius: int = 1) -> float:
        node = self.nodes.get(nid)
        if node is None:
            return 1.0
        pool = [node] + [self.nodes[n] for n in self.neighbors(nid, radius) if n in self.nodes]
        return sum(n.uncertainty for n in pool) / len(pool)

    def local_contradiction(self, nid: str, radius: int = 1) -> float:
        region = self.neighbors(nid, radius) | {nid}
        hits = sum(
            1
            for e in self.edges.values()
            if e.relation is Relation.CONTRADICTS
            and (e.source in region or e.target in region)
        )
        status_hits = sum(
            1
            for n in region
            if n in self.nodes
            and self.nodes[n].status is EpistemicStatus.CONTRADICTED
        )
        return 1.0 - 1.0 / (1.0 + hits + 0.5 * status_hits)

    def stats(self) -> dict:
        by_status: dict[str, int] = defaultdict(int)
        for n in self.nodes.values():
            by_status[n.status.value] += 1
        unc = [n.uncertainty for n in self.nodes.values()] or [0.0]
        return {
            "nodes": len(self.nodes),
            "edges": len(self.edges),
            "by_status": dict(by_status),
            "mean_uncertainty": sum(unc) / len(unc),
            "contradictions": len(self.contradiction_pairs()),
            "unexplained": len(self.unexplained()),
        }

    # ---------- persistence ----------

    def to_dict(self) -> dict:
        return {
            "nodes": [n.to_dict() for n in self.nodes.values()],
            "edges": [e.to_dict() for e in self.edges.values()],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "KnowledgeGraph":
        g = cls()
        for nd in d.get("nodes", ()):
            node = Node.from_dict(nd)
            g.nodes[node.id] = node
        for ed in d.get("edges", ()):
            edge = Edge.from_dict(ed)
            if edge.source in g.nodes and edge.target in g.nodes:
                g.edges[edge.key] = edge
                g._out[edge.source].add(edge.target)
                g._in[edge.target].add(edge.source)
        return g

    def to_dot(self) -> str:
        colors = {
            EpistemicStatus.KNOWN: "#2f9e44",
            EpistemicStatus.PARTIALLY_KNOWN: "#74b816",
            EpistemicStatus.UNCERTAIN: "#f08c00",
            EpistemicStatus.UNKNOWN: "#868e96",
            EpistemicStatus.CONTRADICTED: "#e03131",
        }
        lines = ["digraph spiral {", '  rankdir=LR; node [shape=box, style=rounded];']
        for n in self.nodes.values():
            label = n.label.replace('"', "'")
            lines.append(
                f'  "{n.id}" [label="{label}\\n[{n.status.value}]", '
                f'color="{colors[n.status]}"];'
            )
        for e in self.edges.values():
            style = "dashed" if e.relation is Relation.UNKNOWN_LINK else "solid"
            lines.append(
                f'  "{e.source}" -> "{e.target}" '
                f'[label="{e.relation.value}", style={style}];'
            )
        lines.append("}")
        return "\n".join(lines)
