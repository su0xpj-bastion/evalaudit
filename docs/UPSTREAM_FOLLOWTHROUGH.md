# Upstream follow-through

Filing an issue is the start, not the end. This page tracks the four EvalPlus issues from this audit
until each one is fixed upstream or has a documented workaround here.

Refresh the status with `python scripts/upstream_status.py --write` (read-only GitHub queries).

## Status

<!-- status:start -->
| Issue | Problem | State | Comments | Last response |
|---|---|---|---|---|
| [#333](https://github.com/evalplus/evalplus/issues/333) | grader trusts the solution (`__eq__`, frame peek) | open | 0 | none |
| [#334](https://github.com/evalplus/evalplus/issues/334) | HumanEval/32 unpassable in 0.3.1; reference fails oracle on master | open | 0 | none |
| [#335](https://github.com/evalplus/evalplus/issues/335) | timeouts graded as wrong answers | open | 0 | none |
| [#336](https://github.com/evalplus/evalplus/issues/336) | empty / degenerate MBPP+ plus suites | open | 0 | none |

Upstream activity: last commit 2025-10-02, latest release v0.3.1 (2024-10-20).
<!-- status:end -->

## What the upstream signal says

EvalPlus is lightly maintained: the latest PyPI release (v0.3.1) is from October 2024, and the last commit
on `master` is from October 2025. Of the 63 issues opened since September 2024, 18 are closed and 24
have any reply (measured 2026-11-20). So waiting is not a plan. Every finding needs a path that does not
depend on a maintainer answering.

## Action items

| ID | Issue | Action | Owner | Due | State |
|---|---|---|---|---|---|
| F-1 | all | Workaround available without upstream: `hardened.py` grader (0 of 542 cheaters pass; reference solutions still pass) | maintainer | — | done, in `evalaudit/hardened.py` + `tests/` |
| F-2 | all | Wait 14 days for a maintainer reply before escalating | maintainer | 2026-12-01 | open |
| F-3 | #333 | Offer a PR: keep `expected` in the trusted parent, accept only plain builtin data from the child | maintainer | 2026-12-08 | open, needs a go-ahead before posting |
| F-4 | #334 | Ask for a patch release: the bookkeeping fix is on `master` but unreleased, so every `pip install` user scores HumanEval/32 as 0 | maintainer | 2026-12-08 | open, needs a go-ahead before posting |
| F-5 | #335 | Offer a PR: report timeouts as a separate status, not as a wrong answer | maintainer | 2026-12-15 | open |
| F-6 | #336 | Offer a PR: fill or flag the 7 degenerate MBPP+ plus suites | maintainer | 2026-12-15 | open |
| F-7 | all | If there is still no reply by 2026-12-15, publish the hardened grader as a drop-in and say so on each issue | maintainer | 2026-12-15 | open |

Rule: anything posted upstream (comments, PRs) is a public action and is approved one at a time.
