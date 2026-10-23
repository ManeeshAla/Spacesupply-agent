import pytest
from app.scheduler import ALGORITHMS, solve
from app.scheduler.metrics import count_conflicts, evaluate
from app.scheduler.problem import build_problem


@pytest.mark.parametrize("alg", ["FCFS", "PRIORITY", "GA", "CPSAT"])
def test_schedule_is_feasible(db, alg):
    p = build_problem(db)
    s = solve(p, alg)
    assert set(s.assign) == set(p.jobs), "every pending job must be scheduled"
    assert count_conflicts(p, s.assign) == 0


def test_cpsat_not_worse_than_heuristics(db):
    p = build_problem(db)
    obj = {a: evaluate(p, solve(p, a))["objective"] for a in ALGORITHMS}
    assert obj["CPSAT"] <= obj["FCFS"]
    assert obj["CPSAT"] <= obj["PRIORITY"]


def test_unknown_algorithm(db):
    with pytest.raises(ValueError):
        solve(build_problem(db), "NOPE")


def test_release_times_respected(db):
    p = build_problem(db)
    s = solve(p, "CPSAT")
    for j, (_, start, _) in s.assign.items():
        assert start >= p.jobs[j].release
