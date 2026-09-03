import React from 'react';
import { Card } from '../components/common/Card';
import { MetricCard } from '../components/common/MetricCard';
import { StatusBadge } from '../components/common/StatusBadge';
import { Zap, AlertTriangle, ShieldCheck, ArrowRight, Play } from 'lucide-react';

export const OperationsView: React.FC = () => {
  // Static demonstration mock data for layout shell
  const mockCases = [
    {
      id: 'rc_9a8b7c6d',
      paymentId: 'pay_rzp_9901',
      orderId: 'order_rzp_1001',
      amountMinor: 250000,
      failureCode: 'INSUFFICIENT_FUNDS',
      status: 'IN_PROGRESS',
      action: 'PAYMENT_LINK',
      createdAt: '2 mins ago',
    },
    {
      id: 'rc_1e2f3a4b',
      paymentId: 'pay_rzp_9902',
      orderId: 'order_rzp_1002',
      amountMinor: 180000,
      failureCode: 'GATEWAY_TIMEOUT',
      status: 'RECOVERED',
      action: 'RETRY',
      createdAt: '12 mins ago',
    },
    {
      id: 'rc_5c6d7e8f',
      paymentId: 'pay_rzp_9903',
      orderId: 'order_rzp_1003',
      amountMinor: 500000,
      failureCode: 'AUTHENTICATION_FAILED',
      status: 'OPEN',
      action: 'PENDING_HUMAN_REVIEW',
      createdAt: '25 mins ago',
    },
  ];

  return (
    <div>
      <div className="metrics-grid">
        <MetricCard
          label="Total Payment Failures"
          value={142}
          subtitle="Ingested via Razorpay Webhook"
          icon={<Zap size={18} style={{ color: '#3b82f6' }} />}
        />
        <MetricCard
          label="Active Recovery Cases"
          value={18}
          subtitle="Under active orchestration"
          icon={<AlertTriangle size={18} style={{ color: '#f59e0b' }} />}
        />
        <MetricCard
          label="Successful Recoveries"
          value={98}
          trend={{ value: '+69%', isPositive: true }}
          subtitle="Payments recovered safely"
          icon={<ShieldCheck size={18} style={{ color: '#10b981' }} />}
        />
        <MetricCard
          label="Amount at Risk"
          value={34500000}
          isCurrencyPaise={true}
          subtitle="Across active cases"
          icon={<Zap size={18} style={{ color: '#8b5cf6' }} />}
        />
      </div>

      <div className="grid-2">
        <Card
          title="Active Recovery Cases Feed"
          subtitle="Real-time status transitions derived from durable PostgreSQL inbox"
          action={
            <button className="btn btn-secondary">
              <Play size={14} /> Simulate Ingestion
            </button>
          }
        >
          <div className="data-table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Case ID</th>
                  <th>Payment ID</th>
                  <th>Amount</th>
                  <th>Failure Reason</th>
                  <th>Status</th>
                  <th>Selected Action</th>
                </tr>
              </thead>
              <tbody>
                {mockCases.map((c) => (
                  <tr key={c.id}>
                    <td className="font-mono">{c.id}</td>
                    <td className="font-mono">{c.paymentId}</td>
                    <td style={{ fontWeight: 600 }}>₹{(c.amountMinor / 100).toLocaleString('en-IN')}</td>
                    <td>
                      <span className="font-mono" style={{ fontSize: '0.78rem', color: 'var(--text-secondary)' }}>
                        {c.failureCode}
                      </span>
                    </td>
                    <td>
                      <StatusBadge status={c.status} />
                    </td>
                    <td>
                      <span style={{ fontWeight: 500, color: 'var(--accent-purple)' }}>{c.action}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <Card title="Recovery State Machine Lifecycle" subtitle="Deterministic transition boundaries enforced by domain logic">
          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', padding: '10px 0' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px', background: 'rgba(255, 255, 255, 0.02)', borderRadius: 'var(--radius-md)' }}>
              <div>
                <span style={{ fontWeight: 600, fontSize: '0.9rem' }}>1. Durable Ingestion</span>
                <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>Razorpay Webhook → Inbox Verification</p>
              </div>
              <ArrowRight size={16} style={{ color: 'var(--text-muted)' }} />
            </div>

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px', background: 'rgba(255, 255, 255, 0.02)', borderRadius: 'var(--radius-md)' }}>
              <div>
                <span style={{ fontWeight: 600, fontSize: '0.9rem' }}>2. AI & Economic Decisioning</span>
                <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>AI Context → Policy Gate → Economic Engine</p>
              </div>
              <ArrowRight size={16} style={{ color: 'var(--text-muted)' }} />
            </div>

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px', background: 'rgba(255, 255, 255, 0.02)', borderRadius: 'var(--radius-md)' }}>
              <div>
                <span style={{ fontWeight: 600, fontSize: '0.9rem' }}>3. Outbox-Exclusive Dispatch</span>
                <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>Control Plane → Outbox Worker → Execution</p>
              </div>
              <ArrowRight size={16} style={{ color: 'var(--text-muted)' }} />
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
};
