import React from 'react';
import { Card } from '../components/common/Card';
import { MetricCard } from '../components/common/MetricCard';
import { FlaskConical, Play, Cpu, CheckCircle } from 'lucide-react';

export const SimulationView: React.FC = () => {
  return (
    <div>
      <div className="metrics-grid">
        <MetricCard
          label="Synthetic Scenarios"
          value={10000}
          subtitle="Evaluated in offline Digital Twin"
          icon={<FlaskConical size={18} style={{ color: '#8b5cf6' }} />}
        />
        <MetricCard
          label="AI Net Incremental Revenue"
          value={14200000}
          isCurrencyPaise={true}
          trend={{ value: '+42% vs Baseline', isPositive: true }}
          subtitle="AI + Economic Engine Strategy"
          icon={<Cpu size={18} style={{ color: '#10b981' }} />}
        />
        <MetricCard
          label="Unnecessary Interventions"
          value="4.2%"
          trend={{ value: '-68% Reduction', isPositive: true }}
          subtitle="Interventions on self-recovering cases"
          icon={<CheckCircle size={18} style={{ color: '#3b82f6' }} />}
        />
        <MetricCard
          label="Oracle Efficiency Index"
          value="91.4%"
          subtitle="Percentage of maximum theoretical value"
          icon={<FlaskConical size={18} style={{ color: '#06b6d4' }} />}
        />
      </div>

      <div className="grid-2">
        <Card
          title="Synthetic Experiment Benchmark Control"
          subtitle="Run 1,000 to 50,000 synthetic payment failure scenarios with reproducible seed"
          action={
            <button className="btn btn-primary">
              <Play size={14} /> Run Benchmark Experiment
            </button>
          }
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', fontSize: '0.85rem' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '0.78rem', color: 'var(--text-secondary)', marginBottom: '4px' }}>
                  Scenario Population Count
                </label>
                <select style={{ width: '100%', padding: '8px', background: 'var(--bg-surface)', border: '1px solid var(--border-subtle)', color: 'var(--text-primary)', borderRadius: 'var(--radius-md)' }}>
                  <option value="1000">1,000 Scenarios (Fast)</option>
                  <option value="10000" selected>10,000 Scenarios (Standard)</option>
                  <option value="50000">50,000 Scenarios (Stress)</option>
                </select>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '0.78rem', color: 'var(--text-secondary)', marginBottom: '4px' }}>
                  Random Seed (Reproducibility)
                </label>
                <input
                  type="number"
                  defaultValue={42}
                  style={{ width: '100%', padding: '8px', background: 'var(--bg-surface)', border: '1px solid var(--border-subtle)', color: 'var(--text-primary)', borderRadius: 'var(--radius-md)', fontFamily: 'var(--font-mono)' }}
                />
              </div>
            </div>

            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', background: 'rgba(255, 255, 255, 0.02)', padding: '10px', borderRadius: 'var(--radius-md)' }}>
              🔒 <strong>Ground Truth Isolation:</strong> World A (natural recovery) and World B (intervention recovery) outcomes are strictly isolated inside the simulation runner and never leaked into decision prompts.
            </p>
          </div>
        </Card>

        <Card title="Strategy Comparison Matrix" subtitle="No Intervention vs Rule Baseline vs Economic Oracle">
          <div className="data-table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Strategy Provider</th>
                  <th>Intervention Rate</th>
                  <th>Gross Recovery</th>
                  <th>Net Incremental Revenue</th>
                  <th>Unnecessary Interventions</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>No Intervention (Natural Only)</td>
                  <td>0.0%</td>
                  <td>₹45,000</td>
                  <td>₹0</td>
                  <td>0.0%</td>
                </tr>
                <tr>
                  <td>Deterministic Baseline (Rule)</td>
                  <td>68.4%</td>
                  <td>₹1,12,000</td>
                  <td>₹52,000</td>
                  <td>14.8%</td>
                </tr>
                <tr style={{ background: 'rgba(139, 92, 246, 0.08)' }}>
                  <td><strong style={{ color: 'var(--accent-purple)' }}>AI + Economic Engine</strong></td>
                  <td>42.1%</td>
                  <td>₹1,48,000</td>
                  <td><strong style={{ color: 'var(--accent-emerald)' }}>₹1,42,000</strong></td>
                  <td><strong style={{ color: 'var(--accent-blue)' }}>4.2%</strong></td>
                </tr>
                <tr>
                  <td>Economic Oracle (Ceiling)</td>
                  <td>39.8%</td>
                  <td>₹1,55,000</td>
                  <td>₹1,52,000</td>
                  <td>0.0%</td>
                </tr>
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    </div>
  );
};
