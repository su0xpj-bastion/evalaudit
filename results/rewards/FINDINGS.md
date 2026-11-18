# RL code-reward audit: findings

## 1. Fakes that solve nothing

Share of tasks where at least one fake earns the full reward. A fake never reads the problem; the same text is submitted for every task. `null` is the control and should pass nothing.

| Dataset (tasks) | verl `prime_code` | LiveCodeBench | rllm (DeepCoder) | hardened (ours) | null control (all graders) |
|---|---|---|---|---|---|
| eurus (1024) | **999/1024 (98%)** | 904/1024 (88%) | 997/1024 (97%) | 0/1024 (0%) | 0 passes |
| lcb_v6 (175) | 175/175 (100%) | **175/175 (100%)** | 175/175 (100%) | 0/175 (0%) | 0 passes |
| deepcoder_lcb (139) | 139/139 (100%) | 139/139 (100%) | **139/139 (100%)** | 0/139 (0%) | 0 passes |
| deepcoder_taco (300) | 295/300 (98%) | 295/300 (98%) | **295/300 (98%)** | 0/300 (0%) | 0 passes |
| deepcoder_primeintellect (298) | 298/298 (100%) | 298/298 (100%) | **298/298 (100%)** | 0/298 (0%) | 0 passes |

Bold marks the grader each dataset was built for (verl trains on Eurus; DeepCoder trains with rllm).

### By fake and task type

| Dataset | Type | Fake | verl `prime_code` | LiveCodeBench | rllm (DeepCoder) | hardened (ours) |
|---|---|---|---|---|---|---|
| eurus | call | null | 0/96 (0%) | 0/96 (0%) | 0/96 (0%) | 0/96 (0%) |
| eurus | call | always_equal | 0/96 (0%) | 0/96 (0%) | 94/96 (98%) | 0/96 (0%) |
| eurus | call | peek | 0/96 (0%) | 0/96 (0%) | 94/96 (98%) | 0/96 (0%) |
| eurus | call | vanish | 96/96 (100%) | 1/96 (1%) | 94/96 (98%) | 0/96 (0%) |
| eurus | stdio | null | 0/928 (0%) | 0/928 (0%) | 0/928 (0%) | 0/928 (0%) |
| eurus | stdio | peek | 903/928 (97%) | 903/928 (97%) | 903/928 (97%) | 0/928 (0%) |
| lcb_v6 | call | null | 0/63 (0%) | 0/63 (0%) | 0/63 (0%) | 0/63 (0%) |
| lcb_v6 | call | always_equal | 0/63 (0%) | 63/63 (100%) | 63/63 (100%) | 0/63 (0%) |
| lcb_v6 | call | peek | 63/63 (100%) | 63/63 (100%) | 63/63 (100%) | 0/63 (0%) |
| lcb_v6 | call | vanish | 63/63 (100%) | 63/63 (100%) | 63/63 (100%) | 0/63 (0%) |
| lcb_v6 | stdio | null | 0/112 (0%) | 0/112 (0%) | 0/112 (0%) | 0/112 (0%) |
| lcb_v6 | stdio | peek | 112/112 (100%) | 112/112 (100%) | 112/112 (100%) | 0/112 (0%) |
| deepcoder_lcb | call | null | 0/62 (0%) | 0/62 (0%) | 0/62 (0%) | 0/62 (0%) |
| deepcoder_lcb | call | always_equal | 0/62 (0%) | 62/62 (100%) | 62/62 (100%) | 0/62 (0%) |
| deepcoder_lcb | call | peek | 62/62 (100%) | 62/62 (100%) | 62/62 (100%) | 0/62 (0%) |
| deepcoder_lcb | call | vanish | 62/62 (100%) | 62/62 (100%) | 62/62 (100%) | 0/62 (0%) |
| deepcoder_lcb | stdio | null | 0/77 (0%) | 0/77 (0%) | 0/77 (0%) | 0/77 (0%) |
| deepcoder_lcb | stdio | peek | 77/77 (100%) | 77/77 (100%) | 77/77 (100%) | 0/77 (0%) |
| deepcoder_taco | call | null | 0/39 (0%) | 0/39 (0%) | 0/39 (0%) | 0/39 (0%) |
| deepcoder_taco | call | always_equal | 0/39 (0%) | 39/39 (100%) | 39/39 (100%) | 0/39 (0%) |
| deepcoder_taco | call | peek | 39/39 (100%) | 39/39 (100%) | 39/39 (100%) | 0/39 (0%) |
| deepcoder_taco | call | vanish | 39/39 (100%) | 39/39 (100%) | 39/39 (100%) | 0/39 (0%) |
| deepcoder_taco | stdio | null | 0/261 (0%) | 0/261 (0%) | 0/261 (0%) | 0/261 (0%) |
| deepcoder_taco | stdio | peek | 256/261 (98%) | 256/261 (98%) | 256/261 (98%) | 0/261 (0%) |
| deepcoder_primeintellect | stdio | null | 0/298 (0%) | 0/298 (0%) | 0/298 (0%) | 0/298 (0%) |
| deepcoder_primeintellect | stdio | peek | 298/298 (100%) | 298/298 (100%) | 298/298 (100%) | 0/298 (0%) |

## 2. Real solutions: does the fix reject honest code?

TACO and PrimeIntellect ship a reference solution per task. Each one is graded by every grader. A good fix should pass the same references the upstream graders pass.

| Dataset | verl `prime_code` | LiveCodeBench | rllm (DeepCoder) | hardened (ours) |
|---|---|---|---|---|
| deepcoder_taco | 217/261 (83%) | 223/261 (85%) | 228/261 (87%) | 256/261 (98%) |
| deepcoder_primeintellect | 217/298 (73%) | 204/298 (68%) | 208/298 (70%) | 227/298 (76%) |

- deepcoder_taco, hardened vs verl `prime_code`: both pass 215; only verl `prime_code` passes 2; only hardened passes 41.
- deepcoder_taco, hardened vs LiveCodeBench: both pass 221; only LiveCodeBench passes 2; only hardened passes 35.
- deepcoder_taco, hardened vs rllm (DeepCoder): both pass 226; only rllm (DeepCoder) passes 2; only hardened passes 30.
- deepcoder_primeintellect, hardened vs verl `prime_code`: both pass 201; only verl `prime_code` passes 16; only hardened passes 26.
- deepcoder_primeintellect, hardened vs LiveCodeBench: both pass 204; only LiveCodeBench passes 0; only hardened passes 23.
- deepcoder_primeintellect, hardened vs rllm (DeepCoder): both pass 208; only rllm (DeepCoder) passes 0; only hardened passes 19.

## 4. open-r1 `code_reward`

open-r1 runs each test in a separate `python3 -c` process and compares stdout in the parent, so the in-process fakes can't reach the answers. But it compares lines with `zip`, which stops at the shorter side. `first_line_only` runs the real reference and prints only the first line of its output.

| Solution | open-r1 | hardened |
|---|---|---|
| reference | 72/100 = 72.0% (95% CI 62.5-79.9) | 77/100 = 77.0% (95% CI 67.8-84.2) |
| null | 0/100 = 0.0% (95% CI 0.0-3.7) | 0/100 = 0.0% (95% CI 0.0-3.7) |
| peek | 0/100 = 0.0% (95% CI 0.0-3.7) | 0/100 = 0.0% (95% CI 0.0-3.7) |
| first_line_only | 74/100 = 74.0% (95% CI 64.6-81.6) | 53/100 = 53.0% (95% CI 43.3-62.5) |

Of the 72 tasks whose reference passes open-r1, the truncated program also gets full reward on 20/72 = 27.8% (95% CI 18.8-39.0) while the hardened grader rejects it (confirmed wrong output).

## 5. Why the graders disagree on real solutions

Every reference where the hardened grader and an upstream grader disagreed was re-run alone on an idle machine (`scripts/diagnose_rewards.py`).

| Grader | Cause | References |
|---|---|---|
| LiveCodeBench | fast stdin I/O (fileno / os.read / stdin.buffer) crashes on the mocked stdin | 29 |
| LiveCodeBench | other upstream runtime or comparison difference | 13 |
| LiveCodeBench | other mocked-stdin incompatibility | 10 |
| LiveCodeBench | program wrapped in a function: module-level names and `global` break | 5 |
| LiveCodeBench | upstream passes, hardened fails | 2 |
| LiveCodeBench | exit() / quit() disabled by reliability_guard | 1 |
| rllm (DeepCoder) | fast stdin I/O (fileno / os.read / stdin.buffer) crashes on the mocked stdin | 29 |
| rllm (DeepCoder) | other upstream runtime or comparison difference | 9 |
| rllm (DeepCoder) | other mocked-stdin incompatibility | 5 |
| rllm (DeepCoder) | program wrapped in a function: module-level names and `global` break | 5 |
| rllm (DeepCoder) | upstream passes, hardened fails | 2 |
| rllm (DeepCoder) | exit() / quit() disabled by reliability_guard | 1 |
| verl `prime_code` | fast stdin I/O (fileno / os.read / stdin.buffer) crashes on the mocked stdin | 29 |
| verl `prime_code` | other upstream runtime or comparison difference | 27 |
| verl `prime_code` | upstream passes, hardened fails | 18 |
| verl `prime_code` | other mocked-stdin incompatibility | 5 |
| verl `prime_code` | program wrapped in a function: module-level names and `global` break | 5 |
| verl `prime_code` | exit() / quit() disabled by reliability_guard | 1 |

verl first-10-tests rule (`scripts/verl_first_ten.py`): 29 reference programs fail verl's own all-tests check yet get score 1.0. A toy program that is wrong on tests 11-12 scores 1.0. 679 of 1024 Eurus validation tasks have more than 10 tests.

## Provenance

Grader code, unmodified, at these commits:

- verl: https://github.com/volcengine/verl @ `b0871fd89d19`
- livecodebench: https://github.com/LiveCodeBench/LiveCodeBench @ `28fef95ea8c9`
- rllm: https://github.com/rllm-org/rllm @ `4e828c81680e`
- bigcodebench: https://github.com/bigcode-project/bigcodebench @ `09dd993f46c3`
- open-r1: https://github.com/huggingface/open-r1 @ `5b6ff22b3fb7`

File hashes are in `provenance.json`.
