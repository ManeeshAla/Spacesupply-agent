"""LangGraph agent orchestrator.

   understand (Micro LM) --route--> tracking | supply | scheduling | monitoring | readiness (multi-agent) | smalltalk
                                          \\______________________  compose (+ optional Qwen)  _____/
"""
from __future__ import annotations

import json
from typing import Any, TypedDict

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph

from . import llm
from . import models as m
from .agents.base import fmt, log, now_hour
from .engine import engine
from .microlm.entities import resolve
from .microlm.infer import get_nlu

ROUTES = {
    "COMPONENT_LOCATION": "tracking", "COMPONENT_STATUS": "tracking", "STAGE_PROGRESS": "tracking",
    "INVENTORY_STATUS": "supply", "COMPONENT_SHORTAGE": "supply", "SUPPLIER_INFO": "supply",
    "VIEW_SCHEDULE": "scheduling", "DELAY_EXPLANATION": "scheduling", "RESCHEDULE_TASK": "scheduling",
    "DELAY_DETECTION": "monitoring", "ALERTS_SUMMARY": "monitoring",
    "TASK_READINESS": "readiness", "GREETING": "smalltalk", "HELP": "smalltalk",
}

EXAMPLES = ["Where is CMP-021?", "Is Stage 2 ready to start assembly?", "Are we missing any components for engine assembly?",
            "Why was Engine Assembly delayed?", "Which tasks are delayed?", "Show today's schedule", "Show alerts", "How is Stage 3 going?"]


class ChatState(TypedDict, total=False):
    query: str
    nlu: dict
    intent: str
    resolved: dict
    draft: str
    answer: str
    facts: dict
    trace: list
    clarify: bool
    llm_used: bool
    suggestions: list


def _db(config: RunnableConfig):
    return config["configurable"]["db"]


def _when(db, hour: int | None) -> str:
    if hour is None:
        return "unscheduled"
    d = hour - now_hour(db)
    return f"{fmt(db, hour)} (in {d}h)" if d > 0 else f"{fmt(db, hour)} (now)"


def _t(state, agent, action):
    state.setdefault("trace", []).append({"agent": agent, "action": action})


# ---------------------------------------------------------------- understand
def understand(state: ChatState, config: RunnableConfig):
    db = _db(config)
    nlu = get_nlu().predict(state["query"])
    resolved = resolve(db, state["query"], nlu["entities"])
    ents = ", ".join(f"{e['type']}='{e['text']}'" for e in nlu["entities"]) or "none"
    trace = [{"agent": "Language Agent", "action": f"Micro LM → intent {nlu['intent']} ({nlu['confidence']:.0%})"
                                                   + (" [keyword fallback]" if nlu["fallback"] else "") + f"; entities: {ents}"}]
    log(db, "Language Agent", f"“{state['query'][:80]}” → {nlu['intent']} ({nlu['confidence']:.0%})")
    return {"nlu": nlu, "intent": nlu["intent"], "resolved": resolved, "trace": trace, "facts": {}, "clarify": False}


def route(state: ChatState) -> str:
    if state["nlu"]["confidence"] < 0.30 and not state["nlu"]["fallback"]:
        return "smalltalk"
    return ROUTES.get(state["intent"], "smalltalk")


def _ask(state, text, suggestions=None):
    return {"draft": text, "clarify": True, "suggestions": suggestions or EXAMPLES[:4]}


# ---------------------------------------------------------------- tracking agent
def tracking_node(state: ChatState, config: RunnableConfig):
    db, r, intent = _db(config), state["resolved"], state["intent"]
    tr = engine.tracking
    if intent == "STAGE_PROGRESS":
        stages = tr.stage_progress(db)
        sid = r["stage"]
        sel = [s for s in stages if (sid is None or s["id"] == sid)]
        _t(state, "Tracking Agent", f"Computed progress for {'stage ' + str(sid) if sid else 'all stages'}")
        lines = [f"• {s['name']}: {s['progress']}% ({s['tasks_done']}/{s['tasks_total']} tasks done, {s['tasks_active']} running) – {s['status']}" for s in sel]
        k = engine._kpis(db)
        tail = f"\nProjected launch-readiness review: {k['launch_readiness']}" + (f" ({k['launch_readiness_late_hours']}h late)" if k["launch_readiness_late_hours"] else " (on time)")
        return {"draft": "Assembly progress:\n" + "\n".join(lines) + (tail if sid is None else ""), "facts": {"stages": sel}, "trace": state["trace"]}
    comp = r["component"]
    if comp is None:
        return {**_ask(state, "Which component do you mean? Give me an ID like CMP-021 or a name such as “fuel pump”.",
                       ["Where is CMP-021?", "What is the status of the fuel pump?"]), "trace": state["trace"]}
    loc = tr.locate(db, comp.id)
    _t(state, "Tracking Agent", f"Looked up {comp.id} lifecycle state and event history")
    d = loc["delivery"]
    deliv = ""
    if d:
        deliv = f" Delivery {d['id']} ETA {_when(db, d['eta_hour'])}" + (f", delayed {d['delay_hours']}h" if d["delay_hours"] else "") + "."
    if intent == "COMPONENT_LOCATION":
        text = f"{comp.id} ({comp.name}) is at: {comp.location}. Status: {comp.status.replace('_', ' ').lower()}.{deliv}"
    else:
        hist = tr.history(db, comp.id)[-4:]
        users = ", ".join(f"{t.id}" for t in engine.supply.tasks_needing(db, comp.id, pending_only=False)) or "–"
        text = (f"{comp.id} ({comp.name}) – status: {comp.status.replace('_', ' ').lower()}; inspection: {comp.inspection_status.lower().replace('_', ' ')}; "
                f"location: {comp.location}; on hand {comp.quantity}, required {comp.required_quantity}; supplier {comp.supplier.name}; used by {users}.{deliv}\n"
                "Recent events:\n" + "\n".join(f"• {fmt(db, e.hour)} – {e.event_type.replace('_', ' ').lower()}" + (f" ({e.note})" if e.note and e.note != 'Seed history' else '') for e in hist))
    return {"draft": text, "facts": loc, "trace": state["trace"]}


# ---------------------------------------------------------------- supply agent
def supply_node(state: ChatState, config: RunnableConfig):
    db, r, intent = _db(config), state["resolved"], state["intent"]
    sp = engine.supply
    if intent == "INVENTORY_STATUS":
        s = sp.summary(db)
        rows = sp.shortages(db, stage_id=r["stage"])[:5]
        _t(state, "Supply Agent", "Aggregated inventory classes and open shortages")
        text = (f"Inventory{' for Stage ' + str(r['stage']) if r['stage'] else ''}: {s['sufficient']} lots sufficient, {s['low']} low, "
                f"{s['critical']} critical, {s['on_order']} on order.")
        if rows:
            text += "\nTop shortages:\n" + "\n".join(f"• {x['id']} {x['name']}: need {x['required']}, available {x['available']} (short {x['shortage']}), {x['class'].lower().replace('_', ' ')}" for x in rows)
        return {"draft": text, "facts": {"summary": s, "shortages": rows}, "trace": state["trace"]}
    if intent == "COMPONENT_SHORTAGE":
        comp, task, stage = r["component"], r["task"], r["stage"]
        if comp:
            rows = [x for x in sp.inventory_rows(db) if x["id"] == comp.id]
            scope = comp.name
        elif task:
            rows = sp.shortages(db, task_id=task.id)
            scope = f"{task.id} {task.name}"
        else:
            rows = sp.shortages(db, stage_id=stage)
            scope = f"Stage {stage}" if stage else "the whole vehicle"
        _t(state, "Supply Agent", f"Compared required vs available quantities for {scope}")
        if comp:
            x = rows[0]
            if x["shortage"] == 0:
                text = f"No shortage for {x['id']} {x['name']}: need {x['required']}, available {x['available']}."
            else:
                text = (f"{x['id']} {x['name']}: need {x['required']}, available {x['available']} → short {x['shortage']} "
                        f"({x['class'].lower().replace('_', ' ')}). Incoming {x['incoming']}" + (f", next ETA {_when(db, x['next_eta_hour'])}" if x["next_eta_hour"] is not None else "")
                        + (f". Affects: {', '.join(sp_tasks(db, x['id']))}" if sp_tasks(db, x['id']) else "."))
        elif not rows:
            text = f"No component shortages for {scope}."
        else:
            text = f"{len(rows)} component lot(s) are short for {scope}:\n" + "\n".join(
                f"• {x['id']} {x['name']}: short {x['shortage']} of {x['required']} – {x['status'].replace('_', ' ').lower()}"
                + (f", ETA {_when(db, x['next_eta_hour'])}" if x['next_eta_hour'] is not None else "") + (" (DELAYED)" if x["delayed"] else "") for x in rows[:7])
            if len(rows) > 7:
                text += f"\n…and {len(rows) - 7} more."
        return {"draft": text, "facts": {"rows": rows[:10]}, "trace": state["trace"]}
    # SUPPLIER_INFO
    comp, sup = r["component"], r["supplier"]
    _t(state, "Supply Agent", "Looked up supplier and open deliveries")
    if comp:
        ds = sp.open_deliveries(db, comp.id)
        text = f"{comp.id} ({comp.name}) is supplied by {comp.supplier.name} (reliability {comp.supplier.reliability:.0%}, lead time {comp.supplier.lead_time_days} days)."
        text += "\n" + ("\n".join(f"• Delivery {d.id}: {d.quantity} unit(s), ETA {_when(db, d.eta_hour)}" + (f", delayed {d.delay_hours}h" if d.delay_hours else "") for d in ds)
                        if ds else "No open delivery – the lot has already arrived.")
        return {"draft": text, "facts": {"component": comp.id}, "trace": state["trace"]}
    rep = sp.supplier_report(db, sup.name if sup else None)
    rep = [x for x in rep if x["open_deliveries"]]
    if not rep:
        return {"draft": "No open deliveries.", "trace": state["trace"]}
    lines = []
    for x in (rep[:1] if sup else rep):
        for d in x["open_deliveries"][:6]:
            lines.append(f"• {d['id']} {d['component_id']} {d['component']} – {x['name']}, ETA {_when(db, d['eta_hour'])}" + (f", delayed {d['delay_hours']}h" if d["delay_hours"] else ""))
    return {"draft": ("Open deliveries" + (f" from {sup.name}" if sup else "") + ":\n" + "\n".join(sorted(lines))), "facts": {"suppliers": rep[:4]}, "trace": state["trace"]}


def sp_tasks(db, cid):
    return [f"{t.id} {t.name}" for t in engine.supply.tasks_needing(db, cid)]


# ---------------------------------------------------------------- scheduling agent
def scheduling_node(state: ChatState, config: RunnableConfig):
    db, r, intent = _db(config), state["resolved"], state["intent"]
    sa = engine.scheduling
    rows = sa.schedule_rows(db)
    now = now_hour(db)
    if intent == "RESCHEDULE_TASK":
        res = sa.plan(db, "CPSAT", trigger="Chat request")
        engine.monitoring.scan(db)
        db.commit()
        _t(state, "Scheduling Agent", f"Re-ran OR-Tools CP-SAT ({res['solver_note']})")
        met = res["metrics"]
        text = (f"Schedule re-optimised with OR-Tools CP-SAT: makespan {met['makespan']}h, {met['tardy_tasks']} task(s) projected late, "
                f"{len(res['changes'])} task(s) moved.")
        if res["changes"]:
            text += "\n" + "\n".join(f"• {c['task_id']} {c['name']}: {c['delta_hours']:+d}h – {c['reason']}" for c in res["changes"][:5])
        return {"draft": text, "facts": res, "trace": state["trace"]}
    if intent == "DELAY_EXPLANATION":
        task = r["task"]
        if task is None and r["stage"]:
            cand = [x for x in rows if x["stage_id"] == r["stage"] and x["status"] == m.T_PENDING]
            cand.sort(key=lambda x: (-x["shift_hours"], -x["late_hours"]))
            task = db.get(m.Task, cand[0]["id"]) if cand else None
        if task is None:
            cand = sa.delayed_tasks(db)
            if not cand:
                return {"draft": "Nothing has been delayed relative to the original plan, so there is nothing to explain.", "trace": state["trace"]}
            task = db.get(m.Task, cand[0]["id"])
        ex = sa.explain_task(db, task.id)
        _t(state, "Scheduling Agent", f"Traced the binding constraints behind {task.id}")
        if task.status != m.T_PENDING:
            return {"draft": f"{task.id} {task.name} is already {task.status.lower().replace('_', ' ')}.", "facts": ex, "trace": state["trace"]}
        ver = sa.current_version(db)
        head = f"{task.id} {task.name} is planned for {_when(db, ex['planned_start_hour'])} on {ex.get('workstation')}"
        if ex["shift_hours"] > 0:
            head += f" – {ex['shift_hours']}h later than the original plan ({fmt(db, ex['original_start_hour'])})."
        elif ex["shift_hours"] < 0:
            head += f" – {-ex['shift_hours']}h earlier than the original plan."
        else:
            head += ", unchanged from the original plan."
        if ex["late_hours"] > 0:
            head += f" It is projected to finish {ex['late_hours']}h after its deadline."
        why = "Why:\n" + "\n".join("• " + c for c in ex["chain"]) if ex["chain"] else ""
        trig = f"\nLast re-plan trigger: {ver.trigger}." if ver and ver.trigger not in ("Initial plan",) else ""
        return {"draft": head + ("\n" + why if why else "") + trig, "facts": ex, "trace": state["trace"]}
    # VIEW_SCHEDULE
    ws, stage, task = r["workstation"], r["stage"], r["task"]
    sel = rows
    title = "Today / next 24 hours"
    if task:
        sel, title = [x for x in rows if x["id"] == task.id], task.name
    elif ws:
        sel, title = [x for x in rows if x["workstation"] == ws.id and x["status"] != m.T_COMPLETED], f"{ws.id} ({ws.name})"
    elif stage:
        sel, title = [x for x in rows if x["stage_id"] == stage and x["status"] != m.T_COMPLETED], f"Stage {stage}"
    else:
        sel = [x for x in rows if x["status"] == m.T_IN_PROGRESS or (x["status"] == m.T_PENDING and x["start_hour"] is not None and x["start_hour"] - now <= 24)]
    sel = sorted(sel, key=lambda x: (x["start_hour"] if x["start_hour"] is not None else 10 ** 6))
    _t(state, "Scheduling Agent", f"Read the current schedule (v{sa.current_version(db).id}) for: {title}")
    if not sel:
        return {"draft": f"Nothing scheduled for {title}.", "trace": state["trace"]}
    lines = [f"• {x['id']} {x['name']} – {x['workstation'] or '-'} – " + ("RUNNING, ends " + _when(db, x["end_hour"]) if x["status"] == m.T_IN_PROGRESS
             else ("done" if x["status"] == m.T_COMPLETED else "starts " + _when(db, x["start_hour"]))) for x in sel[:9]]
    return {"draft": f"Schedule – {title}:\n" + "\n".join(lines) + (f"\n…and {len(sel) - 9} more." if len(sel) > 9 else ""), "facts": {"tasks": sel[:12]}, "trace": state["trace"]}


# ---------------------------------------------------------------- monitoring agent
def monitoring_node(state: ChatState, config: RunnableConfig):
    db, r, intent = _db(config), state["resolved"], state["intent"]
    if intent == "ALERTS_SUMMARY":
        alerts = db.query(m.Alert).filter(m.Alert.status == "OPEN").order_by(m.Alert.id.desc()).all()
        _t(state, "Monitoring Agent", f"Read {len(alerts)} open alert(s)")
        if not alerts:
            return {"draft": "No open alerts – all systems nominal.", "trace": state["trace"]}
        rank = {"CRITICAL": 0, "WARNING": 1, "INFO": 2}
        alerts.sort(key=lambda a: (rank[a.severity], -a.id))
        c = {s: sum(1 for a in alerts if a.severity == s) for s in rank}
        return {"draft": f"{len(alerts)} open alert(s): {c['CRITICAL']} critical, {c['WARNING']} warning, {c['INFO']} info.\n" +
                         "\n".join(f"• [{a.severity}] {a.title}" for a in alerts[:6]), "facts": {"counts": c}, "trace": state["trace"]}
    # DELAY_DETECTION
    sa = engine.scheduling
    delayed = sa.delayed_tasks(db)
    if r["stage"]:
        delayed = [x for x in delayed if x["stage_id"] == r["stage"]]
    dd = [d for d in db.query(m.Delivery).filter(m.Delivery.status == "DELAYED").all()]
    _t(state, "Monitoring Agent", "Compared the live plan against original dates and deadlines")
    if not delayed and not dd:
        return {"draft": "No delayed tasks or deliveries right now.", "trace": state["trace"]}
    lines = [f"• {x['id']} {x['name']}: {x['shift_hours']:+d}h vs original plan" + (f", projected {x['late_hours']}h past deadline" if x["late_hours"] else "") for x in delayed[:6]]
    lines += [f"• Delivery {d.id} ({d.component_id} {d.component.name}) delayed {d.delay_hours}h by {d.supplier.name}" for d in dd[:4]]
    return {"draft": f"{len(delayed)} task(s) delayed, {len(dd)} delivery(ies) delayed:\n" + "\n".join(lines), "facts": {"tasks": delayed[:8]}, "trace": state["trace"]}


# ---------------------------------------------------------------- readiness (multi-agent)
def readiness_node(state: ChatState, config: RunnableConfig):
    db, r = _db(config), state["resolved"]
    sa, sp, tr = engine.scheduling, engine.supply, engine.tracking
    if r["task"] is not None:
        rd = sa.task_readiness(db, r["task"].id)
        _t(state, "Tracking Agent", f"Checked lifecycle state of {len(rd['components'])} required component(s)")
        _t(state, "Supply Agent", "Checked required vs available quantities")
        _t(state, "Scheduling Agent", "Checked predecessors and workstation availability")
        title, blockers, ready, frontier = f"{rd['task_id']} {rd['name']}", rd["blockers"], rd["can_start_now"], [rd]
    elif r["stage"]:
        rd = sa.stage_readiness(db, r["stage"])
        n = len(rd["frontier"])
        _t(state, "Tracking Agent", f"Checked component states for {n} eligible task(s) in Stage {r['stage']}")
        _t(state, "Supply Agent", f"Checked shortages: {len(sp.shortages(db, stage_id=r['stage']))} short lot(s) in stage")
        _t(state, "Scheduling Agent", "Checked dependencies and workstation availability")
        title, blockers, ready, frontier = rd["stage"], rd["blockers"], rd["ready"], rd["frontier"]
        if rd.get("complete"):
            return {"draft": f"{title} is already complete.", "facts": rd, "trace": state["trace"]}
    else:
        return {**_ask(state, "Which stage or task? For example “Is Stage 2 ready?” or “Can engine assembly start?”",
                       ["Is Stage 2 ready to start assembly?", "Can engine assembly start today?"]), "trace": state["trace"]}
    if ready:
        text = f"{title} is ready to start now."
        if frontier:
            text += " Eligible: " + ", ".join(f"{f['task_id']} {f['name']}" + (f" (planned on {f['planned_workstation']})" if f.get('planned_workstation') else "") for f in frontier[:4]) + "."
        return {"draft": text, "facts": {"ready": True}, "trace": state["trace"]}
    seen, lines = set(), []
    for b in blockers:
        key = (b["type"], b["ref"])
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"• {b['text']}" + (f" (for {b['task_id']})" if b.get("task_id") and r["task"] is None else ""))
    nxt = [f for f in frontier if f.get("planned_start_hour") is not None]
    plan = ""
    if nxt:
        first = min(nxt, key=lambda f: f["planned_start_hour"])
        plan = f"\nEarliest planned start: {first['task_id']} {first['name']} on {first['planned_workstation']} at {_when(db, first['planned_start_hour'])}."
    return {"draft": f"**{title} is NOT ready to start.**\nReasons:\n" + "\n".join(lines[:7]) + plan, "facts": {"ready": False, "blockers": blockers[:10]}, "trace": state["trace"]}


# ---------------------------------------------------------------- small talk / help / low confidence
def smalltalk_node(state: ChatState, config: RunnableConfig):
    intent, conf = state["intent"], state["nlu"]["confidence"]
    if conf < 0.30 and not state["nlu"]["fallback"]:
        tops = [t["intent"].replace("_", " ").lower() for t in state["nlu"]["top"][:3]]
        return {**_ask(state, f"I am not sure what you mean (my best guesses: {', '.join(tops)}). Could you rephrase? Try one of these:"), "trace": state["trace"]}
    if intent == "GREETING":
        return {"draft": "Hello! I am SpaceSupply-Agent. I can track components, check inventory and shortages, explain schedule changes and monitor alerts. How can I assist you today?",
                "suggestions": EXAMPLES[:4], "trace": state["trace"]}
    return {"draft": ("I understand questions about:\n• Component location and status (“Where is CMP-021?”)\n• Inventory, shortages and suppliers\n"
                      "• Readiness (“Is Stage 2 ready to start assembly?”)\n• The schedule, delays and why tasks moved\n• Alerts and stage progress\n"
                      "• Commands such as “reschedule engine assembly”."), "suggestions": EXAMPLES[:5], "trace": state["trace"]}


# ---------------------------------------------------------------- compose
def compose(state: ChatState, config: RunnableConfig):
    draft = state.get("draft", "")
    polished = None if state.get("clarify") else llm.polish(state["query"], draft)
    if polished:
        _t(state, "Language Agent", f"Qwen layer rephrased the answer ({llm.QWEN_MODEL})")
    return {"answer": polished or draft, "llm_used": bool(polished), "trace": state.get("trace", [])}


def build():
    g = StateGraph(ChatState)
    g.add_node("understand", understand)
    for n, fn in [("tracking", tracking_node), ("supply", supply_node), ("scheduling", scheduling_node), ("monitoring", monitoring_node),
                  ("readiness", readiness_node), ("smalltalk", smalltalk_node)]:
        g.add_node(n, fn)
        g.add_edge(n, "compose")
    g.add_node("compose", compose)
    g.add_edge(START, "understand")
    g.add_conditional_edges("understand", route, {n: n for n in ["tracking", "supply", "scheduling", "monitoring", "readiness", "smalltalk"]})
    g.add_edge("compose", END)
    return g.compile()


_graph = None


def chat(db, query: str) -> dict:
    global _graph
    if _graph is None:
        _graph = build()
    out = _graph.invoke({"query": query, "trace": []}, config={"configurable": {"db": db}})
    nlu = out["nlu"]
    db.commit()
    return {"query": query, "answer": out["answer"], "intent": out["intent"], "confidence": nlu["confidence"], "fallback": nlu["fallback"],
            "entities": nlu["entities"], "top_intents": nlu["top"], "agents_called": out["trace"], "llm_used": out.get("llm_used", False),
            "clarify": out.get("clarify", False), "suggestions": out.get("suggestions", []), "latency_ms": nlu["latency_ms"]}
