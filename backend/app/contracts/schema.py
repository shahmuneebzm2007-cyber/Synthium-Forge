"""
SynthSchema v1 — The single shared contract used by every engine, the UI, the AI layer, and exports.

This is the most important file in the project. Every team member must understand it.
Changes here must be communicated to everyone.
"""
from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional, Union
from pathlib import Path

from pydantic import BaseModel, Field, model_validator


# ── Column kind ────────────────────────────────────────────────────
class ColumnKind(str, Enum):
    ID = "id"
    INT = "int"
    NUM = "num"
    MONEY = "money"
    DATE = "date"
    DATETIME = "datetime"
    CAT = "cat"
    TEXT = "text"
    BOOL = "bool"
    FK = "fk"
    EMAIL = "email"
    PHONE = "phone"
    ADDRESS = "address"
    URL = "url"
    JSON_FIELD = "json"


class PIILevel(str, Enum):
    NONE = "none"
    DIRECT = "direct"      # name, email, phone, SSN
    QUASI = "quasi"         # age + zip + gender can re-identify


class PrivacyAction(str, Enum):
    KEEP = "keep"
    MASK = "mask"
    HASH = "hash"
    SYNTHETIC = "synthetic"
    EXCLUDE = "exclude"
    DP_NOISE = "dp_noise"


class InferenceSource(str, Enum):
    DETECTED = "detected"
    AI_SUGGESTED = "ai_suggested"
    USER_DEFINED = "user_defined"


class Confidence(str, Enum):
    HIGH = "high"
    REVIEW = "review"


# ── Strategy definitions ───────────────────────────────────────────
class SequenceStrategy(BaseModel):
    kind: Literal["sequence"] = "sequence"
    start: int = 1
    prefix: str = ""
    zero_pad: int = 0


class CategoricalStrategy(BaseModel):
    kind: Literal["categorical"] = "categorical"
    weights: dict[str, float]


class NumericStrategy(BaseModel):
    kind: Literal["numeric"] = "numeric"
    distribution: Literal["normal", "lognormal", "uniform", "gamma", "empirical"] = "empirical"
    mean: Optional[float] = None
    std: Optional[float] = None
    shape: Optional[float] = None


class TemporalStrategy(BaseModel):
    kind: Literal["temporal"] = "temporal"
    start: str = "2023-01-01"
    end: str = "2025-12-31"
    seasonality: Optional[str] = None      # "retail", "financial", "uniform"
    weekday_weights: Optional[list[float]] = None  # Mon-Sun


class VocabBankStrategy(BaseModel):
    kind: Literal["vocab_bank"] = "vocab_bank"
    semantic: Optional[str] = None  # "person_name", "company", "product"


class DerivedStrategy(BaseModel):
    kind: Literal["derived"] = "derived"
    from_column: str
    template: str = "{value}"
    domain: str = "example.com"


class FormulaStrategy(BaseModel):
    kind: Literal["formula"] = "formula"
    expr: str                    # "subtotal - discount + tax"


class RollupStrategy(BaseModel):
    kind: Literal["rollup"] = "rollup"
    operation: Literal["sum", "count", "min", "max", "avg"] = "sum"
    source_table: str
    source_column: str
    group_by: str                # FK column name in source


class TaxStrategy(BaseModel):
    kind: Literal["tax"] = "tax"
    rule: str = "locale_default"
    base_column: str = "subtotal"


class ConditionalStrategy(BaseModel):
    kind: Literal["conditional"] = "conditional"
    depends_on: str              # column name
    mapping: dict[str, Any]      # value → strategy params


Strategy = Union[
    SequenceStrategy, CategoricalStrategy, NumericStrategy,
    TemporalStrategy, VocabBankStrategy, DerivedStrategy,
    FormulaStrategy, RollupStrategy, TaxStrategy, ConditionalStrategy
]


# ── Column definition ─────────────────────────────────────────────
class Column(BaseModel):
    name: str
    kind: ColumnKind = ColumnKind.TEXT
    description: str = ""
    nullable: bool = True
    null_rate: float = 0.0
    unique: bool = False
    pii: PIILevel = PIILevel.NONE
    privacy_action: PrivacyAction = PrivacyAction.KEEP
    dp_epsilon: Optional[float] = None     # for DP_NOISE action
    
    # Generation strategy
    strategy: Optional[Strategy] = None
    
    # Detected profile info (filled by profiler)
    minimum: Optional[float] = None
    maximum: Optional[float] = None
    mean: Optional[float] = None
    median: Optional[float] = None
    weights: Optional[dict[str, float]] = None
    format_pattern: Optional[str] = None
    
    # FK reference
    ref: Optional[str] = None              # "customers.customer_id"
    
    # Constraints
    constraints: list[dict[str, Any]] = Field(default_factory=list)
    
    # Metadata
    inference_source: InferenceSource = InferenceSource.USER_DEFINED
    confidence: Confidence = Confidence.HIGH


# ── Missingness config ─────────────────────────────────────────────
class MissingnessConfig(BaseModel):
    default_rate: float = 0.0
    per_column: dict[str, float] = Field(default_factory=dict)
    mechanism: Literal["MCAR", "MAR", "MNAR"] = "MCAR"
    mar_driver: Optional[str] = None       # column that drives MAR


# ── Outlier config ─────────────────────────────────────────────────
class OutlierConfig(BaseModel):
    rate: float = 0.005
    method: Literal["iqr_extreme", "zscore", "boundary", "custom"] = "iqr_extreme"
    factor: float = 3.0


# ── Edge case config ───────────────────────────────────────────────
class EdgeCaseConfig(BaseModel):
    enable: bool = False
    missing_values: bool = True
    boundary_values: bool = True
    rare_categories: bool = True
    duplicates: bool = False
    extreme_numerics: bool = True
    date_boundaries: bool = True
    unicode_names: bool = False
    invalid_records: bool = False
    invalid_count: int = 50
    anomaly_labels: bool = True
    anomaly_rate: float = 0.02
    anomaly_types: list[str] = Field(default_factory=lambda: [
        "duplicate_charge", "amount_spike", "impossible_date",
        "velocity_burst", "null_required_field", "negative_amount"
    ])


# ── Table definition ──────────────────────────────────────────────
class Table(BaseModel):
    name: str
    description: str = ""
    rows: int = 1000
    primary_key: Optional[str] = None
    columns: list[Column]
    missing: MissingnessConfig = Field(default_factory=MissingnessConfig)
    outliers: OutlierConfig = Field(default_factory=OutlierConfig)
    edge_cases: EdgeCaseConfig = Field(default_factory=EdgeCaseConfig)
    
    def get_column(self, name: str) -> Optional[Column]:
        return next((c for c in self.columns if c.name == name), None)
    
    @property
    def fk_columns(self) -> list[Column]:
        return [c for c in self.columns if c.kind == ColumnKind.FK and c.ref]
    
    @property
    def column_names(self) -> list[str]:
        return [c.name for c in self.columns]


# ── Relationship definition ───────────────────────────────────────
class Relationship(BaseModel):
    parent: str                 # table name
    child: str                  # table name
    parent_key: str = ""        # defaults to parent's PK
    child_key: str = ""         # FK column in child
    cardinality: Literal["1:1", "1:N", "N:N"] = "1:N"
    
    # Child count distribution
    dist: Literal["fixed", "poisson", "negbin", "zipf", "empirical", "uniform"] = "negbin"
    mean_children: float = 3.0
    dispersion: float = 1.5
    min_children: int = 0
    max_children: int = 60
    
    # N:N settings
    join_table: Optional[str] = None
    degree_dist_left: Optional[dict] = None
    degree_dist_right: Optional[dict] = None


# ── Business rule ──────────────────────────────────────────────────
class BusinessRule(BaseModel):
    id: str
    expr: str                   # "orders.subtotal == sum(order_items.line_total by order_id)"
    severity: Literal["error", "warn", "info"] = "error"
    description: str = ""


# ── Root schema ────────────────────────────────────────────────────
class SynthSchema(BaseModel):
    version: str = "1"
    name: str = "untitled"
    description: str = ""
    locale: str = "us"
    currency: str = "USD"
    timezone: str = "UTC"
    tables: list[Table]
    relationships: list[Relationship] = Field(default_factory=list)
    rules: list[BusinessRule] = Field(default_factory=list)
    
    # Generation metadata
    generation_mode: Literal["prompt_only", "schema_only", "sample_conditioned"] = "schema_only"
    domain: str = "retail"     # retail, fintech, healthcare, telecom, hr
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    version_history: list[str] = Field(default_factory=lambda: ["v1"])
    
    def get_table(self, name: str) -> Optional[Table]:
        return next((t for t in self.tables if t.name == name), None)
    
    @property
    def table_names(self) -> list[str]:
        return [t.name for t in self.tables]
    
    def dependency_order(self) -> list[str]:
        """Return table names in topological order (parents before children)."""
        graph: dict[str, set[str]] = {t.name: set() for t in self.tables}
        for rel in self.relationships:
            if rel.child in graph:
                graph[rel.child].add(rel.parent)
        
        order = []
        visited: set[str] = set()
        
        def visit(name: str):
            if name in visited:
                return
            visited.add(name)
            for dep in graph.get(name, set()):
                visit(dep)
            order.append(name)
        
        for name in graph:
            visit(name)
        return order
    
    def save(self, path: Union[str, Path]):
        """Save schema to a JSON file."""
        Path(path).write_text(self.model_dump_json(indent=2), encoding="utf-8")
    
    @classmethod
    def load(cls, path: Union[str, Path]) -> "SynthSchema":
        """Load schema from a JSON file."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.model_validate(data)
    
    def schema_hash(self) -> str:
        """Deterministic hash for manifest tracking."""
        import hashlib
        content = self.model_dump_json(exclude={"created_at", "version_history"})
        return f"sha256:{hashlib.sha256(content.encode()).hexdigest()}"
