#!/usr/bin/env python3
"""
Report Generator Module

INTEL CONFIDENTIAL - INTERNAL USE ONLY

Generates comprehensive reports for silicon coverage analysis including
JSON and HTML formats with detailed gap analysis.
"""

import json
import shutil
import yaml
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
from src.ml_visualizations import MLVisualizationGenerator
from src.gap_csv_exporter import GapCSVExporter
from src.regression_detector import RegressionDetector
from src.temporal_trend_analyzer import TemporalTrendAnalyzer
from src.gap_correlation_analyzer import GapCorrelationAnalyzer
from src.platform_gap_comparison import PlatformGapComparison
from src.emon_command_generator import EmonCommandGenerator
from src.ml_gap_prioritizer import MLGapPrioritizer
from src.ml_workload_detector import MLWorkloadDetector
from src.ml_action_prioritizer import MLActionPrioritizer
from src.ml_stress_recommender import MLStressRecommender
from src.ml_saturation_predictor import MLSaturationPredictor
from src.ml_workload_clusterer import MLWorkloadClusterer
from src.ml_gap_forecaster import MLGapForecaster
from src.single_platform_analyzer import SinglePlatformAnalyzer
from src.unified_workload_detector import UnifiedWorkloadDetector
from src.report_tabs import (
    ExecutiveTabGenerator, 
    ActionItemsTabGenerator, 
    CoverageDetailsTabGenerator, 
    WorkloadHealthTabGenerator, 
    PlatformProductInsightsTabGenerator,
    MLTrainingStrategyTabGenerator
)

logger = logging.getLogger(__name__)

# Load domain configuration from YAML
def _load_domain_config():
    """Load domain configuration from domain_config.yaml."""
    config_path = Path(__file__).parent.parent / 'config' / 'domain_config.yaml'
    try:
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.warning(f"Could not load domain_config.yaml: {e}. Using defaults.")
        # Fallback to minimal defaults
        return {
            'domain_colors': {
                'core': '#0071C5', 'uncore': '#388e3c', 'p-core': '#0071C5',
                'e-core': '#f39c12', 'imc': '#27ae60', 'cbo': '#8e44ad'
            },
            'domain_priority': {'p-core': 3, 'e-core': 2, 'imc': 3, 'uncore': 3}
        }

_DOMAIN_CONFIG = _load_domain_config()
DOMAIN_COLORS = _DOMAIN_CONFIG.get('domain_colors', {})


class ReportGenerator:
    """Generates comprehensive analysis reports."""
    
    def __init__(self, config):
        self.config = config
        self.debug = config.get('debug', False)  # Add debug flag
        self.output_formats = config.get('output_format', ['json', 'html'])
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Set output directory
        self.output_dir = Path('output')
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Create backup directory on C drive
        self.backup_dir = Path(r"C:\Silicon_coverage_analyzer_data")
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        # ML visualization generator will be created with product_id when needed
        self.ml_viz = None
        
        # Cache for domain metadata from EMON (populated during analysis)
        self.domain_metadata = {}
        
        # MODULAR REFACTORING FLAG
        # Set to True to use modular tab generation methods
        self.use_modular_tabs = config.get('use_modular_report', True)
        
        # Instruction Mix Categories (loaded per product)
        self.instruction_categories = {}
        self.instruction_categories_loaded = False
        self.current_product_id = None
        
        # Enhanced gap export and regression detection
        self.gap_exporter = GapCSVExporter(config)
        self.regression_detector = RegressionDetector(config)
        
        # Advanced validation features
        self.trend_analyzer = TemporalTrendAnalyzer(config)
        self.correlation_analyzer = GapCorrelationAnalyzer(config)
        self.platform_comparison = PlatformGapComparison(config)
        self.emon_generator = EmonCommandGenerator(config)
        
        # ML-based features (Priority 1 implementations)
        self.ml_gap_prioritizer = MLGapPrioritizer(str(self.backup_dir))
        self.ml_workload_detector = MLWorkloadDetector(str(self.backup_dir))
        self.ml_action_prioritizer = MLActionPrioritizer(str(self.backup_dir))
        
        # ML-based features (High-Value implementations)
        self.ml_stress_recommender = MLStressRecommender(str(self.backup_dir))
        self.ml_saturation_predictor = MLSaturationPredictor(str(self.backup_dir))
        self.ml_workload_clusterer = MLWorkloadClusterer(str(self.backup_dir))
        self.ml_gap_forecaster = MLGapForecaster(str(self.backup_dir))
        
        # Single-platform analyzer for when cross-platform data unavailable
        self.single_platform_analyzer = SinglePlatformAnalyzer(self.backup_dir)
        
        # Unified workload detector (single source of truth)
        self.unified_workload_detector = UnifiedWorkloadDetector(
            ml_detector=self.ml_workload_detector,
            stress_tracker=None  # Will be set during collection if available
        )
        
        # Track gap correlation data for ML features
        self._gap_correlation_cache = {}
        
        # Modular tab generators
        self.executive_tab_generator = ExecutiveTabGenerator(self)
        self.action_items_tab_generator = ActionItemsTabGenerator(self)
        self.coverage_details_tab_generator = CoverageDetailsTabGenerator(self)
        self.workload_health_tab_generator = WorkloadHealthTabGenerator(self)
        self.platform_product_insights_tab_generator = PlatformProductInsightsTabGenerator(self)
        self.ml_training_strategy_tab_generator = MLTrainingStrategyTabGenerator(self)
    
    
    def _load_instruction_categories(self, product_id: str) -> bool:
        """
        Load learned instruction mix categories for the given product.
        
        Args:
            product_id: Product identifier (e.g., 'client_platform_1', 'server_platform_1')
        
        Returns:
            True if categories loaded successfully
        """
        if self.current_product_id == product_id and self.instruction_categories_loaded:
            logger.info(f"Categories already loaded for {product_id}")
            return True  # Already loaded for this product
        
        try:
            # Try to use InstructionMixLearner to load learned categories
            config_dir = Path(__file__).parent.parent / 'config'
            yaml_path = config_dir / f'instruction_categories_{product_id.lower()}.yaml'
            
            logger.info(f"Looking for ML-learned categories at: {yaml_path}")
            
            if not yaml_path.exists():
                logger.warning(f"No learned categories found for {product_id} at {yaml_path}")
                logger.warning(f"    Using fallback seed patterns instead")
                self._use_fallback_categories()
                return False
            
            logger.info(f"Found ML-learned category file, loading...")
            
            with open(yaml_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            # Build categories dict with full metadata
            self.instruction_categories = {}
            for cat in config.get('instruction_categories', []):
                self.instruction_categories[cat['name']] = {
                    'patterns': cat.get('patterns', []),
                    'icon': cat.get('icon', 'CAT'),
                    'color': cat.get('color', '#6c757d'),
                    'description': cat.get('description', ''),
                    'confidence': cat.get('confidence', 'medium'),
                    'event_count': cat.get('event_count', 0)  # ML-learned event count
                }
            
            # Add fallback category
            fallback = config.get('fallback_category', {})
            self.instruction_categories['Other'] = {
                'patterns': [],
                'icon': fallback.get('icon', 'OTHER'),
                'color': fallback.get('color', '#6c757d'),
                'description': fallback.get('description', 'Uncategorized events')
            }
            
            self.instruction_categories_loaded = True
            self.current_product_id = product_id
            
            # Log what was loaded
            total_learned_events = sum(cat.get('event_count', 0) for cat in self.instruction_categories.values() if cat.get('event_count'))
            categories_with_events = [f"{k}({v.get('event_count',0)})" for k,v in self.instruction_categories.items() if v.get('event_count', 0) > 0]
            logger.info(f"Loaded {len(self.instruction_categories)} ML-learned categories for {product_id}")
            logger.info(f"   Generated: {config.get('generated_date', 'unknown date')}")
            logger.info(f"   Categories with events: {categories_with_events}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load instruction categories: {e}")
            logger.error(f"   Using fallback seed patterns")
            self._use_fallback_categories()
            return False
    
    def _use_fallback_categories(self):
        """Use hardcoded fallback categories when learned categories unavailable."""
        self.instruction_categories = {
            'FP_SIMD': {
                'patterns': ['FP_', 'AVX', 'SSE', 'SIMD', 'VEC', 'FMA', 'FLOP', 'DOUBLE', 'SINGLE'],
                'icon': 'FP',
                'color': '#28a745',
                'description': 'Floating-point and SIMD vector operations'
            },
            'Memory': {
                'patterns': ['MEM_LOAD', 'MEM_STORE', 'MEM_INST', 'MEM_UOPS', 'LOAD_', 'STORE_'],
                'icon': 'MEM',
                'color': '#e74c3c',
                'description': 'Memory load and store operations'
            },
            'Branch': {
                'patterns': ['BR_', 'BRANCH', 'BACLEARS', 'JUMP', 'CALL', 'RET'],
                'icon': 'BR',
                'color': '#f39c12',
                'description': 'Branch and control flow operations'
            },
            'Integer_ALU': {
                'patterns': ['INT_', 'ARITH.DIV', 'ARITH.MUL', 'UOPS_EXECUTED', 'ADD', 'SUB'],
                'icon': 'INT',
                'color': '#0071C5',
                'description': 'Integer arithmetic and logic operations'
            },
            'Cache': {
                'patterns': ['L1D', 'L1I', 'L2_', 'L3_', 'LLC', 'LONGEST_LAT', 'CACHE'],
                'icon': 'CACHE',
                'color': '#9b59b6',
                'description': 'Cache hierarchy operations'
            },
            'Other': {
                'patterns': [],
                'icon': 'OTHER',
                'color': '#6c757d',
                'description': 'Uncategorized events'
            }
        }
        self.instruction_categories_loaded = True
        logger.debug("Using fallback instruction categories")
    
    def _categorize_event(self, event_name: str) -> Dict[str, Any]:
        """
        Categorize an event based on learned instruction mix patterns.
        
        Args:
            event_name: Event name to categorize
        
        Returns:
            Dict with category info: name, icon, color, description
        """
        if not self.instruction_categories_loaded:
            self._use_fallback_categories()
        
        event_upper = event_name.upper()
        
        # Try to match against each category's patterns
        for category_name, category_info in self.instruction_categories.items():
            if category_name == 'Other':
                continue  # Check Other last as fallback
            
            for pattern in category_info['patterns']:
                if pattern in event_upper:
                    return {
                        'name': category_name,
                        'icon': category_info['icon'],
                        'color': category_info['color'],
                        'description': category_info['description']
                    }
        
        # Fallback to Other category
        other_category = self.instruction_categories.get('Other', {
            'icon': 'OTHER',
            'color': '#6c757d',
            'description': 'Uncategorized events'
        })
        return {
            'name': 'Other',
            'icon': other_category['icon'],
            'color': other_category['color'],
            'description': other_category['description']
        }
    
    def _get_ml_learned_sentiment_thresholds(self) -> Dict[str, float]:
        """
        Load ML-learned sentiment thresholds from historical validation success patterns.
        
        Analyzes past coverage runs to find optimal thresholds that correlate with
        validation success. Falls back to industry-standard thresholds if insufficient data.
        
        Returns:
            Dict with threshold values: {'excellent': 90, 'good': 70, 'warning': 50, 'critical': 50}
        """
        from pathlib import Path
        import json
        import numpy as np
        
        try:
            # Default industry-standard thresholds (fallback)
            default_thresholds = {
                'excellent': 90.0,
                'good': 70.0,
                'warning': 50.0,
                'critical': 50.0
            }
            
            # Try to load learned thresholds from ML training data
            data_dir = Path(r'C:\silicon_coverage_analyzer_data')
            models_dir = data_dir / 'ml_models'
            
            if not models_dir.exists():
                logger.debug("ML models directory not found, using default thresholds")
                return default_thresholds
            
            # Look for sentiment thresholds file
            thresholds_file = models_dir / 'sentiment_thresholds.json'
            
            if thresholds_file.exists():
                with open(thresholds_file, 'r') as f:
                    learned_thresholds = json.load(f)
                    
                # Validate learned thresholds
                if all(key in learned_thresholds for key in default_thresholds.keys()):
                    # Ensure thresholds are in descending order
                    if (learned_thresholds['excellent'] > learned_thresholds['good'] > 
                        learned_thresholds['warning'] > learned_thresholds['critical']):
                        logger.info(f"Using ML-learned sentiment thresholds: {learned_thresholds}")
                        return learned_thresholds
            
            # If no learned thresholds, try to compute from historical data
            coverage_files = list(data_dir.glob('raw_datasets/*/coverage_*.json'))
            
            if len(coverage_files) >= 10:  # Need at least 10 runs for statistical significance
                coverage_percentages = []
                
                for file in coverage_files:
                    try:
                        with open(file, 'r') as f:
                            data = json.load(f)
                            coverage_pct = data.get('coverage', {}).get('overall_coverage_percentage', 0)
                            if coverage_pct > 0:
                                coverage_percentages.append(coverage_pct)
                    except:
                        continue
                
                if len(coverage_percentages) >= 10:
                    # Use percentile-based thresholds from historical data
                    coverage_percentages = np.array(coverage_percentages)
                    
                    learned_thresholds = {
                        'excellent': float(np.percentile(coverage_percentages, 90)),  # Top 10%
                        'good': float(np.percentile(coverage_percentages, 70)),      # Top 30%
                        'warning': float(np.percentile(coverage_percentages, 40)),   # Middle
                        'critical': float(np.percentile(coverage_percentages, 10))   # Bottom 10%
                    }
                    
                    # Ensure minimum spacing between thresholds
                    if learned_thresholds['excellent'] - learned_thresholds['good'] < 5:
                        learned_thresholds['good'] = learned_thresholds['excellent'] - 5
                    if learned_thresholds['good'] - learned_thresholds['warning'] < 5:
                        learned_thresholds['warning'] = learned_thresholds['good'] - 5
                    if learned_thresholds['warning'] - learned_thresholds['critical'] < 5:
                        learned_thresholds['critical'] = learned_thresholds['warning'] - 5
                    
                    # Save learned thresholds for future use
                    models_dir.mkdir(parents=True, exist_ok=True)
                    with open(thresholds_file, 'w') as f:
                        json.dump(learned_thresholds, f, indent=2)
                    
                    logger.info(f"Computed ML-learned thresholds from {len(coverage_percentages)} historical runs: {learned_thresholds}")
                    return learned_thresholds
            
            logger.debug("Insufficient historical data for ML-learned thresholds, using defaults")
            return default_thresholds
            
        except Exception as e:
            logger.debug(f"Error loading ML-learned thresholds, using defaults: {e}")
            return {
                'excellent': 90.0,
                'good': 70.0,
                'warning': 50.0,
                'critical': 50.0
            }
    
    def _get_ml_learned_stress_thresholds(self) -> Dict[str, float]:
        """
        Get ML-learned stress level thresholds based on historical domain activity patterns.
        
        Uses percentile-based analysis of historical domain activity rates to determine
        environment-specific thresholds for HIGH/MODERATE/LOW stress levels.
        
        Returns:
            Dict with 'high', 'moderate', 'low' threshold values
            Fallback to {high: 80, moderate: 50, low: 20} if insufficient data
        """
        # Get logger reference first (handle cases where self.logger might not exist)
        logger = getattr(self, 'logger', None)
        if logger is None:
            import logging
            logger = logging.getLogger(__name__)
        
        try:
            # Use the same data directory as other methods
            data_dir = Path(r'C:\silicon_coverage_analyzer_data')
            
            # Try loading cached thresholds
            thresholds_file = data_dir / 'ml_models' / 'stress_thresholds.json'
            if thresholds_file.exists():
                with open(thresholds_file, 'r') as f:
                    learned_thresholds = json.load(f)
                    logger.info(f"? Using ML-learned stress thresholds: {learned_thresholds}")
                    return learned_thresholds
            
            # Need historical data to learn from
            coverage_files = list((data_dir / 'raw_datasets').glob('*/coverage_*.json'))
            
            if len(coverage_files) >= 10:
                logger.info(f"Computing ML-learned stress thresholds from {len(coverage_files)} historical runs...")
                
                # Collect all domain activity rates from historical runs
                all_activity_rates = []
                
                for cov_file in coverage_files:
                    try:
                        with open(cov_file, 'r') as f:
                            coverage_data = json.load(f)
                            
                            # Extract domain activity rates
                            domain_results = coverage_data.get('domain_results', {})
                            for domain, stats in domain_results.items():
                                activity_rate = stats.get('activity_rate', 0)
                                if activity_rate > 0:  # Only include active domains
                                    all_activity_rates.append(activity_rate)
                    except Exception as e:
                        logger.warning(f"Could not load {cov_file.name}: {e}")
                        continue
                
                if len(all_activity_rates) >= 30:  # Need enough samples
                    # Use percentiles to determine thresholds
                    # High stress: Top 20% of activity rates
                    # Moderate stress: Top 50% of activity rates
                    # Low stress: Top 80% of activity rates
                    
                    learned_thresholds = {
                        'high': float(np.percentile(all_activity_rates, 80)),      # Top 20%
                        'moderate': float(np.percentile(all_activity_rates, 50)),  # Top 50%
                        'low': float(np.percentile(all_activity_rates, 20))        # Top 80%
                    }
                    
                    # Ensure minimum 10% spacing between thresholds
                    if learned_thresholds['high'] - learned_thresholds['moderate'] < 10:
                        learned_thresholds['moderate'] = learned_thresholds['high'] - 10
                    if learned_thresholds['moderate'] - learned_thresholds['low'] < 10:
                        learned_thresholds['low'] = learned_thresholds['moderate'] - 10
                    
                    # Ensure thresholds are in valid range (0-100)
                    learned_thresholds['high'] = min(95, max(60, learned_thresholds['high']))
                    learned_thresholds['moderate'] = min(learned_thresholds['high'] - 10, max(30, learned_thresholds['moderate']))
                    learned_thresholds['low'] = min(learned_thresholds['moderate'] - 10, max(10, learned_thresholds['low']))
                    
                    # Save for future use
                    thresholds_file.parent.mkdir(parents=True, exist_ok=True)
                    with open(thresholds_file, 'w') as f:
                        json.dump(learned_thresholds, f, indent=2)
                    
                    logger.info(f"? Learned stress thresholds from {len(all_activity_rates)} domain samples:")
                    logger.info(f"  High: {learned_thresholds['high']:.1f}% (top 20% activity)")
                    logger.info(f"  Moderate: {learned_thresholds['moderate']:.1f}% (top 50% activity)")
                    logger.info(f"  Low: {learned_thresholds['low']:.1f}% (top 80% activity)")
                    
                    return learned_thresholds
                else:
                    logger.info(f"Only {len(all_activity_rates)} domain samples - need 30+ for stress threshold learning")
            else:
                logger.info(f"Only {len(coverage_files)} coverage files - need 10+ runs for stress threshold learning")
        
        except Exception as e:
            logger.warning(f"Error computing ML-learned stress thresholds: {e}")
        
        # Fallback to industry-standard thresholds
        logger.info("Using fallback stress thresholds: high=80, moderate=50, low=20")
        return {
            'high': 80.0,
            'moderate': 50.0,
            'low': 20.0
        }
    
    def _get_product_id(self, analysis_results: Dict[str, Any]) -> str:
        """
        Extract and normalize product ID from analysis results.
        
        Args:
            analysis_results: Full analysis results dictionary
            
        Returns:
            Normalized product ID string (empty string if not found)
        """
        hw_config = analysis_results.get('hardware_config', {})
        product_id = hw_config.get('product_id')
        
        # Fallback to product_name if product_id not available
        if not product_id:
            product_name = hw_config.get('product_name', '')
            if product_name:
                product_id = product_name.lower().replace(' ', '_').replace('-', '_')
        
        return product_id or ''  # Return empty string if still None
    
    def _get_coverage_sentiment(self, coverage_pct: float, context: str = 'general') -> Dict[str, Any]:
        """
        Get ML-learned sentiment analysis for coverage percentage.
        
        Uses historical validation success patterns to determine thresholds.
        Falls back to industry-standard thresholds if insufficient data.
        
        Args:
            coverage_pct: Coverage percentage (0-100)
            context: Context for sentiment ('general', 'domain', 'gap', 'event')
        
        Returns:
            Dict with sentiment info: level, color, icon, message, badge_html
        """
        # Try to load ML-learned thresholds from historical success patterns
        thresholds = self._get_ml_learned_sentiment_thresholds()
        
        # ML-learned or fallback sentiment thresholds
        if coverage_pct >= thresholds['excellent']:
            level = 'excellent'
            color = '#28a745'
            icon = 'PASS'
            message = 'Excellent coverage'
        elif coverage_pct >= thresholds['good']:
            level = 'good'
            color = '#28a745'
            icon = 'PASS'
            message = 'Good coverage'
        elif coverage_pct >= thresholds['warning']:
            level = 'warning'
            color = '#ffc107'
            icon = 'WARN'
            message = 'Moderate coverage - improvement recommended'
        elif coverage_pct >= thresholds['critical']:
            level = 'critical'
            color = '#dc3545'
            icon = 'WARN'
            message = 'Low coverage - requires attention'
        else:
            level = 'critical'
            color = '#dc3545'
            icon = 'FAIL'
            message = 'Very low coverage - critical gaps'
        
        # Adjust message based on context
        if context == 'gap':
            if coverage_pct >= thresholds['excellent']:
                message = 'Minor gap'
                icon = 'INFO'
            elif coverage_pct >= thresholds['warning']:
                message = 'Moderate gap'
            else:
                message = 'Critical gap'
        
        # Generate badge HTML
        badge_html = f'''<span style="background: {color}; color: white; padding: 4px 10px; 
                         border-radius: 12px; font-size: 0.85em; font-weight: bold; white-space: nowrap;">
                         {icon} {level.upper()}</span>'''
        
        return {
            'level': level,
            'color': color,
            'icon': icon,
            'message': message,
            'badge_html': badge_html,
            'coverage_pct': coverage_pct
        }
    
    def _get_domain_unit_name(self, domain):
        """
        Get the appropriate unit name for each domain type.
        First tries to use EMON-provided metadata, then falls back to pattern matching.
        """
        # Try to use cached metadata from EMON first
        if domain in self.domain_metadata:
            unit_type = self.domain_metadata[domain].get('unit_type', '').lower()
            if 'core' in unit_type:
                return 'cores', 'Cores'
            elif 'memory' in unit_type or 'mc' in unit_type:
                return 'MCs', 'Memory Controllers'
            elif 'cache' in unit_type or 'cbo' in unit_type or 'cha' in unit_type:
                return 'CBOs', 'Cache Box Units'
            elif 'interconnect' in unit_type or 'upi' in unit_type or 'mesh' in unit_type:
                return 'NCUs', 'Node Controller Units'
            elif 'i/o' in unit_type or 'iio' in unit_type or 'pcie' in unit_type:
                return 'I/O units', 'I/O Units'
            elif 'package' in unit_type or 'socket' in unit_type:
                return 'packages', 'Packages'
        
        # Fallback to pattern matching on domain name
        domain_lower = domain.lower()
        
        # Core domains (P-core, E-core, Atom, Core, LP-core, etc.)
        if 'core' in domain_lower:
            return 'cores', 'Cores'
        
        # Memory Controller domains (IMC, MC, M2M, HBM, etc.)
        elif any(x in domain_lower for x in ['imc', 'mc', 'memory', 'm2m', 'hbm', 'ddr']):
            return 'MCs', 'Memory Controllers'
        
        # Cache/Caching Agent domains (CBO, CHA, LLC, etc.)
        elif any(x in domain_lower for x in ['cbo', 'cha', 'llc', 'cache']):
            # Check for HAC variant
            if 'hac' in domain_lower:
                return 'HAC CBOs', 'HAC Cache Box Units'
            return 'CBOs', 'Cache Box Units'
        
        # Non-Coherent Unit domains (NCU handles interrupts, events, non-coherent flows)
        elif any(x in domain_lower for x in ['ncu', 'upi', 'm3upi', 'mesh']):
            if 'hac' in domain_lower:
                return 'HAC NCUs', 'HAC Non-Coherent Units'
            return 'NCUs', 'Non-Coherent Units'
        
        # I/O and Interconnect domains (IIO, PCIe, UFI, etc.)
        elif any(x in domain_lower for x in ['iio', 'pcie', 'ufi', 'bridge']):
            return 'I/O units', 'I/O Units'
        
        # Power/Package/Socket domains
        elif any(x in domain_lower for x in ['power', 'package', 'pkg', 'socket', 'pcu']):
            return 'packages', 'Packages'
        
        # Graphics/Media domains (GT, Media, etc.)
        elif any(x in domain_lower for x in ['gt', 'gpu', 'graphics', 'media']):
            return 'slices', 'Graphics Slices'
        
        # Default: use generic terminology
        else:
            return 'units', 'Units'
    
    def _get_platform_type(self, hw_config):
        """Dynamically determine platform type based on hardware configuration."""
        product_name = hw_config.get('product_name', '').lower()
        p_cores = hw_config.get('p_cores', 0)
        e_cores = hw_config.get('e_cores', 0)
        total_cores = hw_config.get('total_cores', 0)
        
        # Check for hybrid architecture (P+E cores) = Client
        if p_cores > 0 and e_cores > 0:
            return 'Client Desktop Platform'
        
        # Check for Xeon/server keywords
        if any(keyword in product_name for keyword in ['xeon', 'scalable', 'platinum', 'gold', 'silver', 'bronze']):
            return 'Server Platform'
        
        # Check for workstation keywords
        if any(keyword in product_name for keyword in ['w-', 'workstation', 'w series']):
            return 'Workstation Platform'
        
        # High core count suggests server/workstation
        if total_cores >= 32:
            return 'Server/Workstation Platform'
        
        # Default to generic
        return 'Intel Platform'
    
    def _format_core_count(self, hw_config):
        """Dynamically format core count display based on architecture."""
        total_cores = hw_config.get('total_cores', 'N/A')
        p_cores = hw_config.get('p_cores', 0)
        e_cores = hw_config.get('e_cores', 0)
        
        # Hybrid architecture (Client with P+E cores)
        if p_cores > 0 and e_cores > 0:
            return f'{total_cores} cores ({p_cores}P + {e_cores}E)'
        
        # Homogeneous architecture (Server/Workstation)
        if total_cores != 'N/A':
            return f'{total_cores} cores'
        
        return 'N/A'
    
    def _format_os_display(self, os_info: dict) -> str:
        """Format OS information for display."""
        if not os_info:
            return 'Unknown OS'
        
        os_name = os_info.get('name', os_info.get('os_name', 'Unknown'))
        os_version = os_info.get('version', os_info.get('os_version', ''))
        
        if os_version:
            return f'{os_name} {os_version}'
        return os_name
    
    def _format_workload_display(self, analysis_results: dict) -> str:
        """Format workload information for display."""
        stress_info = analysis_results.get('stress_detection', {})
        
        # Check multiple possible field names for workload info
        # Priority: summary > primary_stress > workload
        workload = (stress_info.get('summary') or 
                    stress_info.get('primary_stress') or 
                    stress_info.get('workload') or 'Unknown')
        
        confidence = stress_info.get('confidence', 0)
        
        # If stress was detected with confidence, show it
        if stress_info.get('detected') and workload and workload != 'Unknown':
            if confidence > 0:
                return f'{workload} ({confidence:.0f}% confidence)'
            return workload
        
        # Check if processes were detected but no summary
        processes = stress_info.get('processes', [])
        if processes:
            proc_names = [p.get('type', p.get('name', '')) for p in processes[:2]]
            return ', '.join(proc_names) if proc_names else 'Stress Detected'
        
        return 'Idle / No Workload Detected'
    
    def _format_workload_type_display(self, analysis_results: dict) -> str:
        """Format workload type for display (subvalue)."""
        stress_info = analysis_results.get('stress_detection', {})
        
        # Get stress info from processes
        processes = stress_info.get('processes', [])
        if processes:
            # Show process details
            proc = processes[0]
            cpu_usage = proc.get('cpu_usage', 0)
            memory_mb = proc.get('memory_mb', 0)
            return f"CPU: {cpu_usage:.1f}% | Memory: {memory_mb:.1f} MB"
        
        # Fallback to stress types if available  
        stress_types = stress_info.get('stress_types', [])
        if stress_types:
            return f"Type: {', '.join(stress_types[:2])}"
        
        return 'No active stress detected'
        
    def generate_json_report(self, analysis_results, sut_ip):
        """Generate detailed JSON report."""
        
        # Convert datetime objects to ISO strings for JSON serialization
        def convert_datetimes(obj):
            """Recursively convert datetime objects to ISO strings."""
            if isinstance(obj, datetime):
                return obj.isoformat()
            elif isinstance(obj, dict):
                return {k: convert_datetimes(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_datetimes(item) for item in obj]
            else:
                return obj
        
        # Deep copy and convert datetimes
        analysis_results_serializable = convert_datetimes(analysis_results)
        
        report_data = {
            'report_metadata': {
                'timestamp': self.timestamp,
                'generation_time': datetime.now().isoformat(),
                'sut_ip': sut_ip,
                'tool_version': 'silicon_coverage_analyzer_v1.0',
                'config_used': self.config
            },
            'analysis_summary': self._generate_summary(analysis_results),  # Use original for summary
            'detailed_results': analysis_results_serializable  # Use serializable for JSON
        }
        
        output_path = f"output/silicon_coverage_analysis_{self.timestamp}.json"
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        
        # Custom JSON encoder to handle numpy types
        class NumpyEncoder(json.JSONEncoder):
            def default(self, obj):
                if hasattr(obj, 'item'):  # numpy int64, float64, etc.
                    return obj.item()
                if hasattr(obj, 'tolist'):  # numpy arrays
                    return obj.tolist()
                return super().default(obj)
        
        with open(output_path, 'w') as f:
            json.dump(report_data, f, indent=2, cls=NumpyEncoder)
        
        # Copy to C drive backup location
        backup_path = self.backup_dir / f"silicon_coverage_analysis_{self.timestamp}.json"
        shutil.copy2(output_path, backup_path)
        print(f"\n[OK] JSON report saved to: {output_path}")
        print(f"[OK] Backup saved to: {backup_path}")
            
        return output_path
    
    def generate_html_report(self, analysis_results, sut_ip):
        """Generate comprehensive HTML report."""
        # Store product ID for ML-learned threshold determination
        self._current_product_id = self._get_product_id(analysis_results)
        logger.info(f"[ReportGen] Extracted product_id: '{self._current_product_id}' from hardware_config")
        
        summary = self._generate_summary(analysis_results)
        
        # Cache trend analysis results to avoid redundant disk I/O
        # This single call will be reused across all tabs (Executive Summary, ML Training, etc.)
        product_id = self._current_product_id
        self._cached_trend_results = None
        if product_id:
            try:
                logger.info(f"Analyzing temporal trends for {product_id} (cached for all tabs)...")
                self._cached_trend_results = self.trend_analyzer.analyze_trends(product_id, lookback_runs=20)
            except Exception as e:
                logger.warning(f"Could not cache trend analysis: {e}")
        
        html_content = self._generate_html_template(summary, analysis_results, sut_ip)
        
        output_path = f"output/silicon_coverage_analysis_{self.timestamp}.html"
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        # Copy to C drive backup location
        backup_path = self.backup_dir / f"silicon_coverage_analysis_{self.timestamp}.html"
        shutil.copy2(output_path, backup_path)
        print(f"\n[OK] HTML report saved to: {output_path}")
        print(f"[OK] Backup saved to: {backup_path}")
            
        return output_path
    
    def _generate_summary(self, analysis_results):
        """Generate analysis summary."""
        domains = analysis_results.get('domains', {})
        coverage = analysis_results.get('coverage', {})
        gaps = analysis_results.get('gaps', {})
        
        # Calculate overall SUT coverage from domain results
        # EXCLUDE events that don't exist on platform or had collection failures
        domain_results = coverage.get('domain_results', {})
        
        total_tested = 0
        total_active = 0
        total_unavailable = 0  # Events that don't exist or failed collection
        
        for d in domain_results.values():
            active_events = d.get('active_events', [])
            inactive_events = d.get('inactive_events', [])
            
            # Count active events
            total_active += len(active_events)
            
            # Count only VALID inactive events (exclude unavailable ones)
            for event in inactive_events:
                status = event.get('status', 'low_activity')
                if status in ['event_not_exists', 'not_found', 'no_file', 'collection_failed']:
                    total_unavailable += 1
                else:
                    total_tested += 1  # Count as tested (no_activity or low_activity)
            
            # Add active events to tested count
            total_tested += len(active_events)
        
        # Calculate coverage excluding unavailable events
        overall_coverage_pct = (total_active / total_tested * 100) if total_tested > 0 else 0
        
        # Check if long-run mode
        collection_mode = coverage.get('collection_mode', 'standard')
        collection_hours = coverage.get('collection_duration_hours', 0)
        
        # Calculate domain stress levels
        stress_analysis = self._analyze_domain_stress(domain_results, analysis_results.get('stress_detection', {}), analysis_results)
        
        # Count real gaps (exclude unavailable events)
        real_gaps = []
        for event in gaps.get('non_toggling_events', []):
            if event.get('reason') not in ['event_not_exists', 'not_found', 'no_file']:
                real_gaps.append(event)
        
        # Extract workload information (use stress_tracking if available, otherwise stress_detection)
        workload_info = self._extract_workload_info(analysis_results)
        
        summary = {
            'total_domains': len(domains),
            'available_domains': len([d for d in domains.values() if d.get('available')]),
            'total_events_discovered': sum(d.get('total_events', 0) for d in domains.values()),
            'total_events_tested': total_tested,
            'total_events_unavailable': total_unavailable,
            'active_events': total_active,
            'overall_coverage_percentage': overall_coverage_pct,
            'non_toggling_events': len(real_gaps),
            'critical_gaps': len(gaps.get('critical_gaps', [])),
            'coverage_status': self._determine_overall_status(overall_coverage_pct, analysis_results),
            'domain_stress': stress_analysis,
            'collection_mode': collection_mode,
            'workload': workload_info['workload'],
            'workload_type': workload_info['type'],
            'workload_metadata': workload_info.get('metadata', {})
        }
        
        # Add custom event mode metadata if applicable
        if self.config.get('custom_event_mode', False):
            summary['custom_event_mode'] = True
            summary['custom_events'] = self.config.get('custom_events', [])
        
        # Add long-run specific metadata
        if collection_mode == 'long_run':
            summary['collection_duration_hours'] = collection_hours
            summary['collection_type'] = f'{collection_hours}-hour continuous monitoring'
        
        return summary
    
    def _extract_workload_info(self, analysis_results) -> Dict[str, Any]:
        """Extract workload information from stress_tracking or stress_detection.
        
        Returns:
            Dict with workload name, type, and metadata
        """
        # Try stress_tracking first (enhanced data)
        stress_tracking = analysis_results.get('stress_tracking', {})
        if stress_tracking:
            return {
                'workload': stress_tracking.get('final_classification', 'Unknown'),
                'type': stress_tracking.get('test_type', 'unknown'),
                'metadata': {
                    'initial_stress': stress_tracking.get('initial_stress'),
                    'unique_stresses': stress_tracking.get('unique_stresses', []),
                    'stress_changes_detected': stress_tracking.get('stress_changes_detected', False),
                    'power_transitions': stress_tracking.get('power_transitions', 0),
                    'timeline': stress_tracking.get('timeline', []),
                    'explanation': stress_tracking.get('explanation', '')
                }
            }
        
        # Fallback to stress_detection (legacy)
        stress_info = analysis_results.get('stress_detection', {})
        if stress_info and stress_info.get('detected'):
            workload = stress_info.get('summary', stress_info.get('primary_stress', 'Unknown'))
            return {
                'workload': workload,
                'type': 'single_stress',  # Assume single stress for legacy data
                'metadata': {
                    'initial_stress': workload,
                    'unique_stresses': [workload],
                    'stress_changes_detected': False,
                    'power_transitions': 0
                }
            }
        
        # No stress detected
        return {
            'workload': 'Idle',
            'type': 'idle',
            'metadata': {
                'initial_stress': 'Idle',
                'unique_stresses': [],
                'stress_changes_detected': False,
                'power_transitions': 0
            }
        }
    
    def _get_ml_learned_coverage_thresholds(self, product_id: str, run_count: int) -> Dict[str, Any]:
        """Load ML-learned coverage thresholds with progressive confidence.
        
        Args:
            product_id: Product identifier
            run_count: Number of historical runs available
            
        Returns:
            Dict with 'thresholds' and 'source' (ml/default/validated)
        """
        from pathlib import Path
        import json
        import numpy as np
        
        data_dir = Path(r'C:\silicon_coverage_analyzer_data')
        thresholds_file = data_dir / f'learned_thresholds_{product_id}.json'
        
        # Bootstrap phase (runs 1-3): Use defaults, no choice
        if run_count < 3:
            return {
                'thresholds': {'excellent': 90, 'good': 70, 'warning': 50, 'critical': 50},
                'source': 'default',
                'reason': f'Bootstrap phase ({run_count}/3 runs)'
            }
        
        # Try to load ML-learned thresholds
        try:
            if thresholds_file.exists():
                with open(thresholds_file, 'r') as f:
                    learned = json.load(f)
                
                # Validate learned thresholds
                required_keys = ['excellent', 'good', 'warning', 'critical']
                if all(k in learned for k in required_keys):
                    # Check ranges (10-99%)
                    valid_range = all(10 <= learned[k] <= 99 for k in required_keys)
                    # Check logical order
                    valid_order = (learned['excellent'] > learned['good'] > 
                                  learned['warning'] > learned['critical'])
                    # Check minimum spacing (3%)
                    valid_spacing = (learned['excellent'] - learned['good'] >= 3 and
                                    learned['good'] - learned['warning'] >= 3 and
                                    learned['warning'] - learned['critical'] >= 3)
                    
                    if valid_range and valid_order and valid_spacing:
                        # Early learning phase (runs 3-9): Use ML with validation
                        if run_count < 10:
                            return {
                                'thresholds': learned,
                                'source': 'ml_validated',
                                'reason': f'ML-learned from {run_count} runs (validated)'
                            }
                        # Mature phase (runs 10+): Force ML (fail if invalid)
                        else:
                            return {
                                'thresholds': learned,
                                'source': 'ml',
                                'reason': f'ML-learned from {run_count} runs'
                            }
                    else:
                        # Invalid ML thresholds - regenerate
                        logger.warning(f"ML-learned thresholds failed validation (run {run_count}), regenerating...")
            
            # No valid thresholds found - learn from historical data
            if run_count >= 3:
                raw_datasets_dir = data_dir / 'raw_datasets' / product_id
                coverage_files = list(raw_datasets_dir.glob('coverage_*.json')) if raw_datasets_dir.exists() else []
                
                if len(coverage_files) >= 3:
                    coverage_percentages = []
                    
                    for file in coverage_files:
                        try:
                            with open(file, 'r') as f:
                                data = json.load(f)
                                coverage_results = data.get('coverage_results', {})
                                coverage_pct = coverage_results.get('activity_coverage', 0)
                                if coverage_pct > 0:
                                    coverage_percentages.append(coverage_pct)
                        except Exception as e:
                            logger.debug(f"Could not read {file.name}: {e}")
                            continue
                    
                    if len(coverage_percentages) >= 3:
                        # Use percentile-based thresholds from historical data
                        coverage_percentages = np.array(coverage_percentages)
                        
                        learned = {
                            'excellent': float(np.percentile(coverage_percentages, 85)),  # Top 15%
                            'good': float(np.percentile(coverage_percentages, 60)),       # Above median
                            'warning': float(np.percentile(coverage_percentages, 35)),    # Below median
                            'critical': float(np.percentile(coverage_percentages, 15))    # Bottom 15%
                        }
                        
                        # Ensure minimum spacing (3%)
                        if learned['excellent'] - learned['good'] < 3:
                            learned['good'] = max(learned['excellent'] - 3, 10)
                        if learned['good'] - learned['warning'] < 3:
                            learned['warning'] = max(learned['good'] - 3, 10)
                        if learned['warning'] - learned['critical'] < 3:
                            learned['critical'] = max(learned['warning'] - 3, 10)
                        
                        # Ensure ranges (10-99%)
                        learned = {k: max(10, min(99, v)) for k, v in learned.items()}
                        
                        # Save learned thresholds
                        data_dir.mkdir(parents=True, exist_ok=True)
                        with open(thresholds_file, 'w') as f:
                            json.dump(learned, f, indent=2)
                        
                        logger.info(f"Learned coverage thresholds from {len(coverage_percentages)} runs: {learned}")
                        
                        # Return with appropriate source
                        if run_count < 10:
                            return {
                                'thresholds': learned,
                                'source': 'ml_validated',
                                'reason': f'ML-learned from {run_count} runs (validated)'
                            }
                        else:
                            return {
                                'thresholds': learned,
                                'source': 'ml',
                                'reason': f'ML-learned from {run_count} runs'
                            }
        
        except Exception as e:
            logger.warning(f"Could not learn thresholds: {e}")
        
        # Fallback: Use defaults
        if run_count >= 10:
            logger.warning(f"WARNING: Run {run_count} should use ML-learned thresholds but falling back to defaults")
        
        return {
            'thresholds': {'excellent': 90, 'good': 70, 'warning': 50, 'critical': 50},
            'source': 'default',
            'reason': f'Fallback (ML learning incomplete or invalid)'
        }
    
    def _determine_overall_status(self, coverage_percentage, analysis_results=None):
        """Determine overall coverage status using ML-learned thresholds."""
        # Get product ID from analysis_results (preferred) or cached value
        product_id = None
        if analysis_results:
            product_id = self._get_product_id(analysis_results)
        
        if not product_id:
            product_id = getattr(self, '_current_product_id', None)
        
        # Fallback to 'unknown' only if product_id is truly None or empty
        if not product_id:
            product_id = 'unknown'
            logger.warning(f"Product ID not set, using 'unknown' - check _get_product_id() implementation")
        
        # Count historical runs
        from pathlib import Path
        data_dir = Path(r'C:\silicon_coverage_analyzer_data') / 'raw_datasets' / product_id
        run_count = len(list(data_dir.glob('coverage_*.json'))) if data_dir.exists() else 0
        
        # Debug: Log threshold calculation
        logger.info(f"[ThresholdCalc] product_id='{product_id}', run_count={run_count}, data_dir={data_dir}, exists={data_dir.exists()}")
        if data_dir.exists():
            files = list(data_dir.glob('coverage_*.json'))
            logger.info(f"[ThresholdCalc] Found {len(files)} coverage files in {data_dir}")
            if files:
                logger.info(f"[ThresholdCalc] Sample files: {[f.name for f in files[:3]]}")
        
        # Get ML-learned or default thresholds
        threshold_result = self._get_ml_learned_coverage_thresholds(product_id, run_count)
        thresholds = threshold_result['thresholds']
        
        # Store for reporting
        if not hasattr(self, '_threshold_metadata'):
            self._threshold_metadata = threshold_result
        
        if coverage_percentage >= thresholds['excellent']:
            return 'excellent'
        elif coverage_percentage >= thresholds['good']:
            return 'good'
        elif coverage_percentage >= thresholds['warning']:
            return 'needs_improvement'
        else:
            return 'critical'
    
    def _analyze_domain_stress(self, domain_results, stress_info, analysis_results):
        """Analyze which domains are most stressed by the current workload.
        
        Returns a dict with stress levels for each domain and overall insights.
        """
        if not domain_results:
            return {'domains': {}, 'insights': []}
        
        domain_stress = {}
        
        # Get ML-learned stress thresholds
        stress_thresholds = self._get_ml_learned_stress_thresholds()
        
        for domain, stats in domain_results.items():
            activity_rate = stats.get('activity_rate', 0)
            event_count = stats.get('total_tested', 0)
            active_count = len(stats.get('active_events', []))
            
            # Calculate stress score (0-100)
            # Higher activity rate + more active events = higher stress
            stress_score = activity_rate
            
            # Classify stress level using ML-learned thresholds
            if stress_score >= stress_thresholds['high']:
                stress_level = 'HIGH'
                color = '#dc3545'  # Red
            elif stress_score >= stress_thresholds['moderate']:
                stress_level = 'MODERATE'
                color = '#ffc107'  # Yellow
            elif stress_score >= stress_thresholds['low']:
                stress_level = 'LOW'
                color = '#17a2b8'  # Blue
            else:
                stress_level = 'MINIMAL'
                color = '#6c757d'  # Gray
            
            domain_stress[domain] = {
                'stress_score': stress_score,
                'stress_level': stress_level,
                'color': color,
                'activity_rate': activity_rate,
                'active_events': active_count,
                'total_tested': event_count
            }
        
        # Generate insights based on workload type
        insights = self._generate_stress_insights(domain_stress, stress_info or {}, analysis_results)
        
        return {
            'domains': domain_stress,
            'insights': insights
        }
    
    def _generate_stress_insights(self, domain_stress, stress_info, analysis_results):
        """Generate human-readable insights about stress coverage."""
        insights = []
        
        # Ensure stress_info is a dict
        if stress_info is None:
            stress_info = {}
        
        # Identify highly stressed domains
        high_stress = [d for d, s in domain_stress.items() if s['stress_level'] == 'HIGH']
        moderate_stress = [d for d, s in domain_stress.items() if s['stress_level'] == 'MODERATE']
        low_stress = [d for d, s in domain_stress.items() if s['stress_level'] in ['LOW', 'MINIMAL']]
        
        # Overall stress distribution
        if high_stress:
            insights.append(f"HIGH STRESS domains: {', '.join(high_stress)}")
        if moderate_stress:
            insights.append(f"MODERATE STRESS domains: {', '.join(moderate_stress)}")
        if low_stress:
            insights.append(f"LOW STRESS domains: {', '.join(low_stress)}")
        
        # Workload-specific insights (use stress_tracking if available)
        workload_info = self._extract_workload_info(analysis_results)
        workload = workload_info['workload'].lower()
        workload_type = workload_info['type']
        
        if 'prime95' in workload or 'cpu' in workload:
            # Check for any core domain (p-core, e-core, core, atom, etc.)
            if any('core' in d.lower() or 'cpu' in d.lower() for d in high_stress):
                insights.append("PASS: CPU stress test effectively exercising core domains")
            else:
                insights.append("WARNING: CPU stress test not strongly stressing core domains")
            
            if any('uncore' in d or 'cbo' in d or 'imc' in d for d in low_stress):
                insights.append("RECOMMENDATION: Consider memory-intensive workload to stress uncore/cache/memory domains")
        
        elif 'memory' in workload or 'stream' in workload:
            if any('imc' in d or 'cbo' in d for d in high_stress):
                insights.append("PASS: Memory stress test effectively exercising memory controller and cache")
            else:
                insights.append("WARNING: Memory stress test not showing expected IMC/cache activity")
        
        return insights
    
    def _generate_html_template(self, summary, analysis_results, sut_ip):
        """Generate HTML report template with tabbed interface."""
        status_colors = {
            'excellent': '#27ae60',
            'good': '#2980b9', 
            'needs_improvement': '#f39c12',
            'critical': '#e74c3c'
        }
        
        status_color = status_colors.get(summary['coverage_status'], '#95a5a6')
        
        gaps = analysis_results.get('gaps', {})
        coverage = analysis_results.get('coverage', {})
        stress_info = analysis_results.get('stress_detection', {})
        
        # Load instruction mix categories for this product
        product_id = summary.get('product_name', '').lower().replace(' ', '_')
        if product_id and not self.instruction_categories_loaded:
            self._load_instruction_categories(product_id)
            logger.info(f"Loaded instruction categories for {product_id} in report generation")
        
        # Get collection mode for conditional rendering
        collection_mode = coverage.get('collection_mode', 'standard')
        
        # Get domain descriptions from config
        pmu_config = self.config.get('pmu_domains', {})
        domain_descriptions = {}
        for domain_key, domain_config in pmu_config.items():
            if isinstance(domain_config, dict):
                desc = domain_config.get('description', domain_config.get('name', ''))
                domain_descriptions[domain_key.upper()] = desc
        
        # Format stress information
        stress_display = 'No stress detected (idle/light load)'
        if stress_info.get('detected'):
            stress_display = stress_info.get('primary_stress', 'Unknown stress')
            if stress_info.get('processes'):
                stress_display += f" ({len(stress_info['processes'])} process(es))"
        
        html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="description" content="Intel Silicon Coverage Analysis Report - PMU Event Coverage and Gap Analysis">
    <title>Silicon Coverage Analysis Report - Intel</title>
    <link rel="icon" type="image/x-icon" href="https://www.intel.com/favicon.ico">
    
    <!-- Chart.js Library - Load without defer to ensure availability -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    
    <style>
        /* PERFORMANCE: Hardware acceleration hints */
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        
        /* GPU acceleration for animations */
        .tab, .tab-content, .summary-card, .action-card {{
            will-change: transform, opacity;
        }}
        
        body {{
            font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, 'Helvetica Neue', Arial, sans-serif;
            background: #f5f7fa;
            min-height: 100vh;
            padding: 20px;
            color: #2c3e50;
        }}
        
        .container {{
            max-width: 98%;
            margin: 0 auto;
            background: white;
            border-radius: 10px;
            box-shadow: 0 4px 20px rgba(0,0,0,0.15);
            overflow: hidden;
        }}
        
        @media (min-width: 1920px) {{
            .container {{
                max-width: 95%;
            }}
        }}
        
        .header {{
            background: linear-gradient(135deg, #0071C5 0%, #003f87 100%);
            color: white;
            padding: 25px 50px;
            display: flex;
            align-items: center;
            gap: 30px;
        }}
        
        .intel-logo-container {{
            display: flex;
            align-items: center;
        }}
        
        .intel-logo {{
            height: 45px;
            width: auto;
        }}
        
        .header-divider {{
            height: 50px;
            width: 2px;
            background: rgba(255,255,255,0.4);
        }}
        
        .header-content {{
            flex: 1;
        }}
        
        .header h1 {{
            font-size: 1.8em;
            margin: 0;
            font-weight: 600;
        }}
        
        .header-subtitle {{
            font-size: 0.9em;
            opacity: 0.85;
            margin-top: 5px;
        }}
        
        .info-banner {{
            background: #f8f9fa;
            border-left: 4px solid #0071C5;
            padding: 20px 50px;
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 30px;
        }}
        
        .info-item {{
            display: flex;
            flex-direction: column;
        }}
        
        .info-label {{
            font-size: 0.75em;
            color: #6c757d;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            font-weight: 600;
            margin-bottom: 5px;
        }}
        
        .info-value {{
            font-size: 1.1em;
            color: #2c3e50;
            font-weight: 600;
        }}
        
        .info-subvalue {{
            font-size: 0.85em;
            color: #6c757d;
            margin-top: 2px;
        }}
        
        .status-badge {{
            display: inline-block;
            background: {status_color};
            padding: 8px 20px;
            border-radius: 25px;
            font-weight: bold;
            text-transform: uppercase;
            margin: 15px 0;
        }}
        
        .tabs {{
            display: flex;
            background: #f8f9fa;
            border-bottom: 2px solid #dee2e6;
        }}
        
        .tab {{
            padding: 15px 30px;
            cursor: pointer;
            border: none;
            background: transparent;
            font-size: 16px;
            font-weight: 600;
            color: #495057;
            transition: all 0.3s;
            border-radius: 8px 8px 0 0;
        }}
        
        .tab:hover {{
            background: #e9ecef;
        }}
        
        .tab.active {{
            background: linear-gradient(135deg, #0071C5 0%, #005a9e 100%);
            color: white;
            border-bottom: 3px solid #003d6b;
            box-shadow: 0 2px 8px rgba(0, 113, 197, 0.3);
        }}
        
        .tab-content {{
            display: none;
            padding: 0 50px 30px 50px;
            background: white;
            animation: fadeIn 0.3s;
        }}
        
        @media (min-width: 1200px) {{
            .tab-content {{
                padding: 0 50px 35px 50px;
            }}
        }}
        
        .tab-content.active {{
            display: block;
        }}
        
        @keyframes fadeIn {{
            from {{ opacity: 0; }}
            to {{ opacity: 1; }}
        }}
        
        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 20px;
            margin-bottom: 30px;
        }}
        
        .metric-card {{
            background: white;
            border: 1px solid #e1e8ed;
            border-radius: 8px;
            padding: 25px;
            text-align: center;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        
        .metric-card:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        }}
        
        .metric-value {{
            font-size: 2.8em;
            font-weight: bold;
            margin: 10px 0;
            background: linear-gradient(135deg, #0071C5 0%, #003e7e 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }}
        
        .metric-label {{
            font-size: 0.9em;
            color: #6c757d;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        
        .metric-subtitle {{
            font-size: 0.85em;
            color: #95a5a6;
            margin-top: 5px;
        }}
        
        .chart-grid {{
            display: grid;
            grid-template-columns: 2fr 1fr;
            gap: 25px;
            margin: 30px 0;
        }}
        
        .chart-container {{
            background: white;
            border: 1px solid #e1e8ed;
            border-radius: 8px;
            padding: 25px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        }}
        
        .chart-title {{
            font-size: 1.2em;
            font-weight: 600;
            color: #2c3e50;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 2px solid #e1e8ed;
        }}
        
        .chart-canvas {{
            min-height: 300px;
            max-height: 400px;
        }}
        
        .full-width-chart {{
            grid-column: 1 / -1;
        }}
        
        .section-title {{
            color: #2c3e50;
            margin: 30px 0 20px 0;
            padding-bottom: 10px;
            font-size: 1.5em;
            font-weight: 600;
        }}
        
        .event-table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        }}
        
        .event-table th {{
            background: linear-gradient(135deg, #0071C5 0%, #003e7e 100%);
            color: white;
            padding: 14px 12px;
            text-align: left;
            font-weight: 600;
            font-size: 0.9em;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        
        .event-table td {{
            padding: 12px;
            border-bottom: 1px solid #e1e8ed;
            font-size: 0.95em;
        }}
        
        .event-table tr:nth-child(even) {{
            background: #f8f9fa;
        }}
        
        .event-table tr:hover {{
            background: #e3f2fd;
            cursor: pointer;
        }}
        
        .event-table .warning-row {{
            background: #fff3cd !important;
        }}
        
        .event-table .warning-row:hover {{
            background: #ffe69c !important;
        }}
        
        .sortable {{
            cursor: pointer;
            user-select: none;
        }}
        
        .sortable:hover {{
            background: rgba(255,255,255,0.1);
        }}
        
        .sortable::after {{
            content: ' ?';
            opacity: 0.5;
        }}
        
        .domain-section {{
            background: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
            margin: 20px 0;
            border-left: 4px solid #3498db;
        }}
        
        .counter-detail {{
            font-family: 'Courier New', monospace;
            font-size: 0.9em;
            color: #495057;
        }}
        
        .core-breakdown {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 10px;
            margin: 15px 0;
        }}
        
        .summary-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }}
        
        .summary-card {{
            background: white;
            padding: 20px;
            border-radius: 8px;
            border: 1px solid #e0e0e0;
            text-align: center;
            box-shadow: 0 2px 4px rgba(0,0,0,0.08);
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        
        .summary-card:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        }}
        
        .metric-value {{
            font-size: 2.5em;
            font-weight: 700;
            margin: 10px 0;
            line-height: 1;
        }}
        
        .metric-label {{
            font-size: 0.95em;
            color: #666;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin: 8px 0;
        }}
        
        .metric-subtitle {{
            font-size: 0.85em;
            color: #999;
            margin: 8px 0 0 0;
        }}
        
        .core-card {{
            background: white;
            padding: 10px;
            border-radius: 5px;
            border: 1px solid #dee2e6;
            text-align: center;
        }}
        
        .core-card.active {{
            border-color: #28a745;
            background: #d4edda;
        }}
        
        .workload-tag {{
            display: inline-block;
            padding: 5px 15px;
            border-radius: 15px;
            margin: 5px;
            font-size: 0.85em;
            font-weight: 600;
        }}
        
        .workload-compute {{ background: #fff3cd; color: #856404; }}
        .workload-memory {{ background: #d1ecf1; color: #0c5460; }}
        .workload-cache {{ background: #d4edda; color: #155724; }}
        .workload-branch {{ background: #f8d7da; color: #721c24; }}
        
        /* Unified Coverage View Styles */
        .view-mode-btn {{
            transition: all 0.3s ease;
        }}
        
        .view-mode-btn:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 8px rgba(0, 113, 197, 0.3);
        }}
        
        .unified-view-container {{
            animation: fadeIn 0.4s ease-in;
        }}
        
        @keyframes fadeIn {{
            from {{ opacity: 0; transform: translateY(10px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        
        /* PERFORMANCE: Optimize rendering */
        .tab-content {{
            contain: layout style paint;  /* CSS containment for better performance */
        }}
        
        table {{
            contain: layout;  /* Isolate table reflows */
        }}
        
        /* Performance Monitor Badge */
        #perfMonitor {{
            position: fixed;
            bottom: 20px;
            left: 20px;
            background: rgba(0, 113, 197, 0.95);
            color: white;
            padding: 10px 15px;
            border-radius: 20px;
            font-size: 0.8em;
            font-weight: 600;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
            z-index: 9999;
            cursor: pointer;
            transition: all 0.3s;
            display: none;
        }}
        
        #perfMonitor:hover {{
            transform: scale(1.05);
            background: rgba(0, 113, 197, 1);
        }}
        
        #perfMonitor.warning {{
            background: rgba(255, 193, 7, 0.95);
            color: #333;
        }}
        
        #perfMonitor.error {{
            background: rgba(220, 53, 69, 0.95);
        }}
        
        .footer {{
            background: #f8f9fa;
            border-top: 3px solid #0071C5;
            color: #2c3e50;
            padding: 30px 50px;
            text-align: center;
        }}
        
        @media (min-width: 1200px) {{  
            .footer {{
                padding: 35px 50px;
            }}
        }}
        
        .footer p {{
            margin: 5px 0;
            opacity: 0.8;
            font-size: 0.95em;
            color: #495057;
        }}
        
        .footer .copyright {{
            margin-top: 12px;
            padding-top: 12px;
            border-top: 1px solid #dee2e6;
            font-size: 0.85em;
            opacity: 0.75;
            color: #6c757d;
        }}
        
        #backToTop {{
            display: none;
            position: fixed;
            bottom: 30px;
            right: 30px;
            z-index: 99;
            border: none;
            outline: none;
            background: linear-gradient(135deg, #0071C5 0%, #005a9e 100%);
            color: white;
            cursor: pointer;
            padding: 0;
            border-radius: 50%;
            font-size: 28px;
            font-weight: 900;
            width: 60px;
            height: 60px;
            box-shadow: 0 4px 16px rgba(0,113,197,0.5);
            transition: all 0.3s;
            display: flex;
            align-items: center;
            justify-content: center;
            line-height: 1;
        }}
        
        #backToTop:hover {{
            background: linear-gradient(135deg, #005a9e 0%, #003f87 100%);
            transform: translateY(-5px) scale(1.05);
            box-shadow: 0 8px 24px rgba(0,113,197,0.7);
        }}
        
        #backToTop:active {{
            transform: translateY(-2px) scale(1.02);
        }}
    </style>
    <script>
        // PERFORMANCE OPTIMIZATION: Lazy Tab Loading
        const tabsRendered = {{
            'executive': true,  // Always render first tab
            'action-items': false,
            'coverage-details': false,
            'workload-health': false,
            'platform-product-insights': false,
            'ml-training-strategy': false
        }};
        
        function switchTab(tabName) {{
            const startTime = performance.now();
            
            // Hide all tabs
            const contents = document.querySelectorAll('.tab-content');
            contents.forEach(c => c.classList.remove('active'));
            
            const tabs = document.querySelectorAll('.tab');
            tabs.forEach(t => t.classList.remove('active'));
            
            // Lazy render tab on first access
            if (!tabsRendered[tabName]) {{
                renderTabContent(tabName);
                tabsRendered[tabName] = true;
            }}
            
            // Show selected tab
            const tabElement = document.getElementById(tabName);
            if (tabElement) {{
                tabElement.classList.add('active');
                document.querySelector(`[onclick="switchTab('${{tabName}}')"]`).classList.add('active');
                
                // Initialize tab-specific features
                initializeTabFeatures(tabName);
                
                const renderTime = performance.now() - startTime;
                if (renderTime > 100) {{
                    console.log(`Tab "${{tabName}}" switched in ${{renderTime.toFixed(0)}}ms`);
                }}
            }}
        }}
        
        function renderTabContent(tabName) {{
            // Tab content is pre-rendered in Python, just show it
            // Future enhancement: Could load via AJAX for truly dynamic loading
            console.log(`Rendering tab: ${{tabName}}`);
        }}
        
        function initializeTabFeatures(tabName) {{
            // Initialize charts and interactive features for the tab
            if (tabName === 'coverage-details' && typeof initUnifiedCharts === 'function') {{
                // Use setTimeout to ensure DOM is fully visible before rendering charts
                setTimeout(function() {{
                    initUnifiedCharts();
                }}, 50);
            }}
            
            // Initialize pagination for large tables
            if (tabName === 'action-items') {{
                initializePagination('action-items-table', 100);
            }}
        }}
        
        // PERFORMANCE OPTIMIZATION: Table Pagination
        let paginationState = {{}};
        
        function initializePagination(tableId, pageSize = 100) {{
            const table = document.getElementById(tableId);
            if (!table || paginationState[tableId]) return; // Already initialized
            
            const tbody = table.querySelector('tbody');
            if (!tbody) return;
            
            const rows = Array.from(tbody.querySelectorAll('tr'));
            const totalRows = rows.length;
            
            if (totalRows <= pageSize) return; // No pagination needed
            
            paginationState[tableId] = {{
                currentPage: 1,
                pageSize: pageSize,
                totalPages: Math.ceil(totalRows / pageSize),
                rows: rows
            }};
            
            // Create pagination controls
            const paginationDiv = document.createElement('div');
            paginationDiv.id = tableId + '-pagination';
            paginationDiv.style.cssText = 'display: flex; justify-content: space-between; align-items: center; padding: 15px; background: #f8f9fa; border-radius: 8px; margin-top: 15px;';
            
            paginationDiv.innerHTML = `
                <div style="color: #666;">
                    Showing <span id="${{tableId}}-range">1-${{Math.min(pageSize, totalRows)}}</span> of ${{totalRows}} rows
                </div>
                <div style="display: flex; gap: 10px;">
                    <button onclick="changePage('${{tableId}}', 'first')" style="padding: 8px 12px; background: white; border: 1px solid #dee2e6; border-radius: 4px; cursor: pointer;">First</button>
                    <button onclick="changePage('${{tableId}}', 'prev')" style="padding: 8px 12px; background: white; border: 1px solid #dee2e6; border-radius: 4px; cursor: pointer;">Previous</button>
                    <span style="padding: 8px 12px; background: white; border: 1px solid #dee2e6; border-radius: 4px;">
                        Page <span id="${{tableId}}-page">1</span> of ${{paginationState[tableId].totalPages}}
                    </span>
                    <button onclick="changePage('${{tableId}}', 'next')" style="padding: 8px 12px; background: white; border: 1px solid #dee2e6; border-radius: 4px; cursor: pointer;">Next</button>
                    <button onclick="changePage('${{tableId}}', 'last')" style="padding: 8px 12px; background: white; border: 1px solid #dee2e6; border-radius: 4px; cursor: pointer;">Last</button>
                </div>
            `;
            
            table.parentNode.insertBefore(paginationDiv, table.nextSibling);
            
            // Show first page
            showPage(tableId, 1);
        }}
        
        function showPage(tableId, pageNum) {{
            const state = paginationState[tableId];
            if (!state || pageNum < 1 || pageNum > state.totalPages) return;
            
            state.currentPage = pageNum;
            
            const start = (pageNum - 1) * state.pageSize;
            const end = start + state.pageSize;
            
            // Hide all rows, show only current page
            state.rows.forEach((row, idx) => {{
                row.style.display = (idx >= start && idx < end) ? '' : 'none';
            }});
            
            // Update pagination UI
            document.getElementById(tableId + '-page').textContent = pageNum;
            document.getElementById(tableId + '-range').textContent = 
                `${{start + 1}}-${{Math.min(end, state.rows.length)}}`;
        }}
        
        function changePage(tableId, direction) {{
            const state = paginationState[tableId];
            if (!state) return;
            
            let newPage = state.currentPage;
            switch(direction) {{
                case 'first': newPage = 1; break;
                case 'prev': newPage = Math.max(1, state.currentPage - 1); break;
                case 'next': newPage = Math.min(state.totalPages, state.currentPage + 1); break;
                case 'last': newPage = state.totalPages; break;
            }}
            
            showPage(tableId, newPage);
        }}
        
        // Scroll to Domain Coverage section within Executive Summary
        function scrollToDomainCoverage() {{
            const section = document.getElementById('domainCoverageSection');
            if (section) {{
                section.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
                // Add highlight effect
                section.style.backgroundColor = '#fff3cd';
                setTimeout(() => {{
                    section.style.transition = 'background-color 1s';
                    section.style.backgroundColor = '';
                }}, 1500);
            }}
        }}
        
        // Action Items Filters
        function applyActionItemFilters() {{
            const domain = document.getElementById('filter-domain').value;
            const severity = document.getElementById('filter-severity').value;
            
            const rows = document.querySelectorAll('#action-items-table tbody tr');
            let visibleCount = 0;
            
            rows.forEach(row => {{
                const rowDomain = row.getAttribute('data-domain') || '';
                const rowSeverity = row.getAttribute('data-severity') || '';
                
                const domainMatch = domain === 'all' || rowDomain.toLowerCase() === domain.toLowerCase();
                const severityMatch = severity === 'all' || rowSeverity.toLowerCase() === severity.toLowerCase();
                
                if (domainMatch && severityMatch) {{
                    row.style.display = '';
                    visibleCount++;
                }} else {{
                    row.style.display = 'none';
                }}
            }});
            
            // Filter anomaly detection sections by domain
            const anomalySections = document.querySelectorAll('.domain-anomalies');
            anomalySections.forEach(section => {{
                const sectionDomain = section.getAttribute('data-domain') || '';
                const domainMatch = domain === 'all' || sectionDomain.toLowerCase() === domain.toLowerCase();
                
                if (domainMatch) {{
                    section.style.display = '';
                }} else {{
                    section.style.display = 'none';
                }}
            }});
            
            // Also filter persistent gaps by domain
            const persistentGapSections = document.querySelectorAll('.persistent-gap-domain');
            persistentGapSections.forEach(section => {{
                const sectionDomain = section.getAttribute('data-domain') || '';
                const domainMatch = domain === 'all' || sectionDomain.toLowerCase() === domain.toLowerCase();
                
                if (domainMatch) {{
                    section.style.display = '';
                }} else {{
                    section.style.display = 'none';
                }}
            }});
            
            showToast(`Filtered: ${{visibleCount}} gaps match criteria`);
        }}
        
        function resetActionItemFilters() {{
            document.getElementById('filter-domain').value = 'all';
            document.getElementById('filter-severity').value = 'all';
            applyActionItemFilters();
        }}
        
        // Export Functions
        function exportActionItemsCSV() {{
            const rows = document.querySelectorAll('#action-items-table tbody tr');
            let csv = 'Event,Domain,Toggle Rate,Severity,Workload Recommendation\\n';
            
            rows.forEach(row => {{
                if (row.style.display !== 'none') {{
                    const cells = row.querySelectorAll('td');
                    const event = cells[0].textContent.trim();
                    const domain = cells[1].textContent.trim();
                    const toggleRate = cells[2].textContent.trim();
                    const severity = cells[3].textContent.trim();
                    const workload = cells[4].textContent.trim().replace(/\\d+% confident/g, '').trim();
                    
                    csv += `"${{event}}","${{domain}}","${{toggleRate}}","${{severity}}","${{workload}}"\\n`;
                }}
            }});
            
            downloadFile(csv, 'action_items.csv', 'text/csv');
            showToast('Exported action items to CSV');
        }}
        
        function exportActionItemsJSON() {{
            const rows = document.querySelectorAll('#action-items-table tbody tr');
            const data = [];
            
            rows.forEach(row => {{
                if (row.style.display !== 'none') {{
                    const cells = row.querySelectorAll('td');
                    data.push({{
                        event_name: cells[0].textContent.trim(),
                        domain: cells[1].textContent.trim(),
                        toggle_rate: cells[2].textContent.trim(),
                        severity: cells[3].textContent.trim(),
                        workload_recommendation: cells[4].textContent.trim().replace(/\\d+% confident/g, '').trim()
                    }});
                }}
            }});
            
            const json = JSON.stringify(data, null, 2);
            downloadFile(json, 'action_items.json', 'application/json');
            showToast('Exported action items to JSON');
        }}
        
        // Helper Functions
        function downloadFile(content, filename, mimeType) {{
            const blob = new Blob([content], {{ type: mimeType }});
            const url = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = filename;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            URL.revokeObjectURL(url);
        }}
        
        function showToast(message) {{
            const toast = document.createElement('div');
            toast.style.cssText = 'position: fixed; top: 20px; right: 20px; background: #2e7d32; color: white; padding: 15px 25px; border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,0.3); z-index: 10000; font-weight: bold;';
            toast.textContent = message;
            document.body.appendChild(toast);
            
            setTimeout(() => {{
                toast.style.transition = 'opacity 0.5s';
                toast.style.opacity = '0';
                setTimeout(() => document.body.removeChild(toast), 500);
            }}, 3000);
        }}
        
        // Trends Chart Update
        function updateTrendsChart() {{
            const selector = document.getElementById('domain-selector');
            const selectedDomains = Array.from(selector.selectedOptions).map(opt => opt.value);
            
            // Hide/show chart datasets based on selection
            if (window.trendsChart) {{
                window.trendsChart.data.datasets.forEach((dataset, idx) => {{
                    const domainName = dataset.label.toLowerCase();
                    dataset.hidden = !selectedDomains.some(d => domainName.includes(d));
                }});
                window.trendsChart.update();
                showToast('Chart updated with selected domains');
            }} else {{
                showToast(`Updated chart for: ${{selectedDomains.join(', ')}}`);
            }}
        }}
        
        // Chart click handler - drill down to domain details
        function handleChartClick(evt, activeElements, chart) {{
            if (activeElements.length > 0) {{
                const element = activeElements[0];
                const datasetIndex = element.datasetIndex;
                const dataIndex = element.index;
                
                const domainName = chart.data.datasets[datasetIndex].label;
                const runNumber = dataIndex + 1;
                const coverageValue = chart.data.datasets[datasetIndex].data[dataIndex];
                
                showChartDrilldown(domainName, runNumber, coverageValue);
            }}
        }}
        
        // Show drill-down modal for chart click
        function showChartDrilldown(domain, runNumber, coverage) {{
            const modal = document.createElement('div');
            modal.id = 'chart-drilldown-modal';
            modal.style.cssText = 'position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); z-index: 10000; display: flex; align-items: center; justify-content: center;';
            
            modal.innerHTML = `
                <div style="background: white; border-radius: 8px; padding: 30px; max-width: 700px; max-height: 80vh; overflow-y: auto; box-shadow: 0 8px 32px rgba(0,0,0,0.3);">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                        <h2 style="margin: 0; color: #0071C5;">Coverage Details</h2>
                        <button onclick="closeChartDrilldown()" style="background: #dc3545; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; font-weight: bold;">
                            ? Close
                        </button>
                    </div>
                    
                    <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px;">
                        <h3 style="margin: 0 0 15px 0; font-size: 24px;">${{domain}}</h3>
                        <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 15px;">
                            <div>
                                <div style="opacity: 0.9; font-size: 14px;">Collection Run</div>
                                <div style="font-size: 28px; font-weight: bold;">Run ${{runNumber}}</div>
                            </div>
                            <div>
                                <div style="opacity: 0.9; font-size: 14px;">Coverage</div>
                                <div style="font-size: 28px; font-weight: bold;">${{coverage.toFixed(1)}}%</div>
                            </div>
                        </div>
                    </div>
                    
                    <h3 style="color: #333; margin-top: 25px;">Event Breakdown</h3>
                    <div style="background: #f8f9fa; padding: 15px; border-radius: 6px;">
                        <p style="margin: 0; color: #666;">Detailed event-level data will be populated as more collections are run.</p>
                    </div>
                    
                    <h3 style="color: #333; margin-top: 25px;">Gaps in This Run</h3>
                    <div style="background: #fff3cd; padding: 15px; border-radius: 6px; border-left: 4px solid #ffc107;">
                        <p style="margin: 0; color: #856404;">Switch to Action Items tab to see gaps for this domain.</p>
                    </div>
                    
                    <h3 style="color: #333; margin-top: 25px;">Historical Comparison</h3>
                    <div style="background: #e3f2fd; padding: 15px; border-radius: 6px; border-left: 4px solid #0071C5;">
                        <p style="margin: 0; color: #0d47a1;">Compare this run with previous runs to identify regressions.</p>
                    </div>
                </div>
            `;
            
            document.body.appendChild(modal);
            
            // Close on background click
            modal.addEventListener('click', (e) => {{
                if (e.target === modal) closeChartDrilldown();
            }});
        }}
        
        function closeChartDrilldown() {{
            const modal = document.getElementById('chart-drilldown-modal');
            if (modal) {{
                modal.remove();
            }}
        }}
        
        // Copy EMON Command
        function copyEmonCommand(commandText) {{
            navigator.clipboard.writeText(commandText).then(() => {{
                showToast('EMON command copied to clipboard!');
            }}).catch(err => {{
                // Fallback for older browsers
                const textArea = document.createElement('textarea');
                textArea.value = commandText;
                textArea.style.position = 'fixed';
                textArea.style.left = '-999999px';
                document.body.appendChild(textArea);
                textArea.select();
                try {{
                    document.execCommand('copy');
                    showToast('EMON command copied to clipboard!');
                }} catch (err) {{
                    showToast('Failed to copy command');
                }}
                document.body.removeChild(textArea);
            }});
        }}
        
        // Export All Gaps to CSV
        function exportAllGapsCSV() {{
            const rows = document.querySelectorAll('#action-items-table tbody tr');
            let csv = 'Event,Domain,Toggle Rate,Severity,Workload Recommendation,EMON Command\\n';
            
            rows.forEach(row => {{
                if (row.style.display !== 'none') {{
                    const cells = row.querySelectorAll('td');
                    const event = cells[0].textContent.trim();
                    const domain = cells[1].textContent.trim();
                    const toggleRate = cells[2].textContent.trim();
                    const severity = cells[3].textContent.trim();
                    const workload = cells[4].textContent.trim().replace(/\\d+% confident/g, '').trim();
                    const emonCmd = cells[5] ? cells[5].querySelector('code')?.textContent.trim() || 'N/A' : 'N/A';
                    
                    csv += `"${{event}}","${{domain}}","${{toggleRate}}","${{severity}}","${{workload}}","${{emonCmd}}"\\n`;
                }}
            }});
            
            downloadFile(csv, 'all_gaps_with_emon.csv', 'text/csv');
            showToast('Exported all gaps with EMON commands to CSV');
        }}
        
        // Export EMON Script
        function exportEmonScript() {{
            const rows = document.querySelectorAll('#action-items-table tbody tr');
            let script = '#!/bin/bash\\n# EMON Validation Script\\n# Generated: ' + new Date().toISOString() + '\\n\\n';
            
            rows.forEach((row, idx) => {{
                if (row.style.display !== 'none') {{
                    const cells = row.querySelectorAll('td');
                    const event = cells[0].textContent.trim();
                    const emonCmd = cells[5] ? cells[5].querySelector('code')?.textContent.trim() : null;
                    
                    if (emonCmd && emonCmd !== 'N/A' && emonCmd !== 'No command') {{
                        script += `# Event: ${{event}}\\n`;
                        script += `${{emonCmd}}\\n\\n`;
                    }}
                }}
            }});
            
            script += '# End of EMON validation script\\n';
            downloadFile(script, 'emon_validation.sh', 'text/plain');
            showToast('Exported EMON validation script');
        }}
        
        function copyAllEmonCommands() {{
            const rows = document.querySelectorAll('#action-items-table tbody tr');
            let commands = [];
            let copyText = '# EMON Commands for Coverage Gaps\\n# Generated: ' + new Date().toISOString() + '\\n\\n';
            
            rows.forEach((row, idx) => {{
                if (row.style.display !== 'none') {{
                    const cells = row.querySelectorAll('td');
                    const event = cells[0].textContent.trim();
                    const domain = cells[1].textContent.trim();
                    const priority = cells[3].textContent.replace(/ML/g, '').trim();
                    const emonCmd = cells[5] ? cells[5].querySelector('code')?.textContent.trim() : null;
                    
                    if (emonCmd && emonCmd !== 'N/A' && emonCmd !== 'No command') {{
                        commands.push({{event, domain, priority, emonCmd}});
                    }}
                }}
            }});
            
            // Group by priority
            ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'].forEach(prio => {{
                const prioCommands = commands.filter(c => c.priority === prio);
                if (prioCommands.length > 0) {{
                    copyText += `### ${{prio}} Priority (${{prioCommands.length}} gaps)\\n`;
                    prioCommands.forEach(cmd => {{
                        copyText += `# ${{cmd.event}} [${{cmd.domain}}]\\n`;
                        copyText += `${{cmd.emonCmd}}\\n\\n`;
                    }});
                    copyText += '\\n';
                }}
            }});
            
            navigator.clipboard.writeText(copyText).then(() => {{
                showToast(`Copied ${{commands.length}} EMON commands to clipboard!`);
            }}).catch(err => {{
                showToast('Failed to copy - please enable clipboard access', true);
            }});
        }}
        
        // Show Gap Details Modal
        function showGapDetails(eventName, domain) {{
            const modal = document.createElement('div');
            modal.id = 'gap-details-modal';
            modal.style.cssText = 'position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); z-index: 10000; display: flex; align-items: center; justify-content: center;';
            
            modal.innerHTML = `
                <div style="background: white; border-radius: 8px; padding: 30px; max-width: 800px; max-height: 80vh; overflow-y: auto; box-shadow: 0 8px 32px rgba(0,0,0,0.3);">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                        <h2 style="margin: 0; color: #0071C5;">Gap Details: ${{eventName}}</h2>
                        <button onclick="closeGapModal()" style="background: #dc3545; color: white; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; font-weight: bold;">
                            ? Close
                        </button>
                    </div>
                    
                    <div style="background: #f8f9fa; padding: 15px; border-radius: 6px; margin-bottom: 20px;">
                        <p style="margin: 0 0 10px 0;"><strong>Domain:</strong> ${{domain}}</p>
                        <p style="margin: 0 0 10px 0;"><strong>Status:</strong> <span style="color: #dc3545; font-weight: bold;">Never Toggled</span></p>
                        <p style="margin: 0;"><strong>Priority:</strong> Needs Investigation</p>
                    </div>
                    
                    <h3 style="color: #333; margin-top: 25px;">Historical Timeline</h3>
                    <div style="background: #e3f2fd; padding: 15px; border-radius: 6px; border-left: 4px solid #0071C5;">
                        <p style="margin: 0; color: #0d47a1;">Historical data will be populated as more collections are run.</p>
                    </div>
                    
                    <h3 style="color: #333; margin-top: 25px;">ML Recommendations</h3>
                    <div style="background: #fff3cd; padding: 15px; border-radius: 6px; border-left: 4px solid #ffc107;">
                        <p style="margin: 0; color: #856404;">Run stress tests to gather more data for ML recommendations.</p>
                    </div>
                    
                    <h3 style="color: #333; margin-top: 25px;">Related Events</h3>
                    <p style="color: #666;">Events that frequently appear together in gaps will be shown here.</p>
                </div>
            `;
            
            document.body.appendChild(modal);
            
            // Close on background click
            modal.addEventListener('click', (e) => {{
                if (e.target === modal) closeGapModal();
            }});
        }}
        
        function closeGapModal() {{
            const modal = document.getElementById('gap-details-modal');
            if (modal) {{
                modal.remove();
            }}
        }}
        
        // Coverage Details Domain Filter
        function filterDomainDetails() {{
            const domain = document.getElementById('domain-filter-details').value;
            
            // Filter hottest events table
            const hottestRows = document.querySelectorAll('#hottest-events-table tbody tr');
            hottestRows.forEach(row => {{
                const rowDomain = row.getAttribute('data-domain') || '';
                if (domain === 'all' || rowDomain === domain) {{
                    row.style.display = '';
                }} else {{
                    row.style.display = 'none';
                }}
            }});
            
            // Filter domain detail sections
            const domainSections = document.querySelectorAll('.domain-detail-section');
            domainSections.forEach(section => {{
                const sectionDomain = section.getAttribute('data-domain') || '';
                if (domain === 'all' || sectionDomain === domain) {{
                    section.style.display = '';
                }} else {{
                    section.style.display = 'none';
                }}
            }});
            
            if (domain === 'all') {{
                showToast('Showing all domains');
            }} else {{
                showToast(`Filtered to: ${{domain.toUpperCase()}}`);
            }}
        }}
        
        // ML Anomaly Explanation Toggle
        function toggleExplanation(explanationId) {{
            const element = document.getElementById(explanationId);
            if (element) {{
                if (element.style.display === 'none') {{
                    element.style.display = 'block';
                }} else {{
                    element.style.display = 'none';
                }}
            }}
        }}
        
        function scrollToTop() {{
            window.scrollTo({{
                top: 0,
                behavior: 'smooth'
            }});
        }}
        
        // Show/hide back-to-top button based on scroll position
        window.onscroll = function() {{
            const backToTopBtn = document.getElementById('backToTop');
            if (backToTopBtn) {{
                if (document.body.scrollTop > 300 || document.documentElement.scrollTop > 300) {{
                    backToTopBtn.style.display = 'block';
                }} else {{
                    backToTopBtn.style.display = 'none';
                }}
            }}
        }};
        
        // ========================================
        // INTERACTIVE ONBOARDING SYSTEM
        // ========================================
        
        let tourStep = 0;
        const tourSteps = [
            {{
                element: '#executive-summary',
                title: 'Welcome to Silicon Coverage Analyzer! ',
                message: 'This tool measures how thoroughly Intel silicon is validated by analyzing PMU event coverage during stress testing. Let\\'s take a quick tour!',
                position: 'bottom'
            }},
            {{
                element: '.quick-stats',
                title: 'Quick Stats Dashboard',
                message: 'Start here for at-a-glance metrics: total coverage %, gap count, anomalies detected, and flaky events.',
                position: 'bottom'
            }},
            {{
                element: '#action-items-table',
                title: 'Action Items - Your Top Priorities',
                message: 'These are the coverage gaps that need immediate attention. Sorted by priority (CRITICAL -> HIGH -> MEDIUM -> LOW). Look for the ML badge to see ML-powered recommendations.',
                position: 'top'
            }},
            {{
                element: 'button[onclick*="copyAllEmonCommands"]',
                title: 'Bulk Export Feature ',
                message: 'Click "Copy All Commands" to copy all EMON validation commands at once - saves 5-10 minutes!',
                position: 'left'
            }},
            {{
                element: '.tab[onclick*="coverage-details"]',
                title: 'Coverage Details Tab',
                message: 'Dive deep into domain-level coverage, hottest events, and toggle rate distributions.',
                position: 'bottom'
            }},
            {{
                element: '.tab[onclick*="ml-training"]',
                title: 'ML Training Status',
                message: 'Track ML model training progress. Models auto-train every 5 runs. Check the visual progress bar!',
                position: 'bottom'
            }},
            {{
                element: '#executive-summary',
                title: 'You\\'re All Set! ',
                message: 'Start by reviewing your Action Items, then export EMON commands for validation. Run more collections to train ML models. Happy analyzing!',
                position: 'center'
            }}
        ];
        
        function startTour() {{
            // Check if user has completed tour
            if (localStorage.getItem('silicon_analyzer_tour_completed') === 'true') {{
                return; // Skip tour for returning users
            }}
            
            tourStep = 0;
            showTourStep();
        }}
        
        function showTourStep() {{
            // Remove any existing tour overlay
            const existing = document.getElementById('tour-overlay');
            if (existing) existing.remove();
            
            // Show emergency close button
            const emergencyBtn = document.getElementById('emergency-close-tour');
            if (emergencyBtn) emergencyBtn.style.display = 'block';
            
            if (tourStep >= tourSteps.length) {{
                endTour();
                return;
            }}
            
            const step = tourSteps[tourStep];
            const targetElement = document.querySelector(step.element);
            
            if (!targetElement) {{
                tourStep++;
                showTourStep();
                return;
            }}
            
            // Create overlay
            const overlay = document.createElement('div');
            overlay.id = 'tour-overlay';
            overlay.style.cssText = 'position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.7); z-index: 9998; backdrop-filter: blur(2px); pointer-events: none;';
            
            // Highlight target element
            const rect = targetElement.getBoundingClientRect();
            const highlight = document.createElement('div');
            highlight.style.cssText = `position: fixed; top: ${{rect.top - 5}}px; left: ${{rect.left - 5}}px; width: ${{rect.width + 10}}px; height: ${{rect.height + 10}}px; border: 3px solid #0071C5; border-radius: 8px; box-shadow: 0 0 0 9999px rgba(0,0,0,0.7), 0 0 20px #0071C5; z-index: 9999; pointer-events: none; animation: pulse 2s infinite;`;
            
            // Create tooltip
            const tooltip = document.createElement('div');
            tooltip.style.cssText = 'position: fixed; background: white; padding: 20px 25px; border-radius: 12px; box-shadow: 0 8px 32px rgba(0,0,0,0.3); z-index: 10000; max-width: 400px; animation: slideIn 0.3s ease; pointer-events: auto;';
            
            // Position tooltip based on step position
            if (step.position === 'bottom') {{
                tooltip.style.top = `${{rect.bottom + 15}}px`;
                tooltip.style.left = `${{rect.left}}px`;
            }} else if (step.position === 'top') {{
                tooltip.style.bottom = `${{window.innerHeight - rect.top + 15}}px`;
                tooltip.style.left = `${{rect.left}}px`;
            }} else if (step.position === 'left') {{
                tooltip.style.top = `${{rect.top}}px`;
                tooltip.style.right = `${{window.innerWidth - rect.left + 15}}px`;
            }} else {{ // center
                tooltip.style.top = '50%';
                tooltip.style.left = '50%';
                tooltip.style.transform = 'translate(-50%, -50%)';
            }}
            
            tooltip.innerHTML = `
                <h3 style="margin: 0 0 10px 0; color: #0071C5; font-size: 1.2em;">${{step.title}}</h3>
                <p style="margin: 0 0 15px 0; color: #333; line-height: 1.6;">${{step.message}}</p>
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span style="color: #666; font-size: 0.9em;">Step ${{tourStep + 1}} of ${{tourSteps.length}}</span>
                    <div>
                        ${{tourStep > 0 ? '<button onclick="prevTourStep()" style="padding: 8px 15px; margin-right: 10px; background: #f0f0f0; border: none; border-radius: 6px; cursor: pointer; font-weight: 600;"><- Back</button>' : ''}}
                        <button onclick="${{tourStep < tourSteps.length - 1 ? 'nextTourStep()' : 'endTour()'}}" style="padding: 8px 20px; background: #0071C5; color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: 600;">
                            ${{tourStep < tourSteps.length - 1 ? 'Next ->' : 'Got It! Done'}}
                        </button>
                    </div>
                </div>
                <button onclick="skipTour()" style="position: absolute; top: 10px; right: 10px; background: transparent; border: none; font-size: 1.5em; color: #999; cursor: pointer; padding: 5px 10px;" title="Skip Tour">×</button>
            `;
            
            document.body.appendChild(overlay);
            document.body.appendChild(highlight);
            document.body.appendChild(tooltip);
            
            // Scroll target into view
            targetElement.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
        }}
        
        function nextTourStep() {{
            tourStep++;
            showTourStep();
        }}
        
        function prevTourStep() {{
            tourStep--;
            showTourStep();
        }}
        
        function skipTour() {{
            localStorage.setItem('silicon_analyzer_tour_completed', 'true');
            endTour();
        }}
        
        function endTour() {{
            const overlay = document.getElementById('tour-overlay');
            if (overlay) overlay.remove();
            const highlights = document.querySelectorAll('[style*="z-index: 9999"]');
            highlights.forEach(h => h.remove());
            const tooltips = document.querySelectorAll('[style*="z-index: 10000"]');
            tooltips.forEach(t => t.remove());
            
            // Hide emergency close button
            const emergencyBtn = document.getElementById('emergency-close-tour');
            if (emergencyBtn) emergencyBtn.style.display = 'none';
            
            // Additional cleanup - remove any stray overlays
            document.querySelectorAll('[id*="tour-"]').forEach(el => el.remove());
            
            localStorage.setItem('silicon_analyzer_tour_completed', 'true');
            showToast('Tour completed! You can restart it anytime from the help menu.');
        }}
        
        // Global escape key handler to exit tour
        document.addEventListener('keydown', function(e) {{
            if (e.key === 'Escape' && document.getElementById('tour-overlay')) {{
                skipTour();
            }}
        }});
        
        function restartTour() {{
            localStorage.removeItem('silicon_analyzer_tour_completed');
            startTour();
        }}
        
        // Add CSS animations
        const style = document.createElement('style');
        style.textContent = `
            @keyframes pulse {{
                0%, 100% {{ box-shadow: 0 0 0 9999px rgba(0,0,0,0.7), 0 0 20px #0071C5; }}
                50% {{ box-shadow: 0 0 0 9999px rgba(0,0,0,0.7), 0 0 30px #0071C5, 0 0 40px #0071C5; }}
            }}
            @keyframes slideIn {{
                from {{ opacity: 0; transform: translateY(-20px); }}
                to {{ opacity: 1; transform: translateY(0); }}
            }}
            .tooltip-help {{
                display: inline-block;
                width: 18px;
                height: 18px;
                background: #0071C5;
                color: white;
                border-radius: 50%;
                text-align: center;
                line-height: 18px;
                font-size: 12px;
                font-weight: bold;
                cursor: help;
                margin-left: 5px;
                position: relative;
            }}
            .tooltip-help:hover::after {{
                content: attr(data-tooltip);
                position: absolute;
                bottom: 25px;
                left: 50%;
                transform: translateX(-50%);
                background: #333;
                color: white;
                padding: 8px 12px;
                border-radius: 6px;
                white-space: nowrap;
                font-size: 13px;
                font-weight: normal;
                z-index: 1000;
                box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            }}
            .tooltip-help:hover::before {{
                content: '';
                position: absolute;
                bottom: 20px;
                left: 50%;
                transform: translateX(-50%);
                border: 5px solid transparent;
                border-top-color: #333;
                z-index: 1000;
            }}
        `;
        document.head.appendChild(style);
        
        // Start tour on page load (only for first-time users)
        // DISABLED: Tour causing UI blocking issues
        // window.addEventListener('load', function() {{
        //     setTimeout(startTour, 1000); // Delay 1 second for page to settle
        // }});
        
        // PERFORMANCE MONITORING: Track page metrics
        let perfMetrics = {{
            pageLoadTime: 0,
            tabSwitchTimes: {{}},
            chartRenderTimes: {{}},
            interactionCount: 0
        }};
        
        window.addEventListener('load', function() {{
            // Calculate page load time using modern API with fallback
            setTimeout(function() {{
                let loadTime = 0;
                
                // Try modern Performance API first
                if (window.performance && window.performance.getEntriesByType) {{
                    const navEntries = window.performance.getEntriesByType('navigation');
                    if (navEntries.length > 0) {{
                        loadTime = navEntries[0].loadEventEnd;
                    }}
                }}
                
                // Fallback to timing API (with validation)
                if (loadTime <= 0 && window.performance && window.performance.timing) {{
                    const perfData = window.performance.timing;
                    if (perfData.loadEventEnd > 0 && perfData.navigationStart > 0) {{
                        loadTime = perfData.loadEventEnd - perfData.navigationStart;
                    }}
                }}
                
                // Only show badge if we got a valid positive time
                if (loadTime > 0 && loadTime < 60000) {{  // Sanity check: under 60 seconds
                    perfMetrics.pageLoadTime = loadTime;
                    
                    if (loadTime > 5000) {{
                        showPerfBadge('error', `Slow: ${{(loadTime/1000).toFixed(1)}}s`);
                    }} else if (loadTime > 3000) {{
                        showPerfBadge('warning', `Load: ${{(loadTime/1000).toFixed(1)}}s`);
                    }} else {{
                        showPerfBadge('good', `Fast: ${{(loadTime/1000).toFixed(1)}}s`);
                    }}
                }}
            }}, 100);  // Small delay to ensure timing data is populated
        }});
        
        function showPerfBadge(status, message) {{
            let badge = document.getElementById('perfMonitor');
            if (!badge) {{
                badge = document.createElement('div');
                badge.id = 'perfMonitor';
                badge.onclick = togglePerfDetails;
                document.body.appendChild(badge);
            }}
            
            badge.className = status;
            badge.textContent = '' + message;
            badge.style.display = 'block';
            
            // Auto-hide after 5 seconds
            setTimeout(() => {{
                badge.style.opacity = '0.3';
            }}, 5000);
        }}
        
        function togglePerfDetails() {{
            const badge = document.getElementById('perfMonitor');
            if (badge.style.opacity === '0.3') {{
                badge.style.opacity = '1';
            }} else {{
                const details = `
PERFORMANCE METRICS:
━━━━━━━━━━━━━━━━━━━━
Page Load: ${{(perfMetrics.pageLoadTime/1000).toFixed(2)}}s
Tab Switches: ${{Object.keys(perfMetrics.tabSwitchTimes).length}}
Interactions: ${{perfMetrics.interactionCount}}

RECOMMENDATIONS:
${{perfMetrics.pageLoadTime > 3000 ? '* Report has large dataset - consider filtering\\n' : ''}}${{Object.keys(perfMetrics.tabSwitchTimes).length > 10 ? '* Frequent tab switching - use browser search\\n' : ''}}* Use Ctrl+F to find specific events
* Export CSV for offline analysis
* Close other browser tabs for speed
                `.trim();
                
                alert(details);
            }}
        }}
        
        // Track interactions
        document.addEventListener('click', function() {{
            perfMetrics.interactionCount++;
        }});
        
        // Optimize: Debounce search inputs
        function debounce(func, wait) {{
            let timeout;
            return function executedFunction(...args) {{
                const later = () => {{
                    clearTimeout(timeout);
                    func(...args);
                }};
                clearTimeout(timeout);
                timeout = setTimeout(later, wait);
            }};
        }}
    </script>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="intel-logo-container" style="cursor: pointer;" onclick="location.reload();" title="Click to refresh report">
                <!-- Official Intel Logo (Black accent with white text for dark background) -->
                <svg class="intel-logo" viewBox="0 0 395.4 155.9" xmlns="http://www.w3.org/2000/svg">
                    <style type="text/css">
                        .st0{{fill:#000000;}}
                    </style>
                    <rect x="4.7" y="5.2" class="st0" width="28.1" height="28.1"/>
                    <g>
                        <path fill="#FFFFFF" d="M32.1,151.6V50.4H5.5v101.2H32.1z M208.9,152.6v-24.8c-3.9,0-7.2-0.2-9.6-0.6c-2.8-0.4-4.9-1.4-6.3-2.8
                            c-1.4-1.4-2.3-3.4-2.8-6c-0.4-2.5-0.6-5.8-0.6-9.8V73.2h19.3V50.4h-19.3V10.9h-26.7v97.9c0,8.3,0.7,15.3,2.1,20.9
                            c1.4,5.5,3.8,10,7.1,13.4s7.7,5.8,13,7.3c5.4,1.5,12.2,2.2,20.3,2.2L208.9,152.6L208.9,152.6z M361.7,151.6V3.1H335v148.5H361.7z
                            M137.2,60.3c-7.4-8-17.8-12-31-12c-6.4,0-12.2,1.3-17.5,3.9C83.5,54.8,79,58.4,75.5,63L74,64.9v-1.7V50.4H47.7v101.2h26.5V97.7
                            v3.7c0-0.6,0-1.2,0-1.8c0.3-9.5,2.6-16.5,7-21c4.7-4.8,10.4-7.2,16.9-7.2c7.7,0,13.6,2.4,17.5,7c3.8,4.6,5.8,11.1,5.8,19.4l0,0V98
                            l0,0l0,0v53.5h26.9V94.1C148.4,79.7,144.6,68.3,137.2,60.3z M321.2,100.8c0-7.3-1.3-14.1-3.8-20.5c-2.6-6.3-6.2-11.9-10.7-16.7
                            c-4.6-4.8-10.1-8.5-16.5-11.2s-13.5-4-21.2-4c-7.3,0-14.2,1.4-20.6,4.1c-6.4,2.8-12,6.5-16.7,11.2s-8.5,10.3-11.2,16.7
                            c-2.8,6.4-4.1,13.3-4.1,20.6c0,7.3,1.3,14.2,3.9,20.6c2.6,6.4,6.3,12,10.9,16.7c4.6,4.7,10.3,8.5,16.9,11.2
                            c6.6,2.8,13.9,4.2,21.7,4.2c22.6,0,36.6-10.3,45-19.9l-19.2-14.6c-4,4.8-13.6,11.3-25.6,11.3c-7.5,0-13.7-1.7-18.4-5.2
                            c-4.7-3.4-7.9-8.2-9.6-14.1l-0.3-0.9h79.5L321.2,100.8L321.2,100.8z M241.9,91.5c0-7.4,8.5-20.3,26.8-20.4
                            c18.3,0,26.9,12.9,26.9,20.3L241.9,91.5z"/>
                        <path fill="#FFFFFF" d="M392.1,138.4c-0.5-1.2-1.2-2.2-2.1-3.1c-0.9-0.9-1.9-1.6-3.1-2.1s-2.5-0.8-3.8-0.8c-1.4,0-2.6,0.3-3.8,0.8
                            c-1.2,0.5-2.2,1.2-3.1,2.1c-0.9,0.9-1.6,1.9-2.1,3.1c-0.5,1.2-0.8,2.5-0.8,3.8c0,1.4,0.3,2.6,0.8,3.8s1.2,2.2,2.1,3.1
                            c0.9,0.9,1.9,1.6,3.1,2.1s2.5,0.8,3.8,0.8c1.4,0,2.6-0.3,3.8-0.8c1.2-0.5,2.2-1.2,3.1-2.1c0.9-0.9,1.6-1.9,2.1-3.1
                            c0.5-1.2,0.8-2.5,0.8-3.8S392.6,139.6,392.1,138.4z M390.5,145.4c-0.4,1-1,1.9-1.7,2.6c-0.7,0.7-1.6,1.3-2.6,1.7s-2,0.6-3.2,0.6
                            c-1.1,0-2.2-0.2-3.2-0.6c-1-0.4-1.9-1-2.6-1.7s-1.3-1.6-1.7-2.6c-0.4-1-0.6-2-0.6-3.2c0-1.1,0.2-2.2,0.6-3.2s1-1.9,1.7-2.6
                            c0.7-0.7,1.6-1.3,2.6-1.7s2-0.6,3.2-0.6c1.1,0,2.2,0.2,3.2,0.6c1,0.4,1.9,1,2.6,1.7s1.3,1.6,1.7,2.6c0.4,1,0.6,2,0.6,3.2
                            C391.2,143.4,390.9,144.4,390.5,145.4z M384.9,143c0.8-0.1,1.4-0.4,1.9-0.9s0.8-1.2,0.8-2.2c0-1.1-0.3-1.9-1-2.5
                            c-0.6-0.6-1.7-0.9-3-0.9h-4.4v11.3h2.1v-4.6h1.5l2.8,4.6h2.2L384.9,143z M383.8,141.4c-0.3,0-0.6,0-1,0h-1.5v-3.2h1.5
                            c0.3,0,0.6,0,1,0c0.3,0,0.6,0.1,0.9,0.2c0.3,0.1,0.5,0.3,0.6,0.5s0.2,0.5,0.2,0.9s-0.1,0.7-0.2,0.9c-0.2,0.2-0.4,0.4-0.6,0.5
                            C384.4,141.3,384.1,141.4,383.8,141.4z"/>
                    </g>
                </svg>
            </div>
            <div class="header-divider"></div>
            <div class="header-content">
                <h1>Silicon Coverage Analysis Report</h1>
                <p class="header-subtitle">Uncore BDC CVE Labs | Generated: {datetime.now().strftime('%B %d, %Y at %I:%M %p')}</p>
            </div>
            <div class="status-badge">{summary['coverage_status'].replace('_', ' ')}</div>
        </div>
        
        <div class="info-banner">
            <div class="info-item">
                <div class="info-label">Product Line</div>
                <div class="info-value">{analysis_results.get('hardware_config', {}).get('product_name', 'Unknown Platform')}</div>
                <div class="info-subvalue">{self._get_platform_type(analysis_results.get('hardware_config', {}))}</div>
            </div>
            <div class="info-item">
                <div class="info-label">System Under Test</div>
                <div class="info-value">{sut_ip}</div>
                <div class="info-subvalue">{self._format_core_count(analysis_results.get('hardware_config', {}))}</div>
            </div>
            <div class="info-item">
                <div class="info-label">Operating System</div>
                <div class="info-value">{self._format_os_display(analysis_results.get('os_info', {}))}</div>
                <div class="info-subvalue">{analysis_results.get('os_info', {}).get('architecture', 'Unknown arch')}</div>
            </div>
            <div class="info-item">
                <div class="info-label">Collection Mode</div>
                <div class="info-value">{summary.get('collection_type', 'Standard (3s samples)')}</div>
                <div class="info-subvalue">{'Long-run batched monitoring' if summary.get('collection_mode') == 'long_run' else 'Fast optimized collection'}</div>
            </div>
            <div class="info-item">
                <div class="info-label">Stress Condition</div>
                <div class="info-value">{self._format_workload_display(analysis_results)}</div>
                <div class="info-subvalue">{self._format_workload_type_display(analysis_results)}</div>
            </div>
            <div class="info-item">
                <div class="info-label">EMON / PMU Version</div>
                <div class="info-value">EMON 5.{analysis_results.get('hardware_config', {}).get('emon_version', '56')}</div>
                <div class="info-subvalue">{summary['total_domains']} PMU domains</div>
            </div>
        </div>
"""
        
        # Add Linux NMI Watchdog warning if applicable
        os_info = analysis_results.get('os_info', {})
        if os_info.get('os_type') == 'linux' and os_info.get('nmi_watchdog_enabled'):
            pmu_starved_count = sum(
                sum(1 for e in domain_data.get('inactive_events', []) if e.get('status') == 'pmu_starved')
                for domain_data in analysis_results.get('coverage', {}).get('domain_results', {}).values()
            )
            
            if pmu_starved_count > 0:
                html_content += f"""
        <div style="background: linear-gradient(135deg, #ff6b6b 0%, #ee5a6f 100%); color: white; padding: 15px 25px; margin: 15px 0; border-radius: 8px; border-left: 4px solid #c92a2a;">
            <div style="display: flex; align-items: center; gap: 12px;">
                <div style="flex: 1;">
                    <strong style="font-size: 16px;">Linux PMU Counter Competition Detected</strong>
                    <div style="margin-top: 5px; font-size: 13px; opacity: 0.95;">
                        <strong>{pmu_starved_count} events</strong> experienced PMU starvation due to Linux kernel NMI watchdog consuming hardware counters.
                        This is <strong>not an EMON issue</strong> - it's kernel-level PMU resource competition that doesn't occur on Windows.
                    </div>
                    <div style="margin-top: 8px; font-size: 12px; background: rgba(0,0,0,0.2); padding: 8px 12px; border-radius: 4px;">
                         <strong>Fix:</strong> Temporarily disable NMI watchdog: <code style="background: rgba(0,0,0,0.3); padding: 2px 6px; border-radius: 3px;">echo 0 > /proc/sys/kernel/nmi_watchdog</code>
                    </div>
                </div>
            </div>
        </div>
"""
        
        html_content += """
        <div class="tabs">
            <button class="tab active" onclick="switchTab('executive')">Executive Summary</button>
            <button class="tab" onclick="switchTab('action-items')">Action Items</button>
            <button class="tab" onclick="switchTab('coverage-details')">Coverage Details</button>
            <button class="tab" onclick="switchTab('workload-health')">Workload & Health</button>
            <button class="tab" onclick="switchTab('platform-product-insights')">Platform & Product Insights</button>
            <button class="tab" onclick="switchTab('ml-training-strategy')">ML Training Strategy</button>
        </div>
        
        <!-- TAB CONTENT SECTIONS -->
"""
        
        # PRE-COMPUTE SHARED DATA: Use cached temporal trends computed at report start
        try:
            trend_results = self._cached_trend_results
            if trend_results:
                analysis_results['temporal_trends'] = trend_results
                if self.debug:
                    print(f"[DEBUG] Using cached temporal trends - Runs analyzed: {trend_results.get('runs_analyzed', 0)}")
                logger.info(f"[Report] Using cached temporal trends - Runs analyzed: {trend_results.get('runs_analyzed', 0)}")
            else:
                if self.debug:
                    print(f"[DEBUG] No cached trend results available")
                logger.warning(f"[WARN] No cached trend results available")
        except Exception as e:
            if self.debug:
                print(f"[DEBUG] Temporal trend retrieval failed: {e}")
            logger.warning(f"[WARN] Temporal trend retrieval failed: {e}")
        
        # MODULAR TAB GENERATION: Use modular methods if enabled
        if self.use_modular_tabs:
            if self.debug:
                print(f"[DEBUG] Using modular tabs - generating new restructured tabs")
            logger.info("[Report] Using modular tab generation")
            # Generate all tabs using consistent modular methods
            tabs_to_generate = [
                ('executive', lambda: self.executive_tab_generator.generate(summary, analysis_results)),
                ('action-items', lambda: self.action_items_tab_generator.generate(analysis_results)),
                ('coverage-details', lambda: self.coverage_details_tab_generator.generate(analysis_results)),
                ('workload-health', lambda: self.workload_health_tab_generator.generate(analysis_results)),
                ('platform-product-insights', lambda: self.platform_product_insights_tab_generator.generate(analysis_results)),
                ('ml-training-strategy', lambda: self.ml_training_strategy_tab_generator.generate(analysis_results)),
            ]
            
            # Generate each tab with per-tab HTML balancing
            for tab_name, tab_generator in tabs_to_generate:
                if self.debug:
                    print(f"[DEBUG] Generating tab: {tab_name}")
                tab_html = tab_generator()
                
                # Per-tab HTML div balancing
                div_opens = tab_html.count('<div')
                div_closes = tab_html.count('</div>')
                if div_opens != div_closes:
                    diff = div_opens - div_closes
                    if self.debug:
                        print(f"[DEBUG] Tab {tab_name}: {div_opens} opens, {div_closes} closes (diff: {diff:+d}) - fixing")
                    if diff > 0:
                        # Add missing closing divs before tab ends
                        tab_html = tab_html.rstrip() + '\n' + '</div>\n' * diff
                    elif diff < 0:
                        # Remove extra closing divs from end
                        for _ in range(abs(diff)):
                            last_pos = tab_html.rfind('</div>')
                            if last_pos != -1:
                                tab_html = tab_html[:last_pos] + tab_html[last_pos + 6:]
                
                html_content += tab_html
            
            # Format total execution time
            total_seconds = analysis_results.get('total_execution_time_seconds', coverage.get('collection_time_seconds', 0))
            hours = int(total_seconds // 3600)
            minutes = int((total_seconds % 3600) // 60)
            seconds = int(total_seconds % 60)
            time_str = f"{hours}:{minutes:02d}:{seconds:02d}"
            
            # Close all tab content and add ONE global footer
            html_content += f"""
        
        <!-- GLOBAL FOOTER (Outside all tabs) -->
        <div class="footer" style="margin-top: 50px; background: linear-gradient(135deg, #0071C5 0%, #003f87 100%); color: white; text-align: center; border-top: 4px solid #0071C5; box-shadow: 0 -4px 12px rgba(0,0,0,0.1);">
            <p style="font-size: 1.2em; font-weight: 600; margin-bottom: 10px; color: white;">Silicon Coverage Analyzer</p>
            <p style="margin-bottom: 15px; color: rgba(255,255,255,0.9);">Report generated: {self.timestamp}</p>
            <div style="border-top: 1px solid rgba(255,255,255,0.3); padding-top: 15px; margin-top: 15px;">
                <p style="margin: 5px 0; color: white; font-weight: 500;">© Intel Corporation | Intel Uncore BDC CVE Labs</p>
                <p style="margin: 5px 0; font-size: 0.9em; color: rgba(255,255,255,0.85);">Intel Confidential - Internal Use Only</p>
            </div>
        </div>
        
        <!-- Floating Back to Top Button -->
        <button id="backToTop" onclick="scrollToTop()" title="Back to Top">
            
        </button>
    </div>
</body>
</html>
"""
            # Runtime fix: Balance any conditional divs BEFORE validation
            div_opens = html_content.count('<div')
            div_closes = html_content.count('</div>')
            
            if div_opens != div_closes:
                diff = div_opens - div_closes
                print(f"\n Runtime HTML balance: {div_opens} opens, {div_closes} closes (diff: {diff:+d}) - auto-fixing\n")
                
                if diff > 0:
                    # Add missing closing divs before </body>
                    closing_divs = '\n' + '</div>\n' * diff
                    html_content = html_content.replace('</body>', closing_divs + '</body>')
                elif diff < 0:
                    # Remove extra closing divs
                    for _ in range(abs(diff)):
                        last_pos = html_content.rfind('</div>')
                        if last_pos != -1:
                            html_content = html_content[:last_pos] + html_content[last_pos + 6:]
            
            # Validate the complete HTML after balancing
            self._validate_html_structure(html_content)
            
            return html_content
    
    def _validate_html_structure(self, html_content):
        """Validate HTML structure for balanced tags."""
        div_opens = html_content.count('<div')
        div_closes = html_content.count('</div>')
        
        if self.config.get('debug', False):
            if div_opens == div_closes:
                print(f"\nHTML VALIDATION PASSED - No structural issues detected\n")
            else:
                diff = div_opens - div_closes
                print(f"\n HTML VALIDATION WARNING: {div_opens} opens, {div_closes} closes (diff: {diff:+d})\n")
    
    # ============================================================================
    # MODULAR TAB GENERATION METHODS
    # ============================================================================
    
    def _classify_gap_priority(self, event_name, domain):
        """Classify gap priority based on event name and domain patterns."""
        event_upper = event_name.upper()
        
        # Critical priority patterns
        critical_patterns = ['THERMAL', 'THROTTLE', 'PROCHOT', 'MACHINE_CLEAR', 'PAGE_FAULT', 
                            'IDQ_UOPS', 'FRONTEND_RETIRED', 'BACKEND_BOUND', 'BAD_SPECULATION']
        if any(pattern in event_upper for pattern in critical_patterns):
            return 'critical'
        
        # High priority patterns
        high_patterns = ['INST_RETIRED', 'UOPS_RETIRED', 'CYCLES', 'STALLS', 'RESOURCE_STALLS',
                        'MEM_LOAD_RETIRED', 'MEM_STORE_RETIRED', 'BR_MISP_RETIRED']
        if any(pattern in event_upper for pattern in high_patterns):
            return 'high'
        
        # Medium priority for critical domains
        critical_domains = _DOMAIN_CONFIG.get('critical_domains', ['p-core', 'e-core', 'imc'])
        if domain.lower() in [d.lower() for d in critical_domains]:
            return 'medium'
        
        # Also check for core/memory patterns in domain name
        if any(x in domain.lower() for x in ['core', 'imc', 'mc', 'memory']):
            return 'medium'
        
        # Default to low
        return 'low'
    
    def generate_all_reports(self, analysis_results, sut_ip):
        """Generate all configured report formats."""
        reports = {}
        
        if 'json' in self.output_formats:
            reports['json'] = self.generate_json_report(analysis_results, sut_ip)
            
        if 'html' in self.output_formats:
            reports['html'] = self.generate_html_report(analysis_results, sut_ip)
        
        # Always generate CSV exports for Excel analysis
        reports['csv_detailed'] = self.generate_detailed_csv(analysis_results, sut_ip)
        reports['csv_summary'] = self.generate_summary_csv(analysis_results, sut_ip)
        
        # Generate enhanced gap analysis CSVs
        try:
            product_id = self._get_product_id(analysis_results)
            
            reports['csv_gap_analysis'] = self.gap_exporter.generate_gap_report_csv(analysis_results, sut_ip)
            reports['csv_workload_recommendations'] = self.gap_exporter.generate_workload_recommendation_csv(analysis_results)
            logger.info("[OK] Enhanced gap analysis CSVs generated")
        except Exception as e:
            logger.warning(f"[WARN] Could not generate enhanced gap CSVs: {e}")
            
        return reports
    
    def generate_detailed_csv(self, analysis_results, sut_ip):
        """Generate detailed CSV with all events and their statistics."""
        import csv
        from datetime import datetime
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_filename = f"detailed_events_{timestamp}.csv"
        output_path = self.output_dir / csv_filename
        
        # Collect all events from all domains
        domain_results = analysis_results.get('coverage', {}).get('domain_results', {})
        
        with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = [
                'Domain', 'Event', 'Status', 'Total_Activity', 
                'Max_Core_Count', 'Min_Core_Count', 'Avg_Core_Count',
                'Active_Cores', 'Total_Cores', 'Samples'
            ]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for domain, data in domain_results.items():
                # Write active events
                for event in data.get('active_events', []):
                    writer.writerow({
                        'Domain': domain,
                        'Event': event.get('event', ''),
                        'Status': 'Active',
                        'Total_Activity': event.get('total_activity', 0),
                        'Max_Core_Count': event.get('max_core_count', 'N/A'),
                        'Min_Core_Count': event.get('min_core_count', 'N/A'),
                        'Avg_Core_Count': event.get('avg_core_count', 'N/A'),
                        'Active_Cores': event.get('active_cores', 'N/A'),
                        'Total_Cores': event.get('total_cores', 'N/A'),
                        'Samples': event.get('samples', 0)
                    })
                
                # Write inactive events
                for event in data.get('inactive_events', []):
                    status = event.get('status', 'inactive')
                    if status == 'event_not_exists':
                        status_text = 'Event Not Found'
                    elif status == 'not_found':
                        status_text = 'Not in Output'
                    elif status == 'no_file':
                        status_text = 'Collection Missing'
                    elif status == 'no_activity':
                        status_text = 'No Activity'
                    else:
                        status_text = 'Low Activity'
                    
                    writer.writerow({
                        'Domain': domain,
                        'Event': event.get('event', ''),
                        'Status': status_text,
                        'Total_Activity': event.get('total_activity', 0),
                        'Max_Core_Count': event.get('max_core_count', 'N/A'),
                        'Min_Core_Count': event.get('min_core_count', 'N/A'),
                        'Avg_Core_Count': event.get('avg_core_count', 'N/A'),
                        'Active_Cores': event.get('active_core_count', 'N/A'),
                        'Total_Cores': event.get('total_core_count', 'N/A'),
                        'Samples': event.get('samples', 0)
                    })
        
        # Copy to C drive backup location
        backup_path = self.backup_dir / csv_filename
        import shutil
        shutil.copy2(output_path, backup_path)
        
        print(f"\n[OK] Detailed CSV saved to: {output_path}")
        print(f"[OK] Backup saved to: {backup_path}")
        return output_path
    
    def generate_summary_csv(self, analysis_results, sut_ip):
        """Generate summary CSV with domain-level statistics."""
        import csv
        from datetime import datetime
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_filename = f"domain_summary_{timestamp}.csv"
        output_path = self.output_dir / csv_filename
        
        domain_results = analysis_results.get('coverage', {}).get('domain_results', {})
        
        with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = [
                'Domain', 'Total_Events', 'Active_Events', 'Inactive_Events',
                'Event_Not_Found', 'Collection_Missing', 'No_Activity', 'Low_Activity',
                'Coverage_Percentage', 'Status'
            ]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for domain, data in domain_results.items():
                total_tested = data.get('total_tested', 0)
                active_count = len(data.get('active_events', []))
                inactive_events = data.get('inactive_events', [])
                
                # Categorize inactive events
                event_not_found = sum(1 for e in inactive_events if e.get('status', '') in ['event_not_exists', 'not_found'])
                collection_missing = sum(1 for e in inactive_events if e.get('status', '') in ['no_file', 'collection_failed'])
                no_activity = sum(1 for e in inactive_events if e.get('status', '') == 'no_activity')
                low_activity = len(inactive_events) - event_not_found - collection_missing - no_activity
                
                coverage_pct = data.get('activity_rate', 0)
                
                # Determine status
                if coverage_pct >= 80:
                    status = 'Excellent'
                elif coverage_pct >= 50:
                    status = 'Good'
                elif coverage_pct >= 20:
                    status = 'Needs Improvement'
                else:
                    status = 'Critical'
                
                writer.writerow({
                    'Domain': domain,
                    'Total_Events': total_tested,
                    'Active_Events': active_count,
                    'Inactive_Events': len(inactive_events),
                    'Event_Not_Found': event_not_found,
                    'Collection_Missing': collection_missing,
                    'No_Activity': no_activity,
                    'Low_Activity': low_activity,
                    'Coverage_Percentage': f"{coverage_pct:.1f}%",
                    'Status': status
                })
        
        # Copy to C drive backup location
        backup_path = self.backup_dir / csv_filename
        import shutil
        shutil.copy2(output_path, backup_path)
        
        print(f"[OK] Summary CSV saved to: {output_path}")
        print(f"[OK] Backup saved to: {backup_path}")
        return output_path
    
    def _get_cumulative_coverage_stats(self, analysis_results, product_id):
        """Get cumulative coverage statistics across all historical runs."""
        from pathlib import Path
        import json
        
        coverage = analysis_results.get('coverage', {})
        domain_results = coverage.get('domain_results', {})
        
        total_covered = 0
        total_available = 0
        
        # Load historical data to calculate cumulative coverage
        all_events_by_domain = {}
        ever_toggled_by_domain = {}
        unavailable_events_by_domain = {}
        
        try:
            data_dir = Path(r'C:\silicon_coverage_analyzer_data')
            if product_id:
                product_dir = data_dir / 'raw_datasets' / product_id
                if product_dir.exists():
                    # Use ALL coverage files for cumulative stats, not just last 10
                    coverage_files = sorted(product_dir.glob('coverage_*.json'))
                    
                    for coverage_file in coverage_files:
                        try:
                            with open(coverage_file, 'r') as f:
                                hist_data = json.load(f)
                                hist_domains = hist_data.get('coverage_results', {}).get('domain_results', {})
                                if not hist_domains:
                                    hist_domains = hist_data.get('coverage', {}).get('domain_results', {})
                                
                                for domain, stats in hist_domains.items():
                                    if domain not in all_events_by_domain:
                                        all_events_by_domain[domain] = set()
                                        ever_toggled_by_domain[domain] = set()
                                        unavailable_events_by_domain[domain] = set()
                                    
                                    for evt in stats.get('active_events', []):
                                        event_name = evt.get('event', '') if isinstance(evt, dict) else str(evt)
                                        if event_name:
                                            all_events_by_domain[domain].add(event_name)
                                            ever_toggled_by_domain[domain].add(event_name)
                                    
                                    for evt in stats.get('inactive_events', []):
                                        event_name = evt.get('event', '') if isinstance(evt, dict) else str(evt)
                                        if event_name:
                                            all_events_by_domain[domain].add(event_name)
                        except Exception:
                            continue
                    
                    # Get unavailable events
                    gaps_data = analysis_results.get('gaps', {})
                    for gap_event in gaps_data.get('non_toggling_events', []):
                        domain = gap_event.get('domain', '')
                        category = gap_event.get('category', '')
                        reason = gap_event.get('reason', '')
                        
                        if category == 'Event_Unavailable' or reason in ['event_not_exists', 'not_found', 'not_supported']:
                            if domain not in unavailable_events_by_domain:
                                unavailable_events_by_domain[domain] = set()
                            event_name = gap_event.get('event_name', gap_event.get('event', ''))
                            if event_name:
                                unavailable_events_by_domain[domain].add(event_name)
        except Exception:
            pass
        
        # Calculate totals
        if all_events_by_domain:
            for domain in domain_results.keys():
                all_events = all_events_by_domain.get(domain, set())
                toggled_events = ever_toggled_by_domain.get(domain, set())
                unavailable = unavailable_events_by_domain.get(domain, set())
                
                available_events = all_events - unavailable
                covered_events = toggled_events & available_events
                
                total_available += len(available_events)
                total_covered += len(covered_events)
        else:
            # Fallback to current run data
            total_available = coverage.get('total_events_tested', 0)
            total_covered = coverage.get('active_events', 0)
        
        coverage_pct = (total_covered / total_available * 100) if total_available > 0 else 0
        
        return {
            'total_events': total_available,
            'covered_events': total_covered,
            'remaining_events': total_available - total_covered,
            'coverage_pct': coverage_pct
        }
    
