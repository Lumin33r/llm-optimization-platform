export interface ServiceInfo {
  name: string;
  namespace: string;
  url: string;
  version: string;
  deployed_at?: string;
  image_tag?: string;
}

export interface HealthStatus {
  team: string;
  status: "healthy" | "degraded" | "unhealthy" | "unknown";
  ready_pods: number;
  total_pods: number;
  last_check: string;
}

export interface PlatformStats {
  total_requests_24h: number;
  error_rate_percent: number;
  p50_latency_ms: number;
  p95_latency_ms: number;
  p99_latency_ms: number;
  requests_by_team: Record<string, number>;
  errors_by_team: Record<string, number>;
  window_start: string;
  window_end: string;
}

export interface TestRequest {
  team: string;
  prompt?: string;
  max_tokens?: number;
}

export interface TestResponse {
  correlation_id: string;
  team: string;
  status: "success" | "error" | "timeout";
  latency_ms: number;
  response?: Record<string, unknown>;
  error?: string;
}

// --- Data Engine / Harness types ---

export interface PromptsetInfo {
  promptset_id: string;
  scenario_id: string;
  dataset_id: string;
  prompt_count: number;
  created_at: string;
  version: string;
  checksum: string;
}

export interface HarnessRunRequest {
  promptset: string;
  team: string;
  variant?: string;
  concurrency: number;
  max_prompts?: number;
}

export interface HarnessRunSummary {
  run_id: string;
  status: "pending" | "running" | "completed" | "failed";
  promptset: string;
  team: string;
  variant?: string;
  total: number;
  passed: number;
  failed: number;
  pass_rate: number;
  avg_latency_ms: number;
  avg_tokens_per_second: number;
  category_breakdown?: Record<string, { total: number; passed: number }>;
  started_at: string;
  completed_at?: string;
  errors: string[];
}

export interface ScoreRequest {
  prompt: string;
  response: string;
  threshold_profile?: string;
}

export interface ScoreResponse {
  eval_id: string;
  coherence: number;
  helpfulness: number;
  factuality: number;
  toxicity: number;
  pass_threshold: boolean;
  reasoning?: string;
}

export class OpsApi {
  constructor(private baseUrl: string) {}

  async getServices(): Promise<ServiceInfo[]> {
    const response = await fetch(`${this.baseUrl}/ops/services`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }

  async getHealth(): Promise<HealthStatus[]> {
    const response = await fetch(`${this.baseUrl}/ops/health`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }

  async getStats(): Promise<PlatformStats> {
    const response = await fetch(`${this.baseUrl}/ops/stats`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }

  async runTest(request: TestRequest): Promise<TestResponse> {
    const response = await fetch(`${this.baseUrl}/ops/test`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }

  // --- Data Engine / Harness methods ---

  async getPromptsets(): Promise<PromptsetInfo[]> {
    const response = await fetch(`${this.baseUrl}/ops/promptsets`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }

  async startHarnessRun(request: HarnessRunRequest): Promise<HarnessRunSummary> {
    const response = await fetch(`${this.baseUrl}/ops/harness/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }

  async getHarnessRuns(): Promise<HarnessRunSummary[]> {
    const response = await fetch(`${this.baseUrl}/ops/harness/runs`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }

  async getHarnessRun(runId: string): Promise<HarnessRunSummary> {
    const response = await fetch(`${this.baseUrl}/ops/harness/runs/${runId}`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }

  async scoreResponse(request: ScoreRequest): Promise<ScoreResponse> {
    const response = await fetch(`${this.baseUrl}/ops/score`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }
}
