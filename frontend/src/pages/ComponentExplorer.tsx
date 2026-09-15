import { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, ReferenceLine, Legend,
} from 'recharts';
import { getComponentDetail } from '../api/client';
import type { ComponentDetail } from '../api/client';

const CHECKPOINT_HOURS = [0, 24, 96, 168];


const PARAM_UNITS: Record<string, string> = {
  iddq: 'mA',
  leakage_current: 'µA',
  propagation_delay: 'ns',
};

function decisionClass(d: string) {
  const m: Record<string, string> = {
    PASS: 'badge-pass', WATCH: 'badge-watch', REVIEW: 'badge-review', REJECT: 'badge-reject',
  };
  return `badge ${m[d] || 'badge-watch'}`;
}

function severityClass(s: string) {
  return `badge badge-${s?.toLowerCase() === 'high' ? 'high' : s?.toLowerCase() === 'medium' ? 'medium' : 'low'}`;
}

function driftClass(r: string) {
  return `badge badge-${r?.toLowerCase() === 'dangerous' ? 'dangerous' : r?.toLowerCase() === 'watch' ? 'watch-drift' : 'safe'}`;
}

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
      <div style={{ color: 'var(--text-secondary)', marginBottom: 4 }}>{label}h</div>
      {payload.map((p: any) => (
        <div key={p.name} style={{ color: p.color, fontWeight: 600, marginBottom: 2 }}>
          {p.name}: {p.value !== null && p.value !== undefined ? Number(p.value).toFixed(4) : 'N/A'}
        </div>
      ))}
    </div>
  );
};

function TrajectoryChart({ record, decision, unit }: {
  record: ComponentDetail['records'][0];
  decision: ComponentDetail['decisions'][0];
  unit: string;
}) {
  const measured = [
    { h: 0, Measured: record.value_0h },
    { h: 24, Measured: record.value_24h },
    { h: 96, Measured: record.value_96h },
    { h: 168, Measured: record.value_168h },
  ].filter(d => d.Measured !== null && d.Measured !== undefined);

  const chartData = CHECKPOINT_HOURS.map(h => {
    const m = measured.find(p => p.h === h);
    const row: any = { h };
    if (m) row['Measured'] = m.Measured;
    if (h === 168 && decision.predicted_168h !== null) {
      row['Predicted'] = decision.predicted_168h;
    }
    return row;
  });

  const specMax = record.spec_max;
  const specMin = record.spec_min;
  const allVals = [
    ...measured.map(m => m.Measured ?? 0),
    decision.predicted_168h ?? 0,
    specMax,
    specMin,
  ].filter(Boolean);
  const yMin = Math.max(0, Math.min(...allVals) * 0.85);
  const yMax = specMax * 1.1;

  return (
    <div className="chart-container chart-container-lg">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={chartData} margin={{ top: 15, right: 20, bottom: 5, left: 10 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(56,139,253,0.08)" />
          <XAxis
            dataKey="h"
            tickFormatter={(v) => `${v}h`}
            tick={{ fill: 'var(--text-muted)', fontSize: 11 }}
          />
          <YAxis
            domain={[yMin, yMax]}
            tickFormatter={(v) => v.toFixed(1)}
            tick={{ fill: 'var(--text-muted)', fontSize: 11 }}
            label={{ value: unit, angle: -90, position: 'insideLeft', fill: 'var(--text-muted)', fontSize: 11 }}
          />
          <Tooltip content={<CustomTooltip />} />
          <Legend formatter={(v) => <span style={{ color: 'var(--text-secondary)', fontSize: '0.8rem' }}>{v}</span>} />

          {/* Spec limits */}
          <ReferenceLine
            y={specMax}
            stroke="var(--color-red)"
            strokeDasharray="6 3"
            label={{ value: `Spec Max (${specMax} ${unit})`, position: 'right', fill: 'var(--color-red)', fontSize: 10 }}
          />
          <ReferenceLine
            y={specMin}
            stroke="var(--color-amber)"
            strokeDasharray="6 3"
            label={{ value: `Spec Min (${specMin} ${unit})`, position: 'right', fill: 'var(--color-amber)', fontSize: 10 }}
          />

          {/* Measured trajectory */}
          <Line
            type="monotone"
            dataKey="Measured"
            stroke="var(--color-teal)"
            strokeWidth={2.5}
            dot={{ fill: 'var(--color-teal)', r: 5, strokeWidth: 2 }}
            connectNulls
          />

          {/* Predicted 168h point */}
          <Line
            type="monotone"
            dataKey="Predicted"
            stroke="var(--color-amber)"
            strokeWidth={2}
            strokeDasharray="5 5"
            dot={{ fill: 'var(--color-amber)', r: 6, strokeWidth: 2 }}
            connectNulls
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export default function ComponentExplorer() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [searchId, setSearchId] = useState(id || '');
  const [detail, setDetail] = useState<ComponentDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedParam, setSelectedParam] = useState<string>('leakage_current');

  const search = async (compId: string) => {
    if (!compId.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const data = await getComponentDetail(compId.trim());
      setDetail(data);
      const params = data.records.map(r => r.parameter);
      if (!params.includes(selectedParam)) setSelectedParam(params[0] || '');
      navigate(`/components/${compId.trim()}`, { replace: true });
    } catch (e: any) {
      setError(e.response?.status === 404 ? `Component "${compId}" not found in database.` : e.message);
      setDetail(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (id) {
      setSearchId(id);
      search(id);
    }
  }, [id]);

  const paramRecord = detail?.records.find(r => r.parameter === selectedParam);
  const paramDecision = detail?.decisions.find(d => d.parameter === selectedParam);
  const unit = PARAM_UNITS[selectedParam] || '';

  const DEMO_COMPONENTS = ['C001', 'C002', 'C003', 'C004', 'C005', 'C006'];

  return (
    <div className="page-content animate-fade-in">
      <div className="page-header">
        <div className="page-header-eyebrow">Analysis</div>
        <h1>Component Explorer</h1>
        <p>Search any component by ID to view its full measurement trajectory, anomaly scores, drift prediction, and decision explanation.</p>
      </div>

      {/* Search bar */}
      <div className="card mb-6 animate-fade-in-delay-1" style={{ padding: 'var(--space-5)' }}>
        <div className="flex items-center gap-4">
          <input
            id="component-search"
            className="search-input"
            placeholder="Enter component ID (e.g. C003, COMP-00042)..."
            value={searchId}
            onChange={e => setSearchId(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && search(searchId)}
            style={{ flex: 1 }}
          />
          <button className="btn btn-primary" onClick={() => search(searchId)}>
            Search
          </button>
        </div>
        <div style={{ marginTop: 'var(--space-3)', display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
          <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Demo components:</span>
          {DEMO_COMPONENTS.map(cid => (
            <button
              key={cid}
              className="btn btn-ghost"
              style={{ padding: '2px 10px', fontSize: '0.75rem' }}
              onClick={() => { setSearchId(cid); search(cid); }}
            >
              {cid}
            </button>
          ))}
        </div>
      </div>

      {loading && (
        <div className="loading-state">
          <div className="spinner" />
          <span>Loading component data...</span>
        </div>
      )}

      {error && (
        <div className="error-state">{error}</div>
      )}

      {detail && !loading && (
        <>
          {/* Component Header */}
          <div className="card mb-6 animate-fade-in-delay-2" style={{ borderColor: 'rgba(56,139,253,0.25)' }}>
            <div className="flex items-center justify-between mb-4">
              <div>
                <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.1em' }}>Component</div>
                <div style={{ fontSize: '1.5rem', fontWeight: 800, fontFamily: 'var(--font-mono)', color: 'var(--color-teal)' }}>
                  {detail.component_id}
                </div>
                <div style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>Lot: {detail.lot_id}</div>
              </div>
              <div style={{ display: 'flex', gap: 'var(--space-3)', flexWrap: 'wrap' }}>
                {detail.decisions.map(d => (
                  <span key={d.parameter} className={decisionClass(d.final_decision || '')}>
                    {d.parameter.replace('_', ' ')}: {d.final_decision}
                  </span>
                ))}
              </div>
            </div>

            {/* Parameter tabs */}
            <div style={{ display: 'flex', gap: 'var(--space-2)', borderTop: '1px solid var(--color-border)', paddingTop: 'var(--space-4)' }}>
              {detail.records.map(r => (
                <button
                  key={r.parameter}
                  onClick={() => setSelectedParam(r.parameter)}
                  className="btn"
                  style={{
                    background: selectedParam === r.parameter ? 'var(--color-teal-dim)' : 'transparent',
                    color: selectedParam === r.parameter ? 'var(--color-teal)' : 'var(--text-secondary)',
                    border: `1px solid ${selectedParam === r.parameter ? 'var(--color-teal)' : 'var(--color-border)'}`,
                    padding: '6px 14px',
                    fontSize: '0.8rem',
                  }}
                >
                  {r.parameter.replace('_', ' ')} ({PARAM_UNITS[r.parameter] || ''})
                </button>
              ))}
            </div>
          </div>

          {paramRecord && paramDecision && (
            <>
              {/* Trajectory Chart */}
              <div className="card mb-6 animate-fade-in-delay-2">
                <div className="card-title">
                  📈 Measurement Trajectory — {selectedParam.replace('_', ' ')} ({unit})
                  <span style={{ marginLeft: 'auto', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                    Teal = Measured · Amber dashed = AI-Predicted 168h · Red = Spec Max
                  </span>
                </div>
                <TrajectoryChart record={paramRecord} decision={paramDecision} unit={unit} />
              </div>

              {/* Scores + Decision */}
              <div className="grid-3 mb-6 animate-fade-in-delay-3">
                {/* Measurements */}
                <div className="card">
                  <div className="card-title">📊 Raw Measurements</div>
                  <table style={{ width: '100%', fontSize: '0.82rem' }}>
                    <tbody>
                      {[
                        ['0h', paramRecord.value_0h],
                        ['24h', paramRecord.value_24h],
                        ['96h', paramRecord.value_96h],
                        ['168h', paramRecord.value_168h],
                      ].map(([label, val]) => (
                        <tr key={label as string}>
                          <td style={{ color: 'var(--text-muted)', padding: '4px 0' }}>{label}</td>
                          <td style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-primary)', textAlign: 'right' }}>
                            {val !== null && val !== undefined ? `${Number(val).toFixed(4)} ${unit}` : 'N/A'}
                          </td>
                        </tr>
                      ))}
                      <tr>
                        <td style={{ color: 'var(--text-muted)', padding: '4px 0' }}>Spec Min</td>
                        <td style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-amber)', textAlign: 'right' }}>
                          {paramRecord.spec_min} {unit}
                        </td>
                      </tr>
                      <tr>
                        <td style={{ color: 'var(--text-muted)', padding: '4px 0' }}>Spec Max</td>
                        <td style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-red)', textAlign: 'right' }}>
                          {paramRecord.spec_max} {unit}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>

                {/* Module A */}
                <div className="card">
                  <div className="card-title">🔬 Module A — Anomaly</div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
                    <div className="flex justify-between items-center">
                      <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>Anomaly Score</span>
                      <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: 'var(--color-teal)' }}>
                        {paramDecision.anomaly_score?.toFixed(3) ?? 'N/A'}
                      </span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>Severity</span>
                      <span className={severityClass(paramDecision.anomaly_severity || 'LOW')}>
                        {paramDecision.anomaly_severity || 'N/A'}
                      </span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>Static Result</span>
                      <span className={`badge ${paramDecision.static_result === 'FAIL' ? 'badge-fail' : 'badge-pass'}`}>
                        {paramDecision.static_result}
                      </span>
                    </div>
                    {/* Score bar */}
                    <div>
                      <div style={{ height: 6, background: 'var(--color-border)', borderRadius: 3, overflow: 'hidden' }}>
                        <div style={{
                          width: `${((paramDecision.anomaly_score ?? 0) * 100).toFixed(1)}%`,
                          height: '100%',
                          background: (paramDecision.anomaly_score ?? 0) > 0.8
                            ? 'var(--color-red)'
                            : (paramDecision.anomaly_score ?? 0) > 0.65
                            ? 'var(--color-amber)'
                            : 'var(--color-teal)',
                          borderRadius: 3,
                          transition: 'width 1s ease',
                        }} />
                      </div>
                    </div>
                  </div>
                </div>

                {/* Module B */}
                <div className="card">
                  <div className="card-title">📉 Module B — Drift</div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
                    <div className="flex justify-between items-center">
                      <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>Predicted 168h</span>
                      <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: 'var(--color-amber)' }}>
                        {paramDecision.predicted_168h !== null
                          ? `${Number(paramDecision.predicted_168h).toFixed(3)} ${unit}`
                          : 'N/A'}
                      </span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>Drift Risk</span>
                      <span className={driftClass(paramDecision.drift_risk || '')}>
                        {paramDecision.drift_risk || 'N/A'}
                      </span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>Final Decision</span>
                      <span className={decisionClass(paramDecision.final_decision || '')}>
                        {paramDecision.final_decision || 'N/A'}
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Explanation */}
              <div className="card animate-fade-in-delay-4">
                <div className="card-title">
                  💬 AI Explanation (for QA Inspector)
                </div>
                <div className="explanation-box">
                  {paramDecision.explanation || 'No explanation available.'}
                </div>
              </div>
            </>
          )}
        </>
      )}

      {!detail && !loading && !error && (
        <div className="empty-state animate-fade-in-delay-2">
          <div className="empty-state-icon">🔍</div>
          <div>Enter a component ID to explore its burn-in data.</div>
          <div style={{ fontSize: '0.8rem', marginTop: 'var(--space-3)', color: 'var(--text-muted)' }}>
            Try the demo components: C001 (healthy), C002 (static fail), C003 (latent defect — the key case)
          </div>
        </div>
      )}
    </div>
  );
}
