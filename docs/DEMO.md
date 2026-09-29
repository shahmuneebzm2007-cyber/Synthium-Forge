# SynthGen AI — Demo Quick-Start

## One-Click Demos

### 1. Retail (Pakistan)
```bash
curl -X POST http://localhost:8000/api/generate \
  -H "Content-Type: application/json" \
  -d '{"seed": 42, "locale": "pk", "currency": "PKR", "rows": {"customers": 1000}, "formats": ["csv", "json"]}'
```

### 2. Fintech
```bash
curl -X POST "http://localhost:8000/api/packs/fintech/generate?seed=42&n_accounts=500&locale=us"
```

### 3. Invoice PDF
```bash
curl -X POST http://localhost:8000/api/documents/invoices \
  -H "Content-Type: application/json" \
  -d '{"count": 5, "locale": "pk", "currency": "PKR", "seed": 42, "render_pdf": true}'
```

### 4. Bank Statement
```bash
curl -X POST http://localhost:8000/api/documents/statements \
  -H "Content-Type: application/json" \
  -d '{"period_days": 90, "opening_balance": 1200, "locale": "pk", "seed": 42, "render_pdf": true}'
```

### 5. Upload & Profile
```bash
curl -X POST http://localhost:8000/api/uploads \
  -F "file=@sample-data/orders_messy.csv"
```

### 6. Privacy Scan
```bash
curl -X POST http://localhost:8000/api/privacy/scan \
  -F "file=@sample-data/customers_clean.csv"
```

### 7. Trust Center
```bash
curl http://localhost:8000/api/trust
```

### 8. Benchmark
```bash
curl "http://localhost:8000/api/benchmarks?rows=10000"
```
