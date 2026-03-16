"""
Checkpoint Manager for Silicon Coverage Analyzer

Provides save/resume capability for long-running collection sessions.
Saves progress after each domain completes to prevent data loss from
SSH timeouts, network issues, or interruptions.

Key Features:
- Saves checkpoint after each domain collection completes
- Stores all collected data (active/inactive events per domain)
- Stores health metrics and stress detection data
- Allows resuming from last successful checkpoint
- Preserves data quality for ML training (no data loss)
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple


class CheckpointManager:
    """Manages checkpoints for long-running collection sessions."""
    
    def __init__(self, checkpoint_dir: str = None, session_id: str = None, debug: bool = False):
        """
        Initialize checkpoint manager.
        
        Args:
            checkpoint_dir: Directory to store checkpoints (default: silicon_coverage_analyzer_data/checkpoints)
            session_id: Unique identifier for this session (auto-generated if None)
            debug: Enable debug output
        """
        self.debug = debug
        
        # Default checkpoint directory
        if checkpoint_dir is None:
            self.checkpoint_dir = Path(r'C:\silicon_coverage_analyzer_data\checkpoints')
        else:
            self.checkpoint_dir = Path(checkpoint_dir)
        
        # Ensure directory exists
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate or use provided session ID
        if session_id is None:
            self.session_id = datetime.now().strftime('%Y%m%d_%H%M%S')
        else:
            self.session_id = session_id
        
        # Checkpoint file path
        self.checkpoint_file = self.checkpoint_dir / f'checkpoint_{self.session_id}.json'
        self.checkpoint_lock = self.checkpoint_dir / f'checkpoint_{self.session_id}.lock'
        
        # Current checkpoint state
        self.state = {
            'session_id': self.session_id,
            'created_at': datetime.now().isoformat(),
            'last_updated': None,
            'status': 'in_progress',  # in_progress, completed, failed
            'config': {},
            'sut_ip': None,
            'os_type': None,
            'hardware_config': {},
            'domains_discovered': [],
            'domains_completed': [],
            'domains_pending': [],
            'domain_results': {},
            'all_active_events': [],
            'all_inactive_events': [],
            'health_history': [],
            'stress_detection': {},
            'collection_start_time': None,
            'collection_duration_seconds': 0,
            'total_events_collected': 0,
            'errors': []
        }
        
        if self.debug:
            print(f"[CHECKPOINT] Initialized: {self.checkpoint_file}")
    
    def start_session(self, config: Dict, sut_ip: str, os_type: str, 
                     hardware_config: Dict, domains: Dict, 
                     stress_detection: Dict = None) -> None:
        """
        Start a new checkpoint session.
        
        Args:
            config: Analysis configuration
            sut_ip: SUT IP address
            os_type: Operating system type (windows/linux)
            hardware_config: Hardware configuration from EMON
            domains: Discovered domains with events
            stress_detection: Detected stress workload info
        """
        available_domains = [name for name, data in domains.items() 
                           if data.get('available', False)]
        
        self.state['config'] = {
            'collection_duration': config.get('collection_duration', 3),
            'long_run_mode': config.get('long_run_mode', False),
            'long_run_hours': config.get('long_run_hours', 1),
            'max_events_per_domain': config.get('max_events_per_domain', 200),
            'debug': config.get('debug', False)
        }
        self.state['sut_ip'] = sut_ip
        self.state['os_type'] = os_type
        self.state['hardware_config'] = hardware_config
        self.state['domains_discovered'] = available_domains
        self.state['domains_pending'] = available_domains.copy()
        self.state['domains_completed'] = []
        self.state['stress_detection'] = stress_detection or {}
        self.state['collection_start_time'] = datetime.now().isoformat()
        self.state['last_updated'] = datetime.now().isoformat()
        
        # Save initial checkpoint
        self._save_checkpoint()
        
        print(f"\n      [CHECKPOINT] Session started: {self.session_id}")
        print(f"      [CHECKPOINT] {len(available_domains)} domains to collect")
        print(f"      [CHECKPOINT] Checkpoint file: {self.checkpoint_file}")
    
    def save_domain_checkpoint(self, domain: str, active_events: List[Dict], 
                               inactive_events: List[Dict], 
                               health_samples: List[Dict] = None) -> None:
        """
        Save checkpoint after completing a domain.
        
        Args:
            domain: Domain name that was completed
            active_events: List of active events from this domain
            inactive_events: List of inactive events from this domain
            health_samples: Optional health monitoring samples
        """
        # Update domain results
        self.state['domain_results'][domain] = {
            'active_events': active_events,
            'inactive_events': inactive_events,
            'total_tested': len(active_events) + len(inactive_events),
            'activity_rate': len(active_events) / (len(active_events) + len(inactive_events)) * 100 
                           if (len(active_events) + len(inactive_events)) > 0 else 0,
            'completed_at': datetime.now().isoformat()
        }
        
        # Add to cumulative lists
        self.state['all_active_events'].extend(active_events)
        self.state['all_inactive_events'].extend(inactive_events)
        
        # Update completion tracking
        if domain in self.state['domains_pending']:
            self.state['domains_pending'].remove(domain)
        if domain not in self.state['domains_completed']:
            self.state['domains_completed'].append(domain)
        
        # Update health history with checkpoint data
        if health_samples:
            # Add checkpoint data to each health sample for coverage tracking
            total_active = len(self.state['all_active_events'])
            total_inactive = len(self.state['all_inactive_events'])
            for sample in health_samples:
                if 'checkpoint_data' not in sample:
                    sample['checkpoint_data'] = {
                        'active_events': total_active,
                        'inactive_events': total_inactive,
                        'domain': domain
                    }
            self.state['health_history'].extend(health_samples)
        
        # Update totals
        self.state['total_events_collected'] = (
            len(self.state['all_active_events']) + 
            len(self.state['all_inactive_events'])
        )
        
        # Calculate elapsed time
        if self.state['collection_start_time']:
            start = datetime.fromisoformat(self.state['collection_start_time'])
            elapsed = (datetime.now() - start).total_seconds()
            self.state['collection_duration_seconds'] = elapsed
        
        self.state['last_updated'] = datetime.now().isoformat()
        
        # Save checkpoint
        self._save_checkpoint()
        
        # Progress message
        completed = len(self.state['domains_completed'])
        total = len(self.state['domains_discovered'])
        active_count = len(active_events)
        total_active = len(self.state['all_active_events'])
        
        print(f"\n      [CHECKPOINT] [OK] {domain.upper()} saved ({active_count} active)")
        print(f"      [CHECKPOINT]   Progress: {completed}/{total} domains | Total active: {total_active}")
    
    def mark_completed(self) -> None:
        """Mark the session as completed successfully."""
        self.state['status'] = 'completed'
        self.state['last_updated'] = datetime.now().isoformat()
        
        # Calculate final duration
        if self.state['collection_start_time']:
            start = datetime.fromisoformat(self.state['collection_start_time'])
            elapsed = (datetime.now() - start).total_seconds()
            self.state['collection_duration_seconds'] = elapsed
        
        self._save_checkpoint()
        
        # Remove lock file
        if self.checkpoint_lock.exists():
            self.checkpoint_lock.unlink()
        
        print(f"\n      [CHECKPOINT] Session completed: {self.session_id}", flush=True)
        print(f"      [CHECKPOINT] Total: {self.state['total_events_collected']} events collected", flush=True)
    
    def mark_failed(self, error: str) -> None:
        """Mark the session as failed with error."""
        self.state['status'] = 'failed'
        self.state['errors'].append({
            'timestamp': datetime.now().isoformat(),
            'error': error
        })
        self.state['last_updated'] = datetime.now().isoformat()
        self._save_checkpoint()
        
        print(f"\n      [CHECKPOINT] Session failed: {error}", flush=True)
        print(f"      [CHECKPOINT] Data saved - can resume with: --resume {self.session_id}", flush=True)
    
    def _save_checkpoint(self) -> None:
        """Save current state to checkpoint file."""
        try:
            # Create lock file
            self.checkpoint_lock.touch()
            
            # Write checkpoint atomically (write to temp, then rename)
            temp_file = self.checkpoint_file.with_suffix('.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(self.state, f, indent=2, default=str)
            
            # Atomic rename
            temp_file.replace(self.checkpoint_file)
            
            if self.debug:
                print(f"      [CHECKPOINT] Saved: {self.checkpoint_file.name}")
                
        except Exception as e:
            print(f"\n      [CHECKPOINT] [WARN] Save failed: {e}")
            self.state['errors'].append({
                'timestamp': datetime.now().isoformat(),
                'error': f'Checkpoint save failed: {e}'
            })
    
    @classmethod
    def find_resumable_sessions(cls, checkpoint_dir: str = None) -> List[Dict]:
        """
        Find all resumable (in_progress or failed) sessions.
        
        Returns:
            List of session info dicts with session_id, status, progress, etc.
        """
        if checkpoint_dir is None:
            checkpoint_dir = Path(r'C:\silicon_coverage_analyzer_data\checkpoints')
        else:
            checkpoint_dir = Path(checkpoint_dir)
        
        sessions = []
        
        if not checkpoint_dir.exists():
            return sessions
        
        for checkpoint_file in checkpoint_dir.glob('checkpoint_*.json'):
            try:
                with open(checkpoint_file, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                
                # Only include in_progress or failed sessions
                if state.get('status') not in ['in_progress', 'failed']:
                    continue
                
                sessions.append({
                    'session_id': state.get('session_id'),
                    'status': state.get('status'),
                    'sut_ip': state.get('sut_ip'),
                    'os_type': state.get('os_type'),
                    'domains_completed': len(state.get('domains_completed', [])),
                    'domains_total': len(state.get('domains_discovered', [])),
                    'events_collected': state.get('total_events_collected', 0),
                    'last_updated': state.get('last_updated'),
                    'created_at': state.get('created_at'),
                    'checkpoint_file': str(checkpoint_file)
                })
            except Exception:
                continue
        
        # Sort by last_updated (most recent first)
        sessions.sort(key=lambda x: x.get('last_updated', ''), reverse=True)
        
        return sessions
    
    @classmethod
    def load_checkpoint(cls, session_id: str, checkpoint_dir: str = None, 
                       debug: bool = False) -> Optional['CheckpointManager']:
        """
        Load an existing checkpoint and create a manager for it.
        
        Args:
            session_id: Session ID to load
            checkpoint_dir: Directory containing checkpoints
            debug: Enable debug output
            
        Returns:
            CheckpointManager with loaded state, or None if not found
        """
        if checkpoint_dir is None:
            checkpoint_dir = Path(r'C:\silicon_coverage_analyzer_data\checkpoints')
        else:
            checkpoint_dir = Path(checkpoint_dir)
        
        checkpoint_file = checkpoint_dir / f'checkpoint_{session_id}.json'
        
        if not checkpoint_file.exists():
            print(f"\n[ERROR] Checkpoint not found: {checkpoint_file}")
            return None
        
        try:
            with open(checkpoint_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
            
            # Create manager with loaded state
            manager = cls(checkpoint_dir=str(checkpoint_dir), 
                         session_id=session_id, debug=debug)
            manager.state = state
            manager.state['status'] = 'in_progress'  # Reset to in_progress for resume
            
            print(f"\n      [CHECKPOINT] Loaded session: {session_id}")
            print(f"      [CHECKPOINT] Progress: {len(state.get('domains_completed', []))}/{len(state.get('domains_discovered', []))} domains")
            print(f"      [CHECKPOINT] Events collected: {state.get('total_events_collected', 0)}")
            print(f"      [CHECKPOINT] Remaining domains: {', '.join(state.get('domains_pending', []))}")
            
            return manager
            
        except Exception as e:
            print(f"\n[ERROR] Failed to load checkpoint: {e}")
            return None
    
    def get_pending_domains(self) -> List[str]:
        """Get list of domains not yet collected."""
        return self.state.get('domains_pending', [])
    
    def get_completed_domains(self) -> List[str]:
        """Get list of completed domains."""
        return self.state.get('domains_completed', [])
    
    def get_collected_data(self) -> Tuple[List[Dict], List[Dict], Dict]:
        """
        Get all collected data from checkpoint.
        
        Returns:
            Tuple of (all_active_events, all_inactive_events, domain_results)
        """
        return (
            self.state.get('all_active_events', []),
            self.state.get('all_inactive_events', []),
            self.state.get('domain_results', {})
        )
    
    def get_config(self) -> Dict:
        """Get stored configuration."""
        return self.state.get('config', {})
    
    def get_sut_info(self) -> Dict:
        """Get SUT information."""
        return {
            'sut_ip': self.state.get('sut_ip'),
            'os_type': self.state.get('os_type'),
            'hardware_config': self.state.get('hardware_config', {})
        }
    
    def get_health_history(self) -> List[Dict]:
        """Get health monitoring history."""
        return self.state.get('health_history', [])
    
    def get_stress_detection(self) -> Dict:
        """Get stress detection info."""
        return self.state.get('stress_detection', {})
    
    def get_session_stats(self) -> Dict:
        """Get session statistics."""
        completed = len(self.state.get('domains_completed', []))
        total = len(self.state.get('domains_discovered', []))
        
        return {
            'session_id': self.session_id,
            'status': self.state.get('status'),
            'domains_completed': completed,
            'domains_total': total,
            'progress_percent': (completed / total * 100) if total > 0 else 0,
            'total_active': len(self.state.get('all_active_events', [])),
            'total_inactive': len(self.state.get('all_inactive_events', [])),
            'total_events': self.state.get('total_events_collected', 0),
            'duration_seconds': self.state.get('collection_duration_seconds', 0),
            'errors': self.state.get('errors', [])
        }


def list_resumable_sessions(checkpoint_dir: str = None) -> None:
    """Print list of resumable sessions for CLI."""
    sessions = CheckpointManager.find_resumable_sessions(checkpoint_dir)
    
    if not sessions:
        print("\n[INFO] No resumable sessions found.")
        print("       Start a new collection to create checkpoints.")
        return
    
    print(f"\n{'='*80}")
    print("RESUMABLE SESSIONS")
    print(f"{'='*80}")
    
    for i, session in enumerate(sessions, 1):
        status_icon = "[WARN]" if session['status'] == 'failed' else "[PAUSE]"
        progress = f"{session['domains_completed']}/{session['domains_total']}"
        
        print(f"\n  {i}. {status_icon} Session: {session['session_id']}")
        print(f"     Status: {session['status'].upper()}")
        print(f"     SUT: {session['sut_ip']} ({session['os_type']})")
        print(f"     Progress: {progress} domains | {session['events_collected']} events")
        print(f"     Last updated: {session['last_updated']}")
        print(f"     Resume command: python analyze_coverage.py --resume {session['session_id']}")
    
    print(f"\n{'='*80}\n")
