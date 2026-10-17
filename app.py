from __future__ import annotations
import json
import pandas as pd
import plotly.express as px
import streamlit as st
from data import build_inventory, HISTORIES
from agents import run_workflow

st.set_page_config(page_title="DASD Capacity Incident Assistant", page_icon="🖥️", layout="wide")
st.title("DASD Capacity Incident Assistant")
st.caption("Synthetic IBM Z storage operations demo · Deterministic Python agents · No production connectivity")
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
if st.button("Investigate Capacity Risk", type="primary"):
    with st.spinner("Running monitoring → investigation → remediation agents..."):
        st.session_state.workflow_result = run_workflow()

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
    - **Reasoning boundary:** findings and forecasts are deterministic; hypotheses are explicitly labeled and not presented as verified root causes.
    - **Safety:** human review is required before any proposed change; no production systems or APIs are connected.
    - **LLM status:** no LLM is configured or claimed in this version.
    """)
