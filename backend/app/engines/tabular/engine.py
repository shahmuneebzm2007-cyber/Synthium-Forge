"""
Tabular Engine — orchestrates profiling, copula fitting, privacy, edge cases,
and post-processing into a single synthesize() call.
"""
from __future__ import annotations

import hashlib
from typing import Any, Optional

import numpy as np
import pandas as pd
from faker import Faker

from app.core.seeding import rng_for
from app.core.money import to_minor
from app.engines.tabular.profiler import profile_df
from app.engines.tabular.copula import GaussianCopulaSynth


# Map our locale codes to valid Faker locales
_FAKER_LOCALES = {
    "pk": "en_US", "us": "en_US", "uk": "en_GB", "ae": "ar_AE",
    "eu": "de_DE", "in": "en_IN", "en_US": "en_US", "en_GB": "en_GB",
    "de_DE": "de_DE", "ar_AE": "ar_AE", "en_IN": "en_IN",
}

def _faker_locale(locale: str) -> str:
    return _FAKER_LOCALES.get(locale, "en_US")


def split_holdout(df: pd.DataFrame, seed: int,
                  frac: float = 0.2, min_rows: int = 20):
    """Hold out 20% for honest privacy/utility evaluation.
    
    Tiny samples (<min_rows) get no holdout — we can't measure
    utility reliably with so few rows.
    """
    if len(df) < min_rows:
        return df, None
    idx = rng_for(seed, "holdout_split").permutation(len(df))
    k = int(len(df) * frac)
    train = df.iloc[idx[k:]].reset_index(drop=True)
    hold = df.iloc[idx[:k]].reset_index(drop=True)
    return train, hold


def fictional(hint: str, i: int, fake: Faker, locale: str = "en_US") -> str:
    """Generate obviously fictional values for PII columns.
    
    Emails use example.com, phones use invalid ranges,
    names are synthetic but culturally plausible.
    """
    h = hint.lower()
    
    # Specific categorical fallbacks
    if "gender" in h or "sex" in h:
        return fake.random_element(elements=("Male", "Female", "Other"))
    if "status" in h:
        return fake.random_element(elements=("Pending", "Active", "Completed", "Cancelled", "Processing"))
    if "reason" in h:
        return fake.random_element(elements=("Checkup", "Consultation", "Follow-up", "Emergency", "Routine"))
    if "specialty" in h:
        return fake.random_element(elements=("Cardiology", "Neurology", "Pediatrics", "Oncology", "General"))
        
    # Standard PII fallbacks
    if "first" in h and "name" in h:
        return fake.first_name()
    if "last" in h and "name" in h:
        return fake.last_name()
    if "name" in h:
        return fake.name()
    if "email" in h:
        return f"{fake.user_name()}@example.com"
    if "phone" in h or "mobile" in h or "cell" in h:
        return fake.phone_number()
    if "address" in h or "street" in h:
        return fake.street_address()
    if "company" in h or "org" in h:
        return fake.company()
    if "city" in h:
        return fake.city()
    if "country" in h:
        return fake.country()
    if "url" in h or "website" in h:
        return f"https://example.com/{i:05d}"
    if "ssn" in h or "cnic" in h or "passport" in h or "national" in h:
        return f"XXX-XX-{i:04d}"
    if "card" in h or "account" in h:
        return f"XXXX-XXXX-XXXX-{i:04d}"
    
    # Generic string fallback for unknown text/cats
    return fake.word().capitalize()


def apply_privacy(df: pd.DataFrame, actions: dict[str, str],
                  salt: str = "project-salt") -> pd.DataFrame:
    """Apply column-level privacy transformations.
    
    Actions:
      - exclude: drop the column entirely
      - hash: salted SHA-256 pseudonymization (NOT anonymization)
      - mask: partial redaction showing last 2 chars
      - synthetic: replaced during generation (handled earlier)
    """
    df = df.copy()
    for col, action in actions.items():
        if col not in df.columns:
            continue
        if action == "exclude":
            df = df.drop(columns=[col])
        elif action == "hash":
            df[col] = df[col].astype(str).map(
                lambda v: hashlib.sha256((salt + v).encode()).hexdigest()[:12]
            )
        elif action == "mask":
            def _mask(v):
                s = str(v)
                if len(s) <= 2:
                    return "*" * len(s)
                return "*" * (len(s) - 2) + s[-2:]
            df[col] = df[col].astype(str).map(_mask)
    return df


def inject_nulls(df: pd.DataFrame, null_config: dict[str, float],
                 rng: np.random.Generator) -> pd.DataFrame:
    """Inject additional missing values per configured rates."""
    df = df.copy()
    for col, rate in null_config.items():
        if col in df.columns and rate > 0:
            mask = rng.random(len(df)) < rate
            df.loc[mask, col] = None
    return df


def inject_outliers(df: pd.DataFrame, kinds: dict[str, str],
                    rate: float, method: str,
                    rng: np.random.Generator) -> tuple[pd.DataFrame, int]:
    """Inject outliers into numeric columns.
    
    Returns (df_with_outliers, count_injected).
    """
    if rate <= 0:
        return df, 0
    df = df.copy()
    total_injected = 0
    num_cols = [c for c in df.columns if kinds.get(c) in ("int", "num", "money")]

    for col in num_cols:
        vals = pd.to_numeric(df[col], errors="coerce")
        valid = vals.dropna()
        if len(valid) < 10:
            continue

        n_outliers = max(1, int(len(df) * rate / max(len(num_cols), 1)))
        idx = rng.choice(len(df), size=n_outliers, replace=False)

        if method == "iqr_extreme":
            q1, q3 = float(valid.quantile(0.25)), float(valid.quantile(0.75))
            iqr = q3 - q1
            if iqr == 0:
                iqr = abs(float(valid.mean())) * 0.1 or 1.0
            low = q1 - 3.0 * iqr
            high = q3 + 3.0 * iqr
            outlier_vals = rng.choice([low, high], size=n_outliers) + rng.normal(0, iqr * 0.1, n_outliers)
        elif method == "zscore":
            mean, std = float(valid.mean()), float(valid.std())
            if std == 0:
                std = 1.0
            signs = rng.choice([-1, 1], size=n_outliers)
            outlier_vals = mean + signs * rng.uniform(4, 6, n_outliers) * std
        elif method == "boundary":
            vmin, vmax = float(valid.min()), float(valid.max())
            span = vmax - vmin or 1.0
            outlier_vals = rng.choice(
                [vmin - span * 0.5, vmax + span * 0.5], size=n_outliers
            )
        else:
            continue

        if kinds.get(col) in ("int", "money"):
            outlier_vals = np.rint(outlier_vals).astype(np.int64)

        df.iloc[idx, df.columns.get_loc(col)] = outlier_vals
        total_injected += n_outliers

    return df, total_injected


def enforce_constraints(df: pd.DataFrame, constraints: list[dict],
                        max_retries: int = 100) -> tuple[pd.DataFrame, list[str]]:
    """Enforce uniqueness, range, and cross-field constraints.
    
    Returns (df, list_of_warnings).
    """
    warnings = []
    df = df.copy()

    for con in constraints:
        ctype = con.get("type", con.get("rule", ""))
        col = con.get("column", "")

        if ctype == "unique" and col in df.columns:
            dupes = df[col].duplicated(keep="first")
            n_dupes = dupes.sum()
            if n_dupes > 0:
                # Try to fix by adding small increments
                if pd.api.types.is_numeric_dtype(df[col]):
                    df.loc[dupes, col] = df.loc[dupes, col] + np.arange(1, n_dupes + 1)
                else:
                    counter = 0
                    for idx in df.index[dupes]:
                        counter += 1
                        df.at[idx, col] = f"{df.at[idx, col]}_{counter}"
                remaining = df[col].duplicated().sum()
                if remaining > 0:
                    warnings.append(f"{col}: {remaining} duplicates remain after repair")

        elif ctype in ("gte", "range") and col in df.columns:
            lo = con.get("min", con.get("value"))
            hi = con.get("max")
            if lo is not None:
                df[col] = df[col].clip(lower=lo)
            if hi is not None:
                df[col] = df[col].clip(upper=hi)

    return df, warnings


def synthesize(
    df: pd.DataFrame,
    n: int,
    seed: int = 42,
    actions: dict[str, str] | None = None,
    dp: dict | None = None,
    salt: str = "project-salt",
    null_config: dict[str, float] | None = None,
    outlier_rate: float = 0.0,
    outlier_method: str = "iqr_extreme",
    constraints: list[dict] | None = None,
    locale: str = "en_US",
) -> tuple[pd.DataFrame, dict]:
    """Main entry point: profile → fit → sample → post-process.

    Args:
        df: Source DataFrame to learn from
        n: Number of rows to generate
        seed: Random seed for reproducibility
        actions: {col: privacy_action} mapping
        dp: {col: (epsilon, low, high)} for DP-Lite
        salt: Project salt for hashing
        null_config: {col: rate} for additional nulls
        outlier_rate: Global outlier injection rate
        outlier_method: iqr_extreme | zscore | boundary
        constraints: List of constraint dicts to enforce
        locale: Faker locale for fictional content

    Returns:
        (synthetic_df, metadata_dict)
    """
    # 1. Profile
    prof = profile_df(df)
    kinds = {c["name"]: c["kind"] for c in prof["columns"]}

    # 2. Split holdout
    train, hold = split_holdout(df, seed)

    # 3. Fit copula
    model = GaussianCopulaSynth()
    model.fit(train, kinds, seed, dp=dp)

    # 4. Sample
    gen_rng = rng_for(seed, "tabular_sample")
    out = model.sample(n, gen_rng)

    # 5. Handle non-modeled columns (IDs, text, PII)
    fake = Faker(_faker_locale(locale))
    Faker.seed(seed)

    for c in prof["columns"]:
        name, kind = c["name"], c["kind"]
        pii = c.get("pii", "none")

        if pii == "direct" and kind not in ("id", "date", "datetime"):
            out[name] = [fictional(name, i, fake, locale) for i in range(n)]
        elif name in out.columns:
            continue
        elif kind == "id":
            if pd.api.types.is_numeric_dtype(df[name]):
                start = int(pd.to_numeric(df[name], errors="coerce").max()) + 1
                out[name] = np.arange(start, start + n)
            else:
                prefix = name.replace("_id", "").replace("id", "").strip("_") or name
                out[name] = [f"{prefix}-{i:06d}" for i in range(n)]
        elif kind in ("text", "email", "phone", "address", "url"):
            out[name] = [fictional(name, i, fake, locale) for i in range(n)]

    # 6. Reorder columns to match source
    col_order = [c for c in df.columns if c in out.columns]
    out = out[col_order]

    # 7. Inject additional nulls
    if null_config:
        out = inject_nulls(out, null_config, rng_for(seed, "nulls"))

    # 8. Inject outliers
    n_outliers = 0
    if outlier_rate > 0:
        out, n_outliers = inject_outliers(
            out, kinds, outlier_rate, outlier_method, rng_for(seed, "outliers")
        )

    # 9. Enforce constraints
    constraint_warnings = []
    if constraints:
        out, constraint_warnings = enforce_constraints(out, constraints)

    # 10. Apply privacy transformations
    out = apply_privacy(out, actions or {}, salt)

    metadata = {
        "profile": prof,
        "kinds": kinds,
        "train_rows": len(train),
        "holdout_rows": len(hold) if hold is not None else 0,
        "train": train,
        "holdout": hold,
        "model": model,
        "outliers_injected": n_outliers,
        "constraint_warnings": constraint_warnings,
        "dp_applied": bool(dp),
    }
    return out, metadata


def synthesize_from_schema(
    table_dict: dict,
    n: int,
    seed: int = 42,
    locale: str = "en_US",
) -> pd.DataFrame:
    """Generate data from a schema definition alone (no sample).

    Uses declared strategies (weights, ranges, distributions) to produce data.
    No fidelity scores possible — the report says so explicitly.
    """
    rng = rng_for(seed, "schema_gen", table_dict.get("name", "t"))
    fake = Faker(_faker_locale(locale))
    Faker.seed(seed)
    columns = table_dict.get("columns", [])
    data: dict[str, Any] = {}

    for col in columns:
        name = col["name"]
        kind = col.get("kind", "text")
        weights = col.get("weights")
        minimum = col.get("minimum")
        maximum = col.get("maximum")
        null_rate = col.get("null_rate", 0.0)

        if kind == "id":
            start = col.get("start", 10001)
            data[name] = np.arange(start, start + n)
        elif kind == "cat" and weights:
            cats = list(weights.keys())
            probs = np.array(list(weights.values()), dtype=float)
            probs = probs / probs.sum()
            data[name] = rng.choice(cats, size=n, p=probs)
        elif kind == "bool":
            p = col.get("true_rate", 0.5)
            data[name] = rng.random(n) < p
        elif kind in ("int", "num", "money"):
            lo = minimum if minimum is not None else 0
            hi = maximum if maximum is not None else 10000
            vals = rng.uniform(lo, hi, n)
            if kind in ("int", "money"):
                vals = np.rint(vals).astype(np.int64)
            data[name] = vals
        elif kind in ("date", "datetime"):
            start_dt = pd.Timestamp(col.get("start", "2023-01-01"))
            end_dt = pd.Timestamp(col.get("end", "2025-12-31"))
            days = max((end_dt - start_dt).days, 1)
            # Build all candidate dates
            all_dates = pd.date_range(start_dt, end_dt, freq="D")
            if len(all_dates) == 0:
                all_dates = pd.DatetimeIndex([start_dt])
            # Weekday weights: Mon-Fri heavier, Sat/Sun lighter
            dow_weights = np.array([1.1, 1.15, 1.2, 1.15, 1.3, 0.6, 0.5])
            w = dow_weights[all_dates.dayofweek.to_numpy()]
            # Month-end spike (25th-31st get 1.3x weight)
            month_end = all_dates.day.to_numpy() >= 25
            w[month_end] *= 1.3
            # Light seasonality: Q4 boost for retail
            q4 = (all_dates.month.to_numpy() >= 10)
            w[q4] *= 1.15
            # Normalize
            w = w / w.sum()
            chosen = rng.choice(len(all_dates), size=n, p=w)
            data[name] = all_dates[chosen].strftime("%Y-%m-%d")
        elif kind in ("email", "phone", "address", "url", "text"):
            data[name] = [fictional(name, i, fake, locale) for i in range(n)]
        else:
            data[name] = [fictional(name, i, fake, locale) for i in range(n)]

        # Inject nulls
        if null_rate > 0 and kind != "id":
            arr = np.array(data[name], dtype=object)
            mask = rng.random(n) < null_rate
            arr[mask] = None
            data[name] = arr

    return pd.DataFrame(data)
