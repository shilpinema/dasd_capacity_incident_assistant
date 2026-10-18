"""Optional OpenAI-compatible LLM client with bounded tool calling.

The LLM can request only a small allowlist of read-only synthetic-data tools.
The application executes tools, returns their results to the model, and validates
its final structured response. No arbitrary code or production actions are exposed.
"""
from __future__ import annotations
import json
import os
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from tools import get_pool_history, get_pool_events, calculate_utilization, forecast_threshold_breach

MAX_TOOL_ROUNDS = 2
MAX_LLM_WALL_SECONDS = 150
MAX_REQUEST_ATTEMPTS = 2
RETRYABLE_HTTP_CODES = {429, 500, 502, 503, 504}


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
    """Make a bounded request, respecting the total investigation deadline."""
    body = json.dumps(payload).encode("utf-8")
    for attempt in range(MAX_REQUEST_ATTEMPTS):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError("LLM investigation exceeded its 150-second time budget.")
        request_timeout = max(1, min(timeout_seconds, int(remaining)))
        request = Request(endpoint, data=body, method="POST", headers={
            "Authorization": f"Bearer {api_key}", "Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=request_timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code in RETRYABLE_HTTP_CODES and attempt < MAX_REQUEST_ATTEMPTS - 1:
                time.sleep(1 * (2 ** attempt))
                continue
            raise RuntimeError(f"LLM provider returned HTTP {exc.code}.") from None
        except (URLError, TimeoutError) as exc:
            if attempt < MAX_REQUEST_ATTEMPTS - 1:
                time.sleep(min(1, max(0, deadline - time.monotonic())))
                continue
            kind = "TimeoutError" if isinstance(exc, TimeoutError) else type(exc).__name__
            raise RuntimeError(f"LLM provider could not be reached: {kind}.") from None
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise RuntimeError("LLM provider returned a response that was not valid JSON.") from None
    raise RuntimeError("LLM request failed after retries.")


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
    """Run a tool-capable investigation and return validated structured advisory fields."""
    missing = [key for key in ("base_url", "api_key", "model") if not config.get(key)]
    if missing:
        raise ValueError("LLM configuration incomplete: " + ", ".join(missing))
    endpoint = config["base_url"].rstrip("/") + "/chat/completions"
    deadline = time.monotonic() + MAX_LLM_WALL_SECONDS
    if trace is not None:
        trace.append({"time": "LLM", "agent": "Capacity Investigation Agent", "event": "llm_start",
                      "detail": "LLM investigation started; maximum total wait is 150 seconds.", "kind": "llm"})
    pool_id = incident["pool_id"]
    system_prompt = (
        "You are a cautious mainframe DASD capacity investigation assistant. Analyze only supplied synthetic evidence and approved tool results. "
        "You may call read-only tools to gather evidence. Never invent metrics, claim a root cause is proven, or execute production actions. "
        "Cite evidence by using short references such as history, events, utilization, or forecast. Separate facts from hypotheses. "
        "When enough evidence is available, return ONLY a JSON object with exactly these keys: summary (string), "
        "hypotheses (array of strings), additional_checks (array of strings), confidence (low|medium|high), "
        "evidence_limitations (array of strings), evidence_refs (array of strings), findings (array of objects with claim, evidence_ref, status). "
        "Finding status must be supported, plausible, or unverified. Use low confidence if evidence is incomplete."
    )
    initial_evidence = {"incident": {"incident_id": incident.get("incident_id"), "pool_id": pool_id,
                        "severity": incident.get("severity"), "pool_snapshot": incident.get("pool_snapshot", {})},
                       "deterministic_observations": deterministic_report.get("observed_facts", []),
                       "known_hypotheses": deterministic_report.get("hypotheses", []),
                       "known_evidence_gaps": deterministic_report.get("missing_evidence", [])}
    messages = [{"role": "system", "content": system_prompt},
                {"role": "user", "content": "Investigate this synthetic incident. Use tools where they materially improve the evidence.\n" + json.dumps(initial_evidence)}]
    tool_calls_made = []
    for round_number in range(MAX_TOOL_ROUNDS + 1):
        payload = {"model": config["model"], "temperature": 0.1, "messages": messages,
                   "tools": _tool_specs(), "tool_choice": "auto"}
        envelope = _post_chat(endpoint, payload, config["api_key"], timeout_seconds, deadline)
        try:
            message = envelope["choices"][0]["message"]
        except (KeyError, IndexError, TypeError):
            raise RuntimeError("LLM response did not match the expected chat-completions format.") from None
        calls = message.get("tool_calls") or []
        if calls:
            messages.append({"role": "assistant", "content": message.get("content"), "tool_calls": calls})
            if round_number >= MAX_TOOL_ROUNDS:
                raise RuntimeError("LLM exceeded the maximum tool-call rounds.")
            for call in calls:
                function = call.get("function", {})
                name = function.get("name", "")
                try:
                    arguments = json.loads(function.get("arguments", "{}"))
                    output = _execute_tool(name, arguments, pool_id)
                    status = "success"
                except Exception as exc:
                    output = {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}
                    status = "error"
                tool_calls_made.append({"tool": name, "status": status})
                if trace is not None:
                    trace.append({"time": "LLM tool", "agent": "Capacity Investigation Agent", "event": "tool_call",
                                  "detail": f"LLM requested {name}() → {status}; read-only synthetic tool.", "kind": "tool"})
                messages.append({"role": "tool", "tool_call_id": call.get("id", ""),
                                 "content": json.dumps(output, ensure_ascii=False, default=str)})
            continue
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
        if not isinstance(result["summary"], str) or any(not isinstance(result[k], list) for k in ("hypotheses", "additional_checks", "evidence_limitations", "evidence_refs", "findings")):
            raise RuntimeError("LLM response contained fields with invalid types.")
        if result["confidence"] not in {"low", "medium", "high"}:
            result["confidence"] = "low"
        clean_findings = []
        for item in result["findings"][:10]:
            if isinstance(item, dict) and isinstance(item.get("claim"), str):
                clean_findings.append({"claim": item["claim"][:500], "evidence_ref": str(item.get("evidence_ref", "unknown"))[:100],
                                      "status": item.get("status") if item.get("status") in {"supported", "plausible", "unverified"} else "unverified"})
        result["findings"] = clean_findings
        for key in ("hypotheses", "additional_checks", "evidence_limitations", "evidence_refs"):
            result[key] = [str(item)[:500] for item in result[key][:10]]
        result["summary"] = result["summary"][:1500]
        result["tool_calls_made"] = tool_calls_made
        result["tool_call_rounds"] = round_number
        return result
    raise RuntimeError("LLM investigation ended without a final answer.")
