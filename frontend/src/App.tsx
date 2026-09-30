import { useState } from 'react';
import { Layers, FileText, Database, Shield, Settings, Menu, ShieldCheck } from 'lucide-react';
import TabularGen from './pages/TabularGen';
import DocumentGen from './pages/DocumentGen';
import PrivacyScan from './pages/PrivacyScan';
import RelationalGen from './pages/RelationalGen';
import Compliance from './pages/Compliance';

function App() {
  const [activeTab, setActiveTab] = useState('tabular');
  const [isSidebarOpen, setSidebarOpen] = useState(false);

  const navItems = [
    { id: 'tabular', label: 'Tabular Data', icon: Database },
    { id: 'relational', label: 'Relational AI Demo', icon: Layers },
    { id: 'documents', label: 'Document Studio', icon: FileText },
    { id: 'privacy', label: 'Privacy Scanner', icon: Shield },
    { id: 'compliance', label: 'Compliance & Legal', icon: ShieldCheck },
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
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col h-screen overflow-hidden">
        <header className="h-16 bg-white border-b border-slate-200 flex items-center px-4 md:px-8 shrink-0">
          <button 
            onClick={() => setSidebarOpen(true)}
            className="p-2 -ml-2 mr-2 text-slate-500 hover:bg-slate-100 rounded-lg md:hidden"
          >
            <Menu className="w-6 h-6" />
          </button>
          <h1 className="text-xl font-semibold text-slate-800">
            {navItems.find(i => i.id === activeTab)?.label}
          </h1>
        </header>

        <div className="flex-1 overflow-auto p-4 md:p-8 bg-slate-50/50">
          <div className="max-w-6xl mx-auto">
            {(() => {
              switch (activeTab) {
                case 'tabular':
                  return <TabularGen />;
                case 'relational':
                  return <RelationalGen />;
                case 'documents':
                  return <DocumentGen />;
                case 'privacy':
                  return <PrivacyScan />;
                case 'compliance':
                  return <Compliance />;
                case 'settings':
                  return <div className="p-6 bg-white rounded-xl border border-slate-200">Settings coming soon...</div>;
                default:
                  return <TabularGen />;
              }
            })()}
          </div>
        </div>
      </main>
    </div>
  );
}

export default App;
