"""Data Engine API — serves promptsets and runs test harness."""

import json
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel

# Add parent directory so we can import the harness
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "test-harness"))
from harness import TestHarness, HarnessResult  # noqa: E402

app = FastAPI(title="Data Engine API", version="1.0.0")

# --------------- Config ---------------
DATA_DIR = Path(os.getenv("DATA_DIR", "/app/data/promptsets"))
GATEWAY_URL = os.getenv("GATEWAY_URL", "http://gateway.platform.svc.cluster.local:8000")

# In-memory run store (survives for pod lifetime)
_runs: Dict[str, dict] = {}
_benchmarks: Dict[str, dict] = {}

# Benchmark team → promptset mapping
BENCHMARK_MAP = {
    "quant": "benchmark-quant",
    "finetune": "benchmark-finetune",
    "eval": "benchmark-eval",
}


# --------------- Models ---------------
class PromptsetInfo(BaseModel):
    promptset_id: str
    scenario_id: str
    dataset_id: str
    prompt_count: int
    created_at: str
    version: str
    checksum: str


class HarnessRunRequest(BaseModel):
    promptset: str        # e.g. "canary" or "performance"
    team: str             # e.g. "quant", "finetune", "eval"
    variant: Optional[str] = None
    concurrency: int = 5
    max_prompts: Optional[int] = None  # limit for quick runs


class HarnessRunSummary(BaseModel):
    run_id: str
    status: str           # pending, running, completed, failed
    promptset: str
    team: str
    variant: Optional[str] = None
    total: int = 0
    passed: int = 0
    failed: int = 0
    pass_rate: float = 0.0
    avg_latency_ms: float = 0.0
    avg_tokens_per_second: float = 0.0
    category_breakdown: Optional[Dict] = None
    started_at: str
    completed_at: Optional[str] = None
    errors: List[str] = []


class BenchmarkRunRequest(BaseModel):
    concurrency: int = 10


class BenchmarkRunSummary(BaseModel):
    benchmark_id: str
    status: str           # pending, running, completed, failed
    team_runs: Dict[str, str] = {}   # team -> run_id
    team_status: Dict[str, str] = {} # team -> status
    started_at: str
    completed_at: Optional[str] = None
    summary: Optional[Dict] = None   # per-team aggregated results


# --------------- Health endpoints ---------------
@app.get("/health")
async def health():
    return {"status": "healthy", "service": "data-engine", "version": os.getenv("SERVICE_VERSION", "1.0.0")}


@app.get("/ready")
async def ready():
    if DATA_DIR.exists():
        return {"status": "ready"}
    raise HTTPException(503, "Data directory not found")


# --------------- Promptset endpoints ---------------
@app.get("/promptsets", response_model=List[PromptsetInfo])
async def list_promptsets():
    """List all available promptsets."""
    promptsets = []
    if not DATA_DIR.exists():
        return promptsets

    for subdir in sorted(DATA_DIR.iterdir()):
        manifest_path = subdir / "manifest.json"
        if manifest_path.exists():
            with open(manifest_path) as f:
                manifest = json.load(f)
            promptsets.append(PromptsetInfo(
                promptset_id=manifest.get("promptset_id", subdir.name),
                scenario_id=manifest.get("scenario_id", "unknown"),
                dataset_id=manifest.get("dataset_id", "unknown"),
                prompt_count=manifest.get("prompt_count", 0),
                created_at=manifest.get("created_at", ""),
                version=manifest.get("version", "1.0.0"),
                checksum=manifest.get("checksum", ""),
            ))
    return promptsets


@app.get("/promptsets/{name}")
async def get_promptset(name: str):
    """Get promptset details and preview."""
    promptset_dir = DATA_DIR / name
    if not promptset_dir.exists():
        raise HTTPException(404, f"Promptset '{name}' not found")

    manifest_path = promptset_dir / "manifest.json"
    promptset_path = promptset_dir / "promptset.jsonl"

    manifest = {}
    if manifest_path.exists():
        with open(manifest_path) as f:
            manifest = json.load(f)

    # Load first 5 prompts as preview
    preview = []
    if promptset_path.exists():
        with open(promptset_path) as f:
            for i, line in enumerate(f):
                if i >= 5:
                    break
                preview.append(json.loads(line))

    return {"manifest": manifest, "preview": preview}


# --------------- Harness endpoints ---------------
async def _execute_run(run_id: str, promptset_name: str, team: str,
                       variant: Optional[str], concurrency: int,
                       max_prompts: Optional[int]):
    """Background task: run the harness and store results."""
    _runs[run_id]["status"] = "running"
    try:
        # Load prompts
        promptset_path = DATA_DIR / promptset_name / "promptset.jsonl"
        prompts = []
        with open(promptset_path) as f:
            for line in f:
                prompts.append(json.loads(line))

        if max_prompts and max_prompts < len(prompts):
            prompts = prompts[:max_prompts]

        _runs[run_id]["total"] = len(prompts)

        # Run harness
        harness = TestHarness(
            gateway_url=GATEWAY_URL,
            run_id=run_id,
            concurrency=concurrency,
        )
        results: List[HarnessResult] = await harness.run_promptset(
            prompts, team, variant
        )

        # Summarize
        passed = sum(1 for r in results if r.passed)
        failed = sum(1 for r in results if not r.passed)
        avg_lat = sum(r.latency_ms for r in results) / len(results) if results else 0
        avg_tps = sum(r.tokens_per_second for r in results) / len(results) if results else 0
        errors = [f"{r.prompt_id}: {r.error}" for r in results if r.error]

        # Category breakdown
        categories = {}
        for r in results:
            cat = r.category or "uncategorized"
            if cat not in categories:
                categories[cat] = {"total": 0, "passed": 0}
            categories[cat]["total"] += 1
            if r.passed:
                categories[cat]["passed"] += 1

        _runs[run_id].update({
            "status": "completed",
            "total": len(results),
            "passed": passed,
            "failed": failed,
            "pass_rate": round(passed / len(results) * 100, 1) if results else 0,
            "avg_latency_ms": round(avg_lat, 1),
            "avg_tokens_per_second": round(avg_tps, 1),
            "category_breakdown": categories if categories else None,
            "completed_at": datetime.utcnow().isoformat() + "Z",
            "errors": errors[:20],  # cap at 20
        })

    except Exception as exc:
        _runs[run_id].update({
            "status": "failed",
            "completed_at": datetime.utcnow().isoformat() + "Z",
            "errors": [str(exc)],
        })


@app.post("/harness/run", response_model=HarnessRunSummary)
async def start_harness_run(req: HarnessRunRequest, bg: BackgroundTasks):
    """Start a harness run against a promptset."""
    # Validate promptset exists — try direct directory match first,
    # then fall back to matching by dataset_id in manifests
    promptset_name = req.promptset
    promptset_path = DATA_DIR / promptset_name / "promptset.jsonl"
    if not promptset_path.exists():
        # Scan manifests for a dataset_id match
        resolved = False
        if DATA_DIR.exists():
            for subdir in DATA_DIR.iterdir():
                mp = subdir / "manifest.json"
                if mp.exists():
                    with open(mp) as mf:
                        manifest = json.load(mf)
                    if manifest.get("dataset_id") == req.promptset:
                        promptset_name = subdir.name
                        promptset_path = subdir / "promptset.jsonl"
                        resolved = True
                        break
        if not resolved:
            raise HTTPException(404, f"Promptset '{req.promptset}' not found")

    run_id = f"run-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"

    _runs[run_id] = {
        "run_id": run_id,
        "status": "pending",
        "promptset": promptset_name,
        "team": req.team,
        "variant": req.variant,
        "total": 0,
        "passed": 0,
        "failed": 0,
        "pass_rate": 0.0,
        "avg_latency_ms": 0.0,
        "started_at": datetime.utcnow().isoformat() + "Z",
        "completed_at": None,
        "errors": [],
    }

    bg.add_task(_execute_run, run_id, promptset_name, req.team,
                req.variant, req.concurrency, req.max_prompts)

    return HarnessRunSummary(**_runs[run_id])


@app.get("/harness/runs", response_model=List[HarnessRunSummary])
async def list_runs():
    """List all harness runs (most recent first)."""
    runs = sorted(_runs.values(), key=lambda r: r["started_at"], reverse=True)
    return [HarnessRunSummary(**r) for r in runs[:50]]


@app.get("/harness/runs/{run_id}", response_model=HarnessRunSummary)
async def get_run(run_id: str):
    """Get status/results for a specific run."""
    if run_id not in _runs:
        raise HTTPException(404, f"Run '{run_id}' not found")
    return HarnessRunSummary(**_runs[run_id])


# --------------- Benchmark endpoints ---------------

async def _execute_benchmark(benchmark_id: str, concurrency: int):
    """Run all 3 team benchmarks sequentially and aggregate results."""
    _benchmarks[benchmark_id]["status"] = "running"
    try:
        for team, promptset_name in BENCHMARK_MAP.items():
            promptset_path = DATA_DIR / promptset_name / "promptset.jsonl"
            if not promptset_path.exists():
                _benchmarks[benchmark_id]["team_status"][team] = "skipped"
                continue

            run_id = f"bench-{team}-{benchmark_id.split('-')[-1]}"
            _benchmarks[benchmark_id]["team_runs"][team] = run_id
            _benchmarks[benchmark_id]["team_status"][team] = "running"

            _runs[run_id] = {
                "run_id": run_id,
                "status": "running",
                "promptset": promptset_name,
                "team": team,
                "variant": None,
                "total": 0,
                "passed": 0,
                "failed": 0,
                "pass_rate": 0.0,
                "avg_latency_ms": 0.0,
                "started_at": datetime.utcnow().isoformat() + "Z",
                "completed_at": None,
                "errors": [],
            }

            await _execute_run(run_id, promptset_name, team, None, concurrency, None)

            _benchmarks[benchmark_id]["team_status"][team] = _runs[run_id]["status"]

        # Aggregate summary
        summary = {}
        for team, run_id in _benchmarks[benchmark_id]["team_runs"].items():
            if run_id in _runs:
                r = _runs[run_id]
                summary[team] = {
                    "total": r["total"],
                    "passed": r["passed"],
                    "failed": r["failed"],
                    "pass_rate": r.get("pass_rate", 0),
                    "avg_latency_ms": r.get("avg_latency_ms", 0),
                    "avg_tokens_per_second": r.get("avg_tokens_per_second", 0),
                    "category_breakdown": r.get("category_breakdown"),
                }

        all_failed = all(s == "failed" for s in _benchmarks[benchmark_id]["team_status"].values())
        _benchmarks[benchmark_id].update({
            "status": "failed" if all_failed else "completed",
            "completed_at": datetime.utcnow().isoformat() + "Z",
            "summary": summary,
        })

    except Exception as exc:
        _benchmarks[benchmark_id].update({
            "status": "failed",
            "completed_at": datetime.utcnow().isoformat() + "Z",
            "summary": {"error": str(exc)},
        })


@app.post("/harness/benchmark", response_model=BenchmarkRunSummary)
async def start_benchmark(req: BenchmarkRunRequest, bg: BackgroundTasks):
    """Start a full benchmark run across all teams."""
    # Validate that at least one benchmark promptset exists
    found = [t for t, ps in BENCHMARK_MAP.items() if (DATA_DIR / ps / "promptset.jsonl").exists()]
    if not found:
        raise HTTPException(404, "No benchmark promptsets found. Run generate-benchmark.py first.")

    benchmark_id = f"benchmark-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
    _benchmarks[benchmark_id] = {
        "benchmark_id": benchmark_id,
        "status": "pending",
        "team_runs": {},
        "team_status": {t: "pending" for t in BENCHMARK_MAP},
        "started_at": datetime.utcnow().isoformat() + "Z",
        "completed_at": None,
        "summary": None,
    }

    bg.add_task(_execute_benchmark, benchmark_id, req.concurrency)
    return BenchmarkRunSummary(**_benchmarks[benchmark_id])


@app.get("/harness/benchmark/{benchmark_id}", response_model=BenchmarkRunSummary)
async def get_benchmark(benchmark_id: str):
    """Get benchmark run status and results."""
    if benchmark_id not in _benchmarks:
        raise HTTPException(404, f"Benchmark '{benchmark_id}' not found")
    return BenchmarkRunSummary(**_benchmarks[benchmark_id])
