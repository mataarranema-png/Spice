"""เครื่องมือหาโครงสร้างในลำดับเหตุการณ์จริง — ใช้ได้เดี่ยว ๆ ไม่ต้องมี LLM."""

import io
import random
import unittest

from spice.find import clumping, describe, enrichment, read_tokens, report
from collections import Counter


def daily_log(days=21, anomaly_hours=(2, 3), noise=0.05, seed=7):
    rng = random.Random(seed)
    out = []
    for h in range(24 * days):
        hour, dow = h % 24, (h // 24) % 7
        if dow >= 5:
            st = "idle" if hour < 9 or hour > 18 else "low"
        elif 9 <= hour < 12 or 14 <= hour < 18:
            st = "busy"
        elif hour in (12, 13, 18, 19, 20):
            st = "low"
        else:
            st = "idle"
        if h > 24 * (days - 7) and hour in anomaly_hours:
            st = "backup"
        if rng.random() < noise:
            st = rng.choice(["busy", "low", "idle", "error"])
        out.append(st)
    return out


class TestInput(unittest.TestCase):
    def test_it_accepts_the_separators_people_actually_use(self):
        for raw in ("a b c", "a,b,c", "a;b;c", "a\tb\tc", "a\nb\nc"):
            self.assertEqual(read_tokens(io.StringIO(raw)), ["a", "b", "c"])

    def test_short_input_is_refused_politely(self):
        self.assertIn("อย่างน้อย", report(["a", "b"] * 4))


class TestReadout(unittest.TestCase):
    def test_programs_are_translated_into_plain_language(self):
        self.assertIn("รอบซ้ำทุก 24", describe("i%24"))
        self.assertIn("ค่าก่อนหน้า", describe("prev3"))
        self.assertIn("โครงสร้างร่วม", describe("(i%24×prev3)"))
        self.assertIn("ทิศทาง", describe("Δprev"))

    def test_clustered_and_scattered_residuals_read_differently(self):
        clustered = list(range(200, 230))
        scattered = list(range(0, 300, 10))
        self.assertIn("กระจุก", clumping(clustered, 400))
        self.assertNotIn("กระจุก", clumping(scattered, 400))

    def test_enrichment_finds_what_is_unpredictable_beyond_its_share(self):
        tokens = ["ok"] * 200 + ["rare"] * 10
        counts = Counter(tokens)
        # ทุกครั้งที่ rare โผล่ แพตเทิร์นทายไม่ได้ ส่วน ok ทายไม่ได้แค่หยิบมือ
        misses = list(range(200, 210)) + [0, 1, 2]
        out = "\n".join(enrichment(tokens, misses, counts))
        self.assertIn("rare", out)
        self.assertIn("ผิดปกติชัดเจน", out)

    def test_a_token_that_fails_at_its_own_rate_is_not_flagged(self):
        tokens = ["a"] * 100 + ["b"] * 100
        counts = Counter(tokens)
        misses = list(range(0, 20)) + list(range(100, 120))
        out = "\n".join(enrichment(tokens, misses, counts))
        self.assertNotIn("ผิดปกติชัดเจน", out)


class TestOnRealisticData(unittest.TestCase):
    def setUp(self):
        self.text = report(daily_log())

    def test_it_recovers_the_daily_cycle(self):
        self.assertIn("รอบซ้ำทุก 24", self.text)

    def test_it_flags_the_rare_events_as_disproportionately_unpredictable(self):
        line = next(l for l in self.text.splitlines() if l.strip().startswith("error"))
        ratio = float(line.split("—")[1].split("เท่า")[0])
        self.assertGreater(ratio, 2.0)

    def test_it_points_at_the_hours_where_the_regime_changed(self):
        line = next((l for l in self.text.splitlines() if "จุดในรอบ" in l), "")
        self.assertTrue(line, "ไม่ได้รายงานจุดในรอบที่พังบ่อย")
        self.assertTrue(
            any(f"ตำแหน่งที่ {h} ของรอบ" in line for h in (2, 3)),
            f"ควรชี้ไปที่ชั่วโมงที่ระบอบเปลี่ยน แต่ได้: {line}",
        )

    def test_it_looks_inside_its_own_residual(self):
        self.assertIn("ซ้อนอยู่ในเศษ", self.text)

    def test_it_says_what_it_does_not_tell_you(self):
        self.assertIn("ไม่ได้บอกว่า", self.text)

    def test_pure_noise_yields_no_confident_structure(self):
        rng = random.Random(3)
        text = report([rng.choice("abcd") for _ in range(400)])
        acc = float(text.split("ทายถูก ")[1].split("%")[0])
        self.assertLess(acc, 55.0)


if __name__ == "__main__":
    unittest.main()
