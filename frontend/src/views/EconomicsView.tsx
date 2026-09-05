/**
 * frontend/src/views/EconomicsView.tsx
 *
 * Economics Control Room — live telemetry from:
 *   GET /api/observability/summary
 *
 * Displays causal economic valuation, net incremental revenue accounting,
 * and cost breakdown computed directly from authoritative PostgreSQL records.
 */

import React from 'react';
import {
  TrendingUp,
  Award,
  DollarSign,
  Wallet,
  RefreshCw,
  Database,
  AlertCircle,
  Loader2,
  PieChart,
} from 'lucide-react';
import { Card } from '../components/common/Card';
import { MetricCard } from '../components/common/MetricCard';
import { useOperationsSummary } from '../hooks/useOperationsSummary';

const formatPaise = (paise: number | null | undefined): string => {
  if (paise == null) return '—';
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 2,
  }).format(paise / 100);
};

const ACTION_UNIT_COSTS_PAISE: Record<string, number> = {
  WAIT: 0,
  RETRY: 20,         // ₹0.20
  PAYMENT_LINK: 50,  // ₹0.50
  NOTIFY: 15,        // ₹0.15
  ESCALATE: 500,     // ₹5.00
};

export const EconomicsView: React.FC = () => {
  const { data, loading, initializing, error, lastFetchedAt, refresh } =
    useOperationsSummary();

  const econ = data.summary?.economic_metrics;
  const dec = data.summary?.decision_metrics;

  const totalDecisions = dec?.total_decisions || 0;
  const actionDist = dec?.final_action_distribution || {};

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* ── Live Economics Header ────────────────────────────────────────── */}
      <div
        style={{
          padding: '16px 20px',
          background: 'rgba(16, 185, 129, 0.06)',
          border: '1px solid rgba(16, 185, 129, 0.25)',
          borderRadius: 'var(--radius-lg)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '14px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
          <TrendingUp size={28} style={{ color: 'var(--accent-emerald)', flexShrink: 0 }} />
          <div>
            <h4 style={{ color: 'var(--text-primary)', fontWeight: 600, fontSize: '1rem', marginBottom: '2px' }}>
              Causal Economic Optimization Telemetry
            </h4>
            <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
              Deterministic revenue accounting subtracting counterfactual natural recovery, gateway intervention costs, and AI token expense.
            </p>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '4px 10px',
              borderRadius: '999px',
              fontSize: '0.75rem',
              fontWeight: 600,
              background: 'rgba(16, 185, 129, 0.15)',
              color: '#34d399',
              border: '1px solid rgba(16, 185, 129, 0.3)',
            }}
          >
            <Database size={12} /> Test-Mode System Telemetry
          </span>
          <button
            onClick={() => refresh()}
            disabled={loading}
            className="btn btn-secondary"
            style={{ padding: '6px 12px', fontSize: '0.8rem', display: 'flex', alignItems: 'center', gap: '6px' }}
            title="Refresh metrics from server"
          >
            <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
            {loading ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      </div>

      {/* ── Error Banner ─────────────────────────────────────────────────── */}
      {error && (
        <div
          style={{
            padding: '12px 16px',
            background: 'rgba(239, 68, 68, 0.1)',
            border: '1px solid rgba(239, 68, 68, 0.3)',
            borderRadius: 'var(--radius-md)',
            color: '#f87171',
            fontSize: '0.86rem',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <AlertCircle size={16} />
            <span>Failed to refresh economic telemetry: {error}</span>
          </div>
          <button onClick={() => refresh()} className="btn btn-secondary" style={{ padding: '4px 8px', fontSize: '0.75rem' }}>
            Retry
          </button>
        </div>
      )}

      {/* ── Top Metric Cards ──────────────────────────────────────────────── */}
      <div className="metrics-grid">
        <MetricCard
          label="Net Incremental Revenue"
          value={econ?.expected_net_incremental_revenue_minor ?? 0}
          isCurrencyPaise={true}
          trend={{ value: 'Projected Net Lift', isPositive: true }}
          subtitle="Model estimate above natural recovery"
          icon={<TrendingUp size={18} style={{ color: '#10b981' }} />}
        />
        <MetricCard
          label="Realized Captured Revenue"
          value={econ?.realized_captured_revenue_minor ?? 0}
          isCurrencyPaise={true}
          subtitle="Observed total recovered payment volume"
          icon={<Award size={18} style={{ color: '#3b82f6' }} />}
        />
        <MetricCard
          label="Intervention Costs"
          value={econ?.intervention_cost_minor ?? 0}
          isCurrencyPaise={true}
          subtitle="Gateway/SMS/Email execution cost"
          icon={<Wallet size={18} style={{ color: '#f59e0b' }} />}
        />
        <MetricCard
          label="AI Inference Cost"
          value={econ?.ai_inference_cost_minor ?? 0}
          isCurrencyPaise={true}
          subtitle="Total LLM token expense in paise"
          icon={<DollarSign size={18} style={{ color: '#8b5cf6' }} />}
        />
      </div>

      {/* ── Detailed Breakdown & Action Strategy Grid ──────────────────────── */}
      <div className="grid-2">
        <Card
          title="Net Incremental Revenue Formula Breakdown"
          subtitle="Causal accounting vs raw payment capture"
        >
          {initializing ? (
            <div style={{ padding: '32px', display: 'flex', justifyContent: 'center' }}>
              <Loader2 size={24} className="animate-spin" style={{ color: 'var(--accent-purple)' }} />
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', fontSize: '0.85rem' }}>
              <div
                style={{
                  padding: '12px 14px',
                  background: 'rgba(255, 255, 255, 0.02)',
                  borderRadius: 'var(--radius-md)',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}
              >
                <span style={{ color: 'var(--accent-emerald)', fontWeight: 600 }}>
                  + Expected Gross Recovery (with intervention):
                </span>
                <span className="font-mono" style={{ fontWeight: 600 }}>
                  {formatPaise(econ?.expected_gross_recovery_minor ?? 0)}
                </span>
              </div>

              <div
                style={{
                  padding: '12px 14px',
                  background: 'rgba(255, 255, 255, 0.02)',
                  borderRadius: 'var(--radius-md)',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}
              >
                <span style={{ color: '#f87171', fontWeight: 600 }}>
                  &minus; Counterfactual Natural Recovery (self-healing):
                </span>
                <span className="font-mono" style={{ fontWeight: 600, color: '#f87171' }}>
                  &minus; {formatPaise(econ?.expected_natural_recovery_minor ?? 0)}
                </span>
              </div>

              <div
                style={{
                  padding: '12px 14px',
                  background: 'rgba(255, 255, 255, 0.02)',
                  borderRadius: 'var(--radius-md)',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}
              >
                <span style={{ color: 'var(--accent-amber)', fontWeight: 600 }}>
                  &minus; Intervention Action Costs:
                </span>
                <span className="font-mono" style={{ fontWeight: 600, color: 'var(--accent-amber)' }}>
                  &minus; {formatPaise(econ?.intervention_cost_minor ?? 0)}
                </span>
              </div>

              <div
                style={{
                  padding: '12px 14px',
                  background: 'rgba(255, 255, 255, 0.02)',
                  borderRadius: 'var(--radius-md)',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}
              >
                <span style={{ color: 'var(--accent-purple)', fontWeight: 600 }}>
                  &minus; AI Inference Token Costs:
                </span>
                <span className="font-mono" style={{ fontWeight: 600, color: 'var(--accent-purple)' }}>
                  &minus; {formatPaise(econ?.ai_inference_cost_minor ?? 0)}
                </span>
              </div>

              <hr style={{ borderColor: 'var(--border-subtle)', margin: '4px 0' }} />

              <div
                style={{
                  padding: '14px 16px',
                  background: 'rgba(16, 185, 129, 0.1)',
                  border: '1px solid rgba(16, 185, 129, 0.3)',
                  borderRadius: 'var(--radius-md)',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}
              >
                <span style={{ fontWeight: 700, fontSize: '0.95rem', color: 'var(--accent-emerald)' }}>
                  = Expected Net Incremental Revenue:
                </span>
                <span className="font-mono" style={{ fontWeight: 700, fontSize: '1.1rem', color: 'var(--accent-emerald)' }}>
                  {formatPaise(econ?.expected_net_incremental_revenue_minor ?? 0)}
                </span>
              </div>
            </div>
          )}
        </Card>

        <Card
          title="Action Distribution & Strategy Efficiency"
          subtitle={`Live breakdown across ${totalDecisions} decisions`}
        >
          {initializing ? (
            <div style={{ padding: '32px', display: 'flex', justifyContent: 'center' }}>
              <Loader2 size={24} className="animate-spin" style={{ color: 'var(--accent-purple)' }} />
            </div>
          ) : (
            <div className="data-table-container">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Strategy Action</th>
                    <th>Executions</th>
                    <th>Share</th>
                    <th>Unit Cost</th>
                    <th>Total Cost</th>
                  </tr>
                </thead>
                <tbody>
                  {['WAIT', 'RETRY', 'PAYMENT_LINK', 'NOTIFY', 'ESCALATE'].map((actType) => {
                    const count = actionDist[actType] || 0;
                    const sharePct = totalDecisions > 0 ? (count / totalDecisions) * 100 : 0;
                    const unitCostPaise = ACTION_UNIT_COSTS_PAISE[actType] ?? 0;
                    const totalCostPaise = count * unitCostPaise;

                    return (
                      <tr key={actType}>
                        <td>
                          <strong>{actType}</strong>
                          {actType === 'WAIT' && (
                            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', display: 'block' }}>
                              (Natural baseline)
                            </span>
                          )}
                        </td>
                        <td className="font-mono">{count}</td>
                        <td className="font-mono">{sharePct.toFixed(1)}%</td>
                        <td className="font-mono">{formatPaise(unitCostPaise)}</td>
                        <td className="font-mono">{formatPaise(totalCostPaise)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
};
