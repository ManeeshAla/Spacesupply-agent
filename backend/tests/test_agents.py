import pytest
from app import models as m
from app.engine import engine


def test_lifecycle_rejects_illegal_transition(db):
    c = db.get(m.Component, "CMP-021")  # ORDERED
    with pytest.raises(Exception):
        engine.tracking.transition(db, c, m.INSTALLED)


def test_supply_summary_counts(db):
    s = engine.supply.summary(db)
    assert s["sufficient"] + s["low"] + s["critical"] + s["on_order"] >= 1


def test_monitoring_dedupes_alerts(db):
    engine.monitoring.scan(db); db.commit()
    n = db.query(m.Alert).count()
    engine.monitoring.scan(db); db.commit()
    assert db.query(m.Alert).count() == n


def test_replan_is_versioned(db):
    n = db.query(m.ScheduleVersion).count()
    engine.scheduling.plan(db, "PRIORITY", trigger="test"); db.commit()
    assert db.query(m.ScheduleVersion).count() == n + 1
    assert db.query(m.ScheduleVersion).filter_by(is_current=True).count() == 1
