/**
 * frontend/src/views/ApprovalsView.tsx
 *
 * Approvals Control Room — live data from:
 *   GET /api/observability/recovery/63f5c724-61b7-4679-91ae-d9862eca9deb
 *   POST /api/recovery-actions/{actionId}/approve
 *   POST /api/recovery-actions/{actionId}/reject
 *
 * Provides human-in-the-loop governance for quarantined high-value actions.
 */

import React, { useState } from 'react';
import {
  ShieldAlert,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Loader2,
  RefreshCw,
  Key,
  Eye,
  EyeOff,
  Database,
  ArrowRight,
  ShieldCheck,
  Send,
  Ban,
  Clock,
  DollarSign,
} from 'lucide-react';
import { Card } from '../components/common/Card';
import { StatusBadge } from '../components/common/StatusBadge';
import { useRecoveryAudit } from '../hooks/useRecoveryAudit';
import { approveRecoveryAction, rejectRecoveryAction } from '../api/client';
import type { ApprovalActionResponse } from '../api/types';

// ─── Constants ───────────────────────────────────────────────────────────────

const DEMO_CASE_ID = '63f5c724-61b7-4679-91ae-d9862eca9deb';
const DEMO_ACTION_ID = 'b1261e75-f2a1-452e-b17f-df4396ce3f2d';

// ─── Helpers ─────────────────────────────────────────────────────────────────

const formatPaise = (paise: number | null | undefined): string => {
  if (paise == null) return '—';
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 2,
  }).format(paise / 100);
};

const formatTimestamp = (iso: string | null | undefined): string => {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('en-IN', {
    dateStyle: 'medium',
    timeStyle: 'medium',
    timeZone: 'Asia/Kolkata',
  });
};

export const ApprovalsView: React.FC = () => {
  const { data, loading, initializing, error, lastFetchedAt, refresh } =
    useRecoveryAudit(DEMO_CASE_ID);

  // Auth & action state
  const [apiKey, setApiKey] = useState<string>(() => {
    try {
      return localStorage.getItem('fal_admin_api_key') || '';
    } catch {
      return '';
    }
  });
  const [showApiKey, setShowApiKey] = useState<boolean>(false);
  const [reason, setReason] = useState<string>('');
  const [actionLoading, setActionLoading] = useState<boolean>(false);
  const [actionResult, setActionResult] = useState<ApprovalActionResponse | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const handleApiKeyChange = (val: string) => {
    setApiKey(val);
    try {
      localStorage.setItem('fal_admin_api_key', val);
    } catch {
      // ignore storage errors
    }
  };

  const handleApprove = async () => {
    setActionError(null);
    setActionLoading(true);
    try {
      const targetActionId = data?.recovery_action_id || DEMO_ACTION_ID;
      const res = await approveRecoveryAction(targetActionId, reason.trim() || undefined, apiKey.trim() || undefined);
      setActionResult(res);
      await refresh();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setActionError(msg);
    } finally {
      setActionLoading(false);
    }
  };

  const handleReject = async () => {
    setActionError(null);
    setActionLoading(true);
    try {
      const targetActionId = data?.recovery_action_id || DEMO_ACTION_ID;
      const res = await rejectRecoveryAction(targetActionId, reason.trim() || undefined, apiKey.trim() || undefined);
      setActionResult(res);
      await refresh();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setActionError(msg);
    } finally {
      setActionLoading(false);
    }
  };

  // Derive dynamic display status
  const currentActionStatus =
    actionResult?.status ||
    data?.execution_status ||
    'PENDING_APPROVAL';

  const actionId = data?.recovery_action_id || DEMO_ACTION_ID;
  const decisionId = data?.decision_id || '72dc33e2-a4b8-4038-9820-67a5a2f34756';
  const amountMinor = data?.observable_context?.amount_minor ?? 2500000;
  const actionType = data?.final_action || data?.proposed_action || 'PAYMENT_LINK';
  const isActionResolved = currentActionStatus === 'APPROVED' || currentActionStatus === 'CANCELLED';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      {/* ── Governance Header Banner ─────────────────────────────────────── */}
      <div
        style={{
          padding: '16px 20px',
          background: 'rgba(245, 158, 11, 0.08)',
          border: '1px solid rgba(245, 158, 11, 0.25)',
          borderRadius: 'var(--radius-lg)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '14px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
          <ShieldAlert size={28} style={{ color: 'var(--accent-amber)', flexShrink: 0 }} />
          <div>
            <h4 style={{ color: 'var(--text-primary)', fontWeight: 600, fontSize: '1rem', marginBottom: '2px' }}>
              Human-in-the-Loop Governance Gatekeeper
            </h4>
            <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
              Actions on high-value transactions (&ge; ₹10,000 threshold) or flagged with{' '}
              <code className="font-mono">requires_human_review = true</code> are held in quarantine until authorized by an administrator.
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
              background: 'rgba(59, 130, 246, 0.15)',
              color: '#60a5fa',
              border: '1px solid rgba(59, 130, 246, 0.3)',
            }}
          >
            <Database size={12} /> Live PostgreSQL record
          </span>
          <button
            onClick={() => refresh()}
            disabled={loading}
            className="btn btn-secondary"
            style={{ padding: '6px 12px', fontSize: '0.8rem', display: 'flex', alignItems: 'center', gap: '6px' }}
            title="Refresh record from server"
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
            padding: '14px 18px',
            background: 'rgba(239, 68, 68, 0.1)',
            border: '1px solid rgba(239, 68, 68, 0.3)',
            borderRadius: 'var(--radius-md)',
            color: '#f87171',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '12px',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <AlertCircle size={18} style={{ flexShrink: 0 }} />
            <span style={{ fontSize: '0.88rem' }}>
              <strong>Failed to fetch recovery case:</strong> {error}
            </span>
          </div>
          <button
            onClick={() => refresh()}
            className="btn btn-secondary"
            style={{ padding: '4px 10px', fontSize: '0.78rem' }}
          >
            Retry
          </button>
        </div>
      )}

      {/* ── Loading Skeleton ──────────────────────────────────────────────── */}
      {initializing ? (
        <Card title="Pending Action Approvals Queue" subtitle="Authorized action dispatch gate">
          <div style={{ padding: '48px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '14px', color: 'var(--text-muted)' }}>
            <Loader2 size={32} className="animate-spin" style={{ color: 'var(--accent-purple)' }} />
            <span style={{ fontSize: '0.9rem' }}>Loading pending action from PostgreSQL…</span>
          </div>
        </Card>
      ) : (
        <Card
          title="Pending Action Approvals Queue"
          subtitle={`Case: ${DEMO_CASE_ID} • Action: ${actionId}`}
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            {/* ── Action Card ──────────────────────────────────────────────── */}
            <div
              style={{
                padding: '20px',
                background: 'var(--bg-surface)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 'var(--radius-lg)',
                display: 'flex',
                flexDirection: 'column',
                gap: '18px',
              }}
            >
              {/* Row 1: Header metrics & Status */}
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  flexWrap: 'wrap',
                  gap: '14px',
                  paddingBottom: '14px',
                  borderBottom: '1px solid var(--border-subtle)',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
                  <StatusBadge status={currentActionStatus} />
                  <span style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                    {formatPaise(amountMinor)}
                  </span>
                  <span
                    style={{
                      padding: '2px 8px',
                      background: 'rgba(168, 85, 247, 0.15)',
                      color: 'var(--accent-purple)',
                      borderRadius: 'var(--radius-sm)',
                      fontSize: '0.8rem',
                      fontWeight: 600,
                    }}
                  >
                    Action: {actionType}
                  </span>
                </div>

                <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <Clock size={13} />
                  Evaluated: {formatTimestamp(data?.created_at || lastFetchedAt)}
                </div>
              </div>

              {/* Row 2: Metadata Identifier Grid */}
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
                  gap: '12px',
                  background: 'rgba(0, 0, 0, 0.2)',
                  padding: '14px',
                  borderRadius: 'var(--radius-md)',
                  border: '1px solid var(--border-subtle)',
                }}
              >
                <div>
                  <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                    Recovery Case ID
                  </div>
                  <div className="font-mono" style={{ fontSize: '0.8rem', color: 'var(--text-primary)', wordBreak: 'break-all' }}>
                    {data?.recovery_case_id || DEMO_CASE_ID}
                  </div>
                </div>

                <div>
                  <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                    Recovery Action ID
                  </div>
                  <div className="font-mono" style={{ fontSize: '0.8rem', color: 'var(--text-primary)', wordBreak: 'break-all' }}>
                    {actionId}
                  </div>
                </div>

                <div>
                  <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                    AI Decision ID
                  </div>
                  <div className="font-mono" style={{ fontSize: '0.8rem', color: 'var(--text-primary)', wordBreak: 'break-all' }}>
                    {decisionId}
                  </div>
                </div>

                <div>
                  <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                    Payment ID
                  </div>
                  <div className="font-mono" style={{ fontSize: '0.8rem', color: 'var(--text-primary)', wordBreak: 'break-all' }}>
                    {data?.observable_context?.payment_id || data?.payment_id || '—'}
                  </div>
                </div>
              </div>

              {/* Row 3: Decision & Governance Context */}
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
                  gap: '14px',
                }}
              >
                <div
                  style={{
                    padding: '12px 14px',
                    background: 'rgba(245, 158, 11, 0.05)',
                    border: '1px solid rgba(245, 158, 11, 0.2)',
                    borderRadius: 'var(--radius-md)',
                  }}
                >
                  <div style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--accent-amber)', display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '4px' }}>
                    <AlertCircle size={14} /> Governance Policy Requirement
                  </div>
                  <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', lineHeight: 1.4 }}>
                    High-value transaction ({formatPaise(amountMinor)}) exceeds the merchant threshold (₹10,000.00). Deterministic policy gate held dispatch in quarantine pending administrator sign-off.
                  </p>
                </div>

                <div
                  style={{
                    padding: '12px 14px',
                    background: 'rgba(59, 130, 246, 0.05)',
                    border: '1px solid rgba(59, 130, 246, 0.2)',
                    borderRadius: 'var(--radius-md)',
                  }}
                >
                  <div style={{ fontSize: '0.78rem', fontWeight: 600, color: '#60a5fa', display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '4px' }}>
                    <ShieldCheck size={14} /> Payment & Failure Details
                  </div>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', display: 'flex', flexDirection: 'column', gap: '2px' }}>
                    <div>Failure Code: <code className="font-mono">{data?.observable_context?.failure_code || 'CUSTOMER_AUTH_FAILED'}</code></div>
                    <div>Payment Method: {data?.observable_context?.payment_method || 'UPI'} • Customer: {data?.observable_context?.customer_segment || 'VIP'}</div>
                    {data?.economic_evaluation && (
                      <div>Expected Net Lift: <strong style={{ color: 'var(--accent-green)' }}>{formatPaise(data.economic_evaluation.expected_net_incremental_revenue_minor)}</strong></div>
                    )}
                  </div>
                </div>
              </div>

              {/* ── Mutation Result Banner ──────────────────────────────────── */}
              {actionResult && (
                <div
                  style={{
                    padding: '14px 18px',
                    background:
                      actionResult.status === 'APPROVED'
                        ? 'rgba(16, 185, 129, 0.12)'
                        : 'rgba(239, 68, 68, 0.12)',
                    border: `1px solid ${
                      actionResult.status === 'APPROVED'
                        ? 'rgba(16, 185, 129, 0.35)'
                        : 'rgba(239, 68, 68, 0.35)'
                    }`,
                    borderRadius: 'var(--radius-md)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    flexWrap: 'wrap',
                    gap: '12px',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    {actionResult.status === 'APPROVED' ? (
                      <CheckCircle2 size={22} style={{ color: 'var(--accent-green)', flexShrink: 0 }} />
                    ) : (
                      <Ban size={22} style={{ color: 'var(--accent-red)', flexShrink: 0 }} />
                    )}
                    <div>
                      <div style={{ fontWeight: 600, fontSize: '0.9rem', color: 'var(--text-primary)' }}>
                        {actionResult.status === 'APPROVED'
                          ? 'Action Approved & Dispatch Enqueued'
                          : 'Action Rejected & Cancelled'}
                      </div>
                      <div style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
                        Status: <code className="font-mono">{actionResult.status}</code> • Execution: <code className="font-mono">{actionResult.execution}</code>
                        {actionResult.execution === 'queued' && (
                          <span style={{ marginLeft: '6px', color: 'var(--accent-green)' }}>
                            (Transactional Outbox event enqueued for asynchronous worker)
                          </span>
                        )}
                        {actionResult.execution === 'not_queued' && (
                          <span style={{ marginLeft: '6px', color: 'var(--accent-amber)' }}>
                            (Dispatch event suppressed; no outbox record created)
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              )}

              {/* ── Action Mutation Error Banner ────────────────────────────── */}
              {actionError && (
                <div
                  style={{
                    padding: '12px 16px',
                    background: 'rgba(239, 68, 68, 0.1)',
                    border: '1px solid rgba(239, 68, 68, 0.3)',
                    borderRadius: 'var(--radius-md)',
                    color: '#f87171',
                    fontSize: '0.84rem',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '10px',
                  }}
                >
                  <AlertCircle size={18} style={{ flexShrink: 0 }} />
                  <div>
                    <strong>Action Authorization Failed:</strong> {actionError}
                    {actionError.includes('503') && (
                      <div style={{ marginTop: '2px', fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                        Note: The backend requires <code>ADMIN_API_KEY</code> to be configured in settings / .env. Provide the matching key in the input below.
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* ── Action Controls & Input Form ────────────────────────────── */}
              <div
                style={{
                  padding: '16px',
                  background: 'rgba(0, 0, 0, 0.25)',
                  borderRadius: 'var(--radius-md)',
                  border: '1px solid var(--border-subtle)',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '14px',
                }}
              >
                <div style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Key size={15} style={{ color: 'var(--accent-purple)' }} /> Administrator Authorization Boundary
                </div>

                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
                    gap: '12px',
                  }}
                >
                  {/* Admin API Key Input */}
                  <div>
                    <label
                      htmlFor="admin-api-key-input"
                      style={{ display: 'block', fontSize: '0.76rem', color: 'var(--text-muted)', marginBottom: '4px' }}
                    >
                      Admin API Key (<code className="font-mono">X-API-Key</code> header)
                    </label>
                    <div style={{ position: 'relative' }}>
                      <input
                        id="admin-api-key-input"
                        type={showApiKey ? 'text' : 'password'}
                        placeholder="Enter configured ADMIN_API_KEY..."
                        value={apiKey}
                        onChange={(e) => handleApiKeyChange(e.target.value)}
                        disabled={actionLoading}
                        style={{
                          width: '100%',
                          padding: '8px 36px 8px 12px',
                          background: 'var(--bg-card)',
                          border: '1px solid var(--border-subtle)',
                          borderRadius: 'var(--radius-sm)',
                          color: 'var(--text-primary)',
                          fontSize: '0.84rem',
                          fontFamily: 'monospace',
                        }}
                      />
                      <button
                        type="button"
                        onClick={() => setShowApiKey(!showApiKey)}
                        style={{
                          position: 'absolute',
                          right: '8px',
                          top: '50%',
                          transform: 'translateY(-50%)',
                          background: 'none',
                          border: 'none',
                          color: 'var(--text-muted)',
                          cursor: 'pointer',
                          padding: '4px',
                        }}
                        title={showApiKey ? 'Hide key' : 'Show key'}
                      >
                        {showApiKey ? <EyeOff size={14} /> : <Eye size={14} />}
                      </button>
                    </div>
                  </div>

                  {/* Optional Justification Reason */}
                  <div>
                    <label
                      htmlFor="approval-reason-input"
                      style={{ display: 'block', fontSize: '0.76rem', color: 'var(--text-muted)', marginBottom: '4px' }}
                    >
                      Decision Justification / Reason (Optional)
                    </label>
                    <input
                      id="approval-reason-input"
                      type="text"
                      placeholder="e.g., Verified customer KYC and transaction validity"
                      value={reason}
                      onChange={(e) => setReason(e.target.value)}
                      disabled={actionLoading}
                      maxLength={512}
                      style={{
                        width: '100%',
                        padding: '8px 12px',
                        background: 'var(--bg-card)',
                        border: '1px solid var(--border-subtle)',
                        borderRadius: 'var(--radius-sm)',
                        color: 'var(--text-primary)',
                        fontSize: '0.84rem',
                      }}
                    />
                  </div>
                </div>

                {/* Submit Action Buttons */}
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'flex-end',
                    gap: '12px',
                    paddingTop: '8px',
                    borderTop: '1px solid var(--border-subtle)',
                  }}
                >
                  <button
                    onClick={handleReject}
                    disabled={actionLoading || isActionResolved}
                    className="btn btn-danger"
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '8px',
                      padding: '8px 16px',
                      fontSize: '0.85rem',
                      opacity: isActionResolved ? 0.5 : 1,
                      cursor: isActionResolved ? 'not-allowed' : 'pointer',
                    }}
                  >
                    {actionLoading ? (
                      <Loader2 size={16} className="animate-spin" />
                    ) : (
                      <XCircle size={16} />
                    )}
                    Reject Action
                  </button>

                  <button
                    onClick={handleApprove}
                    disabled={actionLoading || isActionResolved}
                    className="btn btn-success"
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '8px',
                      padding: '8px 18px',
                      fontSize: '0.85rem',
                      fontWeight: 600,
                      opacity: isActionResolved ? 0.5 : 1,
                      cursor: isActionResolved ? 'not-allowed' : 'pointer',
                    }}
                  >
                    {actionLoading ? (
                      <Loader2 size={16} className="animate-spin" />
                    ) : (
                      <CheckCircle2 size={16} />
                    )}
                    Approve &amp; Dispatch
                  </button>
                </div>
              </div>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
};
