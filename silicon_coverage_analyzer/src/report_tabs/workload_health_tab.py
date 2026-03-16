"""
Workload Health Tab Generator Module

Generates the Workload & Health tab for the HTML report.
Contains system health monitoring and workload detection analysis.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class WorkloadHealthTabGenerator:
    """Generates the Workload & Health tab content."""
    
    def __init__(self, report_generator):
        """
        Initialize with reference to parent ReportGenerator.
        
        Args:
            report_generator: Parent ReportGenerator instance
        """
        self.rg = report_generator
    
    def generate(self, analysis_results: Dict[str, Any]) -> str:
        """
        Generate Workload & Health tab HTML.
        
        Args:
            analysis_results: Full analysis results
            
        Returns:
            HTML string for the workload health tab
        """
        html = self._generate_header()
        
        # Section 1: System Health Monitoring
        html += self._generate_health_section(analysis_results)
        
        # Section 2: Workload Detection & Recommendations
        html += self._generate_workload_section(analysis_results)
        
        html += """
        </div>
        """
        return html
    
    def _generate_header(self) -> str:
        """Generate tab header with interpretation guide."""
        return """
        <div id="workload-health" class="tab-content">
            <h2 class="section-title">System Health & Workload Analysis</h2>
            
            <div style="background: linear-gradient(135deg, #e0f7fa 0%, #b2ebf2 100%); border-left: 5px solid #00838f; padding: 20px; margin-bottom: 25px; border-radius: 8px;">
                <h3 style="margin: 0 0 10px 0; color: #006064;">How to Interpret This Tab</h3>
                <p style="margin: 5px 0; color: #006064; line-height: 1.5; font-size: 0.95em;">
                    <strong>Health Monitoring:</strong> CPU, memory, disk, temperature metrics captured during PMU collection.<br>
                    <strong>Comprehensive Metrics:</strong> Multi-line chart showing all system metrics over time.<br>
                    <strong>Health-Performance Analysis:</strong> Resource usage correlation with coverage timeline.<br>
                    <strong>ML Health Correlation:</strong> Training data for health-event pattern recognition.<br>
                    <strong>Workload Detection:</strong> Detected workload type with confidence score and evidence.<br>
                    <strong>Recommendations:</strong> Suggested workloads to activate missing PMU events.
                </p>
            </div>
"""
    
    def _generate_health_section(self, analysis_results: Dict) -> str:
        """Generate system health monitoring section."""
        html = """
            <div style="background: #e0f7fa; padding: 25px; margin-bottom: 30px; border-radius: 10px; border-left: 5px solid #00838f;">
                <h3 style="color: #006064; margin-top: 0;">System Health Monitoring</h3>
"""
        
        # Generate health content directly instead of calling parent
        health_html = self._generate_health_content(analysis_results)
        html += health_html
        
        html += """
            </div>
"""
        return html
    
    def _generate_workload_section(self, analysis_results: Dict) -> str:
        """Generate workload detection and recommendations section."""
        from src.ml_visualizations import render_recommended_workloads
        
        # Use unified workload detector
        coverage = analysis_results.get('coverage', {})
        metadata = analysis_results.get('metadata', {})
        stress_info = analysis_results.get('stress_detection', {})
        
        if stress_info.get('detected') and stress_info.get('processes'):
            running_processes = [p.get('name', '') for p in stress_info.get('processes', [])]
            metadata = dict(metadata)
            metadata['running_processes'] = running_processes
            metadata['workload_type'] = stress_info.get('primary_stress', '')
            metadata['stress_confidence'] = stress_info.get('confidence', 0)
        
        detection_result = self.rg.unified_workload_detector.detect(coverage, metadata)
        
        detected_workload_raw = detection_result.workload
        confidence = detection_result.confidence
        method = detection_result.method
        evidence = detection_result.evidence
        alternative_detections = detection_result.alternative_detections
        
        # Determine status color based on detection success
        if stress_info.get('detected') or confidence >= 80:
            status_color = '#28a745'  # Green for detected
            status_bg = '#d4edda'
            status_icon = '✅'
        elif confidence >= 50:
            status_color = '#ffc107'  # Yellow for inferred
            status_bg = '#fff3cd'
            status_icon = '⚠️'
        else:
            status_color = '#dc3545'  # Red for unknown
            status_bg = '#f8d7da'
            status_icon = '❌'
        
        html = f"""
            <div style="background: #fff3e0; padding: 25px; margin-bottom: 30px; border-radius: 10px; border-left: 5px solid #f57f17;">
                <h3 style="color: #e65100; margin-top: 0;">Workload Detection & Recommendations</h3>
                
                <!-- PROMINENT WORKLOAD DISPLAY -->
                <div style="background: {status_bg}; border: 2px solid {status_color}; border-radius: 12px; padding: 20px; margin-bottom: 20px; text-align: center;">
                    <div style="font-size: 0.9em; color: #666; margin-bottom: 8px;">{status_icon} DETECTED WORKLOAD</div>
                    <div style="font-size: 2em; font-weight: bold; color: {status_color}; margin-bottom: 8px;">
                        {detected_workload_raw}
                    </div>
                    <div style="display: flex; justify-content: center; gap: 20px; flex-wrap: wrap;">
                        <span style="background: {status_color}; color: white; padding: 5px 15px; border-radius: 20px; font-weight: 600;">
                            {confidence:.0f}% Confidence
                        </span>
                        <span style="background: #6c757d; color: white; padding: 5px 15px; border-radius: 20px;">
                            Method: {method.upper().replace('_', ' ')}
                        </span>
                    </div>
                </div>
                
                <h4 style="color: #f57f17;">Detection Details</h4>
"""
        
        # Detection method display
        html += self._generate_detection_display(method, evidence, alternative_detections)
        
        # Workload recommendations
        html += self._generate_workload_tips(detected_workload_raw)
        
        # Stress-Event Correlation Analysis
        ml_analysis = analysis_results.get('ml_analysis', {})
        stress_corr = ml_analysis.get('stress_correlation', {})
        if stress_corr.get('status') == 'success':
            html += self._generate_stress_correlation(stress_corr, detected_workload_raw)
        
        # Workload-Gap Mapping
        workload_gap_mapping = analysis_results.get('workload_gap_mapping', {})
        if workload_gap_mapping:
            html += """
            <div style="margin-top: 30px;">
                <h4 style="color: #0071C5;">Recommended Workloads for Gap Coverage</h4>
                <p style="color: #666; margin-bottom: 15px;">
                    Specific stress tests recommended to activate missing events.
                </p>
"""
            html += render_recommended_workloads(workload_gap_mapping)
            html += """
            </div>
"""
        
        # Workload Clustering
        html += self._generate_workload_clustering(analysis_results)
        
        html += """
            </div>
"""
        return html
    
    def _generate_detection_display(self, method: str, evidence: List, 
                                     alternative_detections: List) -> str:
        """Generate detection method display."""
        method_display = {
            'process': {
                'label': 'PROCESS DETECTION (90% Confidence)',
                'desc': 'Workload detected by monitoring running processes - most reliable method',
                'color': '#28a745',
                'bg': '#d4edda'
            },
            'ml_pattern': {
                'label': 'ML PATTERN DETECTION (75% Confidence)',
                'desc': 'Workload classified by trained ML model analyzing event patterns',
                'color': '#0071C5',
                'bg': '#e3f2fd'
            },
            'heuristic': {
                'label': 'HEURISTIC DETECTION (60% Confidence)',
                'desc': 'Workload inferred from domain activity patterns using rules',
                'color': '#ffc107',
                'bg': '#fff3cd'
            }
        }
        
        method_info = method_display.get(method, {
            'label': 'NO DETECTION',
            'desc': 'Could not detect workload',
            'color': '#dc3545',
            'bg': '#f8d7da'
        })
        
        html = f"""
            <div style="background: {method_info['bg']}; border-left: 5px solid {method_info['color']}; padding: 20px; border-radius: 8px; margin-bottom: 20px;">
                <div style="margin-bottom: 12px;">
                    <strong style="color: {method_info['color']}; font-size: 1.2em;">{method_info['label']}</strong>
                </div>
                <p style="color: {method_info['color']}; margin: 5px 0; font-size: 0.95em;">
                    {method_info['desc']}
                </p>
                <div style="margin-top: 12px; padding: 12px; background: rgba(255,255,255,0.6); border-radius: 6px;">
                    <strong style="color: #333;">Evidence:</strong>
                    <ul style="margin: 8px 0; padding-left: 25px; color: #555;">
"""
        
        for ev in evidence:
            html += f"                        <li>{ev}</li>\n"
        
        html += """
                    </ul>
                </div>
"""
        
        # Alternative detections
        if alternative_detections:
            html += """
                <details style="margin-top: 15px; cursor: pointer;">
                    <summary style="font-weight: 600; color: #333;">Alternative Detections</summary>
                    <div style="margin-top: 10px; padding: 12px; background: rgba(255,255,255,0.6); border-radius: 6px;">
"""
            for alt in alternative_detections:
                html += f"""
                        <div style="margin: 8px 0; padding: 8px; background: #f8f9fa; border-left: 3px solid #6c757d; border-radius: 4px;">
                            <strong>{alt['method'].upper()}:</strong> {alt['workload']} 
                            <span style="background: #6c757d; color: white; padding: 2px 8px; border-radius: 10px; font-size: 0.8em;">{alt['confidence']:.0f}%</span>
                        </div>
"""
            html += """
                    </div>
                </details>
"""
        
        html += """
            </div>
"""
        return html
    
    def _generate_workload_tips(self, detected_workload: str) -> str:
        """Generate workload-specific tips."""
        detected_norm = detected_workload.lower().replace(' ', '_').replace('-', '_')
        
        workload_tips = {
            'cpu_stress': 'Good CPU-intensive workload. Core domain events should be well-covered. Consider adding memory stress.',
            'memory_stress': 'Good memory-intensive workload. Uncore domain events should be covered. Consider adding CPU stress.',
            'mixed_stress': 'Excellent! Balanced workload provides comprehensive coverage across all domains.',
            'idle': 'Low activity detected. Run CPU stress (stress-ng) or memory stress (memtester) for better coverage.',
            'unknown': 'Could not classify workload. Consider running known stress tests.'
        }
        
        tip = workload_tips.get(detected_norm, workload_tips['unknown'])
        
        return f"""
            <div style="background: #f8f9fa; padding: 15px; border-left: 4px solid #6c757d; border-radius: 8px; margin-top: 20px;">
                <strong style="color: #333;">Workload Recommendations</strong>
                <p style="color: #555; margin: 8px 0 0 0; line-height: 1.6;">{tip}</p>
            </div>
"""
    
    def _generate_stress_correlation(self, stress_corr: Dict, detected_workload: str) -> str:
        """Generate stress-event correlation analysis section."""
        summary = stress_corr.get('summary', {})
        matrix = stress_corr.get('correlation_matrix', {})
        domain_impact = stress_corr.get('domain_stress_impact', {})
        stress_ml_status = stress_corr.get('ml_model_used', False)
        
        html = f"""
            <div class="chart-container" style="margin-top: 25px;">
                <h4>Stress-Event Correlation Analysis</h4>
                <p style="color: #666;">How workload stress affects event activity patterns</p>
                {'<div style="background: #d4edda; padding: 10px; border-left: 4px solid #28a745; margin: 10px 0;"><strong>ML Model Active</strong></div>' if stress_ml_status else '<div style="background: #fff3cd; padding: 10px; border-left: 4px solid #ffc107; margin: 10px 0;"><strong>Rule-Based Analysis</strong></div>'}
                
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 15px; margin-top: 15px;">
                    <div style="background: #fff; padding: 15px; border-left: 4px solid #dc3545; border-radius: 4px;">
                        <h5 style="margin: 0; color: #dc3545;">Stress-Sensitive Events</h5>
                        <div style="font-size: 2.5em; font-weight: bold; color: #dc3545; margin: 10px 0;">{summary.get('stress_sensitive_count', 0)}</div>
                        <p style="color: #666; margin: 0;">High correlation with stress</p>
                    </div>
                    <div style="background: #fff; padding: 15px; border-left: 4px solid #28a745; border-radius: 4px;">
                        <h5 style="margin: 0; color: #28a745;">Stress-Independent Events</h5>
                        <div style="font-size: 2.5em; font-weight: bold; color: #28a745; margin: 10px 0;">{summary.get('stress_independent_count', 0)}</div>
                        <p style="color: #666; margin: 0;">Unaffected by stress level</p>
                    </div>
                    <div style="background: #fff; padding: 15px; border-left: 4px solid #0071C5; border-radius: 4px;">
                        <h5 style="margin: 0; color: #0071C5;">Inferred Workload</h5>
                        <div style="font-size: 1.5em; font-weight: bold; color: #0071C5; margin: 10px 0;">{summary.get('workload_type', detected_workload).title()}</div>
                        <p style="color: #666; margin: 0;">Stress Level: {stress_corr.get('stress_level', 'unknown').upper()}</p>
                    </div>
                </div>
"""
        
        # Correlation heatmap
        if matrix:
            html += self._generate_correlation_heatmap(matrix)
        
        # Domain impact
        if domain_impact:
            html += self._generate_domain_impact(domain_impact)
        
        html += """
            </div>
"""
        return html
    
    def _generate_correlation_heatmap(self, matrix: Dict) -> str:
        """Generate workload-event correlation heatmap."""
        workload_types = set()
        for event_data in matrix.values():
            if isinstance(event_data, dict):
                workload_types.update(event_data.keys())
        workload_types = sorted(workload_types)
        
        html = """
                <div style="margin-top: 25px;">
                    <h5 style="color: #0071C5;">Workload-Event Correlation Heatmap</h5>
                    <div style="overflow-x: auto;">
                        <table style="width: 100%; border-collapse: collapse; font-size: 0.9em;">
                            <thead>
                                <tr style="background: #0071C5; color: white;">
                                    <th style="padding: 12px; text-align: left;">Event</th>
"""
        
        for wl in workload_types:
            html += f'                                    <th style="padding: 12px; text-align: center;">{wl.title()}</th>'
        
        html += """
                                </tr>
                            </thead>
                            <tbody>
"""
        
        # Sort by average correlation
        event_scores = []
        for event, correlations in matrix.items():
            if isinstance(correlations, dict):
                avg_corr = sum(correlations.values()) / len(correlations) if correlations else 0
                event_scores.append((event, avg_corr, correlations))
        event_scores.sort(key=lambda x: x[1], reverse=True)
        
        for event, avg_corr, correlations in event_scores[:30]:
            display_name = event if len(event) <= 30 else event[:27] + "..."
            html += f'                                <tr><td style="padding: 10px; border: 1px solid #ddd;" title="{event}">{display_name}</td>'
            
            for wl in workload_types:
                corr = correlations.get(wl, 0.0)
                if corr >= 0.7:
                    bg, text = "#d4edda", "#155724"
                elif corr >= 0.4:
                    bg, text = "#fff3cd", "#856404"
                else:
                    bg, text = "#f8d7da", "#721c24"
                html += f'<td style="padding: 10px; text-align: center; background: {bg}; color: {text}; font-weight: 600;">{corr:.2f}</td>'
            
            html += '</tr>\n'
        
        html += """
                            </tbody>
                        </table>
                    </div>
                </div>
"""
        return html
    
    def _generate_domain_impact(self, domain_impact: Dict) -> str:
        """Generate per-domain stress impact section."""
        html = """
                <div style="margin-top: 25px;">
                    <h5 style="color: #0071C5;">Per-Domain Stress Impact</h5>
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 15px;">
"""
        
        sorted_domains = sorted(domain_impact.items(), key=lambda x: x[1].get('impact_score', 0), reverse=True)
        
        for domain, impact_data in sorted_domains:
            impact_level = impact_data.get('impact_level', 'UNKNOWN')
            impact_score = impact_data.get('impact_score', 0)
            stress_sensitive_count = impact_data.get('stress_sensitive_count', 0)
            
            if impact_level == 'HIGH':
                border, bg = "#dc3545", "#fff5f5"
            elif impact_level == 'MEDIUM':
                border, bg = "#ffc107", "#fffbf0"
            else:
                border, bg = "#28a745", "#f0fff4"
            
            html += f"""
                        <div style="background: {bg}; padding: 15px; border-left: 4px solid {border}; border-radius: 6px;">
                            <h6 style="margin: 0 0 10px 0; color: #2c3e50;">{domain}</h6>
                            <div style="font-size: 0.9em;">
                                <div><strong>Impact:</strong> <span style="color: {border}; font-weight: bold;">{impact_level}</span></div>
                                <div><strong>Score:</strong> {impact_score:.2f}</div>
                                <div><strong>Sensitive Events:</strong> {stress_sensitive_count}</div>
                            </div>
                        </div>
"""
        
        html += """
                    </div>
                </div>
"""
        return html
    
    def _generate_workload_clustering(self, analysis_results: Dict) -> str:
        """Generate workload portfolio clustering section."""
        if not self.rg.ml_workload_clusterer.is_trained():
            return ""
        
        try:
            product_id = self.rg._get_product_id(analysis_results)
            
            historical_runs = []
            data_dir = Path(r'C:\silicon_coverage_analyzer_data') / 'raw_datasets' / product_id
            if data_dir.exists():
                coverage_files = sorted(data_dir.glob('coverage_*.json'))
                for f in coverage_files:
                    try:
                        with open(f) as cf:
                            data = json.load(cf)
                            historical_runs.append({
                                'run_id': f.stem,
                                'coverage': data.get('coverage', {}),
                                'metadata': data.get('metadata', {})
                            })
                    except:
                        pass
            
            if len(historical_runs) < 3:
                return ""
            
            cluster_result = self.rg.ml_workload_clusterer.cluster_workloads(historical_runs)
            
            if cluster_result.get('status') != 'success':
                return ""
            
            clusters = cluster_result.get('clusters', [])
            gaps = cluster_result.get('portfolio_gaps', {})
            
            html = """
            <div style="margin-top: 30px; background: linear-gradient(135deg, #f3e5f5 0%, #e1bee7 100%); border-left: 5px solid #7b1fa2; padding: 20px; border-radius: 8px;">
                <h4 style="color: #4a148c; margin-top: 0;">Workload Portfolio Analysis (ML Clustering)</h4>
                <p style="color: #6a1b9a; margin-bottom: 15px;">
                    ML identified distinct workload clusters based on coverage patterns.
                </p>
"""
            
            html += f"""
                <div style="background: white; padding: 15px; border-radius: 6px; margin-bottom: 20px;">
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px;">
                        <div style="text-align: center;">
                            <div style="font-size: 2em; font-weight: bold; color: #7b1fa2;">{len(clusters)}</div>
                            <div style="color: #666; font-size: 0.9em;">Distinct Clusters</div>
                        </div>
                        <div style="text-align: center;">
                            <div style="font-size: 2em; font-weight: bold; color: #7b1fa2;">{cluster_result.get('quality_score', 0):.2f}</div>
                            <div style="color: #666; font-size: 0.9em;">Silhouette Score</div>
                        </div>
                        <div style="text-align: center;">
                            <div style="font-size: 2em; font-weight: bold; color: #7b1fa2;">{len(historical_runs)}</div>
                            <div style="color: #666; font-size: 0.9em;">Runs Analyzed</div>
                        </div>
                    </div>
                </div>
                
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 15px;">
"""
            
            for cluster in clusters:
                cluster_id = cluster.get('cluster_id', 0)
                size = cluster.get('size', 0)
                avg_coverage = cluster.get('avg_coverage', 0)
                dominant_workload = cluster.get('dominant_workload', 'Unknown')
                
                if avg_coverage >= 80:
                    border, bg = "#28a745", "#f0fff4"
                elif avg_coverage >= 60:
                    border, bg = "#ffc107", "#fffbf0"
                else:
                    border, bg = "#dc3545", "#fff5f5"
                
                html += f"""
                    <div style="background: {bg}; padding: 15px; border-left: 4px solid {border}; border-radius: 6px;">
                        <h5 style="margin: 0 0 10px 0;">Cluster {cluster_id + 1}</h5>
                        <div style="font-size: 0.9em;">
                            <div><strong>Workload:</strong> {dominant_workload}</div>
                            <div><strong>Runs:</strong> {size}</div>
                            <div><strong>Avg Coverage:</strong> <span style="color: {border}; font-weight: bold;">{avg_coverage:.1f}%</span></div>
                        </div>
                    </div>
"""
            
            html += """
                </div>
"""
            
            # Portfolio gaps
            if gaps:
                underrep = gaps.get('underrepresented_workloads', [])
                low_cov = gaps.get('low_coverage_clusters', [])
                
                if underrep or low_cov:
                    html += """
                <div style="background: #fff3e0; padding: 15px; border-left: 4px solid #f57c00; border-radius: 6px; margin-top: 15px;">
                    <h5 style="margin: 0 0 10px 0; color: #e65100;">Portfolio Gaps</h5>
"""
                    if underrep:
                        html += f'<div><strong>Underrepresented:</strong> {", ".join(underrep)}</div>'
                    if low_cov:
                        html += f'<div><strong>Low Coverage Clusters:</strong> {", ".join([str(c) for c in low_cov])}</div>'
                    html += """
                </div>
"""
            
            html += """
            </div>
"""
            return html
            
        except Exception as e:
            logger.warning(f"Workload clustering failed: {e}")
            return ""

    def _generate_health_content(self, analysis_results: Dict) -> str:
        """Generate System Health monitoring tab with comprehensive metrics visualization."""
        # Get health monitoring data from analysis results
        health_data = analysis_results.get('health_history', {})
        
        # Fallback: Load from health_logs directory if not in analysis_results
        if not health_data or not health_data.get('samples'):
            loaded_health = self._load_health_data()
            if loaded_health:
                health_data = loaded_health
        
        # Get coverage summary for the correlation chart
        coverage_summary = analysis_results.get('summary', {})
        overall_coverage = coverage_summary.get('overall_coverage_percentage', 0)
        active_events = coverage_summary.get('active_events', 0)
        total_events = coverage_summary.get('total_events_tested', 1)
        
        # Fallback: Calculate coverage from coverage results if summary is missing or zero
        if overall_coverage == 0 and 'coverage' in analysis_results:
            coverage_data = analysis_results.get('coverage', {})
            domain_results = coverage_data.get('domain_results', {})
            
            if domain_results:
                # Calculate from domain_results structure
                total_active = 0
                total_tested = 0
                
                for domain_data in domain_results.values():
                    active_list = domain_data.get('active_events', [])
                    inactive_list = domain_data.get('inactive_events', [])
                    
                    # Count active events
                    total_active += len(active_list)
                    
                    # Count valid inactive events (exclude unavailable)
                    for event in inactive_list:
                        status = event.get('status', 'low_activity')
                        if status not in ['event_not_exists', 'not_found', 'no_file', 'collection_failed']:
                            total_tested += 1
                    
                    # Add active to tested count
                    total_tested += len(active_list)
                
                if total_tested > 0:
                    overall_coverage = (total_active / total_tested) * 100
                    active_events = total_active
                    total_events = total_tested
        
        if not health_data or not health_data.get('samples'):
            return """
        <div id="health-section">
            <h2 class="section-title">SYSTEM HEALTH MONITORING</h2>
            <div class="chart-container" style="background: #f8d7da; border-left: 4px solid #dc3545;">
                <h3 style="color: #721c24;">NO HEALTH DATA AVAILABLE</h3>
                <p style="color: #721c24; font-size: 1.05em;">
                    System health monitoring data was not collected during this run. Health monitoring is now enabled by default 
                    and will be available in future collections.
                </p>
            </div>
        </div>
"""
        
        samples = health_data['samples']
        total_samples = len(samples)
        collection_mode = health_data.get('collection_mode', 'unknown')
        
        # Parse timestamps (handle both string and datetime formats)
        first_ts = samples[0]['timestamp']
        last_ts = samples[-1]['timestamp']
        if isinstance(first_ts, str):
            first_ts = datetime.fromisoformat(first_ts)
            last_ts = datetime.fromisoformat(last_ts)
        duration_minutes = (last_ts - first_ts).total_seconds() / 60
        
        # Calculate statistics with correct key names for template
        stats = self._calculate_health_statistics(samples)
        
        # Generate time series data for charts (handle both string and datetime timestamps)
        timestamps = []
        for s in samples:
            ts = s['timestamp']
            if isinstance(ts, str):
                timestamps.append(ts.split('T')[1][:5] if 'T' in ts else ts[:5])
            else:
                timestamps.append(ts.strftime('%H:%M'))
        
        cpu_data = [s.get('metrics', {}).get('cpu_usage_pct', 0) for s in samples]
        memory_data = [s.get('metrics', {}).get('memory_usage_pct', 0) for s in samples]
        disk_data = [s.get('metrics', {}).get('disk_free_gb', 0) for s in samples]
        file_size_data = [s.get('metrics', {}).get('file_size_mb', 0) for s in samples]
        load_avg_data = [s.get('metrics', {}).get('load_avg_1min', 0) for s in samples]
        emon_cpu_data = [s.get('metrics', {}).get('emon_cpu_pct', 0) for s in samples]
        emon_mem_data = [s.get('metrics', {}).get('emon_mem_pct', 0) for s in samples]
        cpu_temp_data = [s.get('metrics', {}).get('temperature_c', 0) for s in samples]
        network_rx_data = [s.get('metrics', {}).get('network_rx_mb', 0) for s in samples]
        network_tx_data = [s.get('metrics', {}).get('network_tx_mb', 0) for s in samples]
        disk_read_data = [s.get('metrics', {}).get('disk_read_mbps', 0) for s in samples]
        disk_write_data = [s.get('metrics', {}).get('disk_write_mbps', 0) for s in samples]
        disk_io_data = [s.get('metrics', {}).get('disk_io_mbps', 0) for s in samples]
        context_switch_data = [s.get('metrics', {}).get('context_switches_per_sec', 0) for s in samples]
        process_data = [s.get('metrics', {}).get('process_count', 0) for s in samples]
        interrupt_data = [s.get('metrics', {}).get('interrupts_per_sec', 0) for s in samples]
        
        # Health issue count
        health_issues = sum(1 for s in samples if not s.get('ok', True))
        
        html = f"""
        <div id="health-section">
            
            <div class="chart-container" style="background: linear-gradient(135deg, #d4edda 0%, #c3e6cb 100%); border-left: 4px solid #28a745;">
                <h3 style="color: #155724;">HEALTH MONITORING ACTIVE</h3>
                <p style="color: #155724; font-size: 1.1em; margin-top: 10px;">
                    Captured {total_samples} health samples over {duration_minutes:.1f} minutes during {collection_mode} collection
                </p>
            </div>
            
            <!-- Health Summary Metrics -->
            <div class="summary-grid" style="margin-top: 20px;">
                <div class="summary-card">
                    <div class="metric-value" style="color: #0071C5;">{stats['avg_cpu']:.1f}%</div>
                    <div class="metric-label">Avg CPU Usage</div>
                    <p class="metric-subtitle">Peak: {stats['max_cpu']:.1f}%</p>
                </div>
                <div class="summary-card">
                    <div class="metric-value" style="color: #2980b9;">{stats['avg_memory']:.1f}%</div>
                    <div class="metric-label">Avg Memory Usage</div>
                    <p class="metric-subtitle">Peak: {stats['max_memory']:.1f}%</p>
                </div>
                <div class="summary-card">
                    <div class="metric-value" style="color: #27ae60;">{stats['avg_disk_free']:.1f} GB</div>
                    <div class="metric-label">Avg Disk Free</div>
                    <p class="metric-subtitle">Min: {stats['min_disk_free']:.1f} GB</p>
                </div>
                <div class="summary-card">
                    <div class="metric-value" style="color: {'#dc3545' if health_issues > 0 else '#28a745'}">{health_issues}</div>
                    <div class="metric-label">Health Issues</div>
                    <p class="metric-subtitle">{total_samples - health_issues} healthy samples</p>
                </div>
"""
        
        # Add Load Average card if available (Linux)
        if stats.get('has_load_avg', False):
            html += f"""
                <div class="summary-card">
                    <div class="metric-value" style="color: #9b59b6;">{stats['avg_load']:.2f}</div>
                    <div class="metric-label">Avg System Load</div>
                    <p class="metric-subtitle">Peak: {stats['max_load']:.2f}</p>
                </div>
"""
        
        # Add Temperature card if available
        if stats.get('has_temp', False) and stats['avg_temp'] > 0:
            temp_color = '#dc3545' if stats['avg_temp'] > 80 else '#f39c12' if stats['avg_temp'] > 70 else '#27ae60'
            html += f"""
                <div class="summary-card">
                    <div class="metric-value" style="color: {temp_color};">{stats['avg_temp']:.1f}°C</div>
                    <div class="metric-label">Avg CPU Temp</div>
                    <p class="metric-subtitle">Peak: {stats['max_temp']:.1f}°C</p>
                </div>
"""
        
        # Add Interrupts card if available
        if any(interrupt_data):
            html += f"""
                <div class="summary-card">
                    <div class="metric-value" style="color: #d35400;">{stats.get('avg_interrupts', 0):,.0f}/s</div>
                    <div class="metric-label">Avg Interrupts</div>
                    <p class="metric-subtitle">System interrupt rate</p>
                </div>
"""
        
        # Add Network I/O card if available
        if stats.get('has_network', False):
            total_network = stats['avg_network_rx_mb'] + stats['avg_network_tx_mb']
            html += f"""
                <div class="summary-card">
                    <div class="metric-value" style="color: #3498db;">{total_network:.1f} MB</div>
                    <div class="metric-label">Total Network I/O</div>
                    <p class="metric-subtitle">RX: {stats['avg_network_rx_mb']:.1f} | TX: {stats['avg_network_tx_mb']:.1f}</p>
                </div>
"""
        
        # Add Disk I/O card if available (platform-agnostic)
        if stats.get('has_disk_io', False):
            # Check which metrics are actually available
            has_separate_io = stats.get('avg_disk_read_mbps', 0) > 0 or stats.get('avg_disk_write_mbps', 0) > 0
            has_combined_io = stats.get('avg_disk_io_mbps', 0) > 0
            
            if has_separate_io:  # Separate read/write metrics available
                html += f"""
                <div class="summary-card">
                    <div class="metric-value" style="color: #27ae60;">{stats.get('avg_disk_read_mbps', 0):.2f} MB/s</div>
                    <div class="metric-label">Avg Disk Read</div>
                    <p class="metric-subtitle">Write: {stats.get('avg_disk_write_mbps', 0):.2f} MB/s</p>
                </div>
"""
            elif has_combined_io:  # Combined I/O metric available
                html += f"""
                <div class="summary-card">
                    <div class="metric-value" style="color: #16a085;">{stats['avg_disk_io_mbps']:.2f} MB/s</div>
                    <div class="metric-label">Avg Disk I/O</div>
                    <p class="metric-subtitle">Total throughput</p>
                </div>
"""
        
        # Add System Activity card if available
        if stats.get('has_system_activity', False):
            html += f"""
                <div class="summary-card">
                    <div class="metric-value" style="color: #8e44ad;">{stats['avg_processes']:.0f}</div>
                    <div class="metric-label">Avg Processes</div>
                    <p class="metric-subtitle">Ctx: {stats['avg_context_switches']:,.0f}/s</p>
                </div>
"""
        
        html += f"""
            </div>
            
            <!-- Comprehensive System Health Metrics Chart -->
            <div class="chart-container" style="margin-top: 30px; background: white; border-left: 5px solid #1976d2; padding: 25px;">
                <h3 class="chart-title" style="color: #1976d2; margin-top: 0;"> COMPREHENSIVE SYSTEM HEALTH METRICS</h3>
                <p style="color: #666; margin-bottom: 10px; font-size: 1.05em;">
                    <strong>Below:</strong> Complete view of all system health metrics captured during PMU collection
                </p>
                <p style="color: #888; margin-bottom: 20px; font-size: 0.9em; font-style: italic;">
                    OS-specific metrics shown when available (e.g., Load Average for Linux, Process Count for Windows). 
                    Hover over chart for detailed metric values at specific timestamps.
                </p>
                <canvas id="allHealthMetricsChart" style="max-height: 500px;"></canvas>
                
                <!-- Metrics Legend -->
                <div style="margin-top: 20px; padding: 15px; background: #f5f5f5; border-radius: 5px;">
                    <h4 style="margin: 0 0 10px 0; color: #333; font-size: 0.95em;">Metric Definitions:</h4>
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 10px; font-size: 0.85em; color: #555;">
                        <div><strong>CPU Usage:</strong> Total system CPU utilization (%)</div>
                        <div><strong>Memory Usage:</strong> System RAM utilization (%)</div>
                        <div><strong>Disk Free:</strong> Available disk space (GB)</div>
                        <div><strong>File Size:</strong> EMON output file size (MB)</div>
                        <div><strong>CPU Temp:</strong> Processor temperature (°C)</div>
                        <div><strong>Load Avg:</strong> System load (Linux 1-min average)</div>
                        <div><strong>EMON CPU:</strong> CPU used by EMON process (%)</div>
                        <div><strong>EMON Memory:</strong> Memory used by EMON (MB)</div>
                        <div><strong>Network I/O:</strong> Network traffic (RX+TX MB)</div>
                        <div><strong>Disk I/O:</strong> Disk read+write throughput (MB/s)</div>
                        <div><strong>Processes:</strong> Total system process count</div>
                        <div><strong>Interrupts:</strong> Hardware interrupts per second</div>
                    </div>
                </div>
            </div>
            
            <!-- Interactive Health-Performance Analysis Section -->
            <div style="margin-top: 40px; background: linear-gradient(135deg, #e8eaf6 0%, #c5cae9 100%); padding: 25px; border-radius: 10px; border-left: 5px solid #3f51b5;">
                <h3 class="chart-title" style="color: #1a237e; font-size: 1.4em; margin-bottom: 10px;"> INTERACTIVE HEALTH-PERFORMANCE ANALYSIS</h3>
                <p style="color: #1a237e; font-size: 1.05em; margin-bottom: 5px;">
                    <strong>System Health During Collection:</strong> Resource usage correlation with coverage timeline
                </p>
                <p style="color: #5c6bc0; font-size: 0.95em; margin-bottom: 20px; font-style: italic;">
                    Analyze how system resource utilization impacts PMU event coverage quality and collection performance below
                </p>
                
                <!-- Resource Usage Correlation with Coverage Timeline -->
                <div class="chart-container" style="margin-bottom: 25px; background: white;">
                    <h4 class="chart-title" style="color: #1565c0; font-size: 1.1em;"> Resource Usage Over Time</h4>
                    <p style="color: #666; font-size: 0.9em; margin-bottom: 15px;">
                        Real-time correlation between CPU/memory utilization and coverage performance during collection
                    </p>
                    <canvas id="resourceTimelineChart" style="max-height: 350px;"></canvas>
                    <p style="margin-top: 15px; color: #666; text-align: center;">
                        CPU: <strong>{stats['avg_cpu']:.1f}%</strong> avg | 
                        Memory: <strong>{stats['avg_memory']:.1f}%</strong> avg | 
                        Coverage: <strong>{overall_coverage:.1f}%</strong>
                    </p>
                </div>
                
                <!-- Resource Usage Distribution -->
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 20px; margin-top: 25px;">
                    <div class="chart-container" style="background: white;">
                        <h4 class="chart-title" style="color: #00796b; font-size: 1em;">CPU Usage Distribution</h4>
                        <div style="padding: 20px; text-align: center;">
                            <div style="font-size: 2.5em; font-weight: bold; color: #00796b; margin-bottom: 10px;">{stats['avg_cpu']:.1f}%</div>
                            <div style="color: #666;">Average CPU Usage</div>
                            <div style="margin-top: 15px; padding: 15px; background: #e0f2f1; border-radius: 5px;">
                                <div style="display: flex; justify-content: space-between; margin: 5px 0;">
                                    <span>Min:</span><strong>{min(cpu_data):.1f}%</strong>
                                </div>
                                <div style="display: flex; justify-content: space-between; margin: 5px 0;">
                                    <span>Max:</span><strong>{stats['max_cpu']:.1f}%</strong>
                                </div>
                                <div style="display: flex; justify-content: space-between; margin: 5px 0;">
                                    <span>Median:</span><strong>{sorted(cpu_data)[len(cpu_data)//2]:.1f}%</strong>
                                </div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="chart-container" style="background: white;">
                        <h4 class="chart-title" style="color: #7b1fa2; font-size: 1em;">Memory Usage Distribution</h4>
                        <div style="padding: 20px; text-align: center;">
                            <div style="font-size: 2.5em; font-weight: bold; color: #7b1fa2; margin-bottom: 10px;">{stats['avg_memory']:.1f}%</div>
                            <div style="color: #666;">Average Memory Usage</div>
                            <div style="margin-top: 15px; padding: 15px; background: #f3e5f5; border-radius: 5px;">
                                <div style="display: flex; justify-content: space-between; margin: 5px 0;">
                                    <span>Min:</span><strong>{min(memory_data):.1f}%</strong>
                                </div>
                                <div style="display: flex; justify-content: space-between; margin: 5px 0;">
                                    <span>Max:</span><strong>{stats['max_memory']:.1f}%</strong>
                                </div>
                                <div style="display: flex; justify-content: space-between; margin: 5px 0;">
                                    <span>Total RAM:</span><strong>{stats['total_memory_gb']:.1f} GB</strong>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                
                <!-- Overall System Health & Performance Profile -->
                <div style="margin-top: 25px; padding: 20px; background: white; border-radius: 8px;">
                    <h4 style="color: #d32f2f; margin-top: 0;"> Overall System Health & Performance Profile</h4>
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px;">
                        <div style="padding: 15px; background: #{'#d4edda' if stats['avg_cpu'] < 80 else '#fff3cd' if stats['avg_cpu'] < 95 else '#f8d7da'}; border-radius: 5px;">
                            <div style="font-weight: bold; margin-bottom: 5px;">CPU Health</div>
                            <div style="font-size: 1.3em; color: #{'#155724' if stats['avg_cpu'] < 80 else '#856404' if stats['avg_cpu'] < 95 else '#721c24'};">
                                {' Optimal' if stats['avg_cpu'] < 80 else ' High' if stats['avg_cpu'] < 95 else ' Critical'}
                            </div>
                        </div>
                        <div style="padding: 15px; background: #{'#d4edda' if stats['avg_memory'] < 80 else '#fff3cd' if stats['avg_memory'] < 90 else '#f8d7da'}; border-radius: 5px;">
                            <div style="font-weight: bold; margin-bottom: 5px;">Memory Health</div>
                            <div style="font-size: 1.3em; color: #{'#155724' if stats['avg_memory'] < 80 else '#856404' if stats['avg_memory'] < 90 else '#721c24'};">
                                {' Optimal' if stats['avg_memory'] < 80 else ' High' if stats['avg_memory'] < 90 else ' Critical'}
                            </div>
                        </div>
                        <div style="padding: 15px; background: #{'#d4edda' if overall_coverage >= 70 else '#fff3cd' if overall_coverage >= 50 else '#f8d7da'}; border-radius: 5px;">
                            <div style="font-weight: bold; margin-bottom: 5px;">Coverage Performance</div>
                            <div style="font-size: 1.3em; color: #{'#155724' if overall_coverage >= 70 else '#856404' if overall_coverage >= 50 else '#721c24'};">
                                {' Good' if overall_coverage >= 70 else ' Moderate' if overall_coverage >= 50 else ' Low'}
                            </div>
                        </div>
                        <div style="padding: 15px; background: #{'#d4edda' if health_issues == 0 else '#fff3cd' if health_issues < 3 else '#f8d7da'}; border-radius: 5px;">
                            <div style="font-weight: bold; margin-bottom: 5px;">System Stability</div>
                            <div style="font-size: 1.3em; color: #{'#155724' if health_issues == 0 else '#856404' if health_issues < 3 else '#721c24'};">
                                {' Stable' if health_issues == 0 else ' Minor Issues' if health_issues < 3 else ' Issues Detected'}
                            </div>
                        </div>
                    </div>
                </div>
            </div>
"""
        
        # Health Issues Table
        if health_issues > 0:
            html += """
            <div class="chart-container" style="margin-top: 30px; background: #fff3cd; border-left: 4px solid #ffc107;">
                <h3 class="chart-title" style="color: #856404;">HEALTH ISSUES DETECTED</h3>
                <table class="event-table">
                    <thead>
                        <tr>
                            <th>Timestamp</th>
                            <th>Issue</th>
                            <th>CPU %</th>
                            <th>Memory %</th>
                            <th>Disk Free</th>
                        </tr>
                    </thead>
                    <tbody>
"""
            for sample in samples:
                if not sample.get('ok', True):
                    timestamp = sample['timestamp'].split('T')[1][:8]  # HH:MM:SS
                    warning = sample.get('warning', 'Unknown issue')
                    metrics = sample.get('metrics', {})
                    cpu = metrics.get('cpu_usage_pct', 0)
                    memory = metrics.get('memory_usage_pct', 0)
                    disk = metrics.get('disk_free_gb', 0)
                    
                    html += f"""
                        <tr style="background: #fff3cd;">
                            <td>{timestamp}</td>
                            <td style="color: #856404; font-weight: 600;">{warning}</td>
                            <td>{cpu:.1f}%</td>
                            <td>{memory:.1f}%</td>
                            <td>{disk:.1f} GB</td>
                        </tr>
"""
            html += """
                    </tbody>
                </table>
            </div>
"""
        
        # ML Health-Performance Correlation Analysis Section
        html += self._generate_ml_health_correlation(analysis_results, samples, stats)
        
        html += """
        
        <script>
            // Resource Usage Timeline Chart (Multi-line chart showing CPU, Memory, Coverage over time)
            window.addEventListener('load', function() {
                if (typeof Chart === 'undefined') return;
                new Chart(document.getElementById('resourceTimelineChart'), {
                    type: 'line',
                    data: {
                        labels: """ + json.dumps(timestamps) + """,
                        datasets: [
                            {
                                label: 'CPU Usage %',
                                data: """ + json.dumps(cpu_data) + """,
                                borderColor: '#0071C5',
                                backgroundColor: 'rgba(0, 113, 197, 0.1)',
                                fill: true,
                                tension: 0.4,
                                yAxisID: 'y'
                            },
                            {
                                label: 'Memory Usage %',
                                data: """ + json.dumps(memory_data) + """,
                                borderColor: '#7b1fa2',
                                backgroundColor: 'rgba(123, 31, 162, 0.1)',
                                fill: true,
                                tension: 0.4,
                                yAxisID: 'y'
                            },
                            {
                                label: 'Coverage % (Constant)',
                                data: Array(""" + str(len(timestamps)) + """).fill(""" + f"{overall_coverage:.1f}" + """),
                                borderColor: '#28a745',
                                backgroundColor: 'rgba(40, 167, 69, 0.1)',
                                borderDash: [5, 5],
                                borderWidth: 2,
                                fill: false,
                                tension: 0,
                                yAxisID: 'y',
                                pointRadius: 0
                            }
                        ]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: true,
                        interaction: {
                            mode: 'index',
                            intersect: false
                        },
                        plugins: {
                            legend: { 
                                display: true,
                                position: 'top'
                            },
                            tooltip: {
                                mode: 'index',
                                intersect: false
                            }
                        },
                        scales: {
                            y: {
                                beginAtZero: true,
                                max: 100,
                                title: {
                                    display: true,
                                    text: 'Percentage (%)'
                                },
                                ticks: {
                                    callback: function(value) {
                                        return value + '%';
                                    }
                                }
                            },
                            x: {
                                title: {
                                    display: true,
                                    text: 'Collection Timeline'
                                }
                            }
                        }
                    }
                });
            });
            
            // Comprehensive System Health Metrics Chart
            window.addEventListener('load', function() {
                if (typeof Chart === 'undefined') return;
                new Chart(document.getElementById('allHealthMetricsChart'), {
                    type: 'line',
                    data: {
                        labels: """ + json.dumps(timestamps) + """,
                        datasets: [
                            {
                                label: 'CPU Usage %',
                                data: """ + json.dumps(cpu_data) + """,
                                borderColor: '#e74c3c',
                                backgroundColor: 'rgba(231, 76, 60, 0.1)',
                                fill: false,
                                tension: 0.3,
                                yAxisID: 'y-percentage'
                            },
                            {
                                label: 'Memory Usage %',
                                data: """ + json.dumps(memory_data) + """,
                                borderColor: '#3498db',
                                backgroundColor: 'rgba(52, 152, 219, 0.1)',
                                fill: false,
                                tension: 0.3,
                                yAxisID: 'y-percentage'
                            },"""
        
        # Add temperature data if available (check if any values are non-zero)
        if any(t > 0 for t in cpu_temp_data):
            html += """
                            {
                                label: 'CPU Temperature (°C)',
                                data: """ + json.dumps(cpu_temp_data) + """,
                                borderColor: '#e67e22',
                                backgroundColor: 'rgba(230, 126, 34, 0.1)',
                                fill: false,
                                tension: 0.3,
                                yAxisID: 'y-temperature'
                            },"""
        
        # Add load average if available (Linux)
        if stats.get('has_load_avg', False):
            html += """
                            {
                                label: 'System Load (1-min avg)',
                                data: """ + json.dumps(load_avg_data) + """,
                                borderColor: '#9b59b6',
                                backgroundColor: 'rgba(155, 89, 182, 0.1)',
                                fill: false,
                                tension: 0.3,
                                yAxisID: 'y-load'
                            },"""
        
        # Add disk I/O if available
        if stats.get('has_disk_io', False):
            if stats['avg_disk_read_mbps'] > 0:  # Linux style
                html += """
                            {
                                label: 'Disk Read (MB/s)',
                                data: """ + json.dumps(disk_read_data) + """,
                                borderColor: '#16a085',
                                backgroundColor: 'rgba(22, 160, 133, 0.1)',
                                fill: false,
                                tension: 0.3,
                                yAxisID: 'y-disk-io'
                            },
                            {
                                label: 'Disk Write (MB/s)',
                                data: """ + json.dumps(disk_write_data) + """,
                                borderColor: '#27ae60',
                                backgroundColor: 'rgba(39, 174, 96, 0.1)',
                                fill: false,
                                tension: 0.3,
                                yAxisID: 'y-disk-io'
                            },"""
            else:  # Windows style
                html += """
                            {
                                label: 'Disk I/O (MB/s)',
                                data: """ + json.dumps(disk_io_data) + """,
                                borderColor: '#16a085',
                                backgroundColor: 'rgba(22, 160, 133, 0.1)',
                                fill: false,
                                tension: 0.3,
                                yAxisID: 'y-disk-io'
                            },"""
        
        # Add network I/O if available
        if stats.get('has_network', False):
            html += """
                            {
                                label: 'Network RX (MB)',
                                data: """ + json.dumps(network_rx_data) + """,
                                borderColor: '#2ecc71',
                                backgroundColor: 'rgba(46, 204, 113, 0.1)',
                                fill: false,
                                tension: 0.3,
                                yAxisID: 'y-network'
                            },
                            {
                                label: 'Network TX (MB)',
                                data: """ + json.dumps(network_tx_data) + """,
                                borderColor: '#f39c12',
                                backgroundColor: 'rgba(243, 156, 18, 0.1)',
                                fill: false,
                                tension: 0.3,
                                yAxisID: 'y-network'
                            },"""
        
        # Add context switches if available
        if any(context_switch_data):
            html += """
                            {
                                label: 'Context Switches/sec',
                                data: """ + json.dumps(context_switch_data) + """,
                                borderColor: '#c0392b',
                                backgroundColor: 'rgba(192, 57, 43, 0.1)',
                                fill: false,
                                tension: 0.3,
                                yAxisID: 'y-switches'
                            },"""
        
        # Add process count if available
        if any(process_data):
            html += """
                            {
                                label: 'Process Count',
                                data: """ + json.dumps(process_data) + """,
                                borderColor: '#8e44ad',
                                backgroundColor: 'rgba(142, 68, 173, 0.1)',
                                fill: false,
                                tension: 0.3,
                                yAxisID: 'y-processes'
                            },"""
        
        # Add interrupts if available
        if any(interrupt_data):
            html += """
                            {
                                label: 'Interrupts/sec',
                                data: """ + json.dumps(interrupt_data) + """,
                                borderColor: '#d35400',
                                backgroundColor: 'rgba(211, 84, 0, 0.1)',
                                fill: false,
                                tension: 0.3,
                                yAxisID: 'y-interrupts'
                            },"""
        
        html += """
                        ]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: true,
                        interaction: {
                            mode: 'index',
                            intersect: false
                        },
                        plugins: {
                            legend: {
                                display: true,
                                position: 'top',
                                labels: {
                                    usePointStyle: true,
                                    padding: 15,
                                    font: { size: 11 }
                                }
                            },
                            tooltip: {
                                enabled: true,
                                mode: 'index',
                                intersect: false
                            }
                        },
                        scales: {
                            x: {
                                display: true,
                                title: {
                                    display: true,
                                    text: 'Time',
                                    font: { size: 12, weight: 'bold' }
                                }
                            },
                            'y-percentage': {
                                type: 'linear',
                                display: true,
                                position: 'left',
                                title: {
                                    display: true,
                                    text: 'Percentage (%)',
                                    font: { size: 12, weight: 'bold' }
                                },
                                min: 0,
                                max: 100
                            },"""
        
        # Add temperature axis if needed (check if any values are non-zero)
        if any(t > 0 for t in cpu_temp_data):
            html += """
                            'y-temperature': {
                                type: 'linear',
                                display: true,
                                position: 'right',
                                title: {
                                    display: true,
                                    text: 'Temperature (°C)',
                                    font: { size: 11 },
                                    color: '#e67e22'
                                },
                                grid: { drawOnChartArea: false },
                                ticks: {
                                    color: '#e67e22'
                                }
                            },"""
        
        # Add load axis if needed
        if stats.get('has_load_avg', False):
            html += """
                            'y-load': {
                                type: 'linear',
                                display: false,
                                position: 'right'
                            },"""
        
        # Add disk I/O axis if needed
        if stats.get('has_disk_io', False):
            html += """
                            'y-disk-io': {
                                type: 'linear',
                                display: false,
                                position: 'right'
                            },"""
        
        # Add network axis if needed
        if stats.get('has_network', False):
            html += """
                            'y-network': {
                                type: 'linear',
                                display: false,
                                position: 'right'
                            },"""
        
        # Add context switches axis if needed
        if any(context_switch_data):
            html += """
                            'y-switches': {
                                type: 'linear',
                                display: false,
                                position: 'right'
                            },"""
        
        # Add processes axis if needed
        if any(process_data):
            html += """
                            'y-processes': {
                                type: 'linear',
                                display: false,
                                position: 'right'
                            },"""
        
        # Add interrupts axis if needed
        if any(interrupt_data):
            html += """
                            'y-interrupts': {
                                type: 'linear',
                                display: true,
                                position: 'right',
                                title: {
                                    display: true,
                                    text: 'Interrupts/sec',
                                    font: { size: 11 },
                                    color: '#d35400'
                                },
                                grid: { drawOnChartArea: false },
                                ticks: {
                                    color: '#d35400'
                                }
                            },"""
        
        html += """
                        }
                    }
                });
            });
        </script>
        </div>
"""
        

        return html
    
    def _load_health_data(self):
        """Load the most recent system health monitoring data."""
        # Use centralized data directory
        health_dir = Path('C:/silicon_coverage_analyzer_data/health_logs')
        if not health_dir.exists():
            return None
        
        # Find most recent health file
        health_files = sorted(health_dir.glob('system_health_*.json'), key=lambda p: p.stat().st_mtime, reverse=True)
        if not health_files:
            return None
        
        try:
            with open(health_files[0], 'r') as f:
                return json.load(f)
        except Exception:
            return None
    
    def _calculate_health_statistics(self, samples):
        """Calculate statistics from health samples."""
        stats = {
            'avg_cpu': 0,
            'max_cpu': 0,
            'avg_memory': 0,
            'max_memory': 0,
            'total_memory_gb': 0,
            'avg_disk_free': 0,
            'min_disk_free': float('inf'),
            'final_file_size_mb': 0,
            'avg_emon_cpu': 0,
            'avg_emon_mem': 0,
            'avg_load': 0,
            'max_load': 0,
            'has_load_avg': False,
            'has_temp': False,
            'avg_temp': 0,
            'max_temp': 0,
            'avg_network_rx_mb': 0,
            'avg_network_tx_mb': 0,
            'has_network': False,
            'avg_disk_read_mbps': 0,
            'avg_disk_write_mbps': 0,
            'avg_disk_io_mbps': 0,
            'has_disk_io': False,
            'avg_context_switches': 0,
            'avg_processes': 0,
            'avg_interrupts': 0,
            'has_system_activity': False,
            'emon_pid': 0
        }
        
        cpu_values = []
        memory_values = []
        disk_values = []
        emon_cpu_values = []
        emon_mem_values = []
        load_values = []
        temp_values = []
        network_rx_values = []
        network_tx_values = []
        disk_read_values = []
        disk_write_values = []
        disk_io_values = []
        context_switch_values = []
        process_values = []
        interrupt_values = []
        
        for sample in samples:
            metrics = sample.get('metrics', {})
            
            if 'cpu_usage_pct' in metrics:
                cpu_values.append(metrics['cpu_usage_pct'])
                stats['max_cpu'] = max(stats['max_cpu'], metrics['cpu_usage_pct'])
            
            if 'memory_usage_pct' in metrics:
                memory_values.append(metrics['memory_usage_pct'])
                stats['max_memory'] = max(stats['max_memory'], metrics['memory_usage_pct'])
            
            if 'memory_total_gb' in metrics:
                stats['total_memory_gb'] = metrics['memory_total_gb']
            
            if 'disk_free_gb' in metrics:
                disk_values.append(metrics['disk_free_gb'])
                stats['min_disk_free'] = min(stats['min_disk_free'], metrics['disk_free_gb'])
            
            if 'file_size_mb' in metrics:
                stats['final_file_size_mb'] = metrics['file_size_mb']
            
            if 'emon_cpu_pct' in metrics:
                emon_cpu_values.append(metrics['emon_cpu_pct'])
            
            if 'load_avg_1min' in metrics:
                load_values.append(metrics['load_avg_1min'])
                stats['max_load'] = max(stats['max_load'], metrics['load_avg_1min'])
                stats['has_load_avg'] = True
            
            if 'temperature_c' in metrics:
                temp_values.append(metrics['temperature_c'])
                stats['max_temp'] = max(stats['max_temp'], metrics['temperature_c'])
                stats['has_temp'] = True
            
            if 'emon_mem_pct' in metrics:
                emon_mem_values.append(metrics['emon_mem_pct'])
            
            if 'emon_pid' in metrics:
                stats['emon_pid'] = metrics['emon_pid']
            
            if 'network_rx_mb' in metrics and metrics['network_rx_mb'] > 0:
                network_rx_values.append(metrics['network_rx_mb'])
                stats['has_network'] = True
            
            if 'network_tx_mb' in metrics and metrics['network_tx_mb'] > 0:
                network_tx_values.append(metrics['network_tx_mb'])
            
            if 'disk_read_mbps' in metrics and metrics['disk_read_mbps'] > 0:
                disk_read_values.append(metrics['disk_read_mbps'])
                stats['has_disk_io'] = True
            
            if 'disk_write_mbps' in metrics and metrics['disk_write_mbps'] > 0:
                disk_write_values.append(metrics['disk_write_mbps'])
            
            if 'disk_io_mbps' in metrics and metrics['disk_io_mbps'] > 0:
                disk_io_values.append(metrics['disk_io_mbps'])
                stats['has_disk_io'] = True
            
            if 'context_switches_per_sec' in metrics and metrics['context_switches_per_sec'] > 0:
                context_switch_values.append(metrics['context_switches_per_sec'])
                stats['has_system_activity'] = True
            
            if 'process_count' in metrics and metrics['process_count'] > 0:
                process_values.append(metrics['process_count'])
            
            if 'interrupts_per_sec' in metrics:
                interrupt_values.append(metrics['interrupts_per_sec'])
        
        # Calculate averages
        if cpu_values:
            stats['avg_cpu'] = sum(cpu_values) / len(cpu_values)
        if memory_values:
            stats['avg_memory'] = sum(memory_values) / len(memory_values)
        if disk_values:
            stats['avg_disk_free'] = sum(disk_values) / len(disk_values)
        if emon_cpu_values:
            stats['avg_emon_cpu'] = sum(emon_cpu_values) / len(emon_cpu_values)
        if emon_mem_values:
            stats['avg_emon_mem'] = sum(emon_mem_values) / len(emon_mem_values)
        if load_values:
            stats['avg_load'] = sum(load_values) / len(load_values)
        if temp_values:
            stats['avg_temp'] = sum(temp_values) / len(temp_values)
        if network_rx_values:
            stats['avg_network_rx_mb'] = sum(network_rx_values) / len(network_rx_values)
        if network_tx_values:
            stats['avg_network_tx_mb'] = sum(network_tx_values) / len(network_tx_values)
        if disk_read_values:
            stats['avg_disk_read_mbps'] = sum(disk_read_values) / len(disk_read_values)
        if disk_write_values:
            stats['avg_disk_write_mbps'] = sum(disk_write_values) / len(disk_write_values)
        if disk_io_values:
            stats['avg_disk_io_mbps'] = sum(disk_io_values) / len(disk_io_values)
        if context_switch_values:
            stats['avg_context_switches'] = sum(context_switch_values) / len(context_switch_values)
        if process_values:
            stats['avg_processes'] = sum(process_values) / len(process_values)
        if interrupt_values:
            stats['avg_interrupts'] = sum(interrupt_values) / len(interrupt_values)
        
        if stats['min_disk_free'] == float('inf'):
            stats['min_disk_free'] = 0
        
        return stats
    
    def _generate_ml_health_correlation(self, analysis_results, samples, stats):
        """Generate ML Health-Performance Correlation Analysis section - ML-ONLY, no fallbacks."""
        html = ""
        
        if not samples or len(samples) == 0:
            return ""
        
        # Check if ML analysis exists
        ml_analysis = analysis_results.get('ml_analysis', {})
        if getattr(self.rg, "debug", False):
            print(f"[DEBUG-Health] ml_analysis keys: {list(ml_analysis.keys()) if ml_analysis else 'None'}")
            print(f"[DEBUG-Health] ml_analysis status: {ml_analysis.get('status') if ml_analysis else 'N/A'}")
        
        # Check health_correlation specifically
        health_corr = ml_analysis.get('health_correlation', {}) if ml_analysis else {}
        if getattr(self.rg, "debug", False):
            print(f"[DEBUG-Health] health_correlation exists: {bool(health_corr)}")
            print(f"[DEBUG-Health] health_correlation keys: {list(health_corr.keys()) if health_corr else 'None'}")
        
        # Check if health correlation data is available (not ml_analysis status!)
        if not health_corr or not health_corr.get('ml_model_used', False):
            return """
            <div class="chart-container" style="margin-top: 30px; background: #fff3cd; border-left: 4px solid #ffc107;">
                <h3 style="color: #856404;">ML HEALTH-EVENT CORRELATION - NO ML DATA AVAILABLE</h3>
                <p style="color: #856404; font-size: 1.05em;">
                    The ML health-performance correlation model has not been trained yet. This model requires:
                </p>
                <ul style="color: #856404; font-size: 1.05em;">
                    <li>Multiple historical runs with health monitoring data (minimum 5 runs recommended)</li>
                    <li>Scikit-learn library installed (<code>pip install scikit-learn</code>)</li>
                    <li>ML training enabled in configuration</li>
                </ul>
                <p style="color: #856404; font-size: 1.05em; margin-top: 15px;">
                    <strong>Status:</strong> Health samples collected this run will be used for future ML training. 
                    Continue collecting data and the ML model will automatically train once sufficient historical data is available.
                </p>
            </div>
"""
        
        total_samples = len(samples)
        has_temp = any(s.get('metrics', {}).get('temperature_c', 0) > 0 for s in samples)
        coverage = analysis_results.get('coverage', {})
        total_events = coverage.get('total_events_tested', 0)
        active_events = coverage.get('active_events', 0)
        coverage_rate = coverage.get('activity_coverage', 0)
        
        # Use health_correlation data from ml_analysis
        ml_health_score = health_corr.get('health_score', 0)
        ml_status = health_corr.get('status_text', 'Unknown')
        ml_color = health_corr.get('status_color', '#6c757d')
        ml_correlations = health_corr.get('correlations', [])
        ml_recommendations = health_corr.get('recommendations', [])
        
        # Get coverage data for ML correlation section
        coverage_data = analysis_results.get('coverage', {})
        # Coverage data is directly in coverage_data, not in a 'summary' sub-key
        coverage_rate_ml = coverage_data.get('activity_coverage', 0)
        active_events_count = coverage_data.get('active_events', 0)
        total_events_count = coverage_data.get('total_events_tested', 1)
        
        # Format coverage rate to avoid f-string issues
        coverage_rate_formatted = f"{coverage_rate_ml:.1f}"
        
        html += f"""
            <div class="chart-container" style="margin-top: 30px; background: #e3f2fd; border-left: 4px solid #0071C5;">
                <h3 style="color: #003e7e;">ML HEALTH-EVENT CORRELATION TRAINING DATA</h3>
                <p style="color: #003e7e; font-size: 1.05em; line-height: 1.8;">
                    This collection generated <strong>{total_samples} health samples</strong> with {16 if has_temp else 15} metrics each, 
                    captured at initialization, after each domain collection, and at finalization. This data trains ML models to correlate 
                    system health (CPU, memory, disk, temperature) with collection success/failure patterns.
                </p>
                <ul style="font-size: 1.05em; line-height: 1.8; color: #003e7e; margin-top: 15px;">
                    <li><strong>Anomaly Detection:</strong> Detect when high memory/CPU correlates with collection failures or timeouts</li>
                    <li><strong>Failure Prediction:</strong> Predict issues before they occur based on health metric trends (e.g., disk space < 10%)</li>
                    <li><strong>Performance Optimization:</strong> Identify optimal system conditions for faster, more reliable collections</li>
                    <li><strong>Quality Correlation:</strong> Link health metrics to event coverage rates and data quality scores</li>
                </ul>
                <div style="background: #fff; padding: 15px; margin-top: 15px; border-radius: 4px;">
                    <h4 style="color: #003e7e; margin-top: 0;">Training Dataset Summary:</h4>
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px;">
                        <div style="padding: 10px; background: #f0f8ff; border-radius: 4px;">
                            <strong>Samples:</strong> {total_samples}
                        </div>
                        <div style="padding: 10px; background: #f0f8ff; border-radius: 4px;">
                            <strong>Metrics per Sample:</strong> {16 if has_temp else 15}
                        </div>
                        <div style="padding: 10px; background: #f0f8ff; border-radius: 4px;">
                            <strong>Domains Collected:</strong> {len(coverage.get('domain_results', {}))}
                        </div>
                        <div style="padding: 10px; background: #f0f8ff; border-radius: 4px;">
                            <strong>Collection Mode:</strong> {analysis_results.get('health_history', {}).get('collection_mode', 'standard')}
                        </div>
                    </div>
                </div>
            </div>
"""
        
        html += f"""
            <div class="chart-container" style="margin-top: 30px;">
                <div style="background: #fff; padding: 15px; border-radius: 4px; border-left: 3px solid #28a745;">
                    <h4 style="color: #155724; margin-top: 0;">ML-GENERATED HEALTH-PERFORMANCE CORRELATION</h4>
                    <p style="color: #666; margin-bottom: 15px;">
                        Machine learning analysis of how system health metrics correlate with EMON collection performance.
                    </p>
"""
        
        html += f"""
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-bottom: 15px;">
                        <div style="background: {ml_color}15; padding: 15px; border-radius: 4px; border-left: 3px solid {ml_color};">
                            <div style="font-size: 2em; margin-bottom: 5px;">[ML]</div>
                            <div style="font-weight: bold; color: {ml_color}; font-size: 1.1em;">{ml_status}</div>
                            <div style="color: #666; margin-top: 5px;">ML Health Score: {ml_health_score}/100</div>
                        </div>
                        <div style="background: #e3f2fd; padding: 15px; border-radius: 4px; border-left: 3px solid #0071C5;">
                            <div style="font-size: 1.5em; margin-bottom: 5px;">[COVERAGE]</div>
                            <div style="font-weight: bold; color: #0071C5; font-size: 1.1em;">Event Coverage: {coverage_rate_formatted}%</div>
                            <div style="color: #666; margin-top: 5px;">{active_events_count}/{total_events_count} events active</div>
                        </div>
                    </div>
"""
        
        # Show ML correlations table if available
        if ml_correlations:
            html += """
                    <table style="width: 100%; border-collapse: collapse; margin-top: 10px;">
                        <thead>
                            <tr style="background: #f8f9fa; border-bottom: 2px solid #dee2e6;">
                                <th style="padding: 10px; text-align: left;">Metric</th>
                                <th style="padding: 10px; text-align: center;">Correlation Strength</th>
                                <th style="padding: 10px; text-align: left;">ML-Predicted Impact</th>
                            </tr>
                        </thead>
                        <tbody>
"""
            for corr in ml_correlations:
                metric_name = corr.get('metric', 'Unknown')
                # Try both 'strength' and 'correlation' keys for compatibility
                correlation = corr.get('strength', corr.get('correlation', 0))
                correlation_formatted = f"{correlation:.2f}"
                impact = corr.get('impact', 'Unknown')
                impact_color = corr.get('impact_color', '#666')
                
                html += f"""
                            <tr style="border-bottom: 1px solid #dee2e6;">
                                <td style="padding: 10px;"><strong>{metric_name}</strong></td>
                                <td style="padding: 10px; text-align: center;">{correlation_formatted}</td>
                                <td style="padding: 10px; color: {impact_color};">{impact}</td>
                            </tr>
"""
            html += """
                        </tbody>
                    </table>
"""
        
        # Show ML recommendations if available
        if ml_recommendations:
            html += """
                    <div style="background: #e3f2fd; padding: 15px; margin-top: 15px; border-radius: 4px; border-left: 3px solid #0071C5;">
                        <h5 style="color: #003e7e; margin-top: 0;">ML-GENERATED RECOMMENDATIONS:</h5>
                        <ul style="margin: 5px 0; padding-left: 20px; color: #003e7e;">
"""
            for rec in ml_recommendations:
                html += f"<li>{rec}</li>\n"
            html += """
                        </ul>
                    </div>
"""
        
        html += """
                </div>
            </div>
"""
        
        return html
    

