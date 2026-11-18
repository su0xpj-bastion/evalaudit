from __future__ import annotations

# Experiments for the RL reward-function audit.
#
#   apps     every fake (and the reference, where the dataset has one) through
#            verl, LiveCodeBench, rllm and the hardened grader
#   bcb      BigCodeBench's untrusted_check with the unittest fakes
#   openr1   open-r1's code_reward script with a deliberately truncated program

import multiprocessing
import os
import signal
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass

from evalaudit.rewards import fakes, graders, tasks
from evalaudit.rewards.hardened import hardened

APPS_DATASETS = ["eurus", "lcb_v6", "deepcoder_lcb", "deepcoder_taco", "deepcoder_primeintellect"]
APPS_GRADERS = {**graders.APPS_GRADERS, "hardened": hardened}

JOB_LIMIT = 900  # seconds; a harness-level backstop, far above any grader's own limit


@dataclass(frozen=True)
class Job:
    kind: str
    dataset: str
    task_id: str
    grader: str
    solution: str


def _first_line_only(code: str) -> str:
    # Runs the real reference program but prints only the first line of its
    # output: a wrong program for any test whose answer has more than one line.
    return (
        "import io as _io, sys as _sys\n"
        "_buf, _real = _io.StringIO(), _sys.stdout\n"
        "_sys.stdout = _buf\n"
        "try:\n"
        f"    exec(compile({code!r}, 'reference', 'exec'), {{'__name__': '__main__'}})\n"
        "finally:\n"
        "    _sys.stdout = _real\n"
        "    _lines = _buf.getvalue().strip().split('\\n')\n"
        "    print(_lines[0])\n"
    )


def _source(task: tasks.Task, solution: str) -> str:
    if solution == "reference":
        return task.reference
    if solution == "first_line_only":
        return _first_line_only(task.reference)
    if task.mode == "unittest":
        return fakes.BCB_FAKES[solution]
    return fakes.APPS_FAKES[task.mode][solution]


class _JobTimeout(Exception):
    pass


def _alarm(signum, frame):
    raise _JobTimeout()


def _run(job: Job) -> dict:
    task = tasks.load(job.dataset)[job.task_id]
    code = _source(task, job.solution)
    signal.signal(signal.SIGALRM, _alarm)
    signal.alarm(JOB_LIMIT)
    try:
        if job.kind == "bcb":
            passed, raw = graders.bigcodebench(code, task.tests["test"], task.tests["entry_point"])
        elif job.grader == "open_r1":
            passed, raw = graders.open_r1(code, task.tests)
        else:
            passed, raw = APPS_GRADERS[job.grader](code, task.tests)
    except _JobTimeout:
        passed, raw = False, "harness timeout"
    except Exception as e:  # a grader crash is a non-pass; keep the reason
        passed, raw = False, f"grader exception: {e!r}"[:300]
    finally:
        signal.alarm(0)
    return {
        "dataset": job.dataset,
        "task_id": job.task_id,
        "mode": task.mode,
        "grader": job.grader,
        "solution": job.solution,
        "passed": bool(passed),
        "raw": raw if isinstance(raw, (bool, int, float)) else str(raw)[:300],
    }


def _execute(jobs: list[Job], workers: int, label: str) -> list[dict]:
    multiprocessing.set_start_method("fork", force=True)
    for d in {j.dataset for j in jobs}:
        tasks.load(d)  # load before forking so workers share it
    out: list[dict] = []
    with ProcessPoolExecutor(max_workers=workers) as pool:
        for i, row in enumerate(pool.map(_run, jobs, chunksize=2), 1):
            out.append(row)
            if i % 250 == 0 or i == len(jobs):
                print(f"  {label}: {i}/{len(jobs)}", flush=True)
    return out


def apps_jobs(datasets: list[str], grader_names: list[str]) -> list[Job]:
    jobs = []
    for d in datasets:
        for t in tasks.load(d).values():
            sols = list(fakes.APPS_FAKES[t.mode])
            if t.reference:
                sols.append("reference")
            for g in grader_names:
                for s in sols:
                    jobs.append(Job("apps", d, t.task_id, g, s))
    return jobs


def apps(datasets: list[str] | None = None, grader_names: list[str] | None = None, workers: int = 6) -> list[dict]:
    jobs = apps_jobs(datasets or APPS_DATASETS, grader_names or list(APPS_GRADERS))
    return _execute(jobs, workers, "apps")


def bcb(workers: int = 6) -> list[dict]:
    jobs = [
        Job("bcb", "bigcodebench", t.task_id, "bigcodebench", s)
        for t in tasks.load("bigcodebench").values()
        for s in ["null", "stub_only", "silence", "reference"]
    ]
    return _execute(jobs, workers, "bcb")


OPENR1_TASKS = 100  # open-r1 starts a fresh python per test, so this is the slow one


def openr1(workers: int = 6) -> list[dict]:
    # PrimeIntellect is the source of open-r1's own verifiable-coding-problems data.
    jobs = []
    pool = [t for t in tasks.load("deepcoder_primeintellect").values() if t.mode == "stdio" and t.reference]
    for t in pool[:OPENR1_TASKS]:
        for g in ("open_r1", "hardened"):
            for s in ("reference", "first_line_only", "null", "peek"):
                jobs.append(Job("openr1", t.dataset, t.task_id, g, s))
    return _execute(jobs, workers, "openr1")


def default_workers() -> int:
    return max(2, (os.cpu_count() or 4) - 2)
