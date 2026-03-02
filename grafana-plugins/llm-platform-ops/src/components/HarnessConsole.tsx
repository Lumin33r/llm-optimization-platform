import { css } from '@emotion/css';
import React, { useEffect, useState } from 'react';
import { BenchmarkRunSummary, HarnessRunSummary, OpsApi, PromptsetInfo } from '../api/opsApi';

interface Props {
  api: OpsApi;
}

export const HarnessConsole: React.FC<Props> = ({ api }) => {
  const styles = getStyles();

  const [promptsets, setPromptsets] = useState<PromptsetInfo[]>([]);
  const [runs, setRuns] = useState<HarnessRunSummary[]>([]);
  const [selectedPromptset, setSelectedPromptset] = useState('');
  const [team, setTeam] = useState('quant');
  const [concurrency, setConcurrency] = useState(5);
  const [maxPrompts, setMaxPrompts] = useState<number | undefined>(10);
  const [launching, setLaunching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showHelp, setShowHelp] = useState(false);
  const [benchmarkRunning, setBenchmarkRunning] = useState(false);
  const [benchmarkResult, setBenchmarkResult] = useState<BenchmarkRunSummary | null>(null);

  // Load promptsets and runs on mount
  useEffect(() => {
    const load = async () => {
      try {
        const [ps, rs] = await Promise.all([
          api.getPromptsets(),
          api.getHarnessRuns(),
        ]);
        setPromptsets(ps);
        setRuns(rs);
        setError(null);
        if (ps.length > 0 && !selectedPromptset) {
            setSelectedPromptset(ps[0].dataset_id || 'canary');
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load');
      }
    };
    load();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Poll running jobs every 5s
  useEffect(() => {
    const hasRunning = runs.some(r => r.status === 'running' || r.status === 'pending');
    const hasBenchmarkRunning = benchmarkResult && (benchmarkResult.status === 'running' || benchmarkResult.status === 'pending');
    if (!hasRunning && !hasBenchmarkRunning) return;

    const interval = setInterval(async () => {
      try {
        const updated = await api.getHarnessRuns();
        setRuns(updated);
        if (hasBenchmarkRunning && benchmarkResult) {
          const bm = await api.getBenchmarkRun(benchmarkResult.benchmark_id);
          setBenchmarkResult(bm);
          if (bm.status === 'completed' || bm.status === 'failed') {
            setBenchmarkRunning(false);
          }
        }
      } catch { /* ignore */ }
    }, 5000);

    return () => clearInterval(interval);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runs.some(r => r.status === 'running' || r.status === 'pending'), benchmarkResult?.status]);

  const startRun = async () => {
    setLaunching(true);
    setError(null);
    try {
      const run = await api.startHarnessRun({
        promptset: selectedPromptset,
        team,
        concurrency,
        max_prompts: maxPrompts,
      });
      setRuns(prev => [run, ...prev]);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start run');
    } finally {
      setLaunching(false);
    }
  };

  const startBenchmark = async () => {
    setBenchmarkRunning(true);
    setError(null);
    setBenchmarkResult(null);
    try {
      const result = await api.startBenchmark({ concurrency });
      setBenchmarkResult(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to start benchmark');
      setBenchmarkRunning(false);
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'completed': return '#73bf69';
      case 'running':   return '#3871dc';
      case 'pending':   return '#ff9830';
      case 'failed':    return '#ff5555';
      default:          return '#8e8e8e';
    }
  };

// Use full dataset_id as the promptset selector (matches directory or resolved by data-engine)
    const uniqueNames = [...new Set(promptsets.map(p => p.dataset_id))];

  return (
    <div className={styles.container}>
      <div className={styles.titleRow}>
        <h3 className={styles.title}>Test Harness</h3>
        <button className={styles.helpToggle} onClick={() => setShowHelp(!showHelp)} title="Toggle help">{showHelp ? '✕' : '?'}</button>
      </div>
      {showHelp && (
        <div className={styles.helpBox}>
          <p><strong>Test Harness</strong> runs batches of prompts against the LLM and validates responses automatically. It is the primary tool for measuring model quality and performance.</p>
          <h4>Controls</h4>
          <ul>
            <li><strong>Promptset:</strong> Which prompt dataset to run. <em>canary</em> (50 short factual prompts with expected answers) tests correctness. <em>performance</em> (100 longer prompts without expected answers) tests throughput and latency under load.</li>
            <li><strong>Team:</strong> Which gateway route (<code>/api/quant/predict</code>, etc.) to send requests through.</li>
            <li><strong>Concurrency:</strong> How many prompts are sent to the model <em>in parallel</em>. Low (1–2) = sequential, gentle on GPU. High (20–50) = stress test, increases latency but reduces total wall-clock time. Default of 5 is a good balance.</li>
            <li><strong>Max Prompts:</strong> Cap on how many prompts to use from the set. Leave blank to run all. Use a small number (3–10) for quick smoke tests.</li>
          </ul>
          <h4>Results Table</h4>
          <ul>
            <li><strong>Run ID:</strong> Unique identifier for each harness run (last 10 chars shown).</li>
            <li><strong>Status:</strong> <span style={{color:'#ff9830'}}>PENDING</span> → <span style={{color:'#3871dc'}}>RUNNING</span> → <span style={{color:'#73bf69'}}>COMPLETED</span>. The table auto-polls every 5 seconds while a run is active.</li>
            <li><strong>Total:</strong> Number of prompts actually sent (may be less than promptset size if Max Prompts is set).</li>
            <li><strong>Passed:</strong> Prompts where the model's response <em>contained all expected keywords</em>. For canary prompts, each has an <code>expected_contains</code> list (e.g., "What is 2+2?" expects "4" in the response). Performance prompts have no expected answers, so they always pass if the model responds.</li>
            <li><strong>Failed:</strong> Prompts where validation did not pass. The model responded, but the answer didn't contain the expected keyword(s). This does NOT mean the request errored — it means the model's answer was wrong or incomplete.</li>
            <li><strong>Pass Rate:</strong> <code>passed ÷ total × 100</code>. A quality score. 100% on canary means the model correctly answers all factual questions. Less than 100% means some answers were incorrect or missing expected content. Use this to compare model variants or detect regressions after fine-tuning.</li>
            <li><strong>Avg Latency:</strong> Mean round-trip time per prompt in milliseconds. Affected by model load, prompt length, concurrency, and GPU utilization.</li>
          </ul>
          <h4>Error Details</h4>
          <p>If a run shows errors below the table, these are per-prompt error messages (e.g., timeouts, connection failures, or validation failures). The format is <code>prompt-id: error message</code>.</p>
        </div>
      )}

      {/* Launch Form */}
      <div className={styles.form}>
        <div className={styles.field}>
          <label>Promptset</label>
          <select
            value={selectedPromptset}
            onChange={e => setSelectedPromptset(e.target.value)}
          >
            {uniqueNames.map(name => (
              <option key={name} value={name}>{name}</option>
            ))}
          </select>
        </div>

        <div className={styles.field}>
          <label>Team</label>
          <select value={team} onChange={e => setTeam(e.target.value)}>
            <option value="quant">Quantization</option>
            <option value="finetune">Fine-tuning</option>
            <option value="eval">Evaluation</option>
          </select>
        </div>

        <div className={styles.field}>
          <label>Concurrency</label>
          <input
            type="number"
            min={1}
            max={50}
            value={concurrency}
            onChange={e => setConcurrency(parseInt(e.target.value) || 5)}
            style={{ width: 60 }}
          />
        </div>

        <div className={styles.field}>
          <label>Max Prompts</label>
          <input
            type="number"
            min={1}
            max={5000}
            value={maxPrompts ?? ''}
            onChange={e => setMaxPrompts(e.target.value ? parseInt(e.target.value) : undefined)}
            placeholder="All"
            style={{ width: 70 }}
          />
        </div>

        <button
          className={styles.button}
          onClick={startRun}
          disabled={launching || !selectedPromptset}
        >
          {launching ? 'Starting...' : 'Run Harness'}
        </button>

        <button
          className={styles.benchmarkButton}
          onClick={startBenchmark}
          disabled={benchmarkRunning || launching}
          title="Run all 3 teams (quant, finetune, eval) with 700 benchmark prompts"
        >
          {benchmarkRunning ? `Benchmark ${benchmarkResult ? Object.values(benchmarkResult.team_status).filter(s => s === 'completed').length + '/3' : '...'}` : 'Run Benchmark'}
        </button>
      </div>

      {error && <div className={styles.errorMessage}>{error}</div>}

      {/* Benchmark Results */}
      {benchmarkResult && (
        <div className={styles.benchmarkBox}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
            <strong style={{ color: '#ff9830' }}>Benchmark: {benchmarkResult.benchmark_id.slice(-10)}</strong>
            <span
              className={styles.statusBadge}
              style={{ backgroundColor: getStatusColor(benchmarkResult.status) }}
            >
              {benchmarkResult.status}
            </span>
          </div>
          <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
            {Object.entries(benchmarkResult.team_status).map(([team, status]) => (
              <span key={team} style={{
                background: '#333',
                padding: '3px 8px',
                borderRadius: 4,
                fontSize: 11,
                color: status === 'completed' ? '#73bf69' : status === 'running' ? '#3871dc' : status === 'failed' ? '#ff5555' : '#aaa',
              }}>
                {team}: {status}
              </span>
            ))}
          </div>
          {benchmarkResult.summary && Object.keys(benchmarkResult.summary).length > 0 && (
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Team</th>
                  <th>Total</th>
                  <th>Passed</th>
                  <th>Failed</th>
                  <th>Pass Rate</th>
                  <th>Avg Latency</th>
                  <th>Tok/s</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(benchmarkResult.summary).map(([team, s]) => (
                  <tr key={team}>
                    <td style={{ fontWeight: 500 }}>{team}</td>
                    <td>{s.total}</td>
                    <td style={{ color: '#73bf69' }}>{s.passed}</td>
                    <td style={{ color: s.failed > 0 ? '#ff5555' : '#8e8e8e' }}>{s.failed}</td>
                    <td>{s.pass_rate}%</td>
                    <td>{s.avg_latency_ms.toFixed(0)}ms</td>
                    <td>{s.avg_tokens_per_second ? s.avg_tokens_per_second.toFixed(1) : '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* Promptset Info */}
      {promptsets.length > 0 && (
        <div className={styles.infoBar}>
          {promptsets.map(p => (
            <span key={p.promptset_id} className={styles.infoBadge}>
              {p.dataset_id}: {p.prompt_count} prompts
            </span>
          ))}
        </div>
      )}

      {/* Runs Table */}
      {runs.length > 0 && (
        <div className={styles.runsSection}>
          <h4 className={styles.subtitle}>Recent Runs</h4>
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Run ID</th>
                <th>Status</th>
                <th>Promptset</th>
                <th>Team</th>
                <th>Total</th>
                <th>Passed</th>
                <th>Failed</th>
                <th>Pass Rate</th>
                <th>Avg Latency</th>
                <th>Tok/s</th>
                <th>Started</th>
              </tr>
            </thead>
            <tbody>
              {runs.slice(0, 10).map(run => (
                <tr key={run.run_id}>
                  <td><code>{run.run_id.slice(-10)}</code></td>
                  <td>
                    <span
                      className={styles.statusBadge}
                      style={{ backgroundColor: getStatusColor(run.status) }}
                    >
                      {run.status}
                    </span>
                  </td>
                  <td>{run.promptset}</td>
                  <td>{run.team}</td>
                  <td>{run.total}</td>
                  <td style={{ color: '#73bf69' }}>{run.passed}</td>
                  <td style={{ color: run.failed > 0 ? '#ff5555' : '#8e8e8e' }}>{run.failed}</td>
                  <td>{run.pass_rate}%</td>
                  <td>{run.avg_latency_ms.toFixed(0)}ms</td>
                  <td>{run.avg_tokens_per_second ? run.avg_tokens_per_second.toFixed(1) : '-'}</td>
                  <td>{new Date(run.started_at).toLocaleTimeString()}</td>
                </tr>
              ))}
            </tbody>
          </table>

          {/* Show category breakdown for completed runs */}
          {runs.filter(r => r.status === 'completed' && r.category_breakdown).slice(0, 2).map(run => (
            <div key={`cat-${run.run_id}`} className={styles.errorBox} style={{ background: '#1a2a1a', borderColor: '#224422' }}>
              <strong style={{ color: '#73bf69' }}>{run.run_id.slice(-10)} — Category Breakdown:</strong>
              <table className={styles.table} style={{ marginTop: 4 }}>
                <thead><tr><th>Category</th><th>Passed</th><th>Total</th><th>Rate</th></tr></thead>
                <tbody>
                  {Object.entries(run.category_breakdown!).map(([cat, s]) => (
                    <tr key={cat}>
                      <td>{cat}</td>
                      <td style={{ color: '#73bf69' }}>{(s as any).passed}</td>
                      <td>{(s as any).total}</td>
                      <td>{((s as any).total > 0 ? ((s as any).passed / (s as any).total * 100).toFixed(0) : 0)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}

          {/* Show errors for failed runs */}
          {runs.filter(r => r.errors.length > 0).slice(0, 3).map(run => (
            <div key={run.run_id} className={styles.errorBox}>
              <strong>{run.run_id.slice(-10)}:</strong>
              {run.errors.slice(0, 5).map((e, i) => (
                <div key={i} className={styles.errorLine}>{e}</div>
              ))}
            </div>
          ))}
        </div>
      )}
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
    h4 { margin: 10px 0 4px; font-size: 12px; color: #7eb3ff; }
    ul { margin: 4px 0 6px 16px; padding: 0; }
    li { margin-bottom: 3px; }
    em { color: #a8c8ff; font-style: normal; }
    code { background: #2a3a55; padding: 1px 5px; border-radius: 3px; font-size: 11px; }
  `,
  subtitle: css`
    margin: 12px 0 8px;
    font-size: 13px;
    color: #ccc;
  `,
  form: css`
    display: flex;
    gap: 12px;
    align-items: flex-end;
    margin-bottom: 12px;
    flex-wrap: wrap;
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
  `,
  button: css`
    padding: 8px 16px;
    background: #56a64b;
    border: none;
    border-radius: 4px;
    color: #fff;
    cursor: pointer;
    font-weight: 500;

    &:hover {
      background: #6bc160;
    }

    &:disabled {
      background: #444;
      cursor: not-allowed;
    }
  `,
  benchmarkButton: css`
    padding: 8px 16px;
    background: #c05a1c;
    border: none;
    border-radius: 4px;
    color: #fff;
    cursor: pointer;
    font-weight: 600;
    font-size: 12px;

    &:hover {
      background: #e06e2c;
    }

    &:disabled {
      background: #555;
      cursor: not-allowed;
    }
  `,
  benchmarkBox: css`
    background: #1a1a2a;
    border: 1px solid #3a3a55;
    border-radius: 4px;
    padding: 10px;
    margin-bottom: 12px;
    font-size: 12px;
  `,
  errorMessage: css`
    color: #ff5555;
    font-size: 13px;
    margin-bottom: 8px;
  `,
  infoBar: css`
    display: flex;
    gap: 8px;
    margin-bottom: 12px;
  `,
  infoBadge: css`
    background: #333;
    padding: 4px 8px;
    border-radius: 4px;
    font-size: 12px;
    color: #aaa;
  `,
  runsSection: css`
    margin-top: 8px;
  `,
  table: css`
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;

    th, td {
      padding: 6px 8px;
      text-align: left;
      border-bottom: 1px solid #333;
    }

    th {
      color: #8e8e8e;
      font-weight: 500;
    }

    code {
      background: #333;
      padding: 2px 4px;
      border-radius: 2px;
      font-size: 11px;
    }
  `,
  statusBadge: css`
    padding: 2px 6px;
    border-radius: 3px;
    font-size: 11px;
    text-transform: uppercase;
    color: #fff;
  `,
  errorBox: css`
    background: #2a1a1a;
    border: 1px solid #442222;
    border-radius: 4px;
    padding: 8px;
    margin-top: 8px;
    font-size: 12px;
  `,
  errorLine: css`
    color: #ff8888;
    font-size: 11px;
    margin-top: 4px;
    padding-left: 8px;
  `,
});
