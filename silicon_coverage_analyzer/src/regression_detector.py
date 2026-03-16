#!/usr/bin/env python3
"""
Regression Detection Module

Detects coverage regressions by comparing current run against previous runs.
Identifies events that stopped toggling and coverage drops.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class RegressionDetector:
    """Detects coverage regressions and event activity changes."""
    
    def __init__(self, config):
        self.config = config
        # Use same absolute path as ML trainer
        self.ml_data_dir = Path(r"C:\silicon_coverage_analyzer_data")
        self.regression_threshold = config.get('regression_threshold', 10.0)  # 10% drop = regression
    
    def detect_regressions(self, current_results: Dict, product_id: str = None) -> Dict:
        """
        Detect regressions by comparing current run against previous run.
        
        Args:
            current_results: Current coverage analysis results
            product_id: Product identifier for product-specific comparison
            
        Returns:
            Dict with regression analysis results
        """
        logger.info("[Regression] Starting regression detection...")
        
        # Load previous run
        previous_results = self._load_previous_run(product_id)
        
        if not previous_results:
            logger.warning("[Regression] No previous run found - skipping regression detection")
            return {
                'status': 'no_baseline',
                'message': 'No previous run available for comparison',
                'regressions_detected': 0
            }
        
        regressions = []
        
        # Compare overall coverage
        overall_regression = self._compare_overall_coverage(current_results, previous_results)
        if overall_regression:
            regressions.append(overall_regression)
        
        # Compare domain-level coverage
        domain_regressions = self._compare_domain_coverage(current_results, previous_results)
        regressions.extend(domain_regressions)
        
        # Compare event-level activity
        event_regressions = self._compare_event_activity(current_results, previous_results)
        regressions.extend(event_regressions)
        
        # Classify severity
        critical_regressions = [r for r in regressions if r['severity'] == 'critical']
        high_regressions = [r for r in regressions if r['severity'] == 'high']
        medium_regressions = [r for r in regressions if r['severity'] == 'medium']
        
        logger.info(f"[Regression] Detected {len(regressions)} total regressions")
        logger.info(f"[Regression]   Critical: {len(critical_regressions)}")
        logger.info(f"[Regression]   High: {len(high_regressions)}")
        logger.info(f"[Regression]   Medium: {len(medium_regressions)}")
        
        return {
            'status': 'complete',
            'regressions_detected': len(regressions),
            'regressions': regressions,
            'critical_count': len(critical_regressions),
            'high_count': len(high_regressions),
            'medium_count': len(medium_regressions),
            'previous_run_timestamp': previous_results.get('timestamp', 'Unknown'),
            'summary': self._generate_regression_summary(regressions, current_results, previous_results)
        }
    
    def _load_previous_run(self, product_id: str = None) -> Optional[Dict]:
        """Load the most recent previous coverage run."""
        try:
            # Look in raw_datasets directory
            if product_id:
                datasets_dir = self.ml_data_dir / 'raw_datasets' / product_id
            else:
                datasets_dir = self.ml_data_dir / 'raw_datasets'
            
            if not datasets_dir.exists():
                # Try old structure
                datasets_dir = self.ml_data_dir / 'raw_data'
            
            if not datasets_dir.exists():
                return None
            
            # Find all coverage files
            if product_id:
                coverage_files = sorted(datasets_dir.glob('coverage_*.json'))
            else:
                # Search in all product subdirectories
                coverage_files = sorted(datasets_dir.glob('*/coverage_*.json'))
                if not coverage_files:
                    coverage_files = sorted(datasets_dir.glob('coverage_*.json'))
            
            if len(coverage_files) < 2:
                # Need at least 2 runs (current + previous)
                return None
            
            # Get second-to-last file (last is current run)
            previous_file = coverage_files[-2]
            
            with open(previous_file, 'r') as f:
                data = json.load(f)
            
            logger.info(f"[Regression] Loaded previous run: {previous_file.name}")
            return data
            
        except Exception as e:
            logger.error(f"[Regression] Error loading previous run: {e}")
            return None
    
    def _compare_overall_coverage(self, current: Dict, previous: Dict) -> Optional[Dict]:
        """Compare overall coverage percentage."""
        current_coverage = current.get('coverage', {})
        previous_coverage = previous.get('coverage_results', previous.get('coverage', {}))
        
        current_pct = current_coverage.get('overall_coverage_percentage', 0)
        previous_pct = previous_coverage.get('overall_coverage_percentage', 0)
        
        drop = previous_pct - current_pct
        
        if drop >= self.regression_threshold:
            severity = 'critical' if drop >= 20 else 'high' if drop >= self.regression_threshold else 'medium'
            
            return {
                'type': 'overall_coverage_drop',
                'severity': severity,
                'message': f'Overall coverage dropped {drop:.1f}% (was {previous_pct:.1f}%, now {current_pct:.1f}%)',
                'previous_value': previous_pct,
                'current_value': current_pct,
                'drop_percentage': drop,
                'recommendation': 'Review recent changes to test workload or system configuration'
            }
        
        return None
    
    def _compare_domain_coverage(self, current: Dict, previous: Dict) -> List[Dict]:
        """Compare domain-level coverage percentages."""
        regressions = []
        
        current_domains = current.get('coverage', {}).get('domain_results', {})
        previous_domains = previous.get('coverage_results', previous.get('coverage', {})).get('domain_results', {})
        
        for domain in current_domains:
            if domain not in previous_domains:
                continue
            
            current_rate = current_domains[domain].get('activity_rate', 0)
            previous_rate = previous_domains[domain].get('activity_rate', 0)
            
            drop = previous_rate - current_rate
            
            if drop >= self.regression_threshold:
                severity = 'high' if drop >= 20 else 'medium'
                
                regressions.append({
                    'type': 'domain_coverage_drop',
                    'domain': domain,
                    'severity': severity,
                    'message': f'{domain.upper()} coverage dropped {drop:.1f}% (was {previous_rate:.1f}%, now {current_rate:.1f}%)',
                    'previous_value': previous_rate,
                    'current_value': current_rate,
                    'drop_percentage': drop,
                    'recommendation': f'Review {domain} domain collection - check for EMON errors or workload changes'
                })
        
        return regressions
    
    def _compare_event_activity(self, current: Dict, previous: Dict) -> List[Dict]:
        """Compare event-level activity - find events that stopped toggling."""
        regressions = []
        
        current_domains = current.get('coverage', {}).get('domain_results', {})
        previous_domains = previous.get('coverage_results', previous.get('coverage', {})).get('domain_results', {})
        
        for domain in current_domains:
            if domain not in previous_domains:
                continue
            
            # Get active events from both runs
            current_active = {e.get('event') for e in current_domains[domain].get('active_events', [])}
            previous_active = {e.get('event') for e in previous_domains[domain].get('active_events', [])}
            
            # Events that stopped toggling
            stopped_events = previous_active - current_active
            
            if stopped_events:
                severity = 'critical' if len(stopped_events) > 10 else 'high' if len(stopped_events) > 3 else 'medium'
                
                regressions.append({
                    'type': 'events_stopped_toggling',
                    'domain': domain,
                    'severity': severity,
                    'message': f'{len(stopped_events)} event(s) stopped toggling in {domain.upper()} domain',
                    'events': list(stopped_events)[:10],  # First 10 events
                    'total_events_affected': len(stopped_events),
                    'recommendation': f'Investigate why these events no longer toggle - check workload changes or EMON collection'
                })
        
        return regressions
    
    def _generate_regression_summary(self, regressions: List[Dict], current: Dict, previous: Dict) -> Dict:
        """Generate summary of regression analysis."""
        # Count events affected
        total_events_stopped = sum(
            r.get('total_events_affected', 0) 
            for r in regressions 
            if r['type'] == 'events_stopped_toggling'
        )
        
        # Count domains affected
        affected_domains = set(
            r['domain'] 
            for r in regressions 
            if 'domain' in r
        )
        
        # Overall coverage change
        current_pct = current.get('coverage', {}).get('overall_coverage_percentage', 0)
        previous_pct = previous.get('coverage_results', previous.get('coverage', {})).get('overall_coverage_percentage', 0)
        coverage_change = current_pct - previous_pct
        
        return {
            'total_regressions': len(regressions),
            'events_stopped_toggling': total_events_stopped,
            'domains_affected': len(affected_domains),
            'overall_coverage_change': coverage_change,
            'trend': 'declining' if coverage_change < 0 else 'improving' if coverage_change > 0 else 'stable'
        }
    
    def generate_regression_report_html(self, regression_results: Dict) -> str:
        """Generate HTML report section for regressions."""
        if regression_results['status'] == 'no_baseline':
            return f"""
            <div class="chart-container" style="background: #fff3cd; border-left: 4px solid #ffc107;">
                <h3 style="color: #856404;">[i] Regression Detection Unavailable</h3>
                <p style="color: #856404;">
                    {regression_results['message']}
                </p>
                <p style="color: #856404; font-size: 0.9em; margin-top: 10px;">
                    Run analyze_coverage.py at least twice to enable regression detection.
                </p>
            </div>
"""
        
        regressions = regression_results.get('regressions', [])
        summary = regression_results.get('summary', {})
        
        if not regressions:
            return f"""
            <div class="chart-container" style="background: #d4edda; border-left: 4px solid #28a745;">
                <h3 style="color: #155724;">[OK] No Regressions Detected</h3>
                <p style="color: #155724;">
                    Coverage is stable or improving compared to previous run 
                    (Trend: <strong>{summary.get('trend', 'unknown').upper()}</strong>, 
                    Change: {summary.get('overall_coverage_change', 0):+.1f}%)
                </p>
                <p style="color: #6c757d; font-size: 0.9em; margin-top: 10px;">
                    Previous run: {regression_results.get('previous_run_timestamp', 'Unknown')}
                </p>
            </div>
"""
        
        # Has regressions
        critical_count = regression_results.get('critical_count', 0)
        high_count = regression_results.get('high_count', 0)
        
        html = f"""
        <div class="chart-container" style="background: #f8d7da; border-left: 4px solid #dc3545;">
            <h3 style="color: #721c24;">[WARN] Regressions Detected: {len(regressions)} Issue(s)</h3>
            <p style="color: #721c24; margin-bottom: 15px;">
                Coverage declined compared to previous run ({regression_results.get('previous_run_timestamp', 'Unknown')})
            </p>
            
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px; margin: 15px 0;">
                <div style="background: #fff; padding: 15px; border-left: 3px solid #dc3545; border-radius: 4px; text-align: center;">
                    <div style="font-size: 2em; font-weight: bold; color: #dc3545;">{critical_count}</div>
                    <div style="color: #666; font-size: 0.9em;">Critical</div>
                </div>
                <div style="background: #fff; padding: 15px; border-left: 3px solid #ffc107; border-radius: 4px; text-align: center;">
                    <div style="font-size: 2em; font-weight: bold; color: #ffc107;">{high_count}</div>
                    <div style="color: #666; font-size: 0.9em;">High</div>
                </div>
                <div style="background: #fff; padding: 15px; border-left: 3px solid #6c757d; border-radius: 4px; text-align: center;">
                    <div style="font-size: 2em; font-weight: bold; color: #6c757d;">{summary.get('events_stopped_toggling', 0)}</div>
                    <div style="color: #666; font-size: 0.9em;">Events Stopped</div>
                </div>
                <div style="background: #fff; padding: 15px; border-left: 3px solid #17a2b8; border-radius: 4px; text-align: center;">
                    <div style="font-size: 2em; font-weight: bold; color: #17a2b8;">{summary.get('domains_affected', 0)}</div>
                    <div style="color: #666; font-size: 0.9em;">Domains Affected</div>
                </div>
            </div>
            
            <h4 style="color: #721c24; margin-top: 25px;">Regression Details:</h4>
"""
        
        for regression in regressions:
            severity = regression['severity']
            reg_type = regression['type']
            
            color_map = {
                'critical': '#dc3545',
                'high': '#ffc107',
                'medium': '#17a2b8'
            }
            color = color_map.get(severity, '#6c757d')
            
            html += f"""
            <div style="background: #fff; padding: 15px; margin: 10px 0; border-left: 4px solid {color}; border-radius: 4px;">
                <div style="display: flex; justify-content: space-between; align-items: start;">
                    <div style="flex: 1;">
                        <h5 style="margin: 0 0 5px 0; color: #333;">
                            {regression['message']}
                        </h5>
                        <p style="color: #666; margin: 5px 0; font-size: 0.9em;">
                            <strong>Recommendation:</strong> {regression.get('recommendation', 'Investigate cause of regression')}
                        </p>
"""
            
            # Add event details for stopped events
            if reg_type == 'events_stopped_toggling':
                events = regression.get('events', [])
                total = regression.get('total_events_affected', 0)
                
                html += f"""
                        <details style="margin-top: 10px;">
                            <summary style="cursor: pointer; color: #0071c5; font-size: 0.9em;">
                                Show affected events ({total} total)
                            </summary>
                            <ul style="margin: 10px 0; padding-left: 20px; font-family: monospace; font-size: 0.85em;">
"""
                for event in events:
                    html += f"                                <li>{event}</li>\n"
                
                if total > len(events):
                    html += f"                                <li><em>...and {total - len(events)} more</em></li>\n"
                
                html += """
                            </ul>
                        </details>
"""
            
            html += f"""
                    </div>
                    <span style="background: {color}; color: white; padding: 5px 12px; border-radius: 12px; font-size: 0.85em; font-weight: bold; white-space: nowrap; margin-left: 15px;">
                        {severity.upper()}
                    </span>
                </div>
            </div>
"""
        
        html += """
        </div>
"""
        
        return html
