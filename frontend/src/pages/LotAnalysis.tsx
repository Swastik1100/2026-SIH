import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Cell,
} from 'recharts';
import { getLotSummary, getScreeningResults } from '../api/client';
import type { LotSummary, ScreeningRecord } from '../api/client';


const CustomTooltip = ({ active, payload, label }: any) => {
  if (!active || !payload?.length) return null;
  return (
    <div style={{
      background: 'var(--color-bg-secondary)',
      border: '1px solid var(--color-border)',
      borderRadius: 'var(--radius-md)',
      padding: '10px 14px',
      fontSize: '0.82rem',
    }}>
      <div style={{ color: 'var(--text-secondary)', marginBottom: 4 }}>{label}</div>
      {payload.map((p: any) => (
        <div key={p.name} style={{ color: p.color || 'var(--text-primary)', fontWeight: 600 }}>
          {p.value?.toFixed ? p.value.toFixed(4) : p.value}
        </div>
      ))}
    </div>
  );
};

function decisionBadge(d: string) {
  const cls = { PASS: 'badge-pass', WATCH: 'badge-watch', REVIEW: 'badge-review', REJECT: 'badge-reject' };
  return `badge ${cls[d as keyof typeof cls] || 'badge-watch'}`;
}

export default function LotAnalysis() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [lotId, setLotId] = useState(id || '');
  const [summary, setSummary] = useState<LotSummary | null>(null);
  const [components, setComponents] = useState<ScreeningRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedParam, setSelectedParam] = useState('leakage_current');

  const search = async (lid: string) => {
    if (!lid.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const [s, all] = await Promise.all([
        getLotSummary(lid.trim()),
        getScreeningResults(),
      ]);
      setSummary(s);
      const lotComps = all.records.filter((r: any) => r.lot_id === lid.trim());
      setComponents(lotComps);
      if (s.parameters[0]) setSelectedParam(s.parameters[0]);
      navigate(`/lots/${lid.trim()}`, { replace: true });
    } catch (e: any) {
      setError(e.response?.status === 404 ? `Lot "${lid}" not found.` : e.message);
      setSummary(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (id) { setLotId(id); search(id); }
  }, [id]);

  // Build histogram data for selected param
  const paramComponents = components.filter(r => r.parameter === selectedParam);

  const PARAM_UNITS: Record<string, string> = { iddq: 'mA', leakage_current: 'µA', propagation_delay: 'ns' };
  const unit = PARAM_UNITS[selectedParam] || '';

  // Distribution: bin anomaly scores
  const anomalyBins = [0, 0.2, 0.4, 0.6, 0.8, 1.0];
  const histData = anomalyBins.slice(0, -1).map((binMin, i) => {
    const binMax = anomalyBins[i + 1];
    const count = paramComponents.filter(r =>
      (r.anomaly_score ?? 0) >= binMin && (r.anomaly_score ?? 0) < binMax
    ).length;
    return { bin: `${binMin.toFixed(1)}–${binMax.toFixed(1)}`, count };
  });

  const statRow = summary?.statistics[selectedParam];
  const anomalousList = components
    .filter(r => r.parameter === selectedParam && ['REVIEW', 'REJECT'].includes(r.final_decision || ''))
    .reduce((acc: string[], r) => acc.includes(r.component_id) ? acc : [...acc, r.component_id], []);

  return (
    <div className="page-content animate-fade-in">
      <div className="page-header">
        <div className="page-header-eyebrow">Analysis</div>
        <h1>Lot Analysis</h1>
        <p>View lot-level statistics, component distribution, and identify anomalous components within a manufacturing lot.</p>
      </div>

      {/* Search */}
      <div className="card mb-6 animate-fade-in-delay-1" style={{ padding: 'var(--space-5)' }}>
        <div className="flex items-center gap-4">
          <input
            id="lot-search"
            className="search-input"
            placeholder="Enter lot ID (e.g. DEMO-LOT, LOT-001)..."
            value={lotId}
            onChange={e => setLotId(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && search(lotId)}
            style={{ flex: 1 }}
          />
          <button className="btn btn-primary" onClick={() => search(lotId)}>Analyze</button>
        </div>
        <div style={{ marginTop: 'var(--space-3)', display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Try:</span>
          {['DEMO-LOT', 'LOT-001', 'LOT-002', 'LOT-003'].map(lid => (
            <button
              key={lid}
              className="btn btn-ghost"
              style={{ padding: '2px 10px', fontSize: '0.75rem' }}
              onClick={() => { setLotId(lid); search(lid); }}
            >
              {lid}
            </button>
          ))}
        </div>
      </div>

      {loading && <div className="loading-state"><div className="spinner" /><span>Loading lot data...</span></div>}
      {error && <div className="error-state">{error}</div>}

      {summary && !loading && (
        <>
          {/* Lot Header Stats */}
          <div className="stats-grid animate-fade-in-delay-2">
            <div className="stat-card" style={{ '--accent-color': 'var(--color-blue)' } as React.CSSProperties}>
              <div className="stat-label">Components</div>
              <div className="stat-value">{summary.component_count}</div>
              <div className="stat-sub">{summary.parameters.length} parameters tracked</div>
            </div>
            <div className="stat-card" style={{ '--accent-color': 'var(--color-red)' } as React.CSSProperties}>
              <div className="stat-label">Anomalous (REVIEW/REJECT)</div>
              <div className="stat-value" style={{ color: 'var(--color-red)' }}>
                {anomalousList.length}
              </div>
              <div className="stat-sub">
                {summary.component_count > 0
                  ? `${((anomalousList.length / summary.component_count) * 100).toFixed(1)}% of lot`
                  : '–'}
              </div>
            </div>
            {statRow && (
              <>
                <div className="stat-card" style={{ '--accent-color': 'var(--color-teal)' } as React.CSSProperties}>
                  <div className="stat-label">Lot Median ({selectedParam.replace('_', ' ')})</div>
                  <div className="stat-value" style={{ color: 'var(--color-teal)', fontSize: '1.4rem' }}>
                    {statRow.median.toFixed(3)} <span style={{ fontSize: '0.8rem' }}>{unit}</span>
                  </div>
                  <div className="stat-sub">MAD: ±{statRow.mad.toFixed(3)} {unit}</div>
                </div>
                <div className="stat-card" style={{ '--accent-color': 'var(--color-purple)' } as React.CSSProperties}>
                  <div className="stat-label">Lot Mean ± Std ({selectedParam.replace('_', ' ')})</div>
                  <div className="stat-value" style={{ color: 'var(--color-purple)', fontSize: '1.4rem' }}>
                    {statRow.mean.toFixed(3)}
                  </div>
                  <div className="stat-sub">± {statRow.std.toFixed(3)} {unit}</div>
                </div>
              </>
            )}
          </div>

          {/* Parameter tabs */}
          <div style={{ display: 'flex', gap: 'var(--space-2)', margin: 'var(--space-5) 0 var(--space-4)' }}>
            {summary.parameters.map(p => (
              <button
                key={p}
                onClick={() => setSelectedParam(p)}
                className="btn"
                style={{
                  background: selectedParam === p ? 'var(--color-teal-dim)' : 'transparent',
                  color: selectedParam === p ? 'var(--color-teal)' : 'var(--text-secondary)',
                  border: `1px solid ${selectedParam === p ? 'var(--color-teal)' : 'var(--color-border)'}`,
                  padding: '6px 14px',
                  fontSize: '0.8rem',
                }}
              >
                {p.replace('_', ' ')}
              </button>
            ))}
          </div>

          <div className="grid-2 animate-fade-in-delay-3">
            {/* Anomaly Score Distribution */}
            <div className="card">
              <div className="card-title">📊 Anomaly Score Distribution</div>
              <div className="chart-container">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={histData} margin={{ top: 10, right: 10, bottom: 0, left: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(56,139,253,0.08)" />
                    <XAxis dataKey="bin" tick={{ fill: 'var(--text-muted)', fontSize: 11 }} />
                    <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 11 }} />
                    <Tooltip content={<CustomTooltip />} />
                    <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                      {histData.map((_entry, i) => (
                        <Cell
                          key={i}
                          fill={
                            i >= 4 ? 'var(--color-red)' :
                            i >= 3 ? 'var(--color-amber)' :
                            'var(--color-teal)'
                          }
                        />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Anomalous components list */}
            <div className="card">
              <div className="card-title">⚠ Anomalous Components (REVIEW / REJECT)</div>
              {anomalousList.length === 0 ? (
                <div className="empty-state" style={{ minHeight: 200 }}>
                  <div className="empty-state-icon">✅</div>
                  <div>No flagged components in this lot for {selectedParam.replace('_', ' ')}</div>
                </div>
              ) : (
                <div style={{ maxHeight: 280, overflowY: 'auto' }}>
                  {anomalousList.map(cid => {
                    const rec = paramComponents.find(r => r.component_id === cid);
                    return (
                      <div
                        key={cid}
                        onClick={() => navigate(`/components/${cid}`)}
                        style={{
                          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                          padding: 'var(--space-3) 0',
                          borderBottom: '1px solid var(--color-border)',
                          cursor: 'pointer',
                        }}
                      >
                        <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-teal)', fontSize: '0.85rem' }}>{cid}</span>
                        <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
                          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                            score: {rec?.anomaly_score?.toFixed(2) ?? '?'}
                          </span>
                          {rec?.final_decision && (
                            <span className={`badge ${decisionBadge(rec.final_decision)}`} style={{ fontSize: '0.65rem' }}>
                              {rec.final_decision}
                            </span>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </>
      )}

      {!summary && !loading && !error && (
        <div className="empty-state animate-fade-in-delay-2">
          <div className="empty-state-icon">📦</div>
          <div>Enter a lot ID to analyze the component population within it.</div>
          <div style={{ fontSize: '0.8rem', marginTop: 'var(--space-3)', color: 'var(--text-muted)' }}>
            Try "DEMO-LOT" for the demonstration dataset
          </div>
        </div>
      )}
    </div>
  );
}
