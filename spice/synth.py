"""การประดิษฐ์ *ตัวดำเนินการฐาน* ขึ้นมาเอง — โดยค้นหาในปริภูมิของโปรแกรม.

ที่ผ่านมาการวัดถูกฮาร์ดโค้ดไว้สี่ห้าแบบ (คาบ บล็อกซ้ำ เอนโทรปี สมมาตร)
โครงสร้างชนิดอื่นระบบจึงมองไม่เห็นเลย และไวยากรณ์ที่งอกก็ยังตั้งอยู่บน
ตัวดำเนินการฐานที่มนุษย์เขียนทั้งหมด

กุญแจคือ: **การวัดคือโปรแกรม** ถ้าให้ระบบมีภาษาเชิงประกอบสำหรับสร้าง
ตัวทำนาย มันก็ค้นหาตัวทำนายที่ไม่มีใครเขียนไว้ได้ แล้วอันที่ได้ผลก็ถูก
*เลื่อนขั้นขึ้นเป็นตัวดำเนินการฐาน* ที่ไวยากรณ์เอาไปประกอบต่อได้เหมือนตัวอื่น

ตัวทำนายหนึ่งตัว = ฟังก์ชันคีย์ + ตารางที่เรียนจากข้อมูลเอง

    key(i) -> อะไรสักอย่างที่แฮชได้
    ทำนาย seq[i] ด้วยค่าที่พบบ่อยที่สุดของคีย์นั้น
    ต้นทุน (MDL) = ขนาดตาราง + จำนวนที่ทายผิด

ฟังก์ชันคีย์เป็นต้นไม้เล็ก ๆ ที่ประกอบได้ — และ `PAIR` ทำให้เอื้อมถึง
โครงสร้างร่วม เช่น `PAIR(POS_MOD 7, POS_MOD 13)` ซึ่งคือโครงสร้างที่แท้จริง
ของสัญญาณทดสอบ และไม่มีใครเขียนตัวตรวจจับแบบนั้นไว้เลย

ความซื่อสัตย์ข้อหนึ่ง: นี่คือการประดิษฐ์ *ภายในปริภูมิของคอมบิเนเตอร์*
ไม่ใช่การสร้างจากความว่างเปล่า — มนุษย์เขียนคอมบิเนเตอร์ ระบบเขียนการวัด
เหมือนที่มนุษย์เขียนตัวดำเนินการ ระบบเขียนการประกอบ  แต่มันลึกลงไปอีกชั้นจริง
และผลของมันคือระบบมองเห็นโครงสร้างชนิดที่ไม่มีใครคาดไว้ล่วงหน้า
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Iterable

def table_cap(n: int) -> int:
    """เพดานขนาดตาราง — สัมพัทธ์กับปริมาณข้อมูล ไม่ใช่ค่าคงที่.

    เพดานตายตัวที่ 64 ตัดโครงสร้างที่แท้จริงของสัญญาณทดสอบทิ้ง (7×13 = 91 ช่อง)
    ทั้งที่ MDL ลงโทษขนาดตารางอยู่แล้วในสมการ  เพดานมีไว้กันการจำข้อมูลดิบ
    และคุมเวลาคำนวณเท่านั้น จึงควรผูกกับจำนวนจุดที่มีให้เรียน.
    """
    return min(160, max(12, n // 4))


# ── คอมบิเนเตอร์ของฟังก์ชันคีย์ ────────────────────────────────────

@dataclass(frozen=True)
class Key:
    """ต้นไม้เล็ก ๆ ที่คำนวณคีย์ของตำแหน่งหนึ่ง — นี่คือส่วนที่ระบบประดิษฐ์."""

    kind: str
    a: int = 0
    b: int = 0
    left: "Key | None" = None
    right: "Key | None" = None

    @property
    def size(self) -> int:
        n = 1
        if self.left:
            n += self.left.size
        if self.right:
            n += self.right.size
        return n

    def __str__(self) -> str:
        if self.kind == "pair":
            return f"({self.left}×{self.right})"
        if self.kind == "pos_mod":
            return f"i%{self.a}"
        if self.kind == "block":
            return f"i÷{self.a}"
        if self.kind == "phase_parity":
            return f"⌊i/{self.a}⌋%2"
        if self.kind == "prev":
            return f"prev{self.a}"
        if self.kind == "delta":
            return "Δprev"
        if self.kind == "runlen":
            return "runlen"
        if self.kind == "const":
            return "·"
        return self.kind

    # -- การประเมินคีย์ที่ตำแหน่ง i ของลำดับ --
    def at(self, seq: list[int], i: int):
        k = self.kind
        if k == "const":
            return 0
        if k == "pos_mod":
            return i % self.a
        if k == "block":
            return i // max(1, self.a)
        if k == "phase_parity":
            return (i // max(1, self.a)) % 2
        if k == "prev":
            if i < self.a:
                return None
            return tuple(seq[i - self.a : i])
        if k == "delta":
            if i < 2:
                return None
            return seq[i - 1] - seq[i - 2]
        if k == "runlen":
            if i == 0:
                return 0
            n, j = 1, i - 1
            while j > 0 and seq[j] == seq[j - 1]:
                n += 1
                j -= 1
            return min(n, 8)
        if k == "pair":
            la = self.left.at(seq, i)
            rb = self.right.at(seq, i)
            if la is None or rb is None:
                return None
            return (la, rb)
        return None

    def to_dict(self) -> dict:
        d = {"kind": self.kind, "a": self.a, "b": self.b}
        if self.left:
            d["left"] = self.left.to_dict()
        if self.right:
            d["right"] = self.right.to_dict()
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Key":
        return cls(
            kind=d["kind"], a=d.get("a", 0), b=d.get("b", 0),
            left=cls.from_dict(d["left"]) if d.get("left") else None,
            right=cls.from_dict(d["right"]) if d.get("right") else None,
        )


@dataclass
class Fit:
    """ผลของการเอาตัวทำนายหนึ่งตัวไปวางบนข้อมูล."""

    key: Key
    accuracy: float
    bits: float
    table_size: int
    hits: tuple[int, ...]
    misses: tuple[int, ...]

    @property
    def bits_per_symbol(self) -> float:
        n = len(self.hits) + len(self.misses)
        return self.bits / n if n else float("inf")

    def to_dict(self) -> dict:
        return {
            "key": str(self.key), "accuracy": round(self.accuracy, 3),
            "bits": round(self.bits, 1), "table": self.table_size,
        }


def fit(seq: list[int], idx: Iterable[int], key: Key) -> Fit | None:
    """เรียนตารางจากข้อมูลเอง แล้ววัดว่าทายถูกกี่ตำแหน่งและใช้กี่บิต."""
    idx = list(idx)
    if len(idx) < 8:
        return None
    counts: dict = {}
    for i in idx:
        k = key.at(seq, i)
        if k is None:
            continue
        counts.setdefault(k, {})
        counts[k][seq[i]] = counts[k].get(seq[i], 0) + 1
    if not counts or len(counts) > table_cap(len(idx)):
        return None
    table = {k: max(c, key=c.get) for k, c in counts.items()}
    hits, misses = [], []
    for i in idx:
        k = key.at(seq, i)
        if k is not None and table.get(k) == seq[i]:
            hits.append(i)
        else:
            misses.append(i)
    alpha = max(2, len(set(seq[i] for i in idx)))
    # MDL: ตาราง + โครงสร้างของคีย์เอง + ข้อยกเว้นที่ต้องจำ
    bits = (
        len(table) * math.log2(alpha)
        + key.size * 4.0
        + len(misses) * math.log2(max(2, len(idx)))
    )
    return Fit(key, len(hits) / len(idx), bits, len(table), tuple(hits), tuple(misses))


# ── ปริภูมิที่ค้นหาได้ ─────────────────────────────────────────────

def primitives(n: int) -> list[Key]:
    out: list[Key] = [Key("const"), Key("delta"), Key("runlen")]
    out += [Key("prev", a=k) for k in (1, 2, 3)]
    top = max(3, min(n // 3, 30))
    out += [Key("pos_mod", a=p) for p in range(2, top + 1)]
    out += [Key("block", a=p) for p in (max(2, n // 8), max(3, n // 4), max(4, n // 2))]
    out += [Key("phase_parity", a=p) for p in (max(2, n // 8), max(3, n // 4))]
    return out


def search(
    seq: list[int], idx: Iterable[int], beam: int = 6, allow_pairs: bool = True
) -> list[Fit]:
    """ค้นหาตัวทำนายที่อธิบายข้อมูลนี้ได้ถูกที่สุด (สั้นที่สุด).

    ไม่มีใครเขียน "ตัวตรวจจับคาบ" หรือ "ตัวตรวจจับมาร์คอฟ" ไว้ ทั้งสองอย่าง
    เป็นแค่จุดสองจุดในปริภูมินี้ — และจุดอื่น ๆ ที่ไม่มีใครตั้งชื่อก็อยู่ในนั้นด้วย.
    """
    idx = list(idx)
    if len(idx) < 12:
        return []
    base = []
    for k in primitives(len(idx)):
        f = fit(seq, idx, k)
        if f is not None:
            base.append(f)
    if not base:
        return []
    base.sort(key=lambda f: f.bits)
    best = base[:beam]

    if allow_pairs:
        combined = []
        prims = primitives(len(idx))
        # จับคู่แบบ *มุ่งไปที่เศษ*: หาตัวที่อธิบาย "ตำแหน่งที่ตัวแรกทายผิด" ได้ดีที่สุด
        # แล้วค่อยจับคู่กัน  การจับคู่เฉพาะตัวที่เก่งเดี่ยว ๆ จะพลาดโครงสร้างร่วม
        # ทั้งหมด — เช่น i%13 ที่คะแนนเดี่ยวแย่มาก แต่พอคูณกับ i%7 แล้วอธิบาย
        # สัญญาณได้เกือบหมด  นี่คือตรรกะของก้นหอยเอง ใช้ซ้อนอยู่ข้างในการค้นหา
        for anchor in base[:3]:
            if not anchor.misses:
                continue
            partners = []
            for k in prims:
                f = fit(seq, anchor.misses, k)
                if f is not None:
                    partners.append((f.accuracy, k))
            partners.sort(key=lambda t: -t[0])
            for _, k in partners[:4]:
                if str(k) == str(anchor.key):
                    continue
                f = fit(seq, idx, Key("pair", left=anchor.key, right=k))
                if f is not None:
                    combined.append(f)
        # และคู่ของตัวที่เก่งเดี่ยว ๆ ด้วย เผื่อโครงสร้างเป็นแบบนั้นจริง
        pool = base[: max(3, beam // 2)]
        for i, x in enumerate(pool):
            for y in pool[i + 1 :]:
                f = fit(seq, idx, Key("pair", left=x.key, right=y.key))
                if f is not None:
                    combined.append(f)
        best = sorted(base + combined, key=lambda f: f.bits)[:beam]
    return best


# ── ตัวดำเนินการฐานที่ระบบประดิษฐ์ขึ้นแล้วเลื่อนขั้น ────────────────

@dataclass
class Invented:
    """การวัดที่ระบบค้นเจอเอง แล้วถูกเลื่อนขั้นเป็นตัวดำเนินการฐาน."""

    key_str: str
    key: Key
    coined: str
    born_epoch: int
    bits_per_symbol: float
    accuracy: float
    uses: int = 0

    @property
    def op_key(self) -> str:
        return f"synth::{self.coined}"

    def to_dict(self) -> dict:
        return {
            "key_str": self.key_str, "key": self.key.to_dict(), "coined": self.coined,
            "born_epoch": self.born_epoch, "bits_per_symbol": self.bits_per_symbol,
            "accuracy": self.accuracy, "uses": self.uses,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Invented":
        return cls(
            key_str=d["key_str"], key=Key.from_dict(d["key"]), coined=d["coined"],
            born_epoch=d["born_epoch"], bits_per_symbol=d["bits_per_symbol"],
            accuracy=d["accuracy"], uses=d.get("uses", 0),
        )


# หลักฐานที่แท้จริงของการเลื่อนขั้นคือ "ชนะซ้ำบนวัตถุมากกว่าหนึ่งชิ้น" ไม่ใช่
# ระยะห่างที่มนุษย์เดาไว้  ตั้ง margin ไว้ที่ 12% แล้ววัดได้ว่ามันตัดโครงสร้าง
# ที่แท้จริงของสัญญาณทดสอบทิ้ง (i%7×i%13 ดีกว่าเดิม 10% พอดี) จึงผ่อนระยะห่าง
# ลงมาแล้วให้ภาระการพิสูจน์ไปอยู่ที่การเกิดซ้ำแทน
PROMOTE_MARGIN = 0.95     # ต้องถูกกว่าเครื่องมือเดิมอย่างน้อยเท่านี้ (บิต/สัญลักษณ์)
PROMOTE_MIN_SEEN = 2      # และต้องชนะซ้ำ ไม่ใช่ชนะครั้งเดียวแล้วโชคดี


class Workshop:
    """โรงหลอมตัวดำเนินการฐาน.

    การวัดที่ค้นเจอแล้ว *อธิบายข้อมูลได้ถูกกว่าเครื่องมือที่มีอยู่* ซ้ำ ๆ
    จะถูกเลื่อนขั้นขึ้นเป็นตัวดำเนินการฐานตัวใหม่ พร้อมชื่อที่ระบบตั้งเอง
    หลังจากนั้นไวยากรณ์เอาไปประกอบและหลอมต่อได้เหมือนตัวฐานที่มนุษย์เขียนทุกประการ
    """

    def __init__(self, coin: Callable[[], str]) -> None:
        self.coin = coin
        self.invented: dict[str, Invented] = {}
        self.candidates: dict[str, dict] = {}

    @staticmethod
    def _is_novel(key: Key) -> bool:
        """โปรแกรมที่ *ซ้ำกับเครื่องมือที่มีอยู่แล้ว* ไม่ใช่การประดิษฐ์.

        `i%k` เดี่ยว ๆ คือสิ่งที่ตัวตรวจจับคาบทำอยู่แล้วทุกประการ การเลื่อนขั้น
        มันขึ้นเป็น "ตัวดำเนินการใหม่" คือการหลอกตัวเอง  สิ่งที่นับว่าใหม่จริง
        คือโครงสร้างร่วม (pair) หรือการมองบริบท/ผลต่าง/ความยาวช่วงซ้ำ ซึ่งไม่มี
        เครื่องมือเดิมตัวไหนเห็น
        """
        return key.kind != "pos_mod"

    def consider(self, f: Fit, baseline_bps: float, epoch: int) -> "Invented | None":
        """เสนอผลการค้นหาเข้าพิจารณา — เลื่อนขั้นเมื่อมันพิสูจน์ตัวเองแล้ว."""
        if not self._is_novel(f.key):
            return None
        ks = str(f.key)
        if any(inv.key_str == ks for inv in self.invented.values()):
            return None
        if baseline_bps <= 0 or f.bits_per_symbol > baseline_bps * PROMOTE_MARGIN:
            return None
        rec = self.candidates.setdefault(
            ks, {"seen": 0, "best": f.bits_per_symbol, "acc": f.accuracy, "key": f.key}
        )
        rec["seen"] += 1
        rec["best"] = min(rec["best"], f.bits_per_symbol)
        rec["acc"] = max(rec["acc"], f.accuracy)
        if rec["seen"] < PROMOTE_MIN_SEEN:
            return None

        inv = Invented(
            key_str=ks, key=rec["key"], coined=self.coin().strip("⟦⟧"),
            born_epoch=epoch, bits_per_symbol=rec["best"], accuracy=rec["acc"],
        )
        self.invented[inv.op_key] = inv
        self.candidates.pop(ks, None)
        _register_operator(inv)
        return inv

    def get(self, op_key: str) -> "Invented | None":
        return self.invented.get(op_key)

    def stats(self) -> dict:
        return {"invented": len(self.invented), "candidates": len(self.candidates)}

    def to_dict(self) -> dict:
        return {"invented": [i.to_dict() for i in self.invented.values()]}

    @classmethod
    def from_dict(cls, d: dict, coin: Callable[[], str]) -> "Workshop":
        w = cls(coin)
        for row in d.get("invented", ()):
            inv = Invented.from_dict(row)
            w.invented[inv.op_key] = inv
            _register_operator(inv)
        return w


def _register_operator(inv: Invented) -> None:
    """ผูกการวัดที่ประดิษฐ์ขึ้นเข้าเป็น *ตัวดำเนินการฐาน* ของพีชคณิตการถาม."""
    from .probe import Kind, OpSpec, register

    register(
        OpSpec(
            key=inv.op_key,
            arity=1,
            kind=Kind.EITHER,
            base=1,
            lift=0,
            th=(
                f"โครงสร้างแบบ «{inv.coined}» ({inv.key_str}) อธิบาย {{0}} ได้แค่ไหน "
                "และตรงไหนที่มันอธิบายไม่ได้?",
                f"ถ้ามอง {{0}} ด้วย «{inv.coined}» ({inv.key_str}) อะไรที่ยังเหลืออธิบายไม่ได้?",
            ),
            en=(
                f"How much of {{0}} does the structure «{inv.coined}» ({inv.key_str}) "
                "account for, and where does it fail?",
            ),
            floor=1,
            nom_th=f"โครงสร้างแบบ {inv.coined} ใน {{0}}",
        )
    )
