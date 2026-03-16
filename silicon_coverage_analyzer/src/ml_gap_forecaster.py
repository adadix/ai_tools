#!/usr/bin/env python3
"""
ML-Based Gap Trend Forecaster

Predicts future gap trends and coverage trajectory using time-series analysis.
Helps answer questions like:
- "When will we hit 90% coverage?"
- "Are gaps increasing or decreasing?"
- "Will we meet our coverage target by deadline?"

Uses ARIMA-like linear forecasting for gap count and coverage prediction.

Author: Intel Corporation
Date: December 2025
"""

import json
import pickle
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional
from datetime import datetime, timedelta
import numpy as np

try:
    from sklearn.linear_model import LinearRegression
    from sklearn.preprocessing import StandardScaler
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    print("[WARNING] scikit-learn not available. Gap forecasting unavailable.")


class MLGapForecaster:
    """ML-based gap trend forecaster."""
    
    def __init__(self, data_dir: str = "C:\\silicon_coverage_analyzer_data"):
        """Initialize gap forecaster."""
        self.data_dir = Path(data_dir)
        self.models_dir = self.data_dir / "models" / "gap_forecaster"
        self.models_dir.mkdir(parents=True, exist_ok=True)
        
        self.coverage_model = None
        self.gap_model = None
        self.scaler = None
        
        # Load trained models if exist
        self._load_model()
    
    def _load_model(self):
        """Load trained models from disk."""
        coverage_model_path = self.models_dir / "coverage_forecaster.pkl"
        gap_model_path = self.models_dir / "gap_forecaster.pkl"
        scaler_path = self.models_dir / "forecaster_scaler.pkl"
        
        if coverage_model_path.exists() and gap_model_path.exists() and scaler_path.exists():
            try:
                with open(coverage_model_path, 'rb') as f:
                    self.coverage_model = pickle.load(f)
                with open(gap_model_path, 'rb') as f:
                    self.gap_model = pickle.load(f)
                with open(scaler_path, 'rb') as f:
                    self.scaler = pickle.load(f)
                
                print(f"[ML] Loaded gap forecaster from {self.models_dir}")
                return True
            except Exception as e:
                print(f"[WARNING] Could not load gap forecaster: {e}")
                self.coverage_model = None
                self.gap_model = None
        return False
    
    def is_trained(self) -> bool:
        """Check if model is trained."""
        return self.coverage_model is not None and self.gap_model is not None
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get model information and status."""
        if not self.is_trained():
            return {'status': 'untrained'}
        
        return {
            'status': 'trained',
            'algorithm': 'Linear Regression (Time-Series)',
            'models': ['Coverage Forecaster', 'Gap Count Forecaster']
        }
    
    def forecast_trends(self, historical_runs: List[Dict], 
                       forecast_runs: int = 5) -> Dict[str, Any]:
        """
        Forecast coverage and gap trends for future runs.
        
        Args:
            historical_runs: List of historical run data
            forecast_runs: Number of future runs to forecast
            
        Returns:
            Forecast predictions
        """
        if not SKLEARN_AVAILABLE:
            return {'status': 'error', 'message': 'scikit-learn not available'}
        
        if len(historical_runs) < 3:
            return {'status': 'insufficient_data',
                   'message': f'Need at least 3 runs for forecasting (have {len(historical_runs)})'}
        
        # Extract time series data
        coverage_series = []
        gap_series = []
        timestamps = []
        
        for i, run in enumerate(historical_runs):
            coverage = run.get('coverage_results', run.get('coverage', {}))
            gaps = run.get('gaps', {})
            
            coverage_pct = coverage.get('activity_coverage',
                                       coverage.get('overall_coverage_percentage', 0))
            gap_count = len(gaps.get('non_toggling_events', []))
            
            coverage_series.append(coverage_pct)
            gap_series.append(gap_count)
            timestamps.append(run.get('timestamp', ''))
        
        # Forecast using ML
        if self.is_trained():
            forecast = self._ml_forecast(coverage_series, gap_series, forecast_runs)
        else:
            forecast = self._heuristic_forecast(coverage_series, gap_series, forecast_runs)
        
        # Calculate trend indicators
        trend_analysis = self._analyze_trends(coverage_series, gap_series)
        
        # Generate predictions with forecasts array for UI compatibility
        forecasts = []
        for i in range(forecast_runs):
            forecasts.append([
                forecast['coverage'][i] if i < len(forecast['coverage']) else 0,
                forecast['gaps'][i] if i < len(forecast['gaps']) else 0
            ])
        
        predictions = {
            'status': 'success',  # Changed from 'complete' for UI compatibility
            'historical_runs': len(historical_runs),
            'forecast_runs': forecast_runs,
            'forecasts': forecasts,  # Added for UI display
            'coverage_forecast': forecast['coverage'],
            'gap_forecast': forecast['gaps'],
            'trend_health': trend_analysis.get('health', 'unknown'),  # Extract for UI
            'trend_analysis': trend_analysis,
            'target_predictions': self._predict_targets(forecast, trend_analysis)
        }
        
        return predictions
    
    def _ml_forecast(self, coverage_series: List[float], gap_series: List[float],
                    forecast_runs: int) -> Dict[str, List]:
        """ML-based forecasting using trained models."""
        X = np.arange(len(coverage_series)).reshape(-1, 1)
        
        # Forecast coverage
        coverage_pred = self.coverage_model.predict(
            np.arange(len(coverage_series), len(coverage_series) + forecast_runs).reshape(-1, 1)
        )
        coverage_pred = np.clip(coverage_pred, 0, 100)  # Bound between 0-100%
        
        # Forecast gaps
        gap_pred = self.gap_model.predict(
            np.arange(len(gap_series), len(gap_series) + forecast_runs).reshape(-1, 1)
        )
        gap_pred = np.maximum(gap_pred, 0)  # No negative gaps
        
        return {
            'coverage': coverage_pred.tolist(),
            'gaps': gap_pred.astype(int).tolist()
        }
    
    def _heuristic_forecast(self, coverage_series: List[float], gap_series: List[float],
                           forecast_runs: int) -> Dict[str, List]:
        """Heuristic-based forecasting using linear extrapolation."""
        # Calculate linear trends
        X = np.arange(len(coverage_series)).reshape(-1, 1)
        
        # Coverage trend
        coverage_model = LinearRegression()
        coverage_model.fit(X, np.array(coverage_series))
        coverage_pred = coverage_model.predict(
            np.arange(len(coverage_series), len(coverage_series) + forecast_runs).reshape(-1, 1)
        )
        coverage_pred = np.clip(coverage_pred, 0, 100)
        
        # Gap trend
        gap_model = LinearRegression()
        gap_model.fit(X, np.array(gap_series))
        gap_pred = gap_model.predict(
            np.arange(len(gap_series), len(gap_series) + forecast_runs).reshape(-1, 1)
        )
        gap_pred = np.maximum(gap_pred, 0)
        
        return {
            'coverage': coverage_pred.tolist(),
            'gaps': gap_pred.astype(int).tolist()
        }
    
    def _analyze_trends(self, coverage_series: List[float], 
                       gap_series: List[float]) -> Dict[str, Any]:
        """Analyze current trends in data."""
        if len(coverage_series) < 2:
            return {'trend': 'unknown'}
        
        # Calculate slopes
        X = np.arange(len(coverage_series)).reshape(-1, 1)
        
        coverage_lr = LinearRegression()
        coverage_lr.fit(X, np.array(coverage_series))
        coverage_slope = coverage_lr.coef_[0]
        
        gap_lr = LinearRegression()
        gap_lr.fit(X, np.array(gap_series))
        gap_slope = gap_lr.coef_[0]
        
        # Determine trend direction
        if coverage_slope > 0.5:
            coverage_trend = 'improving'
        elif coverage_slope < -0.5:
            coverage_trend = 'declining'
        else:
            coverage_trend = 'stable'
        
        if gap_slope < -2:
            gap_trend = 'decreasing'
        elif gap_slope > 2:
            gap_trend = 'increasing'
        else:
            gap_trend = 'stable'
        
        # Calculate velocity (rate of change)
        recent_coverage_change = coverage_series[-1] - coverage_series[-2] if len(coverage_series) >= 2 else 0
        recent_gap_change = gap_series[-1] - gap_series[-2] if len(gap_series) >= 2 else 0
        
        return {
            'coverage_trend': coverage_trend,
            'coverage_slope': float(coverage_slope),
            'coverage_velocity': float(recent_coverage_change),
            'gap_trend': gap_trend,
            'gap_slope': float(gap_slope),
            'gap_velocity': int(recent_gap_change),
            'overall_health': self._assess_health(coverage_trend, gap_trend)
        }
    
    def _assess_health(self, coverage_trend: str, gap_trend: str) -> str:
        """Assess overall validation health based on trends."""
        if coverage_trend == 'improving' and gap_trend == 'decreasing':
            return 'excellent'
        elif coverage_trend == 'improving' or gap_trend == 'decreasing':
            return 'good'
        elif coverage_trend == 'stable' and gap_trend == 'stable':
            return 'stable'
        elif coverage_trend == 'declining' or gap_trend == 'increasing':
            return 'concerning'
        else:
            return 'poor'
    
    def _predict_targets(self, forecast: Dict, trend_analysis: Dict) -> Dict[str, Any]:
        """Predict when targets will be reached."""
        predictions = {}
        
        coverage_forecast = forecast['coverage']
        gap_forecast = forecast['gaps']
        
        # Predict when 90% coverage will be reached
        target_90 = None
        for i, cov in enumerate(coverage_forecast):
            if cov >= 90:
                target_90 = i + 1
                break
        
        if target_90:
            predictions['coverage_90_in_runs'] = target_90
            predictions['coverage_90_message'] = f"Expected to reach 90% coverage in {target_90} more runs"
        elif coverage_forecast[-1] < 90:
            # Extrapolate
            slope = trend_analysis['coverage_slope']
            current = coverage_forecast[0] if coverage_forecast else 0
            if slope > 0:
                runs_needed = int((90 - current) / slope)
                predictions['coverage_90_in_runs'] = runs_needed
                predictions['coverage_90_message'] = f"Estimated {runs_needed} runs to reach 90% (extrapolated)"
            else:
                predictions['coverage_90_message'] = "90% target unlikely with current trend"
        
        # Predict when gaps will drop below 50
        target_gaps = None
        for i, gaps in enumerate(gap_forecast):
            if gaps < 50:
                target_gaps = i + 1
                break
        
        if target_gaps:
            predictions['gaps_below_50_in_runs'] = target_gaps
            predictions['gaps_message'] = f"Expected to reduce gaps below 50 in {target_gaps} more runs"
        elif gap_forecast[-1] >= 50:
            slope = trend_analysis['gap_slope']
            current = gap_forecast[0] if gap_forecast else 0
            if slope < 0:
                runs_needed = int((current - 50) / abs(slope))
                predictions['gaps_below_50_in_runs'] = runs_needed
                predictions['gaps_message'] = f"Estimated {runs_needed} runs to drop below 50 gaps"
            else:
                predictions['gaps_message'] = "Gap reduction unlikely with current trend"
        
        # Risk assessment
        if trend_analysis['overall_health'] in ['concerning', 'poor']:
            predictions['risk_alert'] = "[WARN] Trend reversal detected - investigate potential regression"
        
        return predictions
    
    def train_from_history(self, historical_runs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Train forecasting models from historical data.
        
        Args:
            historical_runs: List of historical run data
            
        Returns:
            Training metrics
        """
        if not SKLEARN_AVAILABLE:
            return {'status': 'error', 'message': 'scikit-learn not available'}
        
        if len(historical_runs) < 5:
            return {'status': 'insufficient_data',
                   'message': f'Need at least 5 runs (have {len(historical_runs)})'}
        
        # Extract time series
        coverage_series = []
        gap_series = []
        
        for run in historical_runs:
            coverage = run.get('coverage_results', run.get('coverage', {}))
            gaps = run.get('gaps', {})
            
            coverage_pct = coverage.get('activity_coverage',
                                       coverage.get('overall_coverage_percentage', 0))
            gap_count = len(gaps.get('non_toggling_events', []))
            
            coverage_series.append(coverage_pct)
            gap_series.append(gap_count)
        
        X = np.arange(len(coverage_series)).reshape(-1, 1)
        
        # Train coverage forecaster
        self.coverage_model = LinearRegression()
        self.coverage_model.fit(X, np.array(coverage_series))
        coverage_score = self.coverage_model.score(X, np.array(coverage_series))
        
        # Train gap forecaster
        self.gap_model = LinearRegression()
        self.gap_model.fit(X, np.array(gap_series))
        gap_score = self.gap_model.score(X, np.array(gap_series))
        
        # Scaler (for future use)
        self.scaler = StandardScaler()
        self.scaler.fit(X)
        
        # Save models
        self._save_model()
        
        print(f"[ML] Gap forecaster trained - Coverage R²: {coverage_score:.3f}, Gap R²: {gap_score:.3f}")
        
        return {
            'status': 'success',
            'model': 'Linear Regression',
            'training_samples': len(historical_runs),
            'coverage_r2': float(coverage_score),
            'gap_r2': float(gap_score)
        }
    
    def _save_model(self):
        """Save trained models to disk."""
        try:
            with open(self.models_dir / "coverage_forecaster.pkl", 'wb') as f:
                pickle.dump(self.coverage_model, f)
            with open(self.models_dir / "gap_forecaster.pkl", 'wb') as f:
                pickle.dump(self.gap_model, f)
            with open(self.models_dir / "forecaster_scaler.pkl", 'wb') as f:
                pickle.dump(self.scaler, f)
        except Exception as e:
            print(f"[WARNING] Could not save gap forecaster: {e}")
