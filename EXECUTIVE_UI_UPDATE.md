# Executive UI update

This update changes the Streamlit presentation layer only. It preserves the existing deterministic capacity calculations, agent orchestration, optional Gemini integration, safety boundary, approval workflow, and JSON export.

## Design decisions
- Dark navy enterprise console with restrained slate and amber accents.
- Agent workflow is emphasized with three clearly sequenced stages and structured handoffs.
- Utilization is shown as a restrained dot plot instead of multicolour bars.
- Full inventory, execution trace, detection payload, LLM diagnostics, and raw JSON remain available on demand.
- The optional LLM failure is communicated without overwhelming the main findings.
- No additional runtime dependencies or Secrets are required.

## Deploy
Replace the existing `app.py` in the GitHub repository with the supplied `app.py` from this package. No `data.py`, `tools.py`, `agents.py`, `llm_client.py`, requirements, or Secrets changes are required. Streamlit Community Cloud should redeploy after the commit.
