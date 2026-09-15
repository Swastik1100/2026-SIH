import React, { useEffect, useState } from 'react';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, PieChart, Pie, Legend,
} from 'recharts';
import { getDashboardStats, getMetrics } from '../api/client';
import type { DashboardStats, MetricsResponse } from '../api/client';


const DECISION_COLORS: Record<string, string> = {
  PASS: 'var(--color-pass)',
  WATCH: 'var(--color-watch)',
  REVIEW: 'var(--color-review)',
  REJECT: 'var(--color-reject)',
};


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
          {p.name}: {p.value}
        </div>
      ))}
    </div>
  );
};

export default function Dashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [metrics, setMetrics] = useState<MetricsResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([getDashboardStats(), getMetrics()])
      .then(([s, m]) => { setStats(s); setMetrics(m); })
      .catch(e => setError(e.message));
  }, []);

  if (error) {
    return (
      <div className="page-content">
        <div className="error-state">
          ⚠ Could not reach backend: {error}. Make sure the FastAPI server is running on port 8000.
        </div>
      </div>
    );
  }

  const decisionData = stats
    ? Object.entries(stats.decisions).map(([k, v]) => ({ name: k, value: v, fill: DECISION_COLORS[k] || '#888' }))
    : [];

  const baseline = metrics?.baseline_comparison;
  const baselineChartData = baseline
    ? [
        {
          name: 'Static Only',
          'Latent Defects Caught': baseline.static_only?.latent_defects_detected ?? 0,
          'False Negatives': baseline.static_only?.false_negatives ?? 0,
          'Detection Rate %': Math.round((baseline.static_only?.detection_rate ?? 0) * 100),
        },
        {
          name: 'Static + Module A',
          'Latent Defects Caught': baseline.static_plus_a?.latent_defects_detected ?? 0,
          'False Negatives': baseline.static_plus_a?.false_negatives ?? 0,
          'Detection Rate %': Math.round((baseline.static_plus_a?.detection_rate ?? 0) * 100),
        },
        {
          name: 'Full System',
          'Latent Defects Caught': baseline.full_system?.latent_defects_detected ?? 0,
          'False Negatives': baseline.full_system?.false_negatives ?? 0,
          'Detection Rate %': Math.round((baseline.full_system?.detection_rate ?? 0) * 100),
        },
      ]
    : [];

  const moduleA = metrics?.module_a;

  return (
    <div className="page-content animate-fade-in">
      <div className="page-header">
        <div className="page-header-eyebrow">Overview</div>
        <h1>Screening Dashboard</h1>
        <p>
          Real-time overview of the AI-driven burn-in screening pipeline.
          All numbers are computed from the actual ML pipeline output.
        </p>
      </div>

      {/* Hero Stat Cards */}
      <div className="stats-grid animate-fade-in-delay-1">
        <div className="stat-card" style={{ '--accent-color': 'var(--color-blue)' } as React.CSSProperties}>
          <div className="stat-label">Total Components</div>
          <div className="stat-value">{stats?.total_components?.toLocaleString() ?? '–'}</div>
          <div className="stat-sub">{stats?.total_records?.toLocaleString()} parameter records</div>
        </div>

        <div className="stat-card" style={{ '--accent-color': 'var(--color-teal)' } as React.CSSProperties}>
          <div className="stat-label">Anomaly Rate</div>
          <div className="stat-value" style={{ color: 'var(--color-teal)' }}>
            {stats?.anomaly_rate?.toFixed(1) ?? '–'}%
          </div>
          <div className="stat-sub">MEDIUM or HIGH severity flags</div>
        </div>

        <div className="stat-card" style={{ '--accent-color': 'var(--color-green)' } as React.CSSProperties}>
          <div className="stat-label">Escaped Defects Prevented</div>
          <div className="stat-value" style={{ color: 'var(--color-green)' }}>
            {stats?.escaped_defects_prevented ?? '–'}
          </div>
          <div className="stat-sub">vs. static-only screening</div>
        </div>

        <div className="stat-card" style={{ '--accent-color': 'var(--color-amber)' } as React.CSSProperties}>
          <div className="stat-label">Module A Recall</div>
          <div className="stat-value" style={{ color: 'var(--color-amber)' }}>
            {moduleA?.recall !== undefined ? `${(moduleA.recall * 100).toFixed(1)}%` : '–'}
          </div>
          <div className="stat-sub">Defect detection sensitivity</div>
        </div>

        <div className="stat-card" style={{ '--accent-color': 'var(--color-purple)' } as React.CSSProperties}>
          <div className="stat-label">False Negative Rate</div>
          <div className="stat-value" style={{ color: 'var(--color-purple)' }}>
            {moduleA?.false_negative_rate !== undefined
              ? `${(moduleA.false_negative_rate * 100).toFixed(1)}%`
              : '–'}
          </div>
          <div className="stat-sub">Missed defects (minimize!)</div>
        </div>

        <div className="stat-card" style={{ '--accent-color': 'var(--color-red)' } as React.CSSProperties}>
          <div className="stat-label">ROC-AUC</div>
          <div className="stat-value" style={{ color: 'var(--color-red)' }}>
            {moduleA?.roc_auc?.toFixed(3) ?? '–'}
          </div>
          <div className="stat-sub">Module A classification quality</div>
        </div>
      </div>

      {/* Charts Row */}
      <div className="grid-2 animate-fade-in-delay-2">
        {/* Decision Distribution */}
        <div className="card">
          <div className="card-title">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/>
            </svg>
            Screening Decisions Distribution
          </div>
          {decisionData.length > 0 ? (
            <div className="chart-container">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={decisionData}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    outerRadius={110}
                    innerRadius={55}
                    label={({ name, value }) => `${name}: ${value}`}
                    labelLine={false}
                  >
                    {decisionData.map((entry, i) => (
                      <Cell key={i} fill={entry.fill} />
                    ))}
                  </Pie>
                  <Tooltip content={<CustomTooltip />} />
                  <Legend
                    formatter={(v) => (
                      <span style={{ color: 'var(--text-secondary)', fontSize: '0.8rem' }}>{v}</span>
                    )}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="loading-state">
              <div className="spinner" />
              <span>Loading...</span>
            </div>
          )}
        </div>

        {/* Baseline Comparison */}
        <div className="card">
          <div className="card-title">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
            </svg>
            AI vs. Static Screening — Detection Rate
          </div>
          {baselineChartData.length > 0 ? (
            <div className="chart-container">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={baselineChartData} margin={{ top: 10, right: 10, bottom: 0, left: 0 }}>
                  <XAxis dataKey="name" tick={{ fill: 'var(--text-muted)', fontSize: 11 }} />
                  <YAxis tick={{ fill: 'var(--text-muted)', fontSize: 11 }} />
                  <Tooltip content={<CustomTooltip />} />
                  <Bar dataKey="Detection Rate %" fill="var(--color-teal)" radius={[4, 4, 0, 0]} />
                  <Bar dataKey="False Negatives" fill="var(--color-red)" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="loading-state">
              <div className="spinner" />
              <span>Loading...</span>
            </div>
          )}
        </div>
      </div>

      {/* C003 Headline Story */}
      <div className="card animate-fade-in-delay-3" style={{ marginTop: 'var(--space-5)', borderColor: 'rgba(0, 212, 170, 0.3)' }}>
        <div className="card-title" style={{ color: 'var(--color-teal)' }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10"/>
            <path d="M12 8v4M12 16h.01"/>
          </svg>
          🎯 Headline Demo: Why Static Screening Fails (Component C003)
        </div>
        <div className="explanation-box">
          <strong>Component C003 — Latent Defect Story:</strong> This component PASSED static screening
          (leakage: 45.1 µA &lt; spec_max: 50 µA). However, the <strong>lot median is only 10.2 µA</strong>.
          Module A flagged it as a <strong>HIGH severity dynamic anomaly</strong> (robust z-score &gt;&gt; 3.5).
          Module B predicted dangerous drift trajectory. Final decision: <strong>REJECT/REVIEW</strong>.{' '}
          <span style={{ color: 'var(--text-secondary)' }}>
            This is the "latent defect" scenario — the AI catches what traditional static screening misses.
            Go to <strong>Component Explorer</strong> → search "C003" to see the full trajectory chart.
          </span>
        </div>
      </div>

      {/* Module A Metrics */}
      {moduleA && (
        <div className="card animate-fade-in-delay-4" style={{ marginTop: 'var(--space-5)' }}>
          <div className="card-title">Module A — Anomaly Detection Metrics (Test Set)</div>
          <div className="grid-3" style={{ gap: 'var(--space-4)' }}>
            {[
              { label: 'Precision', value: moduleA.precision?.toFixed(3), color: 'var(--color-blue)' },
              { label: 'Recall', value: moduleA.recall?.toFixed(3), color: 'var(--color-teal)' },
              { label: 'F1 Score', value: moduleA.f1?.toFixed(3), color: 'var(--color-purple)' },
              { label: 'False Negative Rate', value: moduleA.false_negative_rate?.toFixed(3), color: 'var(--color-red)' },
              { label: 'ROC-AUC', value: moduleA.roc_auc?.toFixed(3), color: 'var(--color-amber)' },
              { label: 'PR-AUC', value: moduleA.pr_auc?.toFixed(3), color: 'var(--color-green)' },
            ].map(({ label, value, color }) => (
              <div key={label} style={{
                background: 'var(--color-bg-secondary)',
                borderRadius: 'var(--radius-md)',
                padding: 'var(--space-4)',
                border: '1px solid var(--color-border)',
              }}>
                <div className="stat-label">{label}</div>
                <div style={{ fontSize: '1.4rem', fontWeight: 800, color, fontFamily: 'var(--font-mono)' }}>
                  {value ?? '–'}
                </div>
              </div>
            ))}
          </div>
          {moduleA.confusion_matrix && (
            <div style={{ marginTop: 'var(--space-4)', fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
              Confusion Matrix — TN: {moduleA.confusion_matrix.tn} | FP: {moduleA.confusion_matrix.fp} |{' '}
              <span style={{ color: 'var(--color-red)' }}>FN: {moduleA.confusion_matrix.fn}</span> |{' '}
              TP: {moduleA.confusion_matrix.tp}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
