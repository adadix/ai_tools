#!/usr/bin/env python3
"""
ML-Based Coverage Saturation Predictor

Predicts when coverage will saturate (plateau) to optimize collection duration.
Uses time-series analysis to determine optimal stopping point.

Features:
- Analyzes coverage growth curves
- Predicts saturation point
- Recommends optimal collection duration
- Estimates marginal coverage gains

Author: Intel Corporation
Date: December 2025
"""

import json
import pickle
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional
from datetime import datetime
import numpy as np

try:
    from sklearn.preprocessing import StandardScaler
    from sklearn.linear_model import LinearRegression
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    print("[WARNING] scikit-learn not available. Saturation predictor will use basic heuristics.")


class MLSaturationPredictor:
    """ML-based coverage saturation predictor."""
    
    def __init__(self, data_dir: str = "C:\\silicon_coverage_analyzer_data"):
        """Initialize saturation predictor."""
        self.data_dir = Path(data_dir)
        self.models_dir = self.data_dir / "models" / "saturation_predictor"
        self.models_dir.mkdir(parents=True, exist_ok=True)
        
        self.model = None
        self.scaler = None
        
        # Saturation parameters
        self.saturation_threshold = 0.02  # <2% gain per 10 min = saturated
        self.min_samples = 3  # Need at least 3 data points
        
        # Load trained model if exists
        self._load_model()
    
    def _load_model(self):
        """Load trained model from disk."""
        model_path = self.models_dir / "saturation_model.pkl"
        scaler_path = self.models_dir / "saturation_scaler.pkl"
        
        if model_path.exists() and scaler_path.exists():
            try:
                with open(model_path, 'rb') as f:
                    self.model = pickle.load(f)
                with open(scaler_path, 'rb') as f:
                    self.scaler = pickle.load(f)
                
                print(f"[ML] Loaded saturation predictor from {model_path}")
                return True
            except Exception as e:
                print(f"[WARNING] Could not load saturation predictor: {e}")
                self.model = None
        return False
    
    def is_trained(self) -> bool:
        """Check if model is trained."""
        return self.model is not None
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get model information and status."""
        if not self.model:
            return {'status': 'untrained'}
        
        return {
            'status': 'trained',
            'algorithm': 'Time-Series Linear Regression',
            'saturation_threshold': f'{self.saturation_threshold*100:.1f}% per 10min'
        }
    
    def predict_saturation(self, coverage_timeline: List[Dict], 
                          current_duration_minutes: float) -> Dict[str, Any]:
        """
        Predict coverage saturation point.
        
        Args:
            coverage_timeline: List of {timestamp, coverage_pct} dicts
            current_duration_minutes: How long collection has run
            
        Returns:
            Saturation prediction with recommendations
        """
        if len(coverage_timeline) < self.min_samples:
            return {
                'status': 'insufficient_data',
                'message': f'Need at least {self.min_samples} coverage measurements',
                'recommendation': 'Continue collection (not enough data yet)'
            }
        
        # Extract time series data
        times = []
        coverages = []
        
        for i, point in enumerate(coverage_timeline):
            times.append(i * 10)  # Assume 10-minute intervals
            coverages.append(point.get('coverage', point.get('coverage_pct', 0)))
        
        times = np.array(times)
        coverages = np.array(coverages)
        
        # Calculate current growth rate
        current_rate = self._calculate_growth_rate(times, coverages)
        
        # Predict saturation
        if SKLEARN_AVAILABLE and self.model:
            prediction = self._ml_predict_saturation(times, coverages, current_rate)
        else:
            prediction = self._heuristic_predict_saturation(times, coverages, current_rate)
        
        # Add current status
        prediction['current_duration_minutes'] = current_duration_minutes
        prediction['current_coverage'] = float(coverages[-1])
        prediction['current_growth_rate'] = float(current_rate)
        
        return prediction
    
    def _calculate_growth_rate(self, times: np.ndarray, coverages: np.ndarray) -> float:
        """Calculate current coverage growth rate (% per 10 minutes)."""
        if len(coverages) < 2:
            return 0.0
        
        # Use last 3 points for recent trend
        recent_times = times[-3:]
        recent_coverages = coverages[-3:]
        
        if len(recent_coverages) < 2:
            return 0.0
        
        # Linear regression on recent data
        if len(recent_times) > 1:
            coeffs = np.polyfit(recent_times, recent_coverages, 1)
            rate = coeffs[0] * 10  # Rate per 10 minutes
        else:
            rate = (recent_coverages[-1] - recent_coverages[-2]) / (recent_times[-1] - recent_times[-2]) * 10
        
        return max(0, rate)
    
    def _ml_predict_saturation(self, times: np.ndarray, coverages: np.ndarray, 
                               current_rate: float) -> Dict[str, Any]:
        """ML-based saturation prediction."""
        # Fit growth curve
        X = times.reshape(-1, 1)
        y = coverages
        
        # Use exponential decay model: coverage = a * (1 - exp(-b*t)) + c
        # Simplified to polynomial for quick prediction
        
        # Predict future coverage
        future_times = np.arange(times[-1], times[-1] + 120, 10).reshape(-1, 1)  # Next 2 hours
        
        # Simple linear extrapolation for now
        lr = LinearRegression()
        lr.fit(X, y)
        future_coverages = lr.predict(future_times)
        
        # Find saturation point (where gain < threshold)
        saturation_time = None
        for i in range(1, len(future_coverages)):
            gain = future_coverages[i] - future_coverages[i-1]
            if gain < self.saturation_threshold:
                saturation_time = future_times[i][0]
                saturation_coverage = future_coverages[i]
                break
        
        if saturation_time:
            minutes_to_saturation = saturation_time - times[-1]
            return {
                'status': 'predicted',
                'saturated': False,
                'minutes_to_saturation': int(minutes_to_saturation),
                'predicted_final_coverage': float(saturation_coverage),
                'expected_gain': float(saturation_coverage - coverages[-1]),
                'recommendation': self._generate_recommendation(minutes_to_saturation, current_rate)
            }
        else:
            # Already saturated or will saturate beyond prediction window
            if current_rate < self.saturation_threshold:
                return {
                    'status': 'saturated',
                    'saturated': True,
                    'recommendation': f'Coverage saturated (growth rate: {current_rate:.2f}%/10min). Safe to stop collection.'
                }
            else:
                return {
                    'status': 'growing',
                    'saturated': False,
                    'recommendation': f'Still growing ({current_rate:.2f}%/10min). Continue collection.'
                }
    
    def _heuristic_predict_saturation(self, times: np.ndarray, coverages: np.ndarray,
                                     current_rate: float) -> Dict[str, Any]:
        """Heuristic-based saturation prediction."""
        # Check if already saturated
        if current_rate < self.saturation_threshold:
            return {
                'status': 'saturated',
                'saturated': True,
                'recommendation': f'Coverage appears saturated (growth: {current_rate:.2f}%/10min). Consider stopping collection.'
            }
        
        # Estimate time to saturation based on current rate
        current_coverage = coverages[-1]
        
        # Assume exponential decay to 95% coverage
        target_coverage = 95.0
        remaining_coverage = max(0, target_coverage - current_coverage)
        
        # Simple linear extrapolation
        if current_rate > 0:
            minutes_to_target = (remaining_coverage / current_rate) * 10
            
            return {
                'status': 'predicted',
                'saturated': False,
                'minutes_to_saturation': int(minutes_to_target),
                'predicted_final_coverage': float(target_coverage),
                'expected_gain': float(remaining_coverage),
                'recommendation': self._generate_recommendation(minutes_to_target, current_rate)
            }
        else:
            return {
                'status': 'stable',
                'saturated': False,
                'recommendation': f'Coverage stable at {current_coverage:.1f}%. May be at plateau.'
            }
    
    def _generate_recommendation(self, minutes_to_saturation: float, current_rate: float) -> str:
        """Generate human-readable recommendation."""
        if minutes_to_saturation < 10:
            return f"Near saturation. Stop collection now (estimated {minutes_to_saturation:.0f} minutes to plateau)."
        elif minutes_to_saturation < 30:
            return f"Continue for ~{minutes_to_saturation:.0f} more minutes to reach saturation."
        elif minutes_to_saturation < 60:
            return f"Run for ~{minutes_to_saturation:.0f} more minutes for maximum coverage (growth rate: {current_rate:.2f}%/10min)."
        else:
            return f"Still far from saturation (~{minutes_to_saturation/60:.1f} hours remaining). Consider longer collection or stopping at target coverage."
    
    def analyze_collection_efficiency(self, coverage_timeline: List[Dict]) -> Dict[str, Any]:
        """
        Analyze collection efficiency over time.
        
        Returns coverage gain per time unit to help optimize future collections.
        """
        if len(coverage_timeline) < 2:
            return {'status': 'insufficient_data'}
        
        times = []
        coverages = []
        
        for i, point in enumerate(coverage_timeline):
            times.append(i * 10)
            coverages.append(point.get('coverage', point.get('coverage_pct', 0)))
        
        # Calculate efficiency metrics
        total_time = times[-1]
        total_gain = coverages[-1] - coverages[0]
        avg_rate = total_gain / (total_time / 10) if total_time > 0 else 0
        
        # Find diminishing returns point
        diminishing_point = None
        for i in range(1, len(coverages)):
            rate = (coverages[i] - coverages[i-1])
            if rate < self.saturation_threshold:
                diminishing_point = times[i]
                break
        
        # Calculate optimal duration (when 80% of total gain achieved)
        target_gain = total_gain * 0.8
        optimal_duration = None
        
        for i, cov in enumerate(coverages):
            if (cov - coverages[0]) >= target_gain:
                optimal_duration = times[i]
                break
        
        return {
            'status': 'complete',
            'total_duration_minutes': int(total_time),
            'total_coverage_gain': float(total_gain),
            'average_rate_per_10min': float(avg_rate),
            'diminishing_returns_at_minute': int(diminishing_point) if diminishing_point else None,
            'optimal_duration_minutes': int(optimal_duration) if optimal_duration else int(total_time),
            'efficiency_score': float(total_gain / (total_time / 60)) if total_time > 0 else 0  # % per hour
        }
    
    def train_from_history(self, historical_runs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Train saturation predictor from historical collection data.
        
        Args:
            historical_runs: List of runs with coverage timelines
            
        Returns:
            Training metrics
        """
        if not SKLEARN_AVAILABLE:
            return {'status': 'error', 'message': 'scikit-learn not available'}
        
        # For now, use simple linear model
        # In future, could use Prophet or ARIMA for better time-series prediction
        
        # Extract saturation points from historical data
        saturation_data = []
        
        for run in historical_runs:
            duration = run.get('metadata', {}).get('duration_seconds', 0) / 60
            coverage = run.get('coverage_results', run.get('coverage', {}))
            final_coverage = coverage.get('activity_coverage', coverage.get('overall_coverage_percentage', 0))
            
            if duration > 0 and final_coverage > 0:
                saturation_data.append({
                    'duration': duration,
                    'coverage': final_coverage
                })
        
        if len(saturation_data) < 5:
            return {'status': 'insufficient_data',
                   'message': f'Need at least 5 runs (have {len(saturation_data)})'}
        
        # Simple model: Learn average saturation curve
        durations = np.array([d['duration'] for d in saturation_data]).reshape(-1, 1)
        coverages = np.array([d['coverage'] for d in saturation_data])
        
        self.scaler = StandardScaler()
        durations_scaled = self.scaler.fit_transform(durations)
        
        self.model = LinearRegression()
        self.model.fit(durations_scaled, coverages)
        
        score = self.model.score(durations_scaled, coverages)
        
        # Save model
        self._save_model()
        
        print(f"[ML] Saturation predictor trained - R²: {score:.3f}")
        
        return {
            'status': 'success',
            'model': 'Linear Regression',
            'training_samples': len(saturation_data),
            'r2_score': float(score)
        }
    
    def _save_model(self):
        """Save trained model to disk."""
        try:
            with open(self.models_dir / "saturation_model.pkl", 'wb') as f:
                pickle.dump(self.model, f)
            with open(self.models_dir / "saturation_scaler.pkl", 'wb') as f:
                pickle.dump(self.scaler, f)
        except Exception as e:
            print(f"[WARNING] Could not save saturation predictor: {e}")
