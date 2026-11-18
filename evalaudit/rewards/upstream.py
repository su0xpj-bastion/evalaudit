from __future__ import annotations

# Loads the real, unmodified grading code from each project at a pinned commit.
#
# Each repo is fetched once (shallow, at the exact commit) into
# ~/.cache/evalaudit/upstream/<name>-<sha12>. We import grader modules from
# there by file path. Nothing in the upstream code is edited; the only thing we
# skip is heavy package __init__ files (e.g. verl's, which imports torch) by
# loading the grader's own sub-package directly.

import hashlib
import importlib.util
import os
import subprocess
import sys
from functools import lru_cache
from pathlib import Path
from types import ModuleType

CACHE = Path(os.environ.get("EVALAUDIT_CACHE", Path.home() / ".cache" / "evalaudit")) / "upstream"

# name -> (git url, commit). Commits were HEAD of each default branch on 2026-11-17.
PINS: dict[str, tuple[str, str]] = {
    "verl": ("https://github.com/volcengine/verl", "b0871fd89d19329d8c9ed58e5402b11dcf920b64"),
    "livecodebench": ("https://github.com/LiveCodeBench/LiveCodeBench", "28fef95ea8c9f7a547c8329f2cd3d32b92c1fa24"),
    "rllm": ("https://github.com/rllm-org/rllm", "4e828c81680e5a85b638ceedeaf09d1e90109ca8"),
    "bigcodebench": ("https://github.com/bigcode-project/bigcodebench", "09dd993f46c3fbf3a799465bb96d524edcb0b199"),
    "open-r1": ("https://github.com/huggingface/open-r1", "5b6ff22b3fb7aa069c54866e517f39dfc3160e09"),
}

# The grading files we rely on, recorded with their hashes in every results file.
GRADER_FILES: dict[str, list[str]] = {
    "verl": [
        "verl/utils/reward_score/prime_code/__init__.py",
        "verl/utils/reward_score/prime_code/utils.py",
        "verl/utils/reward_score/prime_code/testing_util.py",
    ],
    "livecodebench": [
        "lcb_runner/evaluation/testing_util.py",
        "lcb_runner/evaluation/compute_code_generation_metrics.py",
    ],
    "rllm": [
        "rllm/rewards/code_reward.py",
        "rllm/rewards/code_utils/livecodebench.py",
    ],
    "bigcodebench": ["bigcodebench/eval/__init__.py", "bigcodebench/eval/utils.py"],
    "open-r1": ["src/open_r1/rewards.py"],
}


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def src(name: str) -> Path:
    """Return the local checkout of `name` at its pinned commit, fetching if needed."""
    url, sha = PINS[name]
    dest = CACHE / f"{name}-{sha[:12]}"
    if (dest / ".evalaudit-ok").exists():
        return dest
    dest.mkdir(parents=True, exist_ok=True)
    _git("init", "-q", cwd=dest)
    _git("fetch", "-q", "--depth", "1", url, sha, cwd=dest)
    _git("checkout", "-q", "FETCH_HEAD", cwd=dest)
    (dest / ".evalaudit-ok").write_text(sha)
    return dest


def fingerprint() -> dict[str, dict]:
    """Commit and sha256 of every grader file, for the results provenance block."""
    out: dict[str, dict] = {}
    for name, files in GRADER_FILES.items():
        root = src(name)
        out[name] = {
            "repo": PINS[name][0],
            "commit": PINS[name][1],
            "files": {f: hashlib.sha256((root / f).read_bytes()).hexdigest() for f in files},
        }
    return out


def _load_package(alias: str, directory: Path) -> ModuleType:
    """Import `directory` as a package named `alias` (relative imports inside it work)."""
    if alias in sys.modules:
        return sys.modules[alias]
    spec = importlib.util.spec_from_file_location(
        alias, directory / "__init__.py", submodule_search_locations=[str(directory)]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[alias] = module
    spec.loader.exec_module(module)
    return module


def _on_path(root: Path) -> None:
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


@lru_cache(maxsize=None)
def verl_prime_code() -> ModuleType:
    # verl/__init__.py pulls in torch and ray; the prime_code package itself only
    # needs numpy, so load it on its own.
    return _load_package("upstream_verl_prime_code", src("verl") / "verl/utils/reward_score/prime_code")


@lru_cache(maxsize=None)
def lcb_codegen() -> ModuleType:
    # lcb_runner/evaluation/__init__.py imports every metric module (and their
    # deps); load the two modules we need on their own under the real names so
    # `from lcb_runner.evaluation.testing_util import run_test` resolves.
    root = src("livecodebench")
    for pkg in ("lcb_runner", "lcb_runner.evaluation"):
        if pkg not in sys.modules:
            m = ModuleType(pkg)
            m.__path__ = [str(root / pkg.replace(".", "/"))]
            sys.modules[pkg] = m
    _on_path(root)
    return importlib.import_module("lcb_runner.evaluation.compute_code_generation_metrics")


@lru_cache(maxsize=None)
def rllm_code_reward() -> ModuleType:
    _on_path(src("rllm"))
    return importlib.import_module("rllm.rewards.code_reward")


@lru_cache(maxsize=None)
def bigcodebench_eval() -> ModuleType:
    _on_path(src("bigcodebench"))
    return importlib.import_module("bigcodebench.eval")


@lru_cache(maxsize=None)
def open_r1_eval_script_template() -> str:
    """The evaluation script open-r1's `code_reward` ships to its sandbox, verbatim.

    open_r1.rewards imports e2b/morph/trl, so we pull the string literal out with
    `ast` instead of importing the module.
    """
    import ast

    tree = ast.parse((src("open-r1") / "src/open_r1/rewards.py").read_text())
    for fn in ast.walk(tree):
        if isinstance(fn, ast.FunctionDef) and fn.name == "code_reward":
            for node in ast.walk(fn):
                if (
                    isinstance(node, ast.Assign)
                    and getattr(node.targets[0], "id", "") == "evaluation_script_template"
                ):
                    return ast.literal_eval(node.value)
    raise RuntimeError("evaluation_script_template not found in open-r1 rewards.py")
