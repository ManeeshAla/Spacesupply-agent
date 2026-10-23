"""Agent-to-agent message bus."""
from __future__ import annotations

from app import bus as bus_mod
from app import models as m
from app.bus import bus
from app.engine import engine as eng


def test_supplier_delay_is_a_three_agent_conversation(db):
    before = bus_mod.last_id(db)
    eng.handle_event(db, {"type": "SUPPLIER_DELAY", "component_id": "CMP-021", "hours": 24})
    msgs = bus_mod.recent(db, before)
    assert [x["topic"] for x in msgs] == [bus_mod.SUPPLIER_DELAY, bus_mod.SCHEDULE_REPLANNED,
                                          bus_mod.ALERTS_SCANNED]
    assert [x["sender"] for x in msgs] == ["Supply Agent", "Scheduling Agent", "Monitoring Agent"]
    # one trigger, one conversation
    assert len({x["correlation_id"] for x in msgs}) == 1
    assert msgs[0]["payload"]["hours"] == 24
    assert msgs[1]["payload"]["metrics"]["makespan"] > 0


def test_rejection_and_workstation_down_also_flow_through_the_bus(db):
    c = db.query(m.Component).filter(m.Component.status == m.IN_INSPECTION).first()
    if c is not None:
        before = bus_mod.last_id(db)
        eng.handle_event(db, {"type": "REJECT_COMPONENT", "component_id": c.id})
        topics = [x["topic"] for x in bus_mod.recent(db, before)]
        assert topics[0] == bus_mod.COMPONENT_REJECTED and bus_mod.SCHEDULE_REPLANNED in topics
    before = bus_mod.last_id(db)
    eng.handle_event(db, {"type": "WORKSTATION_DOWN", "workstation_id": "WS-04", "hours": 8})
    msgs = bus_mod.recent(db, before)
    assert msgs[0]["topic"] == bus_mod.WORKSTATION_DOWN
    assert msgs[0]["sender"] == "Monitoring Agent"
    assert any(x["topic"] == bus_mod.SCHEDULE_REPLANNED for x in msgs)


def test_subscriptions_are_declared_not_hardcoded():
    assert "Scheduling Agent" in bus.subscribers(bus_mod.SUPPLIER_DELAY)
    assert "Scheduling Agent" in bus.subscribers(bus_mod.REPLAN_REQUESTED)
    assert "Monitoring Agent" in bus.subscribers(bus_mod.SCHEDULE_REPLANNED)


def test_chat_replan_request_uses_the_bus(db):
    before = bus_mod.last_id(db)
    res = eng.request_replan(db, "FCFS", trigger="Chat request (FCFS)")
    assert res["algorithm"] == "FCFS"
    topics = [x["topic"] for x in bus_mod.recent(db, before)]
    assert topics == [bus_mod.REPLAN_REQUESTED, bus_mod.SCHEDULE_REPLANNED, bus_mod.ALERTS_SCANNED]
    assert [s["agent"] for s in res["steps"]] == ["Scheduling Agent", "Monitoring Agent"]


def test_handle_event_result_shape_is_unchanged(db):
    res = eng.handle_event(db, {"type": "SUPPLIER_DELAY", "component_id": "CMP-021", "hours": 12})
    for key in ("event", "trigger", "impact", "steps", "schedule_changes", "before", "after", "version_id"):
        assert key in res
    assert [s["agent"] for s in res["steps"]] == ["Supply Agent", "Scheduling Agent", "Monitoring Agent"]


def test_bus_endpoint(client):
    client.post("/api/simulate", json={"type": "SUPPLIER_DELAY", "component_id": "CMP-021", "hours": 18})
    body = client.get("/api/bus").json()
    assert body["last_id"] > 0
    assert bus_mod.SCHEDULE_REPLANNED in body["topics"]
    r2 = client.get(f"/api/bus?since={body['last_id']}").json()
    assert r2["messages"] == []


def test_alerts_carry_a_stage(client):
    client.post("/api/simulate", json={"type": "SUPPLIER_DELAY", "component_id": "CMP-021", "hours": 48})
    alerts = client.get("/api/alerts").json()
    assert alerts
    assert all("stage_id" in a for a in alerts)
    assert any(a["stage_id"] in (1, 2, 3, 4) for a in alerts)
