import { useState } from 'react';
import { FileText, Play, Download, Loader2, CheckCircle2 } from 'lucide-react';
import api from '../api';

export default function DocumentGen() {
  const [count, setCount] = useState(2);
  const [loading, setLoading] = useState(false);
  const [invoices, setInvoices] = useState<any[]>([]);

  const handleGenerate = async () => {
    setLoading(true);
    try {
      const res = await api.post('/documents/invoices', {
        count: count,
        n_lines: 5,
        locale: 'us',
        currency: 'USD',
        seed: Math.floor(Math.random() * 1000000),
        render_pdf: true
      });
      setInvoices(res.data.invoices || []);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
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
          
          <div className="mt-4 md:mt-0 flex items-center space-x-3">
            <input 
              type="number" 
              value={count} 
              onChange={(e) => setCount(Number(e.target.value))}
              className="w-20 px-3 py-2 border border-slate-300 rounded-lg text-sm text-center"
              min="1" max="10"
            />
            <button 
              onClick={handleGenerate}
              disabled={loading}
              className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg font-medium text-sm flex items-center transition-colors disabled:opacity-50"
            >
              {loading ? <Loader2 className="w-4 h-4 mr-2 animate-spin" /> : <Play className="w-4 h-4 mr-2" />}
              {loading ? 'Rendering PDFs...' : 'Generate Invoices'}
            </button>
          </div>
        </div>
      </div>

      {invoices.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {invoices.map((inv, idx) => (
            <div key={idx} className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden flex flex-col">
              <div className="p-4 border-b border-slate-100 bg-slate-50 flex justify-between items-center">
                <div>
                  <h3 className="font-semibold text-slate-800">{inv.invoice.invoice_number}</h3>
                  <p className="text-xs text-slate-500">{inv.invoice.issuer.name} → {inv.invoice.recipient.name}</p>
                </div>
                <a 
                  href={`data:application/pdf;base64,${inv.pdf_base64}`}
                  download={`${inv.invoice.invoice_number}.pdf`}
                  className="p-2 text-slate-400 hover:text-blue-600 hover:bg-blue-50 rounded-md transition-colors"
                  title="Download PDF"
                >
                  <Download className="w-5 h-5" />
                </a>
              </div>
              
              <div className="p-4 bg-slate-50 border-b border-slate-100">
                <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Math Reconciliation</h4>
                <div className="grid grid-cols-2 gap-2">
                  {inv.reconciliation.slice(0, 4).map((rec: any, i: number) => (
                    <div key={i} className="flex items-center text-xs text-slate-600">
                      <CheckCircle2 className="w-3 h-3 text-green-500 mr-1.5 shrink-0" />
                      <span className="truncate" title={rec.check}>{rec.check}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="flex-1 p-0 h-[400px]">
                <iframe 
                  src={`data:application/pdf;base64,${inv.pdf_base64}`}
                  className="w-full h-full border-0"
                  title={`PDF Preview ${idx}`}
                />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
