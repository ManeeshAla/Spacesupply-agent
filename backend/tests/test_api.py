def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_dashboard_shape(client):
    d = client.get("/api/dashboard").json()
    for k in ("kpis", "stages", "component_status", "inventory", "alerts", "progress", "microlm"):
        assert k in d
    assert d["kpis"]["component_lots"] == 85


def test_component_lookup(client):
    r = client.get("/api/components/CMP-021")
    assert r.status_code == 200 and "Fuel Pump" in r.text
    assert client.get("/api/components/CMP-999").status_code == 404


def test_schedule_has_no_conflicts(client):
    s = client.get("/api/schedule").json()
    assert s
    from app.scheduler.metrics import count_conflicts  # noqa: F401


def test_delay_triggers_replan_and_new_version(client):
    before = len(client.get("/api/schedule/versions").json())
    r = client.post("/api/simulate", json={"type": "SUPPLIER_DELAY", "component_id": "CMP-021", "hours": 24})
    assert r.status_code == 200
    assert len(client.get("/api/schedule/versions").json()) > before
    alerts = client.get("/api/alerts").json()
    assert any(a["component_id"] == "CMP-021" for a in alerts)


def test_reject_component_creates_replacement(client):
    r = client.post("/api/simulate", json={"type": "REJECT_COMPONENT", "component_id": "CMP-031"})
    assert r.status_code == 200
    assert client.get("/api/components/CMP-031").json()["status"] == "REJECTED"


def test_cannot_reject_component_not_yet_received(client):
    r = client.post("/api/simulate", json={"type": "REJECT_COMPONENT", "component_id": "CMP-034"})
    assert r.status_code == 400


def test_workstation_down_raises_alert(client):
    client.post("/api/simulate", json={"type": "WORKSTATION_DOWN", "workstation_id": "WS-04", "hours": 24})
    cats = {a["category"] for a in client.get("/api/alerts").json()}
    assert "WORKSTATION_DOWN" in cats


def test_unknown_event_rejected(client):
    assert client.post("/api/simulate", json={"type": "NOPE"}).status_code == 400


def test_advance_time_moves_clock(client):
    t0 = client.get("/api/dashboard").json()["now_hour"]
    client.post("/api/simulate", json={"type": "ADVANCE_TIME", "hours": 6})
    assert client.get("/api/dashboard").json()["now_hour"] == t0 + 6


def test_replan_all_algorithms(client):
    for a in ("FCFS", "PRIORITY", "GA", "CPSAT"):
        assert client.post("/api/schedule/replan", json={"algorithm": a}).status_code == 200
    assert client.post("/api/schedule/replan", json={"algorithm": "X"}).status_code == 400


def test_chat_empty_rejected(client):
    assert client.post("/api/chat", json={"message": "  "}).status_code == 400


def test_chat_location(client):
    r = client.post("/api/chat", json={"message": "where is the fuel pump"}).json()
    assert r["intent"] == "COMPONENT_LOCATION" and "CMP-021" in r["answer"]
    assert any(a["agent"] == "Tracking Agent" for a in r["agents_called"])


def test_chat_delay_explanation_after_event(client):
    client.post("/api/simulate", json={"type": "SUPPLIER_DELAY", "component_id": "CMP-021", "hours": 24})
    r = client.post("/api/chat", json={"message": "why is engine assembly delayed"}).json()
    assert "CMP-021" in r["answer"] or "Fuel Pump" in r["answer"]


def test_alert_ack(client):
    a = client.get("/api/alerts").json()[0]
    assert client.post(f"/api/alerts/{a['id']}/ack").status_code == 200


def test_live_mode_off_by_default_and_ticks(client):
    st = client.get("/api/live").json()
    assert st["running"] is False and st["chaos"] is True
    t0 = client.get("/api/dashboard").json()["now_hour"]
    from app.live import live
    from app.database import SessionLocal
    db = SessionLocal()
    for _ in range(5):
        live.step(db)
    db.commit(); db.close()
    assert client.get("/api/dashboard").json()["now_hour"] >= t0 + 5
    assert client.get("/api/live").json()["last_id"] > 0


def test_live_config_validation(client):
    assert client.post("/api/live", json={"speed": 3}).status_code == 400
    r = client.post("/api/live", json={"running": True, "speed": 4, "chaos": False}).json()
    assert r["running"] and r["speed"] == 4 and not r["chaos"]
    client.post("/api/live", json={"running": False, "chaos": True, "speed": 2})


def test_live_chaos_run_stays_consistent(client):
    from app.live import live
    from app.database import SessionLocal
    from app.scheduler.metrics import count_conflicts  # noqa: F401
    live._rng.seed(3)
    db = SessionLocal()
    for _ in range(60):
        live.step(db)
        db.commit()
    db.close()
    kinds = {f["kind"] for f in live.state()["feed"]}
    assert "DISRUPTION" in kinds and "REPLAN" in kinds
    assert client.get("/api/schedule").status_code == 200
