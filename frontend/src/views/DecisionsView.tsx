/**
 * frontend/src/views/DecisionsView.tsx
 *
 * Decisions Control Room — live data from:
 *   GET /api/observability/recovery/14ec8d3a-51cd-4107-8624-8b3b07bd49d8
 *
 * Displays Decision → Policy → Economics → Dispatch from a real persisted
 * PostgreSQL record. No hardcoded mock values.
 */

import React from 'react';
import {
  BrainCircuit,
  CheckCircle2,
  XCircle,
  DollarSign,
  RefreshCw,
  AlertCircle,
  Loader2,
  Database,
  TrendingUp,
  ShieldCheck,
  ShieldX,
  Cpu,
} from 'lucide-react';
import { Card } from '../components/common/Card';
import { MetricCard } from '../components/common/MetricCard';
import { StatusBadge } from '../components/common/StatusBadge';
import { useRecoveryAudit } from '../hooks/useRecoveryAudit';

// ─── Constants ───────────────────────────────────────────────────────────────

/** The demo recovery case that already exists in production PostgreSQL. */
const DEMO_CASE_ID = '14ec8d3a-51cd-4107-8624-8b3b07bd49d8';

// ─── Helpers ─────────────────────────────────────────────────────────────────

const formatPaise = (paise: number | null | undefined): string => {
  if (paise == null) return '—';
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 2,
  }).format(paise / 100);
};

const formatPct = (rate: number | null | undefined): string => {
  if (rate == null) return '—';
  return `${Math.round(rate * 100)}%`;
};

const formatTimestamp = (iso: string | null | undefined): string => {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('en-IN', {
    dateStyle: 'medium',
    timeStyle: 'medium',
    timeZone: 'Asia/Kolkata',
  });
};

const truncateId = (id: string | null | undefined, len = 12): string => {
  if (!id) return '—';
  return id.slice(0, len) + '…';
};

// ─── Sub-components ───────────────────────────────────────────────────────────

const InfoRow: React.FC<{ label: string; value: React.ReactNode; mono?: boolean }> = ({
  label,
  value,
  mono = false,
}) => (
  <div
    style={{
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'baseline',
      padding: '7px 0',
      borderBottom: '1px solid var(--border-subtle)',
      gap: '12px',
      flexWrap: 'wrap',
    }}
  >
    <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)', flexShrink: 0 }}>{label}</span>
    <span
      style={{
        fontSize: '0.82rem',
        color: 'var(--text-primary)',
        fontFamily: mono ? 'var(--font-mono)' : undefined,
        fontWeight: 500,
        textAlign: 'right',
      }}
    >
      {value}
    </span>
  </div>
);

const LiveBadge: React.FC = () => (
  <span
    style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: '5px',
      padding: '3px 10px',
      borderRadius: 'var(--radius-full)',
      fontSize: '0.7rem',
      fontWeight: 600,
      letterSpacing: '0.04em',
      textTransform: 'uppercase',
      background: 'rgba(16, 185, 129, 0.12)',
      border: '1px solid rgba(16, 185, 129, 0.35)',
      color: '#10b981',
    }}
  >
    <Database size={10} />
    Live backend record
  </span>
);

// ─── Main view ────────────────────────────────────────────────────────────────

export const DecisionsView: React.FC = () => {
  const { data, loading, initializing, error, lastFetchedAt, refresh } =
    useRecoveryAudit(DEMO_CASE_ID);

  // ── Loading skeleton (first fetch only) ──
  if (initializing) {
    return (
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: '16px',
          minHeight: '280px',
          color: 'var(--text-secondary)',
        }}
      >
        <Loader2
          size={32}
          style={{ color: 'var(--accent-purple)', animation: 'spin 1s linear infinite' }}
        />
        <span style={{ fontSize: '0.9rem' }}>Loading decision audit…</span>
      </div>
    );
  }

  // ── Error banner (shown below any stale data) ──
  const errorBanner = error ? (
    <div
      role="alert"
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: '12px',
        padding: '14px 18px',
        borderRadius: 'var(--radius-md)',
        background: 'rgba(244, 63, 94, 0.08)',
        border: '1px solid rgba(244, 63, 94, 0.3)',
        color: '#f43f5e',
        fontSize: '0.84rem',
        marginBottom: '20px',
      }}
    >
      <AlertCircle size={18} style={{ flexShrink: 0, marginTop: '1px' }} />
      <div style={{ flex: 1 }}>
        <strong>Backend unreachable.</strong>&nbsp;{error}
        <br />
        <span style={{ color: 'var(--text-muted)', fontSize: '0.78rem' }}>
          Make sure the FastAPI server is running on{' '}
          <code style={{ fontFamily: 'var(--font-mono)' }}>localhost:8000</code>.
        </span>
      </div>
      <button
        onClick={refresh}
        style={{
          background: 'none',
          border: 'none',
          color: '#f43f5e',
          cursor: 'pointer',
          padding: '2px',
          flexShrink: 0,
        }}
        title="Retry"
      >
        <RefreshCw size={16} />
      </button>
    </div>
  ) : null;

  // If we have no data at all (first fetch failed), render the error full-page
  if (!data) {
    return (
      <div style={{ padding: '8px 0' }}>
        {errorBanner}
      </div>
    );
  }

  const econ = data.economic_evaluation;
  const ctx = data.observable_context;

  // ── Derived metric card values ──
  const confidencePct = Math.round(data.confidence * 100);

  const refreshButton = (
    <button
      onClick={refresh}
      disabled={loading}
      title="Refresh decision record"
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: '5px',
        padding: '5px 12px',
        borderRadius: 'var(--radius-sm)',
        background: 'rgba(139, 92, 246, 0.1)',
        border: '1px solid rgba(139, 92, 246, 0.25)',
        color: 'var(--accent-purple)',
        fontSize: '0.76rem',
        fontWeight: 600,
        cursor: loading ? 'not-allowed' : 'pointer',
        opacity: loading ? 0.6 : 1,
        transition: 'opacity 0.15s',
      }}
    >
      <RefreshCw
        size={12}
        style={{ animation: loading ? 'spin 1s linear infinite' : undefined }}
      />
      {loading ? 'Refreshing…' : 'Refresh'}
    </button>
  );

  return (
    <div>
      {errorBanner}

      {/* ── Header meta row ── */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '10px',
          marginBottom: '20px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
          <LiveBadge />
          <span style={{ fontSize: '0.76rem', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
            case: {truncateId(data.recovery_case_id, 8)}
          </span>
          {lastFetchedAt && (
            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
              · fetched {formatTimestamp(lastFetchedAt)}
            </span>
          )}
        </div>
        {refreshButton}
      </div>

      {/* ── KPI metric cards ── */}
      <div className="metrics-grid">
        <MetricCard
          label="AI Confidence"
          value={`${confidencePct}%`}
          trend={{
            value: data.uncertainty === 'LOW' ? 'Low uncertainty' : data.uncertainty,
            isPositive: data.uncertainty === 'LOW',
            isNeutral: data.uncertainty === 'MEDIUM',
          }}
          subtitle={`Proposed: ${data.proposed_action}`}
          icon={<BrainCircuit size={18} style={{ color: '#8b5cf6' }} />}
        />
        <MetricCard
          label="Policy Gate"
          value={data.policy_approved ? 'Approved' : 'Rejected'}
          trend={{
            value: data.policy_approved ? 'Compliant' : 'Blocked',
            isPositive: data.policy_approved,
          }}
          subtitle={
            data.requires_human_review ? 'Human review required' : 'No review required'
          }
          icon={
            data.policy_approved ? (
              <CheckCircle2 size={18} style={{ color: '#10b981' }} />
            ) : (
              <XCircle size={18} style={{ color: '#f43f5e' }} />
            )
          }
        />
        <MetricCard
          label="Fallback Used"
          value={data.fallback_used ? 'Yes' : 'No'}
          trend={{
            value: data.fallback_used ? 'Deterministic' : 'AI decision',
            isPositive: !data.fallback_used,
            isNeutral: false,
          }}
          subtitle={data.fallback_reason ?? 'AI agent produced a valid proposal'}
          icon={<XCircle size={18} style={{ color: data.fallback_used ? '#f59e0b' : '#10b981' }} />}
        />
        <MetricCard
          label="Expected Net Revenue"
          value={econ?.expected_net_incremental_revenue_minor ?? 0}
          isCurrencyPaise
          subtitle="EconomicEngine projection above baseline"
          icon={<DollarSign size={18} style={{ color: '#06b6d4' }} />}
        />
      </div>

      {/* ── Two-column detail cards ── */}
      <div className="grid-2">

        {/* ── Decision & Policy card ── */}
        <Card
          title="AI Decision & Policy Audit"
          subtitle="Live structured decision output from AIAssistedRecoveryAgent"
        >
          {/* Proposal highlight box */}
          <div
            style={{
              padding: '14px',
              background: data.policy_approved
                ? 'rgba(16, 185, 129, 0.05)'
                : 'rgba(244, 63, 94, 0.05)',
              border: `1px solid ${data.policy_approved ? 'rgba(16, 185, 129, 0.2)' : 'rgba(244, 63, 94, 0.2)'}`,
              borderRadius: 'var(--radius-md)',
              marginBottom: '14px',
            }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: '10px',
                flexWrap: 'wrap',
                gap: '8px',
              }}
            >
              <span style={{ fontWeight: 700, color: 'var(--text-primary)', fontSize: '0.95rem' }}>
                {data.proposed_action}
              </span>
              <StatusBadge
                status={data.policy_approved ? 'POLICY_COMPLIANT' : 'POLICY_REJECTED'}
              />
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginBottom: '10px' }}>
              {data.reasoning_codes.map((code) => (
                <span
                  key={code}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    padding: '2px 8px',
                    borderRadius: 'var(--radius-full)',
                    fontSize: '0.7rem',
                    fontWeight: 600,
                    background: 'rgba(139, 92, 246, 0.12)',
                    border: '1px solid rgba(139, 92, 246, 0.25)',
                    color: 'var(--accent-purple)',
                    fontFamily: 'var(--font-mono)',
                  }}
                >
                  {code}
                </span>
              ))}
            </div>
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: '1fr 1fr',
                gap: '8px',
                fontSize: '0.78rem',
                color: 'var(--text-muted)',
              }}
            >
              <div>
                Confidence:{' '}
                <strong style={{ color: 'var(--text-primary)' }}>{confidencePct}%</strong>
              </div>
              <div>
                Uncertainty:{' '}
                <strong
                  style={{
                    color:
                      data.uncertainty === 'LOW'
                        ? 'var(--accent-emerald)'
                        : data.uncertainty === 'HIGH'
                        ? '#f43f5e'
                        : 'var(--accent-amber)',
                  }}
                >
                  {data.uncertainty}
                </strong>
              </div>
              <div>
                Final action:{' '}
                <strong style={{ color: 'var(--accent-emerald)' }}>{data.final_action}</strong>
              </div>
              <div>
                Human review:{' '}
                <strong
                  style={{
                    color: data.requires_human_review ? '#f43f5e' : 'var(--text-secondary)',
                  }}
                >
                  {data.requires_human_review ? 'Required' : 'Not required'}
                </strong>
              </div>
            </div>
          </div>

          {/* Policy gate detail rows */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              marginBottom: '10px',
              color: 'var(--text-secondary)',
              fontSize: '0.78rem',
              fontWeight: 600,
            }}
          >
            {data.policy_approved ? (
              <ShieldCheck size={14} style={{ color: '#10b981' }} />
            ) : (
              <ShieldX size={14} style={{ color: '#f43f5e' }} />
            )}
            Policy Gate
          </div>
          <InfoRow label="Policy approved" value={data.policy_approved ? '✓ Yes' : '✗ No'} />
          <InfoRow
            label="Requires human review"
            value={data.requires_human_review ? '⚠ Yes' : 'No'}
          />
          <InfoRow
            label="Fallback triggered"
            value={data.fallback_used ? `Yes — ${data.fallback_reason ?? 'unknown'}` : 'No'}
          />
          <InfoRow label="Discount offered" value={`${data.discount_percent_offered}%`} />

          {/* Payment context */}
          {ctx && (
            <>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  marginTop: '14px',
                  marginBottom: '10px',
                  color: 'var(--text-secondary)',
                  fontSize: '0.78rem',
                  fontWeight: 600,
                }}
              >
                <Cpu size={14} style={{ color: 'var(--accent-blue)' }} />
                Payment Context (at decision time)
              </div>
              <InfoRow label="Amount" value={formatPaise(ctx.amount_minor)} />
              <InfoRow label="Method" value={ctx.payment_method} />
              <InfoRow label="Failure code" value={ctx.failure_code} mono />
              <InfoRow label="Attempt #" value={ctx.attempt_count} />
              <InfoRow label="Customer segment" value={ctx.customer_segment} />
              <InfoRow
                label="Historical success rate"
                value={formatPct(ctx.customer_historical_success_rate)}
              />
              <InfoRow
                label="Business hours"
                value={ctx.is_business_hours ? 'Yes' : 'No'}
              />
            </>
          )}
        </Card>

        {/* ── Economics & Dispatch card ── */}
        <Card
          title="Economic Evaluation & Dispatch"
          subtitle="EconomicEngine projection · Execution status from RecoveryOutbox"
        >
          {econ ? (
            <>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  marginBottom: '10px',
                  color: 'var(--text-secondary)',
                  fontSize: '0.78rem',
                  fontWeight: 600,
                }}
              >
                <TrendingUp size={14} style={{ color: 'var(--accent-cyan)' }} />
                EconomicEngine Projection (integer paise → INR)
              </div>

              {/* Economics summary table */}
              <div className="data-table-container">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Metric</th>
                      <th style={{ textAlign: 'right' }}>INR</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr>
                      <td>Expected gross recovery</td>
                      <td style={{ textAlign: 'right' }}>
                        {formatPaise(econ.expected_gross_revenue_minor)}
                      </td>
                    </tr>
                    <tr>
                      <td>Natural recovery baseline</td>
                      <td style={{ textAlign: 'right' }}>
                        {formatPaise(econ.expected_natural_revenue_minor)}
                      </td>
                    </tr>
                    <tr>
                      <td>Incremental (gross − natural)</td>
                      <td style={{ textAlign: 'right' }}>
                        {formatPaise(econ.expected_incremental_revenue_minor)}
                      </td>
                    </tr>
                    <tr>
                      <td>Intervention cost</td>
                      <td style={{ textAlign: 'right', color: '#f59e0b' }}>
                        − {formatPaise(econ.intervention_cost_minor)}
                      </td>
                    </tr>
                    <tr>
                      <td>AI inference cost</td>
                      <td style={{ textAlign: 'right', color: '#f59e0b' }}>
                        − {formatPaise(econ.estimated_llm_cost_minor)}
                      </td>
                    </tr>
                    <tr
                      style={{
                        background: 'rgba(16, 185, 129, 0.07)',
                        borderTop: '1px solid rgba(16, 185, 129, 0.2)',
                      }}
                    >
                      <td>
                        <strong style={{ color: 'var(--accent-emerald)' }}>
                          Expected net incremental revenue
                        </strong>
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        <strong style={{ color: 'var(--accent-emerald)' }}>
                          {formatPaise(econ.expected_net_incremental_revenue_minor)}
                        </strong>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            <p style={{ color: 'var(--text-muted)', fontSize: '0.82rem', marginBottom: '14px' }}>
              Economic evaluation not available for this record.
            </p>
          )}

          {/* Dispatch / Execution */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              marginTop: '18px',
              marginBottom: '10px',
              color: 'var(--text-secondary)',
              fontSize: '0.78rem',
              fontWeight: 600,
            }}
          >
            <CheckCircle2 size={14} style={{ color: 'var(--accent-emerald)' }} />
            Dispatch & Execution
          </div>
          <InfoRow
            label="Execution status"
            value={
              data.execution_status ? (
                <StatusBadge status={data.execution_status} />
              ) : (
                '—'
              )
            }
          />
          <InfoRow
            label="Execution reference"
            value={data.execution_reference ?? '—'}
            mono
          />
          <InfoRow
            label="Recovery action ID"
            value={truncateId(data.recovery_action_id)}
            mono
          />
          <InfoRow label="Payment status" value={data.payment_status ?? '—'} />
          {data.execution_details && (
            <InfoRow
              label="Retry delay"
              value={
                (data.execution_details as Record<string, unknown>).retry_delay_seconds != null
                  ? `${(data.execution_details as Record<string, unknown>).retry_delay_seconds}s`
                  : '—'
              }
            />
          )}

          {/* AI Provenance */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              marginTop: '18px',
              marginBottom: '10px',
              color: 'var(--text-secondary)',
              fontSize: '0.78rem',
              fontWeight: 600,
            }}
          >
            <BrainCircuit size={14} style={{ color: 'var(--accent-purple)' }} />
            AI Provenance
          </div>
          <InfoRow label="Provider" value={data.provider} />
          <InfoRow label="Model" value={data.model} mono />
          <InfoRow label="Prompt version" value={data.prompt_version} mono />
          <InfoRow label="Schema version" value={data.audit_schema_version} />
          <InfoRow label="Latency" value={data.latency_ms != null ? `${data.latency_ms} ms` : '—'} />
          <InfoRow
            label="Tokens (in / out)"
            value={
              data.input_tokens != null
                ? `${data.input_tokens} / ${data.output_tokens}`
                : '—'
            }
          />
          <InfoRow
            label="Decision timestamp"
            value={formatTimestamp(data.created_at)}
          />
          <InfoRow
            label="Decision ID"
            value={truncateId(data.decision_id)}
            mono
          />
        </Card>
      </div>
    </div>
  );
};
