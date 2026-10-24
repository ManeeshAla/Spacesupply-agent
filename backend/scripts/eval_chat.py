"""Evaluate the Gemini supervisor against the real API.

    cd backend
    python scripts/eval_chat.py              # whole set
    python scripts/eval_chat.py --only read  # one category
    python scripts/eval_chat.py --pace 4.5   # slower, for a tight free-tier RPM

What it measures, per question:
  * tool choice   - did it call one of the tools the question should be answered from?
  * answer        - did the reply contain the expected substrings and avoid the rejected ones?
  * grounding     - did the guard find an invented id or number?
  * confirmation  - did an action stop and ask instead of just running?
  * fallback      - did it have to drop to the offline Micro LM?

The plant is reset before the run, and reset again after any confirmed action, so results do
not depend on the order questions happen to run in. Every question is read-only unless it is
in the "action" category; those are left pending and never confirmed, so the state is stable.

Results are written to artifacts/chat_eval.json and shown on the dashboard's Reports page.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

QUESTIONS = pathlib.Path(__file__).resolve().parents[1] / "eval" / "questions.json"


def grade(q: dict, out: dict) -> dict:
    """Score one answer. Returns the per-question record."""
    answer = (out.get("answer") or "")
    low = answer.lower()
    tools = [c["tool"] for c in out.get("tools_called") or []]
    ui = [c.get("action") for c in out.get("ui_commands") or []]
    fell_back = out.get("source") != "gemini"
    notes: list[str] = []

    # --- tool choice
    want = q.get("tools") or []
    if not want:
        tool_ok = None                      # off-topic questions should not need a tool
        if q.get("off_topic") and tools:
            notes.append(f"called {tools} for an off-topic question")
    elif q.get("all_tools"):
        tool_ok = all(t in tools for t in want)
    else:
        tool_ok = any(t in tools for t in want)
    if tool_ok is False:
        notes.append(f"expected one of {want}, called {tools or 'nothing'}")

    # --- answer content
    answer_ok = True
    if q.get("expect"):
        # the entity may be named in the prose or proved by the tool arguments: an answer that
        # lists WS-04's tasks without repeating "WS-04" is right, just differently worded
        called_with = json.dumps(out.get("tools_called") or [], default=str).lower()
        if not any(s.lower() in low or s.lower() in called_with for s in q["expect"]):
            answer_ok = False
            notes.append(f"neither the answer nor the tool arguments mention any of {q['expect']}")
    for bad in q.get("reject") or []:
        if bad.lower() in low:
            answer_ok = False
            notes.append(f"contains {bad!r}")
    if q.get("expect_no_data"):
        admits = any(p in low for p in ("no ", "not ", "could not", "cannot", "don't have", "do not have",
                                        "unable", "no match", "unknown", "nothing"))
        if not admits:
            answer_ok = False
            notes.append("did not admit it had no data")
    if q.get("off_topic"):
        deflects = any(p in low for p in ("assembly", "outside", "cannot help", "can't help", "not something",
                                          "only", "i cover", "launch-vehicle", "launch vehicle"))
        if not deflects:
            answer_ok = False
            notes.append("did not deflect an off-topic question")

    # --- confirmation gate
    pending = out.get("pending_action")
    confirm_ok = None
    if q.get("confirms"):
        confirm_ok = bool(pending)
        if not confirm_ok:
            notes.append("an action ran (or was skipped) without asking for confirmation")

    # --- ui command
    ui_ok = None
    if q.get("ui"):
        ui_ok = any(a in ui for a in q["ui"])
        if not ui_ok:
            notes.append(f"expected a {q['ui']} ui command, got {ui or 'none'}")
        for key in q.get("ui_has") or []:          # e.g. "open CMP-021" must carry a component_id
            if not any(key in c for c in out.get("ui_commands") or []):
                ui_ok = False
                notes.append(f"the ui command did not carry {key}")
    elif ui:
        # a question that did not ask to be shown something must leave the dashboard alone
        ui_ok = False
        notes.append(f"moved the dashboard ({ui}) on a plain question")

    grounded = bool(out.get("grounded", True))
    if not grounded:
        notes.append(f"ungrounded values: {out.get('ungrounded')}")

    passed = (tool_ok is not False) and answer_ok and grounded and (confirm_ok is not False) \
        and (ui_ok is not False) and not fell_back
    return {"id": q["id"], "category": q["category"], "question": q["q"], "passed": passed,
            "tool_ok": tool_ok, "answer_ok": answer_ok, "grounded": grounded, "confirm_ok": confirm_ok,
            "ui_ok": ui_ok, "fell_back": fell_back, "tools_called": tools, "ui_commands": ui,
            "expected_tools": want, "latency_ms": out.get("latency_ms"), "model": out.get("model"),
            "answer": answer[:400], "notes": notes,
            "pending": (pending or {}).get("summary")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="run one category: read, follow_up, ui, action, tricky, off_topic")
    ap.add_argument("--pace", type=float, default=2.5, help="seconds to wait between questions (free-tier RPM)")
    ap.add_argument("--limit", type=int, help="stop after N questions")
    ap.add_argument("--out", help="where to write the report (default artifacts/chat_eval.json)")
    args = ap.parse_args()

    from app.assistant import gemini, sessions, supervisor
    from app.assistant.tools import ToolCtx
    from app.config import CHAT_EVAL_PATH
    from app.database import SessionLocal
    from app.engine import engine as eng

    if not gemini.configured():
        print("No GEMINI_API_KEY found (put it in backend/.env). Nothing to evaluate.", file=sys.stderr)
        return 2

    spec = json.loads(QUESTIONS.read_text(encoding="utf-8"))
    questions = [q for q in spec["questions"] if not args.only or q["category"] == args.only]
    if args.limit:
        questions = questions[:args.limit]

    db = SessionLocal()
    print("Resetting the plant to its initial state ...")
    eng.reset(db)
    supervisor.reset_memory()
    sessions.clear()

    results: list[dict] = []
    started = time.time()
    for i, q in enumerate(questions, 1):
        # follow-ups share a session with the question they follow; everything else is isolated
        session = f"eval-{q.get('follow_up_of') or q['id']}"
        ctx = ToolCtx(db=db, lock=None, confirm=True)
        print(f"[{i}/{len(questions)}] {q['category']:9s} {q['q'][:60]}", flush=True)
        try:
            out = supervisor.run(ctx, q["q"], session)
        except Exception as exc:
            out = {"answer": "", "source": "error", "tools_called": [], "grounded": True,
                   "error": f"{type(exc).__name__}: {exc}"}
        rec = grade(q, out)
        if out.get("error"):
            rec["notes"].append(out["error"])
        results.append(rec)
        print(f"          {'PASS' if rec['passed'] else 'FAIL'}"
              + (f"  ({'; '.join(rec['notes'])[:110]})" if rec["notes"] else ""), flush=True)
        if i < len(questions):
            time.sleep(args.pace)

    # ---- aggregate
    def rate(rows, key):
        vals = [r[key] for r in rows if r[key] is not None]
        return round(100 * sum(1 for v in vals if v) / len(vals), 1) if vals else None

    lat = [r["latency_ms"] for r in results if r["latency_ms"]]
    by_cat: dict[str, dict] = {}
    for cat in sorted({r["category"] for r in results}):
        rows = [r for r in results if r["category"] == cat]
        by_cat[cat] = {"n": len(rows), "accuracy": rate(rows, "passed"), "tool_choice": rate(rows, "tool_ok"),
                       "answer": rate(rows, "answer_ok"), "grounded": rate(rows, "grounded")}

    report = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "model": gemini.GEMINI_MODEL, "fallback_model": gemini.GEMINI_FALLBACK_MODEL,
        "questions": len(results), "duration_s": round(time.time() - started, 1),
        "overall": {
            "accuracy": rate(results, "passed"),
            "tool_choice_accuracy": rate(results, "tool_ok"),
            "answer_accuracy": rate(results, "answer_ok"),
            "grounded": rate(results, "grounded"),
            "confirmation_respected": rate(results, "confirm_ok"),
            "ui_command_accuracy": rate(results, "ui_ok"),
            "fallback_rate": round(100 * sum(1 for r in results if r["fell_back"]) / len(results), 1),
            "latency_ms_median": int(statistics.median(lat)) if lat else None,
            "latency_ms_p90": int(sorted(lat)[int(0.9 * (len(lat) - 1))]) if lat else None,
        },
        "by_category": by_cat,
        "failures": [{"id": r["id"], "question": r["question"], "notes": r["notes"]}
                     for r in results if not r["passed"]],
        "results": results,
    }
    out_path = pathlib.Path(args.out) if args.out else CHAT_EVAL_PATH
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

    o = report["overall"]
    print("\n" + "=" * 62)
    print(f"  {report['questions']} questions in {report['duration_s']}s on {report['model']}")
    print(f"  overall accuracy      {o['accuracy']}%")
    print(f"  tool choice           {o['tool_choice_accuracy']}%")
    print(f"  answer content        {o['answer_accuracy']}%")
    print(f"  grounded answers      {o['grounded']}%")
    print(f"  confirmation gate     {o['confirmation_respected']}%")
    print(f"  ui commands           {o['ui_command_accuracy']}%")
    print(f"  fell back to Micro LM {o['fallback_rate']}%")
    print(f"  latency median/p90    {o['latency_ms_median']}ms / {o['latency_ms_p90']}ms")
    print("=" * 62)
    for cat, v in by_cat.items():
        print(f"  {cat:10s} n={v['n']:<3d} accuracy {v['accuracy']}%  tool choice {v['tool_choice']}%")
    if report["failures"]:
        print("\n  failures:")
        for f in report["failures"]:
            print(f"   - {f['id']}: {f['question'][:52]} | {'; '.join(f['notes'])[:80]}")
    print(f"\nwritten to {out_path}")
    db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
