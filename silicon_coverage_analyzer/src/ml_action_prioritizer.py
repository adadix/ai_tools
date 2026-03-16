#!/usr/bin/env python3
"""
ML-Based Action Prioritizer

Learns priority ranking from user interactions and validation outcomes.
Uses Learning-to-Rank approach to personalize action recommendations.

Features:
- Learns from historical alert resolution patterns
- Tracks which alerts actually led to fixes
- Adapts to team's workflow priorities
- Provides explainable ranking scores

Author: Intel Corporation
Date: December 2025
"""

import json
import pickle
import yaml
from pathlib import Path
from typing import Dict, List, Tuple, Any
from datetime import datetime
from collections import Counter

try:
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.preprocessing import StandardScaler
    import numpy as np
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    print("[WARNING] scikit-learn not available. Action prioritization will use rule-based fallback.")


class MLActionPrioritizer:
    """ML-based action prioritizer with Learning-to-Rank approach."""
    
    def __init__(self, data_dir: str = "C:\\silicon_coverage_analyzer_data"):
        """Initialize action prioritizer."""
        self.data_dir = Path(data_dir)
        self.models_dir = self.data_dir / "models" / "action_prioritizer"
        self.models_dir.mkdir(parents=True, exist_ok=True)
        
        self.model = None
        self.scaler = None
        self.feature_names = []
        self.feedback_log = self.models_dir / "action_feedback.jsonl"
        
        # Load trained model if exists
        self._load_model()
    
    def _load_model(self):
        """Load trained model from disk."""
        model_path = self.models_dir / "action_ranker.pkl"
        scaler_path = self.models_dir / "action_scaler.pkl"
        features_path = self.models_dir / "action_features.pkl"
        
        if model_path.exists() and scaler_path.exists():
            try:
                with open(model_path, 'rb') as f:
                    self.model = pickle.load(f)
                with open(scaler_path, 'rb') as f:
                    self.scaler = pickle.load(f)
                
                # Load feature names if available
                if features_path.exists():
                    with open(features_path, 'rb') as f:
                        self.feature_names = pickle.load(f)
                else:
                    # Default feature names matching _extract_action_features for backwards compatibility
                    self.feature_names = [
                        'type_regression', 'type_gap', 'type_workload', 'type_platform', 'type_flaky', 'type_anomaly',
                        'severity_score',
                        'total_gaps', 'coverage_pct', 'regression_count', 'anomaly_count', 'flaky_count',
                        'historical_fix_rate', 'avg_fix_time_hours',
                        'regression_magnitude', 'regression_critical',
                        'gap_count', 'gap_high_priority',
                        'is_business_hours', 'critical_domain'
                    ]
                
                print(f"[ML] Loaded action prioritizer model from {model_path}")
                return True
            except Exception as e:
                print(f"[WARNING] Could not load action prioritizer: {e}")
                self.model = None
        return False
    
    def _extract_action_features(self, action: Dict[str, Any], 
                                 context: Dict[str, Any]) -> Dict[str, float]:
        """Extract ML features from action and context."""
        features = {}
        
        action_type = action.get('type', 'unknown')
        severity = action.get('severity', 'medium')
        
        # Action type encoding (one-hot)
        for atype in ['regression', 'gap', 'workload', 'platform', 'flaky', 'anomaly']:
            features[f'type_{atype}'] = 1.0 if action_type == atype else 0.0
        
        # Severity encoding
        severity_map = {'critical': 4.0, 'high': 3.0, 'medium': 2.0, 'low': 1.0, 'info': 0.5}
        features['severity_score'] = severity_map.get(severity, 2.0)
        
        # Context features
        features['total_gaps'] = float(context.get('total_gaps', 0))
        features['coverage_pct'] = float(context.get('coverage_pct', 0))
        features['regression_count'] = float(context.get('regression_count', 0))
        features['anomaly_count'] = float(context.get('anomaly_count', 0))
        features['flaky_count'] = float(context.get('flaky_count', 0))
        
        # Historical resolution data (if available)
        features['historical_fix_rate'] = self._get_historical_fix_rate(action_type)
        features['avg_fix_time_hours'] = self._get_avg_fix_time(action_type)
        
        # Regression-specific features
        if action_type == 'regression':
            drop_pct = float(action.get('drop_percentage', 0))
            features['regression_magnitude'] = drop_pct
            features['regression_critical'] = 1.0 if drop_pct >= 20 else 0.0
        else:
            features['regression_magnitude'] = 0.0
            features['regression_critical'] = 0.0
        
        # Gap-specific features
        if action_type == 'gap':
            gap_count = int(action.get('gap_count', 0))
            features['gap_count'] = float(gap_count)
            features['gap_high_priority'] = 1.0 if gap_count > 50 else 0.0
        else:
            features['gap_count'] = 0.0
            features['gap_high_priority'] = 0.0
        
        # Time-based features
        hour_of_day = datetime.now().hour
        features['is_business_hours'] = 1.0 if 8 <= hour_of_day <= 17 else 0.0
        
        # Domain criticality (if available)
        domain = action.get('domain', '')
        critical_domains = self._get_critical_domains()
        features['critical_domain'] = 1.0 if any(d in domain.lower() for d in critical_domains) else 0.0
        
        return features
    
    def _get_historical_fix_rate(self, action_type: str) -> float:
        """Get historical fix rate for action type from feedback log."""
        if not self.feedback_log.exists():
            return 0.5  # Default
        
        try:
            total = 0
            fixed = 0
            with open(self.feedback_log, 'r') as f:
                for line in f:
                    record = json.loads(line)
                    if record.get('action_type') == action_type:
                        total += 1
                        if record.get('was_fixed', False):
                            fixed += 1
            
            return (fixed / total) if total > 0 else 0.5
        except:
            return 0.5
    
    def _get_avg_fix_time(self, action_type: str) -> float:
        """Get average fix time in hours for action type."""
        if not self.feedback_log.exists():
            return 24.0  # Default 24 hours
        
        try:
            times = []
            with open(self.feedback_log, 'r') as f:
                for line in f:
                    record = json.loads(line)
                    if record.get('action_type') == action_type and record.get('fix_time_hours'):
                        times.append(record['fix_time_hours'])
            
            return np.mean(times) if times else 24.0
        except:
            return 24.0
    
    def prioritize_actions(self, actions: List[Dict[str, Any]], 
                          context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Prioritize list of actions using ML or rule-based ranking.
        
        Args:
            actions: List of action dictionaries
            context: Context with overall metrics
            
        Returns:
            Sorted list of actions with priority scores
        """
        if not actions:
            return []
        
        # Try ML-based ranking first
        if self.model is not None and SKLEARN_AVAILABLE:
            try:
                return self._ml_prioritize(actions, context)
            except Exception as e:
                print(f"[WARNING] ML prioritization failed: {e}")
        
        # Fallback to rule-based ranking
        return self._rule_based_prioritize(actions, context)
    
    def _ml_prioritize(self, actions: List[Dict[str, Any]], 
                      context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """ML-based action prioritization."""
        # Extract features for all actions
        X = []
        for action in actions:
            features = self._extract_action_features(action, context)
            X.append(list(features.values()))
            
            if not self.feature_names:
                self.feature_names = list(features.keys())
        
        X = np.array(X)
        
        # Scale features
        if self.scaler:
            X_scaled = self.scaler.transform(X)
        else:
            X_scaled = X
        
        # Predict priority scores (higher = more important)
        scores = self.model.predict(X_scaled)
        
        # Add scores to actions and sort
        for i, action in enumerate(actions):
            action['ml_priority_score'] = float(scores[i])
            action['ml_ranked'] = True
        
        # Sort by score (descending)
        sorted_actions = sorted(actions, key=lambda x: x['ml_priority_score'], reverse=True)
        
        # Assign rank numbers
        for i, action in enumerate(sorted_actions, 1):
            action['priority'] = i
        
        return sorted_actions
    
    def _rule_based_prioritize(self, actions: List[Dict[str, Any]], 
                               context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Rule-based fallback prioritization."""
        # Define priority weights
        type_weights = {
            'regression': 100,
            'flaky': 90,
            'gap': 70,
            'anomaly': 60,
            'workload': 50,
            'platform': 40
        }
        
        severity_weights = {
            'critical': 40,
            'high': 30,
            'medium': 20,
            'low': 10,
            'info': 5
        }
        
        # Calculate scores
        for action in actions:
            action_type = action.get('type', 'unknown')
            severity = action.get('severity', 'medium')
            
            score = type_weights.get(action_type, 50)
            score += severity_weights.get(severity, 20)
            
            # Regression magnitude boost
            if action_type == 'regression':
                drop_pct = float(action.get('drop_percentage', 0))
                score += drop_pct  # Up to +100 for complete drops
            
            # Gap count boost
            if action_type == 'gap':
                gap_count = int(action.get('gap_count', 0))
                score += min(gap_count / 10, 20)  # Up to +20
            
            action['ml_priority_score'] = float(score)
            action['ml_ranked'] = False  # Rule-based
        
        # Sort by score (descending)
        sorted_actions = sorted(actions, key=lambda x: x['ml_priority_score'], reverse=True)
        
        # Assign rank numbers
        for i, action in enumerate(sorted_actions, 1):
            action['priority'] = i
        
        return sorted_actions
    
    def log_feedback(self, action_type: str, was_fixed: bool, 
                    fix_time_hours: float = None):
        """
        Log user feedback on action resolution.
        
        Args:
            action_type: Type of action that was addressed
            was_fixed: Whether the action was successfully resolved
            fix_time_hours: Time taken to fix (optional)
        """
        feedback = {
            'timestamp': datetime.now().isoformat(),
            'action_type': action_type,
            'was_fixed': was_fixed,
            'fix_time_hours': fix_time_hours
        }
        
        try:
            with open(self.feedback_log, 'a') as f:
                f.write(json.dumps(feedback) + '\n')
        except Exception as e:
            print(f"[WARNING] Could not log feedback: {e}")
    
    def train_from_history(self, historical_runs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Train ML model from historical action outcomes.
        
        Args:
            historical_runs: List of {actions, outcomes} dicts
            
        Returns:
            Training metrics
        """
        if not SKLEARN_AVAILABLE:
            return {'status': 'error', 'message': 'scikit-learn not available'}
        
        # Load feedback log
        if not self.feedback_log.exists():
            return {'status': 'no_feedback',
                   'message': 'No user feedback logged yet. Use log_feedback() to provide training data.'}
        
        # Parse feedback log
        feedback_data = []
        try:
            with open(self.feedback_log, 'r') as f:
                for line in f:
                    feedback_data.append(json.loads(line))
        except Exception as e:
            return {'status': 'error', 'message': f'Could not read feedback log: {e}'}
        
        if len(feedback_data) < 10:
            return {'status': 'insufficient_feedback',
                   'message': f'Need at least 10 feedback samples (have {len(feedback_data)})'}
        
        # Build training data
        X = []
        y = []
        
        for run in historical_runs:
            actions = run.get('actions', [])
            context = run.get('context', {})
            outcomes = run.get('outcomes', {})
            
            for action in actions:
                features = self._extract_action_features(action, context)
                X.append(list(features.values()))
                
                # Priority score based on outcome
                action_id = action.get('id', '')
                outcome = outcomes.get(action_id, {})
                
                # Higher score if fixed quickly
                if outcome.get('was_fixed'):
                    fix_time = outcome.get('fix_time_hours', 24)
                    # Score: 100 if fixed in 1 hour, down to 50 if fixed in 48+ hours
                    priority_score = max(100 - (fix_time - 1) * 2, 50)
                else:
                    priority_score = 25  # Low priority if not fixed
                
                y.append(priority_score)
                
                if not self.feature_names:
                    self.feature_names = list(features.keys())
        
        if len(X) < 10:
            return {'status': 'insufficient_samples',
                   'message': f'Need at least 10 action samples (have {len(X)})'}
        
        X = np.array(X)
        y = np.array(y)
        
        # Scale features
        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X)
        
        # Train RandomForest regressor (Learning-to-Rank)
        self.model = RandomForestRegressor(
            n_estimators=100,
            max_depth=8,
            min_samples_split=5,
            random_state=42
        )
        
        self.model.fit(X_scaled, y)
        
        # Calculate training R²
        train_score = self.model.score(X_scaled, y)
        
        # Save model
        self._save_model()
        
        return {
            'status': 'success',
            'model_type': 'RandomForestRegressor (Learning-to-Rank)',
            'training_samples': len(X),
            'r2_score': float(train_score),
            'feature_count': len(self.feature_names),
            'timestamp': datetime.now().isoformat()
        }
    
    def _save_model(self):
        """Save trained model to disk."""
        try:
            with open(self.models_dir / "action_ranker.pkl", 'wb') as f:
                pickle.dump(self.model, f)
            with open(self.models_dir / "action_scaler.pkl", 'wb') as f:
                pickle.dump(self.scaler, f)
            # Save feature names for feature importance retrieval
            with open(self.models_dir / "action_features.pkl", 'wb') as f:
                pickle.dump(self.feature_names, f)
            
            print(f"[ML] Saved action prioritizer model to {self.models_dir}")
        except Exception as e:
            print(f"[WARNING] Could not save action prioritizer: {e}")
    
    def is_trained(self) -> bool:
        """Check if ML model is trained and ready."""
        return self.model is not None and SKLEARN_AVAILABLE
    
    def get_feature_importance(self) -> Dict[str, float]:
        """Get feature importance scores from trained model."""
        if not self.is_trained():
            return {}
        
        try:
            importances = self.model.feature_importances_
            if len(self.feature_names) == len(importances):
                return dict(zip(self.feature_names, importances))
        except:
            pass
        
        return {}
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get information about loaded model."""
        if self.model is None:
            return {
                'status': 'not_trained',
                'method': 'rule-based ranking',
                'model_exists': False
            }
        
        return {
            'status': 'trained',
            'method': 'ML-based (Learning-to-Rank)',
            'model_exists': True,
            'model_path': str(self.models_dir / "action_ranker.pkl"),
            'feature_count': len(self.feature_names)
        }
    
    def _get_critical_domains(self) -> List[str]:
        """Load critical domain list from config."""
        config_path = self.models_dir.parent.parent.parent / 'config' / 'domain_config.yaml'
        try:
            with open(config_path, 'r') as f:
                domain_config = yaml.safe_load(f)
                return domain_config.get('critical_domains', ['p-core', 'e-core', 'imc', 'memory'])
        except Exception:
            return ['p-core', 'e-core', 'imc', 'memory']  # Default fallback
    
    def train_from_patterns(self, product_id: str) -> Dict[str, Any]:
        """
        AUTONOMOUS TRAINING MODE - Learn from historical patterns without explicit feedback.
        
        Analyzes consecutive runs to infer action effectiveness:
        - If flaky events decreased after "Investigate Flaky Events" -> High priority
        - If coverage gaps closed after "Close Critical Gaps" -> High priority
        - If anomalies reduced after specific actions -> Medium priority
        
        This allows ML training even without user feedback logs.
        
        Args:
            product_id: Product identifier to find historical runs
            
        Returns:
            Training metrics
        """
        if not SKLEARN_AVAILABLE:
            return {'status': 'error', 'message': 'scikit-learn not available'}
        
        # Load historical runs
        data_dir = self.data_dir / "raw_datasets" / product_id
        if not data_dir.exists():
            return {'status': 'no_data', 'message': f'No historical data found for {product_id}'}
        
        coverage_files = sorted(data_dir.glob('coverage_*.json'))
        if len(coverage_files) < 5:
            return {'status': 'insufficient_data', 
                   'message': f'Need at least 5 runs for pattern analysis (have {len(coverage_files)})'}
        
        # Analyze consecutive run pairs to infer action outcomes
        X = []
        y = []
        
        for i in range(len(coverage_files) - 1):
            try:
                # Load run N and run N+1
                with open(coverage_files[i]) as f:
                    run_n = json.load(f)
                with open(coverage_files[i+1]) as f:
                    run_n1 = json.load(f)
                
                # Extract metrics from both runs
                flaky_n = len(run_n.get('anomalies', {}).get('flaky_events', []))
                flaky_n1 = len(run_n1.get('anomalies', {}).get('flaky_events', []))
                
                gaps_n = len(run_n.get('gaps', {}).get('critical_gaps', []))
                gaps_n1 = len(run_n1.get('gaps', {}).get('critical_gaps', []))
                
                coverage_n = run_n.get('summary', {}).get('overall_coverage_percentage', 0)
                coverage_n1 = run_n1.get('summary', {}).get('overall_coverage_percentage', 0)
                
                # Simulate actions that were "implicitly taken"
                actions_with_outcomes = []
                
                # Action 1: Investigate Flaky Events (always add as baseline)
                improvement = max(0, (flaky_n - flaky_n1) / max(1, flaky_n))
                actions_with_outcomes.append({
                    'type': 'flaky',
                    'severity': 'high' if flaky_n > 100 else 'medium',
                    'context': {'flaky_count': max(1, flaky_n), 'total_events': run_n.get('summary', {}).get('total_events_tested', 1000)},
                    'outcome_score': improvement * 100 + 30  # Base score 30, up to 130
                })
                
                # Action 2: Close Critical Gaps (always add as baseline)
                improvement = max(0, (gaps_n - gaps_n1) / max(1, gaps_n))
                actions_with_outcomes.append({
                    'type': 'gap',
                    'severity': 'critical' if gaps_n > 50 else 'high',
                    'context': {'gap_count': max(1, gaps_n), 'coverage': coverage_n},
                    'outcome_score': improvement * 100 + 40  # Base score 40, up to 140
                })
                
                # Action 3: Coverage Improvement (always add as baseline)
                coverage_gain = coverage_n1 - coverage_n
                actions_with_outcomes.append({
                    'type': 'workload',
                    'severity': 'medium',
                    'context': {'coverage': coverage_n, 'gap_count': gaps_n},
                    'outcome_score': max(20, min(100, coverage_gain * 10 + 50))  # Scale 20-100
                })
                
                # Extract features and scores
                for action_data in actions_with_outcomes:
                    features = self._extract_action_features(
                        action_data, 
                        action_data.get('context', {})
                    )
                    # Store feature names from first extraction
                    if not self.feature_names:
                        self.feature_names = list(features.keys())
                    
                    X.append(list(features.values()))
                    y.append(action_data['outcome_score'])
                
            except Exception as e:
                print(f"[DEBUG] Skipping run pair due to error: {e}")
                continue
        
        if len(X) < 3:
            return {'status': 'insufficient_patterns',
                   'message': f'Need at least 3 run pairs for pattern analysis (have {len(X)} samples from {len(coverage_files)} runs)'}
        
        # Train model
        X = np.array(X)
        y = np.array(y)
        
        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X)
        
        self.model = RandomForestRegressor(
            n_estimators=100,
            max_depth=10,
            min_samples_split=5,
            random_state=42
        )
        
        self.model.fit(X_scaled, y)
        
        # Calculate training R²
        train_score = self.model.score(X_scaled, y)
        
        # Save model
        self._save_model()
        
        return {
            'status': 'success',
            'mode': 'autonomous_pattern_analysis',
            'model_type': 'RandomForestRegressor (Pattern-Based Learning)',
            'training_samples': len(X),
            'r2_score': float(train_score),
            'feature_count': len(self.feature_names),
            'message': 'Trained from historical improvement patterns (no explicit feedback needed)',
            'timestamp': datetime.now().isoformat()
        }
