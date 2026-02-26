import { css } from '@emotion/css';
import React, { useState } from 'react';
import { OpsApi, TestResponse } from '../api/opsApi';

interface Props {
  api: OpsApi;
}

export const TestConsole: React.FC<Props> = ({ api }) => {
  const styles = getStyles();

  const [team, setTeam] = useState('quant');
  const [prompt, setPrompt] = useState('Test health check prompt');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<TestResponse | null>(null);

  const runTest = async () => {
    setLoading(true);
    setResult(null);

    try {
      const response = await api.runTest({
        team,
        prompt,
        max_tokens: 10
      });
      setResult(response);
    } catch (err) {
      setResult({
        correlation_id: 'error',
        team,
        status: 'error',
        latency_ms: 0,
        error: err instanceof Error ? err.message : 'Unknown error'
      });
    } finally {
      setLoading(false);
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'success': return '#73bf69';
      case 'timeout': return '#ff9830';
      case 'error': return '#ff5555';
      default: return '#8e8e8e';
    }
  };

  return (
    <div className={styles.container}>
      <h3 className={styles.title}>Test Console</h3>

      <div className={styles.form}>
        <div className={styles.field}>
          <label>Team</label>
          <select value={team} onChange={e => setTeam(e.target.value)}>
            <option value="quant">Quantization</option>
            <option value="finetune">Fine-tuning</option>
            <option value="eval">Evaluation</option>
          </select>
        </div>

        <div className={styles.field}>
          <label>Prompt</label>
          <input
            type="text"
            value={prompt}
            onChange={e => setPrompt(e.target.value)}
            placeholder="Test prompt..."
          />
        </div>

        <button
          className={styles.button}
          onClick={runTest}
          disabled={loading}
        >
          {loading ? 'Running...' : 'Run Test'}
        </button>
      </div>

      {result && (
        <div className={styles.result}>
          <div className={styles.resultHeader}>
            <span
              className={styles.statusBadge}
              style={{ backgroundColor: getStatusColor(result.status) }}
            >
              {result.status}
            </span>
            <span className={styles.latency}>{result.latency_ms.toFixed(0)}ms</span>
          </div>
          <div className={styles.correlationId}>
            Correlation ID: <code>{result.correlation_id}</code>
          </div>
          {result.error && (
            <div className={styles.errorMessage}>{result.error}</div>
          )}
          {result.response && (
            <pre className={styles.responseJson}>
              {JSON.stringify(result.response, null, 2)}
            </pre>
          )}
        </div>
      )}
    </div>
  );
};

const getStyles = () => ({
  container: css``,
  title: css`
    margin-bottom: 12px;
    font-size: 14px;
  `,
  form: css`
    display: flex;
    gap: 12px;
    align-items: flex-end;
    margin-bottom: 16px;
  `,
  field: css`
    display: flex;
    flex-direction: column;
    gap: 4px;

    label {
      font-size: 12px;
      color: #8e8e8e;
    }

    select, input {
      padding: 8px 12px;
      background: #333;
      border: 1px solid #444;
      border-radius: 4px;
      color: #fff;
    }

    input {
      width: 300px;
    }
  `,
  button: css`
    padding: 8px 16px;
    background: #3871dc;
    border: none;
    border-radius: 4px;
    color: #fff;
    cursor: pointer;

    &:hover {
      background: #4c85ed;
    }

    &:disabled {
      background: #444;
      cursor: not-allowed;
    }
  `,
  result: css`
    background: #252525;
    padding: 12px;
    border-radius: 4px;
  `,
  resultHeader: css`
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 8px;
  `,
  statusBadge: css`
    padding: 4px 8px;
    border-radius: 4px;
    font-size: 12px;
    text-transform: uppercase;
  `,
  latency: css`
    color: #8e8e8e;
    font-size: 14px;
  `,
  correlationId: css`
    font-size: 12px;
    color: #8e8e8e;
    margin-bottom: 8px;

    code {
      background: #333;
      padding: 2px 6px;
      border-radius: 2px;
    }
  `,
  errorMessage: css`
    color: #ff5555;
    font-size: 13px;
    margin-top: 8px;
  `,
  responseJson: css`
    background: #1a1a1a;
    padding: 12px;
    border-radius: 4px;
    font-size: 12px;
    overflow: auto;
    max-height: 150px;
  `
});
