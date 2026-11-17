from __future__ import annotations

import ast
import difflib
import json
import sys
from collections import defaultdict
from pathlib import Path

from evalaudit.data import load
from evalaudit.stats import fmt_rate, mde_two_proportions, wilson

ENCODING = "utf-8"
sys.set_int_max_str_digits(0)  # some ground-truth outputs are huge ints
GRADER_LABEL = {
    "original": "original asserts",
    "base": "EvalPlus base",
    "plus": "EvalPlus plus",
    "hardened": "hardened (fix)",
}
BENCH_LABEL = {"humaneval": "HumanEval", "mbpp": "MBPP"}


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open("r", encoding=ENCODING) as f:
        return json.load(f)


def _exploit_section(rows: list[dict], summary: dict) -> list[str]:
    if not rows:
        return []
    out = ["## 1. Non-solving cheaters vs. graders", ""]
    out.append(
        "Every row is a solution that never attempts the task. Any PASS is a false pass."
    )
    out.append("")
    out.append("| Benchmark | Cheater | " + " | ".join(GRADER_LABEL.values()) + " |")
    out.append("|---|---|" + "---|" * len(GRADER_LABEL))
    tally: dict = defaultdict(lambda: [0, 0])
    for r in rows:
        key = (r["benchmark"], r["tag"].split(":", 1)[1], r["grader"])
        tally[key][1] += 1
        tally[key][0] += r["status"] == "pass"
    benches = sorted({r["benchmark"] for r in rows})
    exploits = list(dict.fromkeys(r["tag"].split(":", 1)[1] for r in rows))
    summary["exploits"] = {}
    for b in benches:
        for e in exploits:
            cells = []
            for g in GRADER_LABEL:
                k, n = tally[(b, e, g)]
                cells.append(f"{100 * k / n:.1f}% ({k}/{n})" if n else "-")
                summary["exploits"][f"{b}/{e}/{g}"] = [k, n]
            out.append(f"| {BENCH_LABEL[b]} | `{e}` | " + " | ".join(cells) + " |")
    out.append("")
    for b in benches:
        for g in GRADER_LABEL:
            k, n = tally[(b, "hybrid", g)]
            if n:
                out.append(f"- {BENCH_LABEL[b]} / {GRADER_LABEL[g]}, `hybrid`: {fmt_rate(k, n)}")
    out.append("")
    return out


def _unified(a: str, b: str) -> str:
    a = ast.unparse(ast.parse(a)).splitlines()
    b = b.splitlines()
    return "\n".join(
        line
        for line in difflib.unified_diff(a, b, "reference", "mutant", n=1, lineterm="")
    )


def _mutation_section(rows: list[dict], summary: dict) -> list[str]:
    if not rows:
        return []
    by_mutant: dict = defaultdict(dict)
    src: dict = {}
    for r in rows:
        key = (r["benchmark"], r["task_id"], r["tag"])
        by_mutant[key][r["grader"]] = r["status"]
        src[key] = r["source"]

    out = ["## 2. Grader mutation testing", ""]
    out.append(
        "One-edit mutants of the reference solution. **Confirmed wrong** = on EvalPlus's "
        "base+plus inputs the mutant returns a wrong value or raises (hardened grader; "
        "timeouts are not counted as wrong). "
        "Mutants that pass every suite are *not* counted (may be equivalent)."
    )
    out.append("")
    out.append(
        "| Benchmark | Grader | Mutants | Accepted | Accepted & confirmed wrong | Tasks accepting a confirmed-wrong mutant |"
    )
    out.append("|---|---|---|---|---|---|")
    summary["mutation"] = {}
    examples: list[tuple] = []
    for b in sorted({k[0] for k in by_mutant}):
        keys = [k for k in by_mutant if k[0] == b]
        n_tasks = len(load(b))
        for g in ("original", "base"):
            accepted = [k for k in keys if by_mutant[k].get(g) == "pass"]
            wrong = [k for k in accepted if by_mutant[k].get("hardened", by_mutant[k].get("plus")) == "fail"]
            tasks_wrong = sorted({k[1] for k in wrong})
            out.append(
                f"| {BENCH_LABEL[b]} | {GRADER_LABEL[g]} | {len(keys)} | {len(accepted)} | "
                f"{len(wrong)} | {fmt_rate(len(tasks_wrong), n_tasks)} |"
            )
            summary["mutation"][f"{b}/{g}"] = {
                "mutants": len(keys),
                "accepted": len(accepted),
                "confirmed_wrong": len(wrong),
                "tasks_with_wrong_accepted": len(tasks_wrong),
                "n_tasks": n_tasks,
                "task_ids": tasks_wrong,
            }
            if g == "original":
                seen_tasks: set = set()
                for k in wrong:
                    if k[1] not in seen_tasks and len(examples) < 4 and by_mutant[k].get("base") == "pass":
                        seen_tasks.add(k[1])
                        examples.append(k)
        survived = [k for k in keys if all(by_mutant[k].get(g) == "pass" for g in ("original", "base", "plus"))]
        summary["mutation"][f"{b}/survived_all"] = len(survived)
    out.append("")
    if examples:
        out.append("### Examples: wrong solutions both shipped graders accept")
        out.append("")
        for b, tid, tag in examples:
            task = load(b)[tid]
            out.append(f"**{tid}** (`{tag.split(':', 1)[1]}`), passes original asserts and EvalPlus base, but returns a wrong value on an EvalPlus input:")
            out.append("")
            out.append("```diff")
            out.append(_unified(task.canonical, src[(b, tid, tag)]))
            out.append("```")
            out.append("")
    return out


def _reliability_section(rows: list[dict], summary: dict) -> list[str]:
    if not rows:
        return []
    runs: dict = defaultdict(list)
    for r in rows:
        runs[(r["benchmark"], r["task_id"], r["grader"])].append(r["status"])
    out = ["## 3. Reference-solution reliability", ""]
    out.append(
        "The benchmark's own reference solution, graded repeatedly on an oversubscribed "
        "machine (2x workers per core). A sound grader passes it every time."
    )
    out.append("")
    out.append(
        "| Benchmark | Grader | Always fails (broken) | Flaky (mixed verdicts) | "
        "Non-pass verdicts reported as `fail` / `timeout` |"
    )
    out.append("|---|---|---|---|---|")
    summary["reliability"] = {}
    for b in sorted({k[0] for k in runs}):
        for g in GRADER_LABEL:
            keys = [k for k in runs if k[0] == b and k[2] == g]
            if not keys:
                continue
            broken = sorted(k[1] for k in keys if all(s != "pass" for s in runs[k]))
            flaky = sorted(k[1] for k in keys if len(set(runs[k])) > 1)
            n_fail = sum(s == "fail" for k in keys for s in runs[k])
            n_timeout = sum(s == "timeout" for k in keys for s in runs[k])
            n = len(keys)
            out.append(
                f"| {BENCH_LABEL[b]} | {GRADER_LABEL[g]} | {len(broken)}/{n} {_ids(broken)} | "
                f"{len(flaky)}/{n} {_ids(flaky)} | {n_fail} / {n_timeout} |"
            )
            summary["reliability"][f"{b}/{g}"] = {
                "n": n,
                "broken": broken,
                "flaky": flaky,
                "flaky_detail": {k[1]: runs[k] for k in keys if k[1] in flaky},
            }
    out.append("")
    return out


def _ids(ids: list[str], limit: int = 6) -> str:
    if not ids:
        return ""
    shown = ", ".join(i.split("/")[-1] for i in ids[:limit])
    more = f", +{len(ids) - limit}" if len(ids) > limit else ""
    return f"({shown}{more})"


def _degenerate_section(summary: dict) -> list[str]:
    # Static scan: suites with no inputs, or whose expected outputs are all
    # identical (a constant-returning function passes every input).
    out = ["## 4. Degenerate test suites", ""]
    out.append(
        "A suite with zero inputs passes anything; a suite whose expected outputs are all "
        "identical passes a function that returns that constant."
    )
    out.append("")
    out.append("| Benchmark | Suite | Empty | Single distinct expected output |")
    out.append("|---|---|---|---|")
    summary["degenerate"] = {}
    for b in ("humaneval", "mbpp"):
        tasks = load(b).values()
        for split in ("base", "plus"):
            empty, constant = [], []
            for t in tasks:
                exp = t.expected_base if split == "base" else t.expected_plus
                if not exp:
                    empty.append(t.task_id)
                elif len({repr(x) for x in exp}) == 1 and len(exp) > 1:
                    constant.append(t.task_id)
            summary["degenerate"][f"{b}/{split}"] = {"empty": empty, "constant": constant}
            out.append(
                f"| {BENCH_LABEL[b]} | EvalPlus {split} | {len(empty)} {_ids(empty)} | "
                f"{len(constant)} {_ids(constant)} |"
            )
    out.append("")
    return out


def _power_section(summary: dict) -> list[str]:
    out = ["## 5. Statistical power: how big a gap is real?", ""]
    out.append(
        "Minimum detectable difference between two models' pass rates "
        "(two-proportion z-test, alpha 0.05, power 0.80)."
    )
    out.append("")
    out.append("| Benchmark | Tasks | MDE at 50% pass | MDE at 80% pass | MDE at 90% pass |")
    out.append("|---|---|---|---|---|")
    summary["power"] = {}
    for b in ("humaneval", "mbpp"):
        n = len(load(b))
        cells = [mde_two_proportions(n, p) for p in (0.5, 0.8, 0.9)]
        summary["power"][b] = {"n": n, "mde": cells}
        out.append(f"| {BENCH_LABEL[b]} | {n} | " + " | ".join(f"±{100 * c:.1f} pts" for c in cells) + " |")
    out.append("")
    return out


def write(results_dir: Path) -> None:
    summary: dict = {}
    lines = ["# evalaudit findings", ""]
    lines += _exploit_section(_read(results_dir / "exploits.json"), summary)
    lines += _mutation_section(_read(results_dir / "mutation.json"), summary)
    lines += _reliability_section(_read(results_dir / "reliability.json"), summary)
    lines += _degenerate_section(summary)
    lines += _power_section(summary)
    path = results_dir / "FINDINGS.md"
    with path.open("w", encoding=ENCODING) as f:
        f.write("\n".join(lines) + "\n")
    with (results_dir / "summary.json").open("w", encoding=ENCODING) as f:
        json.dump(summary, f, indent=2)
    print(f"  wrote {path}")


__all__ = ["write", "wilson"]
