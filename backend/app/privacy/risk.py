"""
Privacy Risk Assessment — centralized privacy risk indicators.

Wraps the scoring functions into a clean API for the privacy/ module.
Re-exports from scoring/scores.py and adds k-anonymity analysis.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from app.scoring.scores import (
    exact_match_rate,
    dcr_ratio,
    privacy_indicators,
)


def k_anonymity(df: pd.DataFrame, quasi_columns: list[str]) -> dict:
    """Compute k-anonymity over quasi-identifier columns.
    
    k = smallest group size when grouping by quasi-identifiers.
    Higher k = better privacy. k < 5 is concerning.
    """
    valid_cols = [c for c in quasi_columns if c in df.columns]
    if not valid_cols:
        return {"k": None, "note": "No quasi-identifier columns specified."}

    groups = df.groupby([df[c].astype(str) for c in valid_cols]).size()

    if len(groups) == 0:
        return {"k": None, "note": "No groups found."}

    min_k = int(groups.min())
    pct_below_5 = float((groups < 5).mean())
    pct_below_10 = float((groups < 10).mean())

    return {
        "k": min_k,
        "total_groups": len(groups),
        "pct_groups_below_5": round(pct_below_5, 4),
        "pct_groups_below_10": round(pct_below_10, 4),
        "quasi_columns": valid_cols,
        "risk": "high" if min_k <= 1 else "moderate" if min_k <= 4 else "low",
        "note": ("k-anonymity measures the smallest group when grouping by "
                 "quasi-identifiers. k < 5 means some individuals may be "
                 "identifiable from the combination of these fields."),
    }


def l_diversity(df: pd.DataFrame, quasi_columns: list[str],
                 sensitive_column: str) -> dict:
    """Compute l-diversity: how diverse is the sensitive attribute within each QI group?
    
    l = minimum number of distinct sensitive values in any group.
    Higher l = better privacy for sensitive attributes.
    """
    valid_qi = [c for c in quasi_columns if c in df.columns]
    if not valid_qi or sensitive_column not in df.columns:
        return {"l": None, "note": "Missing columns."}

    groups = df.groupby([df[c].astype(str) for c in valid_qi])[sensitive_column]
    l_values = groups.nunique()

    if len(l_values) == 0:
        return {"l": None, "note": "No groups found."}

    min_l = int(l_values.min())
    return {
        "l": min_l,
        "total_groups": len(l_values),
        "quasi_columns": valid_qi,
        "sensitive_column": sensitive_column,
        "risk": "high" if min_l <= 1 else "moderate" if min_l <= 2 else "low",
        "note": ("l-diversity measures the minimum number of distinct sensitive values "
                 "within any quasi-identifier group."),
    }


def full_privacy_report(
    train: pd.DataFrame,
    synth: pd.DataFrame,
    holdout: Optional[pd.DataFrame],
    kinds: dict[str, str],
    quasi_columns: list[str] | None = None,
    sensitive_columns: list[str] | None = None,
) -> dict:
    """Complete privacy risk report combining all metrics."""
    quasi_columns = quasi_columns or []
    sensitive_columns = sensitive_columns or []

    report = {
        "indicators": privacy_indicators(train, holdout, synth, kinds),
    }

    if quasi_columns:
        report["k_anonymity"] = k_anonymity(synth, quasi_columns)
        for sc in sensitive_columns:
            report[f"l_diversity_{sc}"] = l_diversity(synth, quasi_columns, sc)

    report["disclaimer"] = (
        "These are heuristic risk indicators from specific statistical tests. "
        "They are NOT proof of anonymity or compliance with any regulation. "
        "Consult a privacy specialist for production use."
    )

    return report
