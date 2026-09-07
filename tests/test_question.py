import unittest

from spice.question import Question, QuestionLedger, jaccard, shingles
from spice.types import QuestionLevel


def q(text, level=QuestionLevel.OBJECT):
    return Question(text=text, level=level, strategy="t")


class TestNovelty(unittest.TestCase):
    def test_thai_shingles_work_without_whitespace(self):
        # ภาษาไทยไม่เว้นวรรคระหว่างคำ — word shingle จะให้ชุดว่างเปล่า
        sh = shingles("ก้นหอยเกิดขึ้นได้อย่างไร")
        self.assertGreater(len(sh), 5)

    def test_exact_repeat_has_zero_novelty(self):
        led = QuestionLedger()
        led.record(q("ก้นหอยเกิดขึ้นได้อย่างไร?"))
        self.assertEqual(led.novelty("ก้นหอยเกิดขึ้นได้อย่างไร?"), 0.0)

    def test_near_duplicate_scores_far_below_a_fresh_question(self):
        led = QuestionLedger()
        led.record(q("ก้นหอยเกิดขึ้นได้อย่างไร?"))
        near = led.novelty("ก้นหอยเกิดขึ้นได้อย่างไรกัน?")
        far = led.novelty("ระบบนี้มองไม่เห็นอะไรเพราะวิธีถามของมันเอง?")
        self.assertLess(near, 0.5)
        self.assertGreater(far, 0.9)

    def test_first_question_is_maximally_novel(self):
        self.assertEqual(QuestionLedger().novelty("อะไรก็ได้"), 1.0)

    def test_level_rarity_favours_unused_levels(self):
        led = QuestionLedger()
        for _ in range(10):
            led.record(q(f"ถามวัตถุครั้งที่ {_}", QuestionLevel.OBJECT))
        self.assertLess(
            led.level_rarity(QuestionLevel.OBJECT),
            led.level_rarity(QuestionLevel.SELF_REFERENCE),
        )

    def test_ledger_respects_capacity(self):
        led = QuestionLedger(capacity=5)
        for i in range(20):
            led.record(q(f"คำถามที่ {i}"))
        self.assertEqual(len(led), 5)

    def test_roundtrip_keeps_seen_signatures(self):
        led = QuestionLedger()
        led.record(q("จำฉันไว้"))
        clone = QuestionLedger.from_dict(led.to_dict())
        self.assertTrue(clone.seen("จำฉันไว้"))

    def test_jaccard_bounds(self):
        a = shingles("abcdefgh")
        self.assertEqual(jaccard(a, a), 1.0)
        self.assertEqual(jaccard(a, shingles("")), 0.0)


if __name__ == "__main__":
    unittest.main()
