"""Optional OpenAI-compatible chat-completions client using only the Python standard library.

The app remains fully functional without an LLM. Configure LLM_BASE_URL, LLM_API_KEY,
and LLM_MODEL through environment variables or Streamlit secrets to enable it.
"""
from __future__ import annotations
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def resolve_llm_config(streamlit_secrets=None) -> dict:
    """Read optional config from environment first, then Streamlit secrets."""
    secrets = streamlit_secrets or {}
    def get_value(key: str) -> str:
        value = os.getenv(key)
        if value:
            return value.strip()
        try:
            value = secrets.get(key, "")
            return str(value).strip() if value else ""
        except Exception:
            return ""
    return {
        "base_url": get_value("LLM_BASE_URL").rstrip("/"),
        "api_key": get_value("LLM_API_KEY"),
        "model": get_value("LLM_MODEL"),
    }


def analyze_investigation(incident: dict, deterministic_report: dict, config: dict, timeout_seconds: int = 60) -> dict:
    """Ask an optional LLM to interpret evidence; returns validated advisory fields only."""
    missing = [key for key in ("base_url", "api_key", "model") if not config.get(key)]
    if missing:
        raise ValueError("LLM configuration incomplete: " + ", ".join(missing))

    endpoint = config["base_url"].rstrip("/") + "/chat/completions"
    evidence = {
        "incident": {
            "incident_id": incident.get("incident_id"),
            "pool_id": incident.get("pool_id"),
            "severity": incident.get("severity"),
            "pool_snapshot": incident.get("pool_snapshot", {}),
        },
        "history": deterministic_report.get("history", []),
        "events": deterministic_report.get("events", []),
        "observed_facts": deterministic_report.get("observed_facts", []),
        "existing_hypotheses": deterministic_report.get("hypotheses", []),
        "missing_evidence": deterministic_report.get("missing_evidence", []),
        "historical_average_growth_pp_per_day": deterministic_report.get("historical_average_growth_pp_per_day"),
    }
    system_prompt = (
        "You are a cautious mainframe DASD capacity investigation assistant. Analyze only the supplied synthetic evidence. "
        "Do not claim a root cause is proven. Clearly distinguish observed facts from hypotheses. Do not invent metrics or events. "
        "Recommend read-only verification steps only; never execute or suggest an automatic production change. "
        "Return ONLY valid JSON with exactly these keys: summary (string), hypotheses (array of strings), "
        "additional_checks (array of strings), confidence (one of low, medium, high), evidence_limitations (array of strings). "
        "If evidence is insufficient, say so and use low confidence."
    )
    payload = {
        "model": config["model"],
        "temperature": 0.1,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(evidence, ensure_ascii=False)},
        ],
    }
    request = Request(endpoint, data=json.dumps(payload).encode("utf-8"), method="POST", headers={
        "Authorization": f"Bearer {config['api_key']}",
        "Content-Type": "application/json",
    })
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            response_body = response.read().decode("utf-8")
    except HTTPError as exc:
        # Do not include request headers or secrets in the error.
        raise RuntimeError(f"LLM provider returned HTTP {exc.code}.") from None
    except (URLError, TimeoutError) as exc:
        raise RuntimeError(f"LLM provider could not be reached: {type(exc).__name__}.") from None

    try:
        envelope = json.loads(response_body)
        content = envelope["choices"][0]["message"]["content"]
        # Some models wrap JSON in Markdown fences; remove them safely.
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
        result = json.loads(content)
    except (ValueError, KeyError, IndexError, TypeError):
        raise RuntimeError("LLM response was not valid JSON in the expected chat-completions format.") from None

    required = {"summary", "hypotheses", "additional_checks", "confidence", "evidence_limitations"}
    if not isinstance(result, dict) or not required.issubset(result):
        raise RuntimeError("LLM response did not include all required structured fields.")
    if not isinstance(result["summary"], str) or not all(isinstance(result[k], list) for k in ("hypotheses", "additional_checks", "evidence_limitations")):
        raise RuntimeError("LLM response contained fields with invalid types.")
    if result["confidence"] not in {"low", "medium", "high"}:
        result["confidence"] = "low"
    for key in ("hypotheses", "additional_checks", "evidence_limitations"):
        result[key] = [str(item)[:500] for item in result[key][:8]]
    result["summary"] = result["summary"][:1500]
    return result
