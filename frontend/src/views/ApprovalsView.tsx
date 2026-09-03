import React from 'react';
import { Card } from '../components/common/Card';
import { StatusBadge } from '../components/common/StatusBadge';
import { ShieldAlert, CheckCircle, XCircle, AlertCircle } from 'lucide-react';

export const ApprovalsView: React.FC = () => {
  const pendingApprovals = [
    {
      id: 'appr_001',
      actionId: 'act_7a6b5c4d',
      caseId: 'rc_5c6d7e8f',
      amountMinor: 500000,
      proposedAction: 'PAYMENT_LINK',
      discountPercent: 10,
      reason: 'High-value transaction above ₹4,000 threshold requiring human confirmation.',
      createdAt: '5 mins ago',
    },
    {
      id: 'appr_002',
      actionId: 'act_1a2b3c4d',
      caseId: 'rc_9a8b7c6d',
      amountMinor: 750000,
      proposedAction: 'ESCALATE',
      discountPercent: 0,
      reason: 'Low AI confidence score (0.45) triggered policy human-review flag.',
      createdAt: '18 mins ago',
    },
  ];

  return (
    <div>
      <div style={{ marginBottom: '20px', padding: '16px', background: 'rgba(245, 158, 11, 0.1)', border: '1px solid rgba(245, 158, 11, 0.3)', borderRadius: 'var(--radius-lg)', display: 'flex', alignItems: 'center', gap: '14px' }}>
        <ShieldAlert size={24} style={{ color: 'var(--accent-amber)', flexShrink: 0 }} />
        <div>
          <h4 style={{ color: 'var(--text-primary)', fontWeight: 600 }}>Human-in-the-Loop Governance Gatekeeper</h4>
          <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)' }}>
            Actions flagged with <code className="font-mono">requires_human_review = true</code> or exceeding merchant policy thresholds are held in quarantine until approved by an authorized administrator.
          </p>
        </div>
      </div>

      <Card title="Pending Action Approvals Queue" subtitle="Authorized action dispatch gate">
        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          {pendingApprovals.map((item) => (
            <div
              key={item.id}
              style={{
                padding: '18px',
                background: 'var(--bg-surface)',
                border: '1px solid var(--border-subtle)',
                borderRadius: 'var(--radius-md)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                flexWrap: 'wrap',
                gap: '16px',
              }}
            >
              <div style={{ flex: 1, minWidth: '280px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '6px' }}>
                  <StatusBadge status="PENDING_APPROVAL" />
                  <span className="font-mono" style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                    Case: {item.caseId}
                  </span>
                  <span style={{ fontWeight: 700, color: 'var(--text-primary)' }}>
                    ₹{item.amountMinor / 100}
                  </span>
                </div>
                <div style={{ fontSize: '0.95rem', fontWeight: 600, color: 'var(--accent-purple)', marginBottom: '4px' }}>
                  Action: {item.proposedAction} {item.discountPercent > 0 ? `(${item.discountPercent}% Discount)` : ''}
                </div>
                <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <AlertCircle size={14} style={{ color: 'var(--accent-amber)' }} />
                  {item.reason}
                </p>
              </div>

              <div style={{ display: 'flex', gap: '10px' }}>
                <button className="btn btn-success">
                  <CheckCircle size={16} /> Approve &amp; Dispatch
                </button>
                <button className="btn btn-danger">
                  <XCircle size={16} /> Reject Action
                </button>
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
};
