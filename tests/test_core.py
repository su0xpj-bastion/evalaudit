from __future__ import annotations

import math

import pytest

from evalaudit.data import load
from evalaudit.exploits import EXPLOITS
from evalaudit.graders import GRADERS, grade
from evalaudit.mutation import mutants
from evalaudit.runner import use_fork
from evalaudit.stats import mde_two_proportions, wilson


@pytest.fixture(scope="module", autouse=True)
def _fork():
    use_fork()


# ---------- stats ----------

def test_wilson_bounds_and_known_value():
    lo, hi = wilson(0, 10)
    assert lo == 0.0 and 0.25 < hi < 0.35
    lo, hi = wilson(50, 100)
    assert math.isclose(lo, 0.4038, abs_tol=1e-3) and math.isclose(hi, 0.5962, abs_tol=1e-3)


def test_mde_shrinks_with_n():
    assert mde_two_proportions(1000, 0.5) < mde_two_proportions(100, 0.5)
    assert math.isclose(mde_two_proportions(164, 0.5), 0.155, abs_tol=0.002)


# ---------- mutation ----------

SRC = '''
def f(xs, k):
    """docstring 123"""
    total = 0
    for x in xs:
        if x > k and not x == 3:
            total += x
    return total
'''


def test_mutants_are_distinct_valid_and_only_touch_entry():
    ms = mutants(SRC + "\ndef helper():\n    return 1 + 1\n", "f", max_mutants=100, seed="t")
    assert ms, "expected mutants"
    srcs = [m for _, m in ms]
    assert len(set(srcs)) == len(srcs)
    for s in srcs:
        compile(s, "<m>", "exec")
        assert "return 1 + 1" in s  # helper untouched
        assert "docstring 123" in s  # docstring untouched


def test_mutants_deterministic():
    assert mutants(SRC, "f", seed="a") == mutants(SRC, "f", seed="a")


def test_no_entry_point_no_mutants():
    assert mutants(SRC, "missing") == []


# ---------- graders + exploits (real benchmark tasks) ----------

@pytest.mark.parametrize("benchmark,task_id", [("humaneval", "HumanEval/0"), ("mbpp", "Mbpp/3")])
def test_reference_passes_every_grader(benchmark, task_id):
    task = load(benchmark)[task_id]
    assert [grade(task, task.canonical, g) for g in GRADERS] == ["pass"] * len(GRADERS)


@pytest.mark.parametrize("benchmark,task_id", [("humaneval", "HumanEval/0"), ("mbpp", "Mbpp/3")])
def test_null_control_fails_every_grader(benchmark, task_id):
    task = load(benchmark)[task_id]
    assert [grade(task, EXPLOITS["null"](task), g) for g in GRADERS] == ["fail"] * len(GRADERS)


def test_hybrid_cheater_passes_without_solving():
    task = load("humaneval")["HumanEval/0"]
    sol = EXPLOITS["hybrid"](task)
    assert "sorted" not in sol.split("def has_close_elements(*args")[1]
    assert [grade(task, sol, g) for g in ("original", "base", "plus")] == ["pass"] * 3


@pytest.mark.parametrize("exploit", ["always_equal", "frame_peek", "hybrid"])
def test_hardened_grader_rejects_cheaters(exploit):
    for benchmark, task_id in [("humaneval", "HumanEval/0"), ("mbpp", "Mbpp/2")]:
        task = load(benchmark)[task_id]
        assert grade(task, EXPLOITS[exploit](task), "hardened") == "fail"


def test_hardened_strips_subclass_eq_cheat():
    # A dict subclass with __eq__ -> True must be rebuilt as a plain dict.
    task = load("mbpp")["Mbpp/88"]  # reference returns collections.Counter
    cheat = task.prompt + (
        "\nclass D(dict):\n    def __eq__(self, o):\n        return True\n"
        f"\ndef {task.entry_point}(*a, **k):\n    return D()\n"
    )
    assert grade(task, task.canonical, "hardened") == "pass"
    assert grade(task, cheat, "hardened") == "fail"
    assert grade(task, cheat, "plus") == "pass"  # EvalPlus accepts it
