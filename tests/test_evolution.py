import random
import unittest

from spice.evolution import RETIRE_BELOW, Population
from spice.scoring import Weights
from spice.selfmodel import CapabilityGap
from spice.strategies import builtin_strategies
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
            w = pop.weights.normalized()
            for term in (w.u, w.c, w.n):
                self.assertGreater(term, 0.05)
                self.assertLess(term, 0.7)

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
