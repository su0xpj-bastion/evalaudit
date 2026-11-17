from __future__ import annotations

import math

Z_95 = 1.959963984540054
Z_80_POWER = 0.8416212335729143


def wilson(k: int, n: int, z: float = Z_95) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion."""
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, center - half), min(1.0, center + half))


def mde_two_proportions(n: int, p: float) -> float:
    """Minimum detectable difference between two models' pass rates on the
    same n-task benchmark (independent two-proportion z-test, alpha=0.05
    two-sided, power=0.80). Conservative: ignores pairing."""
    if n <= 0:
        return 1.0
    return (Z_95 + Z_80_POWER) * math.sqrt(2 * p * (1 - p) / n)


def fmt_rate(k: int, n: int) -> str:
    lo, hi = wilson(k, n)
    return f"{k}/{n} = {100 * k / n:.1f}% (95% CI {100 * lo:.1f}-{100 * hi:.1f})"
