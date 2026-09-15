import React, { useEffect, useState } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend, Cell,
} from 'recharts';
import { getMetrics } from '../api/client';
import type { MetricsResponse } from '../api/client';

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
        <div key={p.name} style={{ color: p.fill || p.color || 'var(--text-primary)', fontWeight: 600, marginBottom: 2 }}>
          {p.name}: {p.value}
        </div>
      ))}
    </div>
  );
};

type BL = NonNullable<MetricsResponse['baseline_comparison']>;
type BLKey = keyof BL;

const CONFIG_LABELS: Record<string, string> = {
  static_only: 'Static Only\n(Traditional)',
  static_plus_a: 'Static + AI\n(Module A)',
  full_system: 'Full AI System\n(A + B)',
};

const CONFIG_COLORS = ['#484f58', '#388bfd', '#00d4aa'];

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="card mb-6">
      <div className="card-title" style={{ marginBottom: 'var(--space-5)' }}>{title}</div>
      {children}
    </div>
  );
}

export default function BaselineComparison() {
  const [metrics, setMetrics] = useState<MetricsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getMetrics()
      .then(setMetrics)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const baseline = metrics?.baseline_comparison;
  const configs: BLKey[] = ['static_only', 'static_plus_a', 'full_system'];

  // Build chart datasets
  const detectionData = configs.map((k, i) => ({
    name: CONFIG_LABELS[k].replace('\n', ' '),
    'Latent Defects Caught': baseline?.[k]?.latent_defects_detected ?? 0,
    'Total Defects Caught': baseline?.[k]?.defects_detected ?? 0,
    'False Negatives': baseline?.[k]?.false_negatives ?? 0,
    'False Positives': baseline?.[k]?.false_positives ?? 0,
    'Escaped Defects': baseline?.[k]?.escaped_defects ?? 0,
    fill: CONFIG_COLORS[i],
  }));

  const detectionRateData = configs.map((k, i) => ({
    name: CONFIG_LABELS[k].replace('\n', ' '),
    'Detection Rate %': Math.round((baseline?.[k]?.detection_rate ?? 0) * 100),
    fill: CONFIG_COLORS[i],
  }));

  const moduleB = metrics?.module_b;
  const screening = metrics?.screening;

  return (
    <div className="page-content animate-fade-in">
      <div className="page-header">
        <div className="page-header-eyebrow">Evaluation</div>
        <h1>Baseline Comparison</h1>
        <p>
          The key proof of value: how the AI system compares against traditional static-limit screening.
          All numbers are computed from running the pipeline on the actual held-out test set.
        </p>
      </div>

      {loading && <div className="loading-state"><div className="spinner" /><span>Loading evaluation data...</span></div>}
      {error && <div className="error-state">{error}</div>}

      {!loading && metrics && (
        <>
          {/* Headline Impact */}
          <div className="card animate-fade-in-delay-1" style={{ borderColor: 'rgba(0,212,170,0.3)', marginBottom: 'var(--space-6)' }}>
            <div className="card-title" style={{ color: 'var(--color-teal)' }}>
              🏆 Headline Impact: Why AI Screening Matters
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 'var(--space-4)' }}>
              {configs.map((k, i) => {
                const b = baseline?.[k];
                return (
                  <div key={k} style={{
                    background: i === 2 ? 'rgba(0,212,170,0.08)' : 'var(--color-bg-secondary)',
                    border: `1px solid ${i === 2 ? 'rgba(0,212,170,0.3)' : 'var(--color-border)'}`,
                    borderRadius: 'var(--radius-md)',
                    padding: 'var(--space-5)',
                    position: 'relative',
                  }}>
                    {i === 2 && (
                      <div style={{
                        position: 'absolute', top: -10, right: 12,
                        background: 'var(--color-teal)', color: '#000',
                        fontSize: '0.65rem', fontWeight: 700, padding: '2px 8px',
                        borderRadius: 'var(--radius-full)',
                      }}>OUR SYSTEM</div>
                    )}
                    <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 8 }}>
                      {CONFIG_LABELS[k].replace('\n', ' — ')}
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <span style={{ color: 'var(--text-secondary)', fontSize: '0.82rem' }}>Latent defects caught</span>
                        <span style={{ fontWeight: 800, color: CONFIG_COLORS[i], fontFamily: 'var(--font-mono)' }}>
                          {b?.latent_defects_detected ?? '–'}/{b?.latent_defects_total ?? '–'}
                        </span>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <span style={{ color: 'var(--text-secondary)', fontSize: '0.82rem' }}>False negatives</span>
                        <span style={{ fontWeight: 800, color: (b?.false_negatives ?? 0) > 0 ? 'var(--color-red)' : 'var(--color-green)', fontFamily: 'var(--font-mono)' }}>
                          {b?.false_negatives ?? '–'}
                        </span>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <span style={{ color: 'var(--text-secondary)', fontSize: '0.82rem' }}>Escaped defects</span>
                        <span style={{ fontWeight: 800, color: (b?.escaped_defects ?? 0) > 0 ? 'var(--color-amber)' : 'var(--color-green)', fontFamily: 'var(--font-mono)' }}>
                          {b?.escaped_defects ?? '–'}
                        </span>
                      </div>
                      <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                        <span style={{ color: 'var(--text-secondary)', fontSize: '0.82rem' }}>Detection rate</span>
                        <span style={{ fontWeight: 800, color: 'var(--text-primary)', fontFamily: 'var(--font-mono)' }}>
                          {b?.detection_rate !== undefined ? `${(b.detection_rate * 100).toFixed(1)}%` : '–'}
                        </span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Charts */}
          <div className="grid-2 animate-fade-in-delay-2 mb-6">
            <Section title="📊 Defect Detection Breakdown">
              <div className="chart-container chart-container-lg">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={detectionData} margin={{ top: 10, right: 10, bottom: 0, left: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(56,139,253,0.08)" />
                    <XAxis dataKey="name" tick={{ fill: 'var(--text-muted)', fontSize: 10 }} />
                    <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 11 }} />
                    <Tooltip content={<CustomTooltip />} />
                    <Legend formatter={(v) => <span style={{ color: 'var(--text-secondary)', fontSize: '0.8rem' }}>{v}</span>} />
                    <Bar dataKey="Latent Defects Caught" fill="var(--color-teal)" radius={[4, 4, 0, 0]} />
                    <Bar dataKey="False Negatives" fill="var(--color-red)" radius={[4, 4, 0, 0]} />
                    <Bar dataKey="False Positives" fill="var(--color-amber)" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Section>

            <Section title="🎯 Overall Detection Rate (%)">
              <div className="chart-container chart-container-lg">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={detectionRateData} margin={{ top: 10, right: 10, bottom: 0, left: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(56,139,253,0.08)" />
                    <XAxis dataKey="name" tick={{ fill: 'var(--text-muted)', fontSize: 10 }} />
                    <YAxis domain={[0, 100]} tick={{ fill: 'var(--text-muted)', fontSize: 11 }} unit="%" />
                    <Tooltip content={<CustomTooltip />} />
                    <Bar dataKey="Detection Rate %" radius={[4, 4, 0, 0]}>
                      {detectionRateData.map((entry, i) => (
                        <Cell key={i} fill={entry.fill} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Section>
          </div>

          {/* Module B performance */}
          {moduleB && (
            <div className="card animate-fade-in-delay-3 mb-6">
              <div className="card-title">🤖 Module B — Drift Prediction Performance (Test Set)</div>
              <div className="table-wrapper">
                <table>
                  <thead>
                    <tr>
                      <th>Parameter</th>
                      <th>Model Selected</th>
                      <th>MAE</th>
                      <th>RMSE</th>
                      <th>R²</th>
                      <th>CV MAE (train)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(moduleB).filter(([k]) => k !== 'model_selection').map(([param, m]) => {
                      const sel = (moduleB.model_selection as any)?.[param];
                      return (
                        <tr key={param}>
                          <td style={{ fontWeight: 600 }}>{param.replace('_', ' ')}</td>
                          <td>
                            <span className="badge badge-pass" style={{ fontSize: '0.7rem' }}>
                              {sel?.selected?.replace('_', ' ') ?? 'N/A'}
                            </span>
                          </td>
                          <td className="td-mono" style={{ color: 'var(--color-teal)' }}>
                            {(m as any).mae?.toFixed(4) ?? 'N/A'}
                          </td>
                          <td className="td-mono">{(m as any).rmse?.toFixed(4) ?? 'N/A'}</td>
                          <td className="td-mono" style={{ color: ((m as any).r2 ?? 0) > 0.7 ? 'var(--color-green)' : 'var(--color-amber)' }}>
                            {(m as any).r2?.toFixed(4) ?? 'N/A'}
                          </td>
                          <td className="td-mono" style={{ color: 'var(--text-muted)' }}>
                            {sel?.selected_mae?.toFixed(4) ?? 'N/A'}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              {/* Model selection detail */}
              {moduleB.model_selection && (
                <details style={{ marginTop: 'var(--space-4)' }}>
                  <summary style={{ cursor: 'pointer', color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
                    View full model selection comparison table
                  </summary>
                  <div className="table-wrapper" style={{ marginTop: 'var(--space-3)' }}>
                    <table>
                      <thead>
                        <tr>
                          <th>Parameter</th>
                          <th>Linear Regression MAE</th>
                          <th>Ridge MAE</th>
                          <th>Random Forest MAE</th>
                          <th>Winner</th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(moduleB.model_selection as Record<string, any>).map(([param, results]) => (
                          <tr key={param}>
                            <td style={{ fontWeight: 600 }}>{param.replace('_', ' ')}</td>
                            <td className="td-mono">{results.linear_regression?.mae?.toFixed(4) ?? '–'}</td>
                            <td className="td-mono">{results.ridge?.mae?.toFixed(4) ?? '–'}</td>
                            <td className="td-mono">{results.random_forest?.mae?.toFixed(4) ?? '–'}</td>
                            <td>
                              <span className="badge badge-pass" style={{ fontSize: '0.7rem' }}>
                                {results.selected?.replace('_', ' ') ?? 'N/A'}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </details>
              )}
            </div>
          )}

          {/* Screening summary */}
          {screening && (
            <div className="card animate-fade-in-delay-4">
              <div className="card-title">📋 Latent Defect Screening Summary</div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 'var(--space-4)' }}>
                {[
                  { label: 'Latent Defects Caught', value: `${screening.latent_defects_caught ?? '–'} / ${screening.latent_defects_total ?? '–'}`, color: 'var(--color-teal)' },
                  { label: 'Capture Rate', value: screening.latent_capture_rate !== undefined ? `${(screening.latent_capture_rate * 100).toFixed(1)}%` : '–', color: 'var(--color-green)' },
                  { label: 'False Positives (Healthy → Flagged)', value: String(screening.healthy_false_positives ?? '–'), color: 'var(--color-amber)' },
                  { label: 'Test Components', value: String(screening.test_components ?? '–'), color: 'var(--color-blue)' },
                ].map(({ label, value, color }) => (
                  <div key={label} style={{
                    background: 'var(--color-bg-secondary)',
                    borderRadius: 'var(--radius-md)',
                    padding: 'var(--space-4)',
                    border: '1px solid var(--color-border)',
                  }}>
                    <div className="stat-label">{label}</div>
                    <div style={{ fontSize: '1.5rem', fontWeight: 800, color, fontFamily: 'var(--font-mono)' }}>
                      {value}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      {!loading && !metrics && !error && (
        <div className="empty-state">
          <div className="empty-state-icon">📊</div>
          <div>Run the pipeline first to generate evaluation metrics.</div>
          <div style={{ fontSize: '0.8rem', marginTop: 8, color: 'var(--text-muted)' }}>
            Execute: <code className="font-mono" style={{ background: 'var(--color-bg-secondary)', padding: '2px 8px', borderRadius: 4 }}>
              python scripts/run_pipeline.py
            </code>
          </div>
        </div>
      )}
    </div>
  );
}
