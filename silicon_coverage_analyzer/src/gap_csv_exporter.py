#!/usr/bin/env python3
"""
Gap Export Module

Generates enhanced CSV exports for validation engineers with gap analysis,
severity classification, and actionable recommendations.
"""

import csv
import logging
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime
from src.root_cause_classifier import RootCauseClassifier

logger = logging.getLogger(__name__)


class GapCSVExporter:
    """Enhanced CSV export for gap analysis with validation engineer recommendations."""
    
    def __init__(self, config):
        self.config = config
        self.output_dir = Path('output')
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.backup_dir = Path(r"C:\Silicon_coverage_analyzer_data")
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize root cause classifier
        self.root_cause_classifier = RootCauseClassifier(config)
    
    def generate_gap_report_csv(self, analysis_results: Dict, sut_ip: str = None) -> Path:
        """
        Generate validation-friendly CSV gap report with severity, recommendations, and actionability.
        
        Args:
            analysis_results: Complete analysis results
            sut_ip: SUT IP address (optional)
            
        Returns:
            Path to generated CSV file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_filename = f"gap_analysis_{timestamp}.csv"
        output_path = self.output_dir / csv_filename
        
        # Extract gap data
        gaps = analysis_results.get('gaps', {})
        coverage = analysis_results.get('coverage', {})
        hw_config = analysis_results.get('hardware_config', {})
        os_type = hw_config.get('os_type', 'unknown')
        metadata = analysis_results.get('metadata', {})
        
        non_toggling_events = gaps.get('non_toggling_events', [])
        critical_gaps = gaps.get('critical_gaps', [])
        
        # Get historical context if available
        ml_analysis = analysis_results.get('ml_analysis', {})
        persistent_gaps = self._get_persistent_gaps(analysis_results)
        
        with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = [
                'Domain',
                'Event_Name',
                'Gap_Type',
                'Severity',
                'Total_Activity',
                'Reason',
                'Persistent',
                'Runs_Tested',
                'Actionable',
                'Root_Cause_Category',
                'Recommended_Workload',
                'Recommended_Action',
                'OS_Type',
                'Product'
            ]
            
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            # Write each gap event
            for gap in non_toggling_events:
                event_name = gap.get('event', '')
                domain = gap.get('domain', '')
                reason = gap.get('reason', 'unknown')
                gap_type = gap.get('gap_type', 'performance')
                
                # Determine severity
                severity = self._classify_gap_severity(gap, critical_gaps, gap_type)
                
                # Check if persistent (never toggled in history)
                is_persistent = self._is_persistent_gap(event_name, domain, persistent_gaps)
                runs_tested = persistent_gaps.get(domain, {}).get(event_name, {}).get('runs', 0)
                
                # Classify root cause using ML + rules
                root_cause = self.root_cause_classifier.classify_gap(
                    event_name, domain, reason, hw_config, os_type, metadata
                )
                
                # Determine if actionable
                actionable = root_cause['actionable']
                
                # Get recommendations
                recommended_workload = root_cause.get('recommended_workload', '')
                recommended_action = root_cause.get('recommendation', '')
                
                writer.writerow({
                    'Domain': domain.upper(),
                    'Event_Name': event_name,
                    'Gap_Type': gap_type,
                    'Severity': severity,
                    'Total_Activity': gap.get('total_activity', 0),
                    'Reason': reason,
                    'Persistent': 'Yes' if is_persistent else 'No',
                    'Runs_Tested': runs_tested if runs_tested > 0 else 1,
                    'Actionable': 'Yes' if actionable else 'No',
                    'Root_Cause_Category': root_cause['category'],
                    'Recommended_Workload': recommended_workload,
                    'Recommended_Action': recommended_action,
                    'OS_Type': os_type,
                    'Product': hw_config.get('product_name', 'Unknown')
                })
        
        # Copy to backup location
        import shutil
        backup_path = self.backup_dir / csv_filename
        shutil.copy2(output_path, backup_path)
        
        logger.info(f"[OK] Gap Analysis CSV saved to: {output_path}")
        logger.info(f"[OK] Backup saved to: {backup_path}")
        
        return output_path
    
    def _classify_gap_severity(self, gap: Dict, critical_gaps: List, gap_type: str) -> str:
        """Classify gap severity based on multiple factors."""
        event_name = gap.get('event', '')
        domain = gap.get('domain', '')
        reason = gap.get('reason', '')
        
        # Check if in critical gaps list
        is_critical = any(
            cg.get('event', '') == event_name and cg.get('domain', '') == domain 
            for cg in critical_gaps
        )
        
        if is_critical:
            return 'Critical'
        
        # Functional gaps are higher severity
        if gap_type == 'functional':
            return 'High'
        
        # Events that should exist but don't
        if reason in ['event_not_exists', 'not_found']:
            return 'Low'  # Not actionable
        
        # No activity gaps
        if reason == 'no_activity':
            # Core domains are higher priority (use pattern matching)
            domain_lower = domain.lower()
            if any(x in domain_lower for x in ['core', 'atom', 'cpu']):
                return 'High'  # Core domains are critical
            else:
                return 'Medium'
        
        return 'Medium'
    
    def _is_persistent_gap(self, event_name: str, domain: str, persistent_gaps: Dict) -> bool:
        """Check if gap is persistent (never toggled in history)."""
        if not persistent_gaps:
            return False
        
        domain_gaps = persistent_gaps.get(domain, {})
        return event_name in domain_gaps
    
    def _get_persistent_gaps(self, analysis_results: Dict) -> Dict:
        """Extract persistent gaps from ML analysis."""
        # Try to get from ml_persistent_gaps data
        ml_analysis = analysis_results.get('ml_analysis', {})
        
        # For now, return empty - will be populated by historical analyzer
        return {}
    
    def _classify_root_cause(self, event_name: str, domain: str, reason: str, 
                            hw_config: Dict, os_type: str) -> Dict:
        """
        Classify root cause of gap and determine actionability.
        
        Returns dict with: category, actionable, recommended_workload, recommendation
        """
        # Check for AVX-512 events
        if 'AVX512' in event_name or 'AVX_512' in event_name or 'ZMM' in event_name:
            avx512_enabled = hw_config.get('avx512_enabled', True)
            if not avx512_enabled:
                return {
                    'category': 'HW_Feature_Disabled',
                    'actionable': False,
                    'recommended_workload': 'N/A',
                    'recommendation': 'Enable AVX-512 in BIOS or verify CPU supports AVX-512'
                }
            else:
                return {
                    'category': 'Workload_Missing',
                    'actionable': True,
                    'recommended_workload': 'AVX-512 benchmark (e.g., HPL, LINPACK, y-cruncher)',
                    'recommendation': 'Run AVX-512 intensive workload'
                }
        
        # Check for FP/SIMD events
        if any(fp in event_name for fp in ['FP_', 'SIMD', 'SSE', 'AVX']):
            return {
                'category': 'Workload_Missing',
                'actionable': True,
                'recommended_workload': 'SPECfp, LINPACK, or floating-point benchmark',
                'recommendation': 'Add floating-point intensive workload'
            }
        
        # Check for branch events
        if 'BR_' in event_name or 'BRANCH' in event_name:
            return {
                'category': 'Workload_Missing',
                'actionable': True,
                'recommended_workload': 'Prime95, compression, or branch-heavy code',
                'recommendation': 'Add compute workload with branches/conditionals'
            }
        
        # Check for memory events
        if any(mem in event_name for mem in ['MEM_', 'LOAD_', 'STORE_', 'OFFCORE_']):
            return {
                'category': 'Workload_Missing',
                'actionable': True,
                'recommended_workload': 'stream.exe, membw, or memory-intensive benchmark',
                'recommendation': 'Add memory bandwidth/latency stress workload'
            }
        
        # Check for cache events
        if any(cache in event_name for cache in ['L1D', 'L1I', 'L2_', 'L3_', 'LLC', 'CACHE']):
            return {
                'category': 'Workload_Missing',
                'actionable': True,
                'recommended_workload': 'Cache-intensive workload (e.g., mlc, lmbench)',
                'recommendation': 'Add cache stress workload'
            }
        
        # Check for PEBS events (Windows-specific)
        if 'PEBS' in event_name and os_type.lower() == 'linux':
            return {
                'category': 'OS_Limitation',
                'actionable': False,
                'recommended_workload': 'N/A',
                'recommendation': 'PEBS events require Windows - test on Windows for PEBS coverage'
            }
        
        # Check for uncore events (pattern-based)
        domain_lower = domain.lower()
        if any(x in domain_lower for x in ['imc', 'cbo', 'cha', 'ncu', 'upi', 'mesh', 'ufibridge', 'mc', 'memctrl']):
            return {
                'category': 'Workload_Missing',
                'actionable': True,
                'recommended_workload': 'Uncore stress (memory bandwidth, cache coherency tests)',
                'recommendation': 'Add uncore-specific stress workload'
            }
        
        # Event doesn't exist
        if reason in ['event_not_exists', 'not_found']:
            return {
                'category': 'Event_Unavailable',
                'actionable': False,
                'recommended_workload': 'N/A',
                'recommendation': 'Event not available on this platform/product'
            }
        
        # Collection failure
        if reason in ['no_file', 'collection_failed']:
            return {
                'category': 'Collection_Issue',
                'actionable': True,
                'recommended_workload': 'Re-run collection',
                'recommendation': 'Check EMON collection logs for errors'
            }
        
        # Generic low/no activity
        return {
            'category': 'Workload_Missing',
            'actionable': True,
            'recommended_workload': 'General stress workload',
            'recommendation': 'Add comprehensive stress test (CPU, memory, cache)'
        }
    
    def generate_workload_recommendation_csv(self, analysis_results: Dict) -> Path:
        """
        Generate CSV with workload recommendations to close gaps.
        
        Args:
            analysis_results: Complete analysis results
            
        Returns:
            Path to generated CSV file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_filename = f"workload_recommendations_{timestamp}.csv"
        output_path = self.output_dir / csv_filename
        
        gaps = analysis_results.get('gaps', {})
        hw_config = analysis_results.get('hardware_config', {})
        os_type = hw_config.get('os_type', 'unknown')
        
        non_toggling_events = gaps.get('non_toggling_events', [])
        
        # Aggregate recommendations by workload
        workload_map = {}
        
        for gap in non_toggling_events:
            event_name = gap.get('event', '')
            domain = gap.get('domain', '')
            reason = gap.get('reason', '')
            
            root_cause = self._classify_root_cause(event_name, domain, reason, hw_config, os_type)
            
            if root_cause['actionable']:
                workload = root_cause['recommended_workload']
                category = root_cause['category']
                
                if workload and workload != 'N/A':
                    if workload not in workload_map:
                        workload_map[workload] = {
                            'events': [],
                            'domains': set(),
                            'category': category,
                            'expected_coverage_gain': 0
                        }
                    
                    workload_map[workload]['events'].append(event_name)
                    workload_map[workload]['domains'].add(domain)
        
        # Calculate expected coverage gain
        total_gaps = len(non_toggling_events)
        for workload, data in workload_map.items():
            gap_count = len(data['events'])
            data['expected_coverage_gain'] = (gap_count / total_gaps * 100) if total_gaps > 0 else 0
        
        # Sort by expected coverage gain
        sorted_workloads = sorted(workload_map.items(), key=lambda x: x[1]['expected_coverage_gain'], reverse=True)
        
        with open(output_path, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = [
                'Priority',
                'Recommended_Workload',
                'Category',
                'Gaps_Addressed',
                'Expected_Coverage_Gain_%',
                'Affected_Domains',
                'Sample_Events'
            ]
            
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for priority, (workload, data) in enumerate(sorted_workloads, 1):
                writer.writerow({
                    'Priority': priority,
                    'Recommended_Workload': workload,
                    'Category': data['category'],
                    'Gaps_Addressed': len(data['events']),
                    'Expected_Coverage_Gain_%': f"{data['expected_coverage_gain']:.1f}%",
                    'Affected_Domains': ', '.join(sorted(data['domains'])),
                    'Sample_Events': ', '.join(data['events'][:3])  # First 3 events
                })
        
        # Copy to backup
        import shutil
        backup_path = self.backup_dir / csv_filename
        shutil.copy2(output_path, backup_path)
        
        logger.info(f"[OK] Workload Recommendations CSV saved to: {output_path}")
        logger.info(f"[OK] Backup saved to: {backup_path}")
        
        return output_path
