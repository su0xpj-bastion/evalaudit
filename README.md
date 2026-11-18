# evalaudit: I test the tests

Code benchmarks score models by running their code against tests. This project checks the tests. Can they be cheated? Do they let wrong answers through? Do they give the same result twice?

It covers HumanEval (164 tasks) and MBPP (378 tasks), using both the original tests and [EvalPlus](https://github.com/evalplus/evalplus) 0.3.1, the latest release. EvalPlus's grader is used exactly as published.

## What I found

| What | Result |
|---|---|
| A fake solution that never solves anything, scored by EvalPlus's own `evaluate` | 0.994 on HumanEval+, 1.000 on MBPP+ (empty control: 0.000) |
| The same fake against the original tests | passes 95.7% of HumanEval, 93.9% of MBPP |
| Tasks whose tests accept an answer I can prove wrong | 22.0% of HumanEval, 18.3% of MBPP |
| Correct answers marked wrong on a busy machine | 10 tasks, 39 of 50 runs; all pass on a quiet machine |
| HumanEval/32 | can't be passed in the current release, and the official solution misses 6 test inputs even after the fix |
| MBPP+ extra tests that don't test anything | 1 empty, 6 passed by a function that returns a constant |
| Smallest HumanEval gap you can trust (at 80% pass rate) | about 12 points |
| My fixed grader | blocks every fake (0 of 542); 541 of 542 official solutions pass |

Numbers in parentheses in the full tables are 95% confidence intervals.

The full write-up is in [`WRITEUP.md`](WRITEUP.md), and every table is in [`results/FINDINGS.md`](results/FINDINGS.md). I reported all four problems upstream: [#333](https://github.com/evalplus/evalplus/issues/333), [#334](https://github.com/evalplus/evalplus/issues/334), [#335](https://github.com/evalplus/evalplus/issues/335), [#336](https://github.com/evalplus/evalplus/issues/336).

## Part two: RL code rewards

The same problems show up in the reward functions people use to train coding models. I called verl, LiveCodeBench and rllm unmodified, each on its own data:

| What | Result |
|---|---|
| Fake that solves nothing (verl on Eurus / LiveCodeBench v6 / rllm on DeepCoder) | 97.6% / 100% / 98–100% full reward; empty control 0% |
| Empty the test list before it runs | passes every function-call task on all three (`all([])` is True) |
| verl's default reward | checks only the first 10 tests once one fails; 66% of Eurus tasks have more |
| Eurus function-call tasks | 96 of 1,024 can't be passed by any program |
| Correct programs that use fast stdin I/O | zero reward on all three graders (29 references) |
| open-r1 `code_reward` | full reward for a program that prints only the first line (20 of 72 tasks) |
| My fixed reward | 0 fakes pass on 1,936 tasks; passes more honest references than any upstream grader |

The write-up is [`REWARDS.md`](REWARDS.md) and the tables are in [`results/rewards/FINDINGS.md`](results/rewards/FINDINGS.md). Run it with `python -m evalaudit.rewards all` (needs `pip install -e ".[rewards]"`).

## How it works

- **Fake solutions** (`exploits.py`): four solutions that never read the problem. One returns `None` as a control. One returns an object that's "equal" to anything. One reads the expected answer out of the grader's memory. One combines the last two.
- **Small changes** (`mutation.py`): take the official solution, change one thing (`<` to `<=`, `1` to `2`, `+` to `-`), and see if the tests notice. A change only counts as wrong if it gives a wrong answer on a real input. Timeouts don't count.
- **Repeat runs** (`audit.py`): grade the official solutions several times on a busy machine, then re-check anything that failed on a quiet one.
- **Weak test scan** (`report.py`): look for test suites that are empty or where every expected answer is the same.
- **Score gaps** (`stats.py`): how far apart two models must be before the difference is real.
- **The fix** (`hardened.py`): run the code in a process that never sees the answers, send back plain data only, compare in a trusted process, and report timeouts as timeouts.

## Run it

```bash
uv venv && uv pip install -e ".[dev]"
evalaudit all --workers 8          # about 5 minutes on an 8-core laptop; writes results/
pytest -q
python scripts/verify_official_cli.py   # run the fakes through EvalPlus's own evaluate command
python scripts/diagnose.py humaneval:HumanEval/32:plus   # re-check one task on a quiet machine
```

Runs are repeatable (the small changes use a fixed seed). The benchmarks download the first time you run it.

## Good to know

- These are small, single-function Python tasks. Agent benchmarks that grade a whole repo are next.
- The "original tests" grader rebuilds what `openai/human-eval` does, using the same safety helpers EvalPlus uses. For MBPP it uses the tests EvalPlus ships plus the original imports.
- I ran it on macOS and again on Linux through GitHub Actions (`.github/workflows/audit.yml`, results in `results/linux/`). The results match. macOS doesn't allow EvalPlus's memory limit, so it's turned off there with EvalPlus's own setting. On Linux it stays on.
- I'm not saying any published score was faked. This is about how the grader is built, which matters most when it's used to train models.

## License

MIT
