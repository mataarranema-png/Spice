import random
import unittest

from spice.evolution import W_CEIL, W_FLOOR, RETIRE_BELOW, Population, _clamp
from spice.scoring import Weights
from spice.selfmodel import CapabilityGap
from spice.strategies import Strategy, builtin_strategies
from spice.types import QuestionLevel


class TestPopulation(unittest.TestCase):
    def test_credit_moves_fitness_toward_the_observed_reward(self):
        pop = Population(rng=random.Random(0))
        before = pop.get("object_probe").fitness
        for _ in range(8):
            pop.credit({"object_probe": 1.0})
        self.assertGreater(pop.get("object_probe").fitness, before)

    def test_unused_strategies_fade(self):
        pop = Population(rng=random.Random(0))
        before = pop.get("meta_probe").fitness
        pop.decay_unused({"object_probe"})
        self.assertLess(pop.get("meta_probe").fitness, before)

    def test_a_persistent_gap_creates_exactly_one_tool(self):
        pop = Population(rng=random.Random(1))
        gap = CapabilityGap("ช่องโหว่เดิม", QuestionLevel.ONTOLOGY, "frontier", 0.9)
        pop.evolve(1, [gap], 0.4)
        pop.evolve(2, [gap], 0.4)
        pop.evolve(3, [gap], 0.4)
        # ลูกที่กลายพันธุ์ต่อจากเครื่องมือนั้นมีได้ แต่ *ตัวเครื่องมือ* ต้องมีตัวเดียว
        tools = [s for s in pop.live() if s.origin == "capability-gap"]
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0].lineage, ("<self-model>",))

    def test_retirement_never_empties_a_question_level(self):
        pop = Population(rng=random.Random(3), max_size=40)
        for s in pop.live():
            s.fitness = 0.0
            s.uses = 99
        pop.evolve(1, [], 0.0)
        self.assertGreaterEqual(len(pop.live()), pop.min_size)
        for level in QuestionLevel:
            self.assertTrue(
                any(s.level is level for s in pop.live()),
                f"ระดับ{level.th}หายไปทั้งระดับ",
            )

    def test_population_stays_under_its_ceiling(self):
        pop = Population(rng=random.Random(5), max_size=12)
        for e in range(40):
            pop.credit({s.name: 0.9 for s in pop.live()[:3]})
            pop.evolve(e, [], 0.5)
        self.assertLessEqual(len(pop.live()), 12)

    def test_weights_stay_inside_their_bounds(self):
        pop = Population(rng=random.Random(7))
        reward = 0.0
        for e in range(120):
            reward += 0.01
            pop.evolve(e, [], reward)
            for term in (pop.weights.u, pop.weights.c, pop.weights.n):
                self.assertGreaterEqual(term, W_FLOOR)
                self.assertLessEqual(term, W_CEIL)

    def test_clamp_projects_onto_the_feasible_set(self):
        for w in (Weights(9, 0.01, 0.01), Weights(0, 0, 1), Weights(0.5, 0.4, 0.1)):
            c = _clamp(w)
            for term in (c.u, c.c, c.n):
                self.assertGreaterEqual(term, W_FLOOR)
                self.assertLessEqual(term, W_CEIL)
            self.assertAlmostEqual(c.u + c.c + c.n, 1.0, places=6)

    def _idle(self, name, **kw):
        return Strategy(
            name=name, level=QuestionLevel.OBJECT, source="frontier",
            templates={"th": ["{a}?"]}, born_epoch=0, **kw
        )

    def test_a_strategy_offered_chances_but_never_chosen_is_retired(self):
        pop = Population(rng=random.Random(17), max_size=40)
        idle = self._idle("ตัวที่มีโอกาสแต่ไม่เคยถูกเลือก")
        pop.strategies[idle.name] = idle
        for e in range(1, 30):
            idle.offered += 1          # แหล่งเป้าหมายมีของให้ถามทุกรอบ
            pop.credit({"meta_probe": 0.9})
            pop.evolve(e, [], 0.5)
        self.assertNotIn(idle.name, {s.name for s in pop.live()})

    def test_a_strategy_whose_source_is_still_empty_is_protected(self):
        """comparative_probe ต้องรอจนกราฟมีคำอธิบายที่แข่งกันก่อนถึงจะถามได้.

        ถ้านับความล้าสมัยจากอายุแทนที่จะนับจากโอกาส ความสามารถแบบนี้จะถูก
        ตัดทิ้งก่อนได้ลงสนามสักครั้ง.
        """
        pop = Population(rng=random.Random(19), max_size=40)
        waiting = self._idle("ตัวที่แหล่งเป้าหมายยังว่าง")   # offered คงอยู่ที่ 0
        pop.strategies[waiting.name] = waiting
        for e in range(1, 30):
            pop.credit({"meta_probe": 0.9})
            pop.evolve(e, [], 0.5)
        self.assertIn(waiting.name, {s.name for s in pop.live()})

    def test_gap_born_tools_cannot_swallow_the_population(self):
        pop = Population(rng=random.Random(23), max_size=20)
        for e in range(1, 60):
            gaps = [
                CapabilityGap(f"จุดบอดที่ {e}", QuestionLevel.META, "frontier", 0.9),
                CapabilityGap(f"จุดบอดอีกอันที่ {e}", QuestionLevel.ONTOLOGY, "frontier", 0.9),
            ]
            pop.evolve(e, gaps, 0.5)
        born = [s for s in pop.live() if s.origin == "capability-gap"]
        self.assertLessEqual(len(born), pop.gap_quota)
        self.assertGreater(len(born), 0)

    def test_reverting_a_bad_step_is_possible(self):
        pop = Population(rng=random.Random(11))
        pop.evolve(0, [], 0.9)
        accepted = pop.evolve(1, [], -5.0).accepted_weights
        self.assertFalse(accepted)

    def test_roundtrip_preserves_the_evolved_population(self):
        pop = Population(rng=random.Random(13))
        for e in range(6):
            pop.credit({"meta_probe": 0.8})
            pop.evolve(e, [], 0.5)
        clone = Population.from_dict(pop.to_dict(), random.Random(13))
        self.assertEqual(
            sorted(s.name for s in clone.live()), sorted(s.name for s in pop.live())
        )
        self.assertEqual(clone.generation, pop.generation)
        self.assertAlmostEqual(clone.weights.u, pop.weights.u)


if __name__ == "__main__":
    unittest.main()
