import { ShieldCheck, Lock, FileCheck, Server, Key, EyeOff } from 'lucide-react';

export default function Compliance() {
  return (
    <div className="space-y-6">
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6">
        <h2 className="text-xl font-bold text-slate-800 flex items-center mb-2">
          <ShieldCheck className="w-6 h-6 mr-2 text-indigo-600" />
          Enterprise Compliance & Privacy Guarantees
        </h2>
        <p className="text-sm text-slate-500 mb-8">
          Synthium Forge is designed from the ground up to guarantee absolute data privacy. Our generation engines 
          meet strict compliance requirements for HIPAA, GDPR, and CCPA by ensuring zero raw data leakage.
        </p>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6 mb-8">
          {/* Card 1 */}
          <div className="bg-slate-50 rounded-lg p-5 border border-slate-100">
            <div className="bg-white w-10 h-10 rounded-full flex items-center justify-center shadow-sm mb-4">
              <EyeOff className="w-5 h-5 text-emerald-600" />
            </div>
            <h3 className="font-semibold text-slate-800 text-sm mb-2">Zero-Leakage Privacy Firewall</h3>
            <p className="text-xs text-slate-600 leading-relaxed">
              Our backend privacy firewall strictly guarantees that no raw row data ever reaches an external LLM. 
              Only aggregate statistics, null-rates, and column names are transmitted to the generation models.
            </p>
          </div>

          {/* Card 2 */}
          <div className="bg-slate-50 rounded-lg p-5 border border-slate-100">
            <div className="bg-white w-10 h-10 rounded-full flex items-center justify-center shadow-sm mb-4">
              <Lock className="w-5 h-5 text-blue-600" />
            </div>
            <h3 className="font-semibold text-slate-800 text-sm mb-2">GDPR & CCPA Compliant</h3>
            <p className="text-xs text-slate-600 leading-relaxed">
              By replacing highly sensitive PII (Personally Identifiable Information) with hyper-realistic synthetic 
              counterparts, the resulting datasets fall entirely outside the scope of GDPR and CCPA regulations.
            </p>
          </div>

          {/* Card 3 */}
          <div className="bg-slate-50 rounded-lg p-5 border border-slate-100">
            <div className="bg-white w-10 h-10 rounded-full flex items-center justify-center shadow-sm mb-4">
              <Server className="w-5 h-5 text-purple-600" />
            </div>
            <h3 className="font-semibold text-slate-800 text-sm mb-2">Offline Deterministic Fallbacks</h3>
            <p className="text-xs text-slate-600 leading-relaxed">
              In highly secure air-gapped environments, our NLP engine can fall back to 100% offline generation,
              ensuring that schema inference and data synthesis never trigger a single external network request.
            </p>
          </div>

          {/* Card 4 */}
          <div className="bg-slate-50 rounded-lg p-5 border border-slate-100">
            <div className="bg-white w-10 h-10 rounded-full flex items-center justify-center shadow-sm mb-4">
              <FileCheck className="w-5 h-5 text-rose-600" />
            </div>
            <h3 className="font-semibold text-slate-800 text-sm mb-2">Prove-It™ Mathematical Verification</h3>
            <p className="text-xs text-slate-600 leading-relaxed">
              Every synthetic bank statement and invoice is cryptographically reconciled. Relational schemas are 
              verified against strict Foreign Key constraint tests before they are ever returned to the user.
            </p>
          </div>

          {/* Card 5 */}
          <div className="bg-slate-50 rounded-lg p-5 border border-slate-100">
            <div className="bg-white w-10 h-10 rounded-full flex items-center justify-center shadow-sm mb-4">
              <Key className="w-5 h-5 text-amber-600" />
            </div>
            <h3 className="font-semibold text-slate-800 text-sm mb-2">LLM Provider Agnosticism</h3>
            <p className="text-xs text-slate-600 leading-relaxed">
              Avoid vendor lock-in and minimize compliance risks by seamlessly rotating between secure infrastructure 
              providers like Anthropic, OpenAI, and Google Gemini using our built-in API Key Rotator.
            </p>
          </div>
        </div>

        <div className="border-t border-slate-200 pt-6">
          <h3 className="text-sm font-semibold text-slate-800 mb-3">Acceptable Use Policy</h3>
          <div className="bg-slate-900 rounded-lg p-4 font-mono text-xs text-slate-300 leading-relaxed h-48 overflow-y-auto">
            <p className="mb-2">1. DEFINITIONS</p>
            <p className="mb-4 text-slate-400">"Synthetic Data" refers to artificial data mathematically modeled to mirror the statistical properties of production data without containing any trace of the original source.</p>
            
            <p className="mb-2">2. PROHIBITED USES</p>
            <p className="mb-4 text-slate-400">Users are strictly prohibited from using the Synthium Forge engine to: (a) generate synthetic credentials for unauthorized access; (b) spoof financial documents for fraudulent loan applications; (c) bypass identity verification (KYC/AML) controls.</p>
            
            <p className="mb-2">3. DATA RETENTION</p>
            <p className="mb-4 text-slate-400">All uploaded CSV schemas and target distributions are processed in memory and immediately discarded. No user data is written to persistent storage without explicit local environment configuration.</p>
          </div>
        </div>
      </div>
    </div>
  );
}
