"""verl's default code reward only looks at the first 10 tests once any test fails.

prime_code.compute_score(..., continuous=True) (verl's default route) first runs
every test. If that fails, it re-runs tests one by one but stops after the
first 10 and returns the fraction passed. A program that is right on tests
1-10 and wrong later gets 1.0.

This script:
  1. shows it on a 12-test toy task,
  2. counts, for every PrimeIntellect/TACO reference, programs that verl's own
     full check rejects but its default score gives 1.0,
  3. counts how many tasks in verl's Eurus validation set have more than 10 tests.

    python scripts/verl_first_ten.py [results/rewards]
"""

from __future__ import annotations

import contextlib
import io
import json
import multiprocessing
import sys
from pathlib import Path

from evalaudit.rewards import graders, tasks, upstream


def verl_full_check(code: str, tests: dict) -> bool:
    # The all-tests check compute_score does first (same call, same timeout).
    res, _ = upstream.verl_prime_code().utils.check_correctness(in_outs=tests, generation=code, timeout=5, debug=False)
    return all(x is True for x in res)


def main() -> None:
    multiprocessing.set_start_method("fork", force=True)
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "results/rewards")
    pc = upstream.verl_prime_code()
    result: dict = {}

    toy = {"inputs": [f"{i}\n" for i in range(12)], "outputs": [f"{2 * i}\n" for i in range(12)]}
    wrong_after_ten = "n = int(input())\nprint(2 * n if n < 10 else -1)"
    score, _ = pc.compute_score(graders.as_completion(wrong_after_ten), json.dumps(toy), continuous=True)
    result["toy"] = {"score": score, "full_check": verl_full_check(wrong_after_ten, json.loads(json.dumps(toy)))}
    print("toy:", result["toy"])

    rows = []
    for d in ("deepcoder_taco", "deepcoder_primeintellect"):
        for t in tasks.load(d).values():
            if not t.reference or t.mode != "stdio" or len(t.tests["inputs"]) <= 10:
                continue
            with contextlib.redirect_stdout(io.StringIO()):
                full = verl_full_check(t.reference, json.loads(json.dumps(t.tests)))
                if full:
                    continue
                score, _ = pc.compute_score(graders.as_completion(t.reference), json.dumps(t.tests), continuous=True)
            if score == 1:
                rows.append({"task_id": t.task_id, "tests": len(t.tests["inputs"])})
    result["full_reward_but_fails_full_check"] = rows
    print("references with score 1.0 that fail verl's own full check:", len(rows))

    eurus = list(tasks.load("eurus").values())
    result["eurus_more_than_10_tests"] = [sum(len(t.tests["inputs"]) > 10 for t in eurus), len(eurus)]
    print("Eurus tasks with more than 10 tests:", result["eurus_more_than_10_tests"])
    (out / "verl_first_ten.json").write_text(json.dumps(result, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
