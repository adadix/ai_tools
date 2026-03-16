"""
Stress Tracker - Monitors stress/workload changes during EMON collection

Tracks stress changes over time and classifies collection types:
- Single stress (consistent workload)
- Mixed workload (stress changes during collection)
- Multi-stress (multiple stresses running simultaneously)
- Power cycling (stress alternating with idle states)

Author: Intel Corporation
Date: December 2024
"""

import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple


class StressTracker:
    """Tracks stress/workload changes during EMON collection."""
    
    def __init__(self, sut_communicator, sut_ip: str, check_interval: int = 60, debug: bool = False):
        """Initialize stress tracker.
        
        Args:
            sut_communicator: SUTCommunicator instance for detecting stress
            sut_ip: SUT IP address
            check_interval: Seconds between stress checks (default: 60)
            debug: Enable debug output
        """
        self.sut_comm = sut_communicator
        self.sut_ip = sut_ip
        self.check_interval = check_interval
        self.debug = debug
        
        # Tracking data
        self.timeline: List[Dict] = []  # [{time, stress, type, processes}]
        self.initial_stress: Optional[str] = None
        self.last_check_time: float = 0
        self.collection_start_time: float = 0
        
    def start_tracking(self) -> Dict:
        """Start tracking and record initial stress state.
        
        Returns:
            Initial stress detection info
        """
        self.collection_start_time = time.time()
        self.last_check_time = self.collection_start_time
        
        # Detect initial stress
        print(f"[STRESS TRACKER] Starting detection on {self.sut_ip}...")
        stress_info = self.sut_comm.detect_running_stress(self.sut_ip)
        
        print(f"[STRESS TRACKER] Detection result: detected={stress_info.get('detected')}, processes={len(stress_info.get('processes', []))}")
        
        if stress_info.get('detected'):
            self.initial_stress = stress_info.get('summary', stress_info.get('primary_stress', 'Unknown'))
            print(f"[STRESS TRACKER] Initial stress: {self.initial_stress}")
        else:
            self.initial_stress = 'Idle'
            print(f"[STRESS TRACKER] No stress detected - Idle")
        
        # Record in timeline
        self._add_timeline_entry(
            stress=self.initial_stress,
            stress_type='stress' if stress_info.get('detected') else 'idle',
            processes=stress_info.get('processes', [])
        )
        
        if self.debug:
            print(f"[STRESS TRACKER] Initial stress: {self.initial_stress}")
        
        return stress_info
    
    def check_stress(self, force: bool = False) -> Optional[Dict]:
        """Check current stress state if enough time has elapsed.
        
        Args:
            force: Force check regardless of interval
            
        Returns:
            Stress detection info if check was performed, None otherwise
        """
        current_time = time.time()
        elapsed = current_time - self.last_check_time
        
        if not force and elapsed < self.check_interval:
            return None
        
        # Perform stress detection
        print(f"[STRESS TRACKER] Periodic check at t={int((current_time - self.collection_start_time))}s...")
        try:
            stress_info = self.sut_comm.detect_running_stress(self.sut_ip)
            print(f"[STRESS TRACKER] Check result: detected={stress_info.get('detected')}, processes={len(stress_info.get('processes', []))}")
        except Exception as e:
            print(f"[STRESS TRACKER] Error detecting stress: {e}")
            if self.debug:
                import traceback
                traceback.print_exc()
            return None
            
        self.last_check_time = current_time
        
        if stress_info.get('detected'):
            current_stress = stress_info.get('summary', stress_info.get('primary_stress', 'Unknown'))
            stress_type = 'stress'
            print(f"[STRESS TRACKER] Current stress: {current_stress}")
        else:
            current_stress = 'Idle'
            stress_type = 'idle'
            print(f"[STRESS TRACKER] No stress - Idle")
        
        # Record in timeline
        self._add_timeline_entry(
            stress=current_stress,
            stress_type=stress_type,
            processes=stress_info.get('processes', [])
        )
        
        if self.debug:
            elapsed_min = (current_time - self.collection_start_time) / 60
            print(f"[STRESS TRACKER] t={elapsed_min:.1f}min: {current_stress}")
        
        return stress_info
    
    def finalize_tracking(self) -> Dict:
        """Finalize tracking and classify collection type.
        
        Returns:
            Complete tracking summary with classification
        """
        # Get unique stresses (excluding idle)
        unique_stresses = set()
        idle_count = 0
        
        for entry in self.timeline:
            if entry['type'] == 'stress':
                unique_stresses.add(entry['stress'])
            else:
                idle_count += 1
        
        # Classify collection type
        classification = self._classify_collection(unique_stresses, idle_count)
        
        # Build final summary
        summary = {
            'initial_stress': self.initial_stress,
            'final_classification': classification['label'],
            'test_type': classification['type'],
            'timeline': self.timeline,
            'unique_stresses': sorted(list(unique_stresses)),
            'power_transitions': self._count_transitions(),
            'duration_seconds': time.time() - self.collection_start_time,
            'stress_changes_detected': len(self.timeline) > 1,
            'explanation': classification['explanation']
        }
        
        if self.debug:
            print(f"\n[STRESS TRACKER] Final classification: {classification['label']}")
            print(f"  Type: {classification['type']}")
            print(f"  Unique stresses: {sorted(list(unique_stresses))}")
            print(f"  Transitions: {summary['power_transitions']}")
        
        return summary
    
    def _add_timeline_entry(self, stress: str, stress_type: str, processes: List):
        """Add entry to timeline."""
        elapsed = time.time() - self.collection_start_time
        
        entry = {
            'time': int(elapsed),
            'timestamp': datetime.now().isoformat(),
            'stress': stress,
            'type': stress_type,
            'process_count': len(processes)
        }
        
        self.timeline.append(entry)
    
    def _classify_collection(self, unique_stresses: set, idle_count: int) -> Dict:
        """Classify collection type based on stress patterns.
        
        Args:
            unique_stresses: Set of unique stress names detected
            idle_count: Number of idle periods detected
            
        Returns:
            Classification dict with label, type, and explanation
        """
        num_stresses = len(unique_stresses)
        
        # Single stress throughout collection (no idle)
        if num_stresses == 1 and idle_count == 0:
            stress_name = list(unique_stresses)[0]
            return {
                'label': stress_name,
                'type': 'single_stress',
                'explanation': f'Consistent single stress throughout collection'
            }
        
        # Single stress with idle periods
        # Priority: If stress was detected at start, use it as primary workload
        if num_stresses == 1 and idle_count > 0:
            stress_name = list(unique_stresses)[0]
            
            # Check if stress was at the beginning (primary workload that ended)
            if self.initial_stress and self.initial_stress != 'Idle':
                return {
                    'label': stress_name,
                    'type': 'stress_ended',
                    'explanation': f'Primary stress: {stress_name} (ended during collection with {idle_count} idle period(s))'
                }
            else:
                # Stress started after being idle (less common)
                return {
                    'label': f'{stress_name} with Power State Transitions',
                    'type': 'power_cycling',
                    'explanation': f'Single stress alternating with idle/low-power states ({idle_count} idle periods)'
                }
        
        # Multiple different stresses detected (mixed workload)
        if num_stresses > 1 and idle_count == 0:
            stress_list = ', '.join(sorted(list(unique_stresses)))
            return {
                'label': f'Mixed Workload: {stress_list}',
                'type': 'mixed_workload',
                'explanation': f'Multiple stresses detected during collection ({num_stresses} different stresses)'
            }
        
        # Multiple stresses with idle periods (mixed + power cycling)
        if num_stresses > 1 and idle_count > 0:
            stress_list = ', '.join(sorted(list(unique_stresses)))
            return {
                'label': f'Mixed Workload with Power Transitions: {stress_list}',
                'type': 'mixed_workload_power_cycling',
                'explanation': f'Multiple stresses alternating with idle periods ({num_stresses} stresses, {idle_count} idle periods)'
            }
        
        # Idle throughout - but check if initial stress was detected
        if num_stresses == 0:
            # If we started with stress but it's gone, prefer showing initial stress
            if self.initial_stress and self.initial_stress != 'Idle':
                return {
                    'label': self.initial_stress,
                    'type': 'stress_ended',
                    'explanation': f'Primary stress: {self.initial_stress} (ended before collection completed)'
                }
            else:
                return {
                    'label': 'Idle',
                    'type': 'idle',
                    'explanation': 'No stress detected - baseline/idle collection'
                }
        
        # Fallback
        return {
            'label': 'Unknown',
            'type': 'unknown',
            'explanation': 'Unable to classify workload pattern'
        }
    
    def _count_transitions(self) -> int:
        """Count number of stress/idle transitions."""
        if len(self.timeline) < 2:
            return 0
        
        transitions = 0
        for i in range(1, len(self.timeline)):
            prev_type = self.timeline[i-1]['type']
            curr_type = self.timeline[i]['type']
            if prev_type != curr_type:
                transitions += 1
        
        return transitions
    
    def get_current_classification(self) -> str:
        """Get current (interim) classification without finalizing.
        
        Returns:
            Current classification label
        """
        unique_stresses = set()
        idle_count = 0
        
        for entry in self.timeline:
            if entry['type'] == 'stress':
                unique_stresses.add(entry['stress'])
            else:
                idle_count += 1
        
        classification = self._classify_collection(unique_stresses, idle_count)
        return classification['label']
