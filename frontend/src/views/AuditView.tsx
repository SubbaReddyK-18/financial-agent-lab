import React from 'react';
import { Card } from '../components/common/Card';
import { MetricCard } from '../components/common/MetricCard';
import { FileText, Search, Lock, Layers } from 'lucide-react';

export const AuditView: React.FC = () => {
  return (
    <div>
      <div className="metrics-grid">
        <MetricCard
          label="Immutable Financial Events"
          value={312}
          subtitle="Append-only PostgreSQL records"
          icon={<Lock size={18} style={{ color: '#10b981' }} />}
        />
        <MetricCard
          label="AI Decision Audit Records"
          value={124}
          subtitle="Complete context & prompt provenance"
          icon={<FileText size={18} style={{ color: '#8b5cf6' }} />}
        />
        <MetricCard
          label="Outbox Events Tracked"
          value={118}
          subtitle="Reliable dispatch trail"
          icon={<Layers size={18} style={{ color: '#3b82f6' }} />}
        />
        <MetricCard
          label="Prompt Provenance Hash"
          value="sha256:e3b0c..."
          subtitle="Prompt SHA-256 version metadata"
          icon={<Search size={18} style={{ color: '#06b6d4' }} />}
        />
      </div>

      <Card title="Decision & Event Audit Trail Inspector" subtitle="Full auditability trace explaining context → proposal → policy → action → outcome">
        <div style={{ display: 'flex', gap: '12px', marginBottom: '16px' }}>
          <input
            type="text"
            placeholder="Search by Recovery Case ID, Payment ID, or Correlation ID..."
            style={{ flex: 1, padding: '10px 14px', background: 'var(--bg-surface)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-md)', color: 'var(--text-primary)' }}
          />
          <button className="btn btn-secondary">
            <Search size={14} /> Search Audit Records
          </button>
        </div>

        <div className="data-table-container">
          <table className="data-table">
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Event Type</th>
                <th>Aggregate ID</th>
                <th>Correlation ID</th>
                <th>Audit Version</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td className="font-mono">2026-09-03 17:45:12</td>
                <td><strong style={{ color: 'var(--accent-purple)' }}>AI_DECISION_RECORDED</strong></td>
                <td className="font-mono">dec_001928</td>
                <td className="font-mono">corr_obs_8812</td>
                <td>v1.0.0</td>
                <td><span style={{ color: 'var(--accent-emerald)', fontWeight: 600 }}>PERSISTED</span></td>
              </tr>
              <tr>
                <td className="font-mono">2026-09-03 17:45:13</td>
                <td><strong style={{ color: 'var(--accent-blue)' }}>RECOVERY_ACTION_APPROVED</strong></td>
                <td className="font-mono">act_7a6b5c4d</td>
                <td className="font-mono">corr_obs_8812</td>
                <td>v1.0.0</td>
                <td><span style={{ color: 'var(--accent-emerald)', fontWeight: 600 }}>PERSISTED</span></td>
              </tr>
              <tr>
                <td className="font-mono">2026-09-03 17:45:14</td>
                <td><strong style={{ color: 'var(--accent-emerald)' }}>FINANCIAL_EVENT_COMMITTED</strong></td>
                <td className="font-mono">fe_554192</td>
                <td className="font-mono">corr_obs_8812</td>
                <td>v1.0.0</td>
                <td><span style={{ color: 'var(--accent-emerald)', fontWeight: 600 }}>IMMUTABLE</span></td>
              </tr>
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
};
