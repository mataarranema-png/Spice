"""แบบจำลองที่ระบบมีต่อ *ตัวเอง*.

โมดูลนี้ไม่มองโลกเลย — มันมองสถิติของก้นหอยเท่านั้น: ระดับคำถามที่ไม่เคย
ถูกใช้, เศษที่ทนต่อการอธิบายมาหลายรอบ, ความใหม่ที่กำลังตกลง, ยุทธวิธีที่
ผูกขาดคำถามทั้งหมด, เพดานทรัพยากรที่ใกล้ชน, เครื่องมือที่พัง.

ผลลัพธ์มีสองอย่าง:
  * `limits()` -> ข้อความข้อจำกัด ป้อนให้ strategy ระดับ SELF_REFERENCE
  * `gaps()`   -> ช่องโหว่ที่ร้ายแรงพอจะ *ให้กำเนิดเครื่องมือใหม่*

นี่คือความต่างระหว่าง "ระบบที่ไม่มีขอบเขต" (เป็นไปไม่ได้) กับ
"ระบบที่ค้นพบขอบเขตของตัวเองแล้วสร้างวิธีขยายมัน" (ทำได้ และอยู่ตรงนี้).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .types import QuestionLevel


@dataclass
class Limit:
    kind: str
    text: str
    severity: float
    first_seen: int
    epochs_persisted: int = 1

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "text": self.text,
            "severity": self.severity,
            "first_seen": self.first_seen,
            "epochs_persisted": self.epochs_persisted,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Limit":
        return cls(**d)


@dataclass
class CapabilityGap:
    """ช่องโหว่ที่เรียกร้อง *เครื่องมือใหม่* ไม่ใช่แค่คำถามใหม่."""

    text: str
    level: QuestionLevel
    source: str
    severity: float


@dataclass
class SelfModel:
    stagnation_window: int = 3
    novelty_floor: float = 0.45
    residual_patience: int = 3
    monoculture_share: float = 0.55

    uncertainty_history: list[float] = field(default_factory=list)
    novelty_history: list[float] = field(default_factory=list)
    node_history: list[int] = field(default_factory=list)
    contradiction_history: list[int] = field(default_factory=list)
    residual_age: dict[str, int] = field(default_factory=dict)
    strategy_uses: Counter = field(default_factory=Counter)
    level_uses: Counter = field(default_factory=Counter)
    instrument_failures: list[str] = field(default_factory=list)
    limits_seen: dict[str, Limit] = field(default_factory=dict)
    answered_limits: set[str] = field(default_factory=set)

    # ---------------- การสังเกตตัวเอง ----------------

    def observe_epoch(
        self,
        *,
        epoch: int,
        stats: dict,
        selected_levels: list[QuestionLevel],
        selected_strategies: list[str],
        novelty_mean: float,
        open_residuals: list[str],
        instrument_failures: list[str],
    ) -> None:
        self.uncertainty_history.append(stats["mean_uncertainty"])
        self.novelty_history.append(novelty_mean)
        self.node_history.append(stats["nodes"])
        self.contradiction_history.append(stats["contradictions"])
        self.strategy_uses.update(selected_strategies)
        self.level_uses.update(int(l) for l in selected_levels)
        self.instrument_failures = list(instrument_failures)

        still_open = set(open_residuals)
        for r in still_open:
            self.residual_age[r] = self.residual_age.get(r, 0) + 1
        for r in list(self.residual_age):
            if r not in still_open:
                del self.residual_age[r]

    # ---------------- การค้นพบขอบเขต ----------------

    def detect(self, epoch: int, budget: "Budget | None" = None) -> list[Limit]:
        found: list[Limit] = []

        # 1. ระดับคำถามที่ระบบไม่เคยแตะ
        total_levels = sum(self.level_uses.values())
        for level in QuestionLevel:
            share = self.level_uses.get(int(level), 0) / total_levels if total_levels else 0.0
            if total_levels >= 6 and share < 0.03:
                found.append(
                    Limit(
                        "coverage",
                        f"แทบไม่เคยตั้งคำถามระดับ{level.th}เลย ({share:.0%} ของคำถามทั้งหมด)",
                        0.5 + 0.1 * int(level),
                        epoch,
                    )
                )

        # 2. เศษที่ทนต่อการอธิบาย — จุดบอดที่แท้จริง
        for residual, age in sorted(self.residual_age.items(), key=lambda kv: -kv[1]):
            if age >= self.residual_patience:
                found.append(
                    Limit(
                        "recurrence",
                        f"\"{residual[:70]}\" ยังอธิบายไม่ได้ต่อเนื่อง {age} รอบ",
                        min(1.0, 0.4 + 0.1 * age),
                        epoch,
                    )
                )

        # 3. ก้นหอยหมุนอยู่กับที่
        w = self.stagnation_window
        if len(self.uncertainty_history) >= w:
            recent = self.uncertainty_history[-w:]
            if max(recent) - min(recent) < 0.005:
                found.append(
                    Limit(
                        "stagnation",
                        f"ความไม่แน่นอนรวมแทบไม่ขยับมา {w} รอบ — วิธีถามปัจจุบันอาจตันแล้ว",
                        0.7,
                        epoch,
                    )
                )
        if len(self.node_history) >= w and len(set(self.node_history[-w:])) == 1:
            found.append(
                Limit("stagnation", f"กราฟไม่โตเลยมา {w} รอบ", 0.65, epoch)
            )

        # 4. ความใหม่กำลังยุบ — พื้นที่คำถามเริ่มอิ่มตัว
        if len(self.novelty_history) >= 2:
            recent = self.novelty_history[-w:]
            if recent and sum(recent) / len(recent) < self.novelty_floor:
                found.append(
                    Limit(
                        "saturation",
                        f"ความใหม่เฉลี่ยของคำถามตกไปที่ {sum(recent)/len(recent):.2f} — "
                        "พื้นที่คำถามเดิมใกล้ถูกกินหมด",
                        0.75,
                        epoch,
                    )
                )

        # 5. ความขัดแย้งสะสมโดยไม่มีวิธีตัดสิน
        if len(self.contradiction_history) >= w:
            tail = self.contradiction_history[-w:]
            if tail[0] > 0 and tail[-1] >= tail[0]:
                found.append(
                    Limit(
                        "unresolved",
                        f"ความขัดแย้ง {tail[-1]} คู่ค้างอยู่ไม่ลดลงมา {w} รอบ — "
                        "ระบบยังไม่มีเกณฑ์ตัดสินระหว่างคำอธิบายที่แข่งกัน",
                        0.8,
                        epoch,
                    )
                )

        # 6. ยุทธวิธีเดียวผูกขาดคำถาม
        total_s = sum(self.strategy_uses.values())
        if total_s >= 8:
            name, cnt = self.strategy_uses.most_common(1)[0]
            if cnt / total_s > self.monoculture_share:
                found.append(
                    Limit(
                        "monoculture",
                        f"{cnt/total_s:.0%} ของคำถามมาจากยุทธวิธีเดียว ({name})",
                        0.6,
                        epoch,
                    )
                )

        # 7. เครื่องมือพัง
        for fail in self.instrument_failures[:3]:
            found.append(
                Limit("instrument", f"เครื่องมือสืบค้นล้มเหลว: {fail[:80]}", 0.85, epoch)
            )

        # 8. เพดานทรัพยากร — ข้อจำกัดที่มีอยู่จริงเสมอ ไม่ว่าจะฉลาดแค่ไหน
        if budget is not None:
            for lim in budget.pressure(epoch):
                found.append(lim)

        return self._merge(found, epoch)

    def _merge(self, found: list[Limit], epoch: int) -> list[Limit]:
        out: list[Limit] = []
        fresh_keys = set()
        for lim in found:
            key = f"{lim.kind}:{lim.text}"
            fresh_keys.add(key)
            prev = self.limits_seen.get(key)
            if prev is None:
                self.limits_seen[key] = lim
                out.append(lim)
            else:
                prev.epochs_persisted += 1
                prev.severity = min(1.0, prev.severity + 0.03)
                out.append(prev)
        for key in list(self.limits_seen):
            if key not in fresh_keys:
                del self.limits_seen[key]
        out.sort(key=lambda l: -l.severity)
        return out

    def limits(self, epoch: int, budget: "Budget | None" = None, k: int = 6) -> list[str]:
        return [l.text for l in self.detect(epoch, budget)[:k]]

    def gaps(self, epoch: int, budget: "Budget | None" = None) -> list[CapabilityGap]:
        """ช่องโหว่ที่ *เครื่องมือเดิมไม่พอ* — ต้องให้กำเนิดยุทธวิธีใหม่.

        เกณฑ์: ข้อจำกัดต้องรุนแรงพอ และต้อง *อยู่ทน* อย่างน้อยสองรอบ.
        ข้อจำกัดที่โผล่มารอบเดียวอาจเป็นสัญญาณรบกวน การรีบสร้างเครื่องมือ
        ตอบทุกเสียงรบกวนคือวิธีที่ระบบจะพองจนไร้ทิศทาง.
        """
        out: list[CapabilityGap] = []
        for lim in self.detect(epoch, budget):
            if lim.severity < 0.6 or lim.epochs_persisted < 2:
                continue
            level, source = _GAP_ROUTING.get(
                lim.kind, (QuestionLevel.META, "frontier")
            )
            if lim.kind == "coverage":
                for lv in QuestionLevel:
                    if lv.th in lim.text:
                        level = lv
                        break
                source = "self" if level is QuestionLevel.SELF_REFERENCE else "frontier"
            out.append(CapabilityGap(lim.text, level, source, lim.severity))
        return out[:3]

    # ---------------- persistence ----------------

    def to_dict(self) -> dict:
        return {
            "uncertainty_history": self.uncertainty_history[-64:],
            "novelty_history": self.novelty_history[-64:],
            "node_history": self.node_history[-64:],
            "contradiction_history": self.contradiction_history[-64:],
            "residual_age": self.residual_age,
            "strategy_uses": dict(self.strategy_uses),
            "level_uses": {str(k): v for k, v in self.level_uses.items()},
            "instrument_failures": self.instrument_failures[-8:],
            "limits_seen": {k: v.to_dict() for k, v in self.limits_seen.items()},
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SelfModel":
        sm = cls()
        sm.uncertainty_history = list(d.get("uncertainty_history", ()))
        sm.novelty_history = list(d.get("novelty_history", ()))
        sm.node_history = list(d.get("node_history", ()))
        sm.contradiction_history = list(d.get("contradiction_history", ()))
        sm.residual_age = dict(d.get("residual_age", {}))
        sm.strategy_uses = Counter(d.get("strategy_uses", {}))
        sm.level_uses = Counter({int(k): v for k, v in d.get("level_uses", {}).items()})
        sm.instrument_failures = list(d.get("instrument_failures", ()))
        sm.limits_seen = {
            k: Limit.from_dict(v) for k, v in d.get("limits_seen", {}).items()
        }
        return sm


_GAP_ROUTING: dict[str, tuple[QuestionLevel, str]] = {
    "recurrence": (QuestionLevel.META, "residual"),
    "stagnation": (QuestionLevel.SELF_REFERENCE, "self"),
    "saturation": (QuestionLevel.ONTOLOGY, "hole"),
    "unresolved": (QuestionLevel.ASSUMPTION, "contradiction"),
    "monoculture": (QuestionLevel.META, "frontier"),
    "instrument": (QuestionLevel.SELF_REFERENCE, "self"),
    "resource": (QuestionLevel.SELF_REFERENCE, "self"),
}


@dataclass
class Budget:
    """เพดานที่จักรวาลตั้งไว้ — และระบบต้องรู้ว่ามันกำลังจะชน.

    การชนเพดานไม่ใช่ข้อผิดพลาด มันคือ *การค้นพบขอบเขต* ซึ่งถูกแปลง
    เป็นคำถามระดับ SELF_REFERENCE ทันที.
    """

    max_epochs: int | None = None
    max_nodes: int | None = None
    max_questions: int | None = None
    max_cost: float | None = None

    spent_cost: float = 0.0
    asked: int = 0
    nodes: int = 0

    def pressure(self, epoch: int) -> list[Limit]:
        out: list[Limit] = []

        def check(name: str, used: float, cap: float | None, unit: str) -> None:
            if cap is None or cap <= 0:
                return
            ratio = used / cap
            if ratio >= 0.75:
                out.append(
                    Limit(
                        "resource",
                        f"ใกล้ชนเพดาน{name}แล้ว ({used:g}/{cap:g} {unit}) — "
                        "ขอบเขตนี้ไม่ได้มาจากความไม่รู้ แต่มาจากทรัพยากร",
                        min(1.0, 0.5 + 0.5 * ratio),
                        epoch,
                    )
                )

        check("จำนวนรอบ", epoch, self.max_epochs, "รอบ")
        check("ขนาดกราฟ", self.nodes, self.max_nodes, "node")
        check("จำนวนคำถาม", self.asked, self.max_questions, "คำถาม")
        check("ต้นทุนการสืบค้น", self.spent_cost, self.max_cost, "หน่วย")
        return out

    def exhausted(self, epoch: int) -> str | None:
        if self.max_epochs is not None and epoch >= self.max_epochs:
            return "เพดานจำนวนรอบ"
        if self.max_nodes is not None and self.nodes >= self.max_nodes:
            return "เพดานขนาดกราฟ"
        if self.max_questions is not None and self.asked >= self.max_questions:
            return "เพดานจำนวนคำถาม"
        if self.max_cost is not None and self.spent_cost >= self.max_cost:
            return "เพดานต้นทุนการสืบค้น"
        return None

    def to_dict(self) -> dict:
        return {
            "max_epochs": self.max_epochs,
            "max_nodes": self.max_nodes,
            "max_questions": self.max_questions,
            "max_cost": self.max_cost,
            "spent_cost": self.spent_cost,
            "asked": self.asked,
            "nodes": self.nodes,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Budget":
        return cls(**d)
