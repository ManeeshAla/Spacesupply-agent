"""End-to-end live-mode check: the commit gate for every UI or engine change.

Drives the real dashboard in a real browser against a real server and checks that live
mode still works end to end:

  * press Play and let the plant run for 30 seconds;
  * the simulated clock advances;
  * tasks start AND finish;
  * the Live activity feed on the Dashboard gains new items;
  * a random disruption fires and triggers a re-plan (DISRUPTION + REPLAN in the feed, a new
    schedule version, and a schedule.replanned message on the agent bus);
  * the Agent Communication feed is on the Dashboard and shows that message;
  * press Pause and the clock and the feed stop;
  * no console errors.

It starts its OWN server on a temporary database, so it never resets your real plant.
LIVE_SEED makes the random disruption reproducible instead of a matter of luck.

    pip install playwright          # once; uses your installed Chrome, no browser download
    cd frontend && npm run build    # the server serves the built UI
    cd ../backend && python scripts/e2e_live_check.py

Options: --url to test an already-running server instead (WARNING: resets that plant),
--seconds, --headed, --no-dashboard-bus (only for checking an older build).
Exit code 0 = pass, 1 = a check failed, 2 = could not run.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

BACKEND = pathlib.Path(__file__).resolve().parents[1]
DIST = BACKEND.parent / "frontend" / "dist" / "index.html"
DEFAULT_SEED = "15"          # first random disruption on the 2nd plant hour (see the docstring)


# ---------------------------------------------------------------- tiny HTTP helpers
def api(base: str, path: str, method: str = "GET", body: dict | None = None):
    req = urllib.request.Request(base + "/api" + path, method=method,
                                 data=json.dumps(body or {}).encode() if method != "GET" else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read() or b"null")


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for(base: str, timeout: float = 120) -> None:
    end = time.time() + timeout
    while time.time() < end:
        try:
            if api(base, "/health")["status"] == "ok":
                return
        except Exception:
            time.sleep(0.5)
    raise RuntimeError(f"server at {base} did not come up within {timeout:.0f}s")


def start_server(seed: str) -> tuple[subprocess.Popen, str, str]:
    tmp = tempfile.mkdtemp(prefix="e2e-live-")
    port = free_port()
    env = {**os.environ,
           "DATABASE_URL": f"sqlite:///{pathlib.Path(tmp, 'e2e.db').as_posix()}",
           "LIVE_SEED": seed,
           "GEMINI_API_KEY": "", "GOOGLE_API_KEY": "",      # the check never spends API quota
           "USE_QWEN": "off"}
    log = open(pathlib.Path(tmp, "server.log"), "w")
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
                             "--port", str(port), "--log-level", "warning"],
                            cwd=BACKEND, env=env, stdout=log, stderr=subprocess.STDOUT)
    return proc, f"http://127.0.0.1:{port}", tmp


# ---------------------------------------------------------------- the check
class Report:
    def __init__(self):
        self.rows: list[tuple[bool, str, str]] = []

    def check(self, ok: bool, what: str, detail: str = "") -> bool:
        self.rows.append((bool(ok), what, detail))
        print(f"  {'PASS' if ok else 'FAIL'}  {what}" + (f"  ({detail})" if detail else ""), flush=True)
        return bool(ok)

    @property
    def passed(self) -> bool:
        return all(ok for ok, _, _ in self.rows)


def schedule_state(base: str) -> dict:
    s = api(base, "/schedule")
    statuses = [t["status"] for t in s["tasks"]]
    return {"version": s["version"]["id"], "completed": statuses.count("COMPLETED"),
            "in_progress": statuses.count("IN_PROGRESS"), "now": s["now_hour"]}


def run(base: str, seconds: int, headed: bool, require_dashboard_bus: bool) -> Report:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright is not installed: pip install playwright", file=sys.stderr)
        sys.exit(2)

    rep = Report()
    api(base, "/reset", "POST")
    errors: list[str] = []

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch(channel="chrome", headless=not headed)
        except Exception:
            browser = p.chromium.launch(headless=not headed)   # bundled Chromium, if installed
        page = browser.new_page(viewport={"width": 1440, "height": 950})
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.on("console", lambda m: errors.append(f"console.error: {m.text}") if m.type == "error" else None)
        page.goto(base + "/", wait_until="networkidle")

        # ---- both feeds are on the Dashboard
        feed = page.locator('[data-testid="live-feed"]')
        rep.check(feed.count() > 0 and feed.first.is_visible(), "Live activity feed is on the Dashboard")
        if require_dashboard_bus:
            bus = page.locator('[data-testid="agent-bus"]')
            rep.check(bus.count() > 0 and bus.first.is_visible(), "Agent Communication feed is on the Dashboard")

        # ---- set up: fastest speed, random events on
        page.locator('[data-testid="live-speed-8"]').first.click()
        chaos = page.locator('[data-testid="live-chaos"]').first
        if chaos.get_attribute("data-state") != "on":
            chaos.click()
        page.wait_for_timeout(600)
        st = api(base, "/live")
        rep.check(st["speed"] == 8 and st["chaos"], "speed 8x and random events on", f"speed={st['speed']} chaos={st['chaos']}")

        before = schedule_state(base)
        bus_before = api(base, "/bus")["last_id"]
        feed_items_before = page.locator('[data-testid="live-feed-item"]').count()
        clock_before = page.locator('[data-testid="plant-clock"]').first.get_attribute("data-now")

        # ---- Play
        play = page.locator('[data-testid="live-play"]').first
        play.click()
        page.wait_for_timeout(800)
        rep.check(api(base, "/live")["running"] and play.get_attribute("data-state") == "running",
                  "Play starts live mode")
        print(f"  ...running for {seconds}s", flush=True)
        page.wait_for_timeout(seconds * 1000)

        after = schedule_state(base)
        live = api(base, "/live")
        feed_kinds = [f["kind"] for f in live["feed"]]
        feed_text = " | ".join(f["text"] for f in live["feed"])
        bus = api(base, "/bus", )
        new_bus = [m for m in bus["messages"] if m["id"] > bus_before]

        rep.check(after["now"] > before["now"], "simulated clock advances",
                  f"plant hour {before['now']} -> {after['now']}")
        page.wait_for_timeout(1500)       # let the header's own poll catch up before reading it
        clock_after = page.locator('[data-testid="plant-clock"]').first.get_attribute("data-now")
        rep.check(clock_after and clock_after != clock_before, "the clock shown in the UI moves",
                  f"{clock_before} -> {clock_after}")
        rep.check("STARTED" in feed_text, "tasks start")
        rep.check(after["completed"] > before["completed"] or "COMPLETED" in feed_text, "tasks finish",
                  f"completed {before['completed']} -> {after['completed']}")
        feed_items_after = page.locator('[data-testid="live-feed-item"]').count()
        rep.check(feed_items_after > feed_items_before, "the Live activity feed updates in the UI",
                  f"{feed_items_before} -> {feed_items_after} items")
        rep.check("DISRUPTION" in feed_kinds, "a random disruption fires")
        rep.check("REPLAN" in feed_kinds and after["version"] > before["version"],
                  "the disruption triggers a re-plan",
                  f"plan v{before['version']} -> v{after['version']}")
        rep.check(any(m["topic"] == "schedule.replanned" for m in new_bus),
                  "the agents announce the re-plan on the bus", f"{len(new_bus)} new bus message(s)")
        if require_dashboard_bus:
            try:
                page.wait_for_selector('[data-testid="agent-bus-item"][data-topic="schedule.replanned"]',
                                       timeout=8000)
                shown = True
            except Exception:
                shown = False
            rep.check(shown, "Agent Communication on the Dashboard shows the re-plan")

        # ---- Pause
        play.click()
        page.wait_for_timeout(2500)        # let an in-flight tick finish
        paused_now, paused_feed = api(base, "/schedule")["now_hour"], api(base, "/live")["last_id"]
        rep.check(not api(base, "/live")["running"] and play.get_attribute("data-state") == "paused",
                  "Pause stops live mode")
        page.wait_for_timeout(5000)
        rep.check(api(base, "/schedule")["now_hour"] == paused_now and api(base, "/live")["last_id"] == paused_feed,
                  "after Pause the clock and the feed stay still", f"held at plant hour {paused_now} for 5s")

        rep.check(not errors, "no console errors", "; ".join(errors[:3]))
        browser.close()
    return rep


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", help="test this running server instead of starting one (resets its plant!)")
    ap.add_argument("--seconds", type=int, default=30)
    ap.add_argument("--seed", default=os.getenv("LIVE_SEED", DEFAULT_SEED))
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--no-dashboard-bus", action="store_true",
                    help="skip the Agent Communication-on-Dashboard checks (older builds only)")
    args = ap.parse_args()

    if not args.url and not DIST.exists():
        print(f"no built UI at {DIST}; run `npm run build` in frontend/ first", file=sys.stderr)
        return 2

    proc = tmp = None
    base = args.url.rstrip("/") if args.url else None
    try:
        if base is None:
            proc, base, tmp = start_server(args.seed)
            print(f"started a throwaway server at {base} (LIVE_SEED={args.seed})", flush=True)
        wait_for(base)
        print("live-mode end-to-end check", flush=True)
        rep = run(base, args.seconds, args.headed, not args.no_dashboard_bus)
    except Exception as exc:
        print(f"could not run: {type(exc).__name__}: {exc}", file=sys.stderr)
        if tmp:
            print(f"server log: {pathlib.Path(tmp, 'server.log')}", file=sys.stderr)
        return 2
    finally:
        if proc:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except Exception:
                proc.kill()

    failed = [what for ok, what, _ in rep.rows if not ok]
    print(f"\n{'PASSED' if rep.passed else 'FAILED'}: {len(rep.rows) - len(failed)}/{len(rep.rows)} checks"
          + (f" - failing: {', '.join(failed)}" if failed else ""))
    return 0 if rep.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
