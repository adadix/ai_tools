#!/usr/bin/env python3
"""
ML-Based Stress Test Recommender

Recommends which stress test to run next based on historical effectiveness
at closing coverage gaps. Uses collaborative filtering + RandomForest to
predict which stress test will provide maximum coverage improvement.

Features:
- Learns from historical stress->gap closure patterns
- Predicts expected coverage gain per stress test
- Ranks stress tests by effectiveness
- Considers current gap profile and domain weaknesses

Author: Intel Corporation
Date: December 2025
"""

import json
import pickle
import yaml
from pathlib import Path
from typing import Dict, List, Tuple, Any
from datetime import datetime
from collections import defaultdict, Counter

try:
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.preprocessing import StandardScaler
    import numpy as np
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    print("[WARNING] scikit-learn not available. Stress recommender will use rule-based fallback.")


class MLStressRecommender:
    """ML-based stress test recommender with collaborative filtering."""
    
    def __init__(self, data_dir: str = "C:\\silicon_coverage_analyzer_data"):
        """Initialize stress test recommender."""
        self.data_dir = Path(data_dir)
        self.models_dir = self.data_dir / "models" / "stress_recommender"
        self.models_dir.mkdir(parents=True, exist_ok=True)
        
        self.model = None
        self.scaler = None
        self.stress_test_encoder = {}
        self.domain_encoder = {}
        
        # Load stress profiles from config
        self.stress_profiles = self._load_stress_profiles()
        if not self.stress_profiles:
            # Fallback defaults - try to load from domain categories
            self.stress_profiles = self._load_default_stress_profiles()
        
        # Load trained model if exists
        self._load_model()
    
    def _load_default_stress_profiles(self):
        """Load default stress profiles using domain categories from config."""
        try:
            config_path = Path(__file__).parent.parent / 'config' / 'domain_config.yaml'
            with open(config_path) as f:
                config = yaml.safe_load(f)
            
            # Get core and memory domains from categories
            core_domains = config.get('domain_categories', {}).get('cpu_cores', {}).get('members', ['p-core', 'e-core'])
            memory_domains = config.get('domain_categories', {}).get('memory_subsystem', {}).get('members', ['uncore', 'memory', 'imc'])
            
            return {
                'prime95': {'domains': core_domains, 'type': 'compute', 'intensity': 'high'},
                'memtester': {'domains': memory_domains, 'type': 'memory', 'intensity': 'high'},
                'idle': {'domains': ['system'], 'type': 'baseline', 'intensity': 'low'},
                'unknown': {'domains': core_domains[:1] if core_domains else ['p-core'], 'type': 'mixed', 'intensity': 'medium'}
            }
        except Exception as e:
            self.logger.warning(f"Could not load domain categories from config: {e}")
            # Ultimate fallback
            return {
                'prime95': {'domains': ['p-core', 'e-core'], 'type': 'compute', 'intensity': 'high'},
                'memtester': {'domains': ['uncore', 'memory'], 'type': 'memory', 'intensity': 'high'},
                'idle': {'domains': ['system'], 'type': 'baseline', 'intensity': 'low'},
                'unknown': {'domains': ['p-core'], 'type': 'mixed', 'intensity': 'medium'}
            }
    
    def _load_stress_profiles(self):
        """Load stress tool domain mappings from config."""
        config_path = self.models_dir.parent / 'config' / 'domain_config.yaml'
        try:
            with open(config_path, 'r') as f:
                domain_config = yaml.safe_load(f)
                return domain_config.get('stress_tool_domains', {})
        except Exception as e:
            return None
    
    def _load_model(self):
        """Load trained model from disk."""
        model_path = self.models_dir / "stress_recommender.pkl"
        scaler_path = self.models_dir / "stress_scaler.pkl"
        encoder_path = self.models_dir / "stress_encoders.pkl"
        
        if model_path.exists() and scaler_path.exists() and encoder_path.exists():
            try:
                with open(model_path, 'rb') as f:
                    self.model = pickle.load(f)
                with open(scaler_path, 'rb') as f:
                    self.scaler = pickle.load(f)
                with open(encoder_path, 'rb') as f:
                    encoders = pickle.load(f)
                    self.stress_test_encoder = encoders['stress_tests']
                    self.domain_encoder = encoders['domains']
                
                print(f"[ML] Loaded stress recommender model from {model_path}")
                return True
            except Exception as e:
                print(f"[WARNING] Could not load stress recommender: {e}")
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
            'algorithm': 'RandomForest Regressor',
            'stress_tests_known': len(self.stress_test_encoder),
            'domains_tracked': len(self.domain_encoder)
        }
    
    def recommend_stress_tests(self, current_gaps: List[Dict], 
                               current_workload: str = 'unknown',
                               top_n: int = 5) -> List[Dict[str, Any]]:
        """
        Recommend stress tests based on current gaps.
        Uses learned stress tests from training history, not hardcoded generic tools.
        
        Args:
            current_gaps: List of gap events with domains
            current_workload: Current workload type
            top_n: Number of recommendations to return
            
        Returns:
            List of stress test recommendations with expected coverage gain
        """
        if not SKLEARN_AVAILABLE or not self.model:
            return self._rule_based_recommendations(current_gaps, current_workload, top_n)
        
        # Extract gap features
        gap_features = self._extract_gap_features(current_gaps)
        
        # Non-stress workloads that should never be recommended as stress tests
        non_stress_workloads = {'idle', 'unknown', 'baseline', 'none', 'no_workload', 'no workload'}
        
        # Score each stress test - USE LEARNED STRESS TESTS from encoder, not hardcoded profiles
        recommendations = []
        for stress_test in self.stress_test_encoder.keys():
            if stress_test == current_workload:
                continue  # Skip current workload
            
            # Skip non-stress workloads - they should never be recommended as stress tests
            if stress_test.lower() in non_stress_workloads:
                continue
            
            # Extract features for this stress test
            features = self._extract_stress_features(stress_test, gap_features)
            
            # Predict coverage gain
            X = np.array([list(features.values())])
            X_scaled = self.scaler.transform(X)
            predicted_gain = self.model.predict(X_scaled)[0]
            
            # Get profile (learned from history or fallback to generic if new tool)
            profile = self._get_stress_profile(stress_test)
            
            # Calculate confidence based on historical data
            confidence = self._calculate_confidence(stress_test, gap_features)
            
            recommendations.append({
                'stress_test': stress_test,
                'expected_coverage_gain': max(0, predicted_gain),
                'confidence': confidence,
                'primary_domains': profile['domains'],
                'stress_type': profile['type'],
                'intensity': profile['intensity'],
                'reason': self._generate_recommendation_reason(stress_test, gap_features, predicted_gain)
            })
        
        # Sort by expected gain
        recommendations.sort(key=lambda x: x['expected_coverage_gain'], reverse=True)
        
        return recommendations[:top_n]
    
    def _get_stress_profile(self, stress_test: str) -> Dict[str, Any]:
        """
        Get stress test profile - either from learned history or inferred from name.
        Uses domain categories from config for future-proof detection.
        """
        # Check if we have this in the loaded profiles (from config)
        if stress_test in self.stress_profiles:
            return self.stress_profiles[stress_test]
        
        # Load domain categories for smart detection
        try:
            config_path = Path(__file__).parent.parent / 'config' / 'domain_config.yaml'
            with open(config_path) as f:
                config = yaml.safe_load(f)
            
            core_domains = config.get('domain_categories', {}).get('cpu_cores', {}).get('members', ['p-core', 'e-core'])
            memory_domains = config.get('domain_categories', {}).get('memory_subsystem', {}).get('members', ['uncore', 'memory', 'imc'])
            cache_domains = config.get('domain_categories', {}).get('cache_coherency', {}).get('members', ['cbo', 'cha'])
            interconnect_domains = config.get('domain_categories', {}).get('interconnect', {}).get('members', ['ncu', 'upi', 'mesh'])
            
        except Exception:
            # Fallback to pattern-based domains if config unavailable
            core_domains = ['p-core', 'e-core']
            memory_domains = ['uncore', 'memory', 'imc']
            cache_domains = ['cbo', 'cha']
            interconnect_domains = ['ncu', 'upi', 'mesh']
        
        # Infer from stress test name using domain categories
        stress_lower = stress_test.lower()
        
        # Intel validation tools (learned from detection)
        if any(keyword in stress_lower for keyword in ['memical', 'memrunner', 'mlc', 'stream']):
            return {'domains': memory_domains, 'type': 'memory', 'intensity': 'high'}
        elif any(keyword in stress_lower for keyword in ['sandstone', 'supercollider', 'dynamo']):
            return {'domains': core_domains + ['uncore'], 'type': 'mixed', 'intensity': 'high'}
        elif any(keyword in stress_lower for keyword in ['buslocker']):
            return {'domains': ['uncore'] + memory_domains[:2] + cache_domains, 'type': 'interconnect', 'intensity': 'high'}
        elif any(keyword in stress_lower for keyword in ['glaze', 'burnintest', 'burnin']):
            return {'domains': core_domains + memory_domains, 'type': 'mixed', 'intensity': 'high'}
        
        # Generic fallback based on name patterns
        elif 'mem' in stress_lower or 'ram' in stress_lower:
            return {'domains': memory_domains, 'type': 'memory', 'intensity': 'medium'}
        elif 'cpu' in stress_lower or 'core' in stress_lower or 'prime' in stress_lower:
            return {'domains': core_domains, 'type': 'compute', 'intensity': 'high'}
        elif 'io' in stress_lower or 'disk' in stress_lower or 'fio' in stress_lower:
            return {'domains': ['uncore'], 'type': 'io', 'intensity': 'medium'}
        else:
            # Unknown - assume mixed workload with first core domain + uncore
            return {'domains': [core_domains[0] if core_domains else 'p-core', 'uncore'], 'type': 'mixed', 'intensity': 'medium'}
    
    def _extract_gap_features(self, gaps: List[Dict]) -> Dict[str, Any]:
        """Extract features from current gaps."""
        features = {
            'total_gaps': len(gaps),
            'domain_gaps': defaultdict(int),
            'event_patterns': defaultdict(int)
        }
        
        for gap in gaps:
            domain = gap.get('domain', 'unknown').lower()  # Normalize to lowercase
            event_name = gap.get('event', gap.get('event_name', ''))
            
            features['domain_gaps'][domain] += 1
            
            # Event pattern detection
            if 'MEM_' in event_name or 'LOAD' in event_name or 'STORE' in event_name:
                features['event_patterns']['memory'] += 1
            elif 'FP_' in event_name or 'ARITH' in event_name or 'DIV' in event_name:
                features['event_patterns']['compute'] += 1
            elif 'BR_' in event_name or 'BRANCH' in event_name:
                features['event_patterns']['branch'] += 1
            elif 'L1D' in event_name or 'L2_' in event_name or 'L3_' in event_name:
                features['event_patterns']['cache'] += 1
        
        return features
    
    def _extract_stress_features(self, stress_test: str, gap_features: Dict) -> Dict[str, float]:
        """Extract ML features for stress test prediction."""
        profile = self._get_stress_profile(stress_test)  # Use dynamic profile lookup
        
        features = {
            'total_gaps': gap_features['total_gaps'],
            'stress_test_encoded': self.stress_test_encoder.get(stress_test, 0),
            'intensity_score': {'low': 1, 'medium': 2, 'high': 3, 'extreme': 4}.get(profile['intensity'], 2),
            'is_compute': 1 if profile['type'] in ['compute', 'mixed'] else 0,
            'is_memory': 1 if profile['type'] in ['memory', 'mixed'] else 0,
            'domain_match_score': 0
        }
        
        # Domain match score
        for domain in profile['domains']:
            features['domain_match_score'] += gap_features['domain_gaps'].get(domain, 0)
        
        # Pattern match scores
        if profile['type'] == 'compute':
            features['pattern_match_score'] = gap_features['event_patterns'].get('compute', 0)
        elif profile['type'] == 'memory':
            features['pattern_match_score'] = gap_features['event_patterns'].get('memory', 0)
        else:
            features['pattern_match_score'] = sum(gap_features['event_patterns'].values()) / 2
        
        return features
    
    def _calculate_confidence(self, stress_test: str, gap_features: Dict) -> float:
        """Calculate confidence score for recommendation."""
        # Confidence based on domain alignment
        profile = self._get_stress_profile(stress_test)  # Use dynamic profile lookup
        total_gaps = gap_features['total_gaps']
        
        if total_gaps == 0:
            return 0.5
        
        # Count gaps in target domains
        matching_gaps = sum(gap_features['domain_gaps'].get(d, 0) for d in profile['domains'])
        
        # If no direct domain match, check event patterns
        if matching_gaps == 0:
            pattern_match = gap_features['event_patterns'].get(profile['type'], 0)
            if pattern_match > 0:
                confidence = min(0.7, pattern_match / total_gaps)
            else:
                confidence = 0.3  # Base confidence even without clear match
        else:
            # Confidence = % of gaps in target domains
            confidence = min(1.0, matching_gaps / total_gaps)
        
        return confidence
    
    def _generate_recommendation_reason(self, stress_test: str, gap_features: Dict, predicted_gain: float) -> str:
        """Generate human-readable reason for recommendation."""
        profile = self._get_stress_profile(stress_test)  # Use dynamic profile lookup
        
        # Find dominant gap domain
        domain_gaps = gap_features['domain_gaps']
        if domain_gaps:
            top_domain = max(domain_gaps.items(), key=lambda x: x[1])
            top_domain_name = top_domain[0]
            top_domain_count = top_domain[1]
            
            if top_domain_name in profile['domains']:
                return f"Targets {top_domain_name} domain ({top_domain_count} gaps). Expected to improve coverage by {predicted_gain:.1f}%"
        
        # Find dominant event pattern
        event_patterns = gap_features['event_patterns']
        if event_patterns:
            top_pattern = max(event_patterns.items(), key=lambda x: x[1])
            return f"Matches {top_pattern[0]} event pattern ({top_pattern[1]} events). Expected gain: {predicted_gain:.1f}%"
        
        return f"Expected coverage improvement: {predicted_gain:.1f}%"
    
    def _rule_based_recommendations(self, gaps: List[Dict], current_workload: str, top_n: int) -> List[Dict]:
        """Fallback rule-based recommendations when ML not available."""
        gap_features = self._extract_gap_features(gaps)
        domain_gaps = gap_features['domain_gaps']
        
        # Non-stress workloads that should never be recommended as stress tests
        non_stress_workloads = {'idle', 'unknown', 'baseline', 'none', 'no_workload', 'no workload'}
        
        recommendations = []
        
        # Recommend based on domain gaps
        for stress_test, profile in self.stress_profiles.items():
            # Skip current workload and non-stress workloads
            if stress_test == current_workload:
                continue
            if stress_test.lower() in non_stress_workloads:
                continue
            
            # Calculate score based on domain match
            score = sum(domain_gaps.get(d, 0) for d in profile['domains'])
            
            if score > 0:
                recommendations.append({
                    'stress_test': stress_test,
                    'expected_coverage_gain': min(score * 0.5, 10.0),  # Rough estimate
                    'confidence': 0.6,
                    'primary_domains': profile['domains'],
                    'stress_type': profile['type'],
                    'intensity': profile['intensity'],
                    'reason': f"May help with {', '.join(profile['domains'])} domains ({score} gaps)"
                })
        
        recommendations.sort(key=lambda x: x['expected_coverage_gain'], reverse=True)
        return recommendations[:top_n]
    
    def train_from_history(self, historical_runs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Train ML model from historical stress test effectiveness.
        
        Args:
            historical_runs: List of historical run data with metadata and gaps
            
        Returns:
            Training metrics
        """
        if not SKLEARN_AVAILABLE:
            return {'status': 'error', 'message': 'scikit-learn not available'}
        
        if len(historical_runs) < 5:
            return {'status': 'insufficient_data',
                   'message': f'Need at least 5 runs for training (have {len(historical_runs)})'}
        
        # Build training dataset
        X = []
        y = []
        
        # Build encoders
        stress_tests = set()
        domains = set()
        
        for run in historical_runs:
            metadata = run.get('metadata', {})
            # Prioritize stress_tracking over old workload field
            stress_tracking = metadata.get('stress_tracking', {})
            if stress_tracking and stress_tracking.get('classification'):
                workload = stress_tracking['classification'].get('label', 'unknown')
            else:
                workload = metadata.get('workload', 'unknown')
            stress_tests.add(workload)
            
            gaps = run.get('gaps', {}).get('non_toggling_events', [])
            for gap in gaps:
                domains.add(gap.get('domain', 'unknown'))
        
        # Filter out None values before sorting
        stress_tests = {st for st in stress_tests if st is not None}
        domains = {d for d in domains if d is not None}
        
        self.stress_test_encoder = {st: idx for idx, st in enumerate(sorted(stress_tests))}
        self.domain_encoder = {d: idx for idx, d in enumerate(sorted(domains))}
        
        # Extract features and labels
        for i in range(1, len(historical_runs)):
            prev_run = historical_runs[i-1]
            curr_run = historical_runs[i]
            
            prev_coverage = prev_run.get('coverage_results', prev_run.get('coverage', {}))
            curr_coverage = curr_run.get('coverage_results', curr_run.get('coverage', {}))
            
            prev_pct = prev_coverage.get('activity_coverage', prev_coverage.get('overall_coverage_percentage', 0))
            curr_pct = curr_coverage.get('activity_coverage', curr_coverage.get('overall_coverage_percentage', 0))
            
            # Ensure numeric types
            if prev_pct is None:
                prev_pct = 0
            if curr_pct is None:
                curr_pct = 0
            
            try:
                prev_pct = float(prev_pct)
                curr_pct = float(curr_pct)
            except (ValueError, TypeError):
                continue
            
            coverage_gain = curr_pct - prev_pct
            
            if coverage_gain < -5:  # Skip regressions
                continue
            
            # Extract features - prioritize stress_tracking
            curr_metadata = curr_run.get('metadata', {})
            stress_tracking = curr_metadata.get('stress_tracking', {})
            if stress_tracking and stress_tracking.get('classification'):
                stress_test = stress_tracking['classification'].get('label', 'unknown')
            else:
                stress_test = curr_metadata.get('workload', 'unknown')
            if stress_test is None:
                stress_test = 'unknown'
            
            prev_gaps = prev_run.get('gaps', {}).get('non_toggling_events', [])
            if prev_gaps is None:
                prev_gaps = []
            
            gap_features = self._extract_gap_features(prev_gaps)
            features = self._extract_stress_features(stress_test, gap_features)
            
            X.append(list(features.values()))
            y.append(coverage_gain)
        
        if len(X) < 5:
            return {'status': 'insufficient_samples',
                   'message': f'Need at least 5 training samples (have {len(X)})'}
        
        X = np.array(X)
        y = np.array(y)
        
        # Scale features
        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X)
        
        # Train model
        self.model = RandomForestRegressor(
            n_estimators=100,
            max_depth=10,
            min_samples_split=5,
            random_state=42
        )
        self.model.fit(X_scaled, y)
        
        # Calculate metrics
        train_score = self.model.score(X_scaled, y)
        predictions = self.model.predict(X_scaled)
        mae = np.mean(np.abs(predictions - y))
        
        # Save model
        self._save_model()
        
        print(f"[ML] Stress recommender trained - R²: {train_score:.3f}, MAE: {mae:.2f}%")
        
        return {
            'status': 'success',
            'model': 'RandomForest',
            'training_samples': len(X),
            'r2_score': float(train_score),
            'mae': float(mae),
            'stress_tests_learned': len(self.stress_test_encoder)
        }
    
    def _save_model(self):
        """Save trained model to disk."""
        try:
            with open(self.models_dir / "stress_recommender.pkl", 'wb') as f:
                pickle.dump(self.model, f)
            with open(self.models_dir / "stress_scaler.pkl", 'wb') as f:
                pickle.dump(self.scaler, f)
            with open(self.models_dir / "stress_encoders.pkl", 'wb') as f:
                pickle.dump({
                    'stress_tests': self.stress_test_encoder,
                    'domains': self.domain_encoder
                }, f)
        except Exception as e:
            print(f"[WARNING] Could not save stress recommender: {e}")
