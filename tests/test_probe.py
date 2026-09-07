"""คำถามในฐานะโครงสร้าง — ระดับต้องงอกจากรูป ไม่ใช่จากการประกาศ."""

import unittest

from spice.probe import BASE_OPS, Kind, Probe, Ref, probe, spec
from spice.types import QuestionLevel

A = Ref("n1", "ก้นหอย")
B = Ref("n2", "การเติบโต")


class TestStructure(unittest.TestCase):
    def test_every_base_op_is_declared_consistently(self):
        for key in BASE_OPS:
            s = spec(key)
            with self.subTest(op=key):
                self.assertIsNotNone(s)
                self.assertIn(s.arity, (1, 2))
                self.assertTrue(s.th, f"{key} ไม่มีผิวภาษาไทย")
                self.assertTrue(s.nom_th, f"{key} ไม่มีรูปนาม")

    def test_level_is_computed_from_shape(self):
        self.assertIs(probe("bound", A).level, QuestionLevel.OBJECT)
        self.assertIs(probe("reflect", probe("bound", A)).level, QuestionLevel.META)
        self.assertIs(probe("origin", probe("bound", A)).level, QuestionLevel.ONTOLOGY)
        self.assertIs(
            probe("limit", probe("reflect", probe("bound", A))).level,
            QuestionLevel.SELF_REFERENCE,
        )

    def test_nesting_never_exceeds_the_top_level(self):
        p = probe("bound", A)
        for _ in range(6):
            p = probe("limit", p)
        self.assertIs(p.level, QuestionLevel.SELF_REFERENCE)

    def test_identity_is_structural_not_lexical(self):
        one = probe("reflect", probe("mechanism", A))
        two = probe("reflect", probe("mechanism", Ref("n1", "ชื่อเรียกใหม่หมด")))
        self.assertEqual(one.signature, two.signature)
        self.assertNotEqual(one.signature, probe("mechanism", A).signature)

    def test_shape_forgets_the_subject_but_keeps_the_form(self):
        self.assertEqual(
            probe("compare", probe("mechanism", A), probe("mechanism", B)).shape,
            "compare(mechanism(·),mechanism(·))",
        )

    def test_wellformedness_is_enforced_by_kind(self):
        # ตัวยกระดับรับได้เฉพาะคำถามอื่น ไม่ใช่วัตถุ
        self.assertFalse(Probe("reflect", (A,)).is_wellformed)
        self.assertTrue(probe("reflect", probe("bound", A)).is_wellformed)
        # ตัวที่รับวัตถุอย่างเดียวก็รับคำถามไม่ได้
        self.assertFalse(Probe("identify", (probe("bound", A),)).is_wellformed)

    def test_arity_is_enforced(self):
        self.assertFalse(Probe("compare", (A,)).is_wellformed)
        self.assertTrue(probe("compare", A, B).is_wellformed)

    def test_refs_are_collected_from_the_whole_tree(self):
        p = probe("compare", probe("mechanism", A), probe("bound", B))
        self.assertEqual({r.id for r in p.refs()}, {"n1", "n2"})

    def test_depth_counts_probe_nesting_only(self):
        self.assertEqual(probe("bound", A).depth, 1)
        self.assertEqual(probe("reflect", probe("bound", A)).depth, 2)


class TestSurface(unittest.TestCase):
    def test_a_probe_renders_without_leaving_placeholders(self):
        for p in (
            probe("bound", A),
            probe("reflect", probe("bound", A)),
            probe("compare", probe("mechanism", A), probe("invariant", B)),
            probe("limit", probe("origin", probe("presuppose", A))),
        ):
            with self.subTest(shape=p.shape):
                text = p.render("th")
                self.assertNotIn("{", text)
                self.assertIn("ก้นหอย", text)

    def test_nesting_uses_noun_phrases_not_quoted_sentences(self):
        inner = probe("mechanism", A)
        outer = probe("reflect", inner)
        # รูปนามของตัวในต้องปรากฏ ส่วนประโยคคำถามเต็มของมันต้องไม่
        self.assertIn(inner.nominalise("th"), outer.render("th"))
        self.assertNotIn(inner.render("th"), outer.render("th"))

    def test_deep_nesting_stays_readable(self):
        p = probe("limit", probe("reflect", probe("bound", A)))
        self.assertLess(len(p.render("th")), 200)

    def test_the_structure_survives_without_any_surface(self):
        """โดเมนที่ไม่มีภาษาใช้ต้นไม้ได้โดยไม่ต้อง render เลย."""
        p = probe("mechanism", Ref("s1"))     # ไม่มี hint = ไม่มีชื่อเรียก
        self.assertTrue(p.is_wellformed)
        self.assertEqual(p.shape, "mechanism(·)")
        self.assertIs(p.level, QuestionLevel.MECHANISM)

    def test_roundtrip(self):
        p = probe("compare", probe("mechanism", A), probe("limit", probe("bound", B)))
        self.assertEqual(Probe.from_dict(p.to_dict()).signature, p.signature)


if __name__ == "__main__":
    unittest.main()
