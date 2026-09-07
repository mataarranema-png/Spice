"""เครื่องยนต์ก้นหอย.

    K_n -> Q_n -> E_n -> A_n -> C_n -> M_{n+1} -> Q_{n+1}

กฎเหล็กสามข้อที่ถูกบังคับใช้ในโค้ด ไม่ใช่แค่เขียนไว้ใน README:

1. **ไม่มี `STOP = when answer found`**  ทุกคำตอบถูกแปลงเป็น residual
   node ซึ่งกลายเป็นเป้าหมายของคำถามรอบถัดไปโดยอัตโนมัติ.
2. **ห้ามถามซ้ำ**  ledger บล็อก signature เดิม และ MMR ตัดคำถามที่คล้าย
   กันเองใน epoch เดียว.
3. **ตันแล้วให้ถามถึงความตัน**  ถ้าคัดคำถามใหม่ไม่ครบโควตา ระบบจะสร้าง
   คำถามระดับ SELF_REFERENCE เกี่ยวกับความอิ่มตัวนั้นทันที — ก้นหอยจึง
   ไม่มีสถานะ "จบ" มีแต่สถานะ "ชนเพดานทรัพยากร".
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from .evolution import EvolutionReport, Population
from .graph import KnowledgeGraph
from .investigator import (
    Investigator,
    ReflectiveInvestigator,
    canonical_label,
    ensure_residual,
)
from .question import Question, QuestionLedger
from .scoring import Scored, epoch_reward, select
from .selfmodel import Budget, SelfModel
from .strategies import SELF_NODE, GenerationContext
from .types import EpistemicStatus, Finding, QuestionLevel, Relation

MAX_CANDIDATES = 240


@dataclass
class Turn:
    """หนึ่งคำถาม -> หนึ่งคำตอบ -> หนึ่งเศษที่เหลือ."""

    question: Question
    answer: str
    confidence: float
    residual: str
    nodes_added: int
    contradictions: int
    yield_score: float

    def to_dict(self) -> dict:
        return {
            "question": self.question.to_dict(),
            "answer": self.answer,
            "confidence": self.confidence,
            "residual": self.residual,
            "nodes_added": self.nodes_added,
            "contradictions": self.contradictions,
            "yield": self.yield_score,
        }


@dataclass
class EpochRecord:
    epoch: int
    turns: list[Turn] = field(default_factory=list)
    stats_before: dict = field(default_factory=dict)
    stats_after: dict = field(default_factory=dict)
    novelty_mean: float = 0.0
    reward: float = 0.0
    limits: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    evolution: str = ""
    saturated: bool = False

    def to_dict(self) -> dict:
        return {
            "epoch": self.epoch,
            "turns": [t.to_dict() for t in self.turns],
            "stats_before": self.stats_before,
            "stats_after": self.stats_after,
            "novelty_mean": self.novelty_mean,
            "reward": self.reward,
            "limits": self.limits,
            "gaps": self.gaps,
            "evolution": self.evolution,
            "saturated": self.saturated,
        }


class Spiral:
    def __init__(
        self,
        graph: KnowledgeGraph | None = None,
        *,
        ledger: QuestionLedger | None = None,
        population: Population | None = None,
        self_model: SelfModel | None = None,
        investigator: Investigator | None = None,
        budget: Budget | None = None,
        seed: int = 0,
        lang: str = "th",
        questions_per_epoch: int = 3,
    ) -> None:
        self.rng = random.Random(seed)
        self.graph = graph or KnowledgeGraph()
        self.ledger = ledger or QuestionLedger()
        self.population = population or Population(rng=random.Random(seed + 1))
        self.self_model = self_model or SelfModel()
        self.investigator = investigator or ReflectiveInvestigator(random.Random(seed + 2))
        self.budget = budget or Budget()
        self.lang = lang
        self.k = questions_per_epoch
        self.epoch = 0
        self.history: list[EpochRecord] = []
        self.pending: list[Question] = []   # คำถามที่มนุษย์แทรกเข้ามา

    # ------------------------------------------------------------ seeding

    @classmethod
    def from_topic(cls, topic: str, **kw) -> "Spiral":
        sp = cls(**kw)
        sp.seed_topic(topic)
        return sp

    def seed_topic(self, topic: str) -> None:
        """เมล็ดของก้นหอย: หัวข้อหนึ่งอันในสถานะ UNKNOWN.

        จงใจไม่ใส่ความรู้ตั้งต้นให้ — เพราะแหล่งกำเนิดคำถามคือความไม่รู้
        ไม่ใช่ความรู้.
        """
        self.graph.add_node(
            topic,
            status=EpistemicStatus.UNKNOWN,
            level=QuestionLevel.OBJECT,
            tags=("seed",),
            provenance="seed",
            epoch=self.epoch,
        )

    def ask(self, text: str, level: QuestionLevel = QuestionLevel.OBJECT) -> None:
        """แทรกคำถามของมนุษย์เข้าไปในก้นหอย (จะถูกถามใน epoch ถัดไป)."""
        target = ()
        for node in self.graph:
            if node.label and node.label in text:
                target = (node.id,)
                break
        self.pending.append(
            Question(text=text, level=level, strategy="human", targets=target, forced=True)
        )

    # ------------------------------------------------------------ one turn of the spiral

    def step(self) -> EpochRecord:
        rec = EpochRecord(epoch=self.epoch)
        rec.stats_before = self.graph.stats()

        limits = self.self_model.limits(self.epoch, self.budget)
        rec.limits = limits

        chosen, rec.saturated = self._choose(limits)

        outcomes: dict[str, list[float]] = {}
        for scored in chosen:
            turn = self._investigate_and_integrate(scored)
            rec.turns.append(turn)
            outcomes.setdefault(turn.question.strategy, []).append(turn.yield_score)

        rec.stats_after = self.graph.stats()
        # คำถามหนีความอิ่มตัวมีเลขรอบอยู่ในตัว จึงใหม่ 100% เสมอโดยอัตโนมัติ
        # ถ้านับรวม ระบบจะรายงานว่าตัวเอง "สร้างสรรค์เต็มร้อย" ในรอบที่มันตันสนิท
        # — คือการโกงมาตรวัดของตัวเอง ต้องนับเฉพาะคำถามที่ผ่านการคัดเลือกจริง
        earned = [s.n for s in chosen if not s.question.forced]
        rec.novelty_mean = sum(earned) / len(earned) if earned else 0.0
        rec.reward = epoch_reward(rec.stats_before, rec.stats_after, rec.novelty_mean)

        # ---- ระบบมองตัวเอง ----
        self.self_model.observe_epoch(
            epoch=self.epoch,
            stats=rec.stats_after,
            selected_levels=[t.question.level for t in rec.turns],
            selected_strategies=[t.question.strategy for t in rec.turns],
            novelty_mean=rec.novelty_mean,
            open_residuals=[r for _, r in self.graph.open_residuals(32)],
            instrument_failures=list(getattr(self.investigator, "failures", ()) or ()),
        )

        # ---- ระบบแก้ไขตัวเอง ----
        self.population.credit(
            {name: sum(v) / len(v) for name, v in outcomes.items() if v}
        )
        self.population.decay_unused(set(outcomes))
        gaps = self.self_model.gaps(self.epoch, self.budget)
        rec.gaps = [g.text for g in gaps]
        report: EvolutionReport = self.population.evolve(self.epoch, gaps, rec.reward)
        rec.evolution = report.summary()

        self.budget.nodes = rec.stats_after["nodes"]
        self.history.append(rec)
        self.epoch += 1
        return rec

    def run(self, epochs: int = 5) -> list[EpochRecord]:
        out: list[EpochRecord] = []
        for _ in range(epochs):
            reason = self.budget.exhausted(self.epoch)
            if reason:
                # การชนเพดานไม่ใช่ "จบ" — มันคือขอบเขตที่เพิ่งถูกค้นพบ
                self._record_boundary(reason)
                break
            out.append(self.step())
        return out

    # ------------------------------------------------------------ internals

    def _choose(self, limits: list[str]) -> tuple[list[Scored], bool]:
        ctx = GenerationContext(
            graph=self.graph,
            ledger=self.ledger,
            epoch=self.epoch,
            rng=self.rng,
            lang=self.lang,
            limits=limits,
            recent_answers=[
                (t.question.text, t.answer)
                for r in self.history[-1:]
                for t in r.turns
            ],
        )

        candidates: list[Question] = list(self.pending)
        self.pending.clear()
        for strat in self.population.live():
            candidates.extend(strat.generate(ctx))
        self.rng.shuffle(candidates)
        candidates = candidates[:MAX_CANDIDATES]

        chosen = select(
            candidates,
            self.graph,
            self.ledger,
            self.population.weights,
            k=self.k,
        )

        # กฎข้อ 3: ตันแล้วให้ถามถึงความตัน
        saturated = len(chosen) < self.k
        if saturated:
            chosen.extend(self._saturation_questions(self.k - len(chosen), limits))

        for s in chosen:
            self.ledger.record(s.question)
            self.budget.asked += 1
        return chosen, saturated

    def _saturation_questions(self, n: int, limits: list[str]) -> list[Scored]:
        """เมื่อพื้นที่คำถามเดิมหมด ให้ถามถึง *พื้นที่* เอง.

        คำถามพวกนี้ถูกทำให้ไม่ซ้ำด้วยเลข epoch เสมอ ก้นหอยจึงหมุนต่อได้
        แม้ในทางทฤษฎีคำถามทุกคำถามในกราฟปัจจุบันจะถูกถามไปหมดแล้ว.
        """
        stuck = limits[0] if limits else "พื้นที่คำถามชุดเดิมถูกใช้จนหมด"
        shapes = (
            f"[รอบ {self.epoch}] คำถามที่ระบบสร้างได้ทั้งหมดตอนนี้ถูกถามไปหมดแล้ว "
            f"โดยมี \"{stuck}\" ค้างอยู่ — คำถามชนิดใดที่ *ภาษาปัจจุบันของระบบ* "
            "ยังพูดออกมาไม่ได้เลย?",
            f"[รอบ {self.epoch}] ถ้าความอิ่มตัวนี้เป็นผลจากวิธีแทนความรู้ "
            "(กราฟ node-edge) ไม่ใช่จากโลก — โครงสร้างแบบไหนที่จะทำให้คำถามใหม่กลับมาเป็นไปได้?",
            f"[รอบ {self.epoch}] อะไรที่ระบบนับว่า \"ไม่ใช่คำถาม\" โดยอัตโนมัติ "
            "และการนับแบบนั้นตัดอะไรทิ้งไปบ้าง?",
        )
        out: list[Scored] = []
        for i in range(min(n, len(shapes))):
            q = Question(
                text=shapes[i],
                level=QuestionLevel.SELF_REFERENCE,
                strategy="saturation-escape",
                epoch=self.epoch,
                forced=True,
            )
            out.append(Scored(q, u=1.0, c=0.6, n=1.0, total=1.0))
        return out

    def _investigate_and_integrate(self, scored: Scored) -> Turn:
        q = scored.question
        # คำถามที่ไม่มีเป้าหมายในกราฟ (โดยเฉพาะคำถามถึงตัวระบบ) ต้องได้ node
        # ของตัวเองก่อน มิฉะนั้นคำตอบและเศษที่เหลือจะลอยหลุดจากกราฟ
        if not q.targets and q.subject:
            anchor_node = self.graph.add_node(
                canonical_label(q.subject),
                status=EpistemicStatus.UNKNOWN,
                level=q.level,
                tags=("self",) if q.subject == SELF_NODE else (),
                provenance=q.strategy,
                epoch=self.epoch,
            )
            q.targets = (anchor_node.id,)
        try:
            finding = self.investigator.investigate(q, self.graph)
        except Exception as exc:  # noqa: BLE001 — เครื่องมือพังก็เป็นข้อมูล
            finding = Finding(
                answer=f"การสืบค้นล้มเหลว: {type(exc).__name__}",
                confidence=0.0,
                residual=f"เครื่องมือสืบค้นล้มเหลวกับคำถามระดับ{q.level.th}",
                source="failure",
            )
        finding = ensure_residual(finding, q, self.rng)
        self.budget.spent_cost += finding.cost

        before_nodes = len(self.graph)

        for spec in finding.new_nodes:
            self.graph.add_node(
                canonical_label(spec.label),
                status=spec.status,
                confidence=spec.confidence,
                level=spec.level,
                tags=spec.tags,
                provenance=q.strategy,
                epoch=self.epoch,
            )
        for spec in finding.new_edges:
            self.graph.add_edge(
                canonical_label(spec.source),
                canonical_label(spec.target),
                spec.relation,
                weight=spec.weight,
                provenance=q.strategy,
                epoch=self.epoch,
            )

        # อัปเดตเป้าหมาย: รู้มากขึ้น แต่ไม่มีวันถึง KNOWN แบบปิดประตู
        for tid in q.targets:
            node = self.graph.node(tid)
            if node is None:
                continue
            node.visits += 1
            node.confidence = min(0.95, node.confidence + 0.35 * finding.confidence)
            if node.status is EpistemicStatus.UNKNOWN:
                node.status = EpistemicStatus.PARTIALLY_KNOWN
            elif (
                node.status is EpistemicStatus.PARTIALLY_KNOWN
                and node.confidence > 0.7
            ):
                node.status = EpistemicStatus.UNCERTAIN if finding.contradicts else EpistemicStatus.KNOWN

        # ---- หัวใจ: คำตอบกลายเป็นคำถามรุ่นถัดไป ----
        residual_label = canonical_label(finding.residual)
        anchor = self.graph.node(q.targets[0]) if q.targets else None
        if anchor is not None and residual_label not in anchor.residuals:
            anchor.residuals.append(residual_label)
            if len(anchor.residuals) > 4:
                anchor.residuals.pop(0)
        self.graph.add_node(
            residual_label,
            status=EpistemicStatus.UNKNOWN,
            confidence=0.0,
            level=QuestionLevel(min(int(QuestionLevel.SELF_REFERENCE), int(q.level) + 1)),
            tags=("residual", f"e{self.epoch}"),
            provenance=f"residual::{q.strategy}",
            epoch=self.epoch,
        )
        if anchor is not None:
            self.graph.add_edge(
                residual_label,
                anchor.label,
                Relation.UNKNOWN_LINK,
                provenance="residual",
                epoch=self.epoch,
            )

        nodes_added = len(self.graph) - before_nodes
        contradictions = len(finding.contradicts)
        yield_score = self._yield(scored, nodes_added, contradictions, finding)
        return Turn(
            question=q,
            answer=finding.answer,
            confidence=finding.confidence,
            residual=residual_label,
            nodes_added=nodes_added,
            contradictions=contradictions,
            yield_score=yield_score,
        )

    @staticmethod
    def _yield(scored: Scored, nodes_added: int, contradictions: int, finding: Finding) -> float:
        """ผลผลิตของคำถามหนึ่งข้อ — ใช้ให้เครดิตยุทธวิธีที่ผลิตมัน.

        สังเกตว่า *ความมั่นใจในคำตอบ* มีน้ำหนักน้อยที่สุด และความขัดแย้ง
        ที่ถูกเปิดโปงมีน้ำหนักมาก: ระบบนี้ให้รางวัลกับการทำให้ภาพสั่น
        มากกว่าการทำให้ภาพนิ่ง.
        """
        return max(
            0.0,
            min(
                1.0,
                0.35 * scored.n
                + 0.25 * min(1.0, nodes_added / 2.0)
                + 0.25 * min(1.0, contradictions)
                + 0.10 * scored.u
                + 0.05 * finding.confidence,
            ),
        )

    def _record_boundary(self, reason: str) -> None:
        label = f"ขอบเขตที่ค้นพบ: {reason} ที่รอบ {self.epoch}"
        self.graph.add_node(
            label,
            status=EpistemicStatus.UNKNOWN,
            level=QuestionLevel.SELF_REFERENCE,
            tags=("boundary",),
            provenance="budget",
            epoch=self.epoch,
        )
        self.pending.append(
            Question(
                text=f"ระบบหยุดเพราะ{reason} ไม่ใช่เพราะคำถามหมด — "
                f"ถ้าเพดานนี้ถูกยกออก คำถามข้อถัดไปควรเป็นอะไร?",
                level=QuestionLevel.SELF_REFERENCE,
                strategy="boundary",
                epoch=self.epoch,
                forced=True,
            )
        )

    # ------------------------------------------------------------ reporting

    def report(self, last: int = 3) -> str:
        st = self.graph.stats()
        lines = [
            f"ก้นหอยรอบที่ {self.epoch} | node {st['nodes']} | edge {st['edges']} "
            f"| ขัดแย้ง {st['contradictions']} | U เฉลี่ย {st['mean_uncertainty']:.3f}",
            f"ยุทธวิธีมีชีวิต {len(self.population.live())} ตัว "
            f"(เจเนอเรชัน {self.population.generation}) | ถามไปแล้ว {len(self.ledger)} คำถาม",
            "",
        ]
        for rec in self.history[-last:]:
            lines.append(f"── รอบ {rec.epoch} ─ reward {rec.reward:+.3f} "
                         f"{'[อิ่มตัว→ถามถึงความอิ่มตัว]' if rec.saturated else ''}")
            for t in rec.turns:
                lines.append(f"  [{t.question.level.th}] {t.question.text}")
                lines.append(f"    → {t.answer}")
                lines.append(f"    ↯ เศษที่เหลือ: {t.residual}")
            if rec.limits:
                lines.append("  ขอบเขตที่ตรวจพบ: " + "; ".join(rec.limits[:3]))
            if rec.gaps:
                lines.append("  ช่องโหว่ที่ต้องมีเครื่องมือใหม่: " + "; ".join(g[:60] for g in rec.gaps))
            lines.append("  วิวัฒนาการ: " + rec.evolution)
            lines.append("")
        return "\n".join(lines)

    # ------------------------------------------------------------ persistence

    def to_dict(self) -> dict:
        return {
            "version": 1,
            "epoch": self.epoch,
            "lang": self.lang,
            "k": self.k,
            "graph": self.graph.to_dict(),
            "ledger": self.ledger.to_dict(),
            "population": self.population.to_dict(),
            "self_model": self.self_model.to_dict(),
            "budget": self.budget.to_dict(),
            "history": [r.to_dict() for r in self.history[-32:]],
        }

    @classmethod
    def from_dict(
        cls,
        d: dict,
        *,
        investigator: Investigator | None = None,
        seed: int = 0,
    ) -> "Spiral":
        sp = cls(
            KnowledgeGraph.from_dict(d["graph"]),
            ledger=QuestionLedger.from_dict(d.get("ledger", {})),
            population=Population.from_dict(d["population"], random.Random(seed + 1)),
            self_model=SelfModel.from_dict(d.get("self_model", {})),
            investigator=investigator,
            budget=Budget.from_dict(d.get("budget", {})),
            seed=seed,
            lang=d.get("lang", "th"),
            questions_per_epoch=d.get("k", 3),
        )
        sp.epoch = d.get("epoch", 0)
        return sp
