"""Genetic Algorithm (random-key encoding + dispatching decoder)."""
from __future__ import annotations

import random
import time

from .heuristics import dispatch
from .metrics import evaluate
from .problem import Problem, Solution


def solve_ga(problem: Problem, population: int = 50, generations: int = 60, seed: int = 7) -> Solution:
    t0 = time.perf_counter()
    rng = random.Random(seed)
    ids = sorted(problem.jobs, key=lambda j: problem.jobs[j].order)
    n = len(ids)
    if n == 0:
        return Solution({}, "GA", 0.0)

    def decode(keys: list[float]) -> Solution:
        k = dict(zip(ids, keys))
        return dispatch(problem, lambda c: min(c, key=lambda x: (k[x[0].id], x[0].order))[0], "GA")

    def fitness(keys: list[float]) -> float:
        return evaluate(problem, decode(keys))["objective"]

    # seed the population with rule-of-thumb individuals (priority / deadline order) + random ones
    def rule_keys(f):
        order = sorted(ids, key=f)
        rank = {j: i / n for i, j in enumerate(order)}
        return [rank[j] for j in ids]
    pop = [
        rule_keys(lambda j: (-problem.jobs[j].priority, problem.jobs[j].deadline)),
        rule_keys(lambda j: problem.jobs[j].deadline),
        rule_keys(lambda j: problem.jobs[j].order),
    ]
    while len(pop) < population:
        pop.append([rng.random() for _ in range(n)])
    fits = [fitness(c) for c in pop]

    for _ in range(generations):
        ranked = sorted(zip(fits, pop), key=lambda x: x[0])
        elite = [c for _, c in ranked[: max(2, population // 10)]]
        new = [list(c) for c in elite]
        while len(new) < population:
            def tour():
                a, b = rng.sample(range(len(pop)), 2)
                return pop[a] if fits[a] < fits[b] else pop[b]
            p1, p2 = tour(), tour()
            child = [x if rng.random() < 0.5 else y for x, y in zip(p1, p2)]
            for i in range(n):
                if rng.random() < 0.08:
                    child[i] = min(1.0, max(0.0, child[i] + rng.gauss(0, 0.25)))
            new.append(child)
        pop = new
        fits = [fitness(c) for c in pop]
    best = min(range(len(pop)), key=lambda i: fits[i])
    sol = decode(pop[best])
    sol.runtime_ms = (time.perf_counter() - t0) * 1000
    sol.note = f"population={population}, generations={generations}"
    return sol
