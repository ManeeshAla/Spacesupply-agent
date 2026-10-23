from __future__ import annotations

from datetime import datetime, timedelta

from .. import models as m


def now_hour(db) -> int:
    return db.get(m.SimState, 1).now_hour


def to_dt(db, hour: int) -> datetime:
    return datetime.fromisoformat(db.get(m.SimState, 1).start_iso) + timedelta(hours=hour)


def iso(db, hour: int | None) -> str | None:
    return None if hour is None else to_dt(db, hour).isoformat(timespec="minutes")


def fmt(db, hour: int) -> str:
    return to_dt(db, hour).strftime("%d %b %H:%M")


def log(db, agent: str, message: str) -> None:
    db.add(m.AgentLog(agent=agent, message=message, hour=now_hour(db)))
