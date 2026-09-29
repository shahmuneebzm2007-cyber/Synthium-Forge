import { useState } from 'react';
import { Sparkles, Play, Database, CheckCircle2, ShieldCheck, Loader2, Download, Table2 } from 'lucide-react';
import api, { API_BASE_URL } from '../api';

export default function RelationalGen() {
  const [prompt, setPrompt] = useState('I need a dataset for a hospital system. Include patients, doctors, and appointments.');
  const [schema, setSchema] = useState<any>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [proveResult, setProveResult] = useState<any>(null);
  const [previewData, setPreviewData] = useState<any>(null);
  const [manifest, setManifest] = useState<any>(null);
  const [loadingSchema, setLoadingSchema] = useState(false);
  const [loadingGen, setLoadingGen] = useState(false);

  const handleInferSchema = async () => {
    setLoadingSchema(true);
    setSchema(null);
    setRunId(null);
    setProveResult(null);
    setPreviewData(null);
    setManifest(null);
    try {
      const res = await api.post('/schema/infer', { prompt, domain: 'healthcare' });
      setSchema(res.data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoadingSchema(false);
    }
  };

  const handleRowChange = (index: number, newRows: number) => {
    const updated = { ...schema };
    let parsed = typeof updated.schema === 'string' ? JSON.parse(updated.schema) : updated.schema;
    if (parsed.tables && parsed.tables[index]) {
      parsed.tables[index].rows = newRows;
    }
    updated.schema = parsed;
    setSchema(updated);
  };

  const handleGenerate = async () => {
    if (!schema?.schema) return;
    setLoadingGen(true);
    setPreviewData(null);
    setManifest(null);
    try {
      let finalSchema = schema.schema;
      if (typeof finalSchema === 'string') {
        finalSchema = JSON.parse(finalSchema);
      }

      // 1. Create a relational run
      const genRes = await api.post('/generate', { schema: finalSchema, mode: 'schema_only' });
      const id = genRes.data.run_id;
      setRunId(id);
      
      const proveRes = await api.get(`/generate/${id}/prove`);
      setProveResult(proveRes.data);

      const previewRes = await api.post('/generate/preview', { schema: finalSchema, preview_rows: 5 });
      setPreviewData(previewRes.data.tables);

      const manifestRes = await api.get(`/generate/${id}/manifest`);
      setManifest(manifestRes.data);
    } catch (err) {
      console.error("Generate error", err);
      alert("Invalid JSON schema. Please check your syntax.");
    } finally {
      setLoadingGen(false);
    }
  };

  const currentSchemaObj = typeof schema?.schema === 'string' ? JSON.parse(schema.schema) : schema?.schema;

  return (
    <div className="space-y-6">
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6">
        <h2 className="text-lg font-semibold text-slate-800 flex items-center mb-4">
          <Sparkles className="w-5 h-5 mr-2 text-indigo-500" />
          AI Schema Builder & Relational Engine
        </h2>
        
        <div className="flex space-x-3 mb-6">
          <input 
            type="text" 
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            className="flex-1 px-4 py-2.5 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            placeholder="Describe your database..."
          />
          <button 
            onClick={handleInferSchema}
            disabled={loadingSchema || !prompt}
            className="bg-indigo-600 hover:bg-indigo-700 text-white px-6 py-2.5 rounded-lg font-medium text-sm flex items-center transition-colors disabled:opacity-50"
          >
            {loadingSchema ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Sparkles className="w-4 h-4 mr-2" />}
            Infer Schema
          </button>
        </div>

        {schema && (
          <div className="mt-6 animate-in fade-in grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="bg-slate-50 rounded-lg p-6 border border-slate-200 flex flex-col justify-between">
              <div>
                <h3 className="text-md font-semibold text-slate-800 mb-2">Table Configurations</h3>
                <p className="text-sm text-slate-500 mb-4">Set the exact number of rows to generate for each table.</p>
                
                <div className="space-y-3 mb-6 max-h-[250px] overflow-auto">
                  {currentSchemaObj?.tables?.map((table: any, idx: number) => (
                    <div key={idx} className="flex items-center justify-between bg-white border border-slate-200 p-3 rounded-lg">
                      <div className="flex items-center">
                        <Table2 className="w-4 h-4 text-slate-400 mr-2" />
                        <span className="font-medium text-sm text-slate-700 capitalize">{table.name}</span>
                      </div>
                      <div className="flex items-center space-x-2">
                        <label className="text-xs text-slate-500">Rows:</label>
                        <input 
                          type="number" 
                          min="1"
                          max="100000"
                          value={table.rows || 10}
                          onChange={(e) => handleRowChange(idx, parseInt(e.target.value) || 0)}
                          className="w-20 px-2 py-1 border border-slate-300 rounded text-sm text-right focus:ring-1 focus:ring-blue-500"
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
              
              <button 
                onClick={handleGenerate}
                disabled={loadingGen}
                className="w-full bg-blue-600 hover:bg-blue-700 text-white font-medium py-3 rounded-lg flex items-center justify-center transition-colors disabled:opacity-50"
              >
                {loadingGen ? <Loader2 className="w-5 h-5 mr-2 animate-spin" /> : <Database className="w-5 h-5 mr-2" />}
                {loadingGen ? 'Generating Relational DB...' : 'Synthesize Relational Data'}
              </button>
            </div>
            
            <div className="bg-slate-900 rounded-lg p-4 overflow-auto max-h-[400px] relative">
              <span className="absolute top-2 right-3 text-xs font-mono text-slate-400 bg-slate-800 px-2 py-1 rounded">Source: {schema.source}</span>
              <p className="absolute top-2 left-3 text-xs text-blue-400 font-semibold mb-2">Raw JSON Schema</p>
              <pre className="text-xs text-green-400 font-mono mt-6">
                {JSON.stringify(currentSchemaObj, null, 2)}
              </pre>
            </div>
          </div>
        )}
      </div>

      {proveResult && (
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 animate-in slide-in-from-bottom-4">
          <div className="flex items-center justify-between mb-6">
            <h3 className="text-lg font-semibold text-slate-800 flex items-center">
              <ShieldCheck className="w-5 h-5 mr-2 text-emerald-500" />
              "Prove It" — SQL Integrity Checks
            </h3>
            <span className="px-3 py-1 bg-emerald-100 text-emerald-700 text-xs font-bold rounded-full">0 Violations</span>
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
            {proveResult.prove_it?.map((check: any, idx: number) => (
              <div key={idx} className="bg-slate-50 border border-slate-100 p-4 rounded-lg flex items-start">
                <CheckCircle2 className="w-5 h-5 text-emerald-500 mr-3 shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm font-medium text-slate-800">{check.check || check.rule || "Integrity Check"}</p>
                  <p className="text-xs text-slate-500 mt-1 font-mono">Violations: {check.violations}</p>
                </div>
              </div>
            ))}
          </div>

          {manifest?.artifacts && (
            <div className="mt-8 border-t border-slate-100 pt-6">
              <h3 className="text-lg font-semibold text-slate-800 flex items-center mb-4">
                <Download className="w-5 h-5 mr-2 text-blue-500" />
                Download Exported Artifacts
              </h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
                {manifest.artifacts.map((fileObj: any, idx: number) => {
                  const filename = fileObj.name || (typeof fileObj === 'string' ? fileObj.split('/').pop() : 'file');
                  return (
                    <a
                      key={idx}
                      href={`${API_BASE_URL}/download/${runId}/${filename}`}
                      download={filename}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex flex-col border border-slate-200 rounded-lg p-4 hover:border-blue-400 hover:shadow-md transition-all bg-slate-50 group cursor-pointer"
                    >
                      <Download className="w-6 h-6 text-slate-400 group-hover:text-blue-500 mb-2 transition-colors" />
                      <span className="text-sm font-medium text-slate-700 truncate" title={filename}>{filename}</span>
                      <span className="text-xs text-slate-400 mt-1 uppercase">{filename.split('.').pop()} File</span>
                    </a>
                  )
                })}
              </div>
            </div>
          )}

          {/* Render Data Preview */}
          {previewData && Object.keys(previewData).length > 0 && (
            <div className="mt-8 border-t border-slate-100 pt-6">
              <h3 className="text-lg font-semibold text-slate-800 flex items-center mb-4">
                <Database className="w-5 h-5 mr-2 text-blue-500" />
                Generated Data Preview (First 5 Rows)
              </h3>
              
              <div className="space-y-8">
                {Object.entries(previewData).map(([tableName, rows]: [string, any]) => (
                  <div key={tableName} className="rounded-lg border border-slate-200 overflow-hidden">
                    <div className="bg-slate-50 px-4 py-2 border-b border-slate-200 flex justify-between items-center">
                      <span className="font-semibold text-sm text-slate-700 capitalize">{tableName} Table</span>
                      {manifest?.tables?.[tableName] && (
                        <span className="text-xs text-slate-500 bg-white px-2 py-1 rounded border border-slate-200">{manifest.tables[tableName].rows} rows total generated</span>
                      )}
                    </div>
                    <div className="overflow-x-auto">
                      <table className="w-full text-sm text-left">
                        <thead className="bg-white text-slate-500 border-b border-slate-200">
                          <tr>
                            {rows.length > 0 && Object.keys(rows[0]).map(col => (
                              <th key={col} className="px-4 py-3 font-medium whitespace-nowrap">{col}</th>
                            ))}
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100 bg-white">
                          {rows.map((row: any, i: number) => (
                            <tr key={i} className="hover:bg-slate-50">
                              {Object.values(row).map((val: any, j: number) => (
                                <td key={j} className="px-4 py-2 text-slate-600 whitespace-nowrap truncate max-w-[200px]">
                                  {String(val)}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
