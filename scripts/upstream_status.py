"""Refresh the upstream follow-through tracker from GitHub.

    python scripts/upstream_status.py            # print the status table
    python scripts/upstream_status.py --write    # rewrite the table in docs/UPSTREAM_FOLLOWTHROUGH.md

Needs the GitHub CLI (`gh`), authenticated. Reads only; it never comments or files anything.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

REPO = "evalplus/evalplus"
ISSUES = {333: "grader trusts the solution (`__eq__`, frame peek)",
          334: "HumanEval/32 unpassable in 0.3.1; reference fails oracle on master",
          335: "timeouts graded as wrong answers",
          336: "empty / degenerate MBPP+ plus suites"}
DOC = Path(__file__).resolve().parent.parent / "docs" / "UPSTREAM_FOLLOWTHROUGH.md"
START, END = "<!-- status:start -->", "<!-- status:end -->"


def gh(*args: str):
    return json.loads(subprocess.run(["gh", *args], check=True, capture_output=True, text=True).stdout)


def table() -> str:
    rows = ["| Issue | Problem | State | Comments | Last response |", "|---|---|---|---|---|"]
    for n, what in ISSUES.items():
        d = gh("issue", "view", str(n), "-R", REPO, "--json", "state,comments,url")
        last = d["comments"][-1] if d["comments"] else None
        resp = f"{last['author']['login']} {last['createdAt'][:10]}" if last else "none"
        rows.append(f"| [#{n}]({d['url']}) | {what} | {d['state'].lower()} | {len(d['comments'])} | {resp} |")
    commit = gh("api", f"repos/{REPO}/commits?per_page=1")[0]["commit"]["committer"]["date"][:10]
    release = gh("api", f"repos/{REPO}/releases/latest")
    rows += ["", f"Upstream activity: last commit {commit}, latest release {release['tag_name']} "
                 f"({release['published_at'][:10]})."]
    return "\n".join(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    t = table()
    if args.write:
        text = DOC.read_text()
        head, rest = text.split(START, 1)
        _, tail = rest.split(END, 1)
        DOC.write_text(f"{head}{START}\n{t}\n{END}{tail}")
    print(t)


if __name__ == "__main__":
    main()
