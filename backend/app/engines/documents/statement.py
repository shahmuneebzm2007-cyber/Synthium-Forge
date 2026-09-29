"""
Bank Statement Generator — goal-directed generation with constraint satisfaction.

Supports query-style input like: "last 90 days, opening balance 1200, never below 500"
ALL money in integer minor units. Running balance verified independently.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

import numpy as np
from pydantic import BaseModel, Field

from app.core.money import to_minor, fmt, add, sub
from app.core.seeding import rng_for


class Transaction(BaseModel):
    date: str
    description: str
    category: str
    merchant: str = ""
    debit: int = 0        # minor units (positive = money out)
    credit: int = 0       # minor units (positive = money in)
    balance: int = 0      # running balance after this transaction
    is_recurring: bool = False


class BankStatement(BaseModel):
    account_holder: str = "FICTIONAL ACCOUNT HOLDER"
    account_number: str = "XXXX-XXXX-0000"   # intentionally invalid
    institution: str = "SynthBank (Fictional)"
    period_start: str = ""
    period_end: str = ""
    opening_balance: int = 0
    closing_balance: int = 0
    currency: str = "USD"
    locale: str = "us"

    transactions: list[Transaction] = Field(default_factory=list)

    total_debits: int = 0
    total_credits: int = 0
    avg_daily_balance: int = 0
    n_transactions: int = 0

    constraints_met: list[dict] = Field(default_factory=list)

    def reconcile(self) -> list[dict]:
        """Verify every running balance and overall totals."""
        checks = []
        bal = self.opening_balance
        for i, t in enumerate(self.transactions):
            bal = bal + t.credit - t.debit
            checks.append({
                "check": f"Transaction {i+1} balance",
                "expected": bal, "actual": t.balance,
                "passed": bal == t.balance,
            })
        checks.append({
            "check": "Closing balance",
            "expected": bal, "actual": self.closing_balance,
            "passed": bal == self.closing_balance,
        })
        total_d = sum(t.debit for t in self.transactions)
        total_c = sum(t.credit for t in self.transactions)
        expected_close = self.opening_balance + total_c - total_d
        checks.append({
            "check": "Opening + credits - debits == closing",
            "expected": expected_close, "actual": self.closing_balance,
            "passed": expected_close == self.closing_balance,
        })
        return checks


# ── Fictional merchant banks ──────────────────────────────────────
MERCHANTS = {
    "groceries": ["Greenleaf Market", "FreshMart Express", "Daily Basket", "Nature's Best",
                   "Valley Grocers", "Sunrise Foods", "Garden Fresh", "Pure Harvest"],
    "fuel": ["PeakFuel Station", "Roadway Energy", "Swift Petroleum", "GreenDrive Fuel",
             "Highway Express", "Metro Petrol", "Orbit Fuel"],
    "dining": ["Peak Coffee House", "The Golden Spoon", "Urban Bites", "Riverside Cafe",
               "Cloud Kitchen Express", "The Hungry Fork", "Spice Junction"],
    "utilities": ["Riverside Utilities", "MetroGrid Power", "ClearWater Supply",
                   "City Gas Network", "BrightLine Telecom", "NetStream Internet"],
    "entertainment": ["StreamVault", "GameZone Digital", "CinePlex Online",
                       "MusicWave Premium", "BookShelf Digital"],
    "shopping": ["Urban Style Outlet", "TechHub Store", "HomeComfort Shop",
                  "FashionLane", "GadgetWorld", "BookNook"],
    "healthcare": ["MedCare Pharmacy", "WellLife Clinic", "HealthPlus Lab",
                    "ClearView Opticians", "SmileDent Dental"],
    "transport": ["MetroRide Transit", "QuickCab Services", "CityBus Pass",
                   "ParkRight Garage", "AirTravel Express"],
    "salary": ["Employer Payroll"],
    "transfer": ["Incoming Transfer", "Account Transfer"],
}

CATEGORY_AMOUNTS = {
    "groceries":     {"mean": 3500, "std": 2000, "min": 500, "max": 15000},
    "fuel":          {"mean": 5000, "std": 2500, "min": 1500, "max": 12000},
    "dining":        {"mean": 2500, "std": 1500, "min": 500, "max": 8000},
    "utilities":     {"mean": 8000, "std": 4000, "min": 2000, "max": 25000},
    "entertainment": {"mean": 1500, "std": 1000, "min": 300, "max": 5000},
    "shopping":      {"mean": 7000, "std": 5000, "min": 1000, "max": 50000},
    "healthcare":    {"mean": 4000, "std": 3000, "min": 500, "max": 20000},
    "transport":     {"mean": 2000, "std": 1500, "min": 300, "max": 8000},
}

WEEKDAY_WEIGHTS = [0.12, 0.13, 0.14, 0.14, 0.18, 0.17, 0.12]  # Mon-Sun


class StatementConfig(BaseModel):
    period_days: int = 90
    end_date: str = ""
    opening_balance: int = 120000      # minor units
    min_balance: Optional[int] = None
    target_closing: Optional[int] = None
    closing_tolerance: int = 5000
    currency: str = "USD"
    locale: str = "us"
    seed: int = 42

    recurring: list[dict] = Field(default_factory=lambda: [
        {"type": "salary", "day": 1, "amount": 180000, "description": "Monthly Salary"},
    ])
    spend_mix: dict[str, float] = Field(default_factory=lambda: {
        "groceries": 0.25, "fuel": 0.15, "dining": 0.12,
        "utilities": 0.15, "shopping": 0.15, "entertainment": 0.08,
        "healthcare": 0.05, "transport": 0.05,
    })
    avg_transactions_per_month: int = 30

    account_holder: str = "Ahmed Khan (FICTIONAL)"
    institution: str = "SynthBank (Fictional)"


class StatementGenerator:
    """Generate bank statements with goal-directed constraint satisfaction."""

    def __init__(self, seed: int = 42, locale: str = "pk"):
        self.seed = seed
        self.locale = locale

    def generate(self, config: StatementConfig | None = None) -> BankStatement:
        """Generate a complete bank statement satisfying all constraints."""
        config = config or StatementConfig(seed=self.seed, locale=self.locale)
        rng = rng_for(config.seed, "statement")

        end = date.fromisoformat(config.end_date) if config.end_date else date.today()
        start = end - timedelta(days=config.period_days)
        all_dates = [start + timedelta(days=i) for i in range(config.period_days + 1)]

        transactions: list[Transaction] = []

        # 1. Place recurring items
        for rec in config.recurring:
            for d in all_dates:
                if d.day == rec.get("day", 1):
                    amt = rec["amount"]
                    if rec.get("type") in ("salary", "income", "transfer_in"):
                        transactions.append(Transaction(
                            date=str(d), description=rec.get("description", "Recurring Credit"),
                            category=rec.get("type", "salary"), merchant="Employer Payroll",
                            credit=amt, is_recurring=True,
                        ))
                    else:
                        merchant = rng.choice(MERCHANTS.get(rec.get("type", "utilities"), ["Service Provider"]))
                        transactions.append(Transaction(
                            date=str(d), description=rec.get("description", "Recurring Payment"),
                            category=rec.get("type", "utilities"), merchant=merchant,
                            debit=amt, is_recurring=True,
                        ))

        # 2. Fill with discretionary transactions
        n_months = max(1, config.period_days // 30)
        n_discretionary = config.avg_transactions_per_month * n_months - len(transactions)
        n_discretionary = max(0, n_discretionary)

        categories = list(config.spend_mix.keys())
        cat_probs = np.array([config.spend_mix.get(c, 0.1) for c in categories])
        cat_probs = cat_probs / cat_probs.sum()

        for _ in range(n_discretionary):
            cat = rng.choice(categories, p=cat_probs)
            amounts = CATEGORY_AMOUNTS.get(cat, {"mean": 3000, "std": 2000, "min": 300, "max": 15000})
            amt = int(np.clip(
                rng.normal(amounts["mean"], amounts["std"]),
                amounts["min"], amounts["max"]
            ))

            # Weekday-weighted date selection
            d = all_dates[int(rng.choice(len(all_dates), p=None))]
            merchant = rng.choice(MERCHANTS.get(cat, ["Merchant"]))

            transactions.append(Transaction(
                date=str(d), description=f"{merchant} - Purchase",
                category=cat, merchant=merchant, debit=amt,
            ))

        # Sort by date
        transactions.sort(key=lambda t: t.date)

        # 3. Compute running balance
        balance = config.opening_balance
        for t in transactions:
            balance = balance + t.credit - t.debit
            t.balance = balance

        # 4. Repair pass — fix constraint violations
        constraints_met = []

        # Fix min balance violations
        if config.min_balance is not None:
            iterations = 0
            while iterations < 50:
                violations = [i for i, t in enumerate(transactions) if t.balance < config.min_balance]
                if not violations:
                    break
                # Reduce the largest discretionary debit before the violation
                vi = violations[0]
                for j in range(vi, -1, -1):
                    if transactions[j].debit > 0 and not transactions[j].is_recurring:
                        reduction = min(transactions[j].debit // 2, config.min_balance - transactions[vi].balance + 1000)
                        transactions[j].debit = max(100, transactions[j].debit - reduction)
                        break
                # Recompute
                balance = config.opening_balance
                for t in transactions:
                    balance = balance + t.credit - t.debit
                    t.balance = balance
                iterations += 1
            constraints_met.append({
                "constraint": f"balance >= {config.min_balance}",
                "met": all(t.balance >= config.min_balance for t in transactions),
                "repairs": iterations,
            })

        # Fix closing balance target
        if config.target_closing is not None:
            actual_close = transactions[-1].balance if transactions else config.opening_balance
            diff = config.target_closing - actual_close
            if abs(diff) > config.closing_tolerance:
                if diff > 0:
                    # Need more money — add a transfer credit
                    transactions.append(Transaction(
                        date=str(end), description="Transfer In (adjustment)",
                        category="transfer", merchant="Account Transfer",
                        credit=diff, balance=0,
                    ))
                else:
                    # Too much — add a purchase
                    transactions.append(Transaction(
                        date=str(end), description="End-of-period purchase",
                        category="shopping", merchant="General Store",
                        debit=abs(diff), balance=0,
                    ))
                # Recompute
                transactions.sort(key=lambda t: t.date)
                balance = config.opening_balance
                for t in transactions:
                    balance = balance + t.credit - t.debit
                    t.balance = balance

            constraints_met.append({
                "constraint": f"closing_balance ≈ {config.target_closing}",
                "met": abs((transactions[-1].balance if transactions else config.opening_balance) - config.target_closing) <= config.closing_tolerance,
            })

        # 5. Build statement
        closing = transactions[-1].balance if transactions else config.opening_balance
        total_d = sum(t.debit for t in transactions)
        total_c = sum(t.credit for t in transactions)

        # Avg daily balance
        daily_balances = []
        bal = config.opening_balance
        tx_by_date = {}
        for t in transactions:
            tx_by_date.setdefault(t.date, []).append(t)
        for d in all_dates:
            for t in tx_by_date.get(str(d), []):
                bal = bal + t.credit - t.debit
            daily_balances.append(bal)
        avg_daily = int(np.mean(daily_balances)) if daily_balances else config.opening_balance

        return BankStatement(
            account_holder=config.account_holder,
            account_number=f"XXXX-XXXX-{rng_for(config.seed, 'acct').integers(1000, 9999)}",
            institution=config.institution,
            period_start=str(start),
            period_end=str(end),
            opening_balance=config.opening_balance,
            closing_balance=closing,
            currency=config.currency,
            locale=config.locale,
            transactions=transactions,
            total_debits=total_d,
            total_credits=total_c,
            avg_daily_balance=avg_daily,
            n_transactions=len(transactions),
            constraints_met=constraints_met,
        )

    def generate_from_query(self, query_constraints: dict) -> BankStatement:
        """Generate from parsed query constraints (output of AI or regex parser)."""
        config = StatementConfig(
            seed=self.seed,
            locale=self.locale,
            period_days=query_constraints.get("period", {}).get("days", 90),
            opening_balance=query_constraints.get("opening_balance", 120000),
            min_balance=query_constraints.get("constraints", {}).get("min_balance"),
            target_closing=query_constraints.get("constraints", {}).get("ending_balance", {}).get("target"),
            closing_tolerance=query_constraints.get("constraints", {}).get("ending_balance", {}).get("tolerance", 5000),
        )
        if "recurring" in query_constraints:
            config.recurring = query_constraints["recurring"]
        if "spend_mix" in query_constraints:
            config.spend_mix = query_constraints["spend_mix"]
        return self.generate(config)
