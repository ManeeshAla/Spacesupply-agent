"""Gemini chat model: construction, free-tier rate-limit handling and model fallback.

Model choice, measured against a real free-tier key in October 2026: `gemini-3.5-flash-lite` is
the primary and `gemini-3.1-flash-lite` the fallback. Both support function calling, answer in
1-9s and are listed free of charge. The larger `gemini-3.6-flash` and `gemini-3.8-flash` give
better tool choice but their free allowance is tiny -- they returned 504/503 and then 429
RESOURCE_EXHAUSTED within a handful of calls -- so they are not usable defaults. Override with
GEMINI_MODEL / GEMINI_FALLBACK_MODEL if you have paid quota.

A model that fails with a quota, overload or timeout error is put in a short cooldown and moved
to the back of the chain, so one dead model does not slow every later turn.
"""
from __future__ import annotations

import asyncio
import random
import threading
import time

from ..config import (GEMINI_API_KEY, GEMINI_FALLBACK_MODEL, GEMINI_MAX_RETRIES, GEMINI_MODEL,
                      GEMINI_TIMEOUT_S)

_QUOTA_HINTS = ("429", "resource_exhausted", "resourceexhausted", "quota", "rate limit", "ratelimit",
                "too many requests")
_RETRY_HINTS = ("500", "502", "503", "504", "internal", "unavailable", "deadline", "timeout",
                "overloaded", "connection")


class QuotaExceeded(RuntimeError):
    """Free-tier quota or rate limit hit on every configured model."""


class EmptyResponse(RuntimeError):
    """Gemini returned a stream with no content (it does this now and then after a tool result)."""


class NoApiKey(RuntimeError):
    """No GEMINI_API_KEY (or the SDK is missing), so the supervisor cannot run at all."""


def is_quota_error(exc: BaseException) -> bool:
    s = f"{type(exc).__name__} {exc}".lower()
    return any(h in s for h in _QUOTA_HINTS)


def is_timeout(exc: BaseException) -> bool:
    """A model that timed out will usually time out again: switch models, don't retry it."""
    s = f"{type(exc).__name__} {exc}".lower()
    return any(h in s for h in ("deadline", "timeout", "timed out"))


def is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, EmptyResponse):
        return True
    s = f"{type(exc).__name__} {exc}".lower()
    return is_quota_error(exc) or any(h in s for h in _RETRY_HINTS)


def configured() -> bool:
    """True if a Gemini API key is present and the SDK is importable."""
    if not GEMINI_API_KEY:
        return False
    try:
        import langchain_google_genai  # noqa: F401
    except Exception:
        return False
    return True


def status() -> dict:
    return {"configured": configured(), "model": GEMINI_MODEL, "fallback_model": GEMINI_FALLBACK_MODEL,
            "key_present": bool(GEMINI_API_KEY)}


_models: dict[tuple, object] = {}


def make_model(name: str):
    """ChatGoogleGenerativeAI for one model, cached per running event loop.

    The client keeps an async HTTP pool that is bound to the loop it was first used on. The
    API server has one long-lived loop, but `supervisor.run()` (evaluation script, the
    non-streaming endpoint) starts a fresh loop per call, and a client carried over from an
    earlier loop fails with "Event loop is closed". Keying on the loop avoids that.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    key = (name, loop)                       # the loop object itself: an id() can be recycled
    if key not in _models:
        for k in [k for k in _models if k[1] is not loop]:
            _models.pop(k, None)             # drop clients of loops that are gone
        from langchain_google_genai import ChatGoogleGenerativeAI
        _models[key] = ChatGoogleGenerativeAI(
            # no temperature: the current Gemini models fix their own sampling and ignore it
            model=name, google_api_key=GEMINI_API_KEY,
            timeout=GEMINI_TIMEOUT_S, max_retries=0,   # we do our own backoff so we can report it
        )
    return _models[key]


COOLDOWN_S = 60.0
_cooldown: dict[str, float] = {}


def mark_unhealthy(name: str, seconds: float = COOLDOWN_S) -> None:
    """Skip a model for a while after it failed with a quota / overload / timeout error.

    Without this every turn (and every tool round inside a turn) rediscovers the same dead
    model and wastes several seconds on retries before moving on.
    """
    _cooldown[name] = time.time() + seconds


def mark_healthy(name: str) -> None:
    _cooldown.pop(name, None)


def model_chain() -> list[str]:
    """Primary then fallback, with models in cooldown moved to the back (never dropped:
    if everything is cooling down we still try them rather than refuse to answer)."""
    names = [GEMINI_MODEL]
    if GEMINI_FALLBACK_MODEL and GEMINI_FALLBACK_MODEL != GEMINI_MODEL:
        names.append(GEMINI_FALLBACK_MODEL)
    now = time.time()
    ok = [n for n in names if _cooldown.get(n, 0) <= now]
    cooling = [n for n in names if n not in ok]
    return ok + cooling


# One long-lived event loop for synchronous callers (evaluation script, /api/chat/agent), so
# the Gemini client's connection pool is never carried over to a loop that has been closed.
_loop_lock = threading.Lock()
_loop: asyncio.AbstractEventLoop | None = None


def background_loop() -> asyncio.AbstractEventLoop:
    global _loop
    with _loop_lock:
        if _loop is None or _loop.is_closed():
            _loop = asyncio.new_event_loop()
            threading.Thread(target=_loop.run_forever, name="gemini-loop", daemon=True).start()
        return _loop


def run_sync(coro):
    """Run a coroutine to completion on the shared background loop."""
    return asyncio.run_coroutine_threadsafe(coro, background_loop()).result()


def backoff_delay(attempt: int) -> float:
    """Exponential backoff with jitter: ~0.8s, ~1.9s, ~4.2s."""
    return min(8.0, 0.8 * (2.2 ** attempt)) * (0.75 + random.random() * 0.5)


async def ainvoke_with_retry(bind, messages, on_note=None):
    """Invoke `bind(model_name)` across the model chain with backoff.

    `bind` is called with a model name and must return a runnable; this keeps tool binding
    in the caller. `on_note(text)` reports a retry/switch to the UI.
    Raises QuotaExceeded when every model is rate-limited, or the last error otherwise.
    """
    import asyncio
    last: BaseException | None = None
    quota = False
    for mi, name in enumerate(model_chain()):
        for attempt in range(max(1, GEMINI_MAX_RETRIES)):
            try:
                return await bind(name).ainvoke(messages), name
            except Exception as exc:
                last = exc
                if not is_retryable(exc):
                    raise
                quota = quota or is_quota_error(exc)
                final_attempt = attempt == max(1, GEMINI_MAX_RETRIES) - 1
                if final_attempt:
                    break
                delay = backoff_delay(attempt)
                if on_note:
                    on_note(f"{name} is rate-limited; retrying in {delay:.1f}s")
                await asyncio.sleep(delay)
        if mi + 1 < len(model_chain()) and on_note:
            on_note(f"Switching to {model_chain()[mi + 1]}")
    if quota:
        raise QuotaExceeded(str(last))
    raise last if last else RuntimeError("Gemini call failed")


def invoke_with_retry(bind, messages, on_note=None):
    """Synchronous twin of ainvoke_with_retry (used by the non-streaming endpoint and tests)."""
    last: BaseException | None = None
    quota = False
    for mi, name in enumerate(model_chain()):
        for attempt in range(max(1, GEMINI_MAX_RETRIES)):
            try:
                return bind(name).invoke(messages), name
            except Exception as exc:
                last = exc
                if not is_retryable(exc):
                    raise
                quota = quota or is_quota_error(exc)
                if attempt == max(1, GEMINI_MAX_RETRIES) - 1:
                    break
                delay = backoff_delay(attempt)
                if on_note:
                    on_note(f"{name} is rate-limited; retrying in {delay:.1f}s")
                time.sleep(delay)
        if mi + 1 < len(model_chain()) and on_note:
            on_note(f"Switching to {model_chain()[mi + 1]}")
    if quota:
        raise QuotaExceeded(str(last))
    raise last if last else RuntimeError("Gemini call failed")
