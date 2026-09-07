import unittest

from spice.selfmodel import Budget, SelfModel
from spice.types import QuestionLevel


def feed(sm, epochs, *, levels=None, strategies=None, novelty=0.9, residuals=(), stats=None):
    for e in range(epochs):
        sm.observe_epoch(
            epoch=e,
            stats=stats or {"mean_uncertainty": 0.8 - e * 0.05, "nodes": 10 + e, "contradictions": 0},
            selected_levels=levels or [QuestionLevel.OBJECT],
            selected_strategies=strategies or ["object_probe"],
            novelty_mean=novelty,
            open_residuals=list(residuals),
            instrument_failures=[],
        )


class TestSelfModel(unittest.TestCase):
    def test_monoculture_is_detected(self):
        sm = SelfModel()
        feed(sm, 10, strategies=["object_probe"] * 3)
        self.assertTrue(any(l.kind == "monoculture" for l in sm.detect(10)))

    def test_a_balanced_diet_of_strategies_is_not_flagged(self):
        sm = SelfModel()
        for e in range(10):
            sm.observe_epoch(
                epoch=e,
                stats={"mean_uncertainty": 0.8 - e * 0.05, "nodes": 10 + e, "contradictions": 0},
                selected_levels=list(QuestionLevel),
                selected_strategies=["a", "b", "c", "d"],
                novelty_mean=0.9,
                open_residuals=[],
                instrument_failures=[],
            )
        self.assertFalse(any(l.kind == "monoculture" for l in sm.detect(10)))

    def test_frozen_uncertainty_reads_as_stagnation(self):
        sm = SelfModel()
        feed(sm, 5, stats={"mean_uncertainty": 0.7, "nodes": 10, "contradictions": 0})
        self.assertTrue(any(l.kind == "stagnation" for l in sm.detect(5)))

    def test_collapsing_novelty_reads_as_saturation(self):
        sm = SelfModel()
        feed(sm, 5, novelty=0.1)
        self.assertTrue(any(l.kind == "saturation" for l in sm.detect(5)))

    def test_a_residual_that_survives_becomes_a_limit(self):
        sm = SelfModel()
        feed(sm, 4, residuals=["เศษที่ไม่ยอมหาย"])
        limits = [l for l in sm.detect(4) if l.kind == "recurrence"]
        self.assertTrue(limits)
        self.assertIn("เศษที่ไม่ยอมหาย", limits[0].text)

    def test_a_resolved_residual_stops_counting(self):
        sm = SelfModel()
        feed(sm, 4, residuals=["เศษ"])
        feed(sm, 1, residuals=[])
        self.assertEqual(sm.residual_age, {})

    def test_gaps_require_a_limit_to_persist(self):
        sm = SelfModel()
        feed(sm, 4, novelty=0.1)
        first = sm.gaps(4)          # รอบแรกที่ตรวจพบ — ยังไม่ให้กำเนิดเครื่องมือ
        second = sm.gaps(5)         # ยังอยู่ในรอบถัดมา — คราวนี้ถึงจะนับ
        self.assertEqual(first, [])
        self.assertTrue(second)

    def test_budget_warns_before_it_stops(self):
        b = Budget(max_nodes=100)
        b.nodes = 50
        self.assertEqual(b.pressure(0), [])
        b.nodes = 80
        self.assertTrue(any(l.kind == "resource" for l in b.pressure(0)))
        self.assertIsNone(b.exhausted(0))
        b.nodes = 100
        self.assertEqual(b.exhausted(0), "เพดานขนาดกราฟ")

    def test_roundtrip(self):
        sm = SelfModel()
        feed(sm, 6, residuals=["เศษ"])
        sm.detect(6)
        clone = SelfModel.from_dict(sm.to_dict())
        self.assertEqual(clone.residual_age, sm.residual_age)
        self.assertEqual(clone.strategy_uses, sm.strategy_uses)
        self.assertEqual(len(clone.limits_seen), len(sm.limits_seen))


if __name__ == "__main__":
    unittest.main()
