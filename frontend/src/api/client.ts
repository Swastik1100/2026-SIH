/**
 * Typed API client for BurnSight AI backend.
 * Reads VITE_API_URL env var (defaults to http://localhost:8000).
 */
import axios from 'axios';

const BASE_URL = (import.meta.env.VITE_API_URL as string) || 'http://localhost:8000';

const api = axios.create({
  baseURL: BASE_URL,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

// ── Types ──────────────────────────────────────────────────────────────

export interface AnomalyResult {
  robust_z_score: number;
  isolation_forest_score: number;
  anomaly_score: number;
  anomaly_label: boolean;
  severity: 'LOW' | 'MEDIUM' | 'HIGH';
  xgb_score: number;
  xgb_triggered: boolean;
  contributing_features: string[];
}

export interface DriftResult {
  predicted_168h: number | null;
  predicted_drift: number | null;
  drift_rate: number | null;
  drift_risk: 'SAFE' | 'WATCH' | 'DANGEROUS';
  drift_ratio?: number | null;
}

export interface DecisionResult {
  decision: 'PASS' | 'WATCH' | 'REVIEW' | 'REJECT';
  reason: string;
  rule_name: string;
  static_result: 'PASS' | 'FAIL';
  safety_margin_pct: number;
  confidence: 'HIGH' | 'MEDIUM' | 'LOW';
}

export interface ComponentPrediction {
  component_id: string;
  lot_id: string;
  parameter: string;
  measurements: Record<string, number | null>;
  anomaly: AnomalyResult;
  drift: DriftResult;
  decision: DecisionResult;
  explanation: string;
  label?: string;
}

export interface MeasurementInput {
  component_id: string;
  lot_id: string;
  parameter: string;
  value_0h: number;
  value_24h?: number | null;
  value_96h?: number | null;
  value_168h?: number | null;
  spec_min: number;
  spec_max: number;
  temperature_profile?: string;
}

export interface DashboardStats {
  total_components: number;
  total_records: number;
  decisions: Record<string, number>;
  anomaly_rate: number;
  escaped_defects_prevented: number;
}

export interface ScreeningRecord {
  component_id: string;
  lot_id: string;
  parameter: string;
  static_result: 'PASS' | 'FAIL';
  anomaly_score: number | null;
  predicted_168h: number | null;
  drift_risk: 'SAFE' | 'WATCH' | 'DANGEROUS' | null;
  final_decision: 'PASS' | 'WATCH' | 'REVIEW' | 'REJECT' | null;
  explanation: string | null;
  label?: string | null;
}

export interface PaginatedScreeningResults {
  total: number;
  page: number;
  page_size: number;
  records: ScreeningRecord[];
}

export interface ComponentDetail {
  component_id: string;
  lot_id: string;
  records: Array<{
    parameter: string;
    value_0h: number | null;
    value_24h: number | null;
    value_96h: number | null;
    value_168h: number | null;
    spec_min: number;
    spec_max: number;
  }>;
  decisions: Array<{
    parameter: string;
    static_result: string;
    anomaly_score: number | null;
    anomaly_severity: string | null;
    predicted_168h: number | null;
    drift_risk: string | null;
    final_decision: string | null;
    explanation: string | null;
  }>;
}

export interface LotSummary {
  lot_id: string;
  component_count: number;
  parameters: string[];
  statistics: Record<string, { mean: number; median: number; std: number; mad: number }>;
  anomalous_components: string[];
}

export interface MetricsResponse {
  module_a?: {
    precision?: number;
    recall?: number;
    f1?: number;
    false_negative_rate?: number;
    roc_auc?: number;
    pr_auc?: number;
    confusion_matrix?: { tn: number; fp: number; fn: number; tp: number };
  };
  module_b?: Record<string, {
    mae?: number; rmse?: number; r2?: number;
    model_selection?: Record<string, Record<string, unknown>>;
  }>;
  screening?: {
    latent_defects_caught?: number;
    latent_defects_total?: number;
    latent_capture_rate?: number;
    healthy_false_positives?: number;
    test_components?: number;
  };
  baseline_comparison?: {
    static_only?: BaselineStats;
    static_plus_a?: BaselineStats;
    full_system?: BaselineStats;
  };
}

export interface BaselineStats {
  defects_detected: number;
  latent_defects_detected: number;
  latent_defects_total: number;
  false_negatives: number;
  false_positives: number;
  escaped_defects: number;
  total_defects: number;
  detection_rate: number;
}

// ── API Functions ──────────────────────────────────────────────────────

export const health = () =>
  api.get<{ status: string; version: string }>('/health').then(r => r.data);

/** @deprecated Use health() instead */
export const healthCheck = health;

export const getDashboardStats = () =>
  api.get<DashboardStats>('/dashboard-stats').then(r => r.data);

export const getScreeningResults = (
  page = 1,
  pageSize = 100,
  decision?: string,
) => {
  const params: Record<string, unknown> = { page, page_size: pageSize };
  if (decision) params.decision = decision;
  return api.get<PaginatedScreeningResults>('/screening-results', { params }).then(r => r.data);
};

export const getComponentDetail = (id: string) =>
  api.get<ComponentDetail>(`/component/${id}`).then(r => r.data);

export const getLotSummary = (id: string) =>
  api.get<LotSummary>(`/lot/${id}`).then(r => r.data);

export const getMetrics = () =>
  api.get<MetricsResponse>('/metrics').then(r => r.data);

export const predict = (measurements: MeasurementInput[]) =>
  api.post<{ results: ComponentPrediction[] }>('/predict', { measurements }).then(r => r.data);

export const screenBatch = (measurements: MeasurementInput[]) =>
  api.post('/screen', { measurements }).then(r => r.data);

export default api;
