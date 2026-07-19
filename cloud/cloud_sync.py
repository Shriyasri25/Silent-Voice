"""
Silent Voice — Cloud AI 100 sync

Pushes accumulated session data (gesture, expression, phrase, whether it
was accepted) to a Cloud AI 100 endpoint and prints back whatever
personalization/reranking response it returns.

This is intentionally simple — the demo story is "the system learns
which phrases this user actually uses and reorders/boosts them over
time," not a full training pipeline.

Fill in CLOUD_ENDPOINT and API_KEY once you have Cloud AI 100 console
credentials. If the endpoint isn't reachable at demo time, this script
still shows the request/response exchange in the terminal, which is
enough to demonstrate the integration to judges.

Run standalone for testing:
  python cloud_sync.py
"""

import json
import time

import requests

CLOUD_ENDPOINT = "https://YOUR-CLOUD-AI-100-ENDPOINT/infer"
API_KEY = "YOUR_API_KEY"


def log_session_and_get_update(session_log: list[dict]) -> dict:
    """POST session events, return the cloud's personalization response."""
    payload = {"session_data": session_log, "timestamp": time.time()}

    try:
        response = requests.post(
            CLOUD_ENDPOINT,
            headers={"Authorization": f"Bearer {API_KEY}"},
            json=payload,
            timeout=5,
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        # Fallback so the demo never hard-fails on a flaky venue network.
        print(f"[Cloud] Request failed ({e}) — showing local fallback response")
        return {
            "status": "offline_fallback",
            "reranked_phrases": _local_rerank(session_log),
        }


def _local_rerank(session_log: list[dict]) -> list[str]:
    """Simple local stand-in for cloud reranking: most-used phrases first."""
    counts: dict[str, int] = {}
    for entry in session_log:
        phrase = entry.get("phrase")
        if phrase:
            counts[phrase] = counts.get(phrase, 0) + 1
    return sorted(counts, key=counts.get, reverse=True)


if __name__ == "__main__":
    sample_log = [
        {"gesture": "OPEN", "expression": "NEUTRAL", "phrase": "I need water", "selected": True},
        {"gesture": "FIST", "expression": "SAD", "phrase": "I am in pain", "selected": True},
        {"gesture": "OPEN", "expression": "NEUTRAL", "phrase": "I need water", "selected": True},
    ]
    result = log_session_and_get_update(sample_log)
    print("Cloud AI 100 response:")
    print(json.dumps(result, indent=2))
