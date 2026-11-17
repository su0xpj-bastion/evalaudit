# Draft upstream reports for evalplus/evalplus

Filed 2026-11-17 after reproducing on Linux. These are the original drafts; the filed issues carry final numbers.

| # | Issue |
|---|---|
| 1 | Untrusted solution reads `expected` / controls `==`: https://github.com/evalplus/evalplus/issues/333 |
| 2 | HumanEval/32 `find_zero`: https://github.com/evalplus/evalplus/issues/334 |
| 3 | Timeouts reported as wrong answers: https://github.com/evalplus/evalplus/issues/335 |
| 4 | Degenerate MBPP+ plus suites: https://github.com/evalplus/evalplus/issues/336 |

---

## Issue 1: Untrusted solution can read expected outputs and control comparison (pass@1 ≈ 1.0 without solving)

**Version:** evalplus 0.3.1 (PyPI) and current `master` (`evalplus/eval/__init__.py::unsafe_execute`).

**Summary.** `unsafe_execute` runs the candidate solution in the same process that holds `expected`, and it decides correctness with `out == exp`. A solution that never attempts the task can:

1. return an object whose `__eq__` always returns True (`exact_match = out == exp` evaluates to True, and the `np.allclose` path is skipped), or
2. read `expected[i]` from the caller frame with `sys._getframe(1).f_locals`, which `reliability_guard` does not block.

**Repro.** `python scripts/verify_official_cli.py` in https://github.com/su0xpj-bastion/evalaudit feeds a non-solving `hybrid` solution to `evalplus.evaluate`:

| | HumanEval base | HumanEval+ | MBPP base | MBPP+ |
|---|---|---|---|---|
| `null` (returns None) | 0.000 | 0.000 | 0.000 | 0.000 |
| `hybrid` cheater | 0.994 | 0.994 | 1.000 | 1.000 |

**Why it matters.** Normal leaderboard use isn't adversarial. But EvalPlus-style graders are now used as **RL reward functions**, where the policy is optimizing against the grader. Both patterns are within reach of a policy (`__eq__` overrides are a known reward-hacking behavior).

**Suggested fix.** Keep `expected` out of the untrusted process. The child returns outputs as plain data only (exact builtin types, checked recursively; reject anything else), and the trusted parent runs the existing comparison logic. A reference implementation with tests is in `evalaudit/hardened.py`: it rejects all three cheaters, and reference solutions still pass.

---

## Issue 2: HumanEval/32 (`find_zero`) is unpassable in the 0.3.1 release

In 0.3.1, the `find_zero` special oracle runs `continue` before `details[i] = True` and `progress.value += 1`. `details` is therefore truncated to empty, and every solution, including the reference, is graded FAIL. `master` already fixes this (it sets both before `continue`), but the fix isn't in a PyPI release. Anyone running `pip install evalplus` scores HumanEval/32 as 0 for every model.

**Second problem, still present on master:** with the bookkeeping fixed, the reference `find_zero` still fails the oracle `abs(_poly(xs, x)) <= atol` (atol 1e-4) on 6 of 788 plus inputs (dataset v0.1.10, unchanged on master). The bisection doesn't converge for large coefficients. Worst cases:

| plus input index | coefficients (abridged) | |poly(reference root)| |
|---|---|---|
| 277 | `[9, -6, 20999, ...]` | 1.1e8 |
| 750 | `[-1663750000, 10, 10, -1663750001, ...]` | 2.8e20 |
| 716 | `[-300, 21000, -630001, 9450000, ...]` | 1.8e3 |

**Ask:**
1. Cut a release that includes the bookkeeping fix.
2. Either drop these inputs or replace the reference with one that meets the oracle on them.

---

## Issue 3: Per-input time limits turn machine load into wrong answers

Under 2× CPU oversubscription, reference solutions for 10 HumanEval+/MBPP+ tasks (HumanEval 83, 139; MBPP 255, 271, 389, 392, 583, 599, 603, 630) were graded **FAIL** (not TIMEOUT) in 39 of 50 runs. On an idle machine all 10 pass every time. A `TimeoutException` inside the per-input loop is caught by the same `except BaseException` that handles wrong answers.

**Suggested fix:** report per-input timeouts as `timeout`, so harnesses can retry infrastructure noise instead of scoring it. Optionally, calibrate `ref_time` on the evaluating machine.

---

## Issue 4: Degenerate MBPP+ plus suites

- `Mbpp/793` plus suite has 0 inputs.
- Six tasks have plus suites whose expected outputs are all identical. For example, all 101 `Mbpp/787` plus inputs expect `False`, so a function returning `None` passes the plus suite. The base suite still discriminates, so the end-to-end MBPP+ score is unaffected, but the "plus" rigor on these tasks is nil.
- `Mbpp/120`'s shipped `assertion` field uses `math.isclose` without `import math` (the original MBPP `test_list` uses `==`).
