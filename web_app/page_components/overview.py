import html as _html

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from backend.mysql_database_manager import db_manager
from page_components.data_utils import (
    build_meter_snapshot,
    get_cached_data,
    get_service_states,
    latest_timestamp,
    format_datetime,
    load_static_data,
)
from page_components.ui import render_metric, render_status_pill, section_header, show_glowing_table


def show_overview():
    # ── Load data ─────────────────────────────────────────────────────────────
    data        = get_cached_data(hours=24)
    static_data = load_static_data()
    snapshot    = build_meter_snapshot(
        static_data["meters"], static_data["zones"],
        data["readings"], data["predictions"], data["alerts"],
    )
    service_states    = get_service_states()
    latest_reading    = latest_timestamp(data["readings"],    "timestamp")
    latest_prediction = latest_timestamp(data["predictions"], "timestamp")

    total_meters = len(static_data["meters"]) if not static_data["meters"].empty else 0
    total_zones  = len(static_data["zones"])  if not static_data["zones"].empty  else 0

    # Query all open alerts directly — no time window so alerts older than 24 h
    # (still unresolved) are counted correctly.
    _open_df = db_manager._query_to_df(
        "SELECT COUNT(*) AS n, COUNT(DISTINCT meter_id) AS meters "
        "FROM alerts WHERE status != 'resolved'"
    )
    active_alerts  = int(_open_df.iloc[0]["n"])      if not _open_df.empty else 0
    total_detected = int(_open_df.iloc[0]["meters"]) if not _open_df.empty else 0

    # ── Header ────────────────────────────────────────────────────────────────
    st.title("Overview")
    st.caption(
        f"Real-time telemetry and predictive leak analysis — "
        f"{total_meters} active smart meters across {total_zones} zones."
    )
    st.markdown("<br>", unsafe_allow_html=True)

    # ── KPI row ───────────────────────────────────────────────────────────────
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        render_metric("Total Meters",  str(total_meters),   "text-cyan")
    with m2:
        render_metric("Active Leaks",  str(total_detected), "text-emerald")
    with m3:
        render_metric("Total Alerts",  str(active_alerts),  "text-amber")
    with m4:
        render_metric("Zones",         str(total_zones),    "text-cyan")

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Network trend + System heartbeat ──────────────────────────────────────
    col_trend, col_heart = st.columns([2, 1], gap="medium")

    with col_trend:
        section_header("Network Trend", "Hourly avg flow vs pressure across the network")
        if data["readings"].empty:
            st.info("No meter readings available yet.")
        else:
            readings = data["readings"].copy()
            readings["hour"] = readings["timestamp"].dt.floor("h")
            trend = (
                readings.groupby("hour")
                .agg(Flow=("flow_rate", "mean"), Pressure=("pressure", "mean"))
                .reset_index()
                .tail(24)
            )
            _gc = "rgba(255,255,255,0.04)"
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=trend["hour"], y=trend["Flow"],
                name="Avg Flow",
                mode="lines",
                line=dict(color="#22c55e", width=2.5),
                fill="tozeroy", fillcolor="rgba(34,197,94,0.07)",
                yaxis="y1",
                hovertemplate="<b>%{x|%H:%M}</b><br>Flow: %{y:.3f} m³/h<extra></extra>",
            ))
            fig.add_trace(go.Scatter(
                x=trend["hour"], y=trend["Pressure"],
                name="Avg Pressure",
                mode="lines",
                line=dict(color="#3b82f6", width=2.5),
                yaxis="y2",
                hovertemplate="<b>%{x|%H:%M}</b><br>Pressure: %{y:.1f} PSI<extra></extra>",
            ))
            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font_color="#94a3b8",
                height=270,
                margin=dict(l=55, r=55, t=10, b=35),
                legend=dict(
                    orientation="h", x=0.5, xanchor="center", y=1.14,
                    font=dict(size=10, color="#94a3b8"),
                    bgcolor="rgba(0,0,0,0)",
                ),
                xaxis=dict(
                    showgrid=True, gridcolor=_gc,
                    tickformat="%H:%M",
                    title=dict(text="Time (last 24 h)", font=dict(size=9, color="#475569")),
                    tickfont=dict(size=9, color="#64748b"),
                    zeroline=False,
                ),
                yaxis=dict(
                    title=dict(text="Flow (m³/h)", font=dict(size=9, color="#22c55e")),
                    tickfont=dict(size=9, color="#22c55e"),
                    showgrid=True, gridcolor=_gc,
                    zeroline=False,
                ),
                yaxis2=dict(
                    title=dict(text="Pressure (PSI)", font=dict(size=9, color="#3b82f6")),
                    tickfont=dict(size=9, color="#3b82f6"),
                    overlaying="y", side="right",
                    showgrid=False, zeroline=False,
                ),
                hovermode="x unified",
            )
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    with col_heart:
        section_header("System Heartbeat", "Service readiness and data freshness")
        for svc in service_states:
            c_info, c_stat = st.columns([3, 1])
            with c_info:
                st.markdown(
                    f"<p style='margin:0;font-size:0.75rem;font-weight:700;"
                    f"text-transform:uppercase;letter-spacing:0.07em;color:#94a3b8;'>{_html.escape(svc.name)}</p>"
                    f"<p style='margin:0 0 4px;font-size:0.78rem;color:#475569;'>{_html.escape(svc.detail)}</p>",
                    unsafe_allow_html=True,
                )
            with c_stat:
                render_status_pill("Healthy" if svc.healthy else "Needs Attention", is_healthy=svc.healthy)
            st.divider()
        st.caption(
            f"Last reading: {format_datetime(latest_reading)}  \n"
            f"Last prediction: {format_datetime(latest_prediction)}"
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Recent alerts + Priority meters ───────────────────────────────────────
    col_alerts, col_priority = st.columns([3, 2], gap="medium")

    with col_alerts:
        section_header("Recent Alerts", "Newest alerts raised by the prediction loop")
        alerts = data["alerts"].copy()
        if alerts.empty:
            st.info("No alerts in the last 24 hours.")
        else:
            if not data["meters"].empty and "meter_id" in alerts.columns:
                alerts = alerts.merge(
                    data["meters"][["meter_id", "location"]], on="meter_id", how="left"
                )
            alerts["created_at"] = alerts["created_at"].dt.strftime("%H:%M")
            cols = [c for c in ["created_at", "severity", "title", "meter_id", "location"] if c in alerts.columns]
            show_glowing_table(
                alerts[cols].head(8).rename(columns={
                    "created_at": "TIME",
                    "severity":   "SEVERITY",
                    "title":      "ALERT",
                    "meter_id":   "METER",
                    "location":   "LOCATION",
                })
            )

    with col_priority:
        section_header("Priority Meters", "Meters with highest current leak confidence")
        if snapshot.empty:
            st.info("Meter inventory not loaded.")
        else:
            focus = snapshot[["meter_id", "zone", "confidence"]].copy()
            focus["confidence_pct"] = (focus["confidence"] * 100).round(1)
            st.dataframe(
                focus.head(8),
                use_container_width=True, hide_index=True,
                column_config={
                    "meter_id":       st.column_config.TextColumn("METER",  width="small"),
                    "zone":           st.column_config.TextColumn("ZONE",   width="small"),
                    "confidence":     None,
                    "confidence_pct": st.column_config.ProgressColumn(
                        "CONFIDENCE", format="%.1f%%", min_value=0, max_value=100,
                    ),
                },
            )

    # ── Footer strip ──────────────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
    f1, f2, f3 = st.columns([2, 4, 2])
    with f1:
        st.caption(f"Meters: {total_meters}  ·  Zones: {total_zones}  ·  Alerts: {active_alerts}")
    with f3:
        render_status_pill("System Live", is_healthy=True)
