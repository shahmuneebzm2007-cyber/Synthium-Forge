"""
FastAPI Application — SynthGen AI Backend.

Routes:
  /api/projects     — project management
  /api/uploads      — file upload and profiling
  /api/generate     — generation runs
  /api/documents    — invoice / statement generation
  /api/health       — health check
  /api/trust        — trust center / feature honesty
"""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, UploadFile, File, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.core.config import get_config
from app.contracts.run_config import RunConfig, ExportConfig
from app.engines.tabular.profiler import profile_df, detect_encoding
from app.engines.tabular.engine import synthesize, synthesize_from_schema
from app.engines.relational.retail import generate_retail, get_retail_schema, RETAIL_DDL
from app.engines.documents.invoice import InvoiceGenerator, Invoice, TAX_RULES
from app.engines.documents.statement import StatementGenerator, StatementConfig, BankStatement
from app.engines.documents.pdf_renderer import render_invoice_pdf, render_statement_pdf, render_to_bytes
from app.validation.relational import load_sqlite, prove_it, schema_to_ddl
from app.scoring.scores import compute_scorecard, fidelity_score
from app.export.engine import ExportEngine
from app.ai.adapter import LLMAdapter, PrivacyFirewall, KeyRotator
from app.ai.fallback import OfflineFallback
from app.jobs.orchestrator import RunOrchestrator
from app.privacy import PIIScanner, apply_all_privacy
from app.packs import AVAILABLE_PACKS
from app.packs.fintech import generate_fintech, get_fintech_schema, FINTECH_DDL

# ── App setup ─────────────────────────────────────────────────────
app = FastAPI(
    title="SynthGen AI — Synthetic Data Platform",
    description="Generate realistic, privacy-safe tabular, relational, and document data on demand.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Singletons ────────────────────────────────────────────────────
firewall = PrivacyFirewall()
rotator = KeyRotator()
llm = LLMAdapter(firewall=firewall, rotator=rotator)
fallback = OfflineFallback()
orchestrator = RunOrchestrator()

# In-memory project store (hackathon-grade)
_projects: dict[str, dict] = {}


# ── Request/Response models ───────────────────────────────────────
class GenerateRequest(BaseModel):
    schema_def: dict = Field(default_factory=dict, alias="schema")
    seed: int = 42
    locale: str = "pk"
    currency: str = "PKR"
    mode: str = "schema_only"
    rows: dict[str, int] = Field(default_factory=dict)
    formats: list[str] = Field(default_factory=lambda: ["csv", "json"])
    enable_edge_cases: bool = False
    edge_case_rate: float = 0.02
    prompt: Optional[str] = None
    domain: str = "retail"

class PreviewRequest(BaseModel):
    schema_def: dict = Field(default_factory=dict, alias="schema")
    seed: int = 42
    locale: str = "pk"
    preview_rows: int = 50
    domain: str = "retail"

class InvoiceRequest(BaseModel):
    count: int = 1
    n_lines: int = 3
    locale: str = "pk"
    currency: str = "PKR"
    seed: int = 42
    discount_pct: str = "0"
    render_pdf: bool = True

class StatementRequest(BaseModel):
    period_days: int = 90
    opening_balance: float = 1200.00
    locale: str = "pk"
    currency: str = "PKR"
    seed: int = 42
    min_balance: Optional[float] = None
    target_closing: Optional[float] = None
    avg_transactions_per_month: int = 30
    render_pdf: bool = True
    query: Optional[str] = None

class PromptRequest(BaseModel):
    prompt: str
    domain: str = "retail"

class RefineRequest(BaseModel):
    instruction: str
    current_schema: dict = Field(default_factory=dict)

class ProjectCreate(BaseModel):
    name: str
    domain: str = "retail"
    locale: str = "pk"
    currency: str = "PKR"


# ═══════════════════════════════════════════════════════════════════
#  HEALTH / ROOT
# ═══════════════════════════════════════════════════════════════════

@app.get("/", tags=["Root"])
async def root():
    return {
        "name": "SynthGen AI",
        "version": "1.0.0",
        "tagline": "Realistic · Consistent · Provable",
        "docs": "/docs",
    }

@app.get("/api/health", tags=["Health"])
async def health():
    return {"status": "ok", "python": sys.version, "platform": sys.platform}


# ═══════════════════════════════════════════════════════════════════
#  PROJECTS
# ═══════════════════════════════════════════════════════════════════

@app.post("/api/projects", tags=["Projects"])
async def create_project(req: ProjectCreate):
    pid = str(uuid.uuid4())[:12]
    _projects[pid] = {
        "id": pid, "name": req.name, "domain": req.domain,
        "locale": req.locale, "currency": req.currency,
        "created_at": time.time(), "runs": [],
    }
    return _projects[pid]

@app.get("/api/projects", tags=["Projects"])
async def list_projects():
    return list(_projects.values())

@app.get("/api/projects/{pid}", tags=["Projects"])
async def get_project(pid: str):
    if pid not in _projects:
        raise HTTPException(404, "Project not found")
    return _projects[pid]


# ═══════════════════════════════════════════════════════════════════
#  UPLOADS & PROFILING
# ═══════════════════════════════════════════════════════════════════

@app.post("/api/uploads", tags=["Upload"])
async def upload_file(file: UploadFile = File(...)):
    """Upload a CSV/JSON file and return its profile."""
    content = await file.read()
    fname = file.filename or "upload"

    try:
        if fname.endswith(".json"):
            data = json.loads(content.decode("utf-8"))
            df = pd.DataFrame(data) if isinstance(data, list) else pd.json_normalize(data)
        else:
            enc = detect_encoding(content)
            df = pd.read_csv(io.BytesIO(content), encoding=enc)
    except Exception as e:
        raise HTTPException(400, f"Failed to parse file: {e}")

    profile = profile_df(df)

    # Auto-scan for PII and quasi-identifiers
    scanner = PIIScanner()
    pii_results = scanner.scan_dataframe(df)

    return {
        "filename": fname,
        "profile": profile,
        "preview": df.head(10).to_dict("records"),
        "pii_scan": pii_results,
        "pii_summary": scanner.get_summary(),
    }


@app.post("/api/schema/infer", tags=["Schema"])
async def infer_schema(req: PromptRequest):
    """Convert a prompt or sample profile into a SynthSchema draft."""
    config = get_config()
    if not config.ai.offline:
        try:
            payload = firewall.build_payload({"rows": 0, "columns": []}, req.prompt)
            result = await llm.call(
                prompt=f"Convert this request into a SynthSchema JSON:\n\n{req.prompt}",
                system="You are a data schema designer. Return valid JSON only with this exact structure: {\"tables\": [{\"name\": \"table1\", \"rows\": 10, \"columns\": [{\"name\": \"id\", \"kind\": \"id\", \"nullable\": false}, {\"name\": \"name\", \"kind\": \"text\", \"nullable\": false}]}]}. Use valid kinds like id, text, int, money, date, cat. Include primary keys and foreign keys logically.",
            )
            if not result.get("fallback"):
                return {"schema": result, "source": "ai"}
        except Exception:
            pass

    schema = fallback.prompt_to_schema(req.prompt, req.domain)
    return {"schema": schema, "source": "fallback"}


@app.post("/api/schema/refine", tags=["Schema"])
async def refine_schema(req: RefineRequest):
    """Apply a natural-language instruction to refine the schema."""
    changes = fallback.apply_chat_instruction(req.instruction, req.current_schema)
    return {"changes": changes, "instruction": req.instruction}


# ═══════════════════════════════════════════════════════════════════
#  GENERATION
# ═══════════════════════════════════════════════════════════════════

@app.post("/api/generate", tags=["Generation"])
async def generate(req: GenerateRequest):
    """Run a full generation pipeline."""
    schema = req.schema_def or get_retail_schema()
    if not req.schema_def:
        schema["locale"] = req.locale
        schema["currency"] = req.currency

    config = RunConfig(
        seed=req.seed,
        locale=req.locale,
        currency=req.currency,
        mode=req.mode,
        rows=req.rows,
        enable_edge_cases=req.enable_edge_cases,
        edge_case_rate=req.edge_case_rate,
        prompt=req.prompt,
        export=ExportConfig(formats=req.formats),
    )

    try:
        manifest = await orchestrator.execute_run(schema, config)
        return manifest
    except Exception as e:
        raise HTTPException(500, f"Generation failed: {e}")


@app.post("/api/generate/preview", tags=["Generation"])
async def generate_preview(req: PreviewRequest):
    """Quick 50-row preview."""
    schema = req.schema_def or get_retail_schema()
    config = RunConfig(seed=req.seed, locale=req.locale, is_preview=True,
                       preview_rows=req.preview_rows)
    result = await orchestrator.execute_preview(schema, config)
    return result


@app.get("/api/generate/{run_id}", tags=["Generation"])
async def get_run_status(run_id: str):
    """Get status of a generation run."""
    status = orchestrator.get_status(run_id)
    if not status:
        raise HTTPException(404, "Run not found")
    return status.model_dump()


@app.get("/api/generate/{run_id}/prove", tags=["Generation"])
async def get_prove_it(run_id: str):
    """Get 'Prove It' integrity check results."""
    data = orchestrator.get_run_data(run_id)
    if not data:
        raise HTTPException(404, "Run not found")
    return {"prove_it": data.get("prove_it", []),
            "all_passed": all(r.get("passed", False) for r in data.get("prove_it", []))}


@app.get("/api/generate/{run_id}/scorecard", tags=["Generation"])
async def get_scorecard(run_id: str):
    data = orchestrator.get_run_data(run_id)
    if not data:
        raise HTTPException(404, "Run not found")
    return data.get("scorecard", {})


@app.get("/api/generate/{run_id}/manifest", tags=["Generation"])
async def get_manifest(run_id: str):
    data = orchestrator.get_run_data(run_id)
    if not data:
        raise HTTPException(404, "Run not found")
    return data.get("manifest", {})

from fastapi.responses import FileResponse
import os

@app.get("/api/download/{run_id}/{filename}", tags=["Generation"])
async def download_artifact(run_id: str, filename: str):
    """Download a generated artifact file."""
    config = get_config()
    file_path = config.storage.data_dir / "artifacts" / run_id / filename
    if not file_path.exists():
        raise HTTPException(404, "File not found")
    return FileResponse(path=file_path, filename=filename)

# ═══════════════════════════════════════════════════════════════════
#  DOMAIN PACKS
# ═══════════════════════════════════════════════════════════════════

@app.get("/api/packs", tags=["Packs"])
async def list_packs():
    """List all available domain packs."""
    return AVAILABLE_PACKS


@app.post("/api/packs/fintech/generate", tags=["Packs"])
async def generate_fintech_data(
    seed: int = Query(42),
    n_accounts: int = Query(500, ge=10, le=50000),
    locale: str = Query("us"),
    formats: str = Query("csv,json"),
):
    """Generate a complete fintech dataset (accounts, cards, merchants, transactions)."""
    t0 = time.time()
    tables = generate_fintech(seed=seed, n_accounts=n_accounts, locale=locale)
    elapsed = time.time() - t0
    total_rows = sum(len(df) for df in tables.values())

    # Prove-it for fintech
    from app.validation.relational import load_sqlite as _load_sqlite, prove_it as _prove_it
    try:
        con = _load_sqlite(tables, ddl=FINTECH_DDL)
        prove_results = _prove_it(con, extra_checks=[
            ("Transactions with no matching account",
             "SELECT COUNT(*) FROM transactions t LEFT JOIN accounts a "
             "ON t.account_id = a.account_id WHERE a.account_id IS NULL"),
            ("Cards with no matching account",
             "SELECT COUNT(*) FROM cards c LEFT JOIN accounts a "
             "ON c.account_id = a.account_id WHERE a.account_id IS NULL"),
            ("Transactions with no matching merchant",
             "SELECT COUNT(*) FROM transactions t LEFT JOIN merchants m "
             "ON t.merchant_id = m.merchant_id WHERE m.merchant_id IS NULL"),
        ])
        con.close()
    except Exception as e:
        prove_results = [{"check": "SQLite validation", "error": str(e), "passed": False}]

    # Export
    fmt_list = [f.strip() for f in formats.split(",")]
    export_dir = get_config().storage.data_dir / "artifacts" / f"fintech-{seed}"
    exporter = ExportEngine(str(export_dir))
    artifacts = exporter.export_all(tables, formats=fmt_list, schema_dict=get_fintech_schema())

    return {
        "domain": "fintech",
        "seed": seed,
        "tables": {name: {"rows": len(df), "columns": len(df.columns)} for name, df in tables.items()},
        "total_rows": total_rows,
        "elapsed_seconds": round(elapsed, 3),
        "rows_per_second": round(total_rows / max(elapsed, 0.001), 1),
        "prove_it": prove_results,
        "all_passed": all(r.get("passed", False) for r in prove_results),
        "artifacts": artifacts,
    }


@app.get("/api/packs/fintech/schema", tags=["Packs"])
async def fintech_schema():
    """Get the fintech domain schema definition."""
    return get_fintech_schema()


# ═══════════════════════════════════════════════════════════════════
#  PRIVACY
# ═══════════════════════════════════════════════════════════════════

@app.post("/api/privacy/scan", tags=["Privacy"])
async def scan_privacy(file: UploadFile = File(...)):
    """Upload a file and get a detailed PII + quasi-identifier scan."""
    content = await file.read()
    fname = file.filename or "upload"

    try:
        if fname.endswith(".json"):
            data = json.loads(content.decode("utf-8"))
            df = pd.DataFrame(data) if isinstance(data, list) else pd.json_normalize(data)
        else:
            enc = detect_encoding(content)
            df = pd.read_csv(io.BytesIO(content), encoding=enc)
    except Exception as e:
        raise HTTPException(400, f"Failed to parse file: {e}")

    scanner = PIIScanner()
    results = scanner.scan_dataframe(df)
    summary = scanner.get_summary()

    # Suggest DP-epsilon for each column
    dp_suggestions = []
    for r in results:
        if r["pii_level"] in ("direct", "quasi"):
            dp_suggestions.append(
                scanner.suggest_dp_epsilon(r["column"], r["pii_level"], len(df))
            )

    return {
        "filename": fname,
        "rows": len(df),
        "scan_results": results,
        "summary": summary,
        "dp_suggestions": dp_suggestions,
    }


# ═══════════════════════════════════════════════════════════════════
#  TABULAR COPULA & SCORING
# ═══════════════════════════════════════════════════════════════════

@app.post("/api/generate/tabular", tags=["Generation"])
async def generate_from_csv(
    file: UploadFile = File(...),
    n_rows: int = Query(100),
    formats: str = Query("csv,json,parquet,xlsx,sqlite")
):
    """Upload a real CSV, train a Copula, generate synthetic data, and score Fidelity/TSTR."""
    content = await file.read()
    enc = detect_encoding(content)
    df = pd.read_csv(io.BytesIO(content), encoding=enc)

    t0 = time.time()
    
    # 1. Synthesize using Gaussian Copula (trains on real data)
    synth_df, metadata = synthesize(df, n=n_rows)
    
    # 2. Compute full scorecard (Fidelity & TSTR Utility)
    # Automatically pick a categorical column for the TSTR ML model test (skip PII/IDs)
    target_col = None
    for c in metadata["profile"]["columns"]:
        col, kind, pii = c["name"], c["kind"], c.get("pii", "none")
        if kind == "cat" and pii != "direct" and df[col].nunique() > 1:
            target_col = col
            break

    # Exclude direct PII (like names/emails) and IDs from Fidelity penalty
    scorecard_kinds = {}
    for c in metadata["profile"]["columns"]:
        if c.get("pii", "none") != "direct" and c["kind"] not in ("id", "text"):
            scorecard_kinds[c["name"]] = c["kind"]

    scorecard = compute_scorecard(
        real_df=df,
        synth_df=synth_df,
        kinds=scorecard_kinds,
        train_df=metadata.get("train"),
        holdout_df=metadata.get("holdout"),
        target_col=target_col,
        mode="sample_conditioned"
    )
    
    # 3. Export to ALL requested formats
    run_id = f"tabular-{uuid.uuid4().hex[:6]}"
    export_dir = get_config().storage.data_dir / "artifacts" / run_id
    exporter = ExportEngine(str(export_dir))
    
    fmt_list = [f.strip() for f in formats.split(",")]
    artifacts = exporter.export_all({"synthetic_data": synth_df}, formats=fmt_list)
    
    return {
        "status": "success",
        "run_id": run_id,
        "elapsed_seconds": round(time.time() - t0, 2),
        "scorecard": scorecard,
        "exported_files": artifacts,
        "export_directory": str(export_dir.absolute()),
        "preview": synth_df.head(5).to_dict(orient="records")
    }

# ═══════════════════════════════════════════════════════════════════
#  DOCUMENTS
# ═══════════════════════════════════════════════════════════════════


@app.post("/api/documents/invoices", tags=["Documents"])
async def generate_invoices(req: InvoiceRequest):
    """Generate invoices with optional PDF rendering."""
    gen = InvoiceGenerator(seed=req.seed, locale=req.locale)
    tax_rules = TAX_RULES.get(req.locale, TAX_RULES["us"])
    invoices = gen.generate_bulk(
        count=req.count,
        n_lines=req.n_lines,
        tax_rules=tax_rules,
        discount_pct=req.discount_pct,
        currency=req.currency,
    )

    result = []
    for inv in invoices:
        item: dict[str, Any] = {
            "invoice": inv.model_dump(),
            "reconciliation": inv.reconcile(),
        }
        if req.render_pdf:
            pdf_bytes = render_to_bytes(render_invoice_pdf, inv, req.currency)
            import base64
            item["pdf_base64"] = base64.b64encode(pdf_bytes).decode()
            item["pdf_size_bytes"] = len(pdf_bytes)
        result.append(item)

    return {"invoices": result, "count": len(result)}


@app.post("/api/documents/statements", tags=["Documents"])
async def generate_statement(req: StatementRequest):
    """Generate a bank statement with optional PDF rendering."""
    gen = StatementGenerator(seed=req.seed, locale=req.locale)

    if req.query:
        constraints = fallback.parse_statement_query(req.query)
        stmt = gen.generate_from_query(constraints)
    else:
        config = StatementConfig(
            seed=req.seed,
            locale=req.locale,
            period_days=req.period_days,
            opening_balance=int(req.opening_balance * 100),
            min_balance=int(req.min_balance * 100) if req.min_balance else None,
            target_closing=int(req.target_closing * 100) if req.target_closing else None,
            currency=req.currency,
            avg_transactions_per_month=req.avg_transactions_per_month,
        )
        stmt = gen.generate(config)

    result: dict[str, Any] = {
        "statement": stmt.model_dump(),
        "reconciliation": stmt.reconcile(),
        "constraints_met": stmt.constraints_met,
    }

    if req.render_pdf:
        pdf_bytes = render_to_bytes(render_statement_pdf, stmt, req.currency)
        import base64
        result["pdf_base64"] = base64.b64encode(pdf_bytes).decode()
        result["pdf_size_bytes"] = len(pdf_bytes)

    return result


# ═══════════════════════════════════════════════════════════════════
#  BENCHMARKS & TRUST
# ═══════════════════════════════════════════════════════════════════

@app.get("/api/benchmarks", tags=["Benchmarks"])
async def run_benchmark(rows: int = Query(default=10000, ge=100, le=1_000_000)):
    """Benchmark generation speed."""
    from app.engines.relational.retail import generate_retail
    t0 = time.time()
    tables = generate_retail(seed=42, n_customers=rows)
    elapsed = time.time() - t0
    total_rows = sum(len(df) for df in tables.values())
    return {
        "requested_customers": rows,
        "total_rows_generated": total_rows,
        "elapsed_seconds": round(elapsed, 3),
        "rows_per_second": round(total_rows / max(elapsed, 0.001), 1),
        "tables": {name: len(df) for name, df in tables.items()},
    }


@app.get("/api/trust", tags=["Trust Center"])
async def trust_center():
    """Feature honesty ledger and limitations."""
    return {
        "product": "SynthGen AI — Synthetic Data Studio",
        "version": "1.0.0",
        "honesty_ledger": [
            {"feature": "Tabular generation (Gaussian copula)", "status": "Real", "notes": "Custom implementation, ~200 lines"},
            {"feature": "Relational generation (retail)", "status": "Real", "notes": "PK/FK integrity, computed totals"},
            {"feature": "Invoice PDF generation", "status": "Real", "notes": "Watermarked, reconciled"},
            {"feature": "Bank statement generation", "status": "Real", "notes": "Goal-directed, constraint satisfaction"},
            {"feature": "Fidelity scoring (KS/TVD)", "status": "Real", "notes": "Published formulas"},
            {"feature": "Privacy indicators", "status": "Real-limited", "notes": "Exact match + DCR only"},
            {"feature": "TSTR utility scoring", "status": "Real-limited", "notes": "HistGradientBoosting, not tuned"},
            {"feature": "DP-Lite noise", "status": "Real-limited", "notes": "Laplace on marginals only, not full DP"},
            {"feature": "AI schema inference", "status": "Demonstrative", "notes": "Works with API keys configured"},
            {"feature": "Chat-to-refine", "status": "Demonstrative", "notes": "Regex-based with AI enhancement"},
            {"feature": "Multi-provider rotation", "status": "Real", "notes": "Health tracking + round-robin"},
            {"feature": "Privacy Firewall", "status": "Real", "notes": "Allow-list only, payload hashing"},
        ],
        "limitations": [
            "DP-Lite provides Laplace noise on marginals only — this is NOT full differential privacy",
            "Privacy indicators are heuristic tests, not proof of anonymity",
            "TSTR utility uses a single model (HistGradientBoosting), not an ensemble",
            "Fidelity scores are similarity measures, not certifications",
            "AI features require API keys; fallback mode is regex-based",
            "All generated documents are clearly marked SYNTHETIC",
            "Account numbers and tax IDs use intentionally invalid patterns",
        ],
        "data_retention": "Artifacts auto-expire after 1 hour. No data is stored permanently.",
        "firewall_summary": firewall.get_summary(),
    }


@app.get("/api/ai/status", tags=["AI"])
async def ai_status():
    """AI key rotation health status."""
    return {
        "rotator": rotator.get_status(),
        "usage": llm.get_usage(),
        "firewall": firewall.get_summary(),
        "offline_mode": get_config().ai.offline,
    }


# ═══════════════════════════════════════════════════════════════════
#  TEMPLATES & SAMPLE DATA
# ═══════════════════════════════════════════════════════════════════

@app.get("/api/templates", tags=["Templates"])
async def list_templates():
    """List all demo templates for the frontend gallery."""
    gallery_path = Path(__file__).parent.parent.parent / "templates" / "gallery.json"
    if not gallery_path.exists():
        return {"templates": []}
    return json.loads(gallery_path.read_text(encoding="utf-8"))


@app.get("/api/sample-data", tags=["Sample Data"])
async def list_sample_data():
    """List available sample data files."""
    sample_dir = Path(__file__).parent.parent.parent / "sample-data"
    if not sample_dir.exists():
        return {"files": []}
    files = []
    for p in sorted(sample_dir.glob("*.csv")):
        files.append({
            "name": p.name,
            "size_bytes": p.stat().st_size,
            "path": f"/api/sample-data/{p.name}",
        })
    return {"files": files}


@app.get("/api/sample-data/{filename}", tags=["Sample Data"])
async def get_sample_data(filename: str):
    """Download a sample data file."""
    sample_dir = Path(__file__).parent.parent.parent / "sample-data"
    fpath = sample_dir / filename
    if not fpath.exists() or ".." in filename:
        raise HTTPException(404, "File not found")
    return FileResponse(str(fpath), filename=filename, media_type="text/csv")


# ═══════════════════════════════════════════════════════════════════
#  STARTUP
# ═══════════════════════════════════════════════════════════════════

@app.on_event("startup")
async def startup():
    config = get_config()
    print(f"[*] SynthGen AI starting on {config.server.host}:{config.server.port}")
    print(f"   AI: {'OFFLINE' if config.ai.offline else config.ai.provider}")
    print(f"   Keys: anthropic={len(config.ai.anthropic_keys)}, "
          f"openai={len(config.ai.openai_keys)}, "
          f"gemini={len(config.ai.gemini_keys)}")
    print(f"   Packs: {list(AVAILABLE_PACKS.keys())}")
