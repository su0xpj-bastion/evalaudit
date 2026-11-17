"""End-to-end check: feed the non-solving `hybrid` cheater to EvalPlus's own
`evalplus.evaluate` entry point and read the pass@1 it reports."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from evalaudit.data import load
from evalaudit.exploits import EXPLOITS

ENCODING = "utf-8"

if __name__ == "__main__":
    if sys.platform == "darwin":  # macOS rejects RLIMIT_AS
        os.environ.setdefault("EVALPLUS_MAX_MEMORY_BYTES", "-1")
    from evalplus.evaluate import evaluate

    out = Path(os.environ.get("EVALAUDIT_OFFICIAL_OUT", "results/official_cli"))
    out.mkdir(parents=True, exist_ok=True)
    for bench in sys.argv[1:] or ["humaneval", "mbpp"]:
        for name in ("null", "hybrid"):
            path = out / f"{bench}_{name}.jsonl"
            with path.open("w", encoding=ENCODING) as f:
                for t in load(bench).values():
                    f.write(json.dumps({"task_id": t.task_id, "solution": EXPLOITS[name](t)}) + "\n")
            print(f"=== {bench} / {name} ===", flush=True)
            evaluate(dataset=bench, samples=str(path), i_just_wanna_run=True)
