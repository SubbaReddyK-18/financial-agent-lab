/**
 * frontend/src/views/AuditView.tsx
 *
 * Audit Trace Control Room — live data from:
 *   GET /api/observability/recovery/{caseId}
 *   GET /api/observability/summary
 *
 * Inspects append-only financial events, AI decision audit records, and outbox logs.
 */

import React, { useState } from 'react';
import {
  FileText,
  Search,
  Lock,
  Layers,
  CheckCircle2,
  Database,
  RefreshCw,
  AlertCircle,
  Loader2,
  ShieldCheck,
} from 'lucide-react';
import { Card } from '../components/common/Card';
import { MetricCard } from '../components/common/MetricCard';
import { StatusBadge } from '../components/common/StatusBadge';
import { useRecoveryAudit } from '../hooks/useRecoveryAudit';
import { useOperationsSummary } from '../hooks/useOperationsSummary';

const DEFAULT_CASE_ID = '63f5c724-61b7-4679-91ae-d9862eca9deb';

const formatTimestamp = (iso: string | null | undefined): string => {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('en-IN', {
    dateStyle: 'medium',
    timeStyle: 'medium',
    timeZone: 'Asia/Kolkata',
  });
};

export const AuditView: React.FC = () => {
  const [searchInput, setSearchInput] = useState<string>(DEFAULT_CASE_ID);
  const [activeCaseId, setActiveCaseId] = useState<string>(DEFAULT_CASE_ID);

  const { data: auditData, loading, initializing, error, refresh } =
    useRecoveryAudit(activeCaseId);

  const { data: opsData } = useOperationsSummary();
  const summary = opsData.summary;

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchInput.trim()) {
      setActiveCaseId(searchInput.trim());
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* ── System Aggregate Telemetry Metrics ────────────────────────────── */}
      <div className="metrics-grid">
        <MetricCard
          label="AI Decision Audit Records"
          value={summary?.decision_metrics.total_decisions ?? 0}
          subtitle="Total persistent evaluation audits"
          icon={<FileText size={18} style={{ color: '#8b5cf6' }} />}
        />
        <MetricCard
          label="Completed Actions"
          value={summary?.decision_metrics.actions_completed ?? 0}
          subtitle="Successfully executed interventions"
          icon={<CheckCircle2 size={18} style={{ color: '#10b981' }} />}
        />
        <MetricCard
          label="Approved Actions"
          value={summary?.decision_metrics.actions_approved ?? 0}
          subtitle="Cleared governance policy gate"
          icon={<ShieldCheck size={18} style={{ color: '#3b82f6' }} />}
        />
        <MetricCard
          label="Evaluation Model Provenance"
          value={auditData?.model ?? 'gemini-2.5-flash'}
          subtitle={auditData?.prompt_version ? `Prompt: ${auditData.prompt_version} • Schema v${auditData.audit_schema_version || '1'}` : 'Durable evaluation provenance'}
          icon={<Layers size={18} style={{ color: '#06b6d4' }} />}
        />
      </div>

      {/* ── Case Audit Trail Inspector ────────────────────────────────────── */}
      <Card
        title="Decision & Event Audit Trail Inspector"
        subtitle="Durable auditability trace from GET /observability/recovery/{case_id}"
        action={
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                padding: '4px 10px',
                borderRadius: '999px',
                fontSize: '0.75rem',
                fontWeight: 600,
                background: 'rgba(59, 130, 246, 0.15)',
                color: '#60a5fa',
                border: '1px solid rgba(59, 130, 246, 0.3)',
              }}
            >
              <Database size={12} /> Live PostgreSQL Case Audit
            </span>
            <button
              onClick={() => refresh()}
              disabled={loading}
              className="btn btn-secondary"
              style={{ padding: '6px 12px', fontSize: '0.8rem', display: 'flex', alignItems: 'center', gap: '6px' }}
              title="Refresh audit trail"
            >
              <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
              {loading ? 'Refreshing…' : 'Refresh'}
            </button>
          </div>
        }
      >
        <form onSubmit={handleSearch} style={{ display: 'flex', gap: '12px', marginBottom: '20px' }}>
          <input
            type="text"
            placeholder="Search by Recovery Case ID..."
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            style={{
              flex: 1,
              padding: '10px 14px',
              background: 'var(--bg-surface)',
              border: '1px solid var(--border-subtle)',
              borderRadius: 'var(--radius-md)',
              color: 'var(--text-primary)',
              fontFamily: 'var(--font-mono)',
              fontSize: '0.84rem',
            }}
          />
          <button type="submit" className="btn btn-secondary" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Search size={14} /> Inspect Case Audit
          </button>
        </form>

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
              gap: '8px',
              marginBottom: '16px',
            }}
          >
            <AlertCircle size={16} />
            <span>Failed to load audit record for case {activeCaseId}: {error}</span>
          </div>
        )}

        {initializing ? (
          <div style={{ padding: '40px', display: 'flex', justifyContent: 'center' }}>
            <Loader2 size={28} className="animate-spin" style={{ color: 'var(--accent-purple)' }} />
          </div>
        ) : (
          <div className="data-table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Timestamp</th>
                  <th>Audit Record / Lifecycle Step</th>
                  <th>Record ID (Aggregate)</th>
                  <th>Correlation ID</th>
                  <th>Schema</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {/* 1. AI Decision Record */}
                <tr>
                  <td className="font-mono">{formatTimestamp(auditData?.created_at)}</td>
                  <td>
                    <strong style={{ color: 'var(--accent-purple)' }}>AI_DECISION_RECORD</strong>
                    <span style={{ display: 'block', fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                      Proposed: {auditData?.proposed_action || 'PAYMENT_LINK'} • Evaluation Model: {auditData?.model || '—'}
                    </span>
                  </td>
                  <td className="font-mono">{auditData?.decision_id || '—'}</td>
                  <td className="font-mono">{auditData?.correlation_id || '—'}</td>
                  <td>v{auditData?.audit_schema_version || '1'}.0</td>
                  <td>
                    <span style={{ color: 'var(--accent-emerald)', fontWeight: 600 }}>PERSISTED</span>
                  </td>
                </tr>

                {/* 2. Recovery Action Record */}
                <tr>
                  <td className="font-mono">{formatTimestamp(auditData?.created_at)}</td>
                  <td>
                    <strong style={{ color: 'var(--accent-blue)' }}>RECOVERY_ACTION</strong>
                    <span style={{ display: 'block', fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                      Action: {auditData?.final_action || 'PAYMENT_LINK'}
                    </span>
                  </td>
                  <td className="font-mono">{auditData?.recovery_action_id || '—'}</td>
                  <td className="font-mono">{auditData?.correlation_id || '—'}</td>
                  <td>v{auditData?.audit_schema_version || '1'}.0</td>
                  <td>
                    <StatusBadge status={auditData?.execution_status || 'APPROVED'} />
                  </td>
                </tr>

                {/* 3. Financial Event Record (if persisted) */}
                {auditData?.financial_event_id && (
                  <tr>
                    <td className="font-mono">{formatTimestamp(auditData?.created_at)}</td>
                    <td>
                      <strong style={{ color: 'var(--accent-emerald)' }}>FINANCIAL_EVENT</strong>
                      <span style={{ display: 'block', fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                        Append-only financial audit log
                      </span>
                    </td>
                    <td className="font-mono">{auditData.financial_event_id}</td>
                    <td className="font-mono">{auditData?.correlation_id || '—'}</td>
                    <td>v{auditData?.audit_schema_version || '1'}.0</td>
                    <td>
                      <span style={{ color: 'var(--accent-emerald)', fontWeight: 600 }}>IMMUTABLE</span>
                    </td>
                  </tr>
                )}

                {/* 4. Outbox Dispatch Event (if present) */}
                {auditData?.outbox_event_id && (
                  <tr>
                    <td className="font-mono">{formatTimestamp(auditData?.created_at)}</td>
                    <td>
                      <strong style={{ color: 'var(--accent-amber)' }}>RECOVERY_OUTBOX_EVENT</strong>
                      <span style={{ display: 'block', fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                        Transactional dispatch event
                      </span>
                    </td>
                    <td className="font-mono">{auditData.outbox_event_id}</td>
                    <td className="font-mono">{auditData?.correlation_id || '—'}</td>
                    <td>v{auditData?.audit_schema_version || '1'}.0</td>
                    <td>
                      <span style={{ color: 'var(--accent-green)', fontWeight: 600 }}>
                        {auditData.outbox_status || 'PENDING'}
                      </span>
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
};
