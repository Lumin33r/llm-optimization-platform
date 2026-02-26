import { css } from '@emotion/css';
import React from 'react';
import { ServiceInfo } from '../api/opsApi';

interface Props {
  services: ServiceInfo[];
}

export const ServicesTable: React.FC<Props> = ({ services }) => {
  const styles = getStyles();

  return (
    <div className={styles.container}>
      <h3 className={styles.title}>Registered Services</h3>
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
  title: css`
    margin-bottom: 12px;
    font-size: 14px;
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
