"""Zones and assets page - configured infrastructure view."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from backend.mysql_database_manager import db_manager
from page_components.ui import empty_state, metric_card, page_header, section_header


def show_zones_assets() -> None:
    """Render the zones and asset inventory page."""
    page_header(
        "Zones & Assets",
        "Inspect configured zones, meter coverage, and the structure of the monitored network.",
    )

    zones_df = db_manager.get_all_zones()
    meters_df = db_manager.get_all_meters()

    if zones_df.empty:
        empty_state("No zones are configured in the database yet.")
        return

    meter_counts = meters_df.groupby("zone_id").size().reset_index(name="meters_count") if not meters_df.empty else pd.DataFrame(columns=["zone_id", "meters_count"])
    zones_df = zones_df.merge(meter_counts, on="zone_id", how="left")
    zones_df["meters_count"] = zones_df["meters_count"].fillna(0).astype(int)

    metric_columns = st.columns(4)
    with metric_columns[0]:
        metric_card("Total Zones", str(len(zones_df)), "Configured zones in the data layer", "neutral")
    with metric_columns[1]:
        metric_card("Active Zones", str(int((zones_df["status"] == "active").sum())), "Zones currently marked active", "success")
    with metric_columns[2]:
        metric_card("Total Meters", str(len(meters_df)), "Meters assigned across all zones", "neutral")
    with metric_columns[3]:
        metric_card("Connections", f"{int(zones_df['estimated_connections'].sum()):,}", "Estimated customer connections", "warning")

    filter_columns = st.columns(2)
    with filter_columns[0]:
        region = st.selectbox("Region", ["All"] + sorted(zones_df["region"].dropna().unique().tolist()))
    with filter_columns[1]:
        zone_type = st.selectbox("Zone type", ["All"] + sorted(zones_df["type"].dropna().unique().tolist()))

    filtered = zones_df.copy()
    if region != "All":
        filtered = filtered[filtered["region"] == region]
    if zone_type != "All":
        filtered = filtered[filtered["type"] == zone_type]

    section_header("Zone inventory", "Each zone row shows status, type, estimated connections, and meter coverage.")
    display = filtered[["zone_id", "name", "region", "type", "status", "meters_count", "estimated_connections"]].copy()
    display = display.rename(
        columns={
            "zone_id": "Zone ID",
            "name": "Name",
            "region": "Region",
            "type": "Type",
            "status": "Status",
            "meters_count": "Meters",
            "estimated_connections": "Estimated Connections",
        }
    )
    st.dataframe(display, use_container_width=True, hide_index=True)

    selected_zone = st.selectbox("Inspect zone", filtered["zone_id"].tolist())
    zone_row = zones_df[zones_df["zone_id"] == selected_zone].iloc[0]
    zone_meters = meters_df[meters_df["zone_id"] == selected_zone].copy() if not meters_df.empty else pd.DataFrame()

    detail_columns = st.columns(3)
    with detail_columns[0]:
        metric_card("Zone", zone_row["name"], zone_row["region"].replace("_", " ").title(), "neutral")
    with detail_columns[1]:
        metric_card("Meters", str(int(zone_row["meters_count"])), "Meters deployed in this zone", "success")
    with detail_columns[2]:
        metric_card("Connections", f"{int(zone_row['estimated_connections']):,}", "Estimated served connections", "warning")

    st.caption(zone_row.get("description", "No description available for this zone."))

    section_header("Meters in zone", "Meter inventory for the currently selected zone.")
    if zone_meters.empty:
        empty_state("No meters are linked to this zone yet.")
    else:
        meter_display = zone_meters[["meter_id", "location", "meter_type", "status", "flow_rate"]].copy()
        meter_display = meter_display.rename(
            columns={
                "meter_id": "Meter ID",
                "location": "Location",
                "meter_type": "Type",
                "status": "Status",
                "flow_rate": "Baseline Flow",
            }
        )
        st.dataframe(meter_display, use_container_width=True, hide_index=True)
