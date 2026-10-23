"""Supervisor agent tests. Every one runs offline against the scripted FakeChatModel."""
from __future__ import annotations

import json

import pytest
from fake_llm import FakeChatModel

from app import models as m
from app.assistant import gemini, sessions, supervisor
from app.assistant.tools import REGISTRY, ToolCtx, run_tool


@pytest.fixture(autouse=True)
def clean_chat():
    supervisor.reset_memory()
    gemini._cooldown.clear()
    sessions.clear()
    sessions.settings["confirm"] = True
    yield
    supervisor.reset_memory()
    sessions.clear()
    sessions.settings["confirm"] = True


def ctx_for(db, confirm=True) -> ToolCtx:
    return ToolCtx(db=db, lock=None, confirm=confirm)


def ask(db, script, query, session="t", confirm=True):
    fake = FakeChatModel(script)
    ctx = ctx_for(db, confirm)
    out = supervisor.run(ctx, query, session, model_factory=fake.factory())
    return out, ctx, fake


# ---------------------------------------------------------------- tools
def test_every_read_tool_runs(db):
    """No read tool may raise on a freshly seeded plant, for any task lifecycle state."""
    args = {"get_component": {"component": "CMP-001"}, "get_component_history": {"component": "CMP-001"},
            "explain_task": {"task": "T-001"}, "get_task_readiness": {"task": "T-001"},
            "show_dashboard": {"page": "schedule"}}
    skip = {"compare_schedulers",      # slow: runs all four solvers
            "acknowledge_alert", "control_live_mode"}   # change state; covered separately
    for name, spec in REGISTRY.items():
        if spec.write or name in skip:
            continue
        ctx = ctx_for(db)
        out = run_tool(ctx, name, args.get(name, {}))
        assert "error" not in out, f"{name} failed: {out.get('error')}"


def test_task_tools_handle_every_lifecycle_state(db):
    """explain_task / get_task_readiness return reduced dicts for started tasks: no KeyError."""
    seen = set()
    for t in db.query(m.Task).all():
        if t.status in seen:
            continue
        seen.add(t.status)
        for name in ("explain_task", "get_task_readiness"):
            out = run_tool(ctx_for(db), name, {"task": t.id})
            assert "error" not in out, f"{name} on {t.id} ({t.status}): {out.get('error')}"
    assert len(seen) >= 2


def test_acknowledge_alert_tool(db, client):
    client.post("/api/simulate", json={"type": "SUPPLIER_DELAY", "component_id": "CMP-021", "hours": 36})
    db.expire_all()
    alert = db.query(m.Alert).filter(m.Alert.status == "OPEN").first()
    assert alert is not None
    out = run_tool(ctx_for(db, confirm=True), "acknowledge_alert", {"alert_id": alert.id})
    assert out["status"] == "ACKNOWLEDGED", out
    db.expire_all()
    assert db.get(m.Alert, alert.id).status == "ACKNOWLEDGED"


def test_acknowledge_unknown_alert_is_an_error(db):
    out = run_tool(ctx_for(db), "acknowledge_alert", {"alert_id": 999999})
    assert "error" in out and "999999" in out["error"]


def test_live_mode_tool_round_trip(db):
    try:
        out = run_tool(ctx_for(db), "control_live_mode", {"speed": 2, "random_events": False})
        assert out["speed"] == 2 and out["random_events"] is False
        assert "error" not in run_tool(ctx_for(db), "control_live_mode", {"running": False})
    finally:
        from app.live import live
        live.configure(running=False, speed=4, chaos=True)


def test_bad_tool_arguments_are_reported_not_raised(db):
    # wrong type -> rejected by the schema
    bad_type = run_tool(ctx_for(db), "get_alerts", {"stage": "not-a-number"})
    assert "error" in bad_type and "Invalid arguments" in bad_type["error"]
    # right type, impossible value -> rejected by the agent, still an error string not a crash
    bad_value = run_tool(ctx_for(db), "control_live_mode", {"speed": 7})
    assert "error" in bad_value and "speed" in bad_value["error"]


def test_tool_schemas_are_valid_for_gemini():
    """Gemini's schema is stricter than JSON Schema (string-only enums, no bare anyOf).

    This converts all 25 tools the way langchain-google-genai does before every request, so a
    schema the API would reject fails here instead of on the first live call.
    """
    from langchain_google_genai._function_utils import convert_to_genai_function_declarations
    from app.assistant.supervisor import lc_tools
    broken = []
    for t in lc_tools():
        try:
            convert_to_genai_function_declarations([t])
        except Exception as exc:
            broken.append(f"{t.name}: {str(exc).splitlines()[0]}")
    assert not broken, "tool schemas Gemini would reject: " + "; ".join(broken)


def test_unknown_component_is_an_error_not_a_guess(db):
    out = run_tool(ctx_for(db), "get_component", {"component": "CMP-999"})
    assert "error" in out and "CMP-999" in out["error"]


def test_component_lookup_by_name_and_sloppy_id(db):
    a = run_tool(ctx_for(db), "get_component", {"component": "cmp1"})
    assert a["id"] == "CMP-001"
    name = db.get(m.Component, "CMP-001").name
    b = run_tool(ctx_for(db), "get_component", {"component": name.lower()})
    assert b["id"] == "CMP-001"


def test_read_tool_emits_ui_command(db):
    ctx = ctx_for(db)
    run_tool(ctx, "get_component", {"component": "CMP-021"})
    ui = [e for e in ctx.events if e["type"] == "ui"]
    assert ui and ui[0]["command"] == {"action": "open_component", "component_id": "CMP-021"}


def test_alerts_tool_filters_by_stage(db):
    ctx = ctx_for(db)
    out = run_tool(ctx, "get_alerts", {"status": "ALL", "stage": 2})
    assert all(a["stage_id"] == 2 for a in out["alerts"])


# ---------------------------------------------------------------- tool calling
def test_supervisor_calls_the_tool_and_answers(db):
    out, ctx, fake = ask(db, [
        {"tools": [("get_component", {"component": "CMP-021"})]},
        {"text": "CMP-021 is in the warehouse."},
    ], "where is CMP-021?")
    assert out["source"] == "gemini"
    assert [c["tool"] for c in out["tools_called"]] == ["get_component"]
    assert "CMP-021" in out["answer"]
    assert out["grounded"] is True
    # the tools were actually offered to the model, with their schemas
    assert "get_component" in fake.tool_names()
    assert len(fake.bound_tools) == len(REGISTRY)


def test_microlm_hint_and_system_prompt_reach_the_model(db):
    _out, _ctx, fake = ask(db, [{"text": "Hello."}], "where is CMP-021?")
    first = fake.seen[0]
    assert first[0].type == "system" and "SpaceSupply-Agent" in first[0].content
    assert "Micro LM hint" in first[-1].content and "CMP-021" in first[-1].content


def test_ui_commands_are_returned_to_the_frontend(db):
    out, _ctx, _f = ask(db, [
        {"tools": [("show_dashboard", {"page": "alerts", "stage": 3, "severity": "CRITICAL"})]},
        {"text": "Opened the alerts page for stage 3."},
    ], "show me critical alerts for stage 3")
    assert out["ui_commands"] == [{"action": "navigate", "page": "alerts",
                                  "filters": {"stage": 3, "alertStage": 3, "alertSeverity": "CRITICAL"}}]


def test_tables_are_returned_as_blocks(db):
    out, _ctx, _f = ask(db, [
        {"tools": [("get_schedule", {"window_hours": 24})]},
        {"text": "Here is the plan for the next 24 hours."},
    ], "what is scheduled today?")
    assert out["blocks"] and out["blocks"][0]["type"] == "table"
    assert out["blocks"][0]["columns"][0] == "Task"


def test_memory_makes_followups_work(db):
    fake = FakeChatModel([
        {"tools": [("get_component", {"component": "CMP-021"})]},
        {"text": "CMP-021 is in the warehouse."},
        {"tools": [("get_supplier", {"component": "CMP-021"})]},
        {"text": "Its supplier is listed above."},
    ])
    ctx1 = ctx_for(db)
    supervisor.run(ctx1, "where is CMP-021?", "mem", model_factory=fake.factory())
    ctx2 = ctx_for(db)
    out = supervisor.run(ctx2, "and what about its supplier?", "mem", model_factory=fake.factory())
    assert out["tools_called"][0]["tool"] == "get_supplier"
    # the second turn was given the first turn's exchange
    texts = [getattr(x, "content", "") for x in fake.seen[-1]]
    assert any("CMP-021 is in the warehouse." in t for t in texts if isinstance(t, str))


def test_separate_sessions_do_not_share_memory(db):
    fake = FakeChatModel([{"text": "First."}, {"text": "Second."}])
    supervisor.run(ctx_for(db), "hello", "s1", model_factory=fake.factory())
    supervisor.run(ctx_for(db), "hello again", "s2", model_factory=fake.factory())
    assert len([x for x in fake.seen[-1] if x.type == "human"]) == 1


def test_tool_step_budget_is_enforced(db):
    # always asks for another tool: the loop must stop instead of running forever
    script = [{"tools": [("get_delayed_tasks", {})]} for _ in range(40)]
    out, _ctx, _f = ask(db, script, "loop please")
    assert len(out["tools_called"]) <= 8


# ---------------------------------------------------------------- confirmation
def test_write_tool_asks_before_changing_anything(db, client):
    before = db.query(m.Delivery).filter(m.Delivery.status == "DELAYED").count()
    out, ctx, _f = ask(db, [
        {"tools": [("delay_delivery", {"component": "CMP-021", "hours": 24})]},
        {"text": "Press Confirm and I will register a 24h delay on CMP-021."},
    ], "delay CMP-021 by 24 hours")
    pending = out["pending_action"]
    assert pending and pending["tool"] == "delay_delivery"
    assert "CMP-021" in pending["summary"] and "24" in pending["summary"]
    db.expire_all()
    assert db.query(m.Delivery).filter(m.Delivery.status == "DELAYED").count() == before, "nothing may change yet"
    assert any(e["type"] == "pending" for e in ctx.events)


def test_confirming_executes_and_reports_the_change(db, client):
    out, _ctx, _f = ask(db, [
        {"tools": [("delay_delivery", {"component": "CMP-021", "hours": 24})]},
        {"text": "Confirm to apply it."},
    ], "delay CMP-021 by 24 hours", session="c1")
    sessions.put("c1", out["pending_action"])
    r = client.post("/api/chat/confirm", json={"action_id": out["pending_action"]["id"],
                                              "approve": True, "session_id": "c1"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["approved"] and body["ok"]
    assert "CMP-021" in body["answer"]
    assert "Scheduling Agent" in body["answer"]
    db.expire_all()
    d = db.query(m.Delivery).filter(m.Delivery.component_id == "CMP-021").first()
    assert d.delay_hours >= 24


def test_cancelling_changes_nothing(db, client):
    out, _ctx, _f = ask(db, [
        {"tools": [("reject_component", {"component": "CMP-001"})]},
        {"text": "Confirm to reject it."},
    ], "reject CMP-001", session="c2")
    sessions.put("c2", out["pending_action"])
    r = client.post("/api/chat/confirm", json={"action_id": out["pending_action"]["id"],
                                              "approve": False, "session_id": "c2"})
    assert r.status_code == 200
    assert "Cancelled" in r.json()["answer"]
    db.expire_all()
    assert db.get(m.Component, "CMP-001").status != m.REJECTED


def test_a_confirmation_cannot_be_used_twice(db, client):
    out, _ctx, _f = ask(db, [
        {"tools": [("replan_schedule", {"algorithm": "FCFS"})]},
        {"text": "Confirm to re-plan."},
    ], "replan with FCFS", session="c3")
    sessions.put("c3", out["pending_action"])
    aid = out["pending_action"]["id"]
    assert client.post("/api/chat/confirm", json={"action_id": aid, "session_id": "c3"}).status_code == 200
    assert client.post("/api/chat/confirm", json={"action_id": aid, "session_id": "c3"}).status_code == 404


def test_demo_mode_runs_actions_immediately(db):
    out, _ctx, _f = ask(db, [
        {"tools": [("replan_schedule", {"algorithm": "PRIORITY"})]},
        {"text": "Re-planned with PRIORITY."},
    ], "replan with priority rules", session="demo", confirm=False)
    assert out["pending_action"] is None
    db.expire_all()
    ver = db.query(m.ScheduleVersion).filter(m.ScheduleVersion.is_current == True).first()  # noqa: E712
    assert ver.algorithm == "PRIORITY"


def test_confirm_toggle_endpoint(client):
    try:
        assert client.post("/api/chat/config", json={"confirm": False}).json()["confirm_actions"] is False
        assert client.get("/api/chat/config").json()["confirm_actions"] is False
    finally:
        client.post("/api/chat/config", json={"confirm": True})


# ---------------------------------------------------------------- grounding guard
def test_invented_numbers_are_stripped_from_the_answer(db):
    out, _ctx, _f = ask(db, [
        {"tools": [("get_component", {"component": "CMP-021"})]},
        {"text": "CMP-021 is 847 units short and arrives on CMP-777."},
    ], "where is CMP-021?")
    assert out["grounded"] is False
    assert "847" not in out["answer"] and "CMP-777" not in out["answer"]
    assert "get_component" in out["answer"]
    assert set(out["ungrounded"]) == {"847", "CMP-777"}


def test_a_grounded_answer_is_left_alone(db):
    out, _ctx, _f = ask(db, [
        {"tools": [("get_stage_progress", {"stage": 2})]},
        {"text": "Stage 2 is progressing; see the figures above."},
    ], "how is stage 2?")
    assert out["grounded"] is True
    assert out["answer"] == "Stage 2 is progressing; see the figures above."


def test_guard_allows_facts_that_came_from_the_question(db):
    out, _ctx, _f = ask(db, [{"text": "I have no data for CMP-021 right now."}], "where is CMP-021?")
    assert out["grounded"] is True


# ---------------------------------------------------------------- fallback
def test_quota_error_falls_back_to_the_microlm(db):
    out, _ctx, _f = ask(db, [{"raise": gemini.QuotaExceeded("429 quota exceeded")}] * 12, "where is CMP-021?")
    assert out["source"] == "microlm"
    assert out["fallback_reason"] == "quota"
    assert "CMP-021" in out["answer"]
    assert "quota" in (out["fallback_message"] or "").lower()


def test_a_429_is_retried_then_falls_back(db):
    err = RuntimeError("429 Resource has been exhausted (quota)")
    out, _ctx, fake = ask(db, [{"raise": err}] * 12, "where is CMP-021?")
    assert out["source"] == "microlm"
    # three attempts on the primary model, then three on the fallback model
    assert fake.turns == 6
    assert any("rate-limited" in n for n in out["notes"])
    assert any("Switching to" in n for n in out["notes"])


def test_a_non_retryable_error_falls_back_without_retrying(db):
    out, _ctx, fake = ask(db, [{"raise": ValueError("API key not valid")}] * 5, "show alerts")
    assert out["source"] == "microlm"
    assert out["fallback_reason"] == "error"
    assert fake.turns == 1


def test_without_an_api_key_the_microlm_answers(db):
    """The real factory must refuse clearly, not crash, when GEMINI_API_KEY is unset."""
    ctx = ctx_for(db)
    out = supervisor.run(ctx, "where is CMP-021?", "nokey")   # no fake: uses _default_factory
    assert gemini.configured() is False, "this test assumes no key is configured in the test env"
    assert out["source"] == "microlm"
    assert out["fallback_reason"] == "no_key"
    assert "no gemini api key" in (out["fallback_message"] or "").lower()
    assert "CMP-021" in out["answer"]


def test_fallback_answer_is_still_grounded(db):
    out, _ctx, _f = ask(db, [{"raise": gemini.QuotaExceeded("429")}] * 12, "which tasks are delayed?")
    assert out["grounded"] is True and out["source"] == "microlm"


# ---------------------------------------------------------------- HTTP surface
def test_agent_endpoint(client, monkeypatch):
    fake = FakeChatModel([{"tools": [("get_plant_status", {})]}, {"text": "All nominal."}])
    monkeypatch.setattr(supervisor, "_default_factory", fake.factory())
    r = client.post("/api/chat/agent", json={"message": "how are things?", "session_id": "http"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["answer"] == "All nominal."
    assert body["tools_called"][0]["tool"] == "get_plant_status"


def test_agent_endpoint_rejects_empty(client):
    assert client.post("/api/chat/agent", json={"message": "   "}).status_code == 400


def test_stream_endpoint_event_order(client, monkeypatch):
    fake = FakeChatModel([{"tools": [("get_component", {"component": "CMP-021"})]},
                          {"text": "CMP-021 is tracked."}])
    monkeypatch.setattr(supervisor, "_default_factory", fake.factory())
    with client.stream("POST", "/api/chat/stream",
                       json={"message": "where is CMP-021?", "session_id": "sse"}) as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        events = [json.loads(line[6:]) for line in r.iter_lines() if line.startswith("data: ")]
    kinds = [e["type"] for e in events]
    assert kinds[0] == "start" and kinds[-1] == "done"
    assert kinds.index("tool_call") < kinds.index("tool_result") < kinds.index("done")
    assert "token" in kinds and "ui" in kinds
    assert "".join(e["text"] for e in events if e["type"] == "token").strip() == "CMP-021 is tracked."
    assert events[-1]["answer"] == "CMP-021 is tracked."


def test_chat_config_lists_tools(client):
    body = client.get("/api/chat/config").json()
    assert body["gemini"]["model"]
    assert len(body["tools"]) == len(REGISTRY)
    assert set(body["write_tools"]) == {"delay_delivery", "reject_component", "workstation_down",
                                       "replan_schedule", "advance_time"}


def test_new_chat_clears_memory(client, monkeypatch):
    fake = FakeChatModel([{"text": "one."}, {"text": "two."}])
    monkeypatch.setattr(supervisor, "_default_factory", fake.factory())
    client.post("/api/chat/agent", json={"message": "hello", "session_id": "nc"})
    client.post("/api/chat/new?session_id=nc")
    client.post("/api/chat/agent", json={"message": "hello again", "session_id": "nc"})
    assert len([x for x in fake.seen[-1] if x.type == "human"]) == 1


def test_old_microlm_chat_endpoint_still_works(client):
    r = client.post("/api/chat", json={"message": "where is CMP-021?"})
    assert r.status_code == 200
    assert "CMP-021" in r.json()["answer"]


# ---------------------------------------------------------------- bugs found with the real API
def test_empty_gemini_response_is_retried(db):
    """Gemini sometimes returns an empty stream after a tool result: retry, don't give up."""
    fake = FakeChatModel([{"text": ""}, {"text": "CMP-021 is tracked."}])
    out = supervisor.run(ctx_for(db), "where is CMP-021?", "empty", model_factory=fake.factory())
    assert out["source"] == "gemini" and out["answer"] == "CMP-021 is tracked."
    assert fake.turns == 2


def test_timeouts_switch_model_instead_of_retrying(db):
    err = RuntimeError("504 DEADLINE_EXCEEDED. Deadline expired before operation could complete.")
    out, _ctx, fake = ask(db, [{"raise": err}] * 6, "show alerts")
    assert out["source"] == "microlm"
    assert fake.turns == 2, "one attempt per model, not three"


def test_a_failed_turn_leaves_no_half_finished_exchange_in_memory(db):
    """A tool call followed by a model failure used to be resumed by the NEXT question."""
    fake = FakeChatModel([
        {"tools": [("get_supplier", {"component": "CMP-021"})]},
        {"raise": ValueError("boom")},          # second model turn dies after the tool ran
        {"text": "Hello again."},
    ])
    supervisor.run(ctx_for(db), "who supplies CMP-021?", "poison", model_factory=fake.factory())
    out = supervisor.run(ctx_for(db), "hello", "poison", model_factory=fake.factory())
    assert out["source"] == "gemini" and out["tools_called"] == []
    types = [x.type for x in fake.seen[-1]]
    assert types == ["system", "human"], f"stale messages leaked into the next turn: {types}"


def test_percentages_derived_from_fractions_are_grounded():
    from app import llm
    # the id matters: parsing it as a number used to raise and abort every numeric check,
    # so a correct percentage was reported as invented
    src = '{"component": "CMP-003", "reliability": 0.89, "lead_time_days": 8}'
    assert llm.facts_grounded("Sagar Composites supplies CMP-003, 89% reliable, 8 day lead time.", src)
    assert llm.facts_grounded("Reliability 0.89.", src)
    assert not llm.facts_grounded("Reliability is 71%.", src)
    assert not llm.facts_grounded("Lead time is 17 days.", src)
    assert not llm.facts_grounded("See CMP-777.", src)
    assert llm.ungrounded_facts("89% and CMP-777 and 17", src) == ["17", "CMP-777"]


def test_model_cache_is_per_event_loop(monkeypatch):
    """A client reused across asyncio.run() calls fails with 'Event loop is closed'."""
    import asyncio
    made = []
    class Dummy:
        def __init__(self, **kw): made.append(kw["model"])
    import langchain_google_genai
    monkeypatch.setattr(langchain_google_genai, "ChatGoogleGenerativeAI", Dummy)
    gemini._models.clear()
    async def twice():
        return gemini.make_model("m"), gemini.make_model("m")
    a1, a2 = asyncio.run(twice())
    b1, _ = asyncio.run(twice())
    assert a1 is a2, "same loop -> reuse"
    assert a1 is not b1, "new loop -> new client"
    gemini._models.clear()


def test_history_trim_always_starts_at_a_user_message():
    """Gemini 400s on a window that begins with a tool call or tool result."""
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
    msgs = []
    for i in range(12):
        msgs += [HumanMessage(content=f"q{i}"),
                 AIMessage(content="", tool_calls=[{"name": "get_delayed_tasks", "args": {}, "id": f"c{i}"}]),
                 ToolMessage(content="{}", tool_call_id=f"c{i}", name="get_delayed_tasks"),
                 AIMessage(content=f"a{i}")]
    for n in range(5, len(msgs)):
        cut = supervisor._trim(msgs[:n])
        assert cut and isinstance(cut[0], HumanMessage), f"window of {n} starts with {type(cut[0]).__name__}"
        # every tool result still has its call right before it
        for j, m in enumerate(cut):
            if isinstance(m, ToolMessage):
                assert getattr(cut[j - 1], "tool_calls", None)


def test_a_failing_model_is_skipped_for_a_while():
    first = gemini.model_chain()
    assert first[0] == gemini.GEMINI_MODEL
    gemini.mark_unhealthy(gemini.GEMINI_MODEL, 60)
    assert gemini.model_chain()[0] == gemini.GEMINI_FALLBACK_MODEL
    assert gemini.GEMINI_MODEL in gemini.model_chain(), "never drop a model entirely"
    gemini.mark_healthy(gemini.GEMINI_MODEL)
    assert gemini.model_chain() == first


def test_sync_callers_share_one_event_loop(db):
    a = gemini.background_loop()
    out = supervisor.run(ctx_for(db), "hello", "loop", model_factory=FakeChatModel([{"text": "hi."}]).factory())
    assert out["answer"] == "hi." and gemini.background_loop() is a


def test_an_ungrounded_answer_with_no_tool_data_is_refused_not_rephrased(db):
    """An off-topic question the model answered from nowhere: say so, don't ask to rephrase."""
    out, _ctx, _f = ask(db, [{"text": "ISRO's next launch uses CMP-084 and slips to March."}],
                        "what do you think of the real ISRO launch schedule?")
    assert out["grounded"] is False and out["tools_called"] == []
    assert "CMP-084" not in out["answer"]
    assert "outside what I cover" in out["answer"]
    assert "rephrase" not in out["answer"].lower()
