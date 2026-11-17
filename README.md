# evalaudit: I test the tests

Code benchmarks score models with graders. `evalaudit` checks the graders themselves: whether they can be cheated, how many wrong solutions they let through, whether they give the same verdict twice, and how big a score gap they can actually resolve.

Targets: **HumanEval** (164 tasks) and **MBPP** (378 tasks). For each, it audits the original assert-based tests and the graders in [EvalPlus](https://github.com/evalplus/evalplus) 0.3.1 (latest PyPI release). EvalPlus's grader is imported and called unmodified.

## Headline results

| # | Finding | Number |
|---|---|---|
| 1 | A solution that **never attempts the task** passes EvalPlus's grader, measured end to end through `evalplus.evaluate` | **pass@1 0.994** HumanEval+ · **1.000** MBPP+ (control: 0.000) |
| 2 | Same cheater vs. the original HumanEval / MBPP asserts | **95.7%** (91.5–97.9) · **93.9%** (91.0–95.9) |
| 3 | Tasks whose shipped tests accept a **provably wrong** one-edit solution | **22.0%** of HumanEval (16.3–28.9) · **18.3%** of MBPP (14.7–22.5) |
| 4 | Correct reference solutions graded **wrong** under CPU load (timeouts reported as `fail`) | 39 `fail` verdicts across 10 tasks (5 runs each); **all 10 pass on an idle machine** |
| 5 | HumanEval/32 can't be passed in the EvalPlus 0.3.1 release, and its reference solution fails the `find_zero` oracle on 6 plus inputs even with master's fix | reference solution graded `fail` |
| 6 | Degenerate MBPP+ plus suites: 1 empty, 6 where every expected output is the same value | a one-line constant function passes them |
| 7 | Smallest gap you can trust on HumanEval (164 tasks) at an 80% pass rate | **±12.4 points** |
| Fix | `hardened.py` grader | cheaters **0/542**; references 541/542 pass (the exception is #5) |

95% Wilson intervals are in parentheses.

Full tables: [`results/FINDINGS.md`](results/FINDINGS.md). Write-up: [`WRITEUP.md`](WRITEUP.md). Reported upstream: [evalplus#333](https://github.com/evalplus/evalplus/issues/333), [#334](https://github.com/evalplus/evalplus/issues/334), [#335](https://github.com/evalplus/evalplus/issues/335), [#336](https://github.com/evalplus/evalplus/issues/336).

## What it does

| Experiment | Question | Method |
|---|---|---|
| **Cheaters** (`exploits.py`) | Can a solution that never attempts the task pass? | Four non-solving solutions: `null` (control), `always_equal` (an object whose `__eq__` is always True), `frame_peek` (reads the grader's `expected[i]` off the call stack), `hybrid` |
| **Grader mutation** (`mutation.py`) | How many *wrong* solutions does the grader accept? | One-edit AST mutants of the reference solution, limited to the entry function. A mutant is **confirmed wrong** only if it returns a wrong value (or raises) on one of EvalPlus's ~1,000 inputs. Timeouts and equivalent mutants are never counted. |
| **Reliability** (`audit.py`) | Does the reference solution pass, every time? | Reference solutions graded 5× on an oversubscribed machine (2 workers per core), then re-graded on an idle machine to separate broken tasks from load sensitivity |
| **Degenerate suites** (`report.py`) | Is a suite empty, or does a constant function pass it? | Static scan of expected outputs |
| **Power** (`stats.py`) | How big a pass-rate gap is real? | Minimum detectable difference, two-proportion z-test, α=0.05, power 0.8 |
| **Fix** (`hardened.py`) | Does a different design close the holes? | Expected outputs never enter the untrusted process; the child returns plain data only; the trusted parent compares; timeouts are reported as `timeout`, not `fail` |

## Run it

```bash
uv venv && uv pip install -e ".[dev]"
evalaudit all --workers 8          # ~4 min on an 8-core laptop; writes results/
pytest -q                           # unit + integration tests
python scripts/verify_official_cli.py   # cheaters through EvalPlus's own `evaluate` entry point
python scripts/diagnose.py humaneval:HumanEval/32:plus   # re-grade one task on an idle machine
```

All experiments are deterministic (seeded mutant sampling). Benchmarks download on first run via EvalPlus's loaders.

## Scope and honesty notes

- These are function-level Python benchmarks. Agentic benchmarks with repository-level graders are the next target; the harness (sandbox → grader → oracle → statistics) carries over.
- The `original` grader is a faithful re-implementation of `openai/human-eval`'s `check_correctness`, built from the same guard helpers EvalPlus vendors. For MBPP it uses the `assertion` field EvalPlus ships, plus the original `test_imports`.
- Run on macOS (8 cores) and **reproduced on Linux** in CI (`.github/workflows/audit.yml`, results in `results/linux/`). On macOS only, `EVALPLUS_MAX_MEMORY_BYTES=-1` is set, which is EvalPlus's documented opt-out, because macOS rejects `RLIMIT_AS`.
- The cheaters are a grader-design finding, not a claim that any published model score was obtained this way. They matter because an RL policy optimizing against such a grader can find them.

## License

MIT
