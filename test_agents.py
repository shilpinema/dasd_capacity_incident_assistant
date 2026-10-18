import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from data import build_inventory
from tools import calculate_utilization, forecast_threshold_breach, get_pool_history
from agents import run_workflow


def test_inventory_has_ten_pools_and_consistent_capacity():
    df = build_inventory()
    assert len(df) == 10
    assert ((df.used_capacity_tb + df.free_capacity_tb - df.total_capacity_tb).abs() < 0.02).all()
    assert ((df.utilization_pct >= 0) & (df.utilization_pct <= 100)).all()


def test_predefined_incident_forecast_is_five_days():
    metrics = calculate_utilization("PROD-DASD-07")
    forecast = forecast_threshold_breach("PROD-DASD-07")
    assert metrics["utilization_pct"] == 91.0
    assert forecast["critical_threshold_pct"] == 95.0
    assert forecast["daily_growth_pp"] == 0.8
    assert forecast["estimated_days_to_critical"] == 5.0


def test_history_and_workflow_handoffs():
    assert len(get_pool_history("PROD-DASD-07")) == 7
    result = run_workflow()
    assert result["status"] == "success"
    assert result["incident"]["pool_id"] == "PROD-DASD-07"
    assert len(result["investigation"]["observed_facts"]) >= 3
    assert result["remediation"]["action_record"]["production_change_executed"] is False
    assert any(x["event"] == "handoff" for x in result["trace"])


def test_unknown_pool_fails_safely():
    try:
        calculate_utilization("NOT-A-POOL")
    except KeyError:
        pass
    else:
        raise AssertionError("Expected KeyError for unknown pool")


def test_llm_is_optional_and_workflow_falls_back_without_config():
    result = run_workflow(use_llm=True, llm_config={})
    assert result["status"] == "success"
    assert result["investigation"]["reasoning_mode"] == "deterministic_python"
    assert result["investigation"]["llm_analysis"] is None
    assert any(item["event"] == "llm_fallback" for item in result["trace"])
