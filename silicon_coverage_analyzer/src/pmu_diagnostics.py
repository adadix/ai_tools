"""
Cross-Platform PMU Diagnostics Module
Validates PMU counter issues and provides root cause analysis for both Linux and Windows.
"""

import logging
from typing import Dict, Any, List, Tuple

logger = logging.getLogger(__name__)


class PMUDiagnostics:
    """Diagnose PMU counter issues on both Linux (kernel competition) and Windows (driver/security issues)."""
    
    def __init__(self, transfer, os_type: str, debug: bool = False):
        self.transfer = transfer
        self.os_type = os_type
        self.debug = debug
        
    def run_comprehensive_diagnostics(self) -> Dict[str, Any]:
        """
        Run full PMU diagnostics for both Linux and Windows.
        Returns diagnostic report with confidence level for PMU/data collection issues.
        """
        if self.os_type != 'linux':
            # Run Windows-specific diagnostics
            return self._run_windows_diagnostics()
        
        diagnostics = {
            'platform': 'linux',
            'checks_performed': [],
            'issues_found': [],
            'confidence_score': 0.0,
            'pmu_competition_detected': False,
            'root_cause': 'Unknown',
            'recommendations': []
        }
        
        # Check 1: NMI Watchdog Status
        nmi_status = self._check_nmi_watchdog()
        diagnostics['checks_performed'].append('NMI Watchdog')
        diagnostics['nmi_watchdog'] = nmi_status
        if nmi_status['enabled']:
            diagnostics['issues_found'].append('NMI watchdog consuming 1-2 PMU counters')
            diagnostics['confidence_score'] += 0.4
        
        # Check 2: Active perf_event Sessions
        perf_status = self._check_perf_events()
        diagnostics['checks_performed'].append('perf_event subsystem')
        diagnostics['perf_events'] = perf_status
        if perf_status['active_sessions'] > 0:
            diagnostics['issues_found'].append(f"{perf_status['active_sessions']} active perf sessions consuming PMU")
            diagnostics['confidence_score'] += 0.3
        
        # Check 3: Available PMU Counters
        pmu_counters = self._get_available_pmu_counters()
        diagnostics['checks_performed'].append('PMU Counter Availability')
        diagnostics['pmu_counters'] = pmu_counters
        if pmu_counters['available'] < pmu_counters['total'] * 0.7:
            diagnostics['issues_found'].append(f"Only {pmu_counters['available']}/{pmu_counters['total']} PMU counters available")
            diagnostics['confidence_score'] += 0.2
        
        # Check 4: CPU Governor (affects frequency scaling and counter accuracy)
        governor = self._check_cpu_governor()
        diagnostics['checks_performed'].append('CPU Governor')
        diagnostics['cpu_governor'] = governor
        if governor['mode'] in ['powersave', 'ondemand']:
            diagnostics['issues_found'].append(f"CPU governor '{governor['mode']}' may cause counter variability")
            diagnostics['confidence_score'] += 0.1
        
        # Determine root cause confidence
        if diagnostics['confidence_score'] >= 0.7:
            diagnostics['pmu_competition_detected'] = True
            diagnostics['root_cause'] = 'Confirmed Linux Kernel PMU Competition'
        elif diagnostics['confidence_score'] >= 0.4:
            diagnostics['pmu_competition_detected'] = True
            diagnostics['root_cause'] = 'Likely Linux Kernel PMU Competition'
        else:
            diagnostics['root_cause'] = 'Insufficient evidence for PMU competition'
        
        # Generate recommendations
        diagnostics['recommendations'] = self._generate_recommendations(diagnostics)
        
        return diagnostics
    
    def _check_nmi_watchdog(self) -> Dict[str, Any]:
        """Check if NMI watchdog is consuming PMU counters."""
        cmd = 'cat /proc/sys/kernel/nmi_watchdog 2>/dev/null && echo "PMU_COUNT:$(cat /sys/devices/cpu/events/cpu-cycles 2>/dev/null || echo unknown)"'
        success, output, _ = self.transfer.execute_command(cmd, timeout=10)
        
        result = {
            'enabled': False,
            'value': 'unknown',
            'pmu_counter_used': False
        }
        
        if success and output:
            lines = output.strip().split('\n')
            if lines and lines[0].strip() == '1':
                result['enabled'] = True
                result['value'] = '1'
                result['pmu_counter_used'] = True
        
        return result
    
    def _check_perf_events(self) -> Dict[str, Any]:
        """Check for active perf_event sessions consuming PMU."""
        # Check if perf is running
        cmd = '''
ps aux | grep -E "perf (record|stat|top)" | grep -v grep | wc -l
cat /proc/sys/kernel/perf_event_paranoid 2>/dev/null || echo "-1"
'''
        success, output, _ = self.transfer.execute_command(cmd, timeout=10)
        
        result = {
            'active_sessions': 0,
            'paranoid_level': -1,
            'blocking_emon': False
        }
        
        if success and output:
            lines = output.strip().split('\n')
            if len(lines) >= 2:
                try:
                    result['active_sessions'] = int(lines[0].strip())
                    result['paranoid_level'] = int(lines[1].strip())
                    
                    # paranoid > 1 blocks non-root PMU access
                    if result['paranoid_level'] > 1:
                        result['blocking_emon'] = True
                except ValueError:
                    pass
        
        return result
    
    def _get_available_pmu_counters(self) -> Dict[str, Any]:
        """Estimate available PMU counters vs total."""
        # Try to read CPU PMU info
        cmd = '''
# Get CPU model to estimate PMU counters
model=$(cat /proc/cpuinfo | grep "model name" | head -1 | awk -F: '{print $2}')
echo "CPU:$model"

# Check perf list to see available events (indirect measure)
perf list 2>/dev/null | grep -c "Hardware event" || echo "0"

# Check if PMU is accessible
cat /sys/devices/cpu/type 2>/dev/null || echo "unknown"
'''
        success, output, _ = self.transfer.execute_command(cmd, timeout=15)
        
        result = {
            'total': 8,  # Conservative estimate for modern CPUs
            'available': 6,  # Assume 2 reserved (NMI watchdog)
            'cpu_model': 'Unknown'
        }
        
        if success and output:
            for line in output.split('\n'):
                if line.startswith('CPU:'):
                    result['cpu_model'] = line.replace('CPU:', '').strip()
                    # Estimate based on CPU generation
                    if 'Intel' in result['cpu_model']:
                        if any(gen in result['cpu_model'] for gen in ['Xeon', 'Core i9', 'Core i7']):
                            result['total'] = 8  # Newer Intel CPUs
                        else:
                            result['total'] = 4  # Older or lower-end
        
        return result
    
    def _check_cpu_governor(self) -> Dict[str, Any]:
        """Check CPU frequency governor (affects counter stability)."""
        cmd = 'cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor 2>/dev/null || echo "unknown"'
        success, output, _ = self.transfer.execute_command(cmd, timeout=10)
        
        result = {
            'mode': 'unknown',
            'optimal': False
        }
        
        if success and output:
            mode = output.strip().lower()
            result['mode'] = mode
            # performance mode is best for PMU accuracy
            result['optimal'] = (mode == 'performance')
        
        return result
    
    def _generate_recommendations(self, diagnostics: Dict[str, Any]) -> List[str]:
        """Generate actionable recommendations based on diagnostics."""
        recommendations = []
        
        # NMI Watchdog
        if diagnostics['nmi_watchdog']['enabled']:
            recommendations.append(
                "CRITICAL: Disable NMI watchdog to free PMU counters:\n"
                "  echo 0 > /proc/sys/kernel/nmi_watchdog\n"
                "  (Re-enable after: echo 1 > /proc/sys/kernel/nmi_watchdog)"
            )
        
        # Active perf sessions
        if diagnostics['perf_events']['active_sessions'] > 0:
            recommendations.append(
                f"WARNING: {diagnostics['perf_events']['active_sessions']} active perf sessions detected.\n"
                "  Kill competing perf processes: pkill perf"
            )
        
        # CPU Governor
        if not diagnostics['cpu_governor']['optimal']:
            recommendations.append(
                f"OPTIMIZATION: CPU governor is '{diagnostics['cpu_governor']['mode']}' (not optimal).\n"
                "  Set to performance mode for stable PMU counters:\n"
                "  echo performance > /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor"
            )
        
        # General
        if diagnostics['pmu_competition_detected']:
            recommendations.append(
                "SUMMARY: Linux kernel PMU competition confirmed.\n"
                f"  Confidence: {diagnostics['confidence_score']*100:.0f}%\n"
                "  This is NOT an EMON bug - it's architectural Linux kernel behavior."
            )
        
        return recommendations
    
    def _run_windows_diagnostics(self) -> Dict[str, Any]:
        """
        Run Windows-specific PMU diagnostics.
        Windows issues: Driver problems, security software interference, Hyper-V conflicts.
        """
        diagnostics = {
            'platform': 'windows',
            'checks_performed': [],
            'issues_found': [],
            'confidence_score': 0.0,
            'data_quality_issue_detected': False,
            'root_cause': 'Unknown',
            'recommendations': []
        }
        
        # Check 1: EMON Driver Status
        driver_status = self._check_windows_driver()
        diagnostics['checks_performed'].append('EMON Driver')
        diagnostics['emon_driver'] = driver_status
        if not driver_status['loaded']:
            diagnostics['issues_found'].append('EMON driver not loaded or failed to initialize')
            diagnostics['confidence_score'] += 0.5
        
        # Check 2: Hyper-V Status (blocks PMU access)
        hyperv_status = self._check_hyperv()
        diagnostics['checks_performed'].append('Hyper-V')
        diagnostics['hyperv'] = hyperv_status
        if hyperv_status['enabled']:
            diagnostics['issues_found'].append('Hyper-V enabled (blocks PMU counter access)')
            diagnostics['confidence_score'] += 0.4
        
        # Check 3: Antivirus/Security Software
        av_status = self._check_security_software()
        diagnostics['checks_performed'].append('Security Software')
        diagnostics['antivirus'] = av_status
        if av_status['blocking_emon']:
            diagnostics['issues_found'].append(f"Security software may block EMON: {', '.join(av_status['detected'])}")
            diagnostics['confidence_score'] += 0.2
        
        # Check 4: Windows Power Plan
        power_status = self._check_power_plan()
        diagnostics['checks_performed'].append('Power Plan')
        diagnostics['power_plan'] = power_status
        if power_status['mode'] != 'High performance':
            diagnostics['issues_found'].append(f"Power plan '{power_status['mode']}' may affect counter accuracy")
            diagnostics['confidence_score'] += 0.1
        
        # Determine root cause confidence
        if diagnostics['confidence_score'] >= 0.7:
            diagnostics['data_quality_issue_detected'] = True
            diagnostics['root_cause'] = 'Confirmed Windows Data Collection Issue'
        elif diagnostics['confidence_score'] >= 0.4:
            diagnostics['data_quality_issue_detected'] = True
            diagnostics['root_cause'] = 'Likely Windows Configuration Issue'
        else:
            diagnostics['root_cause'] = 'No major issues detected'
        
        # Generate recommendations
        diagnostics['recommendations'] = self._generate_windows_recommendations(diagnostics)
        
        return diagnostics
    
    def _check_windows_driver(self) -> Dict[str, Any]:
        """Check if EMON/SEP driver is loaded properly."""
        cmd = 'sc query sep5 2>$null; if ($LASTEXITCODE -eq 0) { "LOADED" } else { "NOT_LOADED" }'
        success, output, _ = self.transfer.execute_command(cmd, timeout=10)
        
        result = {
            'loaded': False,
            'status': 'unknown'
        }
        
        if success and output:
            if 'RUNNING' in output or 'LOADED' in output:
                result['loaded'] = True
                result['status'] = 'running'
            elif 'STOPPED' in output:
                result['status'] = 'stopped'
            elif 'NOT_LOADED' in output:
                result['status'] = 'not_installed'
        
        return result
    
    def _check_hyperv(self) -> Dict[str, Any]:
        """Check if Hyper-V is enabled (blocks PMU)."""
        cmd = 'Get-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V-Hypervisor -ErrorAction SilentlyContinue | Select-Object -ExpandProperty State'
        success, output, _ = self.transfer.execute_command(cmd, timeout=15)
        
        result = {
            'enabled': False,
            'state': 'unknown'
        }
        
        if success and output:
            state = output.strip().lower()
            result['state'] = state
            result['enabled'] = ('enabled' in state)
        
        return result
    
    def _check_security_software(self) -> Dict[str, Any]:
        """Check for antivirus/security software that may interfere."""
        cmd = '''
$av = Get-CimInstance -Namespace root/SecurityCenter2 -ClassName AntiVirusProduct -ErrorAction SilentlyContinue
if ($av) { $av.displayName -join "," } else { "NONE" }
'''
        success, output, _ = self.transfer.execute_command(cmd, timeout=15)
        
        result = {
            'detected': [],
            'blocking_emon': False
        }
        
        if success and output and output.strip() != 'NONE':
            av_list = [av.strip() for av in output.split(',') if av.strip()]
            result['detected'] = av_list
            
            # Known problematic AV software
            blocking_av = ['McAfee', 'Symantec', 'Kaspersky', 'Bitdefender']
            result['blocking_emon'] = any(av_name in ' '.join(av_list) for av_name in blocking_av)
        
        return result
    
    def _check_power_plan(self) -> Dict[str, Any]:
        """Check Windows power plan (affects CPU frequency/PMU)."""
        cmd = 'powercfg /getactivescheme'
        success, output, _ = self.transfer.execute_command(cmd, timeout=10)
        
        result = {
            'mode': 'unknown',
            'optimal': False
        }
        
        if success and output:
            if 'High performance' in output:
                result['mode'] = 'High performance'
                result['optimal'] = True
            elif 'Balanced' in output:
                result['mode'] = 'Balanced'
            elif 'Power saver' in output:
                result['mode'] = 'Power saver'
        
        return result
    
    def _generate_windows_recommendations(self, diagnostics: Dict[str, Any]) -> List[str]:
        """Generate Windows-specific recommendations."""
        recommendations = []
        
        # Driver issues
        if not diagnostics['emon_driver']['loaded']:
            recommendations.append(
                "CRITICAL: EMON driver not loaded.\n"
                "  Restart EMON or reinstall SEP driver package.\n"
                "  Check: sc query sep5"
            )
        
        # Hyper-V
        if diagnostics['hyperv']['enabled']:
            recommendations.append(
                "CRITICAL: Hyper-V is enabled (blocks PMU counters).\n"
                "  Disable Hyper-V to enable hardware PMU access:\n"
                "  Disable-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V-Hypervisor\n"
                "  (Requires reboot)"
            )
        
        # Security software
        if diagnostics['antivirus']['blocking_emon']:
            recommendations.append(
                f"WARNING: Security software may interfere: {', '.join(diagnostics['antivirus']['detected'])}\n"
                "  Add EMON to antivirus exclusions or temporarily disable during collection."
            )
        
        # Power plan
        if not diagnostics['power_plan']['optimal']:
            recommendations.append(
                f"OPTIMIZATION: Power plan is '{diagnostics['power_plan']['mode']}' (not optimal).\n"
                "  Set to High Performance for stable PMU counters:\n"
                "  powercfg /setactive 8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"
            )
        
        # General
        if diagnostics['data_quality_issue_detected']:
            recommendations.append(
                "SUMMARY: Windows configuration issue detected.\n"
                f"  Confidence: {diagnostics['confidence_score']*100:.0f}%\n"
                "  This is NOT an EMON bug - it's system configuration blocking PMU access."
            )
        else:
            recommendations.append(
                "STATUS: No major Windows configuration issues detected.\n"
                "  System appears ready for PMU collection."
            )
        
        return recommendations


def validate_pmu_starvation_data_quality(
    domain: str,
    event: str,
    per_core_counts: List[int],
    collection_duration: int,
    os_type: str,
    pmu_diagnostics: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Validate if all-zero data is truly PMU starvation or other issues.
    Prevents ML from learning false patterns.
    
    Returns:
        validation: {
            'is_pmu_starved': bool,
            'confidence': float (0-1),
            'alternative_causes': List[str],
            'safe_for_ml_training': bool
        }
    """
    validation = {
        'is_pmu_starved': False,
        'confidence': 0.0,
        'alternative_causes': [],
        'safe_for_ml_training': True,
        'status': 'unknown'
    }
    
    # Rule 1: Platform-specific handling
    if os_type != 'linux':
        # Windows - check for system configuration issues
        if not per_core_counts or len(per_core_counts) == 0:
            # 0-byte file on Windows = truly unsupported hardware event
            validation['status'] = 'unsupported'
            validation['alternative_causes'].append('Windows: 0-byte file indicates unsupported hardware event')
            validation['safe_for_ml_training'] = True  # Safe - this is accurate unsupported data
        elif sum(per_core_counts) == 0 and len(per_core_counts) > 0:
            # Has structure but all zeros on Windows - check diagnostics
            if pmu_diagnostics and pmu_diagnostics.get('data_quality_issue_detected'):
                # Windows has configuration issues (Hyper-V, driver, AV)
                validation['status'] = 'windows_config_issue'
                validation['confidence'] = pmu_diagnostics.get('confidence_score', 0.5)
                validation['is_pmu_starved'] = False  # Not PMU starvation, but data quality issue
                validation['alternative_causes'].append(f"Windows: {pmu_diagnostics.get('root_cause', 'Configuration issue')}")
                # Only safe for ML if confidence is high (confirmed root cause)
                validation['safe_for_ml_training'] = (validation['confidence'] >= 0.7)
            else:
                # No diagnostics or no issues - legitimate no activity
                validation['status'] = 'no_activity'
                validation['alternative_causes'].append('Windows: Event supported but workload did not trigger it')
                validation['safe_for_ml_training'] = True
        else:
            # Has activity
            validation['status'] = 'low_activity'
            validation['safe_for_ml_training'] = True
        return validation
    
    # Rule 2: Must be long collection (>= 30s)
    if collection_duration < 30:
        validation['alternative_causes'].append('Collection too short (<30s) for PMU starvation')
        validation['status'] = 'not_pmu_starved'
        return validation
    
    # Rule 3: File must have structure (columns exist)
    if not per_core_counts or len(per_core_counts) == 0:
        validation['alternative_causes'].append('No data structure - likely truly unsupported event')
        validation['status'] = 'unsupported'
        validation['safe_for_ml_training'] = False  # Don't train on truly unsupported events
        return validation
    
    # Rule 4: All values must be zero (not just low activity)
    if sum(per_core_counts) > 0:
        validation['alternative_causes'].append('Has activity - not PMU starved')
        validation['status'] = 'low_activity'
        return validation
    
    # Rule 5: PMU competition must be detected
    if pmu_diagnostics and pmu_diagnostics.get('pmu_competition_detected'):
        validation['is_pmu_starved'] = True
        validation['confidence'] = pmu_diagnostics.get('confidence_score', 0.5)
        validation['status'] = 'pmu_starved'
    else:
        # No PMU competition detected but all zeros - alternative causes
        validation['alternative_causes'].append('All zeros but no PMU competition detected')
        validation['alternative_causes'].append('Possible causes: Event exists but no activity, incorrect event code, or driver issue')
        validation['status'] = 'no_activity_ambiguous'
        validation['safe_for_ml_training'] = False  # Don't train on ambiguous data
    
    # Rule 6: Confidence threshold for ML training
    if validation['is_pmu_starved'] and validation['confidence'] < 0.5:
        validation['safe_for_ml_training'] = False  # Low confidence - don't pollute ML data
        validation['alternative_causes'].append(f"Confidence too low ({validation['confidence']*100:.0f}%) for ML training")
    
    return validation
