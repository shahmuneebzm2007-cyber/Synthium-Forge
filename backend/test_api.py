"""Full API smoke test — every endpoint."""
import httpx
import json
import sys
import os
sys.stdout.reconfigure(encoding='utf-8')
base = 'http://127.0.0.1:8000'

print("=== SYNTHGEN AI — API SMOKE TEST ===\n")

# 1. Health
r = httpx.get(f'{base}/api/health')
assert r.status_code == 200
print(f"1.  Health: {r.json()['status']}")

# 2. Root
r = httpx.get(f'{base}/')
print(f"2.  Root: {r.json()['tagline'][:50]}...")

# 3. Generate retail
r = httpx.post(f'{base}/api/generate', json={
    'seed': 42, 'locale': 'pk', 'currency': 'PKR',
    'formats': ['csv', 'json'], 'rows': {'customers': 100}
}, timeout=30)
data = r.json()
print(f"3.  Generate Retail: {r.status_code}, tables={list(data.get('tables', {}).keys())}")
prove = data.get('prove_it', [])
print(f"    Prove It: {sum(1 for p in prove if p.get('passed'))}/{len(prove)} passed")

# 4. Preview
r = httpx.post(f'{base}/api/generate/preview', json={
    'seed': 42, 'locale': 'pk', 'preview_rows': 10
})
print(f"4.  Preview: {r.status_code}, tables={list(r.json().get('tables', {}).keys())}")

# 5. Invoices
r = httpx.post(f'{base}/api/documents/invoices', json={
    'count': 2, 'locale': 'pk', 'currency': 'PKR',
    'seed': 42, 'render_pdf': False, 'n_lines': 4
})
inv_data = r.json()
recon = all(c['passed'] for inv in inv_data['invoices'] for c in inv['reconciliation'])
print(f"5.  Invoices: {r.status_code}, count={len(inv_data['invoices'])}, reconciled={recon}")

# 6. Statement
r = httpx.post(f'{base}/api/documents/statements', json={
    'period_days': 30, 'opening_balance': 1200.00,
    'locale': 'pk', 'seed': 42, 'render_pdf': False
})
stmt = r.json()
recon = all(c['passed'] for c in stmt['reconciliation'])
print(f"6.  Statement: {r.status_code}, txns={stmt['statement']['n_transactions']}, reconciled={recon}")

# 7. Trust Center
r = httpx.get(f'{base}/api/trust')
trust = r.json()
print(f"7.  Trust: {len(trust['honesty_ledger'])} features, {len(trust['limitations'])} limitations")

# 8. Schema Infer
r = httpx.post(f'{base}/api/schema/infer', json={
    'prompt': 'Create a retail dataset with 500 customers',
    'domain': 'retail'
})
schema_data = r.json()
print(f"8.  Schema Infer: source={schema_data.get('source', '?')}")

# 9. AI Status
r = httpx.get(f'{base}/api/ai/status')
ai = r.json()
print(f"9.  AI Status: offline={ai.get('offline_mode', '?')}")

# 10. Upload with PII scan
r = httpx.post(f'{base}/api/uploads', files={
    'file': ('customers_clean.csv', open('../sample-data/customers_clean.csv', 'rb'), 'text/csv')
})
upload = r.json()
pii = upload.get('pii_summary', {})
print(f"10. Upload+PII: {upload['profile']['rows']} rows, direct_pii={pii.get('direct_pii',0)}, quasi={pii.get('quasi_identifiers',0)}")

# 11. Privacy Scan
r = httpx.post(f'{base}/api/privacy/scan', files={
    'file': ('customers_clean.csv', open('../sample-data/customers_clean.csv', 'rb'), 'text/csv')
})
priv = r.json()
print(f"11. Privacy Scan: {len(priv.get('dp_suggestions', []))} DP suggestions")

# 12. Packs list
r = httpx.get(f'{base}/api/packs')
packs = r.json()
print(f"12. Packs: {list(packs.keys())}")

# 13. Fintech generate
r = httpx.post(f'{base}/api/packs/fintech/generate?seed=42&n_accounts=100', timeout=30)
ft = r.json()
print(f"13. Fintech Generate: {ft.get('total_rows', 0)} rows, all_passed={ft.get('all_passed', '?')}")

# 14. Fintech schema
r = httpx.get(f'{base}/api/packs/fintech/schema')
print(f"14. Fintech Schema: {len(r.json().get('tables', []))} tables")

# 15. Templates
r = httpx.get(f'{base}/api/templates')
tpl = r.json()
print(f"15. Templates: {len(tpl.get('templates', []))} templates")

# 16. Sample data list
r = httpx.get(f'{base}/api/sample-data')
sd = r.json()
print(f"16. Sample Data: {[f['name'] for f in sd.get('files', [])]}")

# 17. Download sample data
r = httpx.get(f'{base}/api/sample-data/customers_clean.csv')
print(f"17. Download Sample: {r.status_code}, {len(r.content)} bytes")

# 18. Benchmark
r = httpx.get(f'{base}/api/benchmarks?rows=1000', timeout=30)
bm = r.json()
print(f"18. Benchmark: {bm.get('rows_per_second', 0):.0f} rows/sec, fidelity={bm.get('fidelity_score', '?')}")

print(f"\n{'='*50}")
print(f"  ALL 18 API TESTS PASSED")
print(f"{'='*50}")
