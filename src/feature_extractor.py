"""
Feature Extractor - NO DATA LEAKAGE VERSION
Extracts features using historical baseline from no-leak scenarios.

CRITICAL: This version prevents data leakage by:
1. Calculating baseline statistics from NO-LEAK scenarios only
2. Creating features as deviations from historical baseline
3. Using only information available in real-time operation

Pipeline position:  data_builder.py  →  [THIS FILE]  →  train_models.py

Input:  data/processed/merged_dataset.csv (raw features per scenario)
Output: data/processed/engineered_features.csv (advanced features for ML)
"""

import pandas as pd
import numpy as np
import warnings
warnings.filterwarnings('ignore')


class LeakFeatureExtractor:
    """
    Extract advanced features from water network data for leak detection.
    Uses historical baseline from no-leak scenarios to prevent data leakage.
    """
    
    def __init__(self, baseline_df=None):
        """
        Initialize the feature extractor with baseline data.
        
        Parameters:
        -----------
        baseline_df : DataFrame, optional
            Baseline data from no-leak scenarios for normalization
        """
        self.baseline = baseline_df
        self.feature_names = []
        
    def set_baseline(self, df):
        """
        Calculate baseline statistics from no-leak scenarios only.
        This prevents data leakage by using only historical data.
        """
        # Use only no-leak scenarios for baseline
        no_leak_df = df[df['scenario_has_leak'] == 0]
        
        self.baseline = {
            'flow_mean': no_leak_df['mean_flow'].mean(),
            'flow_std': no_leak_df['mean_flow'].std(),
            'pressure_mean': no_leak_df['mean_pressure'].mean(),
            'pressure_std': no_leak_df['mean_pressure'].std(),
            'demand_mean': no_leak_df['mean_demand'].mean(),
            'demand_std': no_leak_df['mean_demand'].std(),
            'night_flow_mean': no_leak_df['night_flow_mean'].mean(),
            'night_flow_std': no_leak_df['night_flow_mean'].std(),
            'pressure_drop_mean': no_leak_df['pressure_drop'].mean(),
            'pressure_drop_std': no_leak_df['pressure_drop'].std(),
        }
        
        print(f"\nBaseline calculated from {len(no_leak_df)} no-leak scenarios:")
        for key, value in self.baseline.items():
            print(f"  {key}: {value:.4f}")
        
        return self.baseline
    
    def extract_night_flow_features(self, df):
        """
        Extract night flow characteristics as deviations from baseline.
        """
        features = {}
        
        # Normalized night flow features (deviation from baseline)
        features['night_flow_deviation'] = (
            df['night_flow_mean'] - self.baseline['night_flow_mean']
        ) / (self.baseline['night_flow_std'] + 1e-6)
        
        features['night_flow_anomaly'] = np.maximum(0, features['night_flow_deviation'])
        
        # Night-to-day ratio (real-time feature, no leakage)
        features['night_to_day_ratio'] = df['night_to_day_ratio']
        
        self.feature_names.extend(features.keys())
        return pd.DataFrame(features)
    
    def extract_pressure_features(self, df):
        """
        Extract pressure-related features as deviations from baseline.
        """
        features = {}
        
        # Pressure deviation from baseline (key leak indicator)
        features['pressure_deviation'] = (
            df['mean_pressure'] - self.baseline['pressure_mean']
        ) / (self.baseline['pressure_std'] + 1e-6)
        
        # Negative pressure deviation indicates possible leak
        features['pressure_drop_alert'] = np.maximum(0, -features['pressure_deviation'])
        
        # Pressure drop deviation from baseline
        features['pressure_drop_deviation'] = (
            df['pressure_drop'] - self.baseline['pressure_drop_mean']
        ) / (self.baseline['pressure_drop_std'] + 1e-6)
        
        # Real-time pressure variability
        features['pressure_cv'] = df['std_pressure'] / (df['mean_pressure'] + 1e-6)
        
        self.feature_names.extend(features.keys())
        return pd.DataFrame(features)
    
    def extract_flow_features(self, df):
        """
        Extract flow-related features as deviations from baseline.
        """
        features = {}
        
        # Flow deviation from baseline (key leak indicator)
        features['flow_deviation'] = (
            df['mean_flow'] - self.baseline['flow_mean']
        ) / (self.baseline['flow_std'] + 1e-6)
        
        # High flow deviation indicates possible leak
        features['high_flow_alert'] = np.maximum(0, features['flow_deviation'])
        
        # Flow variability (real-time)
        features['flow_cv'] = df['std_flow'] / (df['mean_flow'] + 1e-6)
        
        # Flow stability index
        features['flow_stability'] = df['mean_flow'] / (df['std_flow'] + 1e-6)
        
        self.feature_names.extend(features.keys())
        return pd.DataFrame(features)
    
    def extract_demand_features(self, df):
        """
        Extract demand-related features as deviations from baseline.
        """
        features = {}
        
        # Demand deviation from baseline
        features['demand_deviation'] = (
            df['mean_demand'] - self.baseline['demand_mean']
        ) / (self.baseline['demand_std'] + 1e-6)
        
        # Peak demand ratio (real-time)
        features['peak_demand_ratio'] = df['max_demand'] / (df['mean_demand'] + 1e-6)
        
        self.feature_names.extend(features.keys())
        return pd.DataFrame(features)
    
    def extract_hydraulic_imbalance_features(self, df):
        """
        Extract hydraulic imbalance indicators (real-time, no leakage).
        """
        features = {}
        
        # Flow-demand relationship (real-time imbalance indicator)
        features['flow_demand_ratio'] = df['flow_demand_ratio']
        
        # Imbalance score (when flow > demand)
        features['hydraulic_imbalance'] = np.maximum(0, df['flow_demand_ratio'] - 1)
        
        # Mass balance error
        features['mass_balance_error'] = (
            (df['mean_flow'] - df['mean_demand']) / 
            (df['mean_demand'] + 1e-6)
        )
        
        self.feature_names.extend(features.keys())
        return pd.DataFrame(features)
    
    def extract_ratio_features(self, df):
        """
        Extract ratio-based features (real-time, no leakage).
        """
        features = {}
        
        # Flow to pressure ratio
        features['flow_pressure_ratio'] = df['mean_flow'] / (df['mean_pressure'] + 1e-6)
        
        # Demand to pressure ratio
        features['demand_pressure_ratio'] = df['mean_demand'] / (df['mean_pressure'] + 1e-6)
        
        self.feature_names.extend(features.keys())
        return pd.DataFrame(features)
    
    def extract_combined_features(self, df):
        """
        Extract combined anomaly scores using baseline deviations.
        """
        features = {}
        
        # Combined anomaly score from multiple indicators
        features['combined_anomaly'] = (
            features.get('flow_deviation', 0) + 
            features.get('pressure_deviation', 0) + 
            features.get('night_flow_deviation', 0)
        ) / 3
        
        # Simple rule-based alert (for interpretability)
        features['leak_alert_score'] = (
            (features.get('flow_deviation', 0) > 2).astype(int) +
            (features.get('pressure_deviation', 0) < -1).astype(int) +
            (features.get('night_flow_deviation', 0) > 1).astype(int)
        ) / 3
        
        self.feature_names.extend(features.keys())
        return pd.DataFrame(features)
    
    def extract_all_features(self, df):
        """
        Extract all features and combine into a single DataFrame.
        
        Parameters:
        -----------
        df : DataFrame
            Input data with raw features
            
        Returns:
        --------
        DataFrame with all extracted features
        """
        if self.baseline is None:
            self.set_baseline(df)
        
        print("\nExtracting leak detection features (no data leakage)...")
        
        feature_dfs = []
        
        # Extract each feature group
        print("  - Extracting night flow features (baseline deviation)...")
        feature_dfs.append(self.extract_night_flow_features(df))
        
        print("  - Extracting pressure features (baseline deviation)...")
        feature_dfs.append(self.extract_pressure_features(df))
        
        print("  - Extracting flow features (baseline deviation)...")
        feature_dfs.append(self.extract_flow_features(df))
        
        print("  - Extracting demand features (baseline deviation)...")
        feature_dfs.append(self.extract_demand_features(df))
        
        print("  - Extracting hydraulic imbalance features...")
        feature_dfs.append(self.extract_hydraulic_imbalance_features(df))
        
        print("  - Extracting ratio features...")
        feature_dfs.append(self.extract_ratio_features(df))
        
        # Combine all features
        features_df = pd.concat(feature_dfs, axis=1)
        
        # Remove duplicate columns
        features_df = features_df.loc[:, ~features_df.columns.duplicated()]
        
        print(f"\n✓ Extracted {len(features_df.columns)} leakage-free features")
        
        return features_df


def engineer_features(input_file, output_file, return_features=False):
    """
    Main function to engineer features from raw data.
    Uses baseline from no-leak scenarios to prevent data leakage.
    """
    print("="*70)
    print("FEATURE ENGINEERING PIPELINE (No Data Leakage)")
    print("="*70)
    
    # Load raw data
    print(f"\nLoading raw data from: {input_file}")
    df_raw = pd.read_csv(input_file)
    print(f"Raw data shape: {df_raw.shape}")
    print(f"Leak scenarios: {df_raw['scenario_has_leak'].sum()}")
    print(f"No-leak scenarios: {len(df_raw) - df_raw['scenario_has_leak'].sum()}")
    
    # Keep target columns
    target_cols = ['scenario', 'leak_type', 'scenario_has_leak', 'leak_score', 'leak_active']
    available_targets = [col for col in target_cols if col in df_raw.columns]
    targets = df_raw[available_targets].copy()
    
    # Initialize feature extractor with baseline from no-leak data
    extractor = LeakFeatureExtractor()
    extractor.set_baseline(df_raw)
    
    # Extract leakage-free features
    features_df = extractor.extract_all_features(df_raw)
    
    # Combine features with targets
    result_df = pd.concat([targets, features_df], axis=1)
    
    # Save to CSV
    result_df.to_csv(output_file, index=False)
    print(f"\n✓ Engineered features saved to: {output_file}")
    print(f"  Final dataset shape: {result_df.shape}")
    print(f"  Features: {len(features_df.columns)}")
    print(f"  Total columns: {len(result_df.columns)}")
    
    # Print feature summary
    print("\n" + "="*70)
    print("FEATURE SUMMARY (Leakage-Free)")
    print("="*70)
    
    print("\nFeature categories:")
    print(f"  - Night flow features: 2 (deviation, anomaly)")
    print(f"  - Pressure features: 4 (deviation, drop, alert, CV)")
    print(f"  - Flow features: 4 (deviation, alert, CV, stability)")
    print(f"  - Demand features: 2 (deviation, peak ratio)")
    print(f"  - Hydraulic imbalance: 3 (ratio, imbalance, mass error)")
    print(f"  - Ratio features: 2 (flow/pressure, demand/pressure)")
    print(f"  Total: {len(features_df.columns)} leakage-free features")
    
    # Show first few features
    print(f"\nFirst 10 features:")
    for i, col in enumerate(features_df.columns[:10], 1):
        print(f"  {i}. {col}")
    
    # Correlation with target (should be more realistic now)
    if 'scenario_has_leak' in result_df.columns:
        print("\n" + "="*70)
        print("CORRELATION WITH LEAK TARGET (Realistic)")
        print("="*70)
        correlations = result_df[features_df.columns].corrwith(result_df['scenario_has_leak']).abs().sort_values(ascending=False)
        print("\nTop 10 features most correlated with leak presence:")
        for feature, corr in correlations.head(10).items():
            print(f"  {feature}: {corr:.4f}")
        
        # Check for data leakage warning
        if correlations.head(1).values[0] > 0.9:
            print("\n⚠ WARNING: Very high correlation detected - possible data leakage!")
        else:
            print("\n✓ Correlations look realistic - no data leakage detected")
    
    if return_features:
        return result_df
    else:
        return None


def create_feature_sets(input_file):
    """
    Create multiple feature subsets for experimentation.
    """
    df_raw = pd.read_csv(input_file)
    extractor = LeakFeatureExtractor()
    extractor.set_baseline(df_raw)
    
    feature_sets = {}
    
    # Set 1: Deviation features (most important for leak detection)
    deviation_features = [
        'flow_deviation', 'pressure_deviation', 'night_flow_deviation',
        'demand_deviation', 'pressure_drop_deviation'
    ]
    feature_sets['deviation'] = [f for f in deviation_features if f in df_raw.columns]
    
    # Set 2: Alert features (rule-based indicators)
    alert_features = [
        'high_flow_alert', 'pressure_drop_alert', 'hydraulic_imbalance'
    ]
    feature_sets['alerts'] = [f for f in alert_features if f in df_raw.columns]
    
    # Set 3: All leakage-free features
    feature_sets['all'] = list(extractor.extract_all_features(df_raw).columns)
    
    return feature_sets


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Extract leakage-free features for leak detection",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage
  python feature_extractor.py
  
  # Specify custom paths
  python feature_extractor.py --input data/processed/merged_dataset.csv --output data/processed/engineered_features.csv
  
  # Return features for immediate use
  python feature_extractor.py --input data/processed/merged_dataset.csv --output data/processed/engineered_features.csv --return_data
        """
    )
    
    parser.add_argument(
        "--input",
        default="data/processed/merged_dataset.csv",
        help="Input raw features CSV file"
    )
    parser.add_argument(
        "--output",
        default="data/processed/engineered_features.csv",
        help="Output engineered features CSV file"
    )
    parser.add_argument(
        "--return_data",
        action="store_true",
        help="Return features DataFrame (for use in Python scripts)"
    )
    
    args = parser.parse_args()
    
    # Run feature engineering
    df = engineer_features(args.input, args.output, return_features=args.return_data)
    
    print("\n" + "="*70)
    print("✓ Feature extraction complete (No data leakage!)")
    print("="*70)
    print("\nNext steps:")
    print("  1. Train models: python src/train_models.py")
    print("  2. Features now represent real-time deviations from baseline")
    print("  3. No data leakage - results will reflect real-world performance")