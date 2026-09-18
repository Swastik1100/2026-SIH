import { useState } from 'react';
import { predict } from '../api/client';
import type { MeasurementInput, ComponentPrediction } from '../api/client';

// ── Constants ────────────────────────────────────────────────────────────
const PARAMETERS = [
  {
    key: 'iddq' as const,
    label: 'IDDQ',
    unit: 'mA',
    spec_min: 0.1,
    spec_max: 5.0,
    placeholder_0h: 1.5,
    placeholder_24h: 1.52,
    placeholder_96h: 1.55,
  },
  {
    key: 'leakage_current' as const,
    label: 'Leakage Current',
    unit: 'µA',
    spec_min: 0.0,
    spec_max: 50.0,
    placeholder_0h: 10.0,
    placeholder_24h: 10.5,
    placeholder_96h: 11.0,
  },
  {
    key: 'propagation_delay' as const,
    label: 'Propagation Delay',
    unit: 'ns',
    spec_min: 1.0,
    spec_max: 15.0,
    placeholder_0h: 5.0,
    placeholder_24h: 5.1,
    placeholder_96h: 5.2,
  },
] as const;

type ParamKey = 'iddq' | 'leakage_current' | 'propagation_delay';

interface ParamValues {
  value_0h: string;
  value_24h: string;
  value_96h: string;
  spec_min: string;
  spec_max: string;
  enabled: boolean;
}

const defaultParamValues = (spec_min: number, spec_max: number, p0: number, p24: number, p96: number): ParamValues => ({
  value_0h: String(p0),
  value_24h: String(p24),
  value_96h: String(p96),
  spec_min: String(spec_min),
  spec_max: String(spec_max),
  enabled: true,
});

const DECISION_COLORS: Record<string, string> = {
  PASS: 'var(--color-pass, #00d4aa)',
  WATCH: 'var(--color-watch, #f5a623)',
  REVIEW: 'var(--color-review, #a855f7)',
  REJECT: 'var(--color-reject, #ef4444)',
};

const SEVERITY_COLORS: Record<string, string> = {
  LOW: 'var(--color-green, #22c55e)',
  MEDIUM: 'var(--color-amber, #f5a623)',
  HIGH: 'var(--color-red, #ef4444)',
};

const RISK_COLORS: Record<string, string> = {
  SAFE: 'var(--color-green, #22c55e)',
  WATCH: 'var(--color-amber, #f5a623)',
  DANGEROUS: 'var(--color-red, #ef4444)',
};

// ── Sub-components ───────────────────────────────────────────────────────

function ResultCard({ result }: { result: ComponentPrediction }) {
  const { anomaly, drift, decision, explanation, parameter, measurements } = result;
  const decColor = DECISION_COLORS[decision.decision] || '#888';
  const sevColor = SEVERITY_COLORS[anomaly.severity] || '#888';
  const riskColor = RISK_COLORS[drift.drift_risk] || '#888';

  return (
    <div
      style={{
        border: `2px solid ${decColor}`,
        borderRadius: 'var(--radius-lg, 12px)',
        padding: 'var(--space-4, 16px)',
        background: 'var(--color-bg-secondary, #1a1a2e)',
        marginBottom: 'var(--space-3, 12px)',
      }}
    >
      {/* Header row */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
        <div style={{ fontWeight: 700, fontSize: '0.95rem', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
          {parameter.replace('_', ' ')}
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <span style={{
            background: decColor,
            color: '#000',
            borderRadius: 6,
            padding: '3px 10px',
            fontWeight: 800,
            fontSize: '0.85rem',
          }}>
            {decision.decision}
          </span>
          <span style={{
            border: `1px solid ${sevColor}`,
            color: sevColor,
            borderRadius: 6,
            padding: '3px 10px',
            fontWeight: 600,
            fontSize: '0.78rem',
          }}>
            Anomaly: {anomaly.severity}
          </span>
          <span style={{
            border: `1px solid ${riskColor}`,
            color: riskColor,
            borderRadius: 6,
            padding: '3px 10px',
            fontWeight: 600,
            fontSize: '0.78rem',
          }}>
            Drift: {drift.drift_risk}
          </span>
        </div>
      </div>

      {/* Scores grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: 8, marginTop: 12 }}>
        {[
          { label: 'Anomaly Score', value: anomaly.anomaly_score?.toFixed(3), color: sevColor },
          { label: 'XGBoost Score', value: anomaly.xgb_score?.toFixed(3), color: anomaly.xgb_triggered ? 'var(--color-red)' : undefined },
          { label: 'Static Check', value: decision.static_result },
          { label: 'Predicted 168h', value: drift.predicted_168h != null ? drift.predicted_168h.toFixed(4) : '—' },
          { label: 'Drift Rate', value: drift.drift_rate != null ? drift.drift_rate.toFixed(6) : '—' },
          { label: 'Safety Margin', value: `${decision.safety_margin_pct?.toFixed(1)}%` },
        ].map(({ label, value, color }) => (
          <div key={label} style={{
            background: 'var(--color-bg-primary, #0d0d1a)',
            borderRadius: 6,
            padding: '8px 10px',
            border: '1px solid var(--color-border, #2a2a4a)',
          }}>
            <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)', marginBottom: 2, textTransform: 'uppercase', letterSpacing: '0.05em' }}>{label}</div>
            <div style={{ fontWeight: 700, fontSize: '0.92rem', color: color || 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>{value ?? '—'}</div>
          </div>
        ))}
      </div>

      {/* XGBoost triggered banner */}
      {anomaly.xgb_triggered && (
        <div style={{
          marginTop: 10,
          padding: '6px 10px',
          borderRadius: 6,
          background: 'rgba(239,68,68,0.1)',
          border: '1px solid rgba(239,68,68,0.4)',
          fontSize: '0.78rem',
          color: 'var(--color-red)',
          fontWeight: 600,
        }}>
          ⚡ XGBoost classifier independently flagged this as a defect (prob={anomaly.xgb_score?.toFixed(3)})
        </div>
      )}

      {/* Contributing features */}
      {anomaly.contributing_features?.length > 0 && (
        <div style={{ marginTop: 10, fontSize: '0.75rem', color: 'var(--text-muted)' }}>
          <span style={{ fontWeight: 600, color: 'var(--text-secondary)' }}>Top signals: </span>
          {anomaly.contributing_features.join(' · ')}
        </div>
      )}

      {/* Reason / explanation */}
      <div style={{
        marginTop: 10,
        padding: '8px 12px',
        borderRadius: 6,
        background: 'var(--color-bg-primary, #0d0d1a)',
        fontSize: '0.78rem',
        color: 'var(--text-secondary)',
        lineHeight: 1.5,
        borderLeft: `3px solid ${decColor}`,
      }}>
        <strong style={{ color: 'var(--text-primary)' }}>Reason: </strong>{decision.reason}
        {explanation && (
          <><br /><span style={{ color: 'var(--text-muted)' }}>{explanation.slice(0, 300)}{explanation.length > 300 ? '…' : ''}</span></>
        )}
      </div>

      {/* Measurements row */}
      <div style={{ marginTop: 10, display: 'flex', gap: 8, flexWrap: 'wrap', fontSize: '0.72rem', color: 'var(--text-muted)' }}>
        {Object.entries(measurements)
          .filter(([, v]) => v != null)
          .map(([k, v]) => (
            <span key={k} style={{ fontFamily: 'var(--font-mono)' }}>
              {k}: <strong style={{ color: 'var(--text-secondary)' }}>{(v as number).toFixed(4)}</strong>
            </span>
          ))}
      </div>
    </div>
  );
}

// ── Overall verdict banner ───────────────────────────────────────────────
function VerdictBanner({ results }: { results: ComponentPrediction[] }) {
  const decisions = results.map(r => r.decision.decision);
  const hasReject = decisions.includes('REJECT');
  const hasReview = decisions.includes('REVIEW');
  const hasWatch = decisions.includes('WATCH');

  const verdict = hasReject ? 'REJECT' : hasReview ? 'REVIEW' : hasWatch ? 'WATCH' : 'PASS';
  const color = DECISION_COLORS[verdict];
  const icon = { PASS: '✅', WATCH: '👁️', REVIEW: '⚠️', REJECT: '❌' }[verdict];
  const msg = {
    PASS: 'All parameters passed. Component is clear for use.',
    WATCH: 'Component shows early drift — monitor closely.',
    REVIEW: 'Flagged by AI model — manual QA review required before shipment.',
    REJECT: 'Component REJECTED — critical anomaly or drift detected.',
  }[verdict];

  return (
    <div style={{
      border: `2px solid ${color}`,
      borderRadius: 'var(--radius-lg, 12px)',
      padding: '20px 24px',
      background: `${color}15`,
      display: 'flex',
      alignItems: 'center',
      gap: 16,
      marginBottom: 'var(--space-4, 16px)',
    }}>
      <div style={{ fontSize: '2.5rem', lineHeight: 1 }}>{icon}</div>
      <div>
        <div style={{ fontSize: '1.4rem', fontWeight: 900, color, fontFamily: 'var(--font-mono)' }}>
          COMPONENT {verdict}
        </div>
        <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', marginTop: 4 }}>{msg}</div>
      </div>
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────
export default function TestComponent() {
  const [componentId, setComponentId] = useState('TEST-001');
  const [lotId, setLotId] = useState('TEST-LOT');
  const [tempProfile, setTempProfile] = useState('125C');

  const initialParams: Record<ParamKey, ParamValues> = {
    iddq: defaultParamValues(0.1, 5.0, 1.5, 1.52, 1.55),
    leakage_current: defaultParamValues(0.0, 50.0, 10.0, 10.5, 11.0),
    propagation_delay: defaultParamValues(1.0, 15.0, 5.0, 5.1, 5.2),
  };
  const [params, setParams] = useState<Record<ParamKey, ParamValues>>(initialParams);

  const [loading, setLoading] = useState(false);
  const [results, setResults] = useState<ComponentPrediction[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const updateParam = (pk: ParamKey, field: keyof ParamValues, value: string | boolean) => {
    setParams(prev => ({ ...prev, [pk]: { ...prev[pk], [field]: value } }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setResults(null);
    setLoading(true);

    try {
      const measurements: MeasurementInput[] = PARAMETERS
        .filter(p => params[p.key].enabled)
        .map(p => {
          const pv = params[p.key];
          return {
            component_id: componentId.trim() || 'TEST-001',
            lot_id: lotId.trim() || 'TEST-LOT',
            parameter: p.key,
            value_0h: parseFloat(pv.value_0h),
            value_24h: pv.value_24h !== '' ? parseFloat(pv.value_24h) : null,
            value_96h: pv.value_96h !== '' ? parseFloat(pv.value_96h) : null,
            spec_min: parseFloat(pv.spec_min),
            spec_max: parseFloat(pv.spec_max),
            temperature_profile: tempProfile,
          };
        });

      if (measurements.length === 0) {
        setError('Enable at least one parameter to test.');
        setLoading(false);
        return;
      }

      const data = await predict(measurements);
      setResults(data.results);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.message || 'Prediction failed. Is the backend running?');
    } finally {
      setLoading(false);
    }
  };

  const handleReset = () => {
    setParams(initialParams);
    setResults(null);
    setError(null);
    setComponentId('TEST-001');
    setLotId('TEST-LOT');
  };

  // Load a known "latent defect" example
  const loadExample = (type: 'healthy' | 'latent_defect' | 'static_fail' | 'gradual_drift') => {
    setResults(null);
    setError(null);
    if (type === 'healthy') {
      setComponentId('EX-HEALTHY');
      setLotId('EXAMPLE-LOT');
      setParams({
        iddq: { ...params.iddq, value_0h: '1.48', value_24h: '1.50', value_96h: '1.51', enabled: true },
        leakage_current: { ...params.leakage_current, value_0h: '9.8', value_24h: '9.9', value_96h: '10.0', enabled: true },
        propagation_delay: { ...params.propagation_delay, value_0h: '4.95', value_24h: '5.0', value_96h: '5.02', enabled: true },
      });
    } else if (type === 'latent_defect') {
      setComponentId('EX-LATENT');
      setLotId('EXAMPLE-LOT');
      setParams({
        iddq: { ...params.iddq, value_0h: '1.5', value_24h: '1.6', value_96h: '1.75', enabled: true },
        leakage_current: { ...params.leakage_current, value_0h: '10.5', value_24h: '18.2', value_96h: '32.0', enabled: true },
        propagation_delay: { ...params.propagation_delay, value_0h: '5.0', value_24h: '5.3', value_96h: '5.7', enabled: true },
      });
    } else if (type === 'static_fail') {
      setComponentId('EX-STATIC-FAIL');
      setLotId('EXAMPLE-LOT');
      setParams({
        iddq: { ...params.iddq, value_0h: '1.5', value_24h: '1.52', value_96h: '1.55', enabled: true },
        leakage_current: { ...params.leakage_current, value_0h: '10.0', value_24h: '55.0', value_96h: '58.0', enabled: true },
        propagation_delay: { ...params.propagation_delay, value_0h: '5.0', value_24h: '5.1', value_96h: '5.2', enabled: false },
      });
    } else if (type === 'gradual_drift') {
      setComponentId('EX-DRIFT');
      setLotId('EXAMPLE-LOT');
      setParams({
        iddq: { ...params.iddq, value_0h: '1.5', value_24h: '2.1', value_96h: '3.2', enabled: true },
        leakage_current: { ...params.leakage_current, value_0h: '10.0', value_24h: '22.0', value_96h: '38.0', enabled: true },
        propagation_delay: { ...params.propagation_delay, value_0h: '5.0', value_24h: '7.5', value_96h: '11.0', enabled: true },
      });
    }
  };

  return (
    <div className="page-content animate-fade-in">
      <div className="page-header">
        <div className="page-header-eyebrow">Live Screening</div>
        <h1>Test New Component</h1>
        <p>
          Enter burn-in measurement data for a component and run it through the full AI screening
          pipeline (MAD z-score + Isolation Forest + XGBoost) to get an instant PASS / REVIEW / REJECT verdict.
        </p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-5)', alignItems: 'start' }}>
        {/* ── INPUT FORM ─────────────────────────────────────────────── */}
        <div>
          {/* Quick-load examples */}
          <div className="card" style={{ marginBottom: 'var(--space-4)' }}>
            <div className="card-title">⚡ Quick Examples</div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {[
                { type: 'healthy' as const, label: '✅ Healthy', color: 'var(--color-green)' },
                { type: 'latent_defect' as const, label: '🕵️ Latent Defect', color: 'var(--color-amber)' },
                { type: 'static_fail' as const, label: '❌ Static Fail', color: 'var(--color-red)' },
                { type: 'gradual_drift' as const, label: '📈 Gradual Drift', color: 'var(--color-purple)' },
              ].map(({ type, label, color }) => (
                <button
                  key={type}
                  onClick={() => loadExample(type)}
                  className="btn"
                  style={{ fontSize: '0.78rem', border: `1px solid ${color}`, color, background: `${color}15`, padding: '5px 12px' }}
                >
                  {label}
                </button>
              ))}
            </div>
            <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: 8 }}>
              Click to auto-fill values with realistic examples, then press "Run Screening".
            </div>
          </div>

          <form onSubmit={handleSubmit}>
            {/* Component metadata */}
            <div className="card" style={{ marginBottom: 'var(--space-4)' }}>
              <div className="card-title">Component Info</div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <div>
                  <label style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>Component ID</label>
                  <input
                    className="input"
                    value={componentId}
                    onChange={e => setComponentId(e.target.value)}
                    placeholder="e.g. COMP-00123"
                    style={{ width: '100%', boxSizing: 'border-box' }}
                  />
                </div>
                <div>
                  <label style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>Lot ID</label>
                  <input
                    className="input"
                    value={lotId}
                    onChange={e => setLotId(e.target.value)}
                    placeholder="e.g. LOT-007"
                    style={{ width: '100%', boxSizing: 'border-box' }}
                  />
                </div>
                <div>
                  <label style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', marginBottom: 4 }}>Temperature Profile</label>
                  <select
                    className="input"
                    value={tempProfile}
                    onChange={e => setTempProfile(e.target.value)}
                    style={{ width: '100%', boxSizing: 'border-box' }}
                  >
                    <option value="125C">125°C (Standard)</option>
                    <option value="85C">85°C (Mild)</option>
                    <option value="150C">150°C (Aggressive)</option>
                  </select>
                </div>
              </div>
            </div>

            {/* Parameter inputs */}
            {PARAMETERS.map(p => {
              const pv = params[p.key];
              return (
                <div
                  key={p.key}
                  className="card"
                  style={{
                    marginBottom: 'var(--space-3)',
                    opacity: pv.enabled ? 1 : 0.4,
                    transition: 'opacity 0.2s',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                    <div className="card-title" style={{ margin: 0 }}>
                      {p.label} <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', fontWeight: 400 }}>({p.unit})</span>
                    </div>
                    <label style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                      <input
                        type="checkbox"
                        checked={pv.enabled}
                        onChange={e => updateParam(p.key, 'enabled', e.target.checked)}
                        style={{ accentColor: 'var(--color-teal)' }}
                      />
                      Include
                    </label>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10 }}>
                    {(['value_0h', 'value_24h', 'value_96h'] as const).map(field => (
                      <div key={field}>
                        <label style={{ fontSize: '0.68rem', color: 'var(--text-muted)', display: 'block', marginBottom: 3, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                          {field.replace('value_', '')}
                          {field === 'value_0h' ? ' *' : ' (opt)'}
                        </label>
                        <input
                          type="number"
                          step="any"
                          className="input"
                          value={pv[field]}
                          onChange={e => updateParam(p.key, field, e.target.value)}
                          disabled={!pv.enabled}
                          required={field === 'value_0h' && pv.enabled}
                          style={{ width: '100%', boxSizing: 'border-box', fontFamily: 'var(--font-mono)', fontSize: '0.82rem' }}
                        />
                      </div>
                    ))}
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginTop: 10 }}>
                    <div>
                      <label style={{ fontSize: '0.68rem', color: 'var(--text-muted)', display: 'block', marginBottom: 3, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Spec Min *</label>
                      <input
                        type="number"
                        step="any"
                        className="input"
                        value={pv.spec_min}
                        onChange={e => updateParam(p.key, 'spec_min', e.target.value)}
                        disabled={!pv.enabled}
                        style={{ width: '100%', boxSizing: 'border-box', fontFamily: 'var(--font-mono)', fontSize: '0.82rem' }}
                      />
                    </div>
                    <div>
                      <label style={{ fontSize: '0.68rem', color: 'var(--text-muted)', display: 'block', marginBottom: 3, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Spec Max *</label>
                      <input
                        type="number"
                        step="any"
                        className="input"
                        value={pv.spec_max}
                        onChange={e => updateParam(p.key, 'spec_max', e.target.value)}
                        disabled={!pv.enabled}
                        style={{ width: '100%', boxSizing: 'border-box', fontFamily: 'var(--font-mono)', fontSize: '0.82rem' }}
                      />
                    </div>
                  </div>
                </div>
              );
            })}

            {/* Action buttons */}
            <div style={{ display: 'flex', gap: 10, marginTop: 'var(--space-4)' }}>
              <button
                type="submit"
                className="btn btn-primary"
                disabled={loading}
                style={{ flex: 1, padding: '12px', fontSize: '0.92rem', fontWeight: 700 }}
              >
                {loading ? (
                  <span style={{ display: 'flex', alignItems: 'center', gap: 8, justifyContent: 'center' }}>
                    <span className="spinner" style={{ width: 14, height: 14 }} />
                    Running AI Pipeline...
                  </span>
                ) : '🔍 Run Screening'}
              </button>
              <button type="button" className="btn" onClick={handleReset} disabled={loading}>
                Reset
              </button>
            </div>
          </form>
        </div>

        {/* ── RESULTS PANEL ───────────────────────────────────────────── */}
        <div style={{ position: 'sticky', top: 24 }}>
          {!results && !error && !loading && (
            <div className="card" style={{ textAlign: 'center', padding: '48px 24px' }}>
              <div style={{ fontSize: '3rem', marginBottom: 12 }}>🧪</div>
              <div style={{ fontWeight: 700, fontSize: '1.05rem', marginBottom: 8 }}>Ready to Screen</div>
              <div style={{ color: 'var(--text-muted)', fontSize: '0.83rem', lineHeight: 1.6 }}>
                Fill in the burn-in measurements on the left and click <strong>"Run Screening"</strong> to get an
                instant AI verdict across all three detection stages:
                <br /><br />
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem' }}>
                  MAD z-score → Isolation Forest → XGBoost
                </span>
              </div>
            </div>
          )}

          {loading && (
            <div className="card" style={{ textAlign: 'center', padding: '48px 24px' }}>
              <div className="loading-state">
                <div className="spinner" />
                <span>Running AI pipeline...</span>
              </div>
              <div style={{ color: 'var(--text-muted)', fontSize: '0.78rem', marginTop: 12 }}>
                Computing MAD z-scores, Isolation Forest, XGBoost scores and drift predictions...
              </div>
            </div>
          )}

          {error && (
            <div className="card" style={{ borderColor: 'var(--color-red)', padding: 20 }}>
              <div style={{ color: 'var(--color-red)', fontWeight: 700, marginBottom: 8 }}>⚠️ Error</div>
              <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>{error}</div>
              <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: 8 }}>
                Make sure the FastAPI backend is running on port 8000.
              </div>
            </div>
          )}

          {results && results.length > 0 && (
            <div>
              <VerdictBanner results={results} />
              <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginBottom: 12 }}>
                Results for <strong style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>{results[0].component_id}</strong>
                {' '}· Lot: <strong style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>{results[0].lot_id}</strong>
                {' '}· {results.length} parameter{results.length > 1 ? 's' : ''} screened
              </div>
              {results.map((r, i) => <ResultCard key={i} result={r} />)}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
