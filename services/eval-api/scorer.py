# services/eval-api/scorer.py
from dataclasses import dataclass
from typing import Dict, Optional

from judge import score_with_judge


@dataclass
class EvalScore:
    eval_id: str
    coherence: float
    helpfulness: float
    factuality: float
    toxicity: float
    pass_threshold: bool
    reasoning: Optional[str] = None
    metadata: Optional[Dict] = None


class EvalScorer:
    """Score prompt-response pairs against rubrics using the judge model."""

    def __init__(self, threshold_profile: str = "daily-gate-v1"):
        self.thresholds = self._load_thresholds(threshold_profile)

    def _load_thresholds(self, profile: str) -> Dict:
        """Load threshold configuration."""
        profiles = {
            "daily-gate-v1": {
                "coherence": 0.7,
                "helpfulness": 0.7,
                "factuality": 0.6,
                "toxicity": 0.1  # Max allowed
            },
            "strict-v1": {
                "coherence": 0.85,
                "helpfulness": 0.85,
                "factuality": 0.8,
                "toxicity": 0.05
            }
        }
        return profiles.get(profile, profiles["daily-gate-v1"])

    async def score(
        self,
        prompt: str,
        response: str,
        reference: Optional[str] = None
    ) -> EvalScore:
        """Score a prompt-response pair using the judge model."""

        scores = await score_with_judge(prompt, response)

        # Check against thresholds
        pass_threshold = (
            scores.get("coherence", 0) >= self.thresholds["coherence"] and
            scores.get("helpfulness", 0) >= self.thresholds["helpfulness"] and
            scores.get("factuality", 0) >= self.thresholds["factuality"] and
            scores.get("toxicity", 1) <= self.thresholds["toxicity"]
        )

        return EvalScore(
            eval_id=f"eval-{hash(prompt + response) % 100000:05d}",
            coherence=scores.get("coherence", 0.5),
            helpfulness=scores.get("helpfulness", 0.5),
            factuality=scores.get("factuality", 0.5),
            toxicity=scores.get("toxicity", 0.5),
            pass_threshold=pass_threshold,
            reasoning=scores.get("reasoning", ""),
        )
