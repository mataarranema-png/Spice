"""โดเมนที่ไม่มีภาษา — ลำดับสัญลักษณ์ดิบที่ไม่มีใครอธิบายไว้ก่อน.

ที่ผ่านมาข้อจำกัดใหญ่ที่สุดของระบบคือ *มันไม่รู้อะไรเลย* เพราะตัวสืบค้น
ออฟไลน์เป็นตัวจำลอง ไม่ใช่ตัวรู้  ที่นี่ไม่เป็นอย่างนั้น: คำถามถูกประมวลผล
เป็น **การวัดจริง** บนลำดับ และคำตอบคือสิ่งที่วัดได้ ไม่ใช่สิ่งที่ประดิษฐ์ขึ้น

และเพราะโดเมนนี้ไม่มีคำศัพท์มาให้เลย ระบบต้อง **ตั้งชื่อสิ่งที่มันค้นพบเอง** —
คำศัพท์ทั้งหมดในกราฟเป็นของที่ระบบผลิตขึ้น ไม่ได้ยืมจากภาษาใด

`residual` ที่นี่ไม่ใช่วลีที่ใครเขียน แต่คือ **เซ็ตของตำแหน่งที่แบบจำลอง
ทายผิดจริง ๆ** — รูปที่บริสุทธิ์ที่สุดของ "คำตอบนี้อธิบายอะไรไม่ได้"
และมันกลายเป็นวัตถุชิ้นใหม่ให้ถามต่อได้ทันที
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from .synth import Fit, Workshop, fit as fit_key, search

_SYLL = ("ka", "ru", "mo", "shi", "ta", "ne", "vo", "li", "za", "phe", "dro", "un", "gi")


@dataclass(frozen=True)
class Selection:
    """วัตถุในโดเมนนี้ = เซ็ตของตำแหน่ง ไม่ใช่คำ."""

    name: str                  # ชื่อที่ระบบตั้งเอง
    idx: tuple[int, ...]
    origin: str = "seed"       # มาจากการวัดแบบไหน

    def __len__(self) -> int:
        return len(self.idx)


@dataclass
class Measurement:
    """ผลของการวัดหนึ่งครั้ง — ไม่มีภาษาอยู่ในนี้เลยนอกจากคำอธิบายให้มนุษย์อ่าน."""

    kind: str
    value: dict = field(default_factory=dict)
    explained: tuple[int, ...] = ()      # ตำแหน่งที่แบบจำลองทายถูก
    residual_idx: tuple[int, ...] = ()   # ตำแหน่งที่ทายผิด — เศษที่คำนวณได้
    bits: float = 0.0                    # ต้นทุนคำอธิบาย (ยิ่งน้อยยิ่งดี)

    @property
    def coverage(self) -> float:
        total = len(self.explained) + len(self.residual_idx)
        return len(self.explained) / total if total else 0.0


def entropy(symbols) -> float:
    n = len(symbols)
    if not n:
        return 0.0
    counts: dict[int, int] = {}
    for s in symbols:
        counts[s] = counts.get(s, 0) + 1
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


class SignalDomain:
    """ลำดับสัญลักษณ์ที่ระบบไม่เคยเห็นมาก่อนและไม่มีคำอธิบายกำกับ."""

    def __init__(self, seq: list[int], rng: random.Random | None = None) -> None:
        self.seq = list(seq)
        self.rng = rng or random.Random(0)
        self._coined: set[str] = set()
        self.root = Selection(self.coin(), tuple(range(len(self.seq))), "root")
        self.selections: dict[str, Selection] = {self.root.name: self.root}
        self.workshop = Workshop(self.coin)

    # ---------------- คำศัพท์ที่ระบบผลิตเอง ----------------

    def coin(self) -> str:
        for _ in range(200):
            n = 2 if self.rng.random() < 0.65 else 3
            token = "".join(self.rng.choice(_SYLL) for _ in range(n))
            if token not in self._coined:
                self._coined.add(token)
                return f"⟦{token}⟧"
        return f"⟦x{len(self._coined)}⟧"

    def add(self, idx, origin: str) -> Selection | None:
        idx = tuple(sorted(set(int(i) for i in idx)))
        if len(idx) < 4:
            return None
        for s in self.selections.values():          # อย่าตั้งชื่อซ้ำให้ของเดิม
            if s.idx == idx:
                return s
        sel = Selection(self.coin(), idx, origin)
        self.selections[sel.name] = sel
        return sel

    def get(self, name: str) -> Selection | None:
        return self.selections.get(name)

    def values(self, sel: Selection) -> list[int]:
        return [self.seq[i] for i in sel.idx]

    # ---------------- การวัด = การถาม ----------------

    def identify(self, sel: Selection) -> Measurement:
        v = self.values(sel)
        alpha = sorted(set(v))
        h = entropy(v)
        return Measurement(
            "identify",
            {"length": len(v), "alphabet": len(alpha), "entropy": round(h, 3),
             "max_entropy": round(math.log2(len(alpha)) if alpha else 0.0, 3)},
            explained=(), residual_idx=sel.idx, bits=h * len(v),
        )

    def extent(self, sel: Selection) -> Measurement:
        v = self.values(sel)
        runs, cur = [], 1
        for a, b in zip(v, v[1:]):
            if a == b:
                cur += 1
            else:
                runs.append(cur); cur = 1
        runs.append(cur)
        return Measurement(
            "extent",
            {"run_min": min(runs), "run_max": max(runs),
             "run_mean": round(sum(runs) / len(runs), 2), "distinct_runs": len(set(runs))},
            explained=(), residual_idx=(), bits=0.0,
        )

    def mechanism(self, sel: Selection) -> Measurement:
        """หากลไกที่ทายลำดับนี้ได้ดีที่สุด แล้วคืน *ตำแหน่งที่มันทายผิด*."""
        v = self.values(sel)
        best = None
        limit = max(2, min(len(v) // 3, 40))
        for p in range(2, limit + 1):
            phase: dict[int, dict[int, int]] = {}
            for i, x in enumerate(v):
                phase.setdefault(i % p, {}).setdefault(x, 0)
                phase[i % p][x] += 1
            model = {k: max(c, key=c.get) for k, c in phase.items()}
            hits = [i for i, x in enumerate(v) if model[i % p] == x]
            # ต้นทุนคำอธิบาย: ตารางเฟส + ส่วนที่ต้องจำเป็นข้อยกเว้น
            alpha = max(2, len(set(v)))
            bits = p * math.log2(alpha) + (len(v) - len(hits)) * math.log2(max(2, len(v)))
            score = len(hits) / len(v)
            if best is None or bits < best["bits"]:
                best = {"period": p, "hits": hits, "score": score, "bits": bits,
                        "model": model}
        if best is None:
            return Measurement("mechanism", {}, (), sel.idx, 0.0)
        hits = set(best["hits"])
        return Measurement(
            "mechanism",
            {"period": best["period"], "accuracy": round(best["score"], 3),
             "bits": round(best["bits"], 1)},
            explained=tuple(sel.idx[i] for i in best["hits"]),
            residual_idx=tuple(sel.idx[i] for i in range(len(v)) if i not in hits),
            bits=best["bits"],
        )

    def invariant(self, sel: Selection) -> Measurement:
        """อะไรใน sel ที่ไม่เปลี่ยนภายใต้การแปลง."""
        v = self.values(sel)
        rev = v[::-1]
        same_rev = sum(1 for a, b in zip(v, rev) if a == b) / max(1, len(v))
        shifted = v[1:] + v[:1]
        same_shift = sum(1 for a, b in zip(v, shifted) if a == b) / max(1, len(v))
        h = entropy(v)
        h_rev = entropy(rev)
        return Measurement(
            "invariant",
            {"symmetry_reversal": round(same_rev, 3),
             "symmetry_shift1": round(same_shift, 3),
             "entropy_preserved": abs(h - h_rev) < 1e-9},
            explained=(), residual_idx=(), bits=0.0,
        )

    def bound(self, sel: Selection) -> Measurement:
        """หาจุดที่กลไกเดิมเลิกใช้ได้ — ขอบที่วัดได้ ไม่ใช่ขอบที่นิยามไว้."""
        v = self.values(sel)
        if len(v) < 24:
            return Measurement("bound", {"reason": "สั้นเกินกว่าจะหาขอบ"}, (), sel.idx)
        best = None
        for cut in range(len(v) // 4, 3 * len(v) // 4):
            left = self._period_score(v[:cut])
            right = self._period_score(v[cut:])
            gapv = abs(left[1] - right[1])
            if best is None or gapv > best["gap"]:
                best = {"cut": cut, "gap": gapv, "left": left, "right": right}
        assert best is not None
        return Measurement(
            "bound",
            {"changepoint": best["cut"],
             "left_period": best["left"][0], "left_accuracy": round(best["left"][1], 3),
             "right_period": best["right"][0], "right_accuracy": round(best["right"][1], 3),
             "contrast": round(best["gap"], 3)},
            explained=tuple(sel.idx[: best["cut"]]),
            residual_idx=tuple(sel.idx[best["cut"] :]),
            bits=0.0,
        )

    def decompose(self, sel: Selection) -> Measurement:
        """หาบล็อกที่ซ้ำบ่อยที่สุด — ชิ้นส่วนที่วัดได้."""
        v = self.values(sel)
        best_block, best_n, best_hits = None, 0, ()
        for n in (2, 3, 4, 5):
            counts: dict[tuple, list[int]] = {}
            for i in range(len(v) - n + 1):
                counts.setdefault(tuple(v[i : i + n]), []).append(i)
            if not counts:
                continue
            block, at = max(counts.items(), key=lambda kv: len(kv[1]) * n)
            if len(at) * n > best_n:
                best_block, best_n, best_hits = block, len(at) * n, tuple(at)
        if best_block is None:
            return Measurement("decompose", {}, (), sel.idx)
        covered = {sel.idx[i + k] for i in best_hits for k in range(len(best_block))}
        return Measurement(
            "decompose",
            {"block": list(best_block), "occurrences": len(best_hits),
             "coverage": round(len(covered) / len(sel.idx), 3)},
            explained=tuple(sorted(covered)),
            residual_idx=tuple(i for i in sel.idx if i not in covered),
            bits=len(best_block) * 2.0,
        )

    def compare(self, a: Selection, b: Selection) -> Measurement:
        ma, mb = self.mechanism(a), self.mechanism(b)
        winner = a.name if ma.bits / max(1, len(a)) < mb.bits / max(1, len(b)) else b.name
        return Measurement(
            "compare",
            {"a": a.name, "b": b.name,
             "bits_per_symbol_a": round(ma.bits / max(1, len(a)), 3),
             "bits_per_symbol_b": round(mb.bits / max(1, len(b)), 3),
             "cheaper_to_describe": winner},
            explained=(), residual_idx=(), bits=0.0,
        )

    def reflect(self, sel: Selection) -> Measurement:
        """เกณฑ์ที่ใช้ตัดสินเอนเอียงไปทางไหน — วัดได้ ไม่ใช่ปรัชญา.

        เทียบแบบจำลองที่ *ทายแม่นที่สุด* กับแบบจำลองที่ *อธิบายถูกที่สุด*
        (สั้นที่สุด)  ถ้าสองอันไม่ใช่อันเดียวกัน แปลว่าเกณฑ์กำลังเลือกคำตอบให้เรา.
        """
        v = self.values(sel)
        by_acc, by_bits = None, None
        limit = max(2, min(len(v) // 3, 40))
        alpha = max(2, len(set(v)))
        for p in range(2, limit + 1):
            phase: dict[int, dict[int, int]] = {}
            for i, x in enumerate(v):
                phase.setdefault(i % p, {}).setdefault(x, 0)
                phase[i % p][x] += 1
            model = {k: max(c, key=c.get) for k, c in phase.items()}
            acc = sum(1 for i, x in enumerate(v) if model[i % p] == x) / max(1, len(v))
            bits = p * math.log2(alpha) + (1 - acc) * len(v) * math.log2(max(2, len(v)))
            if by_acc is None or acc > by_acc[1]:
                by_acc = (p, acc, bits)
            if by_bits is None or bits < by_bits[2]:
                by_bits = (p, acc, bits)
        assert by_acc and by_bits
        return Measurement(
            "reflect",
            {"most_accurate_period": by_acc[0], "its_accuracy": round(by_acc[1], 3),
             "shortest_period": by_bits[0], "its_accuracy": round(by_bits[1], 3),
             "criteria_disagree": by_acc[0] != by_bits[0]},
            explained=(), residual_idx=(), bits=0.0,
        )

    def synthesize(self, sel: Selection) -> Measurement:
        """ประดิษฐ์การวัดขึ้นใหม่สำหรับวัตถุนี้ แทนที่จะใช้ของที่มีอยู่.

        ค้นหาในปริภูมิของโปรแกรม แล้วเทียบกับเครื่องมือเดิม (ตัวตรวจจับคาบ)
        ถ้าของใหม่อธิบายได้ถูกกว่าอย่างมีนัย มันจะถูกเสนอเข้าโรงหลอมเพื่อ
        *เลื่อนขั้นเป็นตัวดำเนินการฐาน*
        """
        found = search(self.seq, sel.idx)
        if not found:
            return Measurement("synthesize", {"reason": "ข้อมูลน้อยเกินกว่าจะค้นหา"}, (), sel.idx)
        best = found[0]
        baseline = self.mechanism(sel)
        base_bps = baseline.bits / max(1, len(sel))
        return Measurement(
            "synthesize",
            {"program": str(best.key), "accuracy": round(best.accuracy, 3),
             "bits_per_symbol": round(best.bits_per_symbol, 3),
             "baseline_program": f"i%{baseline.value.get('period', '?')}",
             "baseline_bits_per_symbol": round(base_bps, 3),
             "beats_baseline": best.bits_per_symbol < base_bps},
            explained=best.hits,
            residual_idx=best.misses,
            bits=best.bits,
        )

    def apply_invented(self, sel: Selection, op_key: str) -> Measurement | None:
        """ใช้ตัวดำเนินการที่ระบบประดิษฐ์ขึ้นเอง."""
        inv = self.workshop.get(op_key)
        if inv is None:
            return None
        f = fit_key(self.seq, sel.idx, inv.key)
        if f is None:
            return Measurement("invented", {"reason": "ใช้กับวัตถุนี้ไม่ได้"}, (), sel.idx)
        inv.uses += 1
        return Measurement(
            "invented",
            {"coined": inv.coined, "program": inv.key_str,
             "accuracy": round(f.accuracy, 3), "bits_per_symbol": round(f.bits_per_symbol, 3)},
            explained=f.hits, residual_idx=f.misses, bits=f.bits,
        )

    # ---------------- ภายใน ----------------

    @staticmethod
    def _period_score(v: list[int]) -> tuple[int, float]:
        best = (1, 0.0)
        for p in range(2, max(3, min(len(v) // 3, 24)) + 1):
            phase: dict[int, dict[int, int]] = {}
            for i, x in enumerate(v):
                phase.setdefault(i % p, {}).setdefault(x, 0)
                phase[i % p][x] += 1
            model = {k: max(c, key=c.get) for k, c in phase.items()}
            acc = sum(1 for i, x in enumerate(v) if model[i % p] == x) / max(1, len(v))
            if acc > best[1]:
                best = (p, acc)
        return best


def context_signal(n: int = 400, seed: int = 5, noise: float = 0.06) -> list[int]:
    """สัญญาณที่ตัวตรวจจับคาบ *มองไม่เห็นเลย*.

    ค่าถัดไปถูกกำหนดโดยสองค่าก่อนหน้าผ่านตารางสุ่ม บวกสัญญาณรบกวนเป็นระยะ
    สัญญาณรบกวนไม่ได้แค่ทำให้ค่าเพี้ยนไปหนึ่งตำแหน่ง แต่ *ผลักวิถีทั้งเส้น
    ไปเฟสใหม่* ทำให้ `i % p` พังยับ ในขณะที่กฎ "ดูสองค่าก่อนหน้า" ยังใช้ได้
    เกือบสมบูรณ์

    ก่อนหน้านี้ระบบมองโครงสร้างแบบนี้ไม่เห็นเลย เพราะการวัดทุกแบบที่มีถูก
    เขียนไว้ล่วงหน้าและไม่มีอันไหนดูบริบท.
    """
    rng = random.Random(seed)
    alpha = 4
    table = {
        (a, b): rng.randrange(alpha) for a in range(alpha) for b in range(alpha)
    }
    out = [rng.randrange(alpha), rng.randrange(alpha)]
    for _ in range(n - 2):
        nxt = table[(out[-2], out[-1])]
        if rng.random() < noise:
            nxt = rng.randrange(alpha)
        out.append(nxt)
    return out


def layered_signal(n: int = 420, seed: int = 11) -> list[int]:
    """สัญญาณทดสอบที่มีโครงสร้างซ้อนกันหลายชั้น.

    ระบบไม่เคยเห็นฟังก์ชันนี้ มันเห็นแค่ตัวเลขเรียงกัน — และต้องค้นชั้นเหล่านี้
    ออกมาเองทีละชั้น โดยเศษของชั้นก่อนหน้าเป็นวัตถุของคำถามชั้นถัดไป.
    """
    rng = random.Random(seed)
    base = [0, 1, 1, 2, 0, 2, 1]                 # ชั้นที่ 1: คาบ 7
    out = []
    for i in range(n):
        x = base[i % 7]
        if i % 13 == 0:                          # ชั้นที่ 2: คาบ 13 ทับ
            x = 3
        if i > n * 0.62 and i % 5 == 0:          # ชั้นที่ 3: ระบอบเปลี่ยนกลางทาง
            x = 2
        if rng.random() < 0.04:                  # ชั้นที่ 4: สัญญาณรบกวน
            x = rng.randrange(4)
        out.append(x)
    return out


# ═══════════════════════════════════════════════════════════════════
#  ตัวสืบค้นที่ *วัดจริง* — ต้นไม้คำถามถูกประมวลผล ไม่ใช่ถูกอ่าน
# ═══════════════════════════════════════════════════════════════════

_DISPATCH = {
    "identify": "identify",
    "decompose": "decompose",
    "extent": "extent",
    "bound": "bound",
    "mechanism": "mechanism",
    "condition": "mechanism",
    "invariant": "invariant",
    "negate": "mechanism",
    "presuppose": "reflect",
    "reflect": "reflect",
    "origin": "reflect",
    "limit": "reflect",
    "compare": "compare",
    "bridge": "compare",
    "tension": "compare",
    "synthesize": "synthesize",
}

_SUMMARY = {
    "identify": "ยาว {length} สัญลักษณ์ {alphabet} ชนิด เอนโทรปี {entropy} จากเพดาน {max_entropy}",
    "extent": "ช่วงความยาวช่วงซ้ำ {run_min}–{run_max} เฉลี่ย {run_mean} มี {distinct_runs} ค่าที่ต่างกัน",
    "mechanism": "แบบจำลองคาบ {period} ทายถูก {accuracy} ใช้ {bits} บิตอธิบาย",
    "invariant": "สมมาตรกลับด้าน {symmetry_reversal} เลื่อนหนึ่ง {symmetry_shift1} เอนโทรปีคงที่ {entropy_preserved}",
    "bound": "ขอบที่ตำแหน่ง {changepoint} — ซ้ายคาบ {left_period} แม่น {left_accuracy} ขวาคาบ {right_period} แม่น {right_accuracy}",
    "decompose": "บล็อกที่ซ้ำบ่อยสุด {block} ปรากฏ {occurrences} ครั้ง ครอบ {coverage} ของทั้งหมด",
    "compare": "{a} ใช้ {bits_per_symbol_a} บิต/สัญลักษณ์ · {b} ใช้ {bits_per_symbol_b} — ที่ถูกกว่าคือ {cheaper_to_describe}",
    "reflect": "เกณฑ์แม่นยำเลือกคาบ {most_accurate_period} เกณฑ์สั้นที่สุดเลือกคาบ {shortest_period} — ขัดกัน {criteria_disagree}",
    "synthesize": "ประดิษฐ์การวัด {program} ทายถูก {accuracy} ใช้ {bits_per_symbol} บิต/สัญลักษณ์ "
                  "(ของเดิม {baseline_program} ใช้ {baseline_bits_per_symbol}) — ดีกว่า {beats_baseline}",
    "invented": "ใช้ «{coined}» ({program}) ทายถูก {accuracy} ใช้ {bits_per_symbol} บิต/สัญลักษณ์",
}


class SignalInvestigator:
    """ตอบคำถามด้วยการวัด ไม่ใช่ด้วยการเขียน.

    นี่คือคำตอบตรง ๆ ต่อข้อจำกัดที่ค้างมาตลอด — ในโดเมนนี้ระบบ *รู้จริง*
    เพราะมันวัดเอง และเศษที่มันคืนมาไม่ใช่วลีที่ใครแต่ง แต่คือเซ็ตของตำแหน่ง
    ที่แบบจำลองทายผิด ซึ่งกลายเป็นวัตถุชิ้นใหม่ให้ถามต่อได้ทันที.
    """

    name = "signal"

    def __init__(self, domain: "SignalDomain") -> None:
        self.domain = domain
        self.failures: list[str] = []
        self.promoted: list = []               # ตัวดำเนินการฐานที่ถูกประดิษฐ์ขึ้นระหว่างทาง
        self._periods: dict[str, int] = {}     # ไว้จับความขัดแย้งระหว่างการวัด

    # ------------------------------------------------------------------

    def investigate(self, q, graph):
        from .types import EdgeSpec, EpistemicStatus, Finding, NodeSpec, QuestionLevel, Relation

        d = self.domain
        sel = self._resolve(q, graph)
        if sel is None:
            return Finding(
                answer="คำถามนี้ไม่ได้ชี้ไปที่วัตถุใดในสัญญาณ",
                confidence=0.0,
                residual="วัตถุที่คำถามชี้ถึงแต่ยังไม่มีตัวตนในโดเมน",
                source=self.name,
            )

        op = q.tree.op if q.tree is not None else "mechanism"
        base_op = op.split("~")[-1]            # หน่วยที่งอกใหม่ใช้ตัวในเป็นตัวจริง
        kind = _DISPATCH.get(base_op, "mechanism")

        if op.startswith("synth::"):
            m = d.apply_invented(sel, op) or d.mechanism(sel)
            kind = "invented"
        elif kind == "compare":
            other = self._second(q, graph) or d.root
            m = d.compare(sel, other)
        elif kind == "synthesize":
            m = d.synthesize(sel)
            # เสนอผลการค้นหาเข้าโรงหลอม — ถ้ามันพิสูจน์ตัวเองพอ จะได้เลื่อนขั้น
            found = search(d.seq, sel.idx)
            if found and m.value.get("baseline_bits_per_symbol"):
                inv = d.workshop.consider(
                    found[0], m.value["baseline_bits_per_symbol"], q.epoch
                )
                if inv is not None:
                    self.promoted.append(inv)
                    m.value["promoted_to_operator"] = inv.coined
        else:
            m = getattr(d, kind)(sel)

        # เครื่องมือเดิมทำได้แย่กับวัตถุนี้ = สัญญาณว่าต้องประดิษฐ์เครื่องมือใหม่
        # การประดิษฐ์จึงถูกกระตุ้นด้วย *ความล้มเหลวของเครื่องมือเดิม* ไม่ใช่ด้วย
        # การสุ่มหยิบตัวดำเนินการมาใช้
        # ประตูที่ 0.82 แคบเกินไป — สัญญาณทดสอบที่มีโครงสร้างซ้อนได้ 0.84 พอดี
        # จึงไม่เคยกระตุ้นการประดิษฐ์เลย ทั้งที่ยังเหลืออีก 16% ที่อธิบายไม่ได้
        if kind == "mechanism" and m.value.get("accuracy", 1.0) < 0.92:
            self._try_invent(sel, m, q.epoch)

        nodes: list[NodeSpec] = []
        edges: list[EdgeSpec] = []
        contradicts: list[str] = []

        # ความขัดแย้งที่วัดได้: วัตถุเดียวกันให้คาบคนละค่าจากคนละวิธี
        period = m.value.get("period") or m.value.get("shortest_period")
        if period:
            prev = self._periods.get(sel.name)
            if prev is not None and prev != period:
                contradicts.append(sel.name)
            self._periods[sel.name] = period

        # เศษ = ตำแหน่งที่ทายผิดจริง กลายเป็นวัตถุใหม่ที่ระบบตั้งชื่อเอง
        residual_sel = None
        if m.residual_idx and len(m.residual_idx) < len(sel):
            residual_sel = d.add(m.residual_idx, f"{kind}-residual")
        if residual_sel is not None and residual_sel.name != sel.name:
            nodes.append(
                NodeSpec(
                    label=residual_sel.name,
                    status=EpistemicStatus.UNKNOWN,
                    confidence=0.0,
                    level=QuestionLevel(min(5, int(q.level) + 1)),
                    tags=("signal", "residual-object", f"n{len(residual_sel)}"),
                )
            )
            edges.append(EdgeSpec(residual_sel.name, sel.name, Relation.UNKNOWN_LINK))

        # ส่วนที่อธิบายได้ก็เป็นวัตถุเหมือนกัน
        if m.explained and 4 <= len(m.explained) < len(sel):
            got = d.add(m.explained, f"{kind}-explained")
            if got is not None and got.name not in {sel.name, getattr(residual_sel, "name", "")}:
                nodes.append(
                    NodeSpec(
                        label=got.name,
                        status=EpistemicStatus.PARTIALLY_KNOWN,
                        confidence=round(m.coverage, 3),
                        level=q.level,
                        tags=("signal", "explained", f"n{len(got)}"),
                    )
                )
                edges.append(EdgeSpec(got.name, sel.name, Relation.EXPLAINS))

        summary = _SUMMARY.get(kind, "{}")
        try:
            answer = f"{sel.name}: " + summary.format(**m.value)
        except (KeyError, IndexError):
            answer = f"{sel.name}: " + str(m.value)

        residual = (
            residual_sel.name
            if residual_sel is not None
            else self._describe_gap(kind, m)
        )
        conf = m.coverage if (m.explained or m.residual_idx) else 0.45
        return Finding(
            answer=answer,
            confidence=round(min(0.9, conf), 3),
            new_nodes=nodes,
            new_edges=edges,
            residual=residual,
            contradicts=contradicts,
            cost=1.0,
            source=self.name,
        )

    # ------------------------------------------------------------------

    def _try_invent(self, sel, baseline: "Measurement", epoch: int) -> None:
        """ค้นหาการวัดที่ดีกว่า และเสนอเข้าโรงหลอมถ้ามันชนะจริง."""
        found = search(self.domain.seq, sel.idx)
        if not found:
            return
        base_bps = baseline.bits / max(1, len(sel))
        inv = self.domain.workshop.consider(found[0], base_bps, epoch)
        if inv is not None:
            self.promoted.append(inv)

    def _resolve(self, q, graph):
        for tid in q.targets:
            node = graph.node(tid)
            if node is not None:
                sel = self.domain.get(node.label)
                if sel is not None:
                    return sel
        return self.domain.root

    def _second(self, q, graph):
        seen = []
        for tid in q.targets:
            node = graph.node(tid)
            if node is not None:
                sel = self.domain.get(node.label)
                if sel is not None:
                    seen.append(sel)
        return seen[1] if len(seen) > 1 else None

    @staticmethod
    def _describe_gap(kind: str, m: "Measurement") -> str:
        """เศษสำหรับการวัดที่ไม่ได้ผลิตเซ็ตตำแหน่ง — ยังต้องระบุให้เจาะจง."""
        if kind == "invariant":
            return "การแปลงที่ยังไม่ได้ทดสอบกับวัตถุนี้"
        if kind == "reflect":
            return (
                "เกณฑ์ที่สามที่ไม่ใช่ทั้งความแม่นและความสั้น"
                if not m.value.get("criteria_disagree")
                else "ทางเลือกระหว่างเกณฑ์แม่นยำกับเกณฑ์ประหยัด ที่ยังไม่มีอะไรมาตัดสิน"
            )
        if kind == "extent":
            return "ความหมายของการกระจายความยาวช่วงซ้ำนี้"
        if kind == "compare":
            return "สิ่งที่การเทียบด้วยจำนวนบิตมองไม่เห็น"
        return "ส่วนของโครงสร้างที่การวัดชุดนี้เข้าไม่ถึง"
