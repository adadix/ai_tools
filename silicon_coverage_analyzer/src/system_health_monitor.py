"""
System Health Monitor - Universal monitoring for all collection modes.

Captures comprehensive system metrics during EMON collections for:
1. Real-time health monitoring
2. ML training data
3. Performance diagnostics
4. Failure prediction

Metrics captured:
- File growth (EMON output)
- Disk space (prevent out-of-space)
- EMON process health
- CPU usage
- Memory usage
- Load average
- Network activity
- Temperature (if available)
"""

import json
import time
from datetime import datetime
from pathlib import Path


class SystemHealthMonitor:
    """Universal system health monitoring for all collection modes."""
    
    def __init__(self, transfer, os_type, sut_ip, collection_mode='standard', debug=False):
        """
        Initialize health monitor.
        
        Args:
            transfer: RemoteTransfer instance for SUT communication
            os_type: 'linux' or 'windows'
            sut_ip: SUT IP address
            collection_mode: 'standard', 'optimized', 'longrun', or 'sequential'
            debug: Enable debug output
        """
        self.transfer = transfer
        self.os_type = os_type
        self.sut_ip = sut_ip
        self.collection_mode = collection_mode
        self.debug = debug
        
        # Health history for ML training - use centralized data directory
        self.health_history = []
        
        # Use same base directory as ML training data
        base_data_dir = Path('C:/silicon_coverage_analyzer_data')
        self.health_log_path = base_data_dir / 'health_logs'
        self.health_log_path.mkdir(parents=True, exist_ok=True)
        
        # Collection metadata
        self.collection_start = datetime.now()
        self.last_save_time = time.time()
        self.save_interval_seconds = 300  # Save every 5 minutes
    
    def capture_health_snapshot(self, output_file=None, context=None):
        """
        Capture comprehensive system health snapshot.
        
        Args:
            output_file: Path to EMON output file being monitored
            context: Additional context (e.g., batch number, event name)
        
        Returns:
            dict: Health snapshot with all metrics
        """
        health = {
            'ok': True,
            'timestamp': datetime.now().isoformat(),
            'collection_mode': self.collection_mode,
            'context': context or {},
            'metrics': {}
        }
        
        try:
            if self.os_type == 'linux':
                # Build comprehensive monitoring command
                monitor_cmd = f'''
                echo "===FILE_SIZE==="; stat -c%s "{output_file}" 2>/dev/null || echo "0";
                echo "===DISK_SPACE==="; df /tmp | tail -1 | awk '{{print $2,$3,$4,$5}}';
                echo "===EMON_PROCESS==="; pid=$(pgrep -x emon); if [ -n "$pid" ]; then ps aux | grep "^[^ ]*[ ]*$pid[ ]" | head -1; else echo ""; fi;
                echo "===CPU_USAGE==="; top -bn2 -d 0.5 | grep "Cpu(s)" | tail -1 | sed 's/%.*//g' | awk '{{idle=$8; active=100-idle; printf "%.1f", active}}';
                echo "===MEMORY==="; free -m | grep Mem | awk '{{print $2,$3,$4}}';
                echo "===LOAD_AVG==="; uptime | awk -F'load average:' '{{print $2}}';
                echo "===NETWORK==="; cat /proc/net/dev | grep -vE "lo:|Inter-|face" | head -1 | awk '{{print $2,$10}}';
                echo "===TEMP==="; t=$(sensors 2>/dev/null | grep -i "core 0" | awk '{{print $3}}' | tr -d '+°C'); [ -n "$t" ] && echo "$t" || cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null | awk '{{print int($1/1000)}}' || echo "N/A";
                echo "===DISK_IO==="; iostat -x 1 2 2>/dev/null | grep -E "sda|nvme|xvd" | tail -1 | awk '{{print $4,$5}}' || echo "0 0";
                echo "===CONTEXT_SWITCHES==="; grep ctxt /proc/stat | awk '{{print $2}}';
                echo "===PROCESSES==="; ps aux | wc -l;
                echo "===INTERRUPTS==="; cat /proc/interrupts | tail -n +2 | awk '{{sum=0; for(i=2;i<=NF && $i~/^[0-9]+$/;i++) sum+=$i}} END {{print sum}}';
                ''' if output_file else '''
                echo "===DISK_SPACE==="; df /tmp | tail -1 | awk '{{print $2,$3,$4,$5}}';
                echo "===EMON_PROCESS==="; pgrep -fa emon | grep -v grep | grep -v bash | head -1 || echo "";
                echo "===CPU_USAGE==="; top -bn2 -d 0.5 | grep "Cpu(s)" | tail -1 | sed 's/%.*//g' | awk '{{idle=$8; active=100-idle; printf "%.1f", active}}';
                echo "===MEMORY==="; free -m | grep Mem | awk '{{print $2,$3,$4}}';
                echo "===LOAD_AVG==="; uptime | awk -F'load average:' '{{print $2}}';
                echo "===NETWORK==="; cat /proc/net/dev | grep -vE "lo:|Inter-|face" | head -1 | awk '{{print $2,$10}}';
                echo "===TEMP==="; t=$(sensors 2>/dev/null | grep -i "core 0" | awk '{{print $3}}' | tr -d '+°C'); [ -n "$t" ] && echo "$t" || cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null | awk '{{print int($1/1000)}}' || echo "N/A";
                echo "===DISK_IO==="; iostat -x 1 2 2>/dev/null | grep -E "sda|nvme|xvd" | tail -1 | awk '{{print $4,$5}}' || echo "0 0";
                echo "===CONTEXT_SWITCHES==="; grep ctxt /proc/stat | awk '{{print $2}}';
                echo "===PROCESSES==="; ps aux | wc -l;
                echo "===INTERRUPTS==="; cat /proc/interrupts | tail -n +2 | awk '{{sum=0; for(i=2;i<=NF && $i~/^[0-9]+$/;i++) sum+=$i}} END {{print sum}}';
                '''
            else:
                # Windows PowerShell monitoring with robust CPU detection
                # Commands execute directly in PowerShell context via WinRM/PSRemoting
                monitor_cmd = f'''
Write-Output "===FILE_SIZE==="; Write-Output ((Get-Item "{output_file}" -ErrorAction SilentlyContinue).Length);
Write-Output "===DISK_SPACE==="; $d = Get-PSDrive C; Write-Output "$($d.Used) $($d.Free)";
Write-Output "===EMON_PROCESS==="; $p = Get-Process -Name "*emon*" -ErrorAction SilentlyContinue | Where-Object {{ $_.ProcessName -match 'emon' }} | Select-Object -First 1; if ($p) {{ Write-Output "$($p.Id) $($p.CPU) $([math]::Round($p.WorkingSet64/1MB, 1))" }} else {{ Write-Output "" }};
Write-Output "===CPU_USAGE==="; $cpu = Get-WmiObject Win32_Processor | Measure-Object -Property LoadPercentage -Average | Select-Object -ExpandProperty Average; if ($cpu) {{ Write-Output ([math]::Round($cpu, 1)) }} else {{ Write-Output "0" }};
Write-Output "===MEMORY==="; $os = Get-CimInstance Win32_OperatingSystem; Write-Output "$($os.TotalVisibleMemorySize) $($os.FreePhysicalMemory)";
Write-Output "===DISK_IO==="; $disk = (Get-Counter -Counter '\\PhysicalDisk(_Total)\\Disk Bytes/sec' -SampleInterval 1 -MaxSamples 1 -ErrorAction SilentlyContinue).CounterSamples.CookedValue; if ($disk) {{ Write-Output ([math]::Round($disk / 1MB, 2)) }} else {{ Write-Output "0" }};
Write-Output "===CONTEXT_SWITCHES==="; $ctx = (Get-Counter -Counter '\\System\\Context Switches/sec' -SampleInterval 1 -MaxSamples 1 -ErrorAction SilentlyContinue).CounterSamples.CookedValue; if ($ctx) {{ Write-Output ([math]::Round($ctx)) }} else {{ Write-Output "0" }};
Write-Output "===PROCESSES==="; Write-Output (Get-Process).Count;
Write-Output "===INTERRUPTS==="; $int = (Get-Counter -Counter '\\Processor(_Total)\\Interrupts/sec' -SampleInterval 1 -MaxSamples 1 -ErrorAction SilentlyContinue).CounterSamples.CookedValue; if ($int) {{ Write-Output ([math]::Round($int)) }} else {{ Write-Output "0" }};
'''.strip()
            
            # Execute comprehensive monitoring (with timeout)
            success, output, _ = self.transfer.execute_command(monitor_cmd, timeout=30)
            
            # DEBUG: Log raw command output (first 1000 chars)
            if self.debug:
                if output:
                    debug_output = output[:1000] if len(output) > 1000 else output
                    print(f"\n[DEBUG] Health command output ({len(output)} chars):\n{debug_output}\n")
                else:
                    print(f"[DEBUG] No output from health command! Success={success}")
            
            if success and output:
                # Parse output sections
                sections = output.split('===')
                metrics = health['metrics']
                
                # Add clarification note about CPU metrics
                metrics['note'] = 'CPU utilization (cpu_usage_pct) measures OS workload, NOT EMON coverage. EMON coverage shows % of PMU events monitored (hardware counters), while CPU utilization shows % of CPU time executing vs idle. Both can be valid simultaneously - an idle CPU (0% utilization) can have high EMON coverage (80-90%) because EMON monitors hardware events that occur even when CPU is idle.'
                
                if self.debug:
                    print(f"[DEBUG] Found {len(sections)} sections in output")
                
                # Build a map of markers to their data (next section after marker)
                marker_data = {}
                for idx in range(len(sections) - 1):
                    section = sections[idx].strip()
                    if section in ['FILE_SIZE', 'DISK_SPACE', 'EMON_PROCESS', 'CPU_USAGE', 'MEMORY', 'LOAD_AVG', 'NETWORK', 'TEMP', 'DISK_IO', 'CONTEXT_SWITCHES', 'PROCESSES', 'INTERRUPTS']:
                        # Data is in the next section
                        data = sections[idx + 1].strip()
                        marker_data[section] = data
                        if self.debug:
                            print(f"[DEBUG] {section}: '{data[:80] if len(data) > 80 else data}'")
                
                # Now parse the captured data
                if 'FILE_SIZE' in marker_data:
                    size_str = marker_data['FILE_SIZE'].split('\n')[0].strip()
                    if size_str.isdigit():
                        file_size_bytes = int(size_str)
                        metrics['file_size_mb'] = round(file_size_bytes / (1024 * 1024), 2)
                        metrics['file_size_bytes'] = file_size_bytes
                        # Note: Empty files (0 bytes) are normal for unsupported events - not a health issue
                
                if 'DISK_SPACE' in marker_data:
                    disk_str = marker_data['DISK_SPACE'].split('\n')[0].strip()
                    parts = disk_str.split()
                    
                    if self.os_type == 'linux':
                        # Linux: KB values with usage percentage
                        if len(parts) >= 4:
                            total_kb = int(parts[0]) if parts[0].isdigit() else 0
                            used_kb = int(parts[1]) if parts[1].isdigit() else 0
                            free_kb = int(parts[2]) if parts[2].isdigit() else 0
                            usage_pct = parts[3].rstrip('%')
                            
                            metrics['disk_total_gb'] = round(total_kb / (1024 * 1024), 2)
                            metrics['disk_used_gb'] = round(used_kb / (1024 * 1024), 2)
                            metrics['disk_free_gb'] = round(free_kb / (1024 * 1024), 2)
                            metrics['disk_usage_pct'] = float(usage_pct) if usage_pct.replace('.', '').isdigit() else 0
                            
                            if free_kb < 1048576:  # <1GB free
                                health['ok'] = False
                                health['warning'] = f'Low disk space: {free_kb / 1024:.0f}MB free'
                    else:
                        # Windows: Bytes values (used, free)
                        if len(parts) >= 2:
                            used_bytes = int(parts[0]) if parts[0].isdigit() else 0
                            free_bytes = int(parts[1]) if parts[1].isdigit() else 0
                            total_bytes = used_bytes + free_bytes
                            
                            metrics['disk_total_gb'] = round(total_bytes / (1024 * 1024 * 1024), 2)
                            metrics['disk_used_gb'] = round(used_bytes / (1024 * 1024 * 1024), 2)
                            metrics['disk_free_gb'] = round(free_bytes / (1024 * 1024 * 1024), 2)
                            metrics['disk_usage_pct'] = round((used_bytes / total_bytes * 100), 2) if total_bytes > 0 else 0
                            
                            if free_bytes < 1073741824:  # <1GB free
                                health['ok'] = False
                                health['warning'] = f'Low disk space: {free_bytes / (1024*1024*1024):.1f}GB free'
                
                if 'EMON_PROCESS' in marker_data:
                    emon_str = marker_data['EMON_PROCESS'].split('\n')[0].strip()
                    if self.os_type == 'linux':
                        if emon_str and 'emon' in emon_str:
                            # Parse: user pid %cpu %mem vsz rss tty stat start time command
                            parts = emon_str.split()
                            if len(parts) >= 11:
                                metrics['emon_pid'] = int(parts[1]) if parts[1].isdigit() else 0
                                metrics['emon_cpu_pct'] = float(parts[2]) if parts[2].replace('.', '').isdigit() else 0
                                metrics['emon_mem_pct'] = float(parts[3]) if parts[3].replace('.', '').isdigit() else 0
                                metrics['emon_running'] = True
                        else:
                            metrics['emon_running'] = False
                    else:
                        # Windows: Parse "PID CPU(s) Memory(MB)" format
                        if emon_str:
                            parts = emon_str.split()
                            if len(parts) >= 3:
                                try:
                                    metrics['emon_pid'] = int(parts[0])
                                    metrics['emon_cpu_pct'] = float(parts[1])
                                    metrics['emon_mem_mb'] = float(parts[2])
                                    metrics['emon_running'] = True
                                except (ValueError, IndexError):
                                    metrics['emon_running'] = False
                            else:
                                metrics['emon_running'] = False
                        else:
                            metrics['emon_running'] = False
                
                if 'CPU_USAGE' in marker_data:
                    cpu_str = marker_data['CPU_USAGE'].split('\n')[0].strip()
                    if cpu_str and cpu_str.replace('.', '').replace('-', '').isdigit():
                        metrics['cpu_usage_pct'] = round(float(cpu_str), 2)
                    else:
                        if self.debug:
                            print(f"[DEBUG] CPU_USAGE parsing failed, raw value: '{cpu_str}'")
                
                if 'MEMORY' in marker_data:
                    mem_str = marker_data['MEMORY'].split('\n')[0].strip()
                    parts = mem_str.split()
                    
                    if self.os_type == 'linux':
                        # Linux: MB values (total, used, free)
                        if len(parts) >= 3:
                            total_mb = int(parts[0]) if parts[0].isdigit() else 0
                            used_mb = int(parts[1]) if parts[1].isdigit() else 0
                            free_mb = int(parts[2]) if parts[2].isdigit() else 0
                            
                            metrics['memory_total_gb'] = round(total_mb / 1024, 2)
                            metrics['memory_used_gb'] = round(used_mb / 1024, 2)
                            metrics['memory_free_gb'] = round(free_mb / 1024, 2)
                            metrics['memory_usage_pct'] = round((used_mb / total_mb * 100), 2) if total_mb > 0 else 0
                    else:
                        # Windows: KB values (total, free)
                        if len(parts) >= 2:
                            total_kb = int(parts[0]) if parts[0].isdigit() else 0
                            free_kb = int(parts[1]) if parts[1].isdigit() else 0
                            used_kb = total_kb - free_kb
                            
                            metrics['memory_total_gb'] = round(total_kb / (1024 * 1024), 2)
                            metrics['memory_used_gb'] = round(used_kb / (1024 * 1024), 2)
                            metrics['memory_free_gb'] = round(free_kb / (1024 * 1024), 2)
                            metrics['memory_usage_pct'] = round((used_kb / total_kb * 100), 2) if total_kb > 0 else 0
                
                if 'LOAD_AVG' in marker_data:
                    load_str = marker_data['LOAD_AVG'].split('\n')[0].strip()
                    loads = [x.strip() for x in load_str.split(',')]
                    if len(loads) >= 3:
                        metrics['load_avg_1min'] = float(loads[0]) if loads[0].replace('.', '').replace('-', '').isdigit() else 0
                        metrics['load_avg_5min'] = float(loads[1]) if loads[1].replace('.', '').replace('-', '').isdigit() else 0
                        metrics['load_avg_15min'] = float(loads[2]) if loads[2].replace('.', '').replace('-', '').isdigit() else 0
                
                if 'NETWORK' in marker_data:
                    net_str = marker_data['NETWORK'].split('\n')[0].strip()
                    parts = net_str.split()
                    if len(parts) >= 2:
                        rx_bytes = int(parts[0]) if parts[0].isdigit() else 0
                        tx_bytes = int(parts[1]) if parts[1].isdigit() else 0
                        metrics['network_rx_mb'] = round(rx_bytes / (1024 * 1024), 2)
                        metrics['network_tx_mb'] = round(tx_bytes / (1024 * 1024), 2)
                
                if 'TEMP' in marker_data:
                    temp_str = marker_data['TEMP'].split('\n')[0].strip()
                    if temp_str != 'N/A' and temp_str.replace('.', '').replace('-', '').isdigit():
                        metrics['temperature_c'] = round(float(temp_str), 1)
                
                if 'DISK_IO' in marker_data:
                    dio_str = marker_data['DISK_IO'].split('\n')[0].strip()
                    parts = dio_str.split()
                    if self.os_type == 'linux' and len(parts) >= 2:
                        # Linux iostat: read_mb/s write_mb/s
                        metrics['disk_read_mbps'] = round(float(parts[0]), 2) if parts[0].replace('.', '').isdigit() else 0
                        metrics['disk_write_mbps'] = round(float(parts[1]), 2) if parts[1].replace('.', '').isdigit() else 0
                    elif self.os_type == 'windows' and parts:
                        # Windows: total MB/s
                        total_mbps = float(parts[0]) if parts[0].replace('.', '').isdigit() else 0
                        metrics['disk_io_mbps'] = round(total_mbps, 2)
                
                if 'CONTEXT_SWITCHES' in marker_data:
                    ctx_str = marker_data['CONTEXT_SWITCHES'].split('\n')[0].strip()
                    if ctx_str.isdigit():
                        metrics['context_switches_per_sec'] = int(ctx_str)
                
                if 'PROCESSES' in marker_data:
                    proc_str = marker_data['PROCESSES'].split('\n')[0].strip()
                    if proc_str.isdigit():
                        metrics['process_count'] = int(proc_str)
                
                if 'INTERRUPTS' in marker_data:
                    int_str = marker_data['INTERRUPTS'].split('\n')[0].strip()
                    if int_str.isdigit():
                        metrics['interrupts_per_sec'] = int(int_str)
                
                # Add to history
                self.health_history.append(health.copy())
                
                # Display simple success indicator
                print("[OK]", end="", flush=True)
                
                # Verbose output only in debug mode
                if self.debug:
                    print(f"\n{'='*80}")
                    print(f"[HEALTH] Snapshot captured - CPU: {metrics.get('cpu_usage_pct', 0)}%, Memory: {metrics.get('memory_usage_pct', 0)}%, Disk Free: {metrics.get('disk_free_gb', 0)} GB")
                    print(f"[HEALTH] EMON Running: {metrics.get('emon_running', False)}, PID: {metrics.get('emon_pid', 'N/A')}")
                    print(f"[HEALTH] ")
                    print(f"[HEALTH] NOTE: CPU utilization measures OS workload, NOT EMON PMU coverage")
                    print(f"[HEALTH]       * EMON coverage = % of hardware events monitored")
                    print(f"[HEALTH]       * CPU utilization = % of CPU time executing vs idle")
                    print(f"[HEALTH]       Both can be valid: idle CPU (0%) + high EMON coverage (80-90%)")
                    print(f"{'='*80}\n")
                
                # Save incrementally if interval elapsed
                current_time = time.time()
                if current_time - self.last_save_time >= self.save_interval_seconds:
                    self._save_health_metrics()
                    self.last_save_time = current_time
            
            else:
                health['ok'] = True  # Don't fail collection on monitoring timeout
                health['warning'] = 'Health monitoring timeout (collection continues)'
        
        except Exception as e:
            health['ok'] = True  # Don't fail collection on health check error
            health['warning'] = f'Health check error: {str(e)}'
        
        return health
    
    def _save_health_metrics(self):
        """Save system health metrics incrementally for ML training."""
        if not self.health_history:
            return
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        health_file = self.health_log_path / f'system_health_{timestamp}.json'
        
        try:
            with open(health_file, 'w') as f:
                json.dump({
                    'collection_start': self.collection_start.isoformat(),
                    'collection_mode': self.collection_mode,
                    'total_samples': len(self.health_history),
                    'sut_ip': self.sut_ip,
                    'os_type': self.os_type,
                    'samples': self.health_history
                }, f, indent=2)
            
            if self.debug:
                print(f"      [SAVE] Saved {len(self.health_history)} health samples to {health_file.name}")
            # Keep history for ML analysis and reporting (don't clear)
        
        except Exception as e:
            print(f"      [[WARN]] Failed to save health metrics: {e}")
    
    def finalize(self):
        """Save any remaining health metrics at end of collection."""
        if self.debug:
            print(f"[DEBUG] Finalize called - health_history has {len(self.health_history)} samples")
        if self.health_history:
            self._save_health_metrics()
        elif self.debug:
            print("[DEBUG] No health samples to save")
    
    def get_health_summary(self):
        """Get summary statistics of health metrics."""
        if not self.health_history:
            return None
        
        summary = {
            'total_samples': len(self.health_history),
            'duration_minutes': (datetime.now() - self.collection_start).total_seconds() / 60,
            'health_issues': sum(1 for h in self.health_history if not h['ok']),
            'avg_cpu_usage': 0,
            'avg_memory_usage': 0,
            'avg_disk_free_gb': 0
        }
        
        # Calculate averages
        cpu_values = [h['metrics'].get('cpu_usage_pct', 0) for h in self.health_history if 'cpu_usage_pct' in h['metrics']]
        mem_values = [h['metrics'].get('memory_usage_pct', 0) for h in self.health_history if 'memory_usage_pct' in h['metrics']]
        disk_values = [h['metrics'].get('disk_free_gb', 0) for h in self.health_history if 'disk_free_gb' in h['metrics']]
        
        if cpu_values:
            summary['avg_cpu_usage'] = round(sum(cpu_values) / len(cpu_values), 2)
        if mem_values:
            summary['avg_memory_usage'] = round(sum(mem_values) / len(mem_values), 2)
        if disk_values:
            summary['avg_disk_free_gb'] = round(sum(disk_values) / len(disk_values), 2)
        
        return summary
