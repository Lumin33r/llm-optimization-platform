# services/test-harness/harness.py
import asyncio
import httpx
import json
from datetime import datetime
from typing import List, Dict, Optional
from dataclasses import dataclass
from opentelemetry import trace, metrics
from opentelemetry.propagate import inject

tracer = trace.get_tracer("test-harness")
meter = metrics.get_meter("test-harness")

# Metrics
harness_requests_total = meter.create_counter(
    "lab_harness_requests_total",
    description="Total harness requests"
)
harness_pass_total = meter.create_counter(
    "lab_harness_pass_total",
    description="Total passed validations"
)
harness_fail_total = meter.create_counter(
    "lab_harness_fail_total",
    description="Total failed validations"
)
harness_latency = meter.create_histogram(
    "lab_harness_latency_ms",
    description="Request latency"
)


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


class TestHarness:
    """Execute promptsets against endpoints with observability."""

    def __init__(
        self,
        gateway_url: str,
        run_id: str,
        concurrency: int = 10
    ):
        self.gateway_url = gateway_url
        self.run_id = run_id
        self.concurrency = concurrency
        self.semaphore = asyncio.Semaphore(concurrency)

    async def execute_prompt(
        self,
        prompt: Dict,
        team: str,
        variant: Optional[str] = None
    ) -> HarnessResult:
        """Execute single prompt with telemetry."""

        async with self.semaphore:
            with tracer.start_as_current_span("harness.execute") as span:
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
                inject(headers)

                # Add routing headers
                headers["X-Target-Team"] = team
                if variant:
                    headers["X-Model-Variant"] = variant

                start_time = asyncio.get_event_loop().time()

                try:
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        response = await client.post(
                            f"{self.gateway_url}/predict",
                            json={"prompt": prompt["prompt"], "max_tokens": prompt.get("max_tokens", 100)},
                            headers=headers
                        )
                        response.raise_for_status()
                        result = response.json()

                    latency_ms = (asyncio.get_event_loop().time() - start_time) * 1000

                    # Validate response
                    passed = self._validate_response(prompt, result)

                    # Record metrics
                    labels = {
                        "scenario_id": prompt.get("scenario_id", "unknown"),
                        "team": team,
                        "bucket": prompt.get("bucket", "unknown")
                    }
                    harness_requests_total.add(1, labels)
                    harness_latency.record(latency_ms, labels)

                    if passed:
                        harness_pass_total.add(1, labels)
                    else:
                        harness_fail_total.add(1, labels)

                    return HarnessResult(
                        prompt_id=prompt["prompt_id"],
                        scenario_id=prompt.get("scenario_id", "unknown"),
                        dataset_id=prompt.get("dataset_id", "unknown"),
                        run_id=self.run_id,
                        team=team,
                        variant=variant or "default",
                        passed=passed,
                        latency_ms=latency_ms,
                        response_preview=str(result.get("response", ""))[:200]
                    )

                except Exception as e:
                    latency_ms = (asyncio.get_event_loop().time() - start_time) * 1000
                    span.set_attribute("error.type", type(e).__name__)
                    span.set_attribute("error.message", str(e)[:200])

                    harness_fail_total.add(1, {"scenario_id": prompt.get("scenario_id", "unknown"), "team": team})

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
        response_text = str(result.get("response", "")).lower()

        # Check expected_contains
        if "expected_contains" in prompt:
            for expected in prompt["expected_contains"]:
                if expected.lower() not in response_text:
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
        concurrency=args.concurrency
    )

    results = await harness.run_promptset(prompts, args.team, args.variant)

    # Summary
    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)
    avg_latency = sum(r.latency_ms for r in results) / len(results) if results else 0

    print(f"Run ID: {args.run_id}")
    print(f"Total: {len(results)}, Passed: {passed}, Failed: {failed}")
    print(f"Pass Rate: {passed/len(results)*100:.1f}%")
    print(f"Avg Latency: {avg_latency:.1f}ms")


if __name__ == "__main__":
    asyncio.run(main())
