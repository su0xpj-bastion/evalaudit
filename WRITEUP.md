# I tested the tests: auditing the graders behind HumanEval and MBPP

## TL;DR

I applied QA techniques to the graders of two widely used code benchmarks, HumanEval (164 tasks) and MBPP (378 tasks): adversarial inputs, mutation testing, repeatability under load, static test-data checks, and power analysis. I audited both the original assert-based tests and EvalPlus 0.3.1, the current PyPI release and the de facto rigorous grader.

1. **A solution that never attempts the task scores pass@1 0.994 on HumanEval+ and 1.000 on MBPP+**, measured end to end through EvalPlus's own `evaluate` entry point. Two lines of attack are enough: an object whose `__eq__` always returns True, and reading `expected[i]` off the call stack. Both work because the grader compares answers inside the same process it is grading.
2. **About 1 in 5 tasks accepts a provably wrong solution.** In 22.0% of HumanEval tasks and 18.3% of MBPP tasks, the shipped tests pass a one-edit mutant of the reference that returns a wrong value on an EvalPlus input. One example: an `is_prime` that says 2 isn't prime passes all 13 original HumanEval/31 asserts.
3. **Load changes verdicts.** On a busy machine, correct reference solutions for 10 tasks were graded `fail` in 39 of 50 runs, because timeouts are reported as wrong answers. On an idle machine all 10 pass every time.
4. **Broken and degenerate tasks.** HumanEval/32 can't be passed in the released EvalPlus, and its reference solution fails the oracle on 6 inputs even with the upstream fix. One MBPP+ plus suite is empty, and 6 others pass a constant function.
5. **A fix.** A hardened grader keeps expected outputs out of the untrusted process. It rejects 100% of cheaters (0/542), and every reference solution passes except the one broken task.

## Why audit graders

Every model comparison assumes the grader is right. A benchmark grader is software, and nobody tests it the way production code gets tested. That gap matters more now: the same graders increasingly serve as reward functions in RL, where the policy actively searches for whatever the grader accepts. A grader that can be gamed doesn't just mis-score a leaderboard; it trains the model to game it.

## Method

Four graders are compared:

| Grader | What it is |
|---|---|
| original asserts | Faithful re-implementation of `openai/human-eval`'s `check_correctness`: one program of `solution + test + check(entry)`, run in a guarded child process; PASS if nothing raises. For MBPP: the shipped `assertion` field plus the original `test_imports`. |
| EvalPlus base / plus | `evalplus.eval.untrusted_check`, imported and called **unmodified**. |
| hardened (fix) | Described below. |

Five experiments:

- **Cheaters.** Four solutions that never read the task: `null` (control), `always_equal`, `frame_peek`, and `hybrid`. Any PASS is a false pass by construction.
- **Grader mutation.** Up to 25 one-edit AST mutants per task (comparison flips, +/- swaps, constant ±1, and/or swaps, dropped `not`), limited to the entry function and seeded for determinism. That gave 3,644 mutants. A mutant counts as **confirmed wrong** only if, on EvalPlus's base+plus inputs (about 1,000 per task), it returns a value that disagrees with ground truth or raises. Timeouts don't count: a first version used EvalPlus's own verdict here, and on Linux it marked two slow but correct Mbpp/583 mutants as wrong (finding 3 is the reason). Mutants that pass every suite may be equivalent and are never counted.
- **Reliability.** Every reference solution, under every grader, 5 times, with 2 workers per core to simulate a busy CI box. Every non-pass was then re-graded on an idle machine to separate broken tasks from load sensitivity.
- **Degenerate suites.** A static scan for empty suites and suites where every expected output is the same value. Each hit was then confirmed by running a constant-returning function.
- **Power.** The minimum detectable difference between two models' pass rates (two-proportion z-test, α=0.05, power 0.80).

## Findings

### 1. Non-solving cheaters

| Benchmark | Cheater | original asserts | EvalPlus base | EvalPlus plus | hardened |
|---|---|---|---|---|---|
| HumanEval | `null` (control) | 0.0% | 0.0% | 0.0% | 0.0% |
| HumanEval | `hybrid` | **95.7%** (91.5–97.9) | **99.4%** | **99.4%** | 0.0% (0.0–2.3) |
| MBPP | `null` (control) | 0.0% | 0.0% | 0.5% | 0.0% |
| MBPP | `hybrid` | **93.9%** (91.0–95.9) | **100.0%** | **100.0%** | 0.0% (0.0–1.0) |

End to end through `evalplus.evaluate`: the `hybrid` cheater reports pass@1 = 0.994 (HumanEval and HumanEval+) and 1.000 (MBPP and MBPP+). The `null` control reports 0.000 on all four.

**Why the graders fall:**
- `always_equal` beats any `assert out == expected`. Python asks the left operand first, and when the left operand is a builtin it falls back to the reflected `__eq__`.
- `frame_peek` beats EvalPlus specifically. `unsafe_execute` holds `expected` as a local in the frame that calls the solution, and `reliability_guard` doesn't block `sys._getframe`. The cheater returns the grader's own answer, with the right type, so even the float path with type checks passes.

**The few tasks that resist:**
- `always_equal` fails on tests that call `math.isclose` or use `is`.
- `frame_peek` fails only on HumanEval/32, which nothing can pass (see finding 4).

The `null` control's 2 passes on MBPP plus are the degenerate suites in finding 5.

### 2. Wrong solutions the graders accept

| Benchmark | Grader | Mutants accepted | Confirmed wrong | Tasks accepting a confirmed-wrong mutant |
|---|---|---|---|---|
| HumanEval | original asserts | 205 / 1,685 | 98 | **36 / 164 = 22.0%** (16.3–28.9) |
| HumanEval | EvalPlus base | 202 / 1,685 | 94 | 35 / 164 = 21.3% (15.8–28.2) |
| MBPP | original asserts | 394 / 1,959 | 218 | **69 / 378 = 18.3%** (14.7–22.5) |
| MBPP | EvalPlus base | 394 / 1,959 | 218 | 69 / 378 = 18.3% (14.7–22.5) |

Examples, each passing the original asserts and EvalPlus base:

- **HumanEval/31** `is_prime`: `if n <= 1` → `if n <= 2`, so 2 is reported as not prime. None of the 13 original asserts calls `is_prime(2)`.
- **HumanEval/19** `sort_numbers`: `'eight': 8` → `'eight': 7`.
- **HumanEval/0** `has_close_elements`: `<` → `<=`, so pairs exactly `threshold` apart count as close.
- **HumanEval/20** `find_closest_elements`: `<` → `<=` changes which pair is chosen among ties.

This confirms, with a different method, EvalPlus's original motivation: the base tests are thin. It also gives a per-task kill list (in `results/summary.json`) that a benchmark maintainer could act on directly.

### 3. Verdicts depend on machine load

| Grader | References graded non-pass under 2× load (5 runs) | Reported as `fail` / `timeout` |
|---|---|---|
| EvalPlus plus (HumanEval + MBPP) | 10 tasks, excluding HumanEval/32 | 39 / 0 |
| hardened | same tasks | 0 / 41 (plus the 5 HumanEval/32 fails) |

All 10 tasks (HumanEval 83, 139; MBPP 255, 271, 389, 392, 583, 599, 603, 630) pass every time on an idle machine. EvalPlus sets per-input limits at 4× a reference time measured elsewhere, and catches the resulting `TimeoutException` with the same handler as a wrong answer. A model's score therefore depends on what else the CI box is running, and the result can't be told apart from a wrong answer.

### 4. HumanEval/32 is broken twice

- **In the 0.3.1 release** (latest on PyPI), the `find_zero` special oracle runs `continue` before recording the pass, so every solution, including the reference, is graded FAIL. Master fixes the bookkeeping, but that fix hasn't been released.
- **Even with the fix,** the reference `find_zero` fails the oracle `|poly(x)| ≤ 1e-4` on 6 of 788 plus inputs, by up to 2.8e20 on one input with ~1.7e9 coefficients. Bisection doesn't converge there. The dataset is v0.1.10 on both PyPI and master.

### 5. Degenerate MBPP+ plus suites

- `Mbpp/793`: the plus suite has **0 inputs**.
- `Mbpp/223, 285, 635, 734, 760, 787`: every plus expected output is identical (`False`, `[]` or `0`). A one-line constant function passes all six plus suites (confirmed by running one); only the 3–4-assert base suite catches it.
- `Mbpp/120`: the shipped `assertion` field calls `math.isclose` without `import math`, so the reference fails it.

The end-to-end MBPP+ score requires base and plus to both pass, so headline numbers survive. The "plus" rigor on these tasks, though, is nil.

### 6. How big a gap is real?

| Benchmark | Tasks | MDE at 50% pass | at 80% | at 90% |
|---|---|---|---|---|
| HumanEval | 164 | ±15.5 pts | ±12.4 pts | ±9.3 pts |
| MBPP | 378 | ±10.2 pts | ±8.2 pts | ±6.1 pts |

This is conservative because it ignores pairing; a paired test on the same tasks does somewhat better. Either way, single-digit HumanEval gaps between two models are not evidence on their own.

## The fix

Both cheaters work for the same reason: the grader trusts the process it is grading. `hardened.py` follows these rules:

1. **Expected outputs never enter the untrusted process.**
2. **The child returns plain data only.** Outputs are rebuilt recursively from exact builtin types using the base type's own methods. Subclasses such as `collections.Counter` become a plain `dict`, so any custom `__eq__` is stripped. Anything else is rejected.
3. **The trusted parent compares,** using EvalPlus's decision procedure, special oracles included.
4. **Per-input timeouts are reported as `timeout`, not `fail`.**

| | Result |
|---|---|
| Cheaters (4 kinds × 542 tasks, plus a dict-subclass `__eq__` cheater) | **0 passes** |
| Reference solutions, idle machine | **541 / 542 pass**; the exception is HumanEval/32 (finding 4) |
| Load noise | Reported as `timeout`, so it can be retried |

The cost is one extra pickle round-trip per task.

## What I'd do next

1. **Agentic benchmarks.** Repository-level graders (SWE-style) have a larger attack surface: the agent can edit tests, conftest files, and CI config. The harness carries over (sandbox, grader, oracle, statistics), with test-tamper detection added.
2. **Mutation score as a release gate for new benchmarks.** Require each task to kill a minimum share of non-equivalent mutants before it ships.
3. **Report scores with intervals** and the benchmark's minimum detectable difference.

## Limitations

- Function-level Python benchmarks only.
- "Confirmed wrong" relies on EvalPlus's plus-suite ground truth, which is itself imperfect (finding 4).
- Primary run: macOS, 8 cores, Python 3.14. RLIMIT_AS is disabled through EvalPlus's documented opt-out because macOS rejects it.
- **Reproduced on Linux** (GitHub Actions ubuntu-latest, 4 cores, Python 3.12, EvalPlus's 4 GB RLIMIT_AS sandbox on), results in `results/linux/`. Cheater rates and official pass@1, mutation results, HumanEval/32, the degenerate suites, and the hardened grader's verdicts are identical on both. Load-induced `fail` verdicts reproduce too, on a partly different set of tasks, as expected for a timing effect.
- The cheaters show a grader design flaw. I don't claim any published score was obtained this way.

Reproduce everything with `evalaudit all` (about 5 minutes) and `python scripts/verify_official_cli.py`.
