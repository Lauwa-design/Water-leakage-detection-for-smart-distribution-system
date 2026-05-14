"""Shared data loading and service bootstrapping helpers for the dashboard."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd
import streamlit as st

from backend.mysql_database_manager import db_manager, seed_demo_data
from backend.ml_integration import ml_model
from backend.smart_meter_simulator import setup_sample_meters, smart_meter_simulator
from prediction_loop import prediction_loop, start_prediction_loop


@dataclass
class ServiceState:
    name: str
    healthy: bool
    detail: str
    tone: str


# ── Hot cache ─────────────────────────────────────────────────────────────────
# Static data (meters, zones) is loaded synchronously at module import so it is
# always available the moment the first user logs in — no background wait needed.
# Monitoring data (readings, predictions, alerts) is loaded on first request then
# kept fresh by an incremental background thread every 90 s.
_HOT_CACHE: Dict[str, Any] = {}
_HOT_LOCK   = threading.RLock()
_CACHE_READY = threading.Event()
_LAST_MON_UPDATE:    Optional[datetime] = None
_LAST_STATIC_UPDATE: Optional[datetime] = None
_STATIC_TTL_S     = 600   # refresh meters/zones every 10 min
_BG_INTERVAL_S    = 90    # background worker cadence
_READINGS_MAX_HRS = 48    # rolling window kept in memory
_HISTORY_INIT_HRS = 24    # initial monitoring fetch window


def _normalize_timestamps(df: pd.DataFrame, column: str) -> pd.DataFrame:
    if df.empty or column not in df.columns:
        return df
    normalized = df.copy()
    normalized[column] = pd.to_datetime(normalized[column], errors="coerce")
    return normalized


def _append_df(existing: pd.DataFrame, incoming: pd.DataFrame) -> pd.DataFrame:
    """Append incoming rows to existing, deduplicating by 'id' if the column exists."""
    if incoming.empty:
        return existing
    if existing.empty:
        return incoming.reset_index(drop=True)
    combined = pd.concat([existing, incoming], ignore_index=True)
    if "id" in combined.columns:
        combined = combined.drop_duplicates(subset=["id"], keep="last")
    return combined.reset_index(drop=True)


def clear_alert_cache() -> None:
    """Wipe alerts from the in-memory hot cache (call after an admin DB clear)."""
    with _HOT_LOCK:
        _HOT_CACHE["alerts"] = pd.DataFrame()


def _fetch_monitoring() -> Dict[str, pd.DataFrame]:
    """Raw DB fetch — no Streamlit context needed, callable from any thread."""
    meters  = db_manager.get_all_meters()
    zones   = db_manager.get_all_zones()
    readings     = _normalize_timestamps(db_manager.get_sensor_readings(hours=6),  "timestamp")
    predictions  = _normalize_timestamps(db_manager.get_leak_predictions(hours=24), "timestamp")
    alerts       = _normalize_timestamps(db_manager.get_alerts(hours=24),           "created_at")
    return {
        "meters": meters, "zones": zones,
        "readings": readings, "predictions": predictions, "alerts": alerts,
    }


def _load_static_now() -> None:
    """Synchronously load meters + zones into cache at module import time.

    These tables rarely change and are small — loading them immediately means
    every page render has them available with zero wait, even before the
    background monitoring thread finishes its first cycle.
    """
    global _LAST_STATIC_UPDATE
    try:
        meters = db_manager.get_all_meters()
        zones  = db_manager.get_all_zones()
        with _HOT_LOCK:
            _HOT_CACHE["meters"] = meters
            _HOT_CACHE["zones"]  = zones
            _LAST_STATIC_UPDATE  = datetime.now()
        print(f"[Cache] Static data ready — {len(meters)} meters, {len(zones)} zones")
    except Exception as exc:
        print(f"[Cache] Static pre-load failed: {exc}")


def _bg_worker() -> None:
    """Background thread: seed only when tables are empty, then keep monitoring data fresh."""
    global _LAST_MON_UPDATE, _LAST_STATIC_UPDATE

    # Seed defaults only if the database is genuinely empty (first-time setup)
    try:
        if _HOT_CACHE.get("meters") is None or _HOT_CACHE["meters"].empty:
            seed_demo_data()
            _load_static_now()
    except Exception as exc:
        print(f"[BG] seed check failed: {exc}")

    while True:
        try:
            now = datetime.now()
            with _HOT_LOCK:
                last_mon    = _LAST_MON_UPDATE
                last_static = _LAST_STATIC_UPDATE

            # Refresh static data every 10 min (catches admin meter/zone changes)
            if last_static is None or (now - last_static).total_seconds() >= _STATIC_TTL_S:
                meters = db_manager.get_all_meters()
                zones  = db_manager.get_all_zones()
                with _HOT_LOCK:
                    _HOT_CACHE["meters"] = meters
                    _HOT_CACHE["zones"]  = zones
                    _LAST_STATIC_UPDATE  = now

            # Monitoring data — full fetch on first cycle, incremental after that
            if last_mon is None:
                readings    = _normalize_timestamps(db_manager.get_sensor_readings(hours=_READINGS_MAX_HRS),  "timestamp")
                predictions = _normalize_timestamps(db_manager.get_leak_predictions(hours=_HISTORY_INIT_HRS), "timestamp")
                alerts      = _normalize_timestamps(db_manager.get_alerts(hours=_HISTORY_INIT_HRS),           "created_at")
                with _HOT_LOCK:
                    _HOT_CACHE["readings"]    = readings
                    _HOT_CACHE["predictions"] = predictions
                    _HOT_CACHE["alerts"]      = alerts
                    _LAST_MON_UPDATE          = now
                _CACHE_READY.set()
                print(f"[BG] Monitoring cache ready — {len(readings)} readings, {len(predictions)} predictions, {len(alerts)} alerts")
            else:
                # Incremental: only fetch rows newer than last cycle
                delta_hrs = (now - last_mon).total_seconds() / 3600 + 0.05
                new_r = _normalize_timestamps(db_manager.get_sensor_readings(hours=delta_hrs),  "timestamp")
                new_p = _normalize_timestamps(db_manager.get_leak_predictions(hours=delta_hrs), "timestamp")
                new_a = _normalize_timestamps(db_manager.get_alerts(hours=delta_hrs),           "created_at")
                with _HOT_LOCK:
                    _HOT_CACHE["readings"]    = _append_df(_HOT_CACHE.get("readings",    pd.DataFrame()), new_r)
                    _HOT_CACHE["predictions"] = _append_df(_HOT_CACHE.get("predictions", pd.DataFrame()), new_p)
                    _HOT_CACHE["alerts"]      = _append_df(_HOT_CACHE.get("alerts",      pd.DataFrame()), new_a)
                    r = _HOT_CACHE["readings"]
                    if not r.empty and "timestamp" in r.columns:
                        cutoff = pd.Timestamp.now() - pd.Timedelta(hours=_READINGS_MAX_HRS)
                        _HOT_CACHE["readings"] = r[r["timestamp"] >= cutoff].reset_index(drop=True)
                    _LAST_MON_UPDATE = now
            # Periodic cleanup of expired session tokens
            try:
                from backend.session_manager import SessionManager
                SessionManager(db_manager).cleanup_expired()
            except Exception:
                pass
        except Exception as exc:
            print(f"[BG] Worker error: {exc}")
        time.sleep(_BG_INTERVAL_S)


# ── Pre-load static data synchronously at import time ────────────────────────
# Meters and zones are in the cache before the first user logs in.
_load_static_now()

# Background thread handles monitoring data and incremental updates
threading.Thread(target=_bg_worker, daemon=True).start()


def bootstrap_demo_environment() -> None:
    """Mark session as bootstrapped. Services are started explicitly by a System Admin."""
    st.session_state.setdefault("_thiwasco_bootstrap_complete", True)


@st.cache_data(ttl=600)
def load_static_data() -> Dict[str, pd.DataFrame]:
    """Return meters and zones — served from the in-memory hot cache (no DB round-trip)."""
    with _HOT_LOCK:
        meters = _HOT_CACHE.get("meters", pd.DataFrame())
        zones  = _HOT_CACHE.get("zones",  pd.DataFrame())
    if meters.empty:
        meters = db_manager.get_all_meters()
    if zones.empty:
        zones = db_manager.get_all_zones()
    return {"meters": meters, "zones": zones}


@st.cache_data(ttl=120)
def load_monitoring_data(hours: int = 24) -> Dict[str, pd.DataFrame]:
    """Streamlit-cached monitoring data fetch (requires Streamlit context)."""
    return _fetch_monitoring()


def get_cached_data(hours: int = 24) -> Dict[str, pd.DataFrame]:
    """Return monitoring data — from hot cache if ready, otherwise direct DB fetch.

    Static data (meters, zones) is always present (loaded at import time).
    Monitoring data (readings, predictions, alerts) comes from the hot cache once
    the background thread has completed its first cycle.  If it hasn't finished
    yet (e.g. first seconds after server restart) we do a direct DB fetch
    immediately — no blocking wait — and seed the cache so subsequent calls are
    fast.
    """
    if _CACHE_READY.is_set():
        with _HOT_LOCK:
            return dict(_HOT_CACHE)

    # Background thread still on its first cycle — fetch directly right now
    data = _fetch_monitoring()
    with _HOT_LOCK:
        _HOT_CACHE.update(data)
        if not _CACHE_READY.is_set():
            _CACHE_READY.set()
    return data


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
            columns=dict({"name": "zone_name", "type": "zone_type", "status": "zone_status"})
        )
        snapshot = snapshot.merge(zone_lookup, on="zone_id", how="left")

    if not readings_df.empty:
        readings = readings_df.sort_values("timestamp")
        latest_readings = readings.groupby("meter_id", as_index=False).tail(1)
        latest_readings = latest_readings.rename(
            columns=dict({"flow_rate": "current_flow", "pressure": "current_pressure", "timestamp": "last_seen"})
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
            columns=dict({"timestamp": "prediction_time"})
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
                columns=dict({
                    "severity": "alert_severity",
                    "status": "alert_status",
                    "title": "alert_title",
                    "created_at": "alert_created_at",
                })
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

    # ── Severity — the OPEN ALERT is the source of truth ────────────────────
    # Using the latest prediction confidence would create drift: a meter's
    # prediction score fluctuates every 30 s while its alert stays open until
    # someone resolves it.  Tying severity to alert_severity keeps Leak
    # Analysis, Overview, and the Alerts page counting the same thing.
    #
    #   critical — open alert with severity="critical"  (confidence was ≥ 0.95)
    #   warning  — open alert with severity="warning"   (confidence was 0.85–0.94)
    #   suspected— ML flagged a leak, confidence 0.65–0.84, no open alert yet
    #   (none)   — ML says no leak, or confidence too low to be actionable

    has_open_alert = snapshot["alert_status"].notna()
    raw_leak       = snapshot["leak_detected"].astype(bool)
    # Require confidence ≥ 0.65 for "suspected" to avoid flooding the queue with
    # near-threshold readings (the model floor for zero-feature inputs is ~0.61).
    high_enough    = snapshot["confidence"] >= 0.65

    is_critical  = has_open_alert & (snapshot["alert_severity"] == "critical")
    is_warning   = has_open_alert & (snapshot["alert_severity"] == "warning")
    is_suspected = raw_leak & high_enough & ~has_open_alert

    snapshot["severity"] = np.select(
        [is_critical, is_warning, is_suspected],
        ["critical", "warning", "suspected"],
        default="none",
    )

    # leak_detected: True for any meter the ML flagged OR that has an open alert
    snapshot["leak_detected"] = raw_leak | has_open_alert

    snapshot["status"] = np.select(
        [snapshot["severity"] == "critical", snapshot["severity"] == "warning"],
        ["new", "under_review"],
        default="monitoring",
    )

    snapshot["estimated_loss_l_hr"] = np.where(
        is_critical | is_warning,
        np.maximum(snapshot["current_flow"], snapshot["avg_flow"]) * snapshot["confidence"] * 60.0,
        0.0,
    )

    snapshot["attention_rank"] = np.select(
        [snapshot["severity"] == "critical", snapshot["severity"] == "warning"],
        [2, 1],
        default=0,
    )

    return snapshot.sort_values(["attention_rank", "confidence"], ascending=[False, False]).reset_index(drop=True)


@st.cache_data(ttl=30)
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
