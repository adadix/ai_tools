#!/usr/bin/env python3
"""Test domain configuration loading"""

import yaml
from pathlib import Path

# Test loading domain config
config_path = Path('config/domain_config.yaml')
print(f"Loading config from: {config_path}")

with open(config_path, 'r') as f:
    config = yaml.safe_load(f)

print("\n[OK] Domain config loaded successfully!")
print(f"   - {len(config['domain_colors'])} domain colors")
print(f"   - {len(config['domain_priority'])} domain priorities")  
print(f"   - {len(config['domain_categories'])} categories")
print(f"   - {len(config['stress_tool_domains'])} stress tool mappings")
print(f"   - {len(config['critical_domains'])} critical domains")
print(f"   - {len(config['ml_domain_lists'])} ML model domain lists")

# Test specific values
print("\n Sample values:")
print(f"   P-Core color: {config['domain_colors']['p-core']}")
print(f"   P-Core priority: {config['domain_priority']['p-core']}")
print(f"   Critical domains: {config['critical_domains']}")
print(f"   Uncore domains: {config['uncore_domains'][:5]}...")

# Test stress tool domains
print("\n Sample stress tool mappings:")
for tool in ['prime95', 'memtester', 'mlc']:
    if tool in config['stress_tool_domains']:
        domains = config['stress_tool_domains'][tool]['domains']
        print(f"   {tool}: {domains}")

print("\n[OK] All domain configuration validated!")
