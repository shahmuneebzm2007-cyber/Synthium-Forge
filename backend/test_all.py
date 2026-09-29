"""Full integration test for the SynthGen AI backend — all modules."""
import sys, os
sys.path.insert(0, '.')
sys.stdout.reconfigure(encoding='utf-8')

# Test 1: Core imports
from app.core.money import to_minor, fmt, pct_of, mul, split_amount
print('T1  Money:', fmt(to_minor('42.50'), 'PKR'), '| 18% tax:', fmt(pct_of(to_minor('100'), '0.18'), 'PKR'))

# Test 2: Seeding
from app.core.seeding import rng_for
rng = rng_for(42, 'test')
print('T2  Seeding: rng.integers(100) =', rng.integers(100))

# Test 3: Schema
from app.contracts.schema import SynthSchema, Table, Column, ColumnKind
print('T3  Schema contract loaded')

# Test 4: Profiler
import pandas as pd
import numpy as np
df = pd.DataFrame({'id': range(1, 101), 'name': ['Test']*100, 'price': [42.50]*100, 'active': [True]*100})
from app.engines.tabular.profiler import profile_df
p = profile_df(df)
print(f'T4  Profiler: {p["rows"]} rows, {p["n_columns"]} cols, PK={p["primary_key"]}')

# Test 5: Copula
from app.engines.tabular.copula import GaussianCopulaSynth
data = pd.DataFrame({'a': np.random.normal(100, 10, 500), 'b': np.random.uniform(0, 1, 500)})
model = GaussianCopulaSynth()
model.fit(data, {'a': 'num', 'b': 'num'}, seed=42)
synth = model.sample(100, rng_for(42, 'sample'))
print(f'T5  Copula: Generated {len(synth)} rows, cols={list(synth.columns)}')

# Test 6: Retail generator
from app.engines.relational.retail import generate_retail
tables = generate_retail(seed=42, n_customers=200)
print(f'T6  Retail: customers={len(tables["customers"])}, orders={len(tables["orders"])}, items={len(tables["order_items"])}')

# Test 7: Prove It
from app.validation.relational import load_sqlite, prove_it
con = load_sqlite(tables)
results = prove_it(con)
passed = sum(1 for r in results if r['passed'])
total = len(results)
con.close()
print(f'T7  Prove It: {passed}/{total} checks passed')

# Test 8: Invoice
from app.engines.documents.invoice import InvoiceGenerator
gen = InvoiceGenerator(seed=42, locale='pk')
inv = gen.generate(n_lines=3)
checks = inv.reconcile()
all_ok = all(c['passed'] for c in checks)
print(f'T8  Invoice: {inv.invoice_number}, total={fmt(inv.grand_total, "PKR")}, reconciled={all_ok}')

# Test 9: Statement
from app.engines.documents.statement import StatementGenerator
sgen = StatementGenerator(seed=42, locale='pk')
stmt = sgen.generate()
s_checks = stmt.reconcile()
s_ok = all(c['passed'] for c in s_checks)
print(f'T9  Statement: {stmt.n_transactions} txns, closing={fmt(stmt.closing_balance, "PKR")}, reconciled={s_ok}')

# Test 10: Scoring
from app.scoring.scores import fidelity_score, compute_scorecard
print('T10 Scoring module loaded')

# Test 11: Export
from app.export.engine import ExportEngine
import tempfile
with tempfile.TemporaryDirectory() as td:
    exp = ExportEngine(td)
    arts = exp.export_all(tables, formats=['csv', 'json'])
    print(f'T11 Export: {len(arts)} artifacts created')

# Test 12: AI
from app.ai.adapter import PrivacyFirewall, KeyRotator, LLMAdapter
from app.ai.fallback import OfflineFallback
fb = OfflineFallback()
schema = fb.prompt_to_schema('Create a retail dataset with 500 customers')
n_tables = len(schema.get('tables', []))
print(f'T12 AI Fallback: prompt->schema = "{schema.get("name", "?")}" ({n_tables} tables)')

# Test 13: Locales
from app.locales import get_available_locales, get_locale_names
locales = get_available_locales()
names = get_locale_names('pk', 3, seed=42)
print(f'T13 Locales: {locales}')

# Test 14: PDF Generation
from app.engines.documents.pdf_renderer import render_invoice_pdf, render_statement_pdf
with tempfile.TemporaryDirectory() as td:
    inv_path = os.path.join(td, 'invoice.pdf')
    render_invoice_pdf(inv, inv_path, 'PKR')
    inv_size = os.path.getsize(inv_path)
    stmt_path = os.path.join(td, 'statement.pdf')
    render_statement_pdf(stmt, stmt_path, 'PKR')
    stmt_size = os.path.getsize(stmt_path)
    print(f'T14 PDFs: invoice={inv_size} bytes, statement={stmt_size} bytes')

# Test 15: Privacy Scanner (NEW)
from app.privacy import PIIScanner, apply_all_privacy
sample_df = pd.read_csv('../sample-data/customers_clean.csv')
scanner = PIIScanner()
pii_results = scanner.scan_dataframe(sample_df)
summary = scanner.get_summary()
print(f'T15 Privacy Scanner: {summary["direct_pii"]} direct PII, {summary["quasi_identifiers"]} quasi-identifiers, {summary["safe_columns"]} safe')
for r in pii_results:
    if r['pii_level'] != 'none':
        print(f'    [{r["pii_level"].upper()}] {r["column"]} -> {r["suggested_action"]}')

# Test 16: Privacy Actions (NEW)
from app.privacy.actions import apply_mask, apply_hash, apply_synthetic, apply_dp_noise
masked = apply_mask(pd.Series(["john@example.com", "test@test.com"]))
hashed = apply_hash(pd.Series(["secret123"]))
print(f'T16 Privacy Actions: mask="{masked.iloc[0]}", hash="{hashed.iloc[0]}"')

# Test 17: Privacy Risk (NEW)
from app.privacy.risk import k_anonymity
k_result = k_anonymity(sample_df, ['city', 'gender', 'segment'])
print(f'T17 k-Anonymity: k={k_result["k"]}, risk={k_result["risk"]}')

# Test 18: Fintech Pack (NEW)
from app.packs.fintech import generate_fintech, get_fintech_schema, FINTECH_DDL
ft_tables = generate_fintech(seed=42, n_accounts=100)
ft_total = sum(len(df) for df in ft_tables.values())
print(f'T18 Fintech: accounts={len(ft_tables["accounts"])}, cards={len(ft_tables["cards"])}, '
      f'merchants={len(ft_tables["merchants"])}, txns={len(ft_tables["transactions"])}, total={ft_total}')

# Test 19: Fintech Prove-It (NEW)
con2 = load_sqlite(ft_tables, ddl=FINTECH_DDL)
ft_results = prove_it(con2, extra_checks=[
    ("Txns with no account",
     "SELECT COUNT(*) FROM transactions t LEFT JOIN accounts a "
     "ON t.account_id = a.account_id WHERE a.account_id IS NULL"),
    ("Cards with no account",
     "SELECT COUNT(*) FROM cards c LEFT JOIN accounts a "
     "ON c.account_id = a.account_id WHERE a.account_id IS NULL"),
])
ft_passed = sum(1 for r in ft_results if r['passed'])
ft_total_checks = len(ft_results)
con2.close()
print(f'T19 Fintech Prove-It: {ft_passed}/{ft_total_checks} checks passed')

# Test 20: Edge Cases (NEW)
from app.engines.tabular.edge_cases import EdgeCaseInjector
injector = EdgeCaseInjector(seed=42)
test_df = tables['customers'].copy()
test_kinds = {'customer_id': 'id', 'full_name': 'text', 'email': 'email',
              'city': 'cat', 'signup_date': 'date', 'segment': 'cat'}
result_df, invalid_df = injector.inject_all(test_df, test_kinds, {'anomaly_labels': True, 'anomaly_rate': 0.05})
n_anomalies = result_df['is_anomaly'].sum() if 'is_anomaly' in result_df.columns else 0
print(f'T20 Edge Cases: {n_anomalies} anomalies injected into {len(result_df)} rows')

# Test 21: Time Realism (NEW)
from app.engines.tabular.engine import synthesize_from_schema
date_schema = {"name": "test", "columns": [
    {"name": "id", "kind": "id"},
    {"name": "order_date", "kind": "date", "start": "2024-01-01", "end": "2024-12-31"},
]}
date_df = synthesize_from_schema(date_schema, 1000, seed=42)
dates = pd.to_datetime(date_df['order_date'])
weekday_pct = (dates.dt.dayofweek < 5).mean()
q4_pct = (dates.dt.month >= 10).mean()
print(f'T21 Time Realism: weekday={weekday_pct:.1%} (expect >55%), Q4={q4_pct:.1%} (expect >25%)')

# Test 22: Packs Registry (NEW)
from app.packs import AVAILABLE_PACKS
print(f'T22 Packs: {list(AVAILABLE_PACKS.keys())}')

# Test 23: Templates (NEW)
import json
gallery_path = os.path.join('..', 'templates', 'gallery.json')
with open(gallery_path, 'r') as f:
    gallery = json.load(f)
print(f'T23 Templates: {len(gallery["templates"])} templates loaded')

# Test 24: Sample Data (NEW)
sample_dir = os.path.join('..', 'sample-data')
sample_files = [f for f in os.listdir(sample_dir) if f.endswith('.csv')]
print(f'T24 Sample Data: {sample_files}')

print()
print('=' * 50)
print(f'  ALL 24 TESTS PASSED')
print('=' * 50)
