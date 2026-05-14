"""System Status page - runtime health and readiness."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from backend.mysql_database_manager import db_manager
from backend.ml_integration import MODEL_DIR, ml_model
from backend.rbac import is_system_admin
from page_components.data_utils import (
    clear_alert_cache,
    format_datetime,
    get_cached_data,
    get_service_states,
    latest_timestamp,
    load_static_data,
)

_CSS = """<style>
/* ── Status badges ── */
.ss-badge{display:inline-flex;align-items:center;padding:3px 12px;border-radius:20px;
          font-size:.75rem;font-weight:700;letter-spacing:.05em;}
.ss-badge-green{background:rgba(34,197,94,.12);color:#86efac;
                box-shadow:0 0 10px 2px rgba(34,197,94,.40);}
.ss-badge-red  {background:rgba(239,68,68,.12);color:#fca5a5;
                box-shadow:0 0 10px 2px rgba(239,68,68,.40);}
.ss-badge-amber{background:rgba(245,158,11,.12);color:#fcd34d;
                box-shadow:0 0 10px 2px rgba(245,158,11,.35);}

/* ── Service-checks table ── */
.ss-tbl{width:100%;border-collapse:collapse;font-size:.86rem;}
.ss-tbl td{padding:10px 12px;border-bottom:1px solid rgba(255,255,255,.05);vertical-align:middle;}
.ss-tbl tr:last-child td{border-bottom:none;}
.ss-th{color:#475569;font-size:.7rem;font-weight:700;letter-spacing:.09em;
       text-transform:uppercase;padding:6px 12px 10px;}

/* ── Generic card shell ── */
.ss-card{background:#111d35;border:1px solid rgba(255,255,255,.07);
         border-radius:12px;padding:1rem 1.15rem;margin-bottom:.75rem;}
</style>"""


def _kpi_card(label: str, value: str, sub: str,
              bar_pct: float, bar_color: str, glow: str, border: str) -> str:
    return (
        f"<div style='background:#111d35;border:1px solid {border};border-radius:14px;"
        f"padding:1.1rem 1.2rem;box-shadow:0 0 22px 2px {glow};min-height:115px;'>"
        f"<div style='font-size:.7rem;font-weight:700;text-transform:uppercase;"
        f"letter-spacing:.09em;color:#475569;margin-bottom:.5rem;'>{label}</div>"
        f"<div style='font-size:2.1rem;font-weight:800;color:#e2e8f0;line-height:1;'>"
        f"{value}&nbsp;<span style='font-size:.85rem;font-weight:500;color:#64748b;'>{sub}</span>"
        f"</div>"
        f"<div style='background:rgba(255,255,255,.06);border-radius:4px;height:4px;"
        f"overflow:hidden;margin-top:.75rem;'>"
        f"<div style='width:{bar_pct:.1f}%;height:100%;background:{bar_color};"
        f"border-radius:4px;box-shadow:0 0 6px {bar_color};'></div>"
        f"</div></div>"
    )


def show_system_status() -> None:
    """Render the platform health page."""
    if not is_system_admin():
        st.error("Access denied. This page is only available to System Administrators.")
        st.stop()

    st.markdown(_CSS, unsafe_allow_html=True)

    # ── Load data ──────────────────────────────────────────────────────────────
    load_static_data()
    data = get_cached_data(hours=24)
    stats = db_manager.get_dashboard_stats()
    service_states = get_service_states()

    healthy_count = sum(1 for s in service_states if s.healthy)
    all_healthy = healthy_count == len(service_states)

    try:
        db_connected = db_manager._get_conn() is not None
    except Exception:
        db_connected = False

    active_meters = int(stats.get("active_meters", 0))
    active_zones  = int(stats.get("active_zones", 0))
    leaks_24h     = int(stats.get("leaks_detected_24h", 0))

    # ── Page header ────────────────────────────────────────────────────────────
    health_color = "#22c55e" if all_healthy else "#f59e0b"
    health_msg = (
        "All core systems operational."
        if all_healthy
        else f"{len(service_states) - healthy_count} service(s) need attention."
    )
    now_str = datetime.now().strftime("%I:%M %p")

    hdr_col, btn_col = st.columns([6, 1])
    with hdr_col:
        st.markdown(
            f"<h2 style='font-size:1.9rem;font-weight:800;color:#e2e8f0;margin:0 0 .35rem;'>"
            f"System Status</h2>"
            f"<span style='color:{health_color};font-size:.87rem;font-weight:600;'>"
            f"{health_msg} Service health confirmed at {now_str}.</span>",
            unsafe_allow_html=True,
        )
    with btn_col:
        st.markdown("<div style='margin-top:1.4rem;'></div>", unsafe_allow_html=True)
        st.button("Export Data", use_container_width=True)

    st.markdown("<div style='margin:.9rem 0;'></div>", unsafe_allow_html=True)

    # ── KPI row ────────────────────────────────────────────────────────────────
    kpi_cols = st.columns(4)
    kpis = [
        dict(
            label="Healthy Services",
            value=f"{healthy_count}/{len(service_states)}",
            sub="Operational",
            bar_pct=(healthy_count / max(len(service_states), 1)) * 100,
            bar_color="#22c55e" if all_healthy else "#f59e0b",
            glow="rgba(34,197,94,.28)" if all_healthy else "rgba(245,158,11,.28)",
            border="rgba(34,197,94,.20)" if all_healthy else "rgba(245,158,11,.20)",
        ),
        dict(
            label="Active Meters",
            value=str(active_meters),
            sub="Syncing",
            bar_pct=min(100, (active_meters / max(active_meters, 1)) * 100),
            bar_color="#3b82f6",
            glow="rgba(59,130,246,.25)",
            border="rgba(59,130,246,.18)",
        ),
        dict(
            label="Active Zones",
            value=str(active_zones),
            sub="Monitored",
            bar_pct=min(100, (active_zones / max(active_zones, 1)) * 100),
            bar_color="#3b82f6",
            glow="rgba(59,130,246,.25)",
            border="rgba(59,130,246,.18)",
        ),
        dict(
            label="Leaks (24H)",
            value=str(leaks_24h),
            sub="Detected",
            bar_pct=min(100, leaks_24h * 10) if leaks_24h else 4,
            bar_color="#ef4444" if leaks_24h else "#22c55e",
            glow="rgba(239,68,68,.30)" if leaks_24h else "rgba(34,197,94,.22)",
            border="rgba(239,68,68,.20)" if leaks_24h else "rgba(34,197,94,.18)",
        ),
    ]
    for col, kpi in zip(kpi_cols, kpis):
        with col:
            st.markdown(_kpi_card(**kpi), unsafe_allow_html=True)

    st.markdown("<div style='margin:.6rem 0;'></div>", unsafe_allow_html=True)

    # ── Two-column: Service checks | Right panel ───────────────────────────────
    left, right = st.columns([1.5, 1])

    with left:
        st.markdown(
            "<div style='display:flex;justify-content:space-between;align-items:center;"
            "margin-bottom:.7rem;'>"
            "<span style='font-size:.95rem;font-weight:700;color:#e2e8f0;'>Service Checks</span>"
            "<span style='background:rgba(34,197,94,.1);color:#86efac;"
            "border:1px solid rgba(34,197,94,.25);font-size:.67rem;font-weight:700;"
            "letter-spacing:.1em;padding:3px 10px;border-radius:20px;"
            "box-shadow:0 0 8px rgba(34,197,94,.3);'>LIVE MONITORING</span>"
            "</div>",
            unsafe_allow_html=True,
        )

        rows_html = "".join(
            f"<tr>"
            f"<td style='color:#e2e8f0;font-weight:600;'>{s.name}</td>"
            f"<td><span class='ss-badge {'ss-badge-green' if s.healthy else 'ss-badge-red'}'>"
            f"{'Healthy' if s.healthy else 'Stopped'}</span></td>"
            f"<td style='color:#94a3b8;font-size:.82rem;'>{s.detail}</td>"
            f"<td style='color:#475569;font-size:.78rem;'>—</td>"
            f"</tr>"
            for s in service_states
        )
        st.markdown(
            f"<div class='ss-card'>"
            f"<table class='ss-tbl'>"
            f"<tr><th class='ss-th'>Service</th><th class='ss-th'>Status</th>"
            f"<th class='ss-th'>Details</th><th class='ss-th'>Last Sync</th></tr>"
            f"{rows_html}</table></div>",
            unsafe_allow_html=True,
        )

        # Recent activity
        st.markdown(
            "<span style='font-size:.95rem;font-weight:700;color:#e2e8f0;'>Recent Activity</span>",
            unsafe_allow_html=True,
        )
        activity_rows = "".join(
            f"<tr><td style='color:#94a3b8;font-size:.82rem;'>{sig}</td>"
            f"<td style='color:#e2e8f0;font-size:.82rem;text-align:right;'>{val}</td></tr>"
            for sig, val in [
                ("Latest reading",    format_datetime(latest_timestamp(data["readings"],    "timestamp"))),
                ("Latest prediction", format_datetime(latest_timestamp(data["predictions"], "timestamp"))),
                ("Latest alert",      format_datetime(latest_timestamp(data["alerts"],      "created_at"))),
            ]
        )
        st.markdown(
            f"<div class='ss-card' style='margin-top:.5rem;'>"
            f"<table style='width:100%;border-collapse:collapse;'>{activity_rows}</table></div>",
            unsafe_allow_html=True,
        )

    with right:
        # ── Background Services ──
        from backend.smart_meter_simulator import smart_meter_simulator, setup_sample_meters
        from prediction_loop import prediction_loop

        sim_running  = smart_meter_simulator.is_running
        loop_running = prediction_loop.is_running

        st.markdown(
            "<span style='font-size:.95rem;font-weight:700;color:#e2e8f0;'>Background Services</span>",
            unsafe_allow_html=True,
        )

        svc_c1, svc_c2 = st.columns(2)
        for col, name, running, start_key, stop_key, start_fn, stop_fn in [
            (svc_c1, "Simulator",       sim_running,  "start_sim",  "stop_sim",
             lambda: (setup_sample_meters() if not smart_meter_simulator.meters else None,
                      smart_meter_simulator.start_simulation()),
             smart_meter_simulator.stop_simulation),
            (svc_c2, "Prediction Loop", loop_running, "start_loop", "stop_loop",
             prediction_loop.start,
             prediction_loop.stop),
        ]:
            with col:
                bc = "ss-badge-green" if running else "ss-badge-red"
                label = "Running" if running else "Inactive"
                st.markdown(
                    f"<div class='ss-card' style='margin-bottom:.4rem;'>"
                    f"<div style='font-size:.82rem;font-weight:700;color:#e2e8f0;margin-bottom:.4rem;'>{name}</div>"
                    f"<span class='ss-badge {bc}'>{label}</span></div>",
                    unsafe_allow_html=True,
                )
                if running:
                    if st.button(f"Stop", key=stop_key, use_container_width=True):
                        stop_fn()
                        st.rerun()
                else:
                    if st.button(f"Start", key=start_key, use_container_width=True):
                        start_fn()
                        st.rerun()

        # ── Maintenance Actions ──
        st.markdown(
            "<div style='font-size:.67rem;font-weight:700;letter-spacing:.1em;text-transform:uppercase;"
            "color:#475569;margin:.9rem 0 .5rem;'>Maintenance Actions</div>",
            unsafe_allow_html=True,
        )
        train_btn = st.button("Train ML Models",      use_container_width=True, key="train_btn")
        if st.button(        "Clear Historic Alerts", use_container_width=True, key="clr_alerts_btn"):
            st.session_state["_confirm_clear_alerts"] = True

        if st.session_state.get("_confirm_clear_alerts"):
            st.warning("Permanently deletes **all** alerts. Are you sure?")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Yes, Clear", type="primary", key="confirm_clear"):
                    db_manager.clear_all_alerts()
                    clear_alert_cache()
                    st.session_state.pop("_confirm_clear_alerts", None)
                    st.success("Cleared.")
                    st.rerun()
            with c2:
                if st.button("Cancel", key="cancel_clear"):
                    st.session_state.pop("_confirm_clear_alerts", None)
                    st.rerun()

        # ── DB Connection card ──
        cfg = db_manager.config
        db_glow   = "rgba(34,197,94,.25)"  if db_connected else "rgba(239,68,68,.25)"
        db_border = "rgba(34,197,94,.18)"  if db_connected else "rgba(239,68,68,.18)"
        conn_color = "#22c55e" if db_connected else "#ef4444"
        conn_label = "CONNECTED"           if db_connected else "DISCONNECTED"

        db_rows_html = "".join(
            f"<tr><td style='color:#475569;font-size:.79rem;padding:4px 0;'>{k}</td>"
            f"<td style='color:#94a3b8;font-size:.79rem;font-family:monospace;text-align:right;'>{v}</td></tr>"
            for k, v in [
                ("Host",     f"{cfg.get('host','localhost')}:{cfg.get('port',3306)}"),
                ("Database", cfg.get("database", "thiwasco_1")),
                ("User",     cfg.get("user", "root")),
            ]
        )
        st.markdown(
            f"<div style='background:#111d35;border:1px solid {db_border};border-radius:12px;"
            f"padding:1rem 1.1rem;box-shadow:0 0 16px 1px {db_glow};margin-top:.8rem;'>"
            f"<div style='font-size:.88rem;font-weight:700;color:#e2e8f0;margin-bottom:.3rem;'>DB Connection</div>"
            f"<div style='margin-bottom:.6rem;'>"
            f"<span style='color:{conn_color};font-size:.7rem;font-weight:700;letter-spacing:.1em;'>"
            f"{conn_label}</span></div>"
            f"<table style='width:100%;border-collapse:collapse;'>{db_rows_html}</table>"
            f"</div>",
            unsafe_allow_html=True,
        )

    # ── Model Artifacts ────────────────────────────────────────────────────────
    st.markdown("<div style='margin:.5rem 0;'></div>", unsafe_allow_html=True)
    last_pred = format_datetime(latest_timestamp(data["predictions"], "timestamp"))

    st.markdown(
        f"<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:.6rem;'>"
        f"<span style='font-size:.95rem;font-weight:700;color:#e2e8f0;'>Model Artifacts</span>"
        f"<span style='font-size:.78rem;color:#475569;'>Last inference: {last_pred}</span></div>",
        unsafe_allow_html=True,
    )

    def _status_html(val: str) -> str:
        if not val or val == "Missing":
            return "<span style='color:#fca5a5;font-weight:600;font-size:.82rem;'>Missing</span>"
        return "<span style='color:#86efac;font-weight:600;font-size:.82rem;'>Loaded</span>"

    artifact_data = [
        ("Binary model",     str(ml_model.binary_model_path)  if ml_model.binary_model_path  else "Missing"),
        ("Multi-class model",str(ml_model.multi_model_path)   if ml_model.multi_model_path   else "Missing"),
        ("Scaler",           str(ml_model.scaler_path)        if ml_model.scaler_path        else "Missing"),
        ("Feature list",     str(ml_model.features_path)      if ml_model.features_path      else "Missing"),
        ("Feature count",    str(len(ml_model.feature_list or []))),
        ("Model directory",  str(MODEL_DIR)),
    ]
    art_rows = "".join(
        f"<tr>"
        f"<td style='color:#e2e8f0;font-weight:600;font-size:.85rem;width:22%;'>{name}</td>"
        f"<td style='color:#64748b;font-size:.78rem;font-family:monospace;'>{val}</td>"
        f"<td style='text-align:right;width:12%;'>{_status_html(val)}</td>"
        f"</tr>"
        for name, val in artifact_data
    )
    st.markdown(
        f"<div class='ss-card'>"
        f"<table class='ss-tbl'>"
        f"<tr><th class='ss-th'>Artifact</th><th class='ss-th'>Path / Value</th>"
        f"<th class='ss-th' style='text-align:right;'>Status</th></tr>"
        f"{art_rows}</table></div>",
        unsafe_allow_html=True,
    )

    # ── Train ML models (handled after render) ─────────────────────────────────
    if train_btn:
        import os
        import subprocess
        import sys as _sys
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[2]
        raw_csv = repo_root / "data" / "raw" / "simulated_leaks.csv"
        if not raw_csv.exists():
            st.error("Raw scenario data not found. Run `python src/generate_scenarios.py` first.")
        else:
            with st.spinner("Running training pipeline — this may take several minutes…"):
                py = _sys.executable
                steps = [
                    str(repo_root / "src" / "data_builder.py"),
                    str(repo_root / "src" / "feature_extractor.py"),
                    str(repo_root / "src" / "train_model.py"),
                ]
                all_ok = True
                output_lines: list[str] = []
                for script in steps:
                    res = subprocess.run(
                        [py, script],
                        capture_output=True, text=True,
                        cwd=str(repo_root),
                        env={**os.environ, "ALLOW_WEAK_SIGNAL_TRAINING": "1"},
                    )
                    output_lines.append(f"=== {Path(script).name} ===")
                    output_lines.append(res.stdout or "")
                    if res.returncode != 0:
                        output_lines.append(res.stderr or "")
                        all_ok = False
                        break

            if all_ok:
                st.success("Training complete. Restart the app to load the new models.")
            else:
                st.error("Training pipeline failed — see details below.")
            st.code("\n".join(output_lines), language="text")
