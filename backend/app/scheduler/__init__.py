from .cpsat import solve_cpsat
from .ga import solve_ga
from .heuristics import solve_fcfs, solve_priority
from .metrics import evaluate
from .problem import Problem, Solution, build_problem
from .reasons import explain

ALGORITHMS = {"FCFS": solve_fcfs, "PRIORITY": solve_priority, "GA": solve_ga, "CPSAT": solve_cpsat}


def solve(problem: Problem, algorithm: str = "CPSAT", **kw) -> Solution:
    algorithm = algorithm.upper()
    if algorithm not in ALGORITHMS:
        raise ValueError(f"Unknown algorithm {algorithm}")
    return ALGORITHMS[algorithm](problem, **kw)
