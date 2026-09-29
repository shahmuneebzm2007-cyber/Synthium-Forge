"""
Relational Engine — Retail demo dataset + generic multi-table generator.

ALL money is integer minor units (cents/paisa).
ALL totals are COMPUTED, never sampled.
Temporal ordering is enforced by construction.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.core.seeding import rng_for
from app.core.money import pct_of, mul

# ── Name banks (Pakistani + international diversity) ───────────────
FIRST_M = ["Bilal", "Hamza", "Omar", "Farhan", "Qasim", "Talha", "Ahmed", "Zain",
            "Saad", "Ali", "Usman", "Jamal", "Mateo", "Daniel", "Liam", "Noah",
            "Arjun", "Ravi", "Wei", "Kenji"]
FIRST_F = ["Ayesha", "Sana", "Fatima", "Nadia", "Kiran", "Layla", "Rania", "Hira",
            "Maryam", "Zara", "Emma", "Grace", "Carmen", "Sofia", "Priya", "Iris",
            "Mei", "Yuki", "Amina", "Aisha"]
LAST = ["Khan", "Ahmed", "Shah", "Malik", "Raza", "Hussain", "Iqbal", "Farooq",
        "Usman", "Butt", "Chen", "Diaz", "Evans", "Garcia", "Jones", "Lopez",
        "Nguyen", "Patel", "Turner", "Vega"]

CITIES = {"Karachi": .32, "Lahore": .28, "Islamabad": .14, "Rawalpindi": .08,
          "Peshawar": .06, "Multan": .06, "Quetta": .03, "Faisalabad": .03}
STATUS_W = {"delivered": .82, "cancelled": .08, "returned": .04, "pending": .06}

ADJ = ["Classic", "Smart", "Urban", "Eco", "Pro", "Compact", "Prime", "Daily",
       "Elite", "Swift", "Cozy", "Bright", "Fresh", "Pure", "Zen"]
NOUN = ["Lamp", "Backpack", "Kettle", "Headset", "Notebook", "Mixer", "Sneakers",
        "Charger", "Bottle", "Speaker", "Watch", "Pillow", "Jacket", "Mug", "Fan"]
CATS = ["Electronics", "Home", "Fashion", "Grocery", "Beauty", "Sports",
        "Books", "Toys", "Health", "Garden"]

RETAIL_DDL = """
CREATE TABLE IF NOT EXISTS customers (
    customer_id INTEGER PRIMARY KEY,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL,
    city TEXT,
    signup_date TEXT NOT NULL,
    segment TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS products (
    sku TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    unit_price INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(customer_id),
    order_date TEXT NOT NULL,
    status TEXT NOT NULL,
    subtotal INTEGER NOT NULL,
    discount INTEGER NOT NULL,
    tax INTEGER NOT NULL,
    total INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS order_items (
    item_id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(order_id),
    sku TEXT NOT NULL REFERENCES products(sku),
    quantity INTEGER NOT NULL,
    unit_price INTEGER NOT NULL,
    line_total INTEGER NOT NULL
);
"""


def _norm(w: dict) -> tuple[list, np.ndarray]:
    keys = list(w)
    p = np.array([max(float(w[k]), 0.0) for k in keys], dtype=np.float64)
    return keys, p / p.sum()


def generate_retail(
    seed: int = 42,
    n_customers: int = 1000,
    n_products: int = 60,
    mean_orders: float = 3.2,
    dispersion: float = 1.4,
    tax_rate: float = 0.18,
    start: str = "2023-01-01",
    end: str = "2025-12-31",
    status_weights: dict | None = None,
    city_weights: dict | None = None,
    locale: str = "pk",
) -> dict[str, pd.DataFrame]:
    """Generate the full retail demo dataset with perfect integrity.

    Returns dict with keys: customers, products, orders, order_items.
    ALL money values are integer cents. ALL totals are computed.
    """
    rc = rng_for(seed, "customers")
    rp = rng_for(seed, "products")
    ro = rng_for(seed, "orders")
    ri = rng_for(seed, "items")

    t0, t1 = pd.Timestamp(start), pd.Timestamp(end)
    span = max((t1 - t0).days, 1)

    # ── Customers ─────────────────────────────────────────────────
    cid = np.arange(10001, 10001 + n_customers)
    genders = rc.choice(["M", "F"], n_customers)
    fn = np.where(genders == "M",
                  rc.choice(FIRST_M, n_customers),
                  rc.choice(FIRST_F, n_customers))
    ln = rc.choice(LAST, n_customers)

    ck, cp = _norm(city_weights or CITIES)
    signup_offsets = rc.integers(0, span + 1, n_customers)
    signup_dates = t0 + pd.to_timedelta(signup_offsets, unit="D")

    customers = pd.DataFrame({
        "customer_id": cid,
        "full_name": [f"{a} {b}" for a, b in zip(fn, ln)],
        "email": [f"{a.lower()}.{b.lower()}{i}@example.com"
                  for a, b, i in zip(fn, ln, cid)],
        "city": rc.choice(ck, n_customers, p=cp),
        "signup_date": signup_dates.strftime("%Y-%m-%d"),
        "segment": rc.choice(["regular", "loyal", "vip"], n_customers, p=[.70, .25, .05]),
    })

    # ── Products (prices in cents) ────────────────────────────────
    prices = np.clip(
        np.rint(np.exp(rp.normal(8.0, 0.9, n_products))).astype(np.int64),
        199, 500_000
    )
    products = pd.DataFrame({
        "sku": [f"SKU-{i:04d}" for i in range(1, n_products + 1)],
        "name": [f"{rp.choice(ADJ)} {rp.choice(NOUN)}" for _ in range(n_products)],
        "category": rp.choice(CATS, n_products),
        "unit_price": prices,
    })

    # ── Orders (heavy-tailed count per customer) ──────────────────
    p_nb = dispersion / (dispersion + mean_orders)
    counts = np.clip(ro.negative_binomial(dispersion, p_nb, n_customers), 0, 60)
    n_orders = int(counts.sum())

    if n_orders == 0:
        orders = pd.DataFrame(columns=["order_id", "customer_id", "order_date",
                                         "status", "subtotal", "discount", "tax", "total"])
        items = pd.DataFrame(columns=["item_id", "order_id", "sku", "quantity",
                                        "unit_price", "line_total"])
        return {"customers": customers, "products": products,
                "orders": orders, "order_items": items}

    o_cust = np.repeat(cid, counts)
    signup_arr = np.repeat(signup_dates.to_numpy(), counts)
    signup_ts = pd.to_datetime(signup_arr)
    room = np.maximum((t1 - signup_ts).days.to_numpy(), 0)
    off = np.floor(ro.random(n_orders) * (room + 1)).astype(int)
    order_dates = (signup_ts + pd.to_timedelta(off, unit="D"))

    sk, sp = _norm(status_weights or STATUS_W)
    oid = np.arange(500001, 500001 + n_orders)

    # ── Order Items ───────────────────────────────────────────────
    items_per_order = ri.integers(1, 6, n_orders)
    n_items = int(items_per_order.sum())

    # Zipf-weighted product selection (popular products bought more)
    w = 1.0 / np.arange(1, n_products + 1) ** 0.8
    sku_idx = ri.choice(n_products, n_items, p=w / w.sum())
    qty = ri.integers(1, 5, n_items).astype(np.int64)
    unit = products["unit_price"].to_numpy()[sku_idx]
    line_total = qty * unit  # computed, never sampled

    items = pd.DataFrame({
        "item_id": np.arange(9_000_001, 9_000_001 + n_items),
        "order_id": np.repeat(oid, items_per_order),
        "sku": products["sku"].to_numpy()[sku_idx],
        "quantity": qty,
        "unit_price": unit,
        "line_total": line_total,
    })

    # ── Roll-ups (all integer cents, all computed) ────────────────
    subtotal = items.groupby("order_id")["line_total"].sum().reindex(oid).to_numpy(dtype=np.int64)

    seg = customers.set_index("customer_id")["segment"].reindex(o_cust).to_numpy()
    disc_rate = np.where(seg == "vip", 0.10, np.where(seg == "loyal", 0.05, 0.0))
    discount = np.rint(subtotal * disc_rate).astype(np.int64)

    net = subtotal - discount
    tax = np.rint(net * tax_rate).astype(np.int64)
    total = net + tax

    orders = pd.DataFrame({
        "order_id": oid,
        "customer_id": o_cust,
        "order_date": order_dates.strftime("%Y-%m-%d"),
        "status": ro.choice(sk, n_orders, p=sp),
        "subtotal": subtotal,
        "discount": discount,
        "tax": tax,
        "total": total,
    })

    return {
        "customers": customers,
        "products": products,
        "orders": orders,
        "order_items": items,
    }


def get_retail_schema() -> dict:
    """Returns the retail schema as a dict compatible with SynthSchema."""
    return {
        "version": "1",
        "name": "retail_demo",
        "locale": "pk",
        "currency": "PKR",
        "domain": "retail",
        "tables": [
            {
                "name": "customers", "rows": 1000, "primary_key": "customer_id",
                "columns": [
                    {"name": "customer_id", "kind": "id"},
                    {"name": "full_name", "kind": "text", "pii": "direct", "privacy_action": "synthetic"},
                    {"name": "email", "kind": "email", "pii": "direct", "privacy_action": "synthetic"},
                    {"name": "city", "kind": "cat", "weights": dict(CITIES)},
                    {"name": "signup_date", "kind": "date"},
                    {"name": "segment", "kind": "cat", "weights": {"regular": 0.70, "loyal": 0.25, "vip": 0.05}},
                ],
            },
            {
                "name": "products", "rows": 60, "primary_key": "sku",
                "columns": [
                    {"name": "sku", "kind": "id"},
                    {"name": "name", "kind": "text"},
                    {"name": "category", "kind": "cat"},
                    {"name": "unit_price", "kind": "money"},
                ],
            },
            {
                "name": "orders", "primary_key": "order_id",
                "columns": [
                    {"name": "order_id", "kind": "id"},
                    {"name": "customer_id", "kind": "fk", "ref": "customers.customer_id"},
                    {"name": "order_date", "kind": "date"},
                    {"name": "status", "kind": "cat", "weights": dict(STATUS_W)},
                    {"name": "subtotal", "kind": "money"},
                    {"name": "discount", "kind": "money"},
                    {"name": "tax", "kind": "money"},
                    {"name": "total", "kind": "money"},
                ],
            },
            {
                "name": "order_items", "primary_key": "item_id",
                "columns": [
                    {"name": "item_id", "kind": "id"},
                    {"name": "order_id", "kind": "fk", "ref": "orders.order_id"},
                    {"name": "sku", "kind": "fk", "ref": "products.sku"},
                    {"name": "quantity", "kind": "int"},
                    {"name": "unit_price", "kind": "money"},
                    {"name": "line_total", "kind": "money"},
                ],
            },
        ],
        "relationships": [
            {"parent": "customers", "child": "orders", "cardinality": "1:N",
             "mean_children": 3.2, "dispersion": 1.4},
            {"parent": "orders", "child": "order_items", "cardinality": "1:N",
             "mean_children": 2.5, "dispersion": 1.0, "min_children": 1, "max_children": 5},
            {"parent": "products", "child": "order_items", "cardinality": "1:N"},
        ],
        "rules": [
            {"id": "line_total_calc", "expr": "order_items.line_total == order_items.quantity * order_items.unit_price", "severity": "error"},
            {"id": "subtotal_rollup", "expr": "orders.subtotal == sum(order_items.line_total by order_id)", "severity": "error"},
            {"id": "total_formula", "expr": "orders.total == orders.subtotal - orders.discount + orders.tax", "severity": "error"},
            {"id": "total_positive", "expr": "orders.total >= 0", "severity": "warn"},
        ],
    }
