import { useState } from 'react';
import { Layers, FileText, Database, Shield, Settings, Menu } from 'lucide-react';
import TabularGen from './pages/TabularGen';
import DocumentGen from './pages/DocumentGen';
import PrivacyScan from './pages/PrivacyScan';
import RelationalGen from './pages/RelationalGen';

function App() {
  const [activeTab, setActiveTab] = useState('tabular');
  const [isSidebarOpen, setSidebarOpen] = useState(false);

  const navItems = [
    { id: 'tabular', label: 'Tabular Data', icon: Database },
    { id: 'relational', label: 'Relational AI Demo', icon: Layers },
    { id: 'documents', label: 'Document Studio', icon: FileText },
    { id: 'privacy', label: 'Privacy Scanner', icon: Shield },
    { id: 'settings', label: 'Settings', icon: Settings },
  ];

  return (
    <div className="min-h-screen flex bg-slate-50 font-sans">
      {/* Mobile sidebar overlay */}
      {isSidebarOpen && (
        <div 
          className="fixed inset-0 z-40 bg-slate-900/50 md:hidden"
          onClick={() => setSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside className={`
        fixed inset-y-0 left-0 z-50 w-64 bg-white border-r border-slate-200 transform transition-transform duration-200 ease-in-out md:relative md:translate-x-0
        ${isSidebarOpen ? 'translate-x-0' : '-translate-x-full'}
      `}>
        <div className="h-16 flex items-center px-6 border-b border-slate-200">
          <Layers className="w-6 h-6 text-blue-600 mr-3" />
          <span className="font-semibold text-lg text-slate-900 tracking-tight">Synthium Forge</span>
        </div>
        
        <nav className="p-4 space-y-1">
          {navItems.map(item => (
            <button
              key={item.id}
              onClick={() => { setActiveTab(item.id); setSidebarOpen(false); }}
              className={`w-full flex items-center px-3 py-2.5 rounded-lg transition-all duration-200 ${
                activeTab === item.id 
                  ? 'bg-blue-50 text-blue-700 shadow-sm' 
                  : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
              }`}
            >
              <item.icon className={`w-5 h-5 mr-3 ${activeTab === item.id ? 'text-blue-600' : 'text-slate-400'}`} />
              <span className="font-medium text-sm">{item.label}</span>
            </button>
          ))}
        </nav>
        
        <div className="absolute bottom-0 w-full p-4 border-t border-slate-200">
          <div className="flex items-center space-x-3">
            <div className="w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center text-blue-600 font-bold text-xs">
              AI
            </div>
            <div>
              <p className="text-sm font-medium text-slate-900">Engine Active</p>
              <p className="text-xs text-slate-500">Gemini 2.5 Connected</p>
            </div>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <header className="h-16 flex items-center px-4 sm:px-6 lg:px-8 bg-white border-b border-slate-200 shrink-0">
          <button 
            onClick={() => setSidebarOpen(true)}
            className="mr-4 p-2 rounded-md text-slate-400 hover:text-slate-500 hover:bg-slate-100 md:hidden"
          >
            <Menu className="w-6 h-6" />
          </button>
          <h1 className="text-xl font-semibold text-slate-800">
            {navItems.find(i => i.id === activeTab)?.label}
          </h1>
        </header>

        <div className="flex-1 overflow-auto p-4 sm:p-6 lg:p-8">
          <div className="max-w-6xl mx-auto">
            {activeTab === 'tabular' && <TabularGen />}
            {activeTab === 'relational' && <RelationalGen />}
            {activeTab === 'documents' && <DocumentGen />}
            {activeTab === 'privacy' && <PrivacyScan />}
            {activeTab === 'settings' && (
              <div className="bg-white p-6 rounded-xl border border-slate-200 shadow-sm text-center">
                <Shield className="w-12 h-12 text-slate-300 mx-auto mb-4" />
                <h3 className="text-lg font-medium text-slate-900">Settings coming soon</h3>
                <p className="text-slate-500">API keys are currently managed via .env securely.</p>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}

export default App;
