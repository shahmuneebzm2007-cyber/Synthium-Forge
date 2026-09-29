"""
Relational Integrity Validation — SQLite-based proof that generated data is consistent.

The "Prove It" panel: for each guarantee, show the SQL that was run and its result.
Judges can click "Run it yourself" and see the same result.
"""
from __future__ import annotations

import sqlite3
from typing import Optional

import pandas as pd

from app.engines.relational.retail import RETAIL_DDL


# ── Standard integrity checks ─────────────────────────────────────
CHECKS = [
    ("Orders with no matching customer",
     "SELECT COUNT(*) FROM orders o LEFT JOIN customers c "
     "ON o.customer_id = c.customer_id WHERE c.customer_id IS NULL"),

    ("Items with no matching order",
     "SELECT COUNT(*) FROM order_items i LEFT JOIN orders o "
     "ON i.order_id = o.order_id WHERE o.order_id IS NULL"),

    ("Items with no matching product",
     "SELECT COUNT(*) FROM order_items i LEFT JOIN products p "
     "ON i.sku = p.sku WHERE p.sku IS NULL"),

    ("Orders where subtotal ≠ sum of line totals",
     "SELECT COUNT(*) FROM orders o JOIN "
     "(SELECT order_id, SUM(line_total) s FROM order_items GROUP BY order_id) x "
     "ON o.order_id = x.order_id WHERE o.subtotal <> x.s"),

    ("Orders where total ≠ subtotal − discount + tax",
     "SELECT COUNT(*) FROM orders WHERE total <> subtotal - discount + tax"),

    ("Items where line_total ≠ quantity × unit_price",
     "SELECT COUNT(*) FROM order_items WHERE line_total <> quantity * unit_price"),

    ("Orders dated before customer signup",
     "SELECT COUNT(*) FROM orders o JOIN customers c "
     "ON o.customer_id = c.customer_id WHERE o.order_date < c.signup_date"),

    ("Orders that have no items",
     "SELECT COUNT(*) FROM orders o LEFT JOIN order_items i "
     "ON o.order_id = i.order_id WHERE i.order_id IS NULL"),

    ("Duplicate customer IDs",
     "SELECT COUNT(*) - COUNT(DISTINCT customer_id) FROM customers"),

    ("Duplicate order IDs",
     "SELECT COUNT(*) - COUNT(DISTINCT order_id) FROM orders"),

    ("Duplicate item IDs",
     "SELECT COUNT(*) - COUNT(DISTINCT item_id) FROM order_items"),

    ("Negative order totals",
     "SELECT COUNT(*) FROM orders WHERE total < 0"),
]


def load_sqlite(tables: dict[str, pd.DataFrame],
                path: str = ":memory:",
                ddl: str | None = None) -> sqlite3.Connection:
    """Load generated tables into SQLite with FK constraints enabled."""
    con = sqlite3.connect(path)
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")

    if ddl:
        con.executescript(ddl)
    else:
        con.executescript(RETAIL_DDL)

    # Insert in dependency order (parents first)
    order = ["customers", "products", "orders", "order_items"]
    for name in order:
        if name in tables:
            tables[name].to_sql(name, con, if_exists="append", index=False)

    # Insert any remaining tables not in the standard order
    for name, df in tables.items():
        if name not in order:
            df.to_sql(name, con, if_exists="replace", index=False)

    con.commit()
    return con


def prove_it(con: sqlite3.Connection,
             extra_checks: list[tuple[str, str]] | None = None) -> list[dict]:
    """Run all integrity checks and return structured results.

    Each result: {check, sql, violations, passed, sample_violations}
    """
    all_checks = list(CHECKS)
    if extra_checks:
        all_checks.extend(extra_checks)

    # Get existing tables to skip irrelevant checks
    existing_tables = {row[0] for row in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}

    results = []
    for label, sql in all_checks:
        # Skip checks referencing tables that don't exist
        skip = False
        for table in ["orders", "order_items", "customers", "products",
                       "accounts", "cards", "merchants", "transactions"]:
            if table in sql.lower() and table not in existing_tables:
                skip = True
                break
        if skip:
            continue

        try:
            n = con.execute(sql).fetchone()[0]
            results.append({
                "check": label,
                "sql": sql,
                "violations": int(n),
                "passed": n == 0,
            })
        except Exception as e:
            results.append({
                "check": label,
                "sql": sql,
                "violations": -1,
                "passed": False,
                "error": str(e),
            })

    # SQLite built-in FK check
    try:
        fk_violations = con.execute("PRAGMA foreign_key_check").fetchall()
        results.append({
            "check": "SQLite PRAGMA foreign_key_check",
            "sql": "PRAGMA foreign_key_check",
            "violations": len(fk_violations),
            "passed": len(fk_violations) == 0,
        })
    except Exception as e:
        results.append({
            "check": "SQLite PRAGMA foreign_key_check",
            "sql": "PRAGMA foreign_key_check",
            "violations": -1,
            "passed": False,
            "error": str(e),
        })

    return results


def schema_to_ddl(schema_dict: dict) -> str:
    """Auto-generate CREATE TABLE DDL from a schema dict."""
    lines = []
    tables = schema_dict.get("tables", [])

    type_map = {
        "id": "INTEGER", "int": "INTEGER", "num": "REAL", "money": "INTEGER",
        "date": "TEXT", "datetime": "TEXT", "cat": "TEXT", "text": "TEXT",
        "bool": "INTEGER", "fk": "INTEGER", "email": "TEXT", "phone": "TEXT",
        "address": "TEXT", "url": "TEXT",
    }

    for table in tables:
        tname = table["name"]
        pk = table.get("primary_key")
        cols_sql = []
        fks = []

        for col in table.get("columns", []):
            cname = col["name"]
            ckind = col.get("kind", "text")
            sql_type = type_map.get(ckind, "TEXT")

            parts = [cname, sql_type]
            if cname == pk:
                parts.append("PRIMARY KEY")
            if not col.get("nullable", True) or cname == pk:
                parts.append("NOT NULL")
            if col.get("unique", False) and cname != pk:
                parts.append("UNIQUE")

            cols_sql.append(" ".join(parts))

            # FK reference
            ref = col.get("ref")
            if ref and "." in ref:
                ref_table, ref_col = ref.split(".", 1)
                fks.append(f"FOREIGN KEY ({cname}) REFERENCES {ref_table}({ref_col})")

        all_parts = cols_sql + fks
        lines.append(f"CREATE TABLE IF NOT EXISTS {tname} (\n    " +
                      ",\n    ".join(all_parts) + "\n);")

    return "\n\n".join(lines)


def get_table_stats(con: sqlite3.Connection) -> dict:
    """Get row counts and basic stats for all tables."""
    stats = {}
    tables = con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    for (name,) in tables:
        count = con.execute(f"SELECT COUNT(*) FROM [{name}]").fetchone()[0]
        stats[name] = {"rows": count}
    return stats
