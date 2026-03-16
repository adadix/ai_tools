#!/usr/bin/env python3
"""
Temporal Trend Analyzer Module

Analyzes coverage trends over time to track improvement/regression,
identify flaky events, and visualize progress toward validation goals.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Tuple
from collections import defaultdict
from datetime import datetime

logger = logging.getLogger(__name__)


class TemporalTrendAnalyzer:
    """Analyzes coverage trends across multiple historical runs."""
    
    def __init__(self, config):
        self.config = config
        # Use same absolute path as ML trainer
        self.ml_data_dir = Path(r"C:\silicon_coverage_analyzer_data")
        self.flaky_threshold = config.get('flaky_threshold', 0.5)  # <50% reliability = flaky
    
    def analyze_trends(self, product_id: str = None, lookback_runs: int = 10) -> Dict:
        """
        Analyze coverage trends over time.
        
        Args:
            product_id: Product identifier for product-specific analysis
            lookback_runs: Number of historical runs to analyze
            
        Returns:
            Dict with trend analysis results
        """
        logger.info(f"[Trends] Analyzing coverage trends (last {lookback_runs} runs)...")
        
        # Load historical runs
        historical_data = self._load_historical_runs(product_id, lookback_runs)
        
        if len(historical_data) < 2:
            return {
                'status': 'insufficient_data',
                'message': f'Need at least 2 runs for trend analysis (found {len(historical_data)})',
                'runs_available': len(historical_data)
            }
        
        logger.info(f"[Trends] Loaded {len(historical_data)} historical runs")
        
        # Analyze overall coverage trend
        overall_trend = self._analyze_overall_trend(historical_data)
        
        # Analyze domain-level trends
        domain_trends = self._analyze_domain_trends(historical_data)
        
        # Analyze event-level trends (flaky events, regressions, improvements)
        event_trends = self._analyze_event_trends(historical_data)
        
        # Identify improving/declining events
        improving_events = [e for e in event_trends if e['pattern'] == 'improving']
        declining_events = [e for e in event_trends if e['pattern'] == 'declining']
        flaky_events = [e for e in event_trends if e['pattern'] == 'flaky']
        stable_events = [e for e in event_trends if e['pattern'] == 'stable']
        
        logger.info(f"[Trends] Found {len(improving_events)} improving events")
        logger.info(f"[Trends] Found {len(declining_events)} declining events")
        logger.info(f"[Trends] Found {len(flaky_events)} flaky events")
        
        return {
            'status': 'complete',
            'runs_analyzed': len(historical_data),
            'date_range': {
                'first': historical_data[0].get('timestamp', 'Unknown'),
                'last': historical_data[-1].get('timestamp', 'Unknown')
            },
            'overall_trend': overall_trend,
            'domain_trends': domain_trends,
            'event_trends': {
                'improving': improving_events,
                'declining': declining_events,
                'flaky': flaky_events,
                'stable': stable_events[:20]  # Top 20 stable
            },
            'summary': {
                'total_events_tracked': len(event_trends),
                'improving_count': len(improving_events),
                'declining_count': len(declining_events),
                'flaky_count': len(flaky_events),
                'stable_count': len(stable_events)
            }
        }
    
    def _load_historical_runs(self, product_id: str = None, max_runs: int = 10) -> List[Dict]:
        """Load historical coverage runs sorted by timestamp."""
        datasets = []
        
        # Look in raw_datasets directory
        if product_id:
            datasets_dir = self.ml_data_dir / 'raw_datasets' / product_id
        else:
            datasets_dir = self.ml_data_dir / 'raw_datasets'
        
        if not datasets_dir.exists():
            datasets_dir = self.ml_data_dir / 'raw_data'
        
        if not datasets_dir.exists():
            return []
        
        # Find coverage files
        if product_id:
            coverage_files = sorted(datasets_dir.glob('coverage_*.json'))
        else:
            coverage_files = sorted(datasets_dir.glob('*/coverage_*.json'))
            if not coverage_files:
                coverage_files = sorted(datasets_dir.glob('coverage_*.json'))
        
        # Load most recent runs
        for coverage_file in coverage_files[-max_runs:]:
            try:
                with open(coverage_file, 'r') as f:
                    data = json.load(f)
                    datasets.append(data)
            except Exception as e:
                logger.warning(f"[Trends] Error loading {coverage_file.name}: {e}")
        
        # Sort by timestamp
        datasets.sort(key=lambda x: x.get('timestamp', ''))
        
        return datasets
    
    def _analyze_overall_trend(self, historical_data: List[Dict]) -> Dict:
        """Analyze overall coverage percentage trend."""
        coverage_timeline = []
        
        for data in historical_data:
            timestamp = data.get('timestamp', '')
            coverage = data.get('coverage_results', data.get('coverage', {}))
            overall_pct = coverage.get('overall_coverage_percentage', 0)
            
            coverage_timeline.append({
                'timestamp': timestamp,
                'coverage': overall_pct
            })
        
        # Calculate trend
        if len(coverage_timeline) < 2:
            trend_direction = 'unknown'
            change = 0
        else:
            first_coverage = coverage_timeline[0]['coverage']
            last_coverage = coverage_timeline[-1]['coverage']
            change = last_coverage - first_coverage
            
            if change > 5:
                trend_direction = 'improving'
            elif change < -5:
                trend_direction = 'declining'
            else:
                trend_direction = 'stable'
        
        # Calculate statistics
        coverages = [c['coverage'] for c in coverage_timeline]
        avg_coverage = sum(coverages) / len(coverages) if coverages else 0
        min_coverage = min(coverages) if coverages else 0
        max_coverage = max(coverages) if coverages else 0
        
        return {
            'trend_direction': trend_direction,
            'coverage_change': change,
            'first_run_coverage': coverage_timeline[0]['coverage'] if coverage_timeline else 0,
            'last_run_coverage': coverage_timeline[-1]['coverage'] if coverage_timeline else 0,
            'average_coverage': avg_coverage,
            'min_coverage': min_coverage,
            'max_coverage': max_coverage,
            'timeline': coverage_timeline
        }
    
    def _analyze_domain_trends(self, historical_data: List[Dict]) -> Dict:
        """Analyze per-domain coverage trends."""
        domain_timelines = defaultdict(list)
        
        for data in historical_data:
            timestamp = data.get('timestamp', '')
            coverage = data.get('coverage_results', data.get('coverage', {}))
            domain_results = coverage.get('domain_results', {})
            
            for domain, domain_data in domain_results.items():
                if not isinstance(domain_data, dict):
                    continue
                
                activity_rate = domain_data.get('activity_rate', 0)
                domain_timelines[domain].append({
                    'timestamp': timestamp,
                    'coverage': activity_rate
                })
        
        # Analyze each domain
        domain_trends = {}
        for domain, timeline in domain_timelines.items():
            if len(timeline) < 2:
                continue
            
            first_cov = timeline[0]['coverage']
            last_cov = timeline[-1]['coverage']
            change = last_cov - first_cov
            
            if change > 10:
                direction = 'improving'
            elif change < -10:
                direction = 'declining'
            else:
                direction = 'stable'
            
            domain_trends[domain] = {
                'trend_direction': direction,
                'coverage_change': change,
                'first_coverage': first_cov,
                'last_coverage': last_cov,
                'timeline': timeline
            }
        
        return domain_trends
    
    def _analyze_event_trends(self, historical_data: List[Dict]) -> List[Dict]:
        """Analyze individual event trends - identify flaky, improving, declining events."""
        event_activity_history = defaultdict(list)
        
        # Build activity history for each event
        for run_idx, data in enumerate(historical_data):
            timestamp = data.get('timestamp', '')
            coverage = data.get('coverage_results', data.get('coverage', {}))
            domain_results = coverage.get('domain_results', {})
            
            # Track all events seen in this run
            events_this_run = set()
            
            for domain, domain_data in domain_results.items():
                if not isinstance(domain_data, dict):
                    continue
                
                # Get active events
                active_events = domain_data.get('active_events', [])
                for event_info in active_events:
                    if isinstance(event_info, dict):
                        event_name = event_info.get('event', '')
                        if event_name:
                            events_this_run.add((event_name, domain))
                            event_activity_history[(event_name, domain)].append({
                                'run_index': run_idx,
                                'timestamp': timestamp,
                                'active': True
                            })
                
                # Track inactive events as well
                inactive_events = domain_data.get('inactive_events', [])
                for event_info in inactive_events:
                    if isinstance(event_info, dict):
                        event_name = event_info.get('event', '')
                        if event_name:
                            event_activity_history[(event_name, domain)].append({
                                'run_index': run_idx,
                                'timestamp': timestamp,
                                'active': False
                            })
        
        # Analyze patterns for each event
        event_trends = []
        
        for (event_name, domain), history in event_activity_history.items():
            if len(history) < 2:
                continue
            
            # Calculate reliability (% of runs where active)
            active_count = sum(1 for h in history if h['active'])
            total_runs = len(history)
            reliability = active_count / total_runs if total_runs > 0 else 0
            
            # Detect pattern
            pattern, details = self._classify_event_pattern(history, reliability)
            
            if pattern != 'stable':  # Only include non-stable events
                event_trends.append({
                    'event': event_name,
                    'domain': domain,
                    'pattern': pattern,
                    'reliability': reliability,
                    'active_runs': active_count,
                    'total_runs': total_runs,
                    'details': details,
                    'first_seen': history[0]['timestamp'],
                    'last_seen': history[-1]['timestamp']
                })
        
        return event_trends
    
    def _classify_event_pattern(self, history: List[Dict], reliability: float) -> Tuple[str, str]:
        """
        Classify event activity pattern.
        
        Returns:
            (pattern, details) where pattern is: improving, declining, flaky, stable
        """
        activity_sequence = [h['active'] for h in history]
        
        # Flaky: reliability between 20-80%
        if 0.2 < reliability < 0.8:
            return 'flaky', f'Toggles inconsistently ({reliability*100:.0f}% reliability)'
        
        # Regression: was active, then stopped
        if len(activity_sequence) >= 3:
            recent = activity_sequence[-3:]
            early = activity_sequence[:3]
            
            if all(early) and not any(recent):
                last_active_idx = next((i for i, active in reversed(list(enumerate(activity_sequence))) if active), -1)
                return 'declining', f'Stopped toggling after run #{last_active_idx + 1}'
        
        # Improvement: wasn't active, then started
        if len(activity_sequence) >= 3:
            recent = activity_sequence[-3:]
            early = activity_sequence[:3]
            
            if not any(early) and all(recent):
                first_active_idx = next((i for i, active in enumerate(activity_sequence) if active), -1)
                return 'improving', f'Started toggling in run #{first_active_idx + 1}'
        
        # Stable
        return 'stable', f'Consistent activity ({reliability*100:.0f}% reliability)'
    
    def generate_trend_report_html(self, trend_results: Dict) -> str:
        """Generate HTML visualization of temporal trends."""
        if trend_results['status'] == 'insufficient_data':
            return f"""
            <div class="chart-container" style="background: #fff3cd; border-left: 4px solid #ffc107;">
                <h3 style="color: #856404;">[i] Temporal Trend Analysis Unavailable</h3>
                <p style="color: #856404;">
                    {trend_results['message']}
                </p>
                <p style="color: #856404; font-size: 0.9em; margin-top: 10px;">
                    Run analyze_coverage.py multiple times to build historical trend data.
                </p>
            </div>
"""
        
        overall = trend_results['overall_trend']
        summary = trend_results['summary']
        event_trends = trend_results['event_trends']
        
        # Determine trend color
        trend_colors = {
            'improving': '#28a745',
            'declining': '#dc3545',
            'stable': '#17a2b8',
            'unknown': '#6c757d'
        }
        trend_color = trend_colors.get(overall['trend_direction'], '#6c757d')
        
        html = f"""
        <div class="chart-container">
            <h3 style="color: #0071c5; margin-bottom: 10px;"> Coverage Trends Over Time</h3>
            <p style="color: #6c757d; margin-bottom: 20px;">
                Analysis of {trend_results['runs_analyzed']} historical runs 
                ({trend_results['date_range']['first'][:10]} to {trend_results['date_range']['last'][:10]})
            </p>
            
            <!-- Overall Trend Banner -->
            <div style="background: {trend_color}15; border-left: 5px solid {trend_color}; padding: 20px; margin-bottom: 25px; border-radius: 8px;">
                <div style="display: flex; align-items: center; gap: 15px;">
                    <span style="font-size: 3em;">
                        {'' if overall['trend_direction'] == 'improving' else '[v]' if overall['trend_direction'] == 'declining' else '->'}
                    </span>
                    <div>
                        <h3 style="margin: 0; color: {trend_color}; font-size: 1.5em; text-transform: uppercase;">
                            {overall['trend_direction']} Trend
                        </h3>
                        <p style="margin: 5px 0 0 0; color: #666; font-size: 1.1em;">
                            Coverage changed <strong>{overall['coverage_change']:+.1f}%</strong> 
                            (from {overall['first_run_coverage']:.1f}% to {overall['last_run_coverage']:.1f}%)
                        </p>
                    </div>
                </div>
            </div>
            
            <!-- Summary Metrics -->
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin: 20px 0;">
                <div style="background: #d4edda; padding: 15px; border-left: 4px solid #28a745; border-radius: 4px; text-align: center;">
                    <div style="font-size: 2em; font-weight: bold; color: #28a745;">{summary['improving_count']}</div>
                    <div style="color: #155724; font-size: 0.9em; margin-top: 5px;">Events Improving</div>
                </div>
                <div style="background: #f8d7da; padding: 15px; border-left: 4px solid #dc3545; border-radius: 4px; text-align: center;">
                    <div style="font-size: 2em; font-weight: bold; color: #dc3545;">{summary['declining_count']}</div>
                    <div style="color: #721c24; font-size: 0.9em; margin-top: 5px;">Events Declining</div>
                </div>
                <div style="background: #fff3cd; padding: 15px; border-left: 4px solid #ffc107; border-radius: 4px; text-align: center;">
                    <div style="font-size: 2em; font-weight: bold; color: #ffc107;">{summary['flaky_count']}</div>
                    <div style="color: #856404; font-size: 0.9em; margin-top: 5px;">Flaky Events</div>
                </div>
                <div style="background: #d1ecf1; padding: 15px; border-left: 4px solid #17a2b8; border-radius: 4px; text-align: center;">
                    <div style="font-size: 2em; font-weight: bold; color: #17a2b8;">{summary['stable_count']}</div>
                    <div style="color: #0c5460; font-size: 0.9em; margin-top: 5px;">Stable Events</div>
                </div>
            </div>
            
            <!-- Coverage Timeline Chart -->
            <div style="margin: 30px 0;">
                <h4 style="color: #003e7e;">Overall Coverage Timeline</h4>
                <canvas id="coverageTrendChart" style="max-height: 250px;"></canvas>
            </div>
"""
        
        # Add event details sections
        if event_trends['improving']:
            html += f"""
            <div style="margin-top: 30px;">
                <h4 style="color: #28a745;">[OK] Improving Events ({len(event_trends['improving'])} total)</h4>
                <p style="color: #666; font-size: 0.9em;">Events that started toggling in recent runs</p>
                <div style="max-height: 200px; overflow-y: auto;">
                    <table style="width: 100%; border-collapse: collapse; font-size: 0.9em;">
                        <thead style="position: sticky; top: 0; background: #f8f9fa;">
                            <tr>
                                <th style="padding: 8px; text-align: left; border-bottom: 2px solid #dee2e6;">Event</th>
                                <th style="padding: 8px; text-align: left; border-bottom: 2px solid #dee2e6;">Domain</th>
                                <th style="padding: 8px; text-align: center; border-bottom: 2px solid #dee2e6;">Reliability</th>
                                <th style="padding: 8px; text-align: left; border-bottom: 2px solid #dee2e6;">Details</th>
                            </tr>
                        </thead>
                        <tbody>
"""
            for event in event_trends['improving'][:20]:
                html += f"""
                            <tr style="border-bottom: 1px solid #dee2e6;">
                                <td style="padding: 6px 8px; font-family: monospace; font-size: 0.85em;">{event['event']}</td>
                                <td style="padding: 6px 8px;">{event['domain'].upper()}</td>
                                <td style="padding: 6px 8px; text-align: center;">
                                    <span style="background: #28a745; color: white; padding: 2px 8px; border-radius: 10px; font-size: 0.8em;">
                                        {event['reliability']*100:.0f}%
                                    </span>
                                </td>
                                <td style="padding: 6px 8px; color: #666; font-size: 0.85em;">{event['details']}</td>
                            </tr>
"""
            html += """
                        </tbody>
                    </table>
                </div>
            </div>
"""
        
        if event_trends['declining']:
            html += f"""
            <div style="margin-top: 30px;">
                <h4 style="color: #dc3545;">[WARN] Declining Events ({len(event_trends['declining'])} total)</h4>
                <p style="color: #666; font-size: 0.9em;">Events that stopped toggling in recent runs - investigate regressions</p>
                <div style="max-height: 200px; overflow-y: auto;">
                    <table style="width: 100%; border-collapse: collapse; font-size: 0.9em;">
                        <thead style="position: sticky; top: 0; background: #f8f9fa;">
                            <tr>
                                <th style="padding: 8px; text-align: left; border-bottom: 2px solid #dee2e6;">Event</th>
                                <th style="padding: 8px; text-align: left; border-bottom: 2px solid #dee2e6;">Domain</th>
                                <th style="padding: 8px; text-align: center; border-bottom: 2px solid #dee2e6;">Reliability</th>
                                <th style="padding: 8px; text-align: left; border-bottom: 2px solid #dee2e6;">Details</th>
                            </tr>
                        </thead>
                        <tbody>
"""
            for event in event_trends['declining'][:20]:
                html += f"""
                            <tr style="border-bottom: 1px solid #dee2e6;">
                                <td style="padding: 6px 8px; font-family: monospace; font-size: 0.85em;">{event['event']}</td>
                                <td style="padding: 6px 8px;">{event['domain'].upper()}</td>
                                <td style="padding: 6px 8px; text-align: center;">
                                    <span style="background: #dc3545; color: white; padding: 2px 8px; border-radius: 10px; font-size: 0.8em;">
                                        {event['reliability']*100:.0f}%
                                    </span>
                                </td>
                                <td style="padding: 6px 8px; color: #666; font-size: 0.85em;">{event['details']}</td>
                            </tr>
"""
            html += """
                        </tbody>
                    </table>
                </div>
            </div>
"""
        
        if event_trends['flaky']:
            html += f"""
            <div style="margin-top: 30px;">
                <h4 style="color: #ffc107;">[*] Flaky Events ({len(event_trends['flaky'])} total)</h4>
                <p style="color: #666; font-size: 0.9em;">Events with inconsistent activity - unreliable for validation</p>
                <div style="max-height: 200px; overflow-y: auto;">
                    <table style="width: 100%; border-collapse: collapse; font-size: 0.9em;">
                        <thead style="position: sticky; top: 0; background: #f8f9fa;">
                            <tr>
                                <th style="padding: 8px; text-align: left; border-bottom: 2px solid #dee2e6;">Event</th>
                                <th style="padding: 8px; text-align: left; border-bottom: 2px solid #dee2e6;">Domain</th>
                                <th style="padding: 8px; text-align: center; border-bottom: 2px solid #dee2e6;">Reliability</th>
                                <th style="padding: 8px; text-align: left; border-bottom: 2px solid #dee2e6;">Active/Total Runs</th>
                            </tr>
                        </thead>
                        <tbody>
"""
            for event in event_trends['flaky'][:20]:
                html += f"""
                            <tr style="border-bottom: 1px solid #dee2e6;">
                                <td style="padding: 6px 8px; font-family: monospace; font-size: 0.85em;">{event['event']}</td>
                                <td style="padding: 6px 8px;">{event['domain'].upper()}</td>
                                <td style="padding: 6px 8px; text-align: center;">
                                    <span style="background: #ffc107; color: #000; padding: 2px 8px; border-radius: 10px; font-size: 0.8em;">
                                        {event['reliability']*100:.0f}%
                                    </span>
                                </td>
                                <td style="padding: 6px 8px; color: #666; font-size: 0.85em;">
                                    {event['active_runs']}/{event['total_runs']} runs
                                </td>
                            </tr>
"""
            html += """
                        </tbody>
                    </table>
                </div>
            </div>
"""
        
        # Add Chart.js script
        timeline = overall['timeline']
        timestamps = [t['timestamp'][:10] for t in timeline]  # Date only
        coverages = [t['coverage'] for t in timeline]
        
        html += f"""
            <script>
            new Chart(document.getElementById('coverageTrendChart'), {{
                type: 'line',
                data: {{
                    labels: {json.dumps(timestamps)},
                    datasets: [{{
                        label: 'Overall Coverage %',
                        data: {json.dumps(coverages)},
                        borderColor: '{trend_color}',
                        backgroundColor: '{trend_color}30',
                        borderWidth: 3,
                        fill: true,
                        tension: 0.4,
                        pointRadius: 5,
                        pointHoverRadius: 7
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {{
                        legend: {{ display: true }},
                        title: {{
                            display: true,
                            text: 'Coverage Progress Over Time'
                        }}
                    }},
                    scales: {{
                        y: {{
                            beginAtZero: false,
                            min: Math.max(0, Math.min(...{json.dumps(coverages)}) - 10),
                            max: Math.min(100, Math.max(...{json.dumps(coverages)}) + 10),
                            title: {{ display: true, text: 'Coverage %' }}
                        }},
                        x: {{
                            title: {{ display: true, text: 'Collection Date' }}
                        }}
                    }}
                }}
            }});
            </script>
        </div>
"""
        
        return html
