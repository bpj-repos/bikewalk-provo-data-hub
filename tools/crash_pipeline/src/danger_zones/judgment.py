from __future__ import annotations

import json
import os
from typing import Any

import requests

from .config import REPO_ROOT


DEFAULT_JUDGMENT_MODEL = "gpt-5.6-sol"
DEFAULT_REASONING_EFFORT = "high"
RESPONSES_URL = "https://api.openai.com/v1/responses"


JUDGMENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["summary", "findings", "comparisonCaveats"],
    "properties": {
        "summary": {"type": "string"},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "rank",
                    "candidateId",
                    "interpretation",
                    "strongestEvidence",
                    "caveats",
                    "recommendedVerification",
                ],
                "properties": {
                    "rank": {"type": "integer"},
                    "candidateId": {"type": "string"},
                    "interpretation": {"type": "string"},
                    "strongestEvidence": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "caveats": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "recommendedVerification": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
            },
        },
        "comparisonCaveats": {
            "type": "array",
            "items": {"type": "string"},
        },
    },
}


def _local_environment_value(name: str) -> str | None:
    current = os.environ.get(name)
    if current:
        return current
    for path in [REPO_ROOT / ".env.local", REPO_ROOT / ".env"]:
        if not path.exists():
            continue
        for raw_line in path.read_text().splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line.removeprefix("export ").lstrip()
            key, separator, value = line.partition("=")
            if separator and key.strip() == name:
                cleaned = value.strip()
                if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {"'", '"'}:
                    cleaned = cleaned[1:-1]
                return cleaned or None
    return None


def build_judgment_packet(ranking: dict[str, Any], limit: int) -> dict[str, Any]:
    candidates = []
    for candidate in ranking["candidates"][:limit]:
        context = candidate.get("communityContext", {})
        candidates.append(
            {
                "rank": candidate["rank"],
                "candidateId": candidate["candidateId"],
                "name": candidate["name"],
                "reviewPriority": candidate["reviewPriority"],
                "confidence": candidate["confidence"],
                "observedHarm": candidate["observedHarm"],
                "expectedSafety": candidate["expectedSafety"],
                "trafficPressure": candidate["trafficPressure"],
                "trafficStress": candidate["trafficStress"],
                "exposure": candidate["exposure"],
                "crossingContext": candidate.get("crossingContext"),
                "schoolRouteContext": candidate.get("schoolRouteContext"),
                "communityContext": {
                    "reportCount": context.get("reportCount", 0),
                    "issueTypes": context.get("issueTypes", []),
                    "classificationInput": False,
                },
                "limitations": candidate["limitations"],
            }
        )
    return {
        "analysisType": ranking["analysisType"],
        "classificationStatus": ranking["classificationStatus"],
        "sourceCoverage": ranking.get("sourceCoverage", {}),
        "rankingMethod": ranking["methodology"]["rankingMethod"],
        "candidates": candidates,
    }


def build_request_payload(
    packet: dict[str, Any],
    *,
    model: str,
    reasoning_effort: str,
) -> dict[str, Any]:
    return {
        "model": model,
        "store": False,
        "reasoning": {"effort": reasoning_effort},
        "instructions": (
            "Interpret a deterministic street-safety screening ranking. Do not reorder candidates, "
            "change review-priority labels, or present the result as an official danger classification. "
            "Separate observed crashes from expected-safety estimates, traffic pressure, traffic stress, "
            "and exposure. Expected-safety estimates may already use traffic and exposure inputs, so do "
            "not describe those sources as independent corroboration. School-route designation, mapped "
            "crossing controls, and community reports are context only and cannot justify a higher danger "
            "finding. Identify what a traffic engineer should verify in the field. Use calm, factual language."
        ),
        "input": json.dumps(packet, separators=(",", ":"), default=str),
        "max_output_tokens": 5000,
        "text": {
            "verbosity": "medium",
            "format": {
                "type": "json_schema",
                "name": "danger_zone_screening_judgment",
                "strict": True,
                "schema": JUDGMENT_SCHEMA,
            },
        },
    }


def _output_text(response: dict[str, Any]) -> str:
    parts = [
        content.get("text", "")
        for item in response.get("output", [])
        if item.get("type") == "message"
        for content in item.get("content", [])
        if content.get("type") == "output_text"
    ]
    text = "".join(parts).strip()
    if not text:
        raise ValueError("The Responses API returned no output text.")
    return text


def request_judgment(
    ranking: dict[str, Any],
    *,
    limit: int,
    model: str | None = None,
    reasoning_effort: str = DEFAULT_REASONING_EFFORT,
) -> dict[str, Any]:
    api_key = _local_environment_value("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is required only when --with-judgment is requested. "
            "The deterministic ranking does not require it."
        )
    selected_model = model or _local_environment_value(
        "DANGER_ZONE_JUDGMENT_MODEL"
    ) or DEFAULT_JUDGMENT_MODEL
    packet = build_judgment_packet(ranking, limit)
    payload = build_request_payload(
        packet,
        model=selected_model,
        reasoning_effort=reasoning_effort,
    )
    response = requests.post(
        RESPONSES_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=240,
    )
    if not response.ok:
        detail = response.text[:1000]
        raise RuntimeError(f"Responses API request failed ({response.status_code}): {detail}")
    body = response.json()
    parsed = json.loads(_output_text(body))
    return {
        "model": body.get("model", selected_model),
        "responseId": body.get("id"),
        "reasoningEffort": reasoning_effort,
        "usage": body.get("usage"),
        "result": parsed,
    }
