"""Data Engine API — serves promptsets and runs test harness."""

import asyncio
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
    started_at: str
    completed_at: Optional[str] = None
    errors: List[str] = []


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
        errors = [f"{r.prompt_id}: {r.error}" for r in results if r.error]

        _runs[run_id].update({
            "status": "completed",
            "total": len(results),
            "passed": passed,
            "failed": failed,
            "pass_rate": round(passed / len(results) * 100, 1) if results else 0,
            "avg_latency_ms": round(avg_lat, 1),
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
    # Validate promptset exists
    promptset_path = DATA_DIR / req.promptset / "promptset.jsonl"
    if not promptset_path.exists():
        raise HTTPException(404, f"Promptset '{req.promptset}' not found")

    run_id = f"run-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"

    _runs[run_id] = {
        "run_id": run_id,
        "status": "pending",
        "promptset": req.promptset,
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

    bg.add_task(_execute_run, run_id, req.promptset, req.team,
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
