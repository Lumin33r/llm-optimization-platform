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
}
