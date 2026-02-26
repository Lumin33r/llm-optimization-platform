"""LLM Judge using baseline model for evaluation scoring."""

import json
from typing import Dict

import httpx

BASELINE_URL = "http://mistral-7b-baseline.llm-baseline.svc:8000/v1/chat/completions"


async def score_with_baseline_judge(
    prompt: str,
    response: str,
    rubric: str = "coherence",
) -> Dict[str, float]:
    """Use baseline model as judge for quality scoring."""

    judge_prompt = f"""Rate the following response on {rubric} from 0.0 to 1.0.

Question: {prompt}
Response: {response}

Output only a JSON object: {{"score": <float>, "reasoning": "<brief>"}}"""

    async with httpx.AsyncClient(timeout=30.0) as client:
        result = await client.post(
            BASELINE_URL,
            json={
                "model": "mistralai/Mistral-7B-Instruct-v0.2",
                "messages": [{"role": "user", "content": judge_prompt}],
                "max_tokens": 100,
                "temperature": 0.1,
            },
        )
        result.raise_for_status()

        # Parse JSON from response
        content = result.json()["choices"][0]["message"]["content"]
        return json.loads(content)
