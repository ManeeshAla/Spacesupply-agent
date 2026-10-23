"""Domain vocabulary used to synthesise Micro-LM training data and to resolve entities."""
from __future__ import annotations

import re

from ..seed import SUPPLIERS, TASKS, WORKSTATIONS

INTENTS = [
    "COMPONENT_LOCATION", "COMPONENT_STATUS", "INVENTORY_STATUS", "COMPONENT_SHORTAGE", "SUPPLIER_INFO",
    "TASK_READINESS", "VIEW_SCHEDULE", "DELAY_DETECTION", "DELAY_EXPLANATION", "RESCHEDULE_TASK",
    "STAGE_PROGRESS", "ALERTS_SUMMARY", "GREETING", "HELP",
]

ENTITY_TYPES = ["CMP", "CNAME", "STAGE", "TASK", "WS", "SUP"]
TAGS = ["O"] + [f"{p}-{t}" for t in ENTITY_TYPES for p in ("B", "I")]


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", text.lower())).strip()


COMPONENT_NAMES = sorted({clean(c[0]) for t in TASKS for c in t[7]})
TASK_NAMES = {f"T-{t[0]:03d}": clean(t[1]) for t in TASKS}
TASK_ALIASES = {
    "T-013": ["engine assembly", "engine installation", "turbopump installation", "pump installation"],
    "T-012": ["engine mount", "engine mount assembly"],
    "T-011": ["tank integration"],
    "T-014": ["fuel line", "fuel line connection"],
    "T-015": ["avionics check", "avionics system check"],
    "T-016": ["hot fire test", "hot fire readiness test"],
    "T-034": ["stacking", "stage stacking", "vehicle stacking"],
    "T-038": ["final test", "final vehicle test", "integrated vehicle test"],
    "T-028": ["flight computer installation", "flight computer"],
    "T-029": ["navigation calibration", "inertial calibration"],
    "T-031": ["fairing assembly", "payload fairing"],
    "T-039": ["launch readiness review", "launch readiness"],
    "T-024": ["pressure test"],
    "T-007": ["booster pressure test", "leak test"],
    "T-010": ["tank fabrication"],
    "T-036": ["fairing integration", "upper section integration"],
    "T-037": ["electrical check", "vehicle electrical check"],
    "T-032": ["systems test"],
    "T-022": ["thruster fit", "attitude control"],
}
# phrases the user can say for a task (training slot values): aliases + names that don't start with 'stage <n>'
TASK_PHRASES = sorted({a for v in TASK_ALIASES.values() for a in v} |
                      {n for n in TASK_NAMES.values() if not re.match(r"stage \d", n) and not re.search(r"\d", n)})
SUPPLIER_NAMES = [clean(s[1]) for s in SUPPLIERS]
SUPPLIER_SHORT = sorted({" ".join(clean(s[1]).split()[:2]) for s in SUPPLIERS})
WS_NAMES = sorted({clean(w[1]) for w in WORKSTATIONS if not re.search(r"\d", w[1])} | {"test cell", "avionics lab", "inspection lab"})
WS_IDS = [w[0] for w in WORKSTATIONS]
STAGE_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4}
