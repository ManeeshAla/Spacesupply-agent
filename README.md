# SpaceSupply-Agent

**Autonomous multi-agent framework for launch-vehicle assembly-line scheduling and component tracking** — final-year project prototype.

> ⚠️ **All data is synthetic** (fictional suppliers, parts and schedules). The project is not affiliated with ISRO or any space agency.

## What it does
Tracks ~85 component lots through their lifecycle (ordered → received → inspected → warehouse → bay → installed), keeps a precedence- and component-aware assembly schedule for a 4-stage vehicle, and **re-plans automatically** when something goes wrong (supplier delay, rejected part, workstation outage). A chat assistant answers questions about the plant in plain language, **runs simulations on request** (after you confirm) and **drives the dashboard** for you.

## Architecture
```
React dashboard ──► FastAPI ──► Supervisor agent (LangGraph + Gemini tool calling)
                                 Micro LM hint → Gemini ⇄ tools → grounding guard → answer
                                 │
                                 │  25 tools wrapping the specialist agents:
                                 ├─ Tracking Agent    component lifecycle & history
                                 ├─ Supply Agent      inventory, shortages, supplier delays
                                 ├─ Scheduling Agent  FCFS · Priority · Genetic Algorithm · OR-Tools CP-SAT
                                 └─ Monitoring Agent  alerts (delay, rejection, downtime, maintenance, late task)
                                 │
                                 └─ Message bus: agents publish/subscribe to each other
                                SQLAlchemy ──► SQLite (default) or PostgreSQL
```

### The chat assistant (supervisor agent)
A LangGraph tool-calling loop (`agent → tools → agent`) driven by **Gemini** through
`langchain-google-genai`. It has **25 tools**: 18 read tools (component status/history, inventory,
shortages, suppliers, schedule, task explanation, delayed tasks, alerts, stage progress, deliveries,
readiness, scheduler comparison, plant status, live mode, agent messages …), 5 simulation actions,
and tools to acknowledge an alert, control live mode and move the dashboard.

* **Grounded answers.** The model has no knowledge of the plant: it can only report what a tool
  returned. After every answer, `llm.facts_grounded` checks each id and number against the raw tool
  output; if the model invented one, the answer is thrown away and replaced by a deterministic
  summary of the tool results (you see an "answer rewritten" badge). The older Qwen guard
  (`facts_preserved`) still protects the rewording path.
* **Confirmation before anything changes.** The five simulation actions (delay a delivery, reject a
  component, take a workstation down, re-plan, advance the clock) do **not** run when the model asks
  for them. They return a pending action, the chat shows **Confirm / Cancel**, and only your click
  executes it. The result is summarised deterministically from the tool output, not re-narrated by
  the model. Turn the gate off with the checkbox in the chat header (or `CONFIRM_ACTIONS=0`) for a
  hands-free demo.
* **Memory.** A LangGraph `MemorySaver` keyed by session id, so *"and what about its supplier?"*
  resolves against the previous turn. In-process, so it clears on restart or **New chat**.
* **Streaming.** `POST /api/chat/stream` is server-sent events: `start`, `token`, `tool_call`,
  `tool_result`, `ui`, `block`, `pending`, `note`, `replace`, `done`.
* **It drives the dashboard.** Tools return UI commands, so *"show me alerts for stage 3"* opens the
  Alerts page with the filter set, and *"open CMP-021"* opens its drawer. Tools can also return small
  tables rendered inside the chat.
* **The Micro LM is still in the loop**, in three places: it runs first on every question and its
  intent/entity guess is injected as a hint, it powers the input autocomplete, and it is the
  **offline fallback** — if there is no API key, or Gemini errors or runs out of free quota, the
  original Micro LM + template orchestrator answers instead and the UI says so.

### Agent-to-agent communication (message bus)
`backend/app/bus.py`. Agents publish structured messages on topics and subscribe to the topics they
care about, instead of the engine calling them in a fixed order. A supplier delay reads as a
conversation, visible live in the **Agent communication** panel (Agents page and the chat sidebar):

```
Supply Agent      --supplier.delay-->     Registered 24h delay on CMP-021 (Fuel Pump) …
Scheduling Agent  --schedule.replanned--> New plan v2 (CPSAT): 11 task(s) moved, 4 late, makespan 183h
Monitoring Agent  --alerts.scanned-->     5 new alert(s), 0 resolved, 8 open
```

Messages from one trigger share a `correlation_id` (one colour stripe in the UI) and are persisted in
`agent_messages`. This is synchronous in-process pub/sub — real message passing between agent
objects, not a distributed broker.

### The rest
* **Micro LM** (`backend/app/microlm`): Embedding(32) → BiGRU(48) → intent head (14 intents) + BIO entity tagger + next-word head (chat autocomplete). **106,245 trainable parameters.** Trains in ~2 min on CPU; auto-trains on first start if `artifacts/microlm.pt` is missing.
* **Scheduler**: flexible job-shop with precedence, component-readiness release times, workstation availability and deadlines. Objective = 10 × priority-weighted tardiness + makespan. Every task carries a *binding-constraint explanation* (waiting for component X / predecessor Y / workstation Z).
* **Autonomy**: events trigger re-planning (warm-started CP-SAT), a monitoring scan and alerts; a background supervisor runs every 15 s. Schedules are versioned.
* **Qwen layer (optional)**: if [Ollama](https://ollama.com) is running with `qwen2.5:3b-instruct`, the Micro LM's fallback answers are re-worded by Qwen; a guard rejects any rewrite that changes an ID or number. Without Ollama everything still works (deterministic wording).

## Run
```bash
./run.sh                      # creates venv, installs, builds the UI, serves everything on :8000
# open http://localhost:8000
```
Manual: `cd backend && pip install -r requirements.txt && uvicorn app.main:app --port 8000`; for UI development `cd frontend && npm install && npm run dev` (proxies `/api` to :8000).

### Setting up the Gemini API key
The dashboard, scheduling, simulation and live mode all work with **no key at all**; only the
tool-calling chat needs one (without it the chat falls back to the Micro LM and says so).

1. Get a free key at <https://aistudio.google.com/apikey>.
2. `cp backend/.env.example backend/.env` and put the key in `GEMINI_API_KEY=`.
3. Restart the backend. The chat sidebar and Reports page show whether the key was picked up.

`backend/.env` is git-ignored — do not commit your key.

| Variable | Default | Meaning |
|---|---|---|
| `GEMINI_API_KEY` | – | free-tier key; without it the chat is Micro LM only |
| `GEMINI_MODEL` | `gemini-3.5-flash-lite` | primary model (free tier, supports tool calling) |
| `GEMINI_FALLBACK_MODEL` | `gemini-3.1-flash-lite` | used when the primary is out of quota or overloaded |
| `GEMINI_MAX_RETRIES` | `3` | attempts per model, exponential backoff with jitter |
| `MAX_TOOL_STEPS` | `6` | tool-calling rounds allowed per question |
| `CHAT_HISTORY_TURNS` | `8` | turns kept in conversation memory |
| `CONFIRM_ACTIONS` | `1` | `0` runs simulation actions without asking |

Model choice, measured against a real free-tier key rather than taken from the docs: the two
**lite** models are the usable defaults. `gemini-3.5-flash-lite` and `gemini-3.1-flash-lite` both
support tool calling and answered in 1–9s. The larger `gemini-3.6-flash` and `gemini-3.8-flash`
choose tools slightly better, but their free allowance is tiny — on a fresh key they returned
504/503 and then `429 RESOURCE_EXHAUSTED` within a handful of calls, so they are not a sane default.
Set one here if you have paid quota. `gemini-2.0-flash` and `gemini-3-pro-preview` are shut down, and
`gemini-2.5-flash` returns 404 on a new key.

On a `429`, `503` or timeout the assistant retries with exponential backoff, puts that model in a
60-second cooldown so later turns skip it, switches to the fallback model, and only then drops to the
Micro LM — each step is reported in the chat.

Other env: `DATABASE_URL` (see `docker-compose.yml` for PostgreSQL), `USE_QWEN=auto|on|off`, `OLLAMA_URL`, `QWEN_MODEL`, `SUPERVISOR_ENABLED=0`.

## Live mode (the demo everyone watches)
Press **Play** in the header. The simulated clock then runs by itself: deliveries arrive, parts pass inspection into the warehouse, tasks start and finish, and the rocket, Gantt and progress chart move. **Random events** (on by default) inject a supplier delay, a failed inspection or a workstation outage every so often — the agents detect it, re-plan with CP-SAT and raise alerts while you watch. The **Live activity** panel on the dashboard is the running commentary.

* Speed `1× 2× 4× 8×` = 4 / 2 / 1 / 0.5 real seconds per plant hour. At the default **4×** a full vehicle build takes about 3 minutes, which fits a 5-minute presentation.
* **Random events** can be switched off for a clean run; **Scenario** still lets you trigger a specific disruption by hand.
* The reset button (↺) returns the plant to its initial state.
* Live mode starts **paused**, so nothing moves until you press Play.

## 3-minute demo
1. Dashboard: overview, component donut, inventory, alerts, progress. Press **Play** and let it run while you talk.
2. **AI Assistant** → *“Delay CMP-021's delivery by 24 hours.”* → the assistant explains what will happen and waits; press **Confirm**. The agents react, a new schedule version appears, alerts are raised.
3. Agents page → **Agent communication**: the same event as a three-agent exchange (Supply → Scheduling → Monitoring) on one colour stripe.
4. Back in chat: *“Why is it late now?”* then *“show me alerts for stage 2”* → the follow-up resolves from memory and the dashboard jumps to the filtered Alerts page by itself.
5. Schedule page: Gantt with red rings on projected-late tasks; click a bar for the explanation; try **Re-plan** with each algorithm.
6. Reports page: chat-assistant evaluation, Micro LM metrics and scheduler comparison.

## Evaluation (measured, synthetic data)

**Chat assistant** — 46 questions run against the real Gemini API: 20 reads, 6 follow-ups needing
memory, 3 dashboard-control, 8 actions, 6 tricky/no-data, 3 off-topic. A question passes only if the
right tool was called, the answer contained what it should and nothing it should not, the grounding
guard passed, an action stopped for confirmation, and the model did not fall back.

Measured on `gemini-3.5-flash-lite`, free tier, October 2026:

| Metric | Result |
|---|---|
| **Overall accuracy** | **97.8%** (45/46) |
| Correct tool chosen | 100% |
| Answer content | 97.8% |
| **Grounded answers** (no invented id or number) | **100%** |
| Confirmation gate respected on actions | 100% |
| Dashboard commands correct | 100% |
| Fell back to the Micro LM | 2.2% |
| Latency median / p90 | 2.6s / 16.1s |

Per category: reads 100%, follow-ups 100%, dashboard control 100%, actions 100%, tricky 100%,
off-topic 67% (1 of 3).

Reproduce (your numbers will differ a little):
```bash
cd backend
python scripts/eval_chat.py              # whole set, paced for the free tier
python scripts/eval_chat.py --only read  # one category
```
Results are written to `backend/artifacts/chat_eval.json` and shown on the Reports page, including
every failure with its reason.

**Honest notes on these numbers.** Across five runs of the full set I saw 97.8%, 97.8%, 93.5%,
97.8%, 97.8% — the single failure moves between questions, so treat ~95% as the real figure rather
than any one run. The failures were never hallucinations: they were a correct answer phrased without
repeating the id, and the off-topic question landing on the Micro LM fallback (which has no
off-topic intent and so answers it badly). Two bugs the live run exposed and fixed are covered by
tests now: the grounding guard used to flag a correct percentage derived from a fraction
(reliability `0.89` reported as `89%`), and a failed turn used to leave a half-finished exchange in
memory that the next question resumed.

**Micro LM** — 106,245 parameters.
| Split | Intent acc. | Macro F1 | Entity F1 |
|---|---|---|---|
| Validation (seen templates) | 100% | 100% | 100% |
| **Test (unseen templates)** | **78.4%** | **80.3%** | **97.0%** |
| Hand-written challenge (36 queries) | 88.9% | – | – |

The validation score is inflated by template repetition; the held-out-template test number is the honest one. Weak intents (e.g. COMPONENT_LOCATION vs. SUPPLIER_INFO) are visible in the confusion matrix on the Reports page. Low-confidence queries fall back to a keyword prior.

**Schedulers** — mean over 30 randomly perturbed scenarios (delays, outages, deadline squeeze), lower is better, 0 constraint violations for all:
| Suite | FCFS | Priority | GA | CP-SAT |
|---|---|---|---|---|
| Single vehicle (23 tasks) objective | 9228 | 9184 | 9184 | **9181** |
| 3-vehicle campaign (69 tasks) objective | 16119 | 15752 | 14835 | **14349** |
| 3-vehicle runtime (ms) | 1.5 | 1.4 | 4494 | 117 |

On the single vehicle the algorithms almost tie (the problem is dominated by one long component-gated chain); the advantage of optimisation shows on the contended 3-vehicle campaign. Reproduce: `cd backend && python -m scripts.benchmark --n 30`.

## Tests
`cd backend && pytest -q` → **88 tests, all offline, no API key needed.**

The 34 original tests (schedule feasibility for all algorithms, event flow, lifecycle rules, API,
chat, Micro LM parameter count) still pass unchanged. The 54 new ones use a scripted
`FakeChatModel` (`backend/tests/fake_llm.py`) in place of Gemini and cover: every read tool against
every task lifecycle state, tool dispatch and the step budget, the confirmation gate (pending →
confirm / cancel / replay / demo mode), conversation memory and session isolation, the grounding
guard, the retry → fallback-model → Micro LM chain, UI commands and inline tables, the SSE event
order, and the three-agent message-bus exchange.

## Limitations (be upfront in your viva)
* **Synthetic data only**, and the chat evaluation numbers must be produced by running
  `scripts/eval_chat.py` with your own key — they are a live-API measurement, not a fixed result.
* **Free-tier rate limits are the main practical constraint.** The exact RPM/RPD are not published
  per model, and the bigger flash models exhaust their free allowance almost immediately (see the
  model-choice note above). `eval_chat.py` paces itself and may still need `--pace` raised. Hitting a
  limit mid-demo is handled, not prevented: you see the retry notice, then a Micro LM answer.
* **Tests do not call the API.** All 88 run offline against a scripted fake model, so they verify the
  wiring, not Gemini's judgement. Only `scripts/eval_chat.py` measures the real thing.
* **The grounding guard runs after the answer is streamed**, so a bad answer can be briefly visible
  before it is replaced. Numbers 0–10 are whitelisted (models use them to count what they just
  listed), so a wrong *small* count could slip through.
* **Chat memory is in-process** and keyed by session id: it clears on restart, on **New chat**, and
  on a plant reset (the old conversation would refer to a state that no longer exists).
* **The message bus is in-process pub/sub**, not a broker — no retries, no persistence of undelivered
  messages, no cross-process delivery.
* **Prompts go to Google.** The data here is synthetic, but free-tier input may be used by Google to
  improve their products; do not point this at real supplier data without checking their terms.
* The Micro LM is trained on templates, so free-form phrasing is weaker than a real LLM, and it has
  no action intents — **the offline fallback is read-only** and will say so if you ask it to change
  something. It also has no off-topic intent, so when a fallback happens to catch an off-topic
  question it answers it badly (this is the one evaluation failure you will sometimes see).
* The Qwen layer needs Ollama and was not exercised in the build environment; the simulated clock is
  in whole hours; no authentication (prototype).
