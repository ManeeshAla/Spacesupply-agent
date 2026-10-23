"""Chat sessions and the pending-action store.

Actions the model proposes are not executed straight away: they are parked here until the
user presses Confirm in the chat. Everything is in-process, so it is cleared on restart —
that is fine for the simulation, and it keeps a confirmation from outliving the state it
was computed against.
"""
from __future__ import annotations

import threading
import time

TTL_S = 15 * 60          # a confirmation older than this is stale
MAX_PENDING = 64

_lock = threading.Lock()
_pending: dict[str, dict] = {}

# Runtime-switchable chat settings. `confirm` starts from CONFIRM_ACTIONS and can be turned
# off from the UI for a demo run, where stopping to confirm every step gets in the way.
from ..config import CONFIRM_ACTIONS  # noqa: E402

settings: dict = {"confirm": CONFIRM_ACTIONS}


def put(session_id: str, action: dict) -> dict:
    """Store an action awaiting confirmation. Returns the stored record."""
    rec = {**action, "session_id": session_id, "created": time.time(), "status": "PENDING"}
    with _lock:
        _prune()
        _pending[action["id"]] = rec
    return rec


def take(action_id: str) -> dict | None:
    """Pop an action if it exists and is still fresh."""
    with _lock:
        rec = _pending.pop(action_id, None)
    if rec is None:
        return None
    if time.time() - rec["created"] > TTL_S:
        return None
    return rec


def peek(action_id: str) -> dict | None:
    with _lock:
        return _pending.get(action_id)


def clear() -> None:
    with _lock:
        _pending.clear()


def count() -> int:
    with _lock:
        return len(_pending)


def _prune() -> None:
    now = time.time()
    for k in [k for k, v in _pending.items() if now - v["created"] > TTL_S]:
        _pending.pop(k, None)
    while len(_pending) > MAX_PENDING:
        _pending.pop(next(iter(_pending)))
