# -*- coding: utf-8 -*-
"""Build merged_dataset.csv from raw simulated leak CSVs."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from src.utils.config import PROCESSED_DIR, RAW_DIR  # type: ignore
except ModuleNotFoundError:
    from utils.config import PROCESSED_DIR, RAW_DIR  # noqa: E402

# Columns required downstream by feature_extractor.extract_features / extract_window_features
REQUIRED_COLUMNS = frozenset(
    {
        "scenario",
        "mean_flow",
        "mean_pressure",
        "scenario_has_leak",
        "leak_type",
    }
)


def _resolve_raw_csv_path() -> Path:
    """Pick input CSV: env override → canonical name → newest simulated_leaks*.csv."""
    override = os.getenv("MERGED_DATA_SOURCE", "").strip()
    if override:
        p = Path(override)
        if not p.is_absolute():
            p = RAW_DIR / p
        if not p.exists():
            raise FileNotFoundError(
                f"MERGED_DATA_SOURCE points to missing file: {p}"
            )
        return p

    canonical = RAW_DIR / "simulated_leaks.csv"
    if canonical.exists():
        return canonical

    candidates = sorted(
        RAW_DIR.glob("simulated_leaks*.csv"),
        key=lambda x: x.stat().st_mtime,
        reverse=True,
    )
    if candidates:
        return candidates[0]

    raise FileNotFoundError(
        f"No raw simulated leak CSV found under {RAW_DIR}. "
        "Run generate_scenarios or set MERGED_DATA_SOURCE to a CSV path."
    )


def _validate_merged_schema(df: pd.DataFrame) -> None:
    missing = sorted(REQUIRED_COLUMNS - set(df.columns))
    if missing:
        raise ValueError(
            f"merged_dataset schema invalid — missing columns: {missing}. "
            f"Required: {sorted(REQUIRED_COLUMNS)}"
        )
    if df.empty:
        raise ValueError("merged_dataset is empty — nothing to write.")

    if "time_index" in df.columns and df.duplicated(subset=["scenario", "time_index"]).any():
        n_dup = int(df.duplicated(subset=["scenario", "time_index"]).sum())
        raise ValueError(
            f"Duplicate (scenario, time_index) rows ({n_dup}). "
            "Fix raw data or deduplicate before merge."
        )


def _print_dataset_summary(df: pd.DataFrame) -> None:
    n_rows = len(df)
    n_scenarios = df["scenario"].nunique()
    print("\n── merged_dataset summary ──")
    print(f"  Rows      : {n_rows}")
    print(f"  Scenarios : {n_scenarios}")
    print("  scenario_has_leak:")
    for val, cnt in df["scenario_has_leak"].value_counts().sort_index().items():
        print(f"    {val}: {cnt}")
    print("  leak_type (row counts):")
    for lt, cnt in df["leak_type"].value_counts().sort_index().items():
        print(f"    {lt}: {cnt}")
    print()


def build_dataset() -> Path:
    """Read latest/canonical raw CSV, validate, write merged_dataset.csv."""
    raw_path = _resolve_raw_csv_path()
    print(f"[INFO] Building merged dataset from: {raw_path}")

    df = pd.read_csv(raw_path)
    _validate_merged_schema(df)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / "merged_dataset.csv"
    df.to_csv(out_path, index=False)

    print(f"[OK] Wrote {out_path}")
    _print_dataset_summary(df)
    return out_path


if __name__ == "__main__":
    build_dataset()
