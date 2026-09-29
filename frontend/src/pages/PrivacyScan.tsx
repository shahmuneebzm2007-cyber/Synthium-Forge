import { useState } from 'react';
import { UploadCloud, ShieldAlert, CheckCircle2, AlertTriangle, ShieldCheck } from 'lucide-react';
import api from '../api';

export default function PrivacyScan() {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState('');

  const handleScan = async () => {
    if (!file) return;
    setLoading(true);
    setError('');
    
    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await api.post('/privacy/scan', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      setResult(res.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6">
        <div className="flex justify-between items-start mb-6">
          <div>
            <h2 className="text-lg font-semibold text-slate-800 flex items-center">
              <ShieldAlert className="w-5 h-5 mr-2 text-rose-500" />
              Privacy & PII Scanner
            </h2>
            <p className="text-sm text-slate-500 mt-1">Upload a dataset to detect direct identifiers and combination risks.</p>
          </div>
        </div>
        
        <div className="border-2 border-dashed border-slate-300 rounded-lg p-8 flex flex-col items-center justify-center hover:bg-slate-50 transition-colors">
          <UploadCloud className="w-10 h-10 text-slate-400 mb-3" />
          <input 
            type="file" 
            accept=".csv"
            className="hidden" 
            id="privacy-file"
            onChange={(e) => setFile(e.target.files?.[0] || null)}
          />
          <label htmlFor="privacy-file" className="cursor-pointer text-sm text-blue-600 hover:text-blue-700 font-medium bg-blue-50 px-4 py-2 rounded-full mb-3">
            {file ? file.name : 'Choose CSV File to Scan'}
          </label>
          <p className="text-xs text-slate-400">Files remain locally processed.</p>
        </div>
        
        <button 
          onClick={handleScan}
          disabled={!file || loading}
          className="mt-6 w-full bg-slate-900 hover:bg-slate-800 text-white font-medium py-2.5 rounded-lg disabled:opacity-50 transition-colors"
        >
          {loading ? 'Running Deep Scan...' : 'Analyze Privacy Risks'}
        </button>
      </div>

      {error && (
        <div className="bg-red-50 text-red-700 p-4 rounded-lg flex items-start border border-red-200">
          <AlertTriangle className="w-5 h-5 mr-3 shrink-0 mt-0.5" />
          <p className="text-sm">{error}</p>
        </div>
      )}

      {result && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 animate-in fade-in slide-in-from-bottom-4">
          <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
            <h3 className="text-md font-semibold text-slate-800 mb-4">Column Risk Assessment</h3>
            <div className="space-y-3">
              {result.scan_results?.map((col: any) => (
                <div key={col.column} className="flex justify-between items-center p-3 rounded-lg bg-slate-50 border border-slate-100">
                  <span className="font-mono text-sm text-slate-700 font-medium">{col.column}</span>
                  {col.pii_level === 'direct' && <span className="px-2.5 py-1 bg-rose-100 text-rose-700 text-xs font-semibold rounded-full">Direct PII</span>}
                  {col.pii_level === 'quasi' && <span className="px-2.5 py-1 bg-amber-100 text-amber-700 text-xs font-semibold rounded-full">Quasi-ID</span>}
                  {col.pii_level === 'none' && <span className="px-2.5 py-1 bg-green-100 text-green-700 text-xs font-semibold rounded-full flex items-center"><CheckCircle2 className="w-3 h-3 mr-1" />Safe</span>}
                </div>
              ))}
            </div>
          </div>
          
          <div className="space-y-6">
             <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm">
              <h3 className="text-md font-semibold text-slate-800 mb-4 flex items-center">
                <ShieldCheck className="w-4 h-4 mr-2 text-slate-500" /> DP-Epsilon Recommendations
              </h3>
              <div className="space-y-4">
                {result.dp_suggestions?.map((dp: any, idx: number) => (
                  <div key={idx} className="border-l-2 border-blue-500 pl-4 py-1">
                    <p className="text-sm font-semibold text-slate-800">{dp.column}</p>
                    <p className="text-xs text-slate-500 mt-1">{dp.note}</p>
                    <div className="mt-2 flex items-center space-x-4 text-xs font-medium">
                      <span className="bg-blue-50 text-blue-700 px-2 py-1 rounded">ε = {dp.suggested_epsilon}</span>
                      <span className="text-slate-400 capitalize">Noise: {dp.noise_level}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
