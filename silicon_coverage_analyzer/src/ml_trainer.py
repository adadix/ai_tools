"""
ML Trainer - Automatic Model Training on Collected Coverage Data

Trains ML models on coverage datasets collected in C:/silicon_coverage_analyzer/data
Implements incremental learning, pattern recognition, and model persistence.

Uses Intel-accelerated scikit-learn when available for 10-100x speedup.
"""

import json
import logging
import pickle
import numpy as np
import pandas as pd
import warnings
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Tuple
from collections import defaultdict

# Priority 1 ML Models
from src.ml_gap_prioritizer import MLGapPrioritizer
from src.ml_workload_detector import MLWorkloadDetector
from src.ml_action_prioritizer import MLActionPrioritizer

# High-Value ML Models
from src.ml_stress_recommender import MLStressRecommender
from src.ml_saturation_predictor import MLSaturationPredictor
from src.ml_workload_clusterer import MLWorkloadClusterer
from src.ml_gap_forecaster import MLGapForecaster

# Custom JSON encoder for numpy types
class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if hasattr(obj, 'item'):  # numpy int64, float64, etc.
            return obj.item()
        if hasattr(obj, 'tolist'):  # numpy arrays
            return obj.tolist()
        return super().default(obj)

# Suppress numpy warnings for empty slices (inactive events)
warnings.filterwarnings('ignore', message='Mean of empty slice')
warnings.filterwarnings('ignore', message='invalid value encountered in.*divide')
warnings.filterwarnings('ignore', message='Degrees of freedom <= 0 for slice')

# Intel Extension for Scikit-learn (optional but recommended)
try:
    from sklearnex import patch_sklearn
    patch_sklearn()
    INTEL_ACCEL = True
    logging.info("[OK] Using Intel-accelerated scikit-learn (10-100x speedup)")
except ImportError:
    INTEL_ACCEL = False
    logging.info("[i]  Using standard scikit-learn (install scikit-learn-intelex for acceleration)")

try:
    from sklearn.ensemble import RandomForestClassifier, IsolationForest, GradientBoostingRegressor
    from sklearn.preprocessing import StandardScaler
    from sklearn.cluster import DBSCAN
    import joblib
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    logging.warning("scikit-learn not available - ML training will be disabled")

logger = logging.getLogger(__name__)


class MLTrainer:
    """
    Trains ML models on collected silicon coverage data.
    Implements incremental learning and model persistence.
    """
    
    def __init__(self, config):
        """
        Initialize ML Trainer.
        
        Args:
            config (dict): Configuration with training settings
        """
        self.config = config
        self.training_config = config.get('training_data', {})
        self.enabled = SKLEARN_AVAILABLE and self.training_config.get('enabled', True)
        
        # Data directory structure
        self.base_dir = Path(r"C:\silicon_coverage_analyzer_data")
        self.raw_datasets_dir = self.base_dir / "raw_datasets"  # Changed from raw_data
        self.processed_data_dir = self.base_dir / "processed_data"
        self.models_dir = self.base_dir / "models"
        self.logs_dir = self.base_dir / "training_logs"
        
        # Create directories
        for directory in [self.raw_datasets_dir, self.processed_data_dir, self.models_dir, self.logs_dir]:
            directory.mkdir(parents=True, exist_ok=True)
        
        # Product-aware ML: Track current product and models per product
        self.current_product = None  # Will be set when data is saved
        self.product_registry = {}  # Maps product_name -> product_info
        
        # Model instances (product-specific)
        self.anomaly_detector = None
        self.coverage_predictor = None
        self.pattern_classifier = None
        self.event_clusterer = None
        self.stress_correlation_model = None  # For stress-event correlation
        self.health_predictor = None  # NEW: For health-coverage correlation
        
        # Priority 1 ML Models
        self.gap_prioritizer = MLGapPrioritizer(str(self.base_dir))
        self.workload_detector = MLWorkloadDetector(str(self.base_dir))
        self.action_prioritizer = MLActionPrioritizer(str(self.base_dir))
        
        # High-Value ML Models
        self.stress_recommender = MLStressRecommender(str(self.base_dir))
        self.saturation_predictor = MLSaturationPredictor(str(self.base_dir))
        self.workload_clusterer = MLWorkloadClusterer(str(self.base_dir))
        self.gap_forecaster = MLGapForecaster(str(self.base_dir))
        
        # Separate scalers for each model to avoid feature contamination
        if SKLEARN_AVAILABLE:
            self.anomaly_scaler = StandardScaler()
            self.pattern_scaler = StandardScaler()
            self.cluster_scaler = StandardScaler()
            self.stress_scaler = StandardScaler()
            self.health_scaler = StandardScaler()
        else:
            self.anomaly_scaler = None
            self.pattern_scaler = None
            self.cluster_scaler = None
            self.stress_scaler = None
            self.health_scaler = None
        
        # Training history (product-specific)
        self.training_history = {
            'sessions': [],
            'model_versions': {},
            'performance_metrics': {}
        }
        
        # Load product registry
        if self.enabled:
            self._load_product_registry()
        else:
            logger.info("ML training disabled (scikit-learn not available)")
    
    def _get_product_identifier(self, metadata: Dict[str, Any]) -> str:
        """
        Extract product identifier from metadata.
        
        Args:
            metadata: Analysis metadata containing hardware info
            
        Returns:
            str: Normalized product identifier (e.g., 'arrowlake_s', 'wildcatlake')
        """
        # Try to get product name from metadata
        hardware_config = metadata.get('hardware_config', {})
        
        # FIRST: Check if product_id is directly available in hardware_config
        if 'product_id' in hardware_config and hardware_config['product_id']:
            return hardware_config['product_id']
        
        product_name = hardware_config.get('product_name', '')
        
        # Fallback to cpu_family if product_name is empty
        if not product_name:
            product_name = hardware_config.get('cpu_family', '')
        
        # Fallback to hardware string
        if not product_name:
            product_name = metadata.get('hardware', 'unknown')
        
        # Normalize product name: lowercase, replace spaces/hyphens with underscores
        product_id = product_name.lower().replace(' ', '_').replace('-', '_').replace('(', '').replace(')', '')
        
        # Remove common prefixes/suffixes and verbose phrases
        product_id = (product_id
                     .replace('intel_', '')
                     .replace('_processor', '')
                     .replace('_cpu', '')
                     .replace('microarchitecture_code_named_', '')
                     .replace('microarchitecture_', '')
                     .replace('code_named_', ''))
        
        # Handle empty or invalid - use existing product folder if available
        if not product_id or product_id == 'unknown' or product_id == '':
            existing_products = [d.name for d in self.raw_datasets_dir.glob('*') if d.is_dir()]
            if existing_products:
                product_id = existing_products[0]  # Use the first existing product folder
                logger.info(f" Product detection fallback: using existing folder '{product_id}'")
            else:
                product_id = 'generic'
        
        return product_id
    
    def _load_product_registry(self):
        """Load product registry from disk."""
        registry_path = self.base_dir / "product_registry.json"
        if registry_path.exists():
            try:
                with open(registry_path, 'r') as f:
                    self.product_registry = json.load(f)
                logger.info(f"[OK] Loaded product registry: {len(self.product_registry)} products")
                if self.product_registry:
                    logger.info(f"   Known products: {', '.join(self.product_registry.keys())}")
            except Exception as e:
                logger.warning(f"Could not load product registry: {e}")
                self.product_registry = {}
        else:
            self.product_registry = {}
    
    def _save_product_registry(self):
        """Save product registry to disk."""
        registry_path = self.base_dir / "product_registry.json"
        try:
            with open(registry_path, 'w') as f:
                json.dump(self.product_registry, f, indent=2, cls=NumpyEncoder)
        except Exception as e:
            logger.error(f"Failed to save product registry: {e}")
    
    def _register_product(self, product_id: str, metadata: Dict[str, Any]):
        """
        Register a new product in the registry.
        
        Args:
            product_id: Product identifier
            metadata: Product metadata
        """
        # Don't register "generic" as a product
        if product_id == 'generic':
            logger.warning(f"[WARN] Skipping registration of 'generic' product")
            return
        
        if product_id not in self.product_registry:
            hardware_config = metadata.get('hardware_config', {})
            
            self.product_registry[product_id] = {
                'product_id': product_id,
                'product_name': hardware_config.get('product_name', product_id),
                'cpu_family': hardware_config.get('cpu_family', 'unknown'),
                'first_seen': datetime.now().isoformat(),
                'total_cores': hardware_config.get('total_cores', 0),
                'p_cores': hardware_config.get('p_cores', 0),
                'e_cores': hardware_config.get('e_cores', 0),
                'pmu_units': hardware_config.get('pmu_units', {}),
                'domains_seen': [],
                'total_runs': 0,
                'model_versions': {}
            }
            
            # Create product-specific directories
            product_models_dir = self.models_dir / product_id
            product_datasets_dir = self.raw_datasets_dir / product_id
            product_logs_dir = self.logs_dir / product_id
            
            for directory in [product_models_dir, product_datasets_dir, product_logs_dir]:
                directory.mkdir(parents=True, exist_ok=True)
            
            logger.info(f" NEW PRODUCT REGISTERED: {self.product_registry[product_id]['product_name']}")
            logger.info(f"   Product ID: {product_id}")
            logger.info(f"   Created directories: models/{product_id}, raw_datasets/{product_id}, training_logs/{product_id}")
            
            self._save_product_registry()
        else:
            # Update run count
            self.product_registry[product_id]['total_runs'] += 1
            self.product_registry[product_id]['last_seen'] = datetime.now().isoformat()
    
    def _load_models(self, product_id: str):
        """Load existing trained models from disk for specific product.
        
        Args:
            product_id: Product identifier to load models for
        """
        product_models_dir = self.models_dir / product_id
        
        if not product_models_dir.exists():
            logger.info(f"   No existing models for {product_id} (new product)")
            return
        
        try:
            anomaly_model_path = product_models_dir / "anomaly_detector.pkl"
            if anomaly_model_path.exists():
                self.anomaly_detector = joblib.load(anomaly_model_path)
                logger.info(f"[OK] Loaded {product_id} anomaly detector model")
            
            predictor_model_path = product_models_dir / "coverage_predictor.pkl"
            if predictor_model_path.exists():
                self.coverage_predictor = joblib.load(predictor_model_path)
                logger.info(f"[OK] Loaded {product_id} coverage predictor model")
            
            classifier_model_path = product_models_dir / "pattern_classifier.pkl"
            if classifier_model_path.exists():
                self.pattern_classifier = joblib.load(classifier_model_path)
                logger.info(f"[OK] Loaded {product_id} pattern classifier model")
            
            clusterer_model_path = product_models_dir / "event_clusterer.pkl"
            if clusterer_model_path.exists():
                self.event_clusterer = joblib.load(clusterer_model_path)
                logger.info(f"[OK] Loaded {product_id} event clusterer model")
            
            stress_model_path = product_models_dir / "stress_correlation_model.pkl"
            if stress_model_path.exists():
                self.stress_correlation_model = joblib.load(stress_model_path)
                logger.info(f"[OK] Loaded {product_id} stress correlation model")
            
            health_predictor_path = product_models_dir / "health_predictor.pkl"
            if health_predictor_path.exists():
                self.health_predictor = joblib.load(health_predictor_path)
                logger.info(f"[OK] Loaded {product_id} health predictor model")
            
            # Load all model-specific scalers
            anomaly_scaler_path = product_models_dir / "anomaly_scaler.pkl"
            if anomaly_scaler_path.exists():
                self.anomaly_scaler = joblib.load(anomaly_scaler_path)
                logger.info(f"[OK] Loaded {product_id} anomaly scaler")
            
            cluster_scaler_path = product_models_dir / "cluster_scaler.pkl"
            if cluster_scaler_path.exists():
                self.cluster_scaler = joblib.load(cluster_scaler_path)
                logger.info(f"[OK] Loaded {product_id} cluster scaler")
            
            stress_scaler_path = product_models_dir / "stress_scaler.pkl"
            if stress_scaler_path.exists():
                self.stress_scaler = joblib.load(stress_scaler_path)
                logger.info(f"[OK] Loaded {product_id} stress scaler")
            
            health_scaler_path = product_models_dir / "health_scaler.pkl"
            if health_scaler_path.exists():
                self.health_scaler = joblib.load(health_scaler_path)
                logger.info(f"[OK] Loaded {product_id} health scaler")
                
        except Exception as e:
            logger.warning(f"Could not load existing models for {product_id}: {e}")
    
    def _save_models(self, product_id: str):
        """Save trained models to disk for specific product.
        
        Args:
            product_id: Product identifier to save models for
        """
        product_models_dir = self.models_dir / product_id
        product_models_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            if self.anomaly_detector:
                joblib.dump(self.anomaly_detector, product_models_dir / "anomaly_detector.pkl")
            
            if self.coverage_predictor:
                joblib.dump(self.coverage_predictor, product_models_dir / "coverage_predictor.pkl")
            
            if self.pattern_classifier:
                joblib.dump(self.pattern_classifier, product_models_dir / "pattern_classifier.pkl")
            
            if self.event_clusterer:
                joblib.dump(self.event_clusterer, product_models_dir / "event_clusterer.pkl")
            
            if self.stress_correlation_model:
                joblib.dump(self.stress_correlation_model, product_models_dir / "stress_correlation_model.pkl")
            
            if self.health_predictor:
                joblib.dump(self.health_predictor, product_models_dir / "health_predictor.pkl")
            
            # Save all model-specific scalers
            if self.anomaly_scaler:
                joblib.dump(self.anomaly_scaler, product_models_dir / "anomaly_scaler.pkl")
            if self.cluster_scaler:
                joblib.dump(self.cluster_scaler, product_models_dir / "cluster_scaler.pkl")
            if self.stress_scaler:
                joblib.dump(self.stress_scaler, product_models_dir / "stress_scaler.pkl")
            if self.health_scaler:
                joblib.dump(self.health_scaler, product_models_dir / "health_scaler.pkl")
            
            logger.info(f"[OK] Models saved successfully for {product_id}")
            
            # Update product registry with model versions
            if product_id in self.product_registry:
                self.product_registry[product_id]['model_versions']['last_trained'] = datetime.now().isoformat()
                self._save_product_registry()
            
        except Exception as e:
            logger.error(f"Failed to save models for {product_id}: {e}")
    
    def _load_training_history(self, product_id: str):
        """Load training history from disk for specific product.
        
        Args:
            product_id: Product identifier to load history for
        """
        product_logs_dir = self.logs_dir / product_id
        history_path = product_logs_dir / "training_history.json"
        
        if history_path.exists():
            try:
                with open(history_path, 'r') as f:
                    self.training_history = json.load(f)
                logger.info(f"[OK] Loaded {product_id} training history ({len(self.training_history['sessions'])} sessions)")
            except Exception as e:
                logger.warning(f"Could not load training history for {product_id}: {e}")
                self.training_history = {'sessions': [], 'model_versions': {}, 'performance_metrics': {}}
        else:
            self.training_history = {'sessions': [], 'model_versions': {}, 'performance_metrics': {}}
    
    def _save_training_history(self, product_id: str):
        """Save training history to disk for specific product.
        
        Args:
            product_id: Product identifier to save history for
        """
        product_logs_dir = self.logs_dir / product_id
        product_logs_dir.mkdir(parents=True, exist_ok=True)
        history_path = product_logs_dir / "training_history.json"
        
        try:
            with open(history_path, 'w') as f:
                json.dump(self.training_history, f, indent=2, cls=NumpyEncoder)
        except Exception as e:
            logger.error(f"Failed to save training history for {product_id}: {e}")
    
    def save_coverage_data(self, coverage_results: Dict[str, Any], metadata: Dict[str, Any]):
        """
        Save collected coverage data for training.
        
        Args:
            coverage_results: Coverage analysis results (can include 'coverage', 'gaps', 'summary' keys)
            metadata: Collection metadata (timestamp, hardware, workload)
        """
        if not self.enabled:
            return
        
        # Detect product from metadata
        product_id = self._get_product_identifier(metadata)
        self.current_product = product_id
        
        # Register product if new
        self._register_product(product_id, metadata)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save raw data to product-specific directory
        product_datasets_dir = self.raw_datasets_dir / product_id
        product_datasets_dir.mkdir(parents=True, exist_ok=True)
        
        raw_file = product_datasets_dir / f"coverage_{timestamp}.json"
        try:
            # Include hardware_config in saved data for product tracking
            # Support both old format (direct coverage) and new format (with gaps/summary)
            if 'coverage' in coverage_results:
                # New format with gaps and summary
                data_to_save = {
                    'coverage_results': coverage_results.get('coverage', {}),
                    'gaps': coverage_results.get('gaps', {}),
                    'summary': coverage_results.get('summary', {}),
                    'metadata': metadata,
                    'timestamp': timestamp,
                    'product_id': product_id,
                    'hardware_config': metadata.get('hardware_config', {})
                }
            else:
                # Old format - just coverage results
                data_to_save = {
                    'coverage_results': coverage_results,
                    'metadata': metadata,
                    'timestamp': timestamp,
                    'product_id': product_id,
                    'hardware_config': metadata.get('hardware_config', {})
                }
            
            with open(raw_file, 'w') as f:
                json.dump(data_to_save, f, indent=2, cls=NumpyEncoder)
            
            logger.info(f"[OK] Saved coverage data for {product_id}: {raw_file.name}")
            
            # Update product registry with domains seen
            coverage_data = coverage_results.get('coverage', coverage_results) if 'coverage' in coverage_results else coverage_results
            if 'coverage_results' in coverage_data:
                domains = list(coverage_data['coverage_results'].keys())
            else:
                domains = list(coverage_data.keys())
            
            if product_id in self.product_registry:
                existing_domains = set(self.product_registry[product_id].get('domains_seen', []))
                new_domains = set(domains)
                all_domains = existing_domains.union(new_domains)
                self.product_registry[product_id]['domains_seen'] = sorted(list(all_domains))
                self._save_product_registry()
            
        except Exception as e:
            logger.error(f"Failed to save coverage data for {product_id}: {e}")
    
    def train_on_collected_data(self, current_results: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Train ML models on all collected coverage data for the current product.
        
        Args:
            current_results: Optional current analysis results to include
        
        Returns:
            dict: Training results and model performance metrics
        """
        if not self.enabled:
            return {'status': 'disabled', 'message': 'ML training not available'}
        
        # Determine product ID from current results or use current product
        if current_results and 'metadata' in current_results:
            product_id = self._get_product_identifier(current_results['metadata'])
        elif self.current_product:
            product_id = self.current_product
        else:
            logger.warning("[WARN]  Cannot determine product for training")
            return {'status': 'error', 'message': 'Product not identified'}
        
        logger.info("="*80)
        logger.info(f"STARTING ML MODEL TRAINING - PRODUCT: {product_id.upper()}")
        logger.info("="*80)
        
        # Load product-specific models and history
        self._load_models(product_id)
        self._load_training_history(product_id)
        
        logger.info(" PHASE 1: LOADING & UNDERSTANDING PRODUCT DATA")
        logger.info("-"*80)
        
        training_session = {
            'timestamp': datetime.now().isoformat(),
            'product_id': product_id,
            'models_trained': [],
            'data_processed': 0,
            'metrics': {}
        }
        
        # PHASE 1: Load all historical data for this product
        logger.info(f" Step 1.1: Loading historical coverage datasets for {product_id}...")
        historical_data = self._load_historical_data(product_id)
        
        # Add current results if provided
        if current_results:
            historical_data.append(current_results)
            training_session['includes_current'] = True
            logger.info("[OK] Step 1.2: Added current run to training data")
        
        if len(historical_data) == 0:
            logger.warning(f"[WARN]  No training data available yet for {product_id} - ML needs data to learn")
            return {'status': 'no_data', 'message': f'No training data available for {product_id}'}
        
        training_session['data_processed'] = len(historical_data)
        logger.info(f"[OK] Step 1.3: Loaded {len(historical_data)} datasets from {product_id} history")
        
        # Show product-specific info
        if product_id in self.product_registry:
            product_info = self.product_registry[product_id]
            logger.info(f"   Product: {product_info.get('product_name', product_id)}")
            logger.info(f"   Domains: {', '.join(product_info.get('domains_seen', []))}")
            logger.info(f"   Total runs: {product_info.get('total_runs', 0)}")
        
        logger.info("")
        logger.info(f" PHASE 2: UNDERSTANDING {product_id.upper()} PATTERNS")
        logger.info("-"*80)
        
        # PHASE 2: Extract features to understand patterns
        logger.info(" Step 2.1: Analyzing coverage patterns across all runs...")
        logger.info("           -  Per-Core: Toggle rates, count distributions (mean/std/min/max/CV)")
        logger.info("           -  Per-Module: Domain-specific activity rates (p-core, e-core, IMC, CBO, NCU, etc.)")
        logger.info("           -  Per-Event: Individual PMU event behaviors and correlations")
        logger.info("           -   Temporal Patterns: Coverage trends over time")
        features_df = self._extract_features(historical_data)
        
        if features_df is None or len(features_df) == 0:
            logger.error("[FAIL] Failed to extract features from data")
            return {'status': 'error', 'message': 'Feature extraction failed'}
        
        logger.info(f"[OK] Step 2.2: Extracted {len(features_df)} feature vectors from project data")
        
        # Save processed features to CSV for transparency (product-specific)
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            product_processed_dir = self.processed_data_dir / product_id
            product_processed_dir.mkdir(parents=True, exist_ok=True)
            features_file = product_processed_dir / f"features_{timestamp}.csv"
            features_df.to_csv(features_file, index=False)
            logger.info(f" Step 2.3: Saved processed features to {product_id}/{features_file.name}")
        except Exception as e:
            logger.warning(f"[WARN]  Could not save processed features: {e}")
        
        # Count unique domains and events analyzed
        unique_domains = features_df['domain'].nunique() if 'domain' in features_df.columns else 0
        unique_events = features_df['event_name'].nunique() if 'event_name' in features_df.columns else 0
        
        logger.info(f"           -  Granular Analysis: {unique_events} unique events across {unique_domains} domains")
        logger.info(f"           -  Feature Attributes: {len(features_df.columns)} attributes per event (toggle rates, core distributions, counts)")
        logger.info("")
        logger.info("[ML] PHASE 3: TRAINING ML MODELS ON PROJECT DATA")
        logger.info("-"*80)
        
        # PHASE 3: Train models based on learned patterns
        results = {}
        
        # 1. Anomaly Detector
        logger.info(" Training Model 1/4: Anomaly Detector...")
        logger.info("           Goal: Identify unusual event behaviors based on project history")
        anomaly_result = self._train_anomaly_detector(features_df)
        if anomaly_result['status'] == 'success':
            training_session['models_trained'].append('anomaly_detector')
            results['anomaly_detector'] = anomaly_result
            logger.info("[OK] Anomaly Detector trained successfully")
        
        # 2. Coverage Predictor
        logger.info(" Training Model 2/4: Coverage Predictor...")
        logger.info("           Goal: Predict which events will toggle based on workload type")
        predictor_result = self._train_coverage_predictor(features_df, historical_data)
        if predictor_result['status'] == 'success':
            training_session['models_trained'].append('coverage_predictor')
            results['coverage_predictor'] = predictor_result
            logger.info("[OK] Coverage Predictor trained successfully")
        
        # 3. Pattern Classifier
        logger.info(" Training Model 3/4: Pattern Classifier...")
        logger.info("           Goal: Classify events into behavior patterns (low/medium/high activity)")
        classifier_result = self._train_pattern_classifier(features_df, historical_data)
        if classifier_result['status'] == 'success':
            training_session['models_trained'].append('pattern_classifier')
            results['pattern_classifier'] = classifier_result
            logger.info("[OK] Pattern Classifier trained successfully")
            results['pattern_classifier'] = classifier_result
        
        # 4. Event Clusterer
        logger.info(" Training Model 4/5: Event Clusterer...")
        logger.info("           Goal: Group similar events to understand coverage relationships")
        clusterer_result = self._train_event_clusterer(features_df)
        if clusterer_result['status'] == 'success':
            training_session['models_trained'].append('event_clusterer')
            results['event_clusterer'] = clusterer_result
            logger.info("[OK] Event Clusterer trained successfully")
        
        # 5. Stress Correlation Model
        logger.info(" Training Model 5/6: Stress-Event Correlation Model...")
        logger.info("           Goal: Learn which events correlate with workload stress (Prime95, SuperCollider, etc.)")
        stress_corr_result = self._train_stress_correlation_model(features_df, historical_data)
        logger.info(f"[ML-Stress] Training result status: {stress_corr_result.get('status')}")
        logger.info(f"[ML-Stress] Training result message: {stress_corr_result.get('message', 'N/A')}")
        if stress_corr_result['status'] == 'success':
            training_session['models_trained'].append('stress_correlation_model')
            results['stress_correlation_model'] = stress_corr_result
            logger.info("[OK] Stress Correlation Model trained successfully")
        else:
            logger.warning(f"[WARN] Stress Correlation Model training failed: {stress_corr_result.get('message', 'Unknown error')}")
        
        # 6. Health Score Predictor (NEW)
        logger.info(" Training Model 6/9: Health Score Predictor...")
        logger.info("           Goal: Predict coverage impact from system health metrics (CPU, memory, disk, temp)")
        health_pred_result = self._train_health_predictor(historical_data)
        if health_pred_result['status'] == 'success':
            training_session['models_trained'].append('health_predictor')
            results['health_predictor'] = health_pred_result
            logger.info("[OK] Health Score Predictor trained successfully")
        else:
            logger.info(f"[i]  Health predictor not trained: {health_pred_result.get('message', 'Insufficient data')}")
        
        # 7. Gap Priority Classifier (Priority 1)
        logger.info(" Training Model 7/9: Gap Priority Classifier...")
        logger.info("           Goal: Classify coverage gaps by priority (critical/high/medium/low)")
        gap_priority_result = self._train_gap_prioritizer(historical_data)
        if gap_priority_result['status'] == 'success':
            training_session['models_trained'].append('gap_prioritizer')
            results['gap_prioritizer'] = gap_priority_result
            logger.info("[OK] Gap Priority Classifier trained successfully")
        else:
            logger.info(f"[i]  Gap prioritizer not trained: {gap_priority_result.get('message', 'Insufficient data')}")
        
        # 8. Workload Detector (Priority 1)
        logger.info(" Training Model 8/9: Workload Detector...")
        logger.info("           Goal: Detect workload type (CPU/memory/mixed stress, idle) from coverage patterns")
        workload_detect_result = self._train_workload_detector(historical_data)
        if workload_detect_result['status'] == 'success':
            training_session['models_trained'].append('workload_detector')
            results['workload_detector'] = workload_detect_result
            logger.info("[OK] Workload Detector trained successfully")
        else:
            logger.info(f"[i]  Workload detector not trained: {workload_detect_result.get('message', 'Insufficient data')}")
        
        # 9. Action Prioritizer (Priority 1)
        logger.info(" Training Model 9/9: Action Prioritizer...")
        logger.info("           Goal: Rank recommended actions by impact using Learning-to-Rank")
        action_priority_result = self._train_action_prioritizer(historical_data)
        if action_priority_result['status'] == 'success':
            training_session['models_trained'].append('action_prioritizer')
            results['action_prioritizer'] = action_priority_result
            logger.info("[OK] Action Prioritizer trained successfully")
        else:
            logger.info(f"[i]  Action prioritizer not trained: {action_priority_result.get('message', 'Insufficient data')}")
        
        # 10. Stress Test Recommender (High-Value)
        logger.info(" Training Model 10/13: Stress Test Recommender...")
        logger.info("           Goal: Recommend next stress test for maximum coverage gain")
        stress_rec_result = self._train_stress_recommender(historical_data)
        if stress_rec_result['status'] == 'success':
            training_session['models_trained'].append('stress_recommender')
            results['stress_recommender'] = stress_rec_result
            logger.info("[OK] Stress Test Recommender trained successfully")
        else:
            logger.info(f"[i]  Stress recommender not trained: {stress_rec_result.get('message', 'Insufficient data')}")
        
        # 11. Coverage Saturation Predictor (High-Value)
        logger.info(" Training Model 11/13: Coverage Saturation Predictor...")
        logger.info("           Goal: Predict optimal collection duration")
        saturation_result = self._train_saturation_predictor(historical_data)
        if saturation_result['status'] == 'success':
            training_session['models_trained'].append('saturation_predictor')
            results['saturation_predictor'] = saturation_result
            logger.info("[OK] Saturation Predictor trained successfully")
        else:
            logger.info(f"[i]  Saturation predictor not trained: {saturation_result.get('message', 'Insufficient data')}")
        
        # 12. Workload Similarity Clusterer (High-Value)
        logger.info(" Training Model 12/13: Workload Similarity Clusterer...")
        logger.info("           Goal: Cluster runs by similarity, identify coverage gaps")
        cluster_result = self._train_workload_clusterer(historical_data)
        if cluster_result['status'] == 'success':
            training_session['models_trained'].append('workload_clusterer')
            results['workload_clusterer'] = cluster_result
            logger.info("[OK] Workload Clusterer trained successfully")
        else:
            logger.info(f"[i]  Workload clusterer not trained: {cluster_result.get('message', 'Insufficient data')}")
        
        # 13. Gap Trend Forecaster (High-Value)
        logger.info(" Training Model 13/13: Gap Trend Forecaster...")
        logger.info("           Goal: Forecast future coverage and gap trends")
        forecast_result = self._train_gap_forecaster(historical_data)
        if forecast_result['status'] == 'success':
            training_session['models_trained'].append('gap_forecaster')
            results['gap_forecaster'] = forecast_result
            logger.info("[OK] Gap Forecaster trained successfully")
        else:
            logger.info(f"[i]  Gap forecaster not trained: {forecast_result.get('message', 'Insufficient data')}")
        
        # 14. Auto-Learn Instruction Mix Categories (runs after every training)
        logger.info(" Learning instruction mix categories from collected events...")
        try:
            instruction_mix_result = self._learn_instruction_categories(product_id)
            logger.info(f"Instruction mix result: {instruction_mix_result}")
            if instruction_mix_result.get('status') == 'success':
                results['instruction_mix_learning'] = instruction_mix_result
                logger.info(f"[OK] Learned {instruction_mix_result.get('categories', 0)} instruction categories")
            else:
                logger.warning(f"[WARN] Instruction mix learning status: {instruction_mix_result.get('status')}")
                logger.warning(f"[WARN] Error: {instruction_mix_result.get('error', 'Unknown error')}")
        except Exception as e:
            logger.error(f"[FAIL] Exception in instruction mix learning: {e}")
        
        logger.info("")
        logger.info("="*80)
        logger.info(f"[OK] ML TRAINING COMPLETE: {len(training_session['models_trained'])}/13 models trained")
        logger.info("="*80)
        # Save models and history (product-specific)
        self._save_models(product_id)
        training_session['metrics'] = results
        self.training_history['sessions'].append(training_session)
        self._save_training_history(product_id)
        
        logger.info("="*80)
        logger.info(f"[OK] TRAINING COMPLETE - {len(training_session['models_trained'])} models updated for {product_id}")
        logger.info("="*80)
        
        return {
            'status': 'success',
            'session': training_session,
            'results': results
        }
    
    def _load_historical_data(self, product_id: str) -> List[Dict[str, Any]]:
        """Load all historical coverage data for specific product.
        
        Args:
            product_id: Product identifier to load data for
            
        Returns:
            List of coverage datasets for this product
        """
        data = []
        contamination_count = 0
        
        # Load from product-specific directory
        product_datasets_dir = self.raw_datasets_dir / product_id
        
        if not product_datasets_dir.exists():
            logger.warning(f"   [FAIL] No historical data directory for {product_id} (path doesn't exist)")
            return data
        
        for json_file in product_datasets_dir.glob("coverage_*.json"):
            try:
                with open(json_file, 'r') as f:
                    file_data = json.load(f)
                    
                    # CRITICAL: Validate that file's product_id matches folder
                    file_product_id = file_data.get('product_id', '')
                    if file_product_id and file_product_id != product_id:
                        contamination_count += 1
                        logger.warning(f"   [WARN]  CONTAMINATION: {json_file.name} has product_id '{file_product_id}' but is in '{product_id}' folder - SKIPPING")
                        continue
                    
                    data.append(file_data)
            except Exception as e:
                logger.warning(f"Could not load {json_file.name}: {e}")
        
        if contamination_count > 0:
            logger.warning(f"   [WARN]  Found {contamination_count} contaminated files in {product_id} folder")
        
        # Sort by timestamp
        data.sort(key=lambda x: x.get('timestamp', ''))
        
        return data
    
    def _extract_features(self, datasets: List[Dict[str, Any]]) -> pd.DataFrame:
        """
        Extract ML features from coverage datasets.
        
        Features extracted:
        - Event toggle rates per domain
        - Per-core/unit distribution patterns
        - Coverage percentages
        - Temporal patterns (if multiple samples)
        - Event correlations
        """
        features = []
        
        for dataset in datasets:
            coverage_results = dataset.get('coverage_results', {})
            metadata = dataset.get('metadata', {})
            
            # Handle both dict and other formats
            if not isinstance(coverage_results, dict):
                logger.warning(f"Skipping dataset - coverage_results is not a dict: {type(coverage_results)}")
                continue
            
            # Check for domain_results (new format from analyze_coverage)
            domain_results = coverage_results.get('domain_results', {})
            if domain_results and isinstance(domain_results, dict):
                # New format: domain_results contains active_events list
                for domain, domain_data in domain_results.items():
                    if not isinstance(domain_data, dict):
                        continue
                    
                    # Extract domain-level features
                    # Get workload from stress_tracking if available
                    stress_tracking = metadata.get('stress_tracking', {})
                    if stress_tracking and stress_tracking.get('classification'):
                        workload_label = stress_tracking['classification'].get('label', 'unknown')
                    else:
                        workload_label = metadata.get('workload', 'unknown')
                    
                    domain_feature = {
                        'timestamp': dataset.get('timestamp', ''),
                        'domain': domain,
                        'event_name': f'{domain}_domain_summary',
                        'activity_rate': domain_data.get('activity_rate', 0),
                        'total_tested': domain_data.get('total_tested', 0),
                        'workload': workload_label,
                        'duration_seconds': metadata.get('duration_seconds', 0),
                        'os_type': metadata.get('os_type', 'windows'),  # Platform awareness for ML
                        # Composite feature: stress + OS combination for pattern learning
                        'stress_os_combo': f"{workload_label}_{metadata.get('os_type', 'windows')}",
                        # Legacy context features (keep for backward compatibility)
                        'cpu_temp': metadata.get('thermal_context', {}).get('cpu_temp_current', 0),
                        'cpu_freq_mhz': metadata.get('frequency_context', {}).get('current_freq_mhz', 0),
                        'memory_util_pct': metadata.get('memory_context', {}).get('memory_utilization_percent', 0),
                        'cpu_util_pct': metadata.get('workload_profile', {}).get('cpu_utilization_percent', 0),
                        # Health metrics (using actual field names from saved data)
                        'health_cpu_avg': metadata.get('health_metrics', {}).get('avg_cpu_usage', 0),
                        'health_mem_avg': metadata.get('health_metrics', {}).get('avg_memory_usage', 0),
                        'health_disk_min_gb': metadata.get('health_metrics', {}).get('avg_disk_free_gb', 0),
                        'health_duration_min': metadata.get('health_metrics', {}).get('duration_minutes', 0),
                        'health_samples': metadata.get('health_metrics', {}).get('total_samples', 0),
                        'health_issues': metadata.get('health_metrics', {}).get('health_issues', 0),
                    }
                    features.append(domain_feature)
                    
                    # Extract event-level features from active_events
                    active_events = domain_data.get('active_events', [])
                    for event_data in active_events:
                        if not isinstance(event_data, dict):
                            continue
                        
                        feature_row = {
                            'timestamp': dataset.get('timestamp', ''),
                            'domain': domain,
                            'event_name': event_data.get('event', 'unknown'),
                            'total_activity': event_data.get('total_activity', 0),
                            'avg_core_count': event_data.get('avg_core_count', 0),
                            'max_core_count': event_data.get('max_core_count', 0),
                            'min_core_count': event_data.get('min_core_count', 0),
                            'active_cores': event_data.get('active_cores', 0),
                            'total_cores': event_data.get('total_cores', 0),
                            'workload': workload_label,  # Reuse from domain_feature
                            'duration_seconds': metadata.get('duration_seconds', 0),
                            'os_type': metadata.get('os_type', 'windows'),  # Platform awareness for ML
                            # Composite feature: stress + OS combination for pattern learning
                            'stress_os_combo': f"{workload_label}_{metadata.get('os_type', 'windows')}",
                            # Legacy context features (keep for backward compatibility)
                            'cpu_temp': metadata.get('thermal_context', {}).get('cpu_temp_current', 0),
                            'cpu_freq_mhz': metadata.get('frequency_context', {}).get('current_freq_mhz', 0),
                            'memory_util_pct': metadata.get('memory_context', {}).get('memory_utilization_percent', 0),
                            'cpu_util_pct': metadata.get('workload_profile', {}).get('cpu_utilization_percent', 0),
                            # Health metrics (using actual field names from saved data)
                            'health_cpu_avg': metadata.get('health_metrics', {}).get('avg_cpu_usage', 0),
                            'health_mem_avg': metadata.get('health_metrics', {}).get('avg_memory_usage', 0),
                            'health_disk_min_gb': metadata.get('health_metrics', {}).get('avg_disk_free_gb', 0),
                            'health_duration_min': metadata.get('health_metrics', {}).get('duration_minutes', 0),
                            'health_samples': metadata.get('health_metrics', {}).get('total_samples', 0),
                            'health_issues': metadata.get('health_metrics', {}).get('health_issues', 0),
                        }
                        
                        # Calculate toggle rate
                        if feature_row['total_cores'] > 0:
                            feature_row['toggle_rate'] = feature_row['active_cores'] / feature_row['total_cores']
                        else:
                            feature_row['toggle_rate'] = 0
                        
                        # Distribution statistics
                        per_core_counts = event_data.get('per_core_counts', [])
                        if per_core_counts:
                            counts_array = np.array(per_core_counts)
                            active_counts = counts_array[counts_array > 0]
                            if len(active_counts) > 0:
                                count_mean = np.mean(active_counts)
                                count_std = np.std(active_counts)
                                feature_row['count_std'] = count_std
                                feature_row['count_cv'] = (count_std / count_mean) if count_mean > 0 else 0
                            else:
                                feature_row['count_std'] = 0
                                feature_row['count_cv'] = 0
                        
                        features.append(feature_row)
                
                continue  # Skip old format processing
            
            # Old format fallback: iterate domains directly
            for domain, domain_data in coverage_results.items():
                # Skip if domain_data is not a dict
                if not isinstance(domain_data, dict):
                    continue
                    
                # Skip if no event data
                if 'events' not in domain_data:
                    continue
                
                events = domain_data['events']
                if not isinstance(events, dict):
                    continue
                
                for event_name, event_data in events.items():
                    feature_row = {
                        'timestamp': dataset.get('timestamp', ''),
                        'domain': domain,
                        'event_name': event_name,
                    }
                    
                    # Basic counts
                    feature_row['total_count'] = event_data.get('total_count', 0)
                    feature_row['active_count'] = event_data.get('active_count', 0)
                    feature_row['zero_count'] = event_data.get('zero_count', 0)
                    
                    # Toggle rate
                    total_units = event_data.get('total_count', 0)
                    if total_units > 0:
                        feature_row['toggle_rate'] = event_data.get('active_count', 0) / total_units
                    else:
                        feature_row['toggle_rate'] = 0
                    
                    # Distribution statistics (if per-core/unit data available)
                    if 'per_core_counts' in event_data:
                        counts = event_data['per_core_counts']
                        if len(counts) > 0:
                            counts_array = np.array(counts)
                            active_counts = counts_array[counts_array > 0]
                            
                            if len(active_counts) > 0:
                                count_mean = np.mean(active_counts)
                                count_std = np.std(active_counts)
                                feature_row['count_mean'] = count_mean
                                feature_row['count_std'] = count_std
                                feature_row['count_min'] = np.min(active_counts)
                                feature_row['count_max'] = np.max(active_counts)
                                feature_row['count_cv'] = (count_std / count_mean) if count_mean > 0 else 0
                            else:
                                feature_row['count_mean'] = 0
                                feature_row['count_std'] = 0
                                feature_row['count_min'] = 0
                                feature_row['count_max'] = 0
                                feature_row['count_cv'] = 0
                    
                    # Workload and hardware context (use already extracted workload_label)
                    feature_row['workload'] = workload_label  # Already extracted from stress_tracking above
                    feature_row['duration_seconds'] = metadata.get('duration_seconds', 0)
                    
                    features.append(feature_row)
        
        if len(features) == 0:
            return None
        
        df = pd.DataFrame(features)
        
        # Encode categorical variables
        if 'domain' in df.columns:
            df['domain_encoded'] = pd.Categorical(df['domain']).codes
        if 'workload' in df.columns:
            df['workload_encoded'] = pd.Categorical(df['workload']).codes
        if 'os_type' in df.columns:
            # Encode OS type: windows=0, linux=1 (for ML models to understand platform differences)
            df['os_type_encoded'] = pd.Categorical(df['os_type']).codes
        if 'stress_os_combo' in df.columns:
            # Encode stress+OS combinations: e.g., "cpu_stress_windows", "memory_stress_linux"
            # This allows ML to learn health patterns specific to each stress type on each platform
            df['stress_os_combo_encoded'] = pd.Categorical(df['stress_os_combo']).codes
        
        return df
    
    def _train_anomaly_detector(self, features_df: pd.DataFrame) -> Dict[str, Any]:
        """Train anomaly detection model using Isolation Forest."""
        try:
            logger.info(" Training anomaly detector...")
            
            # Select numerical features for anomaly detection
            numeric_cols = ['total_count', 'active_count', 'zero_count', 'toggle_rate',
                           'count_mean', 'count_std', 'count_min', 'count_max', 'count_cv']
            
            available_cols = [col for col in numeric_cols if col in features_df.columns]
            
            if len(available_cols) == 0:
                return {'status': 'failed', 'message': 'No numeric features available'}
            
            X = features_df[available_cols].fillna(0)
            
            # Scale features
            X_scaled = self.anomaly_scaler.fit_transform(X)
            
            # Train Isolation Forest
            self.anomaly_detector = IsolationForest(
                contamination=0.1,  # Expect 10% anomalies
                random_state=42,
                n_estimators=100
            )
            self.anomaly_detector.fit(X_scaled)
            
            # Predict anomalies on training data for validation
            predictions = self.anomaly_detector.predict(X_scaled)
            anomaly_count = sum(predictions == -1)
            
            logger.info(f"[OK] Anomaly detector trained - detected {anomaly_count}/{len(predictions)} anomalies")
            
            return {
                'status': 'success',
                'model': 'IsolationForest',
                'features_used': available_cols,
                'training_samples': len(X),
                'anomalies_detected': int(anomaly_count),
                'anomaly_rate': float(anomaly_count / len(predictions))
            }
            
        except Exception as e:
            logger.error(f"Failed to train anomaly detector: {e}")
            return {'status': 'failed', 'error': str(e)}
    
    def _train_health_predictor(self, historical_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Train health score predictor - predicts coverage impact from system health metrics."""
        try:
            logger.info(" Training health score predictor...")
            
            # Extract health samples and coverage rates from historical data
            health_features = []
            coverage_targets = []
            filtered_runs = 0  # Track data quality filtering
            
            for i, run_data in enumerate(historical_data):
                # Extract from correct nested structure
                metadata = run_data.get('metadata', {})
                health_samples = metadata.get('health_samples', [])
                coverage_results = run_data.get('coverage_results', {})
                coverage_rate = coverage_results.get('activity_coverage', 0)
                
                logger.info(f"   Run {i+1}/{len(historical_data)}: health_samples={len(health_samples)}, coverage={coverage_rate:.1f}%")
                
                if not health_samples:
                    logger.warning(f"   Run {i+1}: No health samples found - health monitoring may not have been enabled")
                    continue
                    
                if coverage_rate == 0:
                    logger.warning(f"   Run {i+1}: Zero coverage - skipping run")
                    continue
                
                # DATA QUALITY CHECK: Filter out runs with unsafe PMU starvation data
                # NOTE: Only filters Linux runs with low-confidence PMU starvation
                # Windows data is NEVER filtered (status != 'pmu_starved', safe_for_ml = True)
                domain_results = coverage_results.get('domain_results', {})
                unsafe_pmu_data = False
                pmu_starved_count = 0
                for domain_data in domain_results.values():
                    for event in domain_data.get('inactive', []):
                        if event.get('status') == 'pmu_starved' and not event.get('safe_for_ml', True):
                            unsafe_pmu_data = True
                            pmu_starved_count += 1
                
                if unsafe_pmu_data:
                    logger.warning(f"   Run {i+1}: [WARN]  Data quality issue - {pmu_starved_count} unsafe PMU-starved events")
                    logger.warning(f"   Run {i+1}: Filtering out run to prevent ML from learning false patterns")
                    filtered_runs += 1
                    continue
                
                # Average health metrics across the run
                cpu_values = [s.get('metrics', {}).get('cpu_usage_pct', 0) for s in health_samples]
                mem_values = [s.get('metrics', {}).get('memory_usage_pct', 0) for s in health_samples]
                disk_values = [s.get('metrics', {}).get('disk_free_gb', 0) for s in health_samples]
                temp_values = [s.get('metrics', {}).get('temperature_c', 0) for s in health_samples if s.get('metrics', {}).get('temperature_c', 0) > 0]
                
                if cpu_values:
                    health_features.append([
                        sum(cpu_values) / len(cpu_values),  # avg_cpu
                        sum(mem_values) / len(mem_values) if mem_values else 0,  # avg_mem
                        sum(disk_values) / len(disk_values) if disk_values else 20,  # avg_disk_free
                        sum(temp_values) / len(temp_values) if temp_values else 60,  # avg_temp
                        max(cpu_values) if cpu_values else 0,  # max_cpu
                        max(mem_values) if mem_values else 0,  # max_mem
                    ])
                    coverage_targets.append(coverage_rate)
            
            if len(health_features) < 3:
                logger.warning(f"[WARN]  Insufficient health data: {len(health_features)}/3 runs have valid health samples")
                logger.warning(f"   Processed {len(historical_data)} total runs, but only {len(health_features)} had health monitoring data")
                if filtered_runs > 0:
                    logger.warning(f"     Data quality: {filtered_runs} runs filtered due to unsafe PMU starvation data")
                logger.warning("   Run 3+ collections with health monitoring enabled to train this model")
                return {'status': 'insufficient_data', 'samples': len(health_features), 'required': 3}
            
            X = np.array(health_features)
            y = np.array(coverage_targets)
            
            # Scale features
            X_scaled = self.health_scaler.fit_transform(X)
            
            # Train Gradient Boosting Regressor
            from sklearn.ensemble import GradientBoostingRegressor
            self.health_predictor = GradientBoostingRegressor(
                n_estimators=100,
                learning_rate=0.1,
                max_depth=4,
                random_state=42
            )
            self.health_predictor.fit(X_scaled, y)
            
            # Calculate training accuracy
            predictions = self.health_predictor.predict(X_scaled)
            mae = np.mean(np.abs(predictions - y))
            
            logger.info(f"[OK] Health predictor trained - MAE: {mae:.2f}% (predicts coverage from health metrics)")
            
            return {
                'status': 'success',
                'model': 'GradientBoostingRegressor',
                'features': ['avg_cpu', 'avg_mem', 'avg_disk_free', 'avg_temp', 'max_cpu', 'max_mem'],
                'training_samples': len(X),
                'mae': float(mae),
                'feature_importance': self.health_predictor.feature_importances_.tolist()
            }
            
        except Exception as e:
            logger.error(f"Failed to train health predictor: {e}")
            return {'status': 'failed', 'error': str(e)}
    
    def _train_gap_prioritizer(self, historical_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Train gap priority classifier - classifies gaps by priority level."""
        try:
            logger.info(" Training gap priority classifier...")
            logger.info(f"   [Debug] Received {len(historical_data)} historical runs")
            
            # Count gaps in historical data for debugging
            total_gaps = 0
            for i, run in enumerate(historical_data):
                gaps = run.get('gaps', {}).get('non_toggling_events', [])
                total_gaps += len(gaps)
                if i < 3:  # Show first 3 runs
                    logger.info(f"   [Debug] Run {i+1}: {len(gaps)} gaps found")
            logger.info(f"   [Debug] Total gaps across all runs: {total_gaps}")
            
            # Delegate to ML model's training method
            result = self.gap_prioritizer.train_from_history(historical_data)
            
            if result.get('status') == 'success':
                logger.info(f"[OK] Gap prioritizer trained - Accuracy: {result.get('accuracy', 0):.2%}")
                return result
            else:
                logger.warning(f"Gap prioritizer training incomplete: {result.get('message', 'Unknown')}")
                return result
                
        except Exception as e:
            logger.error(f"Failed to train gap prioritizer: {e}")
            return {'status': 'failed', 'error': str(e), 'message': str(e)}
    
    def _train_workload_detector(self, historical_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Train workload detector - detects workload type from coverage patterns."""
        try:
            logger.info(" Training workload detector...")
            logger.info(f"   [Debug] Received {len(historical_data)} historical runs")
            
            # Check workload diversity for debugging
            workload_types = {}
            for i, run in enumerate(historical_data):
                metadata = run.get('metadata', {})
                # Prioritize stress_tracking for accurate workload labels
                stress_tracking = metadata.get('stress_tracking', {})
                if stress_tracking and stress_tracking.get('classification'):
                    workload = stress_tracking['classification'].get('label', 'unknown')
                else:
                    workload = metadata.get('workload', 'unknown')
                workload_types[workload] = workload_types.get(workload, 0) + 1
            logger.info(f"   [Debug] Workload diversity: {workload_types}")
            logger.info(f"   [Debug] Unique workload types: {len(workload_types)}")
            
            # Delegate to ML model's training method
            result = self.workload_detector.train_from_history(historical_data)
            
            if result.get('status') == 'success':
                logger.info(f"[OK] Workload detector trained - Accuracy: {result.get('accuracy', 0):.2%}")
                return result
            else:
                logger.warning(f"Workload detector training incomplete: {result.get('message', 'Unknown')}")
                return result
                
        except Exception as e:
            logger.error(f"Failed to train workload detector: {e}")
            return {'status': 'failed', 'error': str(e), 'message': str(e)}
    
    def _train_action_prioritizer(self, historical_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Train action prioritizer - ranks actions using Learning-to-Rank."""
        try:
            logger.info(" Training action prioritizer...")
            
            # Try feedback-based training first (most accurate)
            result = self.action_prioritizer.train_from_history(historical_data)
            
            if result.get('status') == 'success':
                logger.info(f"[OK] Action prioritizer trained from user feedback - NDCG: {result.get('ndcg', 0):.3f}")
                return result
            elif result.get('status') == 'no_feedback':
                # Fallback to autonomous pattern-based training
                logger.info("[i]  No user feedback available - trying autonomous pattern analysis...")
                autonomous_result = self.action_prioritizer.train_from_patterns(self.current_product)
                
                if autonomous_result.get('status') == 'success':
                    logger.info(f"[OK] Action prioritizer trained autonomously - R²: {autonomous_result.get('r2_score', 0):.3f}")
                    logger.info("   Mode: Pattern-based learning (analyzes historical improvement trends)")
                    return autonomous_result
                else:
                    logger.warning(f"Autonomous training incomplete: {autonomous_result.get('message', 'Unknown')}")
                    return autonomous_result
            else:
                logger.warning(f"Action prioritizer training incomplete: {result.get('message', 'Unknown')}")
                return result
                
        except Exception as e:
            logger.error(f"Failed to train action prioritizer: {e}")
            return {'status': 'failed', 'error': str(e), 'message': str(e)}
    
    def _train_coverage_predictor(self, features_df: pd.DataFrame, 
                                   historical_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Train coverage prediction model using Gradient Boosting."""
        try:
            logger.info(" Training coverage predictor...")
            
            # Check if toggle_rate exists
            if 'toggle_rate' not in features_df.columns:
                logger.warning("toggle_rate column missing - computing from available data")
                # Compute toggle_rate if possible
                if 'active_count' in features_df.columns and 'total_count' in features_df.columns:
                    features_df['toggle_rate'] = features_df['active_count'] / features_df['total_count'].replace(0, 1)
                else:
                    return {'status': 'skipped', 'message': 'toggle_rate not available and cannot be computed'}
            
            # Prepare features and target
            feature_cols = ['domain_encoded', 'workload_encoded', 'duration_seconds']
            available_cols = [col for col in feature_cols if col in features_df.columns]
            
            if len(available_cols) < 2:
                return {'status': 'failed', 'message': 'Insufficient features for prediction'}
            
            X = features_df[available_cols].fillna(0)
            y = features_df['toggle_rate'].fillna(0)
            
            # Train Gradient Boosting Regressor
            self.coverage_predictor = GradientBoostingRegressor(
                n_estimators=100,
                max_depth=5,
                random_state=42,
                learning_rate=0.1
            )
            self.coverage_predictor.fit(X, y)
            
            # Calculate R² score on training data
            score = self.coverage_predictor.score(X, y)
            
            logger.info(f"[OK] Coverage predictor trained - R² score: {score:.3f}")
            
            return {
                'status': 'success',
                'model': 'GradientBoostingRegressor',
                'features_used': available_cols,
                'training_samples': len(X),
                'r2_score': float(score)
            }
            
        except Exception as e:
            logger.error(f"Failed to train coverage predictor: {e}")
            return {'status': 'failed', 'error': str(e)}
    
    def _train_pattern_classifier(self, features_df: pd.DataFrame,
                                   historical_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Train pattern classification model using Random Forest."""
        try:
            logger.info(" Training pattern classifier...")
            
            # Check if toggle_rate exists
            if 'toggle_rate' not in features_df.columns:
                logger.warning("toggle_rate column missing - computing from available data")
                # Compute toggle_rate if possible
                if 'active_count' in features_df.columns and 'total_count' in features_df.columns:
                    features_df['toggle_rate'] = features_df['active_count'] / features_df['total_count'].replace(0, 1)
                else:
                    return {'status': 'skipped', 'message': 'toggle_rate not available and cannot be computed'}
            
            # Create pattern labels based on toggle rates
            def classify_pattern(row):
                if row['toggle_rate'] < 0.1:
                    return 'low_activity'
                elif row['toggle_rate'] < 0.5:
                    return 'medium_activity'
                elif row['toggle_rate'] < 0.9:
                    return 'high_activity'
                else:
                    return 'full_toggle'
            
            features_df['pattern'] = features_df.apply(classify_pattern, axis=1)
            
            # Select features (use total_activity which is what's in the data)
            feature_cols = ['total_activity', 'domain_encoded', 'workload_encoded']
            available_cols = [col for col in feature_cols if col in features_df.columns]
            
            if len(available_cols) < 2:
                return {'status': 'failed', 'message': 'Insufficient features for classification'}
            
            X = features_df[available_cols].fillna(0)
            y = pd.Categorical(features_df['pattern']).codes
            
            # Train Random Forest Classifier
            self.pattern_classifier = RandomForestClassifier(
                n_estimators=100,
                max_depth=10,
                random_state=42
            )
            self.pattern_classifier.fit(X, y)
            
            # Save feature names for inference
            self.pattern_classifier_features = available_cols
            
            # Calculate accuracy
            accuracy = self.pattern_classifier.score(X, y)
            
            logger.info(f"[OK] Pattern classifier trained - accuracy: {accuracy:.3f}")
            logger.info(f"   Features used: {available_cols}")
            
            return {
                'status': 'success',
                'model': 'RandomForestClassifier',
                'features_used': available_cols,
                'training_samples': len(X),
                'accuracy': float(accuracy),
                'patterns': ['low_activity', 'medium_activity', 'high_activity', 'full_toggle']
            }
            
        except Exception as e:
            logger.error(f"Failed to train pattern classifier: {e}")
            return {'status': 'failed', 'error': str(e)}
    
    def _train_event_clusterer(self, features_df: pd.DataFrame) -> Dict[str, Any]:
        """Train event clustering model using DBSCAN."""
        try:
            logger.info(" Training event clusterer...")
            
            # Select features for clustering
            cluster_cols = ['toggle_rate', 'count_mean', 'count_std', 'count_cv']
            available_cols = [col for col in cluster_cols if col in features_df.columns]
            
            if len(available_cols) < 2:
                return {'status': 'failed', 'message': 'Insufficient features for clustering'}
            
            X = features_df[available_cols].fillna(0)
            X_scaled = self.cluster_scaler.fit_transform(X)
            
            # Train DBSCAN
            self.event_clusterer = DBSCAN(eps=0.5, min_samples=5)
            clusters = self.event_clusterer.fit_predict(X_scaled)
            
            n_clusters = len(set(clusters)) - (1 if -1 in clusters else 0)
            n_noise = list(clusters).count(-1)
            
            logger.info(f"[OK] Event clusterer trained - {n_clusters} clusters, {n_noise} outliers")
            
            return {
                'status': 'success',
                'model': 'DBSCAN',
                'features_used': available_cols,
                'training_samples': len(X),
                'clusters_found': int(n_clusters),
                'outliers': int(n_noise)
            }
            
        except Exception as e:
            logger.error(f"Failed to train event clusterer: {e}")
            return {'status': 'failed', 'error': str(e)}
    
    def _train_stress_correlation_model(self, features_df: pd.DataFrame, 
                                       historical_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Train a model to predict stress-event correlations with instruction mix.
        Uses RandomForestRegressor to predict correlation strength (0-1) for each event.
        Includes instruction mix features to identify exact scenarios (e.g., FP-heavy CPU stress, Memory-intensive workload).
        """
        if not SKLEARN_AVAILABLE:
            return {'status': 'failed', 'message': 'scikit-learn not available'}
        
        try:
            from sklearn.ensemble import RandomForestRegressor
            
            # Extract stress-related features from historical data
            training_data = []
            
            for dataset in historical_data:
                metadata = dataset.get('metadata', {})
                coverage = dataset.get('coverage_results', {})
                
                # Extract workload and stress indicators - prioritize stress_tracking
                stress_tracking = metadata.get('stress_tracking', {})
                if stress_tracking and stress_tracking.get('classification'):
                    workload = stress_tracking['classification'].get('label', 'unknown').lower()
                    collection_type = stress_tracking['classification'].get('type', 'unknown')
                else:
                    workload = (metadata.get('workload') or 'unknown').lower()
                    collection_type = 'unknown'
                
                cpu_usage = metadata.get('memory_context', {}).get('cpu_utilization_percent', 0)
                mem_usage = metadata.get('memory_context', {}).get('memory_utilization_percent', 0)
                
                # Compute instruction mix percentages from coverage data
                instruction_mix = self._compute_instruction_mix_features(coverage)
                
                # Encode workload type - enhanced with stress_tracking
                stress_level = 0
                if collection_type == 'idle':
                    stress_level = 0  # Low/idle
                elif any(tool in workload for tool in ['prime95', 'supercollider', 'linpack', 'memicals', 'mlc', 'stream']):
                    stress_level = 2  # High stress (known tools)
                elif collection_type in ['single_stress', 'mixed_workload']:
                    stress_level = 1  # Medium stress (detected but unknown tool)
                elif cpu_usage > 70 or mem_usage > 70:
                    stress_level = 1  # Medium stress (high utilization)
                elif cpu_usage > 70 or mem_usage > 70:
                    stress_level = 1  # Medium stress
                else:
                    stress_level = 0  # Low/idle
                
                # Extract per-event features
                domain_results = coverage.get('domain_results', {})
                for domain, domain_data in domain_results.items():
                    if not isinstance(domain_data, dict):
                        continue
                    
                    active_events = domain_data.get('active_events', [])
                    for event_info in active_events:
                        event_name = event_info.get('event', 'unknown')
                        total_activity = event_info.get('total_activity', 0)
                        per_core = event_info.get('per_core_counts', [])
                        
                        if not per_core:
                            continue
                        
                        # Calculate features
                        avg_count = sum(per_core) / len(per_core) if per_core else 0
                        max_count = max(per_core) if per_core else 0
                        std_count = np.std(per_core) if per_core else 0
                        
                        # Correlation target (0-1): higher activity at higher stress = high correlation
                        # This is the label we're trying to learn
                        if total_activity > 1000000000:
                            correlation_target = 0.9  # Highly correlated
                        elif total_activity > 10000000:
                            correlation_target = 0.6  # Moderately correlated
                        else:
                            correlation_target = 0.2  # Low correlation
                        
                        # Build sample with base features
                        sample = {
                            'event': event_name,
                            'domain': domain,
                            'stress_level': stress_level,
                            'total_activity': total_activity,
                            'avg_count': avg_count,
                            'max_count': max_count,
                            'std_count': std_count,
                            'correlation': correlation_target  # Target variable
                        }
                        
                        # Add instruction mix percentages dynamically
                        for key, value in instruction_mix.items():
                            sample[key] = value
                        
                        training_data.append(sample)
            
            if len(training_data) < 10:
                logger.warning(f"[ML-Stress] Insufficient training data: {len(training_data)} samples (need 10+)")
                return {'status': 'insufficient_data', 
                       'message': f'Need at least 10 samples, got {len(training_data)}'}
            
            logger.info(f"[ML-Stress] Training with {len(training_data)} samples from {len(historical_data)} runs")
            # Convert to DataFrame
            train_df = pd.DataFrame(training_data)
            
            # Build feature columns dynamically based on available instruction mix features
            base_features = ['stress_level', 'total_activity', 'avg_count', 'max_count', 'std_count']
            
            # Get all instruction mix percentage columns (any column ending with _pct)
            mix_features = [col for col in train_df.columns if col.endswith('_pct')]
            
            feature_cols = base_features + mix_features
            logger.info(f"Training with {len(mix_features)} instruction mix features: {mix_features}")
            
            X = train_df[feature_cols].fillna(0)
            y = train_df['correlation']
            
            # Normalize features
            X_scaled = self.stress_scaler.fit_transform(X)
            
            # Train Random Forest Regressor
            self.stress_correlation_model = RandomForestRegressor(
                n_estimators=100,
                max_depth=10,
                min_samples_split=5,
                random_state=42
            )
            self.stress_correlation_model.fit(X_scaled, y)
            
            # Evaluate on training data (in production, use cross-validation)
            predictions = self.stress_correlation_model.predict(X_scaled)
            mae = np.mean(np.abs(predictions - y))
            
            logger.info(f"[OK] Stress correlation model trained - MAE: {mae:.3f}")
            
            # Extract scenario insights from feature importance
            feature_importance = dict(zip(feature_cols, 
                                        self.stress_correlation_model.feature_importances_.tolist()))
            
            # Identify most important instruction mix features
            mix_features_importance = {k: v for k, v in feature_importance.items() if '_pct' in k}
            top_mix_features = sorted(mix_features_importance.items(), key=lambda x: x[1], reverse=True)[:5]
            
            # Check if using learned categories
            using_learned = len(mix_features) > 5  # More than 5 means using learned categories
            
            return {
                'status': 'success',
                'model': 'RandomForestRegressor',
                'features_used': feature_cols,
                'instruction_mix_features': mix_features,
                'using_learned_categories': using_learned,
                'training_samples': len(X),
                'mean_absolute_error': float(mae),
                'feature_importance': feature_importance,
                'top_instruction_mix_features': [{'category': k, 'importance': float(v)} for k, v in top_mix_features],
                'scenario_correlation_enabled': True
            }
            
        except Exception as e:
            logger.error(f"Failed to train stress correlation model: {e}")
            return {'status': 'failed', 'error': str(e)}
    
    def _compute_instruction_mix_features(self, coverage_results: Dict[str, Any]) -> Dict[str, float]:
        """
        Compute instruction mix percentages from coverage data.
        Uses learned categories if available, otherwise falls back to hardcoded patterns.
        Returns percentages for key instruction categories.
        """
        # Try to load learned categories for current product
        learned_categories = {}
        if self.current_product:
            try:
                from src.instruction_mix_learner import InstructionMixLearner
                learned_categories = InstructionMixLearner.load_learned_categories(
                    self.current_product, 
                    Path(__file__).parent.parent / 'config'
                )
            except Exception as e:
                logger.debug(f"Could not load learned categories: {e}")
        
        # Use learned categories if available, otherwise use hardcoded fallback
        if learned_categories:
            instruction_patterns = learned_categories
            logger.debug(f"Using {len(learned_categories)} learned instruction categories for features")
        else:
            # Fallback to hardcoded patterns if no learned categories available
            instruction_patterns = {
                'FP_SIMD': ['FP_', 'AVX', 'SSE', 'SIMD', 'VEC', 'FMA'],
                'Memory': ['MEM_LOAD', 'MEM_STORE', 'MEM_INST', 'MEM_UOPS'],
                'Branch': ['BR_', 'BRANCH', 'BACLEARS'],
                'Integer_ALU': ['INT_', 'ARITH.DIV', 'ARITH.MUL', 'UOPS_EXECUTED'],
                'Cache': ['L1D', 'L1I', 'L2_', 'L3_', 'LONGEST_LAT', 'LLC']
            }
            logger.debug("Using fallback hardcoded instruction patterns")
        
        # Count events in each category
        category_counts = {cat: 0 for cat in instruction_patterns.keys()}
        total_events = 0
        
        domain_results = coverage_results.get('domain_results', {})
        for domain, domain_data in domain_results.items():
            if not isinstance(domain_data, dict):
                continue
            
            active_events = domain_data.get('active_events', [])
            for event_info in active_events:
                event_name = event_info.get('event', '').upper()
                total_events += 1
                
                # Check which category this event belongs to
                for category, patterns in instruction_patterns.items():
                    if any(pattern in event_name for pattern in patterns):
                        category_counts[category] += 1
                        break  # Event can only belong to one category
        
        # Calculate percentages
        result = {}
        if total_events > 0:
            for category, count in category_counts.items():
                result[f'{category}_pct'] = (count / total_events) * 100
        else:
            # Default to 0% if no events
            for category in category_counts.keys():
                result[f'{category}_pct'] = 0.0
        
        return result
    
    def _learn_instruction_categories(self, product_id: str) -> Dict[str, Any]:
        """
        Auto-learn instruction mix categories from all collected events for this product.
        Updates the product-specific instruction categorization config.
        
        Args:
            product_id: Product identifier
        
        Returns:
            Dict with learning results
        """
        try:
            from src.instruction_mix_learner import InstructionMixLearner
            
            # Initialize learner for this product
            logger.info(f" Initializing instruction mix learner for product: {product_id}")
            learner = InstructionMixLearner(product_id, self.base_dir)
            
            # Learn categories from historical data
            learn_result = learner.learn_categories(min_event_threshold=2)
            
            if learn_result.get('status') == 'success':
                # Export to product-specific YAML
                yaml_path = learner.export_to_yaml()
                
                # Update main templates config
                learner.update_template_config()
                
                # Get statistics
                stats = learner.get_statistics()
                
                return {
                    'status': 'success',
                    'categories': learn_result.get('categories', 0),
                    'categorized_events': learn_result.get('categorized_events', 0),
                    'uncategorized_events': learn_result.get('uncategorized_events', 0),
                    'category_details': learn_result.get('category_details', {}),
                    'config_path': str(yaml_path),
                    'statistics': stats,
                    'timestamp': datetime.now().isoformat()
                }
            else:
                return learn_result
        
        except Exception as e:
            import traceback
            logger.warning(f"Instruction mix learning failed: {e}")
            logger.warning(f"Full traceback:\n{traceback.format_exc()}")
            return {'status': 'failed', 'error': str(e)}
    
    def get_training_summary(self) -> Dict[str, Any]:
        """Get summary of training history and model status."""
        # Count datasets for current product
        dataset_count = 0
        instruction_mix_learning = {}
        
        if self.current_product:
            product_datasets_dir = self.raw_datasets_dir / self.current_product
            if product_datasets_dir.exists():
                dataset_count = len(list(product_datasets_dir.glob("coverage_*.json")))
            
            # Check for instruction mix learning results
            if self.training_history.get('sessions'):
                last_session = self.training_history['sessions'][-1]
                if 'metrics' in last_session and 'instruction_mix_learning' in last_session['metrics']:
                    instruction_mix_learning = last_session['metrics']['instruction_mix_learning']
        
        summary = {
            'models_available': {
                'anomaly_detector': self.anomaly_detector is not None,
                'coverage_predictor': self.coverage_predictor is not None,
                'pattern_classifier': self.pattern_classifier is not None,
                'event_clusterer': self.event_clusterer is not None,
                'stress_correlation_model': self.stress_correlation_model is not None,
                'health_predictor': self.health_predictor is not None,
                'gap_prioritizer': self.gap_prioritizer.is_trained(),
                'workload_detector': self.workload_detector.is_trained(),
                'action_prioritizer': self.action_prioritizer.is_trained(),
                'stress_recommender': self.stress_recommender.is_trained(),
                'saturation_predictor': self.saturation_predictor.is_trained(),
                'workload_clusterer': self.workload_clusterer.is_trained(),
                'gap_forecaster': self.gap_forecaster.is_trained()
            },
            'training_sessions': len(self.training_history.get('sessions', [])),
            'last_training': self.training_history['sessions'][-1]['timestamp'] if self.training_history.get('sessions') else 'Never',
            'data_directory': str(self.base_dir),
            'raw_datasets': dataset_count,
            'datasets_collected': dataset_count,
            'current_product': self.current_product,
            'products_registered': len(self.product_registry),
            'product_list': list(self.product_registry.keys())
        }
        
        # Add instruction mix learning if available
        if instruction_mix_learning:
            summary['instruction_mix_learning'] = instruction_mix_learning
        
        return summary
    
    def get_product_summary(self) -> Dict[str, Any]:
        """Get summary of all registered products and their training status.
        
        Returns:
            dict: Product registry with training statistics
        """
        summary = {
            'total_products': len(self.product_registry),
            'products': {}
        }
        
        for product_id, product_info in self.product_registry.items():
            # Count datasets for this product
            product_datasets_dir = self.raw_datasets_dir / product_id
            dataset_count = len(list(product_datasets_dir.glob("coverage_*.json"))) if product_datasets_dir.exists() else 0
            
            # Check if models exist
            product_models_dir = self.models_dir / product_id
            has_models = product_models_dir.exists() and any(product_models_dir.glob("*.pkl"))
            
            # Get training history
            product_logs_dir = self.logs_dir / product_id
            history_path = product_logs_dir / "training_history.json"
            training_sessions = 0
            last_trained = None
            
            if history_path.exists():
                try:
                    with open(history_path, 'r') as f:
                        history = json.load(f)
                        training_sessions = len(history.get('sessions', []))
                        if history.get('sessions'):
                            last_trained = history['sessions'][-1].get('timestamp')
                except:
                    pass
            
            summary['products'][product_id] = {
                'product_name': product_info.get('product_name', product_id),
                'cpu_family': product_info.get('cpu_family', 'unknown'),
                'cores': {
                    'total': product_info.get('total_cores', 0),
                    'p_cores': product_info.get('p_cores', 0),
                    'e_cores': product_info.get('e_cores', 0)
                },
                'pmu_units': product_info.get('pmu_units', {}),
                'domains_discovered': product_info.get('domains_seen', []),
                'first_seen': product_info.get('first_seen'),
                'last_seen': product_info.get('last_seen'),
                'total_runs': product_info.get('total_runs', 0),
                'datasets_collected': dataset_count,
                'models_trained': has_models,
                'training_sessions': training_sessions,
                'last_trained': last_trained
            }
        
        return summary
    
    def _train_stress_recommender(self, historical_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Train stress test recommender - recommends next best stress test."""
        try:
            logger.info(" Training stress test recommender...")
            
            result = self.stress_recommender.train_from_history(historical_data)
            
            if result['status'] == 'success':
                logger.info(f"[OK] Stress recommender trained with R²={result.get('r2_score', 0):.3f}")
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to train stress recommender: {e}")
            return {'status': 'failed', 'error': str(e)}
    
    def _train_saturation_predictor(self, historical_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Train coverage saturation predictor - predicts optimal collection duration."""
        try:
            logger.info(" Training saturation predictor...")
            
            result = self.saturation_predictor.train_from_history(historical_data)
            
            if result['status'] == 'success':
                logger.info(f"[OK] Saturation predictor trained with R²={result.get('r2_score', 0):.3f}")
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to train saturation predictor: {e}")
            return {'status': 'failed', 'error': str(e)}
    
    def _train_workload_clusterer(self, historical_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Train workload similarity clusterer - groups similar runs."""
        try:
            logger.info(" Training workload clusterer...")
            
            result = self.workload_clusterer.train_from_history(historical_data)
            
            if result['status'] == 'success':
                logger.info(f"[OK] Workload clusterer trained: {result.get('num_clusters', 0)} clusters")
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to train workload clusterer: {e}")
            return {'status': 'failed', 'error': str(e)}
    
    def _train_gap_forecaster(self, historical_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Train gap trend forecaster - predicts future gap trends."""
        try:
            logger.info(" Training gap forecaster...")
            
            result = self.gap_forecaster.train_from_history(historical_data)
            
            if result['status'] == 'success':
                logger.info(f"[OK] Gap forecaster trained: Coverage R²={result.get('coverage_r2', 0):.3f}, Gap R²={result.get('gap_r2', 0):.3f}")
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to train gap forecaster: {e}")
            return {'status': 'failed', 'error': str(e)}
