import unittest

from spice.graph import KnowledgeGraph
from spice.question import Question, QuestionLedger
from spice.scoring import Weights, epoch_reward, score_question, select
from spice.types import EpistemicStatus, QuestionLevel, Relation


class TestScoring(unittest.TestCase):
    def setUp(self):
        self.g = KnowledgeGraph()
        self.known = self.g.add_node(
            "รู้แล้ว", status=EpistemicStatus.KNOWN, confidence=0.95
        )
        self.unknown = self.g.add_node("ยังไม่รู้", status=EpistemicStatus.UNKNOWN)
        self.led = QuestionLedger()

    def _q(self, text, node, level=QuestionLevel.OBJECT):
        return Question(text=text, level=level, strategy="t", targets=(node.id,))

    def test_uncertainty_term_tracks_the_target(self):
        hot = score_question(self._q("ก", self.unknown), self.g, self.led, Weights())
        cold = score_question(self._q("ข", self.known), self.g, self.led, Weights())
        self.assertGreater(hot.u, cold.u)

    def test_self_referential_questions_carry_contradiction_pressure(self):
        low = score_question(
            self._q("ก", self.known, QuestionLevel.OBJECT), self.g, self.led, Weights()
        )
        high = score_question(
            self._q("ข", self.known, QuestionLevel.SELF_REFERENCE),
            self.g,
            self.led,
            Weights(),
        )
        self.assertGreater(high.c, low.c)

    def test_weights_normalize_to_one(self):
        w = Weights(2.0, 1.0, 1.0).normalized()
        self.assertAlmostEqual(w.u + w.c + w.n, 1.0)

    def test_select_rejects_already_asked_questions(self):
        asked = self._q("ถามไปแล้ว", self.unknown)
        self.led.record(asked)
        chosen = select([asked], self.g, self.led, Weights(), k=3)
        self.assertEqual(chosen, [])

    def test_select_drops_near_duplicates_within_one_epoch(self):
        a = self._q("ยังไม่รู้ เกิดขึ้นได้อย่างไร?", self.unknown)
        b = self._q("ยังไม่รู้ เกิดขึ้นได้อย่างไรกัน?", self.unknown)
        chosen = select([a, b], self.g, self.led, Weights(), k=3)
        self.assertEqual(len(chosen), 1)

    def test_select_honours_k(self):
        qs = [self._q(f"คำถามที่แตกต่างกันมากข้อที่ {i} " + "x" * i, self.unknown) for i in range(9)]
        self.assertLessEqual(len(select(qs, self.g, self.led, Weights(), k=3)), 3)

    def test_forced_questions_survive_the_novelty_floor(self):
        self.led.record(self._q("เกือบเหมือนกันเป๊ะทุกตัวอักษร", self.unknown))
        near = self._q("เกือบเหมือนกันเป๊ะทุกตัวอักษรจริง", self.unknown)
        near.forced = True
        self.assertEqual(len(select([near], self.g, self.led, Weights(), k=1)), 1)

    def test_reward_rises_when_contradictions_surface(self):
        before = {"nodes": 10, "mean_uncertainty": 0.5, "contradictions": 0, "unexplained": 3}
        quiet = dict(before, nodes=11)
        loud = dict(before, nodes=11, contradictions=2)
        self.assertGreater(
            epoch_reward(before, loud, 0.5), epoch_reward(before, quiet, 0.5)
        )

    def test_reward_rises_when_uncertainty_falls(self):
        before = {"nodes": 10, "mean_uncertainty": 0.8, "contradictions": 0, "unexplained": 3}
        after = dict(before, mean_uncertainty=0.6)
        self.assertGreater(epoch_reward(before, after, 0.5), epoch_reward(before, before, 0.5))


if __name__ == "__main__":
    unittest.main()
