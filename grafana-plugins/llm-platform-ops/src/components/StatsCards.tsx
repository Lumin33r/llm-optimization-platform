import { css } from '@emotion/css';
import React from 'react';
import { PlatformStats } from '../api/opsApi';

interface Props {
  stats: PlatformStats;
}

export const StatsCards: React.FC<Props> = ({ stats }) => {
  const styles = getStyles();

  const formatNumber = (n: number): string => {
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
    if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
    return n.toString();
  };

  return (
    <div className={styles.container}>
      <h3 className={styles.title}>Platform Stats (24h)</h3>
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
  title: css`
    margin-bottom: 12px;
    font-size: 14px;
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
