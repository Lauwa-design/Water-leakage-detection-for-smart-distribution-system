"""System Status page - runtime health and readiness."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from backend.database_manager import db_manager
from backend.ml_integration import MODEL_DIR, ml_model
from page_components.data_utils import (
    format_datetime,
    get_cached_data,
    get_service_states,
    latest_timestamp,
    load_static_data,
)
from page_components.ui import metric_card, page_header, section_header


def show_system_status() -> None:
    """Render the platform health page."""
    page_header(
        "System Status",
        "Confirm that the database, models, simulator, and prediction services are healthy.",
    )

    # Load static data first (fast - zones, meters)
    static_data = load_static_data()
    
    # Load dynamic data with session state caching (ultra-fast on page switches)
    data = get_cached_data(hours=24)
    
    stats = db_manager.get_dashboard_stats()
    service_states = get_service_states()

    healthy_count = sum(1 for state in service_states if state.healthy)
    metric_columns = st.columns(4)
    with metric_columns[0]:
        metric_card("Healthy Services", f"{healthy_count}/{len(service_states)}", "Runtime service checks", "success" if healthy_count == len(service_states) else "warning")
    with metric_columns[1]:
        metric_card("Active Meters", str(int(stats.get("active_meters", 0))), "Meters available to simulator", "neutral")
    with metric_columns[2]:
        metric_card("Active Zones", str(int(stats.get("active_zones", 0))), "Zones available in the database", "neutral")
    with metric_columns[3]:
        metric_card("Leaks (24h)", str(int(stats.get("leaks_detected_24h", 0))), "Predictions flagged as leaks", "warning")

    left, right = st.columns([1.15, 1])
    with left:
        section_header("Service checks", "Quick health assessment for the main backend services.")
        status_frame = pd.DataFrame(
            [
                {
                    "Service": state.name,
                    "Status": "Healthy" if state.healthy else "Attention",
                    "Detail": state.detail,
                }
                for state in service_states
            ]
        )
        st.dataframe(status_frame, use_container_width=True, hide_index=True)

    with right:
        section_header("Recent activity", "Freshness of database-backed readings and predictions.")
        activity = pd.DataFrame(
            [
                {"Signal": "Latest reading", "Value": format_datetime(latest_timestamp(data["readings"], "timestamp"))},
                {"Signal": "Latest prediction", "Value": format_datetime(latest_timestamp(data["predictions"], "timestamp"))},
                {"Signal": "Latest alert", "Value": format_datetime(latest_timestamp(data["alerts"], "created_at"))},
            ]
        )
        st.dataframe(activity, use_container_width=True, hide_index=True)

    section_header("Model artifacts", "Existing saved model assets currently used by the Streamlit app.")
    model_rows = [
        {"Artifact": "Binary model", "Value": str(ml_model.binary_model_path) if ml_model.binary_model_path else "Missing"},
        {"Artifact": "Multi-class model", "Value": str(ml_model.multi_model_path) if ml_model.multi_model_path else "Missing"},
        {"Artifact": "Scaler", "Value": str(ml_model.scaler_path) if ml_model.scaler_path else "Missing"},
        {"Artifact": "Feature list", "Value": str(ml_model.features_path) if ml_model.features_path else "Missing"},
        {"Artifact": "Feature count", "Value": str(len(ml_model.feature_list or []))},
        {"Artifact": "Model directory", "Value": str(MODEL_DIR)},
    ]
    st.dataframe(pd.DataFrame(model_rows), use_container_width=True, hide_index=True)

    section_header("Data footprint", "Current backing database files detected on disk.")
    root = Path(__file__).resolve().parents[2]
    db_candidates = [
        root / "data" / "leak_detection.db",
        root / "web_app" / "data" / "leak_detection.db",
    ]
    db_rows = []
    for candidate in db_candidates:
        db_rows.append(
            {
                "Database file": str(candidate),
                "Exists": candidate.exists(),
                "Size (KB)": round(candidate.stat().st_size / 1024, 1) if candidate.exists() else 0,
            }
        )
    st.dataframe(pd.DataFrame(db_rows), use_container_width=True, hide_index=True)
