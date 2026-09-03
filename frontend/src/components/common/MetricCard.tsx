import React from 'react';

interface MetricCardProps {
  label: string;
  value: string | number;
  isCurrencyPaise?: boolean;
  trend?: {
    value: string;
    isPositive?: boolean;
    isNeutral?: boolean;
  };
  subtitle?: string;
  icon?: React.ReactNode;
}

export const MetricCard: React.FC<MetricCardProps> = ({
  label,
  value,
  isCurrencyPaise = false,
  trend,
  subtitle,
  icon,
}) => {
  const formatValue = () => {
    if (isCurrencyPaise && typeof value === 'number') {
      const rupees = value / 100;
      return new Intl.NumberFormat('en-IN', {
        style: 'currency',
        currency: 'INR',
        maximumFractionDigits: 0,
      }).format(rupees);
    }
    return value;
  };

  return (
    <div className="card metric-card">
      <div className="metric-header">
        <span className="metric-label">{label}</span>
        {icon && <div className="metric-icon-wrapper">{icon}</div>}
      </div>

      <div className="metric-value">{formatValue()}</div>

      {(trend || subtitle) && (
        <div className="metric-footer">
          {trend && (
            <span
              className={`trend-indicator ${
                trend.isNeutral
                  ? 'trend-neutral'
                  : trend.isPositive
                  ? 'trend-positive'
                  : 'trend-negative'
              }`}
            >
              {trend.value}
            </span>
          )}
          {subtitle && <span>{subtitle}</span>}
        </div>
      )}
    </div>
  );
};
