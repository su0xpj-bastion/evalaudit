from __future__ import annotations

import multiprocessing

import pytest

from evalaudit.rewards import fakes, graders
from evalaudit.rewards.hardened import grade, hardened, stdio_equal

multiprocessing.set_start_method("fork", force=True)

STDIO = {"inputs": ["3 4\n", "10 5\n"], "outputs": ["7\n", "15\n"]}
CALL = {"fn_name": "addTwo", "inputs": ["3\n4", "10\n5"], "outputs": ["7", "15"]}
REF = {
    "stdio": "a, b = map(int, input().split())\nprint(a + b)",
    "call": "class Solution:\n    def addTwo(self, a, b):\n        return a + b",
}
TESTS = {"stdio": STDIO, "call": CALL}


def _fresh(mode):
    import json

    return json.loads(json.dumps(TESTS[mode]))


# Which (grader, mode, fake) combinations earn full reward on the pinned upstream code.
EXPECTED_PASS = {
    ("verl", "call"): {"peek", "vanish"},
    ("livecodebench", "call"): {"always_equal", "peek", "vanish"},
    ("rllm", "call"): {"always_equal", "peek", "vanish"},
    ("verl", "stdio"): {"peek"},
    ("livecodebench", "stdio"): {"peek"},
    ("rllm", "stdio"): {"peek"},
}


@pytest.mark.parametrize("grader", ["verl", "livecodebench", "rllm"])
@pytest.mark.parametrize("mode", ["call", "stdio"])
def test_upstream_graders_accept_fakes(grader, mode):
    fn = graders.APPS_GRADERS[grader]
    assert fn(REF[mode], _fresh(mode))[0], "reference must pass"
    for name, code in fakes.APPS_FAKES[mode].items():
        passed = fn(code, _fresh(mode))[0]
        assert passed == (name in EXPECTED_PASS[(grader, mode)]), (grader, mode, name)


@pytest.mark.parametrize("mode", ["call", "stdio"])
def test_hardened_rejects_every_fake_and_passes_reference(mode):
    assert hardened(REF[mode], _fresh(mode))[0]
    for name, code in fakes.APPS_FAKES[mode].items():
        assert not hardened(code, _fresh(mode))[0], name


def test_hardened_counts_tests_itself():
    # A child that exits after the first answer can't pass by reporting less.
    code = "import os\nclass Solution:\n    def addTwo(self, a, b):\n        if b == 5:\n            os._exit(0)\n        return a + b"
    status, detail = grade(code, _fresh("call"))
    assert status == "fail" and "only 1 of 2" in detail["error"]


def test_hardened_reports_timeouts_separately():
    status, _ = grade("import time\ntime.sleep(5)", _fresh("stdio"), per_test=0.5)
    assert status == "timeout"


def test_stdio_equal_follows_livecodebench_rules():
    assert stdio_equal("1.50\n", "1.5")
    assert stdio_equal("  a b \n", "a b")
    assert not stdio_equal("1\n2\n", "1")
    assert not stdio_equal("x", "y")


def test_open_r1_accepts_truncated_output():
    tests = {"inputs": ["2\n1 2\n3 4\n"], "outputs": ["3\n7\n"]}
    full = "t = int(input())\nfor _ in range(t):\n    a, b = map(int, input().split())\n    print(a + b)"
    first_only = "t = int(input())\na, b = map(int, input().split())\nprint(a + b)"
    assert graders.open_r1(full, tests)[0]
    assert graders.open_r1(first_only, tests)[0]  # wrong program, full reward
    assert not hardened(first_only, tests)[0]


def test_bigcodebench_silence_fake():
    test_code = (
        "import unittest\n"
        "class TestCases(unittest.TestCase):\n"
        "    def test_one(self):\n"
        "        self.assertEqual(task_func(2), 4)\n"
    )
    ref = "def task_func(x):\n    return x * 2\n"
    assert graders.bigcodebench(ref, test_code, "task_func", time_limit=5)[0]
    assert not graders.bigcodebench("", test_code, "task_func", time_limit=5)[0]
    assert graders.bigcodebench(fakes.BCB_FAKES["silence"], test_code, "task_func", time_limit=5)[0]
