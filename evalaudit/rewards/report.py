from __future__ import annotations

# Writes results/rewards/FINDINGS.md and summary.json from the raw rows.

import json
from collections import defaultdict
from pathlib import Path

from evalaudit.stats import fmt_rate
from evalaudit.rewards.tasks import NATIVE

ENCODING = "utf-8"
UPSTREAM = ["verl", "livecodebench", "rllm"]
GRADER_NAMES = {
    "verl": "verl `prime_code`",
    "livecodebench": "LiveCodeBench",
    "rllm": "rllm (DeepCoder)",
    "hardened": "hardened (ours)",
    "open_r1": "open-r1 `code_reward`",
    "bigcodebench": "BigCodeBench",
}
FAKES = ["null", "always_equal", "peek", "vanish"]


def _load(out: Path, name: str) -> list[dict] | None:
    p = out / name
    if not p.exists():
        return None
    with p.open(encoding=ENCODING) as f:
        return json.load(f)


def _rate(k: int, n: int) -> str:
    return "n/a" if n == 0 else fmt_rate(k, n)


def _short(k: int, n: int) -> str:
    return "–" if n == 0 else f"{k}/{n} ({100 * k / n:.0f}%)"


def _apps_section(rows: list[dict], summary: dict) -> list[str]:
    by = defaultdict(lambda: defaultdict(dict))  # (dataset, grader) -> task -> solution -> passed
    modes = {}
    for r in rows:
        by[(r["dataset"], r["grader"])][r["task_id"]][r["solution"]] = r["passed"]
        modes[r["task_id"]] = r["mode"]
    datasets = sorted({r["dataset"] for r in rows}, key=lambda d: list(NATIVE).index(d) if d in NATIVE else 99)
    graders = [g for g in UPSTREAM + ["hardened"] if any(k[1] == g for k in by)]

    out = ["## 1. Fakes that solve nothing", ""]
    out.append(
        "Share of tasks where at least one fake earns the full reward. A fake never reads the problem; "
        "the same text is submitted for every task. `null` is the control and should pass nothing."
    )
    out.append("")
    out.append("| Dataset (tasks) | " + " | ".join(GRADER_NAMES[g] for g in graders) + " | null control (all graders) |")
    out.append("|---|" + "---|" * (len(graders) + 1))
    summary["any_fake"] = {}
    for d in datasets:
        n_tasks = len(by[(d, graders[0])])
        cells = []
        null_pass = 0
        for g in graders:
            t = by[(d, g)]
            k = sum(any(v.get(f) for f in FAKES if f != "null") for v in t.values())
            null_pass += sum(bool(v.get("null")) for v in t.values())
            mark = "**" if NATIVE.get(d) == g else ""
            cells.append(f"{mark}{_short(k, len(t))}{mark}")
            summary["any_fake"][f"{d}|{g}"] = [k, len(t)]
        out.append(f"| {d} ({n_tasks}) | " + " | ".join(cells) + f" | {null_pass} passes |")
    out.append("")
    out.append("Bold marks the grader each dataset was built for (verl trains on Eurus; DeepCoder trains with rllm).")
    out.append("")

    out.append("### By fake and task type")
    out.append("")
    out.append("| Dataset | Type | Fake | " + " | ".join(GRADER_NAMES[g] for g in graders) + " |")
    out.append("|---|---|---|" + "---|" * len(graders))
    for d in datasets:
        for mode in ("call", "stdio"):
            for f in FAKES:
                cells = []
                seen = False
                for g in graders:
                    t = [v for tid, v in by[(d, g)].items() if modes[tid] == mode and f in v]
                    if t:
                        seen = True
                    cells.append(_short(sum(v[f] for v in t), len(t)))
                if seen:
                    out.append(f"| {d} | {mode} | {f} | " + " | ".join(cells) + " |")
    out.append("")

    # Reference solutions: does the hardened grader agree with the upstream graders?
    out.append("## 2. Real solutions: does the fix reject honest code?")
    out.append("")
    out.append(
        "TACO and PrimeIntellect ship a reference solution per task. Each one is graded by every grader. "
        "A good fix should pass the same references the upstream graders pass."
    )
    out.append("")
    out.append("| Dataset | " + " | ".join(GRADER_NAMES[g] for g in graders) + " |")
    out.append("|---|" + "---|" * len(graders))
    summary["reference"] = {}
    for d in datasets:
        refs = {g: {tid: v["reference"] for tid, v in by[(d, g)].items() if "reference" in v} for g in graders}
        if not refs[graders[0]]:
            continue
        cells = []
        for g in graders:
            k, n = sum(refs[g].values()), len(refs[g])
            cells.append(_short(k, n))
            summary["reference"][f"{d}|{g}"] = [k, n]
        out.append(f"| {d} | " + " | ".join(cells) + " |")
        if "hardened" in refs:
            for g in UPSTREAM:
                if g not in refs:
                    continue
                both = sum(refs[g][t] and refs["hardened"][t] for t in refs[g])
                up_only = [t for t in refs[g] if refs[g][t] and not refs["hardened"][t]]
                hard_only = [t for t in refs[g] if refs["hardened"][t] and not refs[g][t]]
                summary["reference"][f"{d}|agree|{g}"] = {"both_pass": both, "upstream_only": up_only, "hardened_only": hard_only}
    out.append("")
    lines = []
    for key, v in summary["reference"].items():
        if "|agree|" in key:
            d, _, g = key.split("|")
            lines.append(
                f"- {d}, hardened vs {GRADER_NAMES[g]}: both pass {v['both_pass']}; "
                f"only {GRADER_NAMES[g]} passes {len(v['upstream_only'])}; only hardened passes {len(v['hardened_only'])}."
            )
    out += lines
    out.append("")
    return out


def _bcb_section(rows: list[dict], summary: dict) -> list[str]:
    by = defaultdict(dict)
    for r in rows:
        by[r["task_id"]][r["solution"]] = r["passed"]
    n = len(by)
    ref_ok = [t for t, v in by.items() if v.get("reference")]
    out = ["## 3. BigCodeBench", ""]
    out.append(
        "BigCodeBench runs the solution and its unittest suite in the same module. "
        "`silence` replaces `unittest.TestResult.addFailure` and `addError` with no-ops (plus import stubs so a "
        "missing library can't crash the test module first). `stub_only` is the stubs alone, as a control."
    )
    out.append("")
    out.append("| Solution | All tasks | Tasks whose reference passes here |")
    out.append("|---|---|---|")
    summary["bcb"] = {}
    for s in ["reference", "null", "stub_only", "silence"]:
        k_all = sum(bool(v.get(s)) for v in by.values())
        k_ref = sum(bool(by[t].get(s)) for t in ref_ok)
        summary["bcb"][s] = {"all": [k_all, n], "ref_ok": [k_ref, len(ref_ok)]}
        out.append(f"| {s} | {_rate(k_all, n)} | {_rate(k_ref, len(ref_ok))} |")
    out.append("")
    return out


def _openr1_section(rows: list[dict], summary: dict) -> list[str]:
    by = defaultdict(lambda: defaultdict(dict))
    for r in rows:
        by[r["grader"]][r["task_id"]][r["solution"]] = r["passed"]
    o, h = by["open_r1"], by["hardened"]
    tasks = [t for t in o if o[t].get("reference")]
    accepted_wrong = [t for t in tasks if o[t].get("first_line_only") and h.get(t, {}).get("reference") and not h[t].get("first_line_only")]
    out = ["## 4. open-r1 `code_reward`", ""]
    out.append(
        "open-r1 runs each test in a separate `python3 -c` process and compares stdout in the parent, so the "
        "in-process fakes can't reach the answers. But it compares lines with `zip`, which stops at the shorter "
        "side. `first_line_only` runs the real reference and prints only the first line of its output."
    )
    out.append("")
    out.append("| Solution | open-r1 | hardened |")
    out.append("|---|---|---|")
    summary["openr1"] = {}
    for s in ["reference", "null", "peek", "first_line_only"]:
        ko = sum(bool(o[t].get(s)) for t in o)
        kh = sum(bool(h[t].get(s)) for t in h)
        summary["openr1"][s] = {"open_r1": [ko, len(o)], "hardened": [kh, len(h)]}
        out.append(f"| {s} | {_rate(ko, len(o))} | {_rate(kh, len(h))} |")
    out.append("")
    out.append(
        f"Of the {len(tasks)} tasks whose reference passes open-r1, the truncated program also gets full reward on "
        f"{_rate(len(accepted_wrong), len(tasks))} while the hardened grader rejects it (confirmed wrong output)."
    )
    summary["openr1"]["accepted_wrong"] = [len(accepted_wrong), len(tasks)]
    out.append("")
    return out


def _diagnosis_section(diag: list[dict] | None, ften: dict | None) -> list[str]:
    out = ["## 5. Why the graders disagree on real solutions", ""]
    if diag:
        from collections import Counter

        def bucket(r: dict) -> str:
            meta = json.dumps(r["lcb_detail"].get("meta", {}))
            if r["cause"] == "agree when idle":
                return "agree when re-run on an idle machine"
            if r["idle_upstream"]:
                return "upstream passes, hardened fails"
            if "fast stdin" in r["cause"]:
                return "fast stdin I/O (fileno / os.read / stdin.buffer) crashes on the mocked stdin"
            if "NameError" in meta:
                return "program wrapped in a function: module-level names and `global` break"
            if "exit()" in r["cause"]:
                return "exit() / quit() disabled by reliability_guard"
            if "MockStdin" in meta or "has no attribu" in meta:
                return "other mocked-stdin incompatibility"
            return "other upstream runtime or comparison difference"

        c = Counter((r["grader"], bucket(r)) for r in diag)
        out.append("Every reference where the hardened grader and an upstream grader disagreed was re-run alone on an idle machine (`scripts/diagnose_rewards.py`).")
        out.append("")
        out.append("| Grader | Cause | References |")
        out.append("|---|---|---|")
        for (g, b), n in sorted(c.items(), key=lambda kv: (kv[0][0], -kv[1])):
            out.append(f"| {GRADER_NAMES[g]} | {b} | {n} |")
        out.append("")
    if ften:
        rows = ften["full_reward_but_fails_full_check"]
        k, n = ften["eurus_more_than_10_tests"]
        out.append(
            f"verl first-10-tests rule (`scripts/verl_first_ten.py`): {len(rows)} reference programs fail verl's own "
            f"all-tests check yet get score 1.0. A toy program that is wrong on tests 11-12 scores {ften['toy']['score']}. "
            f"{k} of {n} Eurus validation tasks have more than 10 tests."
        )
        out.append("")
    return out


def write(out: Path) -> None:
    summary: dict = {}
    md = ["# RL code-reward audit: findings", ""]
    prov = _load(out, "provenance.json")
    apps = _load(out, "apps.json")
    if apps:
        md += _apps_section(apps, summary)
    bcb = _load(out, "bcb.json")
    if bcb:
        md += _bcb_section(bcb, summary)
    o1 = _load(out, "openr1.json")
    if o1:
        md += _openr1_section(o1, summary)
    diag, ften = _load(out, "reference_diagnosis.json"), _load(out, "verl_first_ten.json")
    if diag or ften:
        md += _diagnosis_section(diag, ften)
    if prov:
        md += ["## Provenance", "", "Grader code, unmodified, at these commits:", ""]
        for name, p in prov.items():
            md.append(f"- {name}: {p['repo']} @ `{p['commit'][:12]}`")
        md.append("")
        md.append("File hashes are in `provenance.json`.")
        md.append("")
    (out / "FINDINGS.md").write_text("\n".join(md), encoding=ENCODING)
    with (out / "summary.json").open("w", encoding=ENCODING) as f:
        json.dump(summary, f, indent=2)
    print(f"  wrote {out / 'FINDINGS.md'}")
