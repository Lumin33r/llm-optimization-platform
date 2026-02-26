/**
 * TypeScript interfaces for the LLM Platform Ops panel plugin.
 */

export interface OpsPanelOptions {
  gatewayUrl: string;
  refreshInterval: number; // seconds
}

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
  status: 'healthy' | 'degraded' | 'unhealthy' | 'unknown';
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
  status: 'success' | 'error' | 'timeout';
  latency_ms: number;
  response?: Record<string, unknown>;
  error?: string;
}
