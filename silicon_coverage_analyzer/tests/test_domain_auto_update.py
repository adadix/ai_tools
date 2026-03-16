#!/usr/bin/env python3
"""
Test Domain Configuration Auto-Update

Simulates discovering new domains and updating configuration.
"""

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent))

from src.domain_config_updater import DomainConfigUpdater

# Simulate discovered domains (mix of known and new)
discovered_domains = [
    # Known domains
    'p-core', 'e-core', 'imc', 'cbo', 'ncu',
    
    # New domains to test auto-configuration
    'xyz-core',      # Unknown core type
    'ddr5-mc',       # New memory controller
    'custom_cache',  # Custom cache unit
    'new_fabric',    # New interconnect
    'pcie_gen5'      # New I/O unit
]

# Domain metadata (would come from emon -M <domain>)
domain_metadata = {
    'xyz-core': {'unit_count': 8, 'description': 'Next-gen efficiency cores'},
    'ddr5-mc': {'unit_count': 2, 'description': 'DDR5 memory controller'},
    'custom_cache': {'unit_count': 12, 'description': 'Custom L3 cache slices'},
    'new_fabric': {'unit_count': 4, 'description': 'Next-gen interconnect'},
    'pcie_gen5': {'unit_count': 1, 'description': 'PCIe Gen5 root complex'}
}

print("=" * 80)
print("TESTING DOMAIN CONFIGURATION AUTO-UPDATE")
print("=" * 80)

# Create updater
updater = DomainConfigUpdater()

print(f"\nConfig file: {updater.config_path}")
print(f"Simulating discovery of {len(discovered_domains)} domains")
print(f"   Known: {len([d for d in discovered_domains if d in ['p-core', 'e-core', 'imc', 'cbo', 'ncu']])}")
print(f"   New: {len([d for d in discovered_domains if d not in ['p-core', 'e-core', 'imc', 'cbo', 'ncu']])}")

# Dry run first
print("\n" + "-" * 80)
print("DRY RUN (preview changes)")
print("-" * 80)

result = updater.update_from_discovered_domains(
    discovered_domains,
    domain_metadata,
    dry_run=True
)

if result['status'] == 'updated':
    print(f"\n[OK] Would add {result['new_count']} new domains:")
    for domain in result['new_domains']:
        print(f"   - {domain}")
    
    print(f"\nChanges preview:")
    for change in result['changes'][:10]:  # Show first 10
        print(f"   * {change}")
    
    if len(result['changes']) > 10:
        print(f"   ... and {len(result['changes']) - 10} more changes")
    
    # Ask to apply
    print("\n" + "-" * 80)
    response = input("Apply these changes? (y/n): ").strip().lower()
    
    if response == 'y':
        print("\nApplying changes...")
        
        # Create new updater for actual run
        updater2 = DomainConfigUpdater()
        result2 = updater2.update_from_discovered_domains(
            discovered_domains,
            domain_metadata,
            dry_run=False
        )
        
        updater2.print_summary(result2)
        
        print("\n[OK] Configuration updated successfully!")
        print(f"   Backup: {result2.get('backup_path', 'N/A')}")
        print(f"   Changes logged to: logs/domain_config_changes_*.log")
    else:
        print("\n[FAIL] Changes not applied (dry run only)")
else:
    print(f"\n[OK] {result['message']}")
    print(f"   All {result['existing_count']} domains already configured")

print("\n" + "=" * 80)
