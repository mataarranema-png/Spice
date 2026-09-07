import json
import types
import unittest

from spice.graph import KnowledgeGraph
from spice.investigator import CompositeInvestigator, ReflectiveInvestigator
from spice.llm import FINDING_SCHEMA, ClaudeInvestigator
from spice.question import Question
from spice.spiral import Spiral
from spice.types import EpistemicStatus, QuestionLevel, Relation

PAYLOAD = {
    "answer": "ก้นหอยเกิดจากการเติบโตที่คงอัตราส่วนไว้ตลอด",
    "confidence": 0.6,
    "new_nodes": [
        {
            "label": "การเติบโตคงอัตราส่วน",
            "status": "PARTIALLY_KNOWN",
            "confidence": 0.5,
            "level": 1,
        }
    ],
    "new_edges": [
        {"source": "การเติบโตคงอัตราส่วน", "target": "ก้นหอย", "relation": "causes"}
    ],
    "residual": "ทำไมอัตราส่วนจึงคงที่ ไม่ใช่ค่าอื่น",
    "contradicts": [],
}


def _block(text):
    return types.SimpleNamespace(type="text", text=text)


def _response(payload=None, *, stop_reason="end_turn", category=None):
    return types.SimpleNamespace(
        content=[_block(json.dumps(payload))] if payload is not None else [],
        stop_reason=stop_reason,
        stop_details=types.SimpleNamespace(type="refusal", category=category),
        usage=types.SimpleNamespace(output_tokens=250),
    )


class FakeClient:
    """client ปลอมที่บันทึกพารามิเตอร์ไว้ตรวจ — ไม่แตะเครือข่ายจริง."""

    def __init__(self, response=None, *, beta_error=None, error=None):
        self.calls: list[dict] = []
        self.beta_calls: list[dict] = []
        self._response = response if response is not None else _response(PAYLOAD)
        self._beta_error = beta_error or TypeError("SDK นี้ยังไม่รู้จักธงเบตา")
        self._error = error
        outer = self

        class _Messages:
            def create(self, **kw):
                outer.calls.append(kw)
                if outer._error:
                    raise outer._error
                return outer._response

        class _BetaMessages:
            def create(self, **kw):
                outer.beta_calls.append(kw)
                raise outer._beta_error

        self.messages = _Messages()
        self.beta = types.SimpleNamespace(messages=_BetaMessages())


class TestSchema(unittest.TestCase):
    def test_residual_is_a_required_field(self):
        self.assertIn("residual", FINDING_SCHEMA["required"])
        self.assertGreaterEqual(FINDING_SCHEMA["properties"]["residual"]["minLength"], 1)

    def test_schema_is_closed(self):
        self.assertFalse(FINDING_SCHEMA["additionalProperties"])

    def test_enums_match_the_type_system(self):
        self.assertEqual(
            set(FINDING_SCHEMA["properties"]["new_nodes"]["items"]["properties"]["status"]["enum"]),
            {s.value for s in EpistemicStatus},
        )
        self.assertEqual(
            set(FINDING_SCHEMA["properties"]["new_edges"]["items"]["properties"]["relation"]["enum"]),
            {r.value for r in Relation},
        )


class TestClaudeInvestigator(unittest.TestCase):
    def setUp(self):
        self.graph = KnowledgeGraph()
        self.node = self.graph.add_node("ก้นหอย")
        self.q = Question(
            text="ก้นหอยเกิดขึ้นได้อย่างไร?",
            level=QuestionLevel.MECHANISM,
            strategy="mechanism_probe",
            targets=(self.node.id,),
        )

    def test_parses_a_structured_finding(self):
        inv = ClaudeInvestigator(client=FakeClient())
        f = inv.investigate(self.q, self.graph)
        self.assertEqual(f.answer, PAYLOAD["answer"])
        self.assertEqual(f.residual, PAYLOAD["residual"])
        self.assertEqual([n.label for n in f.new_nodes], ["การเติบโตคงอัตราส่วน"])
        self.assertIs(f.new_edges[0].relation, Relation.CAUSES)

    def test_request_uses_the_documented_shape(self):
        client = FakeClient()
        ClaudeInvestigator(client=client, model="claude-opus-5").investigate(self.q, self.graph)
        kw = client.calls[-1]
        self.assertEqual(kw["model"], "claude-opus-5")
        self.assertEqual(kw["thinking"], {"type": "adaptive"})
        self.assertEqual(kw["output_config"]["format"]["type"], "json_schema")
        self.assertIn("effort", kw["output_config"])
        self.assertEqual(kw["system"][0]["cache_control"], {"type": "ephemeral"})

    def test_falls_back_once_when_the_beta_flag_is_unsupported(self):
        client = FakeClient()
        inv = ClaudeInvestigator(client=client)
        inv.investigate(self.q, self.graph)
        inv.investigate(self.q, self.graph)
        self.assertEqual(len(client.beta_calls), 1)   # ไม่ลองซ้ำทุกครั้ง
        self.assertEqual(len(client.calls), 2)
        self.assertTrue(inv.failures)

    def test_prompt_carries_graph_context(self):
        self.node.residuals.append("เศษเดิมที่ยังค้าง")
        client = FakeClient()
        ClaudeInvestigator(client=client).investigate(self.q, self.graph)
        prompt = client.calls[-1]["messages"][0]["content"]
        self.assertIn("ก้นหอย", prompt)
        self.assertIn("เศษเดิมที่ยังค้าง", prompt)

    def test_a_refusal_becomes_a_finding_not_a_crash(self):
        inv = ClaudeInvestigator(client=FakeClient(_response(stop_reason="refusal", category="cyber")))
        f = inv.investigate(self.q, self.graph)
        self.assertEqual(f.confidence, 0.0)
        self.assertIn("cyber", f.residual)

    def test_unparseable_output_raises(self):
        bad = types.SimpleNamespace(
            content=[_block("นี่ไม่ใช่ JSON")], stop_reason="end_turn", usage=None
        )
        inv = ClaudeInvestigator(client=FakeClient(bad))
        with self.assertRaises(json.JSONDecodeError):
            inv.investigate(self.q, self.graph)

    def test_out_of_range_values_are_clamped(self):
        payload = dict(PAYLOAD, confidence=42)
        payload["new_nodes"] = [
            {"label": "x", "status": "ไม่มีสถานะนี้", "confidence": -3, "level": 99}
        ]
        f = ClaudeInvestigator(client=FakeClient(_response(payload))).investigate(
            self.q, self.graph
        )
        self.assertEqual(f.confidence, 1.0)
        self.assertEqual(f.new_nodes[0].confidence, 0.0)
        self.assertIs(f.new_nodes[0].level, QuestionLevel.SELF_REFERENCE)
        self.assertIs(f.new_nodes[0].status, EpistemicStatus.PARTIALLY_KNOWN)

    def test_composite_keeps_the_spiral_turning_when_claude_fails(self):
        broken = ClaudeInvestigator(client=FakeClient(error=RuntimeError("เครือข่ายล่ม")))
        composite = CompositeInvestigator(broken, ReflectiveInvestigator())
        sp = Spiral.from_topic("ก้นหอย", seed=1, investigator=composite)
        sp.run(3)
        self.assertTrue(composite.failures)
        self.assertTrue([t for r in sp.history for t in r.turns])
        # ความล้มเหลวของเครื่องมือถูกยกขึ้นเป็นข้อจำกัดของตัวระบบ
        self.assertTrue(any(l.kind == "instrument" for l in sp.self_model.detect(sp.epoch)))


if __name__ == "__main__":
    unittest.main()
