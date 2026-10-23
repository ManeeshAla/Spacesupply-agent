"""Optional Qwen language layer (served by a local Ollama).  Pure add-on: the system works without it.

The Micro LM stays responsible for understanding; the agents stay responsible for the facts.
Qwen only *rephrases* the agents' draft answer, and its output is rejected if it alters any ID or number.
"""
from __future__ import annotations

import re
import time

import httpx

from .config import OLLAMA_URL, QWEN_MODEL, USE_QWEN

_cache = {"t": 0.0, "ok": False}
FACT_RE = re.compile(r"(?:CMP|WS|T|DEL|SUP)-\d+|\d+(?:\.\d+)?")


def available() -> bool:
    if USE_QWEN == "off":
        return False
    if time.time() - _cache["t"] < 30:
        return _cache["ok"]
    try:
        r = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=0.6)
        names = [m.get("name", "") for m in r.json().get("models", [])]
        _cache.update(t=time.time(), ok=r.status_code == 200 and any(QWEN_MODEL.split(":")[0] in n for n in names))
    except Exception:
        _cache.update(t=time.time(), ok=False)
    return _cache["ok"]


def facts_preserved(draft: str, rewritten: str) -> bool:
    """Every ID / number in the draft must still be present, and no new ones may appear."""
    a = set(FACT_RE.findall(draft))
    b = set(FACT_RE.findall(rewritten))
    return a <= b and not (b - a)


# Numbers an answer may always use: list positions, "24 hours" style rephrasing of ratios,
# and the small integers a model uses to count things it just listed.
_SAFE_NUMBERS = {str(i) for i in range(0, 11)}


def ungrounded_facts(answer: str, sources: str) -> list[str]:
    """IDs / numbers that appear in the answer but in none of the sources.

    `sources` is the concatenation of every tool result the model saw plus the user's own
    question, so anything the agents actually returned is allowed. Unlike
    `facts_preserved` this is one-directional: the model may leave facts out, it may not
    invent them.
    """
    allowed = set(FACT_RE.findall(sources))
    # parse the numeric tokens once: an id such as CMP-003 in the sources must not abort the
    # numeric comparison for every other token
    numbers = []
    for a in allowed:
        try:
            numbers.append(float(a))
        except ValueError:
            continue
    out = []
    for tok in FACT_RE.findall(answer):
        if tok in allowed or tok in _SAFE_NUMBERS:
            continue
        try:
            v = float(tok)
        except ValueError:
            out.append(tok)          # an id that is not in the sources
            continue
        if any(abs(v - n) < 1e-9 for n in numbers):
            continue                 # 8 vs 8.0 vs 08 are the same fact
        if any(n <= 1.0 and abs(v - round(n * 100)) < 1e-9 for n in numbers):
            continue                 # a fraction reported as a percentage: 0.89 -> 89%
        out.append(tok)
    return sorted(set(out))


def facts_grounded(answer: str, sources: str) -> bool:
    """True if the answer introduces no ID or number that the tools did not return."""
    return not ungrounded_facts(answer, sources)


def polish(question: str, draft: str) -> str | None:
    if not available():
        return None
    try:
        from langchain_core.prompts import ChatPromptTemplate
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are SpaceSupply-Agent, an assistant for a launch-vehicle assembly line. Rewrite the DRAFT ANSWER so it reads "
                       "naturally and concisely (max 6 lines). Use ONLY the facts in the draft. Keep every ID, number and time exactly. "
                       "Do not add new facts, numbers or advice."),
            ("human", "User question: {question}\n\nDRAFT ANSWER:\n{draft}")])
        msgs = prompt.format_messages(question=question, draft=draft)
        payload = {"model": QWEN_MODEL, "stream": False, "options": {"temperature": 0.2},
                   "messages": [{"role": "system" if m.type == "system" else "user", "content": m.content} for m in msgs]}
        r = httpx.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=25)
        text = r.json()["message"]["content"].strip()
        return text if text and facts_preserved(draft, text) else None
    except Exception:
        return None
