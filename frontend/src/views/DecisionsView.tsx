import React from 'react';
import { Card } from '../components/common/Card';
import { MetricCard } from '../components/common/MetricCard';
import { StatusBadge } from '../components/common/StatusBadge';
import { BrainCircuit, CheckCircle2, XCircle, DollarSign } from 'lucide-react';

export const DecisionsView: React.FC = () => {
  return (
    <div>
      <div className="metrics-grid">
        <MetricCard
          label="AI Proposals Attempted"
          value={124}
          subtitle="Bounded LLM decision evaluations"
          icon={<BrainCircuit size={18} style={{ color: '#8b5cf6' }} />}
        />
        <MetricCard
          label="Policy Pass Rate"
          value="95.2%"
          trend={{ value: 'Compliant', isPositive: true }}
          subtitle="Passed deterministic policy gate"
          icon={<CheckCircle2 size={18} style={{ color: '#10b981' }} />}
        />
        <MetricCard
          label="Fallback Triggered"
          value={6}
          subtitle="Deterministic baseline fallbacks"
          icon={<XCircle size={18} style={{ color: '#f59e0b' }} />}
        />
        <MetricCard
          label="Avg Economic Net Value"
          value={185000}
          isCurrencyPaise={true}
          subtitle="Expected per decision"
          icon={<DollarSign size={18} style={{ color: '#06b6d4' }} />}
        />
      </div>

      <div className="grid-2">
        <Card title="Latest AI Proposal & Policy Audit" subtitle="Structured output validation & policy gate checks">
          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            <div style={{ padding: '14px', background: 'rgba(139, 92, 246, 0.05)', border: '1px solid rgba(139, 92, 246, 0.2)', borderRadius: 'var(--radius-md)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>Proposal: PAYMENT_LINK</span>
                <StatusBadge status="POLICY_COMPLIANT" />
              </div>
              <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', marginBottom: '10px' }}>
                "Customer experienced INSUFFICIENT_FUNDS on card. Offering alternate payment link with 5% discount maximizes expected recovery."
              </p>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px', fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                <div>Confidence: <strong style={{ color: 'var(--text-primary)' }}>92%</strong></div>
                <div>Discount: <strong style={{ color: 'var(--text-primary)' }}>5% (Max 10%)</strong></div>
                <div>Action Success Prob: <strong style={{ color: 'var(--accent-emerald)' }}>80%</strong></div>
                <div>Natural Recovery Prob: <strong style={{ color: 'var(--text-primary)' }}>15%</strong></div>
              </div>
            </div>
          </div>
        </Card>

        <Card title="Candidate Action Economic Valuation" subtitle="Determined by EconomicEngine in integer minor units (paise)">
          <div className="data-table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Action</th>
                  <th>Exp. Gross Recovery</th>
                  <th>Intervention Cost</th>
                  <th>Expected Net Revenue</th>
                  <th>Selected</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>WAIT</td>
                  <td>₹270</td>
                  <td>₹0</td>
                  <td>₹270</td>
                  <td>No</td>
                </tr>
                <tr>
                  <td>RETRY</td>
                  <td>₹900</td>
                  <td>₹15</td>
                  <td>₹885</td>
                  <td>No</td>
                </tr>
                <tr style={{ background: 'rgba(16, 185, 129, 0.08)' }}>
                  <td><strong style={{ color: 'var(--accent-emerald)' }}>PAYMENT_LINK</strong></td>
                  <td>₹1,440</td>
                  <td>₹25</td>
                  <td><strong style={{ color: 'var(--accent-emerald)' }}>₹1,415</strong></td>
                  <td><strong style={{ color: 'var(--accent-emerald)' }}>YES ✓</strong></td>
                </tr>
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    </div>
  );
};
