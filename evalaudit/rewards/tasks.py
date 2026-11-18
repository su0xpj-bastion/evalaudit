from __future__ import annotations

# Task loaders for the reward-function audit. Every dataset is pinned to a
# Hugging Face revision and converted to the APPS test format the graders use:
#   {"inputs": [...], "outputs": [...], "fn_name": optional}
# For function-call tasks, each input is one JSON value per line and each
# output is a JSON string (the LiveCodeBench convention). Eurus rows are passed
# through untouched, because verl reads them as-is.

import base64
import io
import json
import pickle
import random
import zlib
from dataclasses import dataclass, field
from functools import lru_cache

DATASETS: dict[str, tuple[str, str, list[str]]] = {
    # name -> (HF repo, revision, files)
    "eurus": ("PRIME-RL/Eurus-2-RL-Data", "9776b13264b5aaa0b16495fcf086a0a8d86fd655", ["validation.parquet"]),
    "lcb_v6": ("livecodebench/code_generation_lite", "0fe84c3912ea0c4d4a78037083943e8f0c4dd505", ["test6.jsonl"]),
    "deepcoder_lcb": (
        "agentica-org/DeepCoder-Preview-Dataset",
        "177913a7bd43791646ef6a43645caa3c871ab3db",
        [f"lcbv5/test-0000{i}-of-00008.parquet" for i in (4, 5, 6, 7)],
    ),
    "deepcoder_taco": (
        "agentica-org/DeepCoder-Preview-Dataset",
        "177913a7bd43791646ef6a43645caa3c871ab3db",
        ["taco/train-00001-of-00004.parquet"],
    ),
    "deepcoder_primeintellect": (
        "agentica-org/DeepCoder-Preview-Dataset",
        "177913a7bd43791646ef6a43645caa3c871ab3db",
        ["primeintellect/train-00002-of-00005.parquet"],
    ),
    "bigcodebench": ("bigcode/bigcodebench", "b74c0d0bf70d2c0bc459be537895cca163007f1a", ["data/v0.1.4-00000-of-00001.parquet"]),
}

# Which grader each dataset is native to (used for the headline table).
NATIVE = {
    "eurus": "verl",
    "lcb_v6": "livecodebench",
    "deepcoder_lcb": "rllm",
    "deepcoder_taco": "rllm",
    "deepcoder_primeintellect": "rllm",
}

SAMPLE = 300  # tasks per large training shard (fixed seed)


@dataclass
class Task:
    dataset: str
    task_id: str
    mode: str  # "call" or "stdio"
    tests: dict
    reference: str | None = None
    extra: dict = field(default_factory=dict)


def _path(dataset: str, filename: str) -> str:
    from huggingface_hub import hf_hub_download

    repo, rev, _ = DATASETS[dataset]
    return hf_hub_download(repo, filename, repo_type="dataset", revision=rev)


def _frames(dataset: str):
    import pandas as pd

    _, _, files = DATASETS[dataset]
    return pd.concat([pd.read_parquet(_path(dataset, f)) for f in files], ignore_index=True)


def _sample(rows: list, n: int, seed: str) -> list:
    if len(rows) <= n:
        return rows
    rng = random.Random(seed)
    return sorted(rng.sample(rows, n), key=lambda r: r[0])


class _StringsOnly(pickle.Unpickler):
    # LiveCodeBench stores private tests as base64(zlib(pickle(json_str))).
    # Refuse any global so a pickle can only produce plain values.
    def find_class(self, module, name):
        raise pickle.UnpicklingError(f"blocked global {module}.{name}")


def _lcb_private(blob: str) -> list:
    raw = zlib.decompress(base64.b64decode(blob.encode("utf-8")))
    return json.loads(_StringsOnly(io.BytesIO(raw)).load())


def _from_lcb_list(tests: list, fn_name: str | None) -> dict:
    out = {"inputs": [t["input"] for t in tests], "outputs": [t["output"] for t in tests]}
    if fn_name:
        out["fn_name"] = fn_name
    return out


def _strip_fence(code: str) -> str:
    if "```" in code:
        code = code.split("```python")[-1] if "```python" in code else code.split("```")[1]
        code = code.split("```")[0]
    return code.strip("\n")


@lru_cache(maxsize=None)
def load(dataset: str) -> dict[str, Task]:
    tasks: list[Task] = []
    if dataset == "eurus":
        df = _frames(dataset)
        df = df[df.ability == "code"].reset_index(drop=True)
        for i, row in df.iterrows():
            tests = json.loads(row.reward_model["ground_truth"])
            mode = "call" if tests.get("fn_name") else "stdio"
            tasks.append(Task(dataset, f"eurus/{row.data_source}/{i}", mode, tests, extra={"source": row.data_source}))
    elif dataset == "lcb_v6":
        with open(_path(dataset, "test6.jsonl"), encoding="utf-8") as fh:
            for line in fh:
                r = json.loads(line)
                fn = json.loads(r["metadata"] or "{}").get("func_name")
                tests = json.loads(r["public_test_cases"]) + _lcb_private(r["private_test_cases"])
                tasks.append(Task(dataset, f"lcb_v6/{r['question_id']}", "call" if fn else "stdio", _from_lcb_list(tests, fn)))
    elif dataset == "deepcoder_lcb":
        df = _frames(dataset)
        for i, row in df.iterrows():
            meta = row.metadata if isinstance(row.metadata, dict) else json.loads(row.metadata.replace("'", '"').replace("None", "null"))
            fn = meta.get("func_name")
            tests = json.loads(row.tests)
            tasks.append(Task(dataset, f"deepcoder_lcb/{i}", "call" if fn else "stdio", _from_lcb_list(tests, fn)))
    elif dataset == "deepcoder_taco":
        df = _frames(dataset)
        rows = _sample(list(df.iterrows()), SAMPLE, dataset)
        for i, row in rows:
            raw = json.loads(row.tests)
            sols = json.loads(row.solutions) if isinstance(row.solutions, str) else list(row.solutions)
            fn = raw.get("fn_name")
            if fn:  # TACO stores call args/returns as JSON values; LCB format wants strings
                tests = {
                    "fn_name": fn,
                    "inputs": ["\n".join(json.dumps(a) for a in args) for args in raw["inputs"]],
                    "outputs": [json.dumps(o[0] if isinstance(o, list) and len(o) == 1 else o) for o in raw["outputs"]],
                }
            else:
                tests = {"inputs": raw["inputs"], "outputs": raw["outputs"]}
            ref = sols[0] if sols and not fn else None  # TACO call refs are bare functions, not class Solution
            tasks.append(Task(dataset, f"deepcoder_taco/{i}", "call" if fn else "stdio", tests, ref))
    elif dataset == "deepcoder_primeintellect":
        df = _frames(dataset)
        rows = _sample(list(df.iterrows()), SAMPLE, dataset)
        for i, row in rows:
            raw = json.loads(row.tests)
            if any(t.get("type") != "stdin_stdout" for t in raw):
                continue  # 14 of 3,250 rows are function-call with mixed formats; skip
            sols = json.loads(row.solutions) if isinstance(row.solutions, str) else list(row.solutions)
            tests = {"inputs": [t["input"] for t in raw], "outputs": [t["output"] for t in raw]}
            ref = _strip_fence(sols[0]) if len(sols) else None
            tasks.append(Task(dataset, f"deepcoder_primeintellect/{i}", "stdio", tests, ref))
    elif dataset == "bigcodebench":
        df = _frames(dataset)
        for _, row in df.iterrows():
            tasks.append(
                Task(
                    dataset, row.task_id, "unittest",
                    {"test": row.test, "entry_point": row.entry_point},
                    row.code_prompt + row.canonical_solution,
                    extra={"libs": row.libs},
                )
            )
    else:
        raise KeyError(dataset)
    return {t.task_id: t for t in tasks}
