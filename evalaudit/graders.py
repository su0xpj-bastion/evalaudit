from __future__ import annotations

# The graders under audit.
#
#   original  - faithful re-implementation of openai/human-eval `check_correctness`
#               (and the identical MBPP convention): build one program
#               `solution + test + check(entry)`, exec it in a guarded child
#               process, PASS iff no exception. Uses the same guard helpers
#               (reliability_guard / swallow_io / time_limit / create_tempdir)
#               that EvalPlus vendored from human-eval.
#   base/plus - EvalPlus's own `untrusted_check`, imported and called unmodified.

import multiprocessing

from evalplus.eval import untrusted_check
from evalplus.eval.utils import (
    create_tempdir,
    reliability_guard,
    swallow_io,
    time_limit,
)

from evalaudit.data import Task

PASS, FAIL, TIMEOUT = "pass", "fail", "timeout"
ORIGINAL_TIMEOUT_S = 3.0  # human-eval default


def _exec_original(program: str, timeout: float, result) -> None:
    with create_tempdir():
        import os
        import shutil

        rmtree, rmdir, chdir = shutil.rmtree, os.rmdir, os.chdir
        reliability_guard()
        try:
            exec_globals: dict = {}
            with swallow_io():
                with time_limit(timeout):
                    exec(program, exec_globals)
            result.value = 0
        except BaseException as exc:  # noqa: BLE001 - mirror human-eval
            result.value = 2 if type(exc).__name__ == "TimeoutException" else 1
        shutil.rmtree, os.rmdir, os.chdir = rmtree, rmdir, chdir


def run_original(task: Task, solution: str, timeout: float = ORIGINAL_TIMEOUT_S) -> str:
    program = solution + task.original_test
    result = multiprocessing.Value("i", 3)
    p = multiprocessing.Process(target=_exec_original, args=(program, timeout, result))
    p.start()
    p.join(timeout=timeout + 1)
    if p.is_alive():
        p.kill()
        p.join()
        return TIMEOUT
    return {0: PASS, 1: FAIL, 2: TIMEOUT}.get(result.value, FAIL)


def run_evalplus(task: Task, solution: str, split: str, fast_check: bool = True) -> str:
    inputs = task.base_input if split == "base" else task.plus_input
    expected = task.expected_base if split == "base" else task.expected_plus
    ref_time = task.base_time if split == "base" else task.plus_time
    status, _details = untrusted_check(
        task.benchmark,
        solution,
        inputs,
        task.entry_point,
        expected=expected,
        atol=task.atol,
        ref_time=ref_time,
        fast_check=fast_check,
    )
    return status


GRADERS = ("original", "base", "plus", "hardened")


def grade(task: Task, solution: str, grader: str) -> str:
    if grader == "original":
        return run_original(task, solution)
    if grader in ("base", "plus"):
        return run_evalplus(task, solution, grader)
    if grader == "hardened":
        from evalaudit.hardened import run_hardened

        return run_hardened(task, solution)
    raise ValueError(f"unknown grader: {grader}")
