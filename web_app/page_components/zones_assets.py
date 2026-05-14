"""Zones and assets page — Risk Score Heatmap and inventory."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from backend.mysql_database_manager import db_manager
from page_components.data_utils import build_meter_snapshot, get_cached_data, load_static_data
from page_components.ui import empty_state, metric_card, page_header, section_header, show_glowing_table


# ── Card HTML renderers ───────────────────────────────────────────────────────

def _big_card(zone: pd.Series, is_top: bool = False) -> None:
    region = str(zone.get("region", "")).replace("_", " ").upper()
    name = str(zone.get("name", ""))
    flagged = int(zone.get("flagged", 0))
    warn = "TOP" if is_top else ""
    st.markdown(
        f"""<div style="background:#162032;border:1px solid #2a3a50;border-radius:10px;
            padding:20px 18px 16px;margin-bottom:12px;min-height:155px;">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;">
            <div style="color:#8899aa;font-size:10px;letter-spacing:1.5px;font-weight:600;">{region}</div>
            <div style="font-size:12px;color:#e87878;font-weight:700;line-height:1;">{warn}</div>
          </div>
          <div style="font-size:20px;font-weight:700;color:#e2e8f0;margin:6px 0 10px;">{name}</div>
          <div style="font-size:44px;font-weight:800;color:#e87878;line-height:1;">{flagged}</div>
          <div style="display:flex;justify-content:space-between;align-items:center;margin-top:8px;">
            <span style="color:#8899aa;font-size:12px;">meters flagged</span>
            <span style="background:#3d1a1a;color:#e87878;font-size:10px;font-weight:700;
                  padding:2px 9px;border-radius:12px;">HIGH</span>
          </div>
        </div>""",
        unsafe_allow_html=True,
    )


def _medium_high_card(zone: pd.Series) -> None:
    region = str(zone.get("region", "")).replace("_", " ").upper()
    name = str(zone.get("name", ""))
    flagged = int(zone.get("flagged", 0))
    st.markdown(
        f"""<div style="background:#162032;border:1px solid #2a3a50;border-radius:10px;
            padding:14px 16px;margin-bottom:12px;min-height:100px;">
          <div style="color:#8899aa;font-size:9px;letter-spacing:1.5px;font-weight:600;">{region}</div>
          <div style="font-size:16px;font-weight:700;color:#e2e8f0;margin:4px 0 8px;">{name}</div>
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <span style="font-size:26px;font-weight:800;color:#e87878;">{flagged}</span>
            <span style="background:#3d1a1a;color:#e87878;font-size:10px;font-weight:700;
                  padding:2px 8px;border-radius:12px;">HIGH</span>
          </div>
        </div>""",
        unsafe_allow_html=True,
    )


def _medium_mid_card(zone: pd.Series) -> None:
    region = str(zone.get("region", "")).replace("_", " ").upper()
    name = str(zone.get("name", ""))
    flagged = int(zone.get("flagged", 0))
    st.markdown(
        f"""<div style="background:#162032;border:1px solid #2a3a50;border-radius:10px;
            padding:14px 16px;margin-bottom:12px;min-height:100px;">
          <div style="color:#8899aa;font-size:9px;letter-spacing:1.5px;font-weight:600;">{region}</div>
          <div style="font-size:16px;font-weight:700;color:#e2e8f0;margin:4px 0 8px;">{name}</div>
          <div style="display:flex;justify-content:space-between;align-items:center;">
            <span style="font-size:18px;font-weight:700;color:#4DD9D5;">{flagged} Flagged</span>
            <span style="background:#0d2d2c;color:#4DD9D5;font-size:10px;font-weight:700;
                  padding:2px 8px;border-radius:12px;">MID</span>
          </div>
        </div>""",
        unsafe_allow_html=True,
    )


def _small_card(zone: pd.Series) -> None:
    region = str(zone.get("region", "")).replace("_", " ").upper()
    name = str(zone.get("name", ""))
    flagged = int(zone.get("flagged", 0))
    total = int(zone.get("meters_count", 0))
    if flagged > 0:
        count_html = (
            f'<div style="font-size:22px;font-weight:800;color:#e87878;">{total}</div>'
            f'<div style="color:#e87878;font-size:9px;font-weight:700;letter-spacing:1px;">HIGH RISK</div>'
        )
    else:
        count_html = (
            f'<div style="font-size:22px;font-weight:800;color:#c5d0dc;">{total}</div>'
            f'<div style="color:#8899aa;font-size:9px;letter-spacing:1px;">METERS</div>'
        )
    st.markdown(
        f"""<div style="background:#162032;border:1px solid #2a3a50;border-radius:10px;
            padding:12px 14px;margin-bottom:10px;min-height:90px;">
          <div style="color:#8899aa;font-size:9px;letter-spacing:1.5px;font-weight:600;">{region}</div>
          <div style="font-size:13px;font-weight:700;color:#e2e8f0;margin:3px 0 8px;">{name}</div>
          {count_html}
        </div>""",
        unsafe_allow_html=True,
    )


# ── Heatmap section ───────────────────────────────────────────────────────────

def _render_risk_heatmap(zones_df: pd.DataFrame) -> None:
    """Risk Score Heatmap by Zone — cards sorted by flagged meter count."""
    static_data = load_static_data()
    data = get_cached_data()
    snapshot = build_meter_snapshot(
        static_data["meters"], static_data["zones"],
        data["readings"], data["predictions"], data["alerts"],
    )

    if not snapshot.empty and "zone" in snapshot.columns and "leak_detected" in snapshot.columns:
        flagged_counts = (
            snapshot[snapshot["leak_detected"] == True]
            .groupby("zone").size()
            .reset_index(name="flagged")
        )
    else:
        flagged_counts = pd.DataFrame(columns=["zone", "flagged"])

    zd = zones_df.merge(flagged_counts, left_on="name", right_on="zone", how="left")
    zd["flagged"] = zd["flagged"].fillna(0).astype(int)
    zd = zd.sort_values("flagged", ascending=False).reset_index(drop=True)

    high = zd[zd["flagged"] >= 5].reset_index(drop=True)
    mid  = zd[(zd["flagged"] > 0) & (zd["flagged"] < 5)].reset_index(drop=True)
    low  = zd[zd["flagged"] == 0].reset_index(drop=True)

    # Header + legend
    hcol, lcol = st.columns([5, 2])
    with hcol:
        st.markdown("## Risk Score Heatmap by Zone")
        st.caption("Real-time infrastructure health and flagged meter density per municipal zone.")
    with lcol:
        st.markdown(
            '<div style="display:flex;gap:18px;justify-content:flex-end;padding-top:18px;">'
            '<span style="display:inline-flex;align-items:center;gap:5px;color:#e87878;font-size:12px;font-weight:700;">'
            '<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#e87878;"></span> HIGH RISK</span>'
            '<span style="display:inline-flex;align-items:center;gap:5px;color:#4DD9D5;font-size:12px;font-weight:700;">'
            '<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:#4DD9D5;"></span> MEDIUM RISK</span>'
            '</div>',
            unsafe_allow_html=True,
        )

    # CRITICAL PRIORITY
    if not high.empty:
        st.markdown(
            '<span style="border:1px solid #e87878;color:#e87878;padding:3px 12px;'
            'border-radius:4px;font-size:11px;font-weight:700;letter-spacing:1.5px;">'
            'CRITICAL PRIORITY</span>',
            unsafe_allow_html=True,
        )
        st.write("")
        top3 = high.head(3)
        cols = st.columns(len(top3))
        for i, (_, z) in enumerate(top3.iterrows()):
            with cols[i]:
                _big_card(z, is_top=(i == 0))
        rest = high.iloc[3:].reset_index(drop=True)
        if not rest.empty:
            for chunk_start in range(0, len(rest), 4):
                chunk = rest.iloc[chunk_start:chunk_start + 4]
                cols = st.columns(len(chunk))
                for i, (_, z) in enumerate(chunk.iterrows()):
                    with cols[i]:
                        _medium_high_card(z)

    # ACTIVE MONITORING
    if not mid.empty or not low.empty:
        st.markdown(
            '<span style="border:1px solid #4DD9D5;color:#4DD9D5;padding:3px 12px;'
            'border-radius:4px;font-size:11px;font-weight:700;letter-spacing:1.5px;">'
            'ACTIVE MONITORING</span>',
            unsafe_allow_html=True,
        )
        st.write("")
        if not mid.empty and not low.empty:
            left_col, right_col = st.columns([2, 3])
            with left_col:
                grid = st.columns(2)
                for i, (_, z) in enumerate(mid.iterrows()):
                    with grid[i % 2]:
                        _medium_mid_card(z)
            with right_col:
                grid = st.columns(3)
                for i, (_, z) in enumerate(low.iterrows()):
                    with grid[i % 3]:
                        _small_card(z)
        elif not mid.empty:
            cols = st.columns(min(len(mid), 4))
            for i, (_, z) in enumerate(mid.iterrows()):
                with cols[i % 4]:
                    _medium_mid_card(z)
        else:
            cols = st.columns(min(len(low), 5))
            for i, (_, z) in enumerate(low.iterrows()):
                with cols[i % 5]:
                    _small_card(z)


# ── Page entry point ──────────────────────────────────────────────────────────

def show_zones_assets() -> None:
    """Render the zones and asset inventory page."""
    page_header(
        "Zones & Assets",
        "Real-time infrastructure health and flagged meter density per municipal zone.",
    )

    zones_df = db_manager.get_all_zones()
    meters_df = db_manager.get_all_meters()

    if zones_df.empty:
        empty_state("No zones are configured in the database yet.")
        return

    meter_counts = (
        meters_df.groupby("zone_id").size().reset_index(name="meters_count")
        if not meters_df.empty
        else pd.DataFrame(columns=["zone_id", "meters_count"])
    )
    zones_df = zones_df.merge(meter_counts, on="zone_id", how="left")
    zones_df["meters_count"] = zones_df["meters_count"].fillna(0).astype(int)

    # Top metrics
    mc = st.columns(4)
    with mc[0]:
        metric_card("Total Zones", str(len(zones_df)), "Configured zones", "neutral")
    with mc[1]:
        metric_card("Active Zones", str(int((zones_df["status"] == "active").sum())), "Currently active", "success")
    with mc[2]:
        metric_card("Total Meters", str(len(meters_df)), "Meters across all zones", "neutral")
    with mc[3]:
        metric_card("Connections", f"{int(zones_df['estimated_connections'].sum()):,}", "Estimated customer connections", "warning")

    st.divider()
    _render_risk_heatmap(zones_df)
    st.divider()

    # Inventory in collapsible section
    with st.expander("Zone & Meter Inventory", expanded=False):
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

        section_header("Zone inventory", "Status, type, connections, and meter coverage per zone.")
        display = filtered[["zone_id", "name", "region", "type", "status", "meters_count", "estimated_connections"]].copy()
        display = display.rename(columns={
            "zone_id": "Zone ID", "name": "Name", "region": "Region", "type": "Type",
            "status": "Status", "meters_count": "Meters", "estimated_connections": "Estimated Connections",
        })
        show_glowing_table(display)

        zone_ids = filtered["zone_id"].tolist()
        if not zone_ids:
            st.info("No zones match the selected filters.")
            return
        selected_zone = st.selectbox("Inspect zone", zone_ids)
        zone_row = zones_df[zones_df["zone_id"] == selected_zone].iloc[0]
        zone_meters = (
            meters_df[meters_df["zone_id"] == selected_zone].copy()
            if not meters_df.empty
            else pd.DataFrame()
        )

        detail_columns = st.columns(3)
        with detail_columns[0]:
            metric_card("Zone", zone_row["name"], zone_row["region"].replace("_", " ").title(), "neutral")
        with detail_columns[1]:
            metric_card("Meters", str(int(zone_row["meters_count"])), "Deployed in this zone", "success")
        with detail_columns[2]:
            metric_card("Connections", f"{int(zone_row['estimated_connections']):,}", "Estimated served", "warning")

        st.caption(zone_row.get("description", "No description available for this zone."))

        section_header("Meters in zone", "Meter inventory for the selected zone.")
        if zone_meters.empty:
            empty_state("No meters are linked to this zone yet.")
        else:
            meter_display = zone_meters[["meter_id", "location", "meter_type", "status", "flow_rate"]].copy()
            meter_display = meter_display.rename(columns={
                "meter_id": "Meter ID", "location": "Location", "meter_type": "Type",
                "status": "Status", "flow_rate": "Baseline Flow",
            })
            show_glowing_table(meter_display)
