import { css } from '@emotion/css';
import React from 'react';
import { HealthStatus } from '../api/opsApi';

interface Props {
  health: HealthStatus[];
}

export const HealthOverview: React.FC<Props> = ({ health }) => {
  const styles = getStyles();

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'healthy': return '#73bf69';
      case 'degraded': return '#ff9830';
      case 'unhealthy': return '#ff5555';
      default: return '#8e8e8e';
    }
  };

  return (
    <div className={styles.container}>
      <h3 className={styles.title}>Team Health</h3>
      <div className={styles.grid}>
        {health.map(h => (
          <div key={h.team} className={styles.card}>
            <div
              className={styles.indicator}
              style={{ backgroundColor: getStatusColor(h.status) }}
            />
            <div className={styles.info}>
              <span className={styles.team}>{h.team}</span>
              <span className={styles.status}>{h.status}</span>
              <span className={styles.pods}>
                {h.ready_pods}/{h.total_pods} pods
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

const getStyles = () => ({
  container: css``,
  title: css`
    margin-bottom: 12px;
    font-size: 14px;
  `,
  grid: css`
    display: flex;
    flex-direction: column;
    gap: 8px;
  `,
  card: css`
    display: flex;
    align-items: center;
    padding: 8px 12px;
    background: #252525;
    border-radius: 4px;
  `,
  indicator: css`
    width: 12px;
    height: 12px;
    border-radius: 50%;
    margin-right: 12px;
  `,
  info: css`
    display: flex;
    flex-direction: column;
  `,
  team: css`
    font-weight: 500;
    text-transform: capitalize;
  `,
  status: css`
    font-size: 12px;
    color: #8e8e8e;
  `,
  pods: css`
    font-size: 11px;
    color: #666;
  `
});
