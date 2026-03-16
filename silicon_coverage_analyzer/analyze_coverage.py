#!/usr/bin/env python3
"""
Silicon Coverage Analyzer - Main Entry Point

INTEL CONFIDENTIAL - INTERNAL USE ONLY

Analyzes silicon coverage by collecting EMON events across all PMU domains
and identifying non-toggling events that indicate coverage gaps.

Usage:
    python analyze_coverage.py [--config CONFIG] [--duration SECONDS] [--domains DOMAIN1,DOMAIN2]

Author: Intel Corporation
Date: November 2025
"""

import sys
import os

# CRITICAL: Force unbuffered output to prevent PowerShell terminal hanging
# This must be set BEFORE any print statements or imports that print
sys.stdout.reconfigure(line_buffering=True) if hasattr(sys.stdout, 'reconfigure') else None
os.environ['PYTHONUNBUFFERED'] = '1'

import json
import argparse
import re
import subprocess
import time
import yaml
from pathlib import Path
from datetime import datetime, timedelta

# Ensure proper encoding for Windows
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Global log file handle for debug mode
_debug_log_file = None

class TeeOutput:
    """Writes to both console and log file simultaneously."""
    def __init__(self, console, log_file):
        self.console = console
        self.log_file = log_file
    
    def write(self, message):
        self.console.write(message)
        if self.log_file:
            self.log_file.write(message)
            self.log_file.flush()
    
    def flush(self):
        self.console.flush()
        if self.log_file:
            self.log_file.flush()
    
    def isatty(self):
        return self.console.isatty()

def enable_debug_logging():
    """Enable debug logging to timestamped file."""
    global _debug_log_file
    
    # Create logs directory if it doesn't exist
    log_dir = Path('logs')
    log_dir.mkdir(exist_ok=True)
    
    # Create timestamped log filename
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    log_file = log_dir / f'debug_log_{timestamp}.txt'
    
    # Open log file
    _debug_log_file = open(log_file, 'w', encoding='utf-8')
    
    # Write header
    _debug_log_file.write(f"="*80 + "\n")
    _debug_log_file.write(f"Silicon Coverage Analyzer - Debug Log\n")
    _debug_log_file.write(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    _debug_log_file.write(f"="*80 + "\n\n")
    _debug_log_file.flush()
    
    # Replace stdout and stderr with Tee objects
    sys.stdout = TeeOutput(sys.stdout, _debug_log_file)
    sys.stderr = TeeOutput(sys.stderr, _debug_log_file)
    
    print(f"[DEBUG] Logging enabled: {log_file}")
    return log_file

def close_debug_logging():
    """Close debug log file and restore stdout/stderr."""
    global _debug_log_file
    
    if _debug_log_file:
        try:
            # Write footer
            _debug_log_file.write(f"\n" + "="*80 + "\n")
            _debug_log_file.write(f"Ended: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            _debug_log_file.write(f"="*80 + "\n")
            _debug_log_file.flush()
            _debug_log_file.close()
        except Exception:
            pass  # Ignore errors during cleanup
        finally:
            _debug_log_file = None

# Auto-install Intel-compliant dependencies if missing
def ensure_dependencies():
    """Auto-install required Intel-approved packages if missing."""
    required_packages = {
        'numpy': 'numpy>=1.24.0',
        'pandas': 'pandas>=2.0.0',
        'matplotlib': 'matplotlib>=3.7.0',
        'seaborn': 'seaborn>=0.12.0',
        'yaml': 'pyyaml>=6.0',
        'psutil': 'psutil>=5.9.0',
        'sklearn': 'scikit-learn>=1.3.0',
        'joblib': 'joblib>=1.3.0',
        'sklearnex': 'scikit-learn-intelex>=2024.0.0'  # Intel ML acceleration
    }
    
    missing = []
    for module, package in required_packages.items():
        try:
            __import__(module)
        except ImportError:
            missing.append(package)
    
    if missing:
        print(f"[AUTO-INSTALL] Installing {len(missing)} missing Intel-approved packages...")
        for package in missing:
            print(f"  Installing {package}...")
            try:
                subprocess.check_call([sys.executable, '-m', 'pip', 'install', package, '-q'])
                print(f"  [OK] {package} installed")
            except Exception as e:
                print(f"  [WARN] Failed to install {package}: {e}")
        print()

# Run dependency check
ensure_dependencies()

from src.sut_communicator import SUTCommunicator
from src.domain_analyzer import DomainAnalyzer
from src.optimized_batch_collector import OptimizedBatchCollector
from src.gap_detector import GapDetector
from src.azure_integration import integrate_azure
from src.checkpoint_manager import CheckpointManager, list_resumable_sessions

def is_admin():
    """Check if script is running with administrator privileges."""
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except:
        return False

def elevate_and_rerun():
    """Request admin elevation and rerun the script."""
    import ctypes
    import sys
    
    try:
        # Get the command line arguments
        script = sys.argv[0]
        params = ' '.join([f'"{arg}"' if ' ' in arg else arg for arg in sys.argv[1:]])
        
        # Run with elevation
        ret = ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            sys.executable,
            f'"{script}" {params}',
            None,
            1  # SW_SHOWNORMAL
        )
        
        if ret > 32:  # Success
            sys.exit(0)
        else:
            print("\n[FAIL] Administrator elevation denied or failed")
            print("\nAlternative: Run this command manually as Administrator:")
            print(f"Set-Item WSMan:\\localhost\\Client\\TrustedHosts -Value '*' -Force")
            sys.exit(1)
    except Exception as e:
        print(f"\n[FAIL] Elevation failed: {e}")
        sys.exit(1)
from src.report_generator import ReportGenerator


class OverallProgressTracker:
    """Tracks progress across the entire workflow with dynamic ETA calculation."""
    
    def __init__(self):
        self.start_time = time.time()
        self.phases = {
            'initialization': {'weight': 5, 'status': 'pending', 'start': None, 'end': None},
            'collection': {'weight': 70, 'status': 'pending', 'start': None, 'end': None},
            'transfer': {'weight': 10, 'status': 'pending', 'start': None, 'end': None},
            'analysis': {'weight': 10, 'status': 'pending', 'start': None, 'end': None},
            'reporting': {'weight': 5, 'status': 'pending', 'start': None, 'end': None}
        }
        self.total_weight = sum(p['weight'] for p in self.phases.values())
        self.current_phase = None
        self.collection_progress = 0  # 0-100 for collection sub-progress
        self.collection_duration_seconds = None  # Actual configured collection duration
        
    def start_phase(self, phase_name):
        """Start a new phase."""
        if phase_name in self.phases:
            self.phases[phase_name]['status'] = 'in_progress'
            self.phases[phase_name]['start'] = time.time()
            self.current_phase = phase_name
            
    def end_phase(self, phase_name):
        """Mark phase as complete."""
        if phase_name in self.phases:
            self.phases[phase_name]['status'] = 'complete'
            self.phases[phase_name]['end'] = time.time()
            
    def update_collection_progress(self, current, total):
        """Update collection sub-progress."""
        self.collection_progress = (current / total * 100) if total > 0 else 0
        
    def get_overall_progress(self):
        """Calculate overall progress percentage (0-100)."""
        completed_weight = 0
        
        for phase, data in self.phases.items():
            if data['status'] == 'complete':
                completed_weight += data['weight']
            elif data['status'] == 'in_progress' and phase == 'collection':
                # Add partial progress for collection phase
                completed_weight += (data['weight'] * self.collection_progress / 100)
                
        return (completed_weight / self.total_weight) * 100
        
    def get_eta(self):
        """Calculate ETA based on configured duration for collection phase, or elapsed time for other phases."""
        elapsed = time.time() - self.start_time
        progress = self.get_overall_progress()
        
        if progress < 5:  # Too early to estimate
            return None
        
        # If we're in the collection phase and have a configured duration, use it for better accuracy
        if self.current_phase == 'collection' and self.collection_duration_seconds:
            collection_start = self.phases['collection'].get('start')
            if collection_start:
                collection_elapsed = time.time() - collection_start
                
                # Check if this is long-run mode (configured duration >> typical batch time)
                # Long-run mode: collection_duration_seconds >= 3600 (1 hour or more)
                is_long_run = self.collection_duration_seconds >= 3600
                
                if is_long_run:
                    # Long-run mode: Use configured duration directly
                    remaining_collection = self.collection_duration_seconds - collection_elapsed
                    overhead_seconds = 300  # ~5 minutes for batch transfer/analysis/reporting
                    remaining = remaining_collection + overhead_seconds
                    return max(0, remaining)
                else:
                    # Standard mode: Use actual progress to estimate (more accurate for variable batch sizes)
                    # Calculate collection progress percentage
                    collection_progress = self.collection_progress  # 0-100
                    if collection_progress > 5:
                        # Estimate total collection time based on actual progress
                        estimated_total_collection = (collection_elapsed / collection_progress) * 100
                        remaining_collection = estimated_total_collection - collection_elapsed
                        
                        # Add overhead for other phases (transfer, analysis, reporting)
                        # These are quick in standard mode (~1-2 minutes total)
                        overhead_seconds = 120
                        
                        remaining = remaining_collection + overhead_seconds
                        return max(0, remaining)
        
        # Fallback to progress-based calculation for other phases
        total_estimated = (elapsed / progress) * 100 if progress > 0 else 0
        remaining = total_estimated - elapsed
        
        return max(0, remaining)
        
    def display_progress(self):
        """Display unified progress bar."""
        progress = self.get_overall_progress()
        bar_length = 50
        filled = int(bar_length * progress / 100)
        bar = '█' * filled + '░' * (bar_length - filled)
        
        eta = self.get_eta()
        eta_str = ""
        if eta is not None:
            if eta >= 60:
                eta_str = f" | ETA: {int(eta // 60)}m {int(eta % 60)}s"
            else:
                eta_str = f" | ETA: {int(eta)}s"
        
        phase_name = self.current_phase.replace('_', ' ').title() if self.current_phase else "Starting"
        
        # Force immediate output in PowerShell (prevents buffering/hanging)
        import sys
        sys.stdout.write(f"\r[{bar}] {progress:5.1f}% | {phase_name:<15}{eta_str}  ")
        sys.stdout.flush()


class SiliconCoverageAnalyzer:
    """Main orchestrator for silicon coverage analysis."""
    
    def __init__(self, config):
        self.config = config
        self.debug = config.get('debug', False)
        self.sut_ip = None
        self.progress_tracker = OverallProgressTracker()
        self.results = {
            'timestamp': datetime.now().isoformat(),
            'domains': {},
            'coverage': {},
            'gaps': {},
            'config': config
        }
        
        # Checkpoint manager for long runs
        self.checkpoint_manager = None
        self.resume_session_id = config.get('resume_session_id')
        self.checkpoint_dir = config.get('checkpoint_dir')
        self.enable_checkpoints = not config.get('no_checkpoint', False)
        
        # Initialize Azure integration
        self.azure = None
        try:
            self.azure = integrate_azure(self)
        except Exception as e:
            print(f"[INFO] Azure integration disabled: {e}")
    
    def run(self):
        """Execute PMU coverage analysis workflow.
        
        This analyzer collects EMON data and analyzes coverage.
        It integrates with your external stress framework - just run your
        stress tests separately, then run this analyzer to measure coverage.
        """
        import time
        total_start = time.time()  # Track total execution time
        
        try:
            print("="*80)
            print("SILICON COVERAGE ANALYZER - Analysis Mode")
            print("PMU Event Coverage Analysis (Stress-Framework Agnostic)")
            print("="*80)
            print()
            
            # Check for resume mode
            if self.resume_session_id:
                return self._run_resume_mode()
            
            # Step 1: Connect to SUT
            self._connect_sut()
            
            # Step 1.5: Check EMON installation
            self._check_emon_installation()
            
            # Step 1.6: Validate EMON and get hardware config
            self._validate_emon()
            
            # Step 2: Discover PMU domains
            self._discover_domains()
            
            # Step 3: Collect EMON coverage data
            self._collect_coverage()
            
            # Mark checkpoint as completed
            if self.checkpoint_manager:
                self.checkpoint_manager.mark_completed()
            
            # Step 4: Analyze gaps
            self._detect_gaps()
            
            # Step 5: ML-powered analysis (local + GenAI)
            self._train_and_analyze_ml()
            
            # Calculate total execution time (collection + analysis + gap detection + ML)
            total_execution_time = time.time() - total_start
            self.results['total_execution_time_seconds'] = total_execution_time
            
            # Step 6: Generate reports
            reports = self._generate_reports()
            
            # Summary
            self._print_summary()
            
            return reports
            
        except KeyboardInterrupt:
            print("\n\n[INTERRUPTED] Analysis cancelled by user")
            if self.checkpoint_manager:
                self.checkpoint_manager.mark_failed("User interrupted (Ctrl+C)")
                print(f"[CHECKPOINT] Data saved. Resume with: --resume {self.checkpoint_manager.session_id}")
            return None
        except Exception as e:
            print(f"\n[ERROR] Analysis failed: {e}")
            if self.checkpoint_manager:
                self.checkpoint_manager.mark_failed(str(e))
                print(f"[CHECKPOINT] Data saved. Resume with: --resume {self.checkpoint_manager.session_id}")
            import traceback
            traceback.print_exc()
            return None
    
    def _run_resume_mode(self):
        """Resume analysis from a checkpoint."""
        import time
        total_start = time.time()
        
        print(f"[RESUME] Loading checkpoint: {self.resume_session_id}")
        
        # Load checkpoint
        self.checkpoint_manager = CheckpointManager.load_checkpoint(
            self.resume_session_id,
            checkpoint_dir=self.checkpoint_dir,
            debug=self.debug
        )
        
        if not self.checkpoint_manager:
            print(f"[ERROR] Could not load checkpoint: {self.resume_session_id}")
            print("        Use --list-sessions to see available checkpoints")
            return None
        
        # Restore SUT info
        sut_info = self.checkpoint_manager.get_sut_info()
        self.sut_ip = sut_info['sut_ip']
        self.config['os_type'] = sut_info['os_type']
        
        # Restore hardware config
        hw_config = sut_info.get('hardware_config', {})
        self.results['hardware_config'] = hw_config
        
        # Restore stress detection
        self.results['stress_detection'] = self.checkpoint_manager.get_stress_detection()
        
        # Get session stats
        stats = self.checkpoint_manager.get_session_stats()
        print(f"\n      [RESUME] Resuming from {stats['domains_completed']}/{stats['domains_total']} domains")
        print(f"      [RESUME] {stats['total_events']} events already collected")
        
        # Step 1: Re-connect to SUT
        print(f"\n[1/5] Re-connecting to SUT: {self.sut_ip}", flush=True)
        self._connect_sut()
        
        # Step 1.5: Validate EMON still works
        self._check_emon_installation()
        self._validate_emon()
        
        # Restore domains from checkpoint or re-discover
        pending = self.checkpoint_manager.get_pending_domains()
        if pending:
            # Re-discover domains to get event lists
            self._discover_domains()
            
            # Continue collection for pending domains only
            self._collect_coverage_resume(pending)
        else:
            print(f"\n      [RESUME] All domains already collected!")
        
        # Merge checkpoint data with any new data
        self._merge_checkpoint_data()
        
        # Mark completed
        self.checkpoint_manager.mark_completed()
        
        # Continue with remaining steps
        self._detect_gaps()
        self._train_and_analyze_ml()
        
        total_execution_time = time.time() - total_start
        self.results['total_execution_time_seconds'] = total_execution_time
        
        reports = self._generate_reports()
        self._print_summary()
        
        return reports
    
    def _merge_checkpoint_data(self):
        """Merge checkpoint data into results."""
        if not self.checkpoint_manager:
            return
        
        all_active, all_inactive, domain_results = self.checkpoint_manager.get_collected_data()
        
        # Merge with any new collection data
        existing_coverage = self.results.get('coverage', {})
        existing_active = existing_coverage.get('all_active', [])
        existing_inactive = existing_coverage.get('all_inactive', [])
        existing_domain_results = existing_coverage.get('domain_results', {})
        
        # Combine
        combined_active = all_active + existing_active
        combined_inactive = all_inactive + existing_inactive
        combined_domain_results = {**domain_results, **existing_domain_results}
        
        # Update results
        self.results['coverage'] = {
            'total_events_tested': len(combined_active) + len(combined_inactive),
            'active_events': len(combined_active),
            'inactive_events': len(combined_inactive),
            'activity_coverage': len(combined_active) / (len(combined_active) + len(combined_inactive)) * 100 
                               if (len(combined_active) + len(combined_inactive)) > 0 else 0,
            'domain_results': combined_domain_results,
            'all_active': combined_active,
            'all_inactive': combined_inactive
        }
        
        # Merge health history
        checkpoint_health = self.checkpoint_manager.get_health_history()
        if checkpoint_health:
            if 'health_history' not in self.results:
                self.results['health_history'] = {'samples': []}
            self.results['health_history']['samples'].extend(checkpoint_health)
    
    def _connect_sut(self):
        """Connect to SUT."""
        print("\n[STARTING] Silicon Coverage Analysis")
        print("=" * 80)
        self.progress_tracker.start_phase('initialization')
        self.progress_tracker.display_progress()
        print("\n")
        print("[1/5] Connecting to SUT...", flush=True)
        
        # Check for IP override
        if 'sut_ip_override' in self.config:
            self.sut_ip = self.config['sut_ip_override']
            print(f"[OVERRIDE] Using specified IP: {self.sut_ip}")
        else:
            sut_comm = SUTCommunicator()
            self.sut_ip = sut_comm.discover_sut_ip()
            
            if not self.sut_ip:
                raise Exception("Failed to discover SUT IP")
        
        # Detect OS and setup remote access
        os_info = self._detect_os_info()
        self.results['os_info'] = os_info
        
        # Store os_type in config for other components
        if os_info.get('detected'):
            self.config['os_type'] = os_info.get('os_type', 'windows').lower()
        
        # If OS detection failed, it might be Linux with SSH key not deployed
        # OR Windows with WinRM/firewall issues
        if not os_info.get('detected'):
            print(f"\n      [INFO] OS detection failed - connection issues detected")
            print(f"\n      Possible causes:")
            print(f"      1. Windows SUT: WinRM not configured or firewall blocking")
            print(f"         -> Run: python setup_windows_sut.py")
            print(f"      2. Linux SUT: SSH key not deployed")
            print(f"         -> Run: python deploy_ssh_key.py")
            print(f"      3. Network connectivity issues")
            print(f"         -> Verify SUT is reachable: ping {self.sut_ip}")
            print(f"\n      After resolving, re-run this analyzer.")
            raise Exception(f"Cannot connect to SUT at {self.sut_ip} - see troubleshooting above")
        
        # Detect running stress using the determined IP
        try:
            sut_comm = SUTCommunicator()
            stress_info = sut_comm.detect_running_stress(self.sut_ip)
            self.results['stress_detection'] = stress_info
            
            if stress_info.get('detected'):
                print(f"\n      [i]  WORKLOAD DETECTED: {stress_info.get('summary', stress_info.get('primary_stress', 'Multi-Component'))}")
                print(f"      Active processes: {len(stress_info.get('processes', []))}")
                print(f"      [INFO] Analyzing coverage under active workload\n")
            else:
                print(f"      [i]  Workload: Idle/Light (analyzing baseline coverage)\n")
        except Exception as e:
            if self.debug:
                print(f"      [DEBUG] Workload detection unavailable: {e}")
            self.results['stress_detection'] = {'detected': False, 'processes': [], 'error': str(e)}
        
        self.results['sut_ip'] = self.sut_ip
        print(f"\n      [OK] Connected: {self.sut_ip}")
        
        # Display OS information
        if os_info.get('detected'):
            print(f"       OS: {os_info.get('os_name', 'Unknown')} {os_info.get('os_version', '')}")
            if os_info.get('os_type') == 'Linux':
                print(f"         Kernel: {os_info.get('kernel_version', 'Unknown')}")
                
                # Check for NMI watchdog (PMU counter competition)
                if os_info.get('nmi_watchdog_enabled'):
                    print(f"         [WARN]  NMI Watchdog: ENABLED (consumes 1-2 PMU counters)")
                    if self.config.get('collection_duration', 3) >= 30:
                        print(f"            [TIP] Long collections may experience PMU starvation")
                        print(f"            [TIP] To improve: echo 0 > /proc/sys/kernel/nmi_watchdog")
                
                # Automatically setup SSH for Linux SUTs
                self._setup_linux_ssh_access()
        
        print()
    
    def _setup_linux_ssh_access(self):
        """Automatically setup SSH access for Linux SUTs."""
        import subprocess
        from pathlib import Path
        
        # Check if SSH key already works
        ssh_key_path = self.config.get('ssh_key_path')
        username = self.config.get('username', 'root')
        
        print(f"\n      [SSH SETUP] Verifying SSH key access...")
        
        if ssh_key_path and Path(ssh_key_path).exists():
            # Test if the configured key works
            test_cmd = ['ssh', '-i', str(ssh_key_path), 
                       '-o', 'BatchMode=yes',
                       '-o', 'StrictHostKeyChecking=no',
                       '-o', 'ConnectTimeout=5',
                       f'{username}@{self.sut_ip}', 
                       'echo SSH_TEST_OK']
            
            try:
                result = subprocess.run(test_cmd, capture_output=True, text=True, timeout=10)
                if result.returncode == 0 and 'SSH_TEST_OK' in result.stdout:
                    print(f"      [OK] SSH key authentication working ({Path(ssh_key_path).name})")
                    return
            except:
                pass
        
        # SSH key not working - guide user to deploy it
        print(f"\n      [FAIL] SSH key authentication not working")
        print(f"\n      Please run the one-time SSH setup:")
        print(f"      -> python deploy_ssh_key.py")
        print(f"\n      Then re-run this analyzer.")
        raise Exception("SSH key setup required - run: python deploy_ssh_key.py")
    
    def _detect_os_info(self):
        """Detect operating system information on the SUT."""
        from src.remote_transfer import RemoteTransfer
        
        # Get credentials from config for initial connection
        # Try with both Windows and Linux credentials to detect OS
        
        # First, try to detect based on open ports via RemoteTransfer
        # RemoteTransfer will set connection_type based on port detection
        transfer_test = RemoteTransfer(
            self.sut_ip,
            username='test',  # Dummy username for port detection
            password='test',
            ssh_key_path=self.config.get('ssh_key_path'),
            collection_hours=self.config.get('hours')
        )
        
        # Based on detected connection type, use appropriate credentials
        if transfer_test.connection_type == 'psremoting' or transfer_test.sut_os_type == 'windows':
            # Windows SUT detected
            username = self.config.get('windows_username', 'Administrator')
            password = self.config.get('windows_password', '')
            ssh_key_path = None
        else:
            # Linux SUT detected or default
            username = self.config.get('linux_username', 'root')
            password = self.config.get('linux_password', 'svsos')
            ssh_key_path = self.config.get('ssh_key_path')
        
        # Now create proper connection with correct credentials
        transfer = RemoteTransfer(
            self.sut_ip,
            username=username,
            password=password,
            ssh_key_path=ssh_key_path,
            collection_hours=self.config.get('hours')
        )
        
        # Try Windows detection first (with retry for initial connection)
        windows_cmd = '''
$os = Get-WmiObject Win32_OperatingSystem
Write-Output "OS:$($os.Caption)"
Write-Output "VERSION:$($os.Version)"
Write-Output "BUILD:$($os.BuildNumber)"
Write-Output "ARCH:$($os.OSArchitecture)"
'''
        # Try up to 2 times with longer timeout for first connection
        success, output, error = False, '', ''
        for attempt in range(2):
            success, output, error = transfer.execute_command(windows_cmd, timeout=30)
            if success and output and "OS:" in output:
                break
            if attempt < 1:
                import time
                time.sleep(2)  # Brief pause before retry
        
        # Debug: Show what we got
        if self.debug and not success:
            print(f"      [DEBUG] Windows detection failed")
            print(f"      [DEBUG] Error: {error[:200] if error else 'No error message'}")
        
        if success and output and "OS:" in output:
            # Parse Windows info
            info = {'detected': True, 'os_type': 'Windows'}
            for line in output.split('\n'):
                if line.startswith('OS:'):
                    info['os_name'] = line.replace('OS:', '').strip()
                elif line.startswith('VERSION:'):
                    info['os_version'] = line.replace('VERSION:', '').strip()
                elif line.startswith('BUILD:'):
                    info['build'] = line.replace('BUILD:', '').strip()
                elif line.startswith('ARCH:'):
                    info['architecture'] = line.replace('ARCH:', '').strip()
            
            # Store Windows credentials in config for other components
            self.config['username'] = username
            self.config['password'] = password
            self.config['ssh_key_path'] = None
            
            return info
        
        # Try Linux detection
        linux_cmd = '''
if [ -f /etc/os-release ]; then
    . /etc/os-release
    echo "OS:$PRETTY_NAME"
    echo "ID:$ID"
    echo "VERSION:$VERSION_ID"
fi
echo "KERNEL:$(uname -r)"
echo "ARCH:$(uname -m)"
echo "NMI_WATCHDOG:$(cat /proc/sys/kernel/nmi_watchdog 2>/dev/null || echo 'unknown')"
'''
        success, output, _ = transfer.execute_command(linux_cmd, timeout=10)
        
        if success and output and "KERNEL:" in output:
            # Parse Linux info
            info = {'detected': True, 'os_type': 'linux'}  # lowercase for consistency
            for line in output.split('\n'):
                if line.startswith('OS:'):
                    info['os_name'] = line.replace('OS:', '').strip()
                elif line.startswith('ID:'):
                    info['distro_id'] = line.replace('ID:', '').strip()
                elif line.startswith('VERSION:'):
                    info['os_version'] = line.replace('VERSION:', '').strip()
                elif line.startswith('KERNEL:'):
                    info['kernel_version'] = line.replace('KERNEL:', '').strip()
                elif line.startswith('ARCH:'):
                    info['architecture'] = line.replace('ARCH:', '').strip()
                elif line.startswith('NMI_WATCHDOG:'):
                    nmi_status = line.replace('NMI_WATCHDOG:', '').strip()
                    info['nmi_watchdog_enabled'] = (nmi_status == '1')
            
            # Store Linux credentials in config for other components
            self.config['username'] = username
            self.config['password'] = password
            self.config['ssh_key_path'] = ssh_key_path
            
            return info
        
        # OS detection failed
        return {'detected': False, 'os_type': 'Unknown', 'os_name': 'Unable to detect'}
    
    def _ensure_client_trustedhosts(self):
        """Ensure client-side TrustedHosts is configured for WinRM."""
        import subprocess
        
        try:
            # Check if TrustedHosts includes this SUT or is set to '*'
            result = subprocess.run(
                ['powershell', '-NoProfile', '-Command', 
                 'Get-Item WSMan:\\localhost\\Client\\TrustedHosts | Select-Object -ExpandProperty Value'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            current_hosts = result.stdout.strip()
            
            # Check if already configured
            if current_hosts == '*' or self.sut_ip in current_hosts:
                return  # Already configured
            
            print(f"   [GEAR]  Configuring client TrustedHosts for {self.sut_ip}...")
            
            # Add this SUT to TrustedHosts
            if current_hosts:
                new_hosts = f"{current_hosts},{self.sut_ip}"
            else:
                new_hosts = self.sut_ip
            
            # Try to update TrustedHosts
            update_result = subprocess.run(
                ['powershell', '-NoProfile', '-Command', 
                 f'Set-Item WSMan:\\localhost\\Client\\TrustedHosts -Value "{new_hosts}" -Force -ErrorAction Stop'],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if update_result.returncode == 0:
                print(f"   [OK] Client TrustedHosts configured")
                # Restart WinRM service
                subprocess.run(
                    ['powershell', '-NoProfile', '-Command', 'Restart-Service WinRM -ErrorAction SilentlyContinue'],
                    capture_output=True,
                    timeout=10
                )
            else:
                # Failed - likely needs admin rights
                print(f"   [WARN]  Could not auto-configure TrustedHosts (needs admin)")
                print(f"   Run as Administrator or manually configure:")
                print(f"   Set-Item WSMan:\\localhost\\Client\\TrustedHosts -Value '{new_hosts}' -Force")
                
        except Exception as e:
            # Silent fail - will show proper error later if connection fails
            pass
    
    def _check_emon_installation(self):
        """Check if EMON is installed on SUT."""
        print("[1.5/5] Checking EMON installation...")
        
        from src.remote_transfer import RemoteTransfer
        import re
        
        # Get OS info and credentials from results
        os_info = self.results.get('os_info', {})
        os_type = os_info.get('os_type', 'windows').lower()
        
        # Create transfer with proper credentials
        ssh_key_path = self.config.get('ssh_key_path')
        username = self.config.get('username', 'root' if os_type == 'linux' else 'administrator')
        password = self.config.get('password')
        
        transfer = RemoteTransfer(
            self.sut_ip,
            username=username,
            password=password,
            ssh_key_path=ssh_key_path,
            collection_hours=self.config.get('hours')
        )
        
        print(f"   Testing connection to {self.sut_ip}...")
        
        # OS-specific connection test
        if os_type == 'linux':
            # Test Linux SSH connection
            test_cmd = 'echo "Connection test"'
            test_success, test_output, test_err = transfer.execute_command(test_cmd, timeout=10)
            
            if not test_success:
                print(f"   [FAIL] SSH connection failed")
                print(f"   Error: {test_err[:200] if test_err else 'NONE'}")
                raise Exception("Cannot communicate with Linux SUT - SSH not accessible")
            
            print(f"   [OK] SSH connection working")
        else:
            # Configure client-side TrustedHosts first for Windows
            self._ensure_client_trustedhosts()
            
            # Test Windows PowerShell remoting
            check_path_cmd = '''
$machinePath = [Environment]::GetEnvironmentVariable("Path", "Machine")
Write-Output "Machine PATH check complete"
'''
            path_success, path_output, path_err = transfer.execute_command(check_path_cmd, timeout=15)
            
            if not path_success or not path_output:
                print(f"   [FAIL] PowerShell remoting failed")
                print(f"   Stdout: {path_output[:200] if path_output else 'NONE'}")
                print(f"   Stderr: {path_err[:200] if path_err else 'NONE'}")
                print(f"\n   Attempting automatic WinRM setup on SUT...")
                
                # Try to setup WinRM remotely
                if self._try_remote_winrm_setup():
                    print(f"   [OK] WinRM setup successful, retrying connection...")
                    # Retry connection
                    path_success, path_output, path_err = transfer.execute_command(check_path_cmd, timeout=15)
                    if path_success and path_output:
                        print(f"   [OK] Connection established after WinRM setup!")
                    else:
                        print(f"   [FAIL] Still cannot connect after setup")
                        self._show_winrm_help()
                        raise Exception("Cannot communicate with SUT - WinRM setup failed")
                else:
                    self._show_winrm_help()
                    raise Exception("Cannot communicate with SUT - WinRM not accessible")
            
            print(f"   [OK] PowerShell remoting working")
        
        # Continue with EMON check
        self._continue_emon_check(transfer)
    
    def _continue_emon_check(self, transfer):
        """Continue EMON check after connection is working."""
        import re
        
        # Get OS type
        os_info = self.results.get('os_info', {})
        os_type = os_info.get('os_type', 'windows').lower()
        
        # Quick check: just verify emon command exists
        if os_type == 'linux':
            # Source sep_vars.sh if it exists, then check emon
            emon_check_cmd = '''
sep_vars=$(find /opt/intel -name "sep_vars.sh" -type f 2>/dev/null | head -1)
if [ -n "$sep_vars" ]; then
    source "$sep_vars"
    emon -v 2>&1 | head -5
else
    emon -v 2>&1 | head -5
fi
'''
        else:
            emon_check_cmd = 'emon -v'
        
        success, stdout, stderr = transfer.execute_command(emon_check_cmd, timeout=30)
        
        # Debug output
        if self.debug:
            print(f"   [DEBUG] Command success: {success}")
            print(f"   [DEBUG] Stdout length: {len(stdout) if stdout else 0}")
            print(f"   [DEBUG] Stderr: {stderr[:100] if stderr else 'None'}")
            if stdout:
                print(f"   [DEBUG] First 200 chars: {stdout[:200]}")
        
        # Check if EMON is working
        if success and stdout and 'EMON' in stdout.upper() and 'Version' in stdout:
            # EMON found and working!
            print("   [OK] EMON is installed and working")
            return
        
        if not success or not stdout or 'command not found' in stdout.lower() or 'EMON_NOT_FOUND' in stdout:
            # EMON not in PATH - try to find and add it
            print("\n   [WARN]  EMON not in PATH, searching for installation...")
            print(f"   Diagnostic output:\n{stdout[:300] if stdout else 'No output'}\n")
            
            if os_type == 'linux':
                # Linux EMON search
                check_locations_cmd = '''
for path in /opt/intel/sep/bin64/emon /usr/local/bin/emon /opt/intel/vtune_profiler/bin64/emon $HOME/sep/bin64/emon; do
    if [ -f "$path" ]; then
        echo "FOUND:$path"
        exit 0
    fi
done
echo "NOTFOUND"
'''
            else:
                # Windows EMON search
                check_locations_cmd = '''
# Check common EMON installation paths
$paths = @()
if (Test-Path "C:\\Program Files (x86)\\IntelSWTools\\sep\\bin64\\emon.exe") {
    $paths += "C:\\Program Files (x86)\\IntelSWTools\\sep\\bin64"
}
$intelTools = "C:\\Program Files (x86)\\IntelSWTools"
if (Test-Path $intelTools) {
    Get-ChildItem $intelTools -Directory | Where-Object { $_.Name -like "sep*" } | ForEach-Object {
        $binPath = Join-Path $_.FullName "bin64\\emon.exe"
        if (Test-Path $binPath) {
            $paths += Join-Path $_.FullName "bin64"
        }
    }
}
if ($paths.Count -gt 0) {
    Write-Output "FOUND:$($paths[0])"
} else {
    Write-Output "NOTFOUND"
}
'''
            
            found_success, found_output, _ = transfer.execute_command(check_locations_cmd, timeout=20)
            
            if found_success and "FOUND:" in found_output:
                emon_path = found_output.replace("FOUND:", "").strip().split('\n')[0]
                print(f"   [OK] Found EMON at: {emon_path}")
                
                if os_type == 'linux':
                    print(f"   Note: EMON found at {emon_path}")
                    print(f"   You may need to use full path or add to PATH on SUT")
                    # For Linux, try using the full path to verify
                    emon_test = f'{emon_path} -v 2>&1'
                    test_success, test_output, _ = transfer.execute_command(emon_test, timeout=15)
                    if test_success and test_output:
                        print(f"   [OK] EMON accessible at full path")
                        success = True
                        stdout = test_output
                else:
                    print(f"   Adding to PATH...")
                    
                    add_path_cmd = f'''
$oldPath = [Environment]::GetEnvironmentVariable("Path", "Machine")
if ($oldPath -notlike "*{emon_path}*") {{
    $newPath = $oldPath + ";{emon_path}"
    [Environment]::SetEnvironmentVariable("Path", $newPath, "Machine")
}}
$env:Path += ";{emon_path}"
emon -v
'''
                    add_success, add_output, _ = transfer.execute_command(add_path_cmd, timeout=15)
                    
                    if "EMON" in add_output:
                        print(f"   [OK] EMON now accessible")
                        success = True
                        stdout = add_output
            
            if not success or not stdout:
                # Offer to install EMON
                from src.emon_installer import EmonInstaller
                
                print("\n   [WARN]  EMON not found on SUT")
                installer = EmonInstaller(self.sut_ip, username=username, password=password, ssh_key_path=ssh_key_path)
                
                if installer.check_and_install_emon():
                    success, stdout, stderr = transfer.execute_command("emon -v", timeout=15)
                    if not success or not stdout:
                        raise Exception("EMON not available after installation")
                else:
                    raise Exception("EMON not installed on SUT")
        
        # Parse EMON version
        version = None
        sep_version = None
        for line in stdout.split('\n'):
            if 'EMON Version' in line and 'V' in line:
                match = re.search(r'V(\d+\.\d+)', line)
                if match:
                    version = match.group(1)
            elif 'SEP Driver Version' in line:
                match = re.search(r'(\d+\.\d+)', line)
                if match:
                    sep_version = match.group(1)
        
        print(f"   [OK] EMON v{version} (SEP {sep_version})")
    
    def _try_remote_winrm_setup(self):
        """Try to setup WinRM on the SUT remotely using various methods."""
        import subprocess
        from pathlib import Path
        
        print(f"   Trying remote WinRM configuration methods...")
        
        # Method 1: Try using PsExec if available
        try:
            # Check if PsExec is available
            psexec_check = subprocess.run(['where', 'psexec.exe'], 
                                         capture_output=True, text=True, timeout=5)
            
            if psexec_check.returncode == 0:
                print(f"   -> Attempting setup via PsExec...")
                
                setup_cmd = f'''
Enable-PSRemoting -Force -SkipNetworkProfileCheck; 
Set-Item WSMan:\\localhost\\Client\\TrustedHosts -Value '*' -Force; 
Start-Service WinRM; 
Set-Service WinRM -StartupType Automatic
'''
                
                psexec_cmd = [
                    'psexec.exe',
                    f'\\\\{self.sut_ip}',
                    '-s',  # Run as SYSTEM
                    '-accepteula',
                    'powershell.exe',
                    '-Command',
                    setup_cmd
                ]
                
                result = subprocess.run(psexec_cmd, capture_output=True, text=True, timeout=60)
                if result.returncode == 0 or 'WinRM' in result.stdout:
                    print(f"   [OK] WinRM configured via PsExec")
                    return True
        except Exception as e:
            print(f"   [WARN] PsExec method failed: {e}")
        
        # Method 2: Try using WMI
        try:
            print(f"   -> Attempting setup via WMI...")
            
            wmi_script = f'''
$computer = "{self.sut_ip}"
$commands = @(
    "powershell.exe -Command Enable-PSRemoting -Force -SkipNetworkProfileCheck",
    "powershell.exe -Command Set-Item WSMan:\\localhost\\Client\\TrustedHosts -Value '*' -Force",
    "powershell.exe -Command Restart-Service WinRM"
)

foreach ($cmd in $commands) {{
    $process = Invoke-WmiMethod -Class Win32_Process -Name Create -ArgumentList $cmd -ComputerName $computer -ErrorAction Stop
    if ($process.ReturnValue -eq 0) {{
        Write-Output "SUCCESS: $cmd"
    }}
}}
'''
            
            script_path = Path(self.config.get('output_dir', 'output')) / 'temp_wmi_setup.ps1'
            script_path.parent.mkdir(exist_ok=True)
            with open(script_path, 'w', encoding='utf-8') as f:
                f.write(wmi_script)
            
            result = subprocess.run(['powershell.exe', '-ExecutionPolicy', 'Bypass', '-File', str(script_path)],
                                  capture_output=True, text=True, timeout=60)
            
            script_path.unlink(missing_ok=True)
            
            if 'SUCCESS' in result.stdout:
                print(f"   [OK] WinRM configured via WMI")
                import time
                time.sleep(3)  # Give WinRM time to start
                return True
        except Exception as e:
            print(f"   [WARN] WMI method failed: {e}")
        
        # Method 3: Try using scheduled task
        try:
            print(f"   -> Attempting setup via Scheduled Task...")
            
            schtask_cmd = [
                'schtasks.exe',
                '/Create',
                '/S', self.sut_ip,
                '/TN', 'EnableWinRM',
                '/TR', 'powershell.exe -Command "Enable-PSRemoting -Force; Set-Item WSMan:\\localhost\\Client\\TrustedHosts -Value \'*\' -Force; Restart-Service WinRM"',
                '/SC', 'ONCE',
                '/ST', '00:00',
                '/RU', 'SYSTEM',
                '/F'
            ]
            
            result = subprocess.run(schtask_cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0:
                # Run the task
                run_cmd = ['schtasks.exe', '/Run', '/S', self.sut_ip, '/TN', 'EnableWinRM']
                subprocess.run(run_cmd, capture_output=True, text=True, timeout=10)
                
                import time
                time.sleep(5)  # Give it time to execute
                
                # Delete the task
                del_cmd = ['schtasks.exe', '/Delete', '/S', self.sut_ip, '/TN', 'EnableWinRM', '/F']
                subprocess.run(del_cmd, capture_output=True, text=True, timeout=10)
                
                print(f"   [OK] WinRM configured via Scheduled Task")
                return True
        except Exception as e:
            print(f"   [WARN] Scheduled Task method failed: {e}")
        
        print(f"   [FAIL] All remote setup methods failed")
        return False
    
    def _show_winrm_help(self):
        """Show WinRM setup instructions."""
        print(f"\n" + "="*80)
        print(f"   SUT WinRM CONFIGURATION REQUIRED")
        print(f"="*80)
        print(f"\n   This SUT ({self.sut_ip}) requires WinRM to be enabled for remote access.")
        print(f"\n   QUICK SETUP (One-time, 30 seconds):")
        print(f"   ────────────────────────────────────")
        print(f"   1. Connect to SUT via RDP:")
        print(f"      > mstsc /v:{self.sut_ip}")
        print(f"")
        print(f"   2. On the SUT, open PowerShell as Administrator and run:")
        print(f"      > Enable-PSRemoting -Force; Set-Item WSMan:\\localhost\\Client\\TrustedHosts -Value '*' -Force; Restart-Service WinRM")
        print(f"")
        print(f"   That's it! After this one-time setup, the tool works automatically.")
        print(f"")
        print(f"   NOTE: Windows security prevents automated remote WinRM enablement.")
        print(f"         This 30-second manual step is required by Microsoft's design.")
        print(f"\n" + "="*80)
    
    def _validate_emon(self):
        """Validate EMON installation and get hardware configuration."""
        print("[1.6/5] Validating EMON installation...")
        
        from src.remote_transfer import RemoteTransfer
        
        # Get OS info and credentials
        os_info = self.results.get('os_info', {})
        os_type = os_info.get('os_type', 'windows').lower()
        ssh_key_path = self.config.get('ssh_key_path')
        username = self.config.get('username', 'root' if os_type == 'linux' else 'administrator')
        password = self.config.get('password')
        
        transfer = RemoteTransfer(
            self.sut_ip,
            username=username,
            password=password,
            ssh_key_path=ssh_key_path,
            collection_hours=self.config.get('hours')
        )
        
        # Run emon -v to get version and hardware info (wrapped for Linux)
        if os_type == 'linux':
            emon_cmd = '''
sep_vars=$(find /opt/intel -name "sep_vars.sh" -type f 2>/dev/null | head -1)
if [ -n "$sep_vars" ]; then
    source "$sep_vars"
fi
emon -v 2>&1
'''
        else:
            emon_cmd = 'emon -v'
        
        success, stdout, stderr = transfer.execute_command(emon_cmd, timeout=30)
        
        # Check if we got valid EMON output (even if success=False due to SSH warnings)
        # EMON -v output should contain "EMON" or "Version" or "Intel"
        has_emon_output = stdout and any(keyword in stdout for keyword in ['EMON', 'Version', 'Intel', 'cpu_family'])
        
        if not success and not has_emon_output:
            print("\n" + "="*80)
            print("ERROR: EMON VALIDATION FAILED")
            print("="*80)
            print("EMON command found but failed to execute.")
            print("")
            print("Error output:")
            print(stderr[:500] if stderr else "(no error output)")
            print("")
            print("Standard output:")
            print(stdout[:500] if stdout else "(no output)")
            print("")
            print("Please reinstall EMON from: goto/emon")
            print("="*80)
            raise Exception("EMON installation corrupt or incompatible")
        
        # Parse hardware configuration
        hw_config = self._parse_emon_version(stdout)
        self.results['hardware_config'] = hw_config
        
        # Derive product_id for ML trainer
        product_name = hw_config.get('product_name', '')
        if product_name:
            # Normalize: lowercase, replace spaces/hyphens with underscores
            product_id = product_name.lower().replace(' ', '_').replace('-', '_')
            hw_config['product_id'] = product_id
        
        print(f"      EMON Version: {hw_config.get('emon_version', 'Unknown')}")
        print(f"      Product: {hw_config.get('product_name', 'Unknown')}")
        print(f"      Cores: {hw_config.get('total_cores', 'Unknown')} ({hw_config.get('p_cores', 0)}P + {hw_config.get('e_cores', 0)}E)")
        
        # Show PMU units
        pmu_units = hw_config.get('pmu_units', {})
        if pmu_units:
            print(f"      PMU Units: {', '.join(f'{k}({v})' for k, v in pmu_units.items())}")
        
        print()
    
    def _parse_emon_version(self, output):
        """Parse emon -v output to extract hardware configuration."""
        config = {
            'emon_version': None,
            'cpu_family': None,
            'cpu_model': None,
            'cpu_stepping': None,
            'total_cores': None,
            'p_cores': None,
            'e_cores': None,
            'pmu_units': {}
        }
        
        lines = output.split('\n')
        in_pmu_section = False
        
        for line in lines:
            line = line.strip()
            
            # Extract EMON version
            if 'EMON Version' in line and '.' in line:
                parts = line.split('.')
                for i, part in enumerate(parts):
                    if 'V' in part or 'v' in part:
                        try:
                            version_start = i
                            config['emon_version'] = '.'.join(parts[version_start:version_start+2]).replace('V', '').replace('v', '').strip('. ').split()[0]
                        except:
                            pass
            
            # Extract CPU family
            if 'cpu_family' in line.lower() and 'Intel' in line:
                full_family = line.split('Intel(R)')[-1].strip('. ')
                config['cpu_family'] = full_family
                
                # Extract just the product code name (e.g., "Wildcatlake" from "microarchitecture code named Wildcatlake")
                if 'code named' in full_family or 'code-named' in full_family:
                    parts = full_family.replace('code-named', 'code named').split('code named')
                    if len(parts) > 1:
                        config['product_name'] = parts[-1].strip()
                    else:
                        config['product_name'] = full_family
                else:
                    config['product_name'] = full_family
            
            # Extract core counts
            if 'total_number_of_processors' in line.lower():
                config['total_cores'] = int(line.split('.')[-1].strip())
            
            if 'number_of_processors (P-core)' in line:
                config['p_cores'] = int(line.split('.')[-1].strip())
            
            if 'number_of_processors (E-core)' in line:
                config['e_cores'] = int(line.split('.')[-1].strip())
            
            # Extract PMU units
            if 'Uncore Performance Monitoring Units:' in line:
                in_pmu_section = True
                continue
            
            if in_pmu_section:
                if ':' in line and len(line.split(':')) == 2:
                    unit_name, count = line.split(':')
                    unit_name = unit_name.strip()
                    try:
                        count = int(count.strip())
                        config['pmu_units'][unit_name] = count
                    except:
                        pass
                elif line == '' or 'GPU' in line or 'RAM' in line:
                    in_pmu_section = False
        
        return config
    
    def _discover_domains(self):
        """Discover PMU domains and events."""
        print("[2/5] Discovering PMU domains and events...", flush=True)
        
        analyzer = DomainAnalyzer(self.sut_ip, self.config)
        domain_results = analyzer.analyze_all_domains()
        
        self.results['domains'] = domain_results
        
        # Store domain metadata for report generation
        self.domain_metadata = getattr(analyzer, 'domain_metadata', {})
        
        # Auto-update domain configuration with newly discovered domains
        try:
            from src.domain_config_updater import DomainConfigUpdater
            
            discovered_domains = list(domain_results.keys())
            updater = DomainConfigUpdater()
            result = updater.update_from_discovered_domains(
                discovered_domains, 
                self.domain_metadata,
                dry_run=False
            )
            
            if result['status'] == 'updated':
                print(f"      [OK] Auto-configured {result['new_count']} new domains")
                if self.config.get('debug'):
                    print(f"         New domains: {', '.join(result['new_domains'][:5])}")
                    if len(result['new_domains']) > 5:
                        print(f"         ... and {len(result['new_domains'])-5} more")
        except Exception as e:
            if self.config.get('debug'):
                print(f"      [DEBUG] Domain config auto-update failed: {e}")
        
        # Filter based on config
        if self.config.get('domains_to_analyze') != 'all':
            requested = self.config['domains_to_analyze']
            domain_results = {k: v for k, v in domain_results.items() if k in requested}
        
        available = [d for d, info in domain_results.items() if info.get('available')]
        total_events = sum(len(info['events']) for info in domain_results.values() if info.get('available'))
        
        print(f"      Domains: {len(available)} available")
        print(f"      Events: {total_events} total discovered")
        
        for domain in available[:5]:  # Show first 5
            count = len(domain_results[domain]['events'])
            print(f"        - {domain}: {count} events")
        
        if len(available) > 5:
            print(f"        ... and {len(available)-5} more")
        
        print()
    
    def _print_time_estimate(self):
        """Print estimated collection time based on events and mode."""
        available_domains = {name: data for name, data in self.results['domains'].items() 
                           if data.get('available', False)}
        
        total_events = 0
        for domain_data in available_domains.values():
            events = domain_data.get('events', [])
            max_events = self.config.get('max_events_per_domain', 10000)
            total_events += min(len(events), max_events)
        
        if self.config.get('long_run_mode'):
            # Long-run mode: time-sliced batched collection
            total_hours_requested = self.config.get('long_run_hours', 5)
            
            # Use realistic batch size estimate (auto-tuning happens later, so we estimate)
            # Typical multiplexing results: 4-8 events/batch (use 6 as middle estimate)
            estimated_batch_size = 6
            num_batches = (total_events + estimated_batch_size - 1) // estimated_batch_size
            
            # Time is DIVIDED across batches to fit within requested duration
            hours_per_batch = total_hours_requested / num_batches
            collection_hours = total_hours_requested
            
            # Transfer time: Reading files via SSH is fast (~5-10 seconds per file with deferred mode)
            # Estimate 7 seconds per batch file for SSH cat + parsing
            transfer_seconds = num_batches * 7
            transfer_minutes = transfer_seconds / 60
            
            total_hours = collection_hours + (transfer_minutes / 60)
            total_days = total_hours / 24
            
            print(f"\n      [ESTIMATE] Long-run batched collection:")
            print(f"          Total events: {total_events}")
            print(f"          Batches: ~{num_batches} (estimated {estimated_batch_size} events/batch after auto-tuning)")
            print(f"          Duration/batch: {hours_per_batch:.2f} hours ({hours_per_batch*60:.0f} minutes)")
            print(f"          Collection time: {collection_hours:.1f} hours")
            print(f"          Transfer time: ~{transfer_minutes:.0f} minutes (~{num_batches} files × 7 sec/file)")
            print(f"          TOTAL TIME: {total_hours:.1f} hours ({total_days:.1f} days)")
            
            from datetime import datetime, timedelta
            completion = datetime.now() + timedelta(hours=total_hours)
            print(f"          Estimated completion: {completion.strftime('%Y-%m-%d %H:%M:%S')}")
            print()
        else:
            # Standard mode: fast batch collection
            duration_per_sample = self.config.get('collection_duration', 3)
            num_domains = len(available_domains)
            
            # Check if sequential mode (1 event at a time)
            if self.config.get('sequential_mode', False):
                batch_size_min = 1
                batch_size_max = 1
                batch_size_typical = 1
            else:
                # Batch size determined at runtime via auto-tuning (can be 1-8)
                batch_size_min = 1  # Worst case: auto-tuning fails
                batch_size_max = 8  # Best case: high multiplexing success
                batch_size_typical = 4  # Most common: moderate multiplexing
            
            # Calculate estimates for typical, best, and worst case
            time_per_batch = duration_per_sample + 2  # 2s overhead for command execution
            avg_events_per_domain = total_events / num_domains if num_domains > 0 else 0
            
            # Typical case (most likely)
            batches_typical = ((avg_events_per_domain + batch_size_typical - 1) // batch_size_typical) * num_domains
            collection_typical = (batches_typical * time_per_batch) / 60
            transfer_typical = (batches_typical * 0.2 + 10) / 60
            total_typical = collection_typical + transfer_typical + 1
            
            # Best case
            batches_best = ((avg_events_per_domain + batch_size_max - 1) // batch_size_max) * num_domains
            collection_best = (batches_best * time_per_batch) / 60
            transfer_best = (batches_best * 0.2 + 10) / 60
            total_best = collection_best + transfer_best + 1
            
            # Worst case
            batches_worst = ((avg_events_per_domain + batch_size_min - 1) // batch_size_min) * num_domains
            collection_worst = (batches_worst * time_per_batch) / 60
            transfer_worst = (batches_worst * 0.2 + 10) / 60
            total_worst = collection_worst + transfer_worst + 1
            
            print(f"\n      [ESTIMATE] Standard optimized collection:")
            print(f"          Total events: {total_events}")
            print(f"          Domains: {num_domains}")
            print(f"          Sample duration: {duration_per_sample} seconds")
            print(f"          Batch size: {batch_size_min}-{batch_size_max} events/batch (auto-tuned at runtime)")
            print(f"")
            print(f"          BEST CASE ({batch_size_max} events/batch):")
            print(f"            Batches: ~{int(batches_best)}")
            print(f"            Time: ~{total_best:.0f} minutes ({total_best/60:.1f} hours)")
            print(f"")
            print(f"          TYPICAL CASE ({batch_size_typical} events/batch):")
            print(f"            Batches: ~{int(batches_typical)}")
            print(f"            Time: ~{total_typical:.0f} minutes ({total_typical/60:.1f} hours)")
            print(f"")
            print(f"          WORST CASE ({batch_size_min} event/batch):")
            print(f"            Batches: ~{int(batches_worst)}")
            print(f"            Time: ~{total_worst:.0f} minutes ({total_worst/60:.1f} hours)")
            
            from datetime import datetime, timedelta
            completion_best = datetime.now() + timedelta(minutes=total_best)
            completion_typical = datetime.now() + timedelta(minutes=total_typical)
            completion_worst = datetime.now() + timedelta(minutes=total_worst)
            print(f"")
            print(f"          Estimated completion: {completion_typical.strftime('%Y-%m-%d %H:%M:%S')} (typical)")
            print(f"                         Range: {completion_best.strftime('%H:%M')} - {completion_worst.strftime('%H:%M')}")
            print()
    
    def _collect_coverage(self):
        """Collect coverage data from all domains."""
        import time
        collection_start = time.time()
        
        self.progress_tracker.end_phase('initialization')
        self.progress_tracker.start_phase('collection')
        print("\n[3/5] Collecting coverage data...", flush=True)
        
        # Check if long-run mode is enabled and calculate duration
        if self.config.get('long_run_mode'):
            hours = self.config.get('long_run_hours', 1)
            print(f"\n      [MODE] Long-run batched collection ({hours} hours)")
            print(f"      Note: Batch size will be auto-tuned (typically 4-8 events/batch)")
            
            # Store hours for later calculation after auto-tune
            collection_duration = int(hours * 3600)
            self.config['long_run_total_seconds'] = collection_duration
            self.config['long_run_hours'] = hours
            
            # Set expected collection duration in progress tracker for accurate ETA
            self.progress_tracker.collection_duration_seconds = collection_duration
        
        # Add OS type to config for collector
        os_info = self.results.get('os_info', {})
        self.config['os_type'] = os_info.get('os_type', 'windows').lower()
        
        # Store OS type for ML metadata
        self.os_type = os_info.get('os_type', 'windows').lower()
        
        # Skip EMON re-initialization (already done in validation step for ALL modes)
        self.config['skip_emon_init'] = True
        
        # Pass domain data to collector for long-run duration calculation
        self.config['all_domains'] = self.results.get('domains', {})
        
        # Print time estimation (handles both standard and long-run modes internally)
        self._print_time_estimate()
        
        # Set estimated collection duration in progress tracker
        if not self.config.get('long_run_mode'):
            
            # Set estimated collection duration for standard mode (use typical case)
            duration_per_sample = self.config.get('collection_duration', 3)
            available_domains = {name: data for name, data in self.results['domains'].items() 
                               if data.get('available', False)}
            num_domains = len(available_domains)
            total_events = sum(len(d.get('events', [])) for d in available_domains.values())
            avg_events_per_domain = total_events / num_domains if num_domains > 0 else 0
            batch_size_typical = 4 if not self.config.get('sequential_mode', False) else 1
            time_per_batch = duration_per_sample + 2
            batches_typical = ((avg_events_per_domain + batch_size_typical - 1) // batch_size_typical) * num_domains
            estimated_collection_seconds = batches_typical * time_per_batch
            
            # Set in progress tracker for ETA calculation
            self.progress_tracker.collection_duration_seconds = int(estimated_collection_seconds)
        
        # Standard optimized batch collection (works for both modes)
        collector = OptimizedBatchCollector(self.sut_ip, self.config)
        
        all_active = []
        all_inactive = []
        domain_results = {}
        
        available_domains = {name: data for name, data in self.results['domains'].items() 
                           if data.get('available', False)}
        
        # Initialize checkpoint manager for long runs (or always if not disabled)
        if self.enable_checkpoints and not self.checkpoint_manager:
            # Only enable checkpoints for long runs or explicitly requested
            should_checkpoint = (
                self.config.get('long_run_mode', False) or 
                len(available_domains) >= 5 or  # Multi-domain runs benefit from checkpoints
                self.config.get('collection_duration', 3) >= 10  # Longer samples
            )
            
            if should_checkpoint:
                self.checkpoint_manager = CheckpointManager(
                    checkpoint_dir=self.checkpoint_dir,
                    debug=self.debug
                )
                
                # Start checkpoint session
                self.checkpoint_manager.start_session(
                    config=self.config,
                    sut_ip=self.sut_ip,
                    os_type=self.config.get('os_type', 'windows'),
                    hardware_config=self.results.get('hardware_config', {}),
                    domains=self.results.get('domains', {}),
                    stress_detection=self.results.get('stress_detection', {})
                )
        
        # Handle custom event mode
        if self.config.get('custom_event_mode', False):
            custom_events = self.config.get('custom_events', [])
            print(f"\n      [CUSTOM MODE] Filtering to {len(custom_events)} user-specified events")
            
            # Filter domains to only those containing custom events
            filtered_domains = {}
            for domain, domain_data in available_domains.items():
                domain_events = domain_data.get('events', [])
                # Find intersection of domain events with custom events
                matching_events = [e for e in custom_events if e in domain_events]
                if matching_events:
                    filtered_domains[domain] = domain_data.copy()
                    filtered_domains[domain]['events'] = matching_events
                    print(f"         {domain.upper()}: {len(matching_events)} events")
            
            available_domains = filtered_domains
            
            if not available_domains:
                print(f"\n      [ERROR] None of the specified events found in available domains")
                print(f"              Check event names (case-sensitive)")
                return {}, {}
        
        # ALWAYS use deferred transfer mode for multi-domain collections
        # This prevents SSH/WinRM connection issues during long collections
        # All files are collected on SUT first, then transferred in batch at the end
        use_deferred_transfer = len(available_domains) > 1
        
        if use_deferred_transfer:
            print(f"      [MODE] Deferred transfer - collect all files first, transfer at end")
            print(f"              This prevents connection timeouts during long collections")
        else:
            print(f"      [MODE] Single domain - immediate transfer after collection")
        
        # Overall progress tracking
        import time
        total_domains = len(available_domains)
        
        print(f"\n      [PROGRESS] Starting collection: {total_domains} domains")
        print(f"      ")
        
        for i, (domain, domain_data) in enumerate(available_domains.items(), 1):
            events = domain_data.get('events', [])
            
            if not events:
                continue
            
            # Update progress tracker (only show in non-debug mode)
            self.progress_tracker.update_collection_progress(i, total_domains)
            if not self.debug:
                self.progress_tracker.display_progress()
            else:
                # In debug mode, show domain name instead of progress bar
                print(f"\n      [DOMAIN {i}/{total_domains}] {domain.upper()}")
            
            # Limit events based on config
            max_events = self.config.get('max_events_per_domain', 200)
            events = events[:max_events]
            
            # Collect with deferred transfer if multiple domains
            # In debug mode, show detailed per-batch progress (quiet=False)
            # In normal mode, use quiet mode for clean overall progress bar (quiet=True)
            use_quiet_mode = not self.debug
            active, inactive = collector.collect_domain_events(domain, events, defer_transfer=use_deferred_transfer, quiet=use_quiet_mode)
            
            if not use_deferred_transfer:
                # Single domain mode - results already parsed
                all_active.extend(active)
                all_inactive.extend(inactive)
                
                domain_results[domain] = {
                    'active_events': active,
                    'inactive_events': inactive,
                    'total_tested': len(active) + len(inactive),
                    'activity_rate': len(active) / (len(active) + len(inactive)) * 100 if (len(active) + len(inactive)) > 0 else 0
                }
                
                # Save checkpoint after each domain (if enabled)
                if self.checkpoint_manager:
                    # Get health samples if available
                    health_samples = None
                    if hasattr(collector, 'health_monitor') and hasattr(collector.health_monitor, 'health_history'):
                        health_samples = collector.health_monitor.health_history.copy()
                    
                    self.checkpoint_manager.save_domain_checkpoint(
                        domain=domain,
                        active_events=active,
                        inactive_events=inactive,
                        health_samples=health_samples
                    )
        
        # Collection phase complete
        self.progress_tracker.end_phase('collection')
        print()  # Newline after progress bar
        
        # Process all pending transfers if in deferred mode
        if use_deferred_transfer:
            self.progress_tracker.start_phase('transfer')
            self.progress_tracker.display_progress()
            print()
            
            active, inactive, per_domain_data = collector.process_pending_transfers()
            all_active.extend(active)
            all_inactive.extend(inactive)
            
            self.progress_tracker.end_phase('transfer')
            
            # Build domain results from collector's tracking
            for domain, data in per_domain_data.items():
                domain_active = data['active']
                domain_inactive = data['inactive']
                
                domain_results[domain] = {
                    'active_events': domain_active,
                    'inactive_events': domain_inactive,
                    'total_tested': len(domain_active) + len(domain_inactive),
                    'activity_rate': len(domain_active) / (len(domain_active) + len(domain_inactive)) * 100 if (len(domain_active) + len(domain_inactive)) > 0 else 0
                }
        
        collection_time = time.time() - collection_start
        
        # Store stress tracking data from collector
        if hasattr(collector, 'stress_tracking_data') and collector.stress_tracking_data:
            self.results['stress_tracking'] = collector.stress_tracking_data
            if self.debug:
                print(f"\n[STRESS TRACKING] Stored tracking data: {collector.stress_tracking_data.get('final_classification')}")
        
        # Capture final health snapshot and finalize health monitoring
        if hasattr(collector, 'health_monitor'):
            if self.debug:
                print("\n[HEALTH] Capturing final system health snapshot...")
            collector.health_monitor.capture_health_snapshot(
                output_file=None,
                context={'phase': 'collection_end', 'total_active': len(all_active), 'total_inactive': len(all_inactive)}
            )
            
            # Get health data BEFORE finalize (which clears the history)
            health_summary = collector.health_monitor.get_health_summary()
            health_samples = collector.health_monitor.health_history.copy()  # Copy before finalize clears it
            
            # Now finalize (saves and clears)
            collector.health_monitor.finalize()
            print(" [OK]")  # Complete the health monitoring line
            
            # Add health data to results for report generation
            if health_summary and health_samples:
                self.results['health_history'] = {
                    'samples': health_samples,
                    'statistics': health_summary,
                    'collection_mode': collector.health_monitor.collection_mode,
                    'os_type': collector.health_monitor.os_type,
                    'sut_ip': collector.health_monitor.sut_ip
                }
        
        self.results['coverage'] = {
            'total_events_tested': len(all_active) + len(all_inactive),
            'active_events': len(all_active),
            'inactive_events': len(all_inactive),
            'activity_coverage': len(all_active) / (len(all_active) + len(all_inactive)) * 100 if (len(all_active) + len(all_inactive)) > 0 else 0,
            'domain_results': domain_results,
            'all_active': all_active,
            'all_inactive': all_inactive,
            'collection_time_seconds': collection_time
        }
        
        print(f"      Total: {len(all_active)}/{len(all_active)+len(all_inactive)} active ({self.results['coverage']['activity_coverage']:.1f}%)")
        print(f"      Overall collection time: {collection_time/60:.1f} minutes ({collection_time:.0f}s)")
        print()
    
    def _collect_coverage_resume(self, pending_domains: list):
        """Resume coverage collection for pending domains only."""
        import time
        collection_start = time.time()
        
        print(f"\n[RESUME] Collecting remaining {len(pending_domains)} domains...")
        
        # Setup config
        os_info = self.results.get('os_info', {})
        self.config['os_type'] = os_info.get('os_type', 'windows').lower()
        self.config['skip_emon_init'] = True
        self.config['all_domains'] = self.results.get('domains', {})
        
        # Create collector
        collector = OptimizedBatchCollector(self.sut_ip, self.config)
        
        all_active = []
        all_inactive = []
        domain_results = {}
        
        # Filter to only pending domains
        available_domains = {name: data for name, data in self.results['domains'].items() 
                           if data.get('available', False) and name in pending_domains}
        
        total_domains = len(available_domains)
        
        for i, (domain, domain_data) in enumerate(available_domains.items(), 1):
            events = domain_data.get('events', [])
            
            if not events:
                continue
            
            print(f"\n      [RESUME {i}/{total_domains}] {domain.upper()}")
            
            # Limit events based on config
            max_events = self.config.get('max_events_per_domain', 200)
            events = events[:max_events]
            
            # Collect with immediate transfer (checkpointing enabled)
            active, inactive = collector.collect_domain_events(
                domain, events, 
                defer_transfer=False, 
                quiet=not self.debug
            )
            
            all_active.extend(active)
            all_inactive.extend(inactive)
            
            domain_results[domain] = {
                'active_events': active,
                'inactive_events': inactive,
                'total_tested': len(active) + len(inactive),
                'activity_rate': len(active) / (len(active) + len(inactive)) * 100 
                               if (len(active) + len(inactive)) > 0 else 0
            }
            
            # Save checkpoint after each domain
            if self.checkpoint_manager:
                health_samples = None
                if hasattr(collector, 'health_monitor') and hasattr(collector.health_monitor, 'health_history'):
                    health_samples = collector.health_monitor.health_history.copy()
                
                self.checkpoint_manager.save_domain_checkpoint(
                    domain=domain,
                    active_events=active,
                    inactive_events=inactive,
                    health_samples=health_samples
                )
        
        collection_time = time.time() - collection_start
        
        # Capture final health
        if hasattr(collector, 'health_monitor'):
            collector.health_monitor.capture_health_snapshot(
                output_file=None,
                context={'phase': 'resume_collection_end', 'total_active': len(all_active)}
            )
            
            health_summary = collector.health_monitor.get_health_summary()
            health_samples = collector.health_monitor.health_history.copy()
            collector.health_monitor.finalize()
            
            if health_summary and health_samples:
                if 'health_history' not in self.results:
                    self.results['health_history'] = {'samples': []}
                self.results['health_history']['samples'].extend(health_samples)
                self.results['health_history']['statistics'] = health_summary
        
        # Store in results (will be merged with checkpoint data)
        self.results['coverage'] = {
            'total_events_tested': len(all_active) + len(all_inactive),
            'active_events': len(all_active),
            'inactive_events': len(all_inactive),
            'activity_coverage': len(all_active) / (len(all_active) + len(all_inactive)) * 100 
                               if (len(all_active) + len(all_inactive)) > 0 else 0,
            'domain_results': domain_results,
            'all_active': all_active,
            'all_inactive': all_inactive,
            'collection_time_seconds': collection_time
        }
        
        print(f"\n      [RESUME] Completed: {len(all_active)} active events from {len(pending_domains)} domains")
        print(f"      [RESUME] Collection time: {collection_time/60:.1f} minutes")

    def _detect_gaps(self):
        """Detect coverage gaps."""
        print("[4/5] Detecting coverage gaps...", flush=True)
        
        detector = GapDetector(self.config)
        gap_results = detector.analyze_gaps(
            self.results['domains'],
            self.results['coverage']
        )
        
        self.results['gaps'] = gap_results
        
        critical_gaps = len(gap_results.get('critical_gaps', []))
        total_non_toggling = len(gap_results.get('non_toggling_events', []))
        
        print(f"      Non-toggling events: {total_non_toggling}", flush=True)
        print(f"      Critical gaps: {critical_gaps}", flush=True)
        print(flush=True)
    
    def _train_and_analyze_ml(self):
        """Train ML models on collected data and generate ML analysis."""
        self.progress_tracker.start_phase('analysis')
        self.progress_tracker.display_progress()
        print(flush=True)
        print("[4.5/5] Training ML models and generating analysis...", flush=True)
        
        try:
            from src.ml_client import MLClient
            from src.ml_analysis_reporter import MLAnalysisReporter
            
            # Initialize ML client
            ml_client = MLClient(self.config)
            
            if not ml_client.local_models_available:
                print("      [WARN]  ML training not available (install scikit-learn)")
                self.results['ml_analysis'] = {'status': 'unavailable'}
                return
            
            # Prepare metadata for training
            from src.system_context_collector import get_system_context
            
            # Collect enhanced system context for ML
            try:
                system_context = get_system_context()
                if self.debug:
                    cpu_util = system_context.get('workload_profile', {}).get('cpu_utilization_percent', 'N/A')
                    print(f"      [DEBUG] System Context: CPU {system_context.get('thermal_context', {}).get('cpu_temp_current', 'N/A')}°C, "
                          f"Freq {system_context.get('frequency_context', {}).get('current_freq_mhz', 'N/A')} MHz, "
                          f"Mem {system_context.get('memory_context', {}).get('memory_utilization_percent', 'N/A')}%")
                    # Only show CPU utilization if it's actually from stress (not EMON overhead)
                    if self.results.get('stress_detection', {}).get('detected'):
                        print(f"      [DEBUG] CPU Utilization: {cpu_util}% (includes active stress workload)")
                    elif cpu_util != 'N/A' and cpu_util > 30:
                        print(f"      [DEBUG] CPU Utilization: {cpu_util}% (EMON collection + background processes)")
            except Exception as e:
                logger.debug(f"Could not collect system context: {e}")
                system_context = {}
            
            # Instruction mix learning is now handled by InstructionMixLearner during ML training
            # Results are available in training_results['instruction_mix_learning']
            instruction_mix_summary = {}
            
            # Get PMU diagnostics if available (for data quality validation)
            pmu_diagnostics = self.results.get('pmu_diagnostics', {})
            if pmu_diagnostics and self.debug:
                print(f"      [DEBUG] PMU Diagnostics: {pmu_diagnostics.get('root_cause', 'N/A')} "
                      f"(confidence: {pmu_diagnostics.get('confidence_score', 0)*100:.0f}%)")
            
            # AUTOMATIC WORKLOAD DETECTION for ML training
            detected_workload = self._detect_workload_type_ml(self.results.get('coverage', {}))
            if self.debug:
                print(f"      [DEBUG] Auto-detected workload: {detected_workload}")
            
            # ENHANCED: Use stress_tracking data if available (more accurate than old detection)
            stress_tracking = self.results.get('stress_tracking', {})
            if stress_tracking and stress_tracking.get('classification'):
                # Override with accurate stress tracking label
                detected_workload = stress_tracking['classification'].get('label', detected_workload)
                if self.debug:
                    print(f"      [DEBUG] Using stress_tracking workload: {detected_workload}")
            
            metadata = {
                'timestamp': datetime.now().isoformat(),
                'workload': detected_workload,
                'hardware': f"{self.results.get('hardware_info', {}).get('sku_name', 'Unknown')}",
                'duration_seconds': self.results['coverage'].get('collection_time_seconds', 0),  # Use actual collection time, not total execution time
                'os_info': self.results.get('os_info', {}),
                'os_type': getattr(self, 'os_type', 'windows'),
                # Hardware config for product detection
                'hardware_config': self.results.get('hardware_config', {}),
                # Enhanced context for ML intelligence
                'thermal_context': system_context.get('thermal_context', {}),
                'frequency_context': system_context.get('frequency_context', {}),
                'memory_context': system_context.get('memory_context', {}),
                'workload_profile': system_context.get('workload_profile', {}),
                # Comprehensive health metrics for ML training (all 15 metrics)
                'health_metrics': self.results.get('health_history', {}).get('statistics', {}),
                # Individual health samples for detailed correlation analysis
                'health_samples': self.results.get('health_history', {}).get('samples', []),
                # Instruction mix for scenario correlation
                'instruction_mix': instruction_mix_summary,
                # PMU diagnostics for data quality validation (Linux only)
                'pmu_diagnostics': pmu_diagnostics,
                # ENHANCED: Stress tracking data for accurate workload classification
                'stress_tracking': stress_tracking
            }
            
            # Step 1: Save collected data (including gaps for ML training)
            if self.debug:
                print("      [DEBUG] Saving coverage data...")
            
            # ENRICH GAPS WITH PRIORITY LABELS for ML training
            enriched_gaps = self._add_gap_priority_labels(self.results.get('gaps', {}))
            if self.debug:
                labeled_count = sum(1 for g in enriched_gaps.get('non_toggling_events', []) if 'priority' in g)
                print(f"      [DEBUG] Labeled {labeled_count} gaps with priority levels")
            
            # COMPUTE ACTION EFFECTIVENESS from historical coverage improvements
            action_effectiveness = self._compute_action_effectiveness(ml_client)
            if self.debug and action_effectiveness:
                print(f"      [DEBUG] Computed effectiveness for {len(action_effectiveness)} action types")
            
            # Save complete results including gaps for Priority 1 ML models
            complete_data = {
                'coverage': self.results['coverage'],
                'gaps': enriched_gaps,
                'summary': self.results.get('summary', {}),
                'action_effectiveness': action_effectiveness
            }
            ml_client.trainer.save_coverage_data(complete_data, metadata)
            
            # Step 2: Train models on all collected data (including current run with gaps)
            if self.debug:
                print("      [DEBUG] Training ML models...")
            # Pass complete_data so gap prioritizer can train on current run's gaps
            training_results = ml_client.train_models(complete_data, metadata)
            
            if training_results.get('status') == 'success':
                models_trained = len(training_results['session']['models_trained'])
                if self.debug:
                    print(f"      [DEBUG] Successfully trained {models_trained} models")
            else:
                if self.debug:
                    print(f"      [DEBUG] Training status: {training_results.get('status')}")
            
            # Step 3: Generate comprehensive ML analysis
            if self.debug:
                print("      [DEBUG] Generating ML analysis...")
            reporter = MLAnalysisReporter(ml_client, debug=self.debug)
            
            # Pass gap analysis results (including ML anomalies from gap detection)
            gap_results = self.results.get('gaps', {})
            ml_analysis = reporter.generate_full_analysis(
                self.results['coverage'], 
                metadata,
                gap_results=gap_results,  # Include anomalies detected during gap analysis
                training_results=training_results  # Include instruction mix learning results
            )
            
            # Store ML analysis in results
            self.results['ml_analysis'] = ml_analysis
            
            # Print detailed summary
            summary = ml_analysis.get('summary', {})
            training_status = ml_analysis.get('training_status', {})
            
            # Detailed training progress report (debug only)
            if self.debug:
                print(f"\n      {'='*70}")
                print(f"      [DEBUG] ML TRAINING PROGRESS REPORT")
                print(f"      {'='*70}")
                
                models_available = training_status.get('models_available', 0)
                training_sessions = training_status.get('training_sessions', 0)
                datasets_collected = training_status.get('datasets_collected', 0)
                
                # Count actually trained models from current session
                total_trained = 0
                if training_results.get('status') == 'success':
                    trained_list = training_results.get('session', {}).get('models_trained', [])
                    total_trained = len(trained_list)
                
                # All available ML models (13 total)
                all_models = [
                    'anomaly_detector', 'coverage_predictor', 'pattern_classifier', 
                    'event_clusterer', 'stress_correlation_model', 'health_predictor',
                    'gap_prioritizer', 'workload_detector', 'action_prioritizer',
                    'saturation_predictor', 'stress_recommender', 'gap_forecaster',
                    'workload_clusterer'
                ]
                total_models = len(all_models)
                
                print(f"      Models Status:")
                print(f"         {total_trained}/{total_models} models trained in this session")
                if total_trained == total_models:
                    print(f"         [OK] All models successfully trained!")
                elif total_trained >= 10:
                    print(f"         [OK] Most models trained - excellent ML coverage")
                elif total_trained >= 7:
                    print(f"         [WARN]  Good progress - {total_models - total_trained} models pending")
                else:
                    print(f"         [WARN]  Limited training - need more diverse datasets")
                print(f"         {datasets_collected} datasets collected")
                print(f"         {training_sessions} training sessions completed")
                print(f"         Last training: {training_status.get('last_training', 'Never')}")
                
                # Data sufficiency analysis
                print(f"\n      Dataset Maturity Analysis:")
                if datasets_collected < 5:
                    maturity = "INSUFFICIENT"
                    recommendation = "Need 5+ diverse datasets for reliable insights"
                elif datasets_collected < 10:
                    maturity = "DEVELOPING"
                    recommendation = "Collect 10+ datasets across different workloads"
                elif datasets_collected < 20:
                    maturity = "GOOD"
                    recommendation = "Good dataset size, add diverse workloads for better accuracy"
                else:
                    maturity = "EXCELLENT"
                    recommendation = "Sufficient data for high-confidence predictions"
                
                print(f"         Status: {maturity} ({datasets_collected} datasets)")
                print(f"         Recommendation: {recommendation}")
                
                # Recommended data collection strategy
                print(f"\n      Recommended Dataset Collection Strategy:")
                print(f"         1. Different workloads: stress-ng, SuperCollider, MLCTest, Prime95")
                print(f"         2. Different durations: 30s, 1m, 5m, 15m tests")
                print(f"         3. Different hardware: Various SKUs and steppings")
                print(f"         4. Different OS: Windows and Linux variants")
                print(f"         5. Edge cases: Idle, thermal throttling, power limit scenarios")
                
                if datasets_collected >= 20:
                    print(f"         Data collection goals met! Focus on quality and diversity.")
                else:
                    remaining = max(20 - datasets_collected, 0)
                    print(f"         Target: Collect {remaining} more datasets for optimal ML accuracy")
                
                # ML Analysis Results
                print(f"\n      {'='*70}")
                print(f"      [DEBUG] ML ANALYSIS RESULTS")
                print(f"      {'='*70}")
                print(f"         - Anomalies detected: {summary.get('total_anomalies', 0)}")
                print(f"         - Patterns classified: {summary.get('patterns_classified', 0)}")
                print(f"         - Correlations found: {summary.get('correlations_found', 0)}")
                print(f"         - Event clusters: {summary.get('clusters_found', 0)}")
                print(f"         - Recommendations: {summary.get('recommendations_count', 0)}")
                
                # Print high-priority recommendations
                recommendations = ml_analysis.get('recommendations', [])
                high_priority = [r for r in recommendations if r.get('priority') == 'HIGH']
                if high_priority:
                    print(f"\n      {len(high_priority)} HIGH-PRIORITY RECOMMENDATIONS:")
                    for i, rec in enumerate(high_priority[:5], 1):  # Show top 5
                        print(f"         {i}. {rec.get('title')}")
                
                # Also show medium priority if no high priority
                if not high_priority:
                    medium_priority = [r for r in recommendations if r.get('priority') == 'MEDIUM']
                    if medium_priority:
                        print(f"\n      {len(medium_priority)} MEDIUM-PRIORITY RECOMMENDATIONS:")
                        for i, rec in enumerate(medium_priority[:3], 1):  # Show top 3
                            print(f"         {i}. {rec.get('title')}")
                
                print(f"      {'='*70}")
                print()
            
        except ImportError as e:
            print(f"      [WARN]  ML modules not available: {e}")
            self.results['ml_analysis'] = {'status': 'unavailable', 'error': 'ImportError'}
        except Exception as e:
            print(f"      [FAIL] ML analysis failed: {e}")
            import traceback
            traceback.print_exc()
            self.results['ml_analysis'] = {'status': 'error', 'error': str(e)}
    
    def _generate_reports(self):
        """Generate analysis reports."""
        self.progress_tracker.end_phase('analysis')
        self.progress_tracker.start_phase('reporting')
        self.progress_tracker.display_progress()
        print()
        print("[5/5] Generating reports...", flush=True)
        
        # Get debug flag from config
        debug_mode = self.config.get('debug', False)
        
        # Use HTML validation system for quality assurance
        if debug_mode:
            print("\n[VALIDATE] HTML validation enabled (checking report structure)")
        
        try:
            from src.html_validator import HTMLValidationSystem
            from pathlib import Path
            
            # Determine output path
            output_dir = Path('output')
            output_dir.mkdir(exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            html_path = output_dir / f"silicon_coverage_analysis_{timestamp}.html"
            
            # Create HTML validation system with automatic validation
            report_gen_path = Path(__file__).parent / 'src' / 'report_generator.py'
            max_iterations = self.config.get('max_heal_iterations', 3)
            validation_system = HTMLValidationSystem(str(report_gen_path), max_iterations=max_iterations, debug=debug_mode)
            
            # Step 1: Scan and fix report_generator.py source code before generation
            scan_result = validation_system.scan_and_fix()
            
            if scan_result['issues_found'] > 0 and debug_mode:
                print(f"   [OK] Fixed {scan_result['issues_found']} issue(s) in report_generator.py:")
                if scan_result.get('html_issues', 0) > 0:
                    print(f"      * HTML: {scan_result['html_issues']} function(s) fixed")
                if scan_result.get('css_issues', 0) > 0:
                    print(f"      * CSS: {scan_result['css_issues']} function(s) fixed")
                if scan_result.get('js_issues', 0) > 0:
                    print(f"      * JavaScript: {scan_result['js_issues']} function(s) fixed")
                print("   [i]  Changes saved to source code - future reports will be correct")
            elif debug_mode:
                print(f"   [OK] No issues detected in report_generator.py source code")
            
            # Step 2: Generate report normally (using fixed code)
            if debug_mode:
                print("\n Generating HTML report...")
            generator = ReportGenerator(self.config)
            generator.domain_metadata = getattr(self, 'domain_metadata', {})
            reports = generator.generate_all_reports(self.results, self.sut_ip)
            
            # Step 3: Comprehensive validation (HTML + CSS + JavaScript)
            if debug_mode:
                print("\n Validating generated HTML, CSS, and JavaScript...")
            if 'html' in reports:
                html_file = Path(reports['html'])
                if html_file.exists():
                    with open(html_file, 'r', encoding='utf-8') as f:
                        html_content = f.read()
                    
                    # Full document validation
                    val_result = validation_system.validator.validate_full_document(html_content, "Generated Report")
                    
                    if val_result['valid']:
                        print("   [OK] HTML structure valid")
                        if debug_mode:
                            print(f"      * HTML: {'[OK]' if val_result['html']['valid'] else '[WARN]'}")
                            print(f"      * CSS: {'[OK]' if val_result['css']['valid'] else '[WARN]'} ({val_result['css']['blocks_checked']} blocks)")
                            print(f"      * JavaScript: {'[OK]' if val_result['javascript']['valid'] else '[WARN]'} ({val_result['javascript']['blocks_checked']} blocks)")
                    else:
                        if debug_mode:
                            print(f"   [WARN]  Validation found issues:")
                            
                            # Show HTML errors
                            if not val_result['html']['valid']:
                                print(f"      HTML: {len(val_result['html']['errors'])} error(s)")
                                for error in val_result['html']['errors'][:2]:
                                    print(f"         * {error}")
                            
                            # Show CSS errors
                            if not val_result['css']['valid']:
                                print(f"      CSS: {len(val_result['css']['errors'])} error(s)")
                                for error in val_result['css']['errors'][:2]:
                                    print(f"         * {error}")
                            
                            # Show JS errors
                            if not val_result['javascript']['valid']:
                                print(f"      JavaScript: {len(val_result['javascript']['errors'])} error(s)")
                                for error in val_result['javascript']['errors'][:2]:
                                    print(f"         * {error}")
                        
                        # Auto-fix the generated HTML file only (source already fixed in step 1)
                        if debug_mode:
                            print("\n Auto-fixing detected issues in generated HTML...")
                        
                        fixed_html, fix_report = validation_system.validator.auto_fix_full_document(html_content)
                        
                        if fix_report['fixed']:
                            if debug_mode:
                                print(f"   [OK] Applied {len(fix_report['fixes_applied'])} fix(es) to HTML output:")
                                for fix in fix_report['fixes_applied']:
                                    print(f"      * {fix}")
                            
                            # Write fixed HTML back to file
                            with open(html_file, 'w', encoding='utf-8') as f:
                                f.write(fixed_html)
                            
                            if debug_mode:
                                print(f"   [OK] Fixed report saved: {html_file}")
                            
                            # Re-validate
                            revalidation = validation_system.validator.validate_full_document(fixed_html, "Fixed Report")
                            
                            if revalidation['valid']:
                                if debug_mode:
                                    print("   [OK] All issues resolved!")
                            else:
                                if debug_mode:
                                    print(f"   [i]  {len(revalidation['errors'])} minor issue(s) remaining (may need manual review)")
                        else:
                            if debug_mode:
                                print("   [i]  No runtime auto-fixes needed")
            
            if debug_mode:
                print(f"\n[OK] Report generation complete!")
            
        except Exception as e:
            print(f"\n[WARN]  Validation error: {e}")
            if debug_mode:
                print("   Falling back to standard generation...")
            
            # Fallback to normal generation
            generator = ReportGenerator(self.config)
            generator.domain_metadata = getattr(self, 'domain_metadata', {})
            reports = generator.generate_all_reports(self.results, self.sut_ip)
        
        for report_type, path in reports.items():
            print(f"      {report_type.upper()}: {path}")
        
        # Note: HTML validation already done by HTMLValidationSystem above
        # No need for second validation pass with HTMLStructureFixer
        
        # Azure upload (if enabled)
        self._upload_to_azure(reports)
        
        print()
        return reports
    
    def _print_summary(self):
        """Print analysis summary."""
        self.progress_tracker.end_phase('reporting')
        self.progress_tracker.display_progress()
        print("\n")
        
        if not self.debug:
            # Non-debug mode: Just show completion
            print("="*80)
            print("ANALYSIS COMPLETE")
            print("="*80)
            return
        
        # Debug mode: Show detailed summary
        print("="*80)
        print("ANALYSIS COMPLETE")
        print("="*80)
        
        coverage = self.results['coverage']
        gaps = self.results['gaps']
        stress_info = self.results.get('stress_detection', {})
        os_info = self.results.get('os_info', {})
        total_time = self.results.get('total_execution_time_seconds', 0)
        
        # Format time as HH:MM:SS
        hours = int(total_time // 3600)
        minutes = int((total_time % 3600) // 60)
        seconds = int(total_time % 60)
        time_str = f"{hours}:{minutes:02d}:{seconds:02d}"
        
        print(f"  SUT: {self.sut_ip}")
        
        # OS information
        if os_info.get('detected'):
            os_display = f"{os_info.get('os_name', 'Unknown')} {os_info.get('os_version', '')}".strip()
            if os_info.get('os_type') == 'Linux' and os_info.get('kernel_version'):
                os_display += f" (Kernel {os_info.get('kernel_version')})"
            print(f"  OS: {os_display}")
        
        print(f"  Total Execution Time: {time_str} (HR:MIN:SEC)")
        
        # Workload information (informational only)
        if stress_info.get('detected'):
            print(f"  Workload: {stress_info.get('primary_stress', 'Unknown')} (detected)")
        else:
            print(f"  Workload: Idle/Baseline (no active stress detected)")
        
        print(f"  Events Tested: {coverage['total_events_tested']}")
        print(f"  Active Events: {coverage['active_events']}")
        print(f"  Activity Coverage: {coverage['activity_coverage']:.1f}%")
        print(f"  Non-toggling Events: {coverage['inactive_events']}")
        print(f"  Critical Gaps: {len(gaps.get('critical_gaps', []))}")
        print()
        
        # Domain breakdown
        print("  Per-Domain Activity:")
        for domain, stats in coverage['domain_results'].items():
            print(f"    {domain:15s}: {stats['activity_rate']:5.1f}%  ({stats['total_tested']} tested)")
        
        # Overall top events across all domains
        print()
        print("  TOP 20 HOTTEST EVENTS (All Domains):")
        all_active = coverage.get('all_active', [])
        sorted_all = sorted(all_active, key=lambda x: x['total_activity'], reverse=True)[:20]
        
        for i, event_data in enumerate(sorted_all, 1):
            event_name = event_data['event']
            total_count = event_data['total_activity']
            max_core = event_data.get('max_core_count', 0)
            avg_core = event_data.get('avg_core_count', 0)
            active_cores = event_data.get('active_cores', 0)
            total_cores = event_data.get('total_cores', 0)
            
            print(f"    {i:2d}. {event_name:50s}")
            print(f"        Total: {total_count:,} | Avg/Core: {avg_core:,} | Max/Core: {max_core:,} | {active_cores}/{total_cores} cores active")
        
        # Workload analysis
        print()
        print("  WORKLOAD SIGNATURE:")
        self._analyze_workload(sorted_all)
        
        print("="*80)
    
    def _analyze_workload(self, top_events):
        """Analyze workload characteristics based on top events."""
        if not top_events:
            print("    Unable to determine - no active events")
            return
        
        # Extract event names
        event_names = [e['event'] for e in top_events[:10]]
        
        # Workload indicators
        compute_indicators = ['INST_RETIRED', 'UOPS_RETIRED', 'ARITH', 'FP_', 'INT_VEC']
        memory_indicators = ['MEM_LOAD', 'MEM_STORE', 'MEM_TRANS', 'L1D', 'L2_', 'L3_']
        cache_indicators = ['LONGEST_LAT_CACHE', 'L2_LINES', 'L3_LINES', 'LLC']
        branch_indicators = ['BR_INST', 'BR_MISP']
        frontend_indicators = ['FRONTEND', 'ICACHE', 'ITLB', 'FETCH']
        backend_indicators = ['BACKEND', 'RESOURCE_STALLS', 'RS_EVENTS']
        
        # Count matches
        compute_count = sum(1 for e in event_names if any(ind in e for ind in compute_indicators))
        memory_count = sum(1 for e in event_names if any(ind in e for ind in memory_indicators))
        cache_count = sum(1 for e in event_names if any(ind in e for ind in cache_indicators))
        branch_count = sum(1 for e in event_names if any(ind in e for ind in branch_indicators))
        frontend_count = sum(1 for e in event_names if any(ind in e for ind in frontend_indicators))
        backend_count = sum(1 for e in event_names if any(ind in e for ind in backend_indicators))
        
        # Determine workload type
        workload_types = []
        if compute_count >= 3:
            workload_types.append("Compute-Intensive")
        if memory_count >= 3:
            workload_types.append("Memory-Intensive")
        if cache_count >= 2:
            workload_types.append("Cache-Intensive")
        if branch_count >= 2:
            workload_types.append("Branch-Heavy")
        if frontend_count >= 2:
            workload_types.append("Frontend-Bound")
        if backend_count >= 2:
            workload_types.append("Backend-Bound")
        
        if workload_types:
            print(f"    Detected: {', '.join(workload_types)}")
        else:
            print("    Type: Mixed/General Purpose")
        
        # Show top 3 event categories
        categories = {
            'Compute': compute_count,
            'Memory': memory_count,
            'Cache': cache_count,
            'Branch': branch_count,
            'Frontend': frontend_count,
            'Backend': backend_count
        }
        sorted_cats = sorted(categories.items(), key=lambda x: x[1], reverse=True)[:3]
        print(f"    Top Categories: {', '.join([f'{cat} ({cnt})' for cat, cnt in sorted_cats if cnt > 0])}")
    
    def _detect_workload_type_ml(self, coverage_data):
        """Detect workload type from event patterns for ML training.
        
        Returns specific workload type instead of 'unknown' to enable
        Workload Detector ML model training.
        """
        if not coverage_data or 'all_active' not in coverage_data:
            return 'unknown'
        
        # FIRST: Check if any actual stress tests are running
        stress_info = self.results.get('stress_detection', {})
        stress_count = stress_info.get('count', 0)
        
        # If no stress detected, it's idle/baseline - don't infer workload from event patterns
        if stress_count == 0:
            return 'idle'
        
        # If stress detected, try to classify based on stress type
        primary_stress = stress_info.get('primary_stress', '').lower()
        if any(keyword in primary_stress for keyword in ['prime95', 'mprime', 'cpu', 'supercollider']):
            return 'cpu_stress'
        elif any(keyword in primary_stress for keyword in ['memory', 'memtester', 'stream', 'membench']):
            return 'memory_stress'
        elif 'mixed' in primary_stress or stress_count > 1:
            return 'mixed_stress'
        
        # Fallback to event pattern analysis only if stress detected but type unclear
        active_events = coverage_data.get('all_active', [])
        if len(active_events) < 10:
            return 'general_purpose'
        
        # Extract event names
        event_names = [e.get('event', '') for e in active_events[:50]]
        
        # Workload indicators with scoring
        workload_scores = {
            'compute_intensive': 0,
            'memory_intensive': 0,
            'cache_intensive': 0,
            'branch_heavy': 0,
            'frontend_bound': 0,
            'backend_bound': 0,
            'io_intensive': 0,
            'mixed_workload': 0
        }
        
        # Pattern matching with weights
        patterns = {
            'compute_intensive': ['INST_RETIRED', 'UOPS_RETIRED', 'ARITH', 'FP_', 'INT_VEC', 'DIV', 'MUL'],
            'memory_intensive': ['MEM_LOAD', 'MEM_STORE', 'MEM_TRANS', 'OFFCORE', 'MEM_INST'],
            'cache_intensive': ['L1D', 'L2_', 'L3_', 'LLC', 'LONGEST_LAT_CACHE', 'CACHE_MISS'],
            'branch_heavy': ['BR_INST', 'BR_MISP', 'BACLEARS', 'BRANCH'],
            'frontend_bound': ['FRONTEND', 'ICACHE', 'ITLB', 'FETCH', 'DECODE'],
            'backend_bound': ['BACKEND', 'RESOURCE_STALLS', 'RS_EVENTS', 'ROB', 'IDQ'],
            'io_intensive': ['IO_', 'CYCLES_DIV', 'PAUSE', 'SERIALIZING']
        }
        
        # Score each workload type
        for workload, indicators in patterns.items():
            for event in event_names:
                for indicator in indicators:
                    if indicator in event:
                        workload_scores[workload] += 1
        
        # Determine primary workload (require at least 3 matches)
        max_score = max(workload_scores.values())
        if max_score < 3:
            return 'general_purpose'
        
        # Get top 2 workload types
        sorted_workloads = sorted(workload_scores.items(), key=lambda x: x[1], reverse=True)
        primary = sorted_workloads[0]
        secondary = sorted_workloads[1]
        
        # If secondary is also high, it's mixed
        if secondary[1] >= max_score * 0.6:
            return 'mixed_workload'
        
        return primary[0]
    
    def _add_gap_priority_labels(self, gap_results):
        """Add priority labels to gaps for ML training.
        
        Labels gaps with priority levels (critical/high/medium/low) based on:
        - Domain criticality
        - Event patterns (memory, compute, cache)
        - Co-occurrence with other gaps
        """
        if not gap_results or 'non_toggling_events' not in gap_results:
            return gap_results
        
        # Load domain priority from config
        config_path = Path(__file__).parent / 'config' / 'domain_config.yaml'
        domain_priority = {'p-core': 3, 'e-core': 2, 'uncore': 3}  # defaults
        try:
            with open(config_path, 'r') as f:
                domain_config = yaml.safe_load(f)
                domain_priority = domain_config.get('domain_priority', domain_priority)
        except Exception as e:
            pass  # Use defaults
        
        # Event criticality patterns
        critical_patterns = ['MEM_LOAD', 'MEM_STORE', 'CACHE_MISS', 'L3_', 'LLC', 'OFFCORE']
        high_patterns = ['BR_MISP', 'INST_RETIRED', 'UOPS_RETIRED', 'STALLS', 'BACKEND']
        medium_patterns = ['L1D', 'L2_', 'FRONTEND', 'DECODE', 'FETCH']
        
        labeled_events = []
        for gap in gap_results.get('non_toggling_events', []):
            event_name = gap.get('event', '')
            domain = gap.get('domain', 'unknown')
            
            # Calculate priority score
            priority_score = 0
            
            # Domain contribution (0-3 points)
            domain_key = domain.lower()
            priority_score += domain_priority.get(domain_key, 1)
            
            # Event pattern contribution (0-3 points)
            if any(pattern in event_name for pattern in critical_patterns):
                priority_score += 3
            elif any(pattern in event_name for pattern in high_patterns):
                priority_score += 2
            elif any(pattern in event_name for pattern in medium_patterns):
                priority_score += 1
            
            # Assign priority label based on score
            if priority_score >= 5:
                priority = 'critical'
            elif priority_score >= 4:
                priority = 'high'
            elif priority_score >= 2:
                priority = 'medium'
            else:
                priority = 'low'
            
            # Add priority to gap
            gap['priority'] = priority
            labeled_events.append(gap)
        
        # Update gap results
        gap_results['non_toggling_events'] = labeled_events
        
        # Add priority breakdown for reporting
        priority_counts = {'critical': 0, 'high': 0, 'medium': 0, 'low': 0}
        for gap in labeled_events:
            priority_counts[gap.get('priority', 'low')] += 1
        gap_results['priority_breakdown'] = priority_counts
        
        return gap_results
    
    def _compute_action_effectiveness(self, ml_client):
        """Compute action effectiveness from coverage improvements.
        
        Analyzes historical runs to determine which action types
        correlate with coverage improvements for Action Prioritizer training.
        """
        try:
            # Load historical data - fix data_dir access
            product_id = self.results.get('metadata', {}).get('product_id', 'unknown')
            backup_dir = Path(r'C:\silicon_coverage_analyzer_data')
            history_dir = backup_dir / 'raw_datasets' / product_id
            
            if not history_dir.exists():
                return {}
            
            history_files = sorted(history_dir.glob("coverage_*.json"))
            if len(history_files) < 2:
                return {}  # Need at least 2 runs to measure improvement
            
            # Calculate coverage improvements between consecutive runs
            effectiveness_scores = {
                'gap_focused': [],
                'workload_change': [],
                'platform_tuning': [],
                'stress_increase': []
            }
            
            for i in range(1, len(history_files)):
                try:
                    with open(history_files[i-1], 'r') as f:
                        prev_run = json.load(f)
                    with open(history_files[i], 'r') as f:
                        curr_run = json.load(f)
                    
                    prev_coverage = prev_run.get('coverage', {}).get('activity_coverage', 0)
                    curr_coverage = curr_run.get('coverage', {}).get('activity_coverage', 0)
                    improvement = curr_coverage - prev_coverage
                    
                    # Infer action type from metadata changes
                    prev_workload = prev_run.get('metadata', {}).get('workload', 'unknown')
                    curr_workload = curr_run.get('metadata', {}).get('workload', 'unknown')
                    
                    prev_gaps = len(prev_run.get('gaps', {}).get('non_toggling_events', []))
                    curr_gaps = len(curr_run.get('gaps', {}).get('non_toggling_events', []))
                    
                    # Score different action types
                    if prev_workload != curr_workload:
                        effectiveness_scores['workload_change'].append(improvement)
                    
                    if curr_gaps < prev_gaps:
                        effectiveness_scores['gap_focused'].append(improvement)
                    
                    # Platform tuning if coverage improved significantly
                    if improvement > 2.0:
                        effectiveness_scores['platform_tuning'].append(improvement)
                    
                    # Stress increase if activity coverage increased
                    if improvement > 0:
                        effectiveness_scores['stress_increase'].append(improvement)
                        
                except Exception as e:
                    continue
            
            # Calculate average effectiveness for each action type
            action_effectiveness = {}
            for action_type, improvements in effectiveness_scores.items():
                if improvements:
                    avg_improvement = sum(improvements) / len(improvements)
                    action_effectiveness[action_type] = {
                        'avg_coverage_improvement': avg_improvement,
                        'sample_count': len(improvements),
                        'effectiveness_score': max(0, min(100, 50 + avg_improvement * 10))
                    }
            
            return action_effectiveness
            
        except Exception as e:
            if self.debug:
                print(f"      [DEBUG] Could not compute action effectiveness: {e}")
            return {}
    
    def _upload_to_azure(self, reports: dict):
        """Upload analysis results to Azure if configured."""
        if not self.azure or not self.azure.enabled:
            return
        
        try:
            print()
            print("="*80)
            print("AZURE UPLOAD")
            print("="*80)
            
            urls = self.azure.upload_analysis_results(
                analysis_results=self.results,
                sut_ip=self.sut_ip,
                report_paths=reports
            )
            
            if urls:
                print(f"  [OK] Results uploaded to Azure Storage")
                if 'html' in urls:
                    print(f"     HTML Report: {urls['html']}")
                if 'json' in urls:
                    print(f"     JSON Data: {urls['json']}")
                if 'csv_files' in urls:
                    print(f"     CSV Files: {len(urls['csv_files'])} files")
                print(f"     Metrics: Stored in Table Storage")
            else:
                print(f"  [i] Azure upload skipped")
            
        except Exception as e:
            print(f"  [WARN] Azure upload failed: {e}")
            if self.debug:
                import traceback
                traceback.print_exc()



def load_config(config_path=None):
    """Load configuration."""
    default_config = {
        'collection_duration': 3,
        'min_activity_threshold': 100,
        'max_events_per_domain': 10000,
        'domains_to_analyze': 'all',
        'output_format': ['json', 'html'],
        'use_modular_report': True  # Enable modular tab generation by default
    }
    
    if config_path and Path(config_path).exists():
        with open(config_path, 'r') as f:
            custom_config = json.load(f)
            default_config.update(custom_config)
    
    # Load SUT configuration (credentials, SSH keys, etc.)
    import yaml
    sut_config_path = Path(__file__).parent / "config" / "sut_config.yaml"
    if sut_config_path.exists():
        with open(sut_config_path, 'r') as f:
            sut_config = yaml.safe_load(f)
            if sut_config and 'sut' in sut_config:
                # Store all credential options for OS-specific selection later
                default_config['windows_username'] = sut_config['sut'].get('windows_username', 'Administrator')
                default_config['windows_password'] = sut_config['sut'].get('windows_password', '')
                default_config['linux_username'] = sut_config['sut'].get('linux_username', 'root')
                default_config['linux_password'] = sut_config['sut'].get('linux_password', 'svsos')
                default_config['ssh_key_path'] = sut_config['sut'].get('ssh_key_path')
                
                # Legacy support: set defaults from old fields if present
                default_config['username'] = sut_config['sut'].get('username', 'root')
                default_config['password'] = sut_config['sut'].get('password', 'svsos')
    
    # Load ML API configuration
    ml_config_path = Path(__file__).parent / "config" / "ml_config.yaml"
    if ml_config_path.exists():
        try:
            with open(ml_config_path, 'r') as f:
                ml_config = yaml.safe_load(f)
                if ml_config:
                    default_config['ml_api'] = ml_config.get('ml_api', {})
                    default_config['training_data'] = ml_config.get('training_data', {})
                    default_config['baseline_tracking'] = ml_config.get('baseline_tracking', {})
                    if default_config['ml_api'].get('enabled', False):
                        print("[CONFIG] [OK] ML API enabled")
        except Exception as e:
            print(f"[CONFIG] [WARN] Could not load ML config: {e}")
    
    return default_config


def main():
    """Main entry point."""
    # Check if we need admin rights for TrustedHosts configuration
    if not is_admin():
        # Check if TrustedHosts needs configuration
        import subprocess
        try:
            result = subprocess.run(
                ['powershell', '-NoProfile', '-Command', 
                 'Get-Item WSMan:\\localhost\\Client\\TrustedHosts | Select-Object -ExpandProperty Value'],
                capture_output=True,
                text=True,
                timeout=10
            )
            current_hosts = result.stdout.strip()
            
            # Check if any SUT IP is specified in command line
            sut_ip_specified = '--sut-ip' in sys.argv
            
            if sut_ip_specified:
                sut_idx = sys.argv.index('--sut-ip')
                if sut_idx + 1 < len(sys.argv):
                    sut_ip = sys.argv[sut_idx + 1]
                    
                    # Check if configuration needed
                    if current_hosts != '*' and sut_ip not in current_hosts:
                        print("="*80)
                        print("ADMINISTRATOR RIGHTS NEEDED")
                        print("="*80)
                        print(f"\nFirst-time setup requires admin rights to configure WinRM.")
                        print(f"The tool will now request administrator elevation...")
                        print("\nClick 'Yes' on the UAC prompt to continue.\n")
                        
                        # Self-elevate
                        elevate_and_rerun()
                        return 0
        except:
            pass
    
    parser = argparse.ArgumentParser(
        description='Analyze silicon coverage and identify non-toggling EMON events',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic analysis (10 seconds per batch, ~4 events collected in parallel)
  python analyze_coverage.py --duration 10
  
  # Sequential mode (1 event at a time - thorough but slower)
  python analyze_coverage.py --duration 10 --sequential
  
  # Analyze specific domains only
  python analyze_coverage.py --domains p-core,e-core,imc --duration 10
  
  # Long run (2 hours)
  python analyze_coverage.py --hours 2
  
  # Debug mode with logs
  python analyze_coverage.py --duration 10 --debug
  
  # Quick test (limit 10 events per domain)
  python analyze_coverage.py --duration 10 --max-events 10
  
  # Train Action Prioritizer ML model (log which actions improved coverage)
  python analyze_coverage.py --log-feedback
        """
    )
    
    # Essential arguments
    parser.add_argument('--duration', type=int, default=10, help='Collection duration per batch in seconds (default: 10)')
    parser.add_argument('--hours', type=float, help='Total run duration in hours (for long runs, min: 1 hour)')
    parser.add_argument('--domains', help='Comma-separated domains to analyze (default: all)')
    parser.add_argument('--debug', action='store_true', help='Enable debug output and logging')
    
    # SUT connection (usually auto-detected from config)
    parser.add_argument('--sut-ip', help='SUT IP address (overrides config)')
    parser.add_argument('--username', help='SUT username (overrides config)')
    parser.add_argument('--password', help='SUT password (overrides config)')
    
    # Advanced options
    parser.add_argument('--config', help='Custom configuration file path')
    parser.add_argument('--events', help='Specific events to test (comma-separated)')
    parser.add_argument('--max-events', type=int, help='Maximum events per domain (for quick testing)')
    parser.add_argument('--threshold', type=int, help='Minimum activity threshold (default: 100)')
    parser.add_argument('--sequential', action='store_true', help='Sequential mode: collect 1 event at a time')
    parser.add_argument('--replay', help='Regenerate reports from existing JSON file')
    parser.add_argument('--enable-ml', action='store_true', help='Enable ML-powered analysis')
    parser.add_argument('--resume', metavar='SESSION_ID', help='Resume from checkpoint')
    parser.add_argument('--list-sessions', action='store_true', help='List resumable sessions')
    parser.add_argument('--log-feedback', action='store_true', help='Log feedback for recommended actions (trains Action Prioritizer model)')
    
    args = parser.parse_args()
    
    # Handle --list-sessions
    if args.list_sessions:
        list_resumable_sessions(args.checkpoint_dir)
        return 0
    
    # Handle --log-feedback
    if args.log_feedback:
        from src.ml_action_prioritizer import MLActionPrioritizer
        config = load_config(args.config) if args.config else load_config()
        prioritizer = MLActionPrioritizer(config)
        
        print("\n" + "="*80)
        print("ACTION FEEDBACK LOGGER - Train the Action Prioritizer ML Model")
        print("="*80)
        print("This tool helps train the ML Action Prioritizer by logging which actions")
        print("you took and whether they successfully improved coverage.\n")
        
        # Interactive feedback loop
        while True:
            print("\nAction Types Available:")
            print("  1. run_emon_command    - Ran EMON command from report")
            print("  2. adjust_workload     - Changed stress test/workload")
            print("  3. fix_configuration   - Fixed PMU/PEBS/system config")
            print("  4. increase_duration   - Extended collection time")
            print("  5. reboot_system       - Rebooted SUT to clear state")
            print("  6. update_driver       - Updated EMON/driver version")
            print("  7. other               - Other action")
            print("  q. Quit\n")
            
            choice = input("Select action type (1-7, or q): ").strip()
            
            if choice.lower() == 'q':
                print("\n[OK] Feedback logging complete!")
                print(f"Feedback saved to: {prioritizer.feedback_log}")
                print("\nRun analysis again to retrain the Action Prioritizer model.\n")
                return 0
            
            action_map = {
                '1': 'run_emon_command',
                '2': 'adjust_workload',
                '3': 'fix_configuration',
                '4': 'increase_duration',
                '5': 'reboot_system',
                '6': 'update_driver',
                '7': 'other'
            }
            
            if choice not in action_map:
                print("[FAIL] Invalid choice. Please select 1-7 or q.")
                continue
            
            action_type = action_map[choice]
            
            # Ask if it was successful
            was_fixed = input(f"\nDid '{action_type}' improve coverage? (y/n): ").strip().lower() == 'y'
            
            # Optional: ask for time taken
            fix_time = input("How long did it take? (hours, press Enter to skip): ").strip()
            fix_time_hours = float(fix_time) if fix_time and fix_time.replace('.', '').isdigit() else None
            
            # Log the feedback
            prioritizer.log_feedback(action_type, was_fixed, fix_time_hours)
            
            print(f"[OK] Logged: {action_type} -> {'SUCCESS' if was_fixed else 'NO IMPROVEMENT'}")
            
            # Ask if they want to log more
            more = input("\nLog another action? (y/n): ").strip().lower()
            if more != 'y':
                print("\n[OK] Feedback logging complete!")
                print(f"Feedback saved to: {prioritizer.feedback_log}")
                print("\nRun analysis again to retrain the Action Prioritizer model.\n")
                return 0
    
    # Auto-cleanup old output files before starting analysis (30 day retention)
    print("[DEBUG] Starting cleanup check...")
    try:
        from src.output_cleanup import OutputCleanup
        cleanup = OutputCleanup(output_dir='output', retention_days=30)
        print("[DEBUG] Calling auto_cleanup_if_needed...")
        result = cleanup.auto_cleanup_if_needed(max_size_mb=500, max_files=1000)
        print(f"[DEBUG] Cleanup result: {result}")
        if result:
            print(f"[CLEANUP] Deleted {result.get('total_deleted', 0)} old files, freed {result.get('total_size_freed', 0)/(1024*1024):.1f}MB")
        print("[DEBUG] Cleanup completed successfully")
    except Exception as e:
        logger.warning(f"Output cleanup failed (non-critical): {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
    
    print("[DEBUG] After cleanup section...")
    
    # Check if replay mode
    if args.replay:
        from pathlib import Path
        from src.report_generator import ReportGenerator
        
        json_path = Path(args.replay)
        if not json_path.exists():
            print(f"Error: JSON file not found: {json_path}")
            return 1
        
        print(f"\n[REPLAY MODE] Regenerating reports from: {json_path}")
        print("=" * 80)
        
        # Load existing analysis data
        with open(json_path, 'r') as f:
            report_data = json.load(f)
        
        # Extract the actual analysis results (handle both old and new formats)
        if 'detailed_results' in report_data:
            # Old format: data is wrapped in report_metadata + detailed_results
            analysis_results = report_data['detailed_results']
            sut_ip = report_data.get('report_metadata', {}).get('sut_ip', 'unknown')
        else:
            # New format: data is the analysis results directly
            analysis_results = report_data
            sut_ip = report_data.get('hardware_config', {}).get('sut_ip', 'unknown')
        
        # Load config for report generation
        config = load_config(args.config)
        
        # Generate all reports
        from pathlib import Path
        output_dir = Path('output')
        output_dir.mkdir(exist_ok=True)
        
        report_gen = ReportGenerator(config)
        reports = report_gen.generate_all_reports(analysis_results, sut_ip)
        
        print("\n" + "=" * 80)
        print("[COMPLETE] Report regeneration finished!")
        print("\nGenerated files:")
        for report_type, path in reports.items():
            print(f"  [OK] {report_type}: {path}")
        
        return 0
    
    print("[DEBUG] Not in replay mode, loading config...")
    # Load config
    try:
        config = load_config(args.config)
        print(f"[DEBUG] Config loaded successfully")
    except Exception as e:
        print(f"[ERROR] Failed to load config: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    print("[DEBUG] Applying command line overrides...")
    # Apply command line overrides
    if args.sut_ip:
        config['sut_ip_override'] = args.sut_ip
    if args.username:
        config['username'] = args.username
    if args.password:
        config['password'] = args.password
    if args.domains:
        config['domains_to_analyze'] = args.domains.split(',')
    if args.events:
        # Custom event list mode
        event_list = [e.strip() for e in args.events.split(',')]
        config['custom_events'] = event_list
        config['custom_event_mode'] = True
        print(f"[CONFIG] Custom event mode: Testing {len(event_list)} specific events")
        print(f"         Events: {', '.join(event_list[:5])}{'...' if len(event_list) > 5 else ''}")
    if args.duration:
        config['collection_duration'] = args.duration
    if args.max_events:
        config['max_events_per_domain'] = args.max_events
        print(f"[CONFIG] Limiting to {args.max_events} events per domain")
    if args.threshold:
        config['min_activity_threshold'] = args.threshold
    if args.sequential:
        config['sequential_mode'] = True
        print(f"[CONFIG] Sequential mode: 1 event per collection (duration: {args.duration or 10}s per event)")
    if args.hours:
        # Validate minimum 1 hour
        if args.hours < 1.0:
            print("[ERROR] --hours must be at least 1.0 (minimum 1 hour)")
            sys.exit(1)
        # Enable batched collection mode with calculated duration
        config['long_run_mode'] = True
        config['long_run_hours'] = args.hours
        print(f"[CONFIG] Long-run mode: {args.hours} hours using batched collection")
    
    # Set debug mode from command line
    config['debug'] = args.debug
    
    # Enable debug logging to file if --debug is set
    if args.debug:
        try:
            log_file = enable_debug_logging()
            print(f"[DEBUG] All console output will be saved to: {log_file}")
        except Exception as e:
            print(f"[WARNING] Could not enable debug logging: {e}")
    
    # Apply checkpoint settings
    if args.resume:
        config['resume_session_id'] = args.resume
        print(f"[CONFIG] Resume mode: Loading session {args.resume}")
    
    # Apply ML feature flags (--enable-ml enables all ML features) (--enable-ml enables all ML features)
    if args.enable_ml:
        if 'ml_api' not in config:
            config['ml_api'] = {'enabled': True, 'features': {}}
        config['ml_api']['enabled'] = True
        config['ml_api']['features']['anomaly_detection'] = True
        config['ml_api']['features']['coverage_prediction'] = True
        config['ml_api']['features']['workload_recommendation'] = True
        print("[CONFIG] [OK] ML analysis enabled (anomaly detection, coverage prediction, workload recommendations)")
    
    # Run analysis
    print("\n[STARTING] Silicon Coverage Analysis...")
    print(f"[CONFIG] Duration: {config.get('collection_duration', 10)}s, Max events/domain: {config.get('max_events_per_domain', 10000)}")
    try:
        analyzer = SiliconCoverageAnalyzer(config)
        reports = analyzer.run()
        result = 0 if reports else 1
    except Exception as e:
        print(f"\n[ERROR] Analysis failed: {e}")
        import traceback
        traceback.print_exc()
        result = 1
    finally:
        # Ensure all logging handlers are closed first
        import logging
        try:
            logging.shutdown()
        except Exception:
            pass
        
        # Close debug log if it was opened
        if args.debug:
            try:
                close_debug_logging()
                print(f"\n[DEBUG] Log file closed", flush=True)
            except Exception:
                pass  # Ignore cleanup errors
    
    return result


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except Exception:
        sys.exit(1)
