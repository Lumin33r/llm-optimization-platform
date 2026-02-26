# services/data-engine/generator.py
import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass, asdict
import tiktoken


@dataclass
class Prompt:
    prompt_id: str
    prompt: str
    scenario_id: str
    dataset_id: str
    expected_contains: Optional[List[str]] = None
    expected_format: Optional[str] = None
    target_output_tokens: Optional[int] = None
    bucket: Optional[str] = None
    category: Optional[str] = None
    split: Optional[str] = None
    metadata: Optional[Dict] = None


@dataclass
class Manifest:
    promptset_id: str
    scenario_id: str
    dataset_id: str
    created_at: str
    seed: int
    prompt_count: int
    expected_output_schema: Dict
    target_buckets: Dict
    checksum: str
    version: str
    compatible_harness_version: str


class PromptsetGenerator:
    """Generate versioned promptsets from templates and sources."""

    def __init__(self, seed: int = 42):
        self.seed = seed
        self.encoder = tiktoken.get_encoding("cl100k_base")

    def count_tokens(self, text: str) -> int:
        """Count tokens using tiktoken."""
        return len(self.encoder.encode(text))

    def assign_bucket(self, target_tokens: int) -> str:
        """Assign output length bucket."""
        if target_tokens <= 75:
            return "short"
        elif target_tokens <= 300:
            return "medium"
        else:
            return "long"

    def generate_promptset(
        self,
        scenario_id: str,
        dataset_id: str,
        prompts: List[Dict],
        output_dir: Path
    ) -> Manifest:
        """Generate promptset files and manifest."""

        # Process prompts
        processed = []
        for p in prompts:
            prompt = Prompt(
                prompt_id=p["prompt_id"],
                prompt=p["prompt"],
                scenario_id=scenario_id,
                dataset_id=dataset_id,
                expected_contains=p.get("expected_contains"),
                expected_format=p.get("expected_format"),
                target_output_tokens=p.get("target_output_tokens"),
                bucket=self.assign_bucket(p.get("target_output_tokens", 50)),
                category=p.get("category"),
                split=p.get("split"),
                metadata=p.get("metadata")
            )
            processed.append(prompt)

        # Write promptset.jsonl
        promptset_path = output_dir / "promptset.jsonl"
        with open(promptset_path, "w") as f:
            for p in processed:
                f.write(json.dumps(asdict(p)) + "\n")

        # Calculate checksum
        with open(promptset_path, "rb") as f:
            checksum = f"sha256:{hashlib.sha256(f.read()).hexdigest()}"

        # Generate manifest
        manifest = Manifest(
            promptset_id=f"{dataset_id}-{datetime.now().strftime('%Y%m%d')}",
            scenario_id=scenario_id,
            dataset_id=dataset_id,
            created_at=datetime.utcnow().isoformat() + "Z",
            seed=self.seed,
            prompt_count=len(processed),
            expected_output_schema={"format": "text"},
            target_buckets={
                "input_tokens": {"min": 10, "max": 500},
                "output_tokens": {"buckets": [50, 200, 800]}
            },
            checksum=checksum,
            version="1.0.0",
            compatible_harness_version=">=2.0.0"
        )

        # Write manifest.json
        manifest_path = output_dir / "manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(asdict(manifest), f, indent=2)

        return manifest
