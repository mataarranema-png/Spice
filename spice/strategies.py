"""ยุทธวิธีการตั้งคำถาม — และการที่มัน *กลายพันธุ์ได้*.

Strategy หนึ่งตัว = (แหล่งเป้าหมายในกราฟ) + (แม่แบบคำถาม) + (ระดับ).
สิ่งที่ทำให้ระบบนี้ไม่ใช่ template engine ธรรมดาคือ Strategy เป็น *ข้อมูล*
ไม่ใช่โค้ด: มันถูก mutate, ผสมข้าม, ปลดระวาง และ *ให้กำเนิดตัวใหม่จาก
จุดบอดที่ระบบตรวจพบในตัวเอง* แล้วเซฟลงดิสก์ — รอบถัดไประบบจึงโหลด
"ตัวเองรุ่นใหม่" ขึ้นมาทำงาน ไม่ใช่ตัวเดิม.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Any, Callable

from .graph import KnowledgeGraph, Node
from .question import Question, QuestionLedger
from .types import QuestionLevel, stable_id

# แหล่งเป้าหมายที่ Strategy ดึงจากกราฟได้
# สระที่มอง (WIDE) กว้างกว่าจำนวนที่หยิบจริง (NARROW) มาก — ความต่างนี้
# คือสิ่งที่ทำให้พื้นที่คำถามโตตามกราฟแทนที่จะตันอยู่ที่ยอดเดิม
WIDE = 48
NARROW = 8

SOURCES = (
    "frontier",        # node ที่ไม่แน่นอนที่สุด
    "unexplained",     # node ที่ไม่มีอะไรอธิบาย
    "contradiction",   # คู่ที่ขัดแย้งกัน
    "hole",            # คู่ที่ "ควรเกี่ยวกัน" แต่ไม่มีเส้นทางถึงกัน
    "residual",        # เศษที่คำตอบก่อนหน้าอธิบายไม่ได้
    "self",            # ข้อจำกัดของตัวระบบเอง
)


@dataclass
class GenerationContext:
    graph: KnowledgeGraph
    ledger: QuestionLedger
    epoch: int
    rng: random.Random
    lang: str = "th"
    limits: list[str] = field(default_factory=list)
    recent_answers: list[tuple[str, str]] = field(default_factory=list)
    budget_per_strategy: int = 3


@dataclass
class Strategy:
    name: str
    level: QuestionLevel
    source: str
    templates: dict[str, list[str]]
    generation: int = 0
    lineage: tuple[str, ...] = ()
    born_epoch: int = 0
    fitness: float = 0.5
    uses: int = 0
    wins: float = 0.0
    origin: str = "builtin"

    # ---------- การผลิตคำถาม ----------

    def _pick_templates(self, ctx: GenerationContext) -> list[str]:
        pool = self.templates.get(ctx.lang) or self.templates.get("th") or []
        if not pool:
            return []
        k = min(len(pool), ctx.budget_per_strategy)
        return ctx.rng.sample(pool, k)

    def generate(self, ctx: GenerationContext) -> list[Question]:
        slots = _collect_slots(self.source, ctx)
        if not slots:
            return []
        out: list[Question] = []
        templates = self._pick_templates(ctx)
        for tmpl in templates:
            for slot in slots[: ctx.budget_per_strategy]:
                text = _render(tmpl, slot)
                if not text:
                    continue
                q = Question(
                    text=text,
                    level=self.level,
                    strategy=self.name,
                    targets=tuple(slot.get("_ids", ())),
                    epoch=ctx.epoch,
                    subject=slot.get("_subject", slot.get("a", "")),
                )
                out.append(q)
        return out

    # ---------- persistence ----------

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "level": int(self.level),
            "source": self.source,
            "templates": self.templates,
            "generation": self.generation,
            "lineage": list(self.lineage),
            "born_epoch": self.born_epoch,
            "fitness": self.fitness,
            "uses": self.uses,
            "wins": self.wins,
            "origin": self.origin,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Strategy":
        return cls(
            name=d["name"],
            level=QuestionLevel(d["level"]),
            source=d["source"],
            templates={k: list(v) for k, v in d["templates"].items()},
            generation=d.get("generation", 0),
            lineage=tuple(d.get("lineage", ())),
            born_epoch=d.get("born_epoch", 0),
            fitness=d.get("fitness", 0.5),
            uses=d.get("uses", 0),
            wins=d.get("wins", 0.0),
            origin=d.get("origin", "builtin"),
        )


# ---------------------------------------------------------------- slots


# ชื่อ node ที่ระบบใช้แทน *ตัวมันเอง* ในกราฟความรู้ของมันเอง
SELF_NODE = "ระบบผู้ถามเอง"


def _sample(items: list, ctx: "GenerationContext", k: int) -> list:
    """สุ่มเลือกแบบถ่วงน้ำหนักจากสระที่กว้างกว่า k มาก.

    ถ้าหยิบ "k อันดับแรก" แบบตายตัวทุกรอบ พื้นที่คำถามจะหยุดโตทันทีที่
    กราฟโตเกิน k: กราฟมี 200 node แต่ generator เห็นอยู่ 8 อันเดิม
    ผลคือคำถามซ้ำ ถูกกรองทิ้ง แล้วระบบก็ประกาศว่า "อิ่มตัว" ทั้งที่ยังไม่ได้
    มองอะไรเลย.  การสุ่มถ่วงน้ำหนักทำให้พื้นที่คำถามโตตามกราฟ.
    """
    if len(items) <= k:
        return list(items)
    pool = list(items)
    weights = [max(0.05, w) for w in (_slot_weight(x) for x in pool)]
    out = []
    for _ in range(k):
        total = sum(weights)
        r = ctx.rng.random() * total
        acc = 0.0
        for i, w in enumerate(weights):
            acc += w
            if acc >= r:
                break
        out.append(pool.pop(i))
        weights.pop(i)
    return out


def _slot_weight(item: Any) -> float:
    if isinstance(item, Node):
        return item.uncertainty + 0.1
    if isinstance(item, tuple) and item and isinstance(item[0], Node):
        return item[0].uncertainty + 0.1
    return 1.0


def _node_slot(n: Node) -> dict[str, Any]:
    return {"a": n.label, "status": n.status.value, "_ids": (n.id,), "_subject": n.label}


def _collect_slots(source: str, ctx: GenerationContext) -> list[dict[str, Any]]:
    g = ctx.graph
    if source == "frontier":
        return [_node_slot(n) for n in _sample(g.frontier(WIDE), ctx, NARROW)]
    if source == "unexplained":
        return [_node_slot(n) for n in _sample(g.unexplained()[:WIDE], ctx, NARROW)]
    if source == "contradiction":
        return [
            {"a": a.label, "b": b.label, "_ids": (a.id, b.id), "_subject": a.label}
            for a, b in _sample(g.contradiction_pairs()[:WIDE], ctx, NARROW)
        ]
    if source == "hole":
        return [
            {"a": a.label, "b": b.label, "_ids": (a.id, b.id), "_subject": a.label}
            for a, b in _sample(g.structural_holes(WIDE // 2), ctx, NARROW)
        ]
    if source == "residual":
        return [
            {"a": n.label, "residual": r, "_ids": (n.id,), "_subject": n.label}
            for n, r in _sample(g.open_residuals(WIDE), ctx, NARROW)
        ]
    if source == "self":
        # คำถามถึงตัวเองผูกกับ node เดียวเสมอ — ระบบจึงสะสม *แบบจำลอง
        # ของตัวเอง* ไว้ในกราฟความรู้เดียวกับที่ใช้เก็บความรู้เรื่องโลก
        return [
            {"a": SELF_NODE, "limit": lim, "_ids": (), "_subject": SELF_NODE}
            for lim in ctx.limits[:8]
        ]
    return []


def _render(tmpl: str, slot: dict[str, Any]) -> str:
    try:
        return tmpl.format(**{k: v for k, v in slot.items() if not k.startswith("_")})
    except (KeyError, IndexError):
        return ""


# ---------------------------------------------------------------- builtins

def builtin_strategies() -> list[Strategy]:
    """ประชากรรุ่นศูนย์ — ครอบทั้ง 6 ระดับตั้งแต่ต้น.

    ครอบทุกระดับไว้ก่อนไม่ใช่เพื่อความสมบูรณ์ แต่เพื่อให้ selector
    มีทางเลือกจริงตั้งแต่ epoch 0 มิฉะนั้นระบบจะติดอยู่ที่ระดับ OBJECT
    จนกว่าจะบังเอิญกลายพันธุ์ขึ้นไป.
    """
    return [
        Strategy(
            name="object_probe",
            level=QuestionLevel.OBJECT,
            source="frontier",
            templates={
                "th": [
                    "{a} คืออะไรกันแน่ และอะไรที่ทำให้มันต่างจากสิ่งที่ใกล้เคียงที่สุด?",
                    "{a} เกิดขึ้นได้อย่างไร?",
                    "อะไรคือสิ่งที่เราสังเกตได้จริงเกี่ยวกับ {a} และอะไรที่เราแค่อนุมาน?",
                ],
                "en": [
                    "What exactly is {a}, and what separates it from its nearest neighbour?",
                    "How does {a} come about?",
                    "What about {a} is observed, and what is merely inferred?",
                ],
            },
        ),
        Strategy(
            name="mechanism_probe",
            level=QuestionLevel.MECHANISM,
            source="unexplained",
            templates={
                "th": [
                    "กลไกอะไรที่ทำให้ {a} เกิดขึ้น และกลไกนั้นต้องการเงื่อนไขอะไรบ้าง?",
                    "ถ้าถอด {a} ออกเป็นชิ้นส่วน ชิ้นไหนที่ขาดไม่ได้?",
                    "อะไรคือขั้นตอนที่เล็กที่สุดที่ยังทำให้ {a} เป็น {a} อยู่?",
                ],
                "en": [
                    "What mechanism produces {a}, and what does that mechanism require?",
                    "If {a} were decomposed, which part is indispensable?",
                    "What is the smallest step that still leaves {a} being {a}?",
                ],
            },
        ),
        Strategy(
            name="assumption_probe",
            level=QuestionLevel.ASSUMPTION,
            source="frontier",
            templates={
                "th": [
                    "เราสมมติอะไรไว้เงียบ ๆ ตอนที่พูดว่า {a}?",
                    "ถ้า {a} เป็นเท็จ อะไรที่ยังคงจริงอยู่ และอะไรที่พังตามไปด้วย?",
                    "ข้อสมมติข้อไหนเกี่ยวกับ {a} ที่เราไม่เคยทดสอบเลยสักครั้ง?",
                ],
                "en": [
                    "What are we silently assuming when we say {a}?",
                    "If {a} were false, what would still hold and what would collapse?",
                    "Which assumption about {a} has never once been tested?",
                ],
            },
        ),
        Strategy(
            name="contradiction_probe",
            level=QuestionLevel.ASSUMPTION,
            source="contradiction",
            templates={
                "th": [
                    "{a} กับ {b} ขัดแย้งกัน — เงื่อนไขแบบไหนที่ทำให้ทั้งสองจริงพร้อมกันได้?",
                    "ความขัดแย้งระหว่าง {a} กับ {b} เกิดจากข้อเท็จจริง หรือเกิดจากนิยามที่เราเลือกใช้?",
                    "ถ้าต้องทิ้งอย่างหนึ่งระหว่าง {a} กับ {b} เราจะเสียความสามารถในการอธิบายอะไรไป?",
                ],
                "en": [
                    "{a} and {b} conflict — under what conditions could both hold?",
                    "Is the conflict between {a} and {b} factual, or an artefact of our definitions?",
                    "If we had to drop {a} or {b}, what explanatory power would we lose?",
                ],
            },
        ),
        Strategy(
            name="bridge_probe",
            level=QuestionLevel.MECHANISM,
            source="hole",
            templates={
                "th": [
                    "อะไรเชื่อม {a} กับ {b} เข้าด้วยกัน ทั้งที่ยังไม่มีใครลากเส้น?",
                    "ถ้า {a} กับ {b} เป็นอาการสองอย่างของสาเหตุเดียวกัน สาเหตุนั้นคืออะไร?",
                    "อะไรที่ {a} มี แต่ {b} ไม่มี และความต่างนั้นสำคัญหรือแค่บังเอิญ?",
                ],
                "en": [
                    "What connects {a} and {b} that nobody has drawn yet?",
                    "If {a} and {b} were two symptoms of one cause, what is that cause?",
                    "What does {a} have that {b} lacks — is that difference load-bearing or incidental?",
                ],
            },
        ),
        Strategy(
            name="residual_probe",
            level=QuestionLevel.META,
            source="residual",
            templates={
                "th": [
                    "คำตอบเรื่อง {a} ยังอธิบาย \"{residual}\" ไม่ได้ — อะไรที่หายไปจากแบบจำลอง?",
                    "\"{residual}\" เป็นข้อยกเว้น หรือเป็นสัญญาณว่าเราเข้าใจ {a} ผิดตั้งแต่ต้น?",
                    "ต้องเปลี่ยนอะไรในนิยามของ {a} จึงจะกลืน \"{residual}\" เข้าไปได้?",
                ],
                "en": [
                    "Our account of {a} still cannot explain \"{residual}\" — what is missing from the model?",
                    "Is \"{residual}\" an exception, or a sign we misunderstood {a} from the start?",
                    "What would have to change in the definition of {a} to absorb \"{residual}\"?",
                ],
            },
        ),
        Strategy(
            name="meta_probe",
            level=QuestionLevel.META,
            source="frontier",
            templates={
                "th": [
                    "ทำไมคำตอบเกี่ยวกับ {a} ถึงออกมาในรูปแบบนี้ และเกณฑ์อะไรที่ทำให้เรานับว่ามันเป็นคำอธิบาย?",
                    "เราจะรู้ได้อย่างไรว่าคำอธิบายเรื่อง {a} ผิด? ถ้าตอบไม่ได้ แปลว่าอะไร?",
                    "วิธีที่เราใช้ตอบเรื่อง {a} เอนเอียงไปทางคำตอบแบบไหนโดยอัตโนมัติ?",
                ],
                "en": [
                    "Why does our account of {a} take this shape, and what makes us count it as an explanation?",
                    "How would we know our explanation of {a} is wrong? If we can't say, what follows?",
                    "Which kinds of answer does our method for {a} favour automatically?",
                ],
            },
        ),
        Strategy(
            name="ontology_probe",
            level=QuestionLevel.ONTOLOGY,
            source="frontier",
            templates={
                "th": [
                    "{a} เป็นสิ่งที่มีอยู่จริง หรือเป็นหมวดหมู่ที่ผู้สังเกตสร้างขึ้นเพื่อความสะดวก?",
                    "ถ้าไม่มีใครมองอยู่ {a} ยังเป็น {a} อยู่หรือไม่ และคำถามนี้มีความหมายหรือเปล่า?",
                    "ขอบเขตของ {a} สิ้นสุดตรงไหน และใครเป็นคนตัดสินว่าตรงนั้นคือขอบ?",
                ],
                "en": [
                    "Is {a} a real thing, or a category the observer built for convenience?",
                    "With nobody observing, is {a} still {a} — and is that question even meaningful?",
                    "Where does {a} end, and who decides that is the boundary?",
                ],
            },
        ),
        Strategy(
            name="self_reference_probe",
            level=QuestionLevel.SELF_REFERENCE,
            source="self",
            templates={
                "th": [
                    "ระบบนี้มีข้อจำกัด \"{limit}\" — ข้อจำกัดนั้นทำให้มันมองไม่เห็นคำถามแบบไหน?",
                    "ระบบตรวจพบ \"{limit}\" ได้ด้วยเครื่องมือเดิม หรือจำเป็นต้องสร้างเครื่องมือใหม่?",
                    "ถ้าก้าวพ้น \"{limit}\" ไปได้ จุดบอดอันใหม่ที่จะเกิดขึ้นแทนคืออะไร?",
                ],
                "en": [
                    "This system is limited by \"{limit}\" — which questions does that make invisible?",
                    "Can \"{limit}\" be detected with the existing instruments, or is a new one required?",
                    "If \"{limit}\" were overcome, what new blind spot would take its place?",
                ],
            },
        ),
    ]


# ---------------------------------------------------------------- evolution ops

_MUTATION_PREFIXES_TH = (
    "ในกรณีที่สุดขั้วที่สุด ",
    "ถ้ามองย้อนกลับด้าน ",
    "โดยไม่ใช้คำศัพท์เดิมเลย ",
    "ถ้าจำกัดให้ตอบด้วยสิ่งที่วัดได้เท่านั้น ",
)
_MUTATION_SUFFIXES_TH = (
    " และคำตอบนั้นจะผิดได้ด้วยเงื่อนไขอะไร?",
    " แล้วอะไรที่คำตอบนั้นยังปล่อยทิ้งไว้?",
    " ใครจะไม่เห็นด้วยกับคำตอบนี้ และด้วยเหตุผลอะไร?",
)
_MUTATION_PREFIXES_EN = (
    "In the most extreme case, ",
    "Read in reverse, ",
    "Without reusing any of the existing vocabulary, ",
    "Restricted to measurable terms only, ",
)
_MUTATION_SUFFIXES_EN = (
    " And under what conditions would that answer be wrong?",
    " And what does that answer leave untouched?",
    " Who would disagree, and on what grounds?",
)


def mutate_strategy(
    parent: Strategy, rng: random.Random, epoch: int, *, level_drift: bool = True
) -> Strategy:
    """กลายพันธุ์: เลื่อนระดับ, สลับแหล่งเป้าหมาย, หรือแต่งแม่แบบใหม่."""
    level = parent.level
    if level_drift and rng.random() < 0.5:
        # ไม่เอนขึ้นหรือลง — แรงผลักไปหาระดับที่ยังไม่ถูกใช้อยู่ที่
        # `ledger.level_rarity` ในขั้นให้คะแนนอยู่แล้ว การเอนซ้ำตรงนี้
        # จะทำให้ประชากรทั้งหมดลอยไปกอง SELF_REFERENCE ภายในไม่กี่รอบ
        delta = rng.choice((-1, 1))
        level = QuestionLevel(
            max(int(QuestionLevel.OBJECT), min(int(QuestionLevel.SELF_REFERENCE), int(level) + delta))
        )

    source = parent.source
    if rng.random() < 0.25:
        source = rng.choice(SOURCES)

    templates: dict[str, list[str]] = {}
    for lang, pool in parent.templates.items():
        pre = _MUTATION_PREFIXES_TH if lang == "th" else _MUTATION_PREFIXES_EN
        suf = _MUTATION_SUFFIXES_TH if lang == "th" else _MUTATION_SUFFIXES_EN
        mutated = []
        for t in pool:
            r = rng.random()
            if r < 0.4:
                mutated.append(rng.choice(pre) + t[0].lower() + t[1:] if t else t)
            elif r < 0.8:
                mutated.append(t.rstrip("?").rstrip() + "?" + rng.choice(suf))
            else:
                mutated.append(t)
        templates[lang] = mutated

    templates = _retarget_templates(templates, parent.source, source)
    name = f"{_base_name(parent.name)}~m{parent.generation + 1}.{rng.randrange(1000):03d}"
    return Strategy(
        name=name,
        level=level,
        source=source,
        templates=templates,
        generation=parent.generation + 1,
        lineage=parent.lineage + (parent.name,),
        born_epoch=epoch,
        fitness=parent.fitness * 0.9,
        origin="mutation",
    )


def cross_strategies(
    a: Strategy, b: Strategy, rng: random.Random, epoch: int
) -> Strategy:
    """ผสมข้าม: เอาคำถามสองแบบมาต่อกันจนเกิดคำถามที่พ่อแม่ถามไม่ได้.

    ผลลัพธ์อยู่ *สูงกว่า* พ่อแม่หนึ่งระดับเสมอ เพราะการถามว่า
    "ถ้าถามสองอย่างนี้พร้อมกัน คำตอบจะเปลี่ยนไหม" คือการถามถึงตัว
    ความสัมพันธ์ระหว่างคำถาม ไม่ใช่ถามถึงวัตถุอีกต่อไป.
    """
    level = QuestionLevel(
        min(int(QuestionLevel.SELF_REFERENCE), max(int(a.level), int(b.level)) + 1)
    )
    source = a.source if rng.random() < 0.5 else b.source
    templates: dict[str, list[str]] = {}
    for lang in set(a.templates) & set(b.templates):
        joiner = (
            " — และถ้าถามพร้อมกันว่า "
            if lang == "th"
            else " — and if we simultaneously ask "
        )
        tail = (
            " คำตอบของข้อแรกยังยืนอยู่ได้ไหม?"
            if lang == "th"
            else " does the first answer still stand?"
        )
        pool = []
        for ta in a.templates[lang][:2]:
            for tb in b.templates[lang][:2]:
                pool.append(ta.rstrip("?").rstrip() + joiner + tb.rstrip("?").rstrip() + tail)
        templates[lang] = pool[:4]
    if not templates:
        templates = dict(a.templates)
    templates = _retarget_templates(templates, None, source)
    name = f"{_base_name(a.name)}×{_base_name(b.name)}@g{max(a.generation, b.generation) + 1}"
    return Strategy(
        name=name,
        level=level,
        source=source,
        templates=templates,
        generation=max(a.generation, b.generation) + 1,
        lineage=(a.name, b.name),
        born_epoch=epoch,
        fitness=(a.fitness + b.fitness) / 2 * 0.9,
        origin="crossover",
    )


def strategy_from_gap(gap: str, level: QuestionLevel, epoch: int, source: str = "self") -> Strategy:
    """สร้าง *เครื่องมือใหม่* จากจุดบอดที่ระบบตรวจพบในตัวเอง.

    นี่คือข้อ 7 ของสเปค: "สร้างเครื่องมือใหม่เมื่อเครื่องมือเดิมไม่พอ".
    ตัว gap มาจาก SelfModel ซึ่งดูสถิติของตัวระบบเอง ไม่ใช่ดูโลก.
    """
    slot = "{limit}" if source == "self" else "{a}"
    # ชื่อผูกกับ *ตัวจุดบอด* ไม่ใช่รอบที่ตรวจพบ: จุดบอดเดิมที่ยังไม่ถูกปิด
    # จะถูกตรวจพบซ้ำทุกรอบ ถ้าใส่เลขรอบลงในชื่อ ประชากรจะถูกท่วมด้วย
    # เครื่องมือที่เหมือนกันเป๊ะแต่ชื่อต่างกัน
    return Strategy(
        name=f"gap::{gap[:24]}#{stable_id(gap, size=3)}",
        level=level,
        source=source,
        templates={
            "th": [
                f"ระบบตรวจพบช่องโหว่ของตัวเอง: {gap} — " + slot + " ถูกมองข้ามเพราะอะไร?",
                f"ถ้า \"{gap}\" ไม่ใช่ความบังเอิญ แต่เป็นผลจากวิธีถามของระบบ ต้องเปลี่ยนวิธีถามอย่างไรกับ " + slot + "?",
                f"เครื่องมือแบบไหนที่ระบบยังไม่มี แล้วจะทำให้ \"{gap}\" หายไป เมื่อใช้กับ " + slot + "?",
            ],
            "en": [
                f"The system detected a gap in itself: {gap} — why was " + slot + " overlooked?",
                f"If \"{gap}\" is a product of how the system asks rather than chance, how must it ask about " + slot + " instead?",
                f"What instrument is missing that would dissolve \"{gap}\" when applied to " + slot + "?",
            ],
        },
        generation=0,
        lineage=("<self-model>",),
        born_epoch=epoch,
        fitness=0.6,
        origin="capability-gap",
    )


def _base_name(name: str) -> str:
    return name.split("~")[0].split("×")[0].split("@")[0]


_SLOT_TOKENS = ("{a}", "{b}", "{residual}", "{limit}", "{status}")


def _retarget_templates(
    templates: dict[str, list[str]], old_source: str | None, new_source: str
) -> dict[str, list[str]]:
    """ทำให้ตัวแปรในแม่แบบเข้ากับแหล่งเป้าหมายใหม่ มิฉะนั้น render จะพัง."""
    required = {
        "frontier": ("{a}",),
        "unexplained": ("{a}",),
        "contradiction": ("{a}", "{b}"),
        "hole": ("{a}", "{b}"),
        "residual": ("{a}", "{residual}"),
        "self": ("{limit}",),
    }[new_source]
    allowed = set(required)
    out: dict[str, list[str]] = {}
    for lang, pool in templates.items():
        fixed = []
        for t in pool:
            for tok in _SLOT_TOKENS:
                if tok in t and tok not in allowed:
                    t = t.replace(tok, required[0])
            if not any(tok in t for tok in required):
                t = f"{required[0]}: {t}"
            fixed.append(t)
        out[lang] = fixed
    return out
