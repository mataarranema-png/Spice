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

from . import gain as gainlib
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
QUESTION_SPACE = "พื้นที่คำถามของระบบ"   # คนละสิ่งกับ "ระบบผู้ถามเอง"
MIGRATION_COOLDOWN = 8   # รอบขั้นต่ำที่ต้องขุดย่านหนึ่งก่อนย้ายไปย่านใหม่
MIGRATION_MIN_WORK = 4   # การเยี่ยมขั้นต่ำในย่านนั้น ก่อนจะเรียกว่า "ตันแล้ว"


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
    gain: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "question": self.question.to_dict(),
            "answer": self.answer,
            "confidence": self.confidence,
            "residual": self.residual,
            "nodes_added": self.nodes_added,
            "contradictions": self.contradictions,
            "yield": self.yield_score,
            "gain": self.gain,
        }


@dataclass
class EpochRecord:
    epoch: int
    turns: list[Turn] = field(default_factory=list)
    stats_before: dict = field(default_factory=dict)
    stats_after: dict = field(default_factory=dict)
    novelty_mean: float = 0.0
    gain_mean: float = 0.0
    reward: float = 0.0
    migrated: str | None = None
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
            "gain_mean": self.gain_mean,
            "reward": self.reward,
            "migrated": self.migrated,
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
        self.focus: str | None = None       # ย่านที่กำลังขุดอยู่ (node id)
        self._last_migration = -MIGRATION_COOLDOWN
        self._thin_epochs = 0               # รอบติดกันที่ถามได้ไม่ครบโควตา
        self._proposed: list[Scored] = []    # รอบที่เปิดค้างไว้รอคำตอบจากภายนอก
        self._pending_record: EpochRecord | None = None

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
        # ย่านที่ให้คำถามไม่ครบโควตาติดกันหลายรอบ = ย่านนั้นถูกขุดหมดแล้วจริง
        # นี่เป็นสัญญาณ *เฉพาะที่* ซึ่งตรงกว่าความอิ่มตัวระดับทั้งระบบ
        self._thin_epochs = self._thin_epochs + 1 if len(chosen) < self.k else 0

        turns = [self._investigate_and_integrate(s) for s in chosen]
        return self._close_epoch(rec, chosen, turns)

    def _close_epoch(
        self, rec: EpochRecord, chosen: list[Scored], turns: list[Turn]
    ) -> EpochRecord:
        """บัญชีปิดรอบ — ใช้ร่วมกันทั้ง `step()` และ `propose()/absorb()`."""
        rec.turns = turns
        outcomes: dict[str, list[float]] = {}
        for t in turns:
            outcomes.setdefault(t.question.strategy, []).append(t.yield_score)

        rec.stats_after = self.graph.stats()
        gains = [t.gain.get("total", 0.0) for t in turns]
        rec.gain_mean = sum(gains) / len(gains) if gains else 0.0

        # คำถามหนีความอิ่มตัวมีเลขรอบอยู่ในตัว จึงใหม่ 100% เสมอโดยอัตโนมัติ
        # ถ้านับรวม ระบบจะรายงานว่าตัวเอง "สร้างสรรค์เต็มร้อย" ในรอบที่มันตันสนิท
        earned = [s.n for s in chosen if not s.question.forced]
        rec.novelty_mean = sum(earned) / len(earned) if earned else 0.0

        # รางวัลยึดกับ *ความประหลาดใจที่วัดได้จริง* เป็นหลัก
        # ส่วนตัวเลขระดับกราฟเหลือไว้เป็นสมอกันไม่ให้หลุดลอย
        rec.reward = 0.65 * rec.gain_mean + 0.35 * epoch_reward(
            rec.stats_before, rec.stats_after, rec.novelty_mean
        )

        # ---- ระบบมองตัวเอง ----
        self.self_model.observe_epoch(
            epoch=self.epoch,
            stats=rec.stats_after,
            selected_levels=[t.question.level for t in turns],
            selected_strategies=[t.question.strategy for t in turns],
            novelty_mean=rec.novelty_mean,
            gain_mean=rec.gain_mean,
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

        rec.migrated = self._maybe_migrate()

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
            focus_ids=self._focus_ids(),
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
            bonus=lambda q: self.population.explore_bonus(q.strategy),
        )

        # กฎข้อ 3: ตันแล้วให้ถามถึงความตัน
        #
        # "ตัน" หมายถึงถามอะไรใหม่ไม่ได้เลย ไม่ใช่ถามได้ไม่ครบโควตา การเติม
        # คำถามหนีความอิ่มตัวให้ครบ k ทุกครั้งที่ขาดแม้แต่ข้อเดียว ทำให้
        # คำถามประเภทนั้นครองรันไปกว่าครึ่ง — ถามคำถามดี ๆ ข้อเดียว
        # ดีกว่าถามคำถามดีข้อหนึ่งบวกคำถามหนีอีกสองข้อ
        saturated = not chosen
        if saturated:
            chosen.extend(self._saturation_questions(1, limits))

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
                # ต้องระบุ subject ไม่งั้นตัวสืบค้นจะเดาจากข้อความคำถาม แล้ว
                # เอาทั้งประโยคไปตั้งเป็นชื่อ node (อาการ label บวมย้อนกลับ)
                # แต่ต้อง *ไม่ใช่* node ของตัวระบบ: ลองผูกกับ SELF_NODE แล้ว
                # วัดได้ว่ากราฟยุบจาก 308 เหลือ 80 node และสัดส่วนคำถามที่พับ
                # กลับหาตัวเองพุ่งจาก 43% เป็น 65% — ก้นหอยยุบเข้าหาสะดือตัวเอง
                # "พื้นที่คำถาม" เป็นวัตถุที่ถามถึงได้ในตัวมันเอง และโตได้
                subject=QUESTION_SPACE,
            )
            out.append(Scored(q, u=1.0, c=0.6, n=1.0, total=1.0))
        return out

    def _investigate_and_integrate(self, scored: Scored) -> Turn:
        return self._integrate(scored, self._investigate(scored))

    def _investigate(self, scored: Scored) -> Finding:
        q = scored.question
        self._anchor(q)
        try:
            anchor_node = self.graph.add_node(
                canonical_label(q.subject),
                status=EpistemicStatus.UNKNOWN,
                level=q.level,
                tags=("self",) if q.subject == SELF_NODE else (),
                provenance=q.strategy,
                epoch=self.epoch,
            )
            finding = self.investigator.investigate(q, self.graph)
        except Exception as exc:  # noqa: BLE001 — เครื่องมือพังก็เป็นข้อมูล
            finding = Finding(
                answer=f"การสืบค้นล้มเหลว: {type(exc).__name__}",
                confidence=0.0,
                residual=f"เครื่องมือสืบค้นล้มเหลวกับคำถามระดับ{q.level.th}",
                source="failure",
            )
        return ensure_residual(finding, q, self.rng)

    def _integrate(self, scored: Scored, finding: Finding) -> Turn:
        """ผนวกคำตอบเข้ากราฟ — ไม่สนใจว่าคำตอบมาจากไหน.

        แยกออกมาเพื่อให้คำตอบที่มาจากภายนอก (มนุษย์, เซสชัน LLM อื่น,
        การทดลองจริง) เดินผ่านเส้นทางเดียวกันกับคำตอบของตัวสืบค้นในตัว
        รวมถึงกฎเหล็กข้อ 1 และการวัดความประหลาดใจ.
        """
        q = scored.question
        finding = ensure_residual(finding, q, self.rng)
        self.budget.spent_cost += finding.cost

        self._anchor(q)
        before_region = gainlib.snapshot(self.graph, q.targets)
        known_residuals = gainlib.all_residuals(self.graph)
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
        g = gainlib.measure(
            before_region, self.graph, q.targets, residual_label, known_residuals
        )
        # ความใหม่เชิงคำยังมีที่ยืน แต่เป็นส่วนน้อย — สิ่งที่ตัดสินคือ
        # คำถามนี้เปลี่ยนแบบจำลองไปได้จริงแค่ไหน
        yield_score = max(0.0, min(1.0, 0.8 * g.total + 0.2 * scored.n))
        return Turn(
            question=q,
            answer=finding.answer,
            confidence=finding.confidence,
            residual=residual_label,
            nodes_added=nodes_added,
            contradictions=contradictions,
            yield_score=yield_score,
            gain=g.to_dict(),
        )

    def _anchor(self, q: Question) -> None:
        """คำถามที่ยังไม่มีเป้าหมายในกราฟต้องได้ node ของตัวเองก่อน
        มิฉะนั้นคำตอบและเศษที่เหลือจะลอยหลุดออกจากกราฟ."""
        if q.targets or not q.subject:
            return
        anchor = self.graph.add_node(
            canonical_label(q.subject),
            status=EpistemicStatus.UNKNOWN,
            level=q.level,
            tags=("self",) if q.subject == SELF_NODE else (),
            provenance=q.strategy,
            epoch=self.epoch,
        )
        q.targets = (anchor.id,)

    # ------------------------------------------------------------ ตัวสืบค้นภายนอก

    def propose(self) -> list[Scored]:
        """เลือกคำถามของรอบนี้ แต่ยัง *ไม่* ไปหาคำตอบ.

        ใช้คู่กับ `absorb()` เมื่อผู้ตอบอยู่นอกโปรเซสนี้ — มนุษย์, เซสชัน
        LLM อื่น, หรือการทดลองจริง.
        """
        self._pending_record = EpochRecord(epoch=self.epoch)
        self._pending_record.stats_before = self.graph.stats()
        limits = self.self_model.limits(self.epoch, self.budget)
        self._pending_record.limits = limits
        chosen, self._pending_record.saturated = self._choose(limits)
        self._thin_epochs = self._thin_epochs + 1 if len(chosen) < self.k else 0
        for s in chosen:
            self._anchor(s.question)
        self._proposed = chosen
        return chosen

    def absorb(self, findings: dict[str, Finding]) -> EpochRecord:
        """รับคำตอบจากภายนอกเข้ามาปิดรอบที่ `propose()` เปิดค้างไว้.

        คำถามที่ไม่มีคำตอบส่งกลับมาจะตกไปให้ตัวสืบค้นในตัวจัดการ ก้นหอย
        จึงไม่หยุดหมุนเพราะมีใครตอบไม่ครบ.
        """
        if not self._proposed:
            raise RuntimeError("ต้องเรียก propose() ก่อน absorb()")
        rec = self._pending_record or EpochRecord(epoch=self.epoch)
        chosen = self._proposed
        self._proposed = []
        self._pending_record = None
        turns = []
        for s in chosen:
            f = findings.get(s.question.id)
            turns.append(self._integrate(s, f) if f else self._investigate_and_integrate(s))
        return self._close_epoch(rec, chosen, turns)

    def _focus_ids(self) -> frozenset[str]:
        if self.focus is None or self.focus not in self.graph.nodes:
            return frozenset()
        return frozenset(self.graph.neighbors(self.focus, 2) | {self.focus})

    def _maybe_migrate(self) -> str | None:
        """ย่านตันแล้วให้ย้ายไปย่านใหม่ที่ตัวระบบเองชี้ว่ามีของมากที่สุด.

        ก้นหอยที่สุ่มทั่วกราฟอย่างสม่ำเสมอจะสำรวจได้กว้างแต่ตื้น การขุดลึก
        ในย่านเดียวจนตันแล้วค่อยอพยพ ให้ทั้งความลึกและความกว้าง — และตัว
        "ตันแล้ว" ไม่ได้ถูกกำหนดโดยตารางเวลา แต่มาจากที่ SelfModel ตรวจพบ
        ความอิ่มตัว/การหยุดนิ่งของตัวเองติดต่อกัน.
        """
        near = self._focus_ids()
        if self.focus is not None:
            # เงื่อนไขสามข้อต้องครบ ไม่งั้นการ "อพยพ" จะกลายเป็นการกระตุก
            # ย้ายทุกรอบ — ซึ่งให้ผลแย่กว่าการสุ่มทั่วกราฟเสียอีก เพราะ
            # ก้นหอยไม่เคยอยู่ที่ไหนนานพอจะขุดถึงก้น
            exhausted_here = self._thin_epochs >= 3
            if (
                not exhausted_here
                and self.epoch - self._last_migration < MIGRATION_COOLDOWN
            ):
                return None
            worked = sum(
                self.graph.nodes[i].visits for i in near if i in self.graph.nodes
            )
            if worked < MIGRATION_MIN_WORK:
                return None
            if not exhausted_here:
                stuck = [
                    l
                    for l in self.self_model.detect(self.epoch, self.budget)
                    if l.kind in ("saturation", "stagnation", "exhaustion")
                    and l.epochs_persisted >= 2
                ]
                if not stuck:
                    return None

        pool = [n for n in self.graph.nodes.values() if n.id not in near]
        if not pool:
            return None
        best = max(
            pool,
            key=lambda n: (
                n.uncertainty * (1.0 + 0.4 * len(n.residuals))
                + (0.25 if n.visits == 0 else 0.0)
            ),
        )
        if best.id == self.focus:
            return None
        first = self.focus is None
        self.focus = best.id
        self._last_migration = self.epoch
        self._thin_epochs = 0
        return None if first else best.label   # ครั้งแรกคือการตั้งหลัก ไม่ใช่การอพยพ

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
                subject=SELF_NODE,
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
            lines.append(
                f"── รอบ {rec.epoch} ─ reward {rec.reward:+.3f} "
                f"· ความประหลาดใจ {rec.gain_mean:.3f}"
                + (" [อิ่มตัว→ถามถึงความอิ่มตัว]" if rec.saturated else "")
            )
            if rec.migrated:
                lines.append(f"  ⇢ อพยพย่าน: {rec.migrated}")
            for t in rec.turns:
                lines.append(f"  [{t.question.level.th}] {t.question.text}")
                lines.append(f"    → {t.answer}")
                lines.append(
                    f"    ↯ เศษที่เหลือ: {t.residual}"
                    f"   (แก้ความเชื่อเดิม {t.gain.get('revision', 0):.2f}"
                    f" · เศษใหม่จริง {t.gain.get('freshness', 0):.2f})"
                )
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
            "focus": self.focus,
            "proposed": [
                {"question": s.question.to_dict(), "u": s.u, "c": s.c, "n": s.n, "total": s.total}
                for s in self._proposed
            ],
            "pending_stats": (
                self._pending_record.stats_before if self._pending_record else None
            ),
            "pending_limits": (
                self._pending_record.limits if self._pending_record else None
            ),
            "last_migration": self._last_migration,
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
        sp.focus = d.get("focus")
        sp._last_migration = d.get("last_migration", -MIGRATION_COOLDOWN)
        sp._proposed = [
            Scored(
                Question.from_dict(x["question"]),
                u=x["u"], c=x["c"], n=x["n"], total=x["total"],
            )
            for x in d.get("proposed", ())
        ]
        if sp._proposed:
            rec = EpochRecord(epoch=sp.epoch)
            rec.stats_before = d.get("pending_stats") or sp.graph.stats()
            rec.limits = list(d.get("pending_limits") or ())
            sp._pending_record = rec
        return sp
