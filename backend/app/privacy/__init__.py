"""
Privacy module — centralized PII detection, privacy actions, and risk assessment.

Usage:
    from app.privacy import PIIScanner, apply_all_privacy, full_privacy_report
"""
from app.privacy.scanner import PIIScanner
from app.privacy.actions import (
    apply_mask, apply_hash, apply_synthetic, apply_dp_noise,
    apply_exclude, apply_all_privacy,
)
from app.privacy.risk import (
    k_anonymity, l_diversity, full_privacy_report,
)

__all__ = [
    "PIIScanner",
    "apply_mask", "apply_hash", "apply_synthetic", "apply_dp_noise",
    "apply_exclude", "apply_all_privacy",
    "k_anonymity", "l_diversity", "full_privacy_report",
]
