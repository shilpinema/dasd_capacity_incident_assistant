"""Simple orchestrated agents with structured handoffs and execution tracing."""
from __future__ import annotations
from datetime import datetime, timezone
import traceback
from tools import (get_storage_inventory, get_pool_history, get_pool_events,
                   calculate_utilization, forecast_threshold_breach, create_incident_report)
from llm_client import analyze_investigation


def _log(trace: list[dict], agent: str, event: str, detail: str, kind: str = "info") -> None:
    trace.append({"time": datetime.now(timezone.utc).strftime("%H:%M:%S UTC"),
                  "agent": agent, "event": event, "detail": detail, "kind": kind})


def monitoring_agent(trace: list[dict], growth_alert_pp: float = 0.5) -> dict:
    name = "Capacity Monitoring Agent"
    _log(trace, name, "start", "Scanning synthetic storage inventory.")
    inventory = get_storage_inventory()
    _log(trace, name, "tool_call", f"get_storage_inventory() returned {len(inventory)} pools.", "tool")
    candidates = []
    for pool in inventory:
        utilization = calculate_utilization(pool["pool_id"])
        _log(trace, name, "tool_call", f"calculate_utilization('{pool['pool_id']}') → {utilization['utilization_pct']}%.", "tool")
        above_warning = utilization["utilization_pct"] >= utilization["warning_threshold_pct"]
        above_critical = utilization["utilization_pct"] >= utilization["critical_threshold_pct"]
        fast_growth = pool["daily_growth_pp"] >= growth_alert_pp
        if above_warning or above_critical or fast_growth:
            severity = "Critical" if above_critical else "Warning" if above_warning else "Watch"
            criticality_weight = {"Critical": 3, "High": 2, "Low": 1}.get(pool["business_criticality"], 1)
            score = round(utilization["utilization_pct"] + pool["daily_growth_pp"] * 5 + criticality_weight * 2, 2)
            candidates.append({**pool, **utilization, "severity": severity, "fast_growth": fast_growth,
                               "priority_score": score, "trigger_reasons": [r for ok, r in [
                                   (above_warning, f"Utilization ≥ warning threshold ({utilization['warning_threshold_pct']}%)"),
                                   (above_critical, f"Utilization ≥ critical threshold ({utilization['critical_threshold_pct']}%)"),
                                   (fast_growth, f"Growth ≥ {growth_alert_pp} percentage points/day")
                               ] if ok]})
    candidates.sort(key=lambda x: (x["priority_score"], x["utilization_pct"]), reverse=True)
    if not candidates:
        _log(trace, name, "complete", "No pools met alert criteria.")
        return {"status": "no_incidents", "inventory_count": len(inventory), "incidents": [], "selected_incident": None}
    selected = candidates[0]
    incident = {"incident_id": f"INC-{selected['pool_id']}", "pool_id": selected["pool_id"],
                "severity": selected["severity"], "priority_score": selected["priority_score"],
                "trigger_reasons": selected["trigger_reasons"], "pool_snapshot": selected,
                "detected_at_utc": datetime.now(timezone.utc).isoformat(),
                "monitoring_summary": f"{len(candidates)} pools flagged; highest priority is {selected['pool_id']} at {selected['utilization_pct']}%."}
    _log(trace, name, "handoff", f"Passing structured incident {incident['incident_id']} to investigation agent.", "handoff")
    return {"status": "incident_found", "inventory_count": len(inventory), "incidents": candidates,
            "selected_incident": incident}


def investigation_agent(incident: dict, trace: list[dict], use_llm: bool = False, llm_config: dict | None = None) -> dict:
    name = "Capacity Investigation Agent"
    pool_id = incident["pool_id"]
    _log(trace, name, "start", f"Investigating incident {incident['incident_id']} for {pool_id}.")
    history = get_pool_history(pool_id)
    _log(trace, name, "tool_call", f"get_pool_history('{pool_id}') returned {len(history)} points.", "tool")
    events = get_pool_events(pool_id)
    _log(trace, name, "tool_call", f"get_pool_events('{pool_id}') returned {len(events)} events.", "tool")
    if len(history) >= 2:
        first, last = history[0]["utilization_pct"], history[-1]["utilization_pct"]
        observed_change = round(float(last) - float(first), 2)
        daily_average = round(observed_change / (len(history) - 1), 3)
        history_status = "available"
        trend_comparison = f"Across {len(history)} daily points, utilization changed by {observed_change} pp (average {daily_average} pp/day)."
    else:
        observed_change, daily_average, history_status = None, None, "insufficient"
        trend_comparison = "Insufficient history to compare recent growth reliably."
    observed_facts = [f"Current utilization is {incident['pool_snapshot']['utilization_pct']}%.",
                      f"Warning threshold is {incident['pool_snapshot']['warning_threshold_pct']}%; critical threshold is {incident['pool_snapshot']['critical_threshold_pct']}%.",
                      trend_comparison]
    observed_facts.extend([f"Event at {e['timestamp']}: {e['description']}" for e in events])
    hypotheses = []
    if any("workload" in e["description"].lower() and "increased" in e["description"].lower() for e in events):
        hypotheses.append("Increased workload demand may be contributing to the utilization rise; validate with workload and allocation telemetry.")
    if not events:
        hypotheses.append("No event records are available; a causal explanation cannot be inferred from this dataset.")
    if not hypotheses:
        hypotheses.append("Available synthetic evidence does not establish a definitive root cause.")
    missing_evidence = ["Actual allocation/free-space time series and measurement interval", "Volume-level growth and top space consumers",
                        "Batch/job schedule and workload metrics correlated to growth", "Recent storage changes, deletes, and space reclamation results"]
    if history_status != "available":
        missing_evidence.insert(0, "Sufficient historical utilization points")
    report = {"pool_id": pool_id, "incident_id": incident["incident_id"], "history": history,
              "events": events, "history_status": history_status, "observed_change_pp": observed_change,
              "historical_average_growth_pp_per_day": daily_average, "observed_facts": observed_facts,
              "hypotheses": hypotheses, "missing_evidence": missing_evidence,
              "root_cause_status": "Unconfirmed — evidence supports a possible contributor, not a proven cause"}
    report["reasoning_mode"] = "deterministic_python"
    report["llm_analysis"] = None
    if use_llm:
        _log(trace, name, "llm_call", "Submitting retrieved synthetic evidence for optional LLM interpretation.", "llm")
        try:
            llm_result = analyze_investigation(incident, report, llm_config or {}, timeout_seconds=60, trace=trace)
            report["llm_analysis"] = llm_result
            report["reasoning_mode"] = "deterministic_python_plus_llm"
            # Preserve deterministic findings. Display LLM suggestions in a separate field.
            _log(trace, name, "llm_result", f"LLM returned structured analysis with confidence={llm_result['confidence']}.", "llm")
        except Exception as exc:
            report["llm_error"] = f"{type(exc).__name__}: {exc}"
            _log(trace, name, "llm_fallback", f"Optional LLM unavailable; retaining deterministic findings ({type(exc).__name__}).", "warning")
    _log(trace, name, "handoff", f"Passing investigation report with {len(observed_facts)} observations and {len(missing_evidence)} evidence gaps to remediation agent.", "handoff")
    return report


def verification_agent(incident: dict, investigation: dict, remediation: dict, trace: list[dict]) -> dict:
    """Verify deterministic claims and calculate transparent evidence confidence.

    This is a rule-based evidence score, not a probability that the conclusion is true.
    """
    name = "Evidence Verification Agent"
    _log(trace, name, "start", "Checking numerical claims and evidence coverage.")
    snapshot = incident.get("pool_snapshot", {})
    forecast = remediation.get("forecast", {})
    checks = []
    utilization = snapshot.get("utilization_pct")
    warning = snapshot.get("warning_threshold_pct")
    critical = snapshot.get("critical_threshold_pct")
    checks.append({"check": "Utilization is at or above warning threshold",
                   "passed": isinstance(utilization, (int, float)) and isinstance(warning, (int, float)) and utilization >= warning,
                   "detail": f"Utilization={utilization}%; warning={warning}%"})
    days = forecast.get("estimated_days_to_critical")
    growth = forecast.get("daily_growth_pp")
    expected_days = ((critical - utilization) / growth) if isinstance(critical, (int, float)) and isinstance(utilization, (int, float)) and isinstance(growth, (int, float)) and growth > 0 else None
    forecast_passed = expected_days is not None and isinstance(days, (int, float)) and abs(expected_days - days) <= 0.05
    checks.append({"check": "Forecast arithmetic matches linear formula", "passed": forecast_passed,
                   "detail": f"Reported={days}; calculated={round(expected_days, 2) if expected_days is not None else 'not calculable'}"})
    history_count = len(investigation.get("history", []))
    history_passed = history_count >= 2
    checks.append({"check": "At least two history points are available", "passed": history_passed, "detail": f"History points={history_count}"})
    root_cause_unconfirmed = "unconfirmed" in investigation.get("root_cause_status", "").lower()
    checks.append({"check": "Root cause is not overstated", "passed": root_cause_unconfirmed,
                   "detail": investigation.get("root_cause_status", "No root-cause status supplied")})
    passed_count = sum(1 for item in checks if item["passed"])
    # Evidence coverage reflects verifiable checks and available history; it is not an accuracy probability.
    confidence_score = round(100 * passed_count / len(checks))
    llm = investigation.get("llm_analysis") or {}
    llm_findings = llm.get("findings", [])
    unsupported = [item for item in llm_findings if item.get("status") == "unverified"]
    result = {"checks": checks, "checks_passed": passed_count, "checks_total": len(checks),
              "evidence_confidence_score": confidence_score,
              "score_label": "Rule-based verification score, not probability of correctness",
              "llm_findings_reviewed": len(llm_findings), "llm_findings_unverified": len(unsupported),
              "root_cause_confirmed": False,
              "summary": f"{passed_count} of {len(checks)} deterministic checks passed. Root cause remains unconfirmed."}
    _log(trace, name, "complete", result["summary"])
    return result


def remediation_agent(incident: dict, investigation: dict, trace: list[dict]) -> dict:
    name = "Remediation and Operations Agent"
    pool_id = incident["pool_id"]
    _log(trace, name, "start", f"Preparing safe response for {pool_id}; no production changes will be executed.")
    forecast = forecast_threshold_breach(pool_id)
    _log(trace, name, "tool_call", f"forecast_threshold_breach('{pool_id}') → {forecast['estimated_days_to_critical']} days.", "tool")
    utilization = calculate_utilization(pool_id)
    _log(trace, name, "tool_call", f"calculate_utilization('{pool_id}') retrieved current capacity metrics.", "tool")
    days = forecast["estimated_days_to_critical"]
    if utilization["utilization_pct"] >= utilization["critical_threshold_pct"]:
        urgency = "Immediate: critical threshold reached or exceeded"
    elif days is not None and days <= 3:
        urgency = "High: forecast indicates 3 days or less to critical threshold"
    elif days is not None and days <= 7:
        urgency = "Elevated: forecast indicates critical threshold within 7 days"
    else:
        urgency = "Monitor: validate trend and reassess forecast"
    recommendations = [
        {"priority": 1, "action": "Validate current pool and volume free space using the approved storage monitoring source.", "owner": "Storage Operations", "approval_required": False},
        {"priority": 2, "action": "Identify top space consumers and correlate allocation growth with batch/job workload and recent changes.", "owner": "Storage + Workload Operations", "approval_required": False},
        {"priority": 3, "action": "Review reclaimable space, retention, and data lifecycle options under existing operational procedures.", "owner": "Storage Operations + Application Owner", "approval_required": False},
        {"priority": 4, "action": "If the trend is confirmed, submit a capacity expansion or workload-mitigation change for review.", "owner": "Storage Lead / Change Authority", "approval_required": True},
    ]
    impact = ("Potential capacity exhaustion may constrain allocation or workload completion if the trend persists. "
              "No outage is asserted; actual impact depends on pool layout, workload demand, and operational safeguards.")
    action_record = {"proposed_action": "Investigate consumers and prepare a change request only after capacity and trend validation.",
                     "approval_status": "Pending human approval", "approved_by": None,
                     "production_change_executed": False}
    report = {"pool_id": pool_id, "forecast": forecast, "urgency": urgency, "business_impact": impact,
              "recommendations": recommendations, "human_approval_checklist": [
                  {"item": "Validate current capacity against the authoritative monitoring source", "complete": False},
                  {"item": "Confirm growth trend and identify affected volumes/workloads", "complete": False},
                  {"item": "Review risk, implementation plan, and rollback/contingency", "complete": False},
                  {"item": "Obtain authorized change approval before any production action", "complete": False}],
              "action_record": action_record}
    _log(trace, name, "complete", "Recommendations and approval checklist prepared; no production action taken.")
    return report


def run_workflow(use_llm: bool = False, llm_config: dict | None = None) -> dict:
    trace: list[dict] = []
    try:
        monitoring = monitoring_agent(trace)
        if not monitoring.get("selected_incident"):
            return {"status": "no_incidents", "monitoring": monitoring, "trace": trace}
        incident = monitoring["selected_incident"]
        investigation = investigation_agent(incident, trace, use_llm=use_llm, llm_config=llm_config)
        remediation = remediation_agent(incident, investigation, trace)
        verification = verification_agent(incident, investigation, remediation, trace)
        consolidated = {"incident": incident, "investigation": investigation, "remediation": remediation, "verification": verification,
                        "agent_handoffs": ["Capacity Monitoring Agent → Capacity Investigation Agent",
                                           "Capacity Investigation Agent → Remediation and Operations Agent"]}
        report = create_incident_report(consolidated)
        _log(trace, "Orchestrator", "complete", "All three agents completed and consolidated report created.")
        return {"status": "success", "monitoring": monitoring, "incident": incident,
                "investigation": investigation, "remediation": remediation, "verification": verification, "report": report, "trace": trace}
    except Exception as exc:
        _log(trace, "Orchestrator", "failure", f"Workflow failed safely: {type(exc).__name__}: {exc}", "error")
        return {"status": "error", "error": f"{type(exc).__name__}: {exc}", "trace": trace}
