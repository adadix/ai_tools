#!/usr/bin/env python3
"""
Gap Correlation Analyzer Module

Identifies gaps that frequently occur together, clusters them by common root cause,
and provides actionable recommendations to fix multiple gaps simultaneously.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Tuple
from collections import defaultdict
import numpy as np

logger = logging.getLogger(__name__)


class GapCorrelationAnalyzer:
    """Analyzes correlations between coverage gaps to identify common root causes."""
    
    def __init__(self, config):
        self.config = config
        # Use same absolute path as ML trainer
        self.ml_data_dir = Path(r"C:\silicon_coverage_analyzer_data")
        self.correlation_threshold = config.get('gap_correlation_threshold', 0.7)  # 70% co-occurrence
    
    def analyze_correlations(self, gap_results: Dict, historical_runs: int = 10) -> Dict:
        """
        Analyze gap correlations across current and historical runs.
        
        Args:
            gap_results: Current run's gap detection results
            historical_runs: Number of historical runs to include
            
        Returns:
            Dict with correlation analysis
        """
        logger.info("[GapCorr] Analyzing gap correlations...")
        
        # Build gap co-occurrence matrix from historical data
        gap_history = self._build_gap_history(historical_runs)
        
        if not gap_history:
            return {
                'status': 'insufficient_data',
                'message': 'Need historical gap data for correlation analysis'
            }
        
        logger.info(f"[GapCorr] Loaded {len(gap_history)} historical gap records")
        
        # Calculate correlations
        correlations = self._calculate_correlations(gap_history)
        
        # Build correlation matrix for heatmap visualization
        correlation_matrix = self._build_correlation_matrix(correlations)
        
        # Cluster gaps by correlation
        clusters = self._cluster_gaps(correlations, gap_history)
        
        # Identify root cause patterns
        root_cause_patterns = self._identify_root_cause_patterns(gap_results, clusters)
        
        # Generate actionable recommendations
        recommendations = self._generate_cluster_recommendations(clusters, root_cause_patterns)
        
        logger.info(f"[GapCorr] Found {len(clusters)} gap clusters")
        logger.info(f"[GapCorr] Identified {len(root_cause_patterns)} root cause patterns")
        
        return {
            'status': 'complete',
            'runs_analyzed': len(gap_history),
            'total_correlations': len(correlations),
            'high_correlations': len([c for c in correlations if c['correlation'] >= self.correlation_threshold]),
            'correlation_matrix': correlation_matrix,  # Add matrix for heatmap
            'clusters': clusters,
            'root_cause_patterns': root_cause_patterns,
            'recommendations': recommendations,
            'summary': {
                'cluster_count': len(clusters),
                'largest_cluster_size': max([c['event_count'] for c in clusters], default=0),
                'actionable_clusters': len([c for c in clusters if c.get('actionable', False)])
            }
        }
    
    def _build_gap_history(self, max_runs: int = 10) -> List[Dict]:
        """Build historical gap data from previous runs."""
        gap_records = []
        
        # Load historical coverage runs
        datasets_dir = self.ml_data_dir / 'raw_datasets'
        if not datasets_dir.exists():
            datasets_dir = self.ml_data_dir / 'raw_data'
        
        if not datasets_dir.exists():
            logger.warning(f"[GapCorr] Historical data directory not found: {datasets_dir}")
            return []
        
        # Find coverage files - try multiple patterns
        coverage_files = sorted(datasets_dir.glob('*/coverage_*.json'))
        if not coverage_files:
            coverage_files = sorted(datasets_dir.glob('coverage_*.json'))
        
        logger.info(f"[GapCorr] Found {len(coverage_files)} historical coverage files in {datasets_dir}")
        
        for coverage_file in coverage_files[-max_runs:]:
            try:
                with open(coverage_file, 'r') as f:
                    data = json.load(f)
                
                # Extract gaps from this run
                timestamp = data.get('timestamp', '')
                coverage = data.get('coverage_results', data.get('coverage', {}))
                domain_results = coverage.get('domain_results', {})
                
                gaps_this_run = set()
                gap_details = {}
                
                for domain, domain_data in domain_results.items():
                    if not isinstance(domain_data, dict):
                        continue
                    
                    inactive_events = domain_data.get('inactive_events', [])
                    for event_info in inactive_events:
                        if isinstance(event_info, dict):
                            event_name = event_info.get('event', '')
                            reason = event_info.get('reason', 'unknown')
                            
                            if event_name:
                                gap_key = f"{domain}:{event_name}"
                                gaps_this_run.add(gap_key)
                                gap_details[gap_key] = {
                                    'event': event_name,
                                    'domain': domain,
                                    'reason': reason
                                }
                
                if gaps_this_run:
                    gap_records.append({
                        'timestamp': timestamp,
                        'gaps': gaps_this_run,
                        'gap_details': gap_details,
                        'run_file': coverage_file.name
                    })
            
            except Exception as e:
                logger.warning(f"[GapCorr] Error loading {coverage_file.name}: {e}")
        
        return gap_records
    
    def _build_correlation_matrix(self, correlations: List[Dict]) -> Dict:
        """Build correlation matrix from correlation list for heatmap visualization."""
        matrix = {}
        
        for corr in correlations:
            gap1 = corr['gap1']
            gap2 = corr['gap2']
            correlation_value = corr['correlation']
            
            # Initialize nested dict if not exists
            if gap1 not in matrix:
                matrix[gap1] = {}
            if gap2 not in matrix:
                matrix[gap2] = {}
            
            # Store bidirectional correlation
            matrix[gap1][gap2] = correlation_value
            matrix[gap2][gap1] = correlation_value
            
            # Self-correlation is 1.0
            matrix[gap1][gap1] = 1.0
            matrix[gap2][gap2] = 1.0
        
        return matrix
    
    def _calculate_correlations(self, gap_history: List[Dict]) -> List[Dict]:
        """Calculate pairwise gap correlations (co-occurrence)."""
        # Count gap occurrences
        gap_counts = defaultdict(int)
        gap_pair_counts = defaultdict(int)
        
        total_runs = len(gap_history)
        
        for record in gap_history:
            gaps = record['gaps']
            
            # Count individual gaps
            for gap in gaps:
                gap_counts[gap] += 1
            
            # Count gap pairs (co-occurrence)
            gaps_list = sorted(list(gaps))
            for i, gap1 in enumerate(gaps_list):
                for gap2 in gaps_list[i+1:]:
                    pair_key = (gap1, gap2)
                    gap_pair_counts[pair_key] += 1
        
        # Calculate correlation coefficients
        correlations = []
        
        for (gap1, gap2), co_occurrence_count in gap_pair_counts.items():
            gap1_count = gap_counts[gap1]
            gap2_count = gap_counts[gap2]
            
            # Calculate correlation (simplified Jaccard similarity)
            # correlation = co-occurrence / (gap1_count + gap2_count - co_occurrence)
            correlation = co_occurrence_count / total_runs  # Simpler: % of runs where both occur
            
            # Only keep significant correlations
            if correlation >= self.correlation_threshold * 0.5:  # 35% threshold for keeping
                correlations.append({
                    'gap1': gap1,
                    'gap2': gap2,
                    'correlation': correlation,
                    'co_occurrence_count': co_occurrence_count,
                    'gap1_count': gap1_count,
                    'gap2_count': gap2_count,
                    'total_runs': total_runs
                })
        
        # Sort by correlation strength
        correlations.sort(key=lambda x: x['correlation'], reverse=True)
        
        return correlations
    
    def _cluster_gaps(self, correlations: List[Dict], gap_history: List[Dict]) -> List[Dict]:
        """Cluster gaps that frequently occur together."""
        # Build adjacency list of highly correlated gaps
        gap_graph = defaultdict(set)
        
        for corr in correlations:
            if corr['correlation'] >= self.correlation_threshold:
                gap1, gap2 = corr['gap1'], corr['gap2']
                gap_graph[gap1].add(gap2)
                gap_graph[gap2].add(gap1)
        
        # Find connected components (clusters)
        visited = set()
        clusters = []
        
        def dfs(gap, cluster_set):
            """Depth-first search to find connected gaps."""
            if gap in visited:
                return
            visited.add(gap)
            cluster_set.add(gap)
            for neighbor in gap_graph.get(gap, []):
                dfs(neighbor, cluster_set)
        
        for gap in gap_graph.keys():
            if gap not in visited:
                cluster_set = set()
                dfs(gap, cluster_set)
                if len(cluster_set) >= 2:  # Only include clusters with 2+ gaps
                    clusters.append(cluster_set)
        
        # Format cluster results
        formatted_clusters = []
        
        for idx, cluster in enumerate(clusters, 1):
            # Parse cluster events
            cluster_events = []
            domains = set()
            
            for gap_key in cluster:
                domain, event = gap_key.split(':', 1)
                cluster_events.append({
                    'event': event,
                    'domain': domain,
                    'gap_key': gap_key
                })
                domains.add(domain)
            
            # Determine cluster characteristics
            cluster_reasons = self._get_cluster_reasons(cluster, gap_history)
            dominant_reason = max(cluster_reasons.items(), key=lambda x: x[1])[0] if cluster_reasons else 'unknown'
            
            # Check if cluster has common pattern
            event_names = [e['event'] for e in cluster_events]
            common_pattern = self._find_common_pattern(event_names)
            
            formatted_clusters.append({
                'cluster_id': idx,
                'event_count': len(cluster),
                'domains': sorted(list(domains)),
                'events': sorted(cluster_events, key=lambda x: x['event']),
                'dominant_reason': dominant_reason,
                'common_pattern': common_pattern,
                'actionable': dominant_reason not in ['event_not_exists', 'not_available']
            })
        
        # Sort by cluster size
        formatted_clusters.sort(key=lambda x: x['event_count'], reverse=True)
        
        return formatted_clusters
    
    def _get_cluster_reasons(self, cluster: set, gap_history: List[Dict]) -> Dict:
        """Get gap reasons for events in cluster."""
        reason_counts = defaultdict(int)
        
        for record in gap_history:
            gap_details = record['gap_details']
            for gap_key in cluster:
                if gap_key in gap_details:
                    reason = gap_details[gap_key].get('reason', 'unknown')
                    reason_counts[reason] += 1
        
        return reason_counts
    
    def _find_common_pattern(self, event_names: List[str]) -> str:
        """Find common naming pattern in event cluster."""
        if not event_names:
            return 'unknown'
        
        # Check for common prefixes
        prefixes = ['AVX512', 'FP_', 'BR_', 'MEM_', 'L2_', 'L3_', 'OFFCORE', 'PEBS', 
                   'UNC_', 'PMON', 'POWER', 'THERMAL', 'RAPL']
        
        for prefix in prefixes:
            matching = sum(1 for e in event_names if prefix in e.upper())
            if matching >= len(event_names) * 0.7:  # 70% have this prefix
                return prefix
        
        # Check for common domains
        if all('UNCORE' in e.upper() or 'UNC_' in e.upper() for e in event_names):
            return 'UNCORE'
        
        if all(any(x in e.upper() for x in ['CACHE', 'L2', 'L3']) for e in event_names):
            return 'CACHE'
        
        return 'mixed'
    
    def _identify_root_cause_patterns(self, gap_results: Dict, clusters: List[Dict]) -> List[Dict]:
        """Identify common root causes across gap clusters."""
        patterns = []
        
        # Group clusters by dominant reason
        reason_groups = defaultdict(list)
        for cluster in clusters:
            reason = cluster['dominant_reason']
            reason_groups[reason].append(cluster)
        
        for reason, cluster_list in reason_groups.items():
            total_events = sum(c['event_count'] for c in cluster_list)
            
            # Determine actionability
            actionable = reason not in ['event_not_exists', 'not_available']
            
            # Get recommendation based on reason
            recommendation = self._get_reason_recommendation(reason, cluster_list)
            
            patterns.append({
                'root_cause': reason,
                'cluster_count': len(cluster_list),
                'total_events': total_events,
                'actionable': actionable,
                'recommendation': recommendation,
                'affected_domains': list(set(d for c in cluster_list for d in c['domains']))
            })
        
        # Sort by impact (total events)
        patterns.sort(key=lambda x: x['total_events'], reverse=True)
        
        return patterns
    
    def _get_reason_recommendation(self, reason: str, clusters: List[Dict]) -> str:
        """Generate recommendation based on gap reason."""
        recommendations = {
            'no_activity': 'Add comprehensive workload covering multiple instruction types',
            'collection_failed': 'Re-run collection with elevated privileges and verify EMON configuration',
            'no_file': 'Ensure complete EMON collection cycle - check for interrupted runs',
            'event_not_exists': 'Events unavailable on this CPU - skip or use alternative events',
            'not_available': 'Check CPU feature support and BIOS settings',
            'privilege_required': 'Run collection with administrator/root privileges',
            'pebs_not_supported': 'PEBS not available on this OS - use Linux for PEBS events'
        }
        
        base_recommendation = recommendations.get(reason, 'Investigate gap root cause')
        
        # Add pattern-specific guidance
        patterns = [c.get('common_pattern', 'unknown') for c in clusters]
        if 'AVX512' in patterns:
            base_recommendation += ' | For AVX-512: Run AVX-512 stress tests (e.g., Intel MKL, AVX512 benchmarks)'
        elif 'FP_' in patterns or any('FP' in p for p in patterns):
            base_recommendation += ' | For FP/SIMD: Run SPECfp2017 or LINPACK'
        elif 'BR_' in patterns:
            base_recommendation += ' | For Branch: Run Prime95 or branch-heavy benchmarks'
        elif 'MEM_' in patterns or 'CACHE' in patterns:
            base_recommendation += ' | For Memory/Cache: Run stream.exe, mlc, or lmbench'
        elif 'UNCORE' in patterns:
            base_recommendation += ' | For Uncore: Run multi-threaded stress with high memory bandwidth'
        
        return base_recommendation
    
    def _generate_cluster_recommendations(self, clusters: List[Dict], 
                                         root_cause_patterns: List[Dict]) -> List[Dict]:
        """Generate prioritized recommendations to fix clustered gaps."""
        recommendations = []
        
        for pattern in root_cause_patterns:
            if not pattern['actionable']:
                continue
            
            # Find clusters with this root cause
            matching_clusters = [c for c in clusters if c['dominant_reason'] == pattern['root_cause']]
            
            if not matching_clusters:
                continue
            
            # Calculate impact score
            total_events = pattern['total_events']
            cluster_count = pattern['cluster_count']
            impact_score = (total_events * 0.7) + (cluster_count * 0.3)
            
            recommendations.append({
                'priority': len(recommendations) + 1,
                'root_cause': pattern['root_cause'],
                'impact_score': impact_score,
                'gaps_addressed': total_events,
                'cluster_count': cluster_count,
                'affected_domains': pattern['affected_domains'],
                'recommendation': pattern['recommendation'],
                'actionable': True
            })
        
        # Sort by impact
        recommendations.sort(key=lambda x: x['impact_score'], reverse=True)
        
        # Re-assign priority
        for idx, rec in enumerate(recommendations, 1):
            rec['priority'] = idx
        
        return recommendations
    
    def generate_correlation_report_html(self, correlation_results: Dict) -> str:
        """Generate HTML visualization of gap correlations."""
        if correlation_results['status'] == 'insufficient_data':
            return f"""
            <div class="chart-container" style="background: #fff3cd; border-left: 4px solid #ffc107; padding: 20px;">
                <h3 style="color: #856404;">[i] Gap Correlation Analysis Unavailable</h3>
                <p style="color: #856404;">
                    {correlation_results['message']}
                </p>
            </div>
"""
        
        summary = correlation_results['summary']
        clusters = correlation_results['clusters']
        patterns = correlation_results['root_cause_patterns']
        recommendations = correlation_results['recommendations']
        
        html = f"""
        <div class="chart-container">
            <h3 style="color: #0071c5; margin-bottom: 10px;"> Gap Correlation Analysis</h3>
            <p style="color: #6c757d; margin-bottom: 20px;">
                Identified {summary['cluster_count']} gap clusters from {correlation_results['runs_analyzed']} historical runs
            </p>
            
            <!-- Summary Metrics -->
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin: 20px 0;">
                <div style="background: #d4edda; padding: 15px; border-left: 4px solid #28a745; border-radius: 4px; text-align: center;">
                    <div style="font-size: 2em; font-weight: bold; color: #28a745;">{summary['cluster_count']}</div>
                    <div style="color: #155724; font-size: 0.9em;">Gap Clusters</div>
                </div>
                <div style="background: #d1ecf1; padding: 15px; border-left: 4px solid #17a2b8; border-radius: 4px; text-align: center;">
                    <div style="font-size: 2em; font-weight: bold; color: #17a2b8;">{summary['largest_cluster_size']}</div>
                    <div style="color: #0c5460; font-size: 0.9em;">Largest Cluster Size</div>
                </div>
                <div style="background: #fff3cd; padding: 15px; border-left: 4px solid #ffc107; border-radius: 4px; text-align: center;">
                    <div style="font-size: 2em; font-weight: bold; color: #ffc107;">{summary['actionable_clusters']}</div>
                    <div style="color: #856404; font-size: 0.9em;">Actionable Clusters</div>
                </div>
            </div>
"""
        
        # Top Gap Clusters
        if clusters:
            html += f"""
            <div style="margin-top: 30px;">
                <h4 style="color: #003e7e;"> Top Gap Clusters (Events that Gap Together)</h4>
                <p style="color: #666; font-size: 0.9em; margin-bottom: 15px;">
                    Fix one root cause to resolve multiple gaps simultaneously
                </p>
                <div style="max-height: 400px; overflow-y: auto;">
"""
            for cluster in clusters[:10]:  # Top 10 clusters
                badge_color = '#28a745' if cluster['actionable'] else '#6c757d'
                pattern_label = cluster.get('common_pattern', 'mixed').upper()
                
                html += f"""
                    <div style="background: #f8f9fa; border-left: 5px solid {badge_color}; padding: 15px; margin-bottom: 15px; border-radius: 4px;">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                            <h5 style="margin: 0; color: #003e7e;">
                                Cluster #{cluster['cluster_id']}: {cluster['event_count']} Events
                            </h5>
                            <div>
                                <span style="background: {badge_color}; color: white; padding: 4px 10px; border-radius: 12px; font-size: 0.85em; margin-right: 5px;">
                                    {pattern_label}
                                </span>
                                <span style="background: #17a2b8; color: white; padding: 4px 10px; border-radius: 12px; font-size: 0.85em;">
                                    {cluster['dominant_reason']}
                                </span>
                            </div>
                        </div>
                        <div style="color: #666; font-size: 0.9em; margin-bottom: 8px;">
                            <strong>Domains:</strong> {', '.join(cluster['domains'])}
                        </div>
                        <details style="margin-top: 10px;">
                            <summary style="cursor: pointer; color: #0071c5; font-size: 0.9em;">
                                Show {cluster['event_count']} events in cluster
                            </summary>
                            <div style="margin-top: 10px; padding: 10px; background: white; border-radius: 4px; max-height: 150px; overflow-y: auto;">
                                <ul style="margin: 0; padding-left: 20px; font-size: 0.85em; font-family: monospace;">
"""
                for event in cluster['events'][:20]:  # Max 20 events shown
                    html += f"""
                                    <li style="margin: 3px 0;">{event['event']} <span style="color: #999;">({event['domain']})</span></li>
"""
                if len(cluster['events']) > 20:
                    html += f"""
                                    <li style="color: #999; font-style: italic;">... and {len(cluster['events']) - 20} more</li>
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
"""
        
        # Root Cause Patterns
        if patterns:
            html += f"""
            <div style="margin-top: 30px;">
                <h4 style="color: #003e7e;"> Root Cause Patterns</h4>
                <p style="color: #666; font-size: 0.9em; margin-bottom: 15px;">
                    Common reasons why gaps occur together
                </p>
                <table style="width: 100%; border-collapse: collapse; font-size: 0.9em;">
                    <thead>
                        <tr style="background: #f8f9fa;">
                            <th style="padding: 10px; text-align: left; border-bottom: 2px solid #dee2e6;">Root Cause</th>
                            <th style="padding: 10px; text-align: center; border-bottom: 2px solid #dee2e6;">Clusters</th>
                            <th style="padding: 10px; text-align: center; border-bottom: 2px solid #dee2e6;">Total Events</th>
                            <th style="padding: 10px; text-align: left; border-bottom: 2px solid #dee2e6;">Affected Domains</th>
                        </tr>
                    </thead>
                    <tbody>
"""
            for pattern in patterns[:10]:
                actionable_icon = '[OK]' if pattern['actionable'] else '[WARN]'
                html += f"""
                        <tr style="border-bottom: 1px solid #dee2e6;">
                            <td style="padding: 10px;">{actionable_icon} {pattern['root_cause']}</td>
                            <td style="padding: 10px; text-align: center;">{pattern['cluster_count']}</td>
                            <td style="padding: 10px; text-align: center; font-weight: bold; color: #dc3545;">{pattern['total_events']}</td>
                            <td style="padding: 10px; font-size: 0.85em; color: #666;">{', '.join(pattern['affected_domains'][:5])}</td>
                        </tr>
"""
            html += """
                    </tbody>
                </table>
            </div>
"""
        
        # Prioritized Recommendations
        if recommendations:
            html += f"""
            <div style="margin-top: 30px;">
                <h4 style="color: #28a745;">[TIP] Prioritized Recommendations</h4>
                <p style="color: #666; font-size: 0.9em; margin-bottom: 15px;">
                    Fix these root causes to close the most gaps efficiently
                </p>
                <div style="max-height: 300px; overflow-y: auto;">
"""
            for rec in recommendations[:5]:  # Top 5 recommendations
                html += f"""
                    <div style="background: #d4edda; border-left: 5px solid #28a745; padding: 15px; margin-bottom: 15px; border-radius: 4px;">
                        <div style="display: flex; justify-content: between; align-items: start; gap: 15px;">
                            <div style="background: #28a745; color: white; width: 40px; height: 40px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 1.2em; font-weight: bold; flex-shrink: 0;">
                                {rec['priority']}
                            </div>
                            <div style="flex-grow: 1;">
                                <h5 style="margin: 0 0 8px 0; color: #155724;">
                                    {rec['root_cause']} ({rec['gaps_addressed']} gaps in {rec['cluster_count']} clusters)
                                </h5>
                                <p style="margin: 0; color: #155724; font-size: 0.95em;">
                                    {rec['recommendation']}
                                </p>
                                <div style="margin-top: 8px; font-size: 0.85em; color: #666;">
                                    <strong>Domains:</strong> {', '.join(rec['affected_domains'])}
                                </div>
                            </div>
                        </div>
                    </div>
"""
            html += """
                </div>
            </div>
"""
        
        html += """
        </div>
"""
        
        return html
