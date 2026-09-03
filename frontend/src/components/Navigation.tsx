import React from 'react';
import type { ControlRoomSection } from '../types/navigation';
import { 
  Zap, 
  BrainCircuit, 
  ShieldAlert, 
  TrendingUp, 
  FlaskConical, 
  FileText 
} from 'lucide-react';

interface NavigationProps {
  activeSection: ControlRoomSection;
  onSelectSection: (section: ControlRoomSection) => void;
  pendingApprovalsCount?: number;
}

export const Navigation: React.FC<NavigationProps> = ({
  activeSection,
  onSelectSection,
  pendingApprovalsCount = 2,
}) => {
  const navItems: { id: ControlRoomSection; label: string; icon: React.ReactNode; badge?: number }[] = [
    { id: 'operations', label: 'Operations', icon: <Zap size={16} /> },
    { id: 'decisions', label: 'Decisions', icon: <BrainCircuit size={16} /> },
    { 
      id: 'approvals', 
      label: 'Approvals', 
      icon: <ShieldAlert size={16} />, 
      badge: pendingApprovalsCount 
    },
    { id: 'economics', label: 'Economics', icon: <TrendingUp size={16} /> },
    { id: 'simulation', label: 'Simulation', icon: <FlaskConical size={16} /> },
    { id: 'audit', label: 'Audit Trace', icon: <FileText size={16} /> },
  ];

  return (
    <nav className="app-nav-bar">
      {navItems.map((item) => {
        const isActive = activeSection === item.id;
        return (
          <button
            key={item.id}
            className={`nav-item ${isActive ? 'active' : ''}`}
            onClick={() => onSelectSection(item.id)}
          >
            {item.icon}
            <span>{item.label}</span>
            {item.badge !== undefined && item.badge > 0 && (
              <span className="badge-count">{item.badge}</span>
            )}
          </button>
        );
      })}
    </nav>
  );
};
