# I tested the tests

I spent ten years in QA. One habit sticks: before you trust a result, you check the thing that produced it.

Code benchmarks like HumanEval and MBPP score models by running their code against tests. Everyone compares models on these scores. But the graders are software too, and I couldn't find anyone testing them the way we test production code. So I did.

I looked at two benchmarks: HumanEval (164 tasks) and MBPP (378 tasks). For each one I checked the original tests and EvalPlus 0.3.1, the stricter grader most people use today.

## What I found

### 1. You can pass without solving anything

I wrote a fake solution that never looks at the problem. It just returns an object that says "yes, I'm equal" to whatever it's compared with. A second version reaches back into the grader's memory and returns the answer the grader is about to check against.

I ran it through EvalPlus's own `evaluate` command, the same way anyone would submit a model:

| | HumanEval+ | MBPP+ |
|---|---|---|
| Fake solution | 0.994 | 1.000 |
| Empty solution (control) | 0.000 | 0.000 |

The original HumanEval tests let the fake pass 95.7% of the time, and MBPP's let it pass 93.9%.

The cause is simple. EvalPlus runs your code and checks your answer in the same process. Your code can change how the check behaves, or read the expected answer before it's used.

Does this matter? For a normal leaderboard, probably not. Nobody submits a fake on purpose. But these graders are now used to train models with reinforcement learning, and there the model is actively searching for anything the grader will accept. A grader you can fool teaches the model to fool it.

### 2. About one task in five accepts a wrong answer

I took each reference solution and made one tiny change at a time: flip `<` to `<=`, change `1` to `2`, swap `+` and `-`. Then I checked which broken versions the tests still accept. I only counted a version as wrong if I could show it giving a wrong answer on a real input.

- HumanEval: 36 of 164 tasks (22.0%) accept a wrong answer.
- MBPP: 69 of 378 tasks (18.3%) accept a wrong answer.

My favorite example is HumanEval/31, which asks if a number is prime. I changed `n <= 1` to `n <= 2`, so the function now says 2 is not prime. It still passes all 13 original tests, because none of them checks 2.

### 3. A busy machine turns right answers into wrong ones

I graded the benchmark's own correct solutions over and over on a loaded machine. Ten tasks got marked wrong at least once: 39 times out of 50 runs. On a quiet machine all ten pass every time.

EvalPlus sets a time limit for each test input. When a slow run hits that limit, it gets recorded as a wrong answer, not as a timeout. So your score can depend on what else your CI box is doing that day.

This even fooled my own first version. On Linux, two slow but correct changes to Mbpp/583 came back as "wrong" and inflated my count in finding 2. I fixed it by treating timeouts separately, which is the same fix I'm suggesting upstream.

### 4. One task can't be passed at all

HumanEval/32 asks you to find a root of a polynomial. In the current EvalPlus release, a bookkeeping bug fails every answer, including the official one. That's fixed in their code but not released yet.

Even with the fix, the official solution misses on 6 of the extra test inputs. On one of them it's off by about 2.8 × 10²⁰.

### 5. Some extra tests don't test much

- Mbpp/793 has no extra test inputs at all.
- Six other MBPP tasks have extra tests where every expected answer is the same. A one-line function that always returns `False` (or `[]`, or `0`) passes them.

The smaller base tests still catch these, so overall MBPP+ scores are fine. But the extra tests add nothing on those tasks.

### 6. Small score gaps on HumanEval don't mean much

With only 164 tasks, two models need to differ by about 12 points (at an 80% pass rate) before you can be confident the gap is real. A 3-point lead on HumanEval tells you very little by itself.

## The fix

The cheating and the timeout problem have the same root: the grader trusts the code it's grading. I built a grader with four simple rules:

1. Run the code in a separate process that never sees the expected answers.
2. Send back only plain data, like numbers, strings and lists. Anything fancy gets converted or rejected.
3. Compare answers in the trusted process, using EvalPlus's own rules.
4. Report a timeout as a timeout.

On all 542 tasks it blocks every fake solution. Every official solution still passes except HumanEval/32, which is broken on its own (finding 4).

## How I checked my work

- I used EvalPlus's grader exactly as published. I didn't patch or copy it.
- I ran everything on my Mac and again on Linux through GitHub Actions. All the fixed results match on both. The load results move around a bit, which makes sense for a timing problem.
- Each odd result got a second look by hand. For example, I re-ran each slow task alone on a quiet machine, and I ran a constant function against each weak test suite.
- The whole audit reruns with one command in about five minutes.

I've reported all four problems to the EvalPlus maintainers: [#333](https://github.com/evalplus/evalplus/issues/333), [#334](https://github.com/evalplus/evalplus/issues/334), [#335](https://github.com/evalplus/evalplus/issues/335), [#336](https://github.com/evalplus/evalplus/issues/336).

## Limits

- These are small, single-function Python tasks. Bigger agent benchmarks, where the model edits a whole repo, give it many more ways to cheat (editing the tests, for one). That's where I'm going next.
- To decide a change is wrong, I rely on EvalPlus's expected answers, and finding 4 shows those aren't perfect either.
- I'm not saying any published score was faked. This is about how the grader is built.

## What I'd do next

1. Run the same audit on agent benchmarks that grade whole repositories, with checks for tampered tests.
2. Make "does this task catch small mistakes?" a check every new benchmark task has to pass before it ships.
3. Publish scores with error bars, so a small gap isn't mistaken for a real one.
