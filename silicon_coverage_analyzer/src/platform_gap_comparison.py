#!/usr/bin/env python3
"""
Platform Gap Comparison Module

Compares coverage gaps between Windows and Linux platforms to identify
platform-specific issues and recommend the optimal platform for validation.
"""

import json
import logging
import yaml
from pathlib import Path
from typing import Dict, List, Any
from collections import defaultdict

logger = logging.getLogger(__name__)


class PlatformGapComparison:
    """Analyzes and compares gaps across different OS platforms."""
    
    def __init__(self, config):
        self.config = config
        # Use same absolute path as ML trainer
        self.ml_data_dir = Path(r"C:\silicon_coverage_analyzer_data")
        # Load product signatures for domain validation
        self.product_signatures = self._load_product_signatures()
    
    def compare_platforms(self, current_gap_results: Dict, current_os: str, product_id: str = None) -> Dict:
        """
        Compare current platform gaps with other platform data.
        
        Args:
            current_gap_results: Current run's gap results
            current_os: Current operating system (windows/linux)
            product_id: Product identifier to filter comparison (optional)
            
        Returns:
            Dict with platform comparison analysis
        """
        logger.info(f"[PlatformCmp] Comparing gaps across platforms (current: {current_os}, product: {product_id})...")
        
        # Load historical data from both platforms for this product
        platform_data = self._load_platform_data(product_id)
        
        if not platform_data:
            return {
                'status': 'insufficient_data',
                'message': 'Need data from multiple platforms for comparison'
            }
        
        # Extract dataset counts and gaps
        dataset_counts = platform_data.get('dataset_counts', {})
        platform_gaps = platform_data.get('gaps', {})
        
        # Extract current platform gaps
        current_gaps = self._extract_gaps_from_results(current_gap_results, current_os)
        
        # Compare with other platform
        other_os = 'linux' if current_os.lower() == 'windows' else 'windows'
        other_platform_gaps = platform_gaps.get(other_os, {})
        
        if not other_platform_gaps:
            return {
                'status': 'single_platform',
                'message': f'No {other_os} data available for comparison',
                'current_platform': current_os,
                'current_gaps': len(current_gaps)
            }
        
        # Perform comparison
        comparison = self._perform_comparison(current_gaps, other_platform_gaps, current_os, other_os)
        comparison['dataset_counts'] = dataset_counts
        
        # Identify platform-specific events
        platform_specific = self._identify_platform_specific_events(
            current_gaps, other_platform_gaps, current_os, other_os
        )
        
        # Generate recommendations (with statistical validity check)
        recommendations = self._generate_platform_recommendations(
            comparison, platform_specific, current_os, other_os, dataset_counts
        )
        
        logger.info(f"[PlatformCmp] Found {len(platform_specific['current_only'])} {current_os}-only gaps")
        logger.info(f"[PlatformCmp] Found {len(platform_specific['other_only'])} {other_os}-only gaps")
        
        return {
            'status': 'complete',
            'current_platform': current_os,
            'other_platform': other_os,
            'comparison': comparison,
            'platform_specific': platform_specific,
            'recommendations': recommendations,
            'summary': {
                'total_gaps_current': len(current_gaps),
                'total_gaps_other': len(other_platform_gaps),
                'common_gaps': len(comparison['common_gaps']),
                'current_only_gaps': len(platform_specific['current_only']),
                'other_only_gaps': len(platform_specific['other_only']),
                'coverage_advantage': comparison['coverage_advantage']
            }
        }
    
    def _load_platform_data(self, product_id: str = None) -> Dict:
        """Load historical gap data grouped by platform.
        
        Args:
            product_id: Product identifier to filter data (e.g., 'arrowlake_s')
        """
        platform_gaps = {
            'windows': {},
            'linux': {}
        }
        
        # Track dataset counts per platform
        dataset_counts = {
            'windows': 0,
            'linux': 0
        }
        
        # Load historical runs
        datasets_dir = self.ml_data_dir / 'raw_datasets'
        if not datasets_dir.exists():
            datasets_dir = self.ml_data_dir / 'raw_data'
        
        if not datasets_dir.exists():
            return {}
        
        # Find coverage files - filter by product if specified
        if product_id:
            product_dir = datasets_dir / product_id
            if product_dir.exists():
                coverage_files = sorted(product_dir.glob('coverage_*.json'))
                logger.info(f"[PlatformCmp] Loading {len(coverage_files)} files from product '{product_id}'")
            else:
                logger.warning(f"[PlatformCmp] Product directory not found: {product_dir}")
                coverage_files = []
        else:
            # Fallback: load from all product folders (old behavior)
            coverage_files = sorted(datasets_dir.glob('*/coverage_*.json'))
            if not coverage_files:
                coverage_files = sorted(datasets_dir.glob('coverage_*.json'))
        
        for coverage_file in coverage_files:
            try:
                with open(coverage_file, 'r') as f:
                    data = json.load(f)
                
                # Determine platform
                metadata = data.get('metadata', {})
                os_type = metadata.get('os_type', '').lower()
                
                if 'windows' in os_type or 'win' in os_type:
                    platform = 'windows'
                elif 'linux' in os_type:
                    platform = 'linux'
                else:
                    continue  # Skip unknown platforms
                
                # Count this dataset
                dataset_counts[platform] += 1
                
                # Extract gaps with product validation
                gaps = self._extract_gaps_from_coverage_data(data, product_id)
                
                # Merge with existing platform gaps (keep all unique gaps)
                for gap_key, gap_info in gaps.items():
                    if gap_key not in platform_gaps[platform]:
                        platform_gaps[platform][gap_key] = gap_info
                    else:
                        # Update occurrence count
                        platform_gaps[platform][gap_key]['occurrences'] = \
                            platform_gaps[platform][gap_key].get('occurrences', 1) + 1
            
            except Exception as e:
                logger.warning(f"[PlatformCmp] Error loading {coverage_file.name}: {e}")
        
        # Add dataset counts to return data
        logger.info(f"[PlatformCmp] Dataset counts - Windows: {dataset_counts['windows']}, Linux: {dataset_counts['linux']}")
        
        return {
            'gaps': platform_gaps,
            'dataset_counts': dataset_counts
        }
    
    def _extract_gaps_from_results(self, gap_results: Dict, os_type: str) -> Dict:
        """
        Extract gaps from current gap detection results.
        
        Args:
            gap_results: Gap results dictionary with 'gaps' key containing gap data
            os_type: Operating system type
            
        Returns:
            Dict of gaps keyed by domain:event
        """
        gaps = {}
        
        # Get gap data from results - check different possible structures
        gap_data = gap_results.get('gaps', {})
        
        # Structure 1: {'gaps': {'non_toggling_events': [...], 'non_toggling_by_domain': {...}}}
        if 'non_toggling_events' in gap_data:
            # Extract from flat list of non-toggling events
            for gap in gap_data.get('non_toggling_events', []):
                if isinstance(gap, dict):
                    event = gap.get('event', '')
                    domain = gap.get('domain', 'unknown')
                    reason = gap.get('reason', 'unknown')
                    
                    if event and domain:
                        gap_key = f"{domain}:{event}"
                        gaps[gap_key] = {
                            'event': event,
                            'domain': domain,
                            'reason': reason,
                            'os_type': os_type,
                            'occurrences': 1
                        }
        
        # Structure 2: {'gaps': {domain_name: [events...]}}
        elif isinstance(gap_data, dict):
            # Skip meta keys that are not actual domains
            meta_keys = {'non_toggling_events', 'critical_gaps', 'non_toggling_by_domain', 
                        'domain_gaps', 'total_gaps', 'gap_summary', 'anomalies'}
            
            for domain, domain_gaps in gap_data.items():
                # Skip meta keys
                if domain in meta_keys:
                    continue
                    
                if not isinstance(domain_gaps, list):
                    continue
                
                for gap in domain_gaps:
                    if isinstance(gap, dict):
                        event = gap.get('event', '')
                        reason = gap.get('reason', 'unknown')
                        
                        gap_key = f"{domain}:{event}"
                        gaps[gap_key] = {
                            'event': event,
                            'domain': domain,
                            'reason': reason,
                            'os_type': os_type,
                            'occurrences': 1
                        }
        
        return gaps
    
    def _extract_gaps_from_coverage_data(self, data: Dict, product_id: str = None) -> Dict:
        """
        Extract gaps from coverage data file with product domain validation.
        
        Args:
            data: Coverage data dictionary
            product_id: Product identifier for domain validation
            
        Returns:
            Dict of validated gaps
        """
        gaps = {}
        
        coverage = data.get('coverage_results', data.get('coverage', {}))
        domain_results = coverage.get('domain_results', {})
        
        os_type = data.get('metadata', {}).get('os_type', 'unknown')
        
        for domain, domain_data in domain_results.items():
            if not isinstance(domain_data, dict):
                continue
            
            # Validate domain belongs to product
            if product_id and not self._validate_domain_for_product(domain, product_id):
                logger.debug(f"[PlatformCmp] Skipping domain '{domain}' - not valid for product '{product_id}'")
                continue
            
            inactive_events = domain_data.get('inactive_events', [])
            for event_info in inactive_events:
                if isinstance(event_info, dict):
                    event = event_info.get('event', '')
                    reason = event_info.get('reason', 'unknown')
                    
                    if event:
                        gap_key = f"{domain}:{event}"
                        gaps[gap_key] = {
                            'event': event,
                            'domain': domain,
                            'reason': reason,
                            'os_type': os_type,
                            'occurrences': 1
                        }
        
        return gaps
    
    def _perform_comparison(self, current_gaps: Dict, other_gaps: Dict, 
                          current_os: str, other_os: str) -> Dict:
        """Compare gaps between platforms."""
        current_keys = set(current_gaps.keys())
        other_keys = set(other_gaps.keys())
        
        # Find common and unique gaps
        common_keys = current_keys & other_keys
        current_only_keys = current_keys - other_keys
        other_only_keys = other_keys - current_keys
        
        # Calculate coverage advantage
        current_total_events = len(current_keys) + len(other_only_keys)  # Total unique events seen
        other_total_events = len(other_keys) + len(current_only_keys)
        
        current_coverage_pct = ((current_total_events - len(current_keys)) / current_total_events * 100) if current_total_events > 0 else 0
        other_coverage_pct = ((other_total_events - len(other_keys)) / other_total_events * 100) if other_total_events > 0 else 0
        
        if current_coverage_pct > other_coverage_pct:
            coverage_advantage = current_os
            advantage_pct = current_coverage_pct - other_coverage_pct
        elif other_coverage_pct > current_coverage_pct:
            coverage_advantage = other_os
            advantage_pct = other_coverage_pct - current_coverage_pct
        else:
            coverage_advantage = 'equal'
            advantage_pct = 0
        
        return {
            'common_gaps': [current_gaps[k] for k in common_keys],
            'current_only': [current_gaps[k] for k in current_only_keys],
            'other_only': [other_gaps[k] for k in other_only_keys],
            'current_coverage_pct': current_coverage_pct,
            'other_coverage_pct': other_coverage_pct,
            'coverage_advantage': coverage_advantage,
            'advantage_percentage': advantage_pct
        }
    
    def _identify_platform_specific_events(self, current_gaps: Dict, other_gaps: Dict,
                                          current_os: str, other_os: str) -> Dict:
        """Identify events that only gap on one platform."""
        current_keys = set(current_gaps.keys())
        other_keys = set(other_gaps.keys())
        
        current_only = current_keys - other_keys
        other_only = other_keys - current_keys
        
        # Categorize by likely cause
        current_platform_specific = self._categorize_platform_gaps(
            [current_gaps[k] for k in current_only], current_os
        )
        
        other_platform_specific = self._categorize_platform_gaps(
            [other_gaps[k] for k in other_only], other_os
        )
        
        return {
            'current_only': current_platform_specific,
            'other_only': other_platform_specific
        }
    
    def _categorize_platform_gaps(self, gaps: List[Dict], os_type: str) -> List[Dict]:
        """Categorize platform-specific gaps by likely root cause."""
        categorized = []
        
        for gap in gaps:
            event = gap['event'].upper()
            reason = gap['reason']
            
            # Determine likely category
            if 'PEBS' in event and os_type.lower() == 'windows':
                category = 'PEBS_Windows_Limitation'
                explanation = 'PEBS events have limited support on Windows'
            elif 'OFFCORE' in event and os_type.lower() == 'windows':
                category = 'Offcore_Windows_Limitation'
                explanation = 'Offcore events may require specific Windows configuration'
            elif reason == 'privilege_required':
                category = 'Privilege_Issue'
                explanation = f'Collection requires elevated privileges on {os_type}'
            elif reason in ['not_available', 'event_not_exists']:
                category = 'Platform_Unavailable'
                explanation = f'Event not available on {os_type} kernel/drivers'
            elif 'UNC_' in event or 'UNCORE' in event:
                category = 'Uncore_Platform_Specific'
                explanation = f'Uncore event behavior differs on {os_type}'
            else:
                category = 'Unknown_Platform_Specific'
                explanation = f'Gap appears only on {os_type} - investigate'
            
            categorized.append({
                **gap,
                'category': category,
                'explanation': explanation
            })
        
        return categorized
    
    def _generate_platform_recommendations(self, comparison: Dict, 
                                          platform_specific: Dict,
                                          current_os: str, other_os: str,
                                          dataset_counts: Dict) -> List[Dict]:
        """Generate recommendations based on platform comparison."""
        recommendations = []
        
        # Check statistical validity (require balanced sample sizes)
        current_count = dataset_counts.get(current_os.lower(), 0)
        other_count = dataset_counts.get(other_os.lower(), 0)
        
        # Calculate imbalance ratio
        if current_count > 0 and other_count > 0:
            imbalance_ratio = max(current_count, other_count) / min(current_count, other_count)
        else:
            imbalance_ratio = float('inf')
        
        # Recommendation 1: Optimal platform (ONLY if statistically valid)
        if comparison['coverage_advantage'] != 'equal':
            optimal_platform = comparison['coverage_advantage']
            advantage = comparison['advantage_percentage']
            
            # Check if sample sizes are balanced enough (ratio < 3:1)
            if imbalance_ratio < 3.0:
                recommendations.append({
                    'priority': 1,
                    'category': 'Platform_Selection',
                    'title': f'Use {optimal_platform.title()} for Better Coverage',
                    'description': f'{optimal_platform.title()} provides {advantage:.1f}% better coverage (based on {current_count} {current_os} vs {other_count} {other_os} datasets)',
                    'actionable': True,
                    'impact': 'high' if advantage > 10 else 'medium'
                })
            else:
                # Sample size imbalance - recommend balancing instead
                under_tested = current_os if current_count < other_count else other_os
                over_tested = current_os if current_count > other_count else other_os
                recommendations.append({
                    'priority': 1,
                    'category': 'Test_Coverage_Balance',
                    'title': f'Increase {under_tested.title()} Test Coverage',
                    'description': f'Sample size imbalance detected: {dataset_counts[over_tested.lower()]} {over_tested} datasets vs {dataset_counts[under_tested.lower()]} {under_tested}. More testing on {over_tested} reveals more gaps, not better platform. Run more {under_tested} tests for valid comparison.',
                    'actionable': True,
                    'impact': 'high'
                })
        
        # Recommendation 2: PEBS events on Linux
        pebs_gaps_windows = [g for g in platform_specific['current_only'] 
                            if g.get('category') == 'PEBS_Windows_Limitation']
        if pebs_gaps_windows and current_os.lower() == 'windows':
            recommendations.append({
                'priority': 2,
                'category': 'PEBS_Coverage',
                'title': f'Run PEBS Events on Linux',
                'description': f'{len(pebs_gaps_windows)} PEBS events gap on Windows - use Linux for full PEBS coverage',
                'actionable': True,
                'impact': 'high'
            })
        
        # Recommendation 3: Platform-specific optimizations
        if len(platform_specific['current_only']) > 20:
            recommendations.append({
                'priority': 3,
                'category': 'Platform_Optimization',
                'title': f'Investigate {current_os.title()}-Specific Gaps',
                'description': f'{len(platform_specific["current_only"])} events gap only on {current_os} - may indicate configuration issues',
                'actionable': True,
                'impact': 'medium'
            })
        
        # Recommendation 4: Dual-platform validation
        common_gaps = comparison['common_gaps']
        if len(common_gaps) > 10:
            recommendations.append({
                'priority': 4,
                'category': 'Cross_Platform',
                'title': 'Address Common Gaps First',
                'description': f'{len(common_gaps)} gaps occur on both platforms - fix these for maximum impact',
                'actionable': True,
                'impact': 'high'
            })
        
        return recommendations
    
    def generate_platform_comparison_html(self, comparison_results: Dict) -> str:
        """Generate HTML visualization of platform comparison."""
        if comparison_results['status'] == 'insufficient_data':
            return f"""
            <div class="chart-container" style="background: #fff3cd; border-left: 4px solid #ffc107; padding: 20px;">
                <h3 style="color: #856404;">[i] Platform Comparison Unavailable</h3>
                <p style="color: #856404;">
                    {comparison_results['message']}
                </p>
            </div>
"""
        
        if comparison_results['status'] == 'single_platform':
            return f"""
            <div class="chart-container" style="background: #d1ecf1; border-left: 4px solid #17a2b8; padding: 20px;">
                <h3 style="color: #0c5460;">[i] Single Platform Data</h3>
                <p style="color: #0c5460;">
                    {comparison_results['message']}
                </p>
                <p style="color: #0c5460; margin-top: 10px;">
                    Run collections on both Windows and Linux to enable platform comparison.
                </p>
            </div>
"""
        
        current_os = comparison_results['current_platform'].title()
        other_os = comparison_results['other_platform'].title()
        summary = comparison_results['summary']
        comparison = comparison_results['comparison']
        recommendations = comparison_results['recommendations']
        
        # Determine winner
        advantage = comparison['coverage_advantage']
        if advantage == 'equal':
            winner_icon = '[=]'
            winner_text = 'Equal Coverage'
            winner_color = '#17a2b8'
        elif advantage.lower() == current_os.lower():
            winner_icon = ''
            winner_text = f'{current_os} Wins'
            winner_color = '#28a745'
        else:
            winner_icon = ''
            winner_text = f'{other_os} Wins'
            winner_color = '#ffc107'
        
        html = f"""
        <div class="chart-container">
            <h3 style="color: #0071c5; margin-bottom: 10px;"> Platform Gap Comparison</h3>
            <p style="color: #6c757d; margin-bottom: 20px;">
                Comparing {current_os} vs {other_os} gap coverage
            </p>
            
            <!-- Winner Banner -->
            <div style="background: {winner_color}15; border-left: 5px solid {winner_color}; padding: 20px; margin-bottom: 25px; border-radius: 8px; text-align: center;">
                <div style="font-size: 3em; margin-bottom: 10px;">{winner_icon}</div>
                <h3 style="margin: 0; color: {winner_color}; font-size: 1.8em;">
                    {winner_text}
                </h3>
                <p style="margin: 10px 0 0 0; color: #666; font-size: 1.1em;">
                    Coverage: {current_os} {comparison['current_coverage_pct']:.1f}% vs {other_os} {comparison['other_coverage_pct']:.1f}%
                </p>
            </div>
            
            <!-- Platform Comparison Grid -->
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin: 25px 0;">
                <!-- Current Platform -->
                <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; border: 2px solid #0071c5;">
                    <h4 style="margin: 0 0 15px 0; color: #0071c5; text-align: center; font-size: 1.3em;">
                        {current_os}
                    </h4>
                    <div style="display: flex; flex-direction: column; gap: 10px;">
                        <div style="background: #dc3545; color: white; padding: 12px; border-radius: 4px; text-align: center;">
                            <div style="font-size: 2em; font-weight: bold;">{summary['total_gaps_current']}</div>
                            <div style="font-size: 0.9em;">Total Gaps</div>
                        </div>
                        <div style="background: #ffc107; color: #000; padding: 12px; border-radius: 4px; text-align: center;">
                            <div style="font-size: 1.5em; font-weight: bold;">{summary['current_only_gaps']}</div>
                            <div style="font-size: 0.9em;">{current_os}-Only Gaps</div>
                        </div>
                    </div>
                </div>
                
                <!-- Other Platform -->
                <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; border: 2px solid #6c757d;">
                    <h4 style="margin: 0 0 15px 0; color: #6c757d; text-align: center; font-size: 1.3em;">
                        {other_os}
                    </h4>
                    <div style="display: flex; flex-direction: column; gap: 10px;">
                        <div style="background: #dc3545; color: white; padding: 12px; border-radius: 4px; text-align: center;">
                            <div style="font-size: 2em; font-weight: bold;">{summary['total_gaps_other']}</div>
                            <div style="font-size: 0.9em;">Total Gaps</div>
                        </div>
                        <div style="background: #17a2b8; color: white; padding: 12px; border-radius: 4px; text-align: center;">
                            <div style="font-size: 1.5em; font-weight: bold;">{summary['other_only_gaps']}</div>
                            <div style="font-size: 0.9em;">{other_os}-Only Gaps</div>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Common Gaps -->
            <div style="background: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; margin: 20px 0; border-radius: 4px;">
                <h4 style="margin: 0 0 8px 0; color: #856404;">
                     {summary['common_gaps']} Common Gaps (Both Platforms)
                </h4>
                <p style="margin: 0; color: #856404; font-size: 0.95em;">
                    These gaps occur on both {current_os} and {other_os} - likely hardware or workload issues
                </p>
            </div>
"""
        
        # Platform-specific gaps
        platform_specific = comparison_results['platform_specific']
        
        if platform_specific['current_only']:
            html += f"""
            <div style="margin-top: 25px;">
                <h4 style="color: #003e7e;">{current_os}-Specific Gaps ({len(platform_specific['current_only'])} events)</h4>
                <p style="color: #666; font-size: 0.9em;">Events that gap only on {current_os}</p>
                <div style="max-height: 250px; overflow-y: auto;">
                    <table style="width: 100%; border-collapse: collapse; font-size: 0.9em;">
                        <thead style="position: sticky; top: 0; background: #f8f9fa;">
                            <tr>
                                <th style="padding: 8px; text-align: left; border-bottom: 2px solid #dee2e6;">Event</th>
                                <th style="padding: 8px; text-align: left; border-bottom: 2px solid #dee2e6;">Domain</th>
                                <th style="padding: 8px; text-align: left; border-bottom: 2px solid #dee2e6;">Category</th>
                                <th style="padding: 8px; text-align: left; border-bottom: 2px solid #dee2e6;">Explanation</th>
                            </tr>
                        </thead>
                        <tbody>
"""
            for gap in platform_specific['current_only'][:20]:
                html += f"""
                            <tr style="border-bottom: 1px solid #dee2e6;">
                                <td style="padding: 6px 8px; font-family: monospace; font-size: 0.85em;">{gap['event']}</td>
                                <td style="padding: 6px 8px;">{gap['domain'].upper()}</td>
                                <td style="padding: 6px 8px;">
                                    <span style="background: #ffc107; color: #000; padding: 2px 8px; border-radius: 10px; font-size: 0.8em;">
                                        {gap['category'].replace('_', ' ')}
                                    </span>
                                </td>
                                <td style="padding: 6px 8px; color: #666; font-size: 0.85em;">{gap['explanation']}</td>
                            </tr>
"""
            html += """
                        </tbody>
                    </table>
                </div>
            </div>
"""
        
        # Recommendations
        if recommendations:
            html += f"""
            <div style="margin-top: 30px;">
                <h4 style="color: #28a745;">[TIP] Platform Recommendations</h4>
                <div style="display: flex; flex-direction: column; gap: 15px; margin-top: 15px;">
"""
            for rec in recommendations:
                impact_colors = {
                    'high': '#dc3545',
                    'medium': '#ffc107',
                    'low': '#28a745'
                }
                impact_color = impact_colors.get(rec.get('impact', 'medium'), '#17a2b8')
                
                html += f"""
                    <div style="background: #f8f9fa; border-left: 5px solid {impact_color}; padding: 15px; border-radius: 4px;">
                        <div style="display: flex; align-items: start; gap: 15px;">
                            <div style="background: {impact_color}; color: white; width: 35px; height: 35px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-weight: bold; flex-shrink: 0;">
                                {rec['priority']}
                            </div>
                            <div style="flex-grow: 1;">
                                <h5 style="margin: 0 0 6px 0; color: #003e7e;">{rec['title']}</h5>
                                <p style="margin: 0; color: #666; font-size: 0.95em;">{rec['description']}</p>
                                <div style="margin-top: 6px; font-size: 0.85em;">
                                    <span style="background: {impact_color}20; color: {impact_color}; padding: 2px 8px; border-radius: 10px; font-weight: bold;">
                                        {rec.get('impact', 'medium').upper()} IMPACT
                                    </span>
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
    
    def _load_product_signatures(self) -> Dict:
        """
        Load product signatures from YAML config for domain validation.
        
        Returns:
            Dict mapping product_id to {required: [...], forbidden: [...]}
        """
        try:
            config_path = Path(__file__).parent.parent / 'config' / 'product_signatures.yaml'
            if config_path.exists():
                with open(config_path, 'r') as f:
                    config_data = yaml.safe_load(f)
                    signatures = config_data.get('product_signatures', {})
                    logger.info(f"[PlatformCmp] Loaded signatures for {len(signatures)} products")
                    return signatures
            else:
                logger.warning(f"[PlatformCmp] Product signatures config not found: {config_path}")
                return {}
        except Exception as e:
            logger.error(f"[PlatformCmp] Error loading product signatures: {e}")
            return {}
    
    def _validate_domain_for_product(self, domain: str, product_id: str) -> bool:
        """
        Validate if a domain belongs to the specified product.
        
        Args:
            domain: Domain name to validate
            product_id: Product identifier
            
        Returns:
            True if domain is valid for this product, False otherwise
        """
        if not product_id or not self.product_signatures:
            return True  # No validation if signatures not available
        
        signature = self.product_signatures.get(product_id)
        if not signature:
            return True  # No signature for this product - allow all
        
        required = signature.get('required', [])
        forbidden = signature.get('forbidden', [])
        
        # Check if domain is forbidden for this product
        if domain.lower() in [d.lower() for d in forbidden]:
            logger.debug(f"[PlatformCmp] Domain '{domain}' is forbidden for product '{product_id}' - excluding")
            return False
        
        return True
