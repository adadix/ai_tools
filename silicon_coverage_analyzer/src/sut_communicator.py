"""
SUT IP Discovery Module

INTEL CONFIDENTIAL - INTERNAL USE ONLY

This module integrates VF Curve Manager SUT IP discovery and ping functionality
directly into the Silicon Coverage Analyzer.

Author: Intel Corporation
Date: November 2025
"""

import logging
import socket
import subprocess
import time
import os
import platform
import yaml
from typing import Optional, Dict, Any
from pathlib import Path

logger = logging.getLogger(__name__)


def get_sut_ip_from_itp():
    """
    Get SUT IP from ITP communicator configuration.
    Integrated from VF Curve Manager hardware_access.py
    
    Returns:
        str: SUT IP address or None if not found
    """
    try:
        # Try CommunicatorConfig first
        try:
            from evtar.services.communicator.config._ux import CommunicatorConfig
            CommunicatorConfig.Reload()
            target_ip = CommunicatorConfig.Target.DefaultPeer2PeerIP
            if target_ip:
                print(f"[NETWORK] Found SUT IP from CommunicatorConfig: {target_ip}")
                return target_ip
        except (ImportError, Exception):
            pass
        
        # Try to access ITP instance if available
        try:
            # Check if ITP is available in global namespace (from namednodes import)
            import sys
            if hasattr(sys.modules.get('__main__', {}), 'itp'):
                itp = getattr(sys.modules['__main__'], 'itp')
                
                # Try itpii module attributes
                if hasattr(itp, 'communicator') and hasattr(itp.communicator, 'target_ip'):
                    target_ip = itp.communicator.target_ip
                    if target_ip:
                        print(f"[NETWORK] Found SUT IP from ITP communicator: {target_ip}")
                        return target_ip
                elif hasattr(itp, 'target_ip'):
                    target_ip = itp.target_ip
                    if target_ip:
                        print(f"[NETWORK] Found SUT IP from ITP target_ip: {target_ip}")
                        return target_ip
                elif hasattr(itp, 'get_target_ip'):
                    target_ip = itp.get_target_ip()
                    if target_ip:
                        print(f"[NETWORK] Found SUT IP from ITP get_target_ip(): {target_ip}")
                        return target_ip
        except Exception:
            pass
        
        # Check environment variables
        sut_ip = os.environ.get('SUT_IP') or os.environ.get('TARGET_IP') or os.environ.get('ITP_TARGET')
        if sut_ip:
            print(f"[NETWORK] Found SUT IP from environment: {sut_ip}")
            return sut_ip
        
        print("[INFO] Unable to detect SUT IP from ITP communicator")
        return None
        
    except Exception as e:
        print(f"[WARNING] Error getting SUT IP from ITP: {e}")
        return None


def ping_sut(ip, timeout_seconds=2):
    """
    Ping SUT to check if it's reachable.
    Integrated from VF Curve Manager hardware_access.py
    
    Args:
        ip: IP address to ping
        timeout_seconds: Ping timeout in seconds
        
    Returns:
        bool: True if ping successful, False otherwise
    """
    try:
        if platform.system().lower() == "windows":
            cmd = ["ping", "-n", "1", "-w", str(timeout_seconds * 1000), ip]
        else:
            cmd = ["ping", "-c", "1", "-W", str(timeout_seconds), ip]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_seconds + 1)
        return result.returncode == 0
    except (subprocess.TimeoutExpired, Exception):
        return False


class SUTCommunicator:
    """
    Handles SUT (System Under Test) IP discovery and basic connectivity.
    Integrates with VF Curve Manager communicator function.
    """
    
    def __init__(self):
        """Initialize SUT Communicator."""
        self.sut_ip: Optional[str] = None
        self.connection_validated = False
        self.stress_tools_config = None
        logger.info("Initializing SUT Communicator")
        
        # Load stress tools configuration
        self._load_stress_tools_config()
    
    def _load_stress_tools_config(self):
        """Load stress tools configuration from YAML file."""
        try:
            config_path = Path(__file__).parent.parent / 'config' / 'stress_tools.yaml'
            if config_path.exists():
                with open(config_path, 'r') as f:
                    self.stress_tools_config = yaml.safe_load(f)
                logger.debug("Loaded stress tools configuration")
            else:
                logger.warning(f"Stress tools config not found: {config_path}")
                self.stress_tools_config = None
        except Exception as e:
            logger.warning(f"Error loading stress tools config: {e}")
            self.stress_tools_config = None
    
    def discover_sut_ip(self) -> Optional[str]:
        """
        Discover SUT IP using integrated VF Curve Manager functionality.
        
        Returns:
            str: SUT IP address if found, None otherwise
        """
        try:
            logger.info("Attempting to discover SUT IP via ITP communicator...")
            
            # Method 1: Use integrated VF Curve Manager SUT IP discovery
            sut_ip = get_sut_ip_from_itp()
            if sut_ip:
                logger.info(f"Found SUT IP via ITP communicator: {sut_ip}")
                
                # Verify connectivity using integrated ping function
                if ping_sut(sut_ip, timeout_seconds=3):
                    logger.info(f"Confirmed SUT connectivity: {sut_ip}")
                    self.sut_ip = sut_ip
                    return sut_ip
                else:
                    logger.warning(f"ITP found SUT IP {sut_ip} but ping failed")
                    # Continue to fallback methods
            else:
                logger.info("ITP communicator could not determine SUT IP, trying fallback methods")
            
            # Method 2: Check environment variable
            sut_ip = os.environ.get('SUT_IP') or os.environ.get('TARGET_IP') or os.environ.get('ITP_TARGET')
            if sut_ip:
                logger.info(f"Found SUT IP in environment: {sut_ip}")
                if ping_sut(sut_ip, timeout_seconds=3):
                    self.sut_ip = sut_ip
                    return sut_ip
                else:
                    logger.warning(f"Environment SUT IP {sut_ip} not reachable")
            
            # Method 3: Check configuration file
            config_file = Path(__file__).parent.parent / "config" / "sut_config.yaml"
            if config_file.exists():
                try:
                    import yaml
                    with open(config_file, 'r') as f:
                        config = yaml.safe_load(f)
                        sut_ip = config.get('sut', {}).get('ip_address')
                        if sut_ip:
                            logger.info(f"Found SUT IP in config: {sut_ip}")
                            if ping_sut(sut_ip, timeout_seconds=3):
                                self.sut_ip = sut_ip
                                return sut_ip
                            else:
                                logger.warning(f"Config SUT IP {sut_ip} not reachable")
                except Exception as e:
                    logger.warning(f"Error reading config file: {e}")
            
            # Method 4: Network discovery (scan common subnets)
            logger.info("Attempting network discovery...")
            discovered_ip = self._network_discovery()
            if discovered_ip:
                self.sut_ip = discovered_ip
                return discovered_ip
            
            logger.error("Failed to discover SUT IP address")
            return None
            
        except Exception as e:
            logger.error(f"Error discovering SUT IP: {e}")
            return None
    
    def _network_discovery(self) -> Optional[str]:
        """
        Attempt to discover SUT via network scanning.
        
        Returns:
            str: Discovered IP address or None
        """
        try:
            # Get local network info
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
            logger.info(f"Local host IP: {local_ip}")
            
            # Extract network prefix (assume /24)
            network_prefix = '.'.join(local_ip.split('.')[:-1])
            
            # Common SUT IP patterns
            common_sut_suffixes = [100, 101, 102, 150, 200, 201, 250]
            
            for suffix in common_sut_suffixes:
                candidate_ip = f"{network_prefix}.{suffix}"
                if self._test_connectivity(candidate_ip, timeout=2):
                    logger.info(f"Discovered SUT at: {candidate_ip}")
                    return candidate_ip
            
            return None
            
        except Exception as e:
            logger.error(f"Network discovery failed: {e}")
            return None
    
    def _test_connectivity(self, ip: str, port: int = 22, timeout: int = 5) -> bool:
        """
        Test basic connectivity to an IP address.
        
        Args:
            ip: IP address to test
            port: Port to test (default SSH)
            timeout: Connection timeout in seconds
            
        Returns:
            bool: True if connection successful
        """
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((ip, port))
            sock.close()
            return result == 0
        except Exception:
            return False
    
    def validate_connection(self, ip: str = None) -> bool:
        """
        Validate connection to SUT using VF Curve Manager ping method.
        
        Args:
            ip: IP address to validate (uses discovered IP if None)
            
        Returns:
            bool: True if connection is valid
        """
        if ip:
            self.sut_ip = ip
        
        if not self.sut_ip:
            logger.error("No SUT IP address available for validation")
            return False
        
        logger.info(f"Validating connection to SUT: {self.sut_ip}")
        
        # Use integrated ping function first
        if ping_sut(self.sut_ip, timeout_seconds=5):
            logger.info(f"Integrated ping successful to {self.sut_ip}")
            self.connection_validated = True
            return True
        else:
            logger.warning(f"Integrated ping failed to {self.sut_ip}")
        
        # Fallback to standard connectivity tests
        logger.info("Using fallback connectivity tests...")
        
        # Test multiple common ports
        ports_to_test = [22, 3389, 5985, 5986]  # SSH, RDP, WinRM HTTP, WinRM HTTPS
        
        for port in ports_to_test:
            if self._test_connectivity(self.sut_ip, port):
                logger.info(f"Successfully connected to {self.sut_ip}:{port}")
                self.connection_validated = True
                return True
        
        logger.error(f"Failed to connect to SUT at {self.sut_ip}")
        return False
    
    def _detect_os_type(self, target_ip):
        """Detect OS type by checking which ports are open (SSH vs WinRM)."""
        # Try SSH port (Linux)
        if self._test_connectivity(target_ip, 22, timeout=2):
            return 'linux'
        # Try WinRM ports (Windows)
        elif self._test_connectivity(target_ip, 5985, timeout=2) or self._test_connectivity(target_ip, 5986, timeout=2):
            return 'windows'
        else:
            # Default to windows if can't determine
            return 'windows'
    
    def detect_running_stress(self, sut_ip=None):
        """Detect what stress test is currently running on SUT with comprehensive detection."""
        from src.remote_transfer import RemoteTransfer
        
        # Use provided IP or fall back to instance IP
        target_ip = sut_ip or self.sut_ip
        
        if not target_ip:
            return {'detected': False, 'processes': []}
        
        # Detect OS type first
        os_type = self._detect_os_type(target_ip)
        
        # Create transfer with appropriate credentials
        ssh_key_path = None
        username = 'Administrator'  # Default for Windows
        password = ''  # Default empty for Windows
        
        # Load credentials from config file
        try:
            import yaml
            with open('config/sut_config.yaml', 'r') as f:
                config_data = yaml.safe_load(f)
            config = config_data.get('sut', {})  # Get the 'sut' section
            
            if os_type == 'linux':
                ssh_key_path = config.get('ssh_key_path')
                username = config.get('linux_username', 'root')
                password = config.get('linux_password', 'svsos')
            else:  # Windows
                username = config.get('windows_username', 'Administrator')
                password = config.get('windows_password', '')
        except Exception as e:
            logger.debug(f"Could not load config, using defaults: {e}")
            pass
        
        transfer = RemoteTransfer(target_ip, username=username, password=password, ssh_key_path=ssh_key_path)
        
        try:
            if os_type == 'linux':
                return self._detect_stress_linux(transfer)
            else:
                return self._detect_stress_windows(transfer)
        except Exception as e:
            logger.warning(f"Stress detection failed: {e}")
            return {'detected': False, 'processes': [], 'error': str(e)}
    
    def _detect_stress_linux(self, transfer):
        """Detect stress tests on Linux using ps and top."""
        # Get top CPU-consuming processes
        cmd = """
ps aux --sort=-%cpu | head -20 | awk '{printf "{\\"user\\":\\"%s\\",\\"pid\\":%s,\\"cpu\\":%s,\\"mem\\":%s,\\"vsz\\":%s,\\"rss\\":%s,\\"tty\\":\\"%s\\",\\"stat\\":\\"%s\\",\\"start\\":\\"%s\\",\\"time\\":\\"%s\\",\\"command\\":\\"%s\\"}\\n", $1,$2,$3,$4,$5,$6,$7,$8,$9,$10,substr($0,index($0,$11))}'
"""
        success, stdout, stderr = transfer.execute_command(cmd, timeout=30)
        
        # SSH warnings in stderr are normal, check if we got stdout
        if not stdout or not stdout.strip():
            logger.debug(f"Linux stress detection: No stdout. Success: {success}, Output length: {len(stdout) if stdout else 0}")
            if stderr and 'Warning: Permanently added' not in stderr:
                logger.debug(f"Error: {stderr[:200]}")
                return {'detected': False, 'processes': [], 'error': f'Command failed: {stderr[:100]}'}
            else:
                return {'detected': False, 'processes': [], 'error': 'No process output'}
        
        try:
            import json
            stress_info = {
                'detected': False,
                'processes': [],
                'stress_types': [],
                'primary_stress': None,
                'summary': ''
            }
            
            detected_stresses = []
            unrecognized_high_cpu = []  # Track high CPU processes we don't recognize
            
            for line in stdout.strip().split('\n')[1:]:  # Skip header
                try:
                    proc = json.loads(line)
                    cpu = float(proc.get('cpu', 0))
                    mem = float(proc.get('mem', 0))
                    command = proc.get('command', '').lower()
                    
                    # Extract process name from command
                    proc_name = command.split()[0].split('/')[-1] if command else ''
                    
                    # Check if it's a known stress tool first
                    stress_type = self._identify_stress_type(proc_name)
                    
                    # If it's a recognized stress tool, always include it regardless of CPU/memory
                    # This catches I/O stress, disk stress, idle monitoring tools, etc.
                    if stress_type and 'Unknown' not in stress_type:
                        # Known stress tool - include it even with low CPU
                        pass
                    elif cpu < 2.0:
                        # Not a recognized stress tool and very low CPU - skip
                        continue
                    
                    if stress_type and 'Unknown' not in stress_type:
                        rss_mb = float(proc.get('rss', 0)) / 1024  # Convert KB to MB
                        
                        stress_info['processes'].append({
                            'name': proc_name,
                            'type': stress_type,
                            'cpu_usage': cpu,
                            'memory_mb': rss_mb,
                            'command': command[:80]
                        })
                        
                        if stress_type not in detected_stresses:
                            detected_stresses.append(stress_type)
                        
                        # Log detection for debugging
                        logger.info(f"[OK] Detected stress: {stress_type} (process: {proc_name}, CPU: {cpu:.1f}%, Mem: {rss_mb:.0f}MB)")
                    else:
                        # Track unrecognized high-CPU processes for debugging
                        unrecognized_high_cpu.append({'name': proc_name, 'cpu': cpu, 'command': command[:50]})
                except json.JSONDecodeError:
                    continue
            
            # If no stress detected but found unrecognized high-CPU processes, log them
            if not stress_info['processes'] and unrecognized_high_cpu:
                stress_info['unrecognized_processes'] = unrecognized_high_cpu
                logger.debug(f"High CPU processes not recognized as stress: {unrecognized_high_cpu[:5]}")
            
            if stress_info['processes']:
                stress_info['detected'] = True
                stress_info['stress_types'] = detected_stresses
                stress_info['primary_stress'] = detected_stresses[0] if detected_stresses else None
                
                # Calculate confidence based on number of stress processes and CPU usage
                total_stress_cpu = sum(p['cpu_usage'] for p in stress_info['processes'])
                num_processes = len(stress_info['processes'])
                
                # Confidence calculation:
                # - High confidence (85-95%): Known stress tool detected (even with low CPU)
                # - Higher confidence: Multiple stress processes or high CPU usage
                # - Memory/IO stress tools may have low CPU but are still valid stress
                if num_processes >= 3:
                    # Multiple stress tools detected
                    confidence = min(95, 85 + (num_processes * 3))
                elif num_processes >= 2:
                    # Two stress tools
                    confidence = 90
                elif total_stress_cpu >= 20:
                    # Single tool with significant CPU
                    confidence = min(90, 80 + (total_stress_cpu / 10))
                else:
                    # Single tool with low CPU (e.g., memory stress, I/O stress)
                    # Still confident it's stress since we recognized the tool
                    confidence = 85
                
                stress_info['confidence'] = round(confidence, 1)
                
                if len(detected_stresses) == 1:
                    stress_info['summary'] = detected_stresses[0]
                elif len(detected_stresses) > 1:
                    stress_info['summary'] = f"Multi-Component: {', '.join(detected_stresses[:3])}"
            else:
                stress_info['confidence'] = 0
            
            return stress_info
            
        except Exception as e:
            logger.warning(f"Error detecting Linux stress: {e}")
            return {'detected': False, 'processes': [], 'error': str(e)}
    
    def _detect_stress_windows(self, transfer):
        """Detect stress tests on Windows using PowerShell."""
        # Get top processes by CPU usage with detailed info including CPU percentage
        cmd = """
        $cpuCores = (Get-WmiObject Win32_ComputerSystem).NumberOfLogicalProcessors
        Get-Process | Where-Object {$_.CPU -gt 1} | 
        Sort-Object CPU -Descending | 
        Select-Object -First 30 ProcessName, CPU, 
        @{Name='MemoryMB';Expression={[math]::Round($_.WorkingSet64/1MB,2)}}, 
        @{Name='Threads';Expression={$_.Threads.Count}},
        @{Name='CPUPercent';Expression={
            $cpuTime = $_.CPU
            $processTime = (Get-Date) - $_.StartTime
            if ($processTime.TotalSeconds -gt 0) {
                [math]::Round(($cpuTime / $processTime.TotalSeconds / $cpuCores) * 100, 1)
            } else { 0 }
        }} | 
        ConvertTo-Json
        """
        
        success, stdout, stderr = transfer.execute_command(cmd, timeout=30)
        
        if not success or not stdout.strip():
            return {'detected': False, 'processes': []}
        
        try:
            import json
            processes = json.loads(stdout)
            
            # Handle single process (not array)
            if isinstance(processes, dict):
                processes = [processes]
            
            stress_info = {
                'detected': False,
                'processes': [],
                'stress_types': [],
                'primary_stress': None,
                'summary': ''
            }
            
            detected_stresses = []
            
            for proc in processes:
                proc_name = proc.get('ProcessName', '').lower()
                cpu = proc.get('CPU', 0)
                cpu_percent = proc.get('CPUPercent', 0)
                mem_mb = proc.get('MemoryMB', 0)
                threads = proc.get('Threads', 0)
                
                # Check if this is a known stress tool
                stress_type = self._identify_stress_type(proc_name)
                
                if stress_type and 'Unknown' not in stress_type:
                    stress_info['processes'].append({
                        'name': proc_name,
                        'type': stress_type,
                        'cpu_time': cpu,
                        'cpu_usage': cpu_percent,
                        'memory_mb': mem_mb,
                        'threads': threads
                    })
                    
                    if stress_type not in detected_stresses:
                        detected_stresses.append(stress_type)
            
            if stress_info['processes']:
                stress_info['detected'] = True
                stress_info['stress_types'] = detected_stresses
                stress_info['primary_stress'] = detected_stresses[0] if detected_stresses else None
                
                # Calculate confidence based on number of stress processes and CPU usage
                total_stress_cpu = sum(p.get('cpu_usage', 0) for p in stress_info['processes'])
                num_processes = len(stress_info['processes'])
                
                # Confidence calculation (matches Linux logic):
                # Known stress tools detected = high confidence even with low CPU
                if num_processes >= 3:
                    # Multiple stress tools detected
                    confidence = min(95, 85 + (num_processes * 3))
                elif num_processes >= 2:
                    # Two stress tools
                    confidence = 90
                elif total_stress_cpu >= 20:
                    # Single tool with significant CPU
                    confidence = min(90, 80 + (total_stress_cpu / 10))
                else:
                    # Single tool with low CPU (e.g., memory stress, I/O stress)
                    # Still confident it's stress since we recognized the tool
                    confidence = 85
                
                stress_info['confidence'] = round(confidence, 1)
                
                # Create summary
                if len(detected_stresses) == 1:
                    stress_info['summary'] = detected_stresses[0]
                elif len(detected_stresses) > 1:
                    stress_info['summary'] = f"Multi-Component Stress: {', '.join(detected_stresses[:3])}"
                    if len(detected_stresses) > 3:
                        stress_info['summary'] += f" + {len(detected_stresses) - 3} more"
            else:
                stress_info['confidence'] = 0
            
            return stress_info
            
        except Exception as e:
            logger.warning(f"Error detecting stress: {e}")
            return {'detected': False, 'processes': [], 'error': str(e)}
    
    def _identify_stress_type(self, process_name):
        """Identify stress test type from process name using configurable stress tools database."""
        process_lower = process_name.lower()
        
        # If config loaded, use it
        if self.stress_tools_config:
            # Check all tool categories in priority order
            categories = [
                'intel_tools',
                'linux_tools', 
                'cpu_stress_tools',
                'memory_stress_tools',
                'gpu_stress_tools',
                'benchmark_tools'
            ]
            
            for category in categories:
                tools = self.stress_tools_config.get(category, {})
                for tool_key, tool_info in tools.items():
                    # Check main pattern
                    if tool_info.get('exact_match'):
                        # Exact match required
                        if process_lower == tool_key.lower():
                            return tool_info['label']
                    else:
                        # Substring match
                        if tool_key.lower() in process_lower:
                            return tool_info['label']
                    
                    # Check aliases
                    for alias in tool_info.get('aliases', []):
                        if alias.lower() in process_lower:
                            return tool_info['label']
                    
                    # Check complex pattern if defined
                    pattern = tool_info.get('pattern')
                    if pattern:
                        import re
                        if re.search(pattern, process_lower):
                            return tool_info['label']
        
        # Fallback to hardcoded patterns if config not available
        else:
            # Intel Internal Tools (highest priority - SVOS/validation tools)
            if 'memicals' in process_lower:
                return 'Memicals (Intel Memory Stress)'
            elif 'sandstone' in process_lower:
                return 'Sandstone (Intel Instruction Validation)'
            elif 'memrunner' in process_lower:
                return 'MemRunner (Intel Memory Stress)'
            elif 'buslocker' in process_lower:
                return 'BusLocker (Intel Interconnect Stress)'
            elif 'dynamo' in process_lower:
                return 'Dynamo (Intel Dynamic Stress)'
            elif 'glaze' in process_lower:
                return 'Glaze (Intel Stress Tool)'
            elif 'supercollider' in process_lower or 'super_collider' in process_lower:
                return 'SuperCollider (Intel Multi-Component Stress)'
            elif 'mlc' in process_lower:
                return 'MLC (Intel Memory Latency Checker)'
            elif 'ipmctl' in process_lower:
                return 'ipmctl (Intel Optane DCPMM Stress)'
            elif 'svos' in process_lower:
                return 'SVOS (Silicon Validation OS Tool)'
            
            # Linux Stress Tools (high priority)
            elif 'stress-ng' in process_lower:
                return 'stress-ng (Linux Multi-Stress)'
            elif 'sysbench' in process_lower:
                return 'sysbench (Linux Benchmark/Stress)'
            elif process_lower == 'stress':  # Exact match to avoid false positives
                return 'stress (Linux CPU/Memory Stress)'
            elif 'fio' in process_lower:
                return 'fio (Disk I/O Stress)'
            elif 'memtester' in process_lower:
                return 'memtester (Linux Memory Test)'
            elif 'cpuburn' in process_lower:
                return 'cpuburn (Linux CPU Stress)'
            
            # CPU Stress Tools (cross-platform)
            elif 'prime95' in process_lower or 'mprime' in process_lower:
                return 'Prime95/mprime (CPU Stress)'
            elif 'linpack' in process_lower or 'linx' in process_lower:
                return 'Linpack (FP Math Stress)'
            elif 'intelburntest' in process_lower or 'ibt' in process_lower:
                return 'Intel Burn Test (CPU)'
            elif 'y-cruncher' in process_lower or 'ycruncher' in process_lower:
                return 'y-cruncher (Math Stress)'
            
            # Memory Stress Tools
            elif 'memtest' in process_lower:
                return 'MemTest (Memory Stress)'
            elif 'stream' in process_lower:
                return 'Stream (Memory Bandwidth)'
            elif 'hci' in process_lower and 'mem' in process_lower:
                return 'HCI MemTest (Memory Stress)'
            elif 'hci' in process_lower:
                return 'HCI MemTest (Memory)'
        
        # System/Multi-Component
        if 'aida64' in process_name:
            return 'AIDA64 (System Stress)'
        elif 'occt' in process_name:
            return 'OCCT (Stability Test)'
        elif 'burnintest' in process_name:
            return 'BurnInTest (System)'
        
        # Benchmarks
        elif 'cinebench' in process_name:
            return 'Cinebench (CPU Rendering)'
        elif 'geekbench' in process_name:
            return 'Geekbench (Mixed Benchmark)'
        elif '3dmark' in process_name:
            return '3DMark (Graphics)'
        
        # GPU Stress
        elif 'furmark' in process_name:
            return 'FurMark (GPU Stress)'
        
        # Media/Encoding
        elif 'handbrake' in process_name:
            return 'HandBrake (Video Encoding)'
        elif 'blender' in process_name:
            return 'Blender (3D Rendering)'
        elif '7z' in process_name or '7zip' in process_name:
            return '7-Zip (Compression)'
        elif 'wmplayer' in process_name or 'mediaplayer' in process_name:
            return 'Media Player (Playback)'
        
        # Orchestrator/Background Processes (DO NOT REPORT AS STRESS)
        elif 'python' in process_name:
            return None  # Orchestrator - ignore
        elif 'java' in process_name:
            return None  # Runtime - usually not stress
        elif 'perl' in process_name or 'bash' in process_name or 'sh' == process_name:
            return None  # Scripts - ignore
        elif 'systemd' in process_name or 'sshd' in process_name:
            return None  # System services - ignore
        
        # Unknown if no match
        return None  # Not a recognized stress tool
    
    def get_sut_info(self) -> Dict[str, Any]:
        """
        Get SUT information summary.
        
        Returns:
            Dict containing SUT information
        """
        return {
            'ip_address': self.sut_ip,
            'connection_validated': self.connection_validated,
            'discovery_method': 'vf_curve_manager' if self.sut_ip else 'not_discovered'
        }


def test_integrated_sut_communicator():
    """
    Test SUT IP discovery using integrated VF Curve Manager functionality.
    This uses the integrated functions rather than external dependencies.
    
    Returns:
        str: SUT IP address if found and reachable, None otherwise
    """
    try:
        # Test integrated ITP communicator discovery
        sut_ip = get_sut_ip_from_itp()
        
        if sut_ip:
            # Test integrated ping function
            if ping_sut(sut_ip, timeout_seconds=3):
                print(f"Integrated functions: Found reachable SUT at {sut_ip}")
                return sut_ip
            else:
                print(f"Integrated functions: Found SUT IP {sut_ip} but ping failed")
                return None
        else:
            print("Integrated functions: Could not determine SUT IP from ITP communicator")
            return None
            
    except Exception as e:
        print(f"Error using integrated SUT communicator functions: {e}")
        return None


if __name__ == "__main__":
    # Test integrated SUT discovery
    logging.basicConfig(level=logging.INFO)
    
    # Test integrated communicator functions
    print("Testing integrated SUT communicator functions:")
    test_ip = test_integrated_sut_communicator()
    
    if test_ip:
        print(f"[SUCCESS] Integrated test successful: {test_ip}")
    else:
        print("[FAILED] Integrated test failed")
    
    # Test SUTCommunicator class
    print("\nTesting SUTCommunicator class:")
    communicator = SUTCommunicator()
    sut_ip = communicator.discover_sut_ip()
    
    if sut_ip:
        print(f"[SUCCESS] Discovered SUT IP: {sut_ip}")
        if communicator.validate_connection():
            print("[SUCCESS] Connection validated successfully")
        else:
            print("[FAILED] Connection validation failed")
    else:
        print("[FAILED] Failed to discover SUT IP")