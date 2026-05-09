"""Leak analysis page - detailed investigation view."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from page_components.data_utils import build_meter_snapshot, get_cached_data, load_static_data
from page_components.ui import empty_state, metric_card, page_header, section_header


def show_leak_analysis() -> None:
    """Render the detailed leak analysis page."""
    page_header(
        "Leak Analysis",
        "Investigate suspected leaks with confidence, trend, and supporting indicator views.",
    )

    sidebar = st.sidebar
    sidebar.markdown("### Leak Analysis Filters")
    hours = sidebar.selectbox("Time range", [24, 48, 72, 168], index=0, format_func=lambda value: f"Last {value} hours")

    # Load static data first (fast - zones, meters)
    static_data = load_static_data()
    
    # Load dynamic data with session state caching (ultra-fast on page switches)
    data = get_cached_data(hours=hours)
    
    snapshot = build_meter_snapshot(
        static_data["meters"],
        static_data["zones"],
        data["readings"],
        data["predictions"],
        data["alerts"],
    )

    if snapshot.empty:
        empty_state("No meters or readings are available yet for analysis.")
        return

    zone_options = ["All"] + sorted(snapshot["zone"].dropna().unique().tolist())
    selected_zone = sidebar.selectbox("Zone", zone_options)

    # Get all unique meters with leaks (no confidence filter - show all detected)
    leak_candidates = snapshot.copy()
    if selected_zone != "All":
        leak_candidates = leak_candidates[leak_candidates["zone"] == selected_zone]

    # Get unique meters with leaks detected
    unique_leaks = leak_candidates[leak_candidates["leak_detected"] == True].drop_duplicates("meter_id")
    total_detected = len(unique_leaks)
    critical_count = len(unique_leaks[unique_leaks["severity"] == "critical"])
    warning_count = len(unique_leaks[unique_leaks["severity"] == "warning"])

    # For display table, show all predictions (not deduplicated)
    leaks = leak_candidates if not leak_candidates.empty else pd.DataFrame()
    avg_conf = leaks["confidence"].mean() if not leaks.empty else 0.0
    total_loss = leaks["estimated_loss_l_hr"].sum() if not leaks.empty else 0.0

    metric_columns = st.columns(5)
    with metric_columns[0]:
        metric_card("Detected leaks", str(total_detected), "Meters currently flagged by the model", "danger" if total_detected else "neutral")
    with metric_columns[1]:
        metric_card("Critical", str(critical_count), "Highest-priority investigations", "danger")
    with metric_columns[2]:
        metric_card("Warning", str(warning_count), "Moderate-priority investigations", "warning")
    with metric_columns[3]:
        metric_card("Average confidence", f"{avg_conf * 100:.1f}%", "Average confidence of filtered cases", "neutral")
    with metric_columns[4]:
        metric_card("Est. loss", f"{total_loss:.0f} L/hr", "Combined estimated loss across filtered meters", "warning")

    section_header("Detected leak queue", "Filtered view of meters requiring investigation.")
    if leaks.empty:
        empty_state("No leak cases match the selected filters.")
        return

    queue = leaks[["meter_id", "zone", "location", "leak_type", "confidence", "severity", "status", "estimated_loss_l_hr"]].copy()
    queue["confidence"] = (queue["confidence"] * 100).round(1).astype(str) + "%"
    queue["estimated_loss_l_hr"] = queue["estimated_loss_l_hr"].round(1)
    st.dataframe(
        queue.rename(
            columns={
                "meter_id": "Meter",
                "zone": "Zone",
                "location": "Location",
                "leak_type": "Leak Type",
                "confidence": "Confidence",
                "severity": "Severity",
                "status": "Status",
                "estimated_loss_l_hr": "Est. Loss (L/hr)",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

    top_left, top_right = st.columns([1, 1])
    with top_left:
        section_header("Confidence profile", "Confidence distribution for the current filtered leak cases.")
        fig_conf = px.bar(
            leaks.sort_values("confidence", ascending=False).head(12),
            x="meter_id",
            y="confidence",
            color="severity",
            color_discrete_map={"critical": "#b91c1c", "warning": "#b45309", "normal": "#2870b8"},
            labels={"meter_id": "Meter", "confidence": "Confidence"},
        )
        fig_conf.update_yaxes(tickformat=".0%")
        fig_conf.update_layout(
            margin=dict(l=10, r=10, t=20, b=10),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(255,255,255,0.65)",
            legend_title_text="",
        )
        st.plotly_chart(fig_conf, use_container_width=True)

    with top_right:
        section_header("Zone risk concentration", "Where the filtered leak cases are concentrated.")
        zone_summary = leaks.groupby("zone").agg(
            leak_count=("meter_id", "count"),
            avg_confidence=("confidence", "mean"),
        ).reset_index()
        zone_summary["avg_confidence"] = (zone_summary["avg_confidence"] * 100).round(1)
        fig_zone = px.scatter(
            zone_summary,
            x="zone",
            y="leak_count",
            size="avg_confidence",
            color="avg_confidence",
            labels={"zone": "Zone", "leak_count": "Leak cases", "avg_confidence": "Avg confidence (%)"},
        )
        fig_zone.update_layout(
            margin=dict(l=10, r=10, t=20, b=10),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(255,255,255,0.65)",
        )
        st.plotly_chart(fig_zone, use_container_width=True)

    selected_meter = st.selectbox("Inspect meter", leaks["meter_id"].tolist())
    meter_snapshot = leaks[leaks["meter_id"] == selected_meter].iloc[0]
    meter_readings = data["readings"][data["readings"]["meter_id"] == selected_meter].copy()
    meter_predictions = data["predictions"][data["predictions"]["meter_id"] == selected_meter].copy()

    section_header("Meter trend analysis", "Flow, pressure, and prediction history for the selected meter.")
    if meter_readings.empty:
        empty_state("No reading history is available for the selected meter.")
    else:
        meter_readings = meter_readings.sort_values("timestamp")
        fig_ts = make_subplots(
            rows=3,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.08,
            subplot_titles=("Flow rate", "Pressure", "Leak confidence"),
        )
        fig_ts.add_trace(
            go.Scatter(x=meter_readings["timestamp"], y=meter_readings["flow_rate"], mode="lines", name="Flow", line=dict(color="#2870b8", width=2)),
            row=1,
            col=1,
        )
        fig_ts.add_trace(
            go.Scatter(x=meter_readings["timestamp"], y=meter_readings["pressure"], mode="lines", name="Pressure", line=dict(color="#15803d", width=2)),
            row=2,
            col=1,
        )
        if not meter_predictions.empty:
            meter_predictions = meter_predictions.sort_values("timestamp")
            fig_ts.add_trace(
                go.Scatter(
                    x=meter_predictions["timestamp"],
                    y=meter_predictions["confidence"],
                    mode="lines+markers",
                    name="Confidence",
                    line=dict(color="#b45309", width=2),
                ),
                row=3,
                col=1,
            )
            fig_ts.add_hline(y=0.7, line_dash="dash", line_color="#b45309", row=3, col=1)
            fig_ts.add_hline(y=0.9, line_dash="dash", line_color="#b91c1c", row=3, col=1)
        fig_ts.update_layout(
            height=700,
            margin=dict(l=10, r=10, t=30, b=10),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(255,255,255,0.65)",
            legend_title_text="",
        )
        st.plotly_chart(fig_ts, use_container_width=True)

    detail_columns = st.columns(4)
    with detail_columns[0]:
        metric_card("Meter", meter_snapshot["meter_id"], meter_snapshot["location"], "neutral")
    with detail_columns[1]:
        metric_card("Current flow", f"{meter_snapshot['current_flow']:.2f}", "Most recent flow reading", "warning")
    with detail_columns[2]:
        metric_card("Current pressure", f"{meter_snapshot['current_pressure']:.2f}", "Most recent pressure reading", "success")
    with detail_columns[3]:
        metric_card("Minimum night flow", f"{meter_snapshot['mnf']:.2f}", "Average low-demand overnight flow", "neutral")

    section_header("Supporting indicators", "Evidence used to understand why a meter is being flagged.")
    indicator_columns = st.columns(2)
    with indicator_columns[0]:
        feature_frame = pd.DataFrame(
            [
                {"Indicator": "Flow variance", "Value": round(float(meter_snapshot["flow_variance"]), 4)},
                {"Indicator": "Pressure variance", "Value": round(float(meter_snapshot["pressure_variance"]), 4)},
                {"Indicator": "Average flow", "Value": round(float(meter_snapshot["avg_flow"]), 3)},
                {"Indicator": "Average pressure", "Value": round(float(meter_snapshot["avg_pressure"]), 3)},
            ]
        )
        st.dataframe(feature_frame, use_container_width=True, hide_index=True)
    with indicator_columns[1]:
        fig_features = px.scatter(
            leaks,
            x="current_flow",
            y="current_pressure",
            color="severity",
            size="confidence",
            hover_name="meter_id",
            color_discrete_map={"critical": "#b91c1c", "warning": "#b45309", "normal": "#2870b8"},
            labels={"current_flow": "Current flow", "current_pressure": "Current pressure"},
        )
        fig_features.update_layout(
            margin=dict(l=10, r=10, t=20, b=10),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(255,255,255,0.65)",
            legend_title_text="",
        )
        st.plotly_chart(fig_features, use_container_width=True)
