#!/usr/bin/env python3
"""
ML-Based Workload Detector

Replaces fragile pattern matching with learned workload classification from event activity fingerprints.
Uses GradientBoosting Classifier trained on:
- Top active event patterns
- Domain activity distribution
- Event count statistics
- Historical workload labels

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

from .config_utils import get_ml_domains, get_uncore_domains

try:
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.preprocessing import StandardScaler
    import numpy as np
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    print("[WARNING] scikit-learn not available. Workload detection will use rule-based fallback.")


class MLWorkloadDetector:
    """ML-based workload classifier with rule-based fallback."""
    
    WORKLOAD_TYPES = ['cpu_stress', 'memory_stress', 'mixed_stress', 'idle', 'unknown']
    
    def __init__(self, data_dir: str = "C:\\silicon_coverage_analyzer_data"):
        """Initialize workload detector."""
        self.data_dir = Path(data_dir)
        self.models_dir = self.data_dir / "models" / "workload_detector"
        self.models_dir.mkdir(parents=True, exist_ok=True)
        
        self.model = None
        self.scaler = None
        self.feature_names = []
        
        # Load trained model if exists
        self._load_model()
    
    def _load_model(self):
        """Load trained model from disk."""
        model_path = self.models_dir / "workload_classifier.pkl"
        scaler_path = self.models_dir / "feature_scaler.pkl"
        
        if model_path.exists() and scaler_path.exists():
            try:
                with open(model_path, 'rb') as f:
                    self.model = pickle.load(f)
                with open(scaler_path, 'rb') as f:
                    self.scaler = pickle.load(f)
                
                print(f"[ML] Loaded workload detection model from {model_path}")
                return True
            except Exception as e:
                print(f"[WARNING] Could not load workload model: {e}")
                self.model = None
        return False
    
    def _extract_workload_features(self, coverage_results: Dict[str, Any]) -> Dict[str, float]:
        """Extract ML features from coverage results."""
        features = {}
        
        # Get domain results
        domain_results = coverage_results.get('domain_results', {})
        
        # Overall metrics
        total_active = sum(len(d.get('active_events', [])) for d in domain_results.values())
        total_tested = sum(d.get('total_tested', 0) for d in domain_results.values())
        features['overall_coverage'] = (total_active / total_tested * 100) if total_tested > 0 else 0
        
        # Load domain list from config or use defaults
        domain_list = self._get_ml_domains('workload_detector')
        
        # Domain-specific activity rates
        for domain_name in domain_list:
            if domain_name in domain_results:
                activity_rate = domain_results[domain_name].get('activity_rate', 0)
                features[f'{domain_name}_activity'] = activity_rate
            else:
                features[f'{domain_name}_activity'] = 0
        
        # Event pattern analysis - top active events
        all_active_events = []
        for domain_data in domain_results.values():
            all_active_events.extend([e['event'] for e in domain_data.get('active_events', [])])
        
        event_counter = Counter([e.upper() for e in all_active_events])
        top_20 = [name for name, count in event_counter.most_common(20)]
        
        # CPU stress indicators
        cpu_patterns = ['INST_RETIRED', 'UOPS_EXECUTED', 'UOPS_RETIRED', 'CPU_CLK_UNHALTED', 'CYCLES']
        features['cpu_stress_score'] = sum(1 for p in cpu_patterns if any(p in e for e in top_20)) / len(cpu_patterns)
        
        # Memory stress indicators  
        mem_patterns = ['MEM_LOAD', 'MEM_STORE', 'L3_', 'LLC', 'OFFCORE', 'MEM_TRANS']
        features['memory_stress_score'] = sum(1 for p in mem_patterns if any(p in e for e in top_20)) / len(mem_patterns)
        
        # Branch/control flow indicators
        branch_patterns = ['BR_INST', 'BR_MISP', 'BRANCH']
        features['branch_score'] = sum(1 for p in branch_patterns if any(p in e for e in top_20)) / len(branch_patterns)
        
        # FP/SIMD indicators
        fp_patterns = ['FP_', 'AVX', 'SSE', 'SIMD', 'ARITH']
        features['fp_score'] = sum(1 for p in fp_patterns if any(p in e for e in top_20)) / len(fp_patterns)
        
        # Uncore activity (indicates memory bandwidth stress)
        uncore_domains = self._get_uncore_domains()
        uncore_activity = sum(domain_results.get(d, {}).get('activity_rate', 0) for d in uncore_domains)
        features['uncore_activity'] = uncore_activity / len(uncore_domains)
        
        # Core balance (P vs E core activity)
        p_core_activity = domain_results.get('p-core', {}).get('activity_rate', 0)
        e_core_activity = domain_results.get('e-core', {}).get('activity_rate', 0)
        if p_core_activity + e_core_activity > 0:
            features['core_balance'] = abs(p_core_activity - e_core_activity) / (p_core_activity + e_core_activity)
        else:
            features['core_balance'] = 0
        
        # Event diversity (high = mixed workload)
        features['event_diversity'] = len(event_counter) / max(sum(event_counter.values()), 1)
        
        return features
    
    def detect_workload(self, coverage_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Detect active workload type using ML or rule-based fallback.
        
        Args:
            coverage_results: Coverage analysis results with domain data
            
        Returns:
            Dict with 'workload', 'confidence', 'method', 'description'
        """
        # Try ML-based detection first
        if self.model is not None and SKLEARN_AVAILABLE:
            try:
                return self._ml_detect(coverage_results)
            except Exception as e:
                print(f"[WARNING] ML workload detection failed: {e}")
        
        # Fallback to rule-based detection
        return self._rule_based_detect(coverage_results)
    
    def _ml_detect(self, coverage_results: Dict[str, Any]) -> Dict[str, Any]:
        """ML-based workload detection."""
        features = self._extract_workload_features(coverage_results)
        feature_array = np.array([list(features.values())]).reshape(1, -1)
        
        # Scale features
        if self.scaler:
            feature_array = self.scaler.transform(feature_array)
        
        # Predict
        prediction = self.model.predict(feature_array)[0]
        probabilities = self.model.predict_proba(feature_array)[0]
        confidence = float(max(probabilities)) * 100
        
        # Generate description
        descriptions = {
            'cpu_stress': 'Heavy CPU computation stress (Prime95, SuperCollider)',
            'memory_stress': 'Memory bandwidth stress (Stream, MLCC)',
            'mixed_stress': 'Mixed CPU+Memory stress workload',
            'idle': 'System idle or minimal activity',
            'unknown': 'Unrecognized workload pattern'
        }
        
        return {
            'workload': prediction,
            'confidence': confidence,
            'method': 'ml',
            'description': descriptions.get(prediction, 'Unknown workload')
        }
    
    def _rule_based_detect(self, coverage_results: Dict[str, Any]) -> Dict[str, Any]:
        """Rule-based fallback workload detection."""
        features = self._extract_workload_features(coverage_results)
        
        cpu_score = features.get('cpu_stress_score', 0)
        mem_score = features.get('memory_stress_score', 0)
        uncore_activity = features.get('uncore_activity', 0)
        overall_coverage = features.get('overall_coverage', 0)
        
        # Decision tree logic
        if overall_coverage < 10:
            return {
                'workload': 'idle',
                'confidence': 60.0,
                'method': 'rules',
                'description': 'Very low activity - system appears idle'
            }
        
        if cpu_score > 0.6 and mem_score < 0.3:
            confidence = min(cpu_score * 100, 90)
            return {
                'workload': 'cpu_stress',
                'confidence': confidence,
                'method': 'rules',
                'description': 'CPU-intensive workload detected (high instruction/uop activity)'
            }
        
        if mem_score > 0.5 or uncore_activity > 40:
            confidence = min(max(mem_score, uncore_activity / 50) * 100, 90)
            return {
                'workload': 'memory_stress',
                'confidence': confidence,
                'method': 'rules',
                'description': 'Memory-intensive workload detected (high cache/memory activity)'
            }
        
        if cpu_score > 0.4 and mem_score > 0.3:
            confidence = min((cpu_score + mem_score) * 50, 85)
            return {
                'workload': 'mixed_stress',
                'confidence': confidence,
                'method': 'rules',
                'description': 'Mixed CPU+Memory stress workload'
            }
        
        return {
            'workload': 'unknown',
            'confidence': 50.0,
            'method': 'rules',
            'description': 'Workload pattern not recognized'
        }
    
    def _get_ml_domains(self, model_name: str) -> List[str]:
        """Load domain list from config for specific ML model."""
        return get_ml_domains(model_name, ['p-core', 'e-core', 'uncore', 'imc', 'cbo'])
    
    def _get_uncore_domains(self) -> List[str]:
        """Load uncore domain list from config."""
        return get_uncore_domains(['imc', 'cbo', 'cha', 'm2m', 'uncore'])
    
    def train_from_history(self, historical_runs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Train ML model from historical coverage runs with workload labels.
        
        Args:
            historical_runs: List of {coverage_results, workload_label} dicts
            
        Returns:
            Training metrics
        """
        if not SKLEARN_AVAILABLE:
            return {'status': 'error', 'message': 'scikit-learn not available'}
        
        if len(historical_runs) < 5:
            return {'status': 'insufficient_data',
                   'message': f'Need at least 5 runs for training (have {len(historical_runs)})'}
        
        # Extract features and labels
        X = []
        y = []
        
        for run in historical_runs:
            coverage_results = run.get('coverage_results', run.get('coverage', {}))
            metadata = run.get('metadata', {})
            
            # ENHANCED: Prioritize stress_tracking label over old workload field
            stress_tracking = metadata.get('stress_tracking', {})
            if stress_tracking and stress_tracking.get('classification'):
                # Use accurate stress tracking classification
                workload_label = stress_tracking['classification'].get('label', 'unknown').lower()
                collection_type = stress_tracking['classification'].get('type', 'unknown')
                
                # Map stress tracking labels to workload types
                if collection_type == 'idle':
                    workload_label = 'idle'
                elif any(tool in workload_label for tool in ['prime95', 'supercollider', 'linpack', 'stressapptest']):
                    workload_label = 'cpu_stress'
                elif any(tool in workload_label for tool in ['memicals', 'mlc', 'stream', 'bandwidth']):
                    workload_label = 'memory_stress'
                elif collection_type in ['mixed_workload', 'power_cycling']:
                    workload_label = 'mixed_stress'
                else:
                    workload_label = 'unknown'
            else:
                # Fallback to old workload field
                workload_label = metadata.get('workload', 'unknown').lower()
                
                # Map old labels to standard types
                if 'cpu' in workload_label or 'prime95' in workload_label or 'supercollider' in workload_label:
                    workload_label = 'cpu_stress'
                elif 'memory' in workload_label or 'mem' in workload_label:
                    workload_label = 'memory_stress'
                elif 'mixed' in workload_label:
                    workload_label = 'mixed_stress'
                elif 'idle' in workload_label or 'baseline' in workload_label:
                    workload_label = 'idle'
                else:
                    workload_label = 'unknown'
            
            if workload_label not in self.WORKLOAD_TYPES:
                workload_label = 'unknown'
            
            features = self._extract_workload_features(coverage_results)
            X.append(list(features.values()))
            y.append(workload_label)
            
            if not self.feature_names:
                self.feature_names = list(features.keys())
        
        X = np.array(X)
        
        # Check for class diversity (need at least 2 different workload types)
        unique_classes = set(y)
        if len(unique_classes) < 2:
            return {'status': 'insufficient_diversity',
                   'message': f'Need at least 2 different workload types (have {len(unique_classes)})'}
        
        if len(X) < 5:
            return {'status': 'insufficient_samples',
                   'message': f'Need at least 5 samples (have {len(X)})'}
        
        # Scale features
        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X)
        
        # Train GradientBoosting classifier
        self.model = GradientBoostingClassifier(
            n_estimators=100,
            learning_rate=0.1,
            max_depth=4,
            random_state=42
        )
        
        self.model.fit(X_scaled, y)
        
        # Calculate training accuracy
        train_score = self.model.score(X_scaled, y)
        
        # Save model
        self._save_model()
        
        return {
            'status': 'success',
            'model_type': 'GradientBoostingClassifier',
            'training_samples': len(X),
            'training_accuracy': float(train_score),
            'feature_count': len(self.feature_names),
            'timestamp': datetime.now().isoformat()
        }
    
    def _save_model(self):
        """Save trained model to disk."""
        try:
            with open(self.models_dir / "workload_classifier.pkl", 'wb') as f:
                pickle.dump(self.model, f)
            with open(self.models_dir / "feature_scaler.pkl", 'wb') as f:
                pickle.dump(self.scaler, f)
            
            print(f"[ML] Saved workload detection model to {self.models_dir}")
        except Exception as e:
            print(f"[WARNING] Could not save workload model: {e}")
    
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
                'method': 'rule-based fallback',
                'model_exists': False
            }
        
        return {
            'status': 'trained',
            'method': 'ML-based (GradientBoosting)',
            'model_exists': True,
            'model_path': str(self.models_dir / "workload_classifier.pkl"),
            'feature_count': len(self.feature_names)
        }
