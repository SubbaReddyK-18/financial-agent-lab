import React, { useState } from 'react';
import type { ControlRoomSection } from './types/navigation';
import { Header } from './components/Header';
import { Navigation } from './components/Navigation';
import { OperationsView } from './views/OperationsView';
import { DecisionsView } from './views/DecisionsView';
import { ApprovalsView } from './views/ApprovalsView';
import { EconomicsView } from './views/EconomicsView';
import { SimulationView } from './views/SimulationView';
import { AuditView } from './views/AuditView';
import { useOperationsSummary } from './hooks/useOperationsSummary';

export const App: React.FC = () => {
  const [activeSection, setActiveSection] = useState<ControlRoomSection>('operations');
  const { data: opsData } = useOperationsSummary();

  const pendingApprovalsCount =
    opsData.summary?.decision_metrics.human_review_required_count ?? 0;

  const renderActiveView = () => {
    switch (activeSection) {
      case 'operations':
        return <OperationsView />;
      case 'decisions':
        return <DecisionsView />;
      case 'approvals':
        return <ApprovalsView />;
      case 'economics':
        return <EconomicsView />;
      case 'simulation':
        return <SimulationView />;
      case 'audit':
        return <AuditView />;
      default:
        return <OperationsView />;
    }
  };

  return (
    <div className="app-container">
      <Header />
      <Navigation
        activeSection={activeSection}
        onSelectSection={setActiveSection}
        pendingApprovalsCount={pendingApprovalsCount}
      />
      <main className="main-content">
        {renderActiveView()}
      </main>
    </div>
  );
};

export default App;
