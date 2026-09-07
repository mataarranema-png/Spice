"""ให้ใครก็ได้เป็นตัวสืบค้น — โปรโตคอลสองจังหวะผ่านไฟล์."""

import json
import tempfile
import unittest
from pathlib import Path

from spice import exchange
from spice.spiral import Spiral


class TestExchange(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "questions.json"
        self.sp = Spiral.from_topic("ก้นหอย", seed=5)
        self.sp.run(3)

    def tearDown(self):
        self.dir.cleanup()

    def _dump(self):
        exchange.dump(self.sp, self.path)
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data):
        self.path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def test_dump_carries_enough_context_to_answer(self):
        data = self._dump()
        self.assertTrue(data["questions"])
        q = data["questions"][0]
        for key in ("id", "text", "level_th", "target", "nearby_concepts", "answer"):
            self.assertIn(key, q)
        self.assertIn("residual", data["instructions"])

    def test_a_real_answer_beats_the_offline_one_on_measured_gain(self):
        data = self._dump()
        # ผู้ตอบจริงจะไม่คายเศษเดียวกันสามครั้ง — และระบบก็ไม่ควรให้คะแนน
        # ความสดกับเศษที่เพิ่งถูกพูดไปเมื่อกี้ (ดู test ถัดไป)
        distinct = [
            ("การเติบโตแบบโนมอน", "ทำไมอัตราส่วนถึงลงตัวที่ค่านั้น ไม่ใช่ค่าอื่น"),
            ("คลื่นความหนาแน่นในจานหมุน", "กลไกนี้ใช้กับสิ่งมีชีวิตไม่ได้เลย แล้วอะไรเชื่อมสองโลกนี้"),
            ("การจัดเรียงเมล็ดให้ทับกันน้อยที่สุด", "การจัดเรียงที่ดีที่สุดถูกเลือกโดยอะไร"),
        ]
        for q, (label, residual) in zip(data["questions"], distinct):
            q["answer"] = {
                "answer": "คำอธิบายที่มีเนื้อหาจริงและเปลี่ยนแบบจำลอง: " + label,
                "confidence": 0.75,
                "new_nodes": [
                    {"label": label, "status": "PARTIALLY_KNOWN", "confidence": 0.6, "level": 1}
                ],
                "new_edges": [
                    {"source": label, "target": q["target"] or "ก้นหอย", "relation": "causes"}
                ],
                "residual": residual,
                "contradicts": [],
            }
        self._write(data)
        rec, answered = exchange.load(self.sp, self.path)
        self.assertEqual(answered, len(data["questions"]))
        self.assertGreater(rec.gain_mean, 0.3)
        self.assertTrue(all(t.gain["freshness"] > 0.8 for t in rec.turns))

    def test_repeating_one_residual_across_a_round_is_not_rewarded_three_times(self):
        data = self._dump()
        for q in data["questions"]:
            q["answer"] = {
                "answer": "คำตอบที่ต่างกัน แต่คายเศษเดิม",
                "confidence": 0.7, "new_nodes": [], "new_edges": [],
                "residual": "เศษเดียวกันเป๊ะทุกข้อ", "contradicts": [],
            }
        self._write(data)
        rec, _ = exchange.load(self.sp, self.path)
        fresh = [t.gain["freshness"] for t in rec.turns]
        self.assertGreater(fresh[0], 0.8)
        self.assertTrue(all(f < 0.2 for f in fresh[1:]))

    def test_an_answer_without_a_residual_is_not_an_answer(self):
        data = self._dump()
        data["questions"][0]["answer"]["answer"] = "ตอบแล้วนะ"
        data["questions"][0]["answer"]["residual"] = ""
        self._write(data)
        _, answered = exchange.load(self.sp, self.path)
        self.assertEqual(answered, 0)

    def test_unanswered_questions_fall_back_so_the_spiral_keeps_turning(self):
        self._dump()
        rec, answered = exchange.load(self.sp, self.path)
        self.assertEqual(answered, 0)
        self.assertTrue(rec.turns)
        for t in rec.turns:
            self.assertTrue(t.residual.strip())

    def test_absorb_without_propose_is_refused(self):
        fresh = Spiral.from_topic("x", seed=1)
        with self.assertRaises(RuntimeError):
            fresh.absorb({})

    def test_an_open_round_survives_a_save_and_reload(self):
        from spice import store

        exchange.dump(self.sp, self.path)
        state = Path(self.dir.name) / "state.json"
        store.save(self.sp, state)
        back = store.load(state, seed=5)
        self.assertEqual(
            [s.question.id for s in back._proposed],
            [s.question.id for s in self.sp._proposed],
        )
        rec, _ = exchange.load(back, self.path)
        self.assertTrue(rec.turns)

    def test_malformed_entries_are_ignored_rather_than_crashing(self):
        data = self._dump()
        data["questions"][0]["answer"] = {
            "answer": "มีเนื้อหา",
            "confidence": "ไม่ใช่ตัวเลข",
            "new_nodes": [{"label": "x", "status": "ไม่มีสถานะนี้", "level": 99}],
            "new_edges": [{"source": "x", "target": "", "relation": "ไม่มีความสัมพันธ์นี้"}],
            "residual": "เศษที่ใช้ได้",
            "contradicts": [],
        }
        self._write(data)
        rec, answered = exchange.load(self.sp, self.path)
        self.assertEqual(answered, 1)
        self.assertTrue(rec.turns)


if __name__ == "__main__":
    unittest.main()
