"""
System Context Collector - Enhanced ML Intelligence

Collects additional system context for improved ML predictions:
- CPU temperature (thermal context)
- CPU frequency behavior
- Memory utilization
- Workload resource usage
- Power state information
"""

import logging
import platform
import subprocess
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class SystemContextCollector:
    """Collects enhanced system context for ML training."""
    
    def __init__(self):
        self.os_type = platform.system().lower()
    
    def collect_all_context(self) -> Dict[str, Any]:
        """
        Collect all available system context.
        
        Returns comprehensive context including thermal, frequency, memory, etc.
        """
        context = {}
        
        # Phase 1: High-impact, easy to collect
        context['thermal_context'] = self.get_thermal_context()
        context['frequency_context'] = self.get_frequency_context()
        context['memory_context'] = self.get_memory_context()
        context['workload_profile'] = self.get_workload_profile()
        
        return context
    
    def get_thermal_context(self) -> Dict[str, Any]:
        """Get CPU temperature information."""
        thermal = {
            'cpu_temp_current': None,
            'thermal_available': False,
            'method': 'unavailable'
        }
        
        try:
            # Try psutil first (cross-platform)
            try:
                import psutil
                if hasattr(psutil, 'sensors_temperatures'):
                    temps = psutil.sensors_temperatures()
                    if temps:
                        # Try to find CPU package temperature
                        for name, entries in temps.items():
                            if 'coretemp' in name.lower() or 'cpu' in name.lower() or 'package' in name.lower():
                                for entry in entries:
                                    if 'package' in entry.label.lower() or entry.label == '':
                                        thermal['cpu_temp_current'] = entry.current
                                        thermal['thermal_available'] = True
                                        thermal['method'] = 'psutil'
                                        return thermal
            except (ImportError, AttributeError):
                pass
            
            # Platform-specific methods
            if 'windows' in self.os_type:
                thermal = self._get_thermal_windows()
            elif 'linux' in self.os_type:
                thermal = self._get_thermal_linux()
            
        except Exception as e:
            logger.debug(f"Could not collect thermal data: {e}")
        
        return thermal
    
    def _get_thermal_windows(self) -> Dict[str, Any]:
        """Get thermal data on Windows."""
        thermal = {
            'cpu_temp_current': None,
            'thermal_available': False,
            'method': 'unavailable'
        }
        
        try:
            # Try WMI
            import wmi
            w = wmi.WMI(namespace="root\\wmi")
            temp_info = w.MSAcpi_ThermalZoneTemperature()
            if temp_info:
                # Convert from tenths of Kelvin to Celsius
                temp_celsius = (temp_info[0].CurrentTemperature / 10.0) - 273.15
                thermal['cpu_temp_current'] = round(temp_celsius, 1)
                thermal['thermal_available'] = True
                thermal['method'] = 'wmi'
        except Exception as e:
            logger.debug(f"WMI thermal collection failed: {e}")
        
        return thermal
    
    def _get_thermal_linux(self) -> Dict[str, Any]:
        """Get thermal data on Linux."""
        thermal = {
            'cpu_temp_current': None,
            'thermal_available': False,
            'method': 'unavailable'
        }
        
        try:
            # Method 1: Read from /sys/class/thermal
            import glob
            thermal_zones = glob.glob('/sys/class/thermal/thermal_zone*/temp')
            if thermal_zones:
                with open(thermal_zones[0], 'r') as f:
                    temp_millidegrees = int(f.read().strip())
                    thermal['cpu_temp_current'] = temp_millidegrees / 1000.0
                    thermal['thermal_available'] = True
                    thermal['method'] = 'sysfs'
                    return thermal
        except Exception as e:
            logger.debug(f"sysfs thermal read failed: {e}")
        
        try:
            # Method 2: Use sensors command
            result = subprocess.run(['sensors'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if 'Package id 0' in line or 'Core 0' in line:
                        # Extract temperature from output like: "Package id 0:  +45.0°C"
                        parts = line.split(':')
                        if len(parts) > 1:
                            temp_str = parts[1].strip().split()[0]
                            temp = float(temp_str.replace('+', '').replace('°C', ''))
                            thermal['cpu_temp_current'] = temp
                            thermal['thermal_available'] = True
                            thermal['method'] = 'sensors'
                            break
        except Exception as e:
            logger.debug(f"sensors command failed: {e}")
        
        return thermal
    
    def get_frequency_context(self) -> Dict[str, Any]:
        """Get CPU frequency information."""
        freq_context = {
            'current_freq_mhz': None,
            'min_freq_mhz': None,
            'max_freq_mhz': None,
            'frequency_available': False
        }
        
        try:
            import psutil
            freq = psutil.cpu_freq(percpu=False)
            if freq:
                freq_context['current_freq_mhz'] = round(freq.current, 1)
                freq_context['min_freq_mhz'] = round(freq.min, 1)
                freq_context['max_freq_mhz'] = round(freq.max, 1)
                freq_context['frequency_available'] = True
        except Exception as e:
            logger.debug(f"Could not collect frequency data: {e}")
        
        return freq_context
    
    def get_memory_context(self) -> Dict[str, Any]:
        """Get memory utilization information."""
        mem_context = {
            'total_memory_gb': None,
            'available_memory_gb': None,
            'memory_utilization_percent': None,
            'memory_available': False
        }
        
        try:
            import psutil
            mem = psutil.virtual_memory()
            mem_context['total_memory_gb'] = round(mem.total / (1024**3), 1)
            mem_context['available_memory_gb'] = round(mem.available / (1024**3), 1)
            mem_context['memory_utilization_percent'] = mem.percent
            mem_context['memory_available'] = True
        except Exception as e:
            logger.debug(f"Could not collect memory data: {e}")
        
        return mem_context
    
    def get_workload_profile(self) -> Dict[str, Any]:
        """Get workload resource usage profile."""
        profile = {
            'cpu_utilization_percent': None,
            'cpu_count_logical': None,
            'cpu_count_physical': None,
            'workload_available': False
        }
        
        try:
            import psutil
            
            # CPU utilization (over 1 second)
            cpu_percent = psutil.cpu_percent(interval=1.0)
            profile['cpu_utilization_percent'] = cpu_percent
            
            # CPU counts
            profile['cpu_count_logical'] = psutil.cpu_count(logical=True)
            profile['cpu_count_physical'] = psutil.cpu_count(logical=False)
            
            profile['workload_available'] = True
        except Exception as e:
            logger.debug(f"Could not collect workload profile: {e}")
        
        return profile
    
    def get_snapshot(self) -> Dict[str, Any]:
        """
        Get a snapshot of current system state.
        
        Useful for time-series tracking during long tests.
        """
        snapshot = {
            'thermal': self.get_thermal_context(),
            'frequency': self.get_frequency_context(),
            'memory': self.get_memory_context(),
            'cpu_usage': None
        }
        
        try:
            import psutil
            snapshot['cpu_usage'] = psutil.cpu_percent(interval=0.5)
        except:
            pass
        
        return snapshot


# Convenience functions for quick access
def get_system_context() -> Dict[str, Any]:
    """Quick function to get all system context."""
    collector = SystemContextCollector()
    return collector.collect_all_context()


def get_cpu_temperature() -> Optional[float]:
    """Quick function to get CPU temperature."""
    collector = SystemContextCollector()
    thermal = collector.get_thermal_context()
    return thermal.get('cpu_temp_current')


def get_cpu_frequency() -> Optional[float]:
    """Quick function to get current CPU frequency."""
    collector = SystemContextCollector()
    freq = collector.get_frequency_context()
    return freq.get('current_freq_mhz')
