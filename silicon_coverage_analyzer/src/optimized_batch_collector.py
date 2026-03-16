"""
Optimized batch collector - finds max batch size automatically
"""

import os
import re
from datetime import datetime
from src.remote_transfer import RemoteTransfer
from src.system_health_monitor import SystemHealthMonitor
from src.pmu_diagnostics import PMUDiagnostics, validate_pmu_starvation_data_quality
from src.stress_tracker import StressTracker
from src.sut_communicator import SUTCommunicator

class OptimizedBatchCollector:
    """Collects events in optimally-sized batches."""
    
    def __init__(self, sut_ip, config):
        self.sut_ip = sut_ip
        self.config = config
        
        # Initialize RemoteTransfer with SSH key if available
        ssh_key_path = config.get('ssh_key_path')
        username = config.get('username')
        password = config.get('password')
        
        self.transfer = RemoteTransfer(
            sut_ip,
            username=username,
            password=password,
            ssh_key_path=ssh_key_path
        )
        
        # Detect OS type
        self.os_type = config.get('os_type', 'windows')
        if self.os_type not in ['windows', 'linux']:
            self.os_type = 'windows'
        
        self.min_activity_threshold = config.get('min_activity_threshold', 100)
        self.collection_duration = config.get('collection_duration', 3)
        self.max_batch_size = None  # Will be determined
        self.pending_files = []  # For deferred transfer mode
        self.debug = config.get('debug', False)  # Debug output flag
        
        # Adaptive timeout system - generous timeout for latency events
        # Events like LOAD_LATENCY_GT_* need time to wait for specific conditions
        # Minimum 120s to handle slow EMON collections and network latency
        self.base_timeout = max(120, self.collection_duration * 2 + 60)  # Min 120s or 2x duration + 60s
        self.current_timeout = self.base_timeout
        self.collection_times = []  # Track actual collection times
        self.timeout_failures = 0  # Count consecutive timeout failures
        self.successful_collections = 0
        
        # Initialize system health monitoring for ML training
        self.health_monitor = SystemHealthMonitor(
            transfer=self.transfer,
            os_type=self.os_type,
            sut_ip=self.sut_ip,
            collection_mode='optimized',
            debug=self.config.get('debug', False)
        )
        
        # Initialize PMU diagnostics (cross-platform)
        self.pmu_diagnostics = PMUDiagnostics(
            transfer=self.transfer,
            os_type=self.os_type,
            debug=self.debug
        )
        self.pmu_diagnostic_report = None  # Will be populated on first long collection
        
        # Initialize stress tracker for workload monitoring
        sut_comm = SUTCommunicator()
        self.stress_tracker = StressTracker(
            sut_communicator=sut_comm,
            sut_ip=sut_ip,
            check_interval=60,  # Check every 60 seconds
            debug=self.debug
        )
        self.stress_tracking_enabled = config.get('enable_stress_tracking', True)
        self.stress_tracking_data = None
        self.stress_tracking_started = False  # Track if we've started tracking
        
        # Capture initial health snapshot
        if self.debug:
            print("\n[DEBUG] Creating health monitor...")
        print("\n[HEALTH] Monitoring system health: ", end="", flush=True)
        self.health_monitor.capture_health_snapshot(
            output_file=None,
            context={'phase': 'collection_start', 'domain': 'initialization'}
        )
        
        # Initialize EMON driver (skip if already done in validation)
        if self.debug:
            print(f"\n      [DEBUG] skip_emon_init = {self.config.get('skip_emon_init', False)}")
        if not self.config.get('skip_emon_init', False):
            # Initialize EMON driver with full reset and verification
            print("      [INIT] Loading EMON driver...")
            
            # Step 1: Unload any existing driver instance
            if self.debug:
                print(f"      [DEBUG] Unloading existing driver...")
            unload_cmd = self._wrap_emon_cmd('emon -u')
            self.transfer.execute_command(unload_cmd, timeout=120)
            if self.debug:
                print(f"      [DEBUG] Unload complete")
            
            # Step 2: Load driver fresh
            init_cmd = self._wrap_emon_cmd('emon -i')
            
            if self.debug:
                print(f"      [DEBUG] Executing: emon -i")
            success, stdout, stderr = self.transfer.execute_command(init_cmd, timeout=120)
            if self.debug:
                print(f"      [DEBUG] Driver init complete: success={success}")
            
            # Step 3: Verify driver is loaded by checking version
            verify_cmd = self._wrap_emon_cmd('emon -v')
            if self.debug:
                print(f"      [DEBUG] Executing: emon -v")
            v_success, v_stdout, v_stderr = self.transfer.execute_command(verify_cmd, timeout=120)
            
            if v_success and v_stdout and 'SEP' in v_stdout:
                print("      [INIT] [OK] EMON driver ready")
                # Check for any warnings in driver status
                if 'warning' in (stdout or '').lower() or 'warning' in (stderr or '').lower():
                    print("      [INFO] Driver loaded with warnings (non-critical)")
            else:
                print("      [WARN] [WARN]  EMON driver initialization warning")
                if self.debug:
                    print(f"      [DEBUG] Init output: {stderr if stderr else stdout}")
                # Try one more time with elevated privileges hint
                print("      [RETRY] Attempting driver reload...")
                self.transfer.execute_command(self._wrap_emon_cmd('emon -u'), timeout=120)
                success2, stdout2, stderr2 = self.transfer.execute_command(self._wrap_emon_cmd('emon -i'), timeout=120)
                if success2:
                    print("      [INIT] [OK] Driver loaded on retry")
        else:
            if self.debug:
                print("      [INIT] Skipping EMON initialization (already done)")
            print("      [INIT] [OK] Using existing EMON driver")
    
    def _wrap_emon_cmd(self, emon_command):
        """Wrap emon command with environment setup for Linux."""
        if self.os_type == 'linux':
            # Dynamically find and source sep_vars.sh
            return f'''sep_vars=$(find /opt/intel -name "sep_vars.sh" -type f 2>/dev/null | head -1); if [ -n "$sep_vars" ]; then source "$sep_vars"; fi; {emon_command}'''
        else:
            return emon_command
    
    def _get_temp_dir(self):
        """Get temporary directory path for the target OS."""
        if self.os_type == 'linux':
            return '/tmp'
        return 'C:\\Temp'
    
    def _check_file_size_cmd(self, filepath):
        """Get OS-specific command to check file size."""
        if self.os_type == 'linux':
            return f'stat -c%s "{filepath}" 2>/dev/null || echo 0'
        return f'if (Test-Path "{filepath}") {{ (Get-Item "{filepath}").Length }} else {{ 0 }}'
    
    def _remove_file_cmd(self, filepath):
        """Get OS-specific command to remove a file."""
        if self.os_type == 'linux':
            return f'rm -f "{filepath}"'
        return f'Remove-Item "{filepath}" -Force -ErrorAction SilentlyContinue'
        
    def determine_max_batch_size(self, test_events, quiet=False):
        """Find maximum number of events EMON can handle in one collection."""
        # Check if sequential mode is enabled (1 event at a time)
        if self.config.get('sequential_mode', False):
            if not quiet:
                print("      [SEQUENTIAL MODE] Collecting 1 event at a time")
            self.max_batch_size = 1
            return 1
        
        if not quiet:
            print("      [AUTO-TUNE] Finding optimal batch size...")
        
        # Try different batch sizes with very short test duration
        # Conservative sizes to ensure reliable collection
        for size in [8, 6, 4]:
            if len(test_events) < size:
                continue
                
            test_batch = test_events[:size]
            event_list = ",".join(test_batch)
            
            temp_dir = self._get_temp_dir()
            test_file = f'{temp_dir}/batch_test.csv' if self.os_type == 'linux' else f'{temp_dir}\\batch_test.csv'
            
            cmd = f'emon -t 1 -C "{event_list}" -f "{test_file}"'
            # Use generous timeout for multiplexing test (300s) to handle slow SSH connections
            success, stdout, stderr = self.transfer.execute_command(self._wrap_emon_cmd(cmd), timeout=300)
            
            # Check for EMON errors in output
            has_error = False
            if stderr and ('error' in stderr.lower() or 'invalid' in stderr.lower() or 'unsupported' in stderr.lower()):
                has_error = True
            if stdout and ('error' in stdout.lower() or 'invalid' in stdout.lower()):
                has_error = True
            
            if success and not has_error:
                # Verify file was created with content
                check_cmd = self._check_file_size_cmd(test_file)
                s2, out2, _ = self.transfer.execute_command(check_cmd, timeout=10)
                
                try:
                    file_size = int(out2.strip())
                    if file_size > 0:
                        self.transfer.execute_command(self._remove_file_cmd(test_file), timeout=5)
                        if not quiet:
                            print(f"      [AUTO-TUNE] Max batch size: {size} events")
                        self.max_batch_size = size
                        return size
                except:
                    pass
        
        # Fallback to safe minimum
        if not quiet:
            print(f"      [AUTO-TUNE] Using safe default: 4 events")
        self.max_batch_size = 4
        return 4
    
    def collect_domain_events(self, domain, events, defer_transfer=False, quiet=False):
        """Collect all events for a domain using optimized batching.
        
        Args:
            domain: Domain name
            events: List of event names
            defer_transfer: If True, only collect files on SUT without transferring.
                          Files can be transferred later via process_pending_transfers()
            quiet: If True, suppress verbose output (for overall progress bar mode)
        """
        if not events:
            return [], []
        
        import time
        from datetime import datetime, timedelta
        domain_start_time = time.time()
        
        # Start stress tracking on first domain collection (using flag to ensure it only happens once)
        if self.stress_tracking_enabled and not self.stress_tracking_started:
            self.stress_tracking_started = True
            if not quiet:
                print(f"      [STRESS TRACKING] Monitoring workload changes...")
            initial_stress = self.stress_tracker.start_tracking()
            if not quiet and initial_stress.get('detected'):
                print(f"      [STRESS TRACKING] Initial: {initial_stress.get('summary', 'Unknown')}")
        
        # Auto-tune batch size on first domain
        if self.max_batch_size is None:
            self.determine_max_batch_size(events[:50], quiet=quiet)
        
        batch_size = self.max_batch_size
        
        # For long-run mode, calculate duration based on auto-tuned batch size
        if self.config.get('long_run_mode') and self.config.get('long_run_total_seconds'):
            # Calculate total events across all domains for accurate estimation
            total_events_all_domains = sum(
                min(len(d.get('events', [])), self.config.get('max_events_per_domain', 10000))
                for d in self.config.get('all_domains', {}).values()
                if d.get('available', False)
            )
            
            # Calculate number of batches with auto-tuned size
            num_batches = (total_events_all_domains + batch_size - 1) // batch_size
            
            # Calculate duration per batch to spread over total hours
            total_seconds = self.config['long_run_total_seconds']
            duration_per_batch = max(1, total_seconds // num_batches)
            
            # Update collection duration
            self.collection_duration = duration_per_batch
            
            # Recalculate timeout based on new collection duration
            # For long-run batches, need generous timeout: 3x duration + 2 minutes minimum
            self.base_timeout = max(self.collection_duration * 3 + 120, 300)
            self.current_timeout = self.base_timeout
            
            # Display updated estimate (only once, not in quiet mode)
            if not quiet and not hasattr(self, '_long_run_estimate_shown'):
                self._long_run_estimate_shown = True
                hours = self.config.get('long_run_hours', 1)
                
                print(f"\n      [ESTIMATE] Long-run collection ({hours} hour(s)):")
                print(f"          Total events: {total_events_all_domains}")
                print(f"          Domains: {len(self.config.get('all_domains', {}))}")
                print(f"          Auto-tuned batch size: {batch_size} events/batch")
                print()
                print(f"          Total batches: {num_batches}")
                print(f"          Duration per batch: {duration_per_batch} seconds")
                print(f"          Total time: {hours} hour(s) ({total_seconds}s)")
                print()
                
                completion_time = datetime.now() + timedelta(seconds=total_seconds)
                print(f"          Estimated completion: {completion_time.strftime('%Y-%m-%d %H:%M:%S')}")
                print()
        
        # Create batches
        batches = []
        for i in range(0, len(events), batch_size):
            batches.append({
                'batch_id': len(batches),
                'events': events[i:i+batch_size]
            })
        
        total_batches = len(batches)
        total_events = len(events)
        
        if not quiet:
            print(f"      [COLLECT] {total_events} events in {total_batches} batches ({batch_size} events/batch)")
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_files = []
        
        # Phase 1: Collect all batches on SUT (no file reads)
        if not quiet:
            print(f"      [PHASE 1/3] Collecting data on SUT...")
        phase1_start = time.time()
        
        for i, batch in enumerate(batches):
            # Progress bar
            progress = (i + 1) / total_batches
            bar_length = 40
            filled = int(bar_length * progress)
            bar = '█' * filled + '░' * (bar_length - filled)
            
            event_list = ",".join(batch['events'])
            
            temp_dir = self._get_temp_dir()
            if self.os_type == 'linux':
                output_file = f"{temp_dir}/emon_{domain}_{timestamp}_b{i}.csv"
            else:
                output_file = f"{temp_dir}\\emon_{domain}_{timestamp}_b{i}.csv"
            
            output_files.append((output_file, batch['events']))
            
            # For long-duration collections, run EMON in background to avoid session timeouts
            if self.collection_duration >= 60:
                if self.os_type == 'linux':
                    # Linux: run normally (SSH sessions don't have same timeout issues as PowerShell)
                    # Add post-collection delay to ensure file is fully flushed
                    cmd = f'emon -t {self.collection_duration} -C "{event_list}" -f "{output_file}"; sleep 3'
                else:
                    # Windows: use Start-Process with -NoNewWindow to avoid session timeout
                    # Add post-collection delay to ensure file is fully flushed to disk
                    cmd = f'Start-Process -FilePath "emon" -ArgumentList "-t {self.collection_duration} -C \\"{event_list}\\" -f \\"{output_file}\\"" -NoNewWindow -Wait; Start-Sleep -Seconds 3'
            else:
                # Short collections can run synchronously
                cmd = f'emon -t {self.collection_duration} -C "{event_list}" -f "{output_file}"'
            
            # Show batch progress in debug mode
            if self.debug:
                print(f"          [BATCH {i+1}/{total_batches}] Collecting {len(batch['events'])} events ({self.collection_duration}s)...", flush=True)
            
            # Execute EMON command with adaptive timeout
            collection_start = time.time()
            actual_timeout = int(self.current_timeout)
            if self.debug:
                print(f"          [DEBUG] Using timeout: {actual_timeout}s (base={self.base_timeout}, current={self.current_timeout})")
            
            # Capture health metrics during collection based on duration
            # Sample every 1 second for all batches ≥3 seconds
            # Provides high-fidelity health tracking with minimal overhead
            health_samples_during_batch = []
            sampling_thread = None
            stop_sampling = None
            
            if self.collection_duration >= 3:
                import threading
                stop_sampling = threading.Event()
                
                # Always use 1-second sampling for best health tracking
                sample_interval = 1
                
                def sample_health_periodically():
                    """Background thread to sample health metrics every second during EMON collection"""
                    while not stop_sampling.is_set():
                        try:
                            health_snapshot = self.health_monitor.capture_health_snapshot(
                                output_file=output_file,
                                context={'domain': domain, 'batch': i + 1}
                            )
                            if health_snapshot:
                                health_samples_during_batch.append(health_snapshot)
                            
                            # Check for stress changes periodically (if enabled and tracking started)
                            if self.stress_tracking_enabled and self.stress_tracking_started:
                                self.stress_tracker.check_stress(force=False)
                        except Exception as e:
                            if self.debug:
                                print(f"[DEBUG] Health/stress sampling error: {e}")
                        stop_sampling.wait(sample_interval)  # Sleep but wake up if stopped
                
                sampling_thread = threading.Thread(target=sample_health_periodically, daemon=True)
                sampling_thread.start()
            
            # Execute EMON command
            success, stdout, stderr = self.transfer.execute_command(self._wrap_emon_cmd(cmd), timeout=actual_timeout)
            
            # Stop background health sampling if it was started
            if sampling_thread and stop_sampling:
                stop_sampling.set()
                sampling_thread.join(timeout=2)
            
            collection_time = time.time() - collection_start
            
            # Track collection time for adaptive timeout
            self.collection_times.append(collection_time)
            if len(self.collection_times) > 10:
                self.collection_times.pop(0)
            
            # Even if command timed out, EMON continues running on SUT and creates the file
            # So we wait for the file to exist rather than failing immediately
            if not success:
                # Command timed out, but file might still be created
                # Wait up to expected duration + generous buffer for file to appear
                # Some events (like LOAD_LATENCY_GT_*) need longer to trigger
                expected_duration = self.collection_duration
                # More generous buffer: 2x duration or min 30s, max 120s
                buffer = max(30, min(int(expected_duration * 2), 120))
                max_wait = expected_duration + buffer
                wait_start = time.time()
                file_appeared = False
                
                while (time.time() - wait_start) < max_wait:
                    # Check if file exists
                    if self.os_type == 'linux':
                        verify_cmd = f'[ -f "{output_file}" ] && echo "true" || echo "false"'
                    else:
                        verify_cmd = f'Test-Path "{output_file}"'
                    v_success, v_output, _ = self.transfer.execute_command(verify_cmd, timeout=120)
                    
                    if v_success and v_output.strip().lower() == 'true':
                        file_appeared = True
                        self.successful_collections += 1
                        self.timeout_failures = max(0, self.timeout_failures - 1)
                        break
                    
                    time.sleep(3)  # Check every 3 seconds
                
                if not file_appeared:
                    # After 3 consecutive failures, scale up timeout
                    if self.timeout_failures >= 3:
                        old_timeout = self.current_timeout
                        # More aggressive scaling: 2x or +60s, max 10min + collection_duration
                        max_collection_timeout = 600 + self.collection_duration
                        self.current_timeout = min(int(self.current_timeout * 2), max_collection_timeout)
                        if old_timeout != self.current_timeout:
                            print(f"\n      [ADAPTIVE] Multiple timeouts detected - timeout increased: {old_timeout}s -> {self.current_timeout}s")
                        old_timeout = self.current_timeout
                        self.current_timeout = min(int(self.current_timeout * 1.5), max_collection_timeout // 2)
                        if old_timeout != self.current_timeout:
                            print(f"\n      [ADAPTIVE] SUT under heavy stress - timeout increased: {old_timeout}s -> {self.current_timeout}s")
                        self.timeout_failures = 0
            else:
                # Command completed successfully
                self.successful_collections += 1
                self.timeout_failures = max(0, self.timeout_failures - 1)
                
                # Show completion in debug mode
                if self.debug:
                    print(f"          [BATCH {i+1}/{total_batches}] [OK] Completed in {collection_time:.1f}s", flush=True)
                
                # Dynamically adjust timeout based on actual performance
                if len(self.collection_times) >= 5:
                    avg_time = sum(self.collection_times) / len(self.collection_times)
                    max_time = max(self.collection_times)
                    
                    # If average collection time is approaching timeout, scale up preemptively
                    if avg_time > (self.current_timeout * 0.7):
                        old_timeout = self.current_timeout
                        # Scale with collection duration: 5min base + duration
                        preemptive_max = 300 + self.collection_duration
                        self.current_timeout = min(int(max_time * 1.3), preemptive_max)
                        if old_timeout != self.current_timeout:
                            print(f"\n      [ADAPTIVE] Collection times increasing - timeout adjusted: {old_timeout}s -> {self.current_timeout}s")
            
            # Check for discarded events in output
            discarded_events = set()
            emon_error = False
            if stdout or stderr:
                output_text = (stdout or '') + (stderr or '')
                for event in batch['events']:
                    if f"Event {event} discarded" in output_text or f"{event} discarded" in output_text:
                        discarded_events.add(event)
                
                # Check for critical EMON failures (not per-event warnings)
                # Only flag as error if EMON completely failed to start/run
                critical_errors = [
                    "emon: not found",
                    "emon: command not found",
                    "Cannot initialize",
                    "License error",
                    "Driver not loaded",
                    "Failed to start",
                    "No events to collect",
                    "EMON failed",
                    "Segmentation fault",
                    "core dump"
                ]
                for critical_error in critical_errors:
                    if critical_error.lower() in output_text.lower():
                        emon_error = True
                        if self.debug:
                            print(f"\n      [EMON ERROR] Critical failure detected: {critical_error}")
                        break
                    
                # If all events discarded, EMON may not create file
                if len(discarded_events) == len(batch['events']):
                    print(f"\n      [WARNING] Batch {i}: All {len(discarded_events)} events discarded - no file will be created")
                    emon_error = True
            
            # Store discarded info and error status with batch
            output_files[-1] = (output_file, batch['events'], discarded_events, emon_error)
        
        # Capture health snapshot after completing this domain
        if self.debug:
            print(f"\n[HEALTH] Capturing health snapshot after {domain} domain...")
        total_events_collected = sum(len(batch['events']) for batch in batches)
        self.health_monitor.capture_health_snapshot(
            output_file=output_files[-1][0] if output_files else None,
            context={
                'phase': 'domain_complete',
                'domain': domain,
                'batches_collected': len(batches),
                'events_collected': total_events_collected
            }
        )
        
        phase1_time = time.time() - phase1_start
        if not quiet:
            print(f"  ({phase1_time:.1f}s)")
        
        # If deferred transfer mode, save files for later and return
        if defer_transfer:
            # Store files with domain tag for later parsing
            for output_file, batch_events, discarded_events, emon_error in output_files:
                self.pending_files.append((output_file, batch_events, domain, discarded_events, emon_error))
            if not quiet:
                print(f"      [DEFERRED] {len(output_files)} files queued for batch transfer")
            return [], []  # Return empty until transfer happens
        
        # Phase 2: Transfer all files at once with retry and validation
        if not quiet:
            print(f"      [PHASE 2/3] Transferring {len(output_files)} files from SUT...")
        phase2_start = time.time()
        all_active = []
        all_inactive = []
        failed_transfers = []
        zero_byte_files = 0  # Track unsupported events (0-byte files)
        pmu_starved_files = 0  # Track PMU starvation (non-zero files with all-zero data)
        pmu_starved_files = 0  # Track PMU starvation (non-zero files with all-zero data)
        
        # Calculate adaptive timeout based on collection duration (file size predictor)
        # Long collections create large files that need more time to transfer
        # Short collections: 180s max (files are small, ~few KB to MB)
        # Long collections: Scale with duration (files can be 10MB+)
        is_long_collection = self.collection_duration >= 60
        if is_long_collection:
            # For long single-batch collections, allow generous timeouts for large files
            # Scale: 1min per minute of collection, max 30min
            read_timeout = min(1800, int(self.collection_duration / 60) * 60 + 180)
        else:
            read_timeout = 180
        
        for i, (output_file, batch_events, discarded_events, emon_error) in enumerate(output_files):
            content = None
            transfer_success = False
            
            # Show transfer progress in debug mode
            if self.debug:
                print(f"          [FILE {i+1}/{len(output_files)}] Transferring...", end="", flush=True)
            
            # Skip transfer if EMON had errors - file won't exist
            if emon_error:
                # Mark all events as inactive with emon_error status
                for event in batch_events:
                    all_inactive.append({
                        'event': event,
                        'total_activity': 0,
                        'samples': 0,
                        'status': 'event_not_exists' if event in discarded_events else 'emon_error',
                        'error_detail': 'EMON rejected event or all events discarded'
                    })
                # Skip to next file
                continue
            
            # Try up to 3 times to read the file
            failure_reason = None
            for attempt in range(3):
                try:
                    # First verify file exists and has content (OS-aware commands)
                    if self.os_type == 'linux':
                        verify_cmd = f'if [ -f "{output_file}" ]; then stat -c%s "{output_file}"; else echo "MISSING"; fi'
                    else:
                        verify_cmd = f'if (Test-Path "{output_file}") {{ (Get-Item "{output_file}").Length }} else {{ "MISSING" }}'
                    
                    v_success, v_output, _ = self.transfer.execute_command(verify_cmd, timeout=120)
                    
                    if v_output and v_output.strip() != "MISSING":
                        try:
                            file_size = int(v_output.strip())
                            if file_size == 0:
                                # File is empty (0 bytes) - event not supported on this CPU
                                # Skip transfer entirely and mark as unsupported
                                failure_reason = "file_size_zero_unsupported_event"
                                zero_byte_files += 1
                                if self.debug:
                                    print(f" [WARN] 0 bytes (unsupported)", flush=True)
                                break  # Exit retry loop immediately
                            elif file_size > 0:
                                # For long-run mode, verify file is stable (fully written)
                                # by checking size doesn't change after 1 second
                                if self.collection_duration >= 60:
                                    time.sleep(1)
                                    v_success2, v_output2, _ = self.transfer.execute_command(verify_cmd, timeout=120)
                                    if v_output2 and v_output2.strip() != "MISSING":
                                        file_size2 = int(v_output2.strip())
                                        if file_size2 != file_size:
                                            # File still being written, retry
                                            if attempt < 2:
                                                time.sleep(2)
                                                continue
                                
                                # Adaptive transfer strategy based on file size (same as deferred mode)
                                file_size_mb = file_size / (1024 * 1024)
                                
                                if file_size_mb > 10:
                                    # Very large file - use sampled transfer (header + tail)
                                    # Can occur in any domain (core, cbo, ncu, etc.) with long collections or high activity
                                    if self.debug and attempt == 0:
                                        print(f"\n      [LARGE FILE] {domain if domain else 'unknown'}/{os.path.basename(output_file)}: {file_size_mb:.1f}MB detected, using sampled transfer...", end="", flush=True)
                                        print(f"\n      [LARGE FILE] {domain if domain else 'unknown'}/{os.path.basename(output_file)}: {file_size_mb:.1f}MB detected, using sampled transfer...", end="", flush=True)
                                    
                                    if self.os_type == 'linux':
                                        read_cmd = f'(head -c 5242880 "{output_file}" 2>/dev/null; echo "__CHUNK_SEPARATOR__"; tail -c 5242880 "{output_file}" 2>/dev/null) || echo "ERROR"'
                                    else:
                                        read_cmd = f'$file="{output_file}"; if (Test-Path $file) {{ $bytes=[System.IO.File]::ReadAllBytes($file); $head=$bytes[0..[Math]::Min(5242879,$bytes.Length-1)]; $tail=$bytes[[Math]::Max(0,$bytes.Length-5242880)..($bytes.Length-1)]; [System.Text.Encoding]::UTF8.GetString($head) + "`n__CHUNK_SEPARATOR__`n" + [System.Text.Encoding]::UTF8.GetString($tail) }} else {{ "ERROR" }}'
                                    
                                    s2, content, _ = self.transfer.execute_command(read_cmd, timeout=read_timeout)
                                    
                                    # Merge chunks if separator found
                                    if content and '__CHUNK_SEPARATOR__' in content:
                                        parts = content.split('__CHUNK_SEPARATOR__')
                                        if len(parts) == 2:
                                            content = parts[0] + parts[1]
                                            if self.debug:
                                                print(f" sampled {len(content)/(1024*1024):.1f}MB", end="", flush=True)
                                elif file_size_mb > 5:
                                    # Medium file - try gzip compression if available
                                    if self.os_type == 'linux':
                                        read_cmd = f'if command -v gzip &>/dev/null; then gzip -c "{output_file}" 2>/dev/null | base64; else cat "{output_file}" 2>/dev/null; fi'
                                        s2, content, _ = self.transfer.execute_command(read_cmd, timeout=read_timeout)
                                        
                                        # Decompress if base64 encoded
                                        if content and not content.startswith('#'):
                                            try:
                                                import base64
                                                import gzip
                                                decoded = base64.b64decode(content)
                                                content = gzip.decompress(decoded).decode('utf-8')
                                                if self.debug:
                                                    compression_ratio = (1 - len(decoded)/file_size) * 100
                                                    print(f" compressed {len(decoded)/(1024*1024):.1f}MB ({compression_ratio:.0f}% reduction)", end="", flush=True)
                                            except:
                                                pass
                                    else:
                                        read_cmd = f'Get-Content "{output_file}" -Raw -ErrorAction SilentlyContinue'
                                        s2, content, _ = self.transfer.execute_command(read_cmd, timeout=read_timeout)
                                else:
                                    # Small file - direct transfer
                                    if self.os_type == 'linux':
                                        read_cmd = f'cat "{output_file}"'
                                    else:
                                        read_cmd = f'Get-Content "{output_file}" -Raw -ErrorAction SilentlyContinue'
                                    
                                    s2, content, _ = self.transfer.execute_command(read_cmd, timeout=read_timeout)
                                
                                if content and content.strip() and 'ERROR' not in content:
                                    # Verify transfer integrity: check received size matches SUT file size
                                    received_size = len(content)
                                    file_size_mb = file_size / (1024 * 1024)
                                    
                                    # For sampled transfers (large files), expected size is ~10MB
                                    if file_size_mb > 10 and '__CHUNK_SEPARATOR__' in content:
                                        if received_size > 1000000:  # At least 1MB of data
                                            transfer_success = True
                                            if self.debug:
                                                print(f" [OK] sampled", flush=True)
                                            break
                                    else:
                                        # Full transfer - check size match
                                        size_match_pct = (received_size / file_size * 100) if file_size > 0 else 0
                                        
                                        # Allow variance: 2% for small files, 10% for compressed
                                        variance_threshold = 10 if file_size_mb > 5 else 2
                                        
                                        if size_match_pct >= (100 - variance_threshold) and size_match_pct <= (100 + variance_threshold):
                                            transfer_success = True
                                            if self.debug and abs(100 - size_match_pct) > 1:
                                                print(f" [OK] verified ({size_match_pct:.1f}% match)", end="", flush=True)
                                            break
                                        else:
                                            # Size mismatch - possible corruption or incomplete transfer
                                            if self.debug:
                                                print(f" [WARN] size mismatch (expected {file_size_mb:.1f}MB, got {received_size/(1024*1024):.1f}MB, {size_match_pct:.1f}%)", end="", flush=True)
                                            failure_reason = f"size_mismatch_attempt_{attempt+1}_expected_{file_size}_got_{received_size}"
                                            # Retry with longer delay for potentially incomplete transfer
                                            if attempt < 2:
                                                time.sleep(2 * (attempt + 1))
                                                continue
                                else:
                                    failure_reason = f"read_failed_attempt_{attempt+1}_empty_content"
                        except ValueError as e:
                            failure_reason = f"invalid_file_size_response_{str(e)[:30]}"
                            if self.debug:
                                print(f" [WARN] ValueError: {e}", flush=True)
                    else:
                        failure_reason = "file_missing_or_check_failed"
                    
                    # Wait before retry (exponential backoff)
                    if attempt < 2 and not transfer_success:
                        time.sleep(0.5 * (attempt + 1))
                        
                except Exception as e:
                    # Catch network errors, SSH failures, timeouts, etc.
                    failure_reason = f"exception_attempt_{attempt+1}_{type(e).__name__}"
                    if self.debug:
                        print(f" [WARN] Exception on attempt {attempt+1}: {type(e).__name__}: {str(e)[:50]}", flush=True)
                    
                    # For network errors, wait longer before retry
                    if attempt < 2:
                        retry_delay = 2 * (attempt + 1)
                        if self.debug:
                            print(f"      Retrying in {retry_delay}s...", flush=True)
                        time.sleep(retry_delay)
            
            if transfer_success and content:
                # Show parsing in debug mode
                if self.debug:
                    print(f" parsing...", end="", flush=True)
                
                active, inactive = self.parse_emon_output(content, batch_events, discarded_events, domain)
                
                # Show completion in debug mode
                if self.debug:
                    print(f" [OK] ({len(active)} active, {len(inactive)} inactive)", flush=True)
                
                # Debug: For uncore domains, verify data on SUT vs after transfer
                if domain and ('cbo' in domain.lower() or 'ncu' in domain.lower()):
                    # Check if we got any non-zero counts
                    has_activity = any(e.get('total_activity', 0) > 0 for e in active)
                    
                    if not has_activity and len(batch_events) > 0:
                        # All zero - verify on SUT before blaming transfer (only in debug mode)
                        if self.debug:
                            print(f"\n      [VERIFY] {domain}: All events zero, checking raw SUT file...")
                            
                            # Read first few lines from SUT
                            if self.os_type == 'linux':
                                verify_cmd = f'head -20 "{output_file}"'
                            else:
                                verify_cmd = f'Get-Content "{output_file}" -TotalCount 20'
                            
                            v_success, sut_content, _ = self.transfer.execute_command(verify_cmd, timeout=120)
                            
                            if v_success and sut_content:
                                # Show first event line from SUT
                                lines = sut_content.split('\n')
                                for line in lines[1:6]:  # Skip header, show first 5 data lines
                                    if line.strip() and any(evt in line for evt in batch_events[:2]):
                                        # Truncate long lines for display
                                        display_line = line[:120] + '...' if len(line) > 120 else line
                                        print(f"      [SUT RAW] {display_line}")
                                        break
                
                all_active.extend(active)
                all_inactive.extend(inactive)
            else:
                # Determine proper status based on failure reason
                if failure_reason == "file_size_zero_unsupported_event":
                    status = 'unsupported'
                    error_detail = 'Event not supported on this CPU (0-byte file)'
                elif failure_reason == "file_missing_or_check_failed":
                    status = 'no_file'
                    error_detail = 'File not found on SUT'
                elif failure_reason and "size_mismatch" in failure_reason:
                    status = 'transfer_corrupted'
                    error_detail = f'Transfer verification failed: {failure_reason}'
                else:
                    status = 'no_file'
                    error_detail = f'File transfer failed: {failure_reason or "unknown"}'
                
                # Log failed transfer for later retry (skip if zero-byte file)
                if failure_reason != "file_size_zero_unsupported_event":
                    failed_transfers.append((output_file, batch_events, discarded_events, i, failure_reason))
                
                for event in batch_events:
                    all_inactive.append({
                        'event': event,
                        'total_activity': 0,
                        'samples': 0,
                        'status': status,
                        'error_detail': error_detail
                    })
            
            # Progress with dynamic time estimate
            progress = (i + 1) / len(output_files)
            bar_length = 40
            filled = int(bar_length * progress)
            bar = '█' * filled + '░' * (bar_length - filled)
            
            elapsed = time.time() - phase2_start
            if i > 0:
                avg_per_file = elapsed / (i + 1)
                remaining_files = len(output_files) - (i + 1)
                eta_seconds = remaining_files * avg_per_file
                eta_str = f"{int(eta_seconds // 60)}m {int(eta_seconds % 60)}s" if eta_seconds >= 60 else f"{int(eta_seconds)}s"
                print(f"\r         [{bar}] {i+1}/{len(output_files)} files | Elapsed: {int(elapsed)}s | ETA: {eta_str}", end='', flush=True)
            else:
                print(f"\r         [{bar}] {i+1}/{len(output_files)} files transferred", end='', flush=True)
        
        # If any transfers failed, attempt recovery (excluding zero-byte files)
        if failed_transfers:
            if self.debug:
                print(f"\n      [RECOVERY] {len(failed_transfers)} files failed, attempting recovery...")
            
            # Analyze failure reasons
            failure_summary = {}
            for _, _, _, _, reason in failed_transfers:
                failure_summary[reason] = failure_summary.get(reason, 0) + 1
            
            # Display failure breakdown (excluding zero-byte which were already skipped)
            if self.debug:
                for reason, count in failure_summary.items():
                    print(f"                 * {reason}: {count} files")
            
            recovered = 0
            
            for output_file, batch_events, discarded_events, original_idx, reason in failed_transfers:
                # Wait a bit for file system to settle
                time.sleep(1)
                
                # Try one more time with extended timeout
                verify_cmd = f'if (Test-Path "{output_file}") {{ Get-Content "{output_file}" -Raw }} else {{ "" }}'
                s3, content, _ = self.transfer.execute_command(verify_cmd, timeout=120)
                
                if content and content.strip():
                    # Remove the placeholder inactive events we added earlier
                    all_inactive = [e for e in all_inactive if e['event'] not in batch_events or e.get('status') != 'no_file']
                    
                    # Parse recovered data
                    active, inactive = self.parse_emon_output(content, batch_events, discarded_events, domain)
                    all_active.extend(active)
                    all_inactive.extend(inactive)
                    recovered += 1
            
            if self.debug:
                if recovered > 0:
                    print(f"      [RECOVERY] [OK] Recovered {recovered}/{len(failed_transfers)} files")
                if recovered < len(failed_transfers):
                    permanently_lost = len(failed_transfers) - recovered
                    temp_dir = self._get_temp_dir()
                    print(f"      [INFO] [i]  {permanently_lost} files could not be recovered (likely empty/unsupported events)")
                    print(f"                 Common reasons:")
                    print(f"                 * EMON created empty file (0 bytes) - event not supported on this CPU SKU")
                    print(f"                 * Event name typo or not available in this EMON version")
                    print(f"                 * Network timeout - file took >120s to transfer")
                    print(f"                 * Check {temp_dir} on SUT for remaining files")
        
        phase2_time = time.time() - phase2_start
        transfer_rate = len(output_files) / phase2_time if phase2_time > 0 else 0
        
        # Calculate verification statistics
        successful_transfers = len(output_files) - len(failed_transfers) - zero_byte_files
        total_attempted = len(output_files) - zero_byte_files
        verification_rate = (successful_transfers / total_attempted * 100) if total_attempted > 0 else 0
        
        # Show transfer efficiency and verification stats (debug mode only)
        if self.debug:
            if zero_byte_files > 0:
                print(f"\n      [EFFICIENCY] [*] Skipped {zero_byte_files} empty files (0 bytes, truly unsupported) - saved ~{zero_byte_files * 2:.1f}s transfer time")
            
            if successful_transfers > 0:
                print(f"      [VERIFICATION] [OK] {successful_transfers}/{total_attempted} transfers verified ({verification_rate:.1f}% integrity match)")
        
        if self.debug:
            actual_transfers = len(output_files) - zero_byte_files
            print(f"      [STATS] Transferred: {actual_transfers}/{len(output_files)} files ({phase2_time:.1f}s, {transfer_rate:.1f} files/s)")
        if self.debug:
            actual_transfers = len(output_files) - zero_byte_files
            print(f"      [STATS] Transferred: {actual_transfers}/{len(output_files)} files ({phase2_time:.1f}s, {transfer_rate:.1f} files/s)")
        
        # Phase 3: Cleanup all files at once
        if not quiet:
            print(f"      [PHASE 3/3] Cleaning up...")
        phase3_start = time.time()
        cleanup_files = ";".join([f'Remove-Item "{f}" -Force -ErrorAction SilentlyContinue' for f, _, _, _ in output_files])
        # Increased timeout from 30s to 120s for large batch cleanup (85+ files)
        self.transfer.execute_command(cleanup_files, timeout=120)
        phase3_time = time.time() - phase3_start
        
        # Final stats with detailed analysis
        total_active = len(all_active)
        total_tested = total_active + len(all_inactive)
        pct = (total_active/total_tested*100) if total_tested > 0 else 0
        
        # Sort by activity count to find hottest events
        sorted_active = sorted(all_active, key=lambda x: x['total_activity'], reverse=True)
        top_10 = sorted_active[:10]
        total_time = time.time() - domain_start_time
        if not quiet:
            print(f"      [RESULT] {total_active}/{total_tested} active ({pct:.1f}%)")
        if self.debug:
            print(f"      [TIMING] Total: {total_time:.1f}s (Collection: {phase1_time:.1f}s, Transfer: {phase2_time:.1f}s, Cleanup: {phase3_time:.1f}s)")
        
        # Show adaptive timeout info if it changed (only in debug mode)
        if self.debug and self.current_timeout != self.base_timeout:
            print(f"      [ADAPTIVE] Timeout scaled: {self.base_timeout}s -> {self.current_timeout}s (SUT under stress)")
        
        # Show top 10 most active events with per-core breakdown (only in debug mode)
        if self.debug and top_10:
            print(f"\n      [TOP 10 HOTTEST EVENTS]")
            for i, event_data in enumerate(top_10, 1):
                event_name = event_data['event']
                total_count = event_data['total_activity']
                max_core = event_data.get('max_core_count', 0)
                min_core = event_data.get('min_core_count', 0)
                avg_core = event_data.get('avg_core_count', 0)
                active_cores = event_data.get('active_cores', 0)
                total_cores = event_data.get('total_cores', 0)
                
                # Get domain-specific unit name for display
                unit_short = self._get_domain_unit_name(domain)
                
                print(f"         {i:2d}. {event_name:45s}")
                print(f"             Total: {total_count:,} | Avg/Core: {avg_core:,} | Max: {max_core:,} | Min: {min_core:,} | Active: {active_cores}/{total_cores} {unit_short}")
        
        return all_active, all_inactive
    
    def parse_emon_output(self, output, expected_events, discarded_events=None, domain=''):
        """Parse EMON output to identify active events with per-core breakdown."""
        if discarded_events is None:
            discarded_events = set()
        
        # Debug: Show first 500 chars of output
        if self.debug and len(output) < 200:
            print(f"\n      [DEBUG] Output too short ({len(output)} bytes): {output[:100]}")
        
        active_events = []
        inactive_events = []
        found_events = set()
        
        # EMON always returns 3 fixed core events first, then the requested events
        EMON_FIXED_EVENTS = ['INST_RETIRED.ANY', 'CPU_CLK_UNHALTED.THREAD', 'CPU_CLK_UNHALTED.REF_TSC']
        
        lines = output.split('\n')
        
        # Process each event exactly once
        for event in expected_events:
            event_found = False
            total = 0
            per_core_counts = []
            
            for line in lines:
                line = line.strip()
                if not line or '=' in line or 'Version' in line or 'real' in line:
                    continue
                
                # Skip the 3 fixed EMON events - they're core reference, not domain events
                line_starts_with_fixed = any(line.startswith(fixed_event) for fixed_event in EMON_FIXED_EVENTS)
                if line_starts_with_fixed and event not in EMON_FIXED_EVENTS:
                    continue
                
                # Check if this line contains this specific event
                event_base = event.split('.')[0] if '.' in event else event
                
                if event_base in line or event in line:
                    # Extract the event name from the line to verify it's an exact match
                    parts = line.split()
                    if parts and parts[0] in [event, event_base]:
                        # Extract numbers from the line, but skip the event name itself
                        # Split by whitespace and parse numeric values only
                        numeric_parts = parts[1:]  # Skip event name
                        
                        per_core_values = []
                        for part in numeric_parts:
                            try:
                                # Remove commas and convert to int
                                value = int(part.replace(',', ''))
                                per_core_values.append(value)
                            except ValueError:
                                continue
                        
                        if per_core_values:
                            # ALL EMON events have timestamp as first column
                            # Skip column 0 (timestamp), parse columns 1+ (actual counter values)
                            for i, value in enumerate(per_core_values):
                                if i == 0:
                                    continue  # Skip timestamp column for all events
                                per_core_counts.append(value)
                                total += value
                            
                            event_found = True
                            break  # Found the event, stop searching lines
            
            # Categorize based on what we found
            if event_found:
                found_events.add(event)
                
                # Calculate per-module/per-core stats
                valid_modules = [c for c in per_core_counts if c > 0]
                max_module_count = max(per_core_counts) if per_core_counts else 0
                min_module_count = min(per_core_counts) if per_core_counts else 0
                avg_module_count = total / len(per_core_counts) if per_core_counts else 0
                
                # Debug: For uncore domains with zero counts, show if they're in CSV at all
                if self.debug and total == 0 and domain and ('cbo' in domain.lower() or 'ncu' in domain.lower()) and len(per_core_counts) > 0:
                    print(f"      [DEBUG] {domain}/{event}: Found in CSV with {len(per_core_counts)} columns, all zeros")
                
                event_data = {
                    'event': event,
                    'domain': domain,
                    'total_activity': total,
                    'per_core_counts': per_core_counts,
                    'active_cores': len(valid_modules),
                    'total_cores': len(per_core_counts),
                    'max_core_count': max_module_count,
                    'min_core_count': min_module_count,
                    'avg_core_count': int(avg_module_count)
                }
                
                if total >= self.min_activity_threshold:
                    event_data['status'] = 'active'
                    active_events.append(event_data)
                elif total == 0:
                    # Validate if this is PMU starvation or other causes
                    # Run diagnostics on first long collection to establish root cause
                    if self.collection_duration >= 30 and len(per_core_counts) > 0:
                        # Run PMU diagnostics once per collection
                        if self.pmu_diagnostic_report is None and self.os_type == 'linux':
                            if self.debug:
                                print(f"\n      [PMU-DIAG] Running Linux PMU diagnostics (first all-zero event)...")
                            self.pmu_diagnostic_report = self.pmu_diagnostics.run_comprehensive_diagnostics()
                            if self.debug:
                                print(f"      [PMU-DIAG] Confidence: {self.pmu_diagnostic_report['confidence_score']*100:.0f}%")
                                print(f"      [PMU-DIAG] Root cause: {self.pmu_diagnostic_report['root_cause']}")
                        
                        # Validate this specific event
                        validation = validate_pmu_starvation_data_quality(
                            domain=domain,
                            event=event,
                            per_core_counts=per_core_counts,
                            collection_duration=self.collection_duration,
                            os_type=self.os_type,
                            pmu_diagnostics=self.pmu_diagnostic_report
                        )
                        
                        event_data['status'] = validation['status']
                        event_data['validation_confidence'] = validation['confidence']
                        event_data['safe_for_ml'] = validation['safe_for_ml_training']
                        
                        if validation['is_pmu_starved']:
                            event_data['error_detail'] = f"PMU counter exhaustion (confidence: {validation['confidence']*100:.0f}%)"
                            if self.debug and domain:
                                print(f"      [DEBUG] {domain}/{event}: PMU STARVED (validated, conf={validation['confidence']*100:.0f}%)")
                        else:
                            event_data['error_detail'] = '; '.join(validation['alternative_causes'])
                            if self.debug and domain:
                                print(f"      [DEBUG] {domain}/{event}: {validation['status']} - {validation['alternative_causes'][0] if validation['alternative_causes'] else 'Unknown'}")
                    else:
                        event_data['status'] = 'no_activity'
                        event_data['safe_for_ml'] = True
                    inactive_events.append(event_data)
                else:
                    # total > 0 but < threshold (low activity)
                    event_data['status'] = 'low_activity'
                    event_data['safe_for_ml'] = True  # Low activity is valid training data
                    inactive_events.append(event_data)
            else:
                # Event not found in output - check if it was discarded
                if event in discarded_events:
                    status = 'event_not_exists'
                else:
                    status = 'not_found'
                
                inactive_events.append({
                    'event': event,
                    'domain': domain,
                    'total_activity': 0,
                    'per_core_counts': [],
                    'active_cores': 0,
                    'total_cores': 0,
                    'max_core_count': 0,
                    'min_core_count': 0,
                    'avg_core_count': 0,
                    'status': status
                })
        
        return active_events, inactive_events
    
    def process_pending_transfers(self):
        """Transfer and parse all pending files from SUT (for multi-domain deferred mode).
        
        Returns:
            Tuple of (all_active_events, all_inactive_events, domain_results_dict)
        """
        if not self.pending_files:
            return [], [], {}
        
        import time
        num_files = len(self.pending_files)
        
        if self.debug:
            print(f"\n      [BATCH TRANSFER] Processing {num_files} pending files from all domains...")
        
        # Calculate total collection time from number of files (each file = 1 batch)
        # This is more accurate than single batch duration since files accumulate over entire run
        estimated_total_collection_time = num_files * self.collection_duration
        
        # Smart transfer strategy based on TOTAL COLLECTION TIME (file size predictor)
        # Short total runtime (<5min): Small files, fast transfer
        # Long total runtime (≥5min): Large accumulated files, need extended timeouts
        is_long_collection = estimated_total_collection_time >= 300  # 5 minutes
        
        if is_long_collection and self.debug:
            total_min = estimated_total_collection_time / 60
            print(f"      [TRANSFER MODE] Long collection (~{total_min:.1f}min total) - using large file transfer mode")
            print(f"                      Expected large CSV files - enhanced reliability enabled")
        
        transfer_start = time.time()
        
        all_active = []
        all_inactive = []
        domain_results = {}
        
        failed_transfers = []
        zero_byte_files = 0  # Track unsupported events (0-byte files)
        pmu_starved_files = 0  # Track PMU starvation (non-zero files with all-zero data)
        
        # Add initial settling delay for large file operations
        # Long collections create large CSV files that take time to flush to disk
        if is_long_collection:
            settling_delay = min(10, estimated_total_collection_time / 60)  # Scale with total time, max 10s
            if self.debug:
                print(f"      [FILESYSTEM] Waiting {settling_delay:.1f}s for large files to flush to disk...")
            time.sleep(settling_delay)
        
        for i, (output_file, batch_events, domain, discarded_events, emon_error) in enumerate(self.pending_files):
            content = None
            transfer_success = False
            
            # Adaptive retry and timeout based on total collection time (file size predictor)
            # Short collections: 3 retries, 180s timeout (files ~few KB)
            # Long collections: 6 retries, scaled timeout (files can be MB+)
            if is_long_collection:
                max_retries = 6
                # For long collections (>5min total), allow generous timeouts for large files
                # Scale: 1min per minute of collection, max 30min for very long runs
                read_timeout = min(1800, int(estimated_total_collection_time / 60) * 60 + 180)
            else:
                max_retries = 3
                read_timeout = 180
            
            # Try multiple times to read the file
            for attempt in range(max_retries):
                try:
                    # First verify file exists and has content (OS-specific)
                    if self.os_type == 'linux':
                        verify_cmd = f'if [ -f "{output_file}" ]; then stat -c%s "{output_file}" 2>/dev/null; else echo "MISSING"; fi'
                    else:
                        verify_cmd = f'if (Test-Path "{output_file}") {{ (Get-Item "{output_file}").Length }} else {{ "MISSING" }}'
                    v_success, v_output, _ = self.transfer.execute_command(verify_cmd, timeout=min(read_timeout, 120))
                    
                    if v_output and v_output.strip() != "MISSING":
                        try:
                            file_size = int(v_output.strip())
                            if file_size == 0:
                                # File is empty (0 bytes) - event not supported on this CPU
                                # Skip transfer entirely and mark as unsupported
                                zero_byte_files += 1
                                # Mark as unsupported and exit retry loop
                                for event in batch_events:
                                    inactive_event = {
                                        'event': event,
                                        'total_activity': 0,
                                        'samples': 0,
                                        'status': 'unsupported',
                                        'error_detail': 'Event not supported on this CPU (0-byte file)'
                                    }
                                    all_inactive.append(inactive_event)
                                    
                                    if domain not in domain_results:
                                        domain_results[domain] = {'active': [], 'inactive': []}
                                    domain_results[domain]['inactive'].append(inactive_event)
                                break  # Exit retry loop - don't attempt transfer
                            elif file_size > 0:
                                # Adaptive transfer strategy based on file size
                                # Large files (>10MB): Use sampled transfer (header + tail)
                                # Medium files (5-10MB): Use compression if available
                                # Small files (<5MB): Direct transfer
                                file_size_mb = file_size / (1024 * 1024)
                                
                                if file_size_mb > 10:
                                    # Very large file - use sampled transfer (header + tail)
                                    # Read first 5MB (with header) + last 5MB for statistical sampling
                                    if self.debug and attempt == 0:
                                        print(f"\n      [LARGE FILE] {os.path.basename(output_file)}: {file_size_mb:.1f}MB detected, using sampled transfer...", end="", flush=True)
                                    
                                    if self.os_type == 'linux':
                                        # Read first 5MB and last 5MB
                                        read_cmd = f'(head -c 5242880 "{output_file}" 2>/dev/null; echo "__CHUNK_SEPARATOR__"; tail -c 5242880 "{output_file}" 2>/dev/null) || echo "ERROR"'
                                    else:
                                        # Windows: Read first 5MB and last 5MB using Get-Content with byte ranges
                                        read_cmd = f'$file="{output_file}"; if (Test-Path $file) {{ $bytes=[System.IO.File]::ReadAllBytes($file); $head=$bytes[0..[Math]::Min(5242879,$bytes.Length-1)]; $tail=$bytes[[Math]::Max(0,$bytes.Length-5242880)..($bytes.Length-1)]; [System.Text.Encoding]::UTF8.GetString($head) + "`n__CHUNK_SEPARATOR__`n" + [System.Text.Encoding]::UTF8.GetString($tail) }} else {{ "ERROR" }}'
                                    
                                    # Use extended timeout for large file chunks (up to read_timeout, no artificial cap)
                                    chunk_timeout = read_timeout
                                    s2, content, _ = self.transfer.execute_command(read_cmd, timeout=chunk_timeout)
                                    
                                    # Merge chunks if separator found
                                    if content and '__CHUNK_SEPARATOR__' in content:
                                        parts = content.split('__CHUNK_SEPARATOR__')
                                        if len(parts) == 2:
                                            # Reconstruct: header + middle estimate + tail
                                            # For EMON CSV, middle rows are similar format
                                            content = parts[0] + parts[1]  # Concatenate for parsing
                                            if self.debug:
                                                print(f" sampled {len(content)} bytes", end="", flush=True)
                                elif file_size_mb > 5:
                                    # Medium file - try gzip compression if available
                                    if self.os_type == 'linux':
                                        # Check if gzip available and use it
                                        read_cmd = f'if command -v gzip &>/dev/null; then gzip -c "{output_file}" 2>/dev/null | base64; else cat "{output_file}" 2>/dev/null; fi'
                                        s2, content, _ = self.transfer.execute_command(read_cmd, timeout=read_timeout)
                                        
                                        # Decompress if base64 encoded
                                        if content and not content.startswith('#'):
                                            try:
                                                import base64
                                                import gzip
                                                decoded = base64.b64decode(content)
                                                content = gzip.decompress(decoded).decode('utf-8')
                                                if self.debug:
                                                    compression_ratio = (1 - len(decoded)/file_size) * 100
                                                    print(f"\n      [COMPRESSION] {domain if domain else 'unknown'}/{os.path.basename(output_file)}: {file_size_mb:.1f}MB -> {len(decoded)/(1024*1024):.1f}MB ({compression_ratio:.0f}% reduction)", end="", flush=True)
                                            except:
                                                pass  # Fall through to standard parsing
                                    else:
                                        # Windows: standard transfer
                                        read_cmd = f'Get-Content "{output_file}" -Raw -ErrorAction SilentlyContinue'
                                        s2, content, _ = self.transfer.execute_command(read_cmd, timeout=read_timeout)
                                else:
                                    # Small file - direct transfer
                                    if self.os_type == 'linux':
                                        read_cmd = f'cat "{output_file}" 2>/dev/null'
                                    else:
                                        read_cmd = f'Get-Content "{output_file}" -Raw -ErrorAction SilentlyContinue'
                                    s2, content, _ = self.transfer.execute_command(read_cmd, timeout=read_timeout)
                                
                                if content and content.strip() and 'ERROR' not in content:
                                    # Verify transfer integrity: compare received size with SUT file size
                                    received_size = len(content)
                                    
                                    # For sampled transfers (large files), expected size is ~10MB, not full file
                                    if file_size_mb > 10 and '__CHUNK_SEPARATOR__' in content:
                                        # Sampled transfer - validate we got both chunks
                                        if received_size > 1000000:  # At least 1MB of data
                                            transfer_success = True
                                            if self.debug:
                                                print(f" [OK] sampled", flush=True)
                                            break
                                    else:
                                        # Full transfer - check size match
                                        size_match_pct = (received_size / file_size * 100) if file_size > 0 else 0
                                        
                                        # Allow 2% variance for line ending differences (Windows \r\n vs Linux \n)
                                        # For compressed files, allow wider variance (up to 10% due to encoding overhead)
                                        variance_threshold = 10 if file_size_mb > 5 else 2
                                        
                                        if size_match_pct >= (100 - variance_threshold) and size_match_pct <= (100 + variance_threshold):
                                            transfer_success = True
                                            # Log verification in debug mode
                                            if self.debug and (i % 50 == 0 or file_size_mb > 5):  # Every 50th file or large files
                                                print(f"\n      [VERIFY] File {i+1}: SUT={file_size_mb:.1f}MB, Host={received_size/(1024*1024):.1f}MB ({size_match_pct:.1f}% match) [OK]", flush=True)
                                            break
                                        else:
                                            # Size mismatch - possible corruption or incomplete transfer
                                            if self.debug or size_match_pct < 90:  # Always warn on >10% mismatch
                                                print(f"\n      [WARNING] File {i+1}: Size mismatch - SUT={file_size_mb:.1f}MB, Host={received_size/(1024*1024):.1f}MB ({size_match_pct:.1f}%)", flush=True)
                                            # Don't mark as success - will retry
                                            if attempt < max_retries - 1:
                                                # Wait longer for large file transfers to complete
                                                retry_delay = (3.0 if is_long_collection else 1.0) * (attempt + 1)
                                                time.sleep(retry_delay)
                                                continue
                        except ValueError as e:
                            if self.debug:
                                print(f"\n      [ERROR] File {i+1}: Invalid file size response: {e}", flush=True)
                            # Continue to retry
                            pass
                    
                    # Wait before retry (adaptive backoff based on file size/collection duration)
                    # Short collections: 0.5s base (small files, fast retry)
                    # Long collections: 2s base (large files, need more time for network/disk)
                    if attempt < (max_retries - 1) and not transfer_success:
                        retry_delay = (2.0 if is_long_collection else 0.5) * (attempt + 1)
                        time.sleep(retry_delay)
                        
                except Exception as e:
                    # Catch all exceptions: network errors, SSH failures, timeouts, etc.
                    if self.debug or attempt == max_retries - 1:  # Show on last attempt
                        print(f"\n      [ERROR] File {i+1} attempt {attempt+1}/{max_retries}: {type(e).__name__}: {str(e)[:100]}", flush=True)
                    
                    # For critical network errors, wait longer before retry
                    if attempt < max_retries - 1:
                        retry_delay = (3.0 if is_long_collection else 1.5) * (attempt + 1)
                        if self.debug:
                            print(f"      Retrying in {retry_delay:.1f}s...", flush=True)
                        time.sleep(retry_delay)
            
            if transfer_success and content:
                active, inactive = self.parse_emon_output(content, batch_events, discarded_events, domain)
                all_active.extend(active)
                all_inactive.extend(inactive)
                
                # Track per-domain results
                if domain not in domain_results:
                    domain_results[domain] = {'active': [], 'inactive': []}
                domain_results[domain]['active'].extend(active)
                domain_results[domain]['inactive'].extend(inactive)
            else:
                # Log failed transfer for later retry
                failed_transfers.append((output_file, batch_events, domain, discarded_events, i))
                
                for event in batch_events:
                    inactive_event = {
                        'event': event,
                        'total_activity': 0,
                        'samples': 0,
                        'status': 'event_not_exists' if event in discarded_events else 'no_file',
                        'error_detail': 'File not found or empty after 3 attempts'
                    }
                    all_inactive.append(inactive_event)
                    
                    if domain not in domain_results:
                        domain_results[domain] = {'active': [], 'inactive': []}
                    domain_results[domain]['inactive'].append(inactive_event)
            
            # Progress bar only in debug mode
            if self.debug:
                progress = (i + 1) / len(self.pending_files)
                bar_length = 40
                filled = int(bar_length * progress)
                bar = '█' * filled + '░' * (bar_length - filled)
                
                elapsed = time.time() - transfer_start
                if i > 0:
                    avg_per_file = elapsed / (i + 1)
                    remaining_files = len(self.pending_files) - (i + 1)
                    eta_seconds = remaining_files * avg_per_file
                    eta_str = f"{int(eta_seconds // 60)}m {int(eta_seconds % 60)}s" if eta_seconds >= 60 else f"{int(eta_seconds)}s"
                    print(f"\r         [{bar}] {i+1}/{len(self.pending_files)} files | Elapsed: {int(elapsed)}s | ETA: {eta_str}", end='', flush=True)
                else:
                    print(f"\r         [{bar}] {i+1}/{len(self.pending_files)} files transferred", end='', flush=True)
        
        transfer_time = time.time() - transfer_start
        transfer_rate = len(self.pending_files) / transfer_time if transfer_time > 0 else 0
        
        # Calculate verification statistics
        successful_transfers = len(self.pending_files) - len(failed_transfers) - zero_byte_files
        total_attempted = len(self.pending_files) - zero_byte_files
        verification_rate = (successful_transfers / total_attempted * 100) if total_attempted > 0 else 0
        
        # Show transfer efficiency and verification stats
        if self.debug:
            if zero_byte_files > 0:
                # Estimate time saved: ~5s per file for long collections, ~2s for short
                time_per_file = 5 if is_long_collection else 2
                time_saved = zero_byte_files * time_per_file
                print(f"\n      [EFFICIENCY] [*] Skipped {zero_byte_files} empty files (0 bytes, truly unsupported) - saved ~{time_saved:.0f}s transfer time")
            
            if successful_transfers > 0:
                print(f"      [VERIFICATION] [OK] {successful_transfers}/{total_attempted} transfers verified ({verification_rate:.1f}% integrity match)")
        
        if self.debug:
            actual_transfers = len(self.pending_files) - zero_byte_files
            print(f"      [STATS] Transferred: {actual_transfers}/{len(self.pending_files)} files ({transfer_time:.1f}s, {transfer_rate:.1f} files/s)")
        
        # If any transfers failed, attempt robust multi-stage recovery
        if failed_transfers:
            if self.debug:
                print(f"\n      [RECOVERY] {len(failed_transfers)} files failed, initiating robust recovery...")
            recovered = 0
            permanently_failed = []
            
            # Stage 1: Adaptive delay based on collection duration
            if is_long_collection:
                # Scale delay with collection time: longer collections need more flush time
                recovery_delay = min(15, max(5, self.collection_duration / 8))
                if self.debug:
                    print(f"      [RECOVERY] Stage 1: Waiting {recovery_delay:.1f}s for disk flush...")
                time.sleep(recovery_delay)
            else:
                time.sleep(2)
            
            # Stage 2: First retry with standard timeout
            if self.debug:
                print(f"      [RECOVERY] Stage 2: Attempting standard recovery ({len(failed_transfers)} files)...")
            first_pass_failed = []
            
            for output_file, batch_events, domain, discarded_events, original_idx in failed_transfers:
                # File verification with size check (OS-specific)
                if self.os_type == 'linux':
                    verify_cmd = f'[ -f "{output_file}" ] && ls -l "{output_file}" | awk \'{{print $5}}\' && cat "{output_file}" 2>/dev/null || echo "NOTFOUND"'
                else:
                    verify_cmd = f'if (Test-Path "{output_file}") {{ (Get-Item "{output_file}").Length; Get-Content "{output_file}" -Raw }} else {{ "NOTFOUND" }}'
                
                # Recovery timeout: 1.5x base timeout, up to 45min for long collections
                recovery_timeout = min(2700, read_timeout * 1.5)
                s3, content, _ = self.transfer.execute_command(verify_cmd, timeout=recovery_timeout)
                
                if content and content.strip() and "NOTFOUND" not in content:
                    # Check file size (first line should be size in bytes)
                    lines = content.strip().split('\n', 1)
                    try:
                        file_size = int(lines[0]) if lines else 0
                        actual_content = lines[1] if len(lines) > 1 else ""
                        
                        if file_size > 0 and actual_content:
                            # Remove the placeholder inactive events we added earlier
                            all_inactive = [e for e in all_inactive if e['event'] not in batch_events or e.get('status') != 'no_file']
                            if domain in domain_results:
                                domain_results[domain]['inactive'] = [e for e in domain_results[domain]['inactive'] if e['event'] not in batch_events or e.get('status') != 'no_file']
                            
                            # Parse recovered data
                            active, inactive = self.parse_emon_output(actual_content, batch_events, discarded_events, domain)
                            all_active.extend(active)
                            all_inactive.extend(inactive)
                            
                            if domain not in domain_results:
                                domain_results[domain] = {'active': [], 'inactive': []}
                            domain_results[domain]['active'].extend(active)
                            domain_results[domain]['inactive'].extend(inactive)
                            recovered += 1
                            continue
                        elif file_size == 0:
                            if self.debug:
                                print(f"      [RECOVERY] [WARN]  Empty file: {os.path.basename(output_file)} (unsupported event)")
                            permanently_failed.append((output_file, batch_events, domain, discarded_events, original_idx, "empty"))
                            continue
                    except (ValueError, IndexError):
                        pass
                
                # Failed first pass - queue for retry
                first_pass_failed.append((output_file, batch_events, domain, discarded_events, original_idx))
                time.sleep(0.5)  # Brief pause between attempts
            
            # Stage 3: Extended retry for remaining failures
            if first_pass_failed:
                if self.debug:
                    print(f"      [RECOVERY] Stage 3: Extended retry for {len(first_pass_failed)} files (extended timeout)...")
                time.sleep(5 if is_long_collection else 2)
                
                second_pass_failed = []
                for output_file, batch_events, domain, discarded_events, original_idx in first_pass_failed:
                    # Extended timeout: 3x base timeout, up to 1 hour for very large files from long collections
                    extended_timeout = min(3600, read_timeout * 3)
                    
                    if self.os_type == 'linux':
                        verify_cmd = f'[ -f "{output_file}" ] && ls -l "{output_file}" | awk \'{{print $5}}\' && cat "{output_file}" 2>/dev/null || echo "NOTFOUND"'
                    else:
                        verify_cmd = f'if (Test-Path "{output_file}") {{ (Get-Item "{output_file}").Length; Get-Content "{output_file}" -Raw }} else {{ "NOTFOUND" }}'
                    
                    s3, content, _ = self.transfer.execute_command(verify_cmd, timeout=extended_timeout)
                    
                    if content and content.strip() and "NOTFOUND" not in content:
                        lines = content.strip().split('\n', 1)
                        try:
                            file_size = int(lines[0]) if lines else 0
                            actual_content = lines[1] if len(lines) > 1 else ""
                            
                            if file_size > 0 and actual_content:
                                all_inactive = [e for e in all_inactive if e['event'] not in batch_events or e.get('status') != 'no_file']
                                if domain in domain_results:
                                    domain_results[domain]['inactive'] = [e for e in domain_results[domain]['inactive'] if e['event'] not in batch_events or e.get('status') != 'no_file']
                                
                                active, inactive = self.parse_emon_output(actual_content, batch_events, discarded_events, domain)
                                all_active.extend(active)
                                all_inactive.extend(inactive)
                                
                                if domain not in domain_results:
                                    domain_results[domain] = {'active': [], 'inactive': []}
                                domain_results[domain]['active'].extend(active)
                                domain_results[domain]['inactive'].extend(inactive)
                                recovered += 1
                                continue
                            elif file_size == 0:
                                permanently_failed.append((output_file, batch_events, domain, discarded_events, original_idx, "empty"))
                                continue
                        except (ValueError, IndexError):
                            pass
                    
                    # Still failed - add to final failure list
                    second_pass_failed.append((output_file, batch_events, domain, discarded_events, original_idx))
                    time.sleep(1)
                
                # Stage 4: Final attempt with chunked transfer for very large files
                if second_pass_failed and is_long_collection:
                    if self.debug:
                        print(f"      [RECOVERY] Stage 4: Final attempt with chunked transfer ({len(second_pass_failed)} files)...")
                    time.sleep(3)
                    
                    for output_file, batch_events, domain, discarded_events, original_idx in second_pass_failed:
                        # Try reading file in chunks for very large files
                        if self.os_type == 'linux':
                            # Read in 10MB chunks
                            chunk_cmd = f'[ -f "{output_file}" ] && split -b 10M "{output_file}" "{output_file}.chunk" && ls "{output_file}".chunk* 2>/dev/null || echo "NOTFOUND"'
                        else:
                            # For Windows, try direct read one more time with absolute max timeout
                            chunk_cmd = f'if (Test-Path "{output_file}") {{ Get-Content "{output_file}" -Raw }} else {{ "NOTFOUND" }}'
                        
                        s3, content, _ = self.transfer.execute_command(chunk_cmd, timeout=900)  # 15 min absolute max
                        
                        if content and content.strip() and "NOTFOUND" not in content:
                            # For Linux chunks, retrieve and concatenate
                            if self.os_type == 'linux' and '.chunk' in content:
                                chunk_files = [line.strip() for line in content.split('\n') if line.strip() and '.chunk' in line]
                                full_content = ""
                                for chunk_file in chunk_files:
                                    s4, chunk_content, _ = self.transfer.execute_command(f'cat "{chunk_file}" 2>/dev/null', timeout=120)
                                    if chunk_content:
                                        full_content += chunk_content
                                    # Cleanup chunk
                                    self.transfer.execute_command(f'rm -f "{chunk_file}"', timeout=10)
                                content = full_content
                            
                            if content and content.strip():
                                all_inactive = [e for e in all_inactive if e['event'] not in batch_events or e.get('status') != 'no_file']
                                if domain in domain_results:
                                    domain_results[domain]['inactive'] = [e for e in domain_results[domain]['inactive'] if e['event'] not in batch_events or e.get('status') != 'no_file']
                                
                                active, inactive = self.parse_emon_output(content, batch_events, discarded_events, domain)
                                all_active.extend(active)
                                all_inactive.extend(inactive)
                                
                                if domain not in domain_results:
                                    domain_results[domain] = {'active': [], 'inactive': []}
                                domain_results[domain]['active'].extend(active)
                                domain_results[domain]['inactive'].extend(inactive)
                                recovered += 1
                                continue
                        
                        # Truly failed - mark as permanent failure
                        permanently_failed.append((output_file, batch_events, domain, discarded_events, original_idx, "timeout"))
            
            # Report results
            if self.debug:
                if recovered > 0:
                    print(f"      [RECOVERY] [OK] Successfully recovered {recovered}/{len(failed_transfers)} files")
                
                total_failed = len(permanently_failed) + len(second_pass_failed if 'second_pass_failed' in locals() else [])
                if total_failed > 0:
                    empty_count = sum(1 for _, _, _, _, _, reason in permanently_failed if reason == "empty")
                    timeout_count = total_failed - empty_count
                    
                    print(f"      [RECOVERY] [WARN]  {total_failed} files could not be recovered:")
                    if empty_count > 0:
                        print(f"                 * {empty_count} empty files (unsupported events on this CPU SKU)")
                    if timeout_count > 0:
                        print(f"                 * {timeout_count} transfer timeouts (file too large or network issue)")
                    
                    if timeout_count > 0:
                        print(f"      [DEBUG] Failed files:")
                        for item in (permanently_failed + [(f, b, d, de, i, "timeout") for f, b, d, de, i in (second_pass_failed if 'second_pass_failed' in locals() else [])]):
                            if len(item) == 6 and item[5] == "timeout":
                                print(f"              * {os.path.basename(item[0])}")        
        # Cleanup all files at once (OS-specific commands)
        if self.debug:
            print(f"      [CLEANUP] Removing {len(self.pending_files)} files from SUT...")
        cleanup_start = time.time()
        
        if self.os_type == 'linux':
            # Linux: use rm command
            cleanup_files = " ".join([f'rm -f "{f}"' for f, _, _, _, _ in self.pending_files])
        else:
            # Windows: use Remove-Item
            cleanup_files = ";".join([f'Remove-Item "{f}" -Force -ErrorAction SilentlyContinue' for f, _, _, _, _ in self.pending_files])
        
        # Increased timeout from 60s to 120s for large batch cleanup (85+ files)
        self.transfer.execute_command(cleanup_files, timeout=120)
        cleanup_time = time.time() - cleanup_start
        
        if self.debug:
            print(f"      [TIMING] Transfer: {transfer_time:.1f}s, Cleanup: {cleanup_time:.1f}s")
        
        # Clear pending files
        self.pending_files = []
        
        # Finalize stress tracking after all collection is complete
        if self.stress_tracking_enabled and hasattr(self, 'stress_tracker'):
            self.stress_tracking_data = self.stress_tracker.finalize_tracking()
            if self.debug:
                print(f"\n      [STRESS TRACKING] Final: {self.stress_tracking_data.get('final_classification')}")
                if self.stress_tracking_data.get('stress_changes_detected'):
                    print(f"      [STRESS TRACKING] Changes detected: {len(self.stress_tracking_data.get('timeline', []))} checkpoints")
        
        return all_active, all_inactive, domain_results
    
    def _get_domain_unit_name(self, domain):
        """Get the short unit name for a domain (e.g., 'cores', 'MCs', 'CBOs')."""
        domain_lower = domain.lower()
        
        # Core domains (P-core, E-core, Atom, Core, LP-core, etc.)
        if 'core' in domain_lower:
            return 'cores'
        
        # Memory Controller domains (IMC, MC, M2M, HBM, etc.)
        elif any(x in domain_lower for x in ['imc', 'mc', 'memory', 'm2m', 'hbm', 'ddr']):
            return 'MCs'
        
        # Cache/Caching Agent domains (CBO, CHA, LLC, etc.)
        elif any(x in domain_lower for x in ['cbo', 'cha', 'llc', 'cache']):
            if 'hac' in domain_lower:
                return 'HAC CBOs'
            return 'CBOs'
        
        # Non-Coherent Unit domains (NCU handles interrupts, events, non-coherent flows)
        elif any(x in domain_lower for x in ['ncu', 'upi', 'm3upi', 'mesh']):
            if 'hac' in domain_lower:
                return 'HAC NCUs'
            return 'NCUs'
        
        # I/O and Interconnect domains (IIO, PCIe, UFI, etc.)
        elif any(x in domain_lower for x in ['iio', 'pcie', 'ufi']):
            return 'I/O units'
        
        # Package/Socket level
        elif any(x in domain_lower for x in ['package', 'socket']):
            return 'packages'
        
        # Default fallback
        return 'units'
