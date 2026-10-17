"""Callable tools used explicitly by the three agents."""
from __future__ import annotations
from datetime import datetime, timezone
import pandas as pd
from data import build_inventory, HISTORIES, EVENTS


def get_storage_inventory() -> list[dict]:
    """Return all synthetic storage pools as JSON-friendly dictionaries."""
    return build_inventory().to_dict(orient="records")


def get_pool_history(pool_id: str) -> list[dict]:
    if pool_id not in HISTORIES:
        raise KeyError(f"Unknown pool_id: {pool_id}")
    return list(HISTORIES[pool_id])


def get_pool_events(pool_id: str) -> list[dict]:
    if pool_id not in EVENTS:
        raise KeyError(f"Unknown pool_id: {pool_id}")
    return list(EVENTS[pool_id])


def calculate_utilization(pool_id: str) -> dict:
    inventory = build_inventory()
    match = inventory[inventory.pool_id == pool_id]
    if match.empty:
        raise KeyError(f"Unknown pool_id: {pool_id}")
    row = match.iloc[0]
    return {"pool_id": pool_id, "total_capacity_tb": float(row.total_capacity_tb),
            "used_capacity_tb": float(row.used_capacity_tb), "free_capacity_tb": float(row.free_capacity_tb),
            "utilization_pct": float(row.utilization_pct),
            "warning_threshold_pct": float(row.warning_threshold_pct),
            "critical_threshold_pct": float(row.critical_threshold_pct)}


def forecast_threshold_breach(pool_id: str) -> dict:
    inventory = build_inventory()
    match = inventory[inventory.pool_id == pool_id]
    if match.empty:
        raise KeyError(f"Unknown pool_id: {pool_id}")
    row = match.iloc[0]
    current = float(row.utilization_pct)
    threshold = float(row.critical_threshold_pct)
    growth = float(row.daily_growth_pp)
    if growth <= 0:
        days = None
        status = "No breach forecast from current linear trend" if growth == 0 else "Growth is negative; no breach forecast from current trend"
    else:
        days = max(0.0, (threshold - current) / growth)
        status = "Already at or above critical threshold" if current >= threshold else "Linear estimate only"
    return {"pool_id": pool_id, "current_utilization_pct": current,
            "critical_threshold_pct": threshold, "daily_growth_pp": growth,
            "estimated_days_to_critical": round(days, 2) if days is not None else None,
            "forecast_status": status,
            "assumptions": ["Daily growth remains constant", "Capacity and workload mix remain comparable", "No remediation or major workload change occurs"],
            "reliability": "Low: synthetic short history; validate against production telemetry"}


def create_incident_report(incident: dict) -> dict:
    """Create a serializable report envelope and timestamp it in UTC."""
    return {"report_id": f"DASD-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "data_classification": "SYNTHETIC DEMONSTRATION DATA", "incident": incident}
