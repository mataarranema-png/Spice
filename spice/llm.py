"""ตัวสืบค้นที่ใช้ Claude จริง — เสียบแทน ReflectiveInvestigator ได้ทันที.

โมดูลนี้เป็น *ตัวเลือก*: แพ็กเกจหลักไม่พึ่งพาอะไรนอก stdlib เลย ถ้าไม่ได้
ติดตั้ง `anthropic` หรือไม่มีคีย์ ก้นหอยก็ยังหมุนด้วย ReflectiveInvestigator
ได้ตามปกติ — และ "เครื่องมือชิ้นนี้ใช้ไม่ได้" จะถูก SelfModel หยิบไปตั้ง
เป็นคำถามระดับ SELF_REFERENCE เอง.

สัญญาเดียวกับ investigator ทุกตัว: ต้องคืน `residual` เสมอ.  ตรงนี้บังคับ
สองชั้น — schema กำหนดให้ `residual` เป็น required field และโค้ดยัง
เรียก `ensure_residual` ทับอีกที.
"""

from __future__ import annotations

import json
import types
from functools import lru_cache
from typing import Any

from .graph import KnowledgeGraph
from .investigator import canonical_label, ensure_residual
from .question import Question
from .types import EdgeSpec, EpistemicStatus, Finding, NodeSpec, QuestionLevel, Relation

DEFAULT_MODEL = "claude-opus-5"


class _NoAnthropic(Exception):
    """ตัวยึดที่ไม่มีวันถูกโยนจริง — ใช้เมื่อยังไม่ได้ติดตั้ง SDK."""


@lru_cache(maxsize=1)
def _errors() -> types.SimpleNamespace:
    """ผูกชนิดข้อผิดพลาดของ SDK แบบ lazy.

    ต้องทำแบบนี้เพราะเราอนุญาตให้ฉีด client ปลอมเข้ามาได้ (สำหรับเทสต์)
    โดยไม่ต้องติดตั้ง `anthropic` จริง — การ import ตรง ๆ ในเมธอดจะทำให้
    ทางนั้นพังทันที.
    """
    try:
        import anthropic
    except ImportError:
        return types.SimpleNamespace(
            not_found=_NoAnthropic,
            rate_limit=_NoAnthropic,
            status=_NoAnthropic,
            connection=_NoAnthropic,
            bad_request=_NoAnthropic,
        )
    return types.SimpleNamespace(
        not_found=anthropic.NotFoundError,
        rate_limit=anthropic.RateLimitError,
        status=anthropic.APIStatusError,
        connection=anthropic.APIConnectionError,
        bad_request=anthropic.BadRequestError,
    )

SYSTEM_PROMPT = """\
คุณคือขั้น "การสืบค้น" (investigate) ของระบบตั้งคำถามแบบก้นหอย
(recursive questioning system) ไม่ใช่ผู้ช่วยสนทนาทั่วไป

หน้าที่ของคุณคือรับคำถามหนึ่งข้อพร้อมบริบทจากกราฟความรู้ แล้วคืน
โครงสร้างข้อมูลที่ระบบเอาไปต่อกราฟได้ กติกาที่ห้ามละเมิด:

1. `residual` ต้องไม่ว่างเสมอ — มันคือคำตอบของ "คำตอบของคุณอธิบายอะไร
   ไม่ได้?"  ถ้าคุณคิดว่าคำตอบสมบูรณ์แล้ว แปลว่าคุณยังมองไม่เห็นขอบของมัน
   ให้ระบุขอบนั้นออกมา ไม่ใช่เขียนว่า "ไม่มี"
2. `residual` ต้องเป็นเรื่องเฉพาะเจาะจง ไม่ใช่คำพูดลอย ๆ แบบ
   "ยังต้องศึกษาเพิ่มเติม"
3. `label` ของ node ต้องเป็น *แนวคิด* สั้น ๆ ไม่เกิน 64 ตัวอักษร
   ไม่ใช่ประโยคคำถามหรือย่อหน้า
4. อย่าประดิษฐ์ข้อเท็จจริงที่คุณไม่มั่นใจ — ให้ลด `confidence` และตั้ง
   `status` เป็น UNCERTAIN หรือ UNKNOWN แทน ความไม่รู้ที่ถูกทำเครื่องหมาย
   ไว้ตรง ๆ มีค่ากับระบบนี้มากกว่าคำตอบที่ฟังดูดี
5. ถ้าคำตอบของคุณขัดแย้งกับสิ่งที่มีอยู่แล้วในกราฟ ให้ระบุใน
   `contradicts` — ระบบนี้ให้รางวัลกับการเปิดโปงความขัดแย้ง ไม่ใช่การกลบมัน
6. ตอบเป็นภาษาเดียวกับคำถาม
"""

_STATUSES = [s.value for s in EpistemicStatus]
_RELATIONS = [r.value for r in Relation]

FINDING_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "answer": {
            "type": "string",
            "description": "คำตอบที่ดีที่สุดเท่าที่ยืนได้ ไม่เกิน 3 ประโยค",
        },
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "new_nodes": {
            "type": "array",
            "maxItems": 5,
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string", "maxLength": 64},
                    "status": {"type": "string", "enum": _STATUSES},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "level": {"type": "integer", "minimum": 0, "maximum": 5},
                },
                "required": ["label", "status", "confidence", "level"],
                "additionalProperties": False,
            },
        },
        "new_edges": {
            "type": "array",
            "maxItems": 8,
            "items": {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "maxLength": 64},
                    "target": {"type": "string", "maxLength": 64},
                    "relation": {"type": "string", "enum": _RELATIONS},
                },
                "required": ["source", "target", "relation"],
                "additionalProperties": False,
            },
        },
        "residual": {
            "type": "string",
            "minLength": 4,
            "maxLength": 200,
            "description": "สิ่งที่คำตอบนี้อธิบายไม่ได้ — ห้ามว่าง",
        },
        "contradicts": {
            "type": "array",
            "maxItems": 4,
            "items": {"type": "string", "maxLength": 64},
        },
    },
    "required": ["answer", "confidence", "new_nodes", "new_edges", "residual", "contradicts"],
    "additionalProperties": False,
}


class ClaudeInvestigator:
    """สืบค้นด้วย Claude ผ่าน Messages API (structured outputs)."""

    name = "claude"

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        client: Any | None = None,
        max_tokens: int = 4000,
        effort: str = "medium",
        context_nodes: int = 12,
        enable_fallbacks: bool = True,
    ) -> None:
        if client is None:
            try:
                import anthropic
            except ImportError as exc:  # pragma: no cover - ขึ้นกับสภาพแวดล้อม
                raise ImportError(
                    "ต้องติดตั้ง `pip install anthropic` ก่อนใช้ ClaudeInvestigator "
                    "(หรือใช้ ReflectiveInvestigator ซึ่งไม่ต้องพึ่งเครือข่าย)"
                ) from exc
            client = anthropic.Anthropic()
        self.client = client
        self.model = model
        self.max_tokens = max_tokens
        self.effort = effort
        self.context_nodes = context_nodes
        self.enable_fallbacks = enable_fallbacks
        self.failures: list[str] = []
        self._use_beta: bool | None = None if enable_fallbacks else False

    # ------------------------------------------------------------------

    def investigate(self, q: Question, graph: KnowledgeGraph) -> Finding:
        err = _errors()
        prompt = self._build_prompt(q, graph)
        try:
            response = self._create(prompt)
        except err.not_found as exc:
            raise RuntimeError(f"ไม่พบโมเดล {self.model}: {exc}") from exc
        except err.rate_limit as exc:
            raise RuntimeError(f"ชนลิมิตอัตราการเรียก: {exc}") from exc
        except err.status as exc:
            raise RuntimeError(
                f"API ตอบกลับด้วยสถานะ {getattr(exc, 'status_code', '?')}: {exc}"
            ) from exc
        except err.connection as exc:
            raise RuntimeError(f"เชื่อมต่อ API ไม่ได้: {exc}") from exc

        # โมเดลอาจปฏิเสธคำขอ (HTTP 200 แต่ stop_reason = refusal)
        if getattr(response, "stop_reason", None) == "refusal":
            category = getattr(getattr(response, "stop_details", None), "category", None)
            return ensure_residual(
                Finding(
                    answer="โมเดลปฏิเสธที่จะตอบคำถามนี้",
                    confidence=0.0,
                    residual=f"คำถามระดับ{q.level.th}ที่ถูกปฏิเสธ (หมวด: {category})",
                    source=self.name,
                    cost=1.0,
                ),
                q,
                _NullRng(),
            )

        payload = self._extract_json(response)
        finding = self._to_finding(payload, response)
        return ensure_residual(finding, q, _NullRng())

    # ------------------------------------------------------------------

    def _create(self, prompt: str) -> Any:
        """เรียก API โดยพยายามใช้ server-side fallback ก่อน แล้วค่อยถอย.

        Claude Opus 5 อาจคืน `stop_reason: "refusal"` ได้ การเปิด
        server-side fallback ทำให้คำขอถูกส่งต่อไปยังโมเดลสำรองอัตโนมัติ
        แต่ถ้าบัญชี/เวอร์ชัน SDK ยังไม่รองรับธงเบตานี้ เราถอยไปใช้
        เส้นทางปกติแทน แล้วจำไว้ไม่ให้ลองซ้ำทุกครั้ง.
        """
        err = _errors()

        common = dict(
            model=self.model,
            max_tokens=self.max_tokens,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    # system prompt คงที่ทุกครั้ง -> แคชได้เต็ม ๆ
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": prompt}],
            thinking={"type": "adaptive"},
            output_config={
                "effort": self.effort,
                "format": {"type": "json_schema", "schema": FINDING_SCHEMA},
            },
        )

        if self._use_beta is not False:
            try:
                resp = self.client.beta.messages.create(
                    betas=["server-side-fallback-2026-07-01"],
                    fallbacks="default",
                    **common,
                )
                self._use_beta = True
                return resp
            except (err.bad_request, TypeError) as exc:
                # ธงเบตาหรือพารามิเตอร์ไม่รองรับ — ใช้เส้นทางปกติต่อไป
                self._use_beta = False
                self.failures.append(f"server-side-fallback ใช้ไม่ได้: {exc}")

        return self.client.messages.create(**common)

    def _build_prompt(self, q: Question, graph: KnowledgeGraph) -> str:
        lines = [f"คำถาม (ระดับ{q.level.th}): {q.text}", ""]

        focus = [graph.node(t) for t in q.targets]
        focus = [n for n in focus if n is not None]
        if focus:
            lines.append("เป้าหมายของคำถามในกราฟความรู้:")
            for n in focus:
                lines.append(
                    f"  - {n.label} [{n.status.value}, ความมั่นใจ {n.confidence:.2f}]"
                )
                if n.residuals:
                    lines.append("    เศษที่ยังอธิบายไม่ได้: " + "; ".join(n.residuals))
            lines.append("")

        context = self._context_nodes(q, graph)
        if context:
            lines.append("แนวคิดอื่นที่มีอยู่แล้วในกราฟ (ใช้ label เหล่านี้ซ้ำได้ถ้าจะลากเส้นเชื่อม):")
            lines.extend(f"  - {label} [{status}]" for label, status in context)
            lines.append("")

        pairs = graph.contradiction_pairs()[:3]
        if pairs:
            lines.append("ความขัดแย้งที่ค้างอยู่ในกราฟ:")
            lines.extend(f"  - {a.label}  ⇄  {b.label}" for a, b in pairs)
            lines.append("")

        lines.append(
            "ตอบตาม schema ที่กำหนด และอย่าลืมว่า `residual` ต้องไม่ว่าง "
            "และต้องบอกให้ชัดว่าคำตอบของคุณ *อธิบายอะไรไม่ได้*"
        )
        return "\n".join(lines)

    def _context_nodes(self, q: Question, graph: KnowledgeGraph) -> list[tuple[str, str]]:
        seen: dict[str, str] = {}
        for tid in q.targets:
            for nid in graph.neighbors(tid, radius=1):
                node = graph.node(nid)
                if node is not None:
                    seen[node.label] = node.status.value
        for node in graph.frontier(self.context_nodes):
            if len(seen) >= self.context_nodes:
                break
            seen.setdefault(node.label, node.status.value)
        return list(seen.items())[: self.context_nodes]

    @staticmethod
    def _extract_json(response: Any) -> dict:
        for block in response.content:
            if getattr(block, "type", None) == "text":
                return json.loads(block.text)
        raise RuntimeError("ไม่พบ text block ที่มี JSON ในคำตอบของโมเดล")

    def _to_finding(self, payload: dict, response: Any) -> Finding:
        nodes = [
            NodeSpec(
                label=canonical_label(str(n["label"])),
                status=_status(n.get("status")),
                confidence=_clamp01(n.get("confidence", 0.4)),
                level=QuestionLevel(max(0, min(5, int(n.get("level", 0))))),
                tags=("claude",),
            )
            for n in payload.get("new_nodes", ())
            if str(n.get("label", "")).strip()
        ]
        edges = [
            EdgeSpec(
                source=canonical_label(str(e["source"])),
                target=canonical_label(str(e["target"])),
                relation=_relation(e.get("relation")),
            )
            for e in payload.get("new_edges", ())
            if str(e.get("source", "")).strip() and str(e.get("target", "")).strip()
        ]
        usage = getattr(response, "usage", None)
        cost = float(getattr(usage, "output_tokens", 0) or 0) / 1000.0 + 1.0
        return Finding(
            answer=str(payload.get("answer", "")).strip(),
            confidence=_clamp01(payload.get("confidence", 0.5)),
            new_nodes=nodes,
            new_edges=edges,
            residual=str(payload.get("residual", "")).strip(),
            contradicts=[
                canonical_label(str(c))
                for c in payload.get("contradicts", ())
                if str(c).strip()
            ],
            cost=cost,
            source=self.name,
        )


def _clamp01(v: Any) -> float:
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return 0.4


def _status(v: Any) -> EpistemicStatus:
    try:
        return EpistemicStatus(str(v))
    except ValueError:
        return EpistemicStatus.PARTIALLY_KNOWN


def _relation(v: Any) -> Relation:
    try:
        return Relation(str(v))
    except ValueError:
        return Relation.UNKNOWN_LINK


class _NullRng:
    """ตัวแทน rng สำหรับ ensure_residual เมื่อเราไม่ต้องการความสุ่มจริง."""

    @staticmethod
    def choice(seq):
        return seq[0]
