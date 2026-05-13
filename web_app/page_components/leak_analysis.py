"""Leak analysis page — filtered leak table + full meter analysis dashboard."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from page_components.data_utils import build_meter_snapshot, get_cached_data, load_static_data
from page_components.ui import empty_state, metric_card, page_header, section_header, show_glowing_table


_CARD = (
    "background:#111d35;border:1px solid rgba(255,255,255,0.07);"
    "border-radius:12px;padding:1.2rem 1.4rem;"
)
_CHART_BASE = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(color="#64748b", size=10),
    margin=dict(l=8, r=8, t=6, b=8),
    xaxis=dict(showgrid=False, zeroline=False, showline=False, color="#475569"),
    yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)", zeroline=False, color="#475569"),
    showlegend=False,
)


def show_leak_analysis() -> None:

    # ── Data ──────────────────────────────────────────────────────────────────
    static_data = load_static_data()
    data        = get_cached_data()
    snapshot    = build_meter_snapshot(
        static_data["meters"], static_data["zones"],
        data["readings"], data["predictions"], data["alerts"],
    )

    if snapshot.empty:
        empty_state("No meters or readings available yet.")
        return

    # ── Sidebar filters ───────────────────────────────────────────────────────
    sb = st.sidebar
    sb.markdown("### Leak Analysis Filters")
    hours = sb.selectbox(
        "Time range", [24, 48, 72, 168], index=0,
        format_func=lambda v: f"Last {v} hours",
    )
    zone_opts = ["All"] + sorted(snapshot["zone"].dropna().unique().tolist())
    selected_zone = sb.selectbox("Zone", zone_opts)

    # ── Filter to leak cases only ─────────────────────────────────────────────
    leaks = snapshot[snapshot["severity"] != "none"].copy()
    if selected_zone != "All":
        leaks = leaks[leaks["zone"] == selected_zone]

    # ── Page header + status badges ───────────────────────────────────────────
    h_col, badge_col = st.columns([3, 1])
    with h_col:
        page_header(
            "Leak Analysis",
            "Investigate suspected leaks with confidence, trend, and indicator views.",
        )
    with badge_col:
        st.markdown(
            '<div style="display:flex;gap:8px;justify-content:flex-end;padding-top:8px;">'
            '<div style="background:#111d35;border:1px solid rgba(255,255,255,0.07);'
            'border-radius:8px;padding:5px 12px;text-align:center;">'
            '<div style="font-size:8px;font-weight:700;letter-spacing:1.5px;color:#475569;">SYSTEM HEALTH</div>'
            '<div style="font-size:13px;font-weight:800;color:#22c55e;">STABLE</div></div>'
            '<div style="background:#111d35;border:1px solid rgba(255,255,255,0.07);'
            'border-radius:8px;padding:5px 12px;text-align:center;">'
            '<div style="font-size:8px;font-weight:700;letter-spacing:1.5px;color:#475569;">SYNC STATE</div>'
            '<div style="font-size:13px;font-weight:800;color:#e2e8f0;">LIVE</div></div>'
            '</div>',
            unsafe_allow_html=True,
        )

    # ── KPI metrics ───────────────────────────────────────────────────────────
    total_detected = len(leaks)
    critical_count = int((leaks["severity"] == "critical").sum())
    warning_count  = int((leaks["severity"] == "warning").sum())
    avg_conf       = leaks["confidence"].mean() if not leaks.empty else 0.0
    total_loss     = leaks["estimated_loss_l_hr"].sum() if not leaks.empty else 0.0

    mc = st.columns(5)
    with mc[0]: metric_card("Detected Leaks",    str(total_detected),          "Meters flagged",                 "danger" if total_detected else "neutral")
    with mc[1]: metric_card("Critical",           str(critical_count),          "Highest-priority investigations","danger")
    with mc[2]: metric_card("Warning",            str(warning_count),           "Moderate-priority",              "warning")
    with mc[3]: metric_card("Avg Confidence",     f"{avg_conf*100:.1f}%",       "Avg across filtered cases",      "neutral")
    with mc[4]: metric_card("Est. Loss",          f"{total_loss:.0f} L/hr",     "Combined estimated loss",        "warning")

    # ── Leak queue table (only leak rows) ─────────────────────────────────────
    section_header("Detected Leak Queue", "Only meters with an actionable severity level.")
    if leaks.empty:
        st.info("No leak cases match the selected filters.")
        return

    queue_cols = ["meter_id", "zone", "location", "leak_type", "confidence", "severity", "status", "estimated_loss_l_hr"]
    queue = leaks[[c for c in queue_cols if c in leaks.columns]].copy()
    queue["confidence"]         = (queue["confidence"] * 100).round(1).astype(str) + "%"
    queue["estimated_loss_l_hr"] = queue["estimated_loss_l_hr"].round(1)
    show_glowing_table(queue.rename(columns={
        "meter_id":            "Meter",
        "zone":                "Zone",
        "location":            "Location",
        "leak_type":           "Leak Type",
        "confidence":          "Confidence",
        "severity":            "Severity",
        "status":              "Status",
        "estimated_loss_l_hr": "Est. Loss (L/hr)",
    }))

    st.divider()

    # ── Summary charts: Confidence profile + Zone risk ────────────────────────
    section_header("Zone & Confidence Overview", "Distribution of detected cases across zones and confidence levels.")
    chart_left, chart_right = st.columns(2)

    with chart_left:
        fig_bar = px.bar(
            leaks.sort_values("confidence", ascending=False).head(12),
            x="meter_id", y="confidence",
            color="severity",
            color_discrete_map={"critical": "#b91c1c", "warning": "#b45309", "suspected": "#7c3aed"},
            labels={"meter_id": "Meter", "confidence": "Confidence"},
        )
        fig_bar.update_yaxes(tickformat=".0%")
        fig_bar.update_layout(
            margin=dict(l=10, r=10, t=20, b=10),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(255,255,255,0.04)",
            legend_title_text="", height=280,
        )
        st.markdown("**Confidence Profile** — top 12 flagged meters")
        st.plotly_chart(fig_bar, use_container_width=True)

    with chart_right:
        zone_summary = leaks.groupby("zone").agg(
            leak_count=("meter_id", "count"),
            avg_confidence=("confidence", "mean"),
        ).reset_index()
        zone_summary["avg_confidence"] = (zone_summary["avg_confidence"] * 100).round(1)
        fig_zone = px.scatter(
            zone_summary,
            x="zone", y="leak_count",
            size="avg_confidence", color="avg_confidence",
            color_continuous_scale="Teal",
            labels={"zone": "Zone", "leak_count": "Leak cases", "avg_confidence": "Avg conf (%)"},
        )
        fig_zone.update_layout(
            margin=dict(l=10, r=10, t=20, b=10),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(255,255,255,0.04)",
            height=280,
        )
        st.markdown("**Zone Risk Concentration**")
        st.plotly_chart(fig_zone, use_container_width=True)

    st.divider()

    # ── Meter-level drill-down ────────────────────────────────────────────────
    section_header("Meter Trend Analysis", "Select a flagged meter to inspect its readings in detail.")

    selected_meter = st.selectbox("Inspect meter", leaks["meter_id"].tolist())
    meter_row      = leaks[leaks["meter_id"] == selected_meter].iloc[0]
    zone_name      = str(meter_row.get("zone", "—"))
    location       = str(meter_row.get("location", "—"))

    st.markdown(
        f"<div style='font-size:12px;color:#475569;margin:2px 0 14px;'>"
        f"Assets &nbsp;›&nbsp; {zone_name} &nbsp;›&nbsp; {selected_meter}</div>",
        unsafe_allow_html=True,
    )

    meter_readings    = data["readings"][data["readings"]["meter_id"] == selected_meter].copy()
    meter_predictions = data["predictions"][data["predictions"]["meter_id"] == selected_meter].copy()
    if not meter_readings.empty:
        meter_readings = meter_readings.sort_values("timestamp")
    if not meter_predictions.empty:
        meter_predictions = meter_predictions.sort_values("timestamp")

    # Row A: Meter Profile | Flow Rate Trend | Pressure Stability
    col_prof, col_flow, col_press = st.columns([1, 1.4, 1.4])

    with col_prof:
        severity  = str(meter_row.get("severity", "none"))
        sev_color = {"critical": "#ef4444", "warning": "#f59e0b", "suspected": "#a855f7"}.get(severity, "#22c55e")
        sev_label = severity.upper() if severity != "none" else "ACTIVE"
        cur_flow  = float(meter_row.get("current_flow", 0))
        cur_press = float(meter_row.get("current_pressure", 0))
        mnf       = float(meter_row.get("mnf", 0))

        st.markdown(
            f"""<div style="{_CARD}min-height:230px;">
              <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
                <span style="font-size:9px;font-weight:700;letter-spacing:1.5px;color:#475569;">METER PROFILE</span>
                <span style="background:{sev_color}22;color:{sev_color};border:1px solid {sev_color}55;
                      font-size:9px;font-weight:700;padding:2px 9px;border-radius:12px;">{sev_label}</span>
              </div>
              <div style="font-size:24px;font-weight:800;color:#e2e8f0;margin-bottom:14px;">{selected_meter}</div>
              <div style="display:flex;flex-direction:column;gap:9px;font-size:12px;">
                <div style="display:flex;justify-content:space-between;">
                  <span style="color:#475569;">&#128205; Location</span>
                  <span style="color:#e2e8f0;font-weight:600;">{location}</span>
                </div>
                <div style="display:flex;justify-content:space-between;">
                  <span style="color:#475569;">&#128167; Current Flow</span>
                  <span style="color:#e2e8f0;font-weight:700;">{cur_flow:.2f}
                    <span style="font-size:9px;color:#475569;">m³/h</span></span>
                </div>
                <div style="display:flex;justify-content:space-between;">
                  <span style="color:#475569;">&#8645; Current Pressure</span>
                  <span style="color:#4DD9D5;font-weight:700;">{cur_press:.2f}
                    <span style="font-size:9px;color:#475569;">PSI</span></span>
                </div>
                <div style="display:flex;justify-content:space-between;">
                  <span style="color:#475569;">&#9790; Min Night Flow</span>
                  <span style="color:#e2e8f0;font-weight:600;">{mnf:.2f}
                    <span style="font-size:9px;color:#475569;">m³/h</span></span>
                </div>
              </div>
            </div>""",
            unsafe_allow_html=True,
        )

    with col_flow:
        if not meter_readings.empty:
            avg_f     = meter_readings["flow_rate"].mean()
            last_f    = meter_readings["flow_rate"].iloc[-1]
            d_pct     = (last_f - avg_f) / avg_f * 100 if avg_f > 0 else 0
            d_color   = "#22c55e" if d_pct >= 0 else "#ef4444"
            d_sign    = "+" if d_pct >= 0 else ""
            fig_f = go.Figure(go.Scatter(
                x=meter_readings["timestamp"], y=meter_readings["flow_rate"],
                mode="lines", line=dict(color="#4DD9D5", width=2),
                fill="tozeroy", fillcolor="rgba(77,217,213,0.08)",
            ))
            fig_f.update_layout(**_CHART_BASE, height=150)
            st.markdown(
                f'<div style="{_CARD}padding-bottom:4px;">'
                f'<div style="display:flex;justify-content:space-between;">'
                f'<span style="font-size:9px;font-weight:700;letter-spacing:1.5px;color:#94a3b8;">FLOW RATE TREND</span>'
                f'<span style="font-size:9px;font-weight:700;color:{d_color};">{d_sign}{d_pct:.1f}% vs Avg</span>'
                f'</div></div>', unsafe_allow_html=True,
            )
            st.plotly_chart(fig_f, use_container_width=True)

    with col_press:
        if not meter_readings.empty:
            avg_p = meter_readings["pressure"].mean()
            cv    = meter_readings["pressure"].std() / avg_p if avg_p > 0 else 0
            stab  = "Nominal" if cv < 0.05 else ("Unstable" if cv > 0.15 else "Moderate")
            fig_p = go.Figure(go.Scatter(
                x=meter_readings["timestamp"], y=meter_readings["pressure"],
                mode="lines", line=dict(color="#4DD9D5", width=2),
                fill="tozeroy", fillcolor="rgba(77,217,213,0.05)",
            ))
            fig_p.update_layout(**_CHART_BASE, height=150)
            st.markdown(
                f'<div style="{_CARD}padding-bottom:4px;">'
                f'<div style="display:flex;justify-content:space-between;">'
                f'<span style="font-size:9px;font-weight:700;letter-spacing:1.5px;color:#94a3b8;">PRESSURE STABILITY</span>'
                f'<span style="font-size:9px;font-weight:600;color:#64748b;">{stab}</span>'
                f'</div></div>', unsafe_allow_html=True,
            )
            st.plotly_chart(fig_p, use_container_width=True)

    # Row B: Supporting Indicators
    fv = float(meter_row.get("flow_variance", 0))
    pv = float(meter_row.get("pressure_variance", 0))
    af = float(meter_row.get("avg_flow", 0))
    ap = float(meter_row.get("avg_pressure", 0))

    st.markdown(
        f"""<div style="{_CARD}margin-top:10px;">
          <div style="font-size:9px;font-weight:700;letter-spacing:1.5px;color:#94a3b8;margin-bottom:12px;">
            SUPPORTING INDICATORS</div>
          <div style="display:flex;gap:3rem;">
            <div><div style="font-size:8px;font-weight:700;letter-spacing:1px;color:#475569;">FLOW VAR.</div>
                 <div style="font-size:22px;font-weight:800;color:#e2e8f0;">{fv:.4f}</div></div>
            <div><div style="font-size:8px;font-weight:700;letter-spacing:1px;color:#475569;">PRESS. VAR.</div>
                 <div style="font-size:22px;font-weight:800;color:#e2e8f0;">{pv:.4f}</div></div>
            <div><div style="font-size:8px;font-weight:700;letter-spacing:1px;color:#475569;">AVG FLOW</div>
                 <div style="font-size:22px;font-weight:800;color:#e2e8f0;">{af:.3f}</div></div>
            <div><div style="font-size:8px;font-weight:700;letter-spacing:1px;color:#475569;">AVG PRESS.</div>
                 <div style="font-size:22px;font-weight:800;color:#e2e8f0;">{ap:.3f}</div></div>
          </div>
        </div>""",
        unsafe_allow_html=True,
    )

    # Row C: Flow/Pressure/Confidence time-series (3-panel)
    st.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)
    if not meter_readings.empty:
        fig_ts = make_subplots(
            rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.08,
            subplot_titles=("Flow rate", "Pressure", "Leak confidence"),
        )
        fig_ts.add_trace(go.Scatter(
            x=meter_readings["timestamp"], y=meter_readings["flow_rate"],
            mode="lines", name="Flow", line=dict(color="#2870b8", width=2),
        ), row=1, col=1)
        fig_ts.add_trace(go.Scatter(
            x=meter_readings["timestamp"], y=meter_readings["pressure"],
            mode="lines", name="Pressure", line=dict(color="#15803d", width=2),
        ), row=2, col=1)
        if not meter_predictions.empty:
            fig_ts.add_trace(go.Scatter(
                x=meter_predictions["timestamp"],
                y=meter_predictions["confidence"],
                mode="lines+markers", name="Confidence",
                line=dict(color="#b45309", width=2),
            ), row=3, col=1)
            fig_ts.add_hline(y=0.72, line_dash="dash", line_color="#b45309", row=3, col=1)
            fig_ts.add_hline(y=0.95, line_dash="dash", line_color="#b91c1c", row=3, col=1)
        fig_ts.update_layout(
            height=600,
            margin=dict(l=10, r=10, t=30, b=10),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(255,255,255,0.04)",
            legend_title_text="",
        )
        st.plotly_chart(fig_ts, use_container_width=True)

    # Row D: Leak Confidence Index | Correlation Matrix
    col_ci, col_cm = st.columns([3, 2])

    with col_ci:
        st.markdown(
            f'<div style="{_CARD}padding-bottom:4px;">'
            f'<div style="display:flex;justify-content:space-between;align-items:flex-start;">'
            f'<div><div style="font-size:9px;font-weight:700;letter-spacing:1.5px;color:#94a3b8;">LEAK CONFIDENCE INDEX</div>'
            f'<div style="font-size:11px;color:#475569;margin-top:3px;">Automated anomaly detection score over {hours}h</div></div>'
            f'<div style="display:flex;gap:12px;padding-top:2px;">'
            f'<span style="font-size:10px;"><span style="color:#ef4444;">●</span> <span style="color:#64748b;">Critical (95%)</span></span>'
            f'<span style="font-size:10px;"><span style="color:#f59e0b;">●</span> <span style="color:#64748b;">Warning (72%)</span></span>'
            f'</div></div></div>',
            unsafe_allow_html=True,
        )
        if not meter_predictions.empty:
            fig_ci = go.Figure(go.Scatter(
                x=meter_predictions["timestamp"],
                y=meter_predictions["confidence"] * 100,
                mode="lines", line=dict(color="#4DD9D5", width=2),
                fill="tozeroy", fillcolor="rgba(77,217,213,0.06)",
            ))
            fig_ci.add_hline(y=95, line_dash="dash", line_color="rgba(239,68,68,0.55)", line_width=1)
            fig_ci.add_hline(y=72, line_dash="dash", line_color="rgba(245,158,11,0.55)", line_width=1)
            fig_ci.update_layout(**{**_CHART_BASE, "height": 240,
                "yaxis": dict(range=[0, 100], ticksuffix="%",
                              showgrid=True, gridcolor="rgba(255,255,255,0.05)", color="#475569")})
            st.plotly_chart(fig_ci, use_container_width=True)
        else:
            st.info("No prediction history for this meter yet.")

    with col_cm:
        st.markdown(
            f'<div style="{_CARD}padding-bottom:4px;">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;">'
            f'<span style="font-size:9px;font-weight:700;letter-spacing:1.5px;color:#94a3b8;">CORRELATION MATRIX</span>'
            f'<span style="background:#1e3a5f;color:#93c5fd;font-size:9px;font-weight:700;'
            f'padding:2px 9px;border-radius:5px;">Pressure vs Flow</span>'
            f'</div></div>',
            unsafe_allow_html=True,
        )
        if not meter_readings.empty:
            sym = "triangle-up" if severity == "critical" else "circle"
            fig_cm = go.Figure(go.Scatter(
                x=meter_readings["flow_rate"], y=meter_readings["pressure"],
                mode="markers",
                marker=dict(color="#4DD9D5", size=7, opacity=0.7, symbol=sym, line=dict(width=0)),
                hovertemplate="Flow: %{x:.2f}<br>Pressure: %{y:.2f}<extra></extra>",
            ))
            fig_cm.update_layout(**{**_CHART_BASE, "height": 240,
                "xaxis": dict(title="FLOW (M³/H)", titlefont=dict(size=8, color="#475569"),
                              showgrid=False, color="#475569"),
                "yaxis": dict(title="PRESSURE (PSI)", titlefont=dict(size=8, color="#475569"),
                              showgrid=True, gridcolor="rgba(255,255,255,0.05)", color="#475569")})
            st.plotly_chart(fig_cm, use_container_width=True)
        else:
            st.info("No readings for correlation analysis.")
