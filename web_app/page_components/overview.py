"""Overview page - quick operational summary."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st

from backend.database_manager import db_manager
from page_components.data_utils import (
    build_meter_snapshot,
    format_datetime,
    get_cached_data,
    get_service_states,
    latest_timestamp,
    load_static_data,
)
from page_components.ui import empty_state, metric_card, page_header, render_status_row, section_header


def show_overview() -> None:
    """Render the operational overview page."""
    page_header(
        "Overview",
        "At-a-glance monitoring for the current water network state.",
    )

    # Load static data first (fast - zones, meters)
    static_data = load_static_data()
    
    # Load dynamic data with session state caching (ultra-fast on page switches)
    data = get_cached_data(hours=24)
    
    stats = db_manager.get_dashboard_stats()
    snapshot = build_meter_snapshot(
        static_data["meters"],
        static_data["zones"],
        data["readings"],
        data["predictions"],
        data["alerts"],
    )

    latest_reading = latest_timestamp(data["readings"], "timestamp")
    latest_prediction = latest_timestamp(data["predictions"], "timestamp")
    service_items = [(state.name, state.tone) for state in get_service_states()]
    render_status_row(service_items)

    # Calculate leak metrics from snapshot (consistent with Leak Analysis page)
    if not snapshot.empty:
        # Get unique meters with leaks (to avoid counting same meter multiple times)
        unique_leaks = snapshot[snapshot["leak_detected"] == True].drop_duplicates("meter_id")
        total_detected = len(unique_leaks)
        critical_count = len(unique_leaks[unique_leaks["severity"] == "critical"])
        warning_count = len(unique_leaks[unique_leaks["severity"] == "warning"])
        # High-confidence leaks (leak_detected=True AND confidence >= 85%)
        high_conf_leaks = unique_leaks[unique_leaks["confidence"] >= 0.85]
        high_conf = len(high_conf_leaks)
    else:
        total_detected = 0
        critical_count = 0
        warning_count = 0
        high_conf = 0

    metric_columns = st.columns(4)
    with metric_columns[0]:
        metric_card("Detected Leaks", str(total_detected), "Meters with leak_detected=True", "danger")
    with metric_columns[1]:
        metric_card("Critical", str(critical_count), "Meters with ≥95% confidence", "danger")
    with metric_columns[2]:
        metric_card("Warning", str(warning_count), "Meters with 85-94% confidence", "warning")
    with metric_columns[3]:
        metric_card("High Confidence", str(high_conf), "Meters with ≥85% confidence", "neutral")

    # Summary stats from all pages
    st.markdown("---")
    summary_cols = st.columns(5)
    with summary_cols[0]:
        st.metric("Total Meters", len(static_data["meters"]) if not static_data["meters"].empty else 0)
    with summary_cols[1]:
        st.metric("Total Zones", len(static_data["zones"]) if not static_data["zones"].empty else 0)
    with summary_cols[2]:
        active_alerts = len(data["alerts"][data["alerts"]["status"] == "active"]) if not data["alerts"].empty else 0
        st.metric("Active Alerts", active_alerts)
    with summary_cols[3]:
        total_readings = len(data["readings"]) if not data["readings"].empty else 0
        st.metric("Readings (24h)", total_readings)
    with summary_cols[4]:
        total_predictions = len(data["predictions"]) if not data["predictions"].empty else 0
        st.metric("Predictions", total_predictions)

    col_left, col_right = st.columns([1.5, 1])

    with col_left:
        section_header("Network trend", "Recent average flow and pressure from incoming smart meter readings.")
        readings = data["readings"].copy()
        if readings.empty:
            empty_state("No recent meter readings are available yet.")
        else:
            readings["hour_bucket"] = readings["timestamp"].dt.floor("h")
            trend = readings.groupby("hour_bucket").agg(
                avg_flow=("flow_rate", "mean"),
                avg_pressure=("pressure", "mean"),
            ).reset_index()
            fig = px.line(
                trend,
                x="hour_bucket",
                y=["avg_flow", "avg_pressure"],
                markers=True,
                labels={"value": "Average value", "variable": "Signal", "hour_bucket": "Time"},
            )
            fig.update_layout(
                margin=dict(l=10, r=10, t=20, b=10),
                legend_title_text="",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(255,255,255,0.65)",
            )
            st.plotly_chart(fig, use_container_width=True)

    with col_right:
        section_header("System heartbeat", "Service readiness and data freshness.")
        heartbeat = pd.DataFrame(
            [
                {
                    "Service": state.name,
                    "Status": "Healthy" if state.healthy else "Attention",
                    "Detail": state.detail,
                }
                for state in get_service_states()
            ]
        )
        st.dataframe(heartbeat, use_container_width=True, hide_index=True)
        st.caption(f"Latest reading: {format_datetime(latest_reading)}")
        st.caption(f"Latest prediction: {format_datetime(latest_prediction)}")

    lower_left, lower_right = st.columns([1.25, 1])

    with lower_left:
        section_header("Recent alerts", "Newest alerts raised by the prediction loop.")
        alerts = data["alerts"].copy()
        if alerts.empty:
            empty_state("No alerts have been generated in the last 24 hours.")
        else:
            meters = data["meters"][["meter_id", "location"]].copy() if not data["meters"].empty else pd.DataFrame()
            if not meters.empty and "meter_id" in alerts.columns:
                alerts = alerts.merge(meters, on="meter_id", how="left")
            alerts["created_at"] = alerts["created_at"].dt.strftime("%Y-%m-%d %H:%M")
            display_columns = ["created_at", "severity", "title", "meter_id", "location", "status"]
            available = [column for column in display_columns if column in alerts.columns]
            st.dataframe(
                alerts[available].head(8),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "created_at": "Time",
                    "severity": "Severity",
                    "title": "Alert",
                    "meter_id": "Meter",
                    "location": "Location",
                    "status": "Status",
                },
            )

    with lower_right:
        section_header("Priority meters", "Meters with the highest current leak confidence.")
        if snapshot.empty:
            empty_state("Meter inventory has not been loaded yet.")
        else:
            focus = snapshot[["meter_id", "zone", "location", "confidence", "severity", "estimated_loss_l_hr"]].copy()
            focus["confidence"] = (focus["confidence"] * 100).round(1).astype(str) + "%"
            focus["estimated_loss_l_hr"] = focus["estimated_loss_l_hr"].round(1)
            st.dataframe(
                focus.head(8),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "meter_id": "Meter",
                    "zone": "Zone",
                    "location": "Location",
                    "confidence": "Confidence",
                    "severity": "Severity",
                    "estimated_loss_l_hr": "Est. Loss (L/hr)",
                },
            )

    if not snapshot.empty:
        section_header("Zone summary", "Where attention is concentrated across the network.")
        zone_summary = snapshot.groupby("zone").agg(
            meters=("meter_id", "count"),
            leaks=("leak_detected", "sum"),
            avg_confidence=("confidence", "mean"),
        ).reset_index()
        zone_summary["avg_confidence"] = (zone_summary["avg_confidence"] * 100).round(1)
        fig_zone = px.bar(
            zone_summary,
            x="zone",
            y="leaks",
            color="avg_confidence",
            labels={"zone": "Zone", "leaks": "Detected leaks", "avg_confidence": "Avg confidence (%)"},
        )
        fig_zone.update_layout(
            margin=dict(l=10, r=10, t=20, b=10),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(255,255,255,0.65)",
        )
        st.plotly_chart(fig_zone, use_container_width=True)
