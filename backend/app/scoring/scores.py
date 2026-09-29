"""
Scoring — Fidelity, Utility (TSTR), and Privacy Risk Indicators.

Every score has a published formula shown in the UI.
Every score is a heuristic measurement, not a certification.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd
from scipy import stats
from sklearn.neighbors import NearestNeighbors
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.metrics import balanced_accuracy_score, r2_score

EPOCH = pd.Timestamp("1970-01-01")


def _to_numeric(s: pd.Series, kind: str) -> np.ndarray:
    if kind in ("date", "datetime"):
        return (pd.to_datetime(s, errors="coerce") - EPOCH).dt.total_seconds().dropna().to_numpy()
    return pd.to_numeric(s, errors="coerce").dropna().to_numpy()


def _as_num_series(df: pd.DataFrame, c: str, kind: str) -> pd.Series:
    if kind in ("date", "datetime"):
        return (pd.to_datetime(df[c], errors="coerce") - EPOCH).dt.total_seconds()
    return pd.to_numeric(df[c], errors="coerce")


# ── FIDELITY ──────────────────────────────────────────────────────

def column_score(real: pd.Series, synth: pd.Series, kind: str) -> float:
    """Per-column similarity: 1 − KS (numeric) or 1 − TVD (categorical)."""
    if kind == "cat":
        p = real.dropna().astype(str).value_counts(normalize=True)
        q = synth.dropna().astype(str).value_counts(normalize=True)
        idx = p.index.union(q.index)
        tvd = 0.5 * np.abs(
            p.reindex(idx, fill_value=0).to_numpy() -
            q.reindex(idx, fill_value=0).to_numpy()
        ).sum()
        return float(1 - tvd)

    if kind == "bool":
        p_real = real.dropna().astype(str).str.lower().isin(["true", "1", "yes", "t", "y"]).mean()
        p_synth = synth.dropna().astype(str).str.lower().isin(["true", "1", "yes", "t", "y"]).mean()
        return float(1 - abs(p_real - p_synth))

    a = _to_numeric(real, kind)
    b = _to_numeric(synth, kind)
    if len(a) == 0 or len(b) == 0:
        return 0.0
    return float(1 - stats.ks_2samp(a, b).statistic)


def fidelity_score(real: pd.DataFrame, synth: pd.DataFrame,
                   kinds: dict[str, str]) -> dict:
    """Composite fidelity score: 60% column similarity + 40% correlation similarity.

    Formula: Fidelity = 100 × (0.6 × mean(column_scores) + 0.4 × mean(pair_scores))
    """
    scorable = ("int", "num", "date", "datetime", "cat", "money", "bool")
    cols = [c for c in real.columns if kinds.get(c) in scorable and c in synth.columns]

    col_scores = {c: column_score(real[c], synth[c], kinds[c]) for c in cols}

    # Pairwise correlation similarity
    nums = [c for c in cols if kinds[c] in ("int", "num", "date", "datetime", "money")]
    pair_scores = []
    if len(nums) > 1:
        def _corr_matrix(df):
            return pd.DataFrame({c: _as_num_series(df, c, kinds[c]) for c in nums}).corr(method="spearman").to_numpy()

        cr = np.nan_to_num(_corr_matrix(real))
        cs = np.nan_to_num(_corr_matrix(synth))
        diffs = np.abs(cr - cs)
        pair_scores = list(1 - diffs[np.triu_indices(len(nums), 1)] / 2)

    col_mean = float(np.mean(list(col_scores.values()))) if col_scores else 0.0
    pair_mean = float(np.mean(pair_scores)) if pair_scores else col_mean
    score = round(100 * (0.6 * col_mean + 0.4 * pair_mean), 1)

    # Worst columns
    sorted_cols = sorted(col_scores.items(), key=lambda x: x[1])
    worst = sorted_cols[:5]

    return {
        "score": score,
        "columns": {k: round(v, 3) for k, v in col_scores.items()},
        "pair_mean": round(pair_mean, 3),
        "worst_columns": [{"column": k, "score": round(v, 3)} for k, v in worst],
        "formula": "100 × (0.6 × mean(1−KS or 1−TVD per col) + 0.4 × mean(1−|Δρ|/2 per pair))",
        "note": "Heuristic similarity measure, not a certification.",
    }


# ── UTILITY (TSTR) ───────────────────────────────────────────────

def tstr_score(train: pd.DataFrame, synth: pd.DataFrame,
               holdout: Optional[pd.DataFrame], target: str,
               kinds: dict[str, str]) -> dict:
    """Train-on-Synthetic Test-on-Real utility score.

    Utility = metric(TSTR) / metric(TRTR)
    """
    if holdout is None or len(holdout) < 4:
        return {"skipped": True, "reason": "Holdout too small (< 4 rows) or missing."}
    if kinds.get(target) not in ("cat", "int", "num", "money"):
        return {"skipped": True, "reason": f"Target '{target}' must be numeric or categorical."}

    feats = [c for c in train.columns
             if c != target and kinds.get(c) in ("int", "num", "cat", "money")
             and c in synth.columns and c in holdout.columns]
    if not feats:
        return {"skipped": True, "reason": "No usable feature columns."}

    is_clf = kinds[target] == "cat"
    cat_cols = {c: sorted(set(train[c].astype(str)) | set(synth[c].astype(str)) | set(holdout[c].astype(str)))
                for c in feats if kinds[c] == "cat"}

    def _encode(df):
        X = pd.DataFrame(index=df.index)
        for c in feats:
            if kinds[c] == "cat":
                X[c] = pd.Categorical(df[c].astype(str), categories=cat_cols[c]).codes
            else:
                X[c] = pd.to_numeric(df[c], errors="coerce")
        return X.fillna(0)

    def _train_eval(tr_df):
        y = tr_df[target].astype(str) if is_clf else pd.to_numeric(tr_df[target], errors="coerce")
        ok = y.notna()
        Model = HistGradientBoostingClassifier if is_clf else HistGradientBoostingRegressor
        m = Model(max_iter=100, random_state=0)
        m.fit(_encode(tr_df)[ok], y[ok])
        yt = holdout[target].astype(str) if is_clf else pd.to_numeric(holdout[target], errors="coerce")
        ok_h = yt.notna()
        pred = m.predict(_encode(holdout)[ok_h])
        return balanced_accuracy_score(yt[ok_h], pred) if is_clf else max(0.0, r2_score(yt[ok_h], pred))

    try:
        trtr = _train_eval(train)
        tstr = _train_eval(synth)
    except Exception as e:
        return {"skipped": True, "reason": f"Model training failed: {e}"}

    utility = round(tstr / trtr, 3) if trtr > 0 else None
    return {
        "skipped": False,
        "target": target,
        "task_type": "classification" if is_clf else "regression",
        "trtr": round(trtr, 3),
        "tstr": round(tstr, 3),
        "utility": utility,
        "features_used": feats,
        "note": "Utility = TSTR_metric / TRTR_metric. Higher is better.",
    }


# ── PRIVACY RISK ─────────────────────────────────────────────────

def exact_match_rate(train: pd.DataFrame, synth: pd.DataFrame) -> float:
    """Fraction of synthetic rows that exactly match a training row."""
    cols = [c for c in train.columns if c in synth.columns]
    if not cols:
        return 0.0
    train_keys = set(train[cols].astype(str).agg("|".join, axis=1))
    synth_keys = synth[cols].astype(str).agg("|".join, axis=1)
    return float(synth_keys.isin(train_keys).mean())


def dcr_ratio(train: pd.DataFrame, holdout: Optional[pd.DataFrame],
              synth: pd.DataFrame, kinds: dict[str, str]) -> Optional[float]:
    """Distance-to-Closest-Record ratio: synth→train vs holdout→train.

    If synthetic is much closer to train than holdout is, possible memorization.
    """
    if holdout is None:
        return None
    nums = [c for c in train.columns if kinds.get(c) in ("int", "num", "money")
            and c in synth.columns and c in holdout.columns]
    if not nums:
        return None

    mu = train[nums].apply(pd.to_numeric, errors="coerce").mean()
    sd = train[nums].apply(pd.to_numeric, errors="coerce").std().replace(0, 1)

    def _norm(df):
        return ((df[nums].apply(pd.to_numeric, errors="coerce").fillna(mu) - mu) / sd).to_numpy()

    nn = NearestNeighbors(n_neighbors=1, algorithm="auto").fit(_norm(train))
    s = synth.sample(min(len(synth), 2000), random_state=0)
    ds = nn.kneighbors(_norm(s))[0].ravel()
    dh = nn.kneighbors(_norm(holdout))[0].ravel()
    return float(np.median(ds) / max(np.median(dh), 1e-9))


def privacy_indicators(train: pd.DataFrame, holdout: Optional[pd.DataFrame],
                       synth: pd.DataFrame, kinds: dict[str, str]) -> dict:
    """Complete privacy risk assessment."""
    exact = exact_match_rate(train, synth)
    ratio = dcr_ratio(train, holdout, synth, kinds)

    level = "Low"
    if exact > 0.01 or (ratio is not None and ratio < 0.5):
        level = "Elevated"
    elif exact > 0 or (ratio is not None and ratio < 0.8):
        level = "Moderate"

    return {
        "exact_match_rate": round(exact, 4),
        "dcr_ratio": round(ratio, 3) if ratio is not None else None,
        "level": level,
        "note": "Risk indicators from specific tests. Not proof of anonymity.",
    }


# ── COMBINED SCORECARD ────────────────────────────────────────────

def compute_scorecard(
    real_df: Optional[pd.DataFrame],
    synth_df: pd.DataFrame,
    kinds: dict[str, str],
    train_df: Optional[pd.DataFrame] = None,
    holdout_df: Optional[pd.DataFrame] = None,
    target_col: Optional[str] = None,
    mode: str = "schema_only",
) -> dict:
    """Compute the full scorecard — fidelity, utility, privacy."""
    result: dict = {"generation_mode": mode}

    if real_df is not None and mode == "sample_conditioned":
        result["fidelity"] = fidelity_score(real_df, synth_df, kinds)
        if target_col:
            t_df = train_df if train_df is not None else real_df
            result["utility"] = tstr_score(
                t_df, synth_df, holdout_df, target_col, kinds
            )
        if train_df is not None:
            result["privacy"] = privacy_indicators(
                train_df, holdout_df, synth_df, kinds
            )
    else:
        result["fidelity"] = None
        result["utility"] = None
        result["privacy"] = None
        result["note"] = ("No source data to compare against. "
                          "Showing constraint conformance only.")

    return result
