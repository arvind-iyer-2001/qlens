"""Tiers, default scores and labels (SPEC section 5)."""

from __future__ import annotations

DEFAULT_SCORES = {
    "D3": 0.98,
    "D2": 0.97,
    "S": 0.92,
    "S-indirect": 0.80,
    "S-unresolved": 0.35,
    "S-refuted": 0.10,
}


def label(score: float) -> str:
    if score >= 0.9:
        return "EXTRACTED"
    if score >= 0.5:
        return "INFERRED"
    return "AMBIGUOUS"


def score_for(tier: str, scores: dict[str, float] | None = None) -> float:
    return (scores or DEFAULT_SCORES)[tier]
