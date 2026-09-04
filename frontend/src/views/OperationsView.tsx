/**
 * frontend/src/views/OperationsView.tsx
 *
 * Operations Control Room — live backend telemetry.
 *
 * Data sources (polled every 30 s):
 *   GET /observability/summary — decision & economic metrics
 *   GET /health                — liveness
 *   GET /ready                 — readiness + DB/AI status
 *
 * Monetary values are kept as integer paise throughout and converted to INR
 * only at the display layer via formatINR().
 *
 * IMPORTANT: realized_captured_revenue_minor is OBSERVED (sum of CAPTURED
 * payment amounts linked to recovery cases) — NOT causally attributed
 * incremental revenue. Displayed with an explicit label to avoid confusion.
 */

import React from 'react';
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle,
  Circle,
  RefreshCw,
  Server,
  ShieldCheck,
  TrendingUp,
  Zap,
} from 'lucide-react';
import { Card } from '../components/common/Card';
import { MetricCard } from '../components/common/MetricCard';

import { useOperationsSummary } from '../hooks/useOperationsSummary';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/** Format paise integer to INR display string (e.g. 250000 → "₹2,500") */
function formatINR(paise: number): string {
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(paise / 100);
}

/** Format a float in [0, 1] as a percentage string (e.g. 0.8873 → "88.7%") */
function formatPct(rate: number): string {
  return `${(rate * 100).toFixed(1)}%`;
}

/** Format a UTC ISO 8601 string to a short local time */
function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleTimeString('en-IN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

interface SystemStatusRowProps {
  label: string;
  value: string;
  ok: boolean;
  icon?: React.ReactNode;
}

const SystemStatusRow: React.FC<SystemStatusRowProps> = ({ label, value, ok, icon }) => (
  <div
    style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '10px 14px',
      background: 'rgba(255,255,255,0.02)',
      borderRadius: 'var(--radius-md)',
      borderLeft: `3px solid ${ok ? 'var(--accent-green, #10b981)' : 'var(--accent-red, #ef4444)'}`,
    }}
  >
    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
      {icon ?? (ok ? (
        <CheckCircle size={15} style={{ color: 'var(--accent-green, #10b981)', flexShrink: 0 }} />
      ) : (
        <AlertTriangle size={15} style={{ color: 'var(--accent-red, #ef4444)', flexShrink: 0 }} />
      ))}
      <span style={{ fontWeight: 600, fontSize: '0.88rem' }}>{label}</span>
    </div>
    <span
      style={{
        fontFamily: 'var(--font-mono)',
        fontSize: '0.78rem',
        color: ok ? 'var(--accent-green, #10b981)' : 'var(--accent-red, #ef4444)',
        fontWeight: 600,
        textTransform: 'uppercase',
        letterSpacing: '0.04em',
      }}
    >
      {value}
    </span>
  </div>
);

interface ActionDistRowProps {
  action: string;
  count: number;
  total: number;
}

const ActionDistRow: React.FC<ActionDistRowProps> = ({ action, count, total }) => {
  const pct = total > 0 ? (count / total) * 100 : 0;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
          {action}
        </span>
        <span style={{ fontSize: '0.82rem', fontWeight: 600 }}>
          {count} <span style={{ color: 'var(--text-muted)', fontWeight: 400 }}>({pct.toFixed(1)}%)</span>
        </span>
      </div>
      <div style={{ height: '4px', background: 'rgba(255,255,255,0.07)', borderRadius: '2px', overflow: 'hidden' }}>
        <div
          style={{
            height: '100%',
            width: `${pct}%`,
            background: 'linear-gradient(90deg, var(--accent-purple, #8b5cf6), var(--accent-blue, #3b82f6))',
            borderRadius: '2px',
            transition: 'width 0.6s ease',
          }}
        />
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// Skeleton placeholder — shown only on first load (no data yet)
// ---------------------------------------------------------------------------

const SkeletonMetricCard: React.FC = () => (
  <div className="card metric-card" style={{ animationName: 'pulse', animationDuration: '1.5s', animationIterationCount: 'infinite' }}>
    <div style={{ height: '12px', width: '60%', background: 'rgba(255,255,255,0.07)', borderRadius: '4px', marginBottom: '14px' }} />
    <div style={{ height: '28px', width: '45%', background: 'rgba(255,255,255,0.05)', borderRadius: '4px', marginBottom: '10px' }} />
    <div style={{ height: '10px', width: '75%', background: 'rgba(255,255,255,0.04)', borderRadius: '4px' }} />
  </div>
);

// ---------------------------------------------------------------------------
// Main view
// ---------------------------------------------------------------------------

export const OperationsView: React.FC = () => {
  const { data, loading, initializing, error, lastFetchedAt, refresh } =
    useOperationsSummary(30_000);

  const { summary, health, ready } = data;
  const dm = summary?.decision_metrics ?? null;
  const em = summary?.economic_metrics ?? null;

  // System status flags
  const apiOk = health?.status === 'ok';
  const dbOk = ready?.database === 'connected';
  const aiProvider = ready?.ai_provider ?? 'unknown';

  // Total actions for distribution bar
  const totalFinalActions = dm
    ? Object.values(dm.final_action_distribution).reduce((s, v) => s + v, 0)
    : 0;

  // Sort distribution entries by count descending
  const actionDist = dm
    ? Object.entries(dm.final_action_distribution).sort(([, a], [, b]) => b - a)
    : [];

  // ---------------------------------------------------------------------------
  // Render helpers for loading / error states
  // ---------------------------------------------------------------------------

  const ErrorBanner: React.FC<{ message: string }> = ({ message }) => (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '10px',
        padding: '12px 16px',
        marginBottom: '20px',
        background: 'rgba(239, 68, 68, 0.1)',
        border: '1px solid rgba(239, 68, 68, 0.3)',
        borderRadius: 'var(--radius-md)',
        color: '#fca5a5',
        fontSize: '0.85rem',
      }}
    >
      <AlertTriangle size={16} style={{ flexShrink: 0, color: '#ef4444' }} />
      <span>
        <strong>Backend unreachable</strong> — {message}. Displaying last known values where available.
      </span>
    </div>
  );

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div>
      {/* ── Header bar with refresh control and last-updated timestamp ── */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: '20px',
          flexWrap: 'wrap',
          gap: '10px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <Circle
            size={10}
            fill={error ? '#ef4444' : loading ? '#f59e0b' : '#10b981'}
            color={error ? '#ef4444' : loading ? '#f59e0b' : '#10b981'}
            style={{ flexShrink: 0 }}
          />
          <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            {error
              ? 'Connection error'
              : loading
              ? 'Refreshing…'
              : lastFetchedAt
              ? `Live · updated at ${formatTimestamp(lastFetchedAt)}`
              : 'Connecting…'}
          </span>
        </div>
        <button
          className="btn btn-secondary"
          onClick={refresh}
          disabled={loading}
          style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
          id="ops-refresh-btn"
        >
          <RefreshCw size={13} style={{ animation: loading ? 'spin 1s linear infinite' : undefined }} />
          Refresh
        </button>
      </div>

      {/* ── Error banner (non-blocking) ── */}
      {error && !initializing && <ErrorBanner message={error} />}

      {/* ── KPI Metric cards ── */}
      <div className="metrics-grid">
        {initializing ? (
          <>
            <SkeletonMetricCard />
            <SkeletonMetricCard />
            <SkeletonMetricCard />
            <SkeletonMetricCard />
          </>
        ) : (
          <>
            <MetricCard
              label="Total Decisions"
              value={dm?.total_decisions ?? '—'}
              subtitle="AI decisions recorded"
              icon={<Zap size={18} style={{ color: '#3b82f6' }} />}
            />
            <MetricCard
              label="Execution Success"
              value={dm?.execution_success_count ?? '—'}
              trend={
                dm
                  ? {
                      value: `${dm.execution_success_count} / ${dm.actions_completed + dm.actions_failed || 1}`,
                      isPositive: dm.execution_failure_count === 0,
                      isNeutral: dm.execution_failure_count > 0,
                    }
                  : undefined
              }
              subtitle="Actions completed successfully"
              icon={<ShieldCheck size={18} style={{ color: '#10b981' }} />}
            />
            <MetricCard
              label="Pending Human Review"
              value={dm?.human_review_required_count ?? '—'}
              trend={
                dm
                  ? {
                      value: dm.human_review_required_count > 0 ? 'Needs attention' : 'All clear',
                      isPositive: dm.human_review_required_count === 0,
                      isNeutral: dm.human_review_required_count > 0,
                    }
                  : undefined
              }
              subtitle="Decisions requiring review"
              icon={<AlertTriangle size={18} style={{ color: '#f59e0b' }} />}
            />
            <MetricCard
              label="Projected Net Incremental Revenue"
              value={em?.expected_net_incremental_revenue_minor ?? 0}
              isCurrencyPaise={true}
              trend={{
                value: em ? formatPct(em.positive_value_decision_rate) + ' positive-value decisions' : '—',
                isPositive: (em?.positive_value_decision_rate ?? 0) > 0.7,
                isNeutral: (em?.positive_value_decision_rate ?? 0) <= 0.7,
              }}
              subtitle="EconomicEngine model projection"
              icon={<TrendingUp size={18} style={{ color: '#8b5cf6' }} />}
            />
          </>
        )}
      </div>

      {/* ── Main 2-col grid ── */}
      <div className="grid-2">
        {/* ── Action lifecycle & outbox panel ── */}
        <Card
          title="Action Control Plane"
          subtitle="Recovery action lifecycle counts — from RecoveryActionORM"
        >
          {initializing ? (
            <div style={{ padding: '20px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
              Loading…
            </div>
          ) : dm ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', padding: '4px 0' }}>
              {/* Lifecycle breakdown */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
                {(
                  [
                    ['PROPOSED', dm.actions_proposed, '#64748b'],
                    ['APPROVED', dm.actions_approved, '#3b82f6'],
                    ['EXECUTING', dm.actions_executing, '#f59e0b'],
                    ['COMPLETED', dm.actions_completed, '#10b981'],
                    ['FAILED', dm.actions_failed, '#ef4444'],
                    ['CANCELLED', dm.actions_cancelled, '#6b7280'],
                    ['EXPIRED', dm.actions_expired, '#6b7280'],
                    ['SUPERSEDED', dm.actions_superseded, '#6b7280'],
                  ] as [string, number, string][]
                ).map(([label, count, color]) => (
                  <div
                    key={label}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '8px 12px',
                      background: 'rgba(255,255,255,0.02)',
                      borderRadius: 'var(--radius-sm, 6px)',
                      borderLeft: `3px solid ${color}`,
                    }}
                  >
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.72rem', color: 'var(--text-secondary)' }}>
                      {label}
                    </span>
                    <span style={{ fontWeight: 700, fontSize: '1rem', color }}>{count}</span>
                  </div>
                ))}
              </div>

              {/* Outbox health */}
              <div
                style={{
                  marginTop: '6px',
                  padding: '12px',
                  background: 'rgba(255,255,255,0.02)',
                  borderRadius: 'var(--radius-md)',
                }}
              >
                <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginBottom: '8px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Outbox Pipeline
                </p>
                <div style={{ display: 'flex', gap: '16px', flexWrap: 'wrap' }}>
                  {[
                    { label: 'Pending', val: dm.pending_outbox_count, color: '#f59e0b' },
                    { label: 'Processing', val: dm.outbox_processing_count, color: '#3b82f6' },
                    { label: 'Failed', val: dm.outbox_failed_count, color: '#ef4444' },
                    { label: 'Retries', val: dm.total_retries, color: '#8b5cf6' },
                  ].map(({ label, val, color }) => (
                    <div key={label} style={{ textAlign: 'center' }}>
                      <div style={{ fontSize: '1.15rem', fontWeight: 700, color }}>{val}</div>
                      <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '2px' }}>{label}</div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Fallback / policy stats */}
              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                <span
                  className={`badge ${dm.fallback_rate > 0.1 ? 'badge-approval' : 'badge-recovered'}`}
                  style={{ fontSize: '0.75rem' }}
                >
                  Fallback rate: {formatPct(dm.fallback_rate)}
                </span>
                <span
                  className={`badge ${dm.policy_rejection_rate > 0.05 ? 'badge-approval' : 'badge-recovered'}`}
                  style={{ fontSize: '0.75rem' }}
                >
                  Policy rejections: {formatPct(dm.policy_rejection_rate)}
                </span>
              </div>
            </div>
          ) : (
            <div style={{ padding: '20px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
              No data available
            </div>
          )}
        </Card>

        {/* ── Right column: system status + action distribution ── */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          {/* System Status */}
          <Card title="System Status" subtitle="Liveness and readiness from /health and /ready">
            {initializing ? (
              <div style={{ padding: '20px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                Probing…
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', paddingTop: '4px' }}>
                <SystemStatusRow
                  label="API Process"
                  value={health?.status ?? 'unknown'}
                  ok={apiOk}
                  icon={<Server size={15} style={{ color: apiOk ? 'var(--accent-green, #10b981)' : '#ef4444', flexShrink: 0 }} />}
                />
                <SystemStatusRow
                  label="Database"
                  value={ready?.database ?? 'unknown'}
                  ok={dbOk}
                />
                <SystemStatusRow
                  label="AI Provider"
                  value={aiProvider}
                  ok={aiProvider !== 'unknown'}
                />
                <SystemStatusRow
                  label="Environment"
                  value={health?.environment ?? ready?.environment ?? 'unknown'}
                  ok
                />
              </div>
            )}
          </Card>

          {/* Action distribution */}
          <Card
            title="Final Action Distribution"
            subtitle="How the control plane resolved each recovery decision"
          >
            {initializing ? (
              <div style={{ padding: '20px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                Loading…
              </div>
            ) : actionDist.length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', paddingTop: '4px' }}>
                {actionDist.map(([action, count]) => (
                  <ActionDistRow
                    key={action}
                    action={action}
                    count={count}
                    total={totalFinalActions}
                  />
                ))}
              </div>
            ) : (
              <div style={{ padding: '20px', textAlign: 'center', color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                No decisions recorded yet
              </div>
            )}
          </Card>
        </div>
      </div>

      {/* ── Economic summary row ── */}
      {!initializing && em && (
        <Card
          title="Economic Metrics — EconomicEngine Projections"
          subtitle="All values are deterministic model projections in integer paise (÷100 for INR). Monetary values are NOT real settlements."
        >
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: '16px', paddingTop: '8px' }}>
            {[
              {
                label: 'Projected Gross Recovery',
                value: formatINR(em.expected_gross_recovery_minor),
                description: 'EconomicEngine: expected gross recovery',
                color: '#3b82f6',
              },
              {
                label: 'Natural Baseline',
                value: formatINR(em.expected_natural_recovery_minor),
                description: 'Expected recovery without intervention',
                color: '#64748b',
              },
              {
                label: 'Projected Incremental',
                value: formatINR(em.expected_incremental_recovery_minor),
                description: 'Incremental above natural baseline',
                color: '#10b981',
              },
              {
                label: 'Intervention Cost',
                value: formatINR(em.intervention_cost_minor),
                description: 'Discount / retry costs',
                color: '#f59e0b',
              },
              {
                label: 'Projected Net',
                value: formatINR(em.expected_net_incremental_revenue_minor),
                description: 'After intervention + inference costs',
                color: '#8b5cf6',
              },
              {
                label: 'Observed Captured Revenue',
                value: formatINR(em.realized_captured_revenue_minor),
                description:
                  'Observed: sum of CAPTURED payments with recovery cases. Not causally attributed incremental revenue — no holdout.',
                color: '#94a3b8',
                warning: true,
              },
            ].map(({ label, value, description, color, warning }) => (
              <div
                key={label}
                style={{
                  padding: '14px 16px',
                  background: 'rgba(255,255,255,0.02)',
                  borderRadius: 'var(--radius-md)',
                  borderTop: `3px solid ${color}`,
                }}
              >
                <p style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '6px' }}>
                  {label}
                </p>
                <p style={{ fontFamily: 'var(--font-mono)', fontSize: '1.1rem', fontWeight: 700, color }}>
                  {value}
                </p>
                <p
                  style={{
                    fontSize: '0.7rem',
                    marginTop: '6px',
                    color: warning ? '#94a3b8' : 'var(--text-muted)',
                    fontStyle: warning ? 'italic' : 'normal',
                    lineHeight: 1.4,
                  }}
                >
                  {description}
                </p>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* ── Recovery state machine lifecycle (always shown — static, architectural) ── */}
      <Card
        title="Recovery State Machine Lifecycle"
        subtitle="Deterministic transition boundaries enforced by domain logic"
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', padding: '10px 0' }}>
          {[
            {
              step: '1. Durable Ingestion',
              detail: 'Razorpay Webhook → Inbox Verification',
            },
            {
              step: '2. AI & Economic Decisioning',
              detail: 'AI Context → Policy Gate → Economic Engine',
            },
            {
              step: '3. Outbox-Exclusive Dispatch',
              detail: 'Control Plane → Outbox Worker → Execution',
            },
          ].map(({ step, detail }) => (
            <div
              key={step}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '12px',
                background: 'rgba(255, 255, 255, 0.02)',
                borderRadius: 'var(--radius-md)',
              }}
            >
              <div>
                <span style={{ fontWeight: 600, fontSize: '0.9rem' }}>{step}</span>
                <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>{detail}</p>
              </div>
              <ArrowRight size={16} style={{ color: 'var(--text-muted)' }} />
            </div>
          ))}
        </div>
      </Card>

      {/* ── Latency telemetry footer ── */}
      {!initializing && dm && dm.total_decisions > 0 && (
        <Card title="AI Decision Latency" subtitle="Milliseconds · derived from AIDecisionRecordORM">
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))',
              gap: '12px',
              paddingTop: '8px',
            }}
          >
            {[
              { label: 'Avg', val: `${dm.avg_latency_ms.toFixed(1)} ms` },
              { label: 'P50', val: `${dm.p50_latency_ms.toFixed(1)} ms` },
              { label: 'P95', val: `${dm.p95_latency_ms.toFixed(1)} ms` },
              { label: 'P99', val: `${dm.p99_latency_ms.toFixed(1)} ms` },
              { label: 'Avg Input Tokens', val: `${dm.avg_input_tokens.toFixed(0)}` },
              { label: 'Avg Output Tokens', val: `${dm.avg_output_tokens.toFixed(0)}` },
            ].map(({ label, val }) => (
              <div
                key={label}
                style={{
                  padding: '10px 14px',
                  background: 'rgba(255,255,255,0.02)',
                  borderRadius: 'var(--radius-md)',
                  textAlign: 'center',
                }}
              >
                <p style={{ fontFamily: 'var(--font-mono)', fontSize: '1rem', fontWeight: 700 }}>{val}</p>
                <p style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '4px' }}>{label}</p>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
};
