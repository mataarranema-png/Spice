"""การประดิษฐ์ตัวดำเนินการฐานขึ้นมาเอง ด้วยการค้นหาในปริภูมิของโปรแกรม."""

import random
import unittest

from spice.probe import BASE_OPS, Ref, probe, spec
from spice.signal import SignalDomain, context_signal, layered_signal
from spice.synth import Fit, Key, Workshop, fit, primitives, search, table_cap


def periodic(pattern, n=300):
    return [pattern[i % len(pattern)] for i in range(n)]


class TestKeySpace(unittest.TestCase):
    def test_a_key_is_a_composable_tree(self):
        k = Key("pair", left=Key("pos_mod", a=7), right=Key("pos_mod", a=13))
        self.assertEqual(str(k), "(i%7×i%13)")
        self.assertEqual(k.size, 3)

    def test_keys_evaluate_to_something_hashable(self):
        seq = [0, 1, 2, 3] * 20
        for k in primitives(len(seq))[:14]:
            with self.subTest(key=str(k)):
                v = k.at(seq, 12)
                if v is not None:
                    hash(v)

    def test_context_keys_refuse_to_answer_before_they_have_context(self):
        seq = [1, 2, 3]
        self.assertIsNone(Key("prev", a=2).at(seq, 0))
        self.assertIsNotNone(Key("prev", a=2).at(seq, 2))

    def test_a_perfect_key_leaves_no_residual(self):
        seq = periodic([0, 1, 2, 1])
        f = fit(seq, range(len(seq)), Key("pos_mod", a=4))
        self.assertEqual(f.accuracy, 1.0)
        self.assertEqual(f.misses, ())

    def test_a_useless_key_is_still_scored_not_crashed(self):
        seq = periodic([0, 1, 2, 1])
        f = fit(seq, range(len(seq)), Key("const"))
        self.assertLess(f.accuracy, 0.6)
        self.assertTrue(f.misses)

    def test_the_table_cap_scales_with_the_data(self):
        self.assertLess(table_cap(40), table_cap(400))
        self.assertGreaterEqual(table_cap(400), 91)   # ต้องพอให้ 7×13 ผ่านได้

    def test_memorising_is_refused(self):
        seq = [random.Random(1).randrange(4) for _ in range(40)]
        self.assertIsNone(fit(seq, range(len(seq)), Key("block", a=1)))

    def test_roundtrip(self):
        k = Key("pair", left=Key("prev", a=2), right=Key("pos_mod", a=5))
        self.assertEqual(str(Key.from_dict(k.to_dict())), str(k))


class TestSearch(unittest.TestCase):
    def test_it_recovers_a_plain_period(self):
        best = search(periodic([0, 1, 1, 2, 0, 3, 2]), range(300))[0]
        self.assertEqual(str(best.key), "i%7")
        self.assertEqual(best.accuracy, 1.0)

    def test_it_finds_joint_structure_no_single_detector_would_see(self):
        """i%13 เดี่ยว ๆ คะแนนแย่ จึงไม่มีวันเข้ารอบถ้าจับคู่แต่ตัวที่เก่งเดี่ยว
        การจับคู่ต้องมุ่งไปที่ *เศษ* ของตัวที่ดีที่สุด."""
        seq = layered_signal(420, seed=11)
        best = search(seq, range(len(seq)))[0]
        self.assertEqual(str(best.key), "(i%7×i%13)")
        self.assertGreater(best.accuracy, 0.88)

    def test_it_finds_context_structure_that_periodicity_is_blind_to(self):
        seq = context_signal(400, seed=5)
        d = SignalDomain(seq, random.Random(1))
        by_period = d.mechanism(d.root).value["accuracy"]
        best = search(seq, range(len(seq)))[0]
        self.assertLess(by_period, 0.8)          # เครื่องมือเดิมมองไม่เห็น
        self.assertGreater(best.accuracy, 0.9)   # การค้นหาเห็น
        self.assertIn("prev", str(best.key))

    def test_it_prefers_the_shorter_of_two_perfect_models(self):
        best = search(periodic([0, 1, 2] * 4), range(300))[0]
        self.assertEqual(str(best.key), "i%3")

    def test_too_little_data_returns_nothing(self):
        self.assertEqual(search([1, 2, 3], range(3)), [])


class TestWorkshop(unittest.TestCase):
    def setUp(self):
        self.n = 0
        self.w = Workshop(self._coin)

    def _coin(self):
        self.n += 1
        return f"⟦coin{self.n}⟧"

    def _fit_of(self, seq, key):
        return fit(seq, range(len(seq)), key)

    def test_a_re_derivation_of_an_existing_instrument_is_refused(self):
        """i%k เดี่ยว ๆ คือสิ่งที่ตัวตรวจจับคาบทำอยู่แล้ว การเลื่อนขั้นมันคือการหลอกตัวเอง."""
        f = self._fit_of(periodic([0, 1, 2, 1]), Key("pos_mod", a=4))
        for _ in range(4):
            self.assertIsNone(self.w.consider(f, 99.0, 1))
        self.assertEqual(self.w.stats()["invented"], 0)

    def test_a_genuinely_new_program_is_promoted_after_proving_itself_twice(self):
        seq = context_signal(400, seed=5)
        f = self._fit_of(seq, Key("prev", a=2))
        self.assertIsNone(self.w.consider(f, 3.0, 1))     # ครั้งแรกยังไม่พอ
        inv = self.w.consider(f, 3.0, 2)
        self.assertIsNotNone(inv)
        self.assertEqual(inv.key_str, "prev2")
        self.assertTrue(inv.coined)

    def test_a_program_no_better_than_the_baseline_is_refused(self):
        seq = context_signal(400, seed=5)
        f = self._fit_of(seq, Key("prev", a=2))
        for _ in range(4):
            self.assertIsNone(self.w.consider(f, f.bits_per_symbol, 1))

    def test_a_promoted_program_becomes_a_real_operator(self):
        seq = context_signal(400, seed=5)
        f = self._fit_of(seq, Key("prev", a=2))
        self.w.consider(f, 3.0, 1)
        inv = self.w.consider(f, 3.0, 2)
        s = spec(inv.op_key)
        self.assertIsNotNone(s, "ต้องเข้าไปอยู่ในพีชคณิตการถามจริง")
        self.assertEqual(s.arity, 1)
        # และประกอบได้เหมือนตัวฐานอื่นทุกประการ
        p = probe("reflect", probe(inv.op_key, Ref("x", "วัตถุ")))
        self.assertTrue(p.is_wellformed)
        self.assertNotIn("{", p.render("th"))
        self.assertIn(inv.coined, p.render("th"))

    def test_an_invented_operator_is_not_one_of_the_hand_written_base_ops(self):
        seq = context_signal(400, seed=5)
        f = self._fit_of(seq, Key("prev", a=2))
        self.w.consider(f, 3.0, 1)
        inv = self.w.consider(f, 3.0, 2)
        self.assertNotIn(inv.op_key, BASE_OPS)

    def test_roundtrip_keeps_the_invented_operator_usable(self):
        seq = context_signal(400, seed=5)
        f = self._fit_of(seq, Key("prev", a=2))
        self.w.consider(f, 3.0, 1)
        inv = self.w.consider(f, 3.0, 2)
        clone = Workshop.from_dict(self.w.to_dict(), self._coin)
        self.assertIn(inv.op_key, clone.invented)
        self.assertTrue(probe(inv.op_key, Ref("x")).is_wellformed)


class TestDomainInvention(unittest.TestCase):
    def test_synthesize_reports_whether_it_beat_the_old_instrument(self):
        d = SignalDomain(context_signal(400, seed=5), random.Random(1))
        m = d.synthesize(d.root)
        self.assertTrue(m.value["beats_baseline"])
        self.assertLess(m.value["bits_per_symbol"], m.value["baseline_bits_per_symbol"])

    def test_an_invented_operator_can_be_applied_back_to_the_data(self):
        d = SignalDomain(context_signal(400, seed=5), random.Random(1))
        f = fit(d.seq, d.root.idx, Key("prev", a=2))
        d.workshop.consider(f, 3.0, 1)
        inv = d.workshop.consider(f, 3.0, 2)
        m = d.apply_invented(d.root, inv.op_key)
        self.assertGreater(m.value["accuracy"], 0.9)
        self.assertEqual(inv.uses, 1)


if __name__ == "__main__":
    unittest.main()
