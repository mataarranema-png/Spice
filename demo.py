#!/usr/bin/env python3
"""เดินก้นหอยให้ดูสิบรอบ แล้วชี้ให้เห็นว่ามันเปลี่ยนตัวเองตรงไหนบ้าง.

    python3 demo.py            # ออฟไลน์ ไม่ต้องใช้เครือข่ายหรือคีย์
    python3 demo.py --claude   # ใช้ Claude API จริงเป็นตัวสืบค้น
"""

from __future__ import annotations

import argparse

from spice import Spiral
from spice.investigator import CompositeInvestigator, ReflectiveInvestigator

BAR = "─" * 72


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic", default="ก้นหอย")
    ap.add_argument("--epochs", type=int, default=10)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--claude", action="store_true", help="ใช้ Claude API เป็นตัวสืบค้น")
    args = ap.parse_args()

    investigator = None
    if args.claude:
        from spice.llm import ClaudeInvestigator

        investigator = CompositeInvestigator(
            ClaudeInvestigator(), ReflectiveInvestigator()
        )

    sp = Spiral.from_topic(args.topic, seed=args.seed, investigator=investigator)
    before = {s.name for s in sp.population.live()}

    print(BAR)
    print(f"เมล็ด: {args.topic!r} — สถานะเริ่มต้น UNKNOWN ล้วน ๆ")
    print(f"ยุทธวิธีรุ่นศูนย์: {len(before)} ตัว")
    print(BAR)

    for _ in range(args.epochs):
        rec = sp.step()
        head = f"รอบ {rec.epoch:>2}  reward {rec.reward:+.3f}"
        if rec.saturated:
            head += "  [อิ่มตัว → หันไปถามถึงความอิ่มตัวเอง]"
        print("\n" + head)
        for t in rec.turns:
            print(f"  ? [{t.question.level.th}] {t.question.text}")
            print(f"    ↯ {t.residual}")
        if rec.gaps:
            print("  ⚠ จุดบอดที่เรียกร้องเครื่องมือใหม่: " + rec.gaps[0][:64])

    after = {s.name for s in sp.population.live()}
    print("\n" + BAR)
    print(sp.report(last=0).strip())
    print(BAR)
    print("ยุทธวิธีที่ *เกิดใหม่* ระหว่างทาง (ระบบเขียนขึ้นเอง ไม่มีในโค้ดต้นฉบับ):")
    for name in sorted(after - before)[:8]:
        s = sp.population.get(name)
        print(f"  • [{s.origin:<14}] ระดับ{s.level.th:<12} {name}")
    print("\nยุทธวิธีที่ถูกปลดระวาง:")
    for name in sorted(before - after)[:8]:
        print(f"  • {name}")

    print("\nขอบเขตของตัวเองที่ระบบตรวจพบตอนนี้:")
    for lim in sp.self_model.detect(sp.epoch, sp.budget)[:5]:
        print(f"  • [{lim.severity:.2f}] {lim.text}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
