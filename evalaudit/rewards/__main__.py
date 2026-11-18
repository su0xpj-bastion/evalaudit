from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from evalaudit.rewards import audit, report, upstream

ENCODING = "utf-8"


def _save(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding=ENCODING) as f:
        json.dump(rows, f)
    print(f"  wrote {path} ({len(rows)} rows)")


def main() -> None:
    ap = argparse.ArgumentParser(prog="python -m evalaudit.rewards", description="Audit RL code-reward functions.")
    ap.add_argument("command", choices=["apps", "bcb", "openr1", "report", "all"])
    ap.add_argument("--datasets", nargs="+", default=audit.APPS_DATASETS)
    ap.add_argument("--graders", nargs="+", default=list(audit.APPS_GRADERS))
    ap.add_argument("--workers", type=int, default=audit.default_workers())
    ap.add_argument("--out", type=Path, default=Path("results/rewards"))
    args = ap.parse_args()

    t0 = time.time()
    if args.command in ("apps", "all"):
        _save(audit.apps(args.datasets, args.graders, args.workers), args.out / "apps.json")
    if args.command in ("bcb", "all"):
        _save(audit.bcb(args.workers), args.out / "bcb.json")
    if args.command in ("openr1", "all"):
        _save(audit.openr1(args.workers), args.out / "openr1.json")
    if args.command in ("report", "all"):
        with (args.out / "provenance.json").open("w", encoding=ENCODING) as f:
            json.dump(upstream.fingerprint(), f, indent=2)
        report.write(args.out)
    print(f"done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
