#!/usr/bin/env python3
"""ก้นหอยที่ทำงานกับโดเมนซึ่ง *ไม่มีภาษา* อยู่เลย.

ป้อนลำดับตัวเลขดิบให้ ไม่มีคำอธิบาย ไม่มีชื่อเรียก ไม่มีแม่แบบประโยค
คำถามถูกประกอบจากพีชคณิต ถูกประมวลผลเป็นการวัดจริง และเศษที่เหลือคือ
ตำแหน่งที่แบบจำลองทายผิด ซึ่งกลายเป็นวัตถุชิ้นใหม่ที่ระบบตั้งชื่อเอง

    python3 demo_wordless.py [--epochs 60]
"""

from __future__ import annotations

import argparse
import random

from spice.evolution import Population
from spice.signal import SignalDomain, SignalInvestigator, layered_signal
from spice.spiral import Spiral
from spice.strategies import grammar_strategies
from spice.types import EpistemicStatus

BAR = "─" * 76


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--seed", type=int, default=4)
    ap.add_argument("--length", type=int, default=420)
    args = ap.parse_args()

    seq = layered_signal(args.length, seed=11)
    domain = SignalDomain(seq, random.Random(args.seed - 2))
    pop = Population(grammar_strategies(), rng=random.Random(args.seed + 5), max_size=16)
    sp = Spiral(
        population=pop,
        investigator=SignalInvestigator(domain),
        seed=args.seed,
        questions_per_epoch=3,
    )
    sp.graph.add_node(
        domain.root.name, status=EpistemicStatus.UNKNOWN, tags=("signal", "root")
    )

    print(BAR)
    print("สิ่งที่ระบบได้รับ — ไม่มีคำอธิบายกำกับสักตัว:")
    print("  " + " ".join(str(x) for x in seq[:64]) + " …")
    print(f"  ยาว {len(seq)} · ระบบไม่รู้ว่ามันมาจากอะไร")
    print(f"  ชื่อเดียวที่มีคือชื่อที่ระบบตั้งเอง: {domain.root.name}")
    print(BAR)

    minted = []
    for e in range(args.epochs):
        rec = sp.step()
        if rec.minted:
            m = sp.grammar.minted[rec.minted]
            minted.append((e, m))
            print(f"\n✦ รอบ {e}: ไวยากรณ์หลอมหน่วยใหม่ «{m.coined}» = {m.outer}∘{m.inner}")
        if e in (0, 3, 8):
            for t in rec.turns[:1]:
                print(f"\nรอบ {e} [{t.question.level.th}] {t.question.text}")
                print(f"   วัดได้: {t.answer}")
                print(f"   ↯ เศษ: {t.residual}")

    g = sp.grammar.stats()
    print("\n" + BAR)
    print("สิ่งที่ค้นพบจากตัวเลขดิบ (ทั้งหมดวัดเอง ไม่มีใครบอก):")
    m = domain.mechanism(domain.root)
    b = domain.bound(domain.root)
    i = domain.identify(domain.root)
    print(f"  โครงสร้างคาบ         : คาบ {m.value['period']} ทายถูก {m.value['accuracy']:.0%}")
    print(f"  จุดเปลี่ยนระบอบ       : ตำแหน่ง {b.value['changepoint']} จาก {len(seq)}")
    print(f"  สัญลักษณ์             : {i.value['alphabet']} ชนิด เอนโทรปี {i.value['entropy']}/{i.value['max_entropy']}")

    print("\nคำศัพท์ที่ระบบผลิตขึ้นเอง (ไม่ได้ยืมจากภาษาใด):")
    named = list(domain.selections.values())
    for sel in named[:8]:
        print(f"  {sel.name:<11} {len(sel):>4} ตำแหน่ง   ← {sel.origin}")
    if len(named) > 8:
        print(f"  … อีก {len(named) - 8} ชื่อ")

    print(f"\nไวยากรณ์: คำศัพท์ {g['vocabulary']} ตัว (ฐาน {g['base']} + งอกเอง {g['minted']})")
    print(f"รูปคำถามที่เคยประกอบขึ้น: {g['shapes']} แบบ")
    if minted:
        print("\nหน่วยไวยากรณ์ที่ระบบหลอมขึ้นเอง:")
        from spice.probe import spec

        for epoch, mm in minted:
            s = spec(mm.key)
            print(f"  «{mm.coined}» = {mm.outer}∘{mm.inner}  ระดับ{s.base}  "
                  f"เกิดรอบ {epoch} ใช้ต่อ {mm.uses} ครั้ง")
        used = [sh for sh in sp.grammar.shapes_seen if "~" in sh]
        print(f"\n  รูปคำถามที่ใช้หน่วยเหล่านั้นต่อ ({len(used)} แบบ) เช่น:")
        for sh in sorted(used, key=len)[-4:]:
            print("   ", sh)

    deep = sorted(sp.grammar.shapes_seen, key=lambda s: -s.count("("))[:4]
    print("\nรูปคำถามที่ลึกที่สุดที่มันประกอบขึ้น — ไม่มีบรรทัดไหนในโค้ดเขียนรูปเหล่านี้ไว้:")
    for sh in deep:
        print("   ", sh)

    print("\n" + BAR)
    print(sp.report(last=0).strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
