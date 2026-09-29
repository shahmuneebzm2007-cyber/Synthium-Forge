"""
Run Orchestrator — manages the full generation pipeline:
  profile → fit → generate → validate → score → export → manifest

Supports progress tracking via SSE, cancellation, and preview mode.
"""
from __future__ import annotations

import time
import uuid
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from app.core.config import get_config
from app.core.seeding import rng_for
from app.contracts.run_config import (
    RunConfig, RunStatus, RunManifest, ArtifactRecord, AIUsageRecord, TimingRecord
)
from app.engines.tabular.engine import synthesize, synthesize_from_schema
from app.engines.tabular.edge_cases import EdgeCaseInjector
from app.engines.relational.retail import generate_retail, get_retail_schema, RETAIL_DDL
from app.packs.fintech import generate_fintech, get_fintech_schema, FINTECH_DDL
from app.engines.documents.invoice import InvoiceGenerator
from app.engines.documents.statement import StatementGenerator
from app.validation.relational import load_sqlite, prove_it, schema_to_ddl
from app.scoring.scores import compute_scorecard
from app.export.engine import ExportEngine


_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="synthgen")
_runs: dict[str, RunStatus] = {}
_run_data: dict[str, dict] = {}


class RunOrchestrator:
    """Orchestrates the full generation pipeline."""

    def __init__(self):
        self.config = get_config()

    def _update(self, run_id: str, status: str, progress: float, step: str):
        if run_id in _runs:
            _runs[run_id].status = status
            _runs[run_id].progress = progress
            _runs[run_id].current_step = step

    async def execute_run(self, schema: dict, config: RunConfig) -> dict:
        """Execute a full generation run."""
        run_id = config.project_id or str(uuid.uuid4())[:12]
        _runs[run_id] = RunStatus(run_id=run_id, started_at=datetime.utcnow())
        timings: dict[str, int] = {}

        try:
            domain = schema.get("domain", "retail")
            locale = config.locale or schema.get("locale", "us")
            seed = config.seed

            # ── 1. Generate data ──────────────────────────────────
            self._update(run_id, "generating", 0.1, "Generating tables...")
            t0 = time.time()

            if domain == "retail" and not config.prompt:
                # Use the demo retail generator
                n_customers = config.rows.get("customers", 1000)
                tables = generate_retail(
                    seed=seed,
                    n_customers=n_customers,
                    locale=locale,
                )
                kinds = {
                    "customer_id": "id", "full_name": "text", "email": "email",
                    "city": "cat", "signup_date": "date", "segment": "cat",
                    "sku": "id", "name": "text", "category": "cat", "unit_price": "money",
                    "order_id": "id", "order_date": "date", "status": "cat",
                    "subtotal": "money", "discount": "money", "tax": "money", "total": "money",
                    "item_id": "id", "quantity": "int", "line_total": "money",
                }
                used_ddl = RETAIL_DDL
            elif domain == "fintech" and not config.prompt:
                n_accounts = config.rows.get("accounts", 500)
                tables = generate_fintech(
                    seed=seed,
                    n_accounts=n_accounts,
                    locale=locale,
                )
                kinds = {
                    "account_id": "id", "account_type": "cat", "institution": "cat",
                    "open_date": "date", "opening_balance": "money",
                    "holder_name": "text", "holder_email": "email", "status": "cat",
                    "card_id": "id", "card_number": "text", "network": "cat",
                    "expiry": "text", "daily_limit": "money",
                    "merchant_id": "id", "category": "cat", "mcc_code": "int",
                    "tx_id": "id", "tx_date": "date", "tx_type": "cat",
                    "amount": "money", "balance_after": "money", "description": "text",
                }
                used_ddl = FINTECH_DDL
            else:
                # Schema-only generation
                tables = {}
                kinds = {}
                used_ddl = None
                for table_def in schema.get("tables", []):
                    n = config.rows.get(table_def["name"], table_def.get("rows", 1000))
                    df = synthesize_from_schema(table_def, n, seed, locale)
                    tables[table_def["name"]] = df
                    for col in table_def.get("columns", []):
                        kinds[col["name"]] = col.get("kind", "text")

            timings["generate_ms"] = int((time.time() - t0) * 1000)

            # ── 2. Edge cases ─────────────────────────────────────
            if config.enable_edge_cases:
                self._update(run_id, "generating", 0.3, "Injecting edge cases...")
                injector = EdgeCaseInjector(seed)
                for tname, df in tables.items():
                    table_kinds = {c: kinds.get(c, "text") for c in df.columns}
                    tables[tname], _ = injector.inject_all(df, table_kinds, {
                        "anomaly_labels": True,
                        "anomaly_rate": config.edge_case_rate,
                    })

            # ── 3. Validate ───────────────────────────────────────
            self._update(run_id, "validating", 0.5, "Running integrity checks...")
            t0 = time.time()

            prove_results = []
            if used_ddl and len(tables) > 1:
                try:
                    con = load_sqlite(tables, ddl=used_ddl)
                    prove_results = prove_it(con)
                    con.close()
                except Exception as e:
                    prove_results = [{"check": "SQLite validation", "error": str(e),
                                       "passed": False, "violations": -1}]

            timings["validate_ms"] = int((time.time() - t0) * 1000)

            # ── 4. Score ──────────────────────────────────────────
            self._update(run_id, "validating", 0.6, "Computing scorecard...")
            scorecard = compute_scorecard(None, next(iter(tables.values())),
                                           kinds, mode=config.mode)

            # ── 5. Export ─────────────────────────────────────────
            self._update(run_id, "exporting", 0.7, "Exporting artifacts...")
            t0 = time.time()

            export_dir = self.config.storage.data_dir / "artifacts" / run_id
            exporter = ExportEngine(str(export_dir))
            artifacts = exporter.export_all(
                tables,
                formats=config.export.formats,
                schema_dict=schema if domain == "retail" else None,
            )

            timings["export_ms"] = int((time.time() - t0) * 1000)

            # ── 6. Build manifest ─────────────────────────────────
            self._update(run_id, "completed", 1.0, "Done!")
            total_rows = sum(len(df) for df in tables.values())
            total_ms = sum(timings.values())

            manifest = {
                "run_id": run_id,
                "seed": seed,
                "generation_mode": config.mode,
                "domain": domain,
                "locale": locale,
                "timings": {
                    **timings,
                    "total_ms": total_ms,
                    "rows_per_second": round(total_rows / max(total_ms / 1000, 0.001), 1),
                },
                "tables": {name: {"rows": len(df), "columns": len(df.columns)}
                           for name, df in tables.items()},
                "artifacts": artifacts,
                "prove_it": prove_results,
                "scorecard": scorecard,
                "software": {
                    "python": sys.version,
                    "platform": sys.platform,
                },
            }

            _runs[run_id].status = "completed"
            _runs[run_id].completed_at = datetime.utcnow()
            _run_data[run_id] = {
                "tables": tables,
                "manifest": manifest,
                "prove_it": prove_results,
                "scorecard": scorecard,
            }

            return manifest

        except Exception as e:
            _runs[run_id].status = "failed"
            _runs[run_id].error = str(e)
            raise

    async def execute_preview(self, schema: dict, config: RunConfig) -> dict:
        """Quick 50-row preview with no exports."""
        config.is_preview = True
        config.export = type(config.export)(formats=[])
        preview_config = config.model_copy()

        tables = {}
        for table_def in schema.get("tables", []):
            n = min(config.preview_rows, table_def.get("rows", 50))
            df = synthesize_from_schema(table_def, n, config.seed, config.locale)
            tables[table_def["name"]] = df

        return {
            "tables": {name: df.to_dict("records") for name, df in tables.items()},
            "preview_rows": config.preview_rows,
        }

    def get_status(self, run_id: str) -> Optional[RunStatus]:
        return _runs.get(run_id)

    def get_run_data(self, run_id: str) -> Optional[dict]:
        return _run_data.get(run_id)

    def cancel_run(self, run_id: str) -> bool:
        if run_id in _runs:
            _runs[run_id].status = "cancelled"
            return True
        return False
