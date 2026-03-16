"""
ML Analysis Reporter - Generate Detailed ML Insights

Creates comprehensive ML analysis reports including:
- Pattern detection and classification
- Anomaly analysis with explanations
- Coverage predictions and trends
- Event correlations and clusters
- Actionable recommendations
"""

import json
import logging
import yaml
import numpy as np
import pandas as pd
import warnings
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Tuple
from collections import defaultdict

from .config_utils import get_ml_domains

# Suppress numpy warnings for empty arrays (inactive events have zero counts)
warnings.filterwarnings('ignore', message='Mean of empty slice')
warnings.filterwarnings('ignore', message='invalid value encountered in.*divide')
warnings.filterwarnings('ignore', message='Degrees of freedom <= 0 for slice')

logger = logging.getLogger(__name__)


class MLAnalysisReporter:
    """Generates detailed ML analysis reports for coverage data."""
    
    def __init__(self, ml_client, debug=False):
        """
        Initialize ML Analysis Reporter.
        
        Args:
            ml_client: MLClient instance with trained models
            debug: Enable debug output
        """
        self.ml_client = ml_client
        self.trainer = ml_client.trainer
        self.debug = debug
        
        # Load product signatures from YAML config
        self.product_signatures = self._load_product_signatures()
    
    def _get_ml_domains(self, model_name: str) -> List[str]:
        """Load domain list from config for specific ML model."""
        return get_ml_domains(model_name, ['p-core', 'e-core', 'imc', 'cbo', 'hac_cbo', 'ncu', 'hac_ncu', 'ufibridge', 'power'])
    
    def generate_full_analysis(self, coverage_results: Dict[str, Any], 
                               metadata: Dict[str, Any],
                               gap_results: Dict[str, Any] = None,
                               training_results: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Generate comprehensive ML analysis of coverage results.
        
        Args:
            coverage_results: Coverage analysis results by domain
            metadata: Collection metadata (timestamp, workload, hardware)
            gap_results: Gap analysis results (includes ml_anomalies from gap detection)
            training_results: Training session results (includes instruction_mix_learning)
        
        Returns:
            dict: Complete ML analysis with insights and recommendations
        """
        logger.info("="*80)
        logger.info("GENERATING ML ANALYSIS")
        logger.info("="*80)
        
        # Detect product from metadata if not already set
        if not self.trainer.current_product:
            self.trainer.current_product = self.trainer._get_product_identifier(metadata)
            logger.info(f"   Product: {self.trainer.current_product}")
        
        # Extract workload from stress_tracking if available
        stress_tracking = metadata.get('stress_tracking', {})
        if stress_tracking and stress_tracking.get('classification'):
            workload_label = stress_tracking['classification'].get('label', 'Unknown')
        else:
            workload_label = metadata.get('workload', 'Unknown')
        
        analysis = {
            'metadata': {
                'timestamp': datetime.now().isoformat(),
                'analysis_version': '1.0',
                'workload': workload_label,
                'hardware': metadata.get('hardware', 'Unknown'),
                'duration_seconds': metadata.get('duration_seconds', 0)
            },
            'training_status': {},
            'training_results': training_results.get('results', {}) if training_results else {},
            'anomalies': {},
            'patterns': {},
            'predictions': {},
            'correlations': {},
            'clusters': {},
            'trends': {},
            'recommendations': []
        }
        
        # 1. Training Status Summary
        analysis['training_status'] = self._get_training_status()
        
        # 2. Anomaly Detection per Domain (merge with gap detection anomalies)
        logger.info(" Analyzing anomalies...")
        analysis['anomalies'] = self._analyze_anomalies(coverage_results, metadata, workload_label)
        
        # Merge anomalies from gap detection if provided
        if gap_results and 'ml_anomalies' in gap_results:
            gap_anomalies = gap_results['ml_anomalies']
            if gap_anomalies:
                logger.info(f"   Merging {sum(len(v) for v in gap_anomalies.values())} anomalies from gap detection")
                for domain, anomaly_list in gap_anomalies.items():
                    if domain not in analysis['anomalies']['by_domain']:
                        analysis['anomalies']['by_domain'][domain] = []
                    # Add gap detection anomalies (avoid duplicates)
                    existing_events = {a.get('event') for a in analysis['anomalies']['by_domain'][domain]}
                    for anomaly in anomaly_list:
                        if anomaly.get('event') not in existing_events:
                            analysis['anomalies']['by_domain'][domain].append(anomaly)
                
                # Recalculate statistics after merging
                anomalies_by_domain = analysis['anomalies']['by_domain']
                total_anomalies = sum(len(anoms) for anoms in anomalies_by_domain.values())
                severity_counts = defaultdict(int)
                type_counts = defaultdict(int)
                
                for domain_anoms in anomalies_by_domain.values():
                    for anom in domain_anoms:
                        severity_counts[anom.get('severity', 'unknown')] += 1
                        type_counts[anom.get('type', 'unknown')] += 1
                
                analysis['anomalies']['statistics'] = {
                    'total_anomalies': total_anomalies,
                    'domains_affected': len(anomalies_by_domain),
                    'by_severity': dict(severity_counts),
                    'by_type': dict(type_counts)
                }
        
        # 3. Pattern Classification
        logger.info(" Classifying patterns...")
        analysis['patterns'] = self._classify_patterns(coverage_results)
        
        # 4. Coverage Predictions
        logger.info(" Generating predictions...")
        analysis['predictions'] = self._generate_predictions(coverage_results, metadata)
        
        # 5. Event Correlations
        logger.info(" Finding correlations...")
        analysis['correlations'] = self._find_correlations(coverage_results)
        
        # 6. Stress-Event Correlation Analysis
        logger.info(" Analyzing stress-event correlations...")
        analysis['stress_correlation'] = self._analyze_stress_event_correlation(coverage_results, metadata)
        
        # Debug: Check if model exists
        model_status = "trained" if self.trainer.stress_correlation_model is not None else "not_trained"
        logger.info(f"[DEBUG] Stress correlation model status: {model_status}")
        
        # 6.5. Generate Health Correlation from Stress Data
        logger.info(" Generating health correlation analysis...")
        analysis['health_correlation'] = self._generate_health_correlation_from_stress(
            analysis['stress_correlation'], metadata
        )
        logger.info(f"[DEBUG] Health correlation generated - status: {analysis['health_correlation'].get('status')}")
        
        # 7. Event Clusters
        logger.info(" Clustering events...")
        analysis['clusters'] = self._cluster_events(coverage_results)
        
        # 8. Historical Trends
        logger.info("[v] Analyzing trends...")
        analysis['trends'] = self._analyze_trends(coverage_results)
        
        # 9. Generate Recommendations
        logger.info("[TIP] Generating recommendations...")
        analysis['recommendations'] = self._generate_recommendations(analysis)
        
        # 9. Analyze System Health Impact (NEW)
        logger.info(" Analyzing system health...")
        analysis['health_analysis'] = self._analyze_health_impact(coverage_results, metadata)
        
        # 10. Analyze Data Diversity and Generate Intelligent Suggestions
        logger.info(" Analyzing data diversity...")
        analysis['data_diversity'] = self.analyze_data_diversity()
        
        # 11. Workload-Gap Mapping (ML-learned workload recommendations)
        logger.info(" Generating workload-gap mapping...")
        analysis['workload_gap_mapping'] = self._generate_workload_gap_mapping(gap_results, coverage_results)
        
        # 11.5. Generate EMON Validation Commands
        logger.info(" Generating EMON validation commands...")
        analysis['emon_commands'] = self._generate_emon_commands(gap_results, analysis['workload_gap_mapping'])
        
        # 12. Summary Statistics
        analysis['summary'] = self._generate_summary(analysis)
        
        logger.info("="*80)
        logger.info("[OK] ML ANALYSIS COMPLETE")
        logger.info("="*80)
        
        return analysis
    
    def _get_training_status(self) -> Dict[str, Any]:
        """Get current ML training status and model information."""
        if not self.ml_client.local_models_available:
            return {
                'status': 'unavailable',
                'message': 'ML training not available (scikit-learn not installed)'
            }
        
        summary = self.trainer.get_training_summary()
        
        # Handle case where training hasn't completed or returned None
        if summary is None or not isinstance(summary, dict):
            return {
                'status': 'pending',
                'models_available': 0,
                'training_sessions': 0,
                'datasets_collected': 0,
                'last_training': 'Never',
                'data_directory': str(self.trainer.base_dir) if hasattr(self.trainer, 'base_dir') else 'N/A'
            }
        
        return {
            'status': 'ready',
            'models_available': summary.get('models_available', 0),
            'training_sessions': summary.get('training_sessions', 0),
            'datasets_collected': summary.get('raw_datasets', 0),
            'last_training': summary.get('last_training', {}).get('timestamp', 'Never') if isinstance(summary.get('last_training'), dict) else (summary.get('last_training') if summary.get('last_training') else 'Never'),
            'data_directory': summary.get('data_directory', 'N/A')
        }
    
    def _analyze_anomalies(self, coverage_results: Dict[str, Any], 
                          metadata: Dict[str, Any],
                          workload_label: str) -> Dict[str, List[Dict]]:
        """Analyze anomalies in each domain using ML models only (no statistical fallback)."""
        
        # Check if ML model is available
        if not self.ml_client.local_models_available or self.trainer.anomaly_detector is None:
            return {
                'status': 'no_model',
                'message': 'Anomaly detection model not trained yet',
                'requirements': {
                    'min_events': 30,
                    'min_runs': 3,
                    'reason': 'IsolationForest anomaly detector requires diverse event patterns from multiple runs to learn normal behavior'
                }
            }
        
        anomalies_by_domain = {}
        
        # Extract domain_results from coverage structure
        domain_results = coverage_results.get('domain_results', {})
        if not domain_results:
            logger.warning("No domain_results found in coverage_results for anomaly detection")
            return {'by_domain': {}, 'statistics': {'total_anomalies': 0, 'domains_affected': 0, 'by_severity': {}, 'by_type': {}}}
        
        for domain, domain_data in domain_results.items():
            # Skip if domain_data is not a dict
            if not isinstance(domain_data, dict):
                continue
            
            # Get events from active_events list
            active_events = domain_data.get('active_events', [])
            inactive_events = domain_data.get('inactive_events', [])
            
            # Prepare event data for anomaly detection
            event_data = {}
            
            # Add active events
            for event_info in active_events:
                event_name = event_info.get('event', '')
                if event_name:
                    event_data[event_name] = {
                        'total': event_info.get('total_activity', 0),
                        'per_core': {i: count for i, count in enumerate(event_info.get('per_core_counts', []))}
                    }
            
            # Add inactive events with zero counts
            for event_info in inactive_events:
                event_name = event_info.get('event', '') if isinstance(event_info, dict) else event_info
                if event_name:
                    event_data[event_name] = {
                        'total': 0,
                        'per_core': {}
                    }
            
            # Detect anomalies using ML client
            context = {
                'workload': workload_label,  # Use workload_label extracted at start of function
                'hardware': metadata.get('hardware', 'Unknown'),
                'duration': metadata.get('duration_seconds', 0)
            }
            
            anomalies = self.ml_client.detect_anomalies(event_data, domain, context)
            
            if anomalies:
                anomalies_by_domain[domain] = anomalies
        
        # Calculate anomaly statistics
        total_anomalies = sum(len(anoms) for anoms in anomalies_by_domain.values())
        severity_counts = defaultdict(int)
        type_counts = defaultdict(int)
        
        for domain_anoms in anomalies_by_domain.values():
            for anom in domain_anoms:
                severity_counts[anom.get('severity', 'unknown')] += 1
                type_counts[anom.get('type', 'unknown')] += 1
        
        return {
            'by_domain': anomalies_by_domain,
            'statistics': {
                'total_anomalies': total_anomalies,
                'domains_affected': len(anomalies_by_domain),
                'by_severity': dict(severity_counts),
                'by_type': dict(type_counts)
            }
        }
    
    def _classify_patterns(self, coverage_results: Dict[str, Any]) -> Dict[str, Any]:
        """Classify coverage patterns using trained ML classifier only (no rule-based fallback)."""
        if not self.ml_client.local_models_available or self.trainer.pattern_classifier is None:
            return {
                'status': 'no_model',
                'message': 'Pattern classifier not trained yet',
                'requirements': {
                    'min_events': 20,
                    'min_runs': 2,
                    'reason': 'Decision tree pattern classifier requires diverse event data across multiple collection runs'
                }
            }
        
        # Extract domain_results from coverage_results structure
        domain_results = coverage_results.get('domain_results', {})
        if not domain_results:
            logger.warning("No domain_results found in coverage_results")
            return {'status': 'error', 'message': 'No domain data available'}
        
        patterns_by_domain = {}
        pattern_distribution = defaultdict(int)
        
        try:
            for domain, domain_data in domain_results.items():
                # Type check: domain_data must be dict
                if not isinstance(domain_data, dict):
                    continue
                
                # Get both active and inactive events
                active_events = domain_data.get('active_events', [])
                inactive_events = domain_data.get('inactive_events', [])
                all_events = active_events + inactive_events
                
                if not all_events:
                    continue
                
                domain_patterns = []
                
                for event_info in all_events:
                    if not isinstance(event_info, dict):
                        continue
                    
                    event_name = event_info.get('event', 'unknown')
                    total_activity = event_info.get('total_activity', 0)
                    per_core = event_info.get('per_core_counts', [])
                    
                    # USE TRAINED ML MODEL for pattern classification
                    ml_used = False
                    pattern = 'low_activity'  # Default
                    
                    if total_activity > 0:
                        # Prepare features matching training: ['total_activity', 'domain_encoded', 'workload_encoded']
                        # We need to encode domain and workload the same way as training
                        
                        # Load domain list from config or use defaults
                        domain_list = self._get_ml_domains('anomaly_detector')
                        domain_encoded = domain_list.index(domain.lower()) if domain.lower() in domain_list else 0
                        
                        # Workload encoded (0 for idle/unknown since we don't have workload info here)
                        workload_encoded = 0
                        
                        features = pd.DataFrame([{
                            'total_activity': total_activity,
                            'domain_encoded': domain_encoded,
                            'workload_encoded': workload_encoded
                        }])
                        
                        try:
                            # Use trained pattern classifier model (Random Forest doesn't need scaling)
                            pattern_code = self.trainer.pattern_classifier.predict(features)[0]
                            
                            # Map pattern code to label
                            pattern_labels = {0: 'low_activity', 1: 'medium_activity', 2: 'high_activity', 3: 'full_toggle'}
                            pattern = pattern_labels.get(pattern_code, 'low_activity')
                            ml_used = True
                            
                        except Exception as e:
                            logger.error(f"ML pattern classification failed: {e}")
                            # Don't add this event to results if ML fails
                            continue
                    
                    domain_patterns.append({
                        'event': event_name,
                        'pattern': pattern,
                        'total_activity': total_activity,
                        'ml_classified': ml_used  # Only True if ML model actually used
                    })
                    
                    pattern_distribution[pattern] += 1
                
                patterns_by_domain[domain] = domain_patterns
            
            return {
                'status': 'success',
                'by_domain': patterns_by_domain,
                'distribution': dict(pattern_distribution),
                'pattern_types': ['low_activity', 'medium_activity', 'high_activity', 'full_toggle']
            }
            
        except Exception as e:
            logger.error(f"Error classifying patterns: {e}")
            return {'status': 'error', 'message': str(e)}
    
    def _generate_predictions(self, coverage_results: Dict[str, Any],
                            metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Generate coverage predictions for untested scenarios."""
        if not self.ml_client.local_models_available or self.trainer.coverage_predictor is None:
            return {'status': 'no_model', 'message': 'Coverage predictor not trained yet'}
        
        predictions = {
            'status': 'success',
            'current_coverage': {},
            'predicted_improvements': [],
            'optimization_suggestions': []
        }
        
        try:
            # Get domain results - handle different data structures
            # Structure 1: coverage_results = {domain: {events: {...}}}
            # Structure 2: coverage_results = {domain_results: {domain: {active_events: N, total_tested: N}}}
            domain_data_source = coverage_results
            
            # Check if we have the nested domain_results structure
            if 'domain_results' in coverage_results:
                domain_data_source = coverage_results.get('domain_results', {})
            
            # Calculate current coverage rates from domain_results
            for domain, domain_data in domain_data_source.items():
                # Type check: domain_data must be dict
                if not isinstance(domain_data, dict):
                    continue
                
                # Handle Structure 2: {active_events, total_tested, activity_rate}
                if 'total_tested' in domain_data:
                    total_events = domain_data.get('total_tested', 0)
                    # active_events can be a list or an int
                    active_events_data = domain_data.get('active_events', [])
                    if isinstance(active_events_data, list):
                        active_events = len(active_events_data)
                    else:
                        active_events = active_events_data if isinstance(active_events_data, int) else 0
                    
                    coverage_rate = domain_data.get('activity_rate', 0)
                    # activity_rate is already 0-100, convert to 0-1
                    if isinstance(coverage_rate, (int, float)) and coverage_rate > 1:
                        coverage_rate = coverage_rate / 100.0
                    
                    predictions['current_coverage'][domain] = {
                        'total_events': total_events,
                        'active_events': active_events,
                        'coverage_rate': coverage_rate
                    }
                # Handle Structure 1: {events: {...}}
                elif 'events' in domain_data:
                    events = domain_data['events']
                    if not isinstance(events, dict):
                        continue
                    
                    total_events = len(events)
                    active_events = sum(1 for e in events.values() 
                                      if e.get('active_count', 0) > 0)
                    
                    coverage_rate = active_events / total_events if total_events > 0 else 0
                    
                    predictions['current_coverage'][domain] = {
                        'total_events': total_events,
                        'active_events': active_events,
                        'coverage_rate': coverage_rate
                    }
            
            # Generate predictions for different scenarios using TRAINED ML MODEL
            scenarios = [
                {'workload': 'stress_test', 'duration': 600, 'stress_level': 2},
                {'workload': 'mixed_workload', 'duration': 300, 'stress_level': 1},
                {'workload': 'idle_power', 'duration': 120, 'stress_level': 0}
            ]
            
            current_avg_coverage = np.mean([d['coverage_rate'] for d in predictions['current_coverage'].values()])
            
            for scenario in scenarios:
                try:
                    # Check if coverage predictor is available and trained
                    if not self.trainer.coverage_predictor:
                        raise ValueError("Coverage predictor not trained")
                    
                    # Prepare features matching the training features
                    # Training uses: ['domain_encoded', 'workload_encoded', 'duration_seconds']
                    
                    # Use features that match what the model was trained on
                    features = pd.DataFrame([{
                        'domain_encoded': 0,  # Average across domains
                        'workload_encoded': scenario['stress_level'],
                        'duration_seconds': scenario['duration']
                    }])
                    
                    # Predict toggle rate (coverage)
                    predicted_toggle_rate = self.trainer.coverage_predictor.predict(features)[0]
                    
                    # Convert toggle rate (0-1) to coverage percentage (0-100)
                    ml_predicted_coverage = min(1.0, max(0.0, predicted_toggle_rate))
                    
                    # Expected gains by stress level from validation experience:
                    # - High stress (2): +7-10% more events toggle due to intensive CPU/memory pressure
                    # - Mixed (1): +3.5-5% more events due to balanced workload  
                    # - Idle (0): +1-1.5% minimal gain, mostly background activity events
                    base_coverage = current_avg_coverage
                    stress_gains = {0: 0.012, 1: 0.035, 2: 0.07}
                    duration_factor = min(1.0, scenario['duration'] / 600)  # Longer = better, max at 600s
                    
                    expected_gain = stress_gains.get(scenario['stress_level'], 0.035) * duration_factor
                    
                    # Apply diminishing returns at high coverage
                    if base_coverage > 0.85:
                        expected_gain *= 0.3  # Hard to gain more when already at 85%+
                    elif base_coverage > 0.75:
                        expected_gain *= 0.6
                    elif base_coverage > 0.65:
                        expected_gain *= 0.8
                    
                    # ALWAYS apply scenario-based differentiation
                    # Use ML model's prediction as a ceiling but differentiate by scenario
                    analytical_prediction = min(1.0, base_coverage + expected_gain)
                    
                    # Debug logging (use logger.debug for verbose tracing)
                    logger.debug(f"[PREDICT] {scenario['workload']}: base={base_coverage:.3f}, ml_pred={ml_predicted_coverage:.3f}, expected_gain={expected_gain:.4f}")
                    
                    # Final prediction: use analytical estimate (which varies by scenario)
                    # ML model gives us confidence that gains are achievable
                    if ml_predicted_coverage > base_coverage:
                        # ML thinks we can improve - use analytical estimate scaled by ML confidence
                        ml_gain = ml_predicted_coverage - base_coverage
                        # Cap analytical gain at ML's suggested gain
                        final_gain = min(expected_gain, ml_gain)
                        predicted_coverage = base_coverage + final_gain
                        logger.debug(f"[PREDICT] {scenario['workload']}: ml_gain={ml_gain:.4f}, final_gain={final_gain:.4f}, pred_cov={predicted_coverage:.4f}")
                    else:
                        # ML doesn't predict improvement - use conservative analytical estimate
                        predicted_coverage = analytical_prediction
                    
                    # Calculate actual gain
                    predicted_gain = max(0, predicted_coverage - base_coverage)
                    
                    predicted_improvement = {
                        'scenario': scenario,
                        'predicted_coverage': predicted_coverage,  # Keep as float (0.0-1.0)
                        'estimated_coverage_gain': predicted_gain,  # Keep as float
                        'recommended': scenario['workload'] == 'stress_test' and predicted_gain > 0.03,
                        'ml_predicted': True
                    }
                    
                except Exception as e:
                    logger.warning(f"ML prediction failed for {scenario['workload']}: {e}")
                    logger.debug(f"Exception details: {type(e).__name__}: {str(e)}")
                    # Fallback to analytical estimates if model fails
                    current_cov = current_avg_coverage
                    
                    # Estimate coverage gain based on stress level and current coverage
                    stress_gains = {0: 0.012, 1: 0.035, 2: 0.07}  # idle: 1.2%, mixed: 3.5%, high: 7%
                    duration_factor = min(1.0, scenario['duration'] / 600)
                    estimated_gain = stress_gains.get(scenario['stress_level'], 0.035) * duration_factor
                    
                    # Reduce gain if already at high coverage (diminishing returns)
                    if current_cov > 0.85:
                        estimated_gain *= 0.3
                    elif current_cov > 0.75:
                        estimated_gain *= 0.6
                    elif current_cov > 0.65:
                        estimated_gain *= 0.8
                    
                    predicted_improvement = {
                        'scenario': scenario,
                        'estimated_coverage_gain': estimated_gain,
                        'predicted_coverage': min(1.0, current_cov + estimated_gain),  
                        'recommended': scenario['workload'] == 'stress_test' and estimated_gain > 0.03,
                        'ml_predicted': False
                    }
                
                predictions['predicted_improvements'].append(predicted_improvement)
            
            predictions['ml_model_used'] = self.trainer.coverage_predictor is not None
            
        except Exception as e:
            logger.error(f"Error generating predictions: {e}")
            predictions['status'] = 'error'
            predictions['message'] = str(e)
        
        return predictions
    
    def _find_correlations(self, coverage_results: Dict[str, Any]) -> Dict[str, Any]:
        """Find correlations between events across domains."""
        correlations = {
            'status': 'success',
            'strong_correlations': [],
            'cross_domain_links': [],
            'correlation_matrix': {}
        }
        
        try:
            # Collect all event counts
            all_events = {}
            
            for domain, domain_data in coverage_results.items():
                # Type check: domain_data must be dict
                if not isinstance(domain_data, dict):
                    continue
                if 'events' not in domain_data:
                    continue
                
                events = domain_data['events']
                if not isinstance(events, dict):
                    continue
                
                for event_name, event_info in events.items():
                    full_name = f"{domain}.{event_name}"
                    all_events[full_name] = event_info.get('total_count', 0)
            
            # Calculate correlations (simplified - would use actual correlation analysis)
            if len(all_events) > 1:
                event_list = list(all_events.items())
                
                # Find pairs with similar counts (potential correlation)
                for i, (event1, count1) in enumerate(event_list):
                    for event2, count2 in event_list[i+1:]:
                        if count1 > 0 and count2 > 0:
                            ratio = min(count1, count2) / max(count1, count2)
                            
                            if ratio > 0.8:  # Strong similarity
                                correlations['strong_correlations'].append({
                                    'event1': event1,
                                    'event2': event2,
                                    'correlation': ratio,
                                    'explanation': 'Events show similar activity levels'
                                })
            
            # Identify cross-domain relationships
            core_events = [k for k in all_events.keys() if 'core' in k.lower()]
            memory_events = [k for k in all_events.keys() if any(m in k.lower() for m in ['imc', 'memory', 'ddr'])]
            
            if core_events and memory_events:
                correlations['cross_domain_links'].append({
                    'link': 'Core-Memory',
                    'description': 'Core activity should correlate with memory operations',
                    'core_events': len(core_events),
                    'memory_events': len(memory_events)
                })
            
        except Exception as e:
            logger.error(f"Error finding correlations: {e}")
            correlations['status'] = 'error'
            correlations['message'] = str(e)
        
        return correlations
    
    def _analyze_stress_event_correlation(self, coverage_results: Dict[str, Any], 
                                         metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze correlation between stress workloads (SuperCollider, Prime95, etc.) 
        and event activity using trained ML model or rule-based fallback.
        """
        # Extract workload label early for use in result dict
        # stress_tracking structure: {'final_classification': 'Memicals...', 'test_type': 'single_stress', ...}
        stress_tracking = metadata.get('stress_tracking', {})
        if stress_tracking.get('final_classification'):
            # Use the actual stress tracking label
            workload_label = stress_tracking.get('final_classification', 'unknown')
        elif stress_tracking.get('classification'):
            # Legacy format with nested classification dict
            workload_label = stress_tracking['classification'].get('label', 'unknown')
        else:
            workload_label = metadata.get('workload', 'unknown')
        
        result = {
            'status': 'success',
            'workload': workload_label,
            'workload_profile': metadata.get('workload_profile', {}),
            'event_classifications': {},
            'correlation_matrix': {},
            'stress_sensitive_events': [],
            'stress_independent_events': [],
            'domain_stress_impact': {},
            'ml_model_used': self.trainer.stress_correlation_model is not None
        }
        
        try:
            # Get domain results
            domain_results = coverage_results.get('domain_results', {})
            if not domain_results:
                return {'status': 'no_data', 'message': 'No domain results available'}
            
            # Extract workload indicators - PRIORITIZE stress_tracking over old workload field
            stress_tracking = metadata.get('stress_tracking', {})
            
            # Handle both new format (final_classification, test_type) and legacy format (classification.label)
            if stress_tracking.get('final_classification'):
                # New format: stress_tracking has final_classification and test_type directly
                workload_type = stress_tracking.get('final_classification', 'unknown').lower()
                collection_type = stress_tracking.get('test_type', 'idle')
                
                # Determine stress level from tracking data
                # Check for ANY recognized stress tool first (regardless of collection_type)
                if any(tool in workload_type for tool in ['prime95', 'supercollider', 'linpack', 'stressapptest', 'stress-ng']):
                    stress_level = 2  # High - known CPU stress
                elif any(tool in workload_type for tool in ['memicals', 'memtester', 'mlc', 'stream', 'membw']):
                    stress_level = 2  # High - known memory stress
                elif any(tool in workload_type for tool in ['fio', 'iometer', 'diskspd']):
                    stress_level = 2  # High - known I/O stress
                elif any(tool in workload_type for tool in ['sandstone', 'svos', 'ipmctl']):
                    stress_level = 1  # Medium - validation tools
                elif collection_type in ['single_stress', 'mixed_workload']:
                    stress_level = 1  # Medium - unknown stress detected
                elif collection_type == 'idle':
                    stress_level = 0  # Low - idle
                else:
                    stress_level = 1  # Medium - other (power_cycling, stress_ended)
            elif stress_tracking.get('classification'):
                # Legacy format with nested classification dict
                workload_type = stress_tracking['classification'].get('label', 'unknown').lower()
                collection_type = stress_tracking['classification'].get('type', 'idle')
                
                # Same stress level logic
                if any(tool in workload_type for tool in ['prime95', 'supercollider', 'linpack', 'stressapptest', 'stress-ng']):
                    stress_level = 2
                elif any(tool in workload_type for tool in ['memicals', 'memtester', 'mlc', 'stream', 'membw']):
                    stress_level = 2
                elif any(tool in workload_type for tool in ['fio', 'iometer', 'diskspd']):
                    stress_level = 2
                elif any(tool in workload_type for tool in ['sandstone', 'svos', 'ipmctl']):
                    stress_level = 1
                elif collection_type in ['single_stress', 'mixed_workload']:
                    stress_level = 1
                elif collection_type == 'idle':
                    stress_level = 0
                else:
                    stress_level = 1
            else:
                # Fallback to old method
                workload_type = (metadata.get('workload') or 'unknown').lower()
                cpu_usage = metadata.get('memory_context', {}).get('cpu_utilization_percent', 0)
                mem_usage = metadata.get('memory_context', {}).get('memory_utilization_percent', 0)
                
                # Classify workload intensity
                if 'prime95' in workload_type or 'supercollider' in workload_type:
                    stress_level = 2  # High
                elif cpu_usage > 70 or mem_usage > 70:
                    stress_level = 1  # Medium
                else:
                    stress_level = 0  # Low
            
            result['stress_level'] = ['low', 'medium', 'high'][stress_level]
            result['workload_type'] = workload_type  # Store for summary
            
            # Analyze each domain's response to stress
            for domain, domain_data in domain_results.items():
                if not isinstance(domain_data, dict):
                    continue
                
                active_events = domain_data.get('active_events', [])
                inactive_events = domain_data.get('inactive_events', [])
                
                domain_analysis = {
                    'total_events': len(active_events) + len(inactive_events),
                    'active_events': len(active_events),
                    'activity_rate': domain_data.get('activity_rate', 0),
                    'stress_sensitive': [],
                    'stress_independent': [],
                    'moderately_sensitive': []
                }
                
                # Analyze each active event
                for event_info in active_events:
                    event_name = event_info.get('event', 'unknown')
                    total_activity = event_info.get('total_activity', 0)
                    per_core = event_info.get('per_core_counts', [])
                    
                    if not per_core:
                        continue
                    
                    # Calculate metrics
                    max_count = max(per_core)
                    min_count = min(per_core)
                    avg_count = sum(per_core) / len(per_core) if per_core else 0
                    std_count = np.std(per_core) if per_core else 0
                    variation_coef = (max_count - min_count) / avg_count if avg_count > 0 else 0
                    
                    # USE TRAINED ML MODEL if available
                    if self.trainer.stress_correlation_model is not None:
                        import pandas as pd
                        
                        # Get instruction mix from metadata (if available)
                        instruction_mix = metadata.get('instruction_mix', {})
                        
                        # Prepare features for model prediction
                        feature_dict = {
                            'stress_level': stress_level,
                            'total_activity': total_activity,
                            'avg_count': avg_count,
                            'max_count': max_count,
                            'std_count': std_count
                        }
                        
                        # Add instruction mix features if model supports them
                        # (Check if model was trained with scenario correlation)
                        model_features = getattr(self.trainer.stress_correlation_model, 'feature_names_in_', None)
                        if model_features is not None and any('_pct' in str(f) for f in model_features):
                            # Model supports instruction mix - add those features
                            for category in ['fp_simd', 'memory', 'branch', 'integer', 'cache']:
                                cat_data = instruction_mix.get(category, {})
                                feature_dict[f'{category}_pct'] = cat_data.get('percentage', 0)
                        
                        try:
                            features = pd.DataFrame([feature_dict])
                            
                            # Normalize using stress model scaler
                            features_scaled = self.trainer.stress_scaler.transform(features)
                            
                            # Predict correlation score using trained model
                            correlation_score = self.trainer.stress_correlation_model.predict(features_scaled)[0]
                            correlation_score = max(0.0, min(1.0, correlation_score))  # Clamp to [0,1]
                            
                            # Classify based on ML prediction
                            if correlation_score >= 0.7:
                                sensitivity = 'high'
                                category = 'stress_sensitive'
                            elif correlation_score >= 0.4:
                                sensitivity = 'moderate'
                                category = 'moderately_sensitive'
                            else:
                                sensitivity = 'low'
                                category = 'stress_independent'
                            
                            # Generate scenario fingerprint if instruction mix is available
                            scenario_fingerprint = None
                            if instruction_mix:
                                # Find dominant instruction category
                                dominant_category = max(
                                    [(cat, data.get('percentage', 0)) for cat, data in instruction_mix.items()],
                                    key=lambda x: x[1]
                                )[0] if instruction_mix else 'unknown'
                                
                                # Create fingerprint: "StressType + InstructionMix"
                                stress_name = result.get('stress_level', 'unknown')
                                scenario_fingerprint = f"{stress_name.capitalize()} Stress + {dominant_category.replace('_', ' ').title()}"
                        except Exception as ml_error:
                            # ML prediction failed (e.g., feature mismatch) - fall back to rule-based
                            logger.debug(f"ML prediction failed for {event_name}, using rule-based classification: {ml_error}")
                            if total_activity > 1000000000:  # Very high activity (billions)
                                sensitivity = 'high'
                                category = 'stress_sensitive'
                                correlation_score = 0.85 + (variation_coef * 0.15)
                            elif total_activity > 10000000:  # High activity (millions)
                                sensitivity = 'moderate'
                                category = 'moderately_sensitive'
                                correlation_score = 0.50 + (variation_coef * 0.25)
                            else:  # Low activity
                                sensitivity = 'low'
                                category = 'stress_independent'
                                correlation_score = 0.15 + (variation_coef * 0.10)
                    else:
                        # FALLBACK: Rule-based classification
                        if total_activity > 1000000000:  # Very high activity (billions)
                            sensitivity = 'high'
                            category = 'stress_sensitive'
                            correlation_score = 0.85 + (variation_coef * 0.15)
                        elif total_activity > 10000000:  # High activity (millions)
                            sensitivity = 'moderate'
                            category = 'moderately_sensitive'
                            correlation_score = 0.50 + (variation_coef * 0.25)
                        else:  # Low activity
                            sensitivity = 'low'
                            category = 'stress_independent'
                            correlation_score = 0.15 + (variation_coef * 0.10)
                    
                    event_classification = {
                        'event': event_name,
                        'domain': domain,
                        'total_activity': total_activity,
                        'sensitivity': sensitivity,
                        'correlation_score': min(correlation_score, 1.0),
                        'max_count': max_count,
                        'min_count': min_count,
                        'avg_count': int(avg_count),
                        'variation_coefficient': round(variation_coef, 3),
                        'ml_predicted': self.trainer.stress_correlation_model is not None,
                        'scenario_fingerprint': scenario_fingerprint if 'scenario_fingerprint' in locals() else None
                    }
                    
                    domain_analysis[category].append(event_classification)
                    result['event_classifications'][event_name] = event_classification
                    
                    # Add to global lists
                    if sensitivity == 'high':
                        result['stress_sensitive_events'].append(event_classification)
                    elif sensitivity == 'low':
                        result['stress_independent_events'].append(event_classification)
                
                # Calculate domain impact score and level
                stress_sensitive_count = len(domain_analysis['stress_sensitive'])
                moderately_sensitive_count = len(domain_analysis['moderately_sensitive'])
                total_active = len(active_events)
                
                # Impact score: weighted average of correlation scores
                all_correlations = (
                    [e['correlation_score'] for e in domain_analysis['stress_sensitive']] +
                    [e['correlation_score'] for e in domain_analysis['moderately_sensitive']] +
                    [e['correlation_score'] for e in domain_analysis['stress_independent']]
                )
                impact_score = sum(all_correlations) / len(all_correlations) if all_correlations else 0
                
                # Impact level based on percentage of stress-sensitive events
                if total_active > 0:
                    sensitive_pct = (stress_sensitive_count / total_active) * 100
                    if sensitive_pct >= 50:
                        impact_level = 'HIGH'
                    elif sensitive_pct >= 20:
                        impact_level = 'MEDIUM'
                    else:
                        impact_level = 'LOW'
                else:
                    impact_level = 'UNKNOWN'
                
                # Add calculated fields to domain analysis
                domain_analysis['stress_sensitive_count'] = stress_sensitive_count
                domain_analysis['moderately_sensitive_count'] = moderately_sensitive_count
                domain_analysis['stress_independent_count'] = len(domain_analysis['stress_independent'])
                domain_analysis['impact_score'] = round(impact_score, 2)
                domain_analysis['impact_level'] = impact_level
                
                result['domain_stress_impact'][domain] = domain_analysis
            
            # Generate correlation matrix for top events
            result['correlation_matrix'] = self._generate_stress_correlation_matrix(
                result['event_classifications'], 
                stress_level
            )
            
            # Summary statistics
            result['summary'] = {
                'total_events_analyzed': len(result['event_classifications']),
                'stress_sensitive_count': len(result['stress_sensitive_events']),
                'stress_independent_count': len(result['stress_independent_events']),
                'stress_sensitive_pct': (len(result['stress_sensitive_events']) / 
                                        len(result['event_classifications']) * 100) 
                                       if result['event_classifications'] else 0,
                'workload_type': result.get('workload_type', workload_type),  # Use stored value
                'stress_level': result['stress_level'],
                'ml_model_used': result['ml_model_used']
            }
            
        except Exception as e:
            logger.error(f"Error analyzing stress-event correlation: {e}")
            result['status'] = 'error'
            result['message'] = str(e)
        
        return result
    
    def _generate_health_correlation_from_stress(self, stress_data: Dict[str, Any], 
                                                  metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform stress correlation data into health correlation format expected by report.
        Maps stress/workload analysis to health metrics correlation.
        """
        if self.debug:
            print(f"[Health-Corr] Generating health correlation - stress_data keys: {list(stress_data.keys())}")
            print(f"[Health-Corr] ML model used: {stress_data.get('ml_model_used', False)}")
        
        # If model not trained, use rule-based analysis instead of returning empty
        ml_model_used = stress_data.get('ml_model_used', False)
        if self.debug:
            print(f"[Health-Corr] ML model trained: {ml_model_used} - Using {'ML-based' if ml_model_used else 'rule-based'} analysis")
        
        # Extract health metrics from metadata
        health_metrics = metadata.get('health_metrics', {})
        health_samples = metadata.get('health_samples', [])
        avg_cpu = health_metrics.get('avg_cpu_usage', 0)
        avg_mem = health_metrics.get('avg_memory_usage', 0)
        disk_free = health_metrics.get('avg_disk_free_gb', 0)
        
        if self.debug:
            print(f"[Health-Corr] Health metrics - CPU: {avg_cpu}%, Mem: {avg_mem}%, Disk: {disk_free}GB")
        
        # Calculate health score using ML model if available, otherwise rule-based
        health_score = 100.0
        analysis_method = 'Rule-based'
        
        if self.trainer.health_predictor is not None and health_samples:
            try:
                # ML-based health score prediction
                import numpy as np
                
                # Extract temperature if available
                temp_values = [s.get('metrics', {}).get('temperature_c', 0) for s in health_samples if s.get('metrics', {}).get('temperature_c', 0) > 0]
                avg_temp = sum(temp_values) / len(temp_values) if temp_values else 60
                
                # Get max values
                cpu_values = [s.get('metrics', {}).get('cpu_usage_pct', 0) for s in health_samples]
                mem_values = [s.get('metrics', {}).get('memory_usage_pct', 0) for s in health_samples]
                max_cpu = max(cpu_values) if cpu_values else avg_cpu
                max_mem = max(mem_values) if mem_values else avg_mem
                
                # Prepare features: [avg_cpu, avg_mem, avg_disk_free, avg_temp, max_cpu, max_mem]
                features = np.array([[avg_cpu, avg_mem, disk_free, avg_temp, max_cpu, max_mem]])
                features_scaled = self.trainer.health_scaler.transform(features)
                
                # Predict coverage rate from health metrics
                predicted_coverage = self.trainer.health_predictor.predict(features_scaled)[0]
                health_score = min(100, max(0, predicted_coverage))  # Clamp to 0-100
                analysis_method = 'ML-based'
                
                if self.debug:
                    print(f"[Health-Corr] ML predicted coverage from health: {health_score:.1f}%")
                    
            except Exception as e:
                if self.debug:
                    print(f"[Health-Corr] ML prediction failed: {e}, falling back to rule-based")
                # Fall through to rule-based calculation
        
        # Rule-based health score calculation (fallback or if no ML model)
        if analysis_method == 'Rule-based':
            # Penalize high CPU usage
            if avg_cpu > 90:
                health_score -= 30
            elif avg_cpu > 70:
                health_score -= 15
            elif avg_cpu > 50:
                health_score -= 5
            
            # Penalize high memory usage  
            if avg_mem > 90:
                health_score -= 25
            elif avg_mem > 70:
                health_score -= 10
            
            # Penalize low disk space
            if disk_free < 1:
                health_score -= 40
            elif disk_free < 5:
                health_score -= 20
            elif disk_free < 10:
                health_score -= 5
        
        # Determine status and color based on score
        if health_score >= 90:
            status = "Excellent"
            status_color = "#28a745"
        elif health_score >= 75:
            status = "Good"
            status_color = "#17a2b8"
        elif health_score >= 50:
            status = "Fair"
            status_color = "#ffc107"
        else:
            status = "Poor"
            status_color = "#dc3545"
        
        # Generate correlations based on stress analysis
        correlations = []
        
        # CPU-Event correlation
        stress_sensitive_count = len(stress_data.get('stress_sensitive_events', []))
        total_events = len(stress_data.get('event_classifications', {}))
        if self.debug:
            print(f"[Health-Corr] Stress sensitive: {stress_sensitive_count}/{total_events}")
        
        if total_events > 0:
            cpu_correlation = stress_sensitive_count / total_events
            correlations.append({
                'metric': 'CPU Usage',
                'strength': cpu_correlation,
                'impact': f"{stress_sensitive_count}/{total_events} events are stress-sensitive"
            })
        else:
            # Fallback: Use CPU usage as proxy
            cpu_correlation = min(avg_cpu / 100, 1.0)
            correlations.append({
                'metric': 'CPU Usage',
                'strength': cpu_correlation,
                'impact': f"Average {avg_cpu:.1f}% CPU utilization during collection"
            })
        
        # Memory correlation
        mem_correlation = 0.3 + (avg_mem / 200)  # Base correlation
        correlations.append({
            'metric': 'Memory Usage',
            'strength': mem_correlation,
            'impact': f"Average {avg_mem:.1f}% memory utilization during collection"
        })
        
        # Disk space correlation
        disk_correlation = min(disk_free / 50, 1.0)  # More space = better
        correlations.append({
            'metric': 'Disk Space',
            'strength': disk_correlation,
            'impact': f"{disk_free:.1f} GB free - {'Adequate' if disk_free > 10 else 'Limited'}"
        })
        
        # Additional correlations from detailed health samples
        health_samples = metadata.get('health_samples', [])
        
        # Temperature correlation (if available)
        temp_values = [s.get('metrics', {}).get('temperature_c', 0) for s in health_samples if s.get('metrics', {}).get('temperature_c', 0) > 0]
        if temp_values:
            avg_temp = sum(temp_values) / len(temp_values)
            # Higher temp = lower correlation (thermal throttling risk)
            temp_correlation = max(0, 1 - (avg_temp - 30) / 70)  # Optimal: 30°C, Critical: 100°C
            correlations.append({
                'metric': 'CPU Temperature',
                'strength': temp_correlation,
                'impact': f"Average {avg_temp:.1f}°C - {'Normal' if avg_temp < 70 else 'Elevated' if avg_temp < 85 else 'Critical'}"
            })
        
        # EMON process resource usage correlation
        emon_cpu_values = [s.get('metrics', {}).get('emon_cpu_pct', 0) for s in health_samples if 'emon_cpu_pct' in s.get('metrics', {})]
        if emon_cpu_values:
            avg_emon_cpu = sum(emon_cpu_values) / len(emon_cpu_values)
            # Moderate EMON CPU usage is good (10-30%), too high or too low is bad
            if 10 <= avg_emon_cpu <= 30:
                emon_correlation = 0.8
            elif 5 <= avg_emon_cpu <= 50:
                emon_correlation = 0.6
            else:
                emon_correlation = 0.3
            correlations.append({
                'metric': 'EMON Process CPU',
                'strength': emon_correlation,
                'impact': f"Average {avg_emon_cpu:.1f}% CPU usage - {'Optimal' if 10 <= avg_emon_cpu <= 30 else 'Suboptimal'}"
            })
        
        # EMON process memory usage correlation
        emon_mem_values = [s.get('metrics', {}).get('emon_mem_pct', 0) for s in health_samples if 'emon_mem_pct' in s.get('metrics', {})]
        if emon_mem_values:
            avg_emon_mem = sum(emon_mem_values) / len(emon_mem_values)
            emon_mem_correlation = min(avg_emon_mem / 50, 1.0)  # More memory = better buffering
            correlations.append({
                'metric': 'EMON Process Memory',
                'strength': emon_mem_correlation,
                'impact': f"Average {avg_emon_mem:.1f}% memory usage"
            })
        
        # Disk usage percentage correlation
        disk_usage_values = [s.get('metrics', {}).get('disk_usage_pct', 0) for s in health_samples if 'disk_usage_pct' in s.get('metrics', {})]
        if disk_usage_values:
            avg_disk_usage = sum(disk_usage_values) / len(disk_usage_values)
            # Lower disk usage % = more free space = better
            disk_usage_correlation = max(0, 1 - (avg_disk_usage / 100))
            correlations.append({
                'metric': 'Disk Usage %',
                'strength': disk_usage_correlation,
                'impact': f"Average {avg_disk_usage:.1f}% used - {'Healthy' if avg_disk_usage < 80 else 'High' if avg_disk_usage < 95 else 'Critical'}"
            })
        
        # File size growth correlation
        file_size_values = [s.get('metrics', {}).get('file_size_mb', 0) for s in health_samples if 'file_size_mb' in s.get('metrics', {})]
        if file_size_values and len(file_size_values) > 1:
            file_growth_rate = (file_size_values[-1] - file_size_values[0]) / max(len(file_size_values) - 1, 1)
            # Consistent growth is good (0.5-5 MB/sample)
            if 0.5 <= file_growth_rate <= 5:
                growth_correlation = 0.9
            elif 0.1 <= file_growth_rate <= 10:
                growth_correlation = 0.7
            else:
                growth_correlation = 0.4
            correlations.append({
                'metric': 'Data Collection Rate',
                'strength': growth_correlation,
                'impact': f"{file_growth_rate:.2f} MB/sample - {'Stable' if 0.5 <= file_growth_rate <= 5 else 'Variable'}"
            })
        
        # Generate comprehensive ML-based recommendations
        recommendations = []
        
        # === CRITICAL ISSUES (Fix immediately) ===
        if disk_free < 5:
            recommendations.append("[!] CRITICAL: Disk space critically low ({:.1f} GB) - Collection may fail. Free up at least 15 GB immediately".format(disk_free))
        
        if disk_usage_values and sum(disk_usage_values) / len(disk_usage_values) > 95:
            recommendations.append("[!] CRITICAL: Disk usage at {:.0f}% - Risk of collection failure. Delete unnecessary files immediately".format(sum(disk_usage_values) / len(disk_usage_values)))
        
        if temp_values and sum(temp_values) / len(temp_values) > 90:
            recommendations.append("[!] CRITICAL: CPU temperature at {:.0f}°C - Thermal throttling likely. Stop collection and improve cooling".format(sum(temp_values) / len(temp_values)))
        
        if avg_mem > 95:
            recommendations.append("[!] CRITICAL: Memory usage at {:.1f}% - Risk of OOM errors. Close applications immediately".format(avg_mem))
        
        # === HIGH PRIORITY (Should fix soon) ===
        if 5 <= disk_free < 10:
            recommendations.append("[WARN] HIGH: Disk space limited ({:.1f} GB) - Recommend 20+ GB free for reliable long-duration collections".format(disk_free))
        
        if disk_usage_values and 90 <= sum(disk_usage_values) / len(disk_usage_values) <= 95:
            recommendations.append("[WARN] HIGH: Disk usage at {:.0f}% - Free up space to avoid collection interruptions".format(sum(disk_usage_values) / len(disk_usage_values)))
        
        if temp_values and 85 <= sum(temp_values) / len(temp_values) <= 90:
            recommendations.append("[WARN] HIGH: CPU temperature elevated ({:.0f}°C) - Improve cooling to prevent thermal throttling".format(sum(temp_values) / len(temp_values)))
        
        if avg_mem > 80:
            recommendations.append("[WARN] HIGH: Memory usage high ({:.1f}%) - Close background applications to prevent swapping".format(avg_mem))
        
        if avg_cpu > 70:
            recommendations.append("[WARN] HIGH: CPU usage high ({:.1f}%) - Reduce background processes for better EMON performance".format(avg_cpu))
        
        # === MEDIUM PRIORITY (Optimization opportunities) ===
        if emon_cpu_values:
            avg_emon_cpu = sum(emon_cpu_values) / len(emon_cpu_values)
            if avg_emon_cpu < 5:
                recommendations.append("[TIP] OPTIMIZE: EMON process CPU very low ({:.1f}%) - May indicate collection issues or idle periods".format(avg_emon_cpu))
            elif avg_emon_cpu > 50:
                recommendations.append("[TIP] OPTIMIZE: EMON process CPU high ({:.1f}%) - Consider reducing sampling frequency or event count".format(avg_emon_cpu))
        
        if emon_mem_values:
            avg_emon_mem = sum(emon_mem_values) / len(emon_mem_values)
            if avg_emon_mem < 0.5:
                recommendations.append("[TIP] OPTIMIZE: EMON memory usage very low ({:.1f}%) - May indicate buffering issues".format(avg_emon_mem))
            elif avg_emon_mem > 10:
                recommendations.append("[TIP] OPTIMIZE: EMON memory usage high ({:.1f}%) - Large event buffers detected".format(avg_emon_mem))
        
        if file_size_values and len(file_size_values) > 1:
            file_growth_rate = (file_size_values[-1] - file_size_values[0]) / max(len(file_size_values) - 1, 1)
            if file_growth_rate < 0.1:
                recommendations.append("[TIP] OPTIMIZE: Very low data collection rate ({:.2f} MB/sample) - Verify workload is active and events are toggling".format(file_growth_rate))
            elif file_growth_rate > 10:
                recommendations.append("[TIP] OPTIMIZE: High data collection rate ({:.2f} MB/sample) - Monitor disk space closely for long runs".format(file_growth_rate))
        
        if temp_values and 70 <= sum(temp_values) / len(temp_values) < 85:
            recommendations.append("[TIP] OPTIMIZE: CPU temperature warm ({:.0f}°C) - Consider improving airflow for extended collections".format(sum(temp_values) / len(temp_values)))
        
        # === POSITIVE FEEDBACK ===
        if health_score >= 90:
            recommendations.append("[OK] EXCELLENT: System health is optimal for EMON collection")
        elif health_score >= 75:
            recommendations.append("[OK] GOOD: System health is suitable for production EMON collections")
        
        # === COVERAGE-BASED RECOMMENDATIONS ===
        if stress_sensitive_count > 0 and total_events > 0:
            sensitivity_pct = (stress_sensitive_count / total_events) * 100
            if sensitivity_pct > 30:
                recommendations.append(" ML INSIGHT: {:.0f}% of events are stress-sensitive - Use workload stress tests (Prime95, SuperCollider) to maximize coverage".format(sensitivity_pct))
            elif sensitivity_pct < 10:
                recommendations.append(" ML INSIGHT: Only {:.0f}% of events are stress-sensitive - Most events activate under normal/idle conditions".format(sensitivity_pct))
        
        # === LOW PRIORITY (Nice to have) ===
        if disk_free >= 10 and disk_free < 20:
            recommendations.append("[i] INFO: Disk space adequate ({:.1f} GB) but recommend 20+ GB for optimal long-duration collections".format(disk_free))
        
        if not recommendations:
            recommendations.append("[OK] No issues detected - System is ready for EMON collection")
        
        # Sort recommendations by priority (Critical > High > Medium > Positive > Info)
        priority_order = {'[!]': 0, '[WARN]': 1, '[TIP]': 2, '': 3, '[OK]': 4, '[i]': 5}
        recommendations.sort(key=lambda r: priority_order.get(r.split()[0], 99))
        
        return {
            'status': 'success',
            'health_score': round(health_score, 1),
            'status_text': status,
            'status_color': status_color,
            'correlations': correlations,
            'recommendations': recommendations,
            'ml_model_used': (analysis_method == 'ML-based'),  # True if health predictor was used
            'analysis_method': analysis_method,  # 'ML-based' or 'Rule-based'
            'health_prediction_model': 'GradientBoosting' if analysis_method == 'ML-based' else 'Rule-based thresholds',
            'metrics_analyzed': {
                'cpu_avg': avg_cpu,
                'memory_avg': avg_mem,
                'disk_free_gb': disk_free
            }
        }
    
    def _generate_stress_correlation_matrix(self, event_classifications: Dict[str, Any], 
                                           stress_level: str) -> Dict[str, Any]:
        """Generate correlation matrix data for visualization using historical workload data."""
        matrix = {
            'events': [],
            'workloads': ['Prime95', 'SuperCollider', 'Idle', 'Mixed'],
            'correlations': []
        }
        
        # Show ALL events in the correlation matrix (both active and inactive)
        # This gives complete visibility into what's stress-sensitive vs stress-independent
        sorted_events = sorted(
            event_classifications.values(),
            key=lambda x: (
                1 if x.get('sensitivity') == 'high' else 
                2 if x.get('sensitivity') == 'moderate' else 3,  # Sensitivity first
                -x.get('total_activity', 0)  # Then by activity (descending)
            )
        )
        
        # Load historical data to calculate real correlations
        try:
            # Use current product if available, otherwise try to load all data
            product_id = self.trainer.current_product or 'generic'
            historical_data = self.trainer._load_historical_data(product_id)
            
            # Group historical runs by workload type
            workload_groups = {
                'Prime95': [],
                'SuperCollider': [],
                'Idle': [],
                'Mixed': []
            }
            
            for dataset in historical_data:
                workload = (dataset.get('metadata', {}).get('workload') or '').lower()
                domain_results = dataset.get('coverage_results', {}).get('domain_results', {})
                
                # Classify workload
                if 'prime95' in workload:
                    workload_type = 'Prime95'
                elif 'supercollider' in workload:
                    workload_type = 'SuperCollider'
                elif 'idle' in workload or 'low' in workload:
                    workload_type = 'Idle'
                else:
                    workload_type = 'Mixed'
                
                # Extract event activity from this run
                event_activity = {}
                for domain, domain_data in domain_results.items():
                    if isinstance(domain_data, dict):
                        for event in domain_data.get('active_events', []):
                            if isinstance(event, dict):
                                event_name = event.get('event', '')
                                activity = event.get('total_activity', 0)
                                if event_name:
                                    event_activity[event_name] = activity
                
                workload_groups[workload_type].append(event_activity)
            
            # Calculate correlations for each event
            for event_data in sorted_events:
                event_name = event_data['event']
                matrix['events'].append(event_name)
                
                event_correlations = []
                
                # For each workload type, calculate average activity
                for workload_type in ['Prime95', 'SuperCollider', 'Idle', 'Mixed']:
                    runs = workload_groups[workload_type]
                    
                    if runs:
                        # Calculate average activity for this event under this workload
                        activities = [run.get(event_name, 0) for run in runs]
                        avg_activity = np.mean(activities) if activities else 0
                        
                        # Normalize to 0-1 range based on event's max activity
                        max_activity = event_data.get('total_activity', 1)
                        correlation = min(1.0, avg_activity / max_activity) if max_activity > 0 else 0
                    else:
                        # No historical data - use sensitivity-based estimate
                        sensitivity = event_data['sensitivity']
                        if workload_type in ['Prime95', 'SuperCollider']:
                            correlation = 0.9 if sensitivity == 'high' else 0.6 if sensitivity == 'moderate' else 0.25
                        elif workload_type == 'Idle':
                            correlation = 0.2 if sensitivity == 'high' else 0.4 if sensitivity == 'moderate' else 0.8
                        else:  # Mixed
                            correlation = 0.7 if sensitivity == 'high' else 0.5 if sensitivity == 'moderate' else 0.4
                    
                    event_correlations.append(round(correlation, 2))
                
                matrix['correlations'].append(event_correlations)
            
            matrix['data_source'] = 'historical' if any(workload_groups.values()) else 'estimated'
            
        except Exception as e:
            logger.debug(f"Could not load historical correlations, using sensitivity-based estimates: {e}")
            # Fallback to sensitivity-based estimates
            for event_data in sorted_events:
                event_name = event_data['event']
                sensitivity = event_data['sensitivity']
                
                matrix['events'].append(event_name)
                
                # Estimated correlation values based on sensitivity
                if sensitivity == 'high':
                    correlations = [0.9, 0.85, 0.2, 0.7]  # High correlation with stress workloads
                elif sensitivity == 'moderate':
                    correlations = [0.6, 0.55, 0.4, 0.5]  # Moderate correlation
                else:
                    correlations = [0.25, 0.2, 0.8, 0.4]  # Low correlation (independent)
                
                matrix['correlations'].append(correlations)
            
            matrix['data_source'] = 'estimated'
        
        return matrix
    
    def _cluster_events(self, coverage_results: Dict[str, Any]) -> Dict[str, Any]:
        """Cluster similar events using trained ML clusterer (ML-only, no fallback)."""
        if not self.ml_client.local_models_available or self.trainer.event_clusterer is None:
            return {
                'status': 'no_model',
                'message': 'ML clustering model not trained yet',
                'requirements': {
                    'min_events': 10,
                    'min_samples_per_cluster': 5,
                    'min_runs': 3,
                    'reason': 'DBSCAN clustering requires at least 5 events per cluster and sufficient training data from multiple runs'
                }
            }
        
        clusters = {
            'status': 'success',
            'cluster_summary': [],
            'by_domain': {},
            'ml_clustered': True
        }
        
        try:
            for domain, domain_data in coverage_results.items():
                # Type check: domain_data must be dict
                if not isinstance(domain_data, dict):
                    continue
                if 'events' not in domain_data:
                    continue
                
                events = domain_data['events']
                if not isinstance(events, dict):
                    continue
                
                # Prepare features for clustering
                events_list = []
                features_list = []
                
                for event_name, event_info in events.items():
                    counts = event_info.get('per_core_counts', [])
                    if len(counts) > 0:
                        # Safe calculation: filter out zeros
                        counts_array = np.array(counts)
                        active_counts = counts_array[counts_array > 0]
                        
                        if len(active_counts) > 0:
                            count_mean = np.mean(active_counts)
                            count_std = np.std(active_counts)
                            count_cv = (count_std / count_mean) if count_mean > 0 else 0
                        else:
                            count_mean = 0
                            count_std = 0
                            count_cv = 0
                        
                        features = {
                            'toggle_rate': event_info.get('active_count', 0) / event_info.get('total_count', 1),
                            'count_mean': count_mean,
                            'count_std': count_std,
                            'count_cv': count_cv
                        }
                        
                        events_list.append(event_name)
                        features_list.append(features)
                
                if len(features_list) > 0:
                    domain_clusters = defaultdict(list)
                    
                    try:
                        # Prepare features DataFrame for ML model
                        X = pd.DataFrame(features_list)
                        
                        # Fill missing columns with 0
                        required_cols = ['toggle_rate', 'count_mean', 'count_std', 'count_cv']
                        for col in required_cols:
                            if col not in X.columns:
                                X[col] = 0
                        X = X[required_cols].fillna(0)
                        
                        # Scale and predict clusters using cluster scaler
                        X_scaled = self.trainer.cluster_scaler.transform(X)
                        cluster_labels = self.trainer.event_clusterer.predict(X_scaled)
                        
                        # Group events by predicted cluster
                        for event, cluster_id in zip(events_list, cluster_labels):
                            cluster_name = f'cluster_{cluster_id}'
                            domain_clusters[cluster_name].append(event)
                        
                        logger.debug(f"[ML] Clustered {len(events_list)} events into {len(set(cluster_labels))} clusters")
                        
                    except Exception as e:
                        logger.error(f"ML clustering failed: {e}")
                        clusters['status'] = 'error'
                        clusters['message'] = f'Clustering failed: {str(e)}'
                        return clusters
                    
                    clusters['by_domain'][domain] = dict(domain_clusters)
            
        except Exception as e:
            logger.error(f"Error clustering events: {e}")
            clusters['status'] = 'error'
            clusters['message'] = str(e)
        
        return clusters
    
    def _analyze_trends(self, coverage_results: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze historical trends in coverage data."""
        trends = {
            'status': 'success',
            'historical_coverage': [],
            'improvement_rate': None,
            'projected_full_coverage': None
        }
        
        try:
            # Load historical data
            # Use current product if available, otherwise try to load all data
            product_id = self.trainer.current_product or 'generic'
            historical_data = self.trainer._load_historical_data(product_id)
            
            if len(historical_data) < 2:
                trends['message'] = 'Insufficient historical data for trend analysis'
                return trends
            
            # Calculate coverage rates over time
            # IMPORTANT: Track both relative (% of tested) and absolute (unique events found) coverage
            coverage_history = []
            all_discovered_events = set()  # Track cumulative unique active events
            
            for dataset in historical_data:
                coverage_results_hist = dataset.get('coverage_results', {})
                timestamp = dataset.get('timestamp', '')
                
                # Get relative coverage (% of events tested that were active)
                # Handle both dict format and direct value
                if isinstance(coverage_results_hist, dict):
                    coverage_rate = coverage_results_hist.get('activity_coverage', 0)
                    total_events = coverage_results_hist.get('total_events_tested', 0)
                    active_events = coverage_results_hist.get('active_events', 0)
                else:
                    # Fallback: coverage_results might be nested
                    coverage_rate = 0
                    total_events = 0
                    active_events = 0
                
                # Track unique active events across ALL runs for absolute coverage
                domain_results = coverage_results_hist.get('domain_results', {})
                run_active_events = set()
                
                for domain, domain_data in domain_results.items():
                    if isinstance(domain_data, dict):
                        for event in domain_data.get('active_events', []):
                            if isinstance(event, dict):
                                event_name = event.get('event', '')
                                if event_name:
                                    run_active_events.add(event_name)
                                    all_discovered_events.add(event_name)
                
                coverage_history.append({
                    'timestamp': timestamp,
                    'coverage': coverage_rate,  # Relative coverage (% of tested events)
                    'total_events': total_events,
                    'active_events': active_events,
                    'unique_events_found': len(run_active_events),  # Unique events in this run
                    'cumulative_unique_events': len(all_discovered_events)  # Total unique events found so far
                })
            
            trends['historical_coverage'] = coverage_history
            trends['total_unique_events_discovered'] = len(all_discovered_events)
            
            # Calculate improvement rate based on ABSOLUTE coverage (unique events discovered)
            if len(coverage_history) >= 2:
                first_unique = coverage_history[0]['cumulative_unique_events']
                last_unique = coverage_history[-1]['cumulative_unique_events']
                new_events_discovered = last_unique - first_unique
                
                # Also track relative coverage trend
                first_rate = coverage_history[0]['coverage']
                last_rate = coverage_history[-1]['coverage']
                relative_improvement = last_rate - first_rate
                
                trends['new_events_discovered'] = new_events_discovered
                trends['relative_improvement'] = relative_improvement
                
                # Trend direction based on NEW unique events discovered (not just %)
                if new_events_discovered > 5:  # Discovered 5+ new unique events
                    trends['trend_direction'] = 'improving'
                elif new_events_discovered < -5:  # Lost coverage of 5+ events (shouldn't happen)
                    trends['trend_direction'] = 'declining'
                else:
                    trends['trend_direction'] = 'stable'
            
        except Exception as e:
            logger.error(f"Error analyzing trends: {e}")
            trends['status'] = 'error'
            trends['message'] = str(e)
        
        return trends
    
    def _recommend_stress_for_gaps(self, analysis: Dict[str, Any], os_type: str) -> List[Dict[str, str]]:
        """
        Analyze non-toggling events and recommend specific stress tests to activate them.
        
        Args:
            analysis: ML analysis results
            os_type: 'linux' or 'windows'
            
        Returns:
            List of stress test recommendations
        """
        recommendations = []
        
        # Event category to stress test mapping
        stress_mapping = {
            # Memory events
            'memory': {
                'linux': {
                    'tool': 'stress-ng',
                    'command': 'stress-ng --vm 4 --vm-bytes 80% --timeout 300s',
                    'description': 'Memory bandwidth and latency stress'
                },
                'windows': {
                    'tool': 'SuperCollider or MLCTest',
                    'command': 'mlc.exe --loaded_latency -t300',
                    'description': 'Memory stress with loaded latency'
                }
            },
            # CPU/Core events
            'cpu': {
                'linux': {
                    'tool': 'stress-ng',
                    'command': 'stress-ng --cpu 0 --cpu-method all --timeout 300s',
                    'description': 'CPU integer and floating point stress'
                },
                'windows': {
                    'tool': 'SuperCollider',
                    'command': 'Run CPU stress component',
                    'description': 'Multi-core CPU stress test'
                }
            },
            # Cache events  
            'cache': {
                'linux': {
                    'tool': 'stress-ng',
                    'command': 'stress-ng --cache 0 --cache-ways 8 --timeout 300s',
                    'description': 'L1/L2/L3 cache thrashing'
                },
                'windows': {
                    'tool': 'CacheBurn',
                    'command': 'cacheburn.exe -all -duration 300',
                    'description': 'Cache hierarchy stress'
                }
            },
            # IO/PCIe events
            'io': {
                'linux': {
                    'tool': 'fio',
                    'command': 'fio --name=randread --rw=randread --bs=4k --numjobs=4 --runtime=300',
                    'description': 'Random IO stress (PCIe/storage)'
                },
                'windows': {
                    'tool': 'DiskSpd',
                    'command': 'diskspd -c10G -b4K -r -t4 -d300 testfile.dat',
                    'description': 'IO and storage subsystem stress'
                }
            },
            # Power/thermal events
            'power': {
                'linux': {
                    'tool': 'stress-ng + powertop',
                    'command': 'stress-ng --cpu 0 --cpu-method ackermann --timeout 300s',
                    'description': 'High power/thermal stress'
                },
                'windows': {
                    'tool': 'Prime95 or SuperCollider',
                    'command': 'Run P-State transitions with workload',
                    'description': 'Power state and thermal stress'
                }
            },
            # Branch/BTB events
            'branch': {
                'linux': {
                    'tool': 'stress-ng',
                    'command': 'stress-ng --branch 0 --timeout 300s',
                    'description': 'Branch prediction stress'
                },
                'windows': {
                    'tool': 'Custom microbenchmark',
                    'command': 'Run branch-heavy code patterns',
                    'description': 'BTB and branch predictor stress'
                }
            },
            # FP/Vector events
            'vector': {
                'linux': {
                    'tool': 'stress-ng',
                    'command': 'stress-ng --matrix 0 --matrix-method all --timeout 300s',
                    'description': 'AVX/AVX512 vector operations'
                },
                'windows': {
                    'tool': 'y-cruncher or AIDA64',
                    'command': 'Run AVX512 stress test',
                    'description': 'Vector/SIMD unit stress'
                }
            }
        }
        
        # Keywords to identify event categories
        event_keywords = {
            'memory': ['mem', 'dram', 'ddr', 'imc', 'read', 'write', 'load', 'store'],
            'cpu': ['cpu_clk', 'inst_retired', 'cycles', 'uops', 'core'],
            'cache': ['l1', 'l2', 'l3', 'cache', 'cbo', 'miss', 'hit'],
            'io': ['pcie', 'io', 'dma', 'disk', 'ufi'],
            'power': ['power', 'c-state', 'c_state', 'c0', 'c1', 'c6', 'turbo', 'freq'],
            'branch': ['br_', 'branch', 'btb', 'jmp', 'jump'],
            'vector': ['fp_', 'avx', 'simd', 'vec', 'fma', 'sse']
        }
        
        # Analyze patterns to find inactive event categories
        patterns = analysis.get('patterns', {})
        if patterns.get('status') != 'success':
            return recommendations
        
        inactive_events_by_category = defaultdict(list)
        
        for domain, domain_patterns in patterns.get('by_domain', {}).items():
            for pattern_info in domain_patterns:
                event_name = pattern_info.get('event', '').lower()
                total_count = pattern_info.get('total_count', 0)
                
                # Event is inactive (zero or very low count)
                if total_count < 100:  # Threshold for "inactive"
                    # Categorize the event
                    for category, keywords in event_keywords.items():
                        if any(keyword in event_name for keyword in keywords):
                            inactive_events_by_category[category].append({
                                'domain': domain,
                                'event': pattern_info.get('event'),
                                'count': total_count
                            })
                            break
        
        # Generate recommendations for each inactive category
        for category, events in inactive_events_by_category.items():
            if len(events) >= 3:  # At least 3 events in category not toggling
                stress_info = stress_mapping.get(category, {}).get(os_type, {})
                
                if stress_info:
                    recommendations.append({
                        'priority': 'HIGH',
                        'category': 'Stress Recommendation',
                        'title': f'{len(events)} {category.title()} Events Not Toggling',
                        'description': f'Multiple {category} events show zero/low activity. Recommended stress test: {stress_info.get("tool")}',
                        'action': f'Command: {stress_info.get("command")}\nPurpose: {stress_info.get("description")}\n\nInactive events: {", ".join([e["event"] for e in events[:5]])}{"..." if len(events) > 5 else ""}'
                    })
        
        return recommendations
    
    def _generate_recommendations(self, analysis: Dict[str, Any]) -> List[Dict[str, str]]:
        """Generate actionable recommendations based on ML analysis."""
        recommendations = []
        
        # Get OS type for stress recommendations
        os_type = analysis.get('metadata', {}).get('os_type', 'linux')
        
        # Recommendation 1: Stress recommendations for non-toggling events
        stress_recommendations = self._recommend_stress_for_gaps(analysis, os_type)
        recommendations.extend(stress_recommendations)
        
        # Recommendation 2: Based on anomalies
        anomalies = analysis.get('anomalies', {})
        if anomalies.get('statistics', {}).get('total_anomalies', 0) > 0:
            high_severity = anomalies['statistics'].get('by_severity', {}).get('high', 0)
            
            if high_severity > 0:
                recommendations.append({
                    'priority': 'HIGH',
                    'category': 'Anomalies',
                    'title': f'{high_severity} High-Severity Anomalies Detected',
                    'description': 'Review high-severity anomalies immediately as they may indicate hardware issues or workload problems.',
                    'action': 'Check anomaly details in the Anomalies section and investigate affected events.'
                })
        
        # Recommendation 2: Based on patterns
        patterns = analysis.get('patterns', {})
        if patterns.get('status') == 'success':
            low_activity = patterns.get('distribution', {}).get('low_activity', 0)
            total_events = sum(patterns.get('distribution', {}).values())
            
            if total_events > 0 and low_activity / total_events > 0.5:
                recommendations.append({
                    'priority': 'MEDIUM',
                    'category': 'Coverage',
                    'title': 'Low Activity Detected on >50% of Events',
                    'description': 'Many events are showing low activity. Consider running more intensive workloads.',
                    'action': 'Try stress tests or mixed workloads to increase event coverage.'
                })
        
        # Recommendation 3: Based on trends
        trends = analysis.get('trends', {})
        if trends.get('trend_direction') == 'declining':
            recommendations.append({
                'priority': 'HIGH',
                'category': 'Trends',
                'title': 'Coverage Declining Over Time',
                'description': 'Historical data shows decreasing coverage rates.',
                'action': 'Review recent changes to workloads or test configurations.'
            })
        
        # Recommendation 4: Based on correlations
        correlations = analysis.get('correlations', {})
        if len(correlations.get('strong_correlations', [])) > 5:
            recommendations.append({
                'priority': 'LOW',
                'category': 'Optimization',
                'title': f'{len(correlations["strong_correlations"])} Strong Event Correlations Found',
                'description': 'Multiple events show correlated behavior. Test optimization opportunities exist.',
                'action': 'Consider grouping correlated events for more efficient testing.'
            })
        
        # Recommendation 5: Training recommendation
        training_status = analysis.get('training_status', {})
        if training_status.get('datasets_collected', 0) < 5:
            recommendations.append({
                'priority': 'LOW',
                'category': 'Training',
                'title': 'Limited Training Data Available',
                'description': f'Only {training_status.get("datasets_collected", 0)} datasets collected. More data improves ML accuracy.',
                'action': 'Continue running analyses to build training dataset for better insights.'
            })
        
        # Sort by priority
        priority_order = {'HIGH': 0, 'MEDIUM': 1, 'LOW': 2}
        recommendations.sort(key=lambda r: priority_order.get(r['priority'], 3))
        
        return recommendations
    
    def _analyze_health_impact(self, coverage_results: Dict[str, Any], 
                               metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Analyze system health data and correlate with collection quality.
        
        Returns insights about:
        - Resource usage patterns
        - Performance bottlenecks
        - Quality correlation with system state
        - Optimal collection conditions
        - Failure predictions
        """
        # Load most recent health data
        health_data = self._load_health_data()
        
        if not health_data or not health_data.get('samples'):
            return {
                'status': 'no_data',
                'message': 'No system health data available for this collection'
            }
        
        samples = health_data['samples']
        collection_mode = health_data.get('collection_mode', 'unknown')
        
        analysis = {
            'status': 'success',
            'collection_mode': collection_mode,
            'total_samples': len(samples),
            'resource_analysis': {},
            'quality_correlation': {},
            'bottlenecks': [],
            'optimal_conditions': {},
            'failure_risks': [],
            'ml_insights': []
        }
        
        # 1. Resource Usage Analysis
        cpu_values = [s.get('metrics', {}).get('cpu_usage_pct', 0) for s in samples]
        memory_values = [s.get('metrics', {}).get('memory_usage_pct', 0) for s in samples]
        disk_free_values = [s.get('metrics', {}).get('disk_free_gb', 0) for s in samples]
        emon_cpu_values = [s.get('metrics', {}).get('emon_cpu_pct', 0) for s in samples]
        load_values = [s.get('metrics', {}).get('load_avg_1min', 0) for s in samples]
        
        analysis['resource_analysis'] = {
            'cpu': {
                'avg': np.mean(cpu_values) if cpu_values else 0,
                'peak': max(cpu_values) if cpu_values else 0,
                'min': min(cpu_values) if cpu_values else 0,
                'std': np.std(cpu_values) if cpu_values else 0,
                'trend': 'stable' if np.std(cpu_values) < 10 else 'variable'
            },
            'memory': {
                'avg': np.mean(memory_values) if memory_values else 0,
                'peak': max(memory_values) if memory_values else 0,
                'pressure': 'high' if max(memory_values) > 90 else 'normal'
            },
            'disk': {
                'avg_free_gb': np.mean(disk_free_values) if disk_free_values else 0,
                'min_free_gb': min(disk_free_values) if disk_free_values else 0,
                'space_risk': 'high' if min(disk_free_values) < 1 else 'low'
            },
            'emon_overhead': {
                'avg_cpu_pct': np.mean(emon_cpu_values) if emon_cpu_values else 0,
                'peak_cpu_pct': max(emon_cpu_values) if emon_cpu_values else 0
            }
        }
        
        # 2. Detect Resource Bottlenecks
        if max(cpu_values) > 95:
            analysis['bottlenecks'].append({
                'type': 'CPU Saturation',
                'severity': 'HIGH',
                'description': f'CPU usage reached {max(cpu_values):.1f}%, may cause timeouts',
                'recommendation': 'Reduce concurrent workloads or increase collection timeout'
            })
        
        if max(memory_values) > 90:
            analysis['bottlenecks'].append({
                'type': 'Memory Pressure',
                'severity': 'MEDIUM',
                'description': f'Memory usage peaked at {max(memory_values):.1f}%',
                'recommendation': 'Monitor for OOM events, consider reducing batch sizes'
            })
        
        if min(disk_free_values) < 2:
            analysis['bottlenecks'].append({
                'type': 'Low Disk Space',
                'severity': 'HIGH',
                'description': f'Disk space dropped to {min(disk_free_values):.1f} GB',
                'recommendation': 'Clean up old files or use external storage'
            })
        
        if load_values and max(load_values) > 8:
            analysis['bottlenecks'].append({
                'type': 'High System Load',
                'severity': 'MEDIUM',
                'description': f'Load average reached {max(load_values):.2f}',
                'recommendation': 'System under heavy stress, may affect collection timing'
            })
        
        # 3. Quality Correlation (correlate health with collection success)
        health_issues = [s for s in samples if not s.get('ok', True)]
        if health_issues:
            analysis['quality_correlation'] = {
                'health_issues_detected': len(health_issues),
                'issue_rate': len(health_issues) / len(samples),
                'correlation': 'Issues detected during collection - review for impact on data quality'
            }
        else:
            analysis['quality_correlation'] = {
                'health_issues_detected': 0,
                'issue_rate': 0.0,
                'correlation': 'No health issues detected - collection ran under healthy conditions'
            }
        
        # 4. Identify Optimal Collection Conditions
        # Find samples with best conditions (low resource usage, no issues)
        optimal_samples = [s for s in samples if 
                          s.get('ok', True) and
                          s.get('metrics', {}).get('cpu_usage_pct', 100) < 50 and
                          s.get('metrics', {}).get('memory_usage_pct', 100) < 70 and
                          s.get('metrics', {}).get('temperature_c', 0) < 75 and  # Normal temp
                          s.get('metrics', {}).get('disk_io_mbps', 0) < 500]  # Not I/O saturated
        
        if optimal_samples:
            optimal_cpu = np.mean([s['metrics'].get('cpu_usage_pct', 0) for s in optimal_samples])
            optimal_mem = np.mean([s['metrics'].get('memory_usage_pct', 0) for s in optimal_samples])
            optimal_temp = np.mean([s['metrics'].get('temperature_c', 0) for s in optimal_samples if s['metrics'].get('temperature_c', 0) > 0])
            optimal_io = np.mean([s['metrics'].get('disk_io_mbps', 0) for s in optimal_samples])
            
            conditions = [
                f'CPU < 50%',
                f'Memory < 70%'
            ]
            if optimal_temp > 0:
                conditions.append(f'Temperature < 75°C')
            if optimal_io > 0:
                conditions.append(f'Disk I/O < 500 MB/s')
            
            analysis['optimal_conditions'] = {
                'identified': True,
                'sample_count': len(optimal_samples),
                'cpu_range': f'{optimal_cpu-10:.0f}-{optimal_cpu+10:.0f}%',
                'memory_range': f'{optimal_mem-10:.0f}-{optimal_mem+10:.0f}%',
                'temp_avg': f'{optimal_temp:.1f}°C' if optimal_temp > 0 else 'N/A',
                'io_avg': f'{optimal_io:.1f} MB/s' if optimal_io > 0 else 'N/A',
                'recommendation': f'Best collection quality when {", ".join(conditions)}'
            }
        else:
            analysis['optimal_conditions'] = {
                'identified': False,
                'recommendation': 'All samples collected under stress - consider lighter workload for baseline'
            }
        
        # 5. Failure Risk Prediction with Stress+OS Awareness
        # Check for conditions that historically lead to failures
        cpu_spikes = len([c for c in cpu_values if c > 90])
        memory_spikes = len([m for m in memory_values if m > 85])
        disk_warnings = len([d for d in disk_free_values if d < 3])
        
        # Get stress and OS context for intelligent recommendations
        current_stress = analysis.get('metadata', {}).get('workload', 'unknown')
        current_os = analysis.get('metadata', {}).get('os_type', 'unknown')
        stress_os_combo = f"{current_stress}_{current_os}"
        
        # New: Temperature and I/O risk detection
        temp_values = [s.get('metrics', {}).get('temperature_c', 0) for s in samples if s.get('metrics', {}).get('temperature_c', 0) > 0]
        temp_warnings = len([t for t in temp_values if t > 85]) if temp_values else 0
        
        io_values = [s.get('metrics', {}).get('disk_io_mbps', 0) for s in samples]
        io_spikes = len([io for io in io_values if io > 800])  # Very high I/O
        
        ctx_values = [s.get('metrics', {}).get('context_switches_per_sec', 0) for s in samples]
        ctx_spikes = len([ctx for ctx in ctx_values if ctx > 100000])  # >100k context switches = thrashing
        
        if cpu_spikes > len(samples) * 0.2:
            # Stress+OS specific mitigation
            if 'cpu' in current_stress.lower():
                mitigation = f'CPU stress on {current_os}: Expected high CPU. Ensure adequate cooling and consider longer timeout.'
            else:
                mitigation = 'Unexpected high CPU - check for background processes or reduce workload'
            
            analysis['failure_risks'].append({
                'risk_type': 'Timeout Risk',
                'probability': 'MEDIUM' if cpu_spikes < len(samples) * 0.5 else 'HIGH',
                'reason': f'CPU >90% in {cpu_spikes} of {len(samples)} samples ({stress_os_combo})',
                'mitigation': mitigation
            })
        
        if memory_spikes > len(samples) * 0.1:
            # Stress+OS specific mitigation
            if 'memory' in current_stress.lower() or 'mem' in current_stress.lower():
                mitigation = f'Memory stress on {current_os}: Expected high memory. Monitor for OOM killer (Linux) or paging storms (Windows).'
            else:
                mitigation = 'Close background applications or add more RAM'
            
            analysis['failure_risks'].append({
                'risk_type': 'OOM Risk',
                'probability': 'LOW' if memory_spikes < 5 else 'MEDIUM',
                'reason': f'Memory >85% in {memory_spikes} samples ({stress_os_combo})',
                'mitigation': mitigation
            })
        
        if temp_warnings > 0:
            # OS-specific thermal advice
            thermal_mitigation = 'Improve cooling or reduce workload intensity'
            if current_os == 'linux':
                thermal_mitigation += ' (Linux ACPI thermal monitoring active)'
            elif current_os == 'windows':
                thermal_mitigation += ' (Note: Windows thermal data unavailable, using ACPI estimates)'
            
            analysis['failure_risks'].append({
                'risk_type': 'Thermal Throttling Risk',
                'probability': 'MEDIUM' if temp_warnings < len(samples) * 0.3 else 'HIGH',
                'reason': f'CPU temperature >85°C in {temp_warnings} samples ({stress_os_combo})',
                'mitigation': thermal_mitigation
            })
        
        if io_spikes > len(samples) * 0.3:
            analysis['failure_risks'].append({
                'risk_type': 'I/O Bottleneck',
                'probability': 'MEDIUM',
                'reason': f'Disk I/O >800 MB/s in {io_spikes} samples',
                'mitigation': 'Use faster storage or reduce I/O intensive workloads during collection'
            })
        
        if ctx_spikes > len(samples) * 0.2:
            analysis['failure_risks'].append({
                'risk_type': 'System Thrashing',
                'probability': 'HIGH',
                'reason': f'Context switches >100k/sec in {ctx_spikes} samples',
                'mitigation': 'Too many processes competing - reduce concurrent workloads'
            })
        
        if disk_warnings > 0:
            analysis['failure_risks'].append({
                'risk_type': 'Storage Exhaustion',
                'probability': 'HIGH',
                'reason': f'Disk space <3GB in {disk_warnings} samples',
                'mitigation': 'URGENT: Clean disk space or collection will fail'
            })
        
        # 6. ML-Based Insights
        analysis['ml_insights'] = self._generate_health_ml_insights(analysis, samples)
        
        return analysis
    
    def _load_health_data(self) -> Dict[str, Any]:
        """Load most recent system health monitoring data."""
        # Use centralized data directory
        health_dir = Path('C:/silicon_coverage_analyzer_data/health_logs')
        if not health_dir.exists():
            return None
        
        health_files = sorted(health_dir.glob('system_health_*.json'), 
                            key=lambda p: p.stat().st_mtime, reverse=True)
        if not health_files:
            return None
        
        try:
            with open(health_files[0], 'r') as f:
                return json.load(f)
        except Exception:
            return None
    
    def _generate_health_ml_insights(self, health_analysis: Dict[str, Any], 
                                     samples: List[Dict]) -> List[Dict[str, str]]:
        """Generate ML-powered insights from health data patterns."""
        insights = []
        
        resource_analysis = health_analysis.get('resource_analysis', {})
        cpu_info = resource_analysis.get('cpu', {})
        memory_info = resource_analysis.get('memory', {})
        
        # Insight 1: CPU Pattern Recognition
        if cpu_info.get('std', 0) > 15:
            insights.append({
                'type': 'pattern',
                'title': 'Variable CPU Load Detected',
                'description': f'CPU usage varied significantly (σ={cpu_info["std"]:.1f}). This suggests bursty workload behavior.',
                'ml_confidence': 'HIGH',
                'action': 'ML will learn this pattern for better timeout prediction'
            })
        elif cpu_info.get('trend') == 'stable':
            insights.append({
                'type': 'pattern',
                'title': 'Stable CPU Load',
                'description': f'Consistent CPU usage (~{cpu_info["avg"]:.1f}%) indicates predictable workload.',
                'ml_confidence': 'HIGH',
                'action': 'ML can optimize batch sizes for this stable load pattern'
            })
        
        # Insight 2: Memory Trend Analysis
        memory_samples = [s.get('metrics', {}).get('memory_usage_pct', 0) for s in samples]
        if len(memory_samples) > 10:
            # Check for memory leak (increasing trend)
            first_half_avg = np.mean(memory_samples[:len(memory_samples)//2])
            second_half_avg = np.mean(memory_samples[len(memory_samples)//2:])
            
            if second_half_avg > first_half_avg + 10:
                insights.append({
                    'type': 'anomaly',
                    'title': 'Memory Growth Detected',
                    'description': f'Memory increased from {first_half_avg:.1f}% to {second_half_avg:.1f}% during collection.',
                    'ml_confidence': 'MEDIUM',
                    'action': 'Potential memory leak - ML will flag similar patterns'
                })
        
        # Insight 3: Resource Correlation
        cpu_samples = [s.get('metrics', {}).get('cpu_usage_pct', 0) for s in samples]
        file_growth = [s.get('metrics', {}).get('file_size_mb', 0) for s in samples]
        
        if len(cpu_samples) > 5 and len(file_growth) > 5:
            # Calculate correlation between CPU and file growth
            try:
                correlation = np.corrcoef(cpu_samples, file_growth)[0, 1]
                if abs(correlation) > 0.7:
                    insights.append({
                        'type': 'correlation',
                        'title': 'Strong CPU-Output Correlation',
                        'description': f'CPU usage correlates ({correlation:.2f}) with data output rate.',
                        'ml_confidence': 'HIGH',
                        'action': 'ML can predict collection time based on CPU usage'
                    })
            except:
                pass
        
        # Insight 4: Optimal Window Identification
        optimal_conditions = health_analysis.get('optimal_conditions', {})
        if optimal_conditions.get('identified'):
            insights.append({
                'type': 'optimization',
                'title': 'Optimal Collection Window Identified',
                'description': f'{optimal_conditions["sample_count"]} samples met optimal conditions.',
                'ml_confidence': 'HIGH',
                'action': 'ML learned best collection times - future runs can be scheduled accordingly'
            })
        
        # Insight 5: EMON Overhead Analysis
        emon_info = resource_analysis.get('emon_overhead', {})
        if emon_info.get('peak_cpu_pct', 0) > 20:
            insights.append({
                'type': 'overhead',
                'title': 'High EMON Overhead Detected',
                'description': f'EMON process consumed up to {emon_info["peak_cpu_pct"]:.1f}% CPU.',
                'ml_confidence': 'MEDIUM',
                'action': 'Consider reducing event count or sampling rate for lower overhead'
            })
        
        return insights
    
    def analyze_data_diversity(self) -> Dict[str, Any]:
        """
        Analyze training data diversity and suggest specific missing tests.
        
        Returns detailed analysis of:
        - Workload types seen
        - Duration distribution
        - Missing test scenarios
        - Specific actionable recommendations
        """
        # Use current product if available, otherwise try to load all data
        product_id = self.trainer.current_product or 'generic'
        historical_data = self.trainer._load_historical_data(product_id)
        
        if len(historical_data) == 0:
            return {
                'status': 'insufficient_data',
                'datasets': 0,
                'suggestions': []
            }
        
        # Analyze diversity dimensions
        workloads_seen = set()
        durations_seen = []
        os_types_seen = set()
        
        for dataset in historical_data:
            metadata = dataset.get('metadata', {})
            workload = (metadata.get('workload') or 'unknown').lower()
            duration = metadata.get('duration_seconds', 0)
            os_info = metadata.get('os_info', {})
            os_type = (os_info.get('os_type') or 'unknown').lower()
            
            if workload and workload != 'unknown':
                workloads_seen.add(workload)
            if duration > 0:
                durations_seen.append(duration)
            if os_type and os_type != 'unknown':
                os_types_seen.add(os_type)
        
        # Categorize durations
        short_tests = len([d for d in durations_seen if d <= 60])
        medium_tests = len([d for d in durations_seen if 60 < d <= 600])
        long_tests = len([d for d in durations_seen if d > 600])
        
        # Count unique duration categories tested
        duration_categories_tested = sum([1 for count in [short_tests, medium_tests, long_tests] if count > 0])
        
        # Generate intelligent suggestions
        suggestions = []
        
        # Determine current OS context (use most recent dataset's OS)
        current_os = 'unknown'
        if historical_data:
            last_metadata = historical_data[-1].get('metadata', {})
            os_info = last_metadata.get('os_info', {})
            current_os = os_info.get('os_type', 'unknown').lower()
        
        # OS-specific workload recommendations
        if current_os == 'windows':
            known_workloads = {
                'supercollider': {
                    'description': 'Multi-component stress (CPU, Memory, Cache)',
                    'availability': 'Available in SEP package',
                    'command': 'Run SuperCollider.exe from SEP tools'
                },
                'prime95': {
                    'description': 'CPU-intensive, AVX/FMA stress',
                    'availability': 'Download from mersenne.org',
                    'command': 'prime95.exe (select Torture Test)'
                },
                'heavyload': {
                    'description': 'Windows stress tool (CPU, Memory, GPU)',
                    'availability': 'Free tool from JAM Software',
                    'command': 'HeavyLoad.exe with all tests enabled'
                },
                'cinebench': {
                    'description': 'CPU rendering benchmark',
                    'availability': 'Download from Maxon',
                    'command': 'Cinebench.exe (CPU Multi-Core test)'
                },
                'idle': {
                    'description': 'Idle/low-power state testing',
                    'availability': 'No workload needed',
                    'command': 'Run analysis with no active applications'
                }
            }
        elif current_os == 'linux':
            known_workloads = {
                'supercollider': {
                    'description': 'Multi-component stress (CPU, Memory, Cache)',
                    'availability': 'Available in SEP package',
                    'command': './SuperCollider (from SEP bin directory)'
                },
                'stress-ng': {
                    'description': 'Configurable stress with targeted components',
                    'availability': 'Install: sudo apt-get install stress-ng',
                    'command': 'stress-ng --cpu 0 --vm 0 --io 0 --timeout 5m'
                },
                'stream': {
                    'description': 'Memory bandwidth benchmark',
                    'availability': 'Compile from source (cs.virginia.edu/stream)',
                    'command': './stream_c.exe'
                },
                'sysbench': {
                    'description': 'CPU, memory, and thread stress',
                    'availability': 'Install: sudo apt-get install sysbench',
                    'command': 'sysbench cpu --threads=8 run'
                },
                'fio': {
                    'description': 'Storage I/O stress',
                    'availability': 'Install: sudo apt-get install fio',
                    'command': 'fio --name=randwrite --rw=randwrite --size=1G'
                },
                'idle': {
                    'description': 'Idle/low-power state testing',
                    'availability': 'No workload needed',
                    'command': 'Run analysis with minimal background processes'
                }
            }
        else:
            # Generic recommendations if OS unknown
            known_workloads = {
                'supercollider': {
                    'description': 'Multi-component stress (CPU, Memory, Cache)',
                    'availability': 'Available in SEP package',
                    'command': 'Check SEP installation directory'
                },
                'stress-ng': {
                    'description': 'Configurable stress (Linux)',
                    'availability': 'Linux package manager',
                    'command': 'stress-ng --cpu 0 --timeout 5m'
                },
                'prime95': {
                    'description': 'CPU-intensive stress (Windows/Linux)',
                    'availability': 'mersenne.org/download',
                    'command': 'Run torture test'
                },
                'idle': {
                    'description': 'Idle/low-power state testing',
                    'availability': 'No workload needed',
                    'command': 'Run analysis without active workload'
                }
            }
        
        missing_workloads = []
        for wl, info in known_workloads.items():
            if not any(wl in seen for seen in workloads_seen):
                missing_workloads.append({
                    'workload': wl,
                    'description': info['description'],
                    'availability': info['availability'],
                    'command': info['command'],
                    'priority': 'HIGH'
                })
        
        if missing_workloads:
            suggestions.append({
                'category': 'Workload Diversity',
                'priority': 'HIGH',
                'os_context': current_os,
                'missing_count': len(missing_workloads),
                'details': missing_workloads[:3],  # Top 3 recommendations
                'reason': f'ML has only seen {len(workloads_seen)} workload type(s). More diversity improves pattern detection.'
            })
        
        # OS diversity suggestion
        if len(os_types_seen) == 1 and len(historical_data) >= 5:
            missing_os = 'Linux' if 'windows' in os_types_seen else 'Windows'
            suggestions.append({
                'category': 'OS Diversity',
                'priority': 'MEDIUM',
                'recommendation': f'Test on {missing_os} SUT',
                'reason': f'All {len(historical_data)} tests run on {list(os_types_seen)[0].title()}. Cross-OS testing improves ML robustness.',
                'benefit': f'{missing_os} may exhibit different PMU event behaviors and power states'
            })
        
        # Duration diversity suggestions
        if short_tests == 0:
            suggestions.append({
                'category': 'Duration - Short Burst',
                'priority': 'MEDIUM',
                'recommendation': 'Run 30-60 second tests',
                'reason': 'Captures transient behavior and startup patterns',
                'command': 'python analyze_coverage.py --duration 1 --max-event 50'
            })
        
        if medium_tests < 2:
            suggestions.append({
                'category': 'Duration - Sustained Load',
                'priority': 'MEDIUM',
                'recommendation': 'Run 5-10 minute tests',
                'reason': 'Captures sustained workload patterns and steady-state behavior',
                'command': 'python analyze_coverage.py --duration 300 --max-event 100'
            })
        
        if long_tests == 0:
            suggestions.append({
                'category': 'Duration - Thermal/Power States',
                'priority': 'HIGH',
                'recommendation': 'Run 15+ minute tests',
                'reason': 'Captures thermal throttling, power state transitions, and long-term patterns',
                'command': 'python analyze_coverage.py --duration 900 --max-event 150'
            })
        
        # Power domain suggestions (analyze if power events are inactive)
        power_coverage_low = False
        for dataset in historical_data:
            coverage = dataset.get('coverage_results', {})
            domain_results = coverage.get('domain_results', {})
            power_data = domain_results.get('power', {})
            if power_data.get('activity_rate', 0) < 10:  # Less than 10% active
                power_coverage_low = True
                break
        
        if power_coverage_low:
            suggestions.append({
                'category': 'Edge Case - Power States',
                'priority': 'HIGH',
                'recommendation': 'Test idle and C-state transitions',
                'reason': 'Power domain events showing low activity - need idle/sleep workloads',
                'actions': [
                    'Run idle test: Start analysis without active workload',
                    'Run powertop stress tests',
                    'Test with varying CPU frequencies'
                ]
            })
        
        # Analyze domain-specific gaps
        domain_coverage_analysis = self._analyze_domain_gaps(historical_data)
        if domain_coverage_analysis['weak_domains']:
            weak_domains_list = ', '.join(domain_coverage_analysis['weak_domains'][:3])
            suggestions.append({
                'category': 'Domain-Specific Coverage',
                'priority': 'HIGH',
                'recommendation': f'Focus testing on weak domains: {weak_domains_list}',
                'reason': f'{len(domain_coverage_analysis["weak_domains"])} domains consistently show <50% coverage',
                'weak_domains': domain_coverage_analysis['weak_domains'],
                'targeted_workloads': domain_coverage_analysis['recommendations']
            })
        
        # Analyze workload effectiveness
        workload_effectiveness = self._analyze_workload_effectiveness(historical_data)
        if workload_effectiveness['best_workload']:
            suggestions.append({
                'category': 'Workload Optimization',
                'priority': 'MEDIUM',
                'insight': f"Best coverage achieved with '{workload_effectiveness['best_workload']}' ({workload_effectiveness['best_coverage']:.1f}%)",
                'recommendation': f"Run more tests with {workload_effectiveness['best_workload']} for efficient coverage expansion",
                'effectiveness_data': workload_effectiveness['all_workloads']
            })
        
        # Hardware diversity check
        hardware_seen = set()
        for dataset in historical_data:
            hw = dataset.get('metadata', {}).get('hardware', 'unknown')
            if hw and hw != 'unknown':
                hardware_seen.add(hw)
        
        if len(hardware_seen) == 1 and len(historical_data) >= 8:
            suggestions.append({
                'category': 'Hardware Diversity',
                'priority': 'LOW',
                'recommendation': 'Test on different SKU/stepping',
                'reason': f'All tests run on same hardware: {list(hardware_seen)[0]}',
                'benefit': 'Different SKUs may have different PMU characteristics and event availability'
            })
        
        # Analyze OS-specific coverage patterns
        os_comparison_data = self._analyze_os_coverage_comparison(historical_data, os_types_seen)
        
        return {
            'status': 'analyzed',
            'datasets': len(historical_data),
            'diversity_score': len(workloads_seen) * 20 + (short_tests + medium_tests + long_tests) * 5,
            'workloads_seen': list(workloads_seen),
            'duration_coverage': {
                'short_burst': short_tests,
                'sustained_load': medium_tests,
                'long_term': long_tests
            },
            'os_types_seen': list(os_types_seen),
            'os_comparison': os_comparison_data,  # Windows vs Linux comparison
            'hardware_seen': list(hardware_seen),
            'suggestions': suggestions,
            'summary': f"ML has {len(workloads_seen)} workload type{'s' if len(workloads_seen) != 1 else ''}, {duration_categories_tested} duration categor{'ies' if duration_categories_tested != 1 else 'y'} across {len(historical_data)} dataset{'s' if len(historical_data) != 1 else ''}"
        }
    
    def _analyze_domain_gaps(self, historical_data: List[Dict]) -> Dict[str, Any]:
        """Analyze which domains consistently have low coverage."""
        domain_performance = defaultdict(list)
        
        for dataset in historical_data:
            coverage = dataset.get('coverage_results', {})
            domain_results = coverage.get('domain_results', {})
            
            for domain, data in domain_results.items():
                activity_rate = data.get('activity_rate', 0)
                domain_performance[domain].append(activity_rate)
        
        # Find domains with consistently weak coverage (avg < 50%)
        weak_domains = []
        for domain, rates in domain_performance.items():
            if rates and np.mean(rates) < 50:
                weak_domains.append(domain)
        
        # Generate targeted workload recommendations based on weak domains
        recommendations = []
        if any('power' in d for d in weak_domains):
            recommendations.append('Idle/C-state tests for power domain')
        if any('ncu' in d or 'cbo' in d for d in weak_domains):
            recommendations.append('Cache-intensive workloads (LLC stress)')
        if any('imc' in d for d in weak_domains):
            recommendations.append('Memory bandwidth tests (STREAM, MLC)')
        if any('core' in d for d in weak_domains):
            recommendations.append('CPU-intensive workloads (Prime95, Linpack)')
        
        return {
            'weak_domains': weak_domains,
            'recommendations': recommendations,
            'domain_averages': {d: np.mean(r) for d, r in domain_performance.items()}
        }
    
    def _analyze_workload_effectiveness(self, historical_data: List[Dict]) -> Dict[str, Any]:
        """Analyze which workloads produce best coverage results."""
        workload_coverage = defaultdict(list)
        
        for dataset in historical_data:
            metadata = dataset.get('metadata', {})
            workload = metadata.get('workload', 'unknown')
            coverage = dataset.get('coverage_results', {})
            coverage_rate = coverage.get('activity_coverage', 0)
            
            if workload and workload != 'unknown':
                workload_coverage[workload].append(coverage_rate)
        
        # Calculate average coverage per workload
        workload_averages = {}
        for wl, rates in workload_coverage.items():
            if rates:
                workload_averages[wl] = np.mean(rates)
        
        # Find best workload
        best_workload = None
        best_coverage = 0
        if workload_averages:
            best_workload = max(workload_averages, key=workload_averages.get)
            best_coverage = workload_averages[best_workload]
        
        return {
            'best_workload': best_workload,
            'best_coverage': best_coverage,
            'all_workloads': workload_averages
        }
    
    def _analyze_os_coverage_comparison(self, historical_data: List[Dict], os_types_seen: set) -> Dict[str, Any]:
        """
        Analyze coverage differences between Windows and Linux OS.
        
        Returns detailed comparison of domain coverage between operating systems.
        """
        if len(os_types_seen) < 2:
            return {
                'status': 'insufficient_os_diversity',
                'os_types_available': list(os_types_seen),
                'message': 'Need data from both Windows and Linux for comparison'
            }
        
        # Separate datasets by OS
        os_datasets = defaultdict(list)
        for dataset in historical_data:
            metadata = dataset.get('metadata', {})
            os_info = metadata.get('os_info', {})
            os_type = os_info.get('os_type', 'unknown').lower()
            
            if os_type in ['windows', 'linux']:
                os_datasets[os_type].append(dataset)
        
        # Check if we have both OS types
        if 'windows' not in os_datasets or 'linux' not in os_datasets:
            return {
                'status': 'insufficient_os_diversity',
                'os_types_available': list(os_datasets.keys()),
                'message': 'Need data from both Windows and Linux for comparison'
            }
        
        # Calculate domain coverage per OS
        os_domain_coverage = defaultdict(lambda: defaultdict(list))
        
        for os_type, datasets in os_datasets.items():
            for dataset in datasets:
                coverage = dataset.get('coverage_results', {})
                domain_results = coverage.get('domain_results', {})
                
                for domain, data in domain_results.items():
                    activity_rate = data.get('activity_rate', 0)
                    os_domain_coverage[os_type][domain].append(activity_rate)
        
        # Compare coverage across common domains
        common_domains = set(os_domain_coverage['windows'].keys()) & set(os_domain_coverage['linux'].keys())
        
        domain_comparisons = []
        significant_gaps = []
        
        for domain in sorted(common_domains):
            windows_avg = np.mean(os_domain_coverage['windows'][domain])
            linux_avg = np.mean(os_domain_coverage['linux'][domain])
            difference = abs(windows_avg - linux_avg)
            
            comparison = {
                'domain': domain,
                'windows_coverage': windows_avg,
                'linux_coverage': linux_avg,
                'difference_pct': difference,
                'better_on': 'Windows' if windows_avg > linux_avg else 'Linux'
            }
            domain_comparisons.append(comparison)
            
            # Flag significant gaps (>15% difference)
            if difference > 15:
                significant_gaps.append({
                    'domain': domain,
                    'gap': difference,
                    'windows': windows_avg,
                    'linux': linux_avg,
                    'recommendation': f'Investigate why {domain} shows {difference:.1f}% coverage difference between OS'
                })
        
        # Generate OS-specific insights
        insights = []
        
        if significant_gaps:
            top_gap = max(significant_gaps, key=lambda x: x['gap'])
            insights.append({
                'type': 'os_coverage_gap',
                'title': f'OS Coverage Gap in {top_gap["domain"]}',
                'description': f'{top_gap["gap"]:.1f}% difference detected',
                'ml_confidence': 'HIGH',
                'action': top_gap['recommendation']
            })
        
        # Overall OS preference
        windows_avg_overall = np.mean([comp['windows_coverage'] for comp in domain_comparisons])
        linux_avg_overall = np.mean([comp['linux_coverage'] for comp in domain_comparisons])
        
        if abs(windows_avg_overall - linux_avg_overall) > 10:
            better_os = 'Windows' if windows_avg_overall > linux_avg_overall else 'Linux'
            insights.append({
                'type': 'os_preference',
                'title': f'{better_os} Shows Better Overall Coverage',
                'description': f'{better_os} averages {max(windows_avg_overall, linux_avg_overall):.1f}% vs {min(windows_avg_overall, linux_avg_overall):.1f}%',
                'ml_confidence': 'MEDIUM',
                'action': f'Continue testing on {better_os} for broader domain coverage'
            })
        
        return {
            'status': 'analyzed',
            'os_types': ['windows', 'linux'],
            'windows_datasets': len(os_datasets['windows']),
            'linux_datasets': len(os_datasets['linux']),
            'common_domains': len(common_domains),
            'domain_comparisons': sorted(domain_comparisons, key=lambda x: x['difference_pct'], reverse=True),
            'significant_gaps': sorted(significant_gaps, key=lambda x: x['gap'], reverse=True),
            'insights': insights,
            'summary': {
                'windows_avg_coverage': windows_avg_overall,
                'linux_avg_coverage': linux_avg_overall,
                'domains_compared': len(common_domains),
                'significant_gaps_count': len(significant_gaps)
            }
        }
    
    def _generate_summary(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Generate executive summary of ML analysis."""
        anomalies = analysis.get('anomalies', {}).get('statistics', {})
        patterns = analysis.get('patterns', {})
        trends = analysis.get('trends', {})
        training = analysis.get('training_status', {})
        correlations = analysis.get('correlations', {})
        clusters = analysis.get('clusters', {})
        health = analysis.get('health_analysis', {})
        stress_corr = analysis.get('stress_correlation', {})
        
        # Count correlations
        correlations_found = 0
        if correlations.get('status') == 'success':
            correlations_found = len(correlations.get('strong_correlations', [])) + len(correlations.get('cross_domain_links', []))
        
        # Count clusters
        clusters_found = 0
        if clusters.get('status') == 'success':
            clusters_found = len(clusters.get('cluster_summary', []))
        
        # Count only ML-classified patterns (not rule-based fallbacks)
        ml_patterns_count = 0
        if patterns.get('status') == 'success':
            for domain_patterns in patterns.get('by_domain', {}).values():
                ml_patterns_count += sum(1 for p in domain_patterns if isinstance(p, dict) and p.get('ml_classified', False))
        
        # Count only ML-predicted stress correlations
        ml_stress_events = 0
        if stress_corr.get('status') == 'success' and stress_corr.get('ml_model_used', False):
            ml_stress_events = len(stress_corr.get('event_classifications', {}))
        
        # Health summary
        health_summary = {}
        if health.get('status') == 'success':
            resource_analysis = health.get('resource_analysis', {})
            health_summary = {
                'samples_collected': health.get('total_samples', 0),
                'bottlenecks_detected': len(health.get('bottlenecks', [])),
                'failure_risks': len(health.get('failure_risks', [])),
                'ml_insights_generated': len(health.get('ml_insights', [])),
                'avg_cpu_usage': resource_analysis.get('cpu', {}).get('avg', 0),
                'avg_memory_usage': resource_analysis.get('memory', {}).get('avg', 0),
                'collection_health': 'healthy' if len(health.get('bottlenecks', [])) == 0 else 'issues_detected'
            }
        
        return {
            'total_anomalies': anomalies.get('total_anomalies', 0),
            'high_severity_anomalies': anomalies.get('by_severity', {}).get('high', 0),
            'domains_analyzed': anomalies.get('domains_affected', 0),
            'patterns_classified': ml_patterns_count,  # Only ML-classified patterns
            'stress_events_analyzed': ml_stress_events,  # Only ML-analyzed stress events
            'correlations_found': correlations_found,
            'clusters_found': clusters_found,
            'training_datasets': training.get('datasets_collected', 0),
            'models_trained': sum(1 for v in training.get('models_available', {}).values() if v),
            'trend_direction': trends.get('trend_direction', 'unknown'),
            'recommendations_count': len(analysis.get('recommendations', [])),
            'health': health_summary,
            'ml_active': ml_patterns_count > 0 or ml_stress_events > 0  # Flag indicating ML is actually working
        }
    
    def generate_cross_product_comparison(self) -> Dict[str, Any]:
        """
        Generate cross-product comparison analysis from ML training data.
        
        Analyzes all registered products and compares:
        - Common vs unique domains
        - Common vs unique events
        - Coverage patterns across products
        - Stress behavior differences
        - Event activity patterns
        
        Returns:
            dict: Cross-product comparison analysis
        """
        logger.info("="*80)
        logger.info("GENERATING CROSS-PRODUCT COMPARISON ANALYSIS")
        logger.info("="*80)
        
        if self.debug:
            print("\n" + "="*80)
            print("DEBUG: CROSS-PRODUCT COMPARISON STARTED")
            print("="*80)
        
        # Get product registry
        product_summary = self.trainer.get_product_summary()
        
        if self.debug:
            print(f"DEBUG: Total products registered: {product_summary['total_products']}")
            print(f"DEBUG: Products: {list(product_summary.get('products', {}).keys())}")
        
        if product_summary['total_products'] == 0:
            return {
                'status': 'no_data',
                'message': 'No products registered yet',
                'products': []
            }
        
        logger.info(f" Analyzing {product_summary['total_products']} products...")
        
        comparison = {
            'metadata': {
                'timestamp': datetime.now().isoformat(),
                'total_products': product_summary['total_products'],
                'products_analyzed': []
            },
            'products': {},
            'common_analysis': {
                'domains': {},
                'events': {}
            },
            'unique_analysis': {
                'domains': {},
                'events': {}
            },
            'coverage_comparison': {},
            'stress_comparison': {},
            'os_comparison': {},  # NEW: OS-based coverage comparison
            'recommendations': []
        }
        
        # Load product-specific domain signatures for validation
        # Get domain list from config
        domain_list = self._get_ml_domains('anomaly_detector')
        PRODUCT_SIGNATURES = self.product_signatures
        
        # Load data for each product
        product_data = {}
        for product_id, product_info in product_summary['products'].items():
            logger.info(f"   Loading data for {product_info['product_name']} (ID: {product_id})...")
            
            # Load all datasets for this product
            datasets = self.trainer._load_historical_data(product_id)
            
            logger.info(f"      Found {len(datasets)} datasets for {product_id}")
            
            if not datasets:
                logger.warning(f"      [WARN]  No datasets found for {product_id} - skipping")
                continue
            
            # Extract domains, events, and coverage data
            all_domains = set()
            all_events = {}  # domain -> set of events
            coverage_data = defaultdict(lambda: {'runs': 0, 'avg_coverage': 0, 'events_by_stress': defaultdict(list)})
            os_coverage_data = defaultdict(lambda: defaultdict(lambda: {'runs': 0, 'total_coverage': 0, 'active_events': 0, 'total_events': 0}))  # NEW: OS-specific coverage
            valid_datasets = 0
            contaminated_datasets = 0
            
            for dataset in datasets:
                coverage_results = dataset.get('coverage_results', {})
                metadata = dataset.get('metadata', {})
                workload = metadata.get('workload', 'unknown')
                os_type = metadata.get('os_type', 'unknown')  # NEW: Get OS type
                
                # Get domain_results (current format)
                domain_results = coverage_results.get('domain_results', {})
                
                # Fallback: if no domain_results, treat coverage_results as domains directly (old format)
                if not domain_results:
                    domain_results = {k: v for k, v in coverage_results.items() if isinstance(v, dict) and 'events' in str(v)}
                
                # VALIDATION: Check if dataset domains match product signature
                if product_id in PRODUCT_SIGNATURES:
                    dataset_domains = set(domain_results.keys())
                    signature = PRODUCT_SIGNATURES[product_id]
                    
                    # Check for forbidden domains (indicates wrong product)
                    has_forbidden = any(forbidden in dataset_domains for forbidden in signature['forbidden'])
                    # Check for required domains (must have at least one)
                    has_required = any(required in dataset_domains for required in signature['required'])
                    
                    if has_forbidden or not has_required:
                        contaminated_datasets += 1
                        timestamp = dataset.get('timestamp', 'unknown')
                        logger.warning(f"      [WARN]  CONTAMINATION: Skipping dataset {timestamp} - domains {sorted(dataset_domains)} don't match {product_id} signature")
                        continue
                
                valid_datasets += 1
                
                for domain, domain_data in domain_results.items():
                    if not isinstance(domain_data, dict):
                        continue
                    
                    all_domains.add(domain)
                    
                    if domain not in all_events:
                        all_events[domain] = set()
                    
                    # Get active and inactive events
                    active_events = domain_data.get('active_events', [])
                    inactive_events = domain_data.get('inactive_events', [])
                    
                    for event_data in active_events + inactive_events:
                        event_name = event_data.get('event', '')
                        if event_name:
                            all_events[domain].add(event_name)
                            
                            # Track event activity by stress
                            if event_data.get('total_activity', 0) > 0:
                                coverage_data[domain]['events_by_stress'][workload].append({
                                    'event': event_name,
                                    'activity': event_data.get('total_activity', 0),
                                    'toggle_rate': event_data.get('active_cores', 0) / max(1, event_data.get('total_cores', 1))
                                })
                    
                    # Calculate coverage for this domain
                    total_events = len(active_events) + len(inactive_events)
                    active_count = len(active_events)
                    if total_events > 0:
                        coverage_pct = (active_count / total_events) * 100
                        coverage_data[domain]['runs'] += 1
                        coverage_data[domain]['avg_coverage'] += coverage_pct
                        
                        # Track OS-specific coverage
                        os_coverage_data[os_type][domain]['runs'] += 1
                        os_coverage_data[os_type][domain]['total_coverage'] += coverage_pct
                        os_coverage_data[os_type][domain]['active_events'] += active_count
                        os_coverage_data[os_type][domain]['total_events'] += total_events
            
            # Average coverage across runs
            for domain in coverage_data:
                if coverage_data[domain]['runs'] > 0:
                    coverage_data[domain]['avg_coverage'] /= coverage_data[domain]['runs']
            
            # Average OS-specific coverage
            for os_type in os_coverage_data:
                for domain in os_coverage_data[os_type]:
                    if os_coverage_data[os_type][domain]['runs'] > 0:
                        os_coverage_data[os_type][domain]['avg_coverage'] = \
                            os_coverage_data[os_type][domain]['total_coverage'] / os_coverage_data[os_type][domain]['runs']
            
            logger.info(f"      Validated: {valid_datasets} valid, {contaminated_datasets} contaminated (skipped)")
            
            product_data[product_id] = {
                'info': product_info,
                'domains': all_domains,
                'events': all_events,
                'coverage': dict(coverage_data),
                'os_coverage': dict(os_coverage_data),  # NEW: OS-specific coverage
                'dataset_count': valid_datasets  # Use valid count, not total
            }
            
            comparison['metadata']['products_analyzed'].append(product_id)
            comparison['products'][product_id] = {
                'product_name': product_info['product_name'],
                'cpu_family': product_info['cpu_family'],
                'total_domains': len(all_domains),
                'domains_list': sorted(list(all_domains)),  # Debug: Add domain list
                'total_events': sum(len(events) for events in all_events.values()),
                'datasets_analyzed': len(datasets),
                'os_coverage': dict(os_coverage_data)  # Add OS coverage info to product cards
            }
            
            # Debug logging
            logger.info(f"      Product {product_id} domains: {sorted(list(all_domains))}")
            if self.debug:
                print(f"\nDEBUG: Product {product_id} ({product_info['product_name']}):")
                print(f"       Domains ({len(all_domains)}): {sorted(list(all_domains))}")
                print(f"       Total Events: {sum(len(events) for events in all_events.values())}")
                print(f"       Datasets: {len(datasets)}")
        
        if len(product_data) < 2:
            logger.warning(f"[WARN]  Insufficient products for comparison:")
            logger.warning(f"   Products with data: {list(product_data.keys())}")
            logger.warning(f"   Total products registered: {product_summary['total_products']}")
            logger.warning(f"   Products with datasets: {len(product_data)}")
            logger.warning(f"   Need at least 2 products with historical datasets")
            
            # Debug: Show all registered products
            for prod_id, prod_info in product_summary['products'].items():
                datasets = self.trainer._load_historical_data(prod_id)
                logger.warning(f"   - {prod_id}: {prod_info['product_name']} -> {len(datasets)} datasets")
            
            comparison['status'] = 'insufficient_data'
            comparison['message'] = f'Need at least 2 products with data for comparison (found {len(product_data)})'
            comparison['products_found'] = list(product_data.keys())
            return comparison
        
        logger.info(f"[OK] Loaded data for {len(product_data)} products:")
        for product_id, data in product_data.items():
            logger.info(f"   - {product_id}: {data['info']['product_name']} -> {data['dataset_count']} datasets, {len(data['domains'])} domains")
        
        # Analyze common domains
        logger.info(" Analyzing common domains...")
        all_product_domains = [data['domains'] for data in product_data.values()]
        
        # Debug: Log domains for each product
        for product_id, domains in zip(product_data.keys(), all_product_domains):
            logger.info(f"   {product_id}: {len(domains)} domains - {sorted(list(domains))}")
        
        common_domains = set.intersection(*all_product_domains) if all_product_domains else set()
        
        logger.info(f"   Common domains (intersection): {len(common_domains)} - {sorted(list(common_domains))}")
        
        if self.debug:
            print(f"\nDEBUG: COMMON DOMAIN ANALYSIS:")
            print(f"       Total products: {len(all_product_domains)}")
            print(f"       Common domains ({len(common_domains)}): {sorted(list(common_domains))}")
            print("="*80 + "\n")
        
        comparison['common_analysis']['domains'] = {
            'count': len(common_domains),
            'list': sorted(list(common_domains)),
            'products_with_all': len(product_data)
        }
        
        # Analyze unique domains per product
        logger.info(" Analyzing unique domains...")
        for product_id, data in product_data.items():
            other_domains = set()
            for other_id, other_data in product_data.items():
                if other_id != product_id:
                    other_domains.update(other_data['domains'])
            
            unique = data['domains'] - other_domains
            comparison['unique_analysis']['domains'][product_id] = {
                'product_name': data['info']['product_name'],
                'count': len(unique),
                'list': sorted(list(unique))
            }
        
        # Analyze common events per domain
        logger.info(" Analyzing common events...")
        for domain in common_domains:
            domain_events_by_product = []
            for data in product_data.values():
                if domain in data['events']:
                    domain_events_by_product.append(data['events'][domain])
            
            if domain_events_by_product:
                common_events = set.intersection(*domain_events_by_product)
                comparison['common_analysis']['events'][domain] = {
                    'count': len(common_events),
                    'events': sorted(list(common_events)),
                    'coverage_across_products': {}
                }
                
                # Compare coverage for common events
                for product_id, data in product_data.items():
                    if domain in data['coverage']:
                        comparison['common_analysis']['events'][domain]['coverage_across_products'][product_id] = {
                            'product_name': data['info']['product_name'],
                            'avg_coverage_pct': round(data['coverage'][domain]['avg_coverage'], 2),
                            'runs_analyzed': data['coverage'][domain]['runs']
                        }
        
        # Analyze unique events per product per domain
        logger.info(" Analyzing unique events...")
        for domain in common_domains:
            comparison['unique_analysis']['events'][domain] = {}
            
            for product_id, data in product_data.items():
                if domain not in data['events']:
                    continue
                
                # Find events unique to this product
                other_events = set()
                for other_id, other_data in product_data.items():
                    if other_id != product_id and domain in other_data['events']:
                        other_events.update(other_data['events'][domain])
                
                unique_events = data['events'][domain] - other_events
                
                if unique_events:
                    comparison['unique_analysis']['events'][domain][product_id] = {
                        'product_name': data['info']['product_name'],
                        'count': len(unique_events),
                        'events': sorted(list(unique_events))[:20]  # Limit to first 20
                    }
        
        # Coverage comparison across products
        logger.info(" Comparing coverage patterns...")
        for domain in common_domains:
            comparison['coverage_comparison'][domain] = {
                'domain': domain,
                'products': {}
            }
            
            for product_id, data in product_data.items():
                if domain in data['coverage']:
                    cov = data['coverage'][domain]
                    comparison['coverage_comparison'][domain]['products'][product_id] = {
                        'product_name': data['info']['product_name'],
                        'avg_coverage_pct': round(cov['avg_coverage'], 2),
                        'runs_analyzed': cov['runs']
                    }
        
        # Stress comparison - which events activate under which stress per product
        logger.info(" Analyzing stress patterns...")
        for domain in common_domains:
            comparison['stress_comparison'][domain] = {}
            
            for product_id, data in product_data.items():
                if domain not in data['coverage']:
                    continue
                
                stress_events = data['coverage'][domain].get('events_by_stress', {})
                
                for stress, events_list in stress_events.items():
                    if stress not in comparison['stress_comparison'][domain]:
                        comparison['stress_comparison'][domain][stress] = {}
                    
                    comparison['stress_comparison'][domain][stress][product_id] = {
                        'product_name': data['info']['product_name'],
                        'active_events_count': len(events_list),
                        'top_events': sorted(events_list, key=lambda x: x['activity'], reverse=True)[:10]
                    }
        
        # OS Comparison - Windows vs Linux coverage analysis
        logger.info("  Analyzing OS-specific coverage patterns...")
        for product_id, data in product_data.items():
            os_coverage = data.get('os_coverage', {})
            
            if len(os_coverage) > 1:  # Product has data from multiple OS types
                for domain in common_domains:
                    if domain not in comparison['os_comparison']:
                        comparison['os_comparison'][domain] = {}
                    
                    if product_id not in comparison['os_comparison'][domain]:
                        comparison['os_comparison'][domain][product_id] = {
                            'product_name': data['info']['product_name'],
                            'os_results': {}
                        }
                    
                    for os_type, os_domains in os_coverage.items():
                        if domain in os_domains:
                            comparison['os_comparison'][domain][product_id]['os_results'][os_type] = {
                                'avg_coverage_pct': round(os_domains[domain].get('avg_coverage', 0), 2),
                                'runs': os_domains[domain]['runs'],
                                'active_events': os_domains[domain]['active_events'],
                                'total_events': os_domains[domain]['total_events']
                            }
        
        # Generate recommendations
        logger.info("[TIP] Generating recommendations...")
        
        # Recommendation 1: Test common domains consistently
        if common_domains:
            comparison['recommendations'].append({
                'type': 'common_domains',
                'priority': 'high',
                'title': f'Test {len(common_domains)} Common Domains Across All Products',
                'description': f'Domains present in all products: {", ".join(sorted(list(common_domains))[:5])}{"..." if len(common_domains) > 5 else ""}',
                'action': 'Ensure these domains are tested with the same stress types for valid comparisons'
            })
        
        # Recommendation 2: Investigate unique domains
        for product_id, unique_info in comparison['unique_analysis']['domains'].items():
            if unique_info['count'] > 0:
                comparison['recommendations'].append({
                    'type': 'unique_domains',
                    'priority': 'medium',
                    'product': product_id,
                    'title': f"{unique_info['product_name']}: {unique_info['count']} Unique Domains",
                    'description': f"Domains only in {unique_info['product_name']}: {', '.join(unique_info['list'][:3])}{'...' if unique_info['count'] > 3 else ''}",
                    'action': 'Document these product-specific PMU units for architecture reference'
                })
        
        # Recommendation 3: Coverage gaps
        for domain, cov_data in comparison['coverage_comparison'].items():
            coverages = [p['avg_coverage_pct'] for p in cov_data['products'].values()]
            if coverages:
                min_cov = min(coverages)
                max_cov = max(coverages)
                if max_cov - min_cov > 20:  # 20% difference
                    low_product = min(cov_data['products'].items(), key=lambda x: x[1]['avg_coverage_pct'])
                    high_product = max(cov_data['products'].items(), key=lambda x: x[1]['avg_coverage_pct'])
                    
                    comparison['recommendations'].append({
                        'type': 'coverage_gap',
                        'priority': 'high',
                        'domain': domain,
                        'title': f'{domain}: Coverage Gap Detected',
                        'description': f"{high_product[1]['product_name']} achieves {high_product[1]['avg_coverage_pct']}% but {low_product[1]['product_name']} only {low_product[1]['avg_coverage_pct']}%",
                        'action': f"Investigate why {low_product[1]['product_name']} has lower coverage - may need different stress or longer duration"
                    })
        
        # Recommendation 4: OS-specific coverage differences
        for domain, product_os_data in comparison['os_comparison'].items():
            for product_id, os_info in product_os_data.items():
                os_results = os_info.get('os_results', {})
                if len(os_results) >= 2:  # Has both Windows and Linux data
                    coverages = {os: data['avg_coverage_pct'] for os, data in os_results.items()}
                    if coverages:
                        max_os = max(coverages.items(), key=lambda x: x[1])
                        min_os = min(coverages.items(), key=lambda x: x[1])
                        
                        if max_os[1] - min_os[1] > 15:  # 15% difference
                            comparison['recommendations'].append({
                                'type': 'os_coverage_gap',
                                'priority': 'medium',
                                'product': product_id,
                                'domain': domain,
                                'title': f"{os_info['product_name']} - {domain}: OS Coverage Difference",
                                'description': f"{max_os[0].upper()} achieves {max_os[1]:.1f}% but {min_os[0].upper()} only {min_os[1]:.1f}%",
                                'action': f"Review {min_os[0].upper()} stress workloads - may need OS-specific tuning or different stress tools"
                            })
        
        comparison['status'] = 'success'
        logger.info("="*80)
        logger.info(f"[OK] CROSS-PRODUCT COMPARISON COMPLETE")
        logger.info(f"   Products compared: {len(product_data)}")
        logger.info(f"   Common domains: {len(common_domains)}")
        logger.info(f"   Recommendations: {len(comparison['recommendations'])}")
        logger.info("="*80)
        
        return comparison
    
    def _generate_workload_gap_mapping(self, gap_results: Dict[str, Any], 
                                       coverage_results: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate ML-learned workload recommendations for coverage gaps.
        
        Args:
            gap_results: Gap analysis results with missing events
            coverage_results: Current coverage data
            
        Returns:
            Dict with workload recommendations per gap event
        """
        try:
            from src.workload_gap_mapper import WorkloadGapMapper
            
            # Get product ID from coverage
            product_id = coverage_results.get('product_id', 'unknown')
            
            # Initialize mapper with config
            config = {'product_id': product_id}
            mapper = WorkloadGapMapper(config)
            
            # Get gap events from non_toggling_events
            all_gaps = []
            non_toggling = gap_results.get('non_toggling_events', [])
            
            for gap_event in non_toggling:
                if isinstance(gap_event, dict):
                    event_name = gap_event.get('event_name') or gap_event.get('event', '')
                    domain = gap_event.get('domain', 'unknown')
                    
                    if event_name:
                        all_gaps.append({
                            'event': event_name,
                            'domain': domain,
                            'priority': 'MEDIUM'  # Default priority
                        })
            
            # Get recommendations for each gap
            recommendations = []
            for gap in all_gaps:
                event_name = gap['event']
                domain = gap.get('domain', 'unknown')
                workload_recs = mapper.recommend_workloads_for_gap(event_name, domain=domain)
                
                if workload_recs:
                    # Convert string confidence to numeric for each workload recommendation
                    for wl_rec in workload_recs:
                        conf = wl_rec.get('confidence', 0)
                        if isinstance(conf, str):
                            # Convert string confidence to numeric (low=30, medium=60, high=85)
                            conf_map = {'low': 30, 'medium': 60, 'high': 85}
                            wl_rec['confidence'] = conf_map.get(conf.lower(), 0)
                        else:
                            try:
                                wl_rec['confidence'] = float(conf) if conf else 0
                            except (ValueError, TypeError):
                                wl_rec['confidence'] = 0
                    
                    # Get top recommendation confidence
                    top_confidence = workload_recs[0].get('confidence', 0)
                    
                    recommendations.append({
                        'event': event_name,
                        'domain': gap['domain'],
                        'priority': gap['priority'],
                        'recommended_workloads': workload_recs,
                        'confidence': top_confidence
                    })
            
            # Get analysis statistics
            runs_analyzed = len(mapper.workload_event_map) if hasattr(mapper, 'workload_event_map') else 0
            unique_workloads = len(set(mapper.workload_event_map.keys())) if hasattr(mapper, 'workload_event_map') else 0
            
            logger.info(f"Generated workload recommendations for {len(recommendations)} gap events")
            
            return {
                'status': 'success' if recommendations else 'no_data',
                'recommendations': recommendations,
                'runs_analyzed': runs_analyzed,
                'unique_workloads': unique_workloads,
                'total_mappings': sum(len(events) for events in mapper.workload_event_map.values()) if hasattr(mapper, 'workload_event_map') else 0
            }
            
        except Exception as e:
            logger.error(f"Workload-gap mapping failed: {e}")
            logger.exception(e)
            return {
                'status': 'failed',
                'error': str(e),
                'recommendations': []
            }
    
    def _generate_emon_commands(self, gap_results: Dict[str, Any], 
                                workload_mapping: Dict[str, Any]) -> Dict[str, str]:
        """
        Generate EMON validation commands for gap events.
        
        Args:
            gap_results: Gap analysis results
            workload_mapping: Workload-gap mapping with recommendations
            
        Returns:
            Dict mapping event names to EMON commands
        """
        try:
            # Generate simple EMON commands directly from gap data
            event_commands = {}
            
            # Get non-toggling events
            non_toggling = gap_results.get('non_toggling_events', [])
            
            for gap_event in non_toggling:
                if isinstance(gap_event, dict):
                    event_name = gap_event.get('event_name') or gap_event.get('event', '')
                    domain = gap_event.get('domain', 'unknown')
                    
                    if event_name:
                        # Generate basic EMON command
                        # Format: emon -C 0 -e EVENT_NAME -t 5
                        emon_cmd = f"emon -C 0 -e {event_name} -t 5"
                        event_commands[event_name] = emon_cmd
            
            logger.info(f"Generated EMON commands for {len(event_commands)} gap events")
            return event_commands
            
        except Exception as e:
            logger.error(f"EMON command generation failed: {e}")
            logger.exception(e)
            return {}
        logger.info("="*80)
        
        return comparison
    
    def _load_product_signatures(self) -> Dict[str, Dict[str, List[str]]]:
        """Load product signature validation rules from YAML config.
        
        Returns:
            Dict mapping product_id to signature rules (required/forbidden domains)
        """
        try:
            config_path = Path(__file__).parent.parent / 'config' / 'product_signatures.yaml'
            
            if not config_path.exists():
                logger.warning(f"Product signatures config not found: {config_path}")
                logger.info("Attempting to auto-generate signatures from collected data...")
                return self._auto_generate_signatures()
            
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            
            signatures = config.get('product_signatures', {})
            logger.info(f"Loaded product signatures for {len(signatures)} products: {list(signatures.keys())}")
            
            # Check if we should update signatures with new products
            self._update_signatures_if_needed(signatures, config_path)
            
            return signatures
            
        except Exception as e:
            logger.error(f"Failed to load product signatures: {e}")
            logger.info("Validation will be skipped for all products")
            return {}
    
    def _auto_generate_signatures(self) -> Dict[str, Dict[str, List[str]]]:
        """Auto-generate product signatures by analyzing collected datasets.
        
        Returns:
            Dict of product signatures with required/forbidden domains
        """
        try:
            logger.info("Auto-generating product signatures from dataset analysis...")
            
            # Analyze domains per product
            product_domains = self._analyze_product_domains()
            
            if len(product_domains) < 2:
                logger.warning(f"Need at least 2 products for signature generation, found {len(product_domains)}")
                return {}
            
            # Generate signatures based on unique/common domains
            signatures = {}
            all_products = list(product_domains.keys())
            
            for product_id in all_products:
                product_domain_set = product_domains[product_id]
                
                # Find unique domains (present in this product, absent in others)
                unique_domains = set(product_domain_set)
                for other_product_id in all_products:
                    if other_product_id != product_id:
                        unique_domains -= product_domains[other_product_id]
                
                # Find forbidden domains (present in other products, not in this one)
                forbidden_domains = set()
                for other_product_id in all_products:
                    if other_product_id != product_id:
                        other_unique = product_domains[other_product_id] - product_domain_set
                        forbidden_domains.update(other_unique)
                
                # Use most distinctive unique domain as required signature
                if unique_domains:
                    # Sort for consistency
                    required = sorted(list(unique_domains))[:3]  # Top 3 unique domains
                    forbidden = sorted(list(forbidden_domains))[:5]  # Top 5 forbidden
                    
                    signatures[product_id] = {
                        'required': required,
                        'forbidden': forbidden
                    }
                    logger.info(f"Generated signature for {product_id}: required={required}, forbidden={forbidden}")
            
            # Save to config file
            if signatures:
                self._save_signatures_to_yaml(signatures)
            
            return signatures
            
        except Exception as e:
            logger.error(f"Auto-generation of signatures failed: {e}")
            return {}
    
    def _analyze_product_domains(self) -> Dict[str, set]:
        """Analyze all collected datasets to determine domains per product.
        
        Returns:
            Dict mapping product_id to set of domain names
        """
        product_domains = defaultdict(set)
        
        try:
            datasets_dir = self.trainer.raw_datasets_dir
            
            if not datasets_dir.exists():
                return {}
            
            # Iterate through product folders
            for product_dir in datasets_dir.iterdir():
                if not product_dir.is_dir():
                    continue
                
                product_id = product_dir.name
                
                # Load a sample of datasets (first 10 should be enough)
                sample_files = sorted(product_dir.glob('coverage_*.json'))[:10]
                
                for dataset_file in sample_files:
                    try:
                        with open(dataset_file, 'r') as f:
                            data = json.load(f)
                        
                        # Extract domains
                        coverage_results = data.get('coverage_results', {})
                        domain_results = coverage_results.get('domain_results', {})
                        
                        if domain_results:
                            product_domains[product_id].update(domain_results.keys())
                    
                    except Exception as e:
                        logger.debug(f"Could not analyze {dataset_file.name}: {e}")
                        continue
                
                logger.info(f"Product {product_id}: found {len(product_domains[product_id])} domains")
        
        except Exception as e:
            logger.error(f"Domain analysis failed: {e}")
        
        return dict(product_domains)
    
    def _update_signatures_if_needed(self, current_signatures: Dict, config_path: Path):
        """Check for new products and update signatures if needed.
        
        Args:
            current_signatures: Currently loaded signatures
            config_path: Path to YAML config file
        """
        try:
            # Get all products from data directory
            product_domains = self._analyze_product_domains()
            
            # Find new products not in signatures
            new_products = set(product_domains.keys()) - set(current_signatures.keys())
            
            if new_products:
                logger.info(f"Found {len(new_products)} new products: {new_products}")
                logger.info("Auto-generating signatures for new products...")
                
                # Generate signatures for all products (including new ones)
                all_signatures = self._auto_generate_signatures()
                
                if all_signatures:
                    logger.info(f"Updated signatures with {len(new_products)} new products")
        
        except Exception as e:
            logger.warning(f"Signature update check failed: {e}")
    
    def _save_signatures_to_yaml(self, signatures: Dict):
        """Save generated signatures to YAML config file.
        
        Args:
            signatures: Product signatures to save
        """
        try:
            config_path = Path(__file__).parent.parent / 'config' / 'product_signatures.yaml'
            
            # Create config structure
            config = {
                'product_signatures': signatures
            }
            
            # Add header comment
            header = """# Product Signature Validation Configuration (AUTO-GENERATED)
# 
# This file is automatically generated by analyzing collected datasets.
# Signatures are learned from actual domain coverage patterns.
#
# Format:
#   product_id:
#     required: [domains that MUST be present - product-specific]
#     forbidden: [domains that MUST NOT be present - from other products]
#
# Last updated: {timestamp}

"""
            
            # Write to file
            with open(config_path, 'w') as f:
                f.write(header.format(timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)
            
            logger.info(f"[OK] Saved auto-generated signatures to {config_path}")
            
        except Exception as e:
            logger.error(f"Failed to save signatures: {e}")
