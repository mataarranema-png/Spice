"""การแก้ไขตัวเอง: ประชากรของยุทธวิธี + การไต่เขาของน้ำหนักคะแนน.

ระบบนี้ไม่ได้เขียนซอร์สโค้ดตัวเองใหม่ (ซึ่งไม่ปลอดภัยและไม่น่าเชื่อถือ)
แต่มันแก้ไข *สิ่งที่กำหนดพฤติกรรมของมันจริง ๆ* ได้ทั้งหมด:

  * ประชากรของยุทธวิธีการถาม — เกิด, กลายพันธุ์, ผสมข้าม, ปลดระวาง
  * น้ำหนัก (w_u, w_c, w_n) ที่ตัดสินว่าคำถามแบบไหนชนะ
  * และที่สำคัญที่สุด: ยุทธวิธีที่ *เกิดจากจุดบอดที่มันตรวจพบในตัวเอง*

ทั้งหมดถูกเซฟลงดิสก์ รอบถัดไปจึงเริ่มจาก "ตัวเองรุ่นใหม่" ไม่ใช่รุ่นเดิม.
"""

from __future__ import annotations

import math
import random
from collections import defaultdict
from dataclasses import dataclass, field

from .scoring import Weights
from .selfmodel import CapabilityGap
from .strategies import (
    Strategy,
    builtin_strategies,
    cross_strategies,
    mutate_strategy,
    strategy_from_gap,
)
from .types import QuestionLevel

EMA = 0.35
OPTIMISM = 0.55          # fitness เริ่มต้นของยุทธวิธีที่ยังไม่เคยถูกใช้
RETIRE_BELOW = 0.16
MIN_USES_BEFORE_RETIRE = 3
EXPLORE_C = 0.16         # ค่าคงที่ของ UCB — สูงไปคือสุ่มมั่ว ต่ำไปคือโลภ
STALE_AFTER = 8          # เกิดมานานเท่านี้แล้วยังไม่เคยถูกเลือกเลย = ตายแล้ว
W_FLOOR, W_CEIL = 0.10, 0.60   # ห้ามให้พจน์ใดกลืนฟังก์ชันเป้าหมายทั้งหมด


def _clamp(w: Weights, iterations: int = 32) -> Weights:
    """ฉายน้ำหนักลงบนเซต {sum = 1, W_FLOOR <= w_i <= W_CEIL}.

    ถ้าปล่อยอิสระ การไต่เขาจะดันน้ำหนักตัวเดียวไปที่ ~1.0 แล้วระบบจะ
    เหลือแรงจูงใจเดียว — ซึ่งก็คือการยุบก้นหอยกลับเป็นเส้นตรงอีกครั้ง.

    การบีบครั้งเดียวแล้ว normalize ไม่พอ: normalize จะดันค่าที่เพิ่งบีบ
    ให้ทะลุเพดานอีก (0.60, 0.10, 0.10) -> (0.75, 0.125, 0.125) จึงต้อง
    สลับบีบ/normalize จนลู่เข้า.
    """
    for _ in range(iterations):
        w = w.normalized()
        clamped = Weights(
            min(W_CEIL, max(W_FLOOR, w.u)),
            min(W_CEIL, max(W_FLOOR, w.c)),
            min(W_CEIL, max(W_FLOOR, w.n)),
        )
        if abs(clamped.u + clamped.c + clamped.n - 1.0) < 1e-9:
            return clamped
        w = clamped
    # ถ้ายังไม่ลู่เข้าพอดี ให้กรอบชนะผลรวม: `Weights.normalized()` ถูกเรียก
    # ตอนใช้งานอยู่แล้ว ส่วนเพดานคือสิ่งที่ห้ามละเมิด
    return Weights(
        min(W_CEIL, max(W_FLOOR, w.u)),
        min(W_CEIL, max(W_FLOOR, w.c)),
        min(W_CEIL, max(W_FLOOR, w.n)),
    )


def _root(s: "Strategy") -> str:
    return (s.lineage[0] if s.lineage else s.name).split("~")[0].split("×")[0].split("@")[0]


@dataclass
class EvolutionReport:
    born: list[str] = field(default_factory=list)
    retired: list[str] = field(default_factory=list)
    weights_before: Weights = field(default_factory=Weights)
    weights_after: Weights = field(default_factory=Weights)
    reward: float = 0.0
    accepted_weights: bool = False

    def summary(self) -> str:
        bits = []
        if self.born:
            bits.append("เกิด: " + ", ".join(self.born))
        if self.retired:
            bits.append("ปลดระวาง: " + ", ".join(self.retired))
        w = self.weights_after.normalized()
        bits.append(f"w=(u{w.u:.2f} c{w.c:.2f} n{w.n:.2f})")
        bits.append(f"reward={self.reward:+.3f}")
        return " | ".join(bits)


class Population:
    """ประชากรของยุทธวิธี — หน่วยที่วิวัฒนาการจริงในระบบนี้."""

    def __init__(
        self,
        strategies: list[Strategy] | None = None,
        weights: Weights | None = None,
        rng: random.Random | None = None,
        *,
        max_size: int = 22,
        min_size: int = 6,
        gap_quota: int | None = None,
    ) -> None:
        pool = strategies if strategies is not None else builtin_strategies()
        self.strategies: dict[str, Strategy] = {s.name: s for s in pool}
        self.weights = weights or Weights()
        self.rng = rng or random.Random(0)
        self.max_size = max_size
        self.min_size = min_size
        self.gap_quota = gap_quota if gap_quota is not None else max(2, max_size * 2 // 5)

        self._best_reward: float = float("-inf")
        self._last_step: tuple[float, float, float] | None = None
        self.generation: int = 0

    # ---------------- การใช้งาน ----------------

    def live(self) -> list[Strategy]:
        return list(self.strategies.values())

    def get(self, name: str) -> Strategy | None:
        return self.strategies.get(name)

    def credit(self, outcomes: dict[str, float]) -> None:
        """ให้เครดิตยุทธวิธีตามผลที่คำถามของมันสร้างจริงใน epoch นี้."""
        for name, reward in outcomes.items():
            s = self.strategies.get(name)
            if s is None:
                continue
            s.uses += 1
            s.wins += reward
            s.fitness = (1 - EMA) * s.fitness + EMA * max(0.0, min(1.0, reward))

    def explore_bonus(self, name: str) -> float:
        """โบนัสสำรวจแบบ UCB1 ให้ยุทธวิธีที่ยังถูกลองน้อย.

        ถ้าเรียงตาม fitness ล้วน ๆ ยุทธวิธีที่บังเอิญได้คะแนนดีในสองรอบแรก
        จะผูกขาดการเลือกไปตลอด และตัวที่ยังไม่เคยถูกลองเลยจะไม่มีวันได้พิสูจน์
        ตัวเอง — ซึ่งเป็นเหตุผลเดียวกับที่ SelfModel เคยฟ้องว่าเกิด monoculture.
        """
        s = self.strategies.get(name)
        if s is None:
            return 0.0
        total = sum(x.uses for x in self.strategies.values())
        return EXPLORE_C * math.sqrt(math.log(total + 2) / (s.uses + 1))

    def decay_unused(self, used: set[str]) -> None:
        """ยุทธวิธีที่ไม่ถูกเลือกจะจางลง — แต่ *ช้ามาก*.

        เดิมใช้ 0.97 ต่อรอบ ซึ่งดูไม่มาก จนกระทั่งดูตัวเลขจริง: ในประชากร
        22 ตัวที่เลือกได้รอบละ 3 คำถาม ยุทธวิธีหนึ่งถูกเลือกราว 14% ของรอบ
        การหักทบต้นจึงลากทุกตัวลงต่ำกว่าเกณฑ์ปลดระวางภายในร้อยรอบ — รัน
        150 รอบจบลงด้วยประชากรที่ไม่เหลือ builtin สักตัว ทั้งที่ไม่มีตัวไหน
        เคยถูกวัดว่าแย่จริง

        การสำรวจตอนนี้เป็นหน้าที่ของ UCB (`explore_bonus`) แล้ว การปลดระวาง
        จึงควรอิงกับ *ผลที่วัดได้* ไม่ใช่การเหี่ยวเฉาตามเวลา.
        """
        for name, s in self.strategies.items():
            if name not in used:
                s.fitness *= 0.995

    # ---------------- วิวัฒนาการ ----------------

    def evolve(
        self,
        epoch: int,
        gaps: list[CapabilityGap],
        reward: float,
    ) -> EvolutionReport:
        rep = EvolutionReport(weights_before=self.weights, reward=reward)
        rng = self.rng
        self.generation += 1

        # 1. ให้กำเนิดเครื่องมือใหม่จากจุดบอด — สำคัญกว่าการกลายพันธุ์สุ่ม
        # เครื่องมือที่เกิดจากจุดบอดมีค่า แต่ถ้าปล่อยให้เกิดเรื่อย ๆ มันจะกิน
        # ประชากรจนไม่เหลือหัววัดชนิดอื่น (วัดได้ 14 จาก 20 ตัว) จำกัดโควตาไว้
        # แล้ว *สลับตัวที่อ่อนที่สุดออก* แทนที่จะปิดประตูไม่ให้เกิดเลย
        for gap in gaps:
            s = strategy_from_gap(gap.text, gap.level, epoch, gap.source)
            if s.name in self.strategies:
                continue
            existing = [x for x in self.live() if x.origin == "capability-gap"]
            if len(existing) >= self.gap_quota:
                weakest = min(existing, key=lambda x: x.fitness)
                if weakest.fitness >= s.fitness:
                    continue
                del self.strategies[weakest.name]
                rep.retired.append(weakest.name)
            self.strategies[s.name] = s
            rep.born.append(s.name)

        ranked = sorted(self.live(), key=lambda s: -s.fitness)
        median = (
            sorted(s.fitness for s in ranked)[len(ranked) // 2] if ranked else 0.5
        )

        def temper(child: Strategy) -> Strategy:
            """กดความมั่นใจแรกเกิดลงมาที่มัธยฐานของประชากร.

            ลูกที่เกิดใหม่รับ fitness มาจากพ่อแม่ (× 0.9) โดยยังไม่เคยถูกวัด
            เลยสักครั้ง ส่วนตัวที่ทำงานมาแล้วถือคะแนน *ที่วัดได้จริง* ซึ่ง
            มักต่ำกว่า  ผลคือทุกครั้งที่ประชากรล้น ตัวที่ถูกวัดจะถูกตัดออก
            ก่อนตัวที่ยังไม่เคยพิสูจน์ตัวเอง — รัน 150 รอบจึงจบลงโดยไม่เหลือ
            ยุทธวิธีต้นฉบับสักตัว ทั้งที่ไม่มีตัวไหนเคยแพ้การวัดจริง

            การสำรวจเป็นหน้าที่ของ UCB อยู่แล้ว ลูกใหม่จึงไม่ต้องการ
            แต้มต่อเพิ่มเพื่อให้ได้ลงสนาม.
            """
            child.fitness = min(child.fitness, median)
            return child

        # 2. กลายพันธุ์จากตัวที่ทำได้ดี
        if ranked and len(self.strategies) < self.max_size:
            parent = rng.choice(ranked[: max(1, len(ranked) // 3)])
            child = mutate_strategy(parent, rng, epoch)
            if child.name not in self.strategies:
                self.strategies[child.name] = child
                rep.born.append(child.name)

        # 3. ผสมข้าม — แหล่งเดียวของคำถามที่พ่อแม่ *นิยามไม่ได้*
        if len(ranked) >= 2 and len(self.strategies) < self.max_size:
            a = ranked[0]
            # หาคู่ที่ *ไม่ใช่ญาติ* ก่อน — ผสมในสายเลือดเดียวกันได้ลูกที่
            # ถามเหมือนพ่อแม่ ซึ่งขัดกับเหตุผลทั้งหมดของการผสมข้าม
            base = _root(a)
            partners = [s2 for s2 in ranked[1:] if _root(s2) != base] or ranked[1:]
            b = partners[0]
            if a.name != b.name:
                child = temper(cross_strategies(a, b, rng, epoch))
                if child.name not in self.strategies:
                    self.strategies[child.name] = child
                    rep.born.append(child.name)

        # 4. ปลดระวาง — แต่ห้ามทำให้ระดับคำถามใดหายไปทั้งระดับ
        rep.retired.extend(self._retire(epoch))

        # 5. ไต่เขาน้ำหนักคะแนน
        rep.accepted_weights = self._adapt_weights(reward)
        rep.weights_after = self.weights
        return rep

    def _retire(self, epoch: int = 0) -> list[str]:
        retired: list[str] = []
        by_level: dict[int, list[Strategy]] = defaultdict(list)
        for s in self.live():
            by_level[int(s.level)].append(s)

        def can_drop(s: Strategy) -> bool:
            if len(self.strategies) - len(retired) <= self.min_size:
                return False
            # ถ้ามันเป็นตัวสุดท้ายของระดับนั้น การทิ้งมันคือการสร้างจุดบอด
            survivors = [
                x for x in by_level[int(s.level)] if x.name not in retired
            ]
            return len(survivors) > 1

        for s in sorted(self.live(), key=lambda s: s.fitness):
            tried_and_failed = (
                s.uses >= MIN_USES_BEFORE_RETIRE and s.fitness < RETIRE_BELOW
            )
            # "ไม่เคยถูกเลือกเลย ทั้งที่มีโอกาสหลายครั้ง" เป็นเหตุผลให้ปลดระวาง
            # พอ ๆ กับ "ถูกเลือกแล้วให้ผลแย่"
            #
            # นับจาก `offered` ไม่ใช่จากอายุ: ยุทธวิธีอย่าง comparative_probe
            # ต้องรอจนกราฟมีคำอธิบายที่แข่งกันจริงก่อนถึงจะมีอะไรให้ถาม การนับ
            # ตามอายุทำให้มันถูกตัดทิ้งก่อนจะได้ลงสนามสักครั้ง — ความสามารถ
            # หายไปถาวรพอดีตอนที่มันกำลังจะมีประโยชน์
            never_used = s.uses == 0 and s.offered >= STALE_AFTER
            if (tried_and_failed or never_used) and can_drop(s):
                retired.append(s.name)

        # ล้นเพดานประชากร: ตัดตัวอ่อนที่สุดที่ยังทิ้งได้
        while len(self.strategies) - len(retired) > self.max_size:
            candidates = [s for s in self.live() if s.name not in retired and can_drop(s)]
            if not candidates:
                break
            retired.append(min(candidates, key=lambda s: s.fitness).name)

        for name in retired:
            self.strategies.pop(name, None)
        return retired

    def _adapt_weights(self, reward: float) -> bool:
        """(1+1)-ES: เสนอการขยับ ถ้าผลดีขึ้นก็เก็บไว้ ถ้าแย่ลงก็ถอย.

        ระบบจึงเรียนรู้เองว่าตอนนี้ควรวิ่งไล่ความไม่รู้ ความขัดแย้ง หรือ
        ความแปลกใหม่ — โดยไม่มีใครบอก.
        """
        rng = self.rng
        accepted = False
        if self._last_step is not None:
            if reward >= self._best_reward:
                self._best_reward = reward
                accepted = True
            else:
                du, dc, dn = self._last_step
                self.weights = Weights(
                    max(0.02, self.weights.u - du),
                    max(0.02, self.weights.c - dc),
                    max(0.02, self.weights.n - dn),
                )
        else:
            self._best_reward = reward

        sigma = 0.06
        du, dc, dn = (rng.gauss(0, sigma) for _ in range(3))
        self.weights = Weights(
            max(0.02, self.weights.u + du),
            max(0.02, self.weights.c + dc),
            max(0.02, self.weights.n + dn),
        ).normalized()
        self.weights = _clamp(self.weights)
        self._last_step = (du, dc, dn)
        return accepted

    # ---------------- persistence ----------------

    def to_dict(self) -> dict:
        return {
            "strategies": [s.to_dict() for s in self.strategies.values()],
            "weights": self.weights.to_dict(),
            "max_size": self.max_size,
            "min_size": self.min_size,
            "gap_quota": self.gap_quota,
            "generation": self.generation,
            "best_reward": None if self._best_reward == float("-inf") else self._best_reward,
            "last_step": list(self._last_step) if self._last_step else None,
        }

    @classmethod
    def from_dict(cls, d: dict, rng: random.Random | None = None) -> "Population":
        pop = cls(
            [Strategy.from_dict(s) for s in d.get("strategies", ())],
            Weights.from_dict(d.get("weights", {})),
            rng,
            max_size=d.get("max_size", 22),
            min_size=d.get("min_size", 6),
            gap_quota=d.get("gap_quota"),
        )
        pop.generation = d.get("generation", 0)
        br = d.get("best_reward")
        pop._best_reward = float("-inf") if br is None else br
        ls = d.get("last_step")
        pop._last_step = tuple(ls) if ls else None
        return pop

    def table(self) -> str:
        rows = ["fitness  uses  gen  level            origin        name"]
        for s in sorted(self.live(), key=lambda s: -s.fitness):
            rows.append(
                f"{s.fitness:7.3f}  {s.uses:4d}  {s.generation:3d}  "
                f"{s.level.th:<14}  {s.origin:<12}  {s.name}"
            )
        return "\n".join(rows)
