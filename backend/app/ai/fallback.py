"""
Deterministic offline fallback for every AI capability.
Works with ZERO network access. 100% deterministic.
"""
from __future__ import annotations

import re
from typing import Any

from faker import Faker

from app.core.seeding import rng_for


# ── Domain templates ──────────────────────────────────────────────
DOMAIN_TEMPLATES = {
    "retail": {
        "name": "retail_demo",
        "tables": ["customers", "products", "orders", "order_items"],
        "description": "E-commerce retail dataset",
    },
    "fintech": {
        "name": "fintech_demo",
        "tables": ["accounts", "transactions", "cards", "merchants"],
        "description": "Financial technology dataset",
    },
    "healthcare": {
        "name": "healthcare_demo",
        "tables": ["patients", "visits", "prescriptions", "providers"],
        "description": "Healthcare dataset (fully fictional)",
    },
    "telecom": {
        "name": "telecom_demo",
        "tables": ["subscribers", "plans", "usage_records", "bills"],
        "description": "Telecommunications dataset",
    },
    "hr": {
        "name": "hr_demo",
        "tables": ["employees", "departments", "payroll", "attendance"],
        "description": "Human resources dataset",
    },
}

# ── Built-in edge case catalog ────────────────────────────────────
EDGE_CASE_CATALOG = [
    {"type": "missing_values", "reason": "Test null handling in downstream pipelines",
     "default_rate": 0.02, "priority": "high"},
    {"type": "boundary_values", "reason": "Test min/max edge cases in validation logic",
     "default_rate": 0.01, "priority": "high"},
    {"type": "rare_categories", "reason": "Test rare category handling in ML models",
     "default_rate": 0.005, "priority": "medium"},
    {"type": "extreme_numerics", "reason": "Test outlier detection and handling",
     "default_rate": 0.005, "priority": "medium"},
    {"type": "date_boundaries", "reason": "Test leap years, year boundaries, DST transitions",
     "default_rate": 0.005, "priority": "medium"},
    {"type": "duplicates", "reason": "Test deduplication logic",
     "default_rate": 0.01, "priority": "low"},
    {"type": "unicode", "reason": "Test internationalization and encoding",
     "default_rate": 0.005, "priority": "low"},
    {"type": "empty_strings", "reason": "Test empty vs null handling",
     "default_rate": 0.005, "priority": "medium"},
    {"type": "negative_amounts", "reason": "Test sign handling in financial calculations",
     "default_rate": 0.005, "priority": "high"},
    {"type": "zero_values", "reason": "Test division by zero and zero-quantity handling",
     "default_rate": 0.005, "priority": "high"},
]

# ── Regex intent patterns for chat-to-refine ──────────────────────
INTENT_PATTERNS = [
    (r"(?:make|set)\s+(\d+)%?\s+(?:of\s+)?(\w+)\s+(?:to\s+)?(\w+)", "update_weight"),
    (r"(?:add|more)\s+(?:customers?\s+)?(?:from|in)\s+(\w+)", "increase_city_weight"),
    (r"(?:increase|set)\s+(?:row\s+)?count\s+(?:to\s+)?(\d+)", "set_row_count"),
    (r"(?:add|include)\s+(?:a\s+)?column\s+(\w+)\s+(?:of\s+)?(?:type\s+)?(\w+)", "add_column"),
    (r"(?:set|change)\s+null\s+rate\s+(?:to\s+)?(\d+(?:\.\d+)?)%?\s+(?:for\s+)?(\w+)", "set_null_rate"),
    (r"(?:make|set)\s+(\w+)\s+unique", "set_unique"),
    (r"(?:remove|delete|drop)\s+(?:column\s+)?(\w+)", "remove_column"),
    (r"(?:increase|decrease)\s+(\w+)\s+(?:by\s+)?(\d+)%?", "adjust_weight"),
]

# ── Statement query patterns ──────────────────────────────────────
STATEMENT_PATTERNS = [
    (r"(\d+)\s*days?", "period_days"),
    (r"opening\s+(?:balance\s+)?[\$]?([\d,]+(?:\.\d+)?)", "opening_balance"),
    (r"(?:never|not?)\s+below\s+[\$]?([\d,]+(?:\.\d+)?)", "min_balance"),
    (r"ending\s+(?:balance\s+)?(?:about\s+|around\s+|~)?[\$]?([\d,]+(?:\.\d+)?)", "ending_balance"),
    (r"salary\s+(?:on\s+)?(?:the\s+)?(\d+)(?:st|nd|rd|th)?", "salary_day"),
    (r"(\d+)\s+utilit(?:y|ies)\s+bills?", "utility_count"),
]


class OfflineFallback:
    """100% deterministic fallback for every AI capability."""

    def prompt_to_schema(self, prompt: str, domain: str = "retail") -> dict:
        """Convert a prompt to a schema using keyword matching + domain templates."""
        prompt_lower = prompt.lower()

        # Detect domain from prompt
        if any(w in prompt_lower for w in ("customer", "order", "product", "retail", "shop", "store")):
            domain = "retail"
        elif any(w in prompt_lower for w in ("account", "transaction", "bank", "payment", "fintech")):
            domain = "fintech"
        elif any(w in prompt_lower for w in ("patient", "hospital", "doctor", "health", "medical")):
            domain = "healthcare"

        # Get template
        from app.engines.relational.retail import get_retail_schema
        retail_words = ("customer", "order", "product", "retail", "shop", "store")
        if domain == "retail" and not any(w in prompt_lower for w in retail_words) \
                and self._entities_from_prompt(prompt):
            domain = "custom"  # entities named in the prompt but no known domain
        if domain == "retail":
            schema = get_retail_schema()
        else:
            schema = self._build_generic_schema(prompt, domain)

        # Extract row count from prompt
        count_match = re.search(r"(\d+(?:,\d+)*)\s+(?:rows?|records?|entries|customers?|users?)", prompt_lower)
        if count_match:
            n = int(count_match.group(1).replace(",", ""))
            if isinstance(schema, dict) and "tables" in schema:
                for t in schema["tables"]:
                    if t == schema["tables"][0]:
                        t["rows"] = n

        # Extract locale
        locale = "us"
        if any(w in prompt_lower for w in ("pakistan", "pk", "pkr", "karachi", "lahore")):
            locale = "pk"
        elif any(w in prompt_lower for w in ("uk", "british", "london", "gbp")):
            locale = "uk"
        elif any(w in prompt_lower for w in ("india", "inr", "mumbai", "delhi")):
            locale = "in"

        if isinstance(schema, dict):
            schema["locale"] = locale

        return schema

    def suggest_edge_cases(self, column_kinds: dict[str, str]) -> list[dict]:
        """Built-in edge case suggestions based on column types."""
        suggestions = list(EDGE_CASE_CATALOG)
        has_money = any(k in ("money", "num") for k in column_kinds.values())
        has_dates = any(k in ("date", "datetime") for k in column_kinds.values())

        result = []
        for ec in suggestions:
            if ec["type"] == "negative_amounts" and not has_money:
                continue
            if ec["type"] == "date_boundaries" and not has_dates:
                continue
            result.append(ec)
        return result

    def parse_statement_query(self, query: str) -> dict:
        """Parse a natural-language statement query into constraints."""
        result: dict[str, Any] = {"period": {}, "constraints": {}, "recurring": []}

        for pattern, key in STATEMENT_PATTERNS:
            m = re.search(pattern, query, re.I)
            if not m:
                continue
            val = m.group(1).replace(",", "")
            if key == "period_days":
                result["period"]["days"] = int(val)
            elif key == "opening_balance":
                result["opening_balance"] = int(float(val) * 100)
            elif key == "min_balance":
                result["constraints"]["min_balance"] = int(float(val) * 100)
            elif key == "ending_balance":
                result["constraints"]["ending_balance"] = {"target": int(float(val) * 100), "tolerance": 5000}
            elif key == "salary_day":
                result["recurring"].append({"type": "salary", "day": int(val), "amount": 180000,
                                             "description": "Monthly Salary"})
            elif key == "utility_count":
                for i in range(int(val)):
                    result["recurring"].append({"type": "utilities", "day": 10 + i * 5, "amount": 8000,
                                                 "description": f"Utility Bill {i+1}"})

        return result

    def generate_vocab_bank(self, semantic: str, locale: str,
                            size: int = 200, seed: int = 0) -> list[str]:
        """Generate vocabulary using Faker (deterministic)."""
        fake = Faker(self._locale_code(locale))
        Faker.seed(seed)

        generators = {
            "person_name": fake.name,
            "company": fake.company,
            "address": fake.street_address,
            "city": fake.city,
            "email": lambda: f"user{fake.random_int(1, 99999)}@example.com",
            "phone": lambda: f"+00-000-{fake.random_int(1000000, 9999999)}",
            "product": lambda: f"{fake.word().title()} {fake.word().title()}",
        }

        gen = generators.get(semantic, fake.word)
        seen: set[str] = set()
        bank: list[str] = []
        for _ in range(size * 3):
            val = gen()
            if val not in seen:
                seen.add(val)
                bank.append(val)
            if len(bank) >= size:
                break
        return bank

    def apply_chat_instruction(self, instruction: str,
                                current_schema: dict) -> list[dict]:
        """Match instruction to regex intents and produce changes."""
        changes = []
        for pattern, intent in INTENT_PATTERNS:
            m = re.search(pattern, instruction, re.I)
            if not m:
                continue
            if intent == "set_row_count":
                n = int(m.group(1))
                changes.append({"type": "set_row_count", "value": n,
                                 "description": f"Set row count to {n}"})
            elif intent == "update_weight":
                pct = int(m.group(1))
                table = m.group(2)
                value = m.group(3)
                changes.append({"type": "update_weight", "table": table,
                                 "value": value, "weight": pct / 100,
                                 "description": f"Set {value} weight to {pct}% in {table}"})
            elif intent == "increase_city_weight":
                city = m.group(1).title()
                changes.append({"type": "increase_city_weight", "city": city,
                                 "description": f"Increase weight for {city}"})
        return changes

    _EVENT_WORDS = ("appointment", "order", "visit", "transaction", "payment", "bill", "record",
                    "enrollment", "enrolment", "booking", "reservation", "prescription", "invoice",
                    "item", "attendance", "payroll", "usage", "claim", "shipment", "review", "ticket")

    @staticmethod
    def _singular(word: str) -> str:
        w = word.lower()
        if w.endswith("ies") and len(w) > 4:
            return w[:-3] + "y"
        if w.endswith("ses") or w.endswith("xes"):
            return w[:-2]
        if w.endswith("s") and not w.endswith("ss"):
            return w[:-1]
        return w

    def _entities_from_prompt(self, prompt: str) -> list[str]:
        """Pull a comma/and separated noun list out of a prompt like
        'Include patients, doctors, and appointments'."""
        text = prompt.lower()
        m = re.search(r"(?:include|including|with|containing|contains|has|having|tables?(?: for)?|for)\s+([a-z_ ,&/-]+)", text)
        if not m:
            return []
        chunk = re.split(r"[.;:\n]", m.group(1))[0]
        parts = re.split(r",|\band\b|&|/", chunk)
        stop = {"a", "an", "the", "system", "dataset", "data", "database", "some", "their", "its", "many", "all"}
        out: list[str] = []
        for part in parts:
            words = [w for w in re.findall(r"[a-z_]+", part) if w not in stop]
            if not words or len(words) > 2:
                continue
            noun = "_".join(words)
            if noun not in out:
                out.append(noun)
        return out if len(out) >= 2 else []

    def _build_generic_schema(self, prompt: str, domain: str) -> dict:
        tmpl = DOMAIN_TEMPLATES.get(domain, DOMAIN_TEMPLATES["retail"])
        names = self._entities_from_prompt(prompt) or (
            {"healthcare": ["patients", "doctors", "appointments"]}.get(domain) or list(tmpl["tables"]))
        names = [n if n.endswith("s") else n + "s" for n in names]
        singles = {n: self._singular(n) for n in names}

        def is_event(n: str) -> bool:
            return any(singles[n].endswith(w) for w in self._EVENT_WORDS)

        children = [n for n in names if is_event(n)]
        if not children and len(names) > 1:
            children = [names[-1]]
        parents = [n for n in names if n not in children]

        tables, rels = [], []
        for n in names:
            sg = singles[n]
            cols = [{"name": f"{sg}_id", "kind": "id", "nullable": False}]
            if n in children:
                for par in parents:
                    cols.append({"name": f"{singles[par]}_id", "kind": "int", "nullable": False,
                                 "ref": f"{par}.{singles[par]}_id"})
                    rels.append({"parent": par, "child": n, "cardinality": "1:N", "mean_children": 3})
                cols += [
                    {"name": f"{sg}_date", "kind": "date", "start": "2024-01-01", "end": "2025-12-31"},
                    {"name": "status", "kind": "cat",
                     "weights": {"completed": 0.7, "pending": 0.2, "cancelled": 0.1}},
                ]
            else:
                cols.append({"name": "name", "kind": "text", "pii": "direct"})
                cols.append({"name": "created_at", "kind": "date", "start": "2022-01-01", "end": "2025-12-31"})
                if sg == "doctor":
                    cols.append({"name": "specialty", "kind": "cat", "weights": {
                        "General": 0.35, "Cardiology": 0.15, "Pediatrics": 0.2, "Neurology": 0.1, "Oncology": 0.1, "Orthopedics": 0.1}})
            tables.append({"name": n, "rows": 200 if n in parents else 1000,
                           "primary_key": f"{sg}_id", "columns": cols})

        return {
            "name": tmpl["name"],
            "domain": domain,
            "locale": "us",
            "currency": "USD",
            "tables": tables,
            "relationships": rels,
            "note": f"Offline {domain} schema built from your prompt. Review and customize.",
        }

    def _locale_code(self, locale: str) -> str:
        return {"pk": "en_US", "us": "en_US", "uk": "en_GB",
                "eu": "de_DE", "in": "en_IN", "ae": "ar_AE"}.get(locale, "en_US")
