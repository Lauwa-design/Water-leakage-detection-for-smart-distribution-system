"""Shared data loading and service bootstrapping helpers for the dashboard."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict

import numpy as np
import pandas as pd
import streamlit as st

from backend.database_manager import db_manager, seed_demo_data
from backend.ml_integration import ml_model
from backend.smart_meter_simulator import setup_sample_meters, smart_meter_simulator
from prediction_loop import prediction_loop, start_prediction_loop


@dataclass
class ServiceState:
    name: str
    healthy: bool
    detail: str
    tone: str


def bootstrap_demo_environment() -> None:
    """Seed demo assets and start background services once per session."""
    if st.session_state.get("_thiwasco_bootstrap_complete"):
        return

    seed_demo_data()

    if not smart_meter_simulator.meters:
        setup_sample_meters()

    if not smart_meter_simulator.is_running:
        smart_meter_simulator.start_simulation()

    start_prediction_loop()
    st.session_state["_thiwasco_bootstrap_complete"] = True


def _normalize_timestamps(df: pd.DataFrame, column: str) -> pd.DataFrame:
    if df.empty or column not in df.columns:
        return df

    normalized = df.copy()
    normalized[column] = pd.to_datetime(normalized[column], errors="coerce")
    return normalized


@st.cache_data(ttl=600)  # Cache static data for 10 minutes
def load_static_data() -> Dict[str, pd.DataFrame]:
    """Load static data (meters, zones) - fast, cached longer."""
    meters = db_manager.get_all_meters()
    zones = db_manager.get_all_zones()
    return {"meters": meters, "zones": zones}


def get_cached_data(hours: int = 24) -> Dict[str, pd.DataFrame]:
    """Get data with session state caching for ultra-fast page switches."""
    cache_key = f"monitoring_data_{hours}"
    
    # Check if data is in session state (faster than st.cache_data)
    if cache_key in st.session_state:
        return st.session_state[cache_key]
    
    # Load fresh data
    data = load_monitoring_data(hours=hours)
    st.session_state[cache_key] = data
    return data


@st.cache_data(ttl=120)  # Cache for 2 minutes
def load_monitoring_data(hours: int = 24) -> Dict[str, pd.DataFrame]:
    """Load the core dashboard datasets with normalized timestamps."""
    # Load static data first (fast, cached)
    static = load_static_data()
    
    # OPTIMIZATION: Load only recent readings (6h) for faster queries
    # Recent data is most relevant for leak detection
    readings_hours = min(hours, 6)  # Cap at 6 hours for speed
    
    # Load dynamic data separately (can be slow)
    readings = _normalize_timestamps(db_manager.get_sensor_readings(hours=readings_hours), "timestamp")
    predictions = _normalize_timestamps(db_manager.get_leak_predictions(hours=hours), "timestamp")
    alerts = _normalize_timestamps(db_manager.get_alerts(hours=hours), "created_at")

    return {
        "meters": static["meters"],
        "zones": static["zones"],
        "readings": readings,
        "predictions": predictions,
        "alerts": alerts,
    }


@st.cache_data(ttl=60)
def build_meter_snapshot(
    meters_df: pd.DataFrame,
    zones_df: pd.DataFrame,
    readings_df: pd.DataFrame,
    predictions_df: pd.DataFrame,
    alerts_df: pd.DataFrame,
) -> pd.DataFrame:
    """Build a single per-meter snapshot for page rendering."""
    if meters_df.empty:
        return pd.DataFrame()

    snapshot = meters_df.copy().rename(columns={"flow_rate": "baseline_flow"})
    defaults: Dict[str, Any] = {
        "zone_name": None,
        "zone_type": None,
        "zone_status": None,
        "current_flow": None,
        "current_pressure": None,
        "temperature": None,
        "last_seen": None,
        "avg_flow": None,
        "avg_pressure": None,
        "flow_variance": None,
        "pressure_variance": None,
        "readings_count": None,
        "mnf": None,
        "confidence": None,
        "leak_detected": None,
        "leak_type": None,
        "prediction_time": None,
        "alert_severity": None,
        "alert_status": None,
        "alert_title": None,
        "alert_created_at": None,
    }

    zone_columns = ["zone_id", "name", "region", "type", "estimated_connections", "status"]
    available_zone_columns = [column for column in zone_columns if column in zones_df.columns]
    if available_zone_columns:
        zone_lookup = zones_df[available_zone_columns].rename(
            columns={"name": "zone_name", "type": "zone_type", "status": "zone_status"}
        )
        snapshot = snapshot.merge(zone_lookup, on="zone_id", how="left")

    if not readings_df.empty:
        readings = readings_df.sort_values("timestamp")
        latest_readings = readings.groupby("meter_id", as_index=False).tail(1)
        latest_readings = latest_readings.rename(
            columns={"flow_rate": "current_flow", "pressure": "current_pressure", "timestamp": "last_seen"}
        )[["meter_id", "current_flow", "current_pressure", "temperature", "last_seen"]]

        reading_summary = readings.groupby("meter_id").agg(
            avg_flow=("flow_rate", "mean"),
            avg_pressure=("pressure", "mean"),
            flow_variance=("flow_rate", "var"),
            pressure_variance=("pressure", "var"),
            readings_count=("id", "count") if "id" in readings.columns else ("flow_rate", "count"),
        ).reset_index()

        night_readings = readings[readings["timestamp"].dt.hour.between(0, 5)]
        if night_readings.empty:
            mnf = readings.groupby("meter_id").agg(mnf=("flow_rate", "min")).reset_index()
        else:
            mnf = night_readings.groupby("meter_id").agg(mnf=("flow_rate", "mean")).reset_index()

        snapshot = snapshot.merge(latest_readings, on="meter_id", how="left")
        snapshot = snapshot.merge(reading_summary, on="meter_id", how="left")
        snapshot = snapshot.merge(mnf, on="meter_id", how="left")

    if not predictions_df.empty:
        predictions = predictions_df.sort_values("timestamp")
        latest_predictions = predictions.groupby("meter_id", as_index=False).tail(1).rename(
            columns={"timestamp": "prediction_time"}
        )
        latest_predictions = latest_predictions[
            ["meter_id", "confidence", "leak_detected", "leak_type", "prediction_time"]
        ]
        snapshot = snapshot.merge(latest_predictions, on="meter_id", how="left")

    if not alerts_df.empty:
        open_alerts = alerts_df[alerts_df["status"] != "resolved"].copy()
        if not open_alerts.empty:
            latest_alerts = open_alerts.sort_values("created_at").groupby("meter_id", as_index=False).tail(1)
            latest_alerts = latest_alerts.rename(
                columns={
                    "severity": "alert_severity",
                    "status": "alert_status",
                    "title": "alert_title",
                    "created_at": "alert_created_at",
                }
            )
            snapshot = snapshot.merge(
                latest_alerts[["meter_id", "alert_severity", "alert_status", "alert_title", "alert_created_at"]],
                on="meter_id",
                how="left",
            )

    for column, default in defaults.items():
        if column not in snapshot.columns:
            snapshot[column] = default

    snapshot["current_flow"] = snapshot["current_flow"].fillna(snapshot.get("baseline_flow", 0)).fillna(0.0)
    snapshot["current_pressure"] = snapshot["current_pressure"].fillna(snapshot.get("avg_pressure", 0)).fillna(0.0)
    snapshot["avg_flow"] = snapshot["avg_flow"].fillna(snapshot["current_flow"])
    snapshot["avg_pressure"] = snapshot["avg_pressure"].fillna(snapshot["current_pressure"])
    snapshot["flow_variance"] = snapshot["flow_variance"].fillna(0.0)
    snapshot["pressure_variance"] = snapshot["pressure_variance"].fillna(0.0)
    snapshot["mnf"] = snapshot["mnf"].fillna(snapshot["current_flow"])
    snapshot["confidence"] = snapshot["confidence"].fillna(0.0)
    snapshot["leak_detected"] = snapshot["leak_detected"].fillna(False).astype(bool)
    snapshot["leak_type"] = snapshot["leak_type"].fillna("none")
    snapshot["zone_name"] = snapshot["zone_name"].fillna(snapshot["zone_id"])
    snapshot["zone"] = snapshot["zone_name"].fillna(snapshot["zone_id"])

    # Only flag as leak if leak_detected is True AND confidence is high enough
    is_leak = snapshot["leak_detected"] == True
    confidence_warning = is_leak & (snapshot["confidence"] >= 0.85)
    confidence_critical = is_leak & (snapshot["confidence"] >= 0.95)
    # Calculate severity: critical/warning only for leaks, everything else is normal
    snapshot["severity"] = np.select(
        [confidence_critical, confidence_warning],
        ["critical", "warning"],
        default="normal",
    )

    # Calculate status based on severity (for all rows to avoid length mismatch)
    snapshot["status"] = np.select(
        [snapshot["severity"] == "critical", snapshot["severity"] == "warning"],
        ["new", "under_review"],
        default="normal",
    )

    snapshot["estimated_loss_l_hr"] = np.where(
        snapshot["leak_detected"],
        np.maximum(snapshot["current_flow"], snapshot["avg_flow"]) * snapshot["confidence"] * 60.0,
        0.0,
    )

    snapshot["attention_rank"] = np.select(
        [snapshot["severity"] == "critical", snapshot["severity"] == "warning"],
        [2, 1],
        default=0,
    )

    return snapshot.sort_values(["attention_rank", "confidence"], ascending=[False, False]).reset_index(drop=True)


def get_service_states() -> list[ServiceState]:
    """Return a concise health summary for the main runtime services."""
    states: list[ServiceState] = []

    try:
        meter_count = len(db_manager.get_all_meters())
        states.append(ServiceState("Database", True, f"Connected to {meter_count} meters", "success"))
    except Exception as exc:
        states.append(ServiceState("Database", False, f"{type(exc).__name__}: {str(exc)[:40]}", "danger"))

    model_ready = ml_model.binary_model is not None and bool(ml_model.feature_list)
    states.append(
        ServiceState(
            "Leak Model",
            model_ready,
            "Existing models loaded" if model_ready else "Model artifacts unavailable",
            "success" if model_ready else "danger",
        )
    )

    states.append(
        ServiceState(
            "Simulator",
            smart_meter_simulator.is_running,
            f"{len(smart_meter_simulator.meters)} meters in simulator" if smart_meter_simulator.is_running else "Simulator is stopped",
            "success" if smart_meter_simulator.is_running else "warning",
        )
    )

    states.append(
        ServiceState(
            "Prediction Loop",
            prediction_loop.is_running,
            "Background leak scoring is running" if prediction_loop.is_running else "Prediction loop is stopped",
            "success" if prediction_loop.is_running else "warning",
        )
    )

    return states


def latest_timestamp(df: pd.DataFrame, column: str) -> Any:
    """Safely read the latest timestamp from a dataframe."""
    if df.empty or column not in df.columns:
        return None
    latest = df[column].max()
    if pd.isna(latest):
        return None
    return latest


def format_datetime(value: Any) -> str:
    """Format timestamps consistently for the UI."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "No data yet"

    if isinstance(value, str):
        parsed = pd.to_datetime(value, errors="coerce")
        if pd.isna(parsed):
            return value
        value = parsed

    if isinstance(value, pd.Timestamp):
        value = value.to_pydatetime()

    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")

    return str(value)
