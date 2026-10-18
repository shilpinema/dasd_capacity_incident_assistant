# DASD Capacity Incident Assistant

A Streamlit demonstration of three collaborating agents for IBM Z DASD capacity incident triage. It uses synthetic data only, has no mainframe connectivity, and never executes production changes.

## Architecture

1. **Capacity Monitoring Agent** scans inventory, calls `get_storage_inventory()` and `calculate_utilization()`, ranks candidates, and passes a structured incident to Agent 2.
2. **Capacity Investigation Agent** calls `get_pool_history()` and `get_pool_events()`, compares the trend, separates observations from hypotheses, and identifies missing evidence. Optionally, it submits this retrieved synthetic evidence to an LLM for an advisory analysis.
3. **Remediation and Operations Agent** calls `forecast_threshold_breach()` and `calculate_utilization()`, builds prioritized recommendations and a human approval checklist.
4. The orchestrator consolidates outputs using `create_incident_report()` and records trace entries for tool calls, handoffs, and failures.

## Reasoning boundaries

- Inventory scanning, prioritization rules, capacity arithmetic, and threshold forecasting are deterministic Python.
- Optional LLM analysis interprets only the synthetic evidence supplied by the investigation agent. The LLM does not have access to production systems or tools.
- LLM output is validated as structured JSON and shown separately from deterministic facts.
- If the LLM is disabled, misconfigured, unavailable, or returns invalid output, the workflow falls back to deterministic findings.
- No production storage change is executed. Recommendations remain subject to human review.

## Run locally

Python 3.10+ recommended.

```bash
python -m venv .venv
# Windows PowerShell: .venv\\Scripts\\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Optional LLM configuration

The application uses an OpenAI-compatible `/chat/completions` endpoint via Python's standard library; no additional Python package is required. It is optional and disabled by default.

Set these three configuration values using your provider's documented endpoint and model:

- `LLM_BASE_URL`: API base URL, without `/chat/completions` at the end (example format: `https://provider.example/v1`).
- `LLM_API_KEY`: API key for that provider.
- `LLM_MODEL`: exact model identifier supported by that endpoint.

For Streamlit Community Cloud, open the app's **Manage app → Settings → Secrets** and add:

```toml
LLM_BASE_URL = "https://YOUR_PROVIDER_BASE_URL/v1"
LLM_API_KEY = "YOUR_API_KEY"
LLM_MODEL = "YOUR_MODEL_ID"
```

Replace the placeholders with values from your chosen provider. Never commit a real API key to GitHub. A provider may offer a free tier, but free limits and model availability vary; check the provider's current terms. Do not assume a ChatGPT subscription includes API usage. Leave the secrets unset to run the complete deterministic demo without an external model.

When configured, open the app and check **Enable optional LLM-assisted investigation** before clicking **Investigate Capacity Risk**. The trace should show the LLM call and result. If configuration or inference fails, the app records a fallback event and retains deterministic findings.

## Test

```bash
pytest -q
```

## Deploy on Streamlit Community Cloud

1. Upload the project files to a GitHub repository. Ensure `app.py`, `agents.py`, `llm_client.py`, `tools.py`, `data.py`, and `requirements.txt` are in the app root (or configure the correct main file path).
2. Sign in to Streamlit Community Cloud with GitHub.
3. Create an app, select the repository and branch, and set the main file path to `app.py`.
4. Deploy. No secrets are required unless you choose to enable LLM inference.

## Synthetic incident

`PROD-DASD-07` is 91% utilized, has an 85% warning threshold and 95% critical threshold, and is growing at 0.8 percentage points/day. The linear estimate is `(95 - 91) / 0.8 = 5 days`.

## Safety and limitations

- No real storage, SMF, RMF, or mainframe data is read.
- Synthetic event correlation does not prove root cause.
- LLM responses are advisory and may be wrong; validate against authoritative telemetry.
- No production storage action is executed. The interface presents an approval checklist and a pending approval record.


## Agentic AI learning features

This version adds a bounded, optional LLM tool-calling loop and a rule-based evidence verification stage.

- **Structured LLM response:** summary, hypotheses, additional checks, limitations, evidence references, and claim statuses.
- **Approved tool calling:** the model may request only `get_pool_history`, `get_pool_events`, `calculate_utilization`, and `forecast_threshold_breach`. Calls are read-only, restricted to the active incident pool, and limited to three tool-call rounds.
- **Bounded retries:** transient HTTP 429/5xx errors and connection timeouts are retried with short exponential backoff. The request timeout is 60 seconds. Deterministic fallback remains available.
- **Evidence verification stage:** Python checks warning-threshold logic, forecast arithmetic, history availability, and cautious root-cause wording. The displayed score is a rule-based verification score, **not** a probability of correctness.
- **Traceability:** approved tool calls and verification checks are surfaced in the UI.

The model cannot run arbitrary code or execute production changes. All data is synthetic. Gemini/OpenAI-compatible provider availability and quotas still apply; retries do not guarantee successful inference.
