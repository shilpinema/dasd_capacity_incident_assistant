# DASD Capacity Incident Assistant

A zero-paid-LLM, synthetic-data Streamlit demonstration of three collaborating agents for IBM Z DASD capacity incident triage. It has no mainframe connectivity and does not execute production changes.

## Architecture

1. **Capacity Monitoring Agent** scans the inventory, calls `get_storage_inventory()` and `calculate_utilization()`, ranks candidates, and passes a structured incident to Agent 2.
2. **Capacity Investigation Agent** calls `get_pool_history()` and `get_pool_events()`, compares the trend, separates observations from hypotheses, and identifies missing evidence.
3. **Remediation and Operations Agent** calls `forecast_threshold_breach()` and `calculate_utilization()`, builds prioritized recommendations and a human approval checklist.
4. The orchestrator consolidates outputs using `create_incident_report()` and records trace entries for tool calls, handoffs, and failures.

All agent logic and forecasts in this version are deterministic Python, not LLM-generated. The UI labels all data as synthetic. A linear forecast is a planning estimate, not a guaranteed breach date.

## Run locally

Python 3.10+ recommended.

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Open the local URL printed by Streamlit.

## Test

```bash
pytest -q
```

## Deploy on Streamlit Community Cloud

1. Create a GitHub repository and upload `app.py`, `agents.py`, `tools.py`, `data.py`, `requirements.txt`, `README.md`, and `tests/`.
2. Sign in to Streamlit Community Cloud with GitHub.
3. Create an app, select the repository and branch, and set the main file path to `app.py`.
4. Deploy. No secrets or API keys are needed.

## Synthetic incident

`PROD-DASD-07` is 91% utilized, has an 85% warning threshold and 95% critical threshold, and is growing at 0.8 percentage points/day. The linear estimate is `(95 - 91) / 0.8 = 5 days`.

## Safety and limitations

- No real storage, SMF, RMF, or mainframe data is read.
- No LLM is configured or claimed.
- Synthetic event correlation does not prove root cause.
- No production storage action is executed. The interface presents an approval checklist and a pending approval record.
- The demo is not a substitute for authoritative storage telemetry, change control, or capacity planning.
