from __future__ import annotations

"""Benchmark loading: HumanEval(+) and MBPP(+) via EvalPlus's own loaders.

Each Task carries both test suites we audit:
  * original  - the assert-based tests shipped with the original benchmark
                (HumanEval `check(candidate)`, MBPP `assert` list)
  * base/plus - EvalPlus inputs with ground-truth outputs computed by
                EvalPlus's own `get_groundtruth` (cached on disk)
"""

import contextlib
import io
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

BENCHMARKS = ("humaneval", "mbpp")


@dataclass(frozen=True)
class Task:
    benchmark: str
    task_id: str
    entry_point: str
    prompt: str
    canonical: str  # full, runnable reference solution
    original_test: str  # appended after a solution to form the original program
    base_input: list[Any]
    plus_input: list[Any]
    expected_base: list[Any]
    expected_plus: list[Any]
    base_time: list[float]
    plus_time: list[float]
    atol: float


def _load_raw(benchmark: str) -> tuple[dict, dict]:
    from evalplus.data import (
        get_human_eval_plus,
        get_human_eval_plus_hash,
        get_mbpp_plus,
        get_mbpp_plus_hash,
    )
    from evalplus.eval._special_oracle import MBPP_OUTPUT_NOT_NONE_TASKS
    from evalplus.evaluate import get_groundtruth

    with contextlib.redirect_stdout(io.StringIO()):
        if benchmark == "humaneval":
            problems = get_human_eval_plus()
            truth = get_groundtruth(problems, get_human_eval_plus_hash(), [])
        elif benchmark == "mbpp":
            problems = get_mbpp_plus()
            truth = get_groundtruth(
                problems, get_mbpp_plus_hash(), MBPP_OUTPUT_NOT_NONE_TASKS
            )
        else:
            raise ValueError(f"unknown benchmark: {benchmark}")
    return problems, truth


@lru_cache(maxsize=None)
def load(benchmark: str) -> dict[str, Task]:
    problems, truth = _load_raw(benchmark)
    test_imports: dict[str, list[str]] = {}
    if benchmark == "mbpp":
        from evalplus.data.mbpp import get_mbpp

        with contextlib.redirect_stdout(io.StringIO()):
            raw = get_mbpp()  # sanitized MBPP keeps `test_imports` separately
        test_imports = {f"Mbpp/{k}": v.get("test_imports", []) for k, v in raw.items()}
    tasks: dict[str, Task] = {}
    for task_id, p in problems.items():
        entry = p["entry_point"]
        if benchmark == "humaneval":
            # openai/human-eval execution.py: prompt + completion + test + check(entry)
            original_test = "\n" + p["test"] + "\n" + f"check({entry})\n"
        else:
            # google-research/mbpp: code + test_imports + "\n".join(test_list)
            imports = "\n".join(test_imports.get(task_id, []))
            original_test = "\n" + imports + "\n" + p["assertion"] + "\n"
        t = truth[task_id]
        tasks[task_id] = Task(
            benchmark=benchmark,
            task_id=task_id,
            entry_point=entry,
            prompt=p["prompt"],
            canonical=p["prompt"] + p["canonical_solution"],
            original_test=original_test,
            base_input=p["base_input"],
            plus_input=p["plus_input"],
            expected_base=t["base"],
            expected_plus=t["plus"],
            base_time=t["base_time"],
            plus_time=t["plus_time"],
            atol=p["atol"],
        )
    return tasks
