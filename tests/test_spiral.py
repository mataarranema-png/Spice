"""เทสต์ของกฎเหล็ก — ถ้าข้อไหนพัง ระบบก็ไม่ใช่ก้นหอยอีกต่อไป."""

import random
import unittest

from spice.investigator import MAX_LABEL, ReflectiveInvestigator
from spice.question import Question
from spice.selfmodel import Budget
from spice.spiral import Spiral
from spice.types import Finding, QuestionLevel


def spiral(seed=0, **kw):
    return Spiral.from_topic("ก้นหอย", seed=seed, **kw)


class TestSpiralInvariants(unittest.TestCase):
    def test_no_question_is_ever_asked_twice(self):
        sp = spiral(seed=1)
        sp.run(30)
        asked = [t.question.signature for r in sp.history for t in r.turns]
        self.assertEqual(len(asked), len(set(asked)))

    def test_every_answer_leaves_a_residual(self):
        sp = spiral(seed=2)
        sp.run(15)
        turns = [t for r in sp.history for t in r.turns]
        self.assertTrue(turns)
        for t in turns:
            self.assertTrue(t.residual.strip(), f"คำตอบไม่มีเศษเหลือ: {t.question.text}")

    def test_an_investigator_that_answers_completely_still_gets_a_residual(self):
        class Complacent:
            name = "complacent"

            def investigate(self, q, graph):
                return Finding(answer="อธิบายได้ครบถ้วนสมบูรณ์", confidence=1.0, residual="")

        sp = Spiral.from_topic("ก้นหอย", seed=3, investigator=Complacent())
        sp.run(4)
        for r in sp.history:
            for t in r.turns:
                self.assertTrue(t.residual.strip())

    def test_the_spiral_never_stops_producing_questions(self):
        sp = spiral(seed=4)
        for _ in range(25):
            rec = sp.step()
            self.assertTrue(rec.turns, f"รอบ {rec.epoch} ไม่ผลิตคำถามเลย")

    def test_saturation_escalates_to_a_self_referential_question(self):
        sp = spiral(seed=5)
        sp.ledger.novelty = lambda q: 0.0        # ทำให้ทุกคำถามดู "เคยถามแล้ว"
        rec = sp.step()
        self.assertTrue(rec.saturated)
        self.assertTrue(rec.turns)
        for t in rec.turns:
            self.assertIs(t.question.level, QuestionLevel.SELF_REFERENCE)

    def test_labels_stay_bounded(self):
        sp = spiral(seed=6)
        sp.run(25)
        longest = max(len(n.label) for n in sp.graph)
        self.assertLessEqual(longest, MAX_LABEL + 1)

    def test_the_graph_grows_and_climbs_the_question_levels(self):
        sp = spiral(seed=7)
        sp.run(12)
        self.assertGreater(len(sp.graph), 5)
        levels = {t.question.level for r in sp.history for t in r.turns}
        self.assertGreater(len(levels), 2)

    def test_the_system_builds_a_model_of_itself(self):
        sp = spiral(seed=8)
        sp.run(15)
        self.assertIsNotNone(sp.graph.by_label("ระบบผู้ถามเอง"))

    def test_same_seed_gives_the_same_spiral(self):
        a, b = spiral(seed=9), spiral(seed=9)
        a.run(5)
        b.run(5)
        self.assertEqual(
            [t.question.text for r in a.history for t in r.turns],
            [t.question.text for r in b.history for t in r.turns],
        )

    def test_a_human_question_is_asked_next_epoch(self):
        sp = spiral(seed=10)
        sp.ask("อะไรทำให้เราเรียกสิ่งนั้นว่ากลไก?", QuestionLevel.ONTOLOGY)
        rec = sp.step()
        self.assertIn(
            "อะไรทำให้เราเรียกสิ่งนั้นว่ากลไก?", [t.question.text for t in rec.turns]
        )

    def test_hitting_the_ceiling_is_recorded_as_a_discovered_boundary(self):
        sp = Spiral.from_topic("ก้นหอย", seed=11, budget=Budget(max_epochs=3))
        sp.run(20)
        self.assertEqual(sp.epoch, 3)
        boundaries = [n for n in sp.graph if "boundary" in n.tags]
        self.assertTrue(boundaries)
        self.assertTrue(sp.pending)  # ขอบเขตกลายเป็นคำถามข้อถัดไป ไม่ใช่จุดจบ

    def test_a_broken_instrument_does_not_stop_the_spiral(self):
        class Broken:
            name = "broken"

            def investigate(self, q, graph):
                raise RuntimeError("เครื่องมือพัง")

        sp = Spiral.from_topic("ก้นหอย", seed=12, investigator=Broken())
        rec = sp.step()
        self.assertTrue(rec.turns)
        for t in rec.turns:
            self.assertIn("ล้มเหลว", t.answer)
            self.assertTrue(t.residual)

    def test_population_and_weights_actually_change(self):
        sp = spiral(seed=13)
        before_names = {s.name for s in sp.population.live()}
        before_w = sp.population.weights.normalized()
        sp.run(12)
        after_names = {s.name for s in sp.population.live()}
        self.assertNotEqual(before_names, after_names)
        after_w = sp.population.weights.normalized()
        self.assertNotAlmostEqual(before_w.u, after_w.u, places=4)

    def test_roundtrip_resumes_where_it_left_off(self):
        sp = spiral(seed=14)
        sp.run(6)
        clone = Spiral.from_dict(sp.to_dict(), seed=14)
        self.assertEqual(clone.epoch, sp.epoch)
        self.assertEqual(len(clone.graph), len(sp.graph))
        self.assertEqual(
            sorted(s.name for s in clone.population.live()),
            sorted(s.name for s in sp.population.live()),
        )
        clone.run(3)
        asked = [t.question.signature for r in clone.history for t in r.turns]
        self.assertEqual(len(asked), len(set(asked)))

    def test_migration_does_not_thrash(self):
        sp = spiral(seed=20)
        sp.run(60)
        migrations = sum(1 for r in sp.history if r.migrated)
        # เคยยิงทุกรอบ (102/150) ซึ่งแย่กว่าการสุ่มทั่วกราฟ
        self.assertLess(migrations, 30)
        self.assertGreater(migrations, 0)

    def test_the_spiral_settles_on_a_neighbourhood_to_dig(self):
        sp = spiral(seed=21)
        sp.run(6)
        self.assertIsNotNone(sp.focus)
        self.assertIn(sp.focus, sp.graph.nodes)

    def test_evolution_is_credited_by_measured_surprise(self):
        sp = spiral(seed=22)
        sp.run(10)
        for r in sp.history:
            for t in r.turns:
                self.assertIn("total", t.gain)
                self.assertGreaterEqual(t.gain["total"], 0.0)
                self.assertLessEqual(t.gain["total"], 1.0)

    def test_a_run_that_stops_surprising_says_so_about_its_instrument(self):
        class Repetitive:
            name = "repetitive"

            def investigate(self, q, graph):
                from spice.types import Finding

                return Finding(answer="เหมือนเดิมทุกครั้ง", confidence=0.5,
                               residual="เศษเดิมที่ไม่เคยเปลี่ยน")

        sp = Spiral.from_topic("ก้นหอย", seed=23, investigator=Repetitive())
        sp.run(12)
        kinds = {l.kind for l in sp.self_model.detect(sp.epoch, sp.budget)}
        self.assertIn("exhaustion", kinds)

    def test_report_renders(self):
        sp = spiral(seed=15)
        sp.run(3)
        text = sp.report(last=2)
        self.assertIn("ก้นหอยรอบที่", text)
        self.assertIn("เศษที่เหลือ", text)


if __name__ == "__main__":
    unittest.main()
