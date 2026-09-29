"""
PII Scanner — centralized PII detection with quasi-identifier support.

Upgrades over the inline profiler version:
  - Quasi-identifiers (age + city + gender combinations)
  - Configurable sensitivity levels
  - Regex + header + semantic analysis
"""
from __future__ import annotations

import re
from typing import Optional

import pandas as pd

# ── Direct PII patterns ──────────────────────────────────────────
EMAIL_RE = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
PHONE_RE = re.compile(r"^[\+]?[\d\s\-\(\)]{7,20}$")
SSN_RE = re.compile(r"^\d{3}-?\d{2}-?\d{4}$")
CNIC_RE = re.compile(r"^\d{5}-?\d{7}-?\d{1}$")
CREDIT_CARD_RE = re.compile(r"^\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}$")
IP_RE = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")

DIRECT_HEADER = re.compile(
    r"(^name$|_name$|first.?name|last.?name|full.?name|"
    r"email|phone|mobile|cell|"
    r"cnic|ssn|passport|national.?id|"
    r"credit.?card|card.?number|account.?num|iban|"
    r"ip.?addr|mac.?addr|"
    r"date.?of.?birth|^dob$)", re.I
)

QUASI_HEADER = re.compile(
    r"(^age$|age.?group|^gender$|^sex$|"
    r"zip.?code|postal.?code|^zip$|"
    r"city|state|province|country|region|district|"
    r"occupation|job.?title|profession|"
    r"ethnicity|race|religion|nationality|"
    r"education|degree|marital|"
    r"salary|income|^dob$|birth.?year|year.?of.?birth)", re.I
)

SENSITIVE_HEADER = re.compile(
    r"(salary|income|wage|compensation|"
    r"health|diagnosis|medical|prescription|"
    r"criminal|arrest|conviction|"
    r"political|religion|sexual|disability|"
    r"password|secret|token|api.?key)", re.I
)


class PIIScanner:
    """Scan columns for PII and quasi-identifiers."""

    def __init__(self, sample_size: int = 500):
        self.sample_size = sample_size
        self._scan_results: list[dict] = []

    def scan_column(self, name: str, series: pd.Series) -> dict:
        """Classify a single column's PII level and suggest privacy action."""
        vals = series.dropna().astype(str).head(self.sample_size)

        result = {
            "column": name,
            "pii_level": "none",
            "pii_type": None,
            "detected_by": [],
            "suggested_action": "keep",
            "confidence": "high",
        }

        # ── Direct PII: value-based detection ─────────────────────
        if len(vals) > 0:
            email_rate = vals.map(lambda v: bool(EMAIL_RE.match(v))).mean()
            if email_rate > 0.5:
                result.update(pii_level="direct", pii_type="email",
                              detected_by=["value_pattern"], suggested_action="synthetic")
                self._scan_results.append(result)
                return result

            phone_rate = vals.map(lambda v: bool(PHONE_RE.match(v))).mean()
            if phone_rate > 0.5:
                result.update(pii_level="direct", pii_type="phone",
                              detected_by=["value_pattern"], suggested_action="synthetic")
                self._scan_results.append(result)
                return result

            ssn_rate = vals.map(lambda v: bool(SSN_RE.match(v))).mean()
            cnic_rate = vals.map(lambda v: bool(CNIC_RE.match(v))).mean()
            if ssn_rate > 0.3 or cnic_rate > 0.3:
                result.update(pii_level="direct", pii_type="national_id",
                              detected_by=["value_pattern"], suggested_action="hash")
                self._scan_results.append(result)
                return result

            cc_rate = vals.map(lambda v: bool(CREDIT_CARD_RE.match(v))).mean()
            if cc_rate > 0.3:
                result.update(pii_level="direct", pii_type="credit_card",
                              detected_by=["value_pattern"], suggested_action="mask")
                self._scan_results.append(result)
                return result

            ip_rate = vals.map(lambda v: bool(IP_RE.match(v))).mean()
            if ip_rate > 0.5:
                result.update(pii_level="direct", pii_type="ip_address",
                              detected_by=["value_pattern"], suggested_action="hash")
                self._scan_results.append(result)
                return result

        # ── Direct PII: header-based detection ────────────────────
        if DIRECT_HEADER.search(name):
            pii_type = "name" if re.search(r"name", name, re.I) else "identifier"
            if re.search(r"(salary|income)", name, re.I):
                # Salary is sensitive but quasi, not direct
                result.update(pii_level="quasi", pii_type="financial",
                              detected_by=["header_match"], suggested_action="dp_noise")
            else:
                result.update(pii_level="direct", pii_type=pii_type,
                              detected_by=["header_match"], suggested_action="synthetic")
            self._scan_results.append(result)
            return result

        # ── Quasi-identifiers: header-based ───────────────────────
        if QUASI_HEADER.search(name):
            qi_type = "demographic"
            if re.search(r"(zip|postal|city|state|country|region|district)", name, re.I):
                qi_type = "geographic"
            elif re.search(r"(age|birth|dob|gender|sex)", name, re.I):
                qi_type = "demographic"
            elif re.search(r"(occupation|job|profession|education)", name, re.I):
                qi_type = "professional"
            elif re.search(r"(salary|income)", name, re.I):
                qi_type = "financial"

            result.update(pii_level="quasi", pii_type=qi_type,
                          detected_by=["header_match"], suggested_action="dp_noise",
                          confidence="review")
            self._scan_results.append(result)
            return result

        # ── Sensitive data ────────────────────────────────────────
        if SENSITIVE_HEADER.search(name):
            result.update(pii_level="quasi", pii_type="sensitive",
                          detected_by=["header_match"], suggested_action="dp_noise",
                          confidence="review")
            self._scan_results.append(result)
            return result

        # ── Heuristic: high-cardinality text could be PII ─────────
        if series.dtype == object and len(vals) > 0:
            uniq_ratio = vals.nunique() / len(vals) if len(vals) > 0 else 0
            avg_spaces = vals.str.count(" ").mean()
            has_numbers = vals.str.contains(r"\d").any()
            # Likely person names: high uniqueness + ~1 space per value, and no numbers (dates have numbers)
            if uniq_ratio > 0.8 and 0.5 < avg_spaces < 3 and len(vals) > 20 and not has_numbers:
                result.update(pii_level="direct", pii_type="probable_name",
                              detected_by=["heuristic"], suggested_action="synthetic",
                              confidence="review")
                self._scan_results.append(result)
                return result

        result["pii_level"] = "none"
        self._scan_results.append(result)
        return result

    def scan_dataframe(self, df: pd.DataFrame) -> list[dict]:
        """Scan all columns in a DataFrame."""
        self._scan_results = []
        results = [self.scan_column(str(c), df[c]) for c in df.columns]

        # ── Quasi-identifier combination risk ─────────────────────
        quasi_cols = [r["column"] for r in results if r["pii_level"] == "quasi"]
        if len(quasi_cols) >= 2:
            # Check k-anonymity on quasi combinations
            combo_risk = self._assess_combination_risk(df, quasi_cols)
            for r in results:
                if r["column"] in quasi_cols:
                    r["combination_risk"] = combo_risk

        return results

    def _assess_combination_risk(self, df: pd.DataFrame,
                                  quasi_cols: list[str]) -> dict:
        """Assess re-identification risk from quasi-identifier combinations."""
        valid_cols = [c for c in quasi_cols if c in df.columns]
        if len(valid_cols) < 2:
            return {"risk": "low", "reason": "Too few quasi-identifiers"}

        # Use up to 3 quasi-identifiers for the check
        check_cols = valid_cols[:3]
        groups = df.groupby([df[c].astype(str) for c in check_cols]).size()
        min_k = int(groups.min()) if len(groups) > 0 else 0
        pct_small = float((groups < 5).mean()) if len(groups) > 0 else 0.0

        risk = "low"
        if min_k <= 1:
            risk = "high"
        elif min_k <= 3 or pct_small > 0.2:
            risk = "moderate"

        return {
            "risk": risk,
            "columns_checked": check_cols,
            "min_k": min_k,
            "pct_groups_below_5": round(pct_small, 3),
            "note": ("Quasi-identifiers in combination can re-identify individuals. "
                     f"Smallest group has {min_k} records."),
        }

    def get_summary(self) -> dict:
        """Summary for the Trust Center."""
        direct = [r for r in self._scan_results if r["pii_level"] == "direct"]
        quasi = [r for r in self._scan_results if r["pii_level"] == "quasi"]
        return {
            "total_columns": len(self._scan_results),
            "direct_pii": len(direct),
            "quasi_identifiers": len(quasi),
            "safe_columns": len(self._scan_results) - len(direct) - len(quasi),
            "columns": self._scan_results,
        }

    def suggest_dp_epsilon(self, column_name: str, pii_level: str,
                            n_rows: int) -> dict:
        """Suggest DP-Lite epsilon based on column sensitivity and size.
        
        Lower epsilon = more noise = more privacy = less utility.
        These are starting-point suggestions, not guarantees.
        """
        if pii_level == "direct":
            eps = 0.1  # very aggressive noise
            note = "Direct PII: consider synthetic replacement instead of DP noise"
        elif pii_level == "quasi":
            eps = 1.0 if n_rows < 1000 else 2.0
            note = "Quasi-identifier: moderate noise to blur group membership"
        else:
            eps = 5.0
            note = "Low sensitivity: light noise to limit memorization"

        return {
            "column": column_name,
            "suggested_epsilon": eps,
            "noise_level": "heavy" if eps < 1 else "moderate" if eps < 3 else "light",
            "note": note,
            "disclaimer": ("DP-Lite applies Laplace noise to histogram counts only. "
                           "This is NOT full differential privacy."),
        }
