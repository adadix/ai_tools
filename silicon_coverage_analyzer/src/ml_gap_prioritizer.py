#!/usr/bin/env python3
"""
ML-Based Gap Priority Classifier

Replaces hardcoded pattern matching with learned importance from historical gap->bug-severity mapping.
Uses RandomForest Classifier trained on:
- Event name features (extracted patterns)
- Domain classification
- Co-occurrence patterns
- Historical fix priority from past runs

Author: Intel Corporation
Date: December 2025
"""

import json
import pickle
import re
from pathlib import Path
from typing import Dict, List, Tuple, Any
from datetime import datetime
from collections import Counter

try:
    from sklearn.ensemble import RandomForestClassifier
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.preprocessing import LabelEncoder
    import numpy as np
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    print("[WARNING] scikit-learn not available. Gap prioritization will use rule-based fallback.")


class MLGapPrioritizer:
    """ML-based gap priority classifier with rule-based fallback."""
    
    PRIORITY_LEVELS = ['critical', 'high', 'medium', 'low']
    
    def __init__(self, data_dir: str = "C:\\silicon_coverage_analyzer_data"):
        """Initialize gap prioritizer with data directory."""
        self.data_dir = Path(data_dir)
        self.models_dir = self.data_dir / "models" / "gap_prioritizer"
        self.models_dir.mkdir(parents=True, exist_ok=True)
        
        self.model = None
        self.vectorizer = None
        self.domain_encoder = None
        self.feature_importance = {}
        self.feature_mismatch_warned = False  # Track if we've warned about feature mismatch
        
        # Load model if exists
        self._load_model()
    
    def _load_model(self):
        """Load trained model from disk."""
        model_path = self.models_dir / "gap_priority_model.pkl"
        vectorizer_path = self.models_dir / "event_vectorizer.pkl"
        encoder_path = self.models_dir / "domain_encoder.pkl"
        
        if model_path.exists() and vectorizer_path.exists() and encoder_path.exists():
            try:
                with open(model_path, 'rb') as f:
                    self.model = pickle.load(f)
                with open(vectorizer_path, 'rb') as f:
                    self.vectorizer = pickle.load(f)
                with open(encoder_path, 'rb') as f:
                    self.domain_encoder = pickle.load(f)
                
                # Validate feature count compatibility
                if hasattr(self.model, 'n_features_in_'):
                    expected_features = self.model.n_features_in_
                    # Calculate current feature count
                    test_features = self._extract_event_features('TEST_EVENT')
                    vectorizer_size = 100 if self.vectorizer else 0
                    current_features = vectorizer_size + 2 + len(test_features)  # +2 for domain and co_occurrence
                    
                    if current_features != expected_features:
                        print(f"[WARNING] Gap Priority Model Feature Mismatch:")
                        print(f"          Model expects {expected_features} features, code generates {current_features}")
                        print(f"          Disabling ML model - will use rule-based fallback")
                        print(f"          To fix: Retrain model with sufficient historical data")
                        self.model = None
                        self.vectorizer = None
                        self.domain_encoder = None
                        return False
                
                # Extract feature importance (aggregated by feature group)
                if hasattr(self.model, 'feature_importances_'):
                    importances = self.model.feature_importances_
                    # Feature groups:
                    # 0-99: TF-IDF event patterns (100 features)
                    # 100: Domain (1 feature)
                    # 101: Co-occurrence (1 feature)
                    # 102-118: Event features (17 features)
                    tfidf_importance = float(sum(importances[:100])) if len(importances) > 100 else float(sum(importances))
                    domain_importance = float(importances[100]) if len(importances) > 100 else 0.0
                    cooccur_importance = float(importances[101]) if len(importances) > 101 else 0.0
                    event_features_importance = float(sum(importances[102:])) if len(importances) > 102 else 0.0
                    
                    total = tfidf_importance + domain_importance + cooccur_importance + event_features_importance
                    if total > 0:
                        self.feature_importance = {
                            'event_patterns': (tfidf_importance + event_features_importance) / total,  # Combined pattern importance
                            'domain': domain_importance / total,
                            'co_occurrence': cooccur_importance / total
                        }
                    else:
                        self.feature_importance = {'event_patterns': 0.5, 'domain': 0.3, 'co_occurrence': 0.2}
                
                print(f"[ML] Loaded gap priority model from {model_path}")
                return True
            except Exception as e:
                print(f"[WARNING] Could not load gap priority model: {e}")
                self.model = None
        return False
    
    def _extract_event_features(self, event_name: str) -> Dict[str, float]:
        """Extract ML features from event name."""
        event_upper = event_name.upper()
        
        features = {
            # Critical indicators
            'has_misp': 1.0 if 'MISP' in event_upper else 0.0,
            'has_stall': 1.0 if 'STALL' in event_upper else 0.0,
            'has_machine_clear': 1.0 if 'MACHINE_CLEAR' in event_upper or 'MACHINE_CLEARS' in event_upper else 0.0,
            'has_exception': 1.0 if 'EXCEPTION' in event_upper or 'FAULT' in event_upper else 0.0,
            
            # High priority indicators
            'has_cache_miss': 1.0 if any(x in event_upper for x in ['MISS', 'LLC_MISS']) else 0.0,
            'has_tlb': 1.0 if 'TLB' in event_upper or 'DTLB' in event_upper or 'ITLB' in event_upper else 0.0,
            'has_page_walk': 1.0 if 'PAGE_WALK' in event_upper or 'WALK' in event_upper else 0.0,
            'has_resource_stall': 1.0 if 'RESOURCE_STALL' in event_upper or 'RS_' in event_upper else 0.0,
            
            # Medium priority indicators
            'has_uops': 1.0 if 'UOPS' in event_upper else 0.0,
            'has_arith': 1.0 if 'ARITH' in event_upper or 'FP_' in event_upper else 0.0,
            'has_branch': 1.0 if 'BR_' in event_upper or 'BRANCH' in event_upper else 0.0,
            'has_load_store': 1.0 if any(x in event_upper for x in ['LOAD', 'STORE', 'MEM_']) else 0.0,
            
            # Low priority indicators
            'has_inst_retired': 1.0 if 'INST_RETIRED' in event_upper else 0.0,
            'has_cycles': 1.0 if 'CYCLE' in event_upper or 'CLK' in event_upper else 0.0,
            'has_topdown': 1.0 if 'TOPDOWN' in event_upper else 0.0,
        }
        
        # Event name length (normalized)
        features['name_length'] = min(len(event_name) / 50.0, 1.0)
        
        # Underscore count (complexity indicator)
        features['complexity'] = min(event_name.count('_') / 5.0, 1.0)
        
        return features
    
    def classify_gap_priority(self, event_name: str, domain: str, 
                             co_occurrence_count: int = 0) -> Tuple[str, float]:
        """
        Classify gap priority using ML model or rule-based fallback.
        
        Args:
            event_name: PMU event name
            domain: PMU domain (p-core, e-core, uncore, etc.)
            co_occurrence_count: How many other gaps this event co-occurs with
            
        Returns:
            Tuple of (priority_level, confidence_score)
        """
        # Try ML-based classification first
        if self.model is not None and SKLEARN_AVAILABLE:
            try:
                return self._ml_classify(event_name, domain, co_occurrence_count)
            except Exception as e:
                # Only warn once to avoid spam
                if not self.feature_mismatch_warned:
                    print(f"[WARNING] ML classification failed, using rule-based fallback")
                    print(f"          Reason: {str(e)}")
                    print(f"          Future warnings suppressed. Retrain model to restore ML functionality.")
                    self.feature_mismatch_warned = True
        
        # Fallback to rule-based classification
        return self._rule_based_classify(event_name, domain, co_occurrence_count)
    
    def _ml_classify(self, event_name: str, domain: str, 
                    co_occurrence_count: int) -> Tuple[str, float]:
        """ML-based classification using trained RandomForest."""
        # Extract features
        event_features = self._extract_event_features(event_name)
        
        # Vectorize event name for TF-IDF
        if self.vectorizer:
            event_vector = self.vectorizer.transform([event_name]).toarray()[0]
        else:
            event_vector = np.zeros(100)  # Fallback
        
        # Encode domain
        if self.domain_encoder:
            try:
                domain_encoded = self.domain_encoder.transform([domain.lower()])[0]
            except:
                domain_encoded = -1  # Unknown domain
        else:
            domain_encoded = hash(domain) % 10  # Fallback hash
        
        # Combine features
        feature_array = np.concatenate([
            event_vector,
            [domain_encoded],
            [co_occurrence_count / 10.0],  # Normalized
            list(event_features.values())
        ]).reshape(1, -1)
        
        # Predict
        prediction = self.model.predict(feature_array)[0]
        probabilities = self.model.predict_proba(feature_array)[0]
        confidence = float(max(probabilities))
        
        return prediction, confidence
    
    def _rule_based_classify(self, event_name: str, domain: str, 
                            co_occurrence_count: int) -> Tuple[str, float]:
        """Rule-based fallback classification."""
        event_upper = event_name.upper()
        score = 0.0
        
        # Critical indicators (score += 4)
        if any(x in event_upper for x in ['MISP', 'MACHINE_CLEAR', 'EXCEPTION', 'FAULT', 'STALL']):
            score += 4.0
        
        # High priority indicators (score += 3)
        if any(x in event_upper for x in ['MISS', 'TLB', 'PAGE_WALK', 'RESOURCE_STALL']):
            score += 3.0
        
        # Medium priority indicators (score += 2)
        if any(x in event_upper for x in ['UOPS', 'ARITH', 'BR_', 'BRANCH', 'LOAD', 'STORE']):
            score += 2.0
        
        # Low priority indicators (score += 1)
        if any(x in event_upper for x in ['INST_RETIRED', 'CYCLE', 'CLK', 'TOPDOWN']):
            score += 1.0
        
        # Domain-based adjustment
        # Check if it's a core domain (by pattern matching)
        if any(x in domain.lower() for x in ['core', 'atom', 'cpu']):
            score += 0.5  # Core events slightly more important
        # Check if it's uncore/memory domain
        elif any(x in domain.lower() for x in ['uncore', 'cbo', 'cha', 'imc', 'mc', 'cache']):
            score += 0.3
        
        # Co-occurrence boost (events that fail together are important)
        if co_occurrence_count > 5:
            score += 1.0
        elif co_occurrence_count > 2:
            score += 0.5
        
        # Classify based on score
        if score >= 4.0:
            return 'critical', 0.85
        elif score >= 3.0:
            return 'high', 0.75
        elif score >= 2.0:
            return 'medium', 0.65
        else:
            return 'low', 0.55
    
    def train_from_history(self, historical_runs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Train ML model from historical gap data.
        
        Args:
            historical_runs: List of past analysis results with gap data
            
        Returns:
            Training metrics and status
        """
        if not SKLEARN_AVAILABLE:
            return {'status': 'error', 'message': 'scikit-learn not available'}
        
        if len(historical_runs) < 3:
            return {'status': 'insufficient_data', 
                   'message': f'Need at least 3 runs for training (have {len(historical_runs)})'}
        
        # Extract training data
        X_events = []
        X_domains = []
        X_cooccur = []
        X_event_features_list = []  # NEW: Store extracted features for each event
        y_priorities = []
        
        for run in historical_runs:
            gaps = run.get('gaps', {}).get('non_toggling_events', [])
            gap_correlation = run.get('gap_correlation', {})
            
            for gap in gaps:
                event_name = gap.get('event_name', gap.get('event', ''))
                domain = gap.get('domain', 'unknown')
                priority = gap.get('priority', 'medium')
                
                # Count co-occurrences from correlation data
                cooccur_count = 0
                if gap_correlation and gap_correlation.get('correlation_matrix'):
                    matrix = gap_correlation['correlation_matrix']
                    if event_name in matrix:
                        cooccur_count = sum(1 for corr in matrix[event_name].values() if corr > 0.7)
                
                # Extract event features (MUST match _ml_classify)
                event_features = self._extract_event_features(event_name)
                
                X_events.append(event_name)
                X_domains.append(domain.lower())
                X_cooccur.append(cooccur_count)
                X_event_features_list.append(list(event_features.values()))  # NEW: Add extracted features
                y_priorities.append(priority if priority in self.PRIORITY_LEVELS else 'medium')
        
        if len(X_events) < 10:
            return {'status': 'insufficient_samples',
                   'message': f'Need at least 10 gap samples (have {len(X_events)})'}
        
        # Create TF-IDF vectorizer for event names
        self.vectorizer = TfidfVectorizer(max_features=100, analyzer='char', ngram_range=(2, 4))
        X_event_vectors = self.vectorizer.fit_transform(X_events).toarray()
        
        # Encode domains
        self.domain_encoder = LabelEncoder()
        X_domain_encoded = self.domain_encoder.fit_transform(X_domains).reshape(-1, 1)
        
        # Normalize co-occurrence counts
        X_cooccur_normalized = np.array(X_cooccur).reshape(-1, 1) / 10.0
        
        # Convert extracted features to array
        X_event_features_array = np.array(X_event_features_list)
        
        # Combine ALL features (MUST match _ml_classify)
        # Order: TF-IDF vectors + domain + co-occurrence + event features
        X_combined = np.hstack([
            X_event_vectors,           # 100 features from TF-IDF
            X_domain_encoded,          # 1 feature
            X_cooccur_normalized,      # 1 feature  
            X_event_features_array     # 17 features from _extract_event_features
        ])
        # Total: 100 + 1 + 1 + 17 = 119 features
        
        # Train RandomForest
        self.model = RandomForestClassifier(
            n_estimators=100,
            max_depth=10,
            min_samples_split=5,
            random_state=42,
            class_weight='balanced'  # Handle imbalanced priorities
        )
        
        self.model.fit(X_combined, y_priorities)
        
        # Calculate training accuracy
        train_score = self.model.score(X_combined, y_priorities)
        
        # Extract feature importance (aggregated by feature group)
        if hasattr(self.model, 'feature_importances_'):
            importances = self.model.feature_importances_
            tfidf_importance = float(sum(importances[:100]))
            domain_importance = float(importances[100]) if len(importances) > 100 else 0.0
            cooccur_importance = float(importances[101]) if len(importances) > 101 else 0.0
            event_features_importance = float(sum(importances[102:])) if len(importances) > 102 else 0.0
            
            total = tfidf_importance + domain_importance + cooccur_importance + event_features_importance
            if total > 0:
                self.feature_importance = {
                    'event_patterns': (tfidf_importance + event_features_importance) / total,
                    'domain': domain_importance / total,
                    'co_occurrence': cooccur_importance / total
                }
        
        # Save model
        self._save_model()
        
        return {
            'status': 'success',
            'model_type': 'RandomForestClassifier',
            'training_samples': len(X_events),
            'training_accuracy': float(train_score),
            'feature_count': X_combined.shape[1],
            'timestamp': datetime.now().isoformat()
        }
    
    def _save_model(self):
        """Save trained model to disk."""
        try:
            with open(self.models_dir / "gap_priority_model.pkl", 'wb') as f:
                pickle.dump(self.model, f)
            with open(self.models_dir / "event_vectorizer.pkl", 'wb') as f:
                pickle.dump(self.vectorizer, f)
            with open(self.models_dir / "domain_encoder.pkl", 'wb') as f:
                pickle.dump(self.domain_encoder, f)
            
            print(f"[ML] Saved gap priority model to {self.models_dir}")
        except Exception as e:
            print(f"[WARNING] Could not save gap priority model: {e}")
    
    def is_trained(self) -> bool:
        """Check if ML model is trained and ready."""
        return self.model is not None and SKLEARN_AVAILABLE
    
    def get_feature_importance(self) -> Dict[str, float]:
        """Get feature importance scores from trained model."""
        if not self.is_trained():
            return {}
        
        # For gap prioritizer, we track feature importance during classification
        # Return the stored feature importance
        return self.feature_importance if hasattr(self, 'feature_importance') else {}
    
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
            'method': 'ML-based (RandomForest)',
            'model_exists': True,
            'feature_importance': self.feature_importance,
            'model_path': str(self.models_dir / "gap_priority_model.pkl")
        }
