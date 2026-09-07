import random
import unittest

from spice.graph import KnowledgeGraph
from spice.question import QuestionLedger
from spice.strategies import (
    SOURCES,
    GenerationContext,
    Strategy,
    builtin_strategies,
    cross_strategies,
    mutate_strategy,
    strategy_from_gap,
)
from spice.types import EpistemicStatus, QuestionLevel, Relation


def ctx(limits=("หน่วยความจำจำกัด",), seed=0):
    g = KnowledgeGraph()
    g.add_node("ก้นหอย")
    g.add_node("เกลียว", status=EpistemicStatus.UNCERTAIN, level=QuestionLevel.OBJECT)
    g.add_node("คู่ขัดแย้ง")
    g.add_edge("เกลียว", "คู่ขัดแย้ง", Relation.CONTRADICTS)
    g.by_label("ก้นหอย").residuals.append("ทำไมอัตราส่วนจึงคงที่")
    # คำอธิบายสองอันที่แข่งกันอธิบายสิ่งเดียวกัน — วัตถุดิบของ source "comparison"
    g.add_node("การเติบโตแบบโนมอน", confidence=0.7)
    g.add_node("การจัดเรียงแบบฟีโบนักชี", confidence=0.4)
    g.add_edge("การเติบโตแบบโนมอน", "ก้นหอย", Relation.EXPLAINS)
    g.add_edge("การจัดเรียงแบบฟีโบนักชี", "ก้นหอย", Relation.CAUSES)
    from spice.grammar import Grammar

    return GenerationContext(
        g, QuestionLedger(), 0, random.Random(seed),
        grammar=Grammar(random.Random(seed)), limits=list(limits),
    )


class TestStrategies(unittest.TestCase):
    def test_builtins_cover_every_question_level(self):
        levels = {s.level for s in builtin_strategies()}
        self.assertEqual(levels, set(QuestionLevel))

    def test_every_builtin_produces_rendered_questions(self):
        c = ctx()
        for s in builtin_strategies():
            with self.subTest(strategy=s.name):
                out = s.generate(c)
                self.assertTrue(out, f"{s.name} ไม่ผลิตคำถามเลย")
                for q in out:
                    self.assertNotIn("{", q.text)
                    self.assertTrue(q.text.strip())

    def test_generated_questions_carry_their_subject(self):
        c = ctx()
        for s in builtin_strategies():
            for q in s.generate(c):
                self.assertTrue(q.subject, f"{s.name} ไม่ได้ระบุ subject")

    def test_mutation_stays_renderable_after_changing_source(self):
        rng = random.Random(4)
        c = ctx()
        parent = builtin_strategies()[0]
        for _ in range(40):
            child = mutate_strategy(parent, rng, 1)
            self.assertIn(child.source, SOURCES)
            for q in child.generate(c):
                self.assertNotIn("{", q.text)

    def test_crossover_asks_above_both_parents(self):
        rng = random.Random(2)
        a, b = builtin_strategies()[0], builtin_strategies()[6]
        child = cross_strategies(a, b, rng, 1)
        self.assertGreater(int(child.level), max(int(a.level), int(b.level)) - 1)
        self.assertEqual(child.lineage, (a.name, b.name))
        self.assertTrue(child.generate(ctx()))

    def test_gap_strategy_identity_is_the_gap_not_the_epoch(self):
        gap = "แทบไม่เคยตั้งคำถามระดับภววิทยาเลย"
        early = strategy_from_gap(gap, QuestionLevel.ONTOLOGY, 3)
        late = strategy_from_gap(gap, QuestionLevel.ONTOLOGY, 99)
        self.assertEqual(early.name, late.name)
        other = strategy_from_gap("จุดบอดอื่น", QuestionLevel.META, 3)
        self.assertNotEqual(early.name, other.name)

    def test_gap_strategy_renders_for_each_source(self):
        c = ctx()
        for source in SOURCES:
            s = strategy_from_gap("จุดบอดสมมติ", QuestionLevel.META, 1, source)
            with self.subTest(source=source):
                for q in s.generate(c):
                    self.assertNotIn("{", q.text)

    def test_roundtrip(self):
        s = builtin_strategies()[0]
        self.assertEqual(Strategy.from_dict(s.to_dict()).to_dict(), s.to_dict())

    def test_self_source_yields_nothing_without_detected_limits(self):
        c = ctx(limits=())
        selfish = [s for s in builtin_strategies() if s.source == "self"][0]
        self.assertEqual(selfish.generate(c), [])


if __name__ == "__main__":
    unittest.main()
