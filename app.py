from __future__ import annotations
import json
import pandas as pd
import plotly.express as px
import streamlit as st
from data import build_inventory, HISTORIES
from agents import run_workflow
from llm_client import resolve_llm_config

st.set_page_config(page_title="DASD Capacity Incident Assistant", page_icon="🖥️", layout="wide")
st.title("DASD Capacity Incident Assistant")
st.caption("Synthetic IBM Z storage operations demo · Deterministic agents with optional LLM-assisted investigation · No production connectivity")
st.info("All pools, events, and metrics are synthetic. Forecasts are linear estimates, not guaranteed breach dates. No storage changes are executed.")

inventory = build_inventory()
warning = inventory[(inventory.utilization_pct >= inventory.warning_threshold_pct) & (inventory.utilization_pct < inventory.critical_threshold_pct)]
critical = inventory[inventory.utilization_pct >= inventory.critical_threshold_pct]
fast_growth = inventory[inventory.daily_growth_pp >= 0.5]

st.header("A. Executive Overview")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Monitored pools", len(inventory))
c2.metric("Critical pools", len(critical))
c3.metric("Warning pools", len(warning))
c4.metric("Fast-growth pools", len(fast_growth))
chart = px.bar(inventory.sort_values("utilization_pct", ascending=False), x="pool_id", y="utilization_pct", color="environment",
               hover_data=["warning_threshold_pct", "critical_threshold_pct", "daily_growth_pp", "business_criticality"],
               title="Current DASD pool utilization", labels={"pool_id": "Storage pool", "utilization_pct": "Utilization (%)", "environment": "Environment"})
chart.add_hline(y=85, line_dash="dash", annotation_text="85% reference warning")
chart.add_hline(y=95, line_dash="dash", annotation_text="95% reference critical")
st.plotly_chart(chart, use_container_width=True)
show_cols = ["pool_id", "environment", "total_capacity_tb", "used_capacity_tb", "free_capacity_tb", "utilization_pct", "warning_threshold_pct", "critical_threshold_pct", "daily_growth_pp", "business_criticality"]
st.dataframe(inventory[show_cols].style.format({"utilization_pct": "{:.1f}%", "daily_growth_pp": "+{:.2f} pp/day", "total_capacity_tb": "{:.1f}", "used_capacity_tb": "{:.1f}", "free_capacity_tb": "{:.1f}"}), use_container_width=True, hide_index=True)

st.header("B. Run Agent Investigation")
if "workflow_result" not in st.session_state:
    st.session_state.workflow_result = None
use_llm = st.checkbox("Enable optional LLM-assisted investigation", value=False,
                      help="Requires an OpenAI-compatible API endpoint, model name, and API key in Streamlit Secrets. Without configuration, the app safely uses deterministic Python logic.")
try:
    app_secrets = st.secrets
except Exception:
    app_secrets = {}
llm_config = resolve_llm_config(app_secrets)
llm_ready = all(llm_config.get(k) for k in ("base_url", "api_key", "model"))
if use_llm:
    if llm_ready:
        st.info(f"LLM mode enabled · configured model: {llm_config['model']}. Synthetic evidence only; no production tools are available to the model.")
    else:
        st.warning("LLM mode selected, but configuration is incomplete. The workflow will safely fall back to deterministic Python investigation. Configure LLM_BASE_URL, LLM_API_KEY, and LLM_MODEL in Streamlit Secrets to enable inference.")
if st.button("Investigate Capacity Risk", type="primary"):
    with st.spinner("Running monitoring → investigation → remediation agents..."):
        st.session_state.workflow_result = run_workflow(use_llm=use_llm, llm_config=llm_config)

result = st.session_state.workflow_result
if result is None:
    st.write("Run the investigation to see explicit tool calls, structured handoffs, evidence, and recommended next steps.")
elif result["status"] == "error":
    st.error(result["error"])
else:
    trace = result.get("trace", [])
    with st.expander("Agent execution trace and tool invocations", expanded=True):
        if trace:
            st.dataframe(pd.DataFrame(trace), use_container_width=True, hide_index=True)
        else:
            st.write("No trace entries available.")
    if result["status"] == "no_incidents":
        st.success("No pools met the current alert criteria.")
    else:
        incident = result["incident"]
        investigation = result["investigation"]
        remediation = result["remediation"]
        st.subheader("Agent 1 — Capacity Monitoring Agent")
        st.write(result["monitoring"]["selected_incident"]["monitoring_summary"])
        st.json({"incident_id": incident["incident_id"], "pool_id": incident["pool_id"], "severity": incident["severity"],
                 "priority_score": incident["priority_score"], "trigger_reasons": incident["trigger_reasons"]})
        st.subheader("Agent 2 — Capacity Investigation Agent")
        left, right = st.columns(2)
        with left:
            st.markdown("**Observed facts**")
            for fact in investigation["observed_facts"]:
                st.write(f"- {fact}")
            st.markdown("**Historical utilization**")
            hist_df = pd.DataFrame(investigation["history"])
            st.line_chart(hist_df.set_index("day")["utilization_pct"])
        with right:
            st.markdown("**Hypotheses — not confirmed root causes**")
            for hypothesis in investigation["hypotheses"]:
                st.warning(hypothesis)
            st.markdown("**Missing evidence**")
            for item in investigation["missing_evidence"]:
                st.write(f"- {item}")
            st.caption(investigation["root_cause_status"])
        st.markdown(f"**Investigation mode:** `{investigation.get('reasoning_mode', 'deterministic_python')}`")
        if investigation.get("llm_analysis"):
            llm_result = investigation["llm_analysis"]
            st.markdown("**Optional LLM analysis — advisory, evidence-bounded**")
            st.write(llm_result["summary"])
            st.caption(f"LLM confidence: {llm_result['confidence']} · Validate recommendations against authoritative telemetry.")
            llm_left, llm_right = st.columns(2)
            with llm_left:
                st.markdown("**LLM hypotheses**")
                for item in llm_result["hypotheses"]:
                    st.write(f"- {item}")
                st.markdown("**Additional verification checks**")
                for item in llm_result["additional_checks"]:
                    st.write(f"- {item}")
            with llm_right:
                st.markdown("**LLM evidence limitations**")
                for item in llm_result["evidence_limitations"]:
                    st.write(f"- {item}")
        elif investigation.get("llm_error"):
            st.warning("LLM analysis was not used; deterministic findings are shown. Details: " + investigation["llm_error"])
        st.markdown("**Simulated operational events**")
        st.dataframe(pd.DataFrame(investigation["events"]), use_container_width=True, hide_index=True)

        st.header("C. Recommended Actions")
        forecast = remediation["forecast"]
        days = forecast["estimated_days_to_critical"]
        a, b, c = st.columns(3)
        a.metric("Current utilization", f"{forecast['current_utilization_pct']:.1f}%")
        b.metric("Critical threshold", f"{forecast['critical_threshold_pct']:.1f}%")
        c.metric("Estimated days to critical", f"{days:.1f} days" if days is not None else "Not forecastable")
        st.write(f"**Urgency:** {remediation['urgency']}")
        st.write(f"**Forecast status:** {forecast['forecast_status']}")
        st.write(f"**Daily growth assumption:** {forecast['daily_growth_pp']:.2f} percentage points/day")
        st.write(f"**Reliability:** {forecast['reliability']}")
        st.markdown("**Forecast assumptions**")
        for assumption in forecast["assumptions"]:
            st.write(f"- {assumption}")
        st.markdown("**Prioritized recommendations**")
        st.dataframe(pd.DataFrame(remediation["recommendations"]), use_container_width=True, hide_index=True)
        st.markdown("**Potential business impact**")
        st.write(remediation["business_impact"])
        st.markdown("**Human approval checklist**")
        for i, item in enumerate(remediation["human_approval_checklist"]):
            st.checkbox(item["item"], key=f"approval_{i}")
        st.warning(f"Action status: {remediation['action_record']['approval_status']}. No production storage change is executed by this demo.")

        st.header("D. Incident Report")
        st.json(result["report"])
        payload = json.dumps(result["report"], indent=2, ensure_ascii=False)
        st.download_button("Download JSON incident report", data=payload, file_name=f"{incident['incident_id']}_report.json", mime="application/json")

with st.expander("About the demo architecture"):
    st.markdown("""
    - **Agent orchestration:** Python functions exchange structured dictionaries in a fixed workflow.
    - **Tools:** inventory, history, events, utilization calculation, forecast, and report creation are callable Python functions.
    - **Reasoning boundary:** detection, capacity calculations, and forecasts are deterministic Python. Optional LLM analysis interprets only the retrieved synthetic evidence.
    - **Safety:** the LLM has no production tools; human review is required before any proposed change.
    - **LLM status:** optional OpenAI-compatible chat-completions endpoint. When disabled or unavailable, deterministic investigation continues.
    """)
