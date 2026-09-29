"""
Domain packs — pluggable dataset generators for different industries.

Each pack provides: generate_<domain>(), get_<domain>_schema(), <DOMAIN>_DDL
"""
from app.packs.fintech import generate_fintech, get_fintech_schema, FINTECH_DDL

AVAILABLE_PACKS = {
    "retail": {
        "label": "E-Commerce Retail",
        "tables": ["customers", "products", "orders", "order_items"],
        "description": "Customers, products, orders, and order items with computed totals.",
    },
    "fintech": {
        "label": "Fintech / Banking",
        "tables": ["accounts", "cards", "merchants", "transactions"],
        "description": "Bank accounts, cards, merchants, and transaction ledger with running balances.",
    },
}

__all__ = [
    "generate_fintech", "get_fintech_schema", "FINTECH_DDL",
    "AVAILABLE_PACKS",
]
