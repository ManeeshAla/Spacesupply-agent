"""In-process message bus for agent-to-agent communication.

Agents no longer only get called in a fixed order by the engine: they publish structured
messages on topics, and the agents that care about a topic are invoked as subscribers.
A supplier delay therefore reads as a real conversation:

    Supply Agent      --supplier.delay-->      (bus)
    Scheduling Agent  --schedule.replanned-->  (bus)
    Monitoring Agent  --alert.raised-->        (bus)

Every message is persisted in `agent_messages` so the UI can replay the exchange, and all
messages produced by one trigger share a `correlation_id`.

Honest scope: this is synchronous, in-process pub/sub inside one Python process, not a
distributed broker (no Kafka/RabbitMQ). The delivery order and the resulting plant state are
identical to the previous hard-coded call order; what changes is that the wiring is now
declared by subscriptions instead of being baked into `Engine.handle_event`.
"""
from __future__ import annotations

import json
import uuid
from collections import defaultdict
from typing import Callable

from . import models as m
from .agents.base import fmt, now_hour

# topics
SUPPLIER_DELAY = "supplier.delay"
COMPONENT_REJECTED = "component.rejected"
WORKSTATION_DOWN = "workstation.down"
TIME_ADVANCED = "time.advanced"
REPLAN_REQUESTED = "replan.requested"
SCHEDULE_REPLANNED = "schedule.replanned"
ALERTS_SCANNED = "alerts.scanned"
ALERT_RAISED = "alert.raised"

Handler = Callable[["Message"], None]


class Message:
    """One structured message on the bus."""

    __slots__ = ("topic", "sender", "recipient", "payload", "summary", "correlation_id")

    def __init__(self, topic: str, sender: str, payload: dict, summary: str = "", recipient: str = "*",
                 correlation_id: str = ""):
        self.topic = topic
        self.sender = sender
        self.recipient = recipient
        self.payload = payload
        self.summary = summary
        self.correlation_id = correlation_id

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Message {self.topic} from {self.sender}: {self.summary[:40]}>"


class MessageBus:
    def __init__(self) -> None:
        self._subs: dict[str, list[tuple[str, Handler]]] = defaultdict(list)

    def subscribe(self, topic: str, agent: str, handler: Handler) -> None:
        if not any(h is handler for _, h in self._subs[topic]):
            self._subs[topic].append((agent, handler))

    def subscribers(self, topic: str) -> list[str]:
        return [a for a, _ in self._subs[topic]]

    def publish(self, db, topic: str, sender: str, payload: dict, summary: str = "",
                recipient: str = "*", correlation_id: str = "") -> Message:
        """Persist the message, then hand it to every subscriber (depth-first)."""
        msg = Message(topic, sender, payload, summary, recipient, correlation_id or new_correlation_id())
        db.add(m.AgentMessage(topic=topic, sender=sender, recipient=recipient, correlation_id=msg.correlation_id,
                              summary=summary, payload_json=json.dumps(payload, default=str)[:8000],
                              hour=now_hour(db)))
        db.flush()
        for _agent, handler in list(self._subs[topic]):
            handler(msg)
        return msg


def new_correlation_id() -> str:
    return uuid.uuid4().hex[:12]


def recent(db, since: int = 0, limit: int = 80) -> list[dict]:
    """Messages with id > since, oldest first (the UI appends them to a feed)."""
    q = (db.query(m.AgentMessage).filter(m.AgentMessage.id > since)
         .order_by(m.AgentMessage.id.desc()).limit(limit).all())
    rows = []
    for a in reversed(q):
        try:
            payload = json.loads(a.payload_json)
        except Exception:
            payload = {}
        rows.append({"id": a.id, "topic": a.topic, "sender": a.sender, "recipient": a.recipient,
                     "correlation_id": a.correlation_id, "summary": a.summary, "payload": payload,
                     "hour": a.hour, "time": fmt(db, a.hour)})
    return rows


def last_id(db) -> int:
    row = db.query(m.AgentMessage.id).order_by(m.AgentMessage.id.desc()).first()
    return row[0] if row else 0


bus = MessageBus()
