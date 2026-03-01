import { css } from '@emotion/css';
import { PanelProps } from '@grafana/data';
import { useStyles2 } from '@grafana/ui';
import React, { useEffect, useMemo, useState } from 'react';
import { HealthStatus, OpsApi, PlatformStats, ServiceInfo } from '../api/opsApi';
import { HarnessConsole } from './HarnessConsole';
import { HealthOverview } from './HealthOverview';
import { ServicesTable } from './ServicesTable';
import { StatsCards } from './StatsCards';
import { TestConsole } from './TestConsole';

interface OpsPanelOptions {
  gatewayUrl: string;
  refreshInterval: number;  // seconds
}

interface Props extends PanelProps<OpsPanelOptions> {}

export const OpsPanel: React.FC<Props> = ({ options, width, height }) => {
  const styles = useStyles2(getStyles);

  const [services, setServices] = useState<ServiceInfo[]>([]);
  const [health, setHealth] = useState<HealthStatus[]>([]);
  const [stats, setStats] = useState<PlatformStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const api = useMemo(() => new OpsApi(options.gatewayUrl), [options.gatewayUrl]);

  // Fetch data on mount and at interval
  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const [servicesData, healthData, statsData] = await Promise.all([
          api.getServices(),
          api.getHealth(),
          api.getStats()
        ]);
        setServices(servicesData);
        setHealth(healthData);
        setStats(statsData);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to fetch data');
      } finally {
        setLoading(false);
      }
    };

    fetchData();

    const interval = setInterval(fetchData, options.refreshInterval * 1000);
    return () => clearInterval(interval);
  }, [options.gatewayUrl, options.refreshInterval]);

  if (loading && !services.length) {
    return <div className={styles.loading}>Loading...</div>;
  }

  if (error) {
    return <div className={styles.error}>{error}</div>;
  }

  return (
    <div className={styles.container} style={{ width, height }}>
      <div className={styles.header}>
        <h2>LLM Platform Operations</h2>
        <span className={styles.timestamp}>
          Last updated: {new Date().toLocaleTimeString()}
        </span>
      </div>

      <div className={styles.grid}>
        <div className={styles.column}>
          <HealthOverview health={health} />
        </div>

        <div className={styles.column}>
          {stats && <StatsCards stats={stats} />}
        </div>

        <div className={styles.fullWidth}>
          <ServicesTable services={services} />
        </div>

        <div className={styles.fullWidth}>
          <TestConsole api={api} />
        </div>

        <div className={styles.fullWidth}>
          <HarnessConsole api={api} />
        </div>
      </div>
    </div>
  );
};

const getStyles = () => ({
  container: css`
    padding: 16px;
    overflow: auto;
  `,
  header: css`
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
  `,
  timestamp: css`
    color: #8e8e8e;
    font-size: 12px;
  `,
  grid: css`
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
  `,
  column: css`
    background: #1e1e1e;
    border-radius: 4px;
    padding: 12px;
  `,
  fullWidth: css`
    grid-column: 1 / -1;
    background: #1e1e1e;
    border-radius: 4px;
    padding: 12px;
  `,
  loading: css`
    display: flex;
    justify-content: center;
    align-items: center;
    height: 100%;
  `,
  error: css`
    color: #ff5555;
    padding: 16px;
  `
});
