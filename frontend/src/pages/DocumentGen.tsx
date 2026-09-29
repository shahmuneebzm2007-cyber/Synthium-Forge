import { useState } from 'react';
import { FileText, Play, Download, Loader2, CheckCircle2 } from 'lucide-react';
import api from '../api';

export default function DocumentGen() {
  const [count, setCount] = useState(2);
  const [minBalance, setMinBalance] = useState(500);
  const [targetClosing, setTargetClosing] = useState(3000);
  const [loadingType, setLoadingType] = useState<'none' | 'invoice' | 'statement'>('none');
  const [documents, setDocuments] = useState<any[]>([]);

  const handleGenerateInvoices = async () => {
    setLoadingType('invoice');
    setDocuments([]);
    try {
      const res = await api.post('/documents/invoices', {
        count: count,
        n_lines: 5,
        locale: 'us',
        currency: 'USD',
        seed: Math.floor(Math.random() * 1000000),
        render_pdf: true
      });
      setDocuments(res.data.invoices || []);
    } catch (err) {
      console.error(err);
    } finally {
      setLoadingType('none');
    }
  };

  const handleGenerateStatements = async () => {
    setLoadingType('statement');
    setDocuments([]);
    try {
      const res = await api.post('/documents/statements', {
        count: 1, // API currently only supports 1 statement per request
        locale: 'us',
        currency: 'USD',
        seed: Math.floor(Math.random() * 1000000),
        render_pdf: true,
        min_balance: minBalance,
        target_closing: targetClosing,
        opening_balance: targetClosing + 2000
      });
      
      // Since the API returns a single statement dict, wrap it in an array
      if (res.data && res.data.statement) {
        setDocuments([res.data]);
      }
    } catch (err) {
      console.error(err);
    } finally {
      setLoadingType('none');
    }
  };

  return (
    <div className="space-y-6">
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-6">
          <div>
            <h2 className="text-lg font-semibold text-slate-800 flex items-center">
              <FileText className="w-5 h-5 mr-2 text-blue-600" />
              Fintech Document Studio
            </h2>
            <p className="text-sm text-slate-500 mt-1">Generate perfectly reconciled, synthetic PDF invoices and bank statements.</p>
          </div>
          
          <div className="mt-4 md:mt-0 flex flex-col space-y-4 w-full md:w-auto">
            {/* Invoice Controls */}
            <div className="flex items-center justify-end space-x-3 bg-slate-50 p-3 rounded-lg border border-slate-200">
              <div className="flex items-center space-x-2 mr-2">
                <span className="text-xs text-slate-500 font-medium">Invoice Count:</span>
                <input 
                  type="number" 
                  value={count} 
                  onChange={(e) => setCount(Number(e.target.value))}
                  className="w-16 px-2 py-1.5 border border-slate-300 rounded text-sm text-center focus:ring-1 focus:ring-blue-500"
                  min="1" max="10"
                />
              </div>
              <button 
                onClick={handleGenerateInvoices}
                disabled={loadingType !== 'none'}
                className="bg-indigo-600 hover:bg-indigo-700 text-white px-4 py-2 rounded-lg font-medium text-sm flex items-center transition-colors disabled:opacity-50"
              >
                {loadingType === 'invoice' ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Play className="w-4 h-4 mr-2" />}
                {loadingType === 'invoice' ? 'Rendering...' : 'Generate Invoices'}
              </button>
            </div>
            
            {/* Statement Controls */}
            <div className="flex items-center justify-end space-x-3 bg-slate-50 p-3 rounded-lg border border-slate-200">
              <div className="flex items-center space-x-4 mr-2">
                <div className="flex items-center space-x-2">
                  <span className="text-xs text-slate-600 font-medium">Min Balance ($):</span>
                  <input type="number" value={minBalance} onChange={e => setMinBalance(Number(e.target.value))} className="w-20 px-2 py-1 text-sm border rounded focus:ring-1 focus:ring-blue-500" />
                </div>
                <div className="flex items-center space-x-2">
                  <span className="text-xs text-slate-600 font-medium">Target End ($):</span>
                  <input type="number" value={targetClosing} onChange={e => setTargetClosing(Number(e.target.value))} className="w-20 px-2 py-1 text-sm border rounded focus:ring-1 focus:ring-blue-500" />
                </div>
              </div>
              <button 
                onClick={handleGenerateStatements}
                disabled={loadingType !== 'none'}
                className="bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2 rounded-lg font-medium text-sm flex items-center transition-colors disabled:opacity-50"
              >
                {loadingType === 'statement' ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Play className="w-4 h-4 mr-2" />}
                {loadingType === 'statement' ? 'Rendering...' : 'Generate Statement'}
              </button>
            </div>
          </div>
        </div>
      </div>

      {documents.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {documents.map((doc, idx) => {
            const isInvoice = !!doc.invoice;
            const title = isInvoice ? doc.invoice.invoice_number : doc.statement.account_number;
            const subtitle = isInvoice 
              ? `${doc.invoice.issuer.name} -> ${doc.invoice.recipient.name}`
              : `${doc.statement.institution.name} - ${doc.statement.account_holder.name}`;
            
            return (
              <div key={idx} className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden flex flex-col">
                <div className="p-4 border-b border-slate-100 bg-slate-50 flex justify-between items-center">
                  <div>
                    <h3 className="font-semibold text-slate-800">{title}</h3>
                    <p className="text-xs text-slate-500">{subtitle}</p>
                  </div>
                  <a 
                    href={`data:application/pdf;base64,${doc.pdf_base64}`}
                    download={`${title}.pdf`}
                    className="p-2 text-slate-400 hover:text-blue-600 hover:bg-blue-50 rounded-md transition-colors"
                    title="Download PDF"
                  >
                    <Download className="w-5 h-5" />
                  </a>
                </div>
                
                {isInvoice && doc.reconciliation && (
                  <div className="p-4 bg-slate-50 border-b border-slate-100">
                    <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Math Reconciliation</h4>
                    <div className="grid grid-cols-2 gap-2">
                      {doc.reconciliation.slice(0, 4).map((rec: any, i: number) => (
                        <div key={i} className="flex items-center text-xs text-slate-600">
                          <CheckCircle2 className="w-3 h-3 text-green-500 mr-1.5 shrink-0" />
                          <span className="truncate" title={rec.check}>{rec.check}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
                
                {!isInvoice && doc.constraints_met && (
                  <div className="p-4 bg-slate-50 border-b border-slate-100">
                    <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Constraint Validation</h4>
                    <div className="grid grid-cols-1 gap-2">
                      {doc.constraints_met.map((rec: any, i: number) => (
                        <div key={i} className="flex items-center text-xs text-slate-600">
                          <CheckCircle2 className={`w-3 h-3 mr-1.5 shrink-0 ${rec.met ? 'text-green-500' : 'text-red-500'}`} />
                          <span className="truncate" title={rec.constraint}>
                            {rec.constraint} {rec.repairs ? ` (Repaired ${rec.repairs}x)` : ''}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <div className="flex-1 p-0 h-[400px]">
                  <iframe 
                    src={`data:application/pdf;base64,${doc.pdf_base64}`}
                    className="w-full h-full border-0"
                    title={`PDF Preview ${idx}`}
                  />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
