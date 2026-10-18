from __future__ import annotations
import json
import pandas as pd
import plotly.express as px
import streamlit as st
from data import build_inventory, HISTORIES
from agents import run_workflow
from llm_client import resolve_llm_config

st.set_page_config(page_title="DASD Capacity Incident Assistant", page_icon="🖥️", layout="wide", initial_sidebar_state="collapsed")

# Lightweight styling: no extra packages, works on Streamlit Community Cloud.
st.markdown("""
<style>
  :root { --navy-950:#07111f; --navy-900:#0b1728; --navy-800:#122238; --line:#26384e;
          --text:#edf4fc; --muted:#9eb0c5; --blue:#91a9c4; --amber:#e9b65b; --red:#d96f6f; }
  .stApp { background: radial-gradient(ellipse at 12% 0%, #14253d 0%, #0b1422 42%, #080f1a 100%); color:var(--text); }
  [data-testid="stHeader"] { background:rgba(8,15,26,.88); }
  [data-testid="stSidebar"] { background:#0b1728; border-right:1px solid var(--line); }
  .block-container { padding-top:1.25rem; padding-bottom:3rem; max-width:1600px; }
  [data-testid="stMainBlockContainer"] { gap:1.1rem; }
  .hero { padding:1.7rem 1.9rem; border:1px solid #2b4059; border-radius:18px;
          background:linear-gradient(112deg,rgba(19,34,53,.98),rgba(10,22,37,.98) 58%,rgba(15,29,45,.98));
          margin-bottom:1rem; box-shadow:0 14px 36px rgba(0,0,0,.18); }
  .eyebrow { color:#8fc5ff; font-size:.78rem; font-weight:800; letter-spacing:.16em; text-transform:uppercase; }
  .hero h1 { color:#f7fbff; font-size:clamp(2rem,3vw,2.65rem); letter-spacing:-.035em; line-height:1.12; margin:.55rem 0 .55rem; }
  .hero p { color:#c4d2e2; margin:0; font-size:1.04rem; line-height:1.55; max-width:900px; }
  .status-pill { display:inline-block; margin-top:1.1rem; border-radius:999px; padding:.42rem .8rem;
                 color:#ffe2a3; background:rgba(120,75,9,.23); border:1px solid #8b641d; font-size:.76rem; font-weight:800; letter-spacing:.04em; }
  h1,h2,h3 { letter-spacing:-.02em; }
  h2 { color:#f0f6ff !important; font-size:1.55rem !important; padding-top:.55rem; margin-bottom:.2rem !important; }
  h3 { color:#dceaff !important; font-size:1.12rem !important; }
  p, li, label { line-height:1.55; }
  .section-note { color:var(--muted); font-size:.94rem; line-height:1.5; margin-top:0; margin-bottom:.9rem; }
  [data-testid="stMetric"] { background:linear-gradient(145deg,#14243a,#101c2e); border:1px solid #2b4058; padding:1.05rem 1.15rem; border-radius:15px; min-height:112px; }
  [data-testid="stMetricLabel"] { color:#b4c5d9; font-size:.88rem; }
  [data-testid="stMetricValue"] { color:#f8fbff; font-size:1.9rem; font-weight:750; }
  [data-testid="stMetricDelta"] { font-size:.82rem; }
  div[data-testid="stDataFrame"] { border:1px solid #2b4058; border-radius:12px; overflow:hidden; }
  div.stButton > button[kind="primary"] { background:linear-gradient(105deg,#344c68,#405b78); border:1px solid #617991; border-radius:11px; font-weight:800; min-height:3.15rem; box-shadow:0 5px 18px rgba(0,0,0,.18); }
  div.stButton > button { border-radius:10px; min-height:2.55rem; font-weight:650; }
  [data-testid="stDownloadButton"] button { border-radius:10px; font-weight:750; }
  [data-testid="stExpander"] { border:1px solid #2b4058; border-radius:12px; background:rgba(14,27,44,.62); }
  [data-testid="stAlert"] { border-radius:12px; border:1px solid #344960; }
  hr { border-color:#26384e !important; }
  .risk-banner { display:flex; align-items:center; justify-content:space-between; gap:1.25rem; padding:1.2rem 1.35rem;
                 border:1px solid #685634; border-left:3px solid var(--amber); border-radius:15px;
                 background:linear-gradient(100deg,rgba(48,40,27,.55),rgba(17,30,46,.95) 68%); margin:.8rem 0 1.1rem; }
  .risk-label { color:#f6c86d; font-size:.74rem; font-weight:850; letter-spacing:.13em; text-transform:uppercase; }
  .risk-title { color:#f8fbff; font-size:1.2rem; font-weight:800; margin:.25rem 0; }
  .risk-copy { color:#c1cede; font-size:.91rem; line-height:1.5; }
  .risk-value { color:#ffd071; font-size:2.2rem; font-weight:850; white-space:nowrap; line-height:1.05; }
  .agent-card { border:1px solid #314257; border-radius:15px; padding:1.1rem; min-height:174px; height:100%;
                background:linear-gradient(150deg,#132237,#0e1929); box-shadow:0 8px 24px rgba(0,0,0,.12); }
  .agent-kicker { color:#a8bbd1; font-size:.72rem; font-weight:850; letter-spacing:.12em; text-transform:uppercase; }
  .agent-name { color:#f8fbff; font-weight:800; font-size:1.08rem; margin:.45rem 0 .35rem; }
  .agent-status { display:inline-block; border-radius:999px; padding:.23rem .62rem; margin:.35rem 0 .55rem; font-size:.75rem; font-weight:800; }
  .agent-done { color:#d7e5f3; background:rgba(72,94,118,.20); border:1px solid #40556d; }
  .agent-note { color:#b3c3d7; font-size:.88rem; line-height:1.55; margin-top:.25rem; }
  .handoff-line { text-align:center; color:#a6bad0; font-size:.85rem; font-weight:650; padding:.8rem 0 .35rem; }
  .mini-label { color:#91a7c0; text-transform:uppercase; letter-spacing:.1em; font-size:.72rem; font-weight:800; }
  footer { visibility:hidden; }
</style>
<div class="hero">
  <div class="eyebrow">Mainframe AIOps · Storage Operations</div>
  <h1>DASD Capacity Incident Assistant</h1>
  <p>Capacity risk detection, evidence-led investigation, and human-governed remediation.</p>
  <span class="status-pill">● SYNTHETIC DEMONSTRATION · NO PRODUCTION CONNECTIVITY</span>
</div>
""", unsafe_allow_html=True)
st.caption("DETERMINISTIC CAPACITY ANALYTICS  •  THREE-AGENT ORCHESTRATION  •  OPTIONAL GEMINI-ASSISTED INVESTIGATION")
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
# Executive-friendly dot plot: avoids multicolour bars while retaining threshold context.
plot_data = inventory.sort_values("utilization_pct", ascending=True).copy()
plot_data["status"] = plot_data.apply(
    lambda row: "Priority watch" if row["pool_id"] == "PROD-DASD-07" else "Other pools", axis=1
)
chart = px.scatter(
    plot_data, x="utilization_pct", y="pool_id", color="status",
    color_discrete_map={"Priority watch": "#e9b65b", "Other pools": "#9aadc2"},
    template="plotly_dark", size_max=11,
    hover_data=["environment", "warning_threshold_pct", "critical_threshold_pct", "daily_growth_pp", "business_criticality"],
    title="DASD pool utilization against operational thresholds",
    labels={"pool_id": "Storage pool", "utilization_pct": "Utilization (%)", "status": "Pool status", "environment": "Environment"}
)
chart.update_traces(marker=dict(size=11, line=dict(width=1, color="#dbe5ef")))
chart.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", legend_title_text="", margin=dict(l=12,r=18,t=58,b=18), height=390, font=dict(family="Inter, Segoe UI, sans-serif", size=13, color="#c8d6e6"), title=dict(font=dict(size=18, color="#eef5ff"), x=0.01), legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
chart.update_xaxes(range=[0, 100], ticksuffix="%", gridcolor="#263449", zeroline=False)
chart.update_yaxes(title=None, gridcolor="rgba(0,0,0,0)", categoryorder="array", categoryarray=plot_data["pool_id"].tolist())
chart.add_vline(x=85, line_dash="dash", line_color="#8d7953", annotation_text="Warning 85%", annotation_position="top")
chart.add_vline(x=95, line_dash="dash", line_color="#865d5d", annotation_text="Critical 95%", annotation_position="top")
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
st.plotly_chart(chart, width="stretch", config={"displayModeBar": False})
show_cols = ["pool_id", "environment", "total_capacity_tb", "used_capacity_tb", "free_capacity_tb", "utilization_pct", "warning_threshold_pct", "critical_threshold_pct", "daily_growth_pp", "business_criticality"]
with st.expander("View full storage-pool inventory", expanded=False):
    st.dataframe(inventory[show_cols].style.format({"utilization_pct": "{:.1f}%", "daily_growth_pp": "+{:.2f} pp/day", "total_capacity_tb": "{:.1f}", "used_capacity_tb": "{:.1f}", "free_capacity_tb": "{:.1f}"}), width="stretch", hide_index=True)

st.divider()
st.header("02  /  The Agent Workflow")
st.markdown('<div class="section-note">Three specialized agents pass structured evidence from detection to investigation to human-governed action.</div>', unsafe_allow_html=True)
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
if st.button("▶  Investigate Capacity Risk", type="primary", width="stretch"):
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
    with st.expander("Technical detail · Agent execution trace and tool invocations", expanded=False):
        if trace:
            st.dataframe(pd.DataFrame(trace), width="stretch", hide_index=True)
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
        with st.expander("View structured detection payload", expanded=False):
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
            st.info("Optional LLM analysis was unavailable for this run. Deterministic findings and recommendations are still available.")
            with st.expander("LLM diagnostic details", expanded=False):
                st.code(investigation["llm_error"])
        if investigation.get("llm_analysis"):
            st.markdown("**LLM evidence references and findings**")
            llm_result = investigation["llm_analysis"]
            if llm_result.get("evidence_refs"):
                st.caption("Evidence references: " + " · ".join(llm_result["evidence_refs"]))
            if llm_result.get("findings"):
                st.dataframe(pd.DataFrame(llm_result["findings"]), width="stretch", hide_index=True)
            st.caption(f"Approved read-only tool calls: {len(llm_result.get('tool_calls_made', []))} · Tool-call rounds: {llm_result.get('tool_call_rounds', 0)}")

        verification = result.get("verification", {})
        st.markdown("### Evidence verification")
        st.markdown('<div class="section-note">Rule-based checks validate arithmetic and evidence coverage; this score is not a probability of correctness.</div>', unsafe_allow_html=True)
        v1, v2, v3 = st.columns(3)
        v1.metric("Verification score", f"{verification.get('evidence_confidence_score', 0)} / 100")
        v2.metric("Checks passed", f"{verification.get('checks_passed', 0)} / {verification.get('checks_total', 0)}")
        v3.metric("Root cause", "Unconfirmed")
        st.caption(verification.get("summary", "Verification results unavailable."))
        with st.expander("View verification checks", expanded=False):
            checks = verification.get("checks", [])
            if checks:
                st.dataframe(pd.DataFrame(checks), width="stretch", hide_index=True)
            else:
                st.write("No verification checks available.")

        st.markdown("**Simulated operational events**")
        st.dataframe(pd.DataFrame(investigation["events"]), width="stretch", hide_index=True)

        st.divider()
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
        st.dataframe(pd.DataFrame(remediation["recommendations"]), width="stretch", hide_index=True)
        st.markdown("**Potential business impact**")
        st.write(remediation["business_impact"])
        st.markdown("**Human approval checklist**")
        for i, item in enumerate(remediation["human_approval_checklist"]):
            st.checkbox(item["item"], key=f"approval_{i}")
        st.warning(f"Action status: {remediation['action_record']['approval_status']}. No production storage change is executed by this demo.")

        st.divider()
        st.header("04  /  Incident Report")
        st.markdown('<div class="section-note">Review the consolidated output or export the report for a handoff or demo artifact.</div>', unsafe_allow_html=True)
        report = result["report"]
        meta_left, meta_mid, meta_right = st.columns([1.2, 1, 1])
        meta_left.metric("Incident reference", incident["incident_id"])
        meta_mid.metric("Report classification", "Synthetic data")
        meta_right.metric("Production action", "Not executed")
        payload = json.dumps(report, indent=2, ensure_ascii=False)
        st.download_button("Download incident report (JSON)", data=payload, file_name=f"{incident['incident_id']}_report.json", mime="application/json", width="stretch")
        with st.expander("Inspect complete JSON report", expanded=False):
            st.json(report)

with st.expander("About the demo architecture"):
    st.markdown("""
    - **Agent orchestration:** Python functions exchange structured dictionaries in a fixed workflow.
    - **Tools:** inventory, history, events, utilization calculation, forecast, and report creation are callable Python functions.
    - **Reasoning boundary:** detection, capacity calculations, and forecasts are deterministic Python. Optional LLM analysis interprets only the retrieved synthetic evidence.
    - **Safety:** the LLM has no production tools; human review is required before any proposed change.
    - **LLM status:** optional OpenAI-compatible chat-completions endpoint. When disabled or unavailable, deterministic investigation continues.
    """)
