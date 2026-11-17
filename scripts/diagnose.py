"""Re-grade suspicious reference solutions on an idle machine, one at a time,
and time them, to separate 'broken task' from 'load-sensitive time limit'."""
from __future__ import annotations

import sys
import time

from evalaudit.data import load
from evalaudit.graders import grade
from evalaudit.runner import use_fork

if __name__ == "__main__":
    use_fork()
    for spec in sys.argv[1:]:
        bench, tid, grader = spec.split(":")
        task = load(bench)[tid]
        runs = []
        for _ in range(3):
            t0 = time.time()
            runs.append((grade(task, task.canonical, grader), round(time.time() - t0, 2)))
        ref = task.plus_time if grader == "plus" else task.base_time
        print(f"{tid:14s} {grader:8s} idle={runs} ref_total={sum(ref):.2f}s max_input={max(ref) if ref else 0:.3f}s")
