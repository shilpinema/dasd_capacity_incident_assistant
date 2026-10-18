"""Optional OpenAI-compatible LLM client with bounded tool calling.

The LLM can request only a small allowlist of read-only synthetic-data tools.
The application executes tools, returns their results to the model, and validates
its final structured response. No arbitrary code or production actions are exposed.
"""
from __future__ import annotations
import json
import os
import time
import hashlib
from collections import OrderedDict
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from tools import get_pool_history, get_pool_events, calculate_utilization, forecast_threshold_breach

MAX_LLM_WALL_SECONDS = 90
MAX_REQUEST_ATTEMPTS = 2
# Never retry quota exhaustion (429): retries do not restore quota and may worsen limits.
RETRYABLE_HTTP_CODES = {500, 502, 503, 504}
CACHE_MAX_ENTRIES = 32
# Process-local cache of successful analyses. Cache errors are never stored.
_ANALYSIS_CACHE: OrderedDict[str, dict] = OrderedDict()


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
    return {"base_url": get_value("LLM_BASE_URL").rstrip("/"),
            "api_key": get_value("LLM_API_KEY"), "model": get_value("LLM_MODEL")}


def _post_chat(endpoint: str, payload: dict, api_key: str, timeout_seconds: int, deadline: float) -> dict:
    """Make a bounded request. Quota errors are surfaced immediately without retry."""
    body = json.dumps(payload).encode("utf-8")
    for attempt in range(MAX_REQUEST_ATTEMPTS):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError("LLM investigation exceeded its 90-second time budget.")
        request_timeout = max(1, min(timeout_seconds, int(remaining)))
        request = Request(endpoint, data=body, method="POST", headers={
            "Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=request_timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            if exc.code in RETRYABLE_HTTP_CODES and attempt < MAX_REQUEST_ATTEMPTS - 1:
                time.sleep(1 * (2 ** attempt))
                continue
            # Keep the provider's diagnostic message visible, but never include request headers/API key.
            raise RuntimeError(
                f"LLM provider returned HTTP {exc.code}: {error_body[:1000]}"
            ) from None
        except (URLError, TimeoutError) as exc:
            if attempt < MAX_REQUEST_ATTEMPTS - 1:
                time.sleep(min(1, max(0, deadline - time.monotonic())))
                continue
            kind = "TimeoutError" if isinstance(exc, TimeoutError) else type(exc).__name__
            raise RuntimeError(f"LLM provider could not be reached: {kind}.") from None
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise RuntimeError("LLM provider returned a response that was not valid JSON.") from None
    raise RuntimeError("LLM request failed after retries.")


def _cache_key(incident: dict, deterministic_report: dict, config: dict) -> str:
    """Fingerprint the evidence and model configuration; exclude secrets from the key."""
    material = {
        "base_url": config.get("base_url", ""),
        "model": config.get("model", ""),
        "incident": {"incident_id": incident.get("incident_id"),
                     "pool_id": incident.get("pool_id"),
                     "severity": incident.get("severity"),
                     "pool_snapshot": incident.get("pool_snapshot", {})},
        "report": deterministic_report,
    }
    encoded = json.dumps(material, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _remember_analysis(key: str, result: dict) -> None:
    _ANALYSIS_CACHE[key] = json.loads(json.dumps(result, default=str))
    _ANALYSIS_CACHE.move_to_end(key)
    while len(_ANALYSIS_CACHE) > CACHE_MAX_ENTRIES:
        _ANALYSIS_CACHE.popitem(last=False)

def _tool_specs() -> list[dict]:
    return [
        {"type": "function", "function": {"name": "get_pool_history", "description": "Retrieve daily utilization history for the incident pool.",
         "parameters": {"type": "object", "properties": {"pool_id": {"type": "string"}}, "required": ["pool_id"], "additionalProperties": False}}},
        {"type": "function", "function": {"name": "get_pool_events", "description": "Retrieve synthetic operational events for the incident pool.",
         "parameters": {"type": "object", "properties": {"pool_id": {"type": "string"}}, "required": ["pool_id"], "additionalProperties": False}}},
        {"type": "function", "function": {"name": "calculate_utilization", "description": "Retrieve current capacity and utilization metrics for the incident pool.",
         "parameters": {"type": "object", "properties": {"pool_id": {"type": "string"}}, "required": ["pool_id"], "additionalProperties": False}}},
        {"type": "function", "function": {"name": "forecast_threshold_breach", "description": "Calculate a deterministic linear estimate of days until critical utilization.",
         "parameters": {"type": "object", "properties": {"pool_id": {"type": "string"}}, "required": ["pool_id"], "additionalProperties": False}}},
    ]


def _execute_tool(name: str, arguments: dict, expected_pool_id: str) -> dict:
    """Execute only approved read-only tools and constrain them to the incident pool."""
    if not isinstance(arguments, dict) or arguments.get("pool_id") != expected_pool_id:
        raise ValueError("Tool arguments must reference the active incident pool.")
    allowed = {"get_pool_history": get_pool_history, "get_pool_events": get_pool_events,
               "calculate_utilization": calculate_utilization,
               "forecast_threshold_breach": forecast_threshold_breach}
    if name not in allowed:
        raise ValueError("Requested tool is not on the approved allowlist.")
    return allowed[name](expected_pool_id)


def analyze_investigation(incident: dict, deterministic_report: dict, config: dict,
                          timeout_seconds: int = 60, trace: list[dict] | None = None) -> dict:
    """Send prepared evidence in one chat-completions request; cache successful results."""
    missing = [key for key in ("base_url", "api_key", "model") if not config.get(key)]
    if missing:
        raise ValueError("LLM configuration incomplete: " + ", ".join(missing))

    cache_key = _cache_key(incident, deterministic_report, config)
    cached = _ANALYSIS_CACHE.get(cache_key)
    if cached is not None:
        _ANALYSIS_CACHE.move_to_end(cache_key)
        result = json.loads(json.dumps(cached))
        result["cache_hit"] = True
        if trace is not None:
            trace.append({"time": "LLM", "agent": "Capacity Investigation Agent", "event": "llm_cache_hit",
                          "detail": "Reused successful LLM analysis for unchanged evidence; no API request made.", "kind": "llm"})
        return result

    endpoint = config["base_url"].rstrip("/") + "/chat/completions"
    deadline = time.monotonic() + MAX_LLM_WALL_SECONDS
    if trace is not None:
        trace.append({"time": "LLM", "agent": "Capacity Investigation Agent", "event": "llm_start",
                      "detail": "Single-request LLM analysis started; maximum wait is 90 seconds.", "kind": "llm"})

    pool_id = incident["pool_id"]
    system_prompt = (
        "You are a cautious mainframe DASD capacity investigation assistant. Analyze only the synthetic evidence in the user message. "
        "Do not request tools or claim access to systems. Never invent metrics, claim a root cause is proven, or execute production actions. "
        "Cite evidence using short references such as history, events, utilization, or forecast. Separate facts from hypotheses. "
        "Return ONLY one valid JSON object with exactly these keys: summary (string), hypotheses (array of strings), "
        "additional_checks (array of strings), confidence (low|medium|high), evidence_limitations (array of strings), "
        "evidence_refs (array of strings), findings (array of objects with claim, evidence_ref, status). "
        "Finding status must be supported, plausible, or unverified. Use low confidence if evidence is incomplete."
    )
    evidence = {
        "incident": {"incident_id": incident.get("incident_id"), "pool_id": pool_id,
                     "severity": incident.get("severity"), "trigger_reasons": incident.get("trigger_reasons", []),
                     "pool_snapshot": incident.get("pool_snapshot", {})},
        "deterministic_observations": deterministic_report.get("observed_facts", []),
        "known_hypotheses": deterministic_report.get("hypotheses", []),
        "known_evidence_gaps": deterministic_report.get("missing_evidence", []),
        "utilization_history": deterministic_report.get("history", []),
        "synthetic_events": deterministic_report.get("events", []),
        "trend": {"observed_change_pp": deterministic_report.get("observed_change_pp"),
                  "historical_average_growth_pp_per_day": deterministic_report.get("historical_average_growth_pp_per_day")},
        "instructions": "Analyze the supplied evidence only. Do not calculate new operational facts when values are missing."
    }
    payload = {"model": config["model"], "temperature": 0.1,
               "messages": [{"role": "system", "content": system_prompt},
                            {"role": "user", "content": "Investigate this synthetic DASD capacity incident and return the required JSON.\n" + json.dumps(evidence, ensure_ascii=False, default=str)}]}
    envelope = _post_chat(endpoint, payload, config["api_key"], timeout_seconds, deadline)
    try:
        message = envelope["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        raise RuntimeError("LLM response did not match the expected chat-completions format.") from None
    content = message.get("content", "")
    try:
        content = content.strip()
        if content.startswith("```"):
            content = content.split("\n", 1)[1]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()
        result = json.loads(content)
    except (ValueError, AttributeError, TypeError):
        raise RuntimeError("LLM response was not valid structured JSON.") from None

    required = {"summary", "hypotheses", "additional_checks", "confidence", "evidence_limitations", "evidence_refs", "findings"}
    if not isinstance(result, dict) or not required.issubset(result):
        raise RuntimeError("LLM response did not include all required structured fields.")
    list_fields = ("hypotheses", "additional_checks", "evidence_limitations", "evidence_refs", "findings")
    if not isinstance(result["summary"], str) or any(not isinstance(result[k], list) for k in list_fields):
        raise RuntimeError("LLM response contained fields with invalid types.")
    if result["confidence"] not in {"low", "medium", "high"}:
        result["confidence"] = "low"
    clean_findings = []
    for item in result["findings"][:10]:
        if isinstance(item, dict) and isinstance(item.get("claim"), str):
            clean_findings.append({"claim": item["claim"][:500],
                                   "evidence_ref": str(item.get("evidence_ref", "unknown"))[:100],
                                   "status": item.get("status") if item.get("status") in {"supported", "plausible", "unverified"} else "unverified"})
    result["findings"] = clean_findings
    for key in ("hypotheses", "additional_checks", "evidence_limitations", "evidence_refs"):
        result[key] = [str(item)[:500] for item in result[key][:10]]
    result["summary"] = result["summary"][:1500]
    result["tool_calls_made"] = []
    result["tool_call_rounds"] = 0
    result["cache_hit"] = False
    _remember_analysis(cache_key, result)
    return result

