"""Synthetic IBM Z DASD capacity data. No production data is used."""
from __future__ import annotations
import pandas as pd

POOL_SPECS = [
    ("PROD-DASD-01", "Production", 120, 78, 82, 90, 0.35, "High"),
    ("PROD-DASD-02", "Production", 160, 131, 82, 90, 0.55, "Critical"),
    ("PROD-DASD-03", "Production", 100, 69, 82, 90, 0.20, "High"),
    ("PROD-DASD-04", "Production", 200, 151, 82, 90, 0.40, "Critical"),
    ("PROD-DASD-05", "Production", 80, 59, 82, 90, 0.60, "High"),
    ("PROD-DASD-06", "Production", 140, 112, 82, 90, 0.45, "Critical"),
    ("PROD-DASD-07", "Production", 100, 91, 85, 95, 0.80, "Critical"),
    ("TEST-DASD-01", "Test", 60, 31, 82, 90, 0.10, "Low"),
    ("DEV-DASD-01", "Development", 40, 22, 82, 90, 0.15, "Low"),
    ("DR-DASD-01", "Disaster Recovery", 100, 76, 82, 90, 0.25, "High"),
]


def build_inventory() -> pd.DataFrame:
    rows = []
    for pool_id, env, total, used, warning, critical, growth, importance in POOL_SPECS:
        utilization = round(used / total * 100, 1)
        rows.append({
            "pool_id": pool_id, "environment": env, "total_capacity_tb": total,
            "used_capacity_tb": round(total * utilization / 100, 2),
            "free_capacity_tb": round(total * (100 - utilization) / 100, 2),
            "utilization_pct": utilization, "warning_threshold_pct": warning,
            "critical_threshold_pct": critical, "daily_growth_pp": growth,
            "business_criticality": importance,
        })
    return pd.DataFrame(rows)


def build_histories() -> dict[str, list[dict]]:
    inventory = build_inventory().set_index("pool_id")
    histories = {}
    for pool_id, row in inventory.iterrows():
        current = float(row["utilization_pct"])
        growth = float(row["daily_growth_pp"])
        # Seven daily points, with small synthetic variation around the stated trend.
        offsets = [-6.0, -5.0, -4.1, -3.0, -2.0, -1.0, 0.0]
        if pool_id == "PROD-DASD-07":
            vals = [86.2, 86.7, 87.0, 88.0, 89.1, 90.2, 91.0]
        else:
            vals = [round(max(0, min(100, current + x * growth)), 1) for x in offsets]
        histories[pool_id] = [
            {"day": f"D-{6-i}", "utilization_pct": value} for i, value in enumerate(vals)
        ]
    return histories


def build_events() -> dict[str, list[dict]]:
    events = {pool_id: [] for pool_id, *_ in POOL_SPECS}
    events["PROD-DASD-07"] = [
        {"timestamp": "Today 09:10", "type": "Workload", "severity": "Info", "description": "Increased workload demand reported by synthetic batch monitor."},
        {"timestamp": "Today 09:25", "type": "Capacity", "severity": "Warning", "description": "Utilization crossed the 90% operational watch level."},
        {"timestamp": "Today 09:30", "type": "Change", "severity": "Info", "description": "No approved storage expansion change is recorded in this synthetic dataset."},
    ]
    events["PROD-DASD-02"] = [
        {"timestamp": "Today 08:40", "type": "Capacity", "severity": "Warning", "description": "Pool is above its warning threshold."}
    ]
    return events

HISTORIES = build_histories()
EVENTS = build_events()
