import pandas as pd
import numpy as np

df = pd.read_csv('data/processed/engineered_features.csv')
feats = ['mnf','night_flow_ratio','flow_variance','daily_variance',
         'pressure_flow_correlation','pressure_drop_pattern','flow_trend']

print('=== FEATURE DISCRIMINATION ANALYSIS ===')
print()

for f in feats:
    groups = [g[f].values for _, g in df.groupby('leak_type')]
    between_var = np.var([g.mean() for g in groups])
    within_var = np.mean([np.var(g) for g in groups])
    f_stat = between_var / within_var if within_var > 0 else 0
    print(f'{f}: F-stat={f_stat:.6f}')
    for lt in ['none','slow_leak','moderate_leak','extreme_leak']:
        sub = df[df['leak_type']==lt][f]
        print(f'  {lt:15s}: mean={sub.mean():.4f}, std={sub.std():.4f}, min={sub.min():.4f}, max={sub.max():.4f}')
        print()

multiclass = [
    "flow_p95",
    "flow_p99",
    "above_baseline_fraction",
    "spike_sharpness",
    "night_mnf_ratio",
    "pressure_drop_abs",
    "flow_cv",
    "flow_max_step",
    "pressure_cv",
    "flow_late_vs_early_rel",
]
print("=== MULTICLASS FEATURE DISCRIMINATION ===")
print()
for f in multiclass:
    if f not in df.columns:
        continue
    groups = [g[f].values for _, g in df.groupby("leak_type")]
    between_var = np.var([g.mean() for g in groups])
    within_var = np.mean([np.var(g) for g in groups])
    f_stat = between_var / within_var if within_var > 0 else 0
    print(f"{f}: F-stat={f_stat:.6f}")
    for lt in ["none", "slow_leak", "moderate_leak", "extreme_leak"]:
        sub = df[df["leak_type"] == lt][f]
        print(f'  {lt:15s}: mean={sub.mean():.4f}, std={sub.std():.4f}')
    print()

# Check enhanced features too
enhanced = ['peak_hour_flow','off_peak_flow','flow_consistency_score',
            'pressure_variance','pressure_trend','pressure_stability',
            'flow_pressure_ratio','anomaly_score','leak_signature_strength']
print('=== ENHANCED FEATURE DISCRIMINATION ===')
print()
for f in enhanced:
    if f in df.columns:
        groups = [g[f].values for _, g in df.groupby('leak_type')]
        between_var = np.var([g.mean() for g in groups])
        within_var = np.mean([np.var(g) for g in groups])
        f_stat = between_var / within_var if within_var > 0 else 0
        print(f'{f}: F-stat={f_stat:.6f}')
        for lt in ['none','slow_leak','moderate_leak','extreme_leak']:
            sub = df[df['leak_type']==lt][f]
            print(f'  {lt:15s}: mean={sub.mean():.4f}, std={sub.std():.4f}')
        print()
