"""
Locale pack loader — cached access to locale-specific data.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional

from app.core.seeding import rng_for

_LOCALE_DIR = Path(__file__).parent


@lru_cache(maxsize=10)
def load_locale(code: str) -> dict:
    """Load a locale pack by code (pk, us, uk, eu, in, ae)."""
    # Handle special case for India (Python keyword conflict)
    fname = "in_.json" if code == "in" else f"{code}.json"
    path = _LOCALE_DIR / fname
    if not path.exists():
        # Fallback to US
        path = _LOCALE_DIR / "us.json"
    return json.loads(path.read_text(encoding="utf-8"))


def get_available_locales() -> list[str]:
    """List all available locale codes."""
    return [p.stem.rstrip("_") for p in _LOCALE_DIR.glob("*.json")]


def get_locale_names(locale: str, n: int, seed: int = 0) -> list[str]:
    """Generate n full names from a locale's name banks."""
    data = load_locale(locale)
    names_data = data.get("names", {})
    males = names_data.get("given_male", ["User"])
    females = names_data.get("given_female", ["User"])
    families = names_data.get("family", ["Test"])

    rng = rng_for(seed, "locale_names", locale)
    result = []
    for i in range(n):
        given = rng.choice(males) if rng.random() < 0.5 else rng.choice(females)
        family = rng.choice(families)
        result.append(f"{given} {family}")
    return result


def get_locale_merchants(locale: str) -> list[str]:
    """Get the merchant list for a locale."""
    data = load_locale(locale)
    return data.get("merchants", ["General Store"])


def get_locale_companies(locale: str) -> list[str]:
    """Get the fictional company list for a locale."""
    data = load_locale(locale)
    return data.get("companies", ["Fictional Corp"])


def get_locale_cities(locale: str) -> dict[str, float]:
    """Get city weights for a locale."""
    data = load_locale(locale)
    return data.get("cities", {"City": 1.0})


def get_locale_tax_rules(locale: str) -> list[dict]:
    """Get tax rules for a locale."""
    data = load_locale(locale)
    return data.get("tax_rules", [{"label": "Tax", "rate": "0.10"}])


def get_locale_currency(locale: str) -> dict:
    """Get currency info for a locale."""
    data = load_locale(locale)
    return data.get("currency", {"code": "USD", "symbol": "$", "minor_units": 2})
