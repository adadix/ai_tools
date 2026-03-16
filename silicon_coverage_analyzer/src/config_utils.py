"""
Shared Configuration Utilities

Provides common config loading functions used across ML modules.
Eliminates code duplication for domain config access.
"""

import yaml
from pathlib import Path
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

# Cache for loaded config to avoid repeated file reads
_config_cache: Dict[str, Any] = {}


def get_config_path() -> Path:
    """Get the path to the config directory."""
    return Path(__file__).parent.parent / 'config'


def load_domain_config(force_reload: bool = False) -> Dict[str, Any]:
    """
    Load domain configuration from YAML file with caching.
    
    Args:
        force_reload: If True, bypass cache and reload from disk
        
    Returns:
        Domain configuration dictionary
    """
    global _config_cache
    
    cache_key = 'domain_config'
    if not force_reload and cache_key in _config_cache:
        return _config_cache[cache_key]
    
    config_path = get_config_path() / 'domain_config.yaml'
    try:
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
            _config_cache[cache_key] = config
            return config
    except Exception as e:
        logger.warning(f"Could not load domain_config.yaml: {e}")
        return {}


def get_ml_domains(model_name: str, default: Optional[List[str]] = None) -> List[str]:
    """
    Load domain list from config for a specific ML model.
    
    Args:
        model_name: Name of the ML model (e.g., 'workload_detector', 'workload_clusterer')
        default: Default domain list if not found in config
        
    Returns:
        List of domain names for the ML model
    """
    if default is None:
        default = ['p-core', 'e-core', 'uncore', 'imc', 'cbo']
    
    try:
        domain_config = load_domain_config()
        ml_domains = domain_config.get('ml_domain_lists', {})
        return ml_domains.get(model_name, default)
    except Exception:
        return default


def get_uncore_domains(default: Optional[List[str]] = None) -> List[str]:
    """
    Load uncore domain list from config.
    
    Args:
        default: Default uncore domains if not found in config
        
    Returns:
        List of uncore domain names
    """
    if default is None:
        default = ['imc', 'cbo', 'cha', 'm2m', 'uncore']
    
    try:
        domain_config = load_domain_config()
        return domain_config.get('uncore_domains', default)
    except Exception:
        return default


def get_critical_domains(default: Optional[List[str]] = None) -> List[str]:
    """
    Load critical domain list from config.
    
    Args:
        default: Default critical domains if not found in config
        
    Returns:
        List of critical domain names
    """
    if default is None:
        default = ['p-core', 'e-core', 'imc', 'cbo']
    
    try:
        domain_config = load_domain_config()
        return domain_config.get('critical_domains', default)
    except Exception:
        return default


def get_domain_colors() -> Dict[str, str]:
    """
    Load domain color mappings from config.
    
    Returns:
        Dictionary mapping domain names to hex colors
    """
    try:
        domain_config = load_domain_config()
        return domain_config.get('domain_colors', {})
    except Exception:
        return {}


def get_domain_priority() -> Dict[str, int]:
    """
    Load domain priority mappings from config.
    
    Returns:
        Dictionary mapping domain names to priority values
    """
    try:
        domain_config = load_domain_config()
        return domain_config.get('domain_priority', {})
    except Exception:
        return {}


def clear_config_cache():
    """Clear the configuration cache to force reload on next access."""
    global _config_cache
    _config_cache = {}
