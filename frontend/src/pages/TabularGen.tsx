import { useState } from 'react';
import { UploadCloud, Play, Download, Activity, CheckCircle2, AlertTriangle, Settings } from 'lucide-react';
import api, { API_BASE_URL } from '../api';

export default function TabularGen() {
  const [file, setFile] = useState<File | null>(null);
  const [rows, setRows] = useState(100);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState('');

  const handleUpload = async () => {
    if (!file) return;
    setLoading(true);
    setError('');
    
    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await api.post(`/generate/tabular?n_rows=${rows}&formats=csv,json,parquet,sqlite`, formData, {
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
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="p-6 border-b border-slate-100">
          <h2 className="text-lg font-semibold text-slate-800">Generate Tabular Data</h2>
          <p className="text-sm text-slate-500 mt-1">Upload a seed CSV to train the Copula and generate synthetic rows.</p>
        </div>
        
        <div className="p-6 grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="space-y-4">
            <label className="block text-sm font-medium text-slate-700">Source Dataset</label>
            <div className="border-2 border-dashed border-slate-300 rounded-lg p-6 flex flex-col items-center justify-center hover:bg-slate-50 transition-colors">
              <UploadCloud className="w-8 h-8 text-slate-400 mb-2" />
              <input 
                type="file" 
                accept=".csv"
                className="hidden" 
                id="file-upload"
                onChange={(e) => setFile(e.target.files?.[0] || null)}
              />
              <label htmlFor="file-upload" className="cursor-pointer text-sm text-blue-600 hover:text-blue-700 font-medium">
                {file ? file.name : 'Click to upload CSV'}
              </label>
            </div>
            
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-2">Rows to Generate</label>
              <input 
                type="number" 
                value={rows}
                onChange={(e) => setRows(Number(e.target.value))}
                className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm focus:ring-blue-500 focus:border-blue-500"
              />
            </div>
          </div>
          
          <div className="bg-slate-50 rounded-lg p-6 border border-slate-200 flex flex-col justify-between">
            <div>
              <h3 className="text-sm font-semibold text-slate-800 mb-4 flex items-center">
                <Settings className="w-4 h-4 mr-2 text-slate-500" /> Engine Configuration
              </h3>
              <ul className="space-y-2 text-sm text-slate-600">
                <li className="flex items-center"><CheckCircle2 className="w-4 h-4 mr-2 text-green-500" /> Gaussian Copula Synthesizer</li>
                <li className="flex items-center"><CheckCircle2 className="w-4 h-4 mr-2 text-green-500" /> TSTR Utility Scoring</li>
                <li className="flex items-center"><CheckCircle2 className="w-4 h-4 mr-2 text-green-500" /> Export: CSV, JSON, Parquet, SQLite</li>
              </ul>
            </div>
            
            <button 
              onClick={handleUpload}
              disabled={!file || loading}
              className="mt-6 w-full bg-blue-600 hover:bg-blue-700 text-white font-medium py-2.5 rounded-lg flex items-center justify-center disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {loading ? (
                <span className="flex items-center">
                  <Activity className="w-5 h-5 mr-2 animate-spin" /> Generating...
                </span>
              ) : (
                <span className="flex items-center">
                  <Play className="w-5 h-5 mr-2" /> Synthesize Data
                </span>
              )}
            </button>
          </div>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 text-red-700 p-4 rounded-lg flex items-start border border-red-200">
          <AlertTriangle className="w-5 h-5 mr-3 shrink-0 mt-0.5" />
          <p className="text-sm">{error}</p>
        </div>
      )}

      {result && (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden animate-in fade-in slide-in-from-bottom-4">
          <div className="p-6 border-b border-slate-100 bg-slate-50/50 flex justify-between items-center">
            <h2 className="text-lg font-semibold text-slate-800">Quality Scorecard</h2>
            <span className="px-3 py-1 bg-green-100 text-green-700 text-xs font-semibold rounded-full flex items-center">
              <CheckCircle2 className="w-3 h-3 mr-1" /> Success
            </span>
          </div>
          
          <div className="p-6 grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="bg-white border border-slate-200 p-5 rounded-xl shadow-sm relative overflow-hidden">
              <div className="absolute top-0 left-0 w-1 h-full bg-blue-500"></div>
              <p className="text-sm text-slate-500 font-medium mb-1">Fidelity Score</p>
              <div className="flex items-baseline">
                <span className="text-3xl font-bold text-slate-900">{result.scorecard?.fidelity?.score?.toFixed(1) || 'N/A'}%</span>
              </div>
              <p className="text-xs text-slate-400 mt-2">{result.scorecard?.fidelity?.note}</p>
            </div>
            
            <div className="bg-white border border-slate-200 p-5 rounded-xl shadow-sm relative overflow-hidden">
              <div className="absolute top-0 left-0 w-1 h-full bg-purple-500"></div>
              <p className="text-sm text-slate-500 font-medium mb-1">Utility (TSTR)</p>
              <div className="flex items-baseline">
                <span className="text-3xl font-bold text-slate-900">
                  {result.scorecard?.utility?.skipped ? 'Skipped' : (result.scorecard?.utility?.tstr?.toFixed(3) || 'N/A')}
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-2">
                {result.scorecard?.utility?.skipped ? result.scorecard?.utility?.reason : `Target: ${result.scorecard?.utility?.target}`}
              </p>
            </div>
            
            <div className="bg-white border border-slate-200 p-5 rounded-xl shadow-sm relative overflow-hidden">
              <div className="absolute top-0 left-0 w-1 h-full bg-emerald-500"></div>
              <p className="text-sm text-slate-500 font-medium mb-1">Privacy Risk</p>
              <div className="flex items-baseline">
                <span className="text-3xl font-bold text-slate-900 capitalize">{result.scorecard?.privacy?.level}</span>
              </div>
              <p className="text-xs text-slate-400 mt-2">Exact match rate: {result.scorecard?.privacy?.exact_match_rate}%</p>
            </div>
          </div>
          
          <div className="px-6 pb-6 pt-2">
            <h3 className="text-sm font-semibold text-slate-800 mb-4 flex items-center">
              <Download className="w-4 h-4 mr-2 text-slate-500" /> Exported Artifacts
            </h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              {result.exported_files?.map((file: any) => (
                <a 
                  key={file.name} 
                  href={`${API_BASE_URL}/download/${result.run_id}/${file.name}`}
                  download={file.name}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex flex-col border border-slate-200 rounded-lg p-3 hover:border-blue-400 hover:shadow-sm transition-all cursor-pointer bg-white group"
                >
                  <Download className="w-6 h-6 text-slate-400 group-hover:text-blue-500 mb-2 transition-colors" />
                  <span className="text-sm font-medium text-slate-700 truncate">{file.name}</span>
                  <span className="text-xs text-slate-400 mt-1">{(file.size_bytes / 1024).toFixed(1)} KB</span>
                </a>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
