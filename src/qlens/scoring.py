"""Tiers, scores and labels (SPEC section 5). Scores live in calibration.json."""

from __future__ import annotations

import json
from functools import lru_cache
from importlib import resources
from pathlib import Path

TIERS = ("D3", "D2", "S", "S-indirect", "S-unresolved", "S-refuted")


def label(score: float) -> str:
    if score >= 0.9:
        return "EXTRACTED"
    if score >= 0.5:
        return "INFERRED"
    return "AMBIGUOUS"


@lru_cache
def load_scores(path: str | None = None) -> dict[str, float]:
    p = Path(path) if path else Path(str(resources.files("qlens") / "calibration.json"))
    d = json.loads(p.read_text())
    missing = [t for t in TIERS if t not in d]
    if missing:
        raise ValueError(f"calibration file {p} lacks tiers {missing}")
    return {t: float(d[t]) for t in TIERS}


DEFAULT_SCORES = load_scores()


def score_for(tier: str, scores: dict[str, float] | None = None) -> float:
    return (scores or DEFAULT_SCORES)[tier]
