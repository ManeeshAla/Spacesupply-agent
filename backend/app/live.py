"""Live mode: a background simulator that runs the plant clock and (optionally) injects random disruptions.

It only *drives* the existing engine (advance / handle_event); all agent logic is unchanged.
Default: OFF until Play is pressed; random disruptions ON.
"""
from __future__ import annotations

import asyncio
import os
import random
import threading
from collections import deque

from . import models as m
from .agents.base import fmt, now_hour
from .database import SessionLocal
from .engine import engine as eng

SPEEDS = {1: 4.0, 2: 2.0, 4: 1.0, 8: 0.5}      # speed multiplier -> real seconds per plant hour
DISRUPTION_P = 0.06                              # chance per plant hour
COOLDOWN_H = 10                                  # min plant hours between disruptions


class LiveSim:
    def __init__(self) -> None:
        self.running = False
        self.speed = 4
        self.chaos = True
        self.feed: deque[dict] = deque(maxlen=300)
        self._id = 0
        self._since_disruption = COOLDOWN_H
        self._rng = self._new_rng()
        self.lock = threading.Lock()

    @staticmethod
    def _new_rng() -> random.Random:
        """LIVE_SEED makes random disruptions reproducible (used by the end-to-end live check).
        Unset - the default - keeps them genuinely random."""
        seed = os.getenv("LIVE_SEED", "").strip()
        return random.Random(int(seed)) if seed else random.Random()

    # ---------------------------------------------------------------- feed
    def push(self, db, kind: str, text: str, severity: str = "INFO") -> None:
        with self.lock:
            self._id += 1
            self.feed.append({"id": self._id, "kind": kind, "severity": severity, "text": text, "time": fmt(db, now_hour(db))})

    def state(self, since: int = 0) -> dict:
        with self.lock:
            return {"running": self.running, "speed": self.speed, "chaos": self.chaos, "last_id": self._id,
                    "seconds_per_hour": SPEEDS[self.speed], "feed": [f for f in self.feed if f["id"] > since][-80:]}

    def configure(self, running=None, speed=None, chaos=None) -> dict:
        if speed is not None:
            if int(speed) not in SPEEDS:
                raise ValueError("speed must be one of 1, 2, 4, 8")
            self.speed = int(speed)
        if chaos is not None:
            self.chaos = bool(chaos)
        if running is not None:
            self.running = bool(running)
        return self.state()

    def clear(self) -> None:
        with self.lock:
            self.feed.clear()
            self._id = 0
        self._since_disruption = COOLDOWN_H
        self._rng = self._new_rng()       # a reset replays the same disruptions when LIVE_SEED is set

    # ---------------------------------------------------------------- one plant hour
    def step(self, db) -> None:
        if db.query(m.Task).filter(m.Task.status != m.T_COMPLETED).count() == 0:
            self.running = False
            self.push(db, "SYSTEM", "Vehicle assembly complete – all tasks finished. Live mode paused.", "INFO")
            return
        res = eng.advance(db, 1)
        for line in res["changes"]:
            kind = "TASK" if line.startswith("T-") else "LOGISTICS"
            sev = "INFO"
            self.push(db, kind, line, sev)
        if res["replans"]:
            self.push(db, "REPLAN", "Scheduling Agent re-planned (a task could not start as scheduled).", "WARNING")
        for key in res["alerts"]["created"]:
            a = db.query(m.Alert).filter(m.Alert.dedupe_key == key).order_by(m.Alert.id.desc()).first()
            if a and a.category != "SCHEDULE_CHANGE":
                self.push(db, "ALERT", f"{a.severity}: {a.title}", a.severity)
        self._since_disruption += 1
        if self.chaos and self._since_disruption >= COOLDOWN_H and self._rng.random() < DISRUPTION_P:
            self._disrupt(db)

    def _disrupt(self, db) -> None:
        now = now_hour(db)
        options = []
        deliveries = db.query(m.Delivery).filter(m.Delivery.status == "ON_TIME", m.Delivery.eta_hour > now,
                                                 m.Delivery.is_replacement == False).all()  # noqa: E712
        if deliveries:
            options.append("delay")
        ws = [w for w in db.query(m.Workstation).filter(m.Workstation.status == "AVAILABLE").all()]
        if ws:
            options.append("down")
        insp = db.query(m.Component).filter(m.Component.status == m.IN_INSPECTION).all()
        if insp:
            options.append("reject")
        if not options:
            return
        pick = self._rng.choice(options)
        try:
            if pick == "delay":
                d = self._rng.choice(deliveries)
                hours = self._rng.choice([12, 18, 24])
                ev = {"type": "SUPPLIER_DELAY", "component_id": d.component_id, "hours": hours}
                text = f"Supplier {d.supplier.name} delayed {d.component.name} ({d.component_id}) by +{hours}h"
            elif pick == "down":
                w = self._rng.choice(ws)
                hours = self._rng.choice([6, 10, 14])
                ev = {"type": "WORKSTATION_DOWN", "workstation_id": w.id, "hours": hours}
                text = f"{w.id} {w.name} went down for {hours}h"
            else:
                c = self._rng.choice(insp)
                ev = {"type": "REJECT_COMPONENT", "component_id": c.id, "replacement_hours": 36}
                text = f"{c.name} ({c.id}) FAILED inspection – replacement ordered"
            self.push(db, "DISRUPTION", text, "CRITICAL")
            res = eng.handle_event(db, ev)
            self._since_disruption = 0
            ch = res["schedule_changes"]
            after = res["after"]
            self.push(db, "REPLAN", f"Agents re-planned with CP-SAT: {len(ch)} task(s) moved, {after['tardy_tasks']} projected late, "
                                    f"launch readiness {after['launch_readiness']}", "WARNING")
        except Exception as exc:  # a failed random event must never stop the demo
            db.rollback()
            self.push(db, "SYSTEM", f"Skipped a random event ({exc})", "INFO")


live = LiveSim()


async def live_loop(lock) -> None:
    """Background task: while running, advance one plant hour per tick."""
    while True:
        if not live.running:
            await asyncio.sleep(0.4)
            continue
        wait = SPEEDS[live.speed]

        def work():
            with lock:
                db = SessionLocal()
                try:
                    live.step(db)
                    db.commit()
                finally:
                    db.close()
        try:
            await asyncio.to_thread(work)
        except Exception as exc:
            print("live loop error:", exc)
        await asyncio.sleep(wait)
