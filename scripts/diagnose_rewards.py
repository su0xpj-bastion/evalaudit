"""Re-grade every reference where the hardened grader and an upstream grader
disagree, one at a time on an idle machine, and record why.

    python scripts/diagnose_rewards.py [results/rewards]

Writes <out>/reference_diagnosis.json with, per (task, grader):
  - the idle re-run results of both graders
  - LiveCodeBench's own error message for the first failing test (it's the
    same runtime as rllm's copy, and verl's is the APPS original)
  - which known cause it matches
"""

from __future__ import annotations

import json
import multiprocessing
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from evalaudit.rewards import graders, tasks, upstream
from evalaudit.rewards.hardened import grade

FASTIO = re.compile(r"fileno\(|os\.read\(|stdin\.buffer|sys\.stdin\.detach")
EXIT = re.compile(r"(^|[^.\w])(exit|quit)\(")


def lcb_error(code: str, tests: dict) -> str:
    upstream.lcb_codegen()
    tu = sys.modules["lcb_runner.evaluation.testing_util"]
    mgr = multiprocessing.Manager()
    out = mgr.list()

    def run():
        try:
            res, meta = tu.run_test({"input_output": json.dumps(tests)}, test=code, debug=False, timeout=6)
            out.append({"res": [repr(x) for x in res], "meta": {k: str(v)[:200] for k, v in meta.items()}})
        except BaseException as e:  # noqa: BLE001
            out.append({"res": [], "meta": {"error": repr(e)[:200]}})

    p = multiprocessing.Process(target=run)
    p.start()
    p.join(6 * len(tests["inputs"]) + 10)
    if p.is_alive():
        p.kill()
    return out[0] if out else {"res": [], "meta": {"error": "global timeout"}}


def cause(code: str, upstream_detail: dict, hard: tuple[str, dict]) -> str:
    err = json.dumps(upstream_detail.get("meta", {}))
    if hard[0] == "timeout":
        return "hardened timeout"
    if "fileno" in err or FASTIO.search(code):
        return "fast stdin I/O (fileno/os.read/stdin.buffer) unsupported by mocked stdin"
    if "NoneType' object is not callable" in err and EXIT.search(code):
        return "exit()/quit() disabled by reliability_guard"
    if "Time Limit" in err or "-3" in err or "global timeout" in err:
        return "upstream timeout"
    if "Wrong Answer" in err:
        return "upstream wrong answer (comparison rules differ)"
    return "other: " + err[:120]


def main() -> None:
    multiprocessing.set_start_method("fork", force=True)
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "results/rewards")
    rows = json.load((out / "apps.json").open(encoding="utf-8"))
    ref = defaultdict(dict)
    for r in rows:
        if r["solution"] == "reference":
            ref[(r["dataset"], r["task_id"])][r["grader"]] = r["passed"]
    todo = [(k, g) for k, v in ref.items() for g in ("verl", "livecodebench", "rllm") if v[g] != v["hardened"]]
    print(f"{len(todo)} disagreements to re-check")
    results = []
    cache: dict = {}
    for i, ((d, tid), g) in enumerate(todo, 1):
        task = tasks.load(d)[tid]
        fresh = lambda: json.loads(json.dumps(task.tests))  # noqa: E731
        up_pass, up_raw = graders.APPS_GRADERS[g](task.reference, fresh())
        if tid not in cache:
            cache[tid] = (grade(task.reference, fresh()), lcb_error(task.reference, fresh()))
        hard, lcb = cache[tid]
        row = {
            "dataset": d, "task_id": tid, "grader": g,
            "load_upstream": ref[(d, tid)][g], "load_hardened": ref[(d, tid)]["hardened"],
            "idle_upstream": up_pass, "idle_upstream_raw": up_raw if isinstance(up_raw, (int, float, bool)) else str(up_raw)[:200],
            "idle_hardened": hard[0], "lcb_detail": lcb,
        }
        row["cause"] = "agree when idle" if (up_pass == (hard[0] == "pass")) else cause(task.reference, lcb, hard)
        results.append(row)
        if i % 10 == 0:
            print(f"  {i}/{len(todo)}", flush=True)
    (out / "reference_diagnosis.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    c = Counter((r["grader"], r["idle_upstream"], r["idle_hardened"], r["cause"]) for r in results)
    for k, n in c.most_common():
        print(n, k)


if __name__ == "__main__":
    main()
