from __future__ import annotations

# Hardened grader: the proposed fix.
#
# Root cause of both cheaters: EvalPlus runs the untrusted solution and the
# comparison `out == expected` in the SAME process, so the solution can
#   (a) control the comparison (custom __eq__)      -> always_equal
#   (b) read `expected` off the call stack           -> frame_peek
#
# Fix, three rules:
#   1. Expected outputs never enter the untrusted process.
#   2. The child returns only plain data (exact builtin types, recursively);
#      anything else (custom classes, subclasses) is rejected.
#   3. The trusted parent compares, using EvalPlus's semantics (exact match,
#      float tolerance, and the same special oracles).
# Also: a per-input timeout is reported as TIMEOUT, not as a wrong answer, so
# CI can retry infrastructure noise instead of scoring it.

import multiprocessing

import numpy as np
from evalplus.eval import is_floats
from evalplus.eval._special_oracle import (
    MBPP_OUTPUT_NOT_NONE_TASKS,
    MBPP_OUTPUT_SET_EQ_TASKS,
    _digit_distance_nums,
    _poly,
    _surface_Area,
)
from evalplus.eval.utils import create_tempdir, reliability_guard, swallow_io, time_limit

from evalaudit.data import Task
from evalaudit.graders import FAIL, PASS, TIMEOUT

_PLAIN = (int, float, bool, str, type(None), complex)
_CONTAINERS = (list, tuple, set, frozenset, dict)
_REJECTED = "__evalaudit_rejected_non_plain_output__"


_SCALAR_BASES = (bool, int, float, complex, str)  # bool before int


def _plain(x, depth: int = 0):
    """Convert x to plain data built only from exact builtin types.

    Subclasses of builtins (e.g. collections.Counter, a str subclass) are
    rebuilt as their base type via the base type's own methods, so any custom
    __eq__/__hash__/__iter__ behaviour is stripped. Anything that is not a
    builtin or a subclass of one is rejected."""
    if depth > 50:
        raise TypeError("output nested too deep")
    t = type(x)
    if t in _PLAIN:
        return x
    for base in _SCALAR_BASES:
        if isinstance(x, base):
            return {
                bool: lambda v: bool(int.__int__(v)),
                int: int.__int__,
                float: float.__float__,
                complex: lambda v: complex(float.__float__(v.real), float.__float__(v.imag)),
                str: str.__str__,
            }[base](x)
    if isinstance(x, dict):
        return {_plain(k, depth + 1): _plain(v, depth + 1) for k, v in dict.items(x)}
    for base in (list, tuple, set, frozenset):
        if isinstance(x, base):
            return base(_plain(v, depth + 1) for v in base.__iter__(x))
    raise TypeError(f"non-plain output type {t.__name__}")


def _plain_or_raw(x):
    try:
        return _plain(x)
    except TypeError:
        return x


def _child(task_fields: tuple, solution: str, inputs: list, limits: list, conn) -> None:
    entry_point, not_none = task_fields
    with create_tempdir():
        import os
        import shutil

        rmtree, rmdir, chdir = shutil.rmtree, os.rmdir, os.chdir
        reliability_guard()
        results: list = []
        try:
            g: dict = {}
            with swallow_io():
                exec(solution, g)
            fn = g[entry_point]
            for inp, limit in zip(inputs, limits):
                try:
                    with time_limit(limit):
                        with swallow_io():
                            out = fn(*inp)
                    if not_none and type(out) is not bool:
                        out = out is not None
                    results.append(("ok", _plain(out)))
                except BaseException as exc:  # noqa: BLE001
                    kind = "timeout" if type(exc).__name__ == "TimeoutException" else "error"
                    results.append((kind, None))
        except BaseException:  # noqa: BLE001 - solution failed to load
            pass
        shutil.rmtree, os.rmdir, os.chdir = rmtree, rmdir, chdir
        try:
            conn.send(results)
        except BaseException:  # noqa: BLE001 - e.g. unpicklable; parent sees no data
            pass
        conn.close()


def _matches(task: Task, inp, out, exp, atol: float) -> bool:
    # Same decision procedure as evalplus.eval.unsafe_execute, run in the
    # trusted parent on plain data.
    ep = task.entry_point
    if task.benchmark == "humaneval" and ep == "find_zero":
        try:
            return type(out) in (int, float) and abs(_poly(*inp, out)) <= atol
        except Exception:  # noqa: BLE001
            return False
    exact = type(out) is type(exp) and out == exp or (
        type(out) in (int, float) and type(exp) in (int, float) and out == exp
    )
    if task.benchmark == "mbpp":
        if ep == "are_equivalent":
            exact = True
        elif ep == "sum_div":
            exact = exact or out == 0
        elif ep == "surface_Area":
            exact = exact or (type(out) in (int, float) and abs(out - _surface_Area(*inp)) <= atol)
        elif ep == "digit_distance_nums":
            exact = exact or out == _digit_distance_nums(*inp)
        elif ep in MBPP_OUTPUT_SET_EQ_TASKS:
            try:
                exact = set(out) == set(exp)
            except TypeError:
                exact = False
    if exact:
        return True
    if atol == 0 and is_floats(exp):
        atol = 1e-6
    if atol == 0 or type(out) is not type(exp):
        return False
    if isinstance(exp, (list, tuple)) and len(out) != len(exp):
        return False
    try:
        return bool(np.allclose(out, exp, rtol=1e-07, atol=atol))
    except Exception:  # noqa: BLE001
        return False


def run_hardened(task: Task, solution: str, min_limit: float = 1.0, factor: float = 4.0) -> str:
    inputs = list(task.base_input) + list(task.plus_input)
    expected = list(task.expected_base) + list(task.expected_plus)
    ref = list(task.base_time) + list(task.plus_time)
    limits = [max(min_limit, factor * t) for t in ref]
    parent, child = multiprocessing.Pipe(duplex=False)
    fields = (task.entry_point, task.entry_point in MBPP_OUTPUT_NOT_NONE_TASKS and task.benchmark == "mbpp")
    p = multiprocessing.Process(target=_child, args=(fields, solution, inputs, limits, child))
    p.start()
    child.close()
    budget = min(120.0, sum(limits)) + 2
    results = parent.recv() if parent.poll(budget) else None
    p.join(timeout=1)
    if p.is_alive():
        p.kill()
        p.join()
    if results is None:
        return TIMEOUT
    if len(results) != len(inputs):
        return FAIL
    saw_timeout = False
    for inp, (kind, out), exp in zip(inputs, results, expected):
        if kind == "timeout":
            saw_timeout = True
            continue
        # expected comes from the trusted reference; normalize it the same way
        if kind != "ok" or not _matches(task, inp, out, _plain_or_raw(exp), task.atol):
            return FAIL
    return TIMEOUT if saw_timeout else PASS
