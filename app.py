from __future__ import annotations
import json
import pandas as pd
import plotly.express as px
import streamlit as st
from data import build_inventory, HISTORIES
from agents import run_workflow
from llm_client import resolve_llm_config

st.set_page_config(page_title="DASD Capacity Incident Assistant", page_icon="🖥️", layout="wide", initial_sidebar_state="expanded")

# Lightweight styling: no extra packages, works on Streamlit Community Cloud.
st.markdown("""
<style>
  .stApp { background: #0b1220; }
  [data-testid="stHeader"] { background: rgba(11,18,32,0.92); }
  [data-testid="stSidebar"] { background: #111b2e; border-right: 1px solid #253247; }
  .block-container { padding-top: 1.6rem; padding-bottom: 2.5rem; max-width: 1500px; }
  .hero { padding: 1.45rem 1.6rem; border: 1px solid #29374d; border-radius: 18px;
          background: linear-gradient(120deg,#15243a 0%,#111827 58%,#182438 100%); margin-bottom: 1rem; }
  .eyebrow { color: #93c5fd; font-size: .76rem; font-weight: 700; letter-spacing: .13em; text-transform: uppercase; }
  .hero h1 { color: #f8fafc; font-size: 2rem; line-height: 1.2; margin: .45rem 0 .35rem 0; }
  .hero p { color: #cbd5e1; margin: 0; font-size: .98rem; }
  .status-pill { display: inline-block; margin-top: .9rem; border-radius: 999px; padding: .28rem .7rem;
                 color: #fde68a; background: #422006; border: 1px solid #92400e; font-size: .75rem; font-weight: 700; }
  h2 { color: #e5edf8 !important; padding-top: .65rem; }
  h3 { color: #dbeafe !important; }
  [data-testid="stMetric"] { background: #111b2e; border: 1px solid #29374d; padding: 1rem 1.1rem; border-radius: 14px; }
  [data-testid="stMetricLabel"] { color: #aabbd0; }
  [data-testid="stMetricValue"] { color: #f8fafc; }
  [data-testid="stMetricDelta"] { font-size: .8rem; }
  div[data-testid="stDataFrame"] { border: 1px solid #29374d; border-radius: 12px; overflow: hidden; }
  div.stButton > button[kind="primary"] { background: #2563eb; border: 1px solid #3b82f6; border-radius: 10px; font-weight: 700; min-height: 2.8rem; }
  div.stButton > button { border-radius: 10px; }
  [data-testid="stExpander"] { border: 1px solid #29374d; border-radius: 12px; }
  [data-testid="stAlert"] { border-radius: 12px; }
  .section-note { color: #94a3b8; font-size: .88rem; margin-top: -.55rem; margin-bottom: .8rem; }
  .risk-banner { display:flex; align-items:center; justify-content:space-between; gap:1rem; padding:1rem 1.15rem;
                 border:1px solid #92400e; border-radius:14px; background:linear-gradient(100deg,#2b1d16,#1b2433); margin:.7rem 0 1rem 0; }
  .risk-label { color:#fbbf24; font-size:.72rem; font-weight:800; letter-spacing:.12em; text-transform:uppercase; }
  .risk-title { color:#f8fafc; font-size:1.1rem; font-weight:750; margin:.15rem 0; }
  .risk-copy { color:#cbd5e1; font-size:.88rem; }
  .risk-value { color:#fbbf24; font-size:1.8rem; font-weight:800; white-space:nowrap; }
  .agent-card { border:1px solid #29374d; border-radius:14px; padding:1rem; min-height:150px; background:#111b2e; }
  .agent-kicker { color:#93c5fd; font-size:.7rem; font-weight:800; letter-spacing:.1em; text-transform:uppercase; }
  .agent-name { color:#f8fafc; font-weight:750; font-size:1rem; margin:.35rem 0; }
  .agent-status { display:inline-block; border-radius:999px; padding:.18rem .55rem; margin:.35rem 0; font-size:.72rem; font-weight:750; }
  .agent-done { color:#bbf7d0; background:#14532d; border:1px solid #166534; }
  .agent-note { color:#aabbd0; font-size:.82rem; line-height:1.45; margin-top:.3rem; }
  .handoff-line { text-align:center; color:#64748b; font-size:.8rem; padding:.25rem 0 .6rem 0; }
  footer { visibility: hidden; }
</style>
<div class="hero">
  <div class="eyebrow">Mainframe AIOps · Storage Operations</div>
  <h1>DASD Capacity Incident Assistant</h1>
  <p>Capacity risk detection, evidence-led investigation, and human-governed remediation.</p>
  <span class="status-pill">● SYNTHETIC DEMONSTRATION · NO PRODUCTION CONNECTIVITY</span>
</div>
""", unsafe_allow_html=True)
st.caption("Deterministic capacity calculations · Three-agent workflow · Optional Gemini-assisted investigation")
with st.expander("Safety and data notice", expanded=False):
    st.info("All pools, events, and metrics are synthetic. Forecasts are linear estimates, not guaranteed breach dates. The LLM receives only supplied synthetic evidence. No production storage changes are executed.")

inventory = build_inventory()
warning = inventory[(inventory.utilization_pct >= inventory.warning_threshold_pct) & (inventory.utilization_pct < inventory.critical_threshold_pct)]
critical = inventory[inventory.utilization_pct >= inventory.critical_threshold_pct]
fast_growth = inventory[inventory.daily_growth_pp >= 0.5]

st.header("01  /  Executive Overview")
st.markdown('<div class="section-note">Fleet health, threshold exposure, and the pools that need attention first.</div>', unsafe_allow_html=True)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Monitored pools", len(inventory))
c2.metric("Critical pools", len(critical))
c3.metric("Warning pools", len(warning))
c4.metric("Fast-growth pools", len(fast_growth))
chart = px.bar(inventory.sort_values("utilization_pct", ascending=False), x="pool_id", y="utilization_pct", color="environment", template="plotly_dark",
               hover_data=["warning_threshold_pct", "critical_threshold_pct", "daily_growth_pp", "business_criticality"],
               title="Current DASD pool utilization", labels={"pool_id": "Storage pool", "utilization_pct": "Utilization (%)", "environment": "Environment"})
chart.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", legend_title_text="Environment", margin=dict(l=12,r=12,t=55,b=12), height=390)
chart.update_yaxes(range=[0, 100], ticksuffix="%", gridcolor="#263449")
chart.add_hline(y=85, line_dash="dash", line_color="#f59e0b", annotation_text="Warning 85%", annotation_position="top left")
chart.add_hline(y=95, line_dash="dash", line_color="#ef4444", annotation_text="Critical 95%", annotation_position="bottom right")
st.plotly_chart(chart, use_container_width=True)
# Spotlight the predefined synthetic incident so executives can orient quickly.
spotlight = inventory.loc[inventory["pool_id"] == "PROD-DASD-07"]
if not spotlight.empty:
    sp = spotlight.iloc[0]
    st.markdown(f'''<div class="risk-banner">
      <div><div class="risk-label">Priority capacity watch · Synthetic incident</div>
      <div class="risk-title">{sp['pool_id']} · Production storage pool</div>
      <div class="risk-copy">Warning threshold exceeded · Growth {sp['daily_growth_pp']:.2f} percentage points/day · Validate against authoritative telemetry</div></div>
      <div style="text-align:right"><div class="risk-value">{sp['utilization_pct']:.0f}%</div><div class="risk-copy">{100-sp['utilization_pct']:.0f} pp below full capacity</div></div>
    </div>''', unsafe_allow_html=True)
show_cols = ["pool_id", "environment", "total_capacity_tb", "used_capacity_tb", "free_capacity_tb", "utilization_pct", "warning_threshold_pct", "critical_threshold_pct", "daily_growth_pp", "business_criticality"]
st.dataframe(inventory[show_cols].style.format({"utilization_pct": "{:.1f}%", "daily_growth_pp": "+{:.2f} pp/day", "total_capacity_tb": "{:.1f}", "used_capacity_tb": "{:.1f}", "free_capacity_tb": "{:.1f}"}), use_container_width=True, hide_index=True)

st.header("02  /  Run Agent Investigation")
st.markdown('<div class="section-note">Run the monitoring → investigation → remediation workflow and inspect each handoff.</div>', unsafe_allow_html=True)
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
if st.button("▶  Investigate Capacity Risk", type="primary", use_container_width=True):
    with st.spinner("Running monitoring → investigation → remediation agents..."):
        st.session_state.workflow_result = run_workflow(use_llm=use_llm, llm_config=llm_config)

result = st.session_state.workflow_result
if result is None:
    st.write("Run the investigation to see explicit tool calls, structured handoffs, evidence, and recommended next steps.")
elif result["status"] == "error":
    st.error(result["error"])
else:
    trace = result.get("trace", [])
    if result["status"] == "success":
        # Visual workflow timeline: makes the three-agent handoff explicit for demos.
        investigation_for_timeline = result.get("investigation", {})
        llm_used = bool(investigation_for_timeline.get("llm_analysis"))
        llm_failed = bool(investigation_for_timeline.get("llm_error"))
        llm_badge = "LLM-assisted analysis completed" if llm_used else ("LLM unavailable · fallback used" if llm_failed else "Deterministic analysis")
        st.markdown("### Agent workflow timeline")
        st.markdown('<div class="section-note">Each stage consumes the previous stage output. Green status means the stage completed; LLM assistance is shown separately.</div>', unsafe_allow_html=True)
        t1, t2, t3 = st.columns(3, gap="medium")
        with t1:
            st.markdown('<div class="agent-card"><div class="agent-kicker">Stage 01 · Detect</div><div class="agent-name">Capacity Monitoring</div><span class="agent-status agent-done">✓ Completed</span><div class="agent-note">Scanned inventory, evaluated thresholds and growth, and created the structured incident.</div></div>', unsafe_allow_html=True)
        with t2:
            st.markdown(f'<div class="agent-card"><div class="agent-kicker">Stage 02 · Investigate</div><div class="agent-name">Capacity Investigation</div><span class="agent-status agent-done">✓ Completed</span><div class="agent-note">Retrieved history and events; separated observed facts, hypotheses, and evidence gaps.<br><br><b>{llm_badge}</b></div></div>', unsafe_allow_html=True)
        with t3:
            st.markdown('<div class="agent-card"><div class="agent-kicker">Stage 03 · Recommend</div><div class="agent-name">Remediation & Operations</div><span class="agent-status agent-done">✓ Completed</span><div class="agent-note">Calculated the threshold forecast and prepared prioritized checks with a human approval gate.</div></div>', unsafe_allow_html=True)
        st.markdown('<div class="handoff-line">Incident object  →  Investigation report  →  Consolidated incident report</div>', unsafe_allow_html=True)
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

        st.header("03  /  Recommended Actions")
        st.markdown('<div class="section-note">Forecast the risk, review prioritized checks, and keep operational changes behind human approval.</div>', unsafe_allow_html=True)
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

        st.header("04  /  Incident Report")
        st.markdown('<div class="section-note">Review the consolidated output or export the report for a handoff or demo artifact.</div>', unsafe_allow_html=True)
        st.json(result["report"])
        payload = json.dumps(result["report"], indent=2, ensure_ascii=False)
        st.download_button("⬇  Download JSON incident report", data=payload, file_name=f"{incident['incident_id']}_report.json", mime="application/json", use_container_width=True)

with st.expander("About the demo architecture"):
    st.markdown("""
    - **Agent orchestration:** Python functions exchange structured dictionaries in a fixed workflow.
    - **Tools:** inventory, history, events, utilization calculation, forecast, and report creation are callable Python functions.
    - **Reasoning boundary:** detection, capacity calculations, and forecasts are deterministic Python. Optional LLM analysis interprets only the retrieved synthetic evidence.
    - **Safety:** the LLM has no production tools; human review is required before any proposed change.
    - **LLM status:** optional OpenAI-compatible chat-completions endpoint. When disabled or unavailable, deterministic investigation continues.
    """)
