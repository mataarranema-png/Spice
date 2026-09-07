"""ไวยากรณ์ที่งอกหน่วยใหม่ขึ้นมาเอง."""

import random
import unittest

from spice.grammar import MINT_MIN_GAIN, MINT_MIN_USES, Grammar
from spice.probe import BASE_OPS, Ref, probe, spec

REFS = [Ref("a", "ก้นหอย"), Ref("b", "การเติบโต")]


class TestComposition(unittest.TestCase):
    def setUp(self):
        self.g = Grammar(random.Random(3))

    def test_composed_questions_are_wellformed(self):
        made = 0
        for _ in range(200):
            p = self.g.compose(REFS, max_depth=3)
            if p is None:
                continue
            made += 1
            self.assertTrue(p.is_wellformed, p.shape)
            self.assertNotIn("{", p.render("th"))
        self.assertGreater(made, 100)

    def test_composition_reaches_shapes_nobody_wrote(self):
        shapes = set()
        for _ in range(400):
            p = self.g.compose(REFS, max_depth=4)
            if p is not None:
                shapes.add(p.shape)
        self.assertGreater(len(shapes), 40)
        self.assertTrue(any(s.count("(") >= 3 for s in shapes), "ไม่มีรูปที่ลึกเกินสองชั้นเลย")

    def test_no_refs_means_no_questions(self):
        self.assertIsNone(self.g.compose([], max_depth=3))


class TestMinting(unittest.TestCase):
    def setUp(self):
        self.g = Grammar(random.Random(11))

    def _feed(self, outer, inner, gain, times):
        for _ in range(times):
            self.g.observe(probe(outer, probe(inner, REFS[0])), gain)

    def test_a_productive_pair_becomes_one_operator(self):
        self._feed("reflect", "mechanism", 0.6, MINT_MIN_USES + 1)
        m = self.g.mint(5)
        self.assertIsNotNone(m)
        self.assertEqual((m.outer, m.inner), ("reflect", "mechanism"))
        self.assertTrue(m.coined, "หน่วยใหม่ต้องมีชื่อที่ระบบตั้งเอง")
        self.assertIsNotNone(spec(m.key), "หน่วยใหม่ต้องเข้าไปอยู่ในพีชคณิตทันที")

    def test_the_new_unit_composes_like_any_other(self):
        self._feed("reflect", "mechanism", 0.6, MINT_MIN_USES + 1)
        m = self.g.mint(5)
        p = probe("limit", probe(m.key, REFS[0]))
        self.assertTrue(p.is_wellformed)
        self.assertNotIn("{", p.render("th"))
        # หน่วยที่หลอมแล้วประหยัดความลึก: รูปนี้เดิมต้องใช้สามชั้น
        self.assertEqual(p.depth, 2)

    def test_a_weak_pair_is_not_minted(self):
        self._feed("reflect", "bound", MINT_MIN_GAIN - 0.2, MINT_MIN_USES + 3)
        self.assertIsNone(self.g.mint(5))

    def test_a_rare_pair_is_not_minted(self):
        self._feed("origin", "bound", 0.9, MINT_MIN_USES - 1)
        self.assertIsNone(self.g.mint(5))

    def test_the_same_pair_is_only_minted_once(self):
        self._feed("reflect", "mechanism", 0.6, MINT_MIN_USES + 4)
        self.assertIsNotNone(self.g.mint(5))
        self.assertIsNone(self.g.mint(6))

    def test_vocabulary_grows_by_exactly_what_was_minted(self):
        before = len(self.g.vocabulary)
        self._feed("reflect", "mechanism", 0.6, MINT_MIN_USES + 1)
        self.g.mint(5)
        self.assertEqual(len(self.g.vocabulary), before + 1)
        self.assertEqual(self.g.stats()["base"], len(BASE_OPS))

    def test_an_unproductive_unit_is_pruned(self):
        self._feed("reflect", "mechanism", 0.6, MINT_MIN_USES + 1)
        m = self.g.mint(5)
        for _ in range(6):
            self.g.observe(probe(m.key, REFS[0]), 0.01)
        self.assertIn(m.key, [x for x in self.g.prune(9)])
        self.assertNotIn(m.key, self.g.minted)

    def test_success_makes_a_pair_more_likely_to_recur(self):
        """ถ้าไม่เอนไปทางคู่ที่ได้ผล พื้นที่การประกอบจะกว้างเกินกว่าจะตกผลึก."""
        self._feed("reflect", "mechanism", 0.9, 6)
        hits = 0
        for _ in range(300):
            p = self.g.compose(REFS, max_depth=2, lifting_bias=1.0)
            if p is not None and p.shape == "reflect(mechanism(·))":
                hits += 1
        plain = Grammar(random.Random(11))
        base_hits = 0
        for _ in range(300):
            p = plain.compose(REFS, max_depth=2, lifting_bias=1.0)
            if p is not None and p.shape == "reflect(mechanism(·))":
                base_hits += 1
        self.assertGreater(hits, base_hits)

    def test_roundtrip_keeps_the_grown_vocabulary(self):
        self._feed("reflect", "mechanism", 0.6, MINT_MIN_USES + 1)
        m = self.g.mint(5)
        clone = Grammar.from_dict(self.g.to_dict(), random.Random(11))
        self.assertIn(m.key, clone.minted)
        self.assertIsNotNone(spec(m.key))
        self.assertTrue(probe(m.key, REFS[0]).is_wellformed)


if __name__ == "__main__":
    unittest.main()
