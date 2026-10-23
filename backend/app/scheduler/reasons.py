"""Explainability: why does each task start when it does? (the binding constraint)"""
from __future__ import annotations

from .problem import Problem, Solution


def explain(problem: Problem, sol: Solution) -> dict[str, dict]:
    out: dict[str, dict] = {}
    by_m: dict[str, list[tuple[int, str]]] = {}
    for jid, (mid, s, e) in sol.assign.items():
        by_m.setdefault(mid, []).append((s, jid))
    prev_on_machine: dict[str, tuple[str | None, int]] = {}
    for mid, lst in by_m.items():
        lst.sort()
        last_ref, last_end = problem.machines[mid].free_ref, problem.machines[mid].free_at
        for s, jid in lst:
            prev_on_machine[jid] = (last_ref, last_end)
            last_ref, last_end = jid, sol.assign[jid][2]
    for jid, (mid, s, e) in sol.assign.items():
        job = problem.jobs[jid]
        pred_t, pred_ref = job.release_pred, job.release_pred_ref
        for p in job.preds:
            if p in sol.assign and sol.assign[p][2] >= pred_t:
                pred_t, pred_ref = sol.assign[p][2], p
        ws_ref, ws_t = prev_on_machine[jid]
        comp_t, comp_ref = job.release_comp, job.release_comp_ref
        if s == 0 and comp_t == 0 and pred_t == 0 and ws_t == 0:
            rt, text, ref = "NOW", "Ready to start immediately.", None
        elif comp_t > 0 and s == comp_t:
            rt, ref = "COMPONENT", comp_ref
            text = f"Waiting for component {problem.comp_names.get(comp_ref, comp_ref)} ({comp_ref}), usable in {comp_t}h."
        elif pred_t > 0 and s == pred_t:
            rt, ref = "PREDECESSOR", pred_ref
            text = f"Waits for predecessor '{problem.job_names.get(pred_ref, pred_ref)}' ({pred_ref}) to finish at +{pred_t}h."
        elif ws_t > 0 and s == ws_t:
            rt, ref = "WORKSTATION", (ws_ref if ws_ref and ws_ref != "DOWN" else mid)
            who = f" running '{problem.job_names.get(ws_ref, ws_ref)}'" if ws_ref and ws_ref != "DOWN" else (" (down for repair)" if ws_ref == "DOWN" else "")
            text = f"Workstation {mid} is busy{who} until +{ws_t}h."
        else:
            rt, ref = "OPTIMIZER", mid
            text = f"Sequenced after higher-impact tasks on {mid} to minimise total weighted lateness."
        out[jid] = {"reason_type": rt, "reason_text": text, "binding_ref": ref}
    return out
