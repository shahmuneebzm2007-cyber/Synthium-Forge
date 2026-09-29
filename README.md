# 🌌 Synthium Forge

> **Enterprise-Grade Synthetic Data & Privacy Engine** 
> *Built for HackDataV2*

Synthium Forge is a complete, end-to-end platform for generating mathematically sound, privacy-compliant synthetic data. Designed for data scientists, ML engineers, and compliance teams, it leverages Advanced AI, Gaussian Copulas, and Differential Privacy to create data that is **Realistic**, **Consistent**, and **Provable**.

---

## 🚀 Key Features

### 1. Relational AI Engine (Zero-Violation Integrity)
* **Prompt-to-Schema:** Type a plain English requirement (e.g., *"E-commerce with customers, products, and orders"*), and the AI instantly architects a complete Relational JSON schema.
* **Human-in-the-Loop Config:** Granularly edit the generated schema or configure exact row counts per table directly in the UI.
* **Live SQL Constraint Validation:** Synthesizes interconnected tables while mathematically guaranteeing referential integrity. The engine spins up an in-memory SQLite database, runs `PRAGMA foreign_key_check`, and provides a **"0 Violations" Prove-It badge**.
* **Instant Export:** Download generated artifacts as `CSV`, `JSON`, `Parquet`, or `.sqlite` files.

### 2. Document Studio (Unstructured Generation)
* **Financial Data Engine:** Generates highly realistic, localized tabular transaction data.
* **Math Reconciliation:** Proves data consistency by perfectly calculating subtotals, complex tax brackets, and grand totals down to the exact cent.
* **PDF Rendering:** Uses `ReportLab` to instantly render the reconciled tabular data into beautiful, human-readable PDF Invoices and Bank Statements, previewed live in the browser via Base64.

### 3. Privacy & Compliance Scanner
* **Direct PII Detection:** Scans datasets and automatically flags Direct Identifiers (Names, Emails, Phone Numbers) for synthetic replacement.
* **K-Anonymity & Quasi-Identifiers:** Identifies linkage-attack risks (e.g., City, Age, Signup Date).
* **Differential Privacy (DP-Epsilon):** Recommends specific mathematical noise injection levels (`ε`) to blur group membership while retaining dataset utility.

### 4. Tabular Copula & TSTR ML Scoring
* **Gaussian Copula Synthesis:** Upload a real seed CSV, and the engine learns the multi-variate statistical distributions rather than memorizing rows.
* **Fidelity Scoring:** Mathematically compares the shape and variance of the synthetic data against the real data.
* **TSTR (Train-Synthetic, Test-Real):** Auto-detects categorical targets, trains a Machine Learning classifier exclusively on the synthetic data, and tests its predictive accuracy on the real data to prove ML utility.

---

## 🛠️ Tech Stack

**Frontend:**
* React 18 & TypeScript
* Vite (HMR & Build)
* Tailwind CSS v4 (Utility-first styling)
* Lucide React (Iconography)

**Backend:**
* Python 3.12+
* FastAPI (Asynchronous REST framework)
* Uvicorn (ASGI server)
* Pandas & Numpy (Data manipulation & Copula math)
* ReportLab (PDF Generation)
* SQLite3 (In-memory constraint validation)
* Gemini 2.5 Flash API (Direct HTTP Schema Inference)

---

## 💻 Local Development

### Prerequisites
- Node.js (v18+)
- Python (3.10+)

### 1. Start the Python Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate  # Or `venv\Scripts\activate` on Windows
pip install -r requirements.txt

# Add your Gemini API Key
echo "GEMINI_API_KEY=your_key_here" > .env

# Run the server
python run.py
```
*The backend will run at `http://127.0.0.1:8000`*

### 2. Start the React Frontend
```bash
cd frontend
npm install

# Start the Vite development server
npm run dev
```
*The frontend will run at `http://localhost:5173`*

---

## ☁️ Deployment Architecture

Synthium Forge is designed for modern serverless and PaaS deployment (perfect for the GitHub Student Developer Pack):
* **Frontend:** Deployable to **Vercel** or **Netlify**. Simply set the `VITE_API_URL` environment variable to point to your live backend.
* **Backend:** Deployable to **Render**, **Heroku**, or **DigitalOcean App Platform**. 

*Built with ❤️ for the HackData Hackathon.*
