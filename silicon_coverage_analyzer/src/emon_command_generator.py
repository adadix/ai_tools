#!/usr/bin/env python3
"""
EMON Command Generator Module

Automatically generates EMON collection commands for gap validation,
including recommended workloads, validation criteria, and ready-to-run scripts.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Any
from collections import defaultdict

logger = logging.getLogger(__name__)


class EmonCommandGenerator:
    """Generates EMON commands for targeted gap validation."""
    
    def __init__(self, config):
        self.config = config
        self.output_dir = Path(config.get('output_dir', 'output'))
        self.emon_path = config.get('emon_path', 'emon')
    
    def generate_commands(self, gap_results: Dict, workload_recommendations: Dict = None) -> Dict:
        """
        Generate EMON commands for all gaps.
        
        Args:
            gap_results: Gap detection results
            workload_recommendations: Optional workload recommendations from WorkloadGapMapper
            
        Returns:
            Dict with generated commands
        """
        logger.info("[EmonGen] Generating EMON validation commands...")
        
        # Extract gaps
        gaps = self._extract_gaps(gap_results)
        
        if not gaps:
            return {
                'status': 'no_gaps',
                'message': 'No gaps to validate - all events active'
            }
        
        # Group gaps by domain for efficient collection
        domain_groups = self._group_by_domain(gaps)
        
        # Generate commands for each domain
        commands = []
        for domain, domain_gaps in domain_groups.items():
            domain_commands = self._generate_domain_commands(
                domain, domain_gaps, workload_recommendations
            )
            commands.extend(domain_commands)
        
        # Generate validation scripts
        scripts = self._generate_validation_scripts(commands, gap_results)
        
        # Export to CSV
        self._export_commands_csv(commands)
        
        logger.info(f"[EmonGen] Generated {len(commands)} EMON commands")
        
        return {
            'status': 'complete',
            'total_commands': len(commands),
            'total_gaps': len(gaps),
            'commands': commands,
            'scripts': scripts,
            'summary': {
                'actionable_gaps': len([g for g in gaps if g.get('actionable', True)]),
                'domain_count': len(domain_groups),
                'script_count': len(scripts)
            }
        }
    
    def _extract_gaps(self, gap_results: Dict) -> List[Dict]:
        """Extract actionable gaps from results."""
        gaps = []
        
        gap_data = gap_results.get('gaps', {})
        
        for domain, domain_gaps in gap_data.items():
            if not isinstance(domain_gaps, list):
                continue
            
            for gap in domain_gaps:
                if isinstance(gap, dict):
                    event = gap.get('event', '')
                    reason = gap.get('reason', 'unknown')
                    
                    # Determine if actionable
                    actionable = reason not in ['event_not_exists', 'not_available']
                    
                    if event and actionable:
                        gaps.append({
                            'event': event,
                            'domain': domain,
                            'reason': reason,
                            'actionable': actionable
                        })
        
        return gaps
    
    def _group_by_domain(self, gaps: List[Dict]) -> Dict:
        """Group gaps by domain for batch collection."""
        groups = defaultdict(list)
        
        for gap in gaps:
            domain = gap['domain']
            groups[domain].append(gap)
        
        return dict(groups)
    
    def _generate_domain_commands(self, domain: str, gaps: List[Dict], 
                                  workload_recommendations: Dict = None) -> List[Dict]:
        """Generate EMON commands for a specific domain."""
        commands = []
        
        # Batch small domains, individual for large
        if len(gaps) <= 5:
            # Single command for all events in domain
            cmd = self._create_batch_command(domain, gaps, workload_recommendations)
            commands.append(cmd)
        else:
            # Group by event type for more targeted testing
            event_groups = self._group_by_event_type(gaps)
            
            for event_type, type_gaps in event_groups.items():
                cmd = self._create_batch_command(domain, type_gaps, workload_recommendations, event_type)
                commands.append(cmd)
        
        return commands
    
    def _group_by_event_type(self, gaps: List[Dict]) -> Dict:
        """Group events by type (FP, Branch, Memory, etc.)."""
        groups = defaultdict(list)
        
        for gap in gaps:
            event = gap['event'].upper()
            
            # Determine event type
            if 'AVX512' in event or 'AVX_512' in event:
                event_type = 'AVX512'
            elif 'FP_' in event or 'SIMD' in event or 'VEC' in event:
                event_type = 'FP_SIMD'
            elif 'BR_' in event or 'BRANCH' in event:
                event_type = 'BRANCH'
            elif 'MEM_' in event or 'LOAD' in event or 'STORE' in event:
                event_type = 'MEMORY'
            elif 'L2_' in event or 'L3_' in event or 'CACHE' in event:
                event_type = 'CACHE'
            elif 'OFFCORE' in event:
                event_type = 'OFFCORE'
            elif 'PEBS' in event:
                event_type = 'PEBS'
            elif 'UNC_' in event or 'UNCORE' in event:
                event_type = 'UNCORE'
            else:
                event_type = 'OTHER'
            
            groups[event_type].append(gap)
        
        return dict(groups)
    
    def _create_batch_command(self, domain: str, gaps: List[Dict], 
                            workload_recommendations: Dict = None,
                            event_type: str = None) -> Dict:
        """Create a single EMON command for batch testing."""
        # Get event list
        events = [g['event'] for g in gaps]
        
        # Determine recommended workload
        workload = self._get_recommended_workload(event_type or domain, events, workload_recommendations)
        
        # Build EMON command
        emon_cmd = self._build_emon_command(domain, events, workload)
        
        # Build validation criteria
        validation_criteria = self._build_validation_criteria(events, workload)
        
        # Determine OS compatibility
        os_compatibility = self._check_os_compatibility(events, domain)
        
        return {
            'domain': domain,
            'event_type': event_type or 'mixed',
            'event_count': len(events),
            'events': events,
            'workload': workload,
            'emon_command': emon_cmd,
            'validation_criteria': validation_criteria,
            'os_compatibility': os_compatibility,
            'estimated_duration': self._estimate_duration(workload)
        }
    
    def _get_recommended_workload(self, event_type: str, events: List[str], 
                                 workload_recommendations: Dict = None) -> Dict:
        """Get recommended workload for event type."""
        # Check workload recommendations first
        if workload_recommendations:
            # Use first event to get recommendation
            # In real implementation, would aggregate recommendations
            pass
        
        # Fallback to pattern-based recommendations
        workload_map = {
            'AVX512': {
                'name': 'AVX-512 Stress',
                'command': 'avx512_stress.exe',
                'args': '-t 30',
                'description': 'AVX-512 instruction stress test'
            },
            'FP_SIMD': {
                'name': 'SPECfp2017',
                'command': 'specfp2017',
                'args': '--size test',
                'description': 'Floating-point benchmark suite'
            },
            'BRANCH': {
                'name': 'Prime95',
                'command': 'prime95.exe',
                'args': '-t',
                'description': 'CPU stress with heavy branching'
            },
            'MEMORY': {
                'name': 'Stream',
                'command': 'stream.exe',
                'args': '',
                'description': 'Memory bandwidth benchmark'
            },
            'CACHE': {
                'name': 'MLC',
                'command': 'mlc.exe',
                'args': '--loaded_latency',
                'description': 'Cache and memory latency test'
            },
            'OFFCORE': {
                'name': 'Multi-threaded Stress',
                'command': 'stress-ng',
                'args': '--cpu 0 --cpu-method all -t 30',
                'description': 'Multi-core stress for offcore events'
            },
            'PEBS': {
                'name': 'PEBS Workload (Linux)',
                'command': 'sysbench',
                'args': 'cpu --threads=4 run',
                'description': 'CPU benchmark with PEBS support'
            },
            'UNCORE': {
                'name': 'Uncore Stress',
                'command': 'membw',
                'args': '-b 10000 -t 30',
                'description': 'Memory bandwidth stress for uncore'
            },
            'OTHER': {
                'name': 'Generic CPU Stress',
                'command': 'cpu_stress.exe',
                'args': '-a',
                'description': 'General CPU stress test'
            }
        }
        
        return workload_map.get(event_type, workload_map['OTHER'])
    
    def _build_emon_command(self, domain: str, events: List[str], workload: Dict) -> str:
        """Build complete EMON command."""
        # Event list (max 10 per command to avoid overflow)
        event_list = ','.join(events[:10])
        
        # Build command
        workload_cmd = f"{workload['command']} {workload['args']}"
        
        # Windows vs Linux syntax
        if 'exe' in workload['command'].lower():
            # Windows
            cmd = f'emon.exe -collect-edp -event-list "{event_list}" {workload_cmd}'
        else:
            # Linux
            cmd = f'./emon -collect-edp -event-list "{event_list}" {workload_cmd}'
        
        return cmd
    
    def _build_validation_criteria(self, events: List[str], workload: Dict) -> str:
        """Define success criteria for validation."""
        criteria = []
        
        criteria.append(f"[OK] All {len(events)} events should toggle (count > 0)")
        criteria.append("[OK] Event counts should be > 100 for meaningful coverage")
        criteria.append("[OK] No collection errors in EMON output")
        criteria.append(f"[OK] Workload '{workload['name']}' completes successfully")
        
        return ' | '.join(criteria)
    
    def _check_os_compatibility(self, events: List[str], domain: str) -> str:
        """Check OS compatibility for events."""
        has_pebs = any('PEBS' in e.upper() for e in events)
        
        if has_pebs:
            return 'linux_preferred'  # PEBS better on Linux
        elif domain.upper() == 'CORE':
            return 'both'
        else:
            return 'both'
    
    def _estimate_duration(self, workload: Dict) -> str:
        """Estimate collection duration."""
        # Parse duration from args
        args = workload.get('args', '')
        
        if '-t 30' in args or 't 30' in args:
            return '~30 seconds'
        elif '-t' in args:
            return '~1 minute'
        else:
            return '~2-3 minutes'
    
    def _generate_validation_scripts(self, commands: List[Dict], gap_results: Dict) -> Dict:
        """Generate ready-to-run validation scripts."""
        scripts = {}
        
        # Windows batch script
        windows_script = self._generate_windows_script(commands)
        scripts['windows'] = {
            'filename': 'validate_gaps.bat',
            'content': windows_script,
            'path': str(self.output_dir / 'validate_gaps.bat')
        }
        
        # Linux bash script
        linux_script = self._generate_linux_script(commands)
        scripts['linux'] = {
            'filename': 'validate_gaps.sh',
            'content': linux_script,
            'path': str(self.output_dir / 'validate_gaps.sh')
        }
        
        # Save scripts
        self._save_scripts(scripts)
        
        return scripts
    
    def _generate_windows_script(self, commands: List[Dict]) -> str:
        """Generate Windows batch script."""
        script = """@echo off
REM ========================================
REM EMON Gap Validation Script (Windows)
REM Auto-generated by Silicon Coverage Analyzer
REM ========================================

echo Starting EMON gap validation...
echo.

set OUTPUT_DIR=emon_validation_results
if not exist %OUTPUT_DIR% mkdir %OUTPUT_DIR%

"""
        
        for idx, cmd in enumerate(commands, 1):
            os_compat = cmd['os_compatibility']
            if os_compat == 'linux_preferred':
                script += f"\nREM Command {idx}: {cmd['event_type']} ({cmd['event_count']} events) - Linux Preferred\n"
                script += f"REM OS Compatibility: {os_compat} - Run on Linux for better results\n"
                script += f"REM {cmd['emon_command']}\n\n"
            else:
                script += f"\nREM Command {idx}: {cmd['event_type']} ({cmd['event_count']} events)\n"
                script += f"echo Running {cmd['workload']['name']}...\n"
                script += f"{cmd['emon_command']}\n"
                script += f"if %ERRORLEVEL% NEQ 0 (\n"
                script += f"    echo ERROR: Command {idx} failed\n"
                script += f") else (\n"
                script += f"    echo SUCCESS: {cmd['event_type']} events validated\n"
                script += f")\n"
                script += f"echo.\n\n"
        
        script += """
echo.
echo Validation complete! Check emon_validation_results folder for results.
pause
"""
        
        return script
    
    def _generate_linux_script(self, commands: List[Dict]) -> str:
        """Generate Linux bash script."""
        script = """#!/bin/bash
########################################
# EMON Gap Validation Script (Linux)
# Auto-generated by Silicon Coverage Analyzer
########################################

echo "Starting EMON gap validation..."
echo ""

OUTPUT_DIR="emon_validation_results"
mkdir -p $OUTPUT_DIR

"""
        
        for idx, cmd in enumerate(commands, 1):
            script += f"\n# Command {idx}: {cmd['event_type']} ({cmd['event_count']} events)\n"
            script += f"echo \"Running {cmd['workload']['name']}...\"\n"
            
            # Convert to Linux command format
            linux_cmd = cmd['emon_command'].replace('emon.exe', './emon').replace('.exe', '')
            
            script += f"{linux_cmd}\n"
            script += f"if [ $? -eq 0 ]; then\n"
            script += f"    echo \"SUCCESS: {cmd['event_type']} events validated\"\n"
            script += f"else\n"
            script += f"    echo \"ERROR: Command {idx} failed\"\n"
            script += f"fi\n"
            script += f"echo \"\"\n\n"
        
        script += """
echo ""
echo "Validation complete! Check emon_validation_results folder for results."
"""
        
        return script
    
    def _save_scripts(self, scripts: Dict):
        """Save validation scripts to output directory."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        for platform, script_info in scripts.items():
            filepath = Path(script_info['path'])
            
            try:
                with open(filepath, 'w') as f:
                    f.write(script_info['content'])
                
                logger.info(f"[EmonGen] Saved {platform} script: {filepath}")
            except Exception as e:
                logger.error(f"[EmonGen] Error saving {platform} script: {e}")
    
    def _export_commands_csv(self, commands: List[Dict]):
        """Export commands to CSV for easy reference."""
        import csv
        
        csv_path = self.output_dir / 'emon_validation_commands.csv'
        
        try:
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                
                # Header
                writer.writerow([
                    'Domain', 'Event_Type', 'Event_Count', 'Events', 
                    'Workload', 'EMON_Command', 'Validation_Criteria',
                    'OS_Compatibility', 'Estimated_Duration'
                ])
                
                # Data
                for cmd in commands:
                    writer.writerow([
                        cmd['domain'],
                        cmd['event_type'],
                        cmd['event_count'],
                        ', '.join(cmd['events'][:5]) + ('...' if len(cmd['events']) > 5 else ''),
                        cmd['workload']['name'],
                        cmd['emon_command'],
                        cmd['validation_criteria'],
                        cmd['os_compatibility'],
                        cmd['estimated_duration']
                    ])
            
            logger.info(f"[EmonGen] Saved commands CSV: {csv_path}")
        
        except Exception as e:
            logger.error(f"[EmonGen] Error saving CSV: {e}")
    
    def generate_emon_commands_html(self, emon_results: Dict) -> str:
        """Generate HTML display of EMON commands."""
        if emon_results['status'] == 'no_gaps':
            return f"""
            <div class="chart-container" style="background: #d4edda; border-left: 4px solid #28a745; padding: 20px;">
                <h3 style="color: #155724;">[OK] No Gaps to Validate</h3>
                <p style="color: #155724;">
                    {emon_results['message']}
                </p>
            </div>
"""
        
        summary = emon_results['summary']
        commands = emon_results['commands']
        scripts = emon_results['scripts']
        
        html = f"""
        <div class="chart-container">
            <h3 style="color: #0071c5; margin-bottom: 10px;"> EMON Validation Commands</h3>
            <p style="color: #6c757d; margin-bottom: 20px;">
                Generated {emon_results['total_commands']} targeted EMON commands to validate {emon_results['total_gaps']} gaps
            </p>
            
            <!-- Download Scripts -->
            <div style="background: #d4edda; border-left: 4px solid #28a745; padding: 20px; margin-bottom: 25px; border-radius: 8px;">
                <h4 style="margin: 0 0 15px 0; color: #155724;"> Ready-to-Run Validation Scripts</h4>
                <p style="color: #155724; margin-bottom: 15px;">
                    Scripts saved to <code>output/</code> directory - copy to test system and execute
                </p>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px;">
                    <div style="background: white; padding: 15px; border-radius: 4px;">
                        <div style="font-size: 1.2em; margin-bottom: 5px;"> Windows</div>
                        <code style="background: #f8f9fa; padding: 8px; display: block; border-radius: 4px; font-size: 0.9em;">
                            {scripts['windows']['filename']}
                        </code>
                    </div>
                    <div style="background: white; padding: 15px; border-radius: 4px;">
                        <div style="font-size: 1.2em; margin-bottom: 5px;"> Linux</div>
                        <code style="background: #f8f9fa; padding: 8px; display: block; border-radius: 4px; font-size: 0.9em;">
                            {scripts['linux']['filename']}
                        </code>
                    </div>
                </div>
            </div>
            
            <!-- Commands Table -->
            <div style="margin-top: 25px;">
                <h4 style="color: #003e7e;"> Validation Commands by Domain</h4>
                <div style="max-height: 500px; overflow-y: auto; margin-top: 15px;">
"""
        
        for idx, cmd in enumerate(commands, 1):
            os_badge_colors = {
                'both': '#28a745',
                'linux_preferred': '#ffc107',
                'windows_only': '#0071c5'
            }
            os_color = os_badge_colors.get(cmd['os_compatibility'], '#6c757d')
            
            html += f"""
                <div style="background: #f8f9fa; border-left: 5px solid #0071c5; padding: 20px; margin-bottom: 20px; border-radius: 4px;">
                    <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 15px;">
                        <div>
                            <h5 style="margin: 0 0 5px 0; color: #003e7e;">
                                Command {idx}: {cmd['domain'].upper()} - {cmd['event_type']}
                            </h5>
                            <div style="color: #666; font-size: 0.9em;">
                                {cmd['event_count']} events | {cmd['estimated_duration']} | Workload: {cmd['workload']['name']}
                            </div>
                        </div>
                        <span style="background: {os_color}; color: white; padding: 6px 12px; border-radius: 12px; font-size: 0.85em;">
                            {cmd['os_compatibility'].replace('_', ' ').title()}
                        </span>
                    </div>
                    
                    <!-- EMON Command -->
                    <div style="background: #2d2d2d; color: #f8f8f2; padding: 15px; border-radius: 4px; margin-bottom: 15px; font-family: 'Courier New', monospace; font-size: 0.9em; overflow-x: auto;">
                        {cmd['emon_command']}
                    </div>
                    
                    <!-- Validation Criteria -->
                    <div style="background: white; padding: 12px; border-radius: 4px; margin-bottom: 10px;">
                        <strong style="color: #003e7e;">Validation Criteria:</strong>
                        <div style="color: #666; font-size: 0.9em; margin-top: 5px;">
                            {cmd['validation_criteria']}
                        </div>
                    </div>
                    
                    <!-- Events List -->
                    <details>
                        <summary style="cursor: pointer; color: #0071c5; font-size: 0.9em; padding: 8px 0;">
                            Show {cmd['event_count']} events in this command
                        </summary>
                        <div style="background: white; padding: 12px; margin-top: 10px; border-radius: 4px; max-height: 150px; overflow-y: auto;">
                            <ul style="margin: 0; padding-left: 20px; font-size: 0.85em; font-family: monospace; columns: 2;">
"""
            for event in cmd['events']:
                html += f"""
                                <li style="margin: 3px 0;">{event}</li>
"""
            html += """
                            </ul>
                        </div>
                    </details>
                </div>
"""
        
        html += """
                </div>
            </div>
            
            <!-- CSV Export Notice -->
            <div style="background: #d1ecf1; border-left: 4px solid #17a2b8; padding: 15px; margin-top: 20px; border-radius: 4px;">
                <strong style="color: #0c5460;"> CSV Export Available</strong>
                <p style="color: #0c5460; margin: 8px 0 0 0; font-size: 0.9em;">
                    All commands exported to <code>output/emon_validation_commands.csv</code>
                </p>
            </div>
        </div>
"""
        
        return html
