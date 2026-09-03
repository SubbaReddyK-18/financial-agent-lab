import React from 'react';

type StatusType = 
  | 'OPEN' 
  | 'IN_PROGRESS' 
  | 'RECOVERED' 
  | 'CLOSED' 
  | 'APPROVED' 
  | 'COMPLETED' 
  | 'SUPERSEDED' 
  | 'CANCELLED' 
  | 'PENDING_APPROVAL' 
  | 'POLICY_COMPLIANT' 
  | 'POLICY_REJECTED';

interface StatusBadgeProps {
  status: StatusType | string;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status }) => {
  const getBadgeClass = (s: string) => {
    switch (s.toUpperCase()) {
      case 'OPEN':
        return 'badge-open';
      case 'IN_PROGRESS':
      case 'APPROVED':
      case 'EXECUTING':
        return 'badge-in-progress';
      case 'RECOVERED':
      case 'COMPLETED':
      case 'POLICY_COMPLIANT':
        return 'badge-recovered';
      case 'CLOSED':
      case 'SUPERSEDED':
      case 'CANCELLED':
        return 'badge-closed';
      case 'PENDING_APPROVAL':
      case 'POLICY_REJECTED':
        return 'badge-approval';
      default:
        return 'badge-closed';
    }
  };

  return <span className={`badge ${getBadgeClass(status)}`}>{status}</span>;
};
