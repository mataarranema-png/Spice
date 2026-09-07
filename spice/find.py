"""หาโครงสร้างในลำดับเหตุการณ์จริง — ชิ้นที่ใช้ได้ทันที ไม่ต้องมี LLM ไม่ต้องมีคีย์.

    python3 -m spice find events.txt
    cat log.txt | python3 -m spice find -

รับลำดับของโทเคนอะไรก็ได้ (สถานะเซิร์ฟเวอร์ การกระทำของผู้ใช้ รหัสข้อผิดพลาด
เกรดสภาพอากาศ ท่าเดินของเครื่องจักร) แล้วตอบสามอย่าง:

    1. โครงสร้างที่ดีที่สุดที่อธิบายลำดับนี้ได้ — และมันคือแบบไหน
    2. ตำแหน่งที่โครงสร้างนั้นอธิบายไม่ได้ อยู่ตรงไหน กระจุกหรือกระจาย
    3. ในเศษที่เหลือนั้น ยังมีโครงสร้างซ้อนอยู่อีกไหม

ข้อที่สามคือตรรกะของก้นหอย: คำตอบไม่ใช่ปลายทาง มันคือตัวชี้ว่าควรมองที่ไหนต่อ
"""

from __future__ import annotations

import sys
from collections import Counter

from .synth import fit, search

MAX_SHOW = 14


def read_tokens(source) -> list[str]:
    raw = source.read()
    for sep in (",", ";", "\t"):
        raw = raw.replace(sep, " ")
    return [t for t in raw.split() if t]


def describe(key_str: str) -> str:
    """แปลโปรแกรมที่ค้นเจอเป็นภาษาที่คนอ่านรู้เรื่อง."""
    if "×" in key_str:
        parts = key_str.strip("()").split("×")
        return "โครงสร้างร่วมของ " + " และ ".join(describe(p) for p in parts)
    if key_str.startswith("i%"):
        return f"รอบซ้ำทุก {key_str[2:]} ตำแหน่ง"
    if key_str.startswith("i÷"):
        return f"ช่วงบล็อกละ {key_str[2:]} ตำแหน่ง (ค่าต่างกันไปตามบล็อก)"
    if key_str.startswith("⌊i/"):
        return "สลับระบอบไปมาเป็นช่วง ๆ"
    if key_str.startswith("prev"):
        k = key_str[4:]
        return f"ค่าถัดไปขึ้นกับ {k} ค่าก่อนหน้า (มีความจำ ไม่ใช่รอบซ้ำ)"
    if key_str == "Δprev":
        return "ขึ้นกับ *ทิศทางการเปลี่ยน* ของสองค่าก่อนหน้า"
    if key_str == "runlen":
        return "ขึ้นกับว่าค่าเดิมซ้ำติดกันมาแล้วกี่ครั้ง"
    if key_str == "·":
        return "ไม่มีโครงสร้าง — ทายด้วยค่าที่พบบ่อยที่สุดเท่านั้น"
    return key_str


def clumping(misses: list[int], n: int) -> str:
    """เศษกระจุกหรือกระจาย — สองอย่างนี้แปลว่าคนละเรื่องกันโดยสิ้นเชิง.

    ความแปรปรวนของช่องว่างอย่างเดียวแยกไม่ออก: บล็อกที่ติดกันสนิทมีช่องว่าง
    คงที่เท่ากับ 1 จึงถูกอ่านว่า "เว้นระยะสม่ำเสมอ" ทั้งที่มันคือกรณีกระจุกที่สุด
    ที่เป็นไปได้  ต้องดู *ช่วงที่มันกินพื้นที่* ประกอบด้วยเสมอ.
    """
    if len(misses) < 4:
        return "น้อยเกินกว่าจะบอกรูปแบบ"
    first, last = misses[0], misses[-1]
    span = (last - first + 1) / max(1, n)
    density = len(misses) / max(1, last - first + 1)

    if span < 0.45 or density > 0.5:
        return (f"**กระจุกเป็นช่วง** — ไม่ใช่สัญญาณรบกวน แต่เป็นช่วงที่กฎเปลี่ยน "
                f"(หนาแน่นระหว่างตำแหน่ง {first}–{last})")

    gaps = [b - a for a, b in zip(misses, misses[1:])]
    mean = sum(gaps) / len(gaps)
    var = sum((g - mean) ** 2 for g in gaps) / len(gaps)
    spread = (var ** 0.5) / mean if mean else 0
    if spread < 0.45:
        return f"**เว้นระยะสม่ำเสมอ** ทุก ~{mean:.1f} ตำแหน่ง — น่าจะมีรอบซ้ำอีกชั้นซ้อนอยู่"
    return "กระจายค่อนข้างสุ่ม — น่าจะเป็นสัญญาณรบกวนจริง"


def enrichment(tokens: list[str], misses: list[int], counts: Counter) -> list[str]:
    """โทเคนชนิดไหนที่ *แพตเทิร์นทายไม่ได้บ่อยผิดปกติ*.

    นี่คือบรรทัดที่คนใช้จริงอยากได้: ไม่ใช่ "อะไรโผล่ในเศษบ่อยสุด" (ซึ่งก็คือ
    อะไรที่พบบ่อยอยู่แล้ว) แต่คือ "อะไรโผล่ในเศษ *มากกว่าที่ควร* กี่เท่า"
    """
    n = sum(counts.values())
    inmiss = Counter(tokens[m] for m in misses)
    rows = []
    for tok, c in inmiss.items():
        expected = counts[tok] * len(misses) / n
        if expected <= 0 or c < 2:
            continue
        rows.append((c / expected, tok, c, counts[tok]))
    rows.sort(reverse=True)
    if not rows:
        return []
    out = ["  เหตุการณ์ที่แพตเทิร์นทายไม่ได้ *บ่อยผิดปกติ*:"]
    for ratio, tok, c, total in rows[:4]:
        verdict = "ผิดปกติชัดเจน" if ratio >= 2.5 else "สูงกว่าค่าคาด" if ratio >= 1.4 else "ปกติ"
        out.append(f"    {tok:<10} {c}/{total} ครั้ง อยู่ในส่วนที่ทายไม่ได้ "
                   f"— {ratio:.1f} เท่าของที่ควรเป็น ({verdict})")
    return out


def phase_failures(best, misses: list[int], n: int) -> list[str]:
    """ถ้าโครงสร้างเป็นรอบซ้ำ ตำแหน่งไหน *ในรอบ* ที่พังบ่อยสุด."""
    ks = str(best.key)
    period = None
    for part in ks.strip("()").split("×"):
        if part.startswith("i%"):
            try:
                period = int(part[2:])
            except ValueError:
                pass
            break
    if not period or period < 2 or len(misses) < 6:
        return []
    by_phase = Counter(m % period for m in misses)
    expected = len(misses) / period
    hot = [(c, ph) for ph, c in by_phase.items() if c >= max(2, expected * 2)]
    if not hot:
        return []
    hot.sort(reverse=True)
    spots = ", ".join(f"ตำแหน่งที่ {ph} ของรอบ ({c} ครั้ง)" for c, ph in hot[:4])
    return [f"  จุดในรอบ {period} ที่พังบ่อยกว่าที่ควร: {spots}"]


def report(tokens: list[str], depth: int = 2) -> str:
    if len(tokens) < 20:
        return "ต้องการอย่างน้อย 20 โทเคนจึงจะหาโครงสร้างได้"

    vocab = sorted(set(tokens))
    code = {t: i for i, t in enumerate(vocab)}
    seq = [code[t] for t in tokens]
    lines: list[str] = []
    counts = Counter(tokens)

    lines.append(f"ลำดับยาว {len(tokens)} · โทเคนต่างกัน {len(vocab)} ชนิด")
    top = " · ".join(f"{t}×{c}" for t, c in counts.most_common(6))
    lines.append(f"พบบ่อยสุด: {top}")
    lines.append("")

    idx = list(range(len(seq)))
    for level in range(depth):
        found = search(seq, idx)
        if not found:
            lines.append("  (เหลือน้อยเกินกว่าจะหาโครงสร้างต่อ)")
            break
        best = found[0]
        head = "โครงสร้างที่อธิบายได้ดีที่สุด" if level == 0 else f"โครงสร้างที่ซ้อนอยู่ในเศษ (ชั้นที่ {level + 1})"
        lines.append(f"── {head} ──")
        lines.append(f"  {describe(str(best.key))}")
        lines.append(f"  รูปแบบ {best.key} · ทายถูก {best.accuracy:.1%} ของ {len(idx)} ตำแหน่ง")

        runner = found[1] if len(found) > 1 else None
        if runner and runner.accuracy > best.accuracy - 0.02:
            lines.append(f"  (คำอธิบายคู่แข่งที่ดีพอ ๆ กัน: {describe(str(runner.key))})")

        misses = list(best.misses)
        lines.append(f"  อธิบายไม่ได้ {len(misses)} ตำแหน่ง — {clumping(misses, len(seq))}")
        if misses:
            shown = ", ".join(str(m) for m in misses[:MAX_SHOW])
            more = f" … อีก {len(misses) - MAX_SHOW}" if len(misses) > MAX_SHOW else ""
            lines.append(f"  ตำแหน่ง: {shown}{more}")
            lines.extend(enrichment(tokens, misses, counts))
            lines.extend(phase_failures(best, misses, len(seq)))
        lines.append("")
        if len(misses) < 20:
            break
        idx = misses

    lines.append("── สิ่งที่รายงานนี้ *ไม่ได้* บอก ──")
    lines.append("  มันบอกว่าลำดับนี้มีโครงสร้างแบบไหน ไม่ได้บอกว่า *ทำไม* ถึงมีโครงสร้างนั้น")
    lines.append("  ตำแหน่งที่อธิบายไม่ได้คือที่ที่ควรไปดูของจริง ไม่ใช่ข้อสรุป")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    path = argv[0]
    src = sys.stdin if path == "-" else open(path, encoding="utf-8")
    try:
        tokens = read_tokens(src)
    finally:
        if src is not sys.stdin:
            src.close()
    print(report(tokens))
    return 0
