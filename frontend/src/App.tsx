import { BrowserRouter, Routes, Route, NavLink } from 'react-router-dom';
import { lazy, Suspense, Component, type ReactNode, type ErrorInfo, useEffect, useState } from 'react';
import './index.css';

// Lazy-loaded pages for code splitting
const Dashboard = lazy(() => import('./pages/Dashboard'));
const ComponentExplorer = lazy(() => import('./pages/ComponentExplorer'));
const LotAnalysis = lazy(() => import('./pages/LotAnalysis'));
const ScreeningResults = lazy(() => import('./pages/ScreeningResults'));
const BaselineComparison = lazy(() => import('./pages/BaselineComparison'));
const TestComponent = lazy(() => import('./pages/TestComponent'));

// --- Error Boundary ---
interface ErrorBoundaryState { hasError: boolean; message: string }
class ErrorBoundary extends Component<{ children: ReactNode }, ErrorBoundaryState> {
  constructor(props: { children: ReactNode }) {
    super(props);
    this.state = { hasError: false, message: '' };
  }
  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, message: error.message };
  }
  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('BurnSight ErrorBoundary:', error, info);
  }
  render() {
    if (this.state.hasError) {
      return (
        <div className="page-content" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '60vh' }}>
          <div className="error-state" style={{ maxWidth: 480, textAlign: 'center' }}>
            <div style={{ fontSize: '2rem', marginBottom: '1rem' }}>⚠️</div>
            <div style={{ fontWeight: 700, marginBottom: '0.5rem' }}>Something went wrong</div>
            <div style={{ fontSize: '0.82rem', color: 'var(--text-muted)', marginBottom: '1.5rem' }}>{this.state.message}</div>
            <button className="btn btn-primary" onClick={() => this.setState({ hasError: false, message: '' })}>
              Try Again
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

// --- Page loading fallback ---
const PageLoader = () => (
  <div className="page-content" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '60vh' }}>
    <div className="loading-state">
      <div className="spinner" />
      <span>Loading page...</span>
    </div>
  </div>
);

// --- 404 page ---
const NotFound = () => (
  <div className="page-content animate-fade-in">
    <div className="empty-state" style={{ minHeight: '60vh', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
      <div className="empty-state-icon">404</div>
      <div style={{ fontWeight: 700, fontSize: '1.2rem', marginBottom: '0.5rem' }}>Page not found</div>
      <div style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>Navigate using the sidebar.</div>
    </div>
  </div>
);

// --- Backend health hook ---
function useBackendHealth() {
  const [connected, setConnected] = useState<boolean | null>(null);
  useEffect(() => {
    const API_URL = (import.meta as any).env?.VITE_API_URL || 'http://localhost:8000';
    const check = () =>
      fetch(`${API_URL}/health`, { signal: AbortSignal.timeout(3000) })
        .then(r => setConnected(r.ok))
        .catch(() => setConnected(false));
    check();
    const id = setInterval(check, 30_000);
    return () => clearInterval(id);
  }, []);
  return connected;
}

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
  {
    to: '/test',
    label: 'Test Component',
    icon: (
      <svg className="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M9 3H5a2 2 0 0 0-2 2v4m6-6h10a2 2 0 0 1 2 2v4M9 3v18m0 0h10a2 2 0 0 0 2-2v-4M9 21H5a2 2 0 0 1-2-2v-4m0 0h18"/>
      </svg>
    ),
  },
];

function App() {
  const connected = useBackendHealth();

  const statusColor = connected === null
    ? 'var(--color-amber)'   // still checking
    : connected
    ? 'var(--color-green)'   // online
    : 'var(--color-red)';    // offline

  const statusLabel = connected === null ? 'Checking...' : connected ? 'Backend connected' : 'Backend offline';

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
              <span className="status-dot" style={{ background: statusColor }} />
              <span style={{ color: statusColor === 'var(--color-red)' ? 'var(--color-red)' : undefined }}>
                {statusLabel}
              </span>
            </div>
            <div style={{ marginTop: '8px', fontSize: '0.7rem', color: 'var(--text-muted)' }}>
              SIH 2026 · v1.0.0
            </div>
          </div>
        </nav>

        {/* Main content */}
        <main className="main-content">
          <ErrorBoundary>
            <Suspense fallback={<PageLoader />}>
              <Routes>
                <Route path="/" element={<Dashboard />} />
                <Route path="/components" element={<ComponentExplorer />} />
                <Route path="/components/:id" element={<ComponentExplorer />} />
                <Route path="/lots" element={<LotAnalysis />} />
                <Route path="/lots/:id" element={<LotAnalysis />} />
                <Route path="/screening" element={<ScreeningResults />} />
                <Route path="/baseline" element={<BaselineComparison />} />
                <Route path="/test" element={<TestComponent />} />
                <Route path="*" element={<NotFound />} />
              </Routes>
            </Suspense>
          </ErrorBoundary>
        </main>
      </div>
    </BrowserRouter>
  );
}

export default App;
