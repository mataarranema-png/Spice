"""ความประหลาดใจ — สัญญาณที่ควรขับวิวัฒนาการ แทนการนับจำนวน node."""

import unittest

from spice.gain import all_residuals, measure, residual_freshness, snapshot
from spice.graph import KnowledgeGraph
from spice.types import EpistemicStatus, QuestionLevel, Relation


class TestResidualFreshness(unittest.TestCase):
    def test_an_unheard_residual_is_fully_fresh(self):
        self.assertGreater(residual_freshness("ทำไมอัตราส่วนจึงคงที่", ["โครงสร้างของก้นหอย"]), 0.9)

    def test_repeating_a_known_residual_scores_zero(self):
        self.assertEqual(residual_freshness("โครงสร้างของก้นหอย", ["โครงสร้างของก้นหอย"]), 0.0)

    def test_rewording_a_known_residual_scores_low(self):
        score = residual_freshness("โครงสร้างของก้นหอยนั้น", ["โครงสร้างของก้นหอย"])
        self.assertLess(score, 0.4)

    def test_an_empty_residual_is_worth_nothing(self):
        self.assertEqual(residual_freshness("", ["อะไรก็ได้"]), 0.0)


class TestMeasure(unittest.TestCase):
    def setUp(self):
        self.g = KnowledgeGraph()
        self.target = self.g.add_node("ก้นหอย")
        self.g.add_node("เพื่อนบ้าน", status=EpistemicStatus.UNCERTAIN, confidence=0.3)
        self.g.add_edge("เพื่อนบ้าน", "ก้นหอย", Relation.DEPENDS_ON)

    def test_an_answer_that_changes_nothing_scores_zero(self):
        before = snapshot(self.g, [self.target.id])
        gain = measure(before, self.g, [self.target.id], "", [])
        self.assertEqual(gain.total, 0.0)

    def test_revising_an_existing_belief_dominates_mere_volume(self):
        before = snapshot(self.g, [self.target.id])
        self.target.status = EpistemicStatus.PARTIALLY_KNOWN
        self.target.confidence = 0.8
        revised = measure(before, self.g, [self.target.id], "เศษใหม่เอี่ยม", [])

        bulk = KnowledgeGraph()
        anchor = bulk.add_node("ก้นหอย")
        before_bulk = snapshot(bulk, [anchor.id])
        for i in range(3):
            bulk.add_node(f"ของใหม่ {i}")
            bulk.add_edge(f"ของใหม่ {i}", "ก้นหอย", Relation.DEPENDS_ON)
        piled = measure(before_bulk, bulk, [anchor.id], "เศษใหม่เอี่ยม", [])

        self.assertGreater(revised.revision, piled.revision)

    def test_surfacing_a_contradiction_registers(self):
        before = snapshot(self.g, [self.target.id])
        self.g.add_node("คู่แข่ง")
        self.g.add_edge("คู่แข่ง", "ก้นหอย", Relation.CONTRADICTS)
        self.assertGreater(measure(before, self.g, [self.target.id], "เศษ", []).conflict, 0)

    def test_a_stale_residual_cancels_the_freshness_term(self):
        before = snapshot(self.g, [self.target.id])
        self.g.add_node("ของใหม่")
        self.g.add_edge("ของใหม่", "ก้นหอย", Relation.CAUSES)
        fresh = measure(before, self.g, [self.target.id], "เศษที่ไม่เคยมีใครพูด", ["เศษเดิม"])
        stale = measure(before, self.g, [self.target.id], "เศษเดิม", ["เศษเดิม"])
        self.assertGreater(fresh.total, stale.total)

    def test_total_stays_inside_the_unit_interval(self):
        before = snapshot(self.g, [self.target.id])
        for i in range(20):
            self.g.add_node(f"ท่วม {i}")
            self.g.add_edge(f"ท่วม {i}", "ก้นหอย", Relation.CAUSES)
        self.target.status = EpistemicStatus.KNOWN
        self.target.confidence = 1.0
        gain = measure(before, self.g, [self.target.id], "เศษใหม่", [])
        self.assertLessEqual(gain.total, 1.0)
        self.assertGreaterEqual(gain.total, 0.0)

    def test_all_residuals_collects_both_shapes(self):
        self.target.residuals.append("เศษที่แขวนไว้")
        self.g.add_node("เศษที่กลายเป็น node", tags=("residual",))
        found = all_residuals(self.g)
        self.assertIn("เศษที่แขวนไว้", found)
        self.assertIn("เศษที่กลายเป็น node", found)


if __name__ == "__main__":
    unittest.main()
