"""ไวยากรณ์ของการถาม — และการที่มัน *งอกหน่วยใหม่ขึ้นมาเอง*.

`probe.py` ให้ตัวดำเนินการฐานมา 15 ตัว ถ้าหยุดแค่นั้น พื้นที่คำถามก็ยังถูก
ล้อมด้วยสิ่งที่มนุษย์เขียนไว้อยู่ดี แค่ล้อมด้วยตัวดำเนินการแทนที่จะล้อมด้วย
ประโยค

ภาษามนุษย์โตด้วยกลไกชื่อ grammaticalization: การประกอบที่ถูกใช้บ่อยและได้ผล
จะถูก *ยุบเป็นหน่วยเดียว* แล้วหน่วยนั้นเอาไปประกอบต่อได้อีก  โครงสร้างที่เคย
ต้องใช้สามชั้นจึงพูดได้ในชั้นเดียว และความลึกที่ประหยัดไว้ก็เอาไปใช้สร้าง
โครงสร้างที่ก่อนหน้านี้เอื้อมไม่ถึง

โมดูลนี้ทำอย่างนั้น: จดว่าการประกอบคู่ไหนให้ความประหลาดใจสูงซ้ำ ๆ แล้ว
*หลอมมันเป็นตัวดำเนินการใหม่* พร้อมชื่อที่ระบบตั้งเอง  ตัวดำเนินการที่งอกใหม่
เข้าไปอยู่ในพีชคณิตทันที และถูกนำไปประกอบต่อได้เหมือนตัวฐานทุกประการ

ตัวดำเนินการที่งอกแล้วไม่ให้ผลจะถูกปลดระวาง — ไวยากรณ์ที่โตอย่างเดียวไม่ใช่
ไวยากรณ์ที่เรียนรู้ มันคือไวยากรณ์ที่พองเท่านั้น
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from .probe import (
    BASE_OPS,
    Kind,
    OpSpec,
    Probe,
    Ref,
    known_ops,
    probe,
    register,
    spec,
)

MINT_MIN_USES = 3        # ต้องเห็นการประกอบนี้ได้ผลกี่ครั้งก่อนหลอมเป็นหน่วยเดียว
MINT_FLOOR = 0.12        # พื้นสัมบูรณ์ — รันที่ตายแล้วต้องไม่หลอมขยะออกมา
MINT_RATIO = 1.45        # ต้องดีกว่า *พื้นของรันนี้เอง* กี่เท่า
RETIRE_MIN_USES = 5
RETIRE_RATIO = 0.5       # หน่วยที่งอกแล้วทำได้ต่ำกว่าครึ่งของพื้น = ไม่คุ้มค่าที่มันกิน
MAX_MINTED = 14

# พยางค์สำหรับตั้งชื่อหน่วยที่งอกใหม่ — ระบบตั้งชื่อเอง ไม่ได้ยืมคำจากภาษาใด
_SYLL = ("ka", "ru", "mo", "shi", "ta", "ne", "vo", "li", "za", "phe", "dro", "un")


@dataclass
class PairStat:
    uses: int = 0
    gain_sum: float = 0.0

    @property
    def mean(self) -> float:
        return self.gain_sum / self.uses if self.uses else 0.0

    def to_dict(self) -> dict:
        return {"uses": self.uses, "gain_sum": self.gain_sum}


@dataclass
class Minted:
    """หน่วยไวยากรณ์ที่ระบบหลอมขึ้นเอง."""

    key: str
    outer: str
    inner: str
    coined: str            # ชื่อที่ระบบตั้ง — ไม่ได้มาจากภาษาใด
    born_epoch: int
    uses: int = 0
    gain_sum: float = 0.0

    @property
    def mean(self) -> float:
        return self.gain_sum / self.uses if self.uses else 0.5

    def to_dict(self) -> dict:
        return {
            "key": self.key, "outer": self.outer, "inner": self.inner,
            "coined": self.coined, "born_epoch": self.born_epoch,
            "uses": self.uses, "gain_sum": self.gain_sum,
        }


class Grammar:
    def __init__(self, rng: random.Random | None = None) -> None:
        self.rng = rng or random.Random(0)
        self.pairs: dict[tuple[str, str], PairStat] = {}
        self.minted: dict[str, Minted] = {}
        self.shapes_seen: set[str] = set()
        self.adopted: set[str] = set()   # ตัวดำเนินการที่ *รันนี้* ประดิษฐ์ขึ้น
        self.generation = 0
        self.baseline = 0.0        # ความประหลาดใจเฉลี่ยที่รันนี้ทำได้จริง
        self._observations = 0

    # ---------------- ผลิตคำถาม ----------------

    @property
    def vocabulary(self) -> tuple[str, ...]:
        """คำศัพท์ที่ใช้ได้ตอนนี้ = ตัวฐานที่มนุษย์เขียน + ที่หลอมเอง
        + **ที่ประดิษฐ์ขึ้นจากการค้นหาโปรแกรม** (`synth::`)

        ข้อสุดท้ายสำคัญ: ถ้าไม่นับรวม ตัวดำเนินการที่ระบบประดิษฐ์ขึ้นจะถูก
        จดทะเบียนไว้เฉย ๆ โดยไม่มีวันถูกเอาไปประกอบเป็นคำถามเลยสักครั้ง

        และต้องนับเฉพาะที่ *รันนี้* รับมา ไม่ใช่ทุกตัวที่จดทะเบียนไว้ในโปรเซส —
        ทะเบียนตัวดำเนินการเป็นสถานะระดับโมดูล การนับทั้งหมดทำให้สิ่งที่รันก่อน
        หน้าประดิษฐ์ไว้ไหลข้ามมาโผล่ในรันถัดไป ทั้งที่รันนั้นไม่ได้ค้นพบอะไรเลย
        """
        return tuple(
            k for k in known_ops()
            if k in BASE_OPS or k in self.minted or k in self.adopted
        )

    def _fits(self, s: OpSpec, arg) -> bool:
        if s.kind is Kind.PROBE:
            return isinstance(arg, Probe)
        if s.kind is Kind.OBJECT:
            return isinstance(arg, Ref)
        return True

    def compose(
        self, refs: list[Ref], max_depth: int = 3, lifting_bias: float = 0.45
    ) -> Probe | None:
        """สุ่มสร้างคำถามที่ถูกไวยากรณ์ จากคำศัพท์ที่มีอยู่ *ตอนนี้*.

        เมื่อไวยากรณ์งอกหน่วยใหม่ ฟังก์ชันนี้จะเริ่มผลิตรูปที่ก่อนหน้านี้
        สร้างไม่ได้ทันที โดยไม่มีใครต้องแก้โค้ด.
        """
        if not refs:
            return None
        rng = self.rng
        vocab = [k for k in self.vocabulary if spec(k)]
        lifters = [k for k in vocab if spec(k).kind is Kind.PROBE]
        grounders = [k for k in vocab if spec(k).kind is not Kind.PROBE]
        if not grounders:
            return None

        def choose(pool: list[str], outer: str | None) -> str:
            """เลือกตัวดำเนินการ โดยเอนไปทางการประกอบที่เคยได้ผล.

            ถ้าสุ่มเท่ากันหมด พื้นที่การประกอบจะกว้างเกินกว่าจะมีคู่ไหนถูกใช้ซ้ำ
            พอที่จะตกผลึก — วัดได้ว่า 45 รอบผลิตรูปคำถาม 86 แบบ แต่ไม่มีคู่ใด
            ถึงเกณฑ์หลอมเลยสักคู่  ภาษาจริงก็ต้องการการใช้ซ้ำเช่นกัน:
            ความสำเร็จต้องพาไปสู่การทำซ้ำ การทำซ้ำจึงพาไปสู่การหลอมเป็นหน่วย
            คู่ที่ยังไม่เคยลองยังได้น้ำหนักพื้นฐาน การสำรวจจึงไม่ตาย
            """
            if outer is None:
                return rng.choice(pool)
            weights = []
            for k in pool:
                st = self.pairs.get((outer, k))
                if st is None or st.uses == 0:
                    weights.append(1.0)
                else:
                    pull = max(0.0, st.mean - 0.18) * min(1.0, st.uses / 3.0)
                    weights.append(1.0 + 5.0 * pull)
            total = sum(weights)
            r = rng.random() * total
            for k, w in zip(pool, weights):
                r -= w
                if r <= 0:
                    return k
            return pool[-1]

        def build(depth: int, outer: str | None = None) -> Probe | None:
            pool = grounders if depth <= 1 or not lifters else (
                lifters if rng.random() < lifting_bias else grounders
            )
            key = choose(pool, outer)
            s = spec(key)
            args: list[Probe | Ref] = []
            # ตัวดำเนินการสองอาร์กิวเมนต์ที่จับของชิ้นเดียวกันสองครั้ง ไม่ได้ถาม
            # อะไรเลย — เลี่ยงถ้ายังมีตัวเลือกอื่นให้เลี่ยง
            spare = list(refs)
            for _ in range(s.arity):
                if s.kind is Kind.PROBE:
                    inner = build(depth - 1, key)
                    if inner is None:
                        return None
                    args.append(inner)
                elif s.kind is Kind.OBJECT:
                    args.append(_take(spare, refs, rng))
                else:
                    if depth > 1 and rng.random() < 0.34:
                        inner = build(depth - 1, key)
                        args.append(inner if inner is not None else _take(spare, refs, rng))
                    else:
                        args.append(_take(spare, refs, rng))
            p = Probe(op=key, args=tuple(args))
            return p if p.is_wellformed else None

        for _ in range(6):
            p = build(max_depth)
            if p is not None and p.is_wellformed:
                return p
        return None

    # ---------------- เรียนรู้จากผล ----------------

    @property
    def mint_bar(self) -> float:
        """เกณฑ์หลอมหน่วย — สัมพัทธ์กับสิ่งที่รันนี้ทำได้จริง.

        ตอนแรกใช้ค่าคงที่ 0.34 แล้ววัดได้ว่ามีแค่ 1 จาก 6 seed ที่หลอมหน่วยได้เลย
        เพราะความประหลาดใจเฉลี่ยของรันจริงอยู่ที่ 0.12–0.20 — เกณฑ์นั้นเรียกร้อง
        คู่ที่ดีกว่าค่าเฉลี่ยสองเท่า ซึ่งแทบไม่มี และยิ่งหายากขึ้นเมื่อโดเมนถูกขุด
        จนเกลี้ยง  ภาษาก็หลอมหน่วยที่ให้ผลดี *ผิดปกติเทียบกับพื้นรอบตัว*
        ไม่ใช่ที่ผ่านค่าสากลค่าหนึ่ง.
        """
        return max(MINT_FLOOR, self.baseline * MINT_RATIO)

    def adopt(self, op_key: str) -> None:
        """รับตัวดำเนินการที่เพิ่งถูกประดิษฐ์ขึ้นเข้าคำศัพท์ของรันนี้."""
        if spec(op_key) is not None:
            self.adopted.add(op_key)

    def observe(self, p: Probe, gain: float) -> None:
        """จดว่าการประกอบแต่ละคู่ในคำถามนี้ให้ผลเท่าไร."""
        self.shapes_seen.add(p.shape)
        self._observations += 1
        k = 1.0 / min(self._observations, 60)
        self.baseline = (1 - k) * self.baseline + k * gain
        for node in p.walk():
            for a in node.args:
                if isinstance(a, Probe):
                    st = self.pairs.setdefault((node.op, a.op), PairStat())
                    st.uses += 1
                    st.gain_sum += gain
            if node.op in self.minted:
                m = self.minted[node.op]
                m.uses += 1
                m.gain_sum += gain

    def mint(self, epoch: int) -> Minted | None:
        """หลอมการประกอบที่ได้ผลซ้ำ ๆ ให้เป็นตัวดำเนินการเดี่ยว.

        นี่คือจุดที่ไวยากรณ์งอกจริง: หลังจากนี้ระบบพูดสิ่งที่เคยต้องใช้สองชั้น
        ได้ในชั้นเดียว แล้วเอาความลึกที่เหลือไปสร้างรูปที่ก่อนหน้านี้เอื้อมไม่ถึง.
        """
        if len(self.minted) >= MAX_MINTED:
            return None
        bar = self.mint_bar
        best: tuple[tuple[str, str], PairStat] | None = None
        for pair, st in self.pairs.items():
            if st.uses < MINT_MIN_USES or st.mean < bar:
                continue
            key = _mint_key(*pair)
            if key in self.minted:
                continue
            if best is None or st.mean > best[1].mean:
                best = (pair, st)
        if best is None:
            return None

        (outer, inner), st = best
        so, si = spec(outer), spec(inner)
        if so is None or si is None:
            return None

        coined = self._coin()
        key = _mint_key(outer, inner)
        # ผิวของหน่วยใหม่ = ผิวของตัวนอก โดยเอา *รูปนาม* ของตัวในไปแทน
        th = tuple(
            t.replace("{0}", si.nominal("th")).replace("«", "").replace("»", "")
            for t in so.surface("th")[:2]
        )
        nom = so.nominal("th").replace("{0}", si.nominal("th"))
        lvl = int(Probe(op=outer, args=(Probe(op=inner, args=(Ref("x"),)),)).level) \
            if so.kind is Kind.PROBE else max(so.base, si.base)

        register(
            OpSpec(
                key=key,
                arity=si.arity,
                kind=si.kind,
                base=lvl,
                lift=0,
                th=th or (f"{coined}({{0}})?",),
                floor=lvl,
                nom_th=nom,
            )
        )
        m = Minted(key=key, outer=outer, inner=inner, coined=coined, born_epoch=epoch)
        self.minted[key] = m
        self.generation += 1
        return m

    def prune(self, epoch: int) -> list[str]:
        """หน่วยที่งอกแล้วไม่ให้ผลต้องหายไป — ไวยากรณ์ที่โตอย่างเดียวคือไวยากรณ์ที่พอง."""
        gone: list[str] = []
        for key, m in list(self.minted.items()):
            if m.uses >= RETIRE_MIN_USES and m.mean < self.baseline * RETIRE_RATIO:
                del self.minted[key]
                gone.append(key)
        return gone

    def _coin(self) -> str:
        rng = self.rng
        n = 2 if rng.random() < 0.7 else 3
        return "".join(rng.choice(_SYLL) for _ in range(n))

    # ---------------- สถานะ ----------------

    def stats(self) -> dict:
        return {
            "vocabulary": len(self.vocabulary),
            "base": len(BASE_OPS),
            "minted": len(self.minted),
            "invented": len(self.adopted),
            "shapes": len(self.shapes_seen),
            "generation": self.generation,
            "baseline": round(self.baseline, 4),
            "mint_bar": round(self.mint_bar, 4),
        }

    def to_dict(self) -> dict:
        return {
            "pairs": [
                {"outer": o, "inner": i, **st.to_dict()}
                for (o, i), st in self.pairs.items()
            ],
            "minted": [m.to_dict() for m in self.minted.values()],
            "adopted": sorted(self.adopted),
            "shapes_seen": sorted(self.shapes_seen)[:400],
            "generation": self.generation,
            "baseline": self.baseline,
            "observations": self._observations,
        }

    @classmethod
    def from_dict(cls, d: dict, rng: random.Random | None = None) -> "Grammar":
        g = cls(rng)
        for row in d.get("pairs", ()):
            g.pairs[(row["outer"], row["inner"])] = PairStat(
                uses=row.get("uses", 0), gain_sum=row.get("gain_sum", 0.0)
            )
        for row in d.get("minted", ()):
            m = Minted(**row)
            g.minted[m.key] = m
            g._reregister(m)
        g.shapes_seen = set(d.get("shapes_seen", ()))
        g.adopted = {k for k in d.get("adopted", ()) if spec(k) is not None}
        g.generation = d.get("generation", 0)
        g.baseline = d.get("baseline", 0.0)
        g._observations = d.get("observations", 0)
        return g

    def _reregister(self, m: Minted) -> None:
        """ผูกหน่วยที่งอกไว้กลับเข้าพีชคณิตหลังโหลดสถานะ."""
        so, si = spec(m.outer), spec(m.inner)
        if so is None or si is None:
            return
        th = tuple(
            t.replace("{0}", si.nominal("th")).replace("«", "").replace("»", "")
            for t in so.surface("th")[:2]
        )
        lvl = int(Probe(op=m.outer, args=(Probe(op=m.inner, args=(Ref("x"),)),)).level) \
            if so.kind is Kind.PROBE else max(so.base, si.base)
        register(
            OpSpec(
                key=m.key, arity=si.arity, kind=si.kind, base=lvl, lift=0,
                th=th or (f"{m.coined}({{0}})?",), floor=lvl,
                nom_th=so.nominal("th").replace("{0}", si.nominal("th")),
            )
        )


def _take(spare: list[Ref], refs: list[Ref], rng: random.Random) -> Ref:
    if not spare:
        return rng.choice(refs)
    pick = rng.choice(spare)
    spare.remove(pick)
    return pick


def _mint_key(outer: str, inner: str) -> str:
    return f"{outer}~{inner}"
