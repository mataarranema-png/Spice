import unittest

from spice.graph import KnowledgeGraph
from spice.types import EpistemicStatus, QuestionLevel, Relation


class TestKnowledgeGraph(unittest.TestCase):
    def setUp(self):
        self.g = KnowledgeGraph()

    def test_same_label_merges_into_one_node(self):
        a = self.g.add_node("ก้นหอย")
        b = self.g.add_node("ก้นหอย", status=EpistemicStatus.PARTIALLY_KNOWN)
        self.assertEqual(a.id, b.id)
        self.assertEqual(len(self.g), 1)
        self.assertIs(b.status, EpistemicStatus.PARTIALLY_KNOWN)

    def test_merge_never_downgrades_a_contradiction(self):
        self.g.add_node("x", status=EpistemicStatus.CONTRADICTED)
        self.g.add_node("x", status=EpistemicStatus.KNOWN, confidence=0.99)
        self.assertIs(self.g.by_label("x").status, EpistemicStatus.CONTRADICTED)

    def test_contradiction_edge_marks_both_endpoints(self):
        self.g.add_node("a")
        self.g.add_node("b")
        self.g.add_edge("a", "b", Relation.CONTRADICTS)
        self.assertIs(self.g.by_label("a").status, EpistemicStatus.CONTRADICTED)
        self.assertIs(self.g.by_label("b").status, EpistemicStatus.CONTRADICTED)
        self.assertEqual(len(self.g.contradiction_pairs()), 1)

    def test_edge_to_missing_node_is_ignored(self):
        self.g.add_node("a")
        self.assertIsNone(self.g.add_edge("a", "ไม่มีอยู่จริง"))
        self.assertEqual(len(self.g.edges), 0)

    def test_unexplained_excludes_explained_targets(self):
        self.g.add_node("ผล")
        self.g.add_node("เหตุ")
        self.g.add_edge("เหตุ", "ผล", Relation.CAUSES)
        labels = {n.label for n in self.g.unexplained()}
        self.assertIn("เหตุ", labels)
        self.assertNotIn("ผล", labels)

    def test_structural_holes_are_disconnected_pairs(self):
        for label in ("a", "b", "c"):
            self.g.add_node(label, level=QuestionLevel.OBJECT)
        self.g.add_edge("a", "b", Relation.CAUSES)
        holes = self.g.structural_holes(8)
        pairs = {frozenset((x.label, y.label)) for x, y in holes}
        self.assertIn(frozenset(("a", "c")), pairs)
        self.assertNotIn(frozenset(("a", "b")), pairs)

    def test_local_contradiction_rises_near_a_conflict(self):
        self.g.add_node("a")
        self.g.add_node("b")
        self.g.add_node("far")
        self.g.add_edge("a", "b", Relation.CONTRADICTS)
        self.assertGreater(
            self.g.local_contradiction(self.g.by_label("a").id),
            self.g.local_contradiction(self.g.by_label("far").id),
        )

    def test_roundtrip_preserves_nodes_edges_and_adjacency(self):
        self.g.add_node("a", status=EpistemicStatus.UNCERTAIN, confidence=0.3)
        self.g.add_node("b")
        self.g.add_edge("a", "b", Relation.EXPLAINS)
        clone = KnowledgeGraph.from_dict(self.g.to_dict())
        self.assertEqual(clone.stats(), self.g.stats())
        self.assertTrue(clone.path_exists(clone.by_label("a").id, clone.by_label("b").id))

    def test_dot_export_mentions_every_node(self):
        self.g.add_node("ก้นหอย")
        self.g.add_node("เกลียว")
        dot = self.g.to_dot()
        self.assertIn("ก้นหอย", dot)
        self.assertIn("เกลียว", dot)
        self.assertTrue(dot.startswith("digraph"))


if __name__ == "__main__":
    unittest.main()
