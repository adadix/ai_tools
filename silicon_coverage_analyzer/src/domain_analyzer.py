#!/usr/bin/env python3
"""
Domain Analyzer Module

INTEL CONFIDENTIAL - INTERNAL USE ONLY

Analyzes PMU domains to discover available events and their characteristics.
"""

import re
from src.remote_transfer import RemoteTransfer

class DomainAnalyzer:
    """Analyzes PMU domains and their available events."""
    
    def __init__(self, sut_ip, config):
        self.sut_ip = sut_ip
        self.config = config
        
        # Create RemoteTransfer with credentials
        ssh_key_path = config.get('ssh_key_path')
        username = config.get('username')
        password = config.get('password')
        
        self.transfer = RemoteTransfer(
            sut_ip,
            username=username,
            password=password,
            ssh_key_path=ssh_key_path
        )
        
        self.os_type = config.get('os_type', 'windows')
        self.debug = config.get('debug', False)
        if self.debug:
            print(f"   [DEBUG] DomainAnalyzer os_type: {self.os_type}")
        
    def discover_domains(self):
        """Discover all available PMU domains with metadata."""
        cmd = self._wrap_emon_cmd("emon -pmu-types")
        if self.debug:
            print(f"   [DEBUG] Command: {cmd[:150]}")
        success, stdout, stderr = self.transfer.execute_command(cmd, timeout=30)
        if self.debug:
            print(f"   [DEBUG] Success: {success}, Stdout len: {len(stdout) if stdout else 0}, Stderr: {stderr[:100]}")
        
        if not success:
            raise Exception(f"Failed to discover domains: {stderr}")
        
        domains = []
        for line in stdout.split('\n'):
            line = line.strip()
            # Filter out environment variables and invalid domain names
            # Valid PMU domains are short names like: p-core, e-core, imc, cbo, ncu, power
            if (line and len(line) < 20 and any(char.isalpha() for char in line) 
                and line not in ['Types', 'supported', 'on', 'this', 'machine:'] 
                and not line.startswith('PMU')
                and '=' not in line  # Filter out env vars like LD_LIBRARY_PATH=
                and 'PATH' not in line.upper()  # Filter out any PATH-related lines
                and not line.startswith('/')  # Filter out file paths
                and not line.startswith('C_')  # Filter out C_INCLUDE_PATH etc
                and not line.startswith('CPLUS_')):  # Filter out CPLUS_INCLUDE_PATH
                domains.append(line)
        
        # Get metadata for each domain
        self.domain_metadata = {}
        for domain in domains:
            self.domain_metadata[domain] = self._get_domain_metadata(domain)
        
        return domains
    
    def _get_domain_metadata(self, domain):
        """
        Extract metadata about a domain from EMON.
        Returns: dict with 'unit_count', 'unit_type', 'description'
        """
        # Try to get domain info from emon -M <domain>
        cmd = self._wrap_emon_cmd(f"emon -M {domain}")
        success, stdout, stderr = self.transfer.execute_command(cmd, timeout=15)
        
        metadata = {
            'unit_count': 0,
            'unit_type': 'units',
            'description': '',
            'raw_output': stdout[:200] if stdout else ''  # Store raw output for debugging
        }
        
        if not success or not stdout:
            if self.debug:
                print(f"      [DEBUG] {domain}: No output from emon -M")
            return metadata
        
        # Parse output for patterns like:
        # "Number of <type>: X"
        # "X <type> detected"
        # "<domain> has X units"
        
        lines = stdout.lower()
        
        # Look for count patterns
        import re
        
        # Pattern: "number of X: Y" or "Y X" or "X: Y units"
        count_patterns = [
            r'(\d+)\s+(?:unit|counter|module|socket|package|core|cbo|cha|imc|mc)',
            r'number\s+of\s+\w+:\s*(\d+)',
            r'(\d+)\s+\w+\s+detected',
            r'unit\s+count:\s*(\d+)'
        ]
        
        for pattern in count_patterns:
            match = re.search(pattern, lines)
            if match:
                try:
                    metadata['unit_count'] = int(match.group(1))
                    if self.debug:
                        print(f"      [DEBUG] {domain}: Found {metadata['unit_count']} units via pattern")
                    break
                except:
                    pass
        
        # If still 0, show first line of output for debugging
        if self.debug and metadata['unit_count'] == 0 and stdout:
            first_lines = stdout.split('\n')[:3]
            print(f"      [DEBUG] {domain}: Count=0, Output: {' | '.join(first_lines)}")
        
        # Infer unit type from domain name
        domain_lower = domain.lower()
        if 'core' in domain_lower:
            metadata['unit_type'] = 'cores'
        elif any(x in domain_lower for x in ['imc', 'mc', 'memory']):
            metadata['unit_type'] = 'memory controllers'
        elif any(x in domain_lower for x in ['cbo', 'cha', 'cache']):
            metadata['unit_type'] = 'cache units'
        elif any(x in domain_lower for x in ['ncu', 'upi', 'mesh']):
            metadata['unit_type'] = 'non-coherent units'
        elif any(x in domain_lower for x in ['iio', 'pcie', 'bridge']):
            metadata['unit_type'] = 'I/O units'
        elif any(x in domain_lower for x in ['power', 'package', 'socket']):
            metadata['unit_type'] = 'packages'
        
        metadata['description'] = f"{domain} ({metadata['unit_count']} {metadata['unit_type']})"
        
        return metadata
    
    def _wrap_emon_cmd(self, emon_command):
        """Wrap emon command with environment setup for Linux."""
        if self.os_type == 'linux':
            # Dynamically find and source sep_vars.sh
            return f'''sep_vars=$(find /opt/intel -name "sep_vars.sh" -type f 2>/dev/null | head -1); if [ -n "$sep_vars" ]; then source "$sep_vars"; fi; {emon_command}'''
        else:
            return emon_command
    
    def analyze_domain_events(self, domain):
        """Analyze events available in a specific domain."""
        cmd = self._wrap_emon_cmd(f"emon -1 {domain}")
        success, stdout, stderr = self.transfer.execute_command(cmd, timeout=30)
        
        if not success:
            # Check if domain simply doesn't exist on this platform
            if stderr and ('not found' in stderr.lower() or 'does not exist' in stderr.lower() or 'no pmu' in stderr.lower()):
                print(f"      [INFO] {domain}: Not present on this platform")
            return {
                'domain': domain,
                'available': False,
                'error': stderr[:100] if stderr else 'No output',
                'events': [],
                'total_events': 0
            }
        
        # Parse events from output - one event per line
        events = []
        lines = stdout.split('\n')
        
        for line in lines:
            line = line.strip()
            
            # Skip empty lines, headers, and non-event lines
            if not line or any(keyword in line.lower() for keyword in 
                             ['version', 'usage', 'note', 'description', 'example', 'error', 
                              'intel', 'event', 'code', 'umask', 'supported', 'pmu']):
                continue
            
            # Valid event format: WORD.WORD or WORD_WORD (uppercase, with dots or underscores)
            # Must start at beginning of line (not in middle of sentence)
            if re.match(r'^[A-Z][A-Z0-9_]+(?:\.[A-Z0-9_]+)*$', line):
                # Additional validation: must have either a dot or be longer than 5 chars
                if '.' in line or len(line) > 5:
                    events.append(line)
        
        return {
            'domain': domain,
            'available': True,
            'events': events,
            'total_events': len(events),
            'sample_events': events[:10]  # First 10 for reference
        }
    
    def analyze_all_domains(self):
        """Analyze all discovered domains."""
        domains = self.discover_domains()
        
        # Filter domains if specified in config
        if (self.config.get('domains_to_analyze') != 'all' and 
            isinstance(self.config.get('domains_to_analyze'), list)):
            domains = [d for d in domains if d in self.config['domains_to_analyze']]
        
        domain_results = {}
        
        for i, domain in enumerate(domains, 1):
            print(f"   [{i}/{len(domains)}] Analyzing {domain}...")
            
            try:
                result = self.analyze_domain_events(domain)
                domain_results[domain] = result
                
                if result['available']:
                    print(f"      [OK] {result['total_events']} events found")
                else:
                    print(f"      [FAIL] Not available")
                    
            except Exception as e:
                print(f"      [FAIL] Error: {e}")
                domain_results[domain] = {
                    'domain': domain,
                    'available': False,
                    'error': str(e),
                    'events': [],
                    'total_events': 0
                }
        
        return domain_results