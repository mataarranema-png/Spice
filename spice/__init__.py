"""Spice — ระบบตั้งคำถามแบบก้นหอย (a self-expanding epistemic system).

    K_n -> Q_n -> E_n -> A_n -> C_n -> M_{n+1} -> Q_{n+1}

เป้าหมายไม่ใช่ "ระบบที่ไม่มีขอบเขต" (ซึ่งเป็นไปไม่ได้ — หน่วยความจำ เวลา
พลังงาน และการคำนวณยังยืนขวางประตูอยู่) แต่คือ **ระบบที่ค้นพบขอบเขตของ
ตัวเอง แล้วสร้างวิธีการใหม่เพื่อขยายขอบเขตนั้น**.

เริ่มต้นเร็วที่สุด:

    from spice import Spiral
    sp = Spiral.from_topic("ก้นหอย", seed=7)
    sp.run(10)
    print(sp.report())
"""

from .evolution import Population
from .graph import Edge, KnowledgeGraph, Node
from .investigator import (
    CompositeInvestigator,
    Investigator,
    ReflectiveInvestigator,
)
from .question import Question, QuestionLedger
from .scoring import Weights, score_question, select
from .selfmodel import Budget, CapabilityGap, Limit, SelfModel
from .spiral import EpochRecord, Spiral, Turn
from .strategies import Strategy, builtin_strategies
from .types import (
    EdgeSpec,
    EpistemicStatus,
    Finding,
    NodeSpec,
    QuestionLevel,
    Relation,
)

__version__ = "0.1.0"

__all__ = [
    "Budget",
    "CapabilityGap",
    "CompositeInvestigator",
    "Edge",
    "EdgeSpec",
    "EpistemicStatus",
    "EpochRecord",
    "Finding",
    "Investigator",
    "KnowledgeGraph",
    "Limit",
    "Node",
    "NodeSpec",
    "Population",
    "Question",
    "QuestionLedger",
    "QuestionLevel",
    "ReflectiveInvestigator",
    "Relation",
    "SelfModel",
    "Spiral",
    "Strategy",
    "Turn",
    "Weights",
    "__version__",
    "builtin_strategies",
    "score_question",
    "select",
]
