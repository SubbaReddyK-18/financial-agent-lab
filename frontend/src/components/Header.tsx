import React from 'react';
import { Activity, ShieldCheck, Database, Cpu } from 'lucide-react';

export const Header: React.FC = () => {
  return (
    <header className="app-header">
      <div className="brand-section">
        <div className="brand-logo">
          <Activity size={22} />
        </div>
        <div>
          <div className="brand-title">
            Financial Agent Lab
            <span className="brand-badge">
              <span className="pulse-dot" />
              Autonomous Recovery Engine
            </span>
          </div>
        </div>
      </div>

      <div className="header-status-bar">
        <div className="status-pill">
          <ShieldCheck size={14} style={{ color: '#10b981' }} />
          <span>Environment: <strong>Razorpay Test Mode</strong></span>
        </div>

        <div className="status-pill">
          <Database size={14} style={{ color: '#3b82f6' }} />
          <span>Persistence: <strong>PostgreSQL 010/head</strong></span>
        </div>

        <div className="status-pill">
          <Cpu size={14} style={{ color: '#8b5cf6' }} />
          <span>Runtime AI Provider: <strong>Mock LLM (0 Quota Mode)</strong></span>
        </div>
      </div>
    </header>
  );
};
