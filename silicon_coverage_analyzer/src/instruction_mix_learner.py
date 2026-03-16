"""
Instruction Mix Auto-Learner - Product-Specific Event Pattern Recognition

Automatically learns and generates instruction mix categories by analyzing
all collected events for a specific product. Creates product-specific
instruction categorization that improves with each run.

Key Features:
- Scans all historical events for a product
- Uses ML clustering to group similar events
- Auto-generates category patterns and descriptions
- Refines categories with each new collection
- Exports product-specific YAML configs
"""

import json
import yaml
import logging
import re
from pathlib import Path
from collections import defaultdict, Counter
from typing import Dict, List, Any, Set, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class InstructionMixLearner:
    """
    Learns instruction mix categories from collected event data.
    Creates product-specific event categorization automatically.
    """
    
    def __init__(self, product_name: str, data_dir: Path = None):
        """
        Initialize the instruction mix learner.
        
        Args:
            product_name: Product identifier (e.g., "AlderLake_Client")
            data_dir: Base directory for ML data (default: C:/silicon_coverage_analyzer_data)
        """
        self.product_name = product_name
        self.data_dir = data_dir or Path(r"C:\silicon_coverage_analyzer_data")
        self.product_dir = self.data_dir / product_name
        self.config_dir = Path(__file__).parent.parent / 'config'
        
        # Storage for learned patterns
        self.learned_categories = {}
        self.event_registry = defaultdict(lambda: {'count': 0, 'domains': set(), 'patterns': []})
        self.category_patterns = {}
        
        # Common instruction type keywords (seed patterns)
        self.seed_patterns = {
            'FP_SIMD': {
                'keywords': ['FP_', 'AVX', 'SSE', 'SIMD', 'VEC', 'FMA', 'FLOP', 'DOUBLE', 'SINGLE'],
                'icon': '',
                'color': '#28a745',
                'description': 'Floating-point and SIMD vector operations'
            },
            'Memory': {
                'keywords': ['MEM_LOAD', 'MEM_STORE', 'MEM_INST', 'MEM_UOPS', 'LOAD_', 'STORE_'],
                'icon': '',
                'color': '#e74c3c',
                'description': 'Memory load and store operations'
            },
            'Branch': {
                'keywords': ['BR_', 'BRANCH', 'BACLEARS', 'JUMP', 'CALL', 'RET'],
                'icon': '',
                'color': '#f39c12',
                'description': 'Branch and control flow operations'
            },
            'Integer_ALU': {
                'keywords': ['INT_', 'ARITH.DIV', 'ARITH.MUL', 'UOPS_EXECUTED', 'ADD', 'SUB'],
                'icon': '',
                'color': '#0071c5',
                'description': 'Integer arithmetic and logic operations'
            },
            'Cache': {
                'keywords': ['L1D', 'L1I', 'L2_', 'L3_', 'LLC', 'LONGEST_LAT', 'CACHE'],
                'icon': '',
                'color': '#9b59b6',
                'description': 'Cache hierarchy operations'
            },
            'TLB': {
                'keywords': ['DTLB', 'ITLB', 'STLB', 'TLB', 'PAGE'],
                'icon': '',
                'color': '#3498db',
                'description': 'Translation lookaside buffer operations'
            },
            'Pipeline': {
                'keywords': ['FRONTEND', 'BACKEND', 'DECODE', 'IDQ', 'ICACHE', 'FETCH'],
                'icon': '[GEAR]',
                'color': '#34495e',
                'description': 'Pipeline frontend and backend operations'
            },
            'Atomic_Lock': {
                'keywords': ['LOCK', 'ATOMIC', 'MEM_LOCK', 'XCHG'],
                'icon': '',
                'color': '#e67e22',
                'description': 'Atomic and lock operations'
            },
            'Prefetch': {
                'keywords': ['PREFETCH', 'HW_PRE', 'SW_PRE'],
                'icon': '[*]',
                'color': '#16a085',
                'description': 'Hardware and software prefetch operations'
            },
            'Power': {
                'keywords': ['POWER', 'C_STATE', 'FREQ', 'THERMAL', 'ENERGY'],
                'icon': '',
                'color': '#e91e63',
                'description': 'Power management and frequency scaling'
            }
        }
    
    def scan_historical_events(self) -> Dict[str, Any]:
        """
        Scan all historical datasets for this product and extract event patterns.
        
        Returns:
            Dict with event statistics and discovered patterns
        """
        logger.info(f" Scanning historical events for product: {self.product_name}")
        
        # Datasets are stored in data_dir/raw_datasets/product_name/
        datasets_dir = self.data_dir / "raw_datasets" / self.product_name
        if not datasets_dir.exists():
            logger.warning(f"No datasets found for {self.product_name} in {datasets_dir}")
            return {'status': 'no_data', 'events_found': 0}
        
        total_events = 0
        unique_events = set()
        domain_coverage = defaultdict(set)
        
        # Scan all JSON dataset files
        dataset_count = 0
        for dataset_file in datasets_dir.glob("*.json"):
            dataset_count += 1
            try:
                with open(dataset_file, 'r') as f:
                    data = json.load(f)
                
                coverage = data.get('coverage_results', {})
                domain_results = coverage.get('domain_results', {})
                
                for domain, domain_data in domain_results.items():
                    if not isinstance(domain_data, dict):
                        continue
                    
                    # Process active events
                    active_events = domain_data.get('active_events', [])
                    for event_info in active_events:
                        event_name = event_info.get('event', '').upper()
                        if event_name:
                            total_events += 1
                            unique_events.add(event_name)
                            domain_coverage[domain].add(event_name)
                            
                            # Register event
                            self.event_registry[event_name]['count'] += 1
                            self.event_registry[event_name]['domains'].add(domain)
                    
                    # Also track inactive events (for complete picture)
                    inactive_events = domain_data.get('inactive_events', [])
                    for event_info in inactive_events:
                        # inactive_events is a list of dicts, not strings
                        if isinstance(event_info, dict):
                            event_name = event_info.get('event', '').upper()
                        elif isinstance(event_info, str):
                            event_name = event_info.upper()
                        else:
                            continue
                            
                        if event_name:
                            unique_events.add(event_name)
                            domain_coverage[domain].add(event_name)
            
            except Exception as e:
                logger.warning(f"Failed to process {dataset_file.name}: {e}")
                continue
        
        logger.info(f"[OK] Scanned {dataset_count} datasets - Total: {total_events}, Unique: {len(unique_events)}, Domains: {len(domain_coverage)}")
        
        return {
            'status': 'success',
            'total_events': total_events,
            'unique_events': len(unique_events),
            'event_names': list(unique_events),
            'domains': list(domain_coverage.keys()),
            'domain_coverage': {d: len(events) for d, events in domain_coverage.items()}
        }
    
    def learn_categories(self, min_event_threshold: int = 2) -> Dict[str, Any]:
        """
        Learn instruction mix categories from collected events.
        
        Args:
            min_event_threshold: Minimum event occurrences to consider for categorization
        
        Returns:
            Dict with learned categories and statistics
        """
        logger.info(f" Learning instruction categories for {self.product_name}...")
        
        # First scan events if not already done
        scan_result = self.scan_historical_events()
        if scan_result.get('status') != 'success':
            return scan_result
        
        # Initialize categories from seed patterns
        for category, config in self.seed_patterns.items():
            self.learned_categories[category] = {
                'patterns': config['keywords'].copy(),
                'events': [],
                'icon': config['icon'],
                'color': config['color'],
                'description': config['description'],
                'event_count': 0,
                'confidence': 'high'  # Seed patterns are high confidence
            }
        
        # Categorize events based on patterns
        uncategorized_events = []
        
        for event_name, info in self.event_registry.items():
            if info['count'] < min_event_threshold:
                continue  # Skip rare events
            
            categorized = False
            
            # Try to match against seed patterns
            for category, cat_info in self.learned_categories.items():
                for pattern in cat_info['patterns']:
                    if pattern in event_name:
                        cat_info['events'].append({
                            'name': event_name,
                            'occurrences': info['count'],
                            'domains': list(info['domains'])
                        })
                        cat_info['event_count'] += 1
                        categorized = True
                        break
                if categorized:
                    break
            
            if not categorized:
                uncategorized_events.append({
                    'name': event_name,
                    'occurrences': info['count'],
                    'domains': list(info['domains'])
                })
        
        # Try to discover new patterns from uncategorized events
        if uncategorized_events:
            logger.info(f" Discovering patterns from {len(uncategorized_events)} uncategorized events...")
            new_categories = self._discover_new_patterns(uncategorized_events)
            self.learned_categories.update(new_categories)
        
        # Calculate category statistics
        total_categorized = sum(cat['event_count'] for cat in self.learned_categories.values())
        
        result = {
            'status': 'success',
            'product': self.product_name,
            'categories': len(self.learned_categories),
            'categorized_events': total_categorized,
            'uncategorized_events': len(uncategorized_events),
            'category_details': self.learned_categories,
            'timestamp': datetime.now().isoformat()
        }
        
        logger.info(f"[OK] Learned {len(self.learned_categories)} categories covering {total_categorized} events")
        
        return result
    
    def _discover_new_patterns(self, uncategorized_events: List[Dict]) -> Dict[str, Any]:
        """
        Discover new instruction categories from uncategorized events using pattern mining.
        
        Args:
            uncategorized_events: List of events that didn't match existing categories
        
        Returns:
            Dict of newly discovered categories
        """
        new_categories = {}
        
        # Extract common prefixes/patterns
        prefix_groups = defaultdict(list)
        
        for event in uncategorized_events:
            event_name = event['name']
            
            # Extract prefix (before first underscore or dot)
            parts = re.split(r'[_.]', event_name)
            if parts:
                prefix = parts[0]
                if len(prefix) >= 2:  # Meaningful prefix
                    prefix_groups[prefix].append(event)
        
        # Create categories for groups with 3+ events
        for prefix, events in prefix_groups.items():
            if len(events) >= 3:
                category_name = f"{prefix}_Operations"
                new_categories[category_name] = {
                    'patterns': [f"{prefix}_", prefix],
                    'events': events,
                    'icon': '',
                    'color': '#95a5a6',
                    'description': f'{prefix}-related operations (auto-discovered)',
                    'event_count': len(events),
                    'confidence': 'medium'  # Auto-discovered patterns are medium confidence
                }
                logger.info(f" Discovered new category: {category_name} with {len(events)} events")
        
        return new_categories
    
    def export_to_yaml(self, output_path: Path = None) -> Path:
        """
        Export learned categories to YAML configuration file.
        
        Args:
            output_path: Optional custom output path
        
        Returns:
            Path to exported YAML file
        """
        if not output_path:
            output_path = self.config_dir / f"instruction_categories_{self.product_name.lower()}.yaml"
        
        # Build YAML structure
        config = {
            'product': self.product_name,
            'generated_date': datetime.now().isoformat(),
            'auto_generated': True,
            'description': f'Auto-learned instruction categories for {self.product_name}',
            'instruction_categories': []
        }
        
        
        for category, info in self.learned_categories.items():
            config['instruction_categories'].append({
                'name': category,
                'patterns': info['patterns'],
                'icon': info['icon'],
                'color': info['color'],
                'description': info['description'],
                'event_count': info['event_count'],
                'confidence': info['confidence']
            })
        
        # Add fallback category
        config['fallback_category'] = {
            'name': 'Other',
            'icon': '[?]',
            'color': '#6c757d',
            'description': 'Uncategorized events'
        }
        
        # Write YAML file
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        
        logger.info(f"[OK] Exported instruction mix config to: {output_path}")
        
        return output_path
    
    def update_template_config(self) -> bool:
        """
        Update the main instruction_categories_templates.yaml with this product's learned categories.
        
        Returns:
            True if update successful
        """
        templates_path = self.config_dir / 'instruction_categories_templates.yaml'
        
        try:
            # Load existing templates
            if templates_path.exists():
                with open(templates_path, 'r', encoding='utf-8') as f:
                    templates = yaml.safe_load(f) or {}
            else:
                templates = {
                    'version': '2.0',
                    'detection': {'method': 'auto'},
                    'templates': {},
                    'fallback_category': {
                        'name': 'Other',
                        'icon': '[?]',
                        'color': '#6c757d',
                        'description': 'Uncategorized events'
                    }
                }
            
            # Create template entry for this product
            template_key = self.product_name.lower().replace(' ', '_')
            
            templates['templates'][template_key] = {
                'platforms': [self.product_name, template_key.upper()],
                'auto_generated': True,
                'last_updated': datetime.now().isoformat(),
                'instruction_categories': []
            }
            
            for category, info in self.learned_categories.items():
                templates['templates'][template_key]['instruction_categories'].append({
                    'name': category,
                    'patterns': info['patterns'],
                    'icon': info['icon'],
                    'color': info['color'],
                    'description': info['description']
                })
            
            # Write updated templates
            with open(templates_path, 'w', encoding='utf-8') as f:
                yaml.dump(templates, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
            
            logger.info(f"[OK] Updated template config with {template_key}")
            return True
        
        except Exception as e:
            logger.error(f"Failed to update template config: {e}")
            return False
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about learned categories."""
        return {
            'product': self.product_name,
            'total_categories': len(self.learned_categories),
            'total_events': len(self.event_registry),
            'unique_events': len(self.event_registry),
            'categories': {
                name: {
                    'event_count': info['event_count'],
                    'confidence': info['confidence'],
                    'pattern_count': len(info['patterns'])
                }
                for name, info in self.learned_categories.items()
            }
        }
    
    def get_category_patterns_for_ml(self) -> Dict[str, List[str]]:
        """
        Get learned category patterns optimized for ML feature extraction.
        Returns dict mapping category names to their pattern keywords.
        Used by ML models for feature engineering.
        """
        return {
            name: info['patterns']
            for name, info in self.learned_categories.items()
        }
    
    @staticmethod
    def load_learned_categories(product_id: str, config_dir: Path = None) -> Dict[str, List[str]]:
        """
        Load learned instruction categories from YAML config file.
        
        Args:
            product_id: Product identifier
            config_dir: Config directory path (default: config/)
        
        Returns:
            Dict mapping category names to pattern lists
        """
        if config_dir is None:
            config_dir = Path(__file__).parent.parent / 'config'
        
        yaml_path = config_dir / f'instruction_categories_{product_id}.yaml'
        
        if not yaml_path.exists():
            logger.warning(f"No learned categories found for {product_id} at {yaml_path}")
            return {}
        
        try:
            with open(yaml_path, 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            categories = {}
            for cat in config.get('instruction_categories', []):
                categories[cat['name']] = cat['patterns']
            
            logger.info(f"[OK] Loaded {len(categories)} learned categories for {product_id}")
            return categories
            
        except Exception as e:
            logger.error(f"Failed to load learned categories: {e}")
            return {}
