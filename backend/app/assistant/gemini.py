"""Gemini chat model: construction, free-tier rate-limit handling and model fallback.

Model choice (checked against Google's pricing/models pages in October 2026): the stable
`gemini-3.8-flash` and `gemini-3.5-flash-lite` are both offered on the free tier and both
support function calling. We use Flash as the primary model because its tool choice is
noticeably better, and drop to Flash-Lite when the free tier says we are out of quota.
Override either with GEMINI_MODEL / GEMINI_FALLBACK_MODEL.
"""
from __future__ import annotations

import random
import time

from ..config import (GEMINI_API_KEY, GEMINI_FALLBACK_MODEL, GEMINI_MAX_RETRIES, GEMINI_MODEL,
                      GEMINI_TEMPERATURE, GEMINI_TIMEOUT_S)

_QUOTA_HINTS = ("429", "resource_exhausted", "resourceexhausted", "quota", "rate limit", "ratelimit",
                "too many requests")
_RETRY_HINTS = ("500", "502", "503", "504", "internal", "unavailable", "deadline", "timeout",
                "overloaded", "connection")


class QuotaExceeded(RuntimeError):
    """Free-tier quota or rate limit hit on every configured model."""


class NoApiKey(RuntimeError):
    """No GEMINI_API_KEY (or the SDK is missing), so the supervisor cannot run at all."""


def is_quota_error(exc: BaseException) -> bool:
    s = f"{type(exc).__name__} {exc}".lower()
    return any(h in s for h in _QUOTA_HINTS)


def is_retryable(exc: BaseException) -> bool:
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


_models: dict[str, object] = {}


def make_model(name: str):
    """Cached ChatGoogleGenerativeAI for one model name."""
    if name not in _models:
        from langchain_google_genai import ChatGoogleGenerativeAI
        _models[name] = ChatGoogleGenerativeAI(
            model=name, google_api_key=GEMINI_API_KEY, temperature=GEMINI_TEMPERATURE,
            timeout=GEMINI_TIMEOUT_S, max_retries=0,   # we do our own backoff so we can report it
        )
    return _models[name]


def model_chain() -> list[str]:
    names = [GEMINI_MODEL]
    if GEMINI_FALLBACK_MODEL and GEMINI_FALLBACK_MODEL != GEMINI_MODEL:
        names.append(GEMINI_FALLBACK_MODEL)
    return names


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
