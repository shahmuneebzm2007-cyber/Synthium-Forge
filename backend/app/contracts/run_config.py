"""
RunConfig — everything needed to execute a generation run.
Manifest — everything recorded after a run completes (for replay & audit).
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, Field


# ── Run Configuration ──────────────────────────────────────────────
class PrivacyConfig(BaseModel):
    """Per-run privacy settings."""
    actions: dict[str, str] = Field(default_factory=dict)   # col -> action
    dp_epsilon: dict[str, float] = Field(default_factory=dict)  # col -> ε
    salt: str = "project-salt"


class ExportConfig(BaseModel):
    """What to export after generation."""
    formats: list[str] = Field(default_factory=lambda: ["csv", "json"])
    sql_dialect: Literal["sqlite", "postgres", "mysql"] = "sqlite"
    include_report: bool = True
    include_manifest: bool = True
    include_invalid_fixtures: bool = False


class RunConfig(BaseModel):
    """Complete configuration for a generation run."""
    project_id: str = ""
    project_name: str = "untitled"
    
    # Core settings
    seed: int = 42
    locale: str = "us"
    currency: str = "USD"
    timezone: str = "UTC"
    
    # Per-table row overrides
    rows: dict[str, int] = Field(default_factory=dict)  # table_name -> count
    
    # Generation mode
    mode: Literal["prompt_only", "schema_only", "sample_conditioned"] = "schema_only"
    prompt: Optional[str] = None
    
    # Privacy
    privacy: PrivacyConfig = Field(default_factory=PrivacyConfig)
    
    # Export
    export: ExportConfig = Field(default_factory=ExportConfig)
    
    # AI settings
    use_ai: bool = True
    ai_provider: Optional[str] = None
    ai_model: Optional[str] = None
    
    # Edge cases
    enable_edge_cases: bool = False
    edge_case_rate: float = 0.02
    
    # Preview mode
    is_preview: bool = False
    preview_rows: int = 50


# ── Run Status ─────────────────────────────────────────────────────
class RunStatus(BaseModel):
    """Live status of a generation run."""
    run_id: str
    status: Literal["queued", "profiling", "fitting", "generating", "validating",
                     "exporting", "completed", "failed", "cancelled"] = "queued"
    progress: float = 0.0        # 0.0 - 1.0
    current_step: str = ""
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)


# ── Artifact record ───────────────────────────────────────────────
class ArtifactRecord(BaseModel):
    name: str
    format: str
    size_bytes: int = 0
    sha256: str = ""
    path: str = ""
    table_name: Optional[str] = None


# ── AI usage record ───────────────────────────────────────────────
class AIUsageRecord(BaseModel):
    provider: str = ""
    model: str = ""
    calls: int = 0
    total_tokens: int = 0
    firewall_active: bool = True
    firewall_payload_hashes: list[str] = Field(default_factory=list)
    fallback_used: bool = False
    offline_mode: bool = False


# ── Timing record ─────────────────────────────────────────────────
class TimingRecord(BaseModel):
    profile_ms: int = 0
    fit_ms: int = 0
    generate_ms: int = 0
    validate_ms: int = 0
    export_ms: int = 0
    total_ms: int = 0
    rows_per_second: float = 0.0


# ── Run Manifest ──────────────────────────────────────────────────
class RunManifest(BaseModel):
    """Complete record of a generation run for replay and audit.
    
    `synthgen replay manifest.json` must reproduce artifacts with
    identical SHA-256 on the same platform + Python version.
    """
    run_id: str
    schema_hash: str = ""
    schema_version_history: list[str] = Field(default_factory=list)
    
    # Config snapshot
    seed: int = 42
    config: dict[str, Any] = Field(default_factory=dict)
    generation_mode: str = "schema_only"
    
    # AI info
    ai: AIUsageRecord = Field(default_factory=AIUsageRecord)
    
    # Software versions
    software: dict[str, str] = Field(default_factory=dict)
    
    # Timings
    timings: TimingRecord = Field(default_factory=TimingRecord)
    
    # Outputs
    artifacts: list[ArtifactRecord] = Field(default_factory=list)
    report_ref: str = ""
    
    # Scores summary
    scores: dict[str, Any] = Field(default_factory=dict)
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    status: str = "completed"
    
    def save(self, path: Union[str, Path]):
        Path(path).write_text(self.model_dump_json(indent=2), encoding="utf-8")
    
    @classmethod
    def load(cls, path: Union[str, Path]) -> "RunManifest":
        return cls.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))


# ── Project metadata ──────────────────────────────────────────────
class Project(BaseModel):
    """Top-level project container."""
    id: str
    name: str
    description: str = ""
    domain: str = "retail"
    locale: str = "us"
    currency: str = "USD"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    run_count: int = 0
    schema_path: Optional[str] = None
    latest_run_id: Optional[str] = None
