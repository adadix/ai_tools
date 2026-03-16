#!/usr/bin/env python3
"""
Workload-Gap Mapper Module

Learns which workloads trigger which events from historical data.
Provides intelligent workload recommendations to close specific gaps.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Set
from collections import defaultdict

logger = logging.getLogger(__name__)


class WorkloadGapMapper:
    """
    Learns workload-event relationships from historical coverage data.
    Recommends specific workloads to close coverage gaps.
    """
    
    def __init__(self, config):
        self.config = config
        # Use same absolute path as ML trainer
        self.ml_data_dir = Path(r"C:\silicon_coverage_analyzer_data")
        
        # Workload-event mapping: {workload_name: {event: coverage_rate}}
        self.workload_event_map = {}
        
        # Event-workload reverse mapping: {event: [(workload, coverage_rate)]}
        self.event_workload_map = defaultdict(list)
        
        # Load or build mapping
        self._load_or_build_mapping()
    
    def _load_or_build_mapping(self):
        """Load existing mapping or build from historical data."""
        mapping_file = self.ml_data_dir / 'workload_event_mapping.json'
        
        if mapping_file.exists():
            try:
                with open(mapping_file, 'r') as f:
                    data = json.load(f)
                    self.workload_event_map = data.get('workload_event_map', {})
                    # Rebuild reverse map
                    for workload, events in self.workload_event_map.items():
                        for event, rate in events.items():
                            self.event_workload_map[event].append((workload, rate))
                    
                logger.info(f"[WorkloadMapper] Loaded mapping for {len(self.workload_event_map)} workloads")
                return
            except Exception as e:
                logger.warning(f"[WorkloadMapper] Could not load mapping: {e}")
        
        # Build mapping from historical data
        logger.info("[WorkloadMapper] Building workload-event mapping from historical data...")
        self._build_mapping_from_history()
    
    def _build_mapping_from_history(self, product_id: str = None):
        """Build workload-event mapping from historical coverage data."""
        # Look for raw datasets
        if product_id:
            datasets_dir = self.ml_data_dir / 'raw_datasets' / product_id
        else:
            datasets_dir = self.ml_data_dir / 'raw_datasets'
        
        if not datasets_dir.exists():
            datasets_dir = self.ml_data_dir / 'raw_data'
        
        if not datasets_dir.exists():
            logger.warning("[WorkloadMapper] No historical data available")
            return
        
        # Find all coverage files
        if product_id:
            coverage_files = sorted(datasets_dir.glob('coverage_*.json'))
        else:
            coverage_files = sorted(datasets_dir.glob('*/coverage_*.json'))
            if not coverage_files:
                coverage_files = sorted(datasets_dir.glob('coverage_*.json'))
        
        logger.info(f"[WorkloadMapper] Found {len(coverage_files)} historical runs")
        
        for coverage_file in coverage_files:
            try:
                with open(coverage_file, 'r') as f:
                    data = json.load(f)
                
                # Extract workload name
                metadata = data.get('metadata', {})
                workload = metadata.get('workload', metadata.get('stress_type', 'unknown'))
                
                # Treat 'unknown' as 'idle/baseline' workload (still useful for learning)
                if workload == 'unknown':
                    workload = 'idle'
                
                # Initialize workload entry
                if workload not in self.workload_event_map:
                    self.workload_event_map[workload] = {}
                
                # Extract event coverage
                coverage_results = data.get('coverage_results', data.get('coverage', {}))
                domain_results = coverage_results.get('domain_results', {})
                
                for domain, domain_data in domain_results.items():
                    if not isinstance(domain_data, dict):
                        continue
                    
                    active_events = domain_data.get('active_events', [])
                    
                    for event_info in active_events:
                        if not isinstance(event_info, dict):
                            continue
                        
                        event_name = event_info.get('event', '')
                        if not event_name:
                            continue
                        
                        # Calculate coverage rate for this event
                        total_activity = event_info.get('total_activity', 0)
                        active_cores = event_info.get('active_cores', 0)
                        total_cores = event_info.get('total_cores', 1)
                        
                        coverage_rate = (active_cores / total_cores * 100) if total_cores > 0 else 0
                        
                        # Update mapping (use max coverage seen)
                        if event_name not in self.workload_event_map[workload]:
                            self.workload_event_map[workload][event_name] = coverage_rate
                        else:
                            self.workload_event_map[workload][event_name] = max(
                                self.workload_event_map[workload][event_name],
                                coverage_rate
                            )
            
            except Exception as e:
                logger.warning(f"[WorkloadMapper] Error processing {coverage_file.name}: {e}")
                continue
        
        # Build reverse mapping
        for workload, events in self.workload_event_map.items():
            for event, rate in events.items():
                self.event_workload_map[event].append((workload, rate))
        
        # Sort by coverage rate
        for event in self.event_workload_map:
            self.event_workload_map[event].sort(key=lambda x: x[1], reverse=True)
        
        # Save mapping
        self._save_mapping()
        
        logger.info(f"[WorkloadMapper] [OK] Built mapping for {len(self.workload_event_map)} workloads")
    
    def _save_mapping(self):
        """Save workload-event mapping to disk."""
        try:
            mapping_file = self.ml_data_dir / 'workload_event_mapping.json'
            self.ml_data_dir.mkdir(parents=True, exist_ok=True)
            
            with open(mapping_file, 'w') as f:
                json.dump({
                    'workload_event_map': self.workload_event_map,
                    'total_workloads': len(self.workload_event_map),
                    'total_unique_events': len(self.event_workload_map)
                }, f, indent=2)
            
            logger.info(f"[WorkloadMapper] Saved mapping to {mapping_file}")
        except Exception as e:
            logger.warning(f"[WorkloadMapper] Could not save mapping: {e}")
    
    def recommend_workloads_for_gap(self, event_name: str, domain: str = None) -> List[Dict]:
        """
        Recommend workloads that historically triggered this event.
        
        Args:
            event_name: Event that didn't toggle
            domain: Domain name (optional)
            
        Returns:
            List of recommendations sorted by effectiveness
        """
        recommendations = []
        
        # Check if we have historical data for this exact event
        if event_name in self.event_workload_map:
            for workload, coverage_rate in self.event_workload_map[event_name]:
                recommendations.append({
                    'workload': workload,
                    'expected_coverage': coverage_rate,
                    'confidence': 'high' if coverage_rate > 80 else 'medium' if coverage_rate > 50 else 'low',
                    'source': 'historical_data',
                    'details': f'Event toggled at {coverage_rate:.0f}% coverage with this workload'
                })
        
        # If no exact match, try pattern matching
        if not recommendations:
            recommendations = self._pattern_based_recommendations(event_name, domain)
        
        return recommendations[:5]  # Top 5 recommendations
    
    def _pattern_based_recommendations(self, event_name: str, domain: str = None) -> List[Dict]:
        """Generate recommendations based on event name patterns."""
        recommendations = []
        
        # FP/SIMD events
        if any(fp in event_name for fp in ['FP_', 'SIMD', 'AVX', 'SSE']):
            recommendations.append({
                'workload': 'SPECfp2017',
                'expected_coverage': 85,
                'confidence': 'medium',
                'source': 'pattern_match',
                'details': 'FP/SIMD events typically triggered by floating-point benchmarks'
            })
            recommendations.append({
                'workload': 'LINPACK',
                'expected_coverage': 80,
                'confidence': 'medium',
                'source': 'pattern_match',
                'details': 'Dense linear algebra workload for FP operations'
            })
        
        # Branch events
        elif any(br in event_name for br in ['BR_', 'BRANCH']):
            recommendations.append({
                'workload': 'Prime95',
                'expected_coverage': 75,
                'confidence': 'medium',
                'source': 'pattern_match',
                'details': 'Compute-intensive with many conditional branches'
            })
            recommendations.append({
                'workload': '7-zip compression',
                'expected_coverage': 70,
                'confidence': 'medium',
                'source': 'pattern_match',
                'details': 'Branch-heavy compression algorithms'
            })
        
        # Memory events
        elif any(mem in event_name for mem in ['MEM_', 'LOAD_', 'STORE_', 'OFFCORE_']):
            recommendations.append({
                'workload': 'stream.exe',
                'expected_coverage': 90,
                'confidence': 'high',
                'source': 'pattern_match',
                'details': 'Memory bandwidth benchmark - excellent for memory events'
            })
            recommendations.append({
                'workload': 'membw',
                'expected_coverage': 85,
                'confidence': 'medium',
                'source': 'pattern_match',
                'details': 'Memory bandwidth stress test'
            })
        
        # Cache events
        elif any(cache in event_name for cache in ['L1D', 'L1I', 'L2_', 'L3_', 'LLC', 'CACHE']):
            recommendations.append({
                'workload': 'mlc (Memory Latency Checker)',
                'expected_coverage': 88,
                'confidence': 'high',
                'source': 'pattern_match',
                'details': 'Cache hierarchy stress test'
            })
            recommendations.append({
                'workload': 'lmbench',
                'expected_coverage': 75,
                'confidence': 'medium',
                'source': 'pattern_match',
                'details': 'Micro-benchmark suite for cache/memory'
            })
        
        # Uncore events
        elif domain and domain in ['imc', 'cbo', 'hac_cbo', 'ncu', 'hac_ncu']:
            recommendations.append({
                'workload': 'Uncore stress suite',
                'expected_coverage': 70,
                'confidence': 'medium',
                'source': 'domain_match',
                'details': f'Uncore domain {domain} requires specific stress tests'
            })
        
        # Generic fallback
        else:
            recommendations.append({
                'workload': 'Comprehensive stress (CPU + Memory + Cache)',
                'expected_coverage': 60,
                'confidence': 'low',
                'source': 'generic',
                'details': 'Generic recommendation - event pattern not recognized'
            })
        
        return recommendations
    
    def get_gap_closure_plan(self, gaps: List[Dict], top_n: int = 10) -> List[Dict]:
        """
        Generate prioritized workload plan to close the most gaps.
        
        Args:
            gaps: List of gap events
            top_n: Number of top workloads to recommend
            
        Returns:
            List of workload recommendations sorted by impact
        """
        # Aggregate recommendations by workload
        workload_impact = defaultdict(lambda: {
            'gaps_addressed': set(),
            'total_expected_coverage': 0,
            'confidence_scores': [],
            'sample_events': []
        })
        
        for gap in gaps:
            event_name = gap.get('event', '')
            domain = gap.get('domain', '')
            
            recommendations = self.recommend_workloads_for_gap(event_name, domain)
            
            for rec in recommendations[:2]:  # Top 2 per event
                workload = rec['workload']
                workload_impact[workload]['gaps_addressed'].add(event_name)
                workload_impact[workload]['total_expected_coverage'] += rec['expected_coverage']
                
                conf_score = {'high': 3, 'medium': 2, 'low': 1}.get(rec['confidence'], 1)
                workload_impact[workload]['confidence_scores'].append(conf_score)
                
                if len(workload_impact[workload]['sample_events']) < 5:
                    workload_impact[workload]['sample_events'].append(event_name)
        
        # Calculate priority scores
        closure_plan = []
        for workload, impact in workload_impact.items():
            gap_count = len(impact['gaps_addressed'])
            avg_coverage = impact['total_expected_coverage'] / gap_count if gap_count > 0 else 0
            avg_confidence = sum(impact['confidence_scores']) / len(impact['confidence_scores']) if impact['confidence_scores'] else 0
            
            # Priority score: weighted combination
            priority_score = (gap_count * 0.5) + (avg_coverage * 0.3) + (avg_confidence * 20 * 0.2)
            
            closure_plan.append({
                'workload': workload,
                'priority_score': priority_score,
                'gaps_addressed': gap_count,
                'expected_coverage_gain': (gap_count / len(gaps) * 100) if gaps else 0,
                'avg_event_coverage': avg_coverage,
                'confidence': 'high' if avg_confidence > 2.5 else 'medium' if avg_confidence > 1.5 else 'low',
                'sample_events': impact['sample_events']
            })
        
        # Sort by priority score
        closure_plan.sort(key=lambda x: x['priority_score'], reverse=True)
        
        return closure_plan[:top_n]
    
    def generate_workload_plan_html(self, gaps: List[Dict]) -> str:
        """Generate HTML visualization of workload closure plan."""
        plan = self.get_gap_closure_plan(gaps, top_n=10)
        
        if not plan:
            return """
            <div class="chart-container" style="background: #fff3cd; border-left: 4px solid #ffc107;">
                <h3 style="color: #856404;">[i] Workload Recommendations Unavailable</h3>
                <p style="color: #856404;">
                    Build workload-event mapping by running multiple coverage collections with different workloads.
                </p>
            </div>
"""
        
        html = f"""
        <div class="chart-container">
            <h3 style="color: #0071c5; margin-bottom: 10px;"> Gap Closure Plan - Recommended Workloads</h3>
            <p style="color: #6c757d; margin-bottom: 20px;">
                Top {len(plan)} workloads ranked by impact. Running these will close <strong>{len(gaps)} gaps</strong>.
            </p>
            
            <table style="width: 100%; border-collapse: collapse; font-size: 0.95em;">
                <thead>
                    <tr style="background: #f8f9fa; border-bottom: 2px solid #dee2e6;">
                        <th style="padding: 12px; text-align: left;">Priority</th>
                        <th style="padding: 12px; text-align: left;">Recommended Workload</th>
                        <th style="padding: 12px; text-align: center;">Gaps Addressed</th>
                        <th style="padding: 12px; text-align: center;">Expected Coverage Gain</th>
                        <th style="padding: 12px; text-align: center;">Confidence</th>
                        <th style="padding: 12px; text-align: left;">Sample Events</th>
                    </tr>
                </thead>
                <tbody>
"""
        
        for i, item in enumerate(plan, 1):
            conf_color = {'high': '#28a745', 'medium': '#ffc107', 'low': '#6c757d'}[item['confidence']]
            
            html += f"""
                    <tr style="border-bottom: 1px solid #dee2e6;">
                        <td style="padding: 10px;">
                            <span style="background: #0071c5; color: white; padding: 5px 12px; border-radius: 15px; font-weight: bold;">
                                #{i}
                            </span>
                        </td>
                        <td style="padding: 10px;">
                            <strong style="color: #003e7e; font-size: 1.05em;">{item['workload']}</strong>
                        </td>
                        <td style="padding: 10px; text-align: center; font-weight: bold; color: #0071c5;">
                            {item['gaps_addressed']}
                        </td>
                        <td style="padding: 10px; text-align: center; font-weight: bold; color: #28a745;">
                            +{item['expected_coverage_gain']:.1f}%
                        </td>
                        <td style="padding: 10px; text-align: center;">
                            <span style="background: {conf_color}; color: white; padding: 4px 10px; border-radius: 10px; font-size: 0.85em;">
                                {item['confidence'].upper()}
                            </span>
                        </td>
                        <td style="padding: 10px; font-family: monospace; font-size: 0.85em; color: #666;">
                            {', '.join(item['sample_events'][:3])}
                            {'...' if len(item['sample_events']) > 3 else ''}
                        </td>
                    </tr>
"""
        
        html += """
                </tbody>
            </table>
        </div>
"""
        
        return html
