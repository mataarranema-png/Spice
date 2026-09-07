"""การเก็บสถานะ — เพื่อให้ "ตัวเองรุ่นใหม่" รอดข้ามการรัน.

ถ้าไม่มีไฟล์นี้ การวิวัฒนาการทั้งหมดจะหายไปทุกครั้งที่โปรเซสจบ และระบบ
จะเริ่มจากประชากรรุ่นศูนย์ตลอดกาล — ซึ่งแปลว่ามันไม่ได้เรียนรู้อะไรเลย
แค่ *ดูเหมือน* เรียนรู้ภายในหนึ่งการรัน.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .investigator import Investigator
from .spiral import Spiral

SCHEMA_VERSION = 1


def save(spiral: Spiral, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = spiral.to_dict()
    payload["version"] = SCHEMA_VERSION
    # เขียนแบบ atomic: สถานะที่พังครึ่งทางแย่กว่าไม่มีสถานะ
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return path


def load(
    path: str | Path,
    *,
    investigator: Investigator | None = None,
    seed: int = 0,
) -> Spiral:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    version = data.get("version", 0)
    if version > SCHEMA_VERSION:
        raise ValueError(
            f"ไฟล์สถานะเป็นเวอร์ชัน {version} แต่โค้ดนี้รองรับถึง {SCHEMA_VERSION}"
        )
    return Spiral.from_dict(data, investigator=investigator, seed=seed)


def load_or_create(
    path: str | Path,
    topic: str,
    *,
    investigator: Investigator | None = None,
    seed: int = 0,
    **kw,
) -> Spiral:
    p = Path(path)
    if p.exists():
        return load(p, investigator=investigator, seed=seed)
    sp = Spiral(investigator=investigator, seed=seed, **kw)
    sp.seed_topic(topic)
    return sp
