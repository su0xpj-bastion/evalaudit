from __future__ import annotations

# A reference grader for APPS-format code rewards that doesn't trust the code
# it grades. Same idea as evalaudit/hardened.py, applied to RL rewards:
#
#   1. The solution runs in a separate Python process that is never given the
#      expected outputs. (stdin tasks: one fresh process per test.)
#   2. The child sends back plain data only: stdout text, or JSON-encoded
#      return values. An object with a custom __eq__ can't survive JSON.
#   3. The trusted parent compares, using LiveCodeBench's rules.
#   4. The parent counts tests itself. A run that reports fewer results than
#      there are tests fails, so emptying the test list can't pass.
#   5. Timeouts are reported as "timeout", not as wrong answers.
#
# Residual risk: the child still runs as the same OS user. Anything else on
# disk that holds the answers (the dataset file itself) must be kept out of
# reach with a real sandbox. This module removes the in-process attacks only.

import json
import os
import subprocess
import sys
import tempfile
from decimal import Decimal, InvalidOperation

# Same convenience imports LiveCodeBench prepends, so honest solutions that rely
# on them behave the same.
PRELUDE = (
    "from string import *\nfrom re import *\nfrom datetime import *\nfrom collections import *\n"
    "from heapq import *\nfrom bisect import *\nfrom copy import *\nfrom math import *\n"
    "from random import *\nfrom statistics import *\nfrom itertools import *\nfrom functools import *\n"
    "from operator import *\nfrom io import *\nfrom sys import *\nfrom json import *\n"
    "from builtins import *\nfrom typing import *\nimport string\nimport re\nimport datetime\n"
    "import collections\nimport heapq\nimport bisect\nimport copy\nimport math\nimport random\n"
    "import statistics\nimport itertools\nimport functools\nimport operator\nimport io\nimport sys\n"
    "import json\nsys.setrecursionlimit(50000)\n"
)

# Runs in the child for function-call tasks. Reads {"code", "fn_name",
# "inputs"} on stdin; writes one JSON line per input to a private pipe (fd in
# argv[1]), which the solution's own prints can't reach by accident.
_CALL_RUNNER = r'''
import json, os, sys, types
job = json.loads(sys.stdin.read())
out = os.fdopen(int(sys.argv[1]), "w")
mod = types.ModuleType("solution")
try:
    exec(compile(job["prelude"] + job["code"], "solution.py", "exec"), mod.__dict__)
    target = mod.Solution() if "class Solution" in job["code"] else mod
    fn = getattr(target, job["fn_name"])
except BaseException as e:
    out.write(json.dumps({"error": "load: " + repr(e)[:200]}) + "\n"); out.flush(); os._exit(0)
for line in job["inputs"]:
    try:
        args = [json.loads(a) for a in line.split("\n")]
        value = fn(*args)
        if isinstance(value, tuple):
            value = list(value)
        out.write(json.dumps({"value": json.dumps(value)}) + "\n")
    except BaseException as e:
        out.write(json.dumps({"error": repr(e)[:200]}) + "\n")
    out.flush()
os._exit(0)
'''


def _lines(text: str) -> list[str]:
    return [line.strip() for line in text.strip().split("\n")]


def stdio_equal(got: str, expected: str) -> bool:
    """LiveCodeBench's grade_stdio rule: line by line, exact or equal as decimals."""
    a, b = _lines(got), _lines(expected)
    if len(a) != len(b):
        return False
    for x, y in zip(a, b):
        if x == y:
            continue
        try:
            if [Decimal(t) for t in x.split()] != [Decimal(t) for t in y.split()]:
                return False
        except InvalidOperation:
            return False
    return True


def _plain_json(text: str):
    return json.loads(text)


def call_equal(got_json: str, expected_json: str) -> bool:
    got, exp = _plain_json(got_json), _plain_json(expected_json)
    return got == exp


def _env() -> dict:
    env = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "LANG", "LC_ALL", "SYSTEMROOT", "TMPDIR")}
    env["PYTHONHASHSEED"] = "0"
    return env


def _grade_stdio(code: str, tests: dict, per_test: float) -> tuple[str, dict]:
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "solution.py")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(PRELUDE + code)
        for i, (inp, exp) in enumerate(zip(tests["inputs"], tests["outputs"])):
            if isinstance(inp, list):
                inp = "\n".join(inp)
            if isinstance(exp, list):
                exp = "\n".join(exp)
            try:
                proc = subprocess.run(
                    [sys.executable, "-I", path], input=inp, capture_output=True, text=True,
                    timeout=per_test, cwd=tmp, env=_env(),
                )
            except subprocess.TimeoutExpired:
                return "timeout", {"test": i}
            if proc.returncode != 0:
                return "fail", {"test": i, "error": proc.stderr[-200:]}
            if not stdio_equal(proc.stdout, exp):
                return "fail", {"test": i, "error": "wrong answer"}
    return "pass", {"tests": len(tests["inputs"])}


def _grade_call(code: str, tests: dict, per_test: float) -> tuple[str, dict]:
    n = len(tests["inputs"])
    job = json.dumps({"code": code, "fn_name": tests["fn_name"], "inputs": tests["inputs"], "prelude": PRELUDE})
    r, w = os.pipe()
    with tempfile.TemporaryDirectory() as tmp:
        try:
            proc = subprocess.Popen(
                [sys.executable, "-I", "-c", _CALL_RUNNER, str(w)], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, pass_fds=(w,), cwd=tmp, env=_env(),
            )
        finally:
            os.close(w)
        reader = os.fdopen(r)
        try:
            proc.communicate(job.encode(), timeout=per_test * n + 2)
            timed_out = False
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            timed_out = True
        lines = reader.read().splitlines()
        reader.close()
    results = []
    for line in lines:
        try:
            results.append(json.loads(line))
        except json.JSONDecodeError:
            results.append({"error": "garbled"})
    for i, exp in enumerate(tests["outputs"]):
        if i >= len(results):
            return ("timeout" if timed_out else "fail"), {"test": i, "error": f"only {len(results)} of {n} results"}
        res = results[i]
        if "value" not in res:
            return "fail", {"test": i, "error": res.get("error")}
        try:
            ok = call_equal(res["value"], exp)
        except (ValueError, TypeError):
            ok = False
        if not ok:
            return "fail", {"test": i, "error": "wrong answer"}
    return "pass", {"tests": n}


def grade(code: str, tests: dict, per_test: float = 6.0) -> tuple[str, dict]:
    """Return (status, detail). status is pass / fail / timeout."""
    if not tests.get("inputs") or len(tests["inputs"]) != len(tests["outputs"]):
        return "fail", {"error": "no tests"}
    if tests.get("fn_name"):
        return _grade_call(code, tests, per_test)
    return _grade_stdio(code, tests, per_test)


def hardened(code: str, tests: dict) -> tuple[bool, object]:
    """Adapter with the same shape as evalaudit.rewards.graders.*"""
    status, detail = grade(code, tests)
    return status == "pass", {"status": status, **detail}
