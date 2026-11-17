# evalaudit findings

## 1. Non-solving cheaters vs. graders

Every row is a solution that never attempts the task. Any PASS is a false pass.

| Benchmark | Cheater | original asserts | EvalPlus base | EvalPlus plus | hardened (fix) |
|---|---|---|---|---|---|
| HumanEval | `null` | 0.0% (0/164) | 0.0% (0/164) | 0.0% (0/164) | 0.0% (0/164) |
| HumanEval | `always_equal` | 95.7% (157/164) | 99.4% (163/164) | 99.4% (163/164) | 0.0% (0/164) |
| HumanEval | `frame_peek` | 0.0% (0/164) | 99.4% (163/164) | 99.4% (163/164) | 0.0% (0/164) |
| HumanEval | `hybrid` | 95.7% (157/164) | 99.4% (163/164) | 99.4% (163/164) | 0.0% (0/164) |
| MBPP | `null` | 0.0% (0/378) | 0.0% (0/378) | 0.5% (2/378) | 0.0% (0/378) |
| MBPP | `always_equal` | 93.9% (355/378) | 97.4% (368/378) | 97.4% (368/378) | 0.0% (0/378) |
| MBPP | `frame_peek` | 0.0% (0/378) | 100.0% (378/378) | 100.0% (378/378) | 0.0% (0/378) |
| MBPP | `hybrid` | 93.9% (355/378) | 100.0% (378/378) | 100.0% (378/378) | 0.0% (0/378) |

- HumanEval / original asserts, `hybrid`: 157/164 = 95.7% (95% CI 91.5-97.9)
- HumanEval / EvalPlus base, `hybrid`: 163/164 = 99.4% (95% CI 96.6-99.9)
- HumanEval / EvalPlus plus, `hybrid`: 163/164 = 99.4% (95% CI 96.6-99.9)
- HumanEval / hardened (fix), `hybrid`: 0/164 = 0.0% (95% CI 0.0-2.3)
- MBPP / original asserts, `hybrid`: 355/378 = 93.9% (95% CI 91.0-95.9)
- MBPP / EvalPlus base, `hybrid`: 378/378 = 100.0% (95% CI 99.0-100.0)
- MBPP / EvalPlus plus, `hybrid`: 378/378 = 100.0% (95% CI 99.0-100.0)
- MBPP / hardened (fix), `hybrid`: 0/378 = 0.0% (95% CI 0.0-1.0)

## 2. Grader mutation testing

One-edit mutants of the reference solution. **Confirmed wrong** = the mutant fails EvalPlus's plus suite (a concrete input where it disagrees with ground truth). Mutants that pass every suite are *not* counted (may be equivalent).

| Benchmark | Grader | Mutants | Accepted | Accepted & confirmed wrong | Tasks accepting a confirmed-wrong mutant |
|---|---|---|---|---|---|
| HumanEval | original asserts | 1685 | 205 | 99 | 36/164 = 22.0% (95% CI 16.3-28.9) |
| HumanEval | EvalPlus base | 1685 | 202 | 95 | 35/164 = 21.3% (95% CI 15.8-28.2) |
| MBPP | original asserts | 1959 | 394 | 220 | 70/378 = 18.5% (95% CI 14.9-22.7) |
| MBPP | EvalPlus base | 1959 | 394 | 220 | 70/378 = 18.5% (95% CI 14.9-22.7) |

### Examples: wrong solutions both shipped graders accept

**HumanEval/0** (`cmp:0@28`), passes original asserts and EvalPlus base, fails EvalPlus plus:

```diff
--- reference
+++ mutant
@@ -12,3 +12,3 @@
     for i in range(len(sorted_numbers) - 1):
-        if sorted_numbers[i + 1] - sorted_numbers[i] < threshold:
+        if sorted_numbers[i + 1] - sorted_numbers[i] <= threshold:
             return True
```

**HumanEval/19** (`int-1@38`), passes original asserts and EvalPlus base, fails EvalPlus plus:

```diff
--- reference
+++ mutant
@@ -9,3 +9,3 @@
     """
-    to_int = {'zero': 0, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9}
+    to_int = {'zero': 0, 'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 7, 'nine': 9}
     if numbers == '':
```

**HumanEval/20** (`cmp:0@42`), passes original asserts and EvalPlus base, fails EvalPlus plus:

```diff
--- reference
+++ mutant
@@ -15,3 +15,3 @@
         diff = r - l
-        if diff < min_diff:
+        if diff <= min_diff:
             min_diff = diff
```

**HumanEval/31** (`int+1@23`), passes original asserts and EvalPlus base, fails EvalPlus plus:

```diff
--- reference
+++ mutant
@@ -17,3 +17,3 @@
     """
-    if n <= 1:
+    if n <= 2:
         return False
```

## 3. Reference-solution reliability

The benchmark's own reference solution, graded repeatedly on an oversubscribed machine (2x workers per core). A sound grader passes it every time.

| Benchmark | Grader | Always fails (broken) | Flaky (mixed verdicts) | Non-pass verdicts reported as `fail` / `timeout` |
|---|---|---|---|---|
| HumanEval | original asserts | 0/164  | 0/164  | 0 / 0 |
| HumanEval | EvalPlus base | 1/164 (32) | 0/164  | 5 / 0 |
| HumanEval | EvalPlus plus | 3/164 (139, 32, 83) | 0/164  | 15 / 0 |
| HumanEval | hardened (fix) | 3/164 (139, 32, 83) | 1/164 (120) | 5 / 11 |
| MBPP | original asserts | 1/378 (120) | 0/378  | 5 / 0 |
| MBPP | EvalPlus base | 0/378  | 0/378  | 0 / 0 |
| MBPP | EvalPlus plus | 4/378 (255, 389, 599, 603) | 4/378 (271, 392, 583, 630) | 29 / 0 |
| MBPP | hardened (fix) | 3/378 (255, 389, 599) | 6/378 (271, 392, 583, 592, 603, 630) | 0 / 30 |

## 4. Degenerate test suites

A suite with zero inputs passes anything; a suite whose expected outputs are all identical passes a function that returns that constant.

| Benchmark | Suite | Empty | Single distinct expected output |
|---|---|---|---|
| HumanEval | EvalPlus base | 0  | 0  |
| HumanEval | EvalPlus plus | 0  | 0  |
| MBPP | EvalPlus base | 0  | 0  |
| MBPP | EvalPlus plus | 1 (793) | 6 (223, 285, 635, 734, 760, 787) |

## 5. Statistical power: how big a gap is real?

Minimum detectable difference between two models' pass rates (two-proportion z-test, alpha 0.05, power 0.80).

| Benchmark | Tasks | MDE at 50% pass | MDE at 80% pass | MDE at 90% pass |
|---|---|---|---|---|
| HumanEval | 164 | ±15.5 pts | ±12.4 pts | ±9.3 pts |
| MBPP | 378 | ±10.2 pts | ±8.2 pts | ±6.1 pts |

