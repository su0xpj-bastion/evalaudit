from __future__ import annotations

# Thin adapters around each project's own public grading entry point. Each one
# takes (code, tests) and returns (passed, raw) where `raw` is whatever the
# upstream function returned, so a reviewer can check our reading of it.
#
# Test format used throughout ("APPS format", what TACO/APPS/verl use):
#   {"inputs": [str, ...], "outputs": [str, ...], "fn_name": optional str}
# For function-call tasks each input/output is a JSON string, one argument per line.

import json

import numpy as np

from evalaudit.rewards import upstream


def as_completion(code: str) -> str:
    """Wrap code the way a model's answer arrives (both verl and rllm extract the last ```python block)."""
    return f"Here is my solution.\n\n```python\n{code}\n```\n"


def verl(code: str, tests: dict) -> tuple[bool, object]:
    # verl's default route for data_source in {codecontests, apps, codeforces, taco}:
    #   prime_code.compute_score(solution_str, ground_truth, continuous=True)
    score, _meta = upstream.verl_prime_code().compute_score(as_completion(code), json.dumps(tests), continuous=True)
    return (score is True or score == 1), (score if isinstance(score, (bool, int, float)) else repr(score))


def livecodebench(code: str, tests: dict) -> tuple[bool, object]:
    # LCB's codegen_metrics -> evaluate_generations_by_problem -> check_correctness(sample, o, timeout=6)
    # A generation counts as correct when np.all(np.array(results) > 0) (pass_k_utils).
    res, _meta = upstream.lcb_codegen().check_correctness({"input_output": json.dumps(tests)}, code, timeout=6, debug=False)
    fixed = []
    for e in res:
        if isinstance(e, np.ndarray):
            e = e.item(0)
        if isinstance(e, np.bool_):
            e = bool(e)
        fixed.append(e)
    try:
        passed = bool(np.all(np.array(fixed) > 0))
    except TypeError:  # an object that can't be compared to 0
        passed = False
    return passed, [repr(x) for x in fixed]


def to_rllm_tests(tests: dict) -> list[dict]:
    # rllm's DeepCoder cookbook (cookbooks/deepcoder/prepare_deepcoder_data.py)
    # normalizes every row to a list of tests and sets data_source="livecodebench".
    fn = tests.get("fn_name")
    kind = "functional" if fn else "stdin"
    meta = {"func_name": fn}
    return [
        {"input": i, "output": o, "testtype": kind, "metadata": meta}
        for i, o in zip(tests["inputs"], tests["outputs"])
    ]


def rllm(code: str, tests: dict) -> tuple[bool, object]:
    out = upstream.rllm_code_reward().rllm_reward_fn_code("livecodebench", as_completion(code), to_rllm_tests(tests))
    return bool(out.is_correct), out.reward


APPS_GRADERS = {"verl": verl, "livecodebench": livecodebench, "rllm": rllm}


def bigcodebench(code: str, test_code: str, entry_point: str, time_limit: float = 20) -> tuple[bool, object]:
    # BigCodeBench's evaluate() calls untrusted_check with these defaults
    # (max_as_limit=30*1024 MB, max_data_limit=30*1024 MB, max_stack_limit=10 MB).
    # macOS rejects RLIMIT_AS; passing 0 is BigCodeBench's own way to skip the
    # limits (its evaluate CLI exposes --max-as-limit etc.). Linux keeps them.
    import sys

    limits = (0, 0, 0) if sys.platform == "darwin" else (30 * 1024, 30 * 1024, 10)
    stat, details = upstream.bigcodebench_eval().untrusted_check(
        code, test_code, entry_point, *limits, min_time_limit=time_limit, gt_time_limit=time_limit
    )
    return stat == "pass", {"stat": stat, "details": {k: str(v)[:300] for k, v in dict(details).items()}}


def open_r1(code: str, tests: dict) -> tuple[bool, object]:
    """Run open-r1's code_reward evaluation script, verbatim, locally instead of in an E2B sandbox."""
    import subprocess
    import sys

    template = upstream.open_r1_eval_script_template()
    cases = [{"input": i, "output": o} for i, o in zip(tests["inputs"], tests["outputs"])]
    script = template.format(code=json.dumps(code), test_cases=json.dumps(json.dumps(cases)))
    # The template is indented (it lives inside the function). E2B runs it in a
    # Jupyter kernel, whose IPython input transforms strip that leading indent;
    # textwrap.dedent does the same here. The sandbox returns the value of the
    # script's last expression, so we print it.
    import textwrap

    script = textwrap.dedent(script).rstrip() + "\n"
    last = script.rstrip().splitlines()[-1].strip()
    script += f"print(repr({last}))\n"
    proc = subprocess.run(
        [sys.executable, "-c", script.replace("python3", sys.executable)],
        capture_output=True, text=True, timeout=10 * max(1, len(cases)) + 30,
    )
    try:
        rate = float(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return False, {"stderr": proc.stderr[-300:]}
    return rate == 1.0, rate
