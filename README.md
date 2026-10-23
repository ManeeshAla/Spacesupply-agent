# SpaceSupply-Agent

**Autonomous multi-agent framework for launch-vehicle assembly-line scheduling and component tracking** — final-year project prototype.

> ⚠️ **All data is synthetic** (fictional suppliers, parts and schedules). The project is not affiliated with ISRO or any space agency.

## What it does
Tracks ~85 component lots through their lifecycle (ordered → received → inspected → warehouse → bay → installed), keeps a precedence- and component-aware assembly schedule for a 4-stage vehicle, and **re-plans automatically** when something goes wrong (supplier delay, rejected part, workstation outage). You can ask it questions in plain language.

## Architecture
```
React dashboard ──► FastAPI ──► Orchestrator (LangGraph)
                                 understand (PyTorch Micro LM) → route → agent(s) → compose (optional Qwen)
                                 ├─ Tracking Agent    component lifecycle & history
                                 ├─ Supply Agent      inventory, shortages, supplier delays
                                 ├─ Scheduling Agent  FCFS · Priority · Genetic Algorithm · OR-Tools CP-SAT
                                 └─ Monitoring Agent  alerts (delay, rejection, downtime, maintenance, late task)
                                SQLAlchemy ──► SQLite (default) or PostgreSQL
```
* **Micro LM** (`backend/app/microlm`): Embedding(32) → BiGRU(48) → intent head (14 intents) + BIO entity tagger + next-word head (chat autocomplete). **106,245 trainable parameters.** Trains in ~2 min on CPU; auto-trains on first start if `artifacts/microlm.pt` is missing.
* **Scheduler**: flexible job-shop with precedence, component-readiness release times, workstation availability and deadlines. Objective = 10 × priority-weighted tardiness + makespan. Every task carries a *binding-constraint explanation* (waiting for component X / predecessor Y / workstation Z).
* **Autonomy**: events trigger re-planning (warm-started CP-SAT), a monitoring scan and alerts; a background supervisor runs every 15 s. Schedules are versioned.
* **Qwen layer (optional)**: if [Ollama](https://ollama.com) is running with `qwen2.5:3b-instruct`, answers are re-worded by Qwen; a guard rejects any rewrite that changes an ID or number. Without Ollama everything still works (deterministic wording).

## Run
```bash
./run.sh                      # creates venv, installs, builds the UI, serves everything on :8000
# open http://localhost:8000
```
Manual: `cd backend && pip install -r requirements.txt && uvicorn app.main:app --port 8000`; for UI development `cd frontend && npm install && npm run dev` (proxies `/api` to :8000).
Env: `DATABASE_URL` (see `docker-compose.yml` for PostgreSQL), `USE_QWEN=auto|on|off`, `OLLAMA_URL`, `QWEN_MODEL`, `SUPERVISOR_ENABLED=0`.

## Live mode (the demo everyone watches)
Press **Play** in the header. The simulated clock then runs by itself: deliveries arrive, parts pass inspection into the warehouse, tasks start and finish, and the rocket, Gantt and progress chart move. **Random events** (on by default) inject a supplier delay, a failed inspection or a workstation outage every so often — the agents detect it, re-plan with CP-SAT and raise alerts while you watch. The **Live activity** panel on the dashboard is the running commentary.

* Speed `1× 2× 4× 8×` = 4 / 2 / 1 / 0.5 real seconds per plant hour. At the default **4×** a full vehicle build takes about 3 minutes, which fits a 5-minute presentation.
* **Random events** can be switched off for a clean run; **Scenario** still lets you trigger a specific disruption by hand.
* The reset button (↺) returns the plant to its initial state.
* Live mode starts **paused**, so nothing moves until you press Play.

## 3-minute demo
1. Dashboard: overview, component donut, inventory, alerts, progress. Press **Play** and let it run while you talk.
2. **Scenario** → *Supplier delay* → `CMP-021` (Fuel Pump) +24 h → agents react, a new schedule version appears, alerts are raised.
3. Chat: *“Why was Engine Assembly delayed?”* → answer names the Fuel Pump and the chain of tasks.
4. Schedule page: Gantt with red rings on projected-late tasks; click a bar for the explanation; try **Re-plan** with each algorithm.
5. Reports page: Micro LM metrics and scheduler comparison.

## Evaluation (measured, synthetic data)
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
`cd backend && pytest -q` → 34 tests (schedule feasibility for all algorithms, event flow, lifecycle rules, API, chat, Micro LM parameter count ≥ 1000).

## Limitations (be upfront in your viva)
Synthetic data only; the Micro LM is trained on templates so free-form phrasing is weaker than a real LLM; the Qwen layer needs Ollama and was not exercised in the build environment; the simulated clock is in whole hours; no authentication (prototype).
