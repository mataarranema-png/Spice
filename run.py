#!/usr/bin/env python3
"""เปิดระบบ FGP ด้วยการดับเบิลคลิกไฟล์นี้ (ใช้ได้ทุกระบบปฏิบัติการที่มี Python)"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fgp.__main__ import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
