import json
import tempfile
import unittest
from pathlib import Path

from spice import store
from spice.spiral import Spiral


class TestStore(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "nested" / "state.json"

    def tearDown(self):
        self.dir.cleanup()

    def test_save_creates_parents_and_load_restores(self):
        sp = Spiral.from_topic("ก้นหอย", seed=1)
        sp.run(5)
        store.save(sp, self.path)
        self.assertTrue(self.path.exists())
        back = store.load(self.path, seed=1)
        self.assertEqual(back.epoch, sp.epoch)
        self.assertEqual(len(back.graph), len(sp.graph))
        self.assertEqual(len(back.ledger), len(sp.ledger))

    def test_evolved_strategies_survive_the_round_trip(self):
        sp = Spiral.from_topic("ก้นหอย", seed=2)
        sp.run(8)
        evolved = {s.name for s in sp.population.live() if s.origin != "builtin"}
        self.assertTrue(evolved, "ยังไม่มีการวิวัฒนาการให้เก็บ")
        store.save(sp, self.path)
        back = store.load(self.path, seed=2)
        self.assertTrue(evolved <= {s.name for s in back.population.live()})

    def test_resuming_does_not_re_ask_old_questions(self):
        sp = Spiral.from_topic("ก้นหอย", seed=3)
        sp.run(6)
        first = {t.question.signature for r in sp.history for t in r.turns}
        store.save(sp, self.path)
        back = store.load(self.path, seed=3)
        back.run(6)
        second = {t.question.signature for r in back.history for t in r.turns}
        self.assertFalse(first & second)

    def test_load_or_create_seeds_a_fresh_spiral(self):
        sp = store.load_or_create(self.path, "หัวข้อใหม่", seed=4)
        self.assertIsNotNone(sp.graph.by_label("หัวข้อใหม่"))

    def test_a_newer_schema_is_refused_rather_than_misread(self):
        self.path.parent.mkdir(parents=True)
        sp = Spiral.from_topic("x", seed=5)
        payload = sp.to_dict()
        payload["version"] = store.SCHEMA_VERSION + 1
        self.path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaises(ValueError):
            store.load(self.path)

    def test_a_failed_write_leaves_no_temp_files(self):
        sp = Spiral.from_topic("x", seed=6)
        store.save(sp, self.path)
        leftovers = list(self.path.parent.glob("*.tmp"))
        self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
