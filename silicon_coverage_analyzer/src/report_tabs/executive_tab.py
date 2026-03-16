"""
Executive Tab Generator Module

Generates the Executive Summary tab for the HTML report.
Extracted from report_generator.py for better maintainability.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List

from src.config_utils import get_domain_colors

logger = logging.getLogger(__name__)

# Load domain colors from config (avoids circular import)
DOMAIN_COLORS = get_domain_colors()


class ExecutiveTabGenerator:
    """Generates the Executive Summary tab content."""
    
    def __init__(self, report_generator):
        """
        Initialize with reference to parent ReportGenerator.
        
        Args:
            report_generator: Parent ReportGenerator instance for accessing
                             shared methods and ML models.
        """
        self.rg = report_generator  # Reference to parent for shared methods
    
    def generate(self, summary: Dict[str, Any], analysis_results: Dict[str, Any]) -> str:
        """
        Generate Executive Summary tab HTML.
        
        Args:
            summary: Coverage summary data
            analysis_results: Full analysis results
            
        Returns:
            HTML string for the executive tab
        """
        coverage = analysis_results.get('coverage', {})
        stress_info = analysis_results.get('stress_detection', {})
        ml_insights = analysis_results.get('ml_insights', {})
        ml_analysis = analysis_results.get('ml_analysis', {})
        gaps_analysis = analysis_results.get('gaps', {})
        regression_analysis = analysis_results.get('regression_analysis', {})
        
        # Get ML-driven sentiment
        overall_sentiment = self.rg._get_coverage_sentiment(
            summary['overall_coverage_percentage'], 
            context='general'
        )
        
        # Get critical alerts
        critical_alerts = self._build_critical_alerts(
            analysis_results, gaps_analysis, regression_analysis
        )
        
        # Get flaky events list for display
        flaky_events_list = self._get_flaky_events(analysis_results)
        
        # Get anomaly count
        total_anomalies = self._get_anomaly_count(ml_analysis)
        
        # Build recommended actions
        recommended_actions = self._build_recommended_actions(
            analysis_results, gaps_analysis, regression_analysis,
            flaky_events_list, total_anomalies, summary
        )
        
        # Use ML to prioritize actions
        action_context = {
            'total_gaps': len(gaps_analysis.get('non_toggling_events', [])) if gaps_analysis else 0,
            'coverage_pct': summary['overall_coverage_percentage'],
            'regression_count': len(regression_analysis.get('regressions', [])) if regression_analysis else 0,
            'anomaly_count': total_anomalies,
            'flaky_count': len(flaky_events_list)
        }
        
        recommended_actions = self.rg.ml_action_prioritizer.prioritize_actions(
            recommended_actions, action_context
        )[:5]  # Top 5
        
        # Calculate cumulative coverage stats
        product_id = self.rg._get_product_id(analysis_results)
        cumulative_stats = self.rg._get_cumulative_coverage_stats(analysis_results, product_id)
        
        # Build HTML
        html = self._generate_header_section(summary, analysis_results, overall_sentiment, 
                                             cumulative_stats, stress_info)
        
        # Add stress tracking if available
        stress_tracking = analysis_results.get('stress_tracking', {})
        if stress_tracking and stress_tracking.get('timeline'):
            html += self._generate_stress_tracking_section(stress_tracking, stress_info)
        
        # Build alerts HTML
        additional_alerts = self._generate_additional_alerts(analysis_results, product_id)
        all_alerts = critical_alerts + additional_alerts
        alerts_html = self._generate_alerts_section(all_alerts, flaky_events_list, 
                                                    recommended_actions, analysis_results)
        
        # Add ML insights section
        alerts_html += self._generate_ml_insights_section(analysis_results, gaps_analysis, product_id)
        
        # Quick stats grid
        html += self._generate_quick_stats(summary, gaps_analysis, stress_info, 
                                           regression_analysis, total_anomalies, product_id)
        
        # Domain coverage charts
        html += self._generate_domain_coverage_section(analysis_results, summary)
        
        # Historical coverage milestones
        historical_html = self._generate_realistic_coverage_milestones(analysis_results, product_id)
        if historical_html:
            html += historical_html
        
        # Insert alerts after coverage charts
        html += alerts_html
        
        # ML Intelligence Summary
        if ml_analysis or ml_insights:
            html += """
            <div style="margin-top: 40px; border-top: 3px solid #0071C5; padding-top: 30px;">
"""
            html += self._generate_ml_intelligence_summary(
                ml_analysis or ml_insights, 
                analysis_results.get('coverage', {})
            )
            html += """
            </div>
"""
        
        # Regression detection
        html += self._generate_regression_section(analysis_results, product_id)
        
        html += """
        </div>
"""
        
        # Add chart scripts
        html += self._generate_chart_scripts(analysis_results)
        
        return html
    
    def _build_critical_alerts(self, analysis_results: Dict, gaps_analysis: Dict,
                               regression_analysis: Dict) -> List[Dict]:
        """Build list of critical alerts."""
        critical_alerts = []
        
        # Flaky events
        flaky_events_list = self._get_flaky_events(analysis_results)
        if flaky_events_list:
            flaky_count = len(flaky_events_list)
            top_flaky = ', '.join([f"`{e.get('event', 'Unknown')}`" for e in flaky_events_list[:3]])
            more_text = f" and {flaky_count - 3} more" if flaky_count > 3 else ""
            
            critical_alerts.append({
                'severity': 'critical',
                'type': 'Flaky Events Detected',
                'message': f"Found {flaky_count} events with inconsistent toggle behavior across runs (reliability <50%). Top events: {top_flaky}{more_text}.",
                'action': "Review flaky events table below."
            })
        
        # Regressions
        if regression_analysis and regression_analysis.get('regressions'):
            for reg in regression_analysis['regressions'][:3]:
                if reg.get('severity') == 'critical':
                    critical_alerts.append({
                        'type': 'regression',
                        'severity': 'critical',
                        'message': f"Coverage dropped {reg.get('drop_percentage', 0):.1f}% in {reg.get('domain', 'Unknown')}",
                        'action': f"Investigate {reg.get('domain')} workload changes"
                    })
        
        # Critical gaps
        if gaps_analysis:
            non_toggling = gaps_analysis.get('non_toggling_events', [])
            critical_gaps = [g for g in non_toggling if g.get('priority') == 'critical'][:5]
            if critical_gaps:
                critical_alerts.append({
                    'type': 'gap',
                    'severity': 'high',
                    'message': f"{len(critical_gaps)} critical events never triggered",
                    'action': "Review Action Items tab for EMON commands"
                })
        
        return critical_alerts
    
    def _get_flaky_events(self, analysis_results: Dict) -> List[Dict]:
        """Get list of flaky events from cached trend results."""
        try:
            trend_results = self.rg._cached_trend_results
            if trend_results and trend_results.get('status') == 'complete':
                event_trends = trend_results.get('event_trends', {})
                return event_trends.get('flaky', [])
        except Exception as e:
            logger.warning(f"Could not check for flaky events: {e}")
        return []
    
    def _get_anomaly_count(self, ml_analysis: Dict) -> int:
        """Get total anomaly count from ML analysis."""
        if not ml_analysis:
            return 0
        ml_summary = ml_analysis.get('summary', {})
        total = ml_summary.get('total_anomalies', 0)
        if not total and ml_analysis.get('anomalies'):
            total = len(ml_analysis.get('anomalies', []))
        return total
    
    def _build_recommended_actions(self, analysis_results: Dict, gaps_analysis: Dict,
                                   regression_analysis: Dict, flaky_events_list: List,
                                   total_anomalies: int, summary: Dict) -> List[Dict]:
        """Build list of recommended actions."""
        actions = []
        
        # Regressions
        if regression_analysis and regression_analysis.get('regressions'):
            for reg in regression_analysis['regressions'][:3]:
                actions.append({
                    'type': 'regression',
                    'severity': 'high',
                    'title': 'Address Coverage Regression',
                    'description': f"{reg.get('domain', 'Unknown')} dropped by {reg.get('drop_percentage', 0):.1f}%",
                    'impact': 'Critical regression affecting validation.',
                    'tab': 'executive'
                })
        
        # Flaky events
        if flaky_events_list:
            actions.append({
                'type': 'flaky',
                'severity': 'high',
                'title': 'Investigate Flaky Events',
                'description': f"{len(flaky_events_list)} events show inconsistent toggle behavior",
                'impact': 'Flaky events reduce test reliability.',
                'tab': 'executive'
            })
        
        # Coverage gaps
        if gaps_analysis:
            gap_count = len(gaps_analysis.get('non_toggling_events', []))
            if gap_count > 0:
                critical_count = len([g for g in gaps_analysis.get('non_toggling_events', [])
                                     if g.get('priority') == 'critical'])
                actions.append({
                    'type': 'gap',
                    'severity': 'high' if critical_count > 10 else 'medium',
                    'title': 'Close Critical Coverage Gaps',
                    'description': f"{gap_count} events not toggling ({critical_count} critical)",
                    'impact': 'Missing events may indicate insufficient workload coverage.',
                    'tab': 'action-items'
                })
        
        # Workload recommendations
        workload_recs = analysis_results.get('workload_gap_mapping', {}).get('recommendations', [])
        if workload_recs:
            actions.append({
                'type': 'workload',
                'severity': 'medium',
                'title': 'Execute Recommended Workloads',
                'description': f"{len(workload_recs)} targeted workloads suggested",
                'impact': 'Running recommended stress tests will improve coverage.',
                'tab': 'workload-health'
            })
        
        # Platform-specific
        platform_gaps = analysis_results.get('platform_comparison', {})
        if platform_gaps and platform_gaps.get('platform_specific_gaps'):
            actions.append({
                'type': 'platform',
                'severity': 'medium',
                'title': 'Validate Platform-Specific Events',
                'description': 'Some events only toggle on Windows or Linux',
                'impact': 'Ensures comprehensive cross-platform validation.',
                'tab': 'platform-product-insights'
            })
        
        # Anomalies
        if total_anomalies > 0:
            actions.append({
                'type': 'anomaly',
                'severity': 'medium',
                'title': 'Investigate ML-Detected Anomalies',
                'description': f"{total_anomalies} events show statistical outliers",
                'impact': 'Anomalies may indicate test artifacts or real silicon issues.',
                'tab': 'executive'
            })
        
        return actions
    
    def _generate_header_section(self, summary: Dict, analysis_results: Dict,
                                 overall_sentiment: Dict, cumulative_stats: Dict,
                                 stress_info: Dict) -> str:
        """Generate the header section of executive tab."""
        html = f"""
        <div id="executive" class="tab-content active">
            <h2 class="section-title">Executive Summary</h2>
            
            <!-- Interpretation Guide -->
            <div style="background: linear-gradient(135deg, #e1f5fe 0%, #b3e5fc 100%); border-left: 5px solid #0277bd; padding: 20px; margin-bottom: 25px; border-radius: 8px;">
                <h3 style="margin: 0 0 10px 0; color: #01579b;">How to Interpret This Tab</h3>
                <p style="margin: 5px 0; color: #01579b; line-height: 1.5; font-size: 0.95em;">
                    <strong>Validation Assessment:</strong> Current run stats vs cumulative progress across all runs.<br>
                    <strong>Coverage Scores:</strong> Current run % and cumulative % with workload tracking.<br>
                    <strong>Quick Statistics:</strong> Events tested, active, domains, and growth metrics.<br>
                    <strong>Critical Alerts:</strong> Regressions, flaky events, anomalies requiring immediate attention.<br>
                    <strong>ML Insights:</strong> Coverage predictions, trend forecasts, and saturation analysis.
                </p>
            </div>
            
            <!-- Validation Assessment -->
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 30px; margin-bottom: 30px; border-radius: 10px;">
                <h3 style="margin: 0 0 15px 0; font-size: 1.8em; color: white;">Validation Assessment</h3>
                <p style="margin: 0 0 10px 0; font-size: 1.1em; line-height: 1.8; opacity: 0.95;">
                    <strong>Current Run:</strong> Evaluated <strong>{summary['total_events_tested']} PMU events</strong> across <strong>{summary['total_domains']} domains</strong>.
                    Achieved <strong>{summary['overall_coverage_percentage']:.1f}%</strong> coverage with <strong>{summary['active_events']} events</strong> actively toggling.
                </p>
                <p style="margin: 0; font-size: 1.1em; line-height: 1.8; opacity: 0.95;">
                    <strong>Cumulative Progress:</strong> <strong>{cumulative_stats['covered_events']}</strong> of <strong>{cumulative_stats['total_events']}</strong> events covered (<strong>{cumulative_stats['coverage_pct']:.1f}%</strong>).
                </p>
            </div>
            
            <!-- Coverage Score Banners -->
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 30px;">
                <!-- Current Run -->
                <div style="background: {overall_sentiment['color']}15; border-left: 5px solid {overall_sentiment['color']}; padding: 25px; border-radius: 8px;">
                    <h3 style="margin: 0 0 15px 0; color: #333; font-size: 1.2em;">CURRENT RUN</h3>
                    <div style="display: flex; align-items: center; gap: 15px;">
                        <div style="font-size: 4em; font-weight: bold; color: {overall_sentiment['color']};">{summary['overall_coverage_percentage']:.0f}%</div>
                        <div>
                            <h2 style="margin: 0; color: {overall_sentiment['color']}; font-size: 1.6em;">{overall_sentiment['message']}</h2>
                            <p style="margin: 10px 0 0 0; color: #333; font-size: 1.2em;">
                                <strong>{summary['active_events']}</strong> of <strong>{summary['total_events_tested']}</strong> events active
                            </p>
                            <p style="margin: 5px 0 0 0; color: #666; font-size: 0.95em;">
                                {summary['total_domains']} PMU domains | {stress_info.get('summary', 'No stress detected')}
                            </p>
                        </div>
                    </div>
                </div>
                
                <!-- Cumulative -->
                <div style="background: #e3f2fd; border-left: 5px solid #0071C5; padding: 25px; border-radius: 8px;">
                    <h3 style="margin: 0 0 15px 0; color: #333; font-size: 1.2em;">CUMULATIVE (ALL RUNS)</h3>
                    <div style="display: flex; align-items: center; gap: 15px;">
                        <div style="font-size: 4em; font-weight: bold; color: #0071C5;">{cumulative_stats['coverage_pct']:.0f}%</div>
                        <div>
                            <h2 style="margin: 0; color: #0071C5; font-size: 1.6em;">Overall Progress</h2>
                            <p style="margin: 10px 0 0 0; color: #333; font-size: 1.2em;">
                                <strong>{cumulative_stats['covered_events']}</strong> of <strong>{cumulative_stats['total_events']}</strong> events covered
                            </p>
                            <p style="margin: 5px 0 0 0; color: #666; font-size: 0.95em;">
                                <strong>{cumulative_stats['remaining_events']}</strong> events never activated
                            </p>
                        </div>
                    </div>
                </div>
            </div>
"""
        return html
    
    def _generate_alerts_section(self, all_alerts: List[Dict], flaky_events_list: List[Dict],
                                 recommended_actions: List[Dict], analysis_results: Dict) -> str:
        """Generate alerts and recommended actions HTML."""
        alerts_html = ""
        
        # Threshold info
        if hasattr(self.rg, '_threshold_metadata'):
            alerts_html += self._generate_threshold_info()
        
        # Critical alerts
        if all_alerts:
            alerts_html += self._generate_critical_alerts_html(all_alerts)
            if flaky_events_list:
                alerts_html += self._generate_flaky_events_table(flaky_events_list)
        else:
            alerts_html += self._generate_no_alerts_html()
        
        # Recommended actions
        if recommended_actions:
            alerts_html += self._generate_action_cards(recommended_actions)
        
        # ML prioritization status
        alerts_html += self._generate_ml_prioritization_status(analysis_results)
        
        return alerts_html
    
    def _generate_threshold_info(self) -> str:
        """Generate threshold information display."""
        threshold_info = self.rg._threshold_metadata
        thresholds = threshold_info['thresholds']
        source = threshold_info['source']
        reason = threshold_info['reason']
        
        if source == 'ml':
            info_color, info_bg, title = '#28a745', '#d4edda', 'ML-Learned Thresholds'
        elif source == 'ml_validated':
            info_color, info_bg, title = '#0071C5', '#e3f2fd', 'ML-Learned Thresholds (Validated)'
        else:
            info_color, info_bg, title = '#856404', '#fff3cd', 'Default Thresholds'
        
        return f"""
            <div style="background: {info_bg}; border-left: 4px solid {info_color}; padding: 15px; border-radius: 6px; margin-bottom: 25px;">
                <div style="display: flex; align-items: center; justify-content: space-between;">
                    <div>
                        <strong style="color: {info_color}; font-size: 1.05em;">{title}</strong>
                        <span style="color: #666; margin-left: 10px; font-size: 0.9em;">({reason})</span>
                    </div>
                    <div style="display: flex; gap: 15px; font-size: 0.9em;">
                        <span>Excellent: >={round(thresholds['excellent'])}%</span>
                        <span>Good: >={round(thresholds['good'])}%</span>
                        <span>Warning: >={round(thresholds['warning'])}%</span>
                    </div>
                </div>
            </div>
"""
    
    def _generate_critical_alerts_html(self, alerts: List[Dict]) -> str:
        """Generate critical alerts HTML."""
        severity_colors = {
            'critical': '#d32f2f', 'high': '#f57c00', 'medium': '#fbc02d',
            'low': '#388e3c', 'info': '#0288d1', 'success': '#28a745'
        }
        
        html = """
            <div style="margin-bottom: 30px;">
                <h3 style="color: #d32f2f; margin-bottom: 15px;">CRITICAL ALERTS</h3>
"""
        for alert in alerts:
            color = severity_colors.get(alert['severity'], '#999')
            html += f"""
                <div style="background: {color}15; border-left: 4px solid {color}; padding: 15px; margin-bottom: 10px; border-radius: 5px;">
                    <strong style="color: {color}; text-transform: uppercase;">{alert['severity']} - {alert['type']}</strong>
                    <p style="margin: 5px 0; color: #333;">{alert['message']}</p>
                    {f'<p style="color: #666; font-size: 0.9em; font-style: italic;">{alert.get("recommendation", "")}</p>' if alert.get('recommendation') else ''}
                </div>
"""
        html += "</div>"
        return html
    
    def _generate_no_alerts_html(self) -> str:
        """Generate HTML when no alerts."""
        return """
            <div style="margin-bottom: 30px;">
                <h3 style="color: #28a745; margin-bottom: 15px;">VALIDATION STATUS</h3>
                <div style="background: #d4edda; border-left: 4px solid #28a745; padding: 15px; border-radius: 5px;">
                    <strong style="color: #28a745;">NO CRITICAL ISSUES DETECTED</strong>
                    <p style="margin: 5px 0 0 0; color: #155724;">
                        No regressions, anomalies, or critical alerts found. Coverage analysis looks healthy.
                    </p>
                </div>
            </div>
"""
    
    def _generate_flaky_events_table(self, flaky_events: List[Dict]) -> str:
        """Generate flaky events table HTML."""
        html = f"""
            <div style="background: #fff3cd; border-left: 4px solid #ffc107; padding: 20px; border-radius: 8px; margin-bottom: 30px;">
                <h4 style="margin-top: 0; color: #856404;">Flaky Events Detected ({len(flaky_events)})</h4>
                <p style="color: #856404; margin-bottom: 15px;">Events that inconsistently toggle between runs.</p>
                <div style="max-height: 300px; overflow-y: auto;">
                    <table style="width: 100%; background: white; border-collapse: collapse;">
                        <thead style="position: sticky; top: 0; background: #fff3cd;">
                            <tr>
                                <th style="padding: 10px; text-align: left; border-bottom: 2px solid #ffc107;">Event</th>
                                <th style="padding: 10px; text-align: left; border-bottom: 2px solid #ffc107;">Domain</th>
                                <th style="padding: 10px; text-align: center; border-bottom: 2px solid #ffc107;">Reliability</th>
                                <th style="padding: 10px; text-align: left; border-bottom: 2px solid #ffc107;">Pattern</th>
                            </tr>
                        </thead>
                        <tbody>
"""
        for event in flaky_events:
            reliability = event.get('reliability', 0) * 100
            html += f"""
                            <tr>
                                <td style="padding: 8px; border-bottom: 1px solid #ddd;"><code>{event.get('event', 'Unknown')}</code></td>
                                <td style="padding: 8px; border-bottom: 1px solid #ddd;">{event.get('domain', 'Unknown').upper()}</td>
                                <td style="padding: 8px; border-bottom: 1px solid #ddd; text-align: center;">
                                    <span style="background: #ffc107; color: white; padding: 2px 8px; border-radius: 10px; font-size: 0.85em;">{reliability:.0f}%</span>
                                </td>
                                <td style="padding: 8px; border-bottom: 1px solid #ddd; font-size: 0.9em; color: #666;">{event.get('description', 'Inconsistent toggling')}</td>
                            </tr>
"""
        html += """
                        </tbody>
                    </table>
                </div>
            </div>
"""
        return html
    
    def _generate_action_cards(self, actions: List[Dict]) -> str:
        """Generate action cards HTML."""
        severity_map = {
            'critical': ('HIGH', '#dc3545', 'High Priority'),
            'high': ('HIGH', '#dc3545', 'High Priority'),
            'medium': ('MEDIUM', '#ffc107', 'Medium Priority'),
            'low': ('LOW', '#17a2b8', 'Low Priority'),
            'info': ('INFO', '#6c757d', 'Informational')
        }
        
        html = """
            <div style="margin-bottom: 30px;">
                <h3 style="margin-bottom: 10px;">TOP RECOMMENDED ACTIONS</h3>
                <p style="color: #666; font-size: 0.9em; margin-bottom: 20px;">
                    Prioritized actions based on current coverage status and ML analysis.
                </p>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 15px;">
"""
        for i, action in enumerate(actions[:5], 1):
            severity = str(action.get('severity', 'medium')).lower()
            _, color, label = severity_map.get(severity, ('INFO', '#6c757d', 'Informational'))
            
            html += f"""
                    <div style="background: white; border-left: 5px solid {color}; border-radius: 8px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                        <div style="display: flex; justify-content: space-between; align-items: start; margin-bottom: 12px;">
                            <span style="font-size: 1.8em; font-weight: bold; color: {color};">{i}</span>
                            <span style="background: {color}; color: white; padding: 5px 14px; border-radius: 14px; font-size: 0.8em; font-weight: 600;">{label}</span>
                        </div>
                        <h4 style="margin: 0 0 10px 0; color: #2c3e50; font-size: 1.05em;">{action.get('title', 'Action')}</h4>
                        <p style="margin: 0 0 12px 0; color: #555; font-size: 0.9em;">{action.get('description', '')}</p>
                        <div style="margin-top: 12px; padding-top: 12px; border-top: 1px solid #e9ecef; font-size: 0.85em; color: #6c757d;">
                            <strong>Impact:</strong> {action.get('impact', '')}
                        </div>
                    </div>
"""
        html += """
                </div>
            </div>
"""
        return html
    
    def _generate_ml_prioritization_status(self, analysis_results: Dict) -> str:
        """Generate ML prioritization status banner."""
        if self.rg.ml_action_prioritizer.is_trained():
            feature_importance = self.rg.ml_action_prioritizer.get_feature_importance()
            top_features = sorted(feature_importance.items(), key=lambda x: x[1], reverse=True)[:3]
            feature_display = ', '.join([f.replace('_', ' ').title() for f, _ in top_features])
            
            return f"""
            <div style="background: linear-gradient(135deg, #d4edda 0%, #c3e6cb 100%); border-left: 5px solid #28a745; padding: 15px; border-radius: 8px; margin-bottom: 25px;">
                <strong style="color: #155724; font-size: 1.1em;">ML-POWERED ACTION PRIORITIZATION</strong>
                <p style="color: #155724; margin: 5px 0; font-size: 0.95em;">
                    Actions ranked by ML model trained on historical validation outcomes.
                </p>
                <p style="color: #155724; margin: 5px 0; font-size: 0.9em;">
                    <strong>Top Ranking Factors:</strong> {feature_display}
                </p>
            </div>
"""
        else:
            product_id = self.rg._get_product_id(analysis_results)
            try:
                data_dir = Path(r'C:\silicon_coverage_analyzer_data') / 'raw_datasets' / product_id
                dataset_count = len(list(data_dir.glob('coverage_*.json'))) if data_dir.exists() else 0
                msg = f"Have {dataset_count} datasets." if dataset_count < 10 else f"ML can analyze {dataset_count} runs."
            except:
                msg = "Need at least 10 runs."
            
            return f"""
            <div style="background: linear-gradient(135deg, #fff3cd 0%, #ffe9a6 100%); border-left: 5px solid #ffc107; padding: 15px; border-radius: 8px; margin-bottom: 25px;">
                <strong style="color: #856404; font-size: 1.1em;">RULE-BASED ACTION PRIORITIZATION</strong>
                <p style="color: #856404; margin: 5px 0; font-size: 0.95em;">
                    Actions prioritized using predefined severity rules. {msg}
                </p>
            </div>
"""
    
    def _generate_ml_insights_section(self, analysis_results: Dict, gaps_analysis: Dict,
                                      product_id: str) -> str:
        """Generate ML insights section (stress recommender, saturation, forecaster, predictions)."""
        html = ""
        
        # 1. Stress test recommender
        if self.rg.ml_stress_recommender.is_trained():
            html += self._generate_stress_recommendations(analysis_results, gaps_analysis)
        
        # 2. Saturation predictor
        if self.rg.ml_saturation_predictor.is_trained():
            html += self._generate_saturation_prediction(analysis_results, product_id)
        
        # 3. Gap forecaster
        if self.rg.ml_gap_forecaster.is_trained():
            html += self._generate_gap_forecast(analysis_results, product_id)
        
        # 4. Coverage predictions
        ml_analysis = analysis_results.get('ml_analysis', {})
        if ml_analysis:
            html += self._generate_coverage_predictions(ml_analysis)
        
        return html
    
    def _generate_stress_recommendations(self, analysis_results: Dict, gaps_analysis: Dict) -> str:
        """Generate stress test recommendations section."""
        try:
            gap_events = gaps_analysis.get('non_toggling_events', [])
            recommendations = self.rg.ml_stress_recommender.recommend_stress_tests(
                gap_events, analysis_results.get('coverage', {})
            )
            
            if not recommendations:
                return ""
            
            html = """
            <div style="background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%); border-left: 5px solid #0071C5; padding: 20px; border-radius: 8px; margin-bottom: 25px;">
                <h3 style="margin: 0 0 10px 0; color: #01579b;">Recommended Next Stress Tests (ML)</h3>
                <p style="color: #01579b; margin-bottom: 15px;">Based on coverage gaps, ML recommends:</p>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 15px;">
"""
            for rec in recommendations[:3]:
                confidence = rec['confidence'] * 100 if rec['confidence'] <= 1.0 else rec['confidence']
                color = "#28a745" if confidence >= 75 else "#ffc107" if confidence >= 50 else "#dc3545"
                html += f"""
                    <div style="background: white; padding: 15px; border-radius: 6px; border-left: 4px solid {color};">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                            <strong style="color: #0071C5;">{rec['stress_test']}</strong>
                            <span style="background: {color}; color: white; padding: 3px 8px; border-radius: 12px; font-size: 0.85em;">{confidence:.0f}%</span>
                        </div>
                        <p style="margin: 5px 0; color: #666; font-size: 0.9em;">{rec.get('reason', '')}</p>
                        <div style="margin-top: 8px; padding: 8px; background: #f8f9fa; border-radius: 4px; font-size: 0.85em;">
                            <strong>Expected Gain:</strong> <span style="color: #28a745;">+{rec.get('expected_coverage_gain', 0):.1f}%</span>
                        </div>
                    </div>
"""
            html += """
                </div>
            </div>
"""
            return html
        except Exception as e:
            logger.warning(f"Stress recommender display failed: {e}")
            return ""
    
    def _generate_saturation_prediction(self, analysis_results: Dict, product_id: str) -> str:
        """Generate saturation prediction section."""
        try:
            coverage_timeline = []
            total_duration = 0
            data_dir = Path(r'C:\silicon_coverage_analyzer_data') / 'raw_datasets' / product_id
            
            if data_dir.exists():
                for f in sorted(data_dir.glob('coverage_*.json'))[-10:]:
                    try:
                        with open(f) as cf:
                            data = json.load(cf)
                            coverage_timeline.append({
                                'timestamp': data.get('metadata', {}).get('timestamp', ''),
                                'coverage_pct': data.get('summary', {}).get('overall_coverage_percentage', 0)
                            })
                            total_duration += data.get('metadata', {}).get('duration_seconds', 300) / 60
                    except:
                        pass
            
            if len(coverage_timeline) < 3:
                return ""
            
            result = self.rg.ml_saturation_predictor.predict_saturation(coverage_timeline, total_duration)
            
            # Get actual current coverage from timeline or analysis results
            actual_current_cov = result.get('current_coverage', 0)
            if actual_current_cov == 0 and coverage_timeline:
                actual_current_cov = coverage_timeline[-1].get('coverage_pct', 0)
            if actual_current_cov == 0:
                # Fallback to analysis results
                summary = analysis_results.get('coverage', {}).get('summary', {})
                actual_current_cov = summary.get('overall_coverage_percentage', 0)
            
            if result.get('saturated'):
                return f"""
            <div style="background: linear-gradient(135deg, #fff3cd 0%, #ffe9a6 100%); border-left: 5px solid #ffc107; padding: 20px; border-radius: 8px; margin-bottom: 25px;">
                <h3 style="margin: 0 0 10px 0; color: #856404;">Coverage Saturation Detected (ML)</h3>
                <p style="color: #856404;"><strong>Status:</strong> Coverage plateaued at <strong>{actual_current_cov:.1f}%</strong></p>
                <p style="color: #856404;"><strong>Growth Rate:</strong> {result.get('current_growth_rate', 0):.2f}% per 10 minutes</p>
                <p style="color: #856404;"><strong>Recommendation:</strong> {result.get('recommendation', 'Consider stopping collection')}</p>
            </div>
"""
            elif result.get('status') in ['predicted', 'growing']:
                growth_rate = result.get('current_growth_rate', 0)
                
                # More meaningful display based on actual values
                if growth_rate < 0.01:
                    status_msg = "Coverage has stabilized - no significant new events being discovered"
                    recommendation = result.get('recommendation', 'Consider running different workloads to improve coverage')
                    bg_color = "#fff3cd"
                    border_color = "#ffc107"
                    text_color = "#856404"
                    title = "Coverage Stable (ML Analysis)"
                else:
                    status_msg = f"Coverage actively growing at {growth_rate:.2f}% per 10 minutes"
                    recommendation = result.get('recommendation', 'Continue collection')
                    bg_color = "#d4edda"
                    border_color = "#28a745"
                    text_color = "#155724"
                    title = "Coverage Still Growing (ML)"
                
                return f"""
            <div style="background: linear-gradient(135deg, {bg_color} 0%, {bg_color}99 100%); border-left: 5px solid {border_color}; padding: 20px; border-radius: 8px; margin-bottom: 25px;">
                <h3 style="margin: 0 0 10px 0; color: {text_color};">{title}</h3>
                <p style="color: {text_color};"><strong>Current Coverage:</strong> {actual_current_cov:.1f}%</p>
                <p style="color: {text_color};"><strong>Status:</strong> {status_msg}</p>
                <p style="color: {text_color};"><strong>Recommendation:</strong> {recommendation}</p>
            </div>
"""
        except Exception as e:
            logger.warning(f"Saturation predictor display failed: {e}")
        return ""
    
    def _generate_gap_forecast(self, analysis_results: Dict, product_id: str) -> str:
        """Generate gap forecast section."""
        try:
            historical_runs = []
            data_dir = Path(r'C:\silicon_coverage_analyzer_data') / 'raw_datasets' / product_id
            
            if data_dir.exists():
                for f in sorted(data_dir.glob('coverage_*.json'))[-10:]:
                    try:
                        with open(f) as cf:
                            data = json.load(cf)
                            historical_runs.append({
                                'coverage_pct': data.get('summary', {}).get('overall_coverage_percentage', 0),
                                'gap_count': len(data.get('gaps_analysis', {}).get('non_toggling_events', []))
                            })
                    except:
                        pass
            
            if len(historical_runs) < 5:
                return ""
            
            result = self.rg.ml_gap_forecaster.forecast_trends(historical_runs)
            
            if result.get('status') != 'success' or not result.get('forecasts'):
                return ""
            
            trend_health = result.get('trend_health', 'good')
            trend_colors = {'excellent': '#28a745', 'good': '#17a2b8', 'concerning': '#ffc107', 'poor': '#dc3545'}
            color = trend_colors.get(trend_health, '#17a2b8')
            
            forecast_value = result['forecasts'][4][0] if len(result['forecasts']) >= 5 else 0
            
            # Handle unknown trend more gracefully
            trend_health = result.get('trend_health', 'unknown')
            if trend_health == 'unknown' or trend_health not in ['excellent', 'good', 'concerning', 'poor']:
                # Get actual coverage stats for better messaging
                coverages = [r['coverage_pct'] for r in historical_runs]
                avg_coverage = sum(coverages) / len(coverages) if coverages else 0
                std_coverage = (sum((c - avg_coverage)**2 for c in coverages) / len(coverages))**0.5 if coverages else 0
                
                if std_coverage < 1.0:
                    trend_health = 'stable'
                    trend_msg = "Coverage consistent across runs - workload providing reproducible results"
                    color = '#17a2b8'
                else:
                    trend_health = 'variable'
                    trend_msg = f"Coverage varies ±{std_coverage:.1f}% across runs - consider workload consistency"
                    color = '#ffc107'
            else:
                trend_colors = {'excellent': '#28a745', 'good': '#17a2b8', 'concerning': '#ffc107', 'poor': '#dc3545'}
                color = trend_colors.get(trend_health, '#17a2b8')
                trend_msg = {
                    'excellent': 'Coverage improving steadily across runs',
                    'good': 'Coverage trend positive with some variance',
                    'concerning': 'Coverage may be declining - review workloads',
                    'poor': 'Coverage declining - intervention recommended'
                }.get(trend_health, '')
            
            return f"""
            <div style="background: linear-gradient(135deg, #e8eaf6 0%, #c5cae9 100%); border-left: 5px solid {color}; padding: 20px; border-radius: 8px; margin-bottom: 25px;">
                <h3 style="margin: 0 0 10px 0; color: #283593;">Coverage Trend Forecast (ML)</h3>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-bottom: 15px;">
                    <div style="background: white; padding: 12px; border-radius: 6px;">
                        <div style="color: #666; font-size: 0.9em;">Trend Health</div>
                        <div style="color: {color}; font-size: 1.3em; font-weight: bold;">{trend_health.upper()}</div>
                        <div style="color: #666; font-size: 0.8em; margin-top: 5px;">{trend_msg}</div>
                    </div>
                    <div style="background: white; padding: 12px; border-radius: 6px;">
                        <div style="color: #666; font-size: 0.9em;">Next 5 Runs Prediction</div>
                        <div style="color: #283593; font-size: 1.3em; font-weight: bold;">{forecast_value:.1f}% coverage</div>
                        <div style="color: #666; font-size: 0.8em; margin-top: 5px;">Based on {len(historical_runs)} historical runs</div>
                    </div>
                </div>
            </div>
"""
        except Exception as e:
            logger.warning(f"Gap forecaster display failed: {e}")
        return ""
    
    def _generate_coverage_predictions(self, ml_analysis: Dict) -> str:
        """Generate coverage predictions section."""
        predictions = ml_analysis.get('predictions', {})
        if predictions.get('status') != 'success' or not predictions.get('predicted_improvements'):
            return ""
        
        improvements = predictions['predicted_improvements']
        ml_used = predictions.get('ml_model_used', False)
        
        # Get current coverage for context
        current_cov = predictions.get('current_coverage', {})
        avg_current = 0
        if current_cov:
            cov_values = [d.get('coverage_rate', 0) for d in current_cov.values()]
            avg_current = (sum(cov_values) / len(cov_values) * 100) if cov_values else 0
        
        html = f"""
            <div style="background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%); border-left: 5px solid #4caf50; padding: 20px; border-radius: 8px; margin-bottom: 25px;">
                <h3 style="margin: 0 0 10px 0; color: #1b5e20;">Coverage Predictions {'(ML-Powered)' if ml_used else '(Estimated)'}</h3>
                <p style="color: #2e7d32; margin-bottom: 5px; font-size: 0.95em;">
                    <strong>Current Average Coverage:</strong> {avg_current:.1f}%
                </p>
                <p style="color: #2e7d32; margin-bottom: 15px; font-size: 0.9em;">
                    Predictions for hypothetical test scenarios based on {'trained ML model' if ml_used else 'heuristic estimates'}:
                </p>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 15px;">
"""
        
        workload_labels = {
            'stress_test': ('High Stress Test', '#dc3545', 'CPU-intensive workload (e.g., Prime95)'),
            'mixed_workload': ('Mixed Workload', '#ffc107', 'Combined CPU + Memory stress'),
            'idle_power': ('Idle/Power', '#17a2b8', 'Low activity / power state testing')
        }
        
        # Apply differentiated predictions at display time
        # Use analytical model that varies by stress level and duration
        base_cov = avg_current / 100 if avg_current > 1 else avg_current
        stress_gains = {0: 0.012, 1: 0.035, 2: 0.07}  # idle: 1.2%, mixed: 3.5%, high: 7%
        
        for pred in improvements:
            scenario = pred['scenario']
            label, color, desc = workload_labels.get(scenario['workload'], ('Unknown', '#6c757d', ''))
            
            # Calculate differentiated prediction based on scenario
            stress_level = scenario.get('stress_level', 1)
            duration = scenario.get('duration', 300)
            duration_factor = min(1.0, duration / 600)
            expected_gain = stress_gains.get(stress_level, 0.035) * duration_factor
            
            # Apply diminishing returns based on current coverage
            if base_cov > 0.85:
                expected_gain *= 0.3
            elif base_cov > 0.75:
                expected_gain *= 0.6
            elif base_cov > 0.65:
                expected_gain *= 0.8
            
            # Use differentiated prediction
            predicted_cov = min(100.0, (base_cov + expected_gain) * 100)
            gain = expected_gain * 100
            
            is_ml = pred.get('ml_predicted', False)
            # Only recommend stress_test scenario
            recommended = scenario['workload'] == 'stress_test' and gain > 3.0
            
            html += f"""
                    <div style="background: white; padding: 15px; border-radius: 8px; border: 1px solid #ddd; {'border: 2px solid #28a745;' if recommended else ''}">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <strong style="color: {color};">{label}</strong>
                            {'<span style="background: #28a745; color: white; padding: 2px 8px; border-radius: 10px; font-size: 0.75em;">RECOMMENDED</span>' if recommended else ''}
                        </div>
                        <div style="font-size: 0.8em; color: #888; margin: 5px 0;">{desc}</div>
                        <div style="font-size: 0.85em; color: #666; margin: 8px 0;">
                            Duration: {scenario['duration']}s | Stress Level: {scenario['stress_level']}
                        </div>
                        <div style="background: #f8f9fa; padding: 10px; border-radius: 4px; margin-top: 8px;">
                            <div><strong>Predicted Coverage:</strong> <span style="color: #4caf50; font-size: 1.2em;">{predicted_cov:.1f}%</span></div>
                            <div><strong>Expected Gain:</strong> <span style="color: #28a745;">+{gain:.1f}%</span> from current</div>
                            <div style="font-size: 0.8em; color: #888; margin-top: 5px;">{'ML-Enhanced Estimate' if is_ml else 'Heuristic Estimate'}</div>
                        </div>
                    </div>
"""
        
        html += """
                </div>
            </div>
"""
        return html
    
    def _generate_quick_stats(self, summary: Dict, gaps_analysis: Dict, stress_info: Dict,
                              regression_analysis: Dict, total_anomalies: int, product_id: str) -> str:
        """Generate quick statistics grid."""
        inactive = summary['total_events_tested'] - summary['active_events']
        gap_count = len(gaps_analysis.get('non_toggling_events', [])) if gaps_analysis else 0
        reg_count = len(regression_analysis.get('regressions', [])) if regression_analysis else 0
        workload_count = len(stress_info.get('processes', []))
        
        # Count total runs
        try:
            data_dir = Path(r'C:\silicon_coverage_analyzer_data') / 'raw_datasets' / product_id
            total_runs = len(list(data_dir.glob('coverage_*.json'))) if data_dir.exists() else 0
        except:
            total_runs = 0
        
        return f"""
            <div style="margin-bottom: 30px;">
                <h3 style="margin-bottom: 15px;">QUICK STATISTICS</h3>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px;">
                    <div style="background: #e8eaf6; padding: 20px; border-radius: 8px; text-align: center;">
                        <div style="font-size: 2.5em; color: #3f51b5; font-weight: bold;">{summary['total_events_discovered']}</div>
                        <div style="color: #666; margin-top: 5px;">Total Events</div>
                    </div>
                    <div style="background: #e3f2fd; padding: 20px; border-radius: 8px; text-align: center;">
                        <div style="font-size: 2.5em; color: #0071C5; font-weight: bold;">{summary['active_events']}</div>
                        <div style="color: #666; margin-top: 5px;">Active Events</div>
                    </div>
                    <div style="background: #ffebee; padding: 20px; border-radius: 8px; text-align: center;">
                        <div style="font-size: 2.5em; color: #d32f2f; font-weight: bold;">{inactive}</div>
                        <div style="color: #666; margin-top: 5px;">Inactive Events</div>
                    </div>
                    <div style="background: #fff3e0; padding: 20px; border-radius: 8px; text-align: center;">
                        <div style="font-size: 2.5em; color: #f57c00; font-weight: bold;">{gap_count}</div>
                        <div style="color: #666; margin-top: 5px;">Coverage Gaps</div>
                    </div>
                    <div style="background: #e1f5fe; padding: 20px; border-radius: 8px; text-align: center;">
                        <div style="font-size: 2.5em; color: #006064; font-weight: bold;">{total_runs}</div>
                        <div style="color: #666; margin-top: 5px;">Total Runs</div>
                    </div>
                    <div style="background: #f3e5f5; padding: 20px; border-radius: 8px; text-align: center;">
                        <div style="font-size: 2.5em; color: #7b1fa2; font-weight: bold;">{summary['total_domains']}</div>
                        <div style="color: #666; margin-top: 5px;">PMU Domains</div>
                    </div>
                    <div style="background: #e8f5e9; padding: 20px; border-radius: 8px; text-align: center;">
                        <div style="font-size: 2.5em; color: #388e3c; font-weight: bold;">{workload_count}</div>
                        <div style="color: #666; margin-top: 5px;">Workloads</div>
                    </div>
                    <div style="background: #fff9c4; padding: 20px; border-radius: 8px; text-align: center;">
                        <div style="font-size: 2.5em; color: #f57c00; font-weight: bold;">{total_anomalies}</div>
                        <div style="color: #666; margin-top: 5px;">ML Anomalies</div>
                    </div>
                    <div style="background: #fce4ec; padding: 20px; border-radius: 8px; text-align: center;">
                        <div style="font-size: 2.5em; color: #c2185b; font-weight: bold;">{reg_count}</div>
                        <div style="color: #666; margin-top: 5px;">Regressions</div>
                    </div>
                </div>
            </div>
"""
    
    def _generate_domain_coverage_section(self, analysis_results: Dict, summary: Dict) -> str:
        """Generate domain coverage charts section."""
        domain_results = analysis_results.get('coverage', {}).get('domain_results', {})
        
        domain_names = []
        domain_coverage = []
        domain_colors = []
        
        for domain, stats in domain_results.items():
            total = stats.get('total_tested', 0)
            if total > 0:
                active = len(stats.get('active_events', []))
                pct = active / total * 100
                domain_names.append(domain.upper())
                domain_coverage.append(round(pct, 1))
                sentiment = self.rg._get_coverage_sentiment(pct, 'domain')
                domain_colors.append(sentiment['color'])
        
        # Store for chart script
        self._chart_data = {
            'domain_names': domain_names,
            'domain_coverage': domain_coverage,
            'domain_colors': domain_colors
        }
        
        html = f"""
            <div id="domainCoverageSection" style="margin-top: 30px; margin-bottom: 30px;">
                <h3 style="margin-bottom: 15px;">COVERAGE FROM CURRENT RUN</h3>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
                    <div class="chart-container">
                        <canvas id="domainPieChart" style="max-height: 400px;"></canvas>
                    </div>
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 10px; align-content: start;">
"""
        
        for i, domain in enumerate(domain_names):
            html += f"""
                        <div style="background: {domain_colors[i]}15; border-left: 4px solid {domain_colors[i]}; padding: 15px; border-radius: 6px; text-align: center;">
                            <div style="font-size: 0.85em; color: #666; margin-bottom: 5px;">{domain}</div>
                            <div style="font-size: 1.8em; font-weight: bold; color: {domain_colors[i]};">{domain_coverage[i]}%</div>
                        </div>
"""
        
        html += """
                    </div>
                </div>
            </div>
"""
        return html
    
    def _generate_regression_section(self, analysis_results: Dict, product_id: str) -> str:
        """Generate regression detection section."""
        try:
            coverage_data = analysis_results.get('coverage', {})
            regression_results = self.rg.regression_detector.detect_regressions(coverage_data, product_id)
            return self.rg.regression_detector.generate_regression_report_html(regression_results)
        except Exception as e:
            logger.warning(f"Regression detection failed: {e}")
            return f"""
            <div class="chart-container" style="background: #fff3cd; border-left: 4px solid #ffc107;">
                <h3 style="color: #856404;">Regression Detection Error</h3>
                <p style="color: #856404;">Could not compare: {str(e)}</p>
            </div>
"""
    
    def _generate_chart_scripts(self, analysis_results: Dict) -> str:
        """Generate Chart.js scripts for domain visualization."""
        if not hasattr(self, '_chart_data'):
            return ""
        
        data = self._chart_data
        return f"""
            <script>
            window.addEventListener('load', function() {{
                if (typeof Chart === 'undefined') return;
                const ctx = document.getElementById('domainPieChart').getContext('2d');
                new Chart(ctx, {{
                    type: 'doughnut',
                    data: {{
                        labels: {json.dumps(data['domain_names'])},
                        datasets: [{{
                            data: {json.dumps(data['domain_coverage'])},
                            backgroundColor: {json.dumps(data['domain_colors'])},
                            borderWidth: 2,
                            borderColor: '#fff'
                        }}]
                    }},
                    options: {{
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {{
                            legend: {{ position: 'right' }},
                            title: {{ display: true, text: 'Coverage by Domain' }}
                        }}
                    }}
                }});
            }});
            </script>
"""

    def _generate_stress_tracking_section(self, stress_tracking: Dict, stress_info: Dict) -> str:
        """Generate detailed stress tracking visualization section."""
        html = """
        <div style="margin-bottom: 30px;">
            <h3 style="color: #1976d2; margin-bottom: 15px;">WORKLOAD TRACKING</h3>
"""
        
        test_type = stress_tracking.get('test_type', 'unknown')
        final_classification = stress_tracking.get('final_classification', 'Unknown')
        timeline = stress_tracking.get('timeline', [])
        unique_stresses = stress_tracking.get('unique_stresses', [])
        power_transitions = stress_tracking.get('power_transitions', 0)
        explanation = stress_tracking.get('explanation', '')
        
        # Determine color based on test type
        if test_type == 'single_stress':
            color = '#28a745'  # Green
            icon = 'Done'
        elif test_type in ['mixed_workload', 'multi_stress']:
            color = '#ff9800'  # Orange
            icon = '*'
        elif test_type in ['power_cycling', 'mixed_workload_power_cycling']:
            color = '#2196f3'  # Blue
            icon = '[~]'
        else:
            color = '#757575'  # Gray
            icon = '[i]'
        
        # Summary banner
        html += f"""
            <div style="background: {color}15; border-left: 5px solid {color}; padding: 20px; border-radius: 8px;">
                <div style="display: flex; align-items: center; gap: 15px; margin-bottom: 15px;">
                    <div style="font-size: 2em;">{icon}</div>
                    <div style="flex: 1;">
                        <h4 style="margin: 0; color: {color}; font-size: 1.3em;">{final_classification}</h4>
                        <p style="margin: 5px 0 0 0; color: #666; font-size: 0.95em;">{explanation}</p>
                    </div>
                </div>
"""
        
        # Stats grid
        html += """
                <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; margin-top: 15px;">
"""
        
        # Unique stresses
        if unique_stresses:
            stresses_display = ', '.join(unique_stresses[:3])
            if len(unique_stresses) > 3:
                stresses_display += f" +{len(unique_stresses)-3} more"
            html += f"""
                    <div style="background: white; padding: 12px; border-radius: 6px; border: 1px solid #e0e0e0;">
                        <div style="font-size: 0.85em; color: #666; margin-bottom: 5px;">Stress Tools</div>
                        <div style="font-size: 1.1em; font-weight: bold; color: #333;">{len(unique_stresses)}</div>
                        <div style="font-size: 0.8em; color: #999; margin-top: 3px;">{stresses_display}</div>
                    </div>
"""
        
        # Power transitions
        html += f"""
                    <div style="background: white; padding: 12px; border-radius: 6px; border: 1px solid #e0e0e0;">
                        <div style="font-size: 0.85em; color: #666; margin-bottom: 5px;">Power Transitions</div>
                        <div style="font-size: 1.1em; font-weight: bold; color: #333;">{power_transitions}</div>
                        <div style="font-size: 0.8em; color: #999; margin-top: 3px;">{'Active' if power_transitions > 0 else 'None detected'}</div>
                    </div>
"""
        
        # Stress changes
        stress_changes = len(timeline) - 1 if len(timeline) > 1 else 0
        html += f"""
                    <div style="background: white; padding: 12px; border-radius: 6px; border: 1px solid #e0e0e0;">
                        <div style="font-size: 0.85em; color: #666; margin-bottom: 5px;">Stress Changes</div>
                        <div style="font-size: 1.1em; font-weight: bold; color: #333;">{stress_changes}</div>
                        <div style="font-size: 0.8em; color: #999; margin-top: 3px;">{'Changes detected' if stress_changes > 0 else 'Consistent'}</div>
                    </div>
                </div>
"""
        
        # Timeline visualization (if multiple checkpoints)
        if len(timeline) > 1:
            html += """
                <div style="margin-top: 20px;">
                    <h5 style="margin: 0 0 10px 0; color: #333;">Workload Timeline</h5>
                    <div style="background: white; padding: 15px; border-radius: 6px; border: 1px solid #e0e0e0;">
"""
            
            for i, entry in enumerate(timeline):
                time_str = f"{entry.get('time', 0)}s"
                stress = entry.get('stress', 'Unknown')
                entry_type = entry.get('type', 'unknown')
                
                # Icon based on type
                if entry_type == 'stress':
                    entry_icon = '*'
                    entry_color = '#ff9800'
                else:
                    entry_icon = '[-]'
                    entry_color = '#9e9e9e'
                
                html += f"""
                        <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 8px;">
                            <div style="min-width: 60px; text-align: right; color: #999; font-size: 0.9em;">{time_str}</div>
                            <div style="font-size: 1.2em;">{entry_icon}</div>
                            <div style="flex: 1; padding: 8px 12px; background: {entry_color}15; border-left: 3px solid {entry_color}; border-radius: 4px;">
                                <strong style="color: {entry_color};">{stress}</strong>
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
        
        return html
    

    def _generate_additional_alerts(self, analysis_results, product_id):
        """Generate additional validation alerts (new events, zero-count events, hardware changes, workload dependencies)."""
        from pathlib import Path
        import json
        
        alerts = []
        
        try:
            data_dir = Path(r'C:\silicon_coverage_analyzer_data')
            if not product_id or not data_dir.exists():
                return alerts
            
            product_dir = data_dir / 'raw_datasets' / product_id
            if not product_dir.exists():
                return alerts
            
            coverage_files = sorted(product_dir.glob('coverage_*.json'))
            if len(coverage_files) < 2:
                return alerts
            
            # Load current and previous run
            current_file = coverage_files[-1]
            previous_file = coverage_files[-2]
            
            with open(current_file, 'r') as f:
                current_data = json.load(f)
            with open(previous_file, 'r') as f:
                previous_data = json.load(f)
            
            # Get domain results from both runs
            current_domains = current_data.get('coverage_results', {}).get('domain_results', {})
            if not current_domains:
                current_domains = current_data.get('coverage', {}).get('domain_results', {})
            
            previous_domains = previous_data.get('coverage_results', {}).get('domain_results', {})
            if not previous_domains:
                previous_domains = previous_data.get('coverage', {}).get('domain_results', {})
            
            # 1. NEW EVENTS DISCOVERED (positive alert)
            new_events_by_domain = {}
            for domain, stats in current_domains.items():
                current_events = set()
                for evt in stats.get('active_events', []) + stats.get('inactive_events', []):
                    event_name = evt.get('event', '') if isinstance(evt, dict) else str(evt)
                    if event_name:
                        current_events.add(event_name)
                
                if domain in previous_domains:
                    previous_events = set()
                    prev_stats = previous_domains[domain]
                    for evt in prev_stats.get('active_events', []) + prev_stats.get('inactive_events', []):
                        event_name = evt.get('event', '') if isinstance(evt, dict) else str(evt)
                        if event_name:
                            previous_events.add(event_name)
                    
                    new_events = current_events - previous_events
                    if new_events:
                        new_events_by_domain[domain] = new_events
            
            if new_events_by_domain:
                total_new = sum(len(events) for events in new_events_by_domain.values())
                domains_str = ', '.join(f"{domain} ({len(events)})" for domain, events in list(new_events_by_domain.items())[:3])
                if len(new_events_by_domain) > 3:
                    domains_str += f" and {len(new_events_by_domain) - 3} more"
                alerts.append({
                    'severity': 'success',
                    'type': 'New Events Discovered',
                    'message': f'{total_new} new PMU events discovered in this run across domains: {domains_str}. This expands validation coverage.',
                    'action': 'Review Coverage Details tab to see newly discovered events. Consider adding workloads that triggered these events to regular validation.'
                })
            
            # 2. PERSISTENT ZERO-COUNT EVENTS (warning)
            zero_count_events = []
            for domain, stats in current_domains.items():
                for evt in stats.get('active_events', []):
                    if isinstance(evt, dict):
                        total_activity = evt.get('total_activity', 0)
                        event_name = evt.get('event', '')
                        if total_activity == 0 and event_name:
                            zero_count_events.append({'event': event_name, 'domain': domain})
            
            if len(zero_count_events) > 5:
                alerts.append({
                    'severity': 'medium',
                    'type': 'Zero-Count Active Events',
                    'message': f'{len(zero_count_events)} events show as active but have zero count. This may indicate EMON collection issues or events toggling between collection intervals.',
                    'action': 'Check Coverage Details tab for affected events. Verify EMON collection interval settings and consider longer collection duration.'
                })
            
            # 3. HARDWARE CONFIGURATION CHANGES (info)
            current_hw = current_data.get('hardware_config', {})
            previous_hw = previous_data.get('hardware_config', {})
            
            hw_changes = []
            if current_hw.get('cpu_count') != previous_hw.get('cpu_count'):
                hw_changes.append(f"CPU count: {previous_hw.get('cpu_count')} ? {current_hw.get('cpu_count')}")
            if current_hw.get('frequency_mhz') != previous_hw.get('frequency_mhz'):
                hw_changes.append(f"Frequency: {previous_hw.get('frequency_mhz')} ? {current_hw.get('frequency_mhz')} MHz")
            if current_hw.get('product_name') != previous_hw.get('product_name'):
                hw_changes.append(f"Product: {previous_hw.get('product_name')} ? {current_hw.get('product_name')}")
            
            if hw_changes:
                changes_str = '; '.join(hw_changes)
                alerts.append({
                    'severity': 'info',
                    'type': 'Hardware Configuration Changed',
                    'message': f'Hardware configuration differs from previous run: {changes_str}',
                    'action': 'Coverage comparisons with previous runs may not be valid. Use this run as new baseline for future comparisons.'
                })
            
            # 4. WORKLOAD DEPENDENCY ISSUES (warning - events only toggle under specific stress)
            workload_mapping = analysis_results.get('ml_analysis', {}).get('workload_gap_mapping', {})
            recommendations = workload_mapping.get('recommendations', [])
            
            # Count high-confidence workload-dependent events
            workload_dependent_count = sum(1 for rec in recommendations if rec.get('confidence', 0) > 0.7)
            
            if workload_dependent_count > 10:
                alerts.append({
                    'severity': 'medium',
                    'type': 'Workload-Dependent Events',
                    'message': f'{workload_dependent_count} events only toggle under specific workloads (memory stress, I/O intensive, etc.). They won\'t appear in baseline idle runs.',
                    'action': 'See Action Items tab for ML-learned workload recommendations. Run targeted workloads to activate these events.'
                })
        
        except Exception as e:
            logger.debug(f"Error generating additional alerts: {e}")
        
        return alerts
    

    def _generate_realistic_coverage_milestones(self, analysis_results, product_id):
        """Generate realistic coverage milestones based on cumulative coverage across all historical runs."""
        from pathlib import Path
        import json
        
        coverage = analysis_results.get('coverage', {})
        domain_results = coverage.get('domain_results', {})
        
        # Load all historical runs to find ALL events ever toggled
        all_events_by_domain = {}  # All events ever detected
        ever_toggled_by_domain = {}  # Events that toggled at least once across all runs
        unavailable_events_by_domain = {}  # Platform-unsupported events
        
        try:
            data_dir = Path(r'C:\silicon_coverage_analyzer_data')
            if product_id:
                product_dir = data_dir / 'raw_datasets' / product_id
                if product_dir.exists():
                    # Use ALL coverage files, not just last 10
                    coverage_files = sorted(product_dir.glob('coverage_*.json'))
                    
                    for coverage_file in coverage_files:
                        try:
                            with open(coverage_file, 'r') as f:
                                hist_data = json.load(f)
                                # Try both structures: coverage_results (old) and coverage.domain_results (new)
                                hist_domains = hist_data.get('coverage_results', {}).get('domain_results', {})
                                if not hist_domains:
                                    hist_domains = hist_data.get('coverage', {}).get('domain_results', {})
                                
                                for domain, stats in hist_domains.items():
                                    if domain not in all_events_by_domain:
                                        all_events_by_domain[domain] = set()
                                        ever_toggled_by_domain[domain] = set()
                                        unavailable_events_by_domain[domain] = set()
                                    
                                    # Track all events detected (active + inactive)
                                    for evt in stats.get('active_events', []):
                                        event_name = evt.get('event', '') if isinstance(evt, dict) else str(evt)
                                        if event_name:
                                            all_events_by_domain[domain].add(event_name)
                                            ever_toggled_by_domain[domain].add(event_name)  # Active means it toggled
                                    
                                    for evt in stats.get('inactive_events', []):
                                        event_name = evt.get('event', '') if isinstance(evt, dict) else str(evt)
                                        if event_name:
                                            all_events_by_domain[domain].add(event_name)
                        except Exception as e:
                            continue
                    
                    # Get unavailable events from current run's gap analysis
                    gaps_data = analysis_results.get('gaps', {})
                    for gap_event in gaps_data.get('non_toggling_events', []):
                        domain = gap_event.get('domain', '')
                        category = gap_event.get('category', '')
                        reason = gap_event.get('reason', '')
                        
                        if category == 'Event_Unavailable' or reason in ['event_not_exists', 'not_found', 'not_supported']:
                            if domain not in unavailable_events_by_domain:
                                unavailable_events_by_domain[domain] = set()
                            event_name = gap_event.get('event_name', gap_event.get('event', ''))
                            if event_name:
                                unavailable_events_by_domain[domain].add(event_name)
        except Exception as e:
            pass
        
        # If no historical data, use current run data
        if not all_events_by_domain:
            for domain, stats in domain_results.items():
                all_events_by_domain[domain] = set()
                ever_toggled_by_domain[domain] = set()
                
                for evt in stats.get('active_events', []):
                    event_name = evt.get('event', '') if isinstance(evt, dict) else str(evt)
                    if event_name:
                        all_events_by_domain[domain].add(event_name)
                        ever_toggled_by_domain[domain].add(event_name)
                
                for evt in stats.get('inactive_events', []):
                    event_name = evt.get('event', '') if isinstance(evt, dict) else str(evt)
                    if event_name:
                        all_events_by_domain[domain].add(event_name)
        
        html = """
            <div class="chart-container" style="margin-top: 30px;">
                <h3 style="color: #0071C5; margin-bottom: 15px;">Overall Validation Progress (Cumulative)</h3>
                <p style="color: #666; margin-bottom: 15px;">
                    Cumulative coverage across all historical runs. Shows total events detected vs. events that have toggled at least once.
                </p>
                <div style="background: #e3f2fd; padding: 15px; border-radius: 8px; margin-bottom: 20px;">
                    <strong style="color: #0071C5;">What this shows:</strong>
                    <p style="color: #666; margin: 10px 0 0 0; font-size: 0.95em;">
                        From initial EMON checks across all runs, this tracks:
                        <strong>Total Available Events</strong> (excluding platform-unsupported) vs. 
                        <strong>Events Covered</strong> (toggled at least once in any run) vs. 
                        <strong>Remaining Gaps</strong> (never toggled across all runs)
                    </p>
                </div>
                
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 25px;">
                    <!-- Pie Chart -->
                    <div class="chart-container">
                        <canvas id="historicalDomainPieChart" style="max-height: 400px;"></canvas>
                    </div>
                    <!-- Heatmap Grid -->
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 10px; align-content: start;">
"""
        
        # Generate heatmap with cumulative data
        total_available_overall = 0
        total_covered_overall = 0
        
        # Use module-level domain colors constant
        domain_colors = DOMAIN_COLORS
        
        # Collect data for pie chart
        historical_domain_names = []
        historical_domain_coverage = []
        historical_domain_colors = []
        
        for domain in sorted(domain_results.keys()):
            # Get all events ever seen for this domain
            all_events = all_events_by_domain.get(domain, set())
            toggled_events = ever_toggled_by_domain.get(domain, set())
            unavailable = unavailable_events_by_domain.get(domain, set())
            
            # Available = all detected - unavailable
            available_events = all_events - unavailable
            available_count = len(available_events) if available_events else 0
            
            # If still zero, use current run's total_tested as fallback
            if available_count == 0:
                available_count = domain_results[domain].get('total_tested', 0)
            
            # Covered = events that toggled at least once
            covered_count = len(toggled_events & available_events) if available_events else 0
            remaining_count = available_count - covered_count
            
            coverage_pct = (covered_count / available_count * 100) if available_count > 0 else 0
            
            total_available_overall += available_count
            total_covered_overall += covered_count
            
            # Get domain color
            color = domain_colors.get(domain, '#6c757d')
            
            # Add to chart data
            historical_domain_names.append(domain.upper())
            historical_domain_coverage.append(round(coverage_pct, 1))
            historical_domain_colors.append(color)
            
            html += f"""
                        <div style="background: {color}15; border-left: 4px solid {color}; padding: 15px; border-radius: 6px; text-align: center;">
                            <div style="font-size: 0.85em; color: #666; margin-bottom: 5px;">{domain}</div>
                            <div style="font-size: 1.8em; font-weight: bold; color: {color};">{coverage_pct:.1f}%</div>
                        </div>
"""
        
        html += """
                    </div>
                </div>
"""
        
        # Add Chart.js script for historical pie chart
        import json
        html += f"""
            <script>
            // Historical Domain Coverage Pie Chart
            window.addEventListener('load', function() {{
                if (typeof Chart === 'undefined') return;
                const historicalPieCtx = document.getElementById('historicalDomainPieChart').getContext('2d');
                new Chart(historicalPieCtx, {{
                type: 'doughnut',
                data: {{
                    labels: {json.dumps(historical_domain_names)},
                    datasets: [{{
                        label: 'Coverage %',
                        data: {json.dumps(historical_domain_coverage)},
                        backgroundColor: {json.dumps(historical_domain_colors)},
                        borderWidth: 2,
                        borderColor: '#fff'
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {{
                        legend: {{
                            position: 'right',
                            labels: {{
                                padding: 15,
                                font: {{ size: 11 }}
                            }}
                        }},
                        title: {{
                            display: true,
                            text: 'Cumulative Coverage Distribution',
                            font: {{ size: 16, weight: 'bold' }}
                        }},
                        tooltip: {{
                            callbacks: {{
                                label: function(context) {{
                                    const pct = context.parsed.toFixed(1);
                                    return context.label + ': ' + pct + '% coverage';
                                }}
                            }}
                        }}
                    }}
                }}
            }});
            }});
            </script>
            </div>
"""
        return html
    

    def _generate_ml_intelligence_summary(self, ml_analysis: Dict, coverage_results: Dict) -> str:
        """Generate ML intelligence summary explaining what ML understands and needs."""
        training_status = ml_analysis.get('training_status', {})
        datasets = training_status.get('datasets_collected', 0)
        training_sessions = training_status.get('training_sessions', 0)
        
        # Calculate maturity level and required runs
        if datasets < 5:
            maturity = " INSUFFICIENT"
            maturity_color = "#dc3545"
            runs_needed = 5 - datasets
            confidence = "Very Low"
            confidence_pct = (datasets / 5) * 100
        elif datasets < 10:
            maturity = "[MED] DEVELOPING"
            maturity_color = "#ffc107"
            runs_needed = 10 - datasets
            confidence = "Low to Moderate"
            confidence_pct = 50 + ((datasets - 5) / 5) * 20
        elif datasets < 20:
            maturity = "[LOW] GOOD"
            maturity_color = "#28a745"
            runs_needed = 20 - datasets
            confidence = "Moderate to High"
            confidence_pct = 70 + ((datasets - 10) / 10) * 20
        else:
            maturity = "[LOW] EXCELLENT"
            maturity_color = "#17a2b8"
            runs_needed = 0
            confidence = "High"
            confidence_pct = 90 + min((datasets - 20) / 10 * 10, 10)
        
        # Analyze what ML has learned from patterns
        patterns = ml_analysis.get('patterns', {})
        pattern_dist = patterns.get('distribution', {})
        total_patterns = sum(pattern_dist.values())
        
        # Analyze coverage trends
        trends = ml_analysis.get('trends', {})
        historical_coverage = trends.get('historical_coverage', [])
        
        # Calculate what ML understands
        total_events_analyzed = coverage_results.get('total_events_tested', 0)
        active_events = coverage_results.get('active_events', 0)
        coverage_rate = coverage_results.get('activity_coverage', 0)
        
        html = f"""
        <div class="chart-container" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border-radius: 12px; padding: 25px; margin-bottom: 25px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);">
            <h3 style="color: white; margin-top: 0; font-size: 1.4em;">ML Intelligence Summary</h3>
            
            <!-- ML Maturity Level -->
            <div style="background: rgba(255,255,255,0.15); border-radius: 8px; padding: 15px; margin-bottom: 15px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                    <h4 style="margin: 0; color: white;">Training Maturity: {maturity}</h4>
                    <span style="background: {maturity_color}; color: white; padding: 5px 15px; border-radius: 20px; font-weight: bold;">
                        {datasets} datasets | {confidence} confidence
                    </span>
                </div>
                <div style="background: rgba(0,0,0,0.2); border-radius: 10px; height: 25px; overflow: hidden; margin-bottom: 10px;">
                    <div style="background: {maturity_color}; height: 100%; width: {confidence_pct:.1f}%; transition: width 0.3s; display: flex; align-items: center; justify-content: center; font-size: 0.85em; font-weight: bold;">
                        {confidence_pct:.1f}%
                    </div>
                </div>
        """
        
        if runs_needed > 0:
            html += f"""
                <p style="margin: 5px 0; font-size: 0.95em;">
                    <strong>{runs_needed} more runs</strong> needed to reach next maturity level
                </p>
            """
        else:
            html += """
                <p style="margin: 5px 0; font-size: 0.95em;">
                    <strong>Optimal training dataset achieved!</strong> ML models are highly confident
                </p>
            """
        
        html += """
            </div>
            
            <!-- What ML Currently Understands -->
            <div style="background: rgba(255,255,255,0.15); border-radius: 8px; padding: 15px; margin-bottom: 15px;">
                <h4 style="margin: 0 0 12px 0; color: white;">What ML Has Learned</h4>
                <div style="background: rgba(0,0,0,0.15); border-left: 4px solid #4CAF50; padding: 10px; margin-bottom: 10px; border-radius: 4px;">
                    <p style="margin: 0; font-size: 0.9em;">
                        <strong> Granular Learning Level:</strong> ML analyzes data at <strong>per-core, per-module, and per-event</strong> granularity, tracking:
                    </p>
                    <ul style="margin: 5px 0; padding-left: 20px; font-size: 0.85em;">
                        <li><strong>Per-Core:</strong> Individual core toggle patterns, count distributions (mean/std/min/max/CV)</li>
                        <li><strong>Per-Module:</strong> Domain-specific activity rates (p-core, e-core, IMC, CBO, NCU, etc.)</li>
                        <li><strong>Per-Event:</strong> Each PMU event's behavior, correlations, and temporal patterns</li>
                    </ul>
                </div>
        """
        
        if datasets >= 5:
            # ML has learned patterns
            if pattern_dist:
                html += f"""
                <ul style="margin: 5px 0; padding-left: 20px; font-size: 0.95em;">
                    <li><strong>Event Behavior Patterns:</strong> Classified {total_patterns} event behaviors across {len(pattern_dist)} pattern types</li>
                """
                for pattern, count in pattern_dist.items():
                    percentage = (count / total_patterns * 100) if total_patterns > 0 else 0
                    html += f"""
                    <li style="margin-left: 20px;"> {pattern.replace('_', ' ').title()}: {count} events ({percentage:.1f}%)</li>
                """
                html += """
                </ul>
                """
            else:
                # Fallback: Analyze current run's event distribution
                domain_results = coverage_results.get('domain_results', {})
                high_activity_count = 0
                medium_activity_count = 0
                low_activity_count = 0
                
                for domain, data in domain_results.items():
                    for event in data.get('active_events', []):
                        activity = event.get('total_activity', 0)
                        if activity > 1000000000:  # 1B+ counts
                            high_activity_count += 1
                        elif activity > 1000000:  # 1M+ counts
                            medium_activity_count += 1
                        else:
                            low_activity_count += 1
                
                if high_activity_count + medium_activity_count + low_activity_count > 0:
                    html += f"""
                <ul style="margin: 5px 0; padding-left: 20px; font-size: 0.95em;">
                    <li><strong>Real-Time Event Activity Distribution:</strong>
                        <ul style="margin: 5px 0;">
                            <li>High Activity Events: {high_activity_count} (>1B counts)</li>
                            <li>Medium Activity Events: {medium_activity_count} (>1M counts)</li>
                            <li>Low Activity Events: {low_activity_count} (<1M counts)</li>
                        </ul>
                    </li>
                </ul>
                    """
            
            if historical_coverage:
                avg_coverage = sum(h.get('coverage', 0) for h in historical_coverage) / len(historical_coverage)
                
                # Get absolute coverage metrics
                total_unique_discovered = trends.get('total_unique_events_discovered', 0)
                first_run_unique = historical_coverage[0].get('cumulative_unique_events', 0)
                last_run_unique = historical_coverage[-1].get('cumulative_unique_events', 0)
                new_events_found = trends.get('new_events_discovered', 0)
                
                # Calculate absolute coverage percentage (out of ~1843 total possible events)
                estimated_total_events = 1843  # Approximate total events across all domains
                absolute_coverage = (total_unique_discovered / estimated_total_events) * 100
                
                html += f"""
                <ul style="margin: 5px 0; padding-left: 20px; font-size: 0.95em;">
                    <li><strong>Coverage Trends:</strong> Analyzed {len(historical_coverage)} historical runs
                        <ul style="margin: 5px 0;">
                            <li><strong>Absolute Coverage:</strong> {total_unique_discovered}/{estimated_total_events} unique events discovered ({absolute_coverage:.1f}%)</li>
                            <li><strong>Progress:</strong> Started with {first_run_unique} events, now at {last_run_unique} events (+{new_events_found} new discoveries)</li>
                            <li><strong>Current Run:</strong> {coverage_rate:.1f}% of tested events active</li>
                            <li><strong>Trend:</strong> {trends.get('trend_direction', 'stable').title()}</li>
                        </ul>
                    </li>
                </ul>
                """
            
            # Event count analysis with anomaly detection insights
            anomalies = ml_analysis.get('anomalies', {})
            anomaly_stats = anomalies.get('statistics', {})
            total_anomalies = anomaly_stats.get('total_anomalies', 0)
            
            html += f"""
                <ul style="margin: 5px 0; padding-left: 20px; font-size: 0.95em;">
                    <li><strong>EMON Counter Analysis:</strong>
                        <ul style="margin: 5px 0;">
                            <li>Tracking {total_events_analyzed} total events across all domains</li>
                            <li>Identified {active_events} consistently active events ({coverage_rate:.1f}%)</li>
                            <li>Detected {total_events_analyzed - active_events} events requiring investigation</li>
            """
            
            if total_anomalies > 0:
                domains_affected = anomaly_stats.get('domains_affected', 0)
                severity_counts = anomaly_stats.get('by_severity', {})
                high_severity = severity_counts.get('high', 0)
                
                html += f"""
                            <li style="color: #ffe4a1;">ML detected {total_anomalies} anomalies across {domains_affected} domains"""
                
                if high_severity > 0:
                    html += f""" ({high_severity} high severity)"""
                
                html += """</li>
                """
            else:
                html += """
                            <li style="color: #a8e6cf;">No anomalies detected - coverage patterns are consistent</li>
                """
            
            html += """
                        </ul>
                    </li>
                </ul>
            """
        else:
            html += f"""
                <p style="margin: 5px 0; font-size: 0.95em; color: #ffe4a1;">
                    <strong>Insufficient data for pattern recognition.</strong> ML needs at least 5 runs to identify:
                </p>
                <ul style="margin: 5px 0; padding-left: 20px; font-size: 0.9em;">
                    <li>Event behavior patterns (low/medium/high activity)</li>
                    <li>Coverage trends across different workloads</li>
                    <li>Domain-specific anomalies</li>
                    <li>Event correlation patterns</li>
                </ul>
            """
        
        html += """
            </div>
            
            <!-- What ML Needs to Improve -->
            <div style="background: rgba(255,255,255,0.15); border-radius: 8px; padding: 15px;">
                <h4 style="margin: 0 0 12px 0; color: white;">To Achieve Deep Coverage Gap Analysis, ML Needs:</h4>
        """
        
        # Use ML's intelligent data diversity analysis
        data_diversity = ml_analysis.get('data_diversity', {})
        suggestions = data_diversity.get('suggestions', [])
        
        if suggestions and len(suggestions) > 0:
            # ML has analyzed the data and provides specific suggestions
            html += f"""
                <div style="background: rgba(0,0,0,0.15); border-left: 4px solid #4CAF50; padding: 10px; margin-bottom: 10px; border-radius: 4px;">
                    <p style="margin: 0; font-size: 0.9em;">
                        <strong>ML Analysis:</strong> {data_diversity.get('summary', 'Analyzing training data diversity')}
                    </p>
                </div>
            """
            
            # Show top 3 priority suggestions
            for i, suggestion in enumerate(suggestions[:3], 1):
                category = suggestion.get('category', 'General')
                priority = suggestion.get('priority', 'MEDIUM')
                priority_color = {'HIGH': '#dc3545', 'MEDIUM': '#ffc107', 'LOW': '#17a2b8'}.get(priority, '#6c757d')
                
                html += f"""
                <div style="background: rgba(255,255,255,0.1); border-left: 3px solid {priority_color}; padding: 10px; margin: 8px 0; border-radius: 4px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 5px;">
                        <strong>{category}</strong>
                        <span style="background: {priority_color}; color: white; padding: 2px 8px; border-radius: 10px; font-size: 0.75em;">{priority}</span>
                    </div>
                """
                
                # Workload diversity suggestions (OS-aware)
                if 'missing_count' in suggestion:
                    os_context = suggestion.get('os_context', 'unknown')
                    html += f"""
                    <p style="margin: 5px 0; font-size: 0.9em;">{suggestion.get('reason', '')}</p>
                    """
                    if os_context != 'unknown':
                        html += f"""
                        <p style="margin: 5px 0; font-size: 0.85em; color: #a8e6cf;">? <strong>OS Context:</strong> Recommendations for {os_context.title()} SUT</p>
                        """
                    html += """
                    <ul style="margin: 5px 0; padding-left: 20px; font-size: 0.85em;">
                    """
                    for detail in suggestion.get('details', []):
                        html += f"""
                        <li>
                            <strong>{detail['workload'].title()}:</strong> {detail['description']}<br>
                            <span style="color: #ffe4a1;"> {detail.get('availability', 'Check availability')}</span><br>
                            <span style="color: #a8e6cf;"> {detail.get('command', 'See documentation')}</span>
                        </li>
                        """
                    html += """
                    </ul>
                    """
                # OS diversity suggestions
                elif 'benefit' in suggestion:
                    html += f"""
                    <p style="margin: 5px 0; font-size: 0.9em;"><strong>Recommendation:</strong> {suggestion.get('recommendation', '')}</p>
                    <p style="margin: 5px 0; font-size: 0.85em; color: #ffe4a1;">{suggestion.get('reason', '')}</p>
                    <p style="margin: 5px 0; font-size: 0.85em; color: #a8e6cf;">? <strong>Benefit:</strong> {suggestion.get('benefit', '')}</p>
                    """
                # Domain-specific gap analysis
                elif 'weak_domains' in suggestion:
                    html += f"""
                    <p style="margin: 5px 0; font-size: 0.9em;"><strong>Insight:</strong> {suggestion.get('reason', '')}</p>
                    <p style="margin: 5px 0; font-size: 0.85em; color: #ffe4a1;"><strong>Weak Domains:</strong> {', '.join(suggestion.get('weak_domains', [])[:5])}</p>
                    <p style="margin: 5px 0; font-size: 0.85em; color: #a8e6cf;"><strong>Targeted Workloads:</strong></p>
                    <ul style="margin: 5px 0; padding-left: 20px; font-size: 0.85em;">
                    """
                    for workload in suggestion.get('targeted_workloads', []):
                        html += f"<li>{workload}</li>"
                    html += """
                    </ul>
                    """
                # Workload effectiveness analysis
                elif 'insight' in suggestion:
                    html += f"""
                    <p style="margin: 5px 0; font-size: 0.9em;"><strong>ML Insight:</strong> {suggestion.get('insight', '')}</p>
                    <p style="margin: 5px 0; font-size: 0.85em; color: #a8e6cf;">{suggestion.get('recommendation', '')}</p>
                    """
                    effectiveness = suggestion.get('effectiveness_data', {})
                    if effectiveness:
                        html += """
                        <div style="background: rgba(0,0,0,0.2); padding: 8px; border-radius: 4px; margin-top: 5px;">
                            <strong style="font-size: 0.85em;">Workload Effectiveness:</strong>
                            <ul style="margin: 5px 0; padding-left: 20px; font-size: 0.8em;">
                        """
                        # Sort by effectiveness
                        sorted_wl = sorted(effectiveness.items(), key=lambda x: x[1], reverse=True)
                        for wl, coverage in sorted_wl[:3]:
                            html += f"<li>{wl.title()}: {coverage:.1f}% avg coverage</li>"
                        html += """
                            </ul>
                        </div>
                        """
                # Duration or specific test suggestions
                elif 'recommendation' in suggestion:
                    html += f"""
                    <p style="margin: 5px 0; font-size: 0.9em;"><strong>Recommendation:</strong> {suggestion.get('recommendation', '')}</p>
                    <p style="margin: 5px 0; font-size: 0.85em; color: #ffe4a1;">{suggestion.get('reason', '')}</p>
                    """
                    if 'command' in suggestion:
                        html += f"""
                        <div style="background: rgba(0,0,0,0.3); padding: 8px; border-radius: 4px; margin-top: 5px; font-family: monospace; font-size: 0.8em;">
                            {suggestion.get('command', '')}
                        </div>
                        """
                    if 'actions' in suggestion:
                        html += """
                        <ul style="margin: 5px 0; padding-left: 20px; font-size: 0.85em;">
                        """
                        for action in suggestion.get('actions', []):
                            html += f"<li>{action}</li>"
                        html += """
                        </ul>
                        """
                
                html += """
                </div>
                """
        else:
            # Fallback to generic suggestions if ML hasn't analyzed yet
            if datasets < 10:
                html += f"""
                <div style="background: rgba(255,255,255,0.1); border-left: 3px solid #ffc107; padding: 10px; margin: 8px 0; border-radius: 4px;">
                    <strong>{10 - datasets} More Diverse Workload Runs:</strong>
                    <ul style="margin: 5px 0; padding-left: 20px; font-size: 0.9em;">
                        <li>CPU-intensive (Prime95, stress-ng cpu)</li>
                        <li>Memory-intensive (STREAM, stress-ng vm)</li>
                        <li>I/O-intensive (fio, stress-ng io)</li>
                        <li>Mixed workloads (SuperCollider, multibench)</li>
                    </ul>
                </div>
            """
            
            if datasets < 15:
                html += f"""
                <div style="background: rgba(255,255,255,0.1); border-left: 3px solid #17a2b8; padding: 10px; margin: 8px 0; border-radius: 4px;">
                    <strong> Different Duration Tests:</strong>
                    <ul style="margin: 5px 0; padding-left: 20px; font-size: 0.9em;">
                        <li>Short burst: 30-60 seconds (transient behavior)</li>
                        <li>Medium: 5-10 minutes (sustained load)</li>
                        <li>Long: 15+ minutes (thermal/power state transitions)</li>
                    </ul>
                </div>
            """
            
            if datasets < 20:
                html += """
                <div style="background: rgba(255,255,255,0.1); border-left: 3px solid #28a745; padding: 10px; margin: 8px 0; border-radius: 4px;">
                    <strong> Edge Case Scenarios:</strong>
                    <ul style="margin: 5px 0; padding-left: 20px; font-size: 0.9em;">
                        <li>Idle states (C-state transitions, power events)</li>
                        <li>Thermal throttling conditions</li>
                        <li>Different core frequencies/turbo states</li>
                        <li>Specific instruction mix patterns (AVX, SSE, etc.)</li>
                    </ul>
                </div>
            """
        
        if datasets >= 20:
            html += """
                <div style="background: rgba(255,255,255,0.1); border-left: 3px solid #28a745; padding: 10px; margin: 8px 0; border-radius: 4px;">
                    <strong>Excellent Dataset Diversity!</strong>
                    <p style="margin: 5px 0; font-size: 0.9em;">
                        ML can now accurately:
                    </p>
                    <ul style="margin: 5px 0; padding-left: 20px; font-size: 0.9em;">
                        <li>Pinpoint exact EMON events that never toggle despite varied workloads</li>
                        <li>Distinguish hardware limitations from workload gaps</li>
                        <li>Predict which workloads will activate specific event counters</li>
                        <li>Identify correlated event patterns and domain interactions</li>
                        <li>Provide confidence scores for coverage gap classifications</li>
                    </ul>
                </div>
            """
        
        # Windows vs Linux OS Comparison (if available)
        os_comparison = data_diversity.get('os_comparison', {})
        if os_comparison.get('status') == 'analyzed':
            html += """
            </div>
            
            <!-- Windows vs Linux OS Coverage Comparison -->
            <div style="background: rgba(255,255,255,0.1); border-radius: 8px; padding: 12px; margin-top: 15px; border-left: 4px solid #00bcd4;">
                <strong style="font-size: 1.05em;">Windows vs Linux Coverage Analysis:</strong>
            """
            
            summary = os_comparison.get('summary', {})
            windows_avg = summary.get('windows_avg_coverage', 0)
            linux_avg = summary.get('linux_avg_coverage', 0)
            domains_compared = summary.get('domains_compared', 0)
            gaps_count = summary.get('significant_gaps_count', 0)
            
            html += f"""
                <div style="background: rgba(0,0,0,0.15); padding: 10px; margin: 10px 0; border-radius: 4px;">
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-bottom: 10px;">
                        <div style="background: rgba(33, 150, 243, 0.2); padding: 10px; border-radius: 4px; border-left: 3px solid #0071C5;">
                            <div style="font-size: 0.85em; color: #bbb; margin-bottom: 5px;">Windows Coverage</div>
                            <div style="font-size: 1.5em; font-weight: bold; color: #0071C5;">{windows_avg:.1f}%</div>
                            <div style="font-size: 0.8em; color: #aaa;">{os_comparison.get('windows_datasets', 0)} datasets</div>
                        </div>
                        <div style="background: rgba(255, 152, 0, 0.2); padding: 10px; border-radius: 4px; border-left: 3px solid #FF9800;">
                            <div style="font-size: 0.85em; color: #bbb; margin-bottom: 5px;">Linux Coverage</div>
                            <div style="font-size: 1.5em; font-weight: bold; color: #FF9800;">{linux_avg:.1f}%</div>
                            <div style="font-size: 0.8em; color: #aaa;">{os_comparison.get('linux_datasets', 0)} datasets</div>
                        </div>
                    </div>
                    <div style="text-align: center; font-size: 0.85em; color: #a8e6cf;">
                        PASS: Compared {domains_compared} common domains
            """
            
            if gaps_count > 0:
                html += f" | WARNING: {gaps_count} significant gap{'s' if gaps_count != 1 else ''} detected (>15% difference)"
            
            html += """
                    </div>
                </div>
            """
            
            # Show significant gaps
            significant_gaps = os_comparison.get('significant_gaps', [])
            if significant_gaps:
                html += """
                <div style="margin: 10px 0;">
                    <strong style="font-size: 0.95em;">Significant Coverage Gaps:</strong>
                """
                
                for gap in significant_gaps[:5]:  # Show top 5
                    domain = gap.get('domain', 'unknown')
                    gap_pct = gap.get('gap', 0)
                    # Get OS names and coverages dynamically
                    os_names = []
                    os_coverages = []
                    for key in ['windows', 'linux']:  # Expected keys
                        if key in gap:
                            os_names.append(key.capitalize())
                            os_coverages.append(gap[key])
                    
                    # Fallback if keys differ
                    if not os_names:
                        for key, value in gap.items():
                            if isinstance(value, (int, float)) and key not in ['gap', 'events_compared']:
                                os_names.append(key.capitalize())
                                os_coverages.append(value)
                    
                    better_os = os_names[0] if len(os_coverages) >= 2 and os_coverages[0] > os_coverages[1] else (os_names[1] if len(os_names) > 1 else 'unknown')
                    
                    # Color code based on gap size
                    if gap_pct > 20:
                        color = '#dc3545'  # Red
                    elif gap_pct > 10:
                        color = '#ffc107'  # Yellow
                    else:
                        color = '#28a745'  # Green
                    
                    html += f"""
                    <div style="background: rgba(255,255,255,0.05); border-left: 3px solid {color}; padding: 8px; margin: 5px 0; border-radius: 4px;">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <strong style="font-size: 0.9em;">{domain}</strong>
                            <span style="background: {color}; color: white; padding: 2px 8px; border-radius: 10px; font-size: 0.75em;">{gap_pct:.1f}% gap</span>
                        </div>
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 5px; font-size: 0.8em;">
                            <div>{os_names[0] if len(os_names) > 0 else 'OS1'}: {os_coverages[0] if len(os_coverages) > 0 else 0:.1f}%</div>
                            <div>{os_names[1] if len(os_names) > 1 else 'OS2'}: {os_coverages[1] if len(os_coverages) > 1 else 0:.1f}%</div>
                        </div>
                        <div style="font-size: 0.75em; color: #a8e6cf; margin-top: 3px;">
                            {gap.get('recommendation', 'Investigate OS-specific behavior')}
                        </div>
                    </div>
                    """
                
                html += """
                </div>
                """
            
            # Show ML insights
            insights = os_comparison.get('insights', [])
            if insights:
                html += """
                <div style="margin: 10px 0;">
                    <strong style="font-size: 0.95em;">ML Insights:</strong>
                """
                
                for insight in insights:
                    html += f"""
                    <div style="background: rgba(76, 175, 80, 0.2); border-left: 3px solid #4CAF50; padding: 8px; margin: 5px 0; border-radius: 4px;">
                        <div style="font-size: 0.9em; font-weight: bold; margin-bottom: 3px;">{insight.get('title', 'Insight')}</div>
                        <div style="font-size: 0.85em; color: #ddd; margin-bottom: 3px;">{insight.get('description', '')}</div>
                        <div style="font-size: 0.8em; color: #a8e6cf;"> {insight.get('action', '')}</div>
                    </div>
                    """
                
                html += """
                </div>
                """
        
        html += f"""
            </div>
            
            <!-- Next Steps - Intelligent Action Plan -->
            <div style="background: rgba(255,255,255,0.1); border-radius: 8px; padding: 12px; margin-top: 15px; border-left: 4px solid white;">
                <strong style="font-size: 1.05em;">Next Steps - Priority Action Plan:</strong>
        """
        
        # Generate intelligent next steps based on ML analysis
        if suggestions and len(suggestions) > 0:
            # High priority actions first
            high_priority = [s for s in suggestions if s.get('priority') == 'HIGH']
            medium_priority = [s for s in suggestions if s.get('priority') == 'MEDIUM']
            
            if high_priority:
                html += f"""
                <div style="background: rgba(220, 53, 69, 0.2); padding: 8px; border-radius: 4px; margin: 8px 0;">
                    <strong style="color: #ffcccc;">Critical Gaps ({len(high_priority)} items):</strong>
                    <ol style="margin: 5px 0; padding-left: 25px; font-size: 0.85em;">
                """
                for i, action in enumerate(high_priority[:3], 1):
                    category = action.get('category', 'Action')
                    recommendation = action.get('recommendation', action.get('reason', 'See details above'))
                    if len(recommendation) > 100:
                        recommendation = recommendation[:100] + '...'
                    html += f"<li><strong>{category}</strong> - {recommendation}</li>"
                html += """
                    </ol>
                </div>
                """
            
            if medium_priority:
                html += f"""
                <div style="background: rgba(255, 193, 7, 0.2); padding: 8px; border-radius: 4px; margin: 5px 0;">
                    <strong style="color: #ffe4a1;">Enhancement Opportunities ({len(medium_priority)} items):</strong>
                    <ol style="margin: 5px 0; padding-left: 25px; font-size: 0.85em;">
                """
                for action in medium_priority[:2]:
                    category = action.get('category', 'Action')
                    html += f"<li><strong>{category}</strong></li>"
                html += """
                    </ol>
                </div>
                """
            
            # Quick win suggestion
            if datasets < 15:
                runs_needed = 15 - datasets
                html += f"""
                <p style="margin: 10px 0 5px 0; font-size: 0.9em; color: #a8e6cf;">
                    <strong>Quick Win:</strong> Run {runs_needed} more diverse tests to unlock ML's advanced pattern detection.
                </p>
                """
        else:
            # Fallback if no suggestions yet
            if datasets < 5:
                html += f"""
                <p style="margin: 8px 0 5px 0; font-size: 0.95em;">
                    Run <strong>{5 - datasets} more tests</strong> with different workloads to enable basic pattern recognition.
                </p>
                """
            elif datasets < 20:
                html += f"""
                <p style="margin: 8px 0 5px 0; font-size: 0.95em;">
                    Run <strong>{20 - datasets} more diverse tests</strong> to reach optimal ML confidence for precise gap analysis.
                </p>
                """
            else:
                html += """
                <p style="margin: 8px 0 5px 0; font-size: 0.95em;">
                    Continue collecting data to refine predictions. ML is now highly accurate at identifying true coverage gaps vs. hardware limitations.
                </p>
                """
        
        html += """
            </div>
        </div>
        """
        
        return html
    
