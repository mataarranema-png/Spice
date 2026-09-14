"""โหวตหาคำตอบที่น่าเชื่อถือที่สุด — ถามซ้ำหลายรอบแล้วดูว่าอันไหนสอดคล้องกับพวกมากที่สุด.

โมเดลภาษาให้คำตอบต่างกันได้ทุกครั้งที่รัน คำถามที่ต้องการความถูกต้องจึงควรถาม
หลายรอบแล้วเลือกคำตอบที่ "อยู่กลางกลุ่ม" ที่สุด ซึ่งเป็นวิธีที่งานวิจัยเรียกว่า
self-consistency และได้ผลดีกว่าการเชื่อคำตอบเดียวแบบสุ่ม.

ตรงนี้ไม่ต้องใช้โมเดลมาตัดสิน — วัดความใกล้เคียงด้วยเวกเตอร์ในเครื่องก็พอ
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter

import numpy as np

from . import vault

# คำตอบสั้น ๆ ใช้เวกเตอร์ตัดสินไม่ได้ เพราะคำนำเหมือนกันก็ดันคะแนนขึ้นทั้งที่
# เนื้อหาคนละเรื่อง ("คำตอบ ก" กับ "คำตอบ ข") — สั้นกว่านี้ให้นับคำตอบซ้ำแทน
SHORT_ANSWER_CHARS = 60
_NOISE = re.compile(r"[\s\.,!?；;:_\-–—\"'“”‘’()\[\]{}]+")


def normalize(text: str) -> str:
    """ตัดเครื่องหมายและช่องว่างทิ้ง เพื่อเทียบว่า "ตอบเหมือนกันไหม" จริง ๆ."""
    folded = unicodedata.normalize("NFKC", text).strip().lower()
    return _NOISE.sub("", folded)


def _vote_by_exact_match(answers: list[str]) -> dict:
    """นับว่าคำตอบไหนถูกตอบซ้ำมากที่สุด — แม่นกว่าเวกเตอร์เมื่อคำตอบสั้น."""
    keys = [normalize(answer) for answer in answers]
    counts = Counter(keys)
    winning_key, votes = counts.most_common(1)[0]
    winner = next(index for index, key in enumerate(keys) if key == winning_key)
    return {
        "answer": answers[winner],
        "confidence": round(votes / len(answers), 3),
        "agreement": [round(counts[key] / len(answers), 3) for key in keys],
        "samples": len(answers),
        "winner_index": winner,
        "votes": votes,
        "method": "exact",
    }


def pick_consensus(answers: list[str]) -> dict:
    """เลือกคำตอบที่ใกล้เคียงกับคำตอบอื่นมากที่สุด พร้อมคะแนนความมั่นใจ."""
    usable = [answer for answer in answers if answer and answer.strip()]
    if not usable:
        return {"answer": "", "confidence": 0.0, "agreement": [], "samples": 0}
    if len(usable) == 1:
        return {"answer": usable[0], "confidence": 0.0, "agreement": [1.0],
                "samples": 1, "method": "single"}

    if max(len(answer) for answer in usable) <= SHORT_ANSWER_CHARS:
        return _vote_by_exact_match(usable)

    vectors = np.stack([vault.local_embed(answer) for answer in usable])
    similarity = vectors @ vectors.T          # cosine เพราะเวกเตอร์ถูกนอร์มไว้แล้ว
    np.fill_diagonal(similarity, 0.0)

    # คะแนนของแต่ละคำตอบ = ความใกล้เคียงเฉลี่ยกับคำตอบอื่น ๆ
    agreement = similarity.sum(axis=1) / (len(usable) - 1)
    winner = int(np.argmax(agreement))

    return {
        "answer": usable[winner],
        "confidence": round(float(agreement[winner]), 3),
        "agreement": [round(float(score), 3) for score in agreement],
        "samples": len(usable),
        "winner_index": winner,
        "spread": round(float(agreement.max() - agreement.min()), 3),
        "method": "similarity",
    }


def describe(result: dict) -> str:
    """อธิบายผลโหวตให้ผู้ใช้เข้าใจว่าควรเชื่อแค่ไหน."""
    confidence = result.get("confidence", 0)
    samples = result.get("samples", 0)
    if samples < 2:
        return "มีคำตอบเดียว จึงไม่ได้โหวต"
    if result.get("method") == "exact":
        votes = result.get("votes", 0)
        if votes == 1:
            return f"ถาม {samples} รอบ ได้คำตอบไม่ซ้ำกันเลย — ควรตรวจสอบเอง"
        return (f"ถาม {samples} รอบ · ตอบเหมือนกัน {votes} รอบ "
                f"({confidence:.0%}) — {'เชื่อถือได้' if confidence >= 0.6 else 'ยังไม่ชัดเจนนัก'}")
    if confidence >= 0.7:
        level = "คำตอบทุกรอบตรงกันมาก เชื่อถือได้"
    elif confidence >= 0.4:
        level = "คำตอบส่วนใหญ่ไปทางเดียวกัน แต่มีรายละเอียดต่างกันบ้าง"
    else:
        level = "คำตอบแต่ละรอบต่างกันมาก — ควรตรวจสอบเอง หรือถามให้เจาะจงกว่านี้"
    return f"ถาม {samples} รอบ · ความสอดคล้อง {confidence:.0%} — {level}"
