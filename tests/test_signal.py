"""โดเมนที่ไม่มีภาษา — คำถามถูกประมวลผลเป็นการวัด และเศษคือของจริง."""

import random
import unittest

from spice.evolution import Population
from spice.probe import Ref, probe
from spice.question import Question
from spice.signal import SignalDomain, SignalInvestigator, layered_signal
from spice.spiral import Spiral
from spice.strategies import grammar_strategies
from spice.types import EpistemicStatus, QuestionLevel


def periodic(pattern: list[int], n: int = 300) -> list[int]:
    return [pattern[i % len(pattern)] for i in range(n)]


class TestMeasurement(unittest.TestCase):
    def setUp(self):
        self.d = SignalDomain(layered_signal(), random.Random(2))

    def test_it_finds_the_period_that_was_actually_hidden_there(self):
        d = SignalDomain(periodic([0, 1, 1, 2, 0, 3, 2, 1, 3]), random.Random(1))
        m = d.mechanism(d.root)
        self.assertEqual(m.value["period"], 9)
        self.assertEqual(m.value["accuracy"], 1.0)
        self.assertEqual(m.residual_idx, ())

    def test_it_prefers_the_shortest_description_over_a_longer_equal_one(self):
        """[0,1,2] ซ้ำสามรอบ อธิบายด้วยคาบ 3 หรือคาบ 9 ก็ทายถูกหมด
        แต่คาบ 3 สั้นกว่า — เกณฑ์ MDL ต้องเลือกอันนั้น."""
        d = SignalDomain(periodic([0, 1, 2] * 3), random.Random(1))
        m = d.mechanism(d.root)
        self.assertEqual(m.value["period"], 3)
        self.assertEqual(m.value["accuracy"], 1.0)

    def test_it_finds_the_layered_signal_base_period(self):
        m = self.d.mechanism(self.d.root)
        self.assertEqual(m.value["period"], 7)          # ชั้นแรกที่ซ่อนไว้จริง
        self.assertGreater(m.value["accuracy"], 0.75)

    def test_it_finds_the_regime_change_where_it_really_is(self):
        m = self.d.bound(self.d.root)
        # ระบอบเปลี่ยนจริงที่ 0.62 ของความยาว
        self.assertAlmostEqual(m.value["changepoint"] / len(self.d.seq), 0.62, delta=0.06)

    def test_the_residual_is_a_set_of_positions_not_a_phrase(self):
        m = self.d.mechanism(self.d.root)
        self.assertTrue(m.residual_idx)
        self.assertTrue(all(isinstance(i, int) for i in m.residual_idx))
        self.assertEqual(
            len(m.explained) + len(m.residual_idx), len(self.d.root)
        )

    def test_a_residual_becomes_an_object_with_a_name_the_system_coined(self):
        m = self.d.mechanism(self.d.root)
        sel = self.d.add(m.residual_idx, "test")
        self.assertIsNotNone(sel)
        self.assertTrue(sel.name.startswith("⟦"))
        self.assertNotEqual(sel.name, self.d.root.name)
        # และถามต่อกับมันได้ทันที
        self.assertIn("period", self.d.mechanism(sel).value)

    def test_coined_names_are_unique(self):
        names = {self.d.coin() for _ in range(120)}
        self.assertEqual(len(names), 120)

    def test_criteria_can_be_shown_to_disagree(self):
        m = self.d.reflect(self.d.root)
        self.assertIn("most_accurate_period", m.value)
        self.assertIn("shortest_period", m.value)
        self.assertIsInstance(m.value["criteria_disagree"], bool)

    def test_decompose_finds_a_repeated_block(self):
        m = self.d.decompose(self.d.root)
        self.assertGreater(m.value["occurrences"], 3)
        self.assertGreater(m.value["coverage"], 0.1)

    def test_tiny_selections_are_not_named(self):
        self.assertIsNone(self.d.add([1, 2], "too-small"))


class TestInvestigator(unittest.TestCase):
    def setUp(self):
        self.d = SignalDomain(layered_signal(), random.Random(2))
        self.inv = SignalInvestigator(self.d)
        self.sp = Spiral(investigator=self.inv, seed=4)
        self.sp.graph.add_node(
            self.d.root.name, status=EpistemicStatus.UNKNOWN, tags=("signal", "root")
        )

    def _ask(self, tree):
        node = self.sp.graph.by_label(self.d.root.name)
        return Question(
            text=tree.render("th"), level=tree.level, strategy="t",
            targets=(node.id,), tree=tree,
        )

    def test_a_probe_is_answered_by_measuring(self):
        f = self.inv.investigate(
            self._ask(probe("mechanism", Ref("x"))), self.sp.graph
        )
        self.assertIn("คาบ 7", f.answer)
        self.assertTrue(f.residual)
        self.assertTrue(f.new_nodes)

    def test_the_residual_it_returns_is_an_object_in_the_domain(self):
        f = self.inv.investigate(
            self._ask(probe("mechanism", Ref("x"))), self.sp.graph
        )
        self.assertIsNotNone(self.d.get(f.residual))

    def test_every_base_op_is_answerable(self):
        for op in ("identify", "decompose", "extent", "bound", "mechanism",
                   "invariant", "presuppose", "negate"):
            with self.subTest(op=op):
                f = self.inv.investigate(self._ask(probe(op, Ref("x"))), self.sp.graph)
                self.assertTrue(f.answer.strip())
                self.assertTrue(f.residual.strip())

    def test_a_minted_operator_dispatches_on_its_inner_op(self):
        f = self.inv.investigate(
            self._ask(probe("reflect", probe("mechanism", Ref("x")))), self.sp.graph
        )
        self.assertTrue(f.answer.strip())

    def test_the_spiral_runs_over_a_domain_with_no_vocabulary(self):
        pop = Population(grammar_strategies(), rng=random.Random(9), max_size=14)
        sp = Spiral(
            population=pop, investigator=self.inv, seed=4, questions_per_epoch=3
        )
        sp.graph.add_node(self.d.root.name, status=EpistemicStatus.UNKNOWN, tags=("signal",))
        for _ in range(30):
            sp.step()
        asked = [t.question.signature for r in sp.history for t in r.turns]
        self.assertEqual(len(asked), len(set(asked)))
        for r in sp.history:
            for t in r.turns:
                self.assertTrue(t.residual.strip())
        self.assertGreater(len(sp.grammar.shapes_seen), 20)
        self.assertGreater(len(self.d.selections), 5)

    def test_the_grammar_grows_while_working_a_wordless_domain(self):
        pop = Population(grammar_strategies(), rng=random.Random(9), max_size=16)
        sp = Spiral(
            population=pop, investigator=self.inv, seed=4, questions_per_epoch=3
        )
        sp.graph.add_node(self.d.root.name, status=EpistemicStatus.UNKNOWN, tags=("signal",))
        for _ in range(60):
            sp.step()
        self.assertGreater(sp.grammar.stats()["minted"], 0)
        for m in sp.grammar.minted.values():
            self.assertTrue(m.coined)


if __name__ == "__main__":
    unittest.main()
