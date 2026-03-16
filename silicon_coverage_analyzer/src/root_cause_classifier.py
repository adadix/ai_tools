#!/usr/bin/env python3
"""
Root Cause Classifier Module

ML-powered classification of gap root causes to determine why events don't toggle
and provide actionable recommendations.
"""

import logging
import json
from pathlib import Path
from typing import Dict, List, Any, Optional
import numpy as np

logger = logging.getLogger(__name__)

# Try to import sklearn for ML classification
try:
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.feature_extraction.text import TfidfVectorizer
    import joblib
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False
    logger.warning("[RootCause] scikit-learn not available - using rule-based classification only")


class RootCauseClassifier:
    """
    Classifies root causes of coverage gaps using ML + rule-based hybrid approach.
    
    Categories:
    - Workload_Missing: Event needs specific stress workload
    - HW_Feature_Disabled: CPU feature disabled (AVX-512, etc.)
    - OS_Limitation: Platform-specific event (Windows/Linux)
    - Collection_Issue: EMON collection error
    - Event_Unavailable: Event doesn't exist on this product
    - Privilege_Required: Event needs kernel/supervisor mode
    - Multi_Socket_Required: Event needs multi-socket system
    """
    
    ROOT_CAUSE_CATEGORIES = [
        'Workload_Missing',
        'HW_Feature_Disabled', 
        'OS_Limitation',
        'Collection_Issue',
        'Event_Unavailable',
        'Privilege_Required',
        'Multi_Socket_Required'
    ]
    
    def __init__(self, config):
        self.config = config
        self.ml_data_dir = Path(config.get('ml_data_dir', 'ml_data'))
        self.model = None
        self.vectorizer = None
        
        # Load trained model if available
        if ML_AVAILABLE:
            self._load_model()
    
    def _load_model(self):
        """Load pre-trained ML model for root cause classification."""
        try:
            model_dir = self.ml_data_dir / 'models'
            model_path = model_dir / 'root_cause_classifier.pkl'
            vectorizer_path = model_dir / 'root_cause_vectorizer.pkl'
            
            if model_path.exists() and vectorizer_path.exists():
                self.model = joblib.load(model_path)
                self.vectorizer = joblib.load(vectorizer_path)
                logger.info("[RootCause] [OK] Loaded trained ML classifier")
            else:
                logger.info("[RootCause] No trained model found - using rule-based classification")
        except Exception as e:
            logger.warning(f"[RootCause] Could not load model: {e}")
    
    def classify_gap(self, event_name: str, domain: str, reason: str, 
                    hw_config: Dict, os_type: str, metadata: Dict = None) -> Dict:
        """
        Classify root cause of gap using ML + rules.
        
        Args:
            event_name: Event that didn't toggle
            domain: Domain name
            reason: Gap reason (no_activity, event_not_exists, etc.)
            hw_config: Hardware configuration
            os_type: Operating system type
            metadata: Additional metadata (workload, etc.)
            
        Returns:
            Dict with category, actionable, confidence, recommended_workload, recommendation
        """
        # Try ML classification first if model available
        if self.model and self.vectorizer and ML_AVAILABLE:
            ml_result = self._ml_classify(event_name, domain, reason, hw_config, os_type, metadata)
            if ml_result['confidence'] > 0.7:  # High confidence
                return ml_result
        
        # Fallback to rule-based classification
        return self._rule_based_classify(event_name, domain, reason, hw_config, os_type, metadata)
    
    def _ml_classify(self, event_name: str, domain: str, reason: str,
                    hw_config: Dict, os_type: str, metadata: Dict = None) -> Dict:
        """ML-based classification using trained model."""
        try:
            # Extract features for ML
            features = self._extract_features(event_name, domain, reason, hw_config, os_type, metadata)
            
            # Vectorize event name
            event_vec = self.vectorizer.transform([event_name])
            
            # Combine with other features
            feature_array = np.hstack([
                event_vec.toarray(),
                [[
                    1 if 'AVX' in event_name else 0,
                    1 if 'FP_' in event_name else 0,
                    1 if 'BR_' in event_name else 0,
                    1 if 'MEM_' in event_name else 0,
                    1 if 'PEBS' in event_name else 0,
                    1 if os_type.lower() == 'windows' else 0,
                    1 if reason == 'no_activity' else 0,
                    1 if reason == 'event_not_exists' else 0
                ]]
            ])
            
            # Predict
            prediction = self.model.predict(feature_array)[0]
            confidence = self.model.predict_proba(feature_array)[0].max()
            
            # Get recommendation based on prediction
            recommendation = self._get_recommendation_for_category(
                prediction, event_name, domain, hw_config, os_type
            )
            
            return {
                'category': prediction,
                'confidence': float(confidence),
                'method': 'ml',
                **recommendation
            }
            
        except Exception as e:
            logger.warning(f"[RootCause] ML classification failed: {e}")
            return {'category': 'Unknown', 'confidence': 0.0, 'method': 'failed'}
    
    def _rule_based_classify(self, event_name: str, domain: str, reason: str,
                            hw_config: Dict, os_type: str, metadata: Dict = None) -> Dict:
        """Enhanced rule-based classification with detailed analysis."""
        
        # Collection issues
        if reason in ['no_file', 'collection_failed', 'emon_error']:
            return {
                'category': 'Collection_Issue',
                'confidence': 0.95,
                'actionable': True,
                'recommended_workload': 'Re-run collection',
                'recommendation': 'Check EMON collection logs - collection may have failed or timed out',
                'details': 'EMON did not generate output file for this event',
                'method': 'rule'
            }
        
        # Event unavailable
        if reason in ['event_not_exists', 'not_found', 'not_supported']:
            return {
                'category': 'Event_Unavailable',
                'confidence': 0.90,
                'actionable': False,
                'recommended_workload': 'N/A',
                'recommendation': 'Event not available on this platform/product - skip this gap',
                'details': 'Event may be deprecated or not supported on this CPU generation',
                'method': 'rule'
            }
        
        # AVX-512 events
        if any(avx in event_name for avx in ['AVX512', 'AVX_512', 'ZMM', 'MASK']):
            avx512_enabled = hw_config.get('avx512_enabled', True)
            
            if not avx512_enabled:
                return {
                    'category': 'HW_Feature_Disabled',
                    'confidence': 0.98,
                    'actionable': False,
                    'recommended_workload': 'N/A',
                    'recommendation': 'Enable AVX-512 in BIOS or verify CPU supports AVX-512 (may be fused off)',
                    'details': 'AVX-512 is disabled or not supported',
                    'method': 'rule'
                }
            else:
                return {
                    'category': 'Workload_Missing',
                    'confidence': 0.85,
                    'actionable': True,
                    'recommended_workload': 'AVX-512 benchmark: HPL, LINPACK, y-cruncher, or AVX-512 stress test',
                    'recommendation': 'Run AVX-512 intensive workload to trigger these events',
                    'details': 'AVX-512 is enabled but no workload uses it',
                    'method': 'rule'
                }
        
        # FP/SIMD events
        if any(fp in event_name for fp in ['FP_ARITH', 'FP_COMP', 'SIMD', 'SSE', 'AVX', 'VEC', 'FLOP']):
            return {
                'category': 'Workload_Missing',
                'confidence': 0.88,
                'actionable': True,
                'recommended_workload': 'SPECfp2017, LINPACK, Blender, or floating-point benchmark',
                'recommendation': 'Add floating-point intensive workload',
                'details': 'Requires FP/SIMD operations',
                'method': 'rule'
            }
        
        # Branch events
        if any(br in event_name for br in ['BR_INST', 'BR_MISP', 'BRANCH', 'BACLEARS']):
            return {
                'category': 'Workload_Missing',
                'confidence': 0.82,
                'actionable': True,
                'recommended_workload': 'Prime95 small FFT, compression (7-zip), or branch-heavy compute',
                'recommendation': 'Add compute workload with conditional branches',
                'details': 'Requires branch-intensive code',
                'method': 'rule'
            }
        
        # Memory events
        if any(mem in event_name for mem in ['MEM_LOAD', 'MEM_STORE', 'MEM_INST', 'MEM_UOPS', 'LOAD_', 'STORE_']):
            return {
                'category': 'Workload_Missing',
                'confidence': 0.85,
                'actionable': True,
                'recommended_workload': 'stream.exe, membw, or memory bandwidth benchmark',
                'recommendation': 'Add memory-intensive workload (bandwidth or latency stress)',
                'details': 'Requires memory access operations',
                'method': 'rule'
            }
        
        # Cache events
        if any(cache in event_name for cache in ['L1D', 'L1I', 'L2_', 'L3_', 'LLC', 'LONGEST_LAT', 'CACHE']):
            return {
                'category': 'Workload_Missing',
                'confidence': 0.80,
                'actionable': True,
                'recommended_workload': 'mlc (Memory Latency Checker), lmbench, or cache stress test',
                'recommendation': 'Add cache-intensive workload',
                'details': 'Requires cache hierarchy stress',
                'method': 'rule'
            }
        
        # PEBS events (OS-specific)
        if 'PEBS' in event_name:
            if os_type.lower() == 'linux':
                return {
                    'category': 'OS_Limitation',
                    'confidence': 0.92,
                    'actionable': False,
                    'recommended_workload': 'N/A',
                    'recommendation': 'PEBS events require Windows Performance Counters - test on Windows for PEBS coverage',
                    'details': 'PEBS not fully supported on Linux',
                    'method': 'rule'
                }
        
        # Offcore events (may need specific workload)
        if 'OFFCORE_RESPONSE' in event_name or 'OCR' in event_name:
            return {
                'category': 'Workload_Missing',
                'confidence': 0.75,
                'actionable': True,
                'recommended_workload': 'Memory-intensive with specific access patterns (L3 miss generator)',
                'recommendation': 'Add workload with off-core memory requests',
                'details': 'Requires memory requests that go beyond core',
                'method': 'rule'
            }
        
        # Uncore events (pattern-based matching)
        domain_lower = domain.lower()
        if any(x in domain_lower for x in ['imc', 'cbo', 'cha', 'ncu', 'upi', 'mesh', 'ufibridge', 'mc', 'memctrl']):
            return {
                'category': 'Workload_Missing',
                'confidence': 0.78,
                'actionable': True,
                'recommended_workload': 'Uncore stress: memory bandwidth, multi-socket communication, cache coherency tests',
                'recommendation': f'Add uncore-specific stress workload for {domain.upper()} domain',
                'details': f'Requires {domain} domain activity',
                'method': 'rule'
            }
        
        # Power events
        if 'C_STATE' in event_name or 'FREQ' in event_name or 'THERMAL' in event_name or 'POWER' in event_name:
            return {
                'category': 'Workload_Missing',
                'confidence': 0.70,
                'actionable': True,
                'recommended_workload': 'Power state transition tests, DVFS stress, thermal stress',
                'recommendation': 'Add power management stress workload',
                'details': 'Requires power state transitions',
                'method': 'rule'
            }
        
        # Default: Generic workload missing
        return {
            'category': 'Workload_Missing',
            'confidence': 0.60,
            'actionable': True,
            'recommended_workload': 'Comprehensive stress test (CPU, memory, cache, branch)',
            'recommendation': 'Add general stress workload - event type unclear',
            'details': 'Generic gap - requires further analysis',
            'method': 'rule'
        }
    
    def _extract_features(self, event_name: str, domain: str, reason: str,
                         hw_config: Dict, os_type: str, metadata: Dict = None) -> Dict:
        """Extract features for ML classification."""
        return {
            'event_name': event_name,
            'domain': domain,
            'reason': reason,
            'os_type': os_type,
            'has_avx512': 'AVX512' in event_name or 'ZMM' in event_name,
            'has_fp': 'FP_' in event_name or 'FLOP' in event_name,
            'has_branch': 'BR_' in event_name or 'BRANCH' in event_name,
            'has_memory': 'MEM_' in event_name or 'LOAD_' in event_name or 'STORE_' in event_name,
            'has_cache': any(c in event_name for c in ['L1D', 'L1I', 'L2_', 'L3_', 'LLC']),
            'is_uncore': any(x in domain.lower() for x in ['imc', 'cbo', 'cha', 'ncu', 'upi', 'mesh', 'mc', 'memctrl']),
            'is_pebs': 'PEBS' in event_name,
            'workload': metadata.get('workload', 'unknown') if metadata else 'unknown'
        }
    
    def _get_recommendation_for_category(self, category: str, event_name: str,
                                         domain: str, hw_config: Dict, os_type: str) -> Dict:
        """Get actionable recommendation based on predicted category."""
        
        recommendations = {
            'Workload_Missing': {
                'actionable': True,
                'recommended_workload': 'Event-specific stress workload',
                'recommendation': 'Add workload that exercises this event type'
            },
            'HW_Feature_Disabled': {
                'actionable': False,
                'recommended_workload': 'N/A',
                'recommendation': 'Enable CPU feature in BIOS or verify hardware support'
            },
            'OS_Limitation': {
                'actionable': False,
                'recommended_workload': 'N/A',
                'recommendation': 'Event requires different operating system'
            },
            'Collection_Issue': {
                'actionable': True,
                'recommended_workload': 'Re-run collection',
                'recommendation': 'Check EMON logs and re-run collection'
            },
            'Event_Unavailable': {
                'actionable': False,
                'recommended_workload': 'N/A',
                'recommendation': 'Event not supported on this platform - safe to ignore'
            },
            'Privilege_Required': {
                'actionable': True,
                'recommended_workload': 'Run EMON with elevated privileges',
                'recommendation': 'Event requires administrator/root privileges'
            },
            'Multi_Socket_Required': {
                'actionable': False,
                'recommended_workload': 'N/A',
                'recommendation': 'Event requires multi-socket system'
            }
        }
        
        return recommendations.get(category, {
            'actionable': True,
            'recommended_workload': 'Unknown',
            'recommendation': 'Investigate event requirements'
        })
    
    def train_model(self, historical_gap_data: List[Dict]):
        """
        Train ML model on historical gap data with known root causes.
        
        Args:
            historical_gap_data: List of dicts with event_name, domain, reason, actual_category
        """
        if not ML_AVAILABLE:
            logger.warning("[RootCause] Cannot train - scikit-learn not available")
            return
        
        logger.info(f"[RootCause] Training model on {len(historical_gap_data)} labeled gaps...")
        
        # Extract features and labels
        event_names = [gap['event_name'] for gap in historical_gap_data]
        labels = [gap['actual_category'] for gap in historical_gap_data]
        
        # Vectorize event names
        self.vectorizer = TfidfVectorizer(max_features=100, ngram_range=(1, 2))
        event_vectors = self.vectorizer.fit_transform(event_names)
        
        # Add additional features
        additional_features = []
        for gap in historical_gap_data:
            additional_features.append([
                1 if 'AVX' in gap['event_name'] else 0,
                1 if 'FP_' in gap['event_name'] else 0,
                1 if 'BR_' in gap['event_name'] else 0,
                1 if 'MEM_' in gap['event_name'] else 0,
                1 if 'PEBS' in gap['event_name'] else 0,
                1 if gap.get('os_type', '').lower() == 'windows' else 0,
                1 if gap['reason'] == 'no_activity' else 0,
                1 if gap['reason'] == 'event_not_exists' else 0
            ])
        
        # Combine features
        features = np.hstack([event_vectors.toarray(), additional_features])
        
        # Train classifier
        self.model = RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42)
        self.model.fit(features, labels)
        
        # Save model
        model_dir = self.ml_data_dir / 'models'
        model_dir.mkdir(parents=True, exist_ok=True)
        
        joblib.dump(self.model, model_dir / 'root_cause_classifier.pkl')
        joblib.dump(self.vectorizer, model_dir / 'root_cause_vectorizer.pkl')
        
        logger.info("[RootCause] [OK] Model trained and saved")
