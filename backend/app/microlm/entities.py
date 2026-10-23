"""Resolve model-extracted entity strings to real database records (fuzzy, typo tolerant)."""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from .. import models as m
from .catalog import STAGE_WORDS, TASK_ALIASES, clean


def _score(a: str, b: str) -> float:
    a, b = clean(a), clean(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    ra = SequenceMatcher(None, a, b).ratio()
    ta, tb = set(a.split()), set(b.split())
    jac = len(ta & tb) / len(ta | tb) if ta | tb else 0
    contain = 0.9 if (a in b or b in a) and min(len(a), len(b)) >= 4 else 0
    return max(ra, 0.5 * ra + 0.5 * jac, contain)


def best(query: str, candidates: dict[str, list[str]], cutoff: float = 0.62):
    """candidates: id -> [names/aliases]. returns (id, score) or None"""
    top = (None, 0.0)
    for cid, names in candidates.items():
        for n in names:
            s = _score(query, n)
            if s > top[1]:
                top = (cid, s)
    return top if top[1] >= cutoff else None


def parse_stage(text: str) -> int | None:
    t = text.lower()
    mm = re.search(r"\b([1-4])\b", t) or re.search(r"stage\s*([1-4])", t)
    if mm:
        return int(mm.group(1))
    for w, n in STAGE_WORDS.items():
        if re.search(rf"\b{w}\b", t):
            return n
    return None


def norm_cmp(text: str) -> str | None:
    mm = re.search(r"cmp\s*-?\s*(\d+)", text.lower())
    return f"CMP-{int(mm.group(1)):03d}" if mm else None


def resolve(db, text: str, entities: list[dict]) -> dict:
    """Return {'component': Component|None, 'task': Task|None, 'stage': int|None, 'workstation': Workstation|None, 'supplier': Supplier|None}
    Model entities are used first; regex / dictionary scans on the raw text act as a safety net."""
    out: dict = {"component": None, "task": None, "stage": None, "workstation": None, "supplier": None, "unresolved": []}
    comps = {c.id: [c.name] for c in db.query(m.Component).all()}
    tasks = {t.id: [t.name] + TASK_ALIASES.get(t.id, []) for t in db.query(m.Task).all()}
    status = {t.id: t.status for t in db.query(m.Task).all()}
    wss = {w.id: [w.name, w.ws_type] for w in db.query(m.Workstation).all()}
    sups = {s.id: [s.name, " ".join(s.name.split()[:2])] for s in db.query(m.Supplier).all()}

    for e in entities:
        t, val = e["type"], e["text"]
        if t == "CMP":
            cid = norm_cmp(val)
            if cid and db.get(m.Component, cid):
                out["component"] = db.get(m.Component, cid)
            elif val:
                out["unresolved"].append(val)
        elif t == "CNAME" and out["component"] is None:
            hit = best(val, comps)
            if hit:
                out["component"] = db.get(m.Component, hit[0])
            else:
                out["unresolved"].append(val)
        elif t == "STAGE":
            out["stage"] = parse_stage(val)
        elif t == "TASK" and out["task"] is None:
            out["task"] = _pick_task(db, val, tasks, status)
            if out["task"] is None:
                out["unresolved"].append(val)
        elif t == "WS" and out["workstation"] is None:
            mm = re.search(r"ws\s*-?\s*(\d+)", val.lower())
            wid = f"WS-{int(mm.group(1)):02d}" if mm else None
            if wid and db.get(m.Workstation, wid):
                out["workstation"] = db.get(m.Workstation, wid)
            else:
                hit = best(val, wss, 0.55)
                if hit:
                    out["workstation"] = db.get(m.Workstation, hit[0])
        elif t == "SUP" and out["supplier"] is None:
            hit = best(val, sups, 0.55)
            if hit:
                out["supplier"] = db.get(m.Supplier, hit[0])

    # ---- safety net on the raw text -------------------------------------------------
    low = text.lower()
    if out["component"] is None:
        cid = norm_cmp(low)
        if cid and db.get(m.Component, cid):
            out["component"] = db.get(m.Component, cid)
    if out["stage"] is None:
        mm = re.search(r"stage\s*-?\s*([1-4])", low)
        if mm:
            out["stage"] = int(mm.group(1))
        else:
            for w, n in STAGE_WORDS.items():
                if re.search(rf"stage\s+{w}\b", low):
                    out["stage"] = n
    if out["task"] is None:
        mm = re.search(r"\bt\s*-?\s*(\d{1,3})\b", low)
        if mm and db.get(m.Task, f"T-{int(mm.group(1)):03d}"):
            out["task"] = db.get(m.Task, f"T-{int(mm.group(1)):03d}")
    if out["workstation"] is None:
        mm = re.search(r"ws\s*-?\s*(\d+)", low)
        if mm and db.get(m.Workstation, f"WS-{int(mm.group(1)):02d}"):
            out["workstation"] = db.get(m.Workstation, f"WS-{int(mm.group(1)):02d}")
    # dictionary scan: longest n-gram matching a component/task name (handles missed tags & typos)
    words = re.findall(r"[a-z0-9]+", low)
    if out["component"] is None and not out["task"]:
        for n in range(4, 0, -1):
            hit = None
            for i in range(len(words) - n + 1):
                ph = " ".join(words[i:i + n])
                h = best(ph, comps, 0.82)
                if h and (hit is None or h[1] > hit[1]):
                    hit = h
            if hit:
                out["component"] = db.get(m.Component, hit[0])
                break
    if out["task"] is None and out["component"] is None:
        for n in range(4, 1, -1):
            hit = None
            for i in range(len(words) - n + 1):
                ph = " ".join(words[i:i + n])
                h = best(ph, tasks, 0.85)
                if h and (hit is None or h[1] > hit[1]):
                    hit = h
            if hit:
                out["task"] = _pick_task(db, hit[0], tasks, status) if False else db.get(m.Task, hit[0])
                break
    return out


def _pick_task(db, val: str, tasks, status):
    """Prefer exact alias hits; when several tasks tie, prefer a pending one (that is what users ask about)."""
    scored = []
    for tid, names in tasks.items():
        s = max((_score(val, n) for n in names), default=0)
        if s >= 0.62:
            bonus = 0.02 if status[tid] == "PENDING" else 0
            scored.append((s + bonus, tid))
    if not scored:
        return None
    scored.sort(reverse=True)
    return db.get(m.Task, scored[0][1])
