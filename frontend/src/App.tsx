import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom';
import './index.css';
import Dashboard from './pages/Dashboard';
import ComponentExplorer from './pages/ComponentExplorer';
import LotAnalysis from './pages/LotAnalysis';
import ScreeningResults from './pages/ScreeningResults';
import BaselineComparison from './pages/BaselineComparison';

const NAV_ITEMS = [
  {
    to: '/',
    label: 'Dashboard',
    icon: (
      <svg className="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <rect x="3" y="3" width="7" height="7" rx="1"/>
        <rect x="14" y="3" width="7" height="7" rx="1"/>
        <rect x="3" y="14" width="7" height="7" rx="1"/>
        <rect x="14" y="14" width="7" height="7" rx="1"/>
      </svg>
    ),
  },
  {
    to: '/components',
    label: 'Component Explorer',
    icon: (
      <svg className="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <circle cx="11" cy="11" r="8"/>
        <path d="m21 21-4.35-4.35"/>
      </svg>
    ),
  },
  {
    to: '/lots',
    label: 'Lot Analysis',
    icon: (
      <svg className="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M3 3h18v18H3z"/>
        <path d="M8 12h8M8 8h8M8 16h4"/>
      </svg>
    ),
  },
  {
    to: '/screening',
    label: 'Screening Results',
    icon: (
      <svg className="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M9 11l3 3L22 4"/>
        <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>
      </svg>
    ),
  },
  {
    to: '/baseline',
    label: 'Baseline Comparison',
    icon: (
      <svg className="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
      </svg>
    ),
  },
];

function App() {
  return (
    <BrowserRouter>
      <div className="app-layout">
        {/* Sidebar */}
        <nav className="sidebar">
          <div className="sidebar-logo">
            <div className="sidebar-logo-title">⚡ BurnSight AI</div>
            <div className="sidebar-logo-sub">Burn-In Anomaly Detection</div>
          </div>

          <div className="sidebar-nav">
            <div className="nav-section-label">Navigation</div>
            {NAV_ITEMS.map(item => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === '/'}
                className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}
              >
                {item.icon}
                {item.label}
              </NavLink>
            ))}
          </div>

          <div className="sidebar-footer">
            <div className="sidebar-status">
              <span className="status-dot" />
              <span>Backend connected</span>
            </div>
            <div style={{ marginTop: '8px', fontSize: '0.7rem', color: 'var(--text-muted)' }}>
              SIH 2026 · v1.0.0
            </div>
          </div>
        </nav>

        {/* Main content */}
        <main className="main-content">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/components" element={<ComponentExplorer />} />
            <Route path="/components/:id" element={<ComponentExplorer />} />
            <Route path="/lots" element={<LotAnalysis />} />
            <Route path="/lots/:id" element={<LotAnalysis />} />
            <Route path="/screening" element={<ScreeningResults />} />
            <Route path="/baseline" element={<BaselineComparison />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

export default App;
