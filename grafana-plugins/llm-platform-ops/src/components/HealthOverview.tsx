import { css } from '@emotion/css';
import React, { useState } from 'react';
import { HealthStatus } from '../api/opsApi';

interface Props {
  health: HealthStatus[];
}

export const HealthOverview: React.FC<Props> = ({ health }) => {
  const styles = getStyles();
  const [showHelp, setShowHelp] = useState(false);

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
      <div className={styles.titleRow}>
        <h3 className={styles.title}>Team Health</h3>
        <button className={styles.helpToggle} onClick={() => setShowHelp(!showHelp)} title="Toggle help">{showHelp ? '✕' : '?'}</button>
      </div>
      {showHelp && (
        <div className={styles.helpBox}>
          <p><strong>Team Health</strong> shows the live status of each service team in the platform.</p>
          <ul>
            <li><strong>Healthy (green):</strong> All pods are running and passing readiness checks.</li>
            <li><strong>Degraded (orange):</strong> Some pods are down &mdash; the service still works but at reduced capacity.</li>
            <li><strong>Unhealthy (red):</strong> No pods are ready &mdash; the service is offline.</li>
            <li><strong>Pods (e.g. 1/1):</strong> Ready pods vs total desired. Kubernetes automatically restarts failed pods.</li>
          </ul>
          <p>Each team represents a gateway route: <code>/api/quant/predict</code>, <code>/api/finetune/predict</code>, <code>/api/eval/predict</code>.</p>
        </div>
      )}
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
  titleRow: css`
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 8px;
  `,
  title: css`
    font-size: 14px;
    margin: 0;
  `,
  helpToggle: css`
    width: 22px;
    height: 22px;
    border-radius: 50%;
    border: 1px solid #555;
    background: #333;
    color: #aaa;
    font-size: 12px;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0;
    &:hover { background: #444; color: #fff; }
  `,
  helpBox: css`
    background: #1a2233;
    border: 1px solid #2a3a55;
    border-radius: 4px;
    padding: 10px 14px;
    margin-bottom: 12px;
    font-size: 12px;
    line-height: 1.6;
    color: #c8d0dd;
    p { margin: 0 0 6px; }
    ul { margin: 4px 0 6px 16px; padding: 0; }
    li { margin-bottom: 2px; }
    code { background: #2a3a55; padding: 1px 5px; border-radius: 3px; font-size: 11px; }
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
