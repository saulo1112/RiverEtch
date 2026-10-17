"""Whether a recomputed output agrees with the committed one when their bytes differ.

Floating-point results are not bit-identical across CPUs and operating systems: BLAS kernels and
vectorised ``log``/``exp`` round their last bits differently, so a coefficient printed to ten
decimals can come out one unit apart. A recomputed CSV, JSON or Markdown output agrees with the
committed one when everything but its numbers is identical, every integer is identical and every
other number differs by at most one unit in its last printed digit (or 0.001, when that digit is
coarser). A changed choice, level, count or label still fails.
"""

from __future__ import annotations

import re
from decimal import Decimal

# A number standing alone: not part of a word, a hash, a band name or a longer number.
NUMBER = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?(?!\w)")
COARSEST = -3  # the tolerance never exceeds one unit in the third decimal


def _integer(text: str) -> bool:
    return not any(c in text for c in ".eE")


def _last_digit(text: str) -> int:
    exponent = Decimal(text).as_tuple().exponent
    return exponent if isinstance(exponent, int) else 0


def disagreements(committed: str, recomputed: str, limit: int = 3) -> list[str]:
    """Where a recomputed output does not agree with the committed one.

    Args:
        committed: The committed file's text.
        recomputed: The recomputed file's text.
        limit: At most this many disagreements are listed.

    Returns:
        The disagreements (empty when the outputs agree).
    """
    shape = NUMBER.sub("#", committed)
    recomputed_shape = NUMBER.sub("#", recomputed)
    if shape != recomputed_shape:
        pairs = zip(shape.splitlines(), recomputed_shape.splitlines(), strict=False)
        for line, (ours, theirs) in enumerate(pairs, start=1):
            if ours != theirs:
                return [f"line {line} differs beyond its numbers: {ours.strip()[:80]!r}"]
        return ["the line count differs"]
    out = []
    for ours, theirs in zip(NUMBER.findall(committed), NUMBER.findall(recomputed), strict=True):
        if ours == theirs:
            continue
        if _integer(ours) and _integer(theirs):
            out.append(f"{ours} recomputed {theirs} (an integer)")
            continue
        place = min(_last_digit(ours), _last_digit(theirs), COARSEST)
        if abs(Decimal(ours) - Decimal(theirs)) > Decimal(1).scaleb(place):
            out.append(f"{ours} recomputed {theirs}")
    return out[:limit]
