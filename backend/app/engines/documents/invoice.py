"""
Invoice Generator — creates invoices with line items, tax, and reconciled totals.

ALL money in integer minor units (cents). ALL totals computed, never sampled.
Tax rates are illustrative defaults, NOT tax advice.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

import numpy as np
from pydantic import BaseModel, Field

from app.core.money import to_minor, pct_of, fmt, add, sub, mul
from app.core.seeding import rng_for


class InvoiceParty(BaseModel):
    name: str
    address: str
    city: str
    country: str
    tax_id: str = ""
    email: str = ""
    phone: str = ""


class InvoiceLine(BaseModel):
    description: str
    quantity: int
    unit_price: int          # minor units
    discount_pct: str = "0"
    line_discount: int = 0   # minor units
    line_total: int = 0      # minor units (qty * price - discount)


class TaxBreakdown(BaseModel):
    label: str
    rate: str
    amount: int              # minor units


class Invoice(BaseModel):
    invoice_number: str
    issue_date: str
    due_date: str
    payment_terms: str = "Net 30"
    status: str = "draft"
    currency: str = "USD"
    locale: str = "us"

    issuer: InvoiceParty
    recipient: InvoiceParty

    lines: list[InvoiceLine]
    subtotal: int = 0
    discount_total: int = 0
    net_amount: int = 0
    taxes: list[TaxBreakdown] = Field(default_factory=list)
    tax_total: int = 0
    shipping: int = 0
    grand_total: int = 0
    amount_paid: int = 0
    balance_due: int = 0
    notes: str = ""

    def reconcile(self) -> list[dict]:
        """Verify all totals reconcile. Returns list of check results."""
        checks = []
        line_sum = sum(l.line_total for l in self.lines)
        checks.append({"check": "subtotal == sum(line_totals)",
                        "expected": line_sum, "actual": self.subtotal,
                        "passed": line_sum == self.subtotal})
        expected_net = self.subtotal - self.discount_total
        checks.append({"check": "net == subtotal - discount",
                        "expected": expected_net, "actual": self.net_amount,
                        "passed": expected_net == self.net_amount})
        expected_grand = self.net_amount + self.tax_total + self.shipping
        checks.append({"check": "grand_total == net + tax + shipping",
                        "expected": expected_grand, "actual": self.grand_total,
                        "passed": expected_grand == self.grand_total})
        for line in self.lines:
            expected_lt = mul(line.unit_price, line.quantity) - line.line_discount
            checks.append({"check": f"line '{line.description}': qty×price - disc",
                            "expected": expected_lt, "actual": line.line_total,
                            "passed": expected_lt == line.line_total})
        return checks


# ── Fictional data banks ──────────────────────────────────────────
ISSUERS = [
    InvoiceParty(name="Crescent Solutions Pvt Ltd", address="42 Blue Area", city="Islamabad", country="Pakistan", tax_id="NTN-0000001", email="billing@crescent.example.com"),
    InvoiceParty(name="Atlas Trading Co.", address="15 Clifton Road", city="Karachi", country="Pakistan", tax_id="NTN-0000002", email="invoices@atlas.example.com"),
    InvoiceParty(name="Greenfield Technologies", address="789 Innovation Park", city="San Francisco", country="United States", tax_id="EIN-00-0000001", email="ar@greenfield.example.com"),
    InvoiceParty(name="Northwind Supplies Ltd", address="12 Queen Street", city="London", country="United Kingdom", tax_id="VAT-GB-000001", email="finance@northwind.example.com"),
]

RECIPIENTS = [
    InvoiceParty(name="Sunrise Retail Group", address="88 Mall Road", city="Lahore", country="Pakistan", email="ap@sunrise.example.com"),
    InvoiceParty(name="Horizon Digital Agency", address="33 Tech Park", city="Dubai", country="UAE", email="payments@horizon.example.com"),
    InvoiceParty(name="Peak Performance Ltd", address="55 Market Street", city="New York", country="United States", email="accounts@peak.example.com"),
    InvoiceParty(name="Riverside Enterprises", address="7 River Lane", city="Manchester", country="United Kingdom", email="finance@riverside.example.com"),
]

PRODUCTS = [
    ("API Access — Pro Tier", 110000), ("Data Analytics Dashboard", 250000),
    ("Cloud Storage — 1TB/month", 4999), ("Onboarding Support", 14000),
    ("Premium Support — Monthly", 29900), ("Custom Integration Setup", 450000),
    ("SSL Certificate — Annual", 7999), ("Email Service — 10K/month", 1999),
    ("Mobile App License", 89900), ("Training Workshop — Per Session", 75000),
    ("Consulting — Per Hour", 15000), ("Security Audit", 350000),
    ("Domain Registration — Annual", 1299), ("Backup Service — Monthly", 2499),
    ("Load Balancer — Monthly", 5999),
]

TAX_RULES = {
    "pk": [{"label": "GST", "rate": "0.18"}],
    "us": [{"label": "Sales Tax", "rate": "0.0825"}],
    "uk": [{"label": "VAT", "rate": "0.20"}],
    "eu": [{"label": "VAT", "rate": "0.19"}],
    "in": [{"label": "GST", "rate": "0.18"}],
    "ae": [{"label": "VAT", "rate": "0.05"}],
}


def price_invoice(lines: list[dict], tax_rules: list[dict],
                  discount_pct: str = "0", shipping: int = 0) -> dict:
    """Compute all invoice totals from line items. Returns a pricing dict."""
    priced_lines = []
    for l in lines:
        amount = mul(l["unit_price"], l["quantity"])
        line_disc = pct_of(amount, l.get("discount_pct", "0"))
        lt = amount - line_disc
        priced_lines.append(InvoiceLine(
            description=l["description"],
            quantity=l["quantity"],
            unit_price=l["unit_price"],
            discount_pct=l.get("discount_pct", "0"),
            line_discount=line_disc,
            line_total=lt,
        ))

    subtotal = sum(l.line_total for l in priced_lines)
    discount_total = pct_of(subtotal, discount_pct)
    net = subtotal - discount_total

    taxes = []
    tax_total = 0
    for tr in tax_rules:
        amt = pct_of(net, tr["rate"])
        taxes.append(TaxBreakdown(label=tr["label"], rate=tr["rate"], amount=amt))
        tax_total += amt

    grand_total = net + tax_total + shipping

    return {
        "lines": priced_lines,
        "subtotal": subtotal,
        "discount_total": discount_total,
        "net_amount": net,
        "taxes": taxes,
        "tax_total": tax_total,
        "shipping": shipping,
        "grand_total": grand_total,
    }


class InvoiceGenerator:
    """Generates realistic invoices with perfect reconciliation."""

    def __init__(self, seed: int = 42, locale: str = "pk"):
        self.seed = seed
        self.locale = locale
        self.rng = rng_for(seed, "invoices")

    def generate(self, n_lines: int = 3, tax_rules: list[dict] | None = None,
                 discount_pct: str = "0", status: str = "draft",
                 currency: str | None = None) -> Invoice:
        """Generate a single invoice with random but realistic content."""
        tax_rules = tax_rules or TAX_RULES.get(self.locale, TAX_RULES["us"])
        currency = currency or {"pk": "PKR", "us": "USD", "uk": "GBP", "eu": "EUR", "in": "INR", "ae": "AED"}.get(self.locale, "USD")

        inv_num = f"INV-{self.rng.integers(10000, 99999)}"
        issue = date.today() - timedelta(days=int(self.rng.integers(1, 90)))
        due = issue + timedelta(days=30)

        issuer = ISSUERS[int(self.rng.integers(0, len(ISSUERS)))]
        recipient = RECIPIENTS[int(self.rng.integers(0, len(RECIPIENTS)))]

        # Random line items
        chosen = self.rng.choice(len(PRODUCTS), size=min(n_lines, len(PRODUCTS)), replace=False)
        raw_lines = []
        for idx in chosen:
            desc, price = PRODUCTS[idx]
            qty = int(self.rng.integers(1, 5))
            raw_lines.append({"description": desc, "quantity": qty, "unit_price": price})

        pricing = price_invoice(raw_lines, tax_rules, discount_pct)

        return Invoice(
            invoice_number=inv_num,
            issue_date=str(issue),
            due_date=str(due),
            status=status,
            currency=currency,
            locale=self.locale,
            issuer=issuer,
            recipient=recipient,
            balance_due=pricing["grand_total"],
            **pricing,
        )

    def generate_bulk(self, count: int = 10, **kwargs) -> list[Invoice]:
        """Generate multiple invoices."""
        return [self.generate(**kwargs) for _ in range(count)]

    def from_order(self, order: dict, items: list[dict],
                   tax_rules: list[dict] | None = None) -> Invoice:
        """Create an invoice from relational engine order + items."""
        tax_rules = tax_rules or TAX_RULES.get(self.locale, TAX_RULES["us"])
        raw_lines = [
            {"description": f"Product {it.get('sku', 'ITEM')}",
             "quantity": int(it["quantity"]),
             "unit_price": int(it["unit_price"])}
            for it in items
        ]
        pricing = price_invoice(raw_lines, tax_rules)

        return Invoice(
            invoice_number=f"INV-{order.get('order_id', self.rng.integers(10000, 99999))}",
            issue_date=order.get("order_date", str(date.today())),
            due_date=str(date.today() + timedelta(days=30)),
            status="sent",
            currency={"pk": "PKR"}.get(self.locale, "USD"),
            locale=self.locale,
            issuer=ISSUERS[0],
            recipient=RECIPIENTS[int(self.rng.integers(0, len(RECIPIENTS)))],
            balance_due=pricing["grand_total"],
            **pricing,
        )
