import { css } from '@emotion/css';
import React, { useState } from 'react';
import { ServiceInfo } from '../api/opsApi';

interface Props {
  services: ServiceInfo[];
}

export const ServicesTable: React.FC<Props> = ({ services }) => {
  const styles = getStyles();
  const [showHelp, setShowHelp] = useState(false);

  return (
    <div className={styles.container}>
      <div className={styles.titleRow}>
        <h3 className={styles.title}>Registered Services</h3>
        <button className={styles.helpToggle} onClick={() => setShowHelp(!showHelp)} title="Toggle help">{showHelp ? '✕' : '?'}</button>
      </div>
      {showHelp && (
        <div className={styles.helpBox}>
          <p><strong>Registered Services</strong> lists all microservices discovered in the Kubernetes cluster that make up the LLM platform.</p>
          <ul>
            <li><strong>Service:</strong> The Kubernetes deployment name (e.g., <code>quant-api</code>, <code>gateway</code>).</li>
            <li><strong>Namespace:</strong> The K8s namespace where the service runs. Teams are isolated by namespace (<code>quant</code>, <code>finetune</code>, <code>eval</code>) while shared services live in <code>platform</code> or <code>observability</code>.</li>
            <li><strong>Version:</strong> The application version reported by each service's <code>/health</code> endpoint.</li>
            <li><strong>Image Tag:</strong> The Docker image tag currently deployed (e.g., <code>dev-latest</code>). This comes from the Kubernetes deployment spec.</li>
          </ul>
        </div>
      )}
      <table className={styles.table}>
        <thead>
          <tr>
            <th>Service</th>
            <th>Namespace</th>
            <th>Version</th>
            <th>Image Tag</th>
          </tr>
        </thead>
        <tbody>
          {services.map(service => (
            <tr key={service.name}>
              <td>{service.name}</td>
              <td><span className={styles.namespace}>{service.namespace}</span></td>
              <td>{service.version}</td>
              <td>{service.image_tag || '-'}</td>
            </tr>
          ))}
        </tbody>
      </table>
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
  table: css`
    width: 100%;
    border-collapse: collapse;

    th, td {
      text-align: left;
      padding: 8px 12px;
      border-bottom: 1px solid #333;
    }

    th {
      color: #8e8e8e;
      font-weight: 500;
    }
  `,
  namespace: css`
    background: #333;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 12px;
  `
});
