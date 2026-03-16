"""
Action Items Tab Generator Module

Generates the Action Items tab for the HTML report.
Contains coverage gaps, EMON commands, correlations, and root causes.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List

from src.config_utils import load_domain_config

logger = logging.getLogger(__name__)

# Load domain config (avoids circular import)
_DOMAIN_CONFIG = load_domain_config()


class ActionItemsTabGenerator:
    """Generates the Action Items tab content."""
    
    def __init__(self, report_generator):
        """
        Initialize with reference to parent ReportGenerator.
        
        Args:
            report_generator: Parent ReportGenerator instance for accessing
                             shared methods and ML models.
        """
        self.rg = report_generator
    
    def generate(self, analysis_results: Dict[str, Any]) -> str:
        """
        Generate Action Items tab HTML.
        
        Args:
            analysis_results: Full analysis results
            
        Returns:
            HTML string for the action items tab
        """
        coverage = analysis_results.get('coverage', {})
        gaps_analysis = analysis_results.get('gaps', {})
        gap_correlation = analysis_results.get('gap_correlation', {})
        workload_gap_mapping = analysis_results.get('workload_gap_mapping', {})
        root_cause_analysis = analysis_results.get('root_cause_analysis', {})
        emon_commands = analysis_results.get('emon_commands', {})
        platform_comparison = analysis_results.get('platform_comparison', {})
        
        # Process gap events
        non_toggling_events = gaps_analysis.get('non_toggling_events', [])
        gap_events, unique_domains, unavailable_count, actionable_gaps = self._process_gap_events(
            non_toggling_events, analysis_results
        )
        
        # Generate domain filter options
        domain_options = self._generate_domain_options(unique_domains)
        
        # Build HTML
        html = self._generate_header(gap_events, actionable_gaps, unavailable_count, domain_options)
        
        # Gap correlation clusters
        if gap_correlation and gap_correlation.get('clusters'):
            html += self._generate_correlation_clusters(gap_correlation)
        
        # Gaps table
        if gap_events:
            html += self._generate_gaps_table(gap_events, analysis_results)
        
        # Platform-specific gaps
        if platform_comparison and platform_comparison.get('platform_specific_gaps'):
            html += self._generate_platform_gaps(platform_comparison)
        
        # EMON commands
        if emon_commands and emon_commands.get('commands'):
            html += self._generate_emon_commands(emon_commands)
        
        # Anomaly analysis
        ml_analysis = analysis_results.get('ml_analysis', {})
        anomalies = ml_analysis.get('anomalies', {})
        if anomalies.get('statistics', {}).get('total_anomalies', 0) > 0:
            html += self._generate_anomaly_section(anomalies)
        
        # Persistent gaps
        html += self._generate_persistent_gaps(analysis_results)
        
        # ML recommendations
        recommendations = ml_analysis.get('recommendations', [])
        if recommendations:
            html += self._generate_ml_recommendations(recommendations)
        
        # Gap correlation analysis
        html += self._generate_gap_correlation_section(analysis_results, gaps_analysis)
        
        # Instruction mix breakdown
        html += self._generate_instruction_mix_section(coverage, analysis_results)
        
        # Validation checklist
        html += self._generate_validation_checklist(analysis_results)
        
        html += """
        </div>
        """
        
        return html
    
    def _process_gap_events(self, non_toggling_events: List, analysis_results: Dict) -> tuple:
        """Process non-toggling events into gap events list."""
        gap_events = []
        unique_domains = set()
        unavailable_count = 0
        actionable_gaps = 0
        
        correlation_matrix = analysis_results.get('gap_correlation', {}).get('correlation_matrix', {})
        
        for event_info in non_toggling_events:
            reason = event_info.get('reason', '')
            category = event_info.get('category', '')
            
            if category == 'Event_Unavailable' or reason in ['event_not_exists', 'not_found', 'not_supported']:
                unavailable_count += 1
            else:
                actionable_gaps += 1
            
            domain = event_info.get('domain', 'Unknown')
            unique_domains.add(domain)
            event_name = event_info.get('event_name', event_info.get('event', 'Unknown'))
            
            # Count co-occurrences
            cooccur_count = 0
            if correlation_matrix and event_name in correlation_matrix:
                cooccur_count = sum(1 for corr in correlation_matrix[event_name].values() if corr > 0.7)
            
            # ML-based priority
            priority, confidence = self.rg.ml_gap_prioritizer.classify_gap_priority(
                event_name, domain, cooccur_count
            )
            
            gap_events.append({
                'event_name': event_name,
                'domain': domain,
                'reason': event_info.get('reason', 'never_active'),
                'priority': priority,
                'priority_confidence': confidence,
                'ml_classified': self.rg.ml_gap_prioritizer.model is not None,
                'root_cause': event_info.get('reason', 'Unknown')
            })
        
        return gap_events, unique_domains, unavailable_count, actionable_gaps
    
    def _generate_domain_options(self, unique_domains: set) -> str:
        """Generate domain filter options HTML."""
        options = '<option value="all">All Domains</option>\n'
        for domain in sorted(unique_domains):
            domain_display = domain.upper().replace('_', ' ')
            options += f'                            <option value="{domain}">{domain_display}</option>\n'
        return options
    
    def _generate_header(self, gap_events: List, actionable_gaps: int, 
                        unavailable_count: int, domain_options: str) -> str:
        """Generate header section with interpretation guide and stats."""
        ml_info = self.rg.ml_gap_prioritizer.get_model_info()
        
        ml_indicator = ""
        if ml_info['status'] == 'trained':
            weight = int(ml_info.get('feature_importance', {}).get('event_patterns', 0.5) * 100)
            ml_indicator = f"""
            <div style="background: #d4edda; border-left: 4px solid #28a745; padding: 15px; margin-bottom: 20px; border-radius: 5px;">
                <strong style="color: #28a745;">ML-BASED PRIORITIZATION ACTIVE</strong>
                <p style="margin: 5px 0; color: #155724;">
                    Gap priorities classified using trained RandomForest model with {weight}% weight on event patterns.
                </p>
            </div>
"""
        else:
            ml_indicator = """
            <div style="background: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; margin-bottom: 20px; border-radius: 5px;">
                <strong style="color: #856404;">RULE-BASED PRIORITIZATION</strong>
                <p style="margin: 5px 0 0 0; color: #856404;">
                    Using pattern-matching fallback. ML prioritization activates after 3+ historical runs.
                </p>
            </div>
"""
        
        return f"""
        <div id="action-items" class="tab-content">
            <h2 class="section-title">Action Items - Validation Engineer Focus</h2>
            
            <!-- Interpretation Guide -->
            <div style="background: linear-gradient(135deg, #fff3e0 0%, #ffe0b2 100%); border-left: 5px solid #f57c00; padding: 20px; margin-bottom: 25px; border-radius: 8px;">
                <h3 style="margin: 0 0 10px 0; color: #e65100;">How to Interpret This Tab</h3>
                <p style="margin: 5px 0; color: #e65100; line-height: 1.5; font-size: 0.95em;">
                    <strong>Top Coverage Gaps:</strong> ML-prioritized list of inactive PMU events with EMON commands.<br>
                    <strong>Anomaly Detection:</strong> Unusual patterns, flaky events, and statistical outliers.<br>
                    <strong>Persistent Gaps:</strong> Events that remain inactive across multiple runs.<br>
                    <strong>Gap Correlation:</strong> Related gaps that may share root causes.<br>
                    <strong>Instruction Mix:</strong> Categorization of gaps by instruction type (compute, memory, branch).<br>
                    <strong>Validation Checklist:</strong> Step-by-step actions to resolve coverage gaps.
                </p>
            </div>
            
            <p style="color: #6c757d; margin-bottom: 15px;">
                All coverage gaps with priority ranking, root cause classification, and EMON validation commands.
                <strong>{len(gap_events)} total gaps identified.</strong>
            </p>
            
            {ml_indicator}
            
            <!-- Gap Statistics -->
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 25px;">
                <div style="background: linear-gradient(135deg, #dc3545 0%, #c82333 100%); color: white; padding: 20px; border-radius: 8px; text-align: center;">
                    <div style="font-size: 2.5em; font-weight: bold;">{actionable_gaps}</div>
                    <div style="margin-top: 5px;">Actionable Gaps</div>
                </div>
                <div style="background: linear-gradient(135deg, #6c757d 0%, #5a6268 100%); color: white; padding: 20px; border-radius: 8px; text-align: center;">
                    <div style="font-size: 2.5em; font-weight: bold;">{unavailable_count}</div>
                    <div style="margin-top: 5px;">Not Available</div>
                </div>
                <div style="background: linear-gradient(135deg, #0071C5 0%, #005a9c 100%); color: white; padding: 20px; border-radius: 8px; text-align: center;">
                    <div style="font-size: 2.5em; font-weight: bold;">{len(gap_events)}</div>
                    <div style="margin-top: 5px;">Total Gaps</div>
                </div>
            </div>
            
            <!-- Filters -->
            <div style="background: #f5f5f5; padding: 20px; margin-bottom: 25px; border-radius: 8px; display: flex; justify-content: space-between; flex-wrap: wrap; gap: 15px;">
                <div style="display: flex; gap: 15px; flex-wrap: wrap;">
                    <div>
                        <label style="font-weight: bold; margin-right: 8px;">Domain:</label>
                        <select id="filter-domain" style="padding: 8px; border: 1px solid #ccc; border-radius: 4px;">
{domain_options}                        </select>
                    </div>
                    <div>
                        <label style="font-weight: bold; margin-right: 8px;">Severity:</label>
                        <select id="filter-severity" style="padding: 8px; border: 1px solid #ccc; border-radius: 4px;">
                            <option value="all">All Severities</option>
                            <option value="critical">Critical</option>
                            <option value="high">High</option>
                            <option value="medium">Medium</option>
                            <option value="low">Low</option>
                        </select>
                    </div>
                    <button onclick="applyActionItemFilters()" style="padding: 8px 16px; background: #0071C5; color: white; border: none; border-radius: 4px; cursor: pointer;">Apply</button>
                    <button onclick="resetActionItemFilters()" style="padding: 8px 16px; background: #757575; color: white; border: none; border-radius: 4px; cursor: pointer;">Reset</button>
                </div>
                <div style="display: flex; gap: 10px;">
                    <button onclick="exportActionItemsCSV()" style="padding: 8px 16px; background: #2e7d32; color: white; border: none; border-radius: 4px; cursor: pointer;">Export CSV</button>
                    <button onclick="copyAllEmonCommands()" style="padding: 8px 16px; background: #28a745; color: white; border: none; border-radius: 4px; cursor: pointer;">Copy All Commands</button>
                </div>
            </div>
"""
    
    def _generate_correlation_clusters(self, gap_correlation: Dict) -> str:
        """Generate gap correlation clusters section."""
        clusters = gap_correlation['clusters']
        html = """
            <div style="margin-bottom: 30px;">
                <h3 style="color: #0071C5;">CORRELATED GAP CLUSTERS</h3>
                <p style="color: #666; margin-bottom: 15px;">
                    Gaps that occur together. Fixing one may fix others in the same cluster.
                </p>
"""
        for idx, cluster in enumerate(clusters[:5], 1):
            events = cluster.get('events', [])
            html += f"""
                <div style="background: #e3f2fd; border-left: 4px solid #0071C5; padding: 15px; margin-bottom: 15px; border-radius: 5px;">
                    <h4 style="margin-top: 0; color: #0071C5;">Cluster {idx}: {len(events)} events</h4>
                    <p style="margin: 5px 0;"><strong>Common Pattern:</strong> {cluster.get('common_pattern', 'Unknown')}</p>
                    <details>
                        <summary style="cursor: pointer; color: #0071C5;">View events</summary>
                        <ul style="margin: 10px 0; padding-left: 20px;">
"""
            for event in events[:10]:
                html += f"                            <li><code>{event}</code></li>\n"
            html += """
                        </ul>
                    </details>
                </div>
"""
        html += """
            </div>
"""
        return html
    
    def _generate_gaps_table(self, gap_events: List, analysis_results: Dict) -> str:
        """Generate the gaps table."""
        from src.ml_visualizations import render_top_gaps_table
        
        priority_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
        sorted_gaps = sorted(gap_events, key=lambda x: priority_order.get(x.get('priority', 'low'), 999))
        
        # Prepare data for table
        top_gaps_data = []
        ml_analysis = analysis_results.get('ml_analysis', {})
        workload_mapping = ml_analysis.get('workload_gap_mapping', {})
        recommendations_list = workload_mapping.get('recommendations', [])
        
        for gap in sorted_gaps:
            event_name = gap.get('event_name', 'Unknown')
            domain = gap.get('domain', 'Unknown')
            priority = gap.get('priority', 'low')
            
            # Find recommendation
            recommended_workload = ''
            confidence = 0
            for rec in recommendations_list:
                if rec.get('event') == event_name:
                    rec_workloads = rec.get('recommended_workloads', [])
                    if rec_workloads and isinstance(rec_workloads, list) and len(rec_workloads) > 0:
                        top_workload = rec_workloads[0]
                        if isinstance(top_workload, dict):
                            recommended_workload = top_workload.get('workload', '')
                            try:
                                confidence = float(top_workload.get('confidence', 0))
                            except:
                                confidence = 0
                    break
            
            top_gaps_data.append({
                'event_name': event_name,
                'domain': domain,
                'toggle_rate': 0.0,
                'severity': priority,
                'recommended_workload': recommended_workload,
                'confidence': confidence
            })
        
        emon_cmds = ml_analysis.get('emon_commands', {})
        
        html = """
            <div class="coverage-card" style="margin-bottom: 30px;">
                <h3 style="color: #0071C5; margin-bottom: 15px;">TOP COVERAGE GAPS</h3>
"""
        html += render_top_gaps_table(top_gaps_data, max_rows=100, show_emon=True, emon_commands=emon_cmds)
        html += """
            </div>
"""
        return html
    
    def _generate_platform_gaps(self, platform_comparison: Dict) -> str:
        """Generate platform-specific gaps section."""
        platform_gaps = platform_comparison['platform_specific_gaps']
        html = """
            <div style="margin-bottom: 30px;">
                <h3 style="color: #7b1fa2;">PLATFORM-SPECIFIC GAPS</h3>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
                    <div style="background: #e1f5fe; padding: 20px; border-radius: 8px;">
                        <h4 style="margin-top: 0; color: #0277bd;">Windows-Only Gaps</h4>
"""
        windows_gaps = platform_gaps.get('windows_only', [])
        if windows_gaps:
            html += "                        <ul style='margin: 0; padding-left: 20px;'>\n"
            for gap in windows_gaps[:10]:
                html += f"                            <li><code>{gap}</code></li>\n"
            html += "                        </ul>\n"
        else:
            html += "                        <p style='color: #666;'>No Windows-specific gaps found.</p>\n"
        
        html += """
                    </div>
                    <div style="background: #f3e5f5; padding: 20px; border-radius: 8px;">
                        <h4 style="margin-top: 0; color: #6a1b9a;">Linux-Only Gaps</h4>
"""
        linux_gaps = platform_gaps.get('linux_only', [])
        if linux_gaps:
            html += "                        <ul style='margin: 0; padding-left: 20px;'>\n"
            for gap in linux_gaps[:10]:
                html += f"                            <li><code>{gap}</code></li>\n"
            html += "                        </ul>\n"
        else:
            html += "                        <p style='color: #666;'>No Linux-specific gaps found.</p>\n"
        
        html += """
                    </div>
                </div>
            </div>
"""
        return html
    
    def _generate_emon_commands(self, emon_commands: Dict) -> str:
        """Generate EMON commands section."""
        html = """
            <div style="margin-bottom: 30px;">
                <h3 style="color: #00796b;">EMON VALIDATION COMMANDS</h3>
                <p style="color: #666; margin-bottom: 15px;">Ready-to-run EMON commands grouped by domain.</p>
"""
        for cmd_group in emon_commands['commands'][:10]:
            domain = cmd_group.get('domain', 'Unknown')
            command = cmd_group.get('command', '')
            event_count = len(cmd_group.get('events', []))
            
            html += f"""
                <details style="background: #e0f2f1; border-left: 4px solid #00796b; padding: 15px; margin-bottom: 10px; border-radius: 5px;">
                    <summary style="cursor: pointer; color: #00796b; font-weight: bold;">{domain} - {event_count} events</summary>
                    <pre style="background: #263238; color: #aed581; padding: 15px; border-radius: 5px; overflow-x: auto; margin-top: 10px;">{command}</pre>
                </details>
"""
        html += """
            </div>
"""
        return html
    
    def _generate_anomaly_section(self, anomalies: Dict) -> str:
        """Generate anomaly detection section."""
        from src.ml_visualizations import render_explain_panel
        
        stats = anomalies['statistics']
        by_domain = anomalies.get('by_domain', {})
        
        html = f"""
            <div class="coverage-card" style="margin-bottom: 30px;">
                <h3 style="color: #0071C5; margin-bottom: 15px;">ANOMALY DETECTION ANALYSIS</h3>
                <p style="color: #666; margin-bottom: 15px;">
                    ML-detected anomalous events. Found {stats['total_anomalies']} anomalies across {stats['domains_affected']} domains.
                </p>
                
                <div style="display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 20px;">
"""
        
        severity_colors = {'high': '#dc3545', 'medium': '#ffc107', 'low': '#17a2b8'}
        for severity, count in stats.get('by_severity', {}).items():
            color = severity_colors.get(severity, '#6c757d')
            html += f"""
                    <div style="background: {color}; color: white; padding: 8px 20px; border-radius: 20px; font-weight: 600;">
                        {severity.upper()}: {count}
                    </div>
"""
        
        html += """
                </div>
                <div style="max-height: 400px; overflow-y: auto;">
"""
        
        sorted_domains = sorted(by_domain.items(), key=lambda x: len(x[1]), reverse=True)
        for domain, domain_anomalies in sorted_domains[:5]:
            html += f"""
                    <div style="background: #f8f9fa; padding: 15px; margin-bottom: 15px; border-left: 4px solid #0071C5; border-radius: 4px;">
                        <strong style="color: #2c3e50;">{domain.upper()}</strong>
                        <span style="background: #0071C5; color: white; padding: 2px 8px; border-radius: 10px; font-size: 0.85em; margin-left: 10px;">{len(domain_anomalies)} anomalies</span>
"""
            for anom in domain_anomalies[:5]:
                severity = anom.get('severity', 'medium')
                color = severity_colors.get(severity, '#6c757d')
                html += f"""
                        <div style="background: white; padding: 8px; margin-top: 8px; border-left: 3px solid {color}; border-radius: 4px;">
                            <strong>{anom.get('event', 'Unknown')}</strong>
                            <span style="background: {color}; color: white; padding: 2px 6px; border-radius: 8px; font-size: 0.75em; margin-left: 10px;">{severity.upper()}</span>
                            <p style="color: #666; margin: 5px 0 0 0; font-size: 0.9em;">{anom.get('explanation', '')}</p>
                        </div>
"""
            html += """
                    </div>
"""
        
        html += """
                </div>
            </div>
"""
        return html
    
    def _generate_persistent_gaps(self, analysis_results: Dict) -> str:
        """Generate persistent gaps section."""
        from src.ml_persistent_gaps import generate_persistent_gaps_analysis
        
        product_id = self.rg._get_product_id(analysis_results)
        data_directory = Path(r'C:\silicon_coverage_analyzer_data')
        return generate_persistent_gaps_analysis(data_directory, product_id=product_id) or ""
    
    def _generate_ml_recommendations(self, recommendations: List) -> str:
        """Generate ML recommendations section."""
        html = """
            <div class="coverage-card" style="margin-bottom: 30px;">
                <h3 style="color: #0071C5; margin-bottom: 20px;">ML RECOMMENDATIONS</h3>
                <div style="max-height: 400px; overflow-y: auto;">
"""
        
        priority_colors = {'HIGH': '#dc3545', 'MEDIUM': '#ffc107', 'LOW': '#17a2b8'}
        for rec in recommendations:
            priority = rec.get('priority', 'LOW')
            color = priority_colors.get(priority, '#6c757d')
            
            html += f"""
                <div style="background: #f8f9fa; padding: 20px; margin-bottom: 15px; border-left: 4px solid {color}; border-radius: 6px;">
                    <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 10px;">
                        <h4 style="margin: 0; color: #2c3e50;">{rec.get('title', 'Recommendation')}</h4>
                        <span style="background: {color}; color: white; padding: 4px 10px; border-radius: 4px; font-size: 0.75em;">{priority}</span>
                    </div>
                    <p style="color: #666; margin: 5px 0; font-size: 0.9em;"><strong>Category:</strong> {rec.get('category', 'General')}</p>
                    <p style="color: #444; margin: 10px 0;">{rec.get('description', '')}</p>
                    <div style="background: #e8f5e9; padding: 10px; border-radius: 4px;">
                        <strong style="color: #2e7d32;">Action:</strong> {rec.get('action', '')}
                    </div>
                </div>
"""
        
        html += """
                </div>
            </div>
"""
        return html
    
    def _generate_gap_correlation_section(self, analysis_results: Dict, gaps_analysis: Dict) -> str:
        """Generate gap correlation analysis section."""
        # Run correlation analysis
        try:
            correlation_results = self.rg.correlation_analyzer.analyze_correlations(gaps_analysis, historical_runs=10)
            analysis_results['gap_correlation'] = correlation_results
        except Exception as e:
            logger.error(f"Gap correlation analysis failed: {e}")
        
        html = """
        <div class="chart-container" style="margin-top: 30px;">
            <h3 style="color: #0071C5;">Gap Correlation Analysis</h3>
            <p style="color: #666; margin-bottom: 20px;">
                Events that tend to fail together - indicates shared root causes.
            </p>
"""
        
        gap_correlation = analysis_results.get('gap_correlation')
        if gap_correlation:
            html += self._generate_gap_correlation_heatmap(gap_correlation)
        else:
            html += """
            <div style="background: #fff3cd; border-left: 5px solid #ffc107; padding: 20px; border-radius: 8px;">
                <h4 style="color: #856404; margin: 0 0 10px 0;">Correlation Analysis Unavailable</h4>
                <p style="color: #856404; margin: 0;">
                    Requires multiple historical runs to identify patterns. Run more collections to enable.
                </p>
            </div>
"""
        
        html += """
        </div>
"""
        return html
    
    def _generate_instruction_mix_section(self, coverage: Dict, analysis_results: Dict) -> str:
        """Generate instruction mix breakdown section."""
        html = """
        <div class="chart-container" style="margin-top: 30px; background: linear-gradient(135deg, #e3f2fd 0%, #f3e5f5 100%); border-left: 5px solid #0071C5;">
"""
        html += self._generate_instruction_mix_breakdown(coverage, analysis_results)
        html += """
        </div>
"""
        return html

    def _generate_validation_checklist(self, analysis_results):
        """Generate validation checklist with helpful navigation links."""
        coverage = analysis_results.get('coverage', {})
        coverage_pct = coverage.get('activity_coverage', 0)
        total_gaps = len(analysis_results.get('gaps', {}).get('gaps_by_domain', {}))
        
        html = """
            <div class="chart-container" style="margin-top: 30px;">
                <h3 style="color: #f57c00;"> Validation Checklist</h3>
                <p style="color: #666; margin-bottom: 20px;">Track your validation progress</p>
"""
        
        checklist_items = [
            {
                'task': 'Achieve 70%+ overall coverage',
                'completed': coverage_pct >= 70,
                'current': f'{coverage_pct:.1f}%',
                'link': 'ml-training-strategy',
                'link_text': 'View Milestones'
            },
            {
                'task': 'Close all HIGH priority gaps',
                'completed': total_gaps == 0,
                'current': f'{total_gaps} gaps remaining',
                'link': 'action-items',
                'link_text': 'View Gaps'
            },
            {
                'task': 'No regressions detected',
                'completed': len(analysis_results.get('temporal_trends', {}).get('regressions', [])) == 0,
                'current': f'{len(analysis_results.get("temporal_trends", {}).get("regressions", []))} regressions',
                'link': 'executive',
                'link_text': 'Check Status'
            },
            {
                'task': 'Run stress workloads',
                'completed': analysis_results.get('stress_detection', {}).get('detected', False),
                'current': 'Stress detected' if analysis_results.get('stress_detection', {}).get('detected', False) else 'No stress',
                'link': 'workload-health',
                'link_text': 'View Analysis'
            },
            {
                'task': 'Collect 10+ historical runs',
                'completed': analysis_results.get('temporal_trends', {}).get('runs_analyzed', 0) >= 10,
                'current': f'{analysis_results.get("temporal_trends", {}).get("runs_analyzed", 0)} runs',
                'link': 'ml-training-strategy',
                'link_text': 'View Training Status'
            }
        ]
        
        for item in checklist_items:
            status_icon = '' if item['completed'] else ''
            status_color = '#4caf50' if item['completed'] else '#d32f2f'
            
            html += f"""
                <div style="background: #f8f9fa; padding: 15px; margin-bottom: 10px; border-radius: 8px; 
                            border-left: 4px solid {status_color}; display: flex; justify-content: space-between; align-items: center;">
                    <div style="flex: 1;">
                        <span style="font-size: 1.3em; margin-right: 10px;">{status_icon}</span>
                        <strong style="color: #333;">{item['task']}</strong>
                        <span style="color: #666; font-size: 0.9em; margin-left: 10px;">
                            {item['current']}
                        </span>
                    </div>
                    <a href="#" onclick="switchTab('{item['link']}'); return false;" 
                       style="background: #0071C5; color: white; padding: 6px 12px; border-radius: 4px; 
                              text-decoration: none; font-size: 0.85em; white-space: nowrap;">
                        {item['link_text']} ->
                    </a>
                </div>
"""
        
        html += """
            </div>
"""
        return html
    

    def _generate_gap_correlation_heatmap(self, gap_correlation):
        """Generate visual gap correlation heatmap HTML with enhanced interpretation guide."""
        from src.ml_visualizations import render_heatmap
        
        # Check if correlation analysis was successful
        if not gap_correlation:
            return """
            <div style="background: #fff3cd; border-left: 5px solid #ffc107; padding: 20px; border-radius: 8px;">
                <p style="color: #856404; margin: 0;">No correlation data available. Run multiple collection sessions to build correlation patterns.</p>
            </div>
"""
        
        # Check status
        status = gap_correlation.get('status', 'unknown')
        if status == 'insufficient_data':
            message = gap_correlation.get('message', 'Need historical gap data for correlation analysis')
            return f"""
            <div style="background: #fff3cd; border-left: 5px solid #ffc107; padding: 20px; border-radius: 8px;">
                <p style="color: #856404; margin: 0;">{message}</p>
            </div>
"""
        
        # Check for correlation matrix
        matrix_data = gap_correlation.get('correlation_matrix', {})
        if not matrix_data:
            return """
            <div style="background: #fff3cd; border-left: 5px solid #ffc107; padding: 20px; border-radius: 8px;">
                <p style="color: #856404; margin: 0;">Insufficient gap data to compute correlations.</p>
            </div>
"""
        
        # Prepare matrix for heatmap visualization
        events = list(matrix_data.keys())[:15]  # Limit to top 15 events for readability
        
        if len(events) < 2:
            return """
            <div style="background: #e7f3ff; border-left: 5px solid #0071C5; padding: 20px; border-radius: 8px;">
                <p style="color: #01579b; margin: 0;">Only 1 gap event detected - correlation analysis requires at least 2 events.</p>
            </div>
"""
        
        # Build correlation matrix
        matrix = []
        for event1 in events:
            row = []
            for event2 in events:
                if event1 == event2:
                    row.append(1.0)  # Self-correlation
                else:
                    corr = matrix_data.get(event1, {}).get(event2, 0)
                    row.append(corr)
            matrix.append(row)
        
        # Analyze correlation patterns
        all_correlations = []
        for i in range(len(events)):
            for j in range(i + 1, len(events)):
                all_correlations.append(matrix[i][j])
        
        perfect_count = sum(1 for c in all_correlations if c >= 0.99)
        strong_count = sum(1 for c in all_correlations if 0.8 <= c < 0.99)
        moderate_count = sum(1 for c in all_correlations if 0.5 <= c < 0.8)
        weak_count = len(all_correlations) - perfect_count - strong_count - moderate_count
        
        total_pairs = len(all_correlations)
        perfect_pct = (perfect_count / total_pairs * 100) if total_pairs > 0 else 0
        
        # Detect event domains - load from config
        uncore_domains = _DOMAIN_CONFIG.get('uncore_domains', ['cbo', 'ncu', 'hac_cbo', 'hac_ncu', 'cha', 'imc', 'upi', 'qpi', 'm2m', 'm3upi'])
        uncore_count = sum(1 for e in events if any(d in e.lower() for d in uncore_domains))
        uncore_pct = (uncore_count / len(events) * 100) if len(events) > 0 else 0
        
        # Interpretation guide
        html = f"""
        <div style="background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%); border-left: 5px solid #4caf50; padding: 20px; border-radius: 8px; margin-bottom: 20px;">
            <h4 style="margin: 0 0 15px 0; color: #1b5e20;">How to Interpret Gap Correlations</h4>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 15px;">
                <div style="background: white; padding: 10px; border-radius: 5px;">
                    <strong style="color: #dc3545;">1.00 (Perfect):</strong> <span style="font-size: 0.9em;">Events ALWAYS fail together -> single root cause</span>
                </div>
                <div style="background: white; padding: 10px; border-radius: 5px;">
                    <strong style="color: #f39c12;">0.80-0.95 (Strong):</strong> <span style="font-size: 0.9em;">Usually fail together -> shared dependency</span>
                </div>
                <div style="background: white; padding: 10px; border-radius: 5px;">
                    <strong style="color: #17a2b8;">0.50-0.79 (Moderate):</strong> <span style="font-size: 0.9em;">Sometimes fail together -> partial link</span>
                </div>
                <div style="background: white; padding: 10px; border-radius: 5px;">
                    <strong style="color: #6c757d;">0.00-0.49 (Weak):</strong> <span style="font-size: 0.9em;">Fail independently -> different causes</span>
                </div>
            </div>
            <div style="background: rgba(255,255,255,0.7); padding: 12px; border-radius: 5px;">
                <strong>Your Data:</strong> {len(events)} events · 
                <span style="color: #dc3545;">{perfect_count} perfect</span> · 
                <span style="color: #f39c12;">{strong_count} strong</span> · 
                <span style="color: #17a2b8;">{moderate_count} moderate</span> · 
                <span style="color: #6c757d;">{weak_count} weak</span>
            </div>
"""
        
        # Add recommendations
        if perfect_pct > 80:
            workload_tips = ""
            if uncore_pct > 60:
                workload_tips = f"""
                <p style="margin: 8px 0 0 0; color: #856404;"><strong>Detected: {uncore_pct:.0f}% uncore events (CBO/NCU/HAC)</strong></p>
                <ul style="margin: 5px 0; padding-left: 20px; font-size: 0.9em;">
                    <li>Try cross-socket workloads: <code>numactl --interleave=all stress-ng --vm 8</code></li>
                    <li>Enable QPI/UPI traffic generators or NUMA-distributed benchmarks</li>
                    <li>Check BIOS: Verify SNC, COD, UPI link settings</li>
                </ul>
"""
            else:
                workload_tips = """
                <ul style="margin: 5px 0; padding-left: 20px; font-size: 0.9em;">
                    <li>Check if events require specific platform features or BIOS settings</li>
                    <li>Verify EMON collects all domains: <code>emon -v</code></li>
                </ul>
"""
            
            html += f"""
            <div style="background: #fff3cd; padding: 12px; border-radius: 5px; margin-top: 10px; border-left: 3px solid #ffc107;">
                <strong style="color: #856404;">Warning: {perfect_pct:.0f}% Perfect Correlation</strong>
                <p style="margin: 5px 0; font-size: 0.9em; color: #856404;">All gaps likely share ONE root cause (missing workload type, platform limitation, or collection issue)</p>
{workload_tips}
            </div>
"""
        elif strong_count > 0:
            html += f"""
            <div style="background: #d4edda; padding: 12px; border-radius: 5px; margin-top: 10px; border-left: 3px solid #28a745;">
                <strong style="color: #155724;">Good diversity: {strong_count} strong + {moderate_count} moderate correlations</strong>
                <p style="margin: 5px 0 0 0; font-size: 0.9em; color: #155724;">Focus on high-correlation clusters first - fixing one may fix multiple events</p>
            </div>
"""
        
        html += "</div>"
        
        # Truncate event names
        x_labels = [e[:25] + '...' if len(e) > 25 else e for e in events]
        y_labels = x_labels.copy()
        
        legend = {
            'title': 'Correlation',
            'min_label': '0.0 (Independent)',
            'max_label': '1.0 (Always Together)'
        }
        
        return html + render_heatmap(matrix, x_labels, y_labels, legend, 'gapCorrelationHeatmap')
    

    def _generate_instruction_mix_breakdown(self, coverage_results, analysis_results):
        """
        Generate instruction mix category breakdown with ML-learned categories.
        Shows events grouped by learned instruction types (FP_SIMD, Memory, Branch, etc.)
        """
        # Ensure categories are loaded - try multiple sources for product_id
        product_id = None
        
        # Try hardware_config first (most reliable)
        hw_config = analysis_results.get('hardware_config', {})
        if hw_config.get('product_id'):
            product_id = hw_config['product_id']
        elif hw_config.get('product_name'):
            product_id = hw_config['product_name'].lower().replace(' ', '_').replace('-', '_')
        
        # Fallback to coverage_results
        if not product_id and coverage_results.get('product_name'):
            product_id = coverage_results['product_name'].lower().replace(' ', '_').replace('-', '_')
        
        if not product_id:
            logger.warning("No product_id found for instruction mix categorization")
            return ""  # Can't categorize without product ID
        
        # Load categories if not already loaded
        if not self.rg.instruction_categories_loaded:
            self.rg._load_instruction_categories(product_id)
            logger.info(f"Loaded instruction categories for product: {product_id}")
        
        if not self.rg.instruction_categories:
            logger.warning(f"No instruction categories available for {product_id}, using fallback")
            self.rg._use_fallback_categories()
        
        if not self.rg.instruction_categories:
            return ""  # Still no categories (shouldn't happen with fallback)
        
        # Categorize all active events
        category_events = {cat_name: [] for cat_name in self.rg.instruction_categories.keys()}
        category_counts = {cat_name: 0 for cat_name in self.rg.instruction_categories.keys()}
        total_active = 0
        
        domain_results = coverage_results.get('domain_results', {})
        for domain, stats in domain_results.items():
            active_events = stats.get('active_events', [])
            for event_info in active_events:
                event_name = event_info.get('event', '')
                category_info = self.rg._categorize_event(event_name)
                category_name = category_info['name']
                
                category_events[category_name].append({
                    'event': event_name,
                    'domain': domain,
                    'total': event_info.get('total_activity', 0)
                })
                category_counts[category_name] += 1
                total_active += 1
        
        # Calculate percentages
        category_percentages = {}
        for cat_name, count in category_counts.items():
            pct = (count / total_active * 100) if total_active > 0 else 0
            category_percentages[cat_name] = round(pct, 1)
        
        # Log categorization results
        logger.info(f"Instruction Mix Categorization: {total_active} total events categorized")
        logger.info(f"Categories: {', '.join([f'{k}:{v}' for k, v in category_counts.items() if v > 0])}")
        
        # Check if using ML-learned or fallback categories
        is_ml_learned = self.rg.current_product_id and self.rg.instruction_categories_loaded
        category_source = "ML-learned from your historical data" if is_ml_learned else "seed patterns (no ML data yet)"
        
        # Generate HTML
        html = f"""
        <div class="chart-container" style="margin-top: 30px; background: linear-gradient(135deg, #e3f2fd 0%, #f3e5f5 100%); border-left: 5px solid #0071C5;">
            <h3 style="color: #003e7e;">INSTRUCTION MIX CATEGORIZATION</h3>
            <p style="color: #003e7e; font-size: 0.95em;">
                {'ML-learned from ' + str(total_active) + ' events across historical runs' if is_ml_learned else 'Using seed patterns - run ML training (5+ collections) for auto-learned categories'}
            </p>
            
            <!-- Donut Chart and Category Table -->
            <div style="display: grid; grid-template-columns: 450px 1fr; gap: 25px; margin-top: 20px;">
                <div style="background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                    <canvas id="instructionMixChart" style="max-height: 450px; height: 450px;"></canvas>
                </div>
                
                <div style="background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                    <h4 style="color: #003e7e; margin-top: 0;">Category Breakdown</h4>
                    <div style="max-height: 450px; overflow-y: auto; padding-right: 10px;">
                        <table style="width: 100%; border-collapse: collapse;">
                            <thead style="position: sticky; top: 0; background: white; z-index: 10;">
                                <tr style="background: #f8f9fa; border-bottom: 2px solid #dee2e6;">
                                    <th style="padding: 10px; text-align: left;">Category</th>
                                    <th style="padding: 10px; text-align: center;">Events</th>
                                    <th style="padding: 10px; text-align: center;">%</th>
                                </tr>
                            </thead>
                            <tbody>
"""
        
        # Add category rows (exclude 'Other' from main list, show at end)
        categories_sorted = sorted(
            [(name, category_counts[name], category_percentages[name]) 
             for name in self.rg.instruction_categories.keys() if name != 'Other' and category_counts[name] > 0],
            key=lambda x: x[1],
            reverse=True
        )
        
        chart_index = 0
        for cat_name, count, pct in categories_sorted:
            cat_info = self.rg.instruction_categories[cat_name]
            html += f"""
                            <tr style="border-bottom: 1px solid #f0f0f0; cursor: pointer; transition: background 0.2s;" 
                                onmouseover="this.style.background='#f5f5f5'; highlightCategory({chart_index});" 
                                onmouseout="this.style.background=''; highlightCategory(null);">
                                <td style="padding: 12px;">
                                    <div style="display: flex; align-items: center; gap: 10px;">
                                        <div style="width: 12px; height: 12px; border-radius: 50%; background: {cat_info['color']}; flex-shrink: 0;"></div>
                                        <div style="font-weight: 600; color: #333; font-size: 0.95em;">
                                            {cat_name}
                                        </div>
                                    </div>
                                </td>
                                <td style="padding: 12px; text-align: center; font-weight: 700; font-size: 1.05em; color: #333;">{count}</td>
                                <td style="padding: 12px; text-align: center;">
                                    <span style="background: {cat_info['color']}; color: white; padding: 5px 12px; border-radius: 16px; font-weight: 700; font-size: 0.9em;">
                                        {pct}%
                                    </span>
                                </td>
                            </tr>
"""
            chart_index += 1
        
        # Add 'Other' category if it has events
        if category_counts.get('Other', 0) > 0:
            other_info = self.rg.instruction_categories.get('Other', {})
            other_count = category_counts['Other']
            other_pct = category_percentages['Other']
            html += f"""
                            <tr style="border-bottom: 1px solid #dee2e6; background: #f8f9fa; cursor: pointer; transition: background 0.2s;" 
                                onmouseover="this.style.background='#e9ecef'; highlightCategory({chart_index});" 
                                onmouseout="this.style.background='#f8f9fa'; highlightCategory(null);">
                                <td style="padding: 10px;">
                                    <div style="display: flex; align-items: center; gap: 10px;">
                                        <div style="width: 12px; height: 12px; border-radius: 50%; background: {other_info.get('color', '#6c757d')}; flex-shrink: 0;"></div>
                                        <div style="font-weight: 600; color: #333;">Other</div>
                                    </div>
                                </td>
                                <td style="padding: 10px; text-align: center; font-weight: bold;">{other_count}</td>
                                <td style="padding: 10px; text-align: center;">
                                    <span style="background: {other_info.get('color', '#6c757d')}; color: white; padding: 3px 10px; border-radius: 12px; font-weight: bold;">
                                        {other_pct}%
                                    </span>
                                </td>
                            </tr>
"""
        
        html += """
                            </tbody>
                        </table>
                    </div>
                </div>
            </div>
"""
        
        # Prepare chart data
        chart_labels = []
        chart_data = []
        chart_colors = []
        chart_icons = []
        
        for cat_name, count, pct in categories_sorted:
            if count > 0:
                cat_info = self.rg.instruction_categories[cat_name]
                chart_labels.append(f"{cat_info['icon']} {cat_name}")
                chart_data.append(count)
                chart_colors.append(cat_info['color'])
        
        # Add Other if present
        if category_counts.get('Other', 0) > 0:
            other_info = self.rg.instruction_categories.get('Other', {})
            chart_labels.append(f"{other_info.get('icon', '?')} Other")
            chart_data.append(category_counts['Other'])
            chart_colors.append(other_info.get('color', '#6c757d'))
        
        html += f"""
            <script>
            // Instruction Mix Donut Chart - Wait for Chart.js to be available
            window.addEventListener('load', function() {{
                if (typeof Chart === 'undefined') {{
                    console.error('Chart.js not loaded');
                    return;
                }}
                const instructionMixChart = new Chart(document.getElementById('instructionMixChart'), {{
                type: 'doughnut',
                data: {{
                    labels: {json.dumps(chart_labels)},
                    datasets: [{{
                        data: {json.dumps(chart_data)},
                        backgroundColor: {json.dumps(chart_colors)},
                        borderWidth: 2,
                        borderColor: '#fff'
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: true,
                    plugins: {{
                        legend: {{
                            display: false
                        }},
                        tooltip: {{
                            callbacks: {{
                                label: function(context) {{
                                    const label = context.label || '';
                                    const value = context.parsed || 0;
                                    const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                    const pct = ((value / total) * 100).toFixed(1);
                                    return label + ': ' + value + ' events (' + pct + '%)';
                                }}
                            }}
                        }}
                    }}
                }}
            }});
            
            // Function to highlight pie slice on category click
            function highlightCategory(categoryIndex) {{
                // Reset all segments
                instructionMixChart.setActiveElements([]);
                
                // Highlight clicked segment
                if (categoryIndex !== null) {{
                    instructionMixChart.setActiveElements([{{
                        datasetIndex: 0,
                        index: categoryIndex
                    }}]);
                }}
                
                instructionMixChart.update();
            }}
            }});
            </script>
            
            <!-- Missing Category Analysis -->
            <div style="margin-top: 30px; background: white; padding: 25px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                <h4 style="color: #d32f2f; margin-top: 0;"> Missing Category Analysis</h4>
                <p style="color: #666; margin-bottom: 15px;">
                    Categories with low or zero coverage may indicate workload gaps. Add specific stress tests to improve coverage breadth.
                </p>
"""
        
        # Identify missing or low-coverage categories
        missing_categories = []
        low_categories = []
        
        for cat_name, cat_info in self.rg.instruction_categories.items():
            count = category_counts.get(cat_name, 0)
            pct = category_percentages.get(cat_name, 0)
            
            if cat_name == 'Other':
                continue  # Skip 'Other' category
            
            if count == 0:
                missing_categories.append({
                    'name': cat_name,
                    'icon': cat_info['icon'],
                    'description': cat_info['description'],
                    'color': cat_info['color']
                })
            elif pct < 5.0:  # Less than 5% coverage
                low_categories.append({
                    'name': cat_name,
                    'icon': cat_info['icon'],
                    'description': cat_info['description'],
                    'color': cat_info['color'],
                    'count': count,
                    'pct': pct
                })
        
        if missing_categories or low_categories:
            html += """
                <div style="max-height: 400px; overflow-y: auto; padding-right: 10px;">
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
"""
            
            # Missing categories
            if missing_categories:
                html += """
                    <div>
                        <h5 style="color: #d32f2f; margin-bottom: 10px;">? Zero Coverage ({} categories)</h5>
                        <div style="background: #ffebee; padding: 15px; border-radius: 6px; border-left: 4px solid #d32f2f;">
""".format(len(missing_categories))
                
                for cat in missing_categories:
                    html += f"""
                            <div style="margin-bottom: 10px; padding-bottom: 10px; border-bottom: 1px solid #ef9a9a;">
                                <div style="display: flex; align-items: center; gap: 8px;">
                                    <div style="width: 10px; height: 10px; border-radius: 50%; background: {cat['color']}; flex-shrink: 0;"></div>
                                    <strong style="color: #333; font-size: 0.9em;">{cat['name']}</strong>
                                </div>
                            </div>
"""
                
                html += """
                        </div>
                    </div>
"""
            
            # Low coverage categories
            if low_categories:
                html += """
                    <div>
                        <h5 style="color: #f57c00; margin-bottom: 10px;"> Low Coverage ({} categories)</h5>
                        <div style="background: #fff3e0; padding: 15px; border-radius: 6px; border-left: 4px solid #f57c00;">
""".format(len(low_categories))
                
                for cat in low_categories:
                    html += f"""
                            <div style="margin-bottom: 10px; padding-bottom: 10px; border-bottom: 1px solid #ffcc80;">
                                <div style="display: flex; align-items: center; justify-content: space-between;">
                                    <div style="display: flex; align-items: center; gap: 8px;">
                                        <div style="width: 10px; height: 10px; border-radius: 50%; background: {cat['color']}; flex-shrink: 0;"></div>
                                        <strong style="color: #333; font-size: 0.9em;">{cat['name']}</strong>
                                    </div>
                                    <span style="background: #f57c00; color: white; padding: 2px 8px; border-radius: 10px; font-size: 0.75em; font-weight: bold;">
                                        {cat['count']} ({cat['pct']}%)
                                    </span>
                                </div>
                            </div>
"""
                
                html += """
                        </div>
                    </div>
"""
            
            html += """
                    </div>
                </div>
"""
        else:
            html += """
                <div style="background: #e8f5e9; padding: 20px; border-radius: 6px; border-left: 4px solid #4caf50; text-align: center;">
                    <div style="font-size: 2em; margin-bottom: 10px;">?</div>
                    <div style="color: #2e7d32; font-weight: 600; font-size: 1.1em;">Excellent Coverage Breadth!</div>
                    <div style="color: #666; margin-top: 8px;">All instruction categories have sufficient coverage (=5%)</div>
                </div>
"""
        
        html += """
            </div>
            
            <!-- ML Learning Explanation -->
            <div style="margin-top: 30px; background: linear-gradient(135deg, #e1f5fe 0%, #f3e5f5 100%); padding: 25px; border-radius: 8px; border-left: 5px solid #7b1fa2;">
                <h4 style="color: #4a148c; margin-top: 0;">How ML Self-Learning Works</h4>
                <div style="color: #4a148c; line-height: 1.8;">
                    <p style="margin-bottom: 15px;">
                        <strong>This categorization improves automatically with each run:</strong>
                    </p>
                    <ol style="margin-left: 20px;">
                        <li style="margin-bottom: 10px;">
                            <strong>Initial Run:</strong> Uses seed patterns (basic event name matching like "FP_", "LOAD_", "BRANCH_")
                        </li>
                        <li style="margin-bottom: 10px;">
                            <strong>After 5+ Runs:</strong> ML trainer analyzes event co-occurrence patterns across all historical runs
                        </li>
                        <li style="margin-bottom: 10px;">
                            <strong>Pattern Learning:</strong> Events that appear together frequently get auto-grouped (e.g., "If event X always appears with FP events, classify X as FP_SIMD")
                        </li>
                        <li style="margin-bottom: 10px;">
                            <strong>Category Refinement:</strong> K-Means clustering discovers new subcategories your workloads actually use
                        </li>
                        <li style="margin-bottom: 10px;">
                            <strong>Workload-Specific:</strong> Categories adapt to YOUR specific test scenarios, not generic patterns
                        </li>
                    </ol>
                    <p style="margin-top: 15px; padding: 15px; background: rgba(255,255,255,0.7); border-radius: 6px;">
                        <strong> Current Status:</strong> {'Trained on ' + str(total_active) + ' events from your historical runs. Categories are workload-optimized.' if is_ml_learned else 'Using fallback seed patterns. Run ML training (5+ collections) to enable auto-learned categories.'}
                    </p>
                </div>
            </div>
        </div>
"""
        
        return html
    
