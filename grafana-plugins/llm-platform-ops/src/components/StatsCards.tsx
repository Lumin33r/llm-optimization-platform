import { css } from '@emotion/css';
import React, { useState } from 'react';
import { PlatformStats } from '../api/opsApi';

interface Props {
  stats: PlatformStats;
}

export const StatsCards: React.FC<Props> = ({ stats }) => {
  const styles = getStyles();
  const [showHelp, setShowHelp] = useState(false);

  const formatNumber = (n: number): string => {
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
    if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
    return n.toString();
  };

  return (
    <div className={styles.container}>
      <div className={styles.titleRow}>
        <h3 className={styles.title}>Platform Stats (24h)</h3>
        <button className={styles.helpToggle} onClick={() => setShowHelp(!showHelp)} title="Toggle help">{showHelp ? '✕' : '?'}</button>
      </div>
      {showHelp && (
        <div className={styles.helpBox}>
          <p><strong>Platform Stats</strong> are live metrics queried from Prometheus over the last 24 hours.</p>
          <ul>
            <li><strong>Total Requests:</strong> How many inference requests all teams received combined.</li>
            <li><strong>Error Rate:</strong> Percentage of requests that returned HTTP 5xx errors. Below 1% is healthy.</li>
            <li><strong>P50 Latency:</strong> Median response time &mdash; 50% of requests were faster than this.</li>
            <li><strong>P95 Latency:</strong> 95th percentile &mdash; only 5% of requests were slower. Used for SLA targets.</li>
            <li><strong>P99 Latency:</strong> 99th percentile &mdash; the "worst-case" tail latency experienced by 1 in 100 users.</li>
          </ul>
          <p><strong>Requests by Team</strong> breaks down traffic per gateway route to show which team is generating the most load.</p>
        </div>
      )}
      <div className={styles.grid}>
        <div className={styles.card}>
          <span className={styles.label}>Total Requests</span>
          <span className={styles.value}>{formatNumber(stats.total_requests_24h)}</span>
        </div>
        <div className={styles.card}>
          <span className={styles.label}>Error Rate</span>
          <span className={styles.value}>{stats.error_rate_percent.toFixed(2)}%</span>
        </div>
        <div className={styles.card}>
          <span className={styles.label}>P50 Latency</span>
          <span className={styles.value}>{stats.p50_latency_ms.toFixed(0)} ms</span>
        </div>
        <div className={styles.card}>
          <span className={styles.label}>P95 Latency</span>
          <span className={styles.value}>{stats.p95_latency_ms.toFixed(0)} ms</span>
        </div>
        <div className={styles.card}>
          <span className={styles.label}>P99 Latency</span>
          <span className={styles.value}>{stats.p99_latency_ms.toFixed(0)} ms</span>
        </div>
      </div>

      <h4 className={styles.subtitle}>Requests by Team</h4>
      <div className={styles.teamStats}>
        {Object.entries(stats.requests_by_team).map(([team, count]) => (
          <div key={team} className={styles.teamRow}>
            <span className={styles.teamName}>{team}</span>
            <span className={styles.teamValue}>{formatNumber(count)}</span>
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
  subtitle: css`
    margin-top: 16px;
    margin-bottom: 8px;
    font-size: 13px;
    color: #8e8e8e;
  `,
  grid: css`
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
  `,
  card: css`
    display: flex;
    flex-direction: column;
    padding: 8px 12px;
    background: #252525;
    border-radius: 4px;
  `,
  label: css`
    font-size: 11px;
    color: #8e8e8e;
    margin-bottom: 4px;
  `,
  value: css`
    font-size: 18px;
    font-weight: 600;
  `,
  teamStats: css`
    display: flex;
    flex-direction: column;
    gap: 4px;
  `,
  teamRow: css`
    display: flex;
    justify-content: space-between;
    padding: 6px 12px;
    background: #252525;
    border-radius: 4px;
  `,
  teamName: css`
    text-transform: capitalize;
    font-size: 13px;
  `,
  teamValue: css`
    font-size: 13px;
    color: #8e8e8e;
  `
});
