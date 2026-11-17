from __future__ import annotations

# The three experiments. Each returns raw per-job rows; report.py aggregates.

from evalaudit.data import BENCHMARKS, load
from evalaudit.exploits import EXPLOITS
from evalaudit.graders import GRADERS
from evalaudit.mutation import mutants
from evalaudit.runner import Job, run_jobs


def exploit_experiment(benchmarks=BENCHMARKS, workers: int | None = None) -> list[dict]:
    jobs = [
        Job(b, t.task_id, g, fn(t), f"exploit:{name}")
        for b in benchmarks
        for t in load(b).values()
        for name, fn in EXPLOITS.items()
        for g in GRADERS
    ]
    print(f"[exploits] {len(jobs)} jobs")
    return run_jobs(jobs, workers)


def mutation_experiment(
    benchmarks=BENCHMARKS, max_mutants: int = 25, workers: int | None = None
) -> list[dict]:
    # Phase 1: every mutant through the two "shipped" graders.
    jobs: list[Job] = []
    sources: dict[tuple[str, str, str], str] = {}
    for b in benchmarks:
        for t in load(b).values():
            for desc, src in mutants(t.canonical, t.entry_point, max_mutants, seed=t.task_id):
                tag = f"mutant:{desc}"
                sources[(b, t.task_id, tag)] = src
                for g in ("original", "base"):
                    jobs.append(Job(b, t.task_id, g, src, tag))
    print(f"[mutation] phase 1: {len(sources)} mutants, {len(jobs)} jobs")
    rows = run_jobs(jobs, workers)

    # Phase 2: oracle (EvalPlus plus suite) only for mutants some grader accepted.
    accepted = {(r["benchmark"], r["task_id"], r["tag"]) for r in rows if r["status"] == "pass"}
    oracle_jobs = [Job(b, tid, "plus", sources[(b, tid, tag)], tag) for (b, tid, tag) in sorted(accepted)]
    print(f"[mutation] phase 2: {len(oracle_jobs)} accepted mutants -> plus oracle")
    rows += run_jobs(oracle_jobs, workers)
    for r in rows:
        r["source"] = sources[(r["benchmark"], r["task_id"], r["tag"])]
    return rows


def reliability_experiment(
    benchmarks=BENCHMARKS, repeats: int = 5, workers: int | None = None
) -> list[dict]:
    # Reference solutions, every grader, `repeats` times, run with workers >
    # cores to emulate a loaded CI box. A correct grader returns PASS every time.
    jobs = [
        Job(b, t.task_id, g, t.canonical, f"canonical:{r}")
        for r in range(repeats)
        for b in benchmarks
        for t in load(b).values()
        for g in GRADERS
    ]
    print(f"[reliability] {len(jobs)} jobs")
    return run_jobs(jobs, workers)
