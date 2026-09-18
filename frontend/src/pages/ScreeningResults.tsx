import React, { useEffect, useState, useMemo, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { getScreeningResults } from '../api/client';
import type { ScreeningRecord, PaginatedScreeningResults } from '../api/client';

const DECISIONS = ['PASS', 'WATCH', 'REVIEW', 'REJECT'] as const;
const DECISION_COLOR: Record<string, string> = {
  PASS: 'pass', WATCH: 'watch', REVIEW: 'review', REJECT: 'reject',
};

function decisionClass(d: string) {
  return `badge badge-${DECISION_COLOR[d] || 'watch'}`;
}

function driftClass(d: string) {
  return `badge badge-${d === 'DANGEROUS' ? 'dangerous' : d === 'WATCH' ? 'watch-drift' : 'safe'}`;
}

type SortKey = keyof ScreeningRecord;

const SERVER_PAGE_SIZE = 500; // Fetch large pages from server, paginate client-side

export default function ScreeningResults() {
  const navigate = useNavigate();

  // Server data
  const [serverData, setServerData] = useState<PaginatedScreeningResults | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Client-side filters (applied on top of server data)
  const [filterParam, setFilterParam] = useState('');
  const [filterDrift, setFilterDrift] = useState('');
  const [filterDecision, setFilterDecision] = useState('');
  const [searchId, setSearchId] = useState('');

  // Sorting
  const [sortKey, setSortKey] = useState<SortKey>('anomaly_score');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');

  // Client-side pagination
  const [page, setPage] = useState(0);
  const PAGE_SIZE = 50;

  const fetchData = useCallback((decision?: string) => {
    setLoading(true);
    setError(null);
    getScreeningResults(1, SERVER_PAGE_SIZE, decision)
      .then(data => { setServerData(data); setPage(0); })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  const records = serverData?.records ?? [];
  const serverTotal = serverData?.total ?? 0;

  // Available parameter options from current loaded records
  const params = useMemo(() => [...new Set(records.map(r => r.parameter))], [records]);

  // Client-side filter + sort
  const filtered = useMemo(() => {
    let r = records;
    if (filterDecision) r = r.filter(x => x.final_decision === filterDecision);
    if (filterParam) r = r.filter(x => x.parameter === filterParam);
    if (filterDrift) r = r.filter(x => x.drift_risk === filterDrift);
    if (searchId) r = r.filter(x =>
      x.component_id.toLowerCase().includes(searchId.toLowerCase()) ||
      x.lot_id.toLowerCase().includes(searchId.toLowerCase())
    );
    return [...r].sort((a, b) => {
      const av = a[sortKey] ?? (sortDir === 'asc' ? Infinity : -Infinity);
      const bv = b[sortKey] ?? (sortDir === 'asc' ? Infinity : -Infinity);
      if (typeof av === 'number' && typeof bv === 'number') return sortDir === 'asc' ? av - bv : bv - av;
      return sortDir === 'asc' ? String(av).localeCompare(String(bv)) : String(bv).localeCompare(String(av));
    });
  }, [records, filterDecision, filterParam, filterDrift, searchId, sortKey, sortDir]);

  const paged = filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  const totalPages = Math.ceil(filtered.length / PAGE_SIZE);

  // Decision counts from current loaded data
  const counts = useMemo(() =>
    records.reduce((acc, r) => {
      const d = r.final_decision || 'UNKNOWN';
      acc[d] = (acc[d] || 0) + 1;
      return acc;
    }, {} as Record<string, number>),
    [records]
  );

  const handleSort = (key: SortKey) => {
    if (key === sortKey) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortKey(key); setSortDir('desc'); }
    setPage(0);
  };

  const sortIndicator = (key: SortKey) =>
    sortKey === key ? (sortDir === 'asc' ? ' ↑' : ' ↓') : ' ⇅';

  const handleDecisionFilter = (d: string) => {
    const next = filterDecision === d ? '' : d;
    setFilterDecision(next);
    setPage(0);
  };

  const clearFilters = () => {
    setFilterDecision('');
    setFilterParam('');
    setFilterDrift('');
    setSearchId('');
    setPage(0);
  };

  const hasFilters = !!(filterDecision || filterParam || filterDrift || searchId);

  return (
    <div className="page-content animate-fade-in">
      <div className="page-header">
        <div className="page-header-eyebrow">Results</div>
        <h1>Screening Results</h1>
        <p>
          All screened components with anomaly scores, drift predictions, and AI decisions.
          {serverTotal > records.length && (
            <span style={{ color: 'var(--color-amber)', marginLeft: '0.5rem' }}>
              ⚠ Showing {records.length.toLocaleString()} of {serverTotal.toLocaleString()} total records.
            </span>
          )}
        </p>
      </div>

      {/* Summary bar — click to filter by decision */}
      <div className="stats-grid animate-fade-in-delay-1" style={{ gridTemplateColumns: 'repeat(5, 1fr)', marginBottom: 'var(--space-6)' }}>
        {DECISIONS.map(d => (
          <div
            key={d}
            className="stat-card"
            style={{
              '--accent-color': `var(--color-${DECISION_COLOR[d]})`,
              cursor: 'pointer',
              borderColor: filterDecision === d ? `var(--color-${DECISION_COLOR[d]})` : undefined,
              outline: filterDecision === d ? `1px solid var(--color-${DECISION_COLOR[d]})` : undefined,
            } as React.CSSProperties}
            onClick={() => handleDecisionFilter(d)}
          >
            <div className="stat-label">{d}</div>
            <div className="stat-value" style={{ color: `var(--color-${DECISION_COLOR[d]})`, fontSize: '1.5rem' }}>
              {loading ? '–' : (counts[d] || 0).toLocaleString()}
            </div>
          </div>
        ))}
        <div className="stat-card" style={{ '--accent-color': 'var(--color-blue)' } as React.CSSProperties}>
          <div className="stat-label">Total Loaded</div>
          <div className="stat-value" style={{ fontSize: '1.5rem' }}>
            {loading ? '–' : records.length.toLocaleString()}
          </div>
        </div>
      </div>

      {/* Filters */}
      <div className="card mb-6 animate-fade-in-delay-2" style={{ padding: 'var(--space-4)' }}>
        <div style={{ display: 'flex', gap: 'var(--space-3)', flexWrap: 'wrap', alignItems: 'center' }}>
          <input
            className="search-input"
            placeholder="Search component ID or lot..."
            value={searchId}
            onChange={e => { setSearchId(e.target.value); setPage(0); }}
            style={{ flex: 1, minWidth: 200 }}
          />
          <select className="filter-select" value={filterDecision} onChange={e => { setFilterDecision(e.target.value); setPage(0); }}>
            <option value="">All Decisions</option>
            {DECISIONS.map(d => <option key={d} value={d}>{d}</option>)}
          </select>
          <select className="filter-select" value={filterParam} onChange={e => { setFilterParam(e.target.value); setPage(0); }}>
            <option value="">All Parameters</option>
            {params.map(p => <option key={p} value={p}>{p.replace(/_/g, ' ')}</option>)}
          </select>
          <select className="filter-select" value={filterDrift} onChange={e => { setFilterDrift(e.target.value); setPage(0); }}>
            <option value="">All Drift Risk</option>
            {['SAFE', 'WATCH', 'DANGEROUS'].map(d => <option key={d} value={d}>{d}</option>)}
          </select>
          <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem', whiteSpace: 'nowrap' }}>
            {filtered.length.toLocaleString()} results
          </span>
          {hasFilters && (
            <button className="btn btn-ghost" style={{ padding: '6px 12px', fontSize: '0.8rem' }} onClick={clearFilters}>
              Clear
            </button>
          )}
        </div>
      </div>

      {loading && <div className="loading-state"><div className="spinner" /><span>Loading results...</span></div>}
      {error && <div className="error-state">{error}</div>}

      {!loading && (
        <div className="animate-fade-in-delay-3">
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th onClick={() => handleSort('component_id')}>Component ID{sortIndicator('component_id')}</th>
                  <th onClick={() => handleSort('lot_id')}>Lot{sortIndicator('lot_id')}</th>
                  <th onClick={() => handleSort('parameter')}>Parameter{sortIndicator('parameter')}</th>
                  <th onClick={() => handleSort('static_result')}>Static{sortIndicator('static_result')}</th>
                  <th onClick={() => handleSort('anomaly_score')}>Anomaly Score{sortIndicator('anomaly_score')}</th>
                  <th onClick={() => handleSort('predicted_168h')}>Predicted 168h{sortIndicator('predicted_168h')}</th>
                  <th onClick={() => handleSort('drift_risk')}>Drift Risk{sortIndicator('drift_risk')}</th>
                  <th onClick={() => handleSort('final_decision')}>Decision{sortIndicator('final_decision')}</th>
                  <th onClick={() => handleSort('label')}>Label{sortIndicator('label')}</th>
                  <th>Explanation</th>
                </tr>
              </thead>
              <tbody>
                {paged.length === 0 ? (
                  <tr>
                    <td colSpan={10} style={{ textAlign: 'center', padding: 'var(--space-8)', color: 'var(--text-muted)' }}>
                      {records.length === 0 ? 'No screening results found. Run the pipeline first.' : 'No records match the current filter.'}
                    </td>
                  </tr>
                ) : (
                  paged.map((r, i) => (
                    <tr
                      key={`${r.component_id}-${r.parameter}-${i}`}
                      onClick={() => navigate(`/components/${r.component_id}`)}
                      style={{ cursor: 'pointer' }}
                    >
                      <td className="td-mono" style={{ color: 'var(--color-teal)' }}>{r.component_id}</td>
                      <td className="td-mono" style={{ fontSize: '0.75rem' }}>{r.lot_id}</td>
                      <td style={{ fontSize: '0.78rem' }}>{r.parameter?.replace(/_/g, ' ')}</td>
                      <td>
                        <span className={`badge ${r.static_result === 'FAIL' ? 'badge-fail' : 'badge-pass'}`}>
                          {r.static_result}
                        </span>
                      </td>
                      <td>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
                          <div style={{ width: 40, height: 5, background: 'var(--color-border)', borderRadius: 3, overflow: 'hidden' }}>
                            <div style={{
                              width: `${((r.anomaly_score ?? 0) * 100)}%`,
                              height: '100%',
                              background: (r.anomaly_score ?? 0) > 0.8 ? 'var(--color-red)' :
                                          (r.anomaly_score ?? 0) > 0.65 ? 'var(--color-amber)' : 'var(--color-teal)',
                              borderRadius: 3,
                            }} />
                          </div>
                          <span className="td-mono" style={{ fontSize: '0.75rem' }}>
                            {r.anomaly_score?.toFixed(3) ?? 'N/A'}
                          </span>
                        </div>
                      </td>
                      <td className="td-mono" style={{ fontSize: '0.78rem' }}>
                        {r.predicted_168h?.toFixed(3) ?? 'N/A'}
                      </td>
                      <td>
                        {r.drift_risk ? <span className={driftClass(r.drift_risk)}>{r.drift_risk}</span> : '–'}
                      </td>
                      <td>
                        {r.final_decision ? <span className={decisionClass(r.final_decision)}>{r.final_decision}</span> : '–'}
                      </td>
                      <td style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                        {r.label || '–'}
                      </td>
                      <td style={{ maxWidth: 250, fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                        <span title={r.explanation || ''} style={{ display: 'block', maxWidth: 240, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {r.explanation ? `${r.explanation.slice(0, 80)}…` : '–'}
                        </span>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 'var(--space-2)', marginTop: 'var(--space-4)' }}>
              <button className="btn btn-ghost" disabled={page === 0} onClick={() => setPage(p => p - 1)}>← Prev</button>
              <span style={{ padding: '8px 16px', color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
                Page {page + 1} / {totalPages} ({filtered.length.toLocaleString()} records)
              </span>
              <button className="btn btn-ghost" disabled={page >= totalPages - 1} onClick={() => setPage(p => p + 1)}>Next →</button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
