#!/usr/bin/env python3
"""
Domain Configuration Auto-Updater

Automatically discovers PMU domains from EMON and updates domain_config.yaml
with new domains, assigning default colors, priorities, and categories based
on naming patterns.

INTEL CONFIDENTIAL - INTERNAL USE ONLY

Author: Intel Corporation
Date: December 2025
"""

import yaml
import re
import logging
from pathlib import Path
from typing import Dict, List, Set, Tuple, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class DomainConfigUpdater:
    """Automatically updates domain configuration based on discovered domains."""
    
    # Color palette for auto-assignment (cycles through these)
    COLOR_PALETTE = [
        '#0071C5', '#f39c12', '#27ae60', '#8e44ad', '#e74c3c',
        '#16a085', '#d35400', '#2c3e50', '#e91e63', '#3f51b5',
        '#00bcd4', '#9c27b0', '#ff5722', '#4caf50', '#607d8b',
        '#ff9800', '#795548', '#9e9e9e', '#ffc107', '#cddc39'
    ]
    
    def __init__(self, config_path: Path = None):
        """Initialize domain config updater."""
        if config_path is None:
            config_path = Path(__file__).parent.parent / 'config' / 'domain_config.yaml'
        
        self.config_path = config_path
        self.config = self._load_config()
        self.backup_path = None
        self.changes_made = []
    
    def _load_config(self) -> Dict[str, Any]:
        """Load existing domain configuration."""
        try:
            with open(self.config_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.warning(f"Could not load domain config: {e}")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Get minimal default configuration."""
        return {
            'domain_colors': {},
            'domain_priority': {},
            'domain_categories': {},
            'critical_domains': [],
            'ml_domain_lists': {},
            'uncore_domains': [],
            'stress_tool_domains': {},
            'recommendations': {},
            'architectures': {}
        }
    
    def update_from_discovered_domains(self, discovered_domains: List[str], 
                                       domain_metadata: Dict[str, Any] = None,
                                       dry_run: bool = False) -> Dict[str, Any]:
        """
        Update domain configuration with newly discovered domains.
        
        Args:
            discovered_domains: List of domain names from emon -pmu-types
            domain_metadata: Optional metadata about domains (unit counts, etc.)
            dry_run: If True, don't save changes, just return what would be changed
            
        Returns:
            dict: Summary of changes made
        """
        if domain_metadata is None:
            domain_metadata = {}
        
        # Create backup before making changes
        if not dry_run:
            self._create_backup()
        
        existing_domains = set(self.config.get('domain_colors', {}).keys())
        new_domains = set(discovered_domains) - existing_domains
        
        if not new_domains:
            return {
                'status': 'no_changes',
                'message': 'All discovered domains already configured',
                'existing_count': len(existing_domains),
                'new_count': 0
            }
        
        logger.info(f"Found {len(new_domains)} new domains to configure")
        
        # Add each new domain
        for domain in sorted(new_domains):
            self._add_domain(domain, domain_metadata.get(domain, {}))
        
        # Save changes
        if not dry_run:
            self._save_config()
            self._log_changes()
        
        return {
            'status': 'updated',
            'message': f'Added {len(new_domains)} new domains to configuration',
            'existing_count': len(existing_domains),
            'new_count': len(new_domains),
            'new_domains': sorted(list(new_domains)),
            'changes': self.changes_made,
            'backup_path': str(self.backup_path) if self.backup_path else None,
            'dry_run': dry_run
        }
    
    def _add_domain(self, domain: str, metadata: Dict[str, Any]):
        """Add a new domain to configuration with smart defaults."""
        domain_lower = domain.lower()
        
        # Categorize domain
        category, priority = self._categorize_domain(domain_lower, metadata)
        
        # Assign color
        color = self._assign_color(domain_lower)
        
        # Add to domain_colors
        if 'domain_colors' not in self.config:
            self.config['domain_colors'] = {}
        self.config['domain_colors'][domain] = color
        self.changes_made.append(f"Added domain_colors[{domain}] = {color}")
        
        # Add to domain_priority
        if 'domain_priority' not in self.config:
            self.config['domain_priority'] = {}
        self.config['domain_priority'][domain] = priority
        self.changes_made.append(f"Added domain_priority[{domain}] = {priority}")
        
        # Add to appropriate category
        if category:
            if 'domain_categories' not in self.config:
                self.config['domain_categories'] = {}
            if category not in self.config['domain_categories']:
                self.config['domain_categories'][category] = {
                    'description': f'Auto-created category for {category}',
                    'domains': [],
                    'patterns': []
                }
            
            if domain not in self.config['domain_categories'][category]['domains']:
                self.config['domain_categories'][category]['domains'].append(domain)
                self.changes_made.append(f"Added {domain} to category {category}")
        
        # Add to uncore_domains if it's uncore
        if category in ['memory_subsystem', 'cache_coherency', 'interconnect', 'uncore_general']:
            if 'uncore_domains' not in self.config:
                self.config['uncore_domains'] = []
            if domain not in self.config['uncore_domains']:
                self.config['uncore_domains'].append(domain)
                self.changes_made.append(f"Added {domain} to uncore_domains")
        
        # Add to critical_domains if high priority
        if priority == 3:
            if 'critical_domains' not in self.config:
                self.config['critical_domains'] = []
            if domain not in self.config['critical_domains']:
                self.config['critical_domains'].append(domain)
                self.changes_made.append(f"Added {domain} to critical_domains")
        
        # Add to ML domain lists
        self._add_to_ml_lists(domain, category, priority)
        
        logger.info(f"Configured new domain: {domain} (category={category}, priority={priority}, color={color})")
    
    def _categorize_domain(self, domain: str, metadata: Dict[str, Any]) -> Tuple[str, int]:
        """
        Categorize domain based on name and metadata.
        
        Returns:
            (category_name, priority_level)
        """
        # Core domains - Priority 3
        if any(x in domain for x in ['core', 'atom', 'cpu']):
            if 'p-core' in domain or 'p_core' in domain:
                return 'cpu_cores', 3
            elif 'e-core' in domain or 'e_core' in domain:
                return 'cpu_cores', 2
            elif 'lp' in domain or 'low' in domain:
                return 'cpu_cores', 2
            else:
                return 'cpu_cores', 3
        
        # Memory subsystem - Priority 3
        if any(x in domain for x in ['imc', 'mc', 'memory', 'm2m', 'hbm', 'ddr', 'dram']):
            return 'memory_subsystem', 3
        
        # Cache coherency - Priority 2
        if any(x in domain for x in ['cbo', 'cha', 'llc', 'cache', 'l3', 'l2']):
            return 'cache_coherency', 2
        
        # Interconnect - Priority 2
        if any(x in domain for x in ['ncu', 'upi', 'qpi', 'mesh', 'm3upi', 'fabric', 'link']):
            return 'interconnect', 2
        
        # I/O subsystem - Priority 1
        if any(x in domain for x in ['iio', 'pcie', 'pci', 'ufi', 'bridge', 'io']):
            return 'io_subsystem', 1
        
        # Power management - Priority 1
        if any(x in domain for x in ['power', 'pcu', 'energy', 'freq', 'volt']):
            return 'power_management', 1
        
        # Uncore general - Priority 2
        if 'uncore' in domain or 'offcore' in domain:
            return 'uncore_general', 2
        
        # Default: uncore_general, medium priority
        return 'uncore_general', 2
    
    def _assign_color(self, domain: str) -> str:
        """Assign color based on domain type with fallback to palette."""
        # Known color mappings
        color_map = {
            'p-core': '#0071C5', 'p_core': '#0071C5',
            'e-core': '#f39c12', 'e_core': '#f39c12',
            'atom': '#ff9800',
            'imc': '#27ae60', 'mc': '#27ae60',
            'cbo': '#8e44ad', 'cha': '#e91e63',
            'ncu': '#16a085',
            'upi': '#9c27b0', 'qpi': '#2c3e50',
            'power': '#e74c3c', 'pcu': '#e74c3c',
            'uncore': '#388e3c', 'offcore': '#f57c00'
        }
        
        # Check exact match
        if domain in color_map:
            return color_map[domain]
        
        # Check substring match
        for pattern, color in color_map.items():
            if pattern in domain:
                return color
        
        # Assign from palette based on hash
        existing_colors = set(self.config.get('domain_colors', {}).values())
        for color in self.COLOR_PALETTE:
            if color not in existing_colors:
                return color
        
        # Fallback: cycle through palette
        idx = len(self.config.get('domain_colors', {})) % len(self.COLOR_PALETTE)
        return self.COLOR_PALETTE[idx]
    
    def _add_to_ml_lists(self, domain: str, category: str, priority: int):
        """Add domain to appropriate ML model domain lists."""
        if 'ml_domain_lists' not in self.config:
            self.config['ml_domain_lists'] = {
                'workload_detector': [],
                'workload_clusterer': [],
                'anomaly_detector': [],
                'action_prioritizer': []
            }
        
        # Add to workload_detector if core or memory
        if category in ['cpu_cores', 'memory_subsystem', 'cache_coherency']:
            if domain not in self.config['ml_domain_lists']['workload_detector']:
                self.config['ml_domain_lists']['workload_detector'].append(domain)
                self.changes_made.append(f"Added {domain} to ML workload_detector")
        
        # Add to workload_clusterer if core
        if category == 'cpu_cores':
            if domain not in self.config['ml_domain_lists']['workload_clusterer']:
                self.config['ml_domain_lists']['workload_clusterer'].append(domain)
                self.changes_made.append(f"Added {domain} to ML workload_clusterer")
        
        # Add to anomaly_detector if priority 2 or 3
        if priority >= 2:
            if domain not in self.config['ml_domain_lists']['anomaly_detector']:
                self.config['ml_domain_lists']['anomaly_detector'].append(domain)
                self.changes_made.append(f"Added {domain} to ML anomaly_detector")
        
        # Add to action_prioritizer if critical
        if priority == 3:
            if domain not in self.config['ml_domain_lists']['action_prioritizer']:
                self.config['ml_domain_lists']['action_prioritizer'].append(domain)
                self.changes_made.append(f"Added {domain} to ML action_prioritizer")
    
    def _create_backup(self):
        """Create timestamped backup of config file."""
        if not self.config_path.exists():
            return
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        self.backup_path = self.config_path.parent / f"domain_config_backup_{timestamp}.yaml"
        
        try:
            import shutil
            shutil.copy2(self.config_path, self.backup_path)
            logger.info(f"Created backup: {self.backup_path}")
        except Exception as e:
            logger.warning(f"Could not create backup: {e}")
            self.backup_path = None
    
    def _save_config(self):
        """Save updated configuration to file."""
        try:
            with open(self.config_path, 'w') as f:
                yaml.dump(self.config, f, default_flow_style=False, sort_keys=False, indent=2)
            logger.info(f"Saved updated configuration to {self.config_path}")
        except Exception as e:
            logger.error(f"Failed to save configuration: {e}")
            raise
    
    def _log_changes(self):
        """Log all changes to a separate file."""
        log_dir = self.config_path.parent.parent / 'logs'
        log_dir.mkdir(exist_ok=True)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        log_path = log_dir / f"domain_config_changes_{timestamp}.log"
        
        try:
            with open(log_path, 'w') as f:
                f.write(f"Domain Configuration Auto-Update\n")
                f.write(f"Timestamp: {datetime.now().isoformat()}\n")
                f.write(f"Config File: {self.config_path}\n")
                f.write(f"Backup: {self.backup_path}\n")
                f.write(f"\nChanges Made ({len(self.changes_made)}):\n")
                f.write("=" * 80 + "\n")
                for change in self.changes_made:
                    f.write(f"  - {change}\n")
            
            logger.info(f"Logged changes to {log_path}")
        except Exception as e:
            logger.warning(f"Could not write change log: {e}")
    
    def print_summary(self, result: Dict[str, Any]):
        """Print formatted summary of configuration update."""
        print("\n" + "=" * 80)
        print("DOMAIN CONFIGURATION AUTO-UPDATE")
        print("=" * 80)
        
        if result['status'] == 'no_changes':
            print(f"[OK] {result['message']}")
            print(f"   Configured domains: {result['existing_count']}")
        else:
            print(f"[OK] {result['message']}")
            print(f"   Previously configured: {result['existing_count']}")
            print(f"   Newly added: {result['new_count']}")
            
            if result.get('new_domains'):
                print(f"\n   New domains added:")
                for domain in result['new_domains']:
                    print(f"      - {domain}")
            
            if result.get('backup_path'):
                print(f"\n   Backup saved: {result['backup_path']}")
            
            if result.get('dry_run'):
                print(f"\n   [WARN]  DRY RUN - No changes saved")
        
        print("=" * 80 + "\n")
