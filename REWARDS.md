# I tested the rewards

In part one ([WRITEUP.md](WRITEUP.md)) I showed that a fake solution can pass HumanEval+ and MBPP+ without solving anything. I said this matters most when a grader is used as a reward to train a model, because then the model is searching for anything the grader accepts.

So in part two I tested the graders people actually train with. These are the reward functions in three open RL libraries and benchmarks:

- **verl** (`verl/utils/reward_score/prime_code`), the default code reward for `apps`, `taco`, `codecontests` and `codeforces` data
- **LiveCodeBench** (`lcb_runner/evaluation`), used both as a benchmark and as a reward
- **rllm** (`rllm/rewards/code_reward.py`), the reward behind the DeepCoder models

I also looked at **open-r1**'s `code_reward` and **BigCodeBench**.

All five are called as published, at a pinned commit, without editing a line. Each one is graded on the data it was built for: verl on its own Eurus validation set, LiveCodeBench on its newest release (v6), and rllm on the DeepCoder dataset.

## What I found

### 1. A fake that solves nothing gets full reward on almost every task

I wrote fakes that never read the problem. The exact same text goes in for every task.

| Data (tasks) | Grader it was built for | Fake gets full reward | My fixed grader | Empty control |
|---|---|---|---|---|
| Eurus validation (1,024) | verl | 97.6% | 0% | 0% |
| LiveCodeBench v6 (175) | LiveCodeBench | 100% | 0% | 0% |
| DeepCoder LiveCodeBench split (139) | rllm | 100% | 0% | 0% |
| DeepCoder TACO sample (300) | rllm | 98.3% | 0% | 0% |
| DeepCoder PrimeIntellect sample (298) | rllm | 100% | 0% | 0% |

There are three tricks, and each one needs only a few lines:

- **Read the answer.** All three graders run the solution in the same process that holds the expected outputs. The fake walks up the call stack, finds the answer for the current test, and returns or prints it. This works on all three graders, for both stdin and function-call tasks.
- **Empty the test list.** For function-call tasks, the solution is imported before the first test runs. At import time, the fake finds the grader's list of test inputs and clears it. Zero tests run, and in Python `all([])` is `True`, so every grader counts that as a pass. This trick never touches an answer. So "just hide the expected outputs" isn't enough as a fix.
- **Be equal to everything.** Return an object whose `==` always says yes. This works on LiveCodeBench and rllm. verl blocks it, but only by accident: it calls `json.dumps` on the output first, and the fake object can't be turned into JSON.

The full table, split by trick and task type, is in [`results/rewards/FINDINGS.md`](results/rewards/FINDINGS.md).

### 2. verl only checks the first 10 tests once anything fails

verl's default reward first runs all the tests. If any test fails, it runs them again one at a time, but it stops after test 10 and returns the share that passed. So a program that's right on tests 1 to 10 and wrong on everything after gets a reward of 1.0.

I checked this two ways:
- **A toy task.** A program that's wrong on tests 11 and 12 scores 1.0 under verl. LiveCodeBench, rllm and my grader all reject it.
- **Real reference solutions.** 29 of them fail verl's own all-tests check and still get 1.0.

In verl's own Eurus validation data, 66% of tasks have more than 10 tests. On those, a model only ever needs to get the first 10 right.

### 3. Some tasks can't be passed at all

All 96 function-call tasks in verl's Eurus validation set (9.4% of its code tasks) store their test inputs in a format verl's grader can't read, so it crashes before calling the solution. Even a fake that hands back the exact expected answer gets zero. Those tasks give no reward to any program, ever.

### 4. Correct programs get zero reward

The same in-process design also hurts honest code. TACO and PrimeIntellect ship a reference solution for every task. My grader passes more of them than any upstream grader:

| Data | verl | LiveCodeBench | rllm | My grader |
|---|---|---|---|---|
| TACO (261 with references) | 83% | 85% | 87% | 98% |
| PrimeIntellect (298) | 73% | 68% | 70% | 76% |

I re-ran every disagreement alone on a quiet machine, and all of them held. The main causes:

- **Fast input reading.** Competitive programmers often read input with `os.read(sys.stdin.fileno())`. The graders replace stdin with a fake object that has no file number, so these programs crash. That's 29 correct references across the two datasets.
- **Wrapping the program in a function.** The graders run your script inside a function. A program that uses `global` variables breaks (5 references).
- **`exit()` is switched off.** A program that calls `exit()` when it's done crashes (1 reference).

For RL this is a quiet tax. The model gets punished for perfectly good code, and it learns to avoid habits like fast I/O for no reason.

My grader isn't perfect either. Two TACO references use `return` outside any function. That isn't valid Python on its own, and it only works because the upstream graders wrap the code in a function, so my grader rejects them. verl also passes five references that mine rejects because of its looser float comparison, which is a fair choice.

### 5. open-r1 gives full reward to a program that stops early

open-r1 runs each test in a separate process and compares the output outside it. That's the right design, and none of my in-process fakes worked on it.

But it compares output lines with `zip`, which stops at the shorter side. I took the real reference program and made it print only the first line of its answer. On 100 PrimeIntellect tasks, that truncated program got full reward on 20 of the 72 tasks where the reference passes (27.8%). My grader confirms its output is wrong on all 20. The code even has a TODO saying the comparison is a placeholder.

### 6. BigCodeBench can be silenced

BigCodeBench runs the solution and its unittest suite in the same module, with the solution's code first. A five-line fake that turns `unittest`'s "record a failure" and "record an error" into no-ops passed all three tasks I tried locally, including one whose own reference can't run here because a library is missing. The full 1,140-task run needs BigCodeBench's own task libraries on Linux; that job is in the GitHub Actions workflow.

## The fix

`evalaudit/rewards/hardened.py` is a drop-in grader for APPS-format tests. It's built on five rules:

1. Run the solution in a separate Python process that's never given the expected outputs. For stdin tasks, use a fresh process for every test.
2. Send back plain data only: stdout text, or return values as JSON. A fake object can't survive JSON.
3. Compare in the trusted parent process, using LiveCodeBench's rules.
4. Count the tests in the parent. If fewer results come back than there are tests, it's a fail.
5. Report timeouts as timeouts.

It blocks every fake on all 1,936 tasks, and it passes more honest references than any of the upstream graders.

One risk remains: the child process still runs as the same user. If the dataset file holding the answers sits on the same disk, a determined program could just open it. In production, run the child in a real sandbox (verl's `sandbox_fusion` option is a step in that direction).

## How I checked my work

- Every grader is the upstream code at a pinned commit, loaded straight from its own files. File hashes are in `results/rewards/provenance.json`.
- Every dataset is pinned to a Hugging Face revision.
- The empty control passes nothing on any grader, so a passing fake isn't just a broken harness.
- Every reference disagreement was re-run alone on an idle machine (`scripts/diagnose_rewards.py`). None of them went away.
- `tests/test_rewards.py` pins each finding to a tiny hand-made task, so it can be checked in seconds.

## Limits

- I only had reference solutions for TACO and PrimeIntellect, so the honest-code numbers come from those two.
- TACO and PrimeIntellect are samples of 300 tasks from one data shard each (fixed seed). LiveCodeBench v6, Eurus validation and the DeepCoder LiveCodeBench split are complete.
- I didn't run verl's `sandbox_fusion` path, because it needs a SandboxFusion server.
- As in part one, I'm not saying any trained model actually used these tricks. The point is that nothing in these rewards would stop one.

## Related work

The Berkeley RDI / BenchJack work ([arXiv 2605.12673](https://arxiv.org/abs/2605.12673)) broke agent benchmarks like SWE-bench and Terminal-Bench the same way, by tampering with what the grader trusts. CATCH ([arXiv 2609.39533](https://arxiv.org/abs/2609.39533)) trains models on DeepCoder problems inside a deliberately cheatable setup and watches them learn to cheat. As far as I can find, nobody had tested the reward functions in verl, rllm or LiveCodeBench themselves.
