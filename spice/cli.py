"""บรรทัดคำสั่งของก้นหอย.

    python -m spice run --topic "ก้นหอย" --epochs 12
    python -m spice ask  "อะไรทำให้เราเรียกสิ่งนี้ว่ากลไก?"
    python -m spice report | strategies | limits | graph --dot out.dot
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

from . import exchange, store
from .investigator import CompositeInvestigator, ReflectiveInvestigator
from .selfmodel import Budget
from .spiral import Spiral
from .types import QuestionLevel

DEFAULT_STATE = Path("spiral.state.json")


def _investigator(args) -> object:
    offline = ReflectiveInvestigator(random.Random(args.seed + 2))
    if args.backend == "reflective":
        return offline
    from .llm import ClaudeInvestigator

    claude = ClaudeInvestigator(model=args.model, effort=args.effort)
    # ถ้า Claude ล้มเหลว ก้นหอยต้องไม่หยุด — และความล้มเหลวนั้นจะกลายเป็น
    # ข้อจำกัดที่ SelfModel หยิบไปตั้งคำถามระดับ SELF_REFERENCE ต่อเอง
    return CompositeInvestigator(claude, offline)


def _load(args, topic: str | None = None) -> Spiral:
    path = Path(args.state)
    inv = _investigator(args)
    if path.exists():
        sp = store.load(path, investigator=inv, seed=args.seed)
        if topic and sp.graph.by_label(topic) is None:
            sp.seed_topic(topic)
        return sp
    if not topic:
        raise SystemExit(
            f"ยังไม่มีไฟล์สถานะ {path} — เริ่มด้วย `python -m spice run --topic \"...\"` ก่อน"
        )
    sp = Spiral(
        investigator=inv,
        seed=args.seed,
        lang=args.lang,
        questions_per_epoch=args.k,
        budget=Budget(
            max_nodes=args.max_nodes,
            max_questions=args.max_questions,
            max_cost=args.max_cost,
        ),
    )
    sp.seed_topic(topic)
    return sp


def cmd_run(args) -> int:
    sp = _load(args, args.topic)
    records = sp.run(args.epochs)
    store.save(sp, args.state)
    if args.quiet:
        st = sp.graph.stats()
        print(
            f"รอบ {sp.epoch} | node {st['nodes']} | ขัดแย้ง {st['contradictions']} "
            f"| U {st['mean_uncertainty']:.3f} | ยุทธวิธี {len(sp.population.live())}"
        )
    else:
        print(sp.report(last=min(len(records), args.show) or 1))
    return 0


def cmd_ask(args) -> int:
    sp = _load(args, args.topic)
    sp.ask(args.question, QuestionLevel(args.level))
    sp.run(1)
    store.save(sp, args.state)
    print(sp.report(last=1))
    return 0


def cmd_propose(args) -> int:
    sp = _load(args, args.topic)
    path = exchange.dump(sp, args.out)
    store.save(sp, args.state)
    print(f"ก้นหอยรอบ {sp.epoch} อยากรู้ {len(sp._proposed)} เรื่อง — เขียนไปที่ {path}")
    for s in sp._proposed:
        print(f"  [{s.question.level.th}] {s.question.text}")
    print(f"\nเติมช่อง answer ในไฟล์ แล้วสั่ง: python -m spice --state {args.state} absorb --in {path}")
    return 0


def cmd_absorb(args) -> int:
    sp = _load(args)
    rec, answered = exchange.load(sp, args.inp)
    store.save(sp, args.state)
    print(f"รับคำตอบจากภายนอก {answered} ข้อ (ที่เหลือใช้ตัวสืบค้นในตัว)\n")
    print(sp.report(last=1))
    return 0


def cmd_report(args) -> int:
    sp = _load(args)
    print(sp.report(last=args.last))
    return 0


def cmd_strategies(args) -> int:
    sp = _load(args)
    print(sp.population.table())
    return 0


def cmd_limits(args) -> int:
    sp = _load(args)
    limits = sp.self_model.detect(sp.epoch, sp.budget)
    if not limits:
        print("ยังตรวจไม่พบขอบเขต — ลองเดินก้นหอยต่ออีกสองสามรอบ")
        return 0
    print("ขอบเขตของตัวระบบที่ตรวจพบตอนนี้:")
    for lim in limits:
        print(f"  [{lim.severity:.2f}] ({lim.kind}, {lim.epochs_persisted} รอบ) {lim.text}")
    gaps = sp.self_model.gaps(sp.epoch, sp.budget)
    if gaps:
        print("\nช่องโหว่ที่เรียกร้องเครื่องมือใหม่:")
        for g in gaps:
            print(f"  [{g.severity:.2f}] ระดับ{g.level.th}: {g.text}")
    return 0


def cmd_graph(args) -> int:
    sp = _load(args)
    if args.dot:
        Path(args.dot).write_text(sp.graph.to_dot(), encoding="utf-8")
        print(f"เขียน DOT ไปที่ {args.dot} (เรนเดอร์ด้วย: dot -Tsvg {args.dot} -o graph.svg)")
        return 0
    for node in sorted(sp.graph, key=lambda n: -n.uncertainty):
        print(f"[{node.status.value:16}] U={node.uncertainty:.2f} {node.label}")
        for r in node.residuals:
            print(f"       ↯ {r}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="spice",
        description="ระบบตั้งคำถามแบบก้นหอยที่เรียนรู้และแก้ไขตัวเองได้",
    )
    p.add_argument("--state", default=str(DEFAULT_STATE), help="ไฟล์สถานะของก้นหอย")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--lang", default="th", choices=("th", "en"))
    p.add_argument("--k", type=int, default=3, help="จำนวนคำถามต่อรอบ")
    p.add_argument(
        "--backend",
        default="reflective",
        choices=("reflective", "claude"),
        help="reflective = ออฟไลน์ ไม่ต้องใช้เครือข่าย; claude = ใช้ Claude API จริง",
    )
    p.add_argument("--model", default="claude-opus-5")
    p.add_argument("--effort", default="medium", choices=("low", "medium", "high", "xhigh", "max"))
    p.add_argument("--max-nodes", type=int, default=None)
    p.add_argument("--max-questions", type=int, default=None)
    p.add_argument("--max-cost", type=float, default=None)

    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="เดินก้นหอยไปข้างหน้า")
    r.add_argument("--topic", default=None, help="หัวข้อตั้งต้น (จำเป็นเมื่อยังไม่มีไฟล์สถานะ)")
    r.add_argument("--epochs", type=int, default=5)
    r.add_argument("--show", type=int, default=2, help="แสดงผลย้อนหลังกี่รอบ")
    r.add_argument("--quiet", action="store_true")
    r.set_defaults(func=cmd_run)

    a = sub.add_parser("ask", help="แทรกคำถามของมนุษย์เข้าไปในก้นหอย")
    a.add_argument("question")
    a.add_argument("--topic", default=None)
    a.add_argument("--level", type=int, default=0, choices=range(6))
    a.set_defaults(func=cmd_ask)

    pr = sub.add_parser("propose", help="ให้ก้นหอยบอกว่ารอบนี้อยากรู้อะไร (ไม่ตอบเอง)")
    pr.add_argument("--out", default="questions.json")
    pr.add_argument("--topic", default=None)
    pr.set_defaults(func=cmd_propose)

    ab = sub.add_parser("absorb", help="ป้อนคำตอบจากภายนอกกลับเข้าก้นหอย")
    ab.add_argument("--in", dest="inp", default="questions.json")
    ab.set_defaults(func=cmd_absorb)

    rep = sub.add_parser("report", help="สรุปรอบล่าสุด")
    rep.add_argument("--last", type=int, default=3)
    rep.set_defaults(func=cmd_report)

    s = sub.add_parser("strategies", help="ดูประชากรยุทธวิธีปัจจุบัน")
    s.set_defaults(func=cmd_strategies)

    l = sub.add_parser("limits", help="ดูขอบเขตของตัวเองที่ระบบตรวจพบ")
    l.set_defaults(func=cmd_limits)

    g = sub.add_parser("graph", help="ดูหรือส่งออกกราฟความรู้")
    g.add_argument("--dot", default=None, help="เขียนไฟล์ Graphviz DOT")
    g.set_defaults(func=cmd_graph)
    return p


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    # `spice find <file>` เป็นเครื่องมือแยกที่ใช้ได้เดี่ยว ๆ ไม่ต้องมีสถานะก้นหอย
    if argv and argv[0] == "find":
        from .find import main as find_main

        return find_main(argv[1:])
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
