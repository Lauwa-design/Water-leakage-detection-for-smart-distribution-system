"""Reports Page - THIWASCO Leak Detection System"""

from __future__ import annotations

import io
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

from backend.mysql_database_manager import db_manager
from backend.report_generator import report_generator
from backend.rbac import has_permission, Permissions, is_nrw_officer, show_permission_denied
from page_components.ui import page_header, show_glowing_table


# ── CSS ───────────────────────────────────────────────────────────────────────
_CSS = """<style>
.rpt-zone-card{background:#111d35;border:1px solid rgba(255,255,255,.07);
               border-radius:12px;padding:1.1rem 1.3rem;margin-bottom:1rem;}
.rpt-zone-title{font-size:1rem;font-weight:700;color:#e2e8f0;margin-bottom:.1rem;}
.rpt-zone-sub{font-size:.75rem;color:#475569;margin-bottom:.75rem;}
.rpt-stat{display:inline-block;margin-right:1.2rem;}
.rpt-stat-val{font-size:1.4rem;font-weight:800;line-height:1;}
.rpt-stat-lbl{font-size:.65rem;font-weight:600;letter-spacing:.08em;
              text-transform:uppercase;color:#475569;}
.rpt-team-pill{display:inline-block;background:rgba(59,130,246,.1);color:#93c5fd;
               border:1px solid rgba(59,130,246,.25);border-radius:5px;
               font-size:.72rem;font-weight:600;padding:2px 8px;margin:2px 3px 2px 0;}
.rpt-badge-crit{color:#fca5a5;font-weight:700;}
.rpt-badge-warn{color:#fcd34d;font-weight:700;}
.rpt-badge-ok  {color:#86efac;font-weight:700;}
</style>"""


# ── Helpers ───────────────────────────────────────────────────────────────────
def _severity_color(s: str) -> str:
    return {"critical": "#ef4444", "warning": "#f59e0b"}.get(str(s).lower(), "#94a3b8")


def _status_color(s: str) -> str:
    return "#22c55e" if str(s).lower() == "resolved" else "#f59e0b"


def _export_csv(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode()


def _export_pdf(
    title: str,
    period: str,
    summary_df: pd.DataFrame,
    detail_df: pd.DataFrame,
) -> bytes:
    """Generate a proper PDF report using fpdf2."""
    from fpdf import FPDF

    def _latin1(text: str) -> str:
        return text.encode("latin-1", errors="replace").decode("latin-1")

    class _PDF(FPDF):
        def header(self):
            self.set_fill_color(26, 58, 92)
            self.rect(0, 0, self.w, 18, "F")
            self.set_font("Helvetica", "B", 13)
            self.set_text_color(255, 255, 255)
            self.set_xy(10, 4)
            self.cell(0, 7, _latin1(f"THIWASCO - {title}"), ln=False)
            self.set_font("Helvetica", "", 7)
            self.set_xy(self.w - 90, 4)
            self.cell(80, 4, _latin1(f"Period: {period}"), align="R", ln=False)
            self.set_xy(self.w - 90, 9)
            self.cell(80, 4, f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}", align="R")
            self.set_text_color(0, 0, 0)
            self.ln(14)

        def footer(self):
            self.set_y(-12)
            self.set_font("Helvetica", "I", 7)
            self.set_text_color(150, 150, 150)
            self.cell(0, 8, f"Page {self.page_no()}", align="C")

    pdf = _PDF(orientation="L", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margins(10, 22, 10)
    pdf.add_page()

    def _draw_table(df: pd.DataFrame, section: str) -> None:
        if df.empty:
            return
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(26, 58, 92)
        pdf.cell(0, 7, _latin1(section), ln=True)
        pdf.set_text_color(0, 0, 0)

        avail = pdf.w - pdf.l_margin - pdf.r_margin
        col_w = avail / len(df.columns)

        pdf.set_font("Helvetica", "B", 7)
        pdf.set_fill_color(26, 58, 92)
        pdf.set_text_color(255, 255, 255)
        for col in df.columns:
            pdf.cell(col_w, 6, _latin1(str(col)[:22]), border=0, fill=True, align="C")
        pdf.ln()

        pdf.set_font("Helvetica", "", 7)
        pdf.set_text_color(30, 30, 30)
        for i, (_, row) in enumerate(df.iterrows()):
            fill = i % 2 == 1
            pdf.set_fill_color(242, 246, 252) if fill else pdf.set_fill_color(255, 255, 255)
            for col in df.columns:
                val = str(row[col]) if not pd.isna(row[col]) else ""
                val = val[:24] + "..." if len(val) > 25 else val
                pdf.cell(col_w, 5, _latin1(val), border=0, fill=True)
            pdf.ln()
        pdf.ln(4)

    if not summary_df.empty:
        _draw_table(summary_df, "Zone Summary")
    if not detail_df.empty:
        _draw_table(detail_df, "Detailed Alerts / Data")

    return bytes(pdf.output())


# ── Page entry point ──────────────────────────────────────────────────────────
def show_reports():
    page_header("Reports", "Generate leak detection and team response reports.", eyebrow="Reporting")

    if not is_nrw_officer():
        show_permission_denied("generate reports")
        st.info("Report generation is restricted to Non-Revenue Water Officers.")
        return

    st.markdown(_CSS, unsafe_allow_html=True)

    tab_gen, tab_data = st.tabs(["Generate Reports", "Data Management"])

    with tab_gen:
        _show_generate_tab()

    with tab_data:
        _show_data_management_tab()


def _show_live_summary():
    """Always-on summary table: zone leak breakdown for the last 7 days."""
    end_dt   = datetime.now()
    start_dt = end_dt - timedelta(days=7)
    try:
        summary_df = db_manager.get_zone_leak_summary(start_dt, end_dt)
    except Exception:
        summary_df = pd.DataFrame()

    st.markdown(
        "<p style='font-size:0.75rem;font-weight:700;letter-spacing:0.1em;"
        "text-transform:uppercase;color:#475569;margin:0 0 0.6rem;'>"
        "Live Snapshot — Last 7 Days</p>",
        unsafe_allow_html=True,
    )

    if summary_df.empty:
        st.info("No alert data in the last 7 days.")
        return

    total_alerts   = int(summary_df["total_leaks"].sum())
    total_resolved = int(summary_df["resolved"].sum())
    total_active   = int(summary_df["active"].sum())
    total_critical = int(summary_df["critical"].sum())

    m1, m2, m3, m4 = st.columns(4)
    with m1: st.metric("Total Alerts",   total_alerts)
    with m2: st.metric("Active",         total_active)
    with m3: st.metric("Resolved",       total_resolved)
    with m4: st.metric("Critical",       total_critical)

    st.markdown("<div style='margin:0.5rem 0;'></div>", unsafe_allow_html=True)

    disp = summary_df[["zone_name", "total_leaks", "critical", "warning",
                        "resolved", "active", "assigned_teams"]].copy()
    disp = disp.rename(columns={
        "zone_name":     "Zone",
        "total_leaks":   "Total",
        "critical":      "Critical",
        "warning":       "Warning",
        "resolved":      "Resolved",
        "active":        "Active",
        "assigned_teams":"Assigned Teams",
    })
    show_glowing_table(disp)


def _show_generate_tab():
    """Report generation form with a live summary always visible at the top."""

    # ── Live summary (always shown, no button needed) ──────────────────────────
    _show_live_summary()
    st.markdown("---")

    report_type = st.selectbox(
        "Report type",
        [
            "Zone Leak Summary",
            "Comprehensive Report",
            "Leak Detection Report",
            "Team Performance Report",
            "Alert Summary Report",
        ],
    )

    st.markdown("### Filters")
    col1, col2 = st.columns(2)

    with col1:
        date_range = st.selectbox(
            "Date range",
            [("Last 24 Hours", 1), ("Last 7 Days", 7),
             ("Last 30 Days", 30), ("Last 90 Days", 90), ("Custom", 0)],
            format_func=lambda x: x[0],
        )
        if date_range[1] == 0:
            start_date = st.date_input("Start date", datetime.now() - timedelta(days=30))
            end_date   = st.date_input("End date",   datetime.now())
            start_dt   = datetime.combine(start_date, datetime.min.time())
            end_dt     = datetime.combine(end_date,   datetime.max.time())
        else:
            end_dt   = datetime.now()
            start_dt = end_dt - timedelta(days=date_range[1])

    with col2:
        if report_type in ("Comprehensive Report", "Leak Detection Report", "Zone Leak Summary"):
            teams_df = db_manager.get_all_teams()
            team_opts = {"All Teams": None}
            if not teams_df.empty:
                for _, t in teams_df[teams_df["status"] == "active"].iterrows():
                    team_opts[t["name"]] = int(t["id"])
            sel_team_name = st.selectbox("Filter by team", list(team_opts.keys()))
            sel_team_id   = team_opts[sel_team_name]
        else:
            sel_team_id = None

        if report_type == "Comprehensive Report":
            sev_filter = st.selectbox("Severity", ["All", "critical", "warning", "normal"],
                                      format_func=str.title)
            severity = None if sev_filter == "All" else sev_filter
        else:
            severity = None

    st.markdown("---")
    col_btn, col_clear = st.columns([2, 1])
    with col_btn:
        if st.button("Generate Report", type="primary", use_container_width=True):
            period_str = f"{start_dt.strftime('%Y-%m-%d')} to {end_dt.strftime('%Y-%m-%d')}"
            st.session_state["_rpt_params"] = (report_type, start_dt, end_dt, sel_team_id, severity, period_str)
    with col_clear:
        if st.button("Clear", use_container_width=True):
            st.session_state.pop("_rpt_params", None)
            st.rerun()

    if "_rpt_params" in st.session_state:
        with st.spinner("Generating..."):
            _dispatch(*st.session_state["_rpt_params"])


def _show_data_management_tab():
    """Clear dynamic simulation/operational data."""
    st.markdown(
        "<p style='color:#94a3b8;font-size:0.88rem;margin-bottom:1rem;'>"
        "Clear sensor readings, predictions, and alerts to reset the system or free up space. "
        "All actions are permanent and cannot be undone."
        "</p>",
        unsafe_allow_html=True,
    )

    counts = db_manager.get_dynamic_data_counts()

    def _oldest(ts) -> str:
        if ts is None or (isinstance(ts, float) and pd.isna(ts)):
            return "—"
        try:
            return pd.to_datetime(ts).strftime("%Y-%m-%d %H:%M")
        except Exception:
            return "—"

    # ── Current counts ─────────────────────────────────────────────────────────
    st.markdown("#### Current Data Volumes")
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Sensor Readings", f"{counts['sensor_readings']:,}")
        st.caption(f"Oldest: {_oldest(counts['oldest_reading'])}")
    with m2:
        st.metric("Leak Predictions", f"{counts['predictions']:,}")
        st.caption(f"Oldest: {_oldest(counts['oldest_prediction'])}")
    with m3:
        total_alerts = counts['alerts_new'] + counts['alerts_assigned'] + counts['alerts_resolved']
        st.metric("Alerts (total)", total_alerts)
        st.caption(f"{counts['alerts_new']} new · {counts['alerts_assigned']} assigned · {counts['alerts_resolved']} resolved")
    with m4:
        st.metric("Resolved Alerts", counts['alerts_resolved'])
        st.caption("Safe to clear")

    st.markdown("---")

    # ── Individual clear actions ───────────────────────────────────────────────
    st.markdown("#### Clear by Category")

    col_r, col_p, col_a = st.columns(3)

    # Sensor readings
    with col_r:
        st.markdown(
            "<div style='background:#111d35;border:1px solid rgba(255,255,255,0.07);"
            "border-radius:10px;padding:1rem 1.1rem;margin-bottom:0.5rem;'>"
            "<div style='font-size:0.75rem;font-weight:700;text-transform:uppercase;"
            "letter-spacing:0.08em;color:#475569;margin-bottom:0.4rem;'>Sensor Readings</div>"
            f"<div style='font-size:1.6rem;font-weight:800;color:#3b82f6;'>{counts['sensor_readings']:,}</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        age_r = st.selectbox(
            "Delete readings older than",
            [("24 hours", 24), ("48 hours", 48), ("7 days", 168), ("30 days", 720), ("All", None)],
            format_func=lambda x: x[0],
            key="age_readings",
        )
        if st.button("Clear Sensor Readings", key="btn_clear_r", use_container_width=True):
            st.session_state["confirm_clear_readings"] = True

        if st.session_state.get("confirm_clear_readings"):
            label = age_r[0] if age_r[1] else "ALL"
            st.warning(f"Delete sensor readings ({label})? This cannot be undone.")
            cy, cn = st.columns(2)
            with cy:
                if st.button("Yes, clear", key="ok_r"):
                    ok, msg, _ = db_manager.clear_sensor_readings(older_than_hours=age_r[1])
                    st.success(msg) if ok else st.error(msg)
                    st.session_state.pop("confirm_clear_readings", None)
                    st.rerun()
            with cn:
                if st.button("Cancel", key="no_r"):
                    st.session_state.pop("confirm_clear_readings", None)
                    st.rerun()

    # Leak predictions
    with col_p:
        st.markdown(
            "<div style='background:#111d35;border:1px solid rgba(255,255,255,0.07);"
            "border-radius:10px;padding:1rem 1.1rem;margin-bottom:0.5rem;'>"
            "<div style='font-size:0.75rem;font-weight:700;text-transform:uppercase;"
            "letter-spacing:0.08em;color:#475569;margin-bottom:0.4rem;'>Leak Predictions</div>"
            f"<div style='font-size:1.6rem;font-weight:800;color:#a855f7;'>{counts['predictions']:,}</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        age_p = st.selectbox(
            "Delete predictions older than",
            [("24 hours", 24), ("48 hours", 48), ("7 days", 168), ("30 days", 720), ("All", None)],
            format_func=lambda x: x[0],
            key="age_preds",
        )
        if st.button("Clear Predictions", key="btn_clear_p", use_container_width=True):
            st.session_state["confirm_clear_preds"] = True

        if st.session_state.get("confirm_clear_preds"):
            label = age_p[0] if age_p[1] else "ALL"
            st.warning(f"Delete predictions ({label})? This cannot be undone.")
            cy, cn = st.columns(2)
            with cy:
                if st.button("Yes, clear", key="ok_p"):
                    ok, msg, _ = db_manager.clear_leak_predictions(older_than_hours=age_p[1])
                    st.success(msg) if ok else st.error(msg)
                    st.session_state.pop("confirm_clear_preds", None)
                    st.rerun()
            with cn:
                if st.button("Cancel", key="no_p"):
                    st.session_state.pop("confirm_clear_preds", None)
                    st.rerun()

    # Alerts
    with col_a:
        st.markdown(
            "<div style='background:#111d35;border:1px solid rgba(255,255,255,0.07);"
            "border-radius:10px;padding:1rem 1.1rem;margin-bottom:0.5rem;'>"
            "<div style='font-size:0.75rem;font-weight:700;text-transform:uppercase;"
            "letter-spacing:0.08em;color:#475569;margin-bottom:0.4rem;'>Alerts</div>"
            f"<div style='font-size:1.6rem;font-weight:800;color:#f59e0b;'>{total_alerts}</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        alert_scope = st.selectbox(
            "Which alerts to delete",
            [("Resolved only", "resolved"), ("All alerts", "all")],
            format_func=lambda x: x[0],
            key="scope_alerts",
        )
        if st.button("Clear Alerts", key="btn_clear_a", use_container_width=True):
            st.session_state["confirm_clear_alerts"] = True

        if st.session_state.get("confirm_clear_alerts"):
            st.warning(f"Delete {alert_scope[0]}? This cannot be undone.")
            cy, cn = st.columns(2)
            with cy:
                if st.button("Yes, clear", key="ok_a"):
                    ok, msg, _ = db_manager.clear_alerts(scope=alert_scope[1])
                    st.success(msg) if ok else st.error(msg)
                    st.session_state.pop("confirm_clear_alerts", None)
                    st.rerun()
            with cn:
                if st.button("Cancel", key="no_a"):
                    st.session_state.pop("confirm_clear_alerts", None)
                    st.rerun()

    # ── Danger zone ────────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown(
        "<div style='border:1px solid rgba(239,68,68,0.35);border-radius:10px;"
        "padding:1rem 1.2rem;background:rgba(239,68,68,0.06);'>"
        "<div style='color:#ef4444;font-size:0.75rem;font-weight:700;text-transform:uppercase;"
        "letter-spacing:0.1em;margin-bottom:0.4rem;'>Danger Zone</div>"
        "<div style='color:#cbd5e1;font-size:0.85rem;'>"
        "Clear ALL sensor readings, predictions, and alerts at once. "
        "Use this to fully reset the system to a clean state."
        "</div>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.markdown("<div style='margin-top:0.7rem;'></div>", unsafe_allow_html=True)

    if st.button("Clear ALL Dynamic Data", key="btn_clear_all", type="primary"):
        st.session_state["confirm_clear_all"] = True

    if st.session_state.get("confirm_clear_all"):
        st.error(
            "This will permanently delete ALL sensor readings, ALL predictions, and ALL alerts. "
            "The system will start collecting data fresh from this point. Are you sure?"
        )
        cy, cn = st.columns(2)
        with cy:
            if st.button("Yes, wipe everything", key="ok_all"):
                ok, msg = db_manager.clear_all_dynamic_data()
                if ok:
                    st.success(msg)
                    st.cache_data.clear()
                else:
                    st.error(msg)
                st.session_state.pop("confirm_clear_all", None)
                st.rerun()
        with cn:
            if st.button("Cancel", key="no_all"):
                st.session_state.pop("confirm_clear_all", None)
                st.rerun()


# ── Dispatcher ────────────────────────────────────────────────────────────────
def _dispatch(report_type, start_dt, end_dt, team_id, severity, period_str):
    try:
        if report_type == "Zone Leak Summary":
            _show_zone_summary(start_dt, end_dt, team_id, period_str)
        elif report_type == "Comprehensive Report":
            df = report_generator.generate_comprehensive_report(start_dt, end_dt, team_id, severity)
            _show_comprehensive(df, period_str)
        elif report_type == "Leak Detection Report":
            df = report_generator.generate_leak_report(start_dt, end_dt, team_id)
            _show_leak(df, period_str)
        elif report_type == "Team Performance Report":
            df = report_generator.generate_team_performance_report(start_dt, end_dt)
            _show_team_perf(df, period_str)
        elif report_type == "Alert Summary Report":
            summary = report_generator.generate_alert_summary_report(start_dt, end_dt)
            _show_alert_summary(summary, period_str)
    except Exception as e:
        st.error(f"Error generating report: {e}")
        import traceback
        st.code(traceback.format_exc())


# ── Zone Leak Summary ─────────────────────────────────────────────────────────
def _show_zone_summary(start_dt: datetime, end_dt: datetime, team_id, period_str: str):
    summary_df = db_manager.get_zone_leak_summary(start_dt, end_dt)
    detail_df  = db_manager.get_zone_leak_detail(start_dt, end_dt)

    # Optional team filter
    if team_id is not None and not detail_df.empty and "team_name" in detail_df.columns:
        teams_df = db_manager.get_all_teams()
        team_name = teams_df[teams_df["id"] == team_id]["name"].iloc[0] if not teams_df.empty else None
        if team_name:
            detail_df  = detail_df[detail_df["team_name"] == team_name]
            zone_ids   = detail_df["zone_name"].unique()
            summary_df = summary_df[summary_df["zone_name"].isin(zone_ids)]

    st.success("Report generated")
    st.markdown(
        f"<h3 style='color:#e2e8f0;margin-bottom:.2rem;'>Zone Leak Summary</h3>"
        f"<p style='color:#475569;font-size:.83rem;'>Period: {period_str}</p>",
        unsafe_allow_html=True,
    )

    if summary_df.empty:
        st.info("No leaks detected in this period.")
        return

    # ── Session KPIs ──
    total_leaks  = int(summary_df["total_leaks"].sum())
    total_res    = int(summary_df["resolved"].sum())
    total_active = int(summary_df["active"].sum())
    zones_hit    = len(summary_df)

    k1, k2, k3, k4 = st.columns(4)
    for col, label, val, color in [
        (k1, "Zones Affected", zones_hit,    "#3b82f6"),
        (k2, "Total Leaks",    total_leaks,  "#f59e0b"),
        (k3, "Resolved",       total_res,    "#22c55e"),
        (k4, "Still Active",   total_active, "#ef4444"),
    ]:
        with col:
            st.markdown(
                f"<div style='background:#111d35;border:1px solid rgba(255,255,255,.07);"
                f"border-radius:10px;padding:.9rem 1rem;'>"
                f"<div style='font-size:.65rem;font-weight:700;text-transform:uppercase;"
                f"letter-spacing:.09em;color:#475569;margin-bottom:.4rem;'>{label}</div>"
                f"<div style='font-size:2rem;font-weight:800;color:{color};'>{val}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

    st.markdown("<div style='margin:.9rem 0;'></div>", unsafe_allow_html=True)

    # ── Per-zone cards — fixed-height scroll so export section stays reachable ──
    with st.expander(f"Zone breakdown — {zones_hit} zone(s)", expanded=True):
      with st.container(height=420, border=False):
        for _, zone in summary_df.iterrows():
            res_pct = int((zone["resolved"] / zone["total_leaks"]) * 100) if zone["total_leaks"] else 0
            teams_html = "".join(
                f"<span class='rpt-team-pill'>{t.strip()}</span>"
                for t in (zone["assigned_teams"] or "Unassigned").split("|")
            )

            # Fetch members for each assigned team in this zone
            zone_detail = detail_df[detail_df["zone_name"] == zone["zone_name"]]
            member_info = ""
            if not zone_detail.empty and "team_name" in zone_detail.columns:
                for team_name, grp in zone_detail.groupby("team_name"):
                    if pd.notna(team_name):
                        members = grp["team_members"].dropna().unique()
                        members_str = members[0] if len(members) else "—"
                        member_info += (
                            f"<div style='font-size:.75rem;color:#64748b;margin:.15rem 0 0 .4rem;'>"
                            f"<span style='color:#3b82f6;font-weight:600;'>{team_name}</span>"
                            f" &nbsp;·&nbsp; {members_str}</div>"
                        )

            st.markdown(
                f"<div class='rpt-zone-card'>"
                f"<div class='rpt-zone-title'>{zone['zone_name']}"
                f"<span style='font-size:.72rem;font-weight:400;color:#475569;margin-left:.5rem;'>{zone.get('region','')}</span>"
                f"</div>"
                f"<div style='display:flex;gap:1.5rem;margin:.6rem 0 .7rem;'>"
                f"<div class='rpt-stat'><div class='rpt-stat-val' style='color:#e2e8f0;'>{int(zone['total_leaks'])}</div>"
                f"<div class='rpt-stat-lbl'>Leaks</div></div>"
                f"<div class='rpt-stat'><div class='rpt-stat-val rpt-badge-crit'>{int(zone['critical'])}</div>"
                f"<div class='rpt-stat-lbl'>Critical</div></div>"
                f"<div class='rpt-stat'><div class='rpt-stat-val rpt-badge-warn'>{int(zone['warning'])}</div>"
                f"<div class='rpt-stat-lbl'>Warning</div></div>"
                f"<div class='rpt-stat'><div class='rpt-stat-val rpt-badge-ok'>{int(zone['resolved'])}</div>"
                f"<div class='rpt-stat-lbl'>Resolved</div></div>"
                f"<div class='rpt-stat'><div class='rpt-stat-val' style='color:#f59e0b;'>{res_pct}%</div>"
                f"<div class='rpt-stat-lbl'>Resolution rate</div></div>"
                f"</div>"
                f"<div style='font-size:.72rem;color:#64748b;margin-bottom:.35rem;'>Assigned teams</div>"
                f"{teams_html}{member_info}"
                f"</div>",
                unsafe_allow_html=True,
            )

            # Individual alerts for this zone
            if not zone_detail.empty:
                with st.expander(f"View {int(zone['total_leaks'])} alert(s) — {zone['zone_name']}"):
                    disp = zone_detail[[
                        "alert_id", "meter_id", "severity", "status",
                        "team_name", "team_members", "created_at", "resolved_at", "response_hrs",
                    ]].copy()
                    disp.columns = [
                        "Alert ID", "Meter", "Severity", "Status",
                        "Team", "Members", "Created", "Resolved", "Response (hrs)",
                    ]
                    for c in ("Created", "Resolved"):
                        disp[c] = disp[c].apply(
                            lambda x: x.strftime("%Y-%m-%d %H:%M") if pd.notna(x) else "—"
                        )
                    show_glowing_table(disp)

    # ── Exports ──
    st.markdown("---")
    st.markdown("#### Export Report")

    # Build flat CSV combining summary + detail
    csv_cols = ["zone_name", "total_leaks", "critical", "warning", "resolved", "active",
                "assigned_teams", "alert_id", "meter_id", "severity", "status",
                "team_name", "team_members", "created_at", "resolved_at", "response_hrs"]
    export_df = pd.merge(
        summary_df[["zone_name", "total_leaks", "critical", "warning", "resolved",
                    "active", "assigned_teams"]],
        detail_df,
        on="zone_name", how="right"
    )
    export_df = export_df[[c for c in csv_cols if c in export_df.columns]]

    period_tag = datetime.now().strftime("%Y%m%d_%H%M")
    col_csv, col_pdf = st.columns(2)

    with col_csv:
        st.download_button(
            "Download CSV",
            data=_export_csv(export_df),
            file_name=f"zone_leak_summary_{period_tag}.csv",
            mime="text/csv",
            use_container_width=True,
        )
    with col_pdf:
        pdf_bytes = _export_pdf(
            "Zone Leak Summary", period_str,
            summary_df[["zone_name", "region", "total_leaks", "critical",
                        "warning", "resolved", "active", "assigned_teams"]].rename(columns={
                "zone_name": "Zone", "region": "Region", "total_leaks": "Total",
                "critical": "Critical", "warning": "Warning", "resolved": "Resolved",
                "active": "Active", "assigned_teams": "Teams Assigned",
            }),
            detail_df[["zone_name", "alert_id", "meter_id", "severity", "status",
                       "team_name", "team_members", "created_at", "resolved_at",
                       "response_hrs"]].rename(columns={
                "zone_name": "Zone", "alert_id": "Alert ID", "meter_id": "Meter",
                "severity": "Severity", "status": "Status", "team_name": "Team",
                "team_members": "Members", "created_at": "Created",
                "resolved_at": "Resolved", "response_hrs": "Response (hrs)",
            }),
        )
        st.download_button(
            "Download PDF",
            data=pdf_bytes,
            file_name=f"zone_leak_summary_{period_tag}.pdf",
            mime="application/pdf",
            use_container_width=True,
        )


# ── Comprehensive report ──────────────────────────────────────────────────────
def _show_comprehensive(df: pd.DataFrame, period_str: str):
    st.success("Report generated")
    st.markdown(f"### Comprehensive Report  \n**Period:** {period_str}")
    if df.empty:
        st.info("No data for this period.")
        return

    k1, k2, k3, k4 = st.columns(4)
    with k1: st.metric("Total Alerts", len(df))
    with k2: st.metric("Resolved", len(df[df["status"] == "resolved"]))
    with k3: st.metric("Critical",  len(df[df["severity"] == "critical"]))
    with k4:
        avg = df["response_time_hours"].mean()
        st.metric("Avg Response (hrs)", f"{avg:.1f}" if pd.notna(avg) else "N/A")

    st.markdown("---")
    disp_cols = [c for c in ["alert_id", "meter_id", "zone_name", "severity", "status",
                              "team_name", "team_members", "leak_type", "confidence",
                              "created_at", "resolved_at", "resolved_by_name",
                              "response_time_hours"] if c in df.columns]
    disp = df[disp_cols].copy()
    for c in ("created_at", "resolved_at"):
        if c in disp.columns:
            disp[c] = disp[c].apply(lambda x: x.strftime("%Y-%m-%d %H:%M") if pd.notna(x) else "")
    if "confidence" in disp.columns:
        disp["confidence"] = disp["confidence"].apply(lambda x: f"{x*100:.1f}%" if pd.notna(x) else "")
    show_glowing_table(disp)

    st.markdown("---")
    period_tag = datetime.now().strftime("%Y%m%d_%H%M")
    col_csv, col_pdf = st.columns(2)
    with col_csv:
        st.download_button("Download CSV", _export_csv(df),
                           f"comprehensive_{period_tag}.csv", "text/csv",
                           use_container_width=True)
    with col_pdf:
        pdf = _export_pdf("Comprehensive Report", period_str, pd.DataFrame(), disp)
        st.download_button("Download PDF", pdf,
                           f"comprehensive_{period_tag}.pdf", "application/pdf",
                           use_container_width=True)


# ── Leak detection report ─────────────────────────────────────────────────────
def _show_leak(df: pd.DataFrame, period_str: str):
    st.success("Report generated")
    st.markdown(f"### Leak Detection Report  \n**Period:** {period_str}")
    if df.empty:
        st.info("No leaks detected.")
        return
    k1, k2, k3 = st.columns(3)
    with k1: st.metric("Total Leaks", len(df))
    with k2: st.metric("With Alerts", int(df["alert_id"].notna().sum()) if "alert_id" in df.columns else "—")
    with k3: st.metric("Assigned to Teams", int(df["assigned_team"].notna().sum()) if "assigned_team" in df.columns else "—")
    st.markdown("---")
    show_glowing_table(df)
    period_tag = datetime.now().strftime("%Y%m%d_%H%M")
    col_csv, col_pdf = st.columns(2)
    with col_csv:
        st.download_button("Download CSV", _export_csv(df),
                           f"leak_report_{period_tag}.csv", "text/csv",
                           use_container_width=True)
    with col_pdf:
        pdf = _export_pdf("Leak Detection Report", period_str, pd.DataFrame(), df)
        st.download_button("Download PDF", pdf,
                           f"leak_report_{period_tag}.pdf", "application/pdf",
                           use_container_width=True)


# ── Team performance report ───────────────────────────────────────────────────
def _show_team_perf(df: pd.DataFrame, period_str: str):
    st.success("Report generated")
    st.markdown(f"### Team Performance Report  \n**Period:** {period_str}")
    if df.empty:
        st.info("No team data.")
        return
    k1, k2, k3 = st.columns(3)
    with k1: st.metric("Teams", len(df))
    with k2: st.metric("Total Resolved", int(df["resolved_alerts"].sum()) if "resolved_alerts" in df.columns else "—")
    with k3:
        avg = df["avg_resolution_time_hours"].mean() if "avg_resolution_time_hours" in df.columns else None
        st.metric("Avg Resolution (hrs)", f"{avg:.1f}" if pd.notna(avg) else "N/A")
    st.markdown("---")
    disp = df.rename(columns={
        "team_name": "Team", "member_count": "Members", "total_alerts": "Total",
        "new_alerts": "New", "assigned_alerts": "Assigned", "resolved_alerts": "Resolved",
        "critical_alerts": "Critical", "warning_alerts": "Warning",
        "avg_resolution_time_hours": "Avg Resolution (hrs)", "team_members": "Members List",
    })
    show_cols = [c for c in ["Team", "Members", "Members List", "Total", "New", "Assigned",
                              "Resolved", "Critical", "Warning", "Avg Resolution (hrs)"]
                 if c in disp.columns]
    show_glowing_table(disp[show_cols])
    period_tag = datetime.now().strftime("%Y%m%d_%H%M")
    col_csv, col_pdf = st.columns(2)
    with col_csv:
        st.download_button("Download CSV", _export_csv(df),
                           f"team_performance_{period_tag}.csv", "text/csv",
                           use_container_width=True)
    with col_pdf:
        pdf = _export_pdf("Team Performance Report", period_str, pd.DataFrame(), disp[show_cols])
        st.download_button("Download PDF", pdf,
                           f"team_performance_{period_tag}.pdf", "application/pdf",
                           use_container_width=True)


# ── Alert summary report ──────────────────────────────────────────────────────
def _show_alert_summary(summary: dict, period_str: str):
    st.success("Report generated")
    st.markdown(f"### Alert Summary  \n**Period:** {period_str}")
    if not summary:
        st.info("No alert data.")
        return
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.metric("Total Alerts", int(summary.get("total_alerts", 0)))
        st.metric("New",          int(summary.get("new_alerts", 0)))
    with k2:
        st.metric("Assigned", int(summary.get("assigned_alerts", 0)))
        st.metric("Resolved", int(summary.get("resolved_alerts", 0)))
    with k3:
        st.metric("Critical", int(summary.get("critical_alerts", 0)))
        st.metric("Warning",  int(summary.get("warning_alerts", 0)))
    with k4:
        st.metric("Normal", int(summary.get("normal_alerts", 0)))
        avg = summary.get("avg_resolution_time_hours")
        st.metric("Avg Resolution (hrs)", f"{avg:.1f}" if avg else "N/A")

    st.markdown("---")
    k5, k6 = st.columns(2)
    with k5: st.metric("Assigned to Teams", int(summary.get("assigned_to_team", 0)))
    with k6: st.metric("Unassigned",         int(summary.get("unassigned", 0)))

    period_tag = datetime.now().strftime("%Y%m%d_%H%M")
    summary_df = pd.DataFrame([summary])
    col_csv, col_pdf = st.columns(2)
    with col_csv:
        st.download_button("Download CSV", _export_csv(summary_df),
                           f"alert_summary_{period_tag}.csv", "text/csv",
                           use_container_width=True)
    with col_pdf:
        pdf = _export_pdf("Alert Summary Report", period_str, summary_df, pd.DataFrame())
        st.download_button("Download PDF", pdf,
                           f"alert_summary_{period_tag}.pdf", "application/pdf",
                           use_container_width=True)
