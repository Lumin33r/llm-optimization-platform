# services/test-harness/harness.py
import asyncio
import httpx
import json
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass, field
from contextlib import contextmanager

# Optional OTEL — works without it for local runs
try:
    from opentelemetry import trace, metrics
    from opentelemetry.propagate import inject as otel_inject
    tracer = trace.get_tracer("test-harness")
    meter = metrics.get_meter("test-harness")
    harness_requests_total = meter.create_counter("lab_harness_requests_total", description="Total harness requests")
    harness_pass_total = meter.create_counter("lab_harness_pass_total", description="Total passed validations")
    harness_fail_total = meter.create_counter("lab_harness_fail_total", description="Total failed validations")
    harness_latency = meter.create_histogram("lab_harness_latency_ms", description="Request latency")
    HAS_OTEL = True
except ImportError:
    HAS_OTEL = False
    tracer = None

    @contextmanager
    def _noop_span(name):
        class _Span:
            def set_attribute(self, k, v): pass
        yield _Span()

    def otel_inject(headers): pass


@dataclass
class HarnessResult:
    prompt_id: str
    scenario_id: str
    dataset_id: str
    run_id: str
    team: str
    variant: str
    passed: bool
    latency_ms: float
    error: Optional[str] = None
    response_preview: Optional[str] = None
    # Phase 7 extended metrics
    tokens_generated: int = 0
    tokens_per_second: float = 0.0
    category: Optional[str] = None
    model_version: Optional[str] = None
    quality_scores: Optional[Dict] = None
    # Phase 8 comparison fields
    baseline_response: Optional[str] = None
    baseline_latency_ms: float = 0.0
    baseline_passed: Optional[bool] = None


class TestHarness:
    """Execute promptsets against endpoints with observability."""

    def __init__(
        self,
        gateway_url: str,
        run_id: str,
        concurrency: int = 10,
        compare_baseline: bool = False,
        baseline_team: str = "quant",
    ):
        self.gateway_url = gateway_url
        self.run_id = run_id
        self.concurrency = concurrency
        self.semaphore = asyncio.Semaphore(concurrency)
        self.compare_baseline = compare_baseline
        self.baseline_team = baseline_team

    async def execute_prompt(
        self,
        prompt: Dict,
        team: str,
        variant: Optional[str] = None
    ) -> HarnessResult:
        """Execute single prompt with telemetry."""

        async with self.semaphore:
            span_ctx = tracer.start_as_current_span("harness.execute") if HAS_OTEL else _noop_span("harness.execute")
            with span_ctx as span:
                # Set span attributes
                span.set_attribute("lab.promptset.id", prompt.get("dataset_id", "unknown"))
                span.set_attribute("lab.scenario.id", prompt.get("scenario_id", "unknown"))
                span.set_attribute("lab.dataset.id", prompt.get("dataset_id", "unknown"))
                span.set_attribute("lab.run.id", self.run_id)
                span.set_attribute("lab.prompt.id", prompt["prompt_id"])
                span.set_attribute("lab.target.team", team)

                if variant:
                    span.set_attribute("lab.model.variant.id", variant)

                # Prepare headers with trace propagation
                headers = {"Content-Type": "application/json"}
                otel_inject(headers)

                # Add routing headers
                headers["X-Target-Team"] = team
                if variant:
                    headers["X-Model-Variant"] = variant

                start_time = asyncio.get_event_loop().time()

                try:
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        response = await client.post(
                            f"{self.gateway_url}/api/{team}/predict",
                            json={"prompt": prompt["prompt"], "max_tokens": prompt.get("max_tokens", 100)},
                            headers=headers
                        )
                        response.raise_for_status()
                        result = response.json()

                    latency_ms = (asyncio.get_event_loop().time() - start_time) * 1000

                    # Validate response
                    passed = self._validate_response(prompt, result)

                    # Extract extended metrics (Phase 7)
                    response_text = str(result.get("output") or result.get("response", ""))
                    tokens_generated = result.get("tokens_generated", len(response_text.split()))
                    tokens_per_second = (tokens_generated / (latency_ms / 1000)) if latency_ms > 0 else 0
                    model_version = result.get("model_version", "unknown")
                    category = prompt.get("category")

                    # Record metrics
                    labels = {
                        "scenario_id": prompt.get("scenario_id", "unknown"),
                        "team": team,
                        "bucket": prompt.get("bucket", "unknown")
                    }
                    if HAS_OTEL:
                        harness_requests_total.add(1, labels)
                        harness_latency.record(latency_ms, labels)

                    if passed:
                        if HAS_OTEL:
                            harness_pass_total.add(1, labels)
                    else:
                        if HAS_OTEL:
                            harness_fail_total.add(1, labels)

                    # Phase 8: Comparison mode — send same prompt to baseline
                    baseline_response = None
                    baseline_latency = 0.0
                    baseline_passed = None
                    if self.compare_baseline:
                        try:
                            bl_start = asyncio.get_event_loop().time()
                            async with httpx.AsyncClient(timeout=30.0) as bl_client:
                                bl_resp = await bl_client.post(
                                    f"{self.gateway_url}/api/{self.baseline_team}/predict",
                                    json={"prompt": prompt["prompt"], "max_tokens": prompt.get("max_tokens", 100)},
                                    headers={"Content-Type": "application/json"},
                                )
                                bl_resp.raise_for_status()
                                bl_result = bl_resp.json()
                            baseline_latency = (asyncio.get_event_loop().time() - bl_start) * 1000
                            baseline_response = str(bl_result.get("output") or bl_result.get("response", ""))[:200]
                            baseline_passed = self._validate_response(prompt, bl_result)
                        except Exception:
                            baseline_response = "[baseline error]"

                    return HarnessResult(
                        prompt_id=prompt["prompt_id"],
                        scenario_id=prompt.get("scenario_id", "unknown"),
                        dataset_id=prompt.get("dataset_id", "unknown"),
                        run_id=self.run_id,
                        team=team,
                        variant=variant or "default",
                        passed=passed,
                        latency_ms=latency_ms,
                        response_preview=response_text[:200],
                        tokens_generated=tokens_generated,
                        tokens_per_second=round(tokens_per_second, 1),
                        category=category,
                        model_version=model_version,
                        baseline_response=baseline_response,
                        baseline_latency_ms=baseline_latency,
                        baseline_passed=baseline_passed,
                    )

                except Exception as e:
                    latency_ms = (asyncio.get_event_loop().time() - start_time) * 1000
                    span.set_attribute("error.type", type(e).__name__)
                    span.set_attribute("error.message", str(e)[:200])

                    harness_fail_total.add(1, {"scenario_id": prompt.get("scenario_id", "unknown"), "team": team}) if HAS_OTEL else None

                    return HarnessResult(
                        prompt_id=prompt["prompt_id"],
                        scenario_id=prompt.get("scenario_id", "unknown"),
                        dataset_id=prompt.get("dataset_id", "unknown"),
                        run_id=self.run_id,
                        team=team,
                        variant=variant or "default",
                        passed=False,
                        latency_ms=latency_ms,
                        error=str(e)
                    )

    def _validate_response(self, prompt: Dict, result: Dict) -> bool:
        """Validate response against expected criteria."""
        # Gateway returns "output", fall back to "response" for compatibility
        response_text = str(result.get("output") or result.get("response", "")).lower()

        # Check expected_contains (skip if None or missing)
        expected = prompt.get("expected_contains")
        if expected:
            for term in expected:
                if term.lower() not in response_text:
                    return False

        # Check expected_format
        if prompt.get("expected_format") == "json":
            try:
                json.loads(result.get("response", ""))
            except json.JSONDecodeError:
                return False

        return True

    async def run_promptset(
        self,
        prompts: List[Dict],
        team: str,
        variant: Optional[str] = None
    ) -> List[HarnessResult]:
        """Run full promptset against endpoint."""

        tasks = [
            self.execute_prompt(p, team, variant)
            for p in prompts
        ]

        return await asyncio.gather(*tasks)


# CLI entrypoint
async def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--promptset", required=True, help="Path to promptset.jsonl")
    parser.add_argument("--gateway", default="http://gateway.platform.svc", help="Gateway URL")
    parser.add_argument("--team", required=True, help="Target team")
    parser.add_argument("--variant", help="Model variant")
    parser.add_argument("--concurrency", type=int, default=10, help="Concurrent requests")
    parser.add_argument("--run-id", default=datetime.now().strftime("run-%Y%m%d-%H%M%S"))
    parser.add_argument("--compare-baseline", action="store_true", help="Also send each prompt to baseline for comparison")
    parser.add_argument("--baseline-team", default="quant", help="Team to use as baseline for comparison")
    args = parser.parse_args()

    # Load promptset
    prompts = []
    with open(args.promptset) as f:
        for line in f:
            prompts.append(json.loads(line))

    # Run harness
    harness = TestHarness(
        gateway_url=args.gateway,
        run_id=args.run_id,
        concurrency=args.concurrency,
        compare_baseline=args.compare_baseline,
        baseline_team=args.baseline_team,
    )

    results = await harness.run_promptset(prompts, args.team, args.variant)

    # Summary
    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)
    avg_latency = sum(r.latency_ms for r in results) / len(results) if results else 0
    avg_tps = sum(r.tokens_per_second for r in results) / len(results) if results else 0

    print(f"\n{'='*60}")
    print(f"Run ID: {args.run_id}")
    print(f"Team: {args.team} | Variant: {args.variant or 'default'}")
    print(f"Total: {len(results)}, Passed: {passed}, Failed: {failed}")
    print(f"Pass Rate: {passed/len(results)*100:.1f}%")
    print(f"Avg Latency: {avg_latency:.1f}ms")
    print(f"Avg Tokens/sec: {avg_tps:.1f}")

    # Category breakdown
    categories = {}
    for r in results:
        cat = r.category or "uncategorized"
        if cat not in categories:
            categories[cat] = {"total": 0, "passed": 0}
        categories[cat]["total"] += 1
        if r.passed:
            categories[cat]["passed"] += 1

    if any(r.category for r in results):
        print(f"\nCategory Breakdown:")
        for cat, stats in sorted(categories.items()):
            rate = stats["passed"] / stats["total"] * 100 if stats["total"] else 0
            print(f"  {cat:20s}: {stats['passed']}/{stats['total']} ({rate:.0f}%)")

    # Comparison summary
    if args.compare_baseline:
        bl_passed = sum(1 for r in results if r.baseline_passed)
        bl_avg_lat = sum(r.baseline_latency_ms for r in results) / len(results) if results else 0
        print(f"\n--- Baseline Comparison ---")
        print(f"Baseline Pass Rate: {bl_passed/len(results)*100:.1f}%")
        print(f"Baseline Avg Latency: {bl_avg_lat:.1f}ms")
        print(f"Delta Pass Rate: {(passed - bl_passed)/len(results)*100:+.1f}%")
        print(f"Latency Speedup: {bl_avg_lat/avg_latency:.2f}x" if avg_latency > 0 else "")

    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
