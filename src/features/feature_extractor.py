"""
Feature extraction from leak scenario data
Extracts time-series features for ML model training
"""

import numpy as np
import pandas as pd
from pathlib import Path
from tqdm import tqdm
import json


class FeatureExtractor:
    """Extract features from scenario time-series data"""
    
    def __init__(self, timestep_minutes=30):
        self.timestep_minutes = timestep_minutes
        self.timesteps_per_day = int(24 * 60 / timestep_minutes)
        
    def extract_features_from_node(self, demands, pressures, node_name):
        """Extract features for a single node"""
        
        demand_series = demands[node_name].values
        pressure_series = pressures[node_name].values
        
        # Handle edge cases
        if len(demand_series) == 0:
            return None
            
        # Time-based indices
        night_start = int(22 * 60 / self.timestep_minutes)  # 22:00
        night_end = int(6 * 60 / self.timestep_minutes)      # 06:00
        
        # Create night/day masks
        night_mask = np.zeros(len(demand_series), dtype=bool)
        if len(demand_series) >= self.timesteps_per_day:
            for day in range(len(demand_series) // self.timesteps_per_day):
                start_idx = day * self.timesteps_per_day
                night_mask[start_idx + night_start:start_idx + self.timesteps_per_day] = True
                night_mask[start_idx:start_idx + night_end] = True
        
        day_mask = ~night_mask
        
        # Feature 1: Night-flow ratio
        night_flow = np.mean(demand_series[night_mask]) if night_mask.sum() > 0 else 0
        day_flow = np.mean(demand_series[day_mask]) if day_mask.sum() > 0 else 0
        night_flow_ratio = night_flow / (day_flow + 1e-6)
        
        # Feature 2: Daily variance
        daily_variance = np.std(demand_series)
        
        # Feature 3: Trend (linear regression slope)
        if len(demand_series) > 1:
            x = np.arange(len(demand_series))
            trend = np.polyfit(x, demand_series, 1)[0]
        else:
            trend = 0
        
        # Feature 4: Maximum hourly increase
        if len(demand_series) > 1:
            flow_diff = np.diff(demand_series)
            max_increase = np.max(flow_diff)
        else:
            max_increase = 0
        
        # Feature 5: Coefficient of variation
        mean_flow = np.mean(demand_series)
        cv = daily_variance / (mean_flow + 1e-6)
        
        # Feature 6-7: Flow percentiles
        flow_p50 = np.percentile(demand_series, 50)
        flow_p95 = np.percentile(demand_series, 95)
        
        # Feature 8-9: Pressure features
        mean_pressure = np.mean(pressure_series)
        pressure_variance = np.std(pressure_series)
        
        return {
            'node': node_name,
            'night_flow_ratio': float(night_flow_ratio),
            'daily_variance': float(daily_variance),
            'trend': float(trend),
            'max_increase': float(max_increase),
            'coefficient_variation': float(cv),
            'flow_p50': float(flow_p50),
            'flow_p95': float(flow_p95),
            'mean_pressure': float(mean_pressure),
            'pressure_variance': float(pressure_variance)
        }
    
    def extract_features_from_scenario(self, scenario_dir):
        """Extract features from one scenario"""
        
        scenario_dir = Path(scenario_dir)
        
        # Load data
        demands = pd.read_csv(scenario_dir / 'demands.csv', index_col=0)
        pressures = pd.read_csv(scenario_dir / 'pressures.csv', index_col=0)
        labels = pd.read_csv(scenario_dir / 'labels.csv', index_col=0)
        
        # Get label (max label value = 1 if any leak)
        has_leak = int(labels.values.max())
        
        # Extract features for each node
        features_list = []
        
        for node_name in demands.columns:
            node_features = self.extract_features_from_node(
                demands, pressures, node_name
            )
            
            if node_features:
                node_features['scenario'] = scenario_dir.name
                node_features['label'] = has_leak
                features_list.append(node_features)
        
        return features_list
    
    def extract_from_dataset(self, dataset_dir, output_file):
        """Extract features from all scenarios in dataset"""
        
        dataset_dir = Path(dataset_dir)
        scenario_dirs = sorted(dataset_dir.glob('scenario_*'))
        
        if len(scenario_dirs) == 0:
            print(f"⚠ No scenarios found in {dataset_dir}")
            return None
        
        print(f"\nExtracting features from {len(scenario_dirs)} scenarios...")
        
        all_features = []
        
        for scenario_dir in tqdm(scenario_dirs, desc="Extracting features"):
            try:
                features = self.extract_features_from_scenario(scenario_dir)
                all_features.extend(features)
            except Exception as e:
                print(f"\n⚠ Error in {scenario_dir.name}: {e}")
        
        # Convert to DataFrame
        df = pd.DataFrame(all_features)
        
        # Save
        output_file = Path(output_file)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output_file, index=False)
        
        print(f"\n✓ Features extracted!")
        print(f"  Output: {output_file}")
        print(f"  Shape: {df.shape}")
        print(f"  Leak samples: {df['label'].sum()} ({df['label'].mean()*100:.1f}%)")
        
        return df


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Extract features from scenarios')
    parser.add_argument('--input', type=str, required=True,
                       help='Input dataset directory')
    parser.add_argument('--output', type=str, required=True,
                       help='Output CSV file')
    
    args = parser.parse_args()
    
    extractor = FeatureExtractor()
    extractor.extract_from_dataset(args.input, args.output)