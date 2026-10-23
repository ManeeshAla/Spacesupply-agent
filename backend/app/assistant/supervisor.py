"""The supervisor agent: a LangGraph tool-calling loop driven by Gemini.

    START -> agent --(tool calls?)--> tools --> agent -> ... -> END

The Micro LM runs first and its intent/entity guess is injected into the prompt as a hint,
so the fast local model still does the understanding work it was trained for. Everything the
answer contains has to come out of a tool result: after the final text is produced it is
checked by `llm.facts_grounded`, and an answer that invents an id or a number is replaced by
a deterministic summary of the tool output.

Conversation memory is a LangGraph checkpointer keyed by session id, so follow-ups such as
"and what about its supplier?" resolve against the previous turn.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Annotated, Any, AsyncIterator, Callable, TypedDict

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from .. import llm
from ..config import CHAT_HISTORY_TURNS, GEMINI_MAX_RETRIES, MAX_TOOL_STEPS
from . import gemini
from .tools import REGISTRY, ToolCtx, run_tool

SYSTEM_PROMPT = """You are SpaceSupply-Agent, the assistant for a launch-vehicle assembly line \
(a simulated 4-stage vehicle with synthetic suppliers, component lots, workstations and tasks).

HOW YOU WORK
- You have no knowledge of this plant. Every fact you state must come from a tool result in \
this conversation. Call the tools you need before answering.
- Never invent or estimate an id, a quantity, a date, an hour or a percentage. If a tool did \
not return it, say you do not have it.
- If a tool returns an error or an empty result, say so plainly and suggest what would help \
(for example a component id). Do not guess what the answer might have been.
- Ids look like CMP-021 (component lot), T-012 (task), WS-04 (workstation), DEL-007 \
(delivery), SUP-02 (supplier). Stages are 1-4. All times are simulated plant time.
- For broad questions ("how are things?") call get_plant_status. For anything about one \
component, task, stage, supplier or alert, call the specific tool.
- When the user says "show me", "open" or "take me to", also call show_dashboard so their \
screen follows the conversation.

ACTIONS
- delay_delivery, reject_component, workstation_down, replan_schedule and advance_time change \
the simulation. When one of them returns status "confirmation_required", nothing has happened \
yet: tell the user what will happen and that they need to press Confirm. Never say an action \
is done unless the tool result says it was.

STYLE
- Answer in plain prose, at most about 6 short lines, no preamble. Use "- " bullets for lists.
- Quote the exact ids and numbers from the tools. Give times as the tools give them.
- You may use **bold** for emphasis. Do not use markdown tables or headings.
- If the question is not about this assembly line, say that is outside what you cover and \
name a couple of things you can do."""


class ChatState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    steps: int


# ---------------------------------------------------------------- tool schemas
def _noop(**_kw):  # StructuredTool needs a callable; we dispatch ourselves in the tools node
    raise RuntimeError("tools are executed by the supervisor, not by LangChain")


_lc_tools: list[StructuredTool] | None = None


def lc_tools() -> list[StructuredTool]:
    global _lc_tools
    if _lc_tools is None:
        _lc_tools = [StructuredTool(name=s.name, description=s.description, args_schema=s.args, func=_noop)
                     for s in REGISTRY.values()]
    return _lc_tools


# ---------------------------------------------------------------- graph
def _trim(messages: list[AnyMessage]) -> list[AnyMessage]:
    """Keep the most recent turns without splitting a tool-call/tool-result pair.

    The system prompt is never stored in the checkpoint; it is prepended on every call, so
    changing it takes effect immediately and memory holds only the conversation.
    """
    limit = max(4, CHAT_HISTORY_TURNS * 3)
    rest = [x for x in messages if not isinstance(x, SystemMessage)]
    if len(rest) <= limit:
        cut = rest
    else:
        cut = rest[-limit:]
    # a ToolMessage with no preceding tool call is rejected by the API
    while cut and isinstance(cut[0], ToolMessage):
        cut = cut[1:]
    return cut


async def _agent_node(state: ChatState, config) -> dict:
    ctx: ToolCtx = config["configurable"]["ctx"]
    factory: Callable[[str], Any] = config["configurable"]["model_factory"]

    def bind(name: str):
        return factory(name).bind_tools(lc_tools())

    msgs = [SystemMessage(content=SYSTEM_PROMPT)] + _trim(state["messages"])
    msg, model_used = await _stream_model(bind, msgs, ctx)
    ctx.model_used = model_used
    return {"messages": [msg], "steps": state.get("steps", 0) + 1}


async def _stream_model(bind, messages, ctx: ToolCtx):
    """Stream one model turn, forwarding text deltas to ctx.on_token.

    Retries only while nothing has been emitted yet: once the user has seen tokens we must
    not restart the same answer, so a mid-stream failure is surfaced instead.
    """
    last: BaseException | None = None
    quota = False
    chain = gemini.model_chain()
    tries = max(1, GEMINI_MAX_RETRIES)
    for mi, name in enumerate(chain):
        for attempt in range(tries):
            emitted = False
            acc = None
            try:
                async for chunk in bind(name).astream(messages):
                    acc = chunk if acc is None else acc + chunk
                    text = _text_of(chunk)
                    if text:
                        emitted = True
                        ctx.on_token(text)
                if acc is None:
                    raise RuntimeError("empty response from the model")
                return _as_ai_message(acc), name
            except Exception as exc:
                last = exc
                if emitted or not gemini.is_retryable(exc):
                    raise
                quota = quota or gemini.is_quota_error(exc)
                if attempt >= tries - 1:
                    break
                delay = gemini.backoff_delay(attempt)
                ctx.on_note(f"{name} is busy or rate-limited; retrying in {delay:.1f}s")
                await asyncio.sleep(delay)
        if mi + 1 < len(chain):
            ctx.on_note(f"Switching to {chain[mi + 1]}")
    if quota:
        raise gemini.QuotaExceeded(str(last))
    raise last if last else RuntimeError("Gemini call failed")


def _text_of(chunk) -> str:
    c = getattr(chunk, "content", "")
    if isinstance(c, str):
        return c
    if isinstance(c, list):  # Gemini may return content parts
        return "".join(p.get("text", "") for p in c if isinstance(p, dict) and p.get("type") == "text")
    return ""


def _as_ai_message(acc) -> AIMessage:
    if isinstance(acc, AIMessage) and not hasattr(acc, "tool_call_chunks"):
        return acc
    return AIMessage(content=acc.content, tool_calls=list(getattr(acc, "tool_calls", []) or []),
                     additional_kwargs=getattr(acc, "additional_kwargs", {}) or {})


def _tools_node(state: ChatState, config) -> dict:
    ctx: ToolCtx = config["configurable"]["ctx"]
    last = state["messages"][-1]
    out: list[ToolMessage] = []
    for call in last.tool_calls:
        name, args = call["name"], call.get("args") or {}
        ctx.emit("tool_call", {"tool": name, "args": args})
        started = time.perf_counter()
        result = run_tool(ctx, name, args)
        ms = int((time.perf_counter() - started) * 1000)
        payload = json.dumps(result, default=str)[:6000]
        ctx.called.append({"tool": name, "args": args, "ms": ms, "ok": "error" not in result})
        ctx.sources.append(payload)
        ctx.emit("tool_result", {"tool": name, "ms": ms, "ok": "error" not in result,
                                 "error": result.get("error")})
        out.append(ToolMessage(content=payload, tool_call_id=call["id"], name=name))
        if ctx.pending:          # stop after a confirmation request; nothing else should run
            break
    return {"messages": out}


def _route(state: ChatState) -> str:
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and getattr(last, "tool_calls", None) and state.get("steps", 0) <= MAX_TOOL_STEPS:
        return "tools"
    return END


_graph = None


def graph():
    global _graph
    if _graph is None:
        g = StateGraph(ChatState)
        g.add_node("agent", _agent_node)
        g.add_node("tools", _tools_node)
        g.add_edge(START, "agent")
        g.add_conditional_edges("agent", _route, {"tools": "tools", END: END})
        g.add_edge("tools", "agent")
        _graph = g.compile(checkpointer=MemorySaver())
    return _graph


def reset_memory() -> None:
    """Drop all conversation memory (used by /api/reset and by the tests)."""
    global _graph
    _graph = None


def forget(session_id: str) -> None:
    """Drop one conversation. Falls back to clearing everything if the saver cannot do it."""
    g = _graph
    if g is None:
        return
    saver = getattr(g, "checkpointer", None)
    try:
        saver.delete_thread(session_id)
    except Exception:
        reset_memory()


# ---------------------------------------------------------------- prompt assembly
def _hint(db, query: str) -> tuple[str, dict]:
    """Run the Micro LM first and turn its guess into a prompt hint."""
    try:
        from ..microlm.entities import resolve
        from ..microlm.infer import get_nlu
        nlu = get_nlu().predict(query)
        res = resolve(db, query, nlu["entities"])
        bits = []
        if res.get("component") is not None:
            bits.append(f"component {res['component'].id} ({res['component'].name})")
        if res.get("task") is not None:
            bits.append(f"task {res['task'].id} ({res['task'].name})")
        if res.get("stage"):
            bits.append(f"stage {res['stage']}")
        if res.get("workstation") is not None:
            bits.append(f"workstation {res['workstation'].id}")
        if res.get("supplier") is not None:
            bits.append(f"supplier {res['supplier'].name}")
        hint = (f"[Micro LM hint - a small local model's guess, verify with tools: intent "
                f"{nlu['intent']} ({nlu['confidence']:.0%})"
                + (f"; resolved {', '.join(bits)}" if bits else "")
                + (f"; unrecognised: {', '.join(res['unresolved'])}" if res.get("unresolved") else "") + "]")
        return hint, nlu
    except Exception:
        return "", {}


# ---------------------------------------------------------------- public API
def _default_factory(name: str):
    """Build the real Gemini model, or refuse clearly when there is no key to use."""
    if not gemini.configured():
        raise gemini.NoApiKey("GEMINI_API_KEY is not set")
    return gemini.make_model(name)


def _finalise(ctx: ToolCtx, query: str, answer: str) -> tuple[str, list[str]]:
    """Apply the grounding guard. Returns (final_answer, ungrounded_tokens)."""
    sources = "\n".join(ctx.sources) + "\n" + query
    bad = llm.ungrounded_facts(answer, sources)
    if not bad:
        return answer, []
    return _deterministic_answer(ctx, bad), bad


def _deterministic_answer(ctx: ToolCtx, bad: list[str]) -> str:
    """Replacement text built only from tool output, used when the guard trips.

    The rejected values are deliberately not repeated here - they were never real, and the
    point of the guard is to keep them off the screen. They go to the UI in `ungrounded`.
    """
    head = (f"I dropped my draft answer because {'a figure' if len(bad) == 1 else 'some figures'} in it "
            "did not come from the agents. Here is exactly what the tools returned:")
    if not ctx.sources:
        return ("I could not answer that from the plant data, and my draft answer was not backed by any "
                "tool result, so I have discarded it. Please rephrase the question.")
    lines = []
    for call, src in zip(ctx.called, ctx.sources):
        try:
            data = json.loads(src)
        except Exception:
            continue
        lines.append(f"- {call['tool']}: {_brief(data)}")
    return head + "\n" + "\n".join(lines[:6])


def _brief(data: Any, limit: int = 240) -> str:
    if isinstance(data, dict):
        if "error" in data:
            return f"error - {data['error']}"
        parts = []
        for k, v in data.items():
            if isinstance(v, (str, int, float, bool)) or v is None:
                parts.append(f"{k}={v}")
            elif isinstance(v, list):
                parts.append(f"{k}=[{len(v)} item(s)]")
            elif isinstance(v, dict):
                parts.append(f"{k}={{{', '.join(f'{a}={b}' for a, b in list(v.items())[:3])}}}")
        return "; ".join(parts)[:limit]
    return str(data)[:limit]


async def astream(ctx: ToolCtx, query: str, session_id: str,
                  model_factory: Callable[[str], Any] | None = None) -> AsyncIterator[dict]:
    """Drive one question and yield SSE-ready events."""
    started = time.perf_counter()
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def put(ev: dict) -> None:
        # the tools node runs in a worker thread, so every producer goes through the loop
        loop.call_soon_threadsafe(queue.put_nowait, ev)

    ctx.on_token = lambda t: put({"type": "token", "text": t})
    ctx.on_note = lambda t: put({"type": "note", "text": t})
    ctx.sink = put
    ctx.model_used = None

    hint, nlu = _hint(ctx.db, query)
    yield {"type": "start", "session_id": session_id,
           "microlm": {"intent": nlu.get("intent"), "confidence": nlu.get("confidence"),
                       "entities": nlu.get("entities", [])}}

    human = HumanMessage(content=f"{query}\n{hint}" if hint else query)
    cfg = {"configurable": {"thread_id": session_id, "ctx": ctx,
                            "model_factory": model_factory or _default_factory},
           "recursion_limit": 2 * MAX_TOOL_STEPS + 6}

    async def runner():
        return await graph().ainvoke({"messages": [human], "steps": 0}, config=cfg)

    task = asyncio.create_task(runner())
    text_parts: list[str] = []
    while True:
        getter = asyncio.create_task(queue.get())
        done, _pending = await asyncio.wait({getter, task}, return_when=asyncio.FIRST_COMPLETED)
        if getter in done:
            ev = getter.result()
            if ev["type"] == "token":
                text_parts.append(ev["text"])
            yield ev
            continue
        getter.cancel()
        await asyncio.sleep(0)   # let any call_soon_threadsafe callbacks land
        await asyncio.sleep(0)
        while not queue.empty():
            ev = queue.get_nowait()
            if ev["type"] == "token":
                text_parts.append(ev["text"])
            yield ev
        break

    try:
        out = await task
        answer = _last_text(out["messages"]) or "".join(text_parts)
    except gemini.NoApiKey as exc:
        yield {"type": "fallback", "reason": "no_key",
               "message": "No Gemini API key is configured, so I am answering with the offline Micro LM. "
                          "It can look things up but cannot run actions."}
        async for ev in _microlm_stream(ctx, query, "no_key", str(exc)):
            yield ev
        return
    except gemini.QuotaExceeded as exc:
        yield {"type": "fallback", "reason": "quota",
               "message": "The free Gemini quota is exhausted. Answering with the offline Micro LM instead."}
        async for ev in _microlm_stream(ctx, query, "quota", str(exc)):
            yield ev
        return
    except Exception as exc:
        yield {"type": "fallback", "reason": "error",
               "message": f"The Gemini call failed ({type(exc).__name__}). Answering with the offline Micro LM instead."}
        async for ev in _microlm_stream(ctx, query, "error", str(exc)):
            yield ev
        return

    final, bad = _finalise(ctx, query, answer)
    if bad:
        yield {"type": "replace", "text": final, "ungrounded": bad}
    yield {"type": "done", "source": "gemini", "model": ctx.model_used, "answer": final,
           "grounded": not bad, "ungrounded": bad, "tools_called": ctx.called,
           "pending_action": ctx.pending, "latency_ms": int((time.perf_counter() - started) * 1000)}


def _last_text(messages) -> str:
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and not getattr(msg, "tool_calls", None):
            c = msg.content
            if isinstance(c, str) and c.strip():
                return c.strip()
            if isinstance(c, list):
                t = "".join(p.get("text", "") for p in c if isinstance(p, dict))
                if t.strip():
                    return t.strip()
    return ""


async def _microlm_stream(ctx: ToolCtx, query: str, reason: str, detail: str) -> AsyncIterator[dict]:
    """Offline fallback: the original Micro LM + template orchestrator, streamed word by word."""
    from ..orchestrator import chat as microlm_chat
    started = time.perf_counter()
    try:
        with ctx.guard():
            res = microlm_chat(ctx.db, query)
    except Exception as exc:
        yield {"type": "done", "source": "error", "answer":
               f"Both the Gemini supervisor and the offline fallback failed ({type(exc).__name__}). "
               f"The dashboard pages still show live data.", "grounded": True, "tools_called": [],
               "pending_action": None, "latency_ms": int((time.perf_counter() - started) * 1000),
               "fallback_reason": reason}
        return
    answer = res["answer"]
    for word in answer.split(" "):
        yield {"type": "token", "text": word + " "}
        await asyncio.sleep(0)
    yield {"type": "done", "source": "microlm", "model": "Micro LM (offline fallback)", "answer": answer,
           "grounded": True, "tools_called": [{"tool": f"{t['agent']}", "args": {}, "ms": 0, "ok": True}
                                              for t in res.get("agents_called", [])],
           "pending_action": None, "microlm": {"intent": res["intent"], "confidence": res["confidence"],
                                               "entities": res["entities"]},
           "suggestions": res.get("suggestions", []), "fallback_reason": reason, "fallback_detail": detail[:200],
           "latency_ms": int((time.perf_counter() - started) * 1000)}


# ---------------------------------------------------------------- confirmed actions
def execute_confirmed(ctx: ToolCtx, session_id: str, record: dict) -> dict:
    """Run an action the user confirmed, then write the outcome into the conversation memory.

    The reply is generated from the tool result rather than by the model: there is nothing
    for an LLM to add to "here is what changed", and this way the numbers cannot drift.
    """
    from .tools import execute
    started = time.perf_counter()
    result = execute(ctx, record["tool"], record["args"])
    ok = "error" not in result
    text = _action_summary(record, result)
    ctx.called.append({"tool": record["tool"], "args": record["args"],
                       "ms": int((time.perf_counter() - started) * 1000), "ok": ok})
    remember(session_id, f"[confirmed] {record['summary']}", text)
    return {"ok": ok, "answer": text, "result": result, "tool": record["tool"],
            "ui_commands": [e["command"] for e in ctx.events if e["type"] == "ui"],
            "blocks": [e["block"] for e in ctx.events if e["type"] == "block"],
            "tools_called": ctx.called, "source": "action",
            "latency_ms": int((time.perf_counter() - started) * 1000)}


def _action_summary(record: dict, result: dict) -> str:
    """Plain-language outcome built only from what the tool returned."""
    if "error" in result:
        return f"That did not work: {result['error']}"
    lines: list[str] = []
    if result.get("action") == "simulated_event":
        imp, before, after = result["impact"], result["impact"]["before"], result["impact"]["after"]
        lines.append(f"Done – {result['headline']}.")
        for step in result.get("agent_steps", []):
            lines.append(f"- **{step['agent']}**: {step['action']}")
        lines.append(f"- Projected late tasks {before['tardy_tasks']} → {after['tardy_tasks']}, "
                     f"makespan {before['makespan']}h → {after['makespan']}h.")
        if after.get("launch_readiness"):
            tail = f" ({after['launch_late_hours']}h late)" if after.get("launch_late_hours") else " (on time)"
            lines.append(f"- Launch-readiness review now {after['launch_readiness']}{tail}.")
        _ = imp
    elif result.get("action") == "replan":
        met = result.get("metrics") or {}
        lines.append(f"Done – re-planned with {result.get('algorithm')} as plan version "
                     f"{result.get('plan_version')}.")
        lines.append(f"- {result.get('tasks_moved', 0)} task(s) moved; {met.get('tardy_tasks')} projected late; "
                     f"makespan {met.get('makespan')}h.")
        for c in result.get("changes", [])[:3]:
            lines.append(f"- {c['task_id']} {c['name']}: {c['moved_hours']:+d}h – {c['reason']}")
    elif result.get("action") == "advance_time":
        a, la = result["alerts"], result["launch"]
        lines.append(f"Done – clock advanced {result['hours']}h, now {result['to']}.")
        lines.append(f"- {a['new']} new alert(s), {a['resolved']} resolved, {a['open']} open; "
                     f"{result['drift_replans']} drift re-plan(s).")
        for ch in result.get("state_changes", [])[:4]:
            lines.append(f"- {ch}")
        if la.get("readiness"):
            lines.append(f"- Launch-readiness review now {la['readiness']}.")
    elif result.get("action") == "acknowledge_alert":
        lines.append(f"Done – alert {result['id']} ({result['title']}) is now {result['status']}.")
    elif result.get("action") == "live_mode":
        lines.append(f"Done – live mode {'running' if result['running'] else 'paused'} at {result['speed']}x, "
                     f"random events {'on' if result['random_events'] else 'off'}.")
    else:
        lines.append(f"Done – {record['summary']}")
        lines.append(f"- {_brief(result, 400)}")
    return "\n".join(lines[:8])


def remember(session_id: str, user_text: str, assistant_text: str) -> None:
    """Append a turn to a session's memory without calling the model."""
    try:
        graph().update_state({"configurable": {"thread_id": session_id}},
                             {"messages": [HumanMessage(content=user_text),
                                           AIMessage(content=assistant_text)]})
    except Exception:
        pass   # memory is a convenience; never fail a real action over it


def cancel_note(session_id: str, record: dict) -> str:
    text = f"Cancelled – nothing was changed. ({record['summary']})"
    remember(session_id, f"[cancelled] {record['summary']}", text)
    return text


def run(ctx: ToolCtx, query: str, session_id: str,
        model_factory: Callable[[str], Any] | None = None) -> dict:
    """Non-streaming version of `astream`, for /api/chat/agent, the eval script and the tests."""
    async def collect():
        events: list[dict] = []
        async for ev in astream(ctx, query, session_id, model_factory):
            events.append(ev)
        return events

    events = asyncio.run(collect())
    done = next((e for e in reversed(events) if e["type"] == "done"), None)
    ui = [e["command"] for e in events if e["type"] == "ui"]
    blocks = [e["block"] for e in events if e["type"] == "block"]
    notes = [e["text"] for e in events if e["type"] == "note"]
    fb = next((e for e in events if e["type"] == "fallback"), None)
    out = dict(done or {"type": "done", "answer": "", "source": "error"})
    out.pop("type", None)
    out.update({"query": query, "session_id": session_id, "ui_commands": ui, "blocks": blocks,
                "notes": notes, "fallback_message": (fb or {}).get("message"),
                "events": [e["type"] for e in events]})
    start = next((e for e in events if e["type"] == "start"), None)
    if start and "microlm" not in out:
        out["microlm"] = start["microlm"]
    return out
