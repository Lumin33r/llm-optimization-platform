# services/data-engine/api.py
import json
from datetime import datetime
from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List, Optional
import boto3

app = FastAPI(title="Data Engine API")
s3 = boto3.client("s3")
BUCKET = "llmplatform-data-engine"


class PromptsetMetadata(BaseModel):
    promptset_id: str
    scenario_id: str
    dataset_id: str
    prompt_count: int
    created_at: str
    version: str


class RunRequest(BaseModel):
    promptset_id: str
    team: str
    variant: Optional[str] = None
    concurrency: int = 10


class RunStatus(BaseModel):
    run_id: str
    status: str  # pending, running, completed, failed
    progress: Optional[int] = None
    results_url: Optional[str] = None


def _get_latest_manifest(prefix: str) -> Optional[dict]:
    """Get the latest manifest.json under the given S3 prefix."""
    try:
        # List version directories
        response = s3.list_objects_v2(
            Bucket=BUCKET,
            Prefix=prefix,
            Delimiter="/"
        )
        versions = sorted(
            [p["Prefix"] for p in response.get("CommonPrefixes", [])],
            reverse=True
        )
        if not versions:
            return None

        # Get manifest from latest version
        manifest_key = f"{versions[0]}manifest.json"
        obj = s3.get_object(Bucket=BUCKET, Key=manifest_key)
        return json.loads(obj["Body"].read())
    except Exception:
        return None


async def execute_harness_run(
    run_id: str,
    promptset_id: str,
    team: str,
    variant: Optional[str],
    concurrency: int
):
    """Execute a harness run in the background."""
    # Download promptset from S3
    # Execute via TestHarness
    # Upload results to S3
    pass


@app.get("/promptsets", response_model=List[PromptsetMetadata])
async def list_promptsets():
    """List all available promptsets."""
    promptsets = []
    paginator = s3.get_paginator("list_objects_v2")

    for page in paginator.paginate(Bucket=BUCKET, Prefix="promptsets/", Delimiter="/"):
        for prefix in page.get("CommonPrefixes", []):
            scenario = prefix["Prefix"].split("/")[1]
            # Get latest version
            manifest = _get_latest_manifest(f"promptsets/{scenario}/")
            if manifest:
                promptsets.append(PromptsetMetadata(**manifest))

    return promptsets


@app.get("/promptsets/{promptset_id}", response_model=PromptsetMetadata)
async def get_promptset(promptset_id: str):
    """Get promptset details."""
    try:
        response = s3.get_object(
            Bucket=BUCKET,
            Key=f"promptsets/{promptset_id}/manifest.json"
        )
        manifest = json.loads(response["Body"].read())
        return PromptsetMetadata(**manifest)
    except s3.exceptions.NoSuchKey:
        raise HTTPException(status_code=404, detail="Promptset not found")


@app.post("/runs", response_model=RunStatus)
async def create_run(request: RunRequest, background_tasks: BackgroundTasks):
    """Start a new harness run."""
    run_id = f"run-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    # Queue background task
    background_tasks.add_task(
        execute_harness_run,
        run_id=run_id,
        promptset_id=request.promptset_id,
        team=request.team,
        variant=request.variant,
        concurrency=request.concurrency
    )

    return RunStatus(
        run_id=run_id,
        status="pending"
    )


@app.get("/runs/{run_id}", response_model=RunStatus)
async def get_run(run_id: str):
    """Get run status and results."""
    try:
        response = s3.get_object(
            Bucket=BUCKET,
            Key=f"runs/{run_id}/summary.json"
        )
        summary = json.loads(response["Body"].read())
        return RunStatus(
            run_id=run_id,
            status="completed",
            results_url=f"s3://{BUCKET}/runs/{run_id}/results.jsonl"
        )
    except s3.exceptions.NoSuchKey:
        # Check if run is in progress
        return RunStatus(run_id=run_id, status="running")
