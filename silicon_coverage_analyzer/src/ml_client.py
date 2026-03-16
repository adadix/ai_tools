"""
ML Client - 100% Local ML Analysis (Intel-Compliant)

 NO EXTERNAL API CALLS - ALL PROCESSING LOCAL

This module provides ML-powered coverage analysis using:
- [OK] scikit-learn (local training and inference)
- [OK] scikit-learn-intelex (Intel CPU acceleration)
- [OK] Local data storage only
- [OK] No cloud/API dependencies
- [OK] Intel-approved packages only

ML Capabilities:
- Anomaly detection (IsolationForest)
- Pattern classification (RandomForest)
- Coverage prediction (GradientBoosting)
- Event clustering (DBSCAN)
- Trend analysis
"""

import sys
import os
import json
import logging
import numpy as np
import warnings
from pathlib import Path

# Suppress numpy warnings for edge cases
warnings.filterwarnings('ignore', message='invalid value encountered in divide')
warnings.filterwarnings('ignore', message='invalid value encountered in.*corrcoef')

# Import local ML trainer
from src.ml_trainer import MLTrainer

logger = logging.getLogger(__name__)


class MLClient:
    """
    ML Client for local coverage analysis.
    100% local processing using scikit-learn models.
    """
    
    # Class-level flag to track feature mismatch warning across all instances
    _feature_mismatch_warned = False
    
    def __init__(self, config):
        """
        Initialize ML Client with local trainer.
        
        Args:
            config (dict): Configuration with ml_api settings
        """
        self.config = config
        self.ml_config = config.get('ml_api', {})
        
        # Initialize local ML trainer
        self.trainer = MLTrainer(config)
        self.local_models_available = self.trainer.enabled
        
        # Feature flags
        self.features = self.ml_config.get('features', {})
        self.anomaly_detection_enabled = self.features.get('anomaly_detection', True)
        self.coverage_prediction_enabled = self.features.get('coverage_prediction', True)
        self.workload_recommendation_enabled = self.features.get('workload_recommendation', True)
        
        logger.info("[OK] ML Client initialized with local models only")
    
    def train_models(self, coverage_results=None, metadata=None):
        """
        Train ML models on collected data.
        
        Args:
            coverage_results: Current coverage results to include in training
            metadata: Collection metadata (timestamp, workload, hardware)
        
        Returns:
            dict: Training results and model performance
        """
        if not self.local_models_available:
            return {
                'status': 'unavailable',
                'message': 'ML training not available (scikit-learn missing)'
            }
        
        # Save current data if provided
        if coverage_results and metadata:
            self.trainer.save_coverage_data(coverage_results, metadata)
        
        # Train on all collected data
        results = self.trainer.train_on_collected_data(
            current_results={'coverage_results': coverage_results, 'metadata': metadata}
            if coverage_results else None
        )
        
        return results
    
    def detect_anomalies(self, event_data, domain, context=None):
        """
        Detect anomalies using local trained ML models only (no statistical fallback).
        
        Args:
            event_data (dict): Event data with counts and per-core distributions
            domain (str): PMU domain (e.g., 'p-core', 'imc', 'cbo')
            context (dict): Additional context (workload, hardware, duration)
            
        Returns:
            list: Detected anomalies with scores and recommendations, or empty list if model not trained
        """
        # Use local trained model if available
        if self.local_models_available and self.trainer.anomaly_detector is not None:
            logger.info(f"[ML-Local] Running anomaly detection for {domain}")
            return self._detect_anomalies_local(event_data, domain)
        else:
            # No fallback - return empty list if model not available
            logger.debug(f"[ML] Anomaly detection model not trained yet for {domain}")
            return []
    
    def _detect_anomalies_local(self, event_data, domain):
        """Detect anomalies using locally trained IsolationForest model."""
        import pandas as pd
        
        anomalies = []
        
        # Flag all completely inactive events as anomalies
        for event_name, data in event_data.items():
            total = data.get('total', 0)
            if total == 0:
                anomalies.append({
                    'event': event_name,
                    'type': 'inactive_event',
                    'severity': 'high',
                    'source': 'local_model',
                    'confidence': 1.0,
                    'explanation': "Event did not toggle during collection. "
                                 "The hardware feature monitored by this event is not being exercised.",
                    'recommendation': "Check if workload should activate this feature, "
                                    "or verify event is supported on this hardware"
                })
        
        try:
            # Prepare features for active events
            features_list = []
            event_names = []
            
            for event_name, data in event_data.items():
                # Skip inactive events (already flagged)
                if data.get('total', 0) == 0:
                    continue
                    
                features = {
                    'total_count': data.get('total', 0),
                    'active_count': len([c for c in data.get('per_core', {}).values() if c > 0]),
                    'zero_count': len([c for c in data.get('per_core', {}).values() if c == 0]),
                }
                
                counts = list(data.get('per_core', {}).values())
                if counts:
                    counts_array = np.array(counts)
                    active_counts = counts_array[counts_array > 0]
                    
                    if len(active_counts) > 0:
                        features['count_mean'] = np.mean(active_counts)
                        features['count_std'] = np.std(active_counts)
                        features['count_min'] = np.min(active_counts)
                        features['count_max'] = np.max(active_counts)
                        features['count_cv'] = (np.std(active_counts) / np.mean(active_counts)) \
                                             if np.mean(active_counts) > 0 else 0
                    else:
                        features.update({
                            'count_mean': 0, 'count_std': 0, 'count_min': 0,
                            'count_max': 0, 'count_cv': 0
                        })
                    
                    features['toggle_rate'] = features['active_count'] / features['total_count'] \
                                            if features['total_count'] > 0 else 0
                
                features_list.append(features)
                event_names.append(event_name)
            
            if not features_list:
                return anomalies  # Return just inactive event anomalies
            
            # Create DataFrame
            X = pd.DataFrame(features_list)
            
            # Fill missing columns with 0
            required_cols = ['total_count', 'active_count', 'zero_count', 'toggle_rate',
                           'count_mean', 'count_std', 'count_min', 'count_max', 'count_cv']
            for col in required_cols:
                if col not in X.columns:
                    X[col] = 0
            
            X = X[required_cols].fillna(0)
            
            # Scale and predict using anomaly-specific scaler
            try:
                X_scaled = self.trainer.anomaly_scaler.transform(X)
                predictions = self.trainer.anomaly_detector.predict(X_scaled)
                
                # Collect anomalies
                for i, (pred, event_name) in enumerate(zip(predictions, event_names)):
                    if pred == -1:  # Anomaly detected
                        features = features_list[i]
                        anomalies.append({
                            'event': event_name,
                            'type': 'statistical_outlier',
                            'severity': 'medium',
                            'source': 'local_model',
                            'confidence': 0.8,
                            'explanation': f"Event shows anomalous behavior compared to training data. "
                                         f"Toggle rate: {features.get('toggle_rate', 0):.2%}",
                            'recommendation': "Review this event's behavior across different workloads"
                        })
                
                logger.info(f"[ML-Local] Detected {len(anomalies)} anomalies")
                
            except ValueError as ve:
                # Feature mismatch - models need retraining
                if "feature names" in str(ve).lower():
                    if not MLClient._feature_mismatch_warned:
                        logger.warning("[ML] Feature mismatch detected - "
                                     "models will be retrained at end of run")
                        MLClient._feature_mismatch_warned = True
                    self.trainer.enabled = False
                else:
                    logger.error(f"Error in local anomaly detection: {ve}")
            
        except Exception as e:
            logger.error(f"Error in local anomaly detection: {e}")
        
        return anomalies
    
    def _statistical_anomaly_detection(self, event_data, domain):
        """Fallback statistical anomaly detection using Z-scores."""
        import statistics
        
        anomalies = []
        
        # Check for completely inactive events
        for event, data in event_data.items():
            total = data.get('total', 0)
            if total == 0:
                anomalies.append({
                    'event': event,
                    'type': 'inactive_event',
                    'severity': 'high',
                    'source': 'statistical',
                    'expected_range': [1, float('inf')],
                    'actual_value': 0,
                    'explanation': 'Event did not toggle at all during collection. '
                                 'This indicates the hardware feature is not being exercised by the workload.',
                    'recommendation': 'Verify workload activates this hardware feature, '
                                    'or investigate if event is supported on this hardware',
                    'confidence': 1.0
                })
        
        # Calculate Z-scores for active events
        counts = [data.get('total', 0) for data in event_data.values() if data.get('total', 0) > 0]
        
        if len(counts) < 3:
            return anomalies
        
        mean = statistics.mean(counts)
        stdev = statistics.stdev(counts) if len(counts) > 1 else 0
        
        if stdev == 0:
            return anomalies
        
        for event, data in event_data.items():
            total = data.get('total', 0)
            if total > 0:
                z_score = (total - mean) / stdev
                
                if abs(z_score) > 3.0:  # 3-sigma outlier
                    anomalies.append({
                        'event': event,
                        'type': 'statistical_outlier',
                        'severity': 'high' if abs(z_score) > 4 else 'medium',
                        'source': 'statistical',
                        'expected_range': [mean - 2*stdev, mean + 2*stdev],
                        'actual_value': total,
                        'explanation': f'Event count is {abs(z_score):.1f} standard deviations '
                                     f'from mean (threshold: 3.0). This is statistically unusual.',
                        'recommendation': 'Verify event count is expected for workload',
                        'confidence': 0.7
                    })
        
        return anomalies
    
    def get_stats(self):
        """Get ML client usage statistics."""
        return {
            'enabled': self.local_models_available,
            'models_available': {
                'anomaly_detector': self.trainer.anomaly_detector is not None,
                'coverage_predictor': self.trainer.coverage_predictor is not None,
                'pattern_classifier': self.trainer.pattern_classifier is not None,
                'event_clusterer': self.trainer.event_clusterer is not None,
                'stress_correlation_model': self.trainer.stress_correlation_model is not None,
                'health_predictor': self.trainer.health_predictor is not None
            },
            'training_sessions': len(self.trainer.training_history.get('sessions', [])),
            'data_directory': str(self.trainer.base_dir)
        }
