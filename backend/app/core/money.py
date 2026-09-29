"""
Money arithmetic in integer minor units (cents / paisa).

ALL money flows through this module. Floats are never used for currency math.
  - 1234  means $12.34 or PKR 12.34
  - Banker's rounding (ROUND_HALF_EVEN) everywhere
  - Supports multi-currency formatting
"""
from decimal import Decimal, ROUND_HALF_EVEN, InvalidOperation
from typing import Union

Number = Union[int, float, str, Decimal]

# ── Currency registry ──────────────────────────────────────────────
CURRENCIES = {
    "USD": {"symbol": "$",   "minor": 2, "name": "US Dollar"},
    "PKR": {"symbol": "Rs.", "minor": 2, "name": "Pakistani Rupee"},
    "GBP": {"symbol": "£",   "minor": 2, "name": "British Pound"},
    "EUR": {"symbol": "€",   "minor": 2, "name": "Euro"},
    "INR": {"symbol": "₹",   "minor": 2, "name": "Indian Rupee"},
    "AED": {"symbol": "AED", "minor": 2, "name": "UAE Dirham"},
    "JPY": {"symbol": "¥",   "minor": 0, "name": "Japanese Yen"},
    "BHD": {"symbol": "BHD", "minor": 3, "name": "Bahraini Dinar"},
}

_Q1 = Decimal("1")
_Q01 = Decimal("0.01")


def to_minor(x: Number, minor_digits: int = 2) -> int:
    """Convert a human-readable amount to integer minor units.
    
    >>> to_minor('12.34')
    1234
    >>> to_minor(12.345)  # banker's rounds
    1235
    >>> to_minor('100', minor_digits=0)  # JPY
    100
    """
    try:
        factor = Decimal(10) ** minor_digits
        return int(
            (Decimal(str(x)) * factor).quantize(_Q1, rounding=ROUND_HALF_EVEN)
        )
    except (InvalidOperation, ValueError) as e:
        raise ValueError(f"Cannot convert {x!r} to minor units: {e}") from e


def from_minor(minor: int, minor_digits: int = 2) -> Decimal:
    """Convert minor units back to Decimal.
    
    >>> from_minor(1234)
    Decimal('12.34')
    """
    factor = Decimal(10) ** minor_digits
    return (Decimal(minor) / factor).quantize(
        Decimal(10) ** -minor_digits, rounding=ROUND_HALF_EVEN
    )


def pct_of(minor: int, rate: Number) -> int:
    """Apply a percentage/rate to a minor-unit amount.
    
    >>> pct_of(10000, '0.18')  # 18% tax on $100.00
    1800
    >>> pct_of(1099, '0.05')   # 5% of $10.99
    55
    """
    return int(
        (Decimal(minor) * Decimal(str(rate))).quantize(_Q1, rounding=ROUND_HALF_EVEN)
    )


def add(*amounts: int) -> int:
    """Sum minor-unit amounts (explicit is better than implicit)."""
    return sum(amounts)


def sub(a: int, b: int) -> int:
    """Subtract minor-unit amounts."""
    return a - b


def mul(minor: int, qty: int) -> int:
    """Multiply minor-unit price × integer quantity."""
    return minor * qty


def split_amount(total: int, parts: int) -> list[int]:
    """Split a total into N parts that sum exactly to total.
    
    Distributes remainder penny-by-penny to the first parts.
    >>> split_amount(1000, 3)
    [334, 333, 333]
    """
    if parts <= 0:
        raise ValueError("parts must be > 0")
    base = total // parts
    remainder = total - base * parts
    return [base + (1 if i < remainder else 0) for i in range(parts)]


def fmt(minor: int, currency: str = "USD", show_code: bool = False) -> str:
    """Format minor units for display.
    
    >>> fmt(123456, "USD")
    '$1,234.56'
    >>> fmt(-5099, "PKR")
    '-Rs.50.99'
    >>> fmt(100, "JPY")
    '¥100'
    """
    info = CURRENCIES.get(currency, {"symbol": currency, "minor": 2})
    sym = info["symbol"]
    md = info["minor"]
    sign = "-" if minor < 0 else ""
    m = abs(minor)
    
    if md == 0:
        result = f"{sign}{sym}{m:,}"
    else:
        whole = m // (10 ** md)
        frac = m % (10 ** md)
        result = f"{sign}{sym}{whole:,}.{frac:0{md}d}"
    
    if show_code:
        result += f" {currency}"
    return result


def validate_reconciliation(expected: int, actual: int, label: str = "amount") -> dict:
    """Check that two amounts match exactly. Returns a check result dict."""
    return {
        "check": f"{label} reconciliation",
        "expected": expected,
        "actual": actual,
        "diff": actual - expected,
        "passed": expected == actual,
    }
