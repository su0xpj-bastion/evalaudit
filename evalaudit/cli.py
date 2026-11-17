from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from evalaudit import audit, report
from evalaudit.data import BENCHMARKS

ENCODING = "utf-8"


def _save(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding=ENCODING) as f:
        json.dump(rows, f)
    print(f"  wrote {path} ({len(rows)} rows)")


def main() -> None:
    ap = argparse.ArgumentParser(prog="evalaudit", description="Audit code-benchmark graders.")
    ap.add_argument("command", choices=["exploits", "mutation", "reliability", "report", "all"])
    ap.add_argument("--benchmarks", nargs="+", default=list(BENCHMARKS), choices=BENCHMARKS)
    ap.add_argument("--workers", type=int, default=os.cpu_count())
    ap.add_argument("--max-mutants", type=int, default=25)
    ap.add_argument("--repeats", type=int, default=5)
    ap.add_argument("--out", type=Path, default=Path("results"))
    args = ap.parse_args()

    t0 = time.time()
    cmd = args.command
    if cmd in ("exploits", "all"):
        _save(audit.exploit_experiment(args.benchmarks, args.workers), args.out / "exploits.json")
    if cmd in ("mutation", "all"):
        rows = audit.mutation_experiment(args.benchmarks, args.max_mutants, args.workers)
        _save(rows, args.out / "mutation.json")
    if cmd in ("reliability", "all"):
        # oversubscribe on purpose: 2x cores
        rows = audit.reliability_experiment(args.benchmarks, args.repeats, 2 * args.workers)
        _save(rows, args.out / "reliability.json")
    if cmd in ("report", "all"):
        report.write(args.out)
    print(f"done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
