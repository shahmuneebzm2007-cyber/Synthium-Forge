"""
Privacy Actions — centralized mask / hash / synthetic / DP-noise transformations.

Factored out of engine.py into its own module so the privacy/ folder
matches the architecture diagram.
"""
from __future__ import annotations

import hashlib
from typing import Optional

import numpy as np
import pandas as pd
from faker import Faker

from app.core.seeding import rng_for


def apply_mask(series: pd.Series, show_last: int = 2) -> pd.Series:
    """Partial redaction: show only the last N characters."""
    def _mask(v):
        s = str(v)
        if len(s) <= show_last:
            return "*" * len(s)
        return "*" * (len(s) - show_last) + s[-show_last:]
    return series.astype(str).map(_mask)


def apply_hash(series: pd.Series, salt: str = "project-salt",
               length: int = 12) -> pd.Series:
    """Salted SHA-256 pseudonymization.
    
    NOT anonymization — the same input always maps to the same hash,
    so it preserves joins but doesn't prevent dictionary attacks.
    """
    return series.astype(str).map(
        lambda v: hashlib.sha256((salt + v).encode()).hexdigest()[:length]
    )


def apply_synthetic(series: pd.Series, column_name: str,
                     seed: int = 42, locale: str = "en_US") -> pd.Series:
    """Replace with fictional but type-appropriate values."""
    fake = Faker(locale)
    Faker.seed(seed)
    n = len(series)
    hint = column_name.lower()

    if "email" in hint:
        return pd.Series([f"user{i:05d}@example.com" for i in range(n)])
    if "phone" in hint or "mobile" in hint or "cell" in hint:
        return pd.Series([f"+00-000-{i:07d}" for i in range(n)])
    if "name" in hint:
        return pd.Series([fake.name() for _ in range(n)])
    if "address" in hint or "street" in hint:
        return pd.Series([fake.street_address() for _ in range(n)])
    if "company" in hint or "org" in hint:
        return pd.Series([fake.company() for _ in range(n)])
    if "city" in hint:
        return pd.Series([fake.city() for _ in range(n)])
    if "ssn" in hint or "cnic" in hint or "passport" in hint:
        return pd.Series([f"XXX-XX-{i:04d}" for i in range(n)])
    if "card" in hint or "account" in hint or "iban" in hint:
        return pd.Series([f"XXXX-XXXX-XXXX-{i:04d}" for i in range(n)])
    if "ip" in hint:
        return pd.Series([f"10.0.{i // 256}.{i % 256}" for i in range(n)])

    return pd.Series([f"{column_name}-{i:06d}" for i in range(n)])


def apply_dp_noise(series: pd.Series, epsilon: float,
                    low: float | None = None, high: float | None = None,
                    seed: int = 42) -> pd.Series:
    """Add calibrated Laplace noise to numeric values.
    
    This is DP-Lite: individual values get noise, not a formal DP mechanism
    on the query output. We say so clearly in the UI.
    """
    rng = rng_for(seed, "dp_noise", str(series.name))
    numeric = pd.to_numeric(series, errors="coerce")
    valid = numeric.dropna()
    if len(valid) == 0 or epsilon <= 0:
        return series

    # Sensitivity = range of the data
    data_low = low if low is not None else float(valid.min())
    data_high = high if high is not None else float(valid.max())
    sensitivity = max(data_high - data_low, 1.0)
    scale = sensitivity / epsilon

    noise = rng.laplace(0, scale, len(series))
    noised = numeric + noise

    # Clip to original range
    noised = noised.clip(data_low, data_high)

    # Preserve dtype
    if pd.api.types.is_integer_dtype(series):
        noised = noised.round().astype("Int64")

    # Preserve NaN positions
    result = noised.copy()
    result[series.isna()] = None
    return result


def apply_exclude(df: pd.DataFrame, column: str) -> pd.DataFrame:
    """Drop a column entirely."""
    return df.drop(columns=[column], errors="ignore")


def apply_all_privacy(df: pd.DataFrame, actions: dict[str, str],
                       salt: str = "project-salt", seed: int = 42,
                       locale: str = "en_US",
                       dp_config: dict[str, float] | None = None) -> pd.DataFrame:
    """Apply all privacy actions to a DataFrame.
    
    Args:
        df: Input DataFrame
        actions: {column_name: action} where action is one of:
                 keep, mask, hash, synthetic, exclude, dp_noise
        salt: Project salt for hashing
        seed: Random seed for synthetic/DP
        locale: Faker locale
        dp_config: {column_name: epsilon} for DP-Lite columns
    """
    dp_config = dp_config or {}
    df = df.copy()

    for col, action in actions.items():
        if col not in df.columns:
            continue

        if action == "exclude":
            df = apply_exclude(df, col)
        elif action == "mask":
            df[col] = apply_mask(df[col])
        elif action == "hash":
            df[col] = apply_hash(df[col], salt)
        elif action == "synthetic":
            df[col] = apply_synthetic(df[col], col, seed, locale)
        elif action == "dp_noise":
            eps = dp_config.get(col, 1.0)
            df[col] = apply_dp_noise(df[col], eps, seed=seed)

    return df
