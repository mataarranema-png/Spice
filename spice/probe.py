"""พีชคณิตของการถาม — คำถามในฐานะ *โครงสร้าง* ไม่ใช่ประโยค.

ข้อจำกัดที่ลึกที่สุดของเครื่องยนต์เดิมคือคำถามเป็นสตริง พื้นที่คำถามทั้งหมด
จึงถูกล้อมด้วยประโยคที่มนุษย์เขียนไว้ล่วงหน้า การกลายพันธุ์ทำได้แค่ระดับสำนวน
— เปลี่ยนคำ ไม่เปลี่ยนรูปของการถาม

ที่นี่คำถามคือต้นไม้ของตัวดำเนินการ:

    BOUND(x)                      ขอบของ x อยู่ตรงไหน
    REFLECT(BOUND(x))             เกณฑ์อะไรทำให้เรานับว่านั่นคือขอบ
    LIMIT(REFLECT(BOUND(x)))      อะไรทำให้ตอบเกณฑ์นั้นไม่ได้
    COMPARE(MECHANISM(a), MECHANISM(b))

ผลที่ตามมาสามอย่าง:

* **ระดับคำถามไม่ต้องประกาศอีกต่อไป** มันคำนวณได้จากรูปของต้นไม้ — จำนวนชั้น
  ที่พับกลับมาหาตัวการถามเอง
* **ความซ้ำวัดที่โครงสร้าง** ไม่ใช่ที่ตัวอักษร สองประโยคที่ต่างกันทุกคำแต่มีต้นไม้
  เดียวกัน คือคำถามเดียวกัน
* **ภาษาเป็นแค่ผิว** ต้นไม้ถามกับโดเมนที่ไม่มีคำศัพท์เลยก็ได้ การ render เป็น
  ภาษาไทยเป็นเรื่องของมนุษย์ที่มาอ่านทีหลัง ไม่ใช่เงื่อนไขของการถาม
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterator

from .types import QuestionLevel, stable_id


class Kind(Enum):
    """ตัวดำเนินการรับอะไรเป็นอาร์กิวเมนต์ได้บ้าง."""

    OBJECT = "object"      # รับได้เฉพาะสิ่งในโลก
    PROBE = "probe"        # รับได้เฉพาะคำถามอื่น (ตัวยกระดับ)
    EITHER = "either"      # รับได้ทั้งสองอย่าง


@dataclass(frozen=True)
class OpSpec:
    key: str
    arity: int
    kind: Kind
    base: int              # ระดับพื้นของตัวดำเนินการนี้
    lift: int              # ยกระดับของอาร์กิวเมนต์ขึ้นกี่ชั้น
    th: tuple[str, ...]    # ผิวภาษาไทย (ใช้ {0} {1} แทนอาร์กิวเมนต์)
    en: tuple[str, ...] = ()
    floor: int = 0         # ระดับต่ำสุดที่ตัวดำเนินการนี้พาไปถึงเสมอ
    nom_th: str = ""       # รูป *วลีนาม* — ใช้เมื่อคำถามนี้ไปเป็นอาร์กิวเมนต์ของอีกคำถาม
    nom_en: str = ""

    def surface(self, lang: str) -> tuple[str, ...]:
        return self.en if lang == "en" and self.en else self.th

    def nominal(self, lang: str) -> str:
        """ภาษาจริงประกอบประโยคซ้อนด้วยการแปลงประโยคเป็นวลีนาม ไม่ใช่ด้วยการ
        ยกทั้งประโยคมาใส่เครื่องหมายคำพูด  ถ้าไม่มีรูปนาม การซ้อนสามชั้นจะได้
        ประโยคที่ไม่มีมนุษย์คนไหนอ่านจบ."""
        if lang == "en" and self.nom_en:
            return self.nom_en
        return self.nom_th or (self.th[0] if self.th else "{0}")


# ── ตัวดำเนินการฐาน ───────────────────────────────────────────────
# base คือระดับที่มันอยู่ถ้าใช้เดี่ยว ๆ  lift คือมันดันอาร์กิวเมนต์ขึ้นกี่ชั้น
_OPS: dict[str, OpSpec] = {}


def _op(spec: OpSpec) -> OpSpec:
    _OPS[spec.key] = spec
    return spec


IDENTIFY = _op(OpSpec("identify", 1, Kind.OBJECT, 0, 0,
    ("{0} คืออะไรกันแน่ และอะไรทำให้มันต่างจากสิ่งที่ใกล้เคียงที่สุด?",
     "อะไรคือสิ่งที่สังเกตได้จริงเกี่ยวกับ {0} และอะไรที่เป็นแค่การอนุมาน?"),
    ("What exactly is {0}, and what separates it from its nearest neighbour?",),
    nom_th="สิ่งที่ {0} เป็น"))

DECOMPOSE = _op(OpSpec("decompose", 1, Kind.EITHER, 0, 0,
    ("ถ้าถอด {0} ออกเป็นชิ้นส่วน ชิ้นไหนที่ขาดไม่ได้?",
     "{0} ประกอบขึ้นจากอะไร และชิ้นส่วนเหล่านั้นมาก่อนหรือมาทีหลัง?"),
    ("If {0} were decomposed, which part is indispensable?",),
    nom_th="ชิ้นส่วนที่ประกอบเป็น {0}"))

EXTENT = _op(OpSpec("extent", 1, Kind.EITHER, 1, 0,
    ("{0} มีได้มากน้อยแค่ไหน และวัดเป็นหน่วยอะไร?",
     "{0} เปลี่ยนแบบต่อเนื่อง หรือกระโดดเป็นขั้น?"),
    ("How much {0} can there be, and in what units?",),
    nom_th="ขนาดและหน่วยวัดของ {0}"))

BOUND = _op(OpSpec("bound", 1, Kind.EITHER, 0, 0,
    ("ขอบเขตของ {0} สิ้นสุดตรงไหน และอะไรอยู่นอกขอบนั้น?",
     "อะไรคือค่าที่น้อยที่สุดและมากที่สุดที่ {0} ยังเป็น {0} อยู่?"),
    ("Where does {0} end, and what lies outside that edge?",),
    nom_th="ขอบเขตของ {0}"))

MECHANISM = _op(OpSpec("mechanism", 1, Kind.EITHER, 1, 0,
    ("กลไกอะไรที่ทำให้ {0} เกิดขึ้น และกลไกนั้นต้องการเงื่อนไขอะไรบ้าง?",
     "อะไรคือขั้นตอนที่เล็กที่สุดที่ยังทำให้ {0} เป็น {0} อยู่?"),
    ("What mechanism produces {0}, and what does it require?",),
    nom_th="กลไกที่ทำให้ {0} เกิดขึ้น"))

CONDITION = _op(OpSpec("condition", 1, Kind.EITHER, 1, 0,
    ("{0} ต้องการอะไรจึงจะเกิดได้ และเงื่อนไขไหนที่ขาดไม่ได้จริง ๆ?",),
    ("What does {0} require, and which condition is truly indispensable?",),
    nom_th="เงื่อนไขที่ {0} ต้องการ"))

INVARIANT = _op(OpSpec("invariant", 1, Kind.EITHER, 1, 0,
    ("อะไรใน {0} ที่ไม่เปลี่ยน ไม่ว่าอย่างอื่นจะเปลี่ยนไปแค่ไหน?",),
    ("What in {0} stays fixed however much else changes?",),
    nom_th="สิ่งที่ไม่เปลี่ยนใน {0}"))

NEGATE = _op(OpSpec("negate", 1, Kind.EITHER, 2, 0,
    ("ถ้า {0} ไม่จริง อะไรที่ยังคงจริงอยู่ และอะไรที่พังตามไปด้วย?",
     "อะไรจะต้องเกิดขึ้น เราถึงจะยอมทิ้ง {0}?"),
    ("If {0} were false, what would still hold and what would collapse?",),
    nom_th="สิ่งที่ยังจริงอยู่ถ้า {0} ไม่จริง"))

PRESUPPOSE = _op(OpSpec("presuppose", 1, Kind.EITHER, 2, 0,
    ("เราสมมติอะไรไว้เงียบ ๆ ตอนที่พูดถึง {0}?",
     "ข้อสมมติข้อไหนเกี่ยวกับ {0} ที่ไม่เคยถูกทดสอบเลยสักครั้ง?"),
    ("What are we silently assuming when we speak of {0}?",),
    nom_th="ข้อสมมติเบื้องหลัง {0}"))

COMPARE = _op(OpSpec("compare", 2, Kind.EITHER, 2, 0,
    ("{0} กับ {1} — อันไหนอธิบายได้มากกว่า และวัดด้วยอะไร?",
     "อะไรที่ {0} มี แต่ {1} ไม่มี และความต่างนั้นสำคัญหรือแค่บังเอิญ?"),
    ("{0} versus {1} — which accounts for more, measured how?",),
    nom_th="การเทียบระหว่าง {0} กับ {1}"))

BRIDGE = _op(OpSpec("bridge", 2, Kind.EITHER, 1, 0,
    ("อะไรเชื่อม {0} กับ {1} เข้าด้วยกัน ทั้งที่ยังไม่มีใครลากเส้น?",
     "ถ้า {0} กับ {1} เป็นอาการสองอย่างของสาเหตุเดียวกัน สาเหตุนั้นคืออะไร?"),
    ("What connects {0} and {1} that nobody has drawn yet?",),
    nom_th="สิ่งที่เชื่อม {0} กับ {1}"))

TENSION = _op(OpSpec("tension", 2, Kind.EITHER, 2, 0,
    ("{0} กับ {1} ขัดแย้งกัน — เงื่อนไขแบบไหนที่ทำให้ทั้งสองจริงพร้อมกันได้?",
     "ถ้าต้องทิ้งอย่างหนึ่งระหว่าง {0} กับ {1} เราจะเสียความสามารถอธิบายอะไรไป?"),
    ("{0} and {1} conflict — under what conditions could both hold?",),
    nom_th="ความขัดแย้งระหว่าง {0} กับ {1}"))

# ── ตัวยกระดับ: รับได้เฉพาะคำถามอื่น ระดับจึงงอกจากรูป ไม่ใช่จากการประกาศ ──
REFLECT = _op(OpSpec("reflect", 1, Kind.PROBE, 0, 1,
    ("เกณฑ์อะไรที่ทำให้เรานับว่าคำตอบของ «{0}» เป็นคำอธิบายที่ใช้ได้?",
     "เราจะรู้ได้อย่างไรว่าคำตอบของ «{0}» ผิด?"),
    ("What makes an answer to «{0}» count as an explanation?",),
    nom_th="เกณฑ์ที่ใช้ตัดสิน{0}", floor=3))

ORIGIN = _op(OpSpec("origin", 1, Kind.PROBE, 0, 1,
    ("คำถาม «{0}» มาจากวิธีมองแบบไหน และวิธีมองนั้นตัดอะไรทิ้งไปบ้าง?",),
    ("What way of seeing produces «{0}», and what does it exclude?",),
    nom_th="วิธีมองที่ผลิต{0}", floor=4))

LIMIT = _op(OpSpec("limit", 1, Kind.PROBE, 0, 2,
    ("อะไรที่ทำให้ผู้ถามตอบ «{0}» ไม่ได้ — และข้อจำกัดนั้นตรวจพบได้ด้วยตัวเองไหม?",),
    ("What stops the asker from answering «{0}», and is that limit self-detectable?",),
    nom_th="ข้อจำกัดของผู้ถามต่อ{0}", floor=5))

BASE_OPS = tuple(_OPS)


def spec(key: str) -> OpSpec | None:
    return _OPS.get(key)


def register(spec_: OpSpec) -> OpSpec:
    """ผูกตัวดำเนินการใหม่เข้ากับพีชคณิต — ใช้ตอนไวยากรณ์งอกเอง."""
    _OPS[spec_.key] = spec_
    return spec_


def known_ops() -> tuple[str, ...]:
    return tuple(_OPS)


# ── ต้นไม้คำถาม ────────────────────────────────────────────────────

@dataclass(frozen=True)
class Ref:
    """การอ้างถึงสิ่งในโลก — เป็นแค่ id ไม่ใช่คำ.

    ตัวโดเมนเป็นคนบอกว่า id นี้ *เรียกว่าอะไร* ถ้ามันมีชื่อเรียกให้เลย
    โดเมนที่ไม่มีภาษาก็ไม่ต้องมี.
    """

    id: str
    hint: str = ""        # ชื่อสำหรับมนุษย์อ่าน ถ้ามี — ไม่ใช่ส่วนหนึ่งของอัตลักษณ์

    def __str__(self) -> str:
        return self.hint or self.id


@dataclass(frozen=True)
class Probe:
    op: str
    args: tuple["Probe | Ref", ...]

    # ---------- อัตลักษณ์เชิงโครงสร้าง ----------

    @property
    def signature(self) -> str:
        """อัตลักษณ์ที่ไม่ขึ้นกับภาษาเลย — สองประโยคที่ต่างกันทุกคำแต่มีต้นไม้
        เดียวกัน คือคำถามเดียวกัน."""
        parts = []
        for a in self.args:
            parts.append(a.signature if isinstance(a, Probe) else f"#{a.id}")
        return f"{self.op}({','.join(parts)})"

    @property
    def id(self) -> str:
        return stable_id(self.signature)

    @property
    def shape(self) -> str:
        """รูปของคำถามโดยไม่สนว่าถามถึงอะไร — ใช้ดูว่าไวยากรณ์งอกไปถึงไหน."""
        parts = []
        for a in self.args:
            parts.append(a.shape if isinstance(a, Probe) else "·")
        return f"{self.op}({','.join(parts)})"

    # ---------- โครงสร้าง ----------

    @property
    def depth(self) -> int:
        inner = [a.depth for a in self.args if isinstance(a, Probe)]
        return 1 + max(inner, default=0)

    def walk(self) -> Iterator["Probe"]:
        yield self
        for a in self.args:
            if isinstance(a, Probe):
                yield from a.walk()

    def refs(self) -> tuple[Ref, ...]:
        out: list[Ref] = []
        for p in self.walk():
            out.extend(a for a in p.args if isinstance(a, Ref))
        return tuple(out)

    @property
    def level(self) -> QuestionLevel:
        """ระดับ *คำนวณจากรูป* ไม่ใช่จากการประกาศ.

        ตัวยกระดับแต่ละชั้นดันคำถามออกห่างจากวัตถุไปอีกขั้น ระดับจึงเป็นผลของ
        โครงสร้าง — และคำถามที่ประกอบขึ้นมาใหม่ได้ระดับของมันเองโดยอัตโนมัติ
        โดยไม่มีใครต้องกำหนดให้.
        """
        s = spec(self.op)
        if s is None:
            return QuestionLevel.OBJECT
        inner = max(
            (a.level for a in self.args if isinstance(a, Probe)),
            default=None,
        )
        base = s.base if inner is None else max(s.base, int(inner))
        return QuestionLevel(max(0, min(5, max(base + s.lift, s.floor))))

    @property
    def is_wellformed(self) -> bool:
        s = spec(self.op)
        if s is None or len(self.args) != s.arity:
            return False
        for a in self.args:
            if s.kind is Kind.PROBE and not isinstance(a, Probe):
                return False
            if s.kind is Kind.OBJECT and not isinstance(a, Ref):
                return False
            if isinstance(a, Probe) and not a.is_wellformed:
                return False
        return True

    # ---------- ผิว ----------

    def render(self, lang: str = "th", variant: int = 0) -> str:
        """แปลงเป็นประโยคสำหรับมนุษย์ — เป็นตัวเลือก ไม่ใช่เงื่อนไข.

        โดเมนที่ไม่มีภาษาไม่ต้องเรียกเมธอดนี้เลย ต้นไม้ทำงานได้โดยไม่มีผิว.
        """
        s = spec(self.op)
        if s is None:
            return self.signature
        forms = s.surface(lang)
        tmpl = forms[variant % len(forms)] if forms else self.signature
        rendered: list[str] = []
        for a in self.args:
            if isinstance(a, Probe):
                rendered.append(a.nominalise(lang))
            else:
                rendered.append(str(a))
        try:
            return tmpl.format(*rendered)
        except (IndexError, KeyError):
            return self.signature

    def nominalise(self, lang: str = "th") -> str:
        """รูปวลีนามของคำถามนี้ ใช้ตอนมันไปเป็นอาร์กิวเมนต์ของคำถามอื่น."""
        s = spec(self.op)
        if s is None:
            return self.signature
        parts = [
            a.nominalise(lang) if isinstance(a, Probe) else str(a) for a in self.args
        ]
        try:
            return s.nominal(lang).format(*parts)
        except (IndexError, KeyError):
            return self.signature

    # ---------- persistence ----------

    def to_dict(self) -> dict:
        return {
            "op": self.op,
            "args": [
                a.to_dict() if isinstance(a, Probe) else {"ref": a.id, "hint": a.hint}
                for a in self.args
            ],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Probe":
        args: list[Probe | Ref] = []
        for a in d.get("args", ()):
            if "ref" in a:
                args.append(Ref(a["ref"], a.get("hint", "")))
            else:
                args.append(cls.from_dict(a))
        return cls(op=d["op"], args=tuple(args))


def probe(op: str, *args: "Probe | Ref") -> Probe:
    return Probe(op=op, args=tuple(args))
