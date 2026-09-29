"""
Edge Case & Anomaly Injection — generate labeled test fixtures and anomalies.

Valid data and invalid fixtures go to SEPARATE DataFrames.
Every injected record is traceable via is_anomaly + anomaly_type columns.
"""
from __future__ import annotations

from typing import Any
import numpy as np
import pandas as pd

from app.core.seeding import rng_for


class EdgeCaseInjector:
    """Injects edge cases and labeled anomalies into generated data."""

    def __init__(self, seed: int = 42):
        self.seed = seed
        self.rng = rng_for(seed, "edge_cases")
        self.injection_log: list[dict] = []

    def inject_all(self, df: pd.DataFrame, kinds: dict[str, str],
                   config: dict | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Apply all enabled edge cases.
        
        Returns:
            (main_df_with_anomaly_labels, invalid_fixtures_df)
        """
        config = config or {}
        df = df.copy()
        invalid_rows: list[dict] = []

        if config.get("boundary_values", True):
            df = self.inject_boundary_values(df, kinds)
        if config.get("rare_categories", True):
            df = self.inject_rare_categories(df, kinds)
        if config.get("extreme_numerics", True):
            df = self.inject_extreme_numerics(df, kinds)
        if config.get("date_boundaries", True):
            df = self.inject_date_boundaries(df, kinds)
        if config.get("unicode_names", False):
            df = self.inject_unicode(df)
        if config.get("duplicates", False):
            df = self.inject_duplicates(df)

        # Labeled anomalies in the main dataset
        if config.get("anomaly_labels", True):
            rate = config.get("anomaly_rate", 0.02)
            types = config.get("anomaly_types", [
                "duplicate_charge", "amount_spike", "impossible_date",
                "velocity_burst", "null_required_field", "negative_amount"
            ])
            df = self.inject_labeled_anomalies(df, kinds, rate, types)

        # Invalid fixtures (separate file)
        if config.get("invalid_records", False):
            n_invalid = config.get("invalid_count", 50)
            invalid_df = self.generate_invalid_records(df, kinds, n_invalid)
        else:
            invalid_df = pd.DataFrame()

        return df, invalid_df

    def inject_boundary_values(self, df: pd.DataFrame,
                                kinds: dict[str, str]) -> pd.DataFrame:
        """Inject min/max/zero boundary values into numeric columns."""
        for col in df.columns:
            if kinds.get(col) not in ("int", "num", "money"):
                continue
            vals = pd.to_numeric(df[col], errors="coerce").dropna()
            if len(vals) < 5:
                continue

            n_inject = max(1, len(df) // 500)
            idx = self.rng.choice(len(df), size=min(n_inject * 3, len(df)), replace=False)

            boundaries = []
            vmin, vmax = float(vals.min()), float(vals.max())
            boundaries.extend([vmin] * n_inject)
            boundaries.extend([vmax] * n_inject)
            if vmin <= 0 <= vmax:
                boundaries.extend([0] * n_inject)

            for i, bi in enumerate(boundaries[:len(idx)]):
                val = int(bi) if kinds[col] in ("int", "money") else bi
                df.iloc[idx[i], df.columns.get_loc(col)] = val

            self.injection_log.append({
                "type": "boundary_values", "column": col, "count": min(len(boundaries), len(idx))
            })
        return df

    def inject_rare_categories(self, df: pd.DataFrame,
                                kinds: dict[str, str]) -> pd.DataFrame:
        """Add very-low-frequency category values."""
        for col in df.columns:
            if kinds.get(col) != "cat":
                continue
            existing = df[col].dropna().unique()
            if len(existing) < 2:
                continue
            n_inject = max(1, len(df) // 1000)
            rare_val = f"RARE_{col.upper()}"
            idx = self.rng.choice(len(df), size=n_inject, replace=False)
            df.iloc[idx, df.columns.get_loc(col)] = rare_val
            self.injection_log.append({
                "type": "rare_category", "column": col, "value": rare_val, "count": n_inject
            })
        return df

    def inject_extreme_numerics(self, df: pd.DataFrame,
                                 kinds: dict[str, str]) -> pd.DataFrame:
        """Inject 5+ sigma outliers into numeric columns."""
        for col in df.columns:
            if kinds.get(col) not in ("int", "num", "money"):
                continue
            vals = pd.to_numeric(df[col], errors="coerce").dropna()
            if len(vals) < 10:
                continue
            mean, std = float(vals.mean()), float(vals.std())
            if std == 0:
                continue
            n_inject = max(1, len(df) // 500)
            idx = self.rng.choice(len(df), size=n_inject, replace=False)
            signs = self.rng.choice([-1, 1], size=n_inject)
            extremes = mean + signs * self.rng.uniform(5, 8, n_inject) * std
            if kinds[col] in ("int", "money"):
                extremes = np.rint(extremes).astype(np.int64)
            for i, xi in enumerate(idx):
                df.iloc[xi, df.columns.get_loc(col)] = extremes[i]
            self.injection_log.append({
                "type": "extreme_numeric", "column": col, "count": n_inject
            })
        return df

    def inject_date_boundaries(self, df: pd.DataFrame,
                                kinds: dict[str, str]) -> pd.DataFrame:
        """Inject leap day, year-end, epoch-adjacent, and DST dates."""
        boundary_dates = [
            "2024-02-29",  # leap day
            "2023-12-31",  # year end
            "2024-01-01",  # year start
            "1970-01-01",  # epoch
            "2000-01-01",  # Y2K
            "2025-03-09",  # DST spring forward (US)
            "2025-11-02",  # DST fall back (US)
            "2099-12-31",  # far future
        ]
        for col in df.columns:
            if kinds.get(col) not in ("date", "datetime"):
                continue
            n_inject = min(len(boundary_dates), max(1, len(df) // 200))
            idx = self.rng.choice(len(df), size=n_inject, replace=False)
            for i, xi in enumerate(idx):
                df.iloc[xi, df.columns.get_loc(col)] = boundary_dates[i % len(boundary_dates)]
            self.injection_log.append({
                "type": "date_boundary", "column": col, "count": n_inject
            })
        return df

    def inject_unicode(self, df: pd.DataFrame) -> pd.DataFrame:
        """Inject Unicode edge cases into text columns."""
        unicode_values = [
            "محمد علی",           # Urdu/Arabic
            "José García",        # accented Latin
            "田中太郎",            # Japanese
            "O'Brien-Smith",      # apostrophe + hyphen
            "user\u200b@test",    # zero-width space
            "Name\twith\ttabs",   # tabs
            "  leading spaces",   # leading whitespace
            "trailing spaces  ",  # trailing whitespace
            "ALLCAPS NAME",       # all caps
            "",                   # empty string
        ]
        text_cols = [c for c in df.columns if c in df.select_dtypes(include="object").columns]
        for col in text_cols[:3]:
            n_inject = min(len(unicode_values), max(1, len(df) // 200))
            idx = self.rng.choice(len(df), size=n_inject, replace=False)
            for i, xi in enumerate(idx):
                df.iloc[xi, df.columns.get_loc(col)] = unicode_values[i % len(unicode_values)]
            self.injection_log.append({"type": "unicode", "column": col, "count": n_inject})
        return df

    def inject_duplicates(self, df: pd.DataFrame) -> pd.DataFrame:
        """Inject exact and near-duplicates."""
        n_inject = max(1, len(df) // 500)
        src_idx = self.rng.choice(len(df), size=n_inject, replace=True)
        tgt_idx = self.rng.choice(len(df), size=n_inject, replace=False)
        for s, t in zip(src_idx, tgt_idx):
            df.iloc[t] = df.iloc[s]
        self.injection_log.append({"type": "duplicates", "count": n_inject})
        return df

    def inject_labeled_anomalies(self, df: pd.DataFrame, kinds: dict[str, str],
                                  rate: float, types: list[str]) -> pd.DataFrame:
        """Inject anomalies with is_anomaly and anomaly_type label columns."""
        n_anomalies = max(1, int(len(df) * rate))
        df["is_anomaly"] = False
        df["anomaly_type"] = None

        idx = self.rng.choice(len(df), size=n_anomalies, replace=False)
        assigned_types = self.rng.choice(types, size=n_anomalies)

        num_cols = [c for c in df.columns if kinds.get(c) in ("int", "num", "money") and c not in ("is_anomaly", "anomaly_type")]
        date_cols = [c for c in df.columns if kinds.get(c) in ("date", "datetime")]

        for i, (xi, atype) in enumerate(zip(idx, assigned_types)):
            df.iloc[xi, df.columns.get_loc("is_anomaly")] = True
            df.iloc[xi, df.columns.get_loc("anomaly_type")] = atype

            if atype == "amount_spike" and num_cols:
                col = self.rng.choice(num_cols)
                vals = pd.to_numeric(df[col], errors="coerce").dropna()
                if len(vals) > 0:
                    spike = float(vals.mean()) + float(vals.std() or 1) * self.rng.uniform(5, 10)
                    df.iloc[xi, df.columns.get_loc(col)] = int(spike) if kinds[col] in ("int", "money") else spike

            elif atype == "negative_amount" and num_cols:
                col = self.rng.choice(num_cols)
                df.iloc[xi, df.columns.get_loc(col)] = -abs(int(self.rng.uniform(100, 10000)))

            elif atype == "impossible_date" and date_cols:
                col = self.rng.choice(date_cols)
                df.iloc[xi, df.columns.get_loc(col)] = "2099-13-45"

            elif atype == "null_required_field":
                non_id = [c for c in df.columns if kinds.get(c) != "id" and c not in ("is_anomaly", "anomaly_type")]
                if non_id:
                    col = self.rng.choice(non_id)
                    df.iloc[xi, df.columns.get_loc(col)] = None

        self.injection_log.append({"type": "labeled_anomalies", "count": n_anomalies, "types": list(set(assigned_types))})
        return df

    def generate_invalid_records(self, df: pd.DataFrame, kinds: dict[str, str],
                                  n: int) -> pd.DataFrame:
        """Generate intentionally invalid records for negative testing.
        
        These go to a SEPARATE file (e.g., orders_invalid_fixtures.csv).
        """
        records = []
        template = df.iloc[0].to_dict() if len(df) > 0 else {}

        for i in range(n):
            row = dict(template)
            # Random corruption
            corruption = self.rng.choice([
                "wrong_type", "null_required", "negative_price",
                "empty_string", "overflow", "special_chars", "future_date"
            ])
            row["_fixture_id"] = i
            row["_corruption_type"] = corruption

            if corruption == "wrong_type":
                num_cols = [c for c in df.columns if kinds.get(c) in ("int", "num", "money")]
                if num_cols:
                    col = self.rng.choice(num_cols)
                    row[col] = "not_a_number"
            elif corruption == "null_required":
                cols = [c for c in df.columns if kinds.get(c) == "id"]
                if cols:
                    row[cols[0]] = None
            elif corruption == "negative_price":
                money_cols = [c for c in df.columns if kinds.get(c) == "money"]
                if money_cols:
                    row[money_cols[0]] = -99999
            elif corruption == "empty_string":
                text_cols = [c for c in df.columns if kinds.get(c) in ("text", "cat")]
                if text_cols:
                    row[self.rng.choice(text_cols)] = ""
            elif corruption == "overflow":
                num_cols = [c for c in df.columns if kinds.get(c) in ("int", "num")]
                if num_cols:
                    row[self.rng.choice(num_cols)] = 2**62
            elif corruption == "special_chars":
                text_cols = [c for c in df.columns if kinds.get(c) in ("text", "cat")]
                if text_cols:
                    row[self.rng.choice(text_cols)] = "<script>alert('xss')</script>"

            records.append(row)

        return pd.DataFrame(records)

    def get_injection_summary(self) -> list[dict]:
        """Summary of all injections for the run report."""
        return list(self.injection_log)
