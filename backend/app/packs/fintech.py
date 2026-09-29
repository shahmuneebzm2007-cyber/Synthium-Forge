"""
Fintech Domain Pack — accounts, cards, transactions, merchants.

Reuses the statement generator for transaction patterns.
Each pack = schema + rules + sample prompt + generator.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.core.seeding import rng_for
from app.core.money import pct_of

# ── Fictional institutions & card networks ────────────────────────
INSTITUTIONS = ["SynthBank", "Atlas National", "Crescent Credit Union",
                "Horizon Financial", "Peak Savings", "Riverside Trust"]
CARD_NETWORKS = ["Visa", "Mastercard", "UnionPay"]
ACCOUNT_TYPES = {"checking": 0.50, "savings": 0.35, "business": 0.10, "joint": 0.05}
CARD_STATUSES = {"active": 0.85, "frozen": 0.05, "expired": 0.07, "blocked": 0.03}
TX_CATEGORIES = {
    "groceries": 0.22, "fuel": 0.10, "dining": 0.12, "utilities": 0.10,
    "entertainment": 0.08, "shopping": 0.15, "healthcare": 0.05,
    "transport": 0.06, "transfer": 0.07, "atm": 0.05,
}
TX_TYPES = {"debit": 0.70, "credit": 0.20, "fee": 0.05, "reversal": 0.03, "interest": 0.02}
MERCHANTS = [
    "Greenleaf Market", "FreshMart Express", "Peak Coffee House",
    "Riverside Utilities", "Urban Style Outlet", "TechHub Store",
    "MetroRide Transit", "QuickCab Services", "StreamVault",
    "MedCare Pharmacy", "GameZone Digital", "BookShelf Digital",
    "Shell Station", "Chevron Fuel", "Amazon Fresh", "Uber Eats",
    "Netflix", "Spotify", "Gym Plus", "CinePlex Online",
    "Pizza Palace", "Burger Joint", "Taco Express", "Sushi Bar",
    "Home Depot", "IKEA", "Target", "Walmart", "CVS Pharmacy",
]


def generate_fintech(
    seed: int = 42,
    n_accounts: int = 500,
    n_cards: int = 400,
    n_merchants: int = 50,
    mean_tx_per_account: float = 25.0,
    start: str = "2024-01-01",
    end: str = "2025-06-30",
    locale: str = "us",
) -> dict[str, pd.DataFrame]:
    """Generate a fintech dataset: accounts → cards → transactions → merchants.

    ALL money in integer minor units (cents). ALL balances computed.
    """
    ra = rng_for(seed, "accounts")
    rc = rng_for(seed, "cards")
    rt = rng_for(seed, "transactions")
    rm = rng_for(seed, "merchants")

    t0, t1 = pd.Timestamp(start), pd.Timestamp(end)
    span = max((t1 - t0).days, 1)

    # ── Accounts ──────────────────────────────────────────────────
    acct_ids = [f"ACCT-{i:06d}" for i in range(1, n_accounts + 1)]
    acct_types_keys = list(ACCOUNT_TYPES.keys())
    acct_types_probs = np.array(list(ACCOUNT_TYPES.values()))
    acct_types_probs /= acct_types_probs.sum()

    open_offsets = ra.integers(0, span + 1, n_accounts)
    open_dates = t0 + pd.to_timedelta(open_offsets, unit="D")
    opening_balances = np.clip(
        np.rint(ra.lognormal(11.0, 1.2, n_accounts)).astype(np.int64),
        10000, 50_000_00
    )

    accounts = pd.DataFrame({
        "account_id": acct_ids,
        "account_type": ra.choice(acct_types_keys, n_accounts, p=acct_types_probs),
        "institution": ra.choice(INSTITUTIONS, n_accounts),
        "open_date": open_dates.strftime("%Y-%m-%d"),
        "opening_balance": opening_balances,
        "holder_name": [f"Account Holder {i}" for i in range(1, n_accounts + 1)],
        "holder_email": [f"holder{i}@example.com" for i in range(1, n_accounts + 1)],
        "status": ra.choice(["active", "closed"], n_accounts, p=[0.92, 0.08]),
    })

    # ── Cards ─────────────────────────────────────────────────────
    card_accts = rc.choice(n_accounts, n_cards)
    card_statuses_keys = list(CARD_STATUSES.keys())
    card_statuses_probs = np.array(list(CARD_STATUSES.values()))
    card_statuses_probs /= card_statuses_probs.sum()

    cards = pd.DataFrame({
        "card_id": [f"CARD-{i:06d}" for i in range(1, n_cards + 1)],
        "account_id": [acct_ids[a] for a in card_accts],
        "card_number": [f"XXXX-XXXX-XXXX-{rc.integers(1000, 9999)}" for _ in range(n_cards)],
        "network": rc.choice(CARD_NETWORKS, n_cards),
        "expiry": [(t1 + pd.Timedelta(days=int(rc.integers(30, 730)))).strftime("%m/%Y") for _ in range(n_cards)],
        "status": rc.choice(card_statuses_keys, n_cards, p=card_statuses_probs),
        "daily_limit": rc.choice([50000, 100000, 200000, 500000], n_cards, p=[0.3, 0.35, 0.25, 0.1]),
    })

    # ── Merchants ─────────────────────────────────────────────────
    merch_names = MERCHANTS[:n_merchants] if n_merchants <= len(MERCHANTS) else (
        MERCHANTS + [f"Store {i}" for i in range(len(MERCHANTS), n_merchants)]
    )
    cat_keys = list(TX_CATEGORIES.keys())
    merchants = pd.DataFrame({
        "merchant_id": [f"MERCH-{i:04d}" for i in range(1, len(merch_names) + 1)],
        "name": merch_names,
        "category": rm.choice(cat_keys, len(merch_names)),
        "mcc_code": rm.integers(1000, 9999, len(merch_names)),
    })

    # ── Transactions ──────────────────────────────────────────────
    p_nb = 1.5 / (1.5 + mean_tx_per_account)
    counts = np.clip(rt.negative_binomial(1.5, p_nb, n_accounts), 0, 200)
    n_tx = int(counts.sum())

    if n_tx == 0:
        transactions = pd.DataFrame(columns=[
            "tx_id", "account_id", "card_id", "merchant_id", "tx_date",
            "tx_type", "category", "amount", "balance_after", "description"
        ])
        return {"accounts": accounts, "cards": cards,
                "merchants": merchants, "transactions": transactions}

    tx_acct_idx = np.repeat(np.arange(n_accounts), counts)
    tx_acct = [acct_ids[a] for a in tx_acct_idx]

    # Card assignment (some transactions are cardless)
    acct_card_map: dict[str, list[str]] = {}
    for _, row in cards.iterrows():
        acct_card_map.setdefault(row["account_id"], []).append(row["card_id"])
    tx_card = []
    for aid in tx_acct:
        clist = acct_card_map.get(aid, [])
        if clist and rt.random() < 0.85:
            tx_card.append(rt.choice(clist))
        else:
            tx_card.append(None)

    # Merchant assignment
    merch_w = 1.0 / np.arange(1, len(merch_names) + 1) ** 0.6
    merch_idx = rt.choice(len(merch_names), n_tx, p=merch_w / merch_w.sum())

    # Dates (after account open date)
    open_dates_arr = np.repeat(open_dates.to_numpy(), counts)
    open_ts = pd.to_datetime(open_dates_arr)
    room = np.maximum((t1 - open_ts).days.to_numpy(), 0)
    tx_offsets = np.floor(rt.random(n_tx) * (room + 1)).astype(int)
    tx_dates = open_ts + pd.to_timedelta(tx_offsets, unit="D")

    # Amounts (integer cents, category-based)
    cat_amounts = {
        "groceries": (3500, 2000), "fuel": (5000, 2500), "dining": (2500, 1500),
        "utilities": (8000, 4000), "entertainment": (1500, 1000), "shopping": (7000, 5000),
        "healthcare": (4000, 3000), "transport": (2000, 1500), "transfer": (15000, 10000),
        "atm": (10000, 5000),
    }
    tx_cats = merchants["category"].to_numpy()[merch_idx]
    amounts = np.zeros(n_tx, dtype=np.int64)
    for i, cat in enumerate(tx_cats):
        mu, sig = cat_amounts.get(cat, (3000, 2000))
        amounts[i] = max(100, int(np.clip(rt.normal(mu, sig), 100, 100000)))

    # Type
    tx_type_keys = list(TX_TYPES.keys())
    tx_type_probs = np.array(list(TX_TYPES.values()))
    tx_type_probs /= tx_type_probs.sum()
    tx_types = rt.choice(tx_type_keys, n_tx, p=tx_type_probs)

    # Compute running balances per account
    balance_after = np.zeros(n_tx, dtype=np.int64)
    acct_balance = {aid: int(bal) for aid, bal in zip(acct_ids, opening_balances)}

    # Sort by account then date for balance computation
    order = np.lexsort((tx_dates.to_numpy(), tx_acct_idx))
    for idx in order:
        aid = tx_acct[idx]
        bal = acct_balance[aid]
        t = tx_types[idx]
        if t in ("credit", "reversal", "interest"):
            bal += amounts[idx]
        else:
            bal -= amounts[idx]
        acct_balance[aid] = bal
        balance_after[idx] = bal

    transactions = pd.DataFrame({
        "tx_id": [f"TX-{i:08d}" for i in range(1, n_tx + 1)],
        "account_id": tx_acct,
        "card_id": tx_card,
        "merchant_id": merchants["merchant_id"].to_numpy()[merch_idx],
        "tx_date": tx_dates.strftime("%Y-%m-%d"),
        "tx_type": tx_types,
        "category": tx_cats,
        "amount": amounts,
        "balance_after": balance_after,
        "description": [f"{merchants['name'].to_numpy()[merch_idx[i]]} - {tx_types[i].title()}"
                        for i in range(n_tx)],
    })

    return {
        "accounts": accounts,
        "cards": cards,
        "merchants": merchants,
        "transactions": transactions,
    }


FINTECH_DDL = """
CREATE TABLE IF NOT EXISTS accounts (
    account_id TEXT PRIMARY KEY,
    account_type TEXT NOT NULL,
    institution TEXT NOT NULL,
    open_date TEXT NOT NULL,
    opening_balance INTEGER NOT NULL,
    holder_name TEXT NOT NULL,
    holder_email TEXT NOT NULL,
    status TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS cards (
    card_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES accounts(account_id),
    card_number TEXT NOT NULL,
    network TEXT NOT NULL,
    expiry TEXT NOT NULL,
    status TEXT NOT NULL,
    daily_limit INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS merchants (
    merchant_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    mcc_code INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS transactions (
    tx_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES accounts(account_id),
    card_id TEXT REFERENCES cards(card_id),
    merchant_id TEXT NOT NULL REFERENCES merchants(merchant_id),
    tx_date TEXT NOT NULL,
    tx_type TEXT NOT NULL,
    category TEXT NOT NULL,
    amount INTEGER NOT NULL,
    balance_after INTEGER NOT NULL,
    description TEXT
);
"""


def get_fintech_schema() -> dict:
    """Returns the fintech schema as a dict compatible with SynthSchema."""
    return {
        "version": "1",
        "name": "fintech_demo",
        "locale": "us",
        "currency": "USD",
        "domain": "fintech",
        "tables": [
            {
                "name": "accounts", "rows": 500, "primary_key": "account_id",
                "columns": [
                    {"name": "account_id", "kind": "id"},
                    {"name": "account_type", "kind": "cat", "weights": dict(ACCOUNT_TYPES)},
                    {"name": "institution", "kind": "cat"},
                    {"name": "open_date", "kind": "date"},
                    {"name": "opening_balance", "kind": "money"},
                    {"name": "holder_name", "kind": "text", "pii": "direct", "privacy_action": "synthetic"},
                    {"name": "holder_email", "kind": "email", "pii": "direct", "privacy_action": "synthetic"},
                    {"name": "status", "kind": "cat", "weights": {"active": 0.92, "closed": 0.08}},
                ],
            },
            {
                "name": "cards", "rows": 400, "primary_key": "card_id",
                "columns": [
                    {"name": "card_id", "kind": "id"},
                    {"name": "account_id", "kind": "fk", "ref": "accounts.account_id"},
                    {"name": "card_number", "kind": "text", "pii": "direct", "privacy_action": "mask"},
                    {"name": "network", "kind": "cat"},
                    {"name": "expiry", "kind": "text"},
                    {"name": "status", "kind": "cat", "weights": dict(CARD_STATUSES)},
                    {"name": "daily_limit", "kind": "money"},
                ],
            },
            {
                "name": "merchants", "rows": 50, "primary_key": "merchant_id",
                "columns": [
                    {"name": "merchant_id", "kind": "id"},
                    {"name": "name", "kind": "text"},
                    {"name": "category", "kind": "cat"},
                    {"name": "mcc_code", "kind": "int"},
                ],
            },
            {
                "name": "transactions", "primary_key": "tx_id",
                "columns": [
                    {"name": "tx_id", "kind": "id"},
                    {"name": "account_id", "kind": "fk", "ref": "accounts.account_id"},
                    {"name": "card_id", "kind": "fk", "ref": "cards.card_id"},
                    {"name": "merchant_id", "kind": "fk", "ref": "merchants.merchant_id"},
                    {"name": "tx_date", "kind": "date"},
                    {"name": "tx_type", "kind": "cat", "weights": dict(TX_TYPES)},
                    {"name": "category", "kind": "cat", "weights": dict(TX_CATEGORIES)},
                    {"name": "amount", "kind": "money"},
                    {"name": "balance_after", "kind": "money"},
                    {"name": "description", "kind": "text"},
                ],
            },
        ],
        "relationships": [
            {"parent": "accounts", "child": "cards", "cardinality": "1:N", "mean_children": 1.5},
            {"parent": "accounts", "child": "transactions", "cardinality": "1:N", "mean_children": 25},
            {"parent": "merchants", "child": "transactions", "cardinality": "1:N"},
        ],
        "rules": [
            {"id": "tx_amount_positive", "expr": "transactions.amount > 0", "severity": "error"},
            {"id": "card_belongs_to_account", "expr": "cards.account_id in accounts.account_id", "severity": "error"},
        ],
    }
