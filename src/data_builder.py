# -*- coding: utf-8 -*-
import pandas as pd
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from utils.config import RAW_DIR, PROCESSED_DIR

def build_dataset():
    raw_path = RAW_DIR / "simulated_leaks_1778327858.csv"
    if not raw_path.exists(): return
    
    df = pd.read_csv(raw_path)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df.to_csv(PROCESSED_DIR / "merged_dataset.csv", index=False)
    print(f"[OK] Dataset built at {PROCESSED_DIR}")

if __name__ == "__main__":
    build_dataset()