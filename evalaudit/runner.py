from __future__ import annotations

# Parallel job runner. Each job grades one solution with one grader. Workers
# are forked so they inherit loaded benchmarks; each grader call forks again
# into a guarded child (same isolation model as human-eval / EvalPlus).

import multiprocessing
import os
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass

from evalaudit.data import load
from evalaudit.graders import grade


@dataclass(frozen=True)
class Job:
    benchmark: str
    task_id: str
    grader: str
    solution: str
    tag: str  # caller-defined label, e.g. "exploit:always_equal" or "mutant:3"


def use_fork() -> None:
    # macOS defaults to spawn, which re-imports __main__ and is ~10x slower per
    # check. The graders are fork-safe (no threads before fork).
    multiprocessing.set_start_method("fork", force=True)
    # macOS rejects RLIMIT_AS; EvalPlus's documented opt-out is -1. On Linux
    # EvalPlus's default 4 GB address-space limit stays in force.
    if sys.platform == "darwin":
        os.environ.setdefault("EVALPLUS_MAX_MEMORY_BYTES", "-1")


def _run(job: Job) -> dict:
    task = load(job.benchmark)[job.task_id]
    status = grade(task, job.solution, job.grader)
    return {
        "benchmark": job.benchmark,
        "task_id": job.task_id,
        "grader": job.grader,
        "tag": job.tag,
        "status": status,
    }


def run_jobs(jobs: list[Job], workers: int | None = None, progress: bool = True) -> list[dict]:
    use_fork()
    for benchmark in {j.benchmark for j in jobs}:
        load(benchmark)  # warm cache before fork
    workers = workers or os.cpu_count() or 4
    results: list[dict] = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for i, res in enumerate(pool.map(_run, jobs, chunksize=4), 1):
            results.append(res)
            if progress and (i % 200 == 0 or i == len(jobs)):
                print(f"  {i}/{len(jobs)}", flush=True)
    return results
