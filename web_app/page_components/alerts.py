"""Alerts page - operational queue for leak response."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from backend.mysql_database_manager import db_manager
from page_components.data_utils import build_meter_snapshot, get_cached_data, load_static_data
from page_components.ui import empty_state, metric_card, page_header, section_header


def _format_datetime_safe(series: pd.Series) -> pd.Series:
    """Safely format datetime series, handling non-datetime values."""
    if series.empty:
        return series
    # Convert to datetime, coercing errors to NaT
    dt_series = pd.to_datetime(series, errors="coerce")
    # Format valid datetimes, leave NaT as empty string
    return dt_series.apply(lambda x: x.strftime("%Y-%m-%d %H:%M") if pd.notna(x) else "")


def show_alerts() -> None:
    """Render the alerts management page."""
    page_header(
        "Alerts",
        "Review active leak alerts, filter by severity, and close resolved cases.",
    )

    # Load static data first (fast - zones, meters)
    static_data = load_static_data()
    
    # Load dynamic data with session state caching (ultra-fast on page switches)
    data = get_cached_data(hours=24)
    
    # Build snapshot for consistent leak metrics
    snapshot = build_meter_snapshot(
        static_data["meters"],
        static_data["zones"],
        data["readings"],
        data["predictions"],
        data["alerts"],
    )

    # Calculate leak metrics from snapshot (consistent with Overview and Leak Analysis)
    if not snapshot.empty:
        # Get unique meters with leaks
        unique_leaks = snapshot[snapshot["leak_detected"] == True].drop_duplicates("meter_id")
        total_detected = len(unique_leaks)
        critical_count = len(unique_leaks[unique_leaks["severity"] == "critical"])
        warning_count = len(unique_leaks[unique_leaks["severity"] == "warning"])
    else:
        total_detected = 0
        critical_count = 0
        warning_count = 0

    summary_columns = st.columns(4)
    with summary_columns[0]:
        metric_card("Critical", str(critical_count), "Meters with critical leaks (≥95% confidence)", "danger")
    with summary_columns[1]:
        metric_card("Warnings", str(warning_count), "Meters with warning leaks (85-94% confidence)", "warning")
    with summary_columns[2]:
        metric_card("Detected Leaks", str(total_detected), "Total unique meters with leaks", "neutral")
    with summary_columns[3]:
        metric_card("Active Meters", str(len(static_data["meters"])), "Meters under watch", "success")

    # Filter options
    filter_columns = st.columns([1])
    with filter_columns[0]:
        severity_filter = st.selectbox("Severity", ["All", "critical", "warning", "normal"], format_func=str.title)

    # Get leak data from snapshot (consistent with other pages)
    if not snapshot.empty:
        # Get all leaks (no confidence filter - show all detected)
        leak_alerts = snapshot[snapshot["leak_detected"] == True].copy()

        # Apply severity filter
        if severity_filter != "All":
            leak_alerts = leak_alerts[leak_alerts["severity"] == severity_filter]

        # Sort and get most recent per meter
        leak_alerts = leak_alerts.sort_values("prediction_time", ascending=False)
        leak_alerts = leak_alerts.drop_duplicates(subset=["meter_id"], keep="first")
        total_unique = len(leak_alerts)
    else:
        leak_alerts = pd.DataFrame()
        total_unique = 0

    section_header(f"Active Leak Alerts ({total_unique} unique meters)", "Most recent alert per meter. Resolved alerts are auto-archived after 7 days.")
    if leak_alerts.empty:
        empty_state("No alerts match the selected filters.")
        return

    # Display leak alerts from snapshot data
    display = leak_alerts[["meter_id", "zone", "location", "leak_type", "confidence", "severity", "status", "prediction_time"]].copy()
    display["confidence"] = (display["confidence"] * 100).round(1).astype(str) + "%"
    display = display.rename(
        columns={
            "meter_id": "Meter",
            "zone": "Zone",
            "location": "Location",
            "leak_type": "Leak Type",
            "confidence": "Confidence",
            "severity": "Severity",
            "status": "Status",
            "prediction_time": "Detected At",
        }
    )
    st.dataframe(display, use_container_width=True, hide_index=True)
