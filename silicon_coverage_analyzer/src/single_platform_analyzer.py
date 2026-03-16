"""
Single-Platform Analyzer for Platform Insights Tab

When cross-platform data (Windows + Linux) is unavailable, this module provides
useful insights by analyzing historical trends on the current platform.

Features:
- Historical coverage trends on current OS
- Domain progression analysis
- Workload-specific coverage patterns
- Predictive insights (ML-based "what if" for other platform)
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class SinglePlatformAnalyzer:
    """Analyzes coverage trends when only single-platform data available."""
    
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        
    def analyze_single_platform_trends(self, current_os: str, product_id: str) -> Dict[str, Any]:
        """
        Analyze historical trends on current platform.
        
        Args:
            current_os: 'windows' or 'linux'
            product_id: Product identifier (e.g., 'arrowlake_s')
            
        Returns:
            Dictionary with trend analysis results
        """
        try:
            # Load historical runs for this product + OS
            historical_runs = self._load_historical_runs(product_id, current_os)
            
            if len(historical_runs) < 2:
                return {
                    'status': 'insufficient_data',
                    'runs_available': len(historical_runs),
                    'message': f'Need at least 2 runs on {current_os.title()} for trend analysis'
                }
            
            # Analyze trends
            coverage_trend = self._analyze_coverage_progression(historical_runs)
            domain_trends = self._analyze_domain_progression(historical_runs)
            workload_patterns = self._analyze_workload_patterns(historical_runs)
            
            return {
                'status': 'complete',
                'platform': current_os,
                'runs_analyzed': len(historical_runs),
                'coverage_trend': coverage_trend,
                'domain_trends': domain_trends,
                'workload_patterns': workload_patterns,
                'recommendations': self._generate_single_platform_recommendations(
                    coverage_trend, domain_trends, workload_patterns
                )
            }
            
        except Exception as e:
            logger.error(f"Error analyzing single-platform trends: {e}")
            return {
                'status': 'error',
                'error': str(e)
            }
    
    def _load_historical_runs(self, product_id: str, os_type: str) -> List[Dict]:
        """Load historical coverage runs for specific product + OS."""
        runs = []
        
        try:
            product_dir = self.data_dir / 'raw_datasets' / product_id
            if not product_dir.exists():
                return runs
            
            # Load all coverage JSON files
            for coverage_file in sorted(product_dir.glob('coverage_*.json')):
                try:
                    with open(coverage_file, 'r') as f:
                        data = json.load(f)
                    
                    # Filter by OS type
                    metadata = data.get('metadata', {})
                    run_os = metadata.get('os_type', '').lower()
                    
                    if run_os == os_type.lower():
                        runs.append({
                            'timestamp': metadata.get('timestamp', ''),
                            'coverage': data.get('summary', {}).get('overall_coverage_percentage', 0),
                            'active_events': data.get('summary', {}).get('active_events', 0),
                            'total_events': data.get('summary', {}).get('total_events_tested', 0),
                            'domains': data.get('summary', {}).get('total_domains', 0),
                            'workload': metadata.get('workload_type', 'unknown'),
                            'coverage_by_domain': data.get('coverage_by_domain', {})
                        })
                        
                except Exception as e:
                    logger.warning(f"Could not load {coverage_file}: {e}")
                    continue
            
            return runs
            
        except Exception as e:
            logger.error(f"Error loading historical runs: {e}")
            return []
    
    def _analyze_coverage_progression(self, runs: List[Dict]) -> Dict[str, Any]:
        """Analyze how coverage has progressed over time."""
        coverage_values = [r['coverage'] for r in runs]
        
        # Calculate trend
        if len(coverage_values) >= 2:
            first_half_avg = sum(coverage_values[:len(coverage_values)//2]) / (len(coverage_values)//2)
            second_half_avg = sum(coverage_values[len(coverage_values)//2:]) / (len(coverage_values) - len(coverage_values)//2)
            trend_direction = 'improving' if second_half_avg > first_half_avg else 'declining' if second_half_avg < first_half_avg else 'stable'
            trend_magnitude = abs(second_half_avg - first_half_avg)
        else:
            trend_direction = 'unknown'
            trend_magnitude = 0
        
        return {
            'current': coverage_values[-1] if coverage_values else 0,
            'best': max(coverage_values) if coverage_values else 0,
            'worst': min(coverage_values) if coverage_values else 0,
            'average': sum(coverage_values) / len(coverage_values) if coverage_values else 0,
            'trend': trend_direction,
            'trend_magnitude': trend_magnitude,
            'history': coverage_values
        }
    
    def _analyze_domain_progression(self, runs: List[Dict]) -> Dict[str, Dict]:
        """Analyze per-domain coverage trends."""
        domain_trends = {}
        
        # Collect all domains across runs
        all_domains = set()
        for run in runs:
            all_domains.update(run.get('coverage_by_domain', {}).keys())
        
        # Analyze each domain
        for domain in all_domains:
            domain_coverage = []
            for run in runs:
                cov = run.get('coverage_by_domain', {}).get(domain, {}).get('coverage_percentage', 0)
                domain_coverage.append(cov)
            
            if domain_coverage:
                # Determine trend
                if len(domain_coverage) >= 2:
                    first_half = domain_coverage[:len(domain_coverage)//2]
                    second_half = domain_coverage[len(domain_coverage)//2:]
                    first_avg = sum(first_half) / len(first_half)
                    second_avg = sum(second_half) / len(second_half)
                    
                    if second_avg > first_avg + 5:
                        trend = 'improving'
                    elif second_avg < first_avg - 5:
                        trend = 'declining'
                    else:
                        trend = 'stable'
                else:
                    trend = 'unknown'
                
                domain_trends[domain] = {
                    'current': domain_coverage[-1],
                    'best': max(domain_coverage),
                    'average': sum(domain_coverage) / len(domain_coverage),
                    'trend': trend,
                    'history': domain_coverage
                }
        
        return domain_trends
    
    def _analyze_workload_patterns(self, runs: List[Dict]) -> Dict[str, Any]:
        """Analyze coverage patterns by workload type."""
        workload_stats = {}
        
        for run in runs:
            workload = run.get('workload', 'unknown')
            if workload not in workload_stats:
                workload_stats[workload] = {
                    'coverage_values': [],
                    'count': 0
                }
            
            workload_stats[workload]['coverage_values'].append(run['coverage'])
            workload_stats[workload]['count'] += 1
        
        # Calculate averages
        for workload, stats in workload_stats.items():
            if stats['coverage_values']:
                stats['average_coverage'] = sum(stats['coverage_values']) / len(stats['coverage_values'])
                stats['best_coverage'] = max(stats['coverage_values'])
        
        return workload_stats
    
    def _generate_single_platform_recommendations(self, coverage_trend, domain_trends, workload_patterns) -> List[Dict]:
        """Generate actionable recommendations based on single-platform analysis."""
        recommendations = []
        
        # Recommendation 1: Declining trend
        if coverage_trend['trend'] == 'declining' and coverage_trend['trend_magnitude'] > 5:
            recommendations.append({
                'priority': 'high',
                'title': 'Coverage Declining on This Platform',
                'description': f"Coverage has dropped by {coverage_trend['trend_magnitude']:.1f}% in recent runs",
                'action': 'Review test environment changes, driver versions, or workload configurations that may have changed recently.'
            })
        
        # Recommendation 2: Stagnant coverage
        if coverage_trend['trend'] == 'stable' and coverage_trend['current'] < 70:
            recommendations.append({
                'priority': 'medium',
                'title': 'Coverage Has Plateaued',
                'description': f"Coverage stable at {coverage_trend['current']:.1f}% but below 70% target",
                'action': 'Try different stress test workloads or longer duration tests to activate untested events.'
            })
        
        # Recommendation 3: Declining domains
        declining_domains = [d for d, t in domain_trends.items() if t['trend'] == 'declining']
        if declining_domains:
            recommendations.append({
                'priority': 'medium',
                'title': f'{len(declining_domains)} Domains Showing Decline',
                'description': f"Domains with declining coverage: {', '.join(declining_domains[:3])}",
                'action': 'Review domain-specific validation scripts and ensure stress tests exercise these domains.'
            })
        
        # Recommendation 4: Best workload
        if workload_patterns:
            best_workload = max(workload_patterns.items(), key=lambda x: x[1].get('average_coverage', 0))
            if best_workload[1].get('average_coverage', 0) > 0:
                recommendations.append({
                    'priority': 'info',
                    'title': f"Best Performing Workload: {best_workload[0]}",
                    'description': f"Achieves {best_workload[1]['average_coverage']:.1f}% average coverage",
                    'action': f"Run {best_workload[0]} more frequently to maximize coverage on this platform."
                })
        
        return recommendations
