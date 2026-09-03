import React from 'react';
import { Card } from '../components/common/Card';
import { MetricCard } from '../components/common/MetricCard';
import { TrendingUp, Award, DollarSign, Wallet } from 'lucide-react';

export const EconomicsView: React.FC = () => {
  return (
    <div>
      <div className="metrics-grid">
        <MetricCard
          label="Net Incremental Revenue"
          value={18450000}
          isCurrencyPaise={true}
          trend={{ value: '+24.8%', isPositive: true }}
          subtitle="Primary optimization metric"
          icon={<TrendingUp size={18} style={{ color: '#10b981' }} />}
        />
        <MetricCard
          label="Realized Captured Revenue"
          value={32800000}
          isCurrencyPaise={true}
          subtitle="Observed total recovered payment volume"
          icon={<Award size={18} style={{ color: '#3b82f6' }} />}
        />
        <MetricCard
          label="Intervention Costs"
          value={420000}
          isCurrencyPaise={true}
          subtitle="SMS/Email/Link gateway costs"
          icon={<Wallet size={18} style={{ color: '#f59e0b' }} />}
        />
        <MetricCard
          label="AI Inference Cost"
          value={18000}
          isCurrencyPaise={true}
          subtitle="Total LLM token expense"
          icon={<DollarSign size={18} style={{ color: '#8b5cf6' }} />}
        />
      </div>

      <div className="grid-2">
        <Card title="Net Incremental Revenue Formula Breakdown" subtitle="Causal revenue accounting vs raw recovery rate">
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', fontSize: '0.85rem' }}>
            <div style={{ padding: '12px', background: 'rgba(255, 255, 255, 0.02)', borderRadius: 'var(--radius-md)' }}>
              <span style={{ color: 'var(--accent-emerald)', fontWeight: 600 }}>+ Revenue Recovered with Intervention:</span> ₹3,28,000
            </div>
            <div style={{ padding: '12px', background: 'rgba(255, 255, 255, 0.02)', borderRadius: 'var(--radius-md)' }}>
              <span style={{ color: 'var(--accent-rose)', fontWeight: 600 }}>- Counterfactual Natural Recovery (Would recover anyway):</span> ₹1,35,000
            </div>
            <div style={{ padding: '12px', background: 'rgba(255, 255, 255, 0.02)', borderRadius: 'var(--radius-md)' }}>
              <span style={{ color: 'var(--accent-amber)', fontWeight: 600 }}>- Intervention Action Costs (Link/SMS):</span> ₹4,200
            </div>
            <div style={{ padding: '12px', background: 'rgba(255, 255, 255, 0.02)', borderRadius: 'var(--radius-md)' }}>
              <span style={{ color: 'var(--accent-purple)', fontWeight: 600 }}>- AI Inference Token Costs:</span> ₹180
            </div>
            <hr style={{ borderColor: 'var(--border-subtle)', margin: '4px 0' }} />
            <div style={{ padding: '14px', background: 'rgba(16, 185, 129, 0.1)', border: '1px solid rgba(16, 185, 129, 0.3)', borderRadius: 'var(--radius-md)', fontWeight: 700, fontSize: '1.05rem', color: 'var(--accent-emerald)' }}>
              = Net Incremental Revenue: ₹1,84,500
            </div>
          </div>
        </Card>

        <Card title="Action Distribution & Cost Efficiency" subtitle="Recovery strategy allocation">
          <div className="data-table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Strategy</th>
                  <th>Executions</th>
                  <th>Share</th>
                  <th>Avg Unit Cost</th>
                  <th>Total Cost</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>WAIT (Natural Recovery)</td>
                  <td>28</td>
                  <td>22.5%</td>
                  <td>₹0.00</td>
                  <td>₹0</td>
                </tr>
                <tr>
                  <td>RETRY</td>
                  <td>42</td>
                  <td>33.8%</td>
                  <td>₹0.15</td>
                  <td>₹630</td>
                </tr>
                <tr>
                  <td>PAYMENT_LINK</td>
                  <td>46</td>
                  <td>37.1%</td>
                  <td>₹0.25</td>
                  <td>₹1,150</td>
                </tr>
                <tr>
                  <td>NOTIFY</td>
                  <td>8</td>
                  <td>6.6%</td>
                  <td>₹0.10</td>
                  <td>₹80</td>
                </tr>
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    </div>
  );
};
