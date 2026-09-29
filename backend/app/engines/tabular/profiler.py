"""
Data Profiler — Analyzes uploaded CSV/JSON data and infers column types,
distributions, PII, keys, and statistical patterns.

This is the first step in the pipeline: understand what the user gave us
before we can generate anything.
"""
from __future__ import annotations

import re
import warnings
from typing import Optional

import numpy as np
import pandas as pd
import chardet

# ── Detection patterns ─────────────────────────────────────────────
EMAIL_RE = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
PHONE_RE = re.compile(r"^[\+]?[\d\s\-\(\)]{7,20}$")
URL_RE = re.compile(r"^https?://[^\s]+$", re.I)
MONEY_RE = re.compile(r"^[\$£€₹¥]?\s*[\d,]+\.?\d{0,2}$")
DATE_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S",
                "%d-%m-%Y", "%Y/%m/%d", "%d %b %Y", "%b %d, %Y"]

PII_HINT = re.compile(
    r"(^name$|_name$|first.?name|last.?name|full.?name|"
    r"email|phone|mobile|cell|address|street|"
    r"cnic|ssn|passport|national.?id|"
    r"dob|birth|date.?of.?birth|"
    r"salary|income|credit.?card|account.?num)", re.I
)
ID_HINT = re.compile(r"(^id$|_id$|^id_|_key$|_pk$|_code$)", re.I)
MONEY_HINT = re.compile(r"(price|amount|total|balance|cost|fee|tax|discount|"
                         r"salary|income|revenue|payment|charge|rate$)", re.I)


def detect_encoding(file_bytes: bytes) -> str:
    """Auto-detect file encoding, defaulting to UTF-8."""
    result = chardet.detect(file_bytes[:100_000])
    enc = (result.get("encoding") or "utf-8").lower()
    # Normalize common aliases
    if enc in ("ascii", "windows-1252", "iso-8859-1", "latin-1", "latin1"):
        return enc
    if "utf" in enc and "bom" in enc:
        return "utf-8-sig"
    return enc if result.get("confidence", 0) > 0.5 else "utf-8"


def infer_kind(s: pd.Series, col_name: str = "") -> str:
    """Detect the column kind from its values and name."""
    s = s.dropna()
    if s.empty:
        return "text"

    # Boolean check
    if pd.api.types.is_bool_dtype(s):
        return "bool"
    str_vals = s.astype(str).str.strip()
    unique_lower = set(str_vals.str.lower().unique())
    if unique_lower <= {"true", "false", "yes", "no", "1", "0", "t", "f", "y", "n"}:
        if len(unique_lower) <= 3:
            return "bool"

    # Numeric check
    if pd.api.types.is_numeric_dtype(s):
        if MONEY_HINT.search(col_name):
            return "money"
        if (s.dropna() % 1 == 0).all():
            return "int"
        return "num"

    # Try parsing as numeric
    numeric = pd.to_numeric(str_vals, errors="coerce")
    if numeric.notna().mean() >= 0.90:
        if MONEY_HINT.search(col_name):
            return "money"
        return "num"

    # Email
    if str_vals.head(200).map(lambda v: bool(EMAIL_RE.match(v))).mean() > 0.7:
        return "email"

    # Date (checked BEFORE phone: ISO dates like 2024-04-08 match loose phone patterns)
    if str_vals.head(200).map(lambda v: bool(re.match(r"^\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}(:\d{2})?)?$", v))).mean() > 0.9:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            _p = pd.to_datetime(str_vals, errors="coerce")
        if _p.notna().mean() >= 0.90:
            if _p.dropna().dt.time.eq(pd.Timestamp("00:00:00").time()).all():
                return "date"
            return "datetime"

    # Phone
    if str_vals.head(200).map(lambda v: bool(PHONE_RE.match(v))).mean() > 0.7:
        return "phone"

    # URL
    if str_vals.head(200).map(lambda v: bool(URL_RE.match(v))).mean() > 0.7:
        return "url"

    # Date
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        parsed = pd.to_datetime(str_vals, errors="coerce")
    if parsed.notna().mean() >= 0.90:
        if parsed.dropna().dt.time.eq(pd.Timestamp("00:00:00").time()).all():
            return "date"
        return "datetime"

    # Money pattern
    if str_vals.head(200).map(lambda v: bool(MONEY_RE.match(v))).mean() > 0.7:
        return "money"

    # Categorical vs text
    nunique = s.nunique()
    n = len(s)
    if nunique <= max(20, int(0.05 * n)):
        return "cat"

    return "text"


def pii_class(name: str, s: pd.Series) -> str:
    """Detect PII level: direct / quasi / none."""
    vals = s.dropna().astype(str).head(200)

    # Direct PII checks
    if len(vals) and vals.map(lambda v: bool(EMAIL_RE.match(v))).mean() > 0.7:
        return "direct"
    if PII_HINT.search(name):
        # Salary/income are quasi, names/emails/phones are direct
        if re.search(r"(salary|income)", name, re.I):
            return "quasi"
        return "direct"

    # Quasi-identifiers
    quasi_hints = re.compile(r"(age|gender|sex|zip|postal|city|state|country|"
                              r"occupation|ethnicity|race|religion)", re.I)
    if quasi_hints.search(name):
        return "quasi"

    return "none"


def detect_primary_key(df: pd.DataFrame) -> Optional[str]:
    """Find the most likely primary key column."""
    candidates = []
    for col in df.columns:
        s = df[col].dropna()
        if len(s) == 0:
            continue
        uniqueness = s.nunique() / len(s) if len(s) > 0 else 0
        if uniqueness < 0.95:
            continue
        score = uniqueness
        if ID_HINT.search(col):
            score += 0.5
        if pd.api.types.is_numeric_dtype(s):
            # Check if sequential
            nums = pd.to_numeric(s, errors="coerce").dropna().sort_values()
            if len(nums) > 1:
                diffs = nums.diff().dropna()
                if (diffs == 1).mean() > 0.9:
                    score += 0.3
            score += 0.1
        if col.lower() in ("id", "pk", "key"):
            score += 0.4
        candidates.append((col, score))

    if not candidates:
        return None
    candidates.sort(key=lambda x: -x[1])
    return candidates[0][0]


def detect_foreign_keys(tables: dict[str, pd.DataFrame]) -> list[dict]:
    """Cross-table FK detection via value containment."""
    fk_candidates = []
    # Build PK index
    pks = {}
    for tname, df in tables.items():
        pk = detect_primary_key(df)
        if pk:
            pks[tname] = (pk, set(df[pk].dropna().astype(str)))

    for tname, df in tables.items():
        for col in df.columns:
            s = df[col].dropna().astype(str)
            if s.nunique() < 2:
                continue
            col_vals = set(s)
            for ptable, (pk_col, pk_vals) in pks.items():
                if ptable == tname:
                    continue
                if not pk_vals:
                    continue
                containment = len(col_vals & pk_vals) / max(len(col_vals), 1)
                name_sim = (col.lower().replace("_id", "") in ptable.lower() or
                           ptable.lower().replace("s", "") in col.lower())
                if containment >= 0.95 or (containment >= 0.8 and name_sim):
                    fk_candidates.append({
                        "child_table": tname,
                        "child_column": col,
                        "parent_table": ptable,
                        "parent_column": pk_col,
                        "containment": round(containment, 3),
                        "name_similarity": name_sim,
                        "confidence": "high" if containment >= 0.95 and name_sim else "review",
                    })
    return fk_candidates


def profile_column(s: pd.Series, col_name: str) -> dict:
    """Full statistical profile of a single column."""
    nn = s.dropna()
    kind = infer_kind(s, col_name)
    n = len(s)

    item = {
        "name": col_name,
        "kind": kind,
        "null_count": int(s.isna().sum()),
        "null_rate": round(float(s.isna().mean()), 4),
        "n_unique": int(nn.nunique()),
        "n_total": n,
        "pii": pii_class(col_name, s),
        "inference_source": "detected",
        "confidence": "high",
    }

    if kind in ("int", "num", "money") and len(nn):
        nums = pd.to_numeric(nn, errors="coerce").dropna()
        if len(nums):
            item.update({
                "min": float(nums.min()),
                "max": float(nums.max()),
                "mean": round(float(nums.mean()), 4),
                "median": round(float(nums.median()), 4),
                "std": round(float(nums.std()), 4),
                "quantiles": {
                    str(q): round(float(nums.quantile(q)), 4)
                    for q in [0.01, 0.05, 0.25, 0.5, 0.75, 0.95, 0.99]
                },
                "skewness": round(float(nums.skew()), 4) if len(nums) > 2 else 0.0,
                "kurtosis": round(float(nums.kurtosis()), 4) if len(nums) > 3 else 0.0,
            })

    elif kind in ("date", "datetime") and len(nn):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            dates = pd.to_datetime(nn.astype(str), errors="coerce").dropna()
        if len(dates):
            item.update({
                "min": str(dates.min().date()),
                "max": str(dates.max().date()),
                "date_range_days": int((dates.max() - dates.min()).days),
            })

    elif kind == "cat" and len(nn):
        vc = nn.astype(str).value_counts()
        item["top_values"] = {
            str(k): int(v) for k, v in vc.head(30).items()
        }
        item["weights"] = {
            str(k): round(float(v / vc.sum()), 4)
            for k, v in vc.head(50).items()
        }

    elif kind == "bool" and len(nn):
        vc = nn.astype(str).str.lower().value_counts(normalize=True)
        item["true_rate"] = round(float(vc.get("true", vc.get("1", vc.get("yes", vc.get("t", vc.get("y", 0)))))), 4)

    elif kind == "text" and len(nn):
        lengths = nn.astype(str).str.len()
        item["avg_length"] = round(float(lengths.mean()), 1)
        item["max_length"] = int(lengths.max())
        item["min_length"] = int(lengths.min())

    return item


def profile_df(df: pd.DataFrame) -> dict:
    """Complete profile of a DataFrame — the foundation for schema inference."""
    cols = [profile_column(df[c], str(c)) for c in df.columns]

    # Detect likely PK
    pk = detect_primary_key(df)

    # Mark ID columns
    for c in cols:
        if pk and c["name"] == pk:
            c["kind"] = "id"
            c["is_primary_key"] = True
        elif ID_HINT.search(c["name"]) and c["n_unique"] / max(c["n_total"], 1) >= 0.95:
            c["kind"] = "id"

    return {
        "rows": int(len(df)),
        "columns": cols,
        "primary_key": pk,
        "n_columns": len(cols),
        "memory_mb": round(df.memory_usage(deep=True).sum() / 1e6, 2),
    }


def profile_to_schema(profile: dict, table_name: str) -> dict:
    """Convert a profile dict into a SynthSchema-compatible Table dict."""
    from app.contracts.schema import ColumnKind, PIILevel, PrivacyAction

    columns = []
    for c in profile["columns"]:
        col = {
            "name": c["name"],
            "kind": c["kind"],
            "nullable": c["null_rate"] > 0,
            "null_rate": c["null_rate"],
            "pii": c["pii"],
            "unique": c.get("is_primary_key", False) or c["kind"] == "id",
            "inference_source": "detected",
            "confidence": c.get("confidence", "high"),
        }
        if "min" in c:
            col["minimum"] = c["min"]
        if "max" in c:
            col["maximum"] = c["max"]
        if "mean" in c:
            col["mean"] = c["mean"]
        if "weights" in c:
            col["weights"] = c["weights"]
        # Auto-assign privacy for PII
        if c["pii"] == "direct":
            col["privacy_action"] = "synthetic"
        columns.append(col)

    return {
        "name": table_name,
        "rows": profile["rows"],
        "primary_key": profile.get("primary_key"),
        "columns": columns,
    }
