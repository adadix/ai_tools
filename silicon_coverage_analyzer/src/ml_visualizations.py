"""
ML Visualization Generator

Generates interactive charts and heatmaps for ML analysis:
- Training progress over time
- Event coverage heatmap by domain
- Anomaly detection scatter plot
- Pattern classification distribution
- Event clustering visualization
- Coverage prediction vs actual
"""

import json
import logging
import yaml
from pathlib import Path
from typing import Dict, List, Any

from src.ml_persistent_gaps import generate_persistent_gaps_analysis

logger = logging.getLogger(__name__)


class MLVisualizationGenerator:
    """Generates Chart.js visualizations for ML analysis."""
    
    def __init__(self, data_directory: str, product_id: str = None):
        """
        Initialize visualization generator.
        
        Args:
            data_directory: Path to ML data directory
            product_id: Optional product identifier for product-specific visualizations
        """
        self.data_dir = Path(data_directory)
        self.product_id = product_id
        
        # Load domain colors from config (dynamic)
        self.domain_colors = self._load_domain_colors()
        
        # Determine training log path based on product
        if product_id:
            self.training_log_path = self.data_dir / 'training_logs' / product_id / 'training_history.json'
        else:
            # Fallback to old path for backward compatibility
            self.training_log_path = self.data_dir / 'training_logs' / 'training_history.json'
    
    def _load_domain_colors(self) -> Dict[str, str]:
        """Load domain colors from domain_config.yaml."""
        try:
            config_path = Path('config/domain_config.yaml')
            if config_path.exists():
                with open(config_path, 'r') as f:
                    config = yaml.safe_load(f)
                    return config.get('domain_colors', {})
        except Exception as e:
            logger.warning(f"Could not load domain colors: {e}")
        
        # Fallback default colors
        return {
            'core': '#0071C5', 'p-core': '#0071C5', 'e-core': '#f39c12',
            'imc': '#27ae60', 'cbo': '#8e44ad', 'ncu': '#16a085',
            'power': '#e74c3c', 'uncore': '#388e3c'
        }
    
    def generate_all_visualizations(self, ml_analysis: Dict[str, Any]) -> str:
        """
        Generate all ML visualizations as HTML with Chart.js.
        
        Args:
            ml_analysis: ML analysis results dictionary
            
        Returns:
            str: HTML content with all visualizations
        """
        html = """
        <div style="margin-top: 25px;">
            <h2 class="section-title">ML Visualizations</h2>
            <p style="color: #6c757d; margin-bottom: 20px;">
                Interactive charts showing ML analysis insights
            </p>
        </div>
        """
        
        # Load training history
        training_history = self._load_training_history()
        
        # NOTE: Training Progress Chart moved to ML Training Strategy tab
        
        # 1. Coverage Heatmap by Domain
        html += self._generate_coverage_heatmap(training_history)
        
        # 2. Anomaly Confidence Map
        anomalies = ml_analysis.get('anomalies', {})
        if anomalies.get('by_domain'):
            html += self._generate_anomaly_scatter(anomalies)
        
        # 3. Pattern Distribution Over Time
        html += self._generate_pattern_distribution_chart(training_history)
        
        # 4. Event Clustering Visualization
        clusters = ml_analysis.get('clusters', {})
        if clusters.get('status') == 'success':
            html += self._generate_cluster_visualization(clusters)
        
        # 5. Prediction Accuracy Chart
        predictions = ml_analysis.get('predictions', {})
        if predictions.get('status') == 'success':
            html += self._generate_prediction_chart(predictions, training_history)
        
        # NOTE: Persistent Coverage Gaps Analysis moved to Action Items tab
        
        return html
    
    def _load_training_history(self) -> Dict:
        """Load training history from JSON file."""
        try:
            if self.training_log_path.exists():
                with open(self.training_log_path, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Error loading training history: {e}")
        
        return {'sessions': [], 'model_versions': {}, 'performance_metrics': {}}
    
    def _generate_training_progress_chart(self, training_history: Dict) -> str:
        """Generate line chart showing model accuracy over training sessions (all 9 models)."""
        sessions = training_history.get('sessions', [])
        if not sessions:
            return ""
        
        # Extract metrics from each session
        timestamps = []
        anomaly_rates = []
        predictor_r2 = []
        classifier_accuracy = []
        cluster_counts = []
        stress_r2 = []
        health_mae = []
        gap_accuracy = []
        workload_accuracy = []
        action_ndcg = []
        
        for session in sessions:
            timestamp = session.get('timestamp', '')[:10]  # YYYY-MM-DD
            timestamps.append(timestamp)
            
            metrics = session.get('metrics', {})
            anomaly_rates.append(metrics.get('anomaly_detector', {}).get('anomaly_rate', 0) * 100)
            predictor_r2.append(metrics.get('coverage_predictor', {}).get('r2_score', 0) * 100)
            classifier_accuracy.append(metrics.get('pattern_classifier', {}).get('accuracy', 0) * 100)
            
            clusterer = metrics.get('event_clusterer', {})
            cluster_counts.append(clusterer.get('clusters_found', 0))
            
            # Add stress correlation (Model 5) - uses MAE, convert to accuracy
            stress_mae = metrics.get('stress_correlation_model', {}).get('mean_absolute_error', 0)
            # Convert MAE to accuracy: 100% - MAE (lower MAE = better, cap at 100)
            stress_accuracy = max(0, min(100, 100 - (stress_mae * 100)))
            stress_r2.append(stress_accuracy)
            
            # Add health predictor (Model 6) - convert MAE to accuracy
            health_mae_val = metrics.get('health_predictor', {}).get('mae', 0)
            # Convert MAE to accuracy: 100% - MAE% (lower MAE = higher accuracy)
            health_accuracy = max(0, min(100, 100 - health_mae_val)) if health_mae_val > 0 else 0
            health_mae.append(health_accuracy)
            
            # Priority 1 models (Models 7-9)
            gap_prioritizer = metrics.get('gap_prioritizer', {})
            # Support both 'accuracy' and 'training_accuracy' keys
            gap_acc = gap_prioritizer.get('accuracy', 0) or gap_prioritizer.get('training_accuracy', 0)
            gap_accuracy.append(gap_acc * 100)
            
            workload_detector = metrics.get('workload_detector', {})
            # Support both 'accuracy' and 'training_accuracy' keys
            workload_acc = workload_detector.get('accuracy', 0) or workload_detector.get('training_accuracy', 0)
            workload_accuracy.append(workload_acc * 100)
            
            action_prioritizer = metrics.get('action_prioritizer', {})
            # Support both NDCG (feedback-based) and R² (autonomous pattern-based)
            action_score = action_prioritizer.get('ndcg_score', 0) or action_prioritizer.get('r2_score', 0)
            action_ndcg.append(action_score * 100)
        
        return f"""
        <div class="chart-container" style="margin-top: 25px;">
            <h3>Training Progress Over Time</h3>
            <p style="color: #666;">Model performance metrics across {len(sessions)} training sessions (9 models tracked)</p>
            <canvas id="trainingProgressChart" style="max-height: 400px;"></canvas>
        </div>
        
        <script>
        (function() {{
            const ctx = document.getElementById('trainingProgressChart').getContext('2d');
            new Chart(ctx, {{
                type: 'line',
                data: {{
                    labels: {json.dumps(timestamps)},
                    datasets: [
                        {{
                            label: 'Coverage Predictor R² (%)',
                            data: {json.dumps(predictor_r2)},
                            borderColor: '#2196F3',
                            backgroundColor: 'rgba(33, 150, 243, 0.1)',
                            tension: 0.4,
                            fill: true
                        }},
                        {{
                            label: 'Pattern Classifier Accuracy (%)',
                            data: {json.dumps(classifier_accuracy)},
                            borderColor: '#4CAF50',
                            backgroundColor: 'rgba(76, 175, 80, 0.1)',
                            tension: 0.4,
                            fill: true
                        }},
                        {{
                            label: 'Anomaly Detection Rate (%)',
                            data: {json.dumps(anomaly_rates)},
                            borderColor: '#FF9800',
                            backgroundColor: 'rgba(255, 152, 0, 0.1)',
                            tension: 0.4,
                            fill: true
                        }},
                        {{
                            label: 'Stress Correlation R² (%)',
                            data: {json.dumps(stress_r2)},
                            borderColor: '#E91E63',
                            backgroundColor: 'rgba(233, 30, 99, 0.1)',
                            tension: 0.4,
                            fill: true
                        }},
                        {{
                            label: 'Health Predictor Accuracy (%)',
                            data: {json.dumps(health_mae)},
                            borderColor: '#00796b',
                            backgroundColor: 'rgba(0, 121, 107, 0.1)',
                            tension: 0.4,
                            fill: true
                        }},
                        {{
                            label: 'Event Clusters Found',
                            data: {json.dumps(cluster_counts)},
                            borderColor: '#9C27B0',
                            backgroundColor: 'rgba(156, 39, 176, 0.1)',
                            tension: 0.4,
                            fill: false,
                            yAxisID: 'y1'
                        }},
                        {{
                            label: 'Gap Prioritizer Accuracy (%)',
                            data: {json.dumps(gap_accuracy)},
                            borderColor: '#6A1B9A',
                            backgroundColor: 'rgba(106, 27, 154, 0.1)',
                            tension: 0.4,
                            fill: true
                        }},
                        {{
                            label: 'Workload Detector Accuracy (%)',
                            data: {json.dumps(workload_accuracy)},
                            borderColor: '#00897B',
                            backgroundColor: 'rgba(0, 137, 123, 0.1)',
                            tension: 0.4,
                            fill: true
                        }},
                        {{
                            label: 'Action Prioritizer NDCG (%)',
                            data: {json.dumps(action_ndcg)},
                            borderColor: '#C62828',
                            backgroundColor: 'rgba(198, 40, 40, 0.1)',
                            tension: 0.4,
                            fill: true
                        }}
                    ]
                }},
                options: {{
                    responsive: true,
                    interaction: {{
                        mode: 'index',
                        intersect: false
                    }},
                    plugins: {{
                        legend: {{
                            position: 'top'
                        }},
                        tooltip: {{
                            callbacks: {{
                                label: function(context) {{
                                    let label = context.dataset.label || '';
                                    if (label) {{
                                        label += ': ';
                                    }}
                                    if (context.parsed.y !== null) {{
                                        label += context.parsed.y.toFixed(2);
                                        if (!label.includes('Clusters')) {{
                                            label += '%';
                                        }}
                                    }}
                                    return label;
                                }}
                            }}
                        }}
                    }},
                    scales: {{
                        y: {{
                            type: 'linear',
                            display: true,
                            position: 'left',
                            title: {{
                                display: true,
                                text: 'Percentage (%)'
                            }},
                            min: 0,
                            max: 100
                        }},
                        y1: {{
                            type: 'linear',
                            display: true,
                            position: 'right',
                            title: {{
                                display: true,
                                text: 'Cluster Count'
                            }},
                            grid: {{
                                drawOnChartArea: false
                            }}
                        }}
                    }}
                }}
            }});
        }})();
        </script>
        
        """
    
    def _generate_coverage_heatmap(self, training_history: Dict) -> str:
        """Generate heatmap showing coverage by domain over time."""
        sessions = training_history.get('sessions', [])
        if len(sessions) < 2:
            return ""
        
        # Extract domain coverage from raw data files
        timestamps = []
        domain_data = {}
        domains_set = set()
        
        # Get raw data directory (product-specific)
        if self.product_id:
            raw_data_dir = self.data_dir / 'raw_datasets' / self.product_id
        else:
            raw_data_dir = self.data_dir / 'raw_datasets'
            if not raw_data_dir.exists():
                raw_data_dir = self.data_dir / 'raw_data'  # Fallback
        
        if not raw_data_dir.exists():
            return ""
        
        # Load last 10 coverage files
        if self.product_id:
            coverage_files = sorted(raw_data_dir.glob('coverage_*.json'))[-10:]
        else:
            coverage_files = sorted(raw_data_dir.glob('*/coverage_*.json'))[-10:]
            if not coverage_files:
                coverage_files = sorted(raw_data_dir.glob('coverage_*.json'))[-10:]
        
        for coverage_file in coverage_files:
            try:
                with open(coverage_file, 'r') as f:
                    data = json.load(f)
                    
                # Extract timestamp from metadata
                metadata = data.get('metadata', {})
                timestamp = metadata.get('timestamp', '')[:10]  # YYYY-MM-DD
                if not timestamp:
                    continue
                    
                timestamps.append(timestamp)
                
                # Extract coverage results
                coverage_results = data.get('coverage_results', {})
                domain_results = coverage_results.get('domain_results', {})
                
                for domain, domain_info in domain_results.items():
                    domain_upper = domain.upper()
                    domains_set.add(domain_upper)
                    
                    if domain_upper not in domain_data:
                        domain_data[domain_upper] = []
                    
                    # Get activity_rate directly (already in percentage format)
                    activity_rate = domain_info.get('activity_rate', 0)
                    domain_data[domain_upper].append(activity_rate)
                        
            except Exception as e:
                logger.debug(f"Could not extract coverage from {coverage_file}: {e}")
                continue
        
        # Ensure all domains have same length (pad with 0 for missing data points)
        for domain in domains_set:
            while len(domain_data[domain]) < len(timestamps):
                domain_data[domain].append(0)
        
        # If no real data, return empty
        if not domains_set or not timestamps:
            return ""
        
        domains = sorted(domains_set)
        
        # Convert to heatmap-like visualization using stacked bars
        datasets = []
        colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22']
        
        for i, domain in enumerate(domains):
            datasets.append({
                'label': domain,
                'data': domain_data[domain],
                'backgroundColor': colors[i % len(colors)],
                'borderWidth': 1
            })
        
        return f"""
        <div class="chart-container" style="margin-top: 25px;">
            <h3> Coverage Heatmap by Domain</h3>
            <p style="color: #666;">Event coverage percentage across domains over time</p>
            <canvas id="coverageHeatmapChart" style="max-height: 450px;"></canvas>
        </div>
        
        <script>
        (function() {{
            const ctx = document.getElementById('coverageHeatmapChart').getContext('2d');
            new Chart(ctx, {{
                type: 'bar',
                data: {{
                    labels: {json.dumps(timestamps)},
                    datasets: {json.dumps(datasets)}
                }},
                options: {{
                    responsive: true,
                    plugins: {{
                        legend: {{
                            position: 'right'
                        }},
                        tooltip: {{
                            callbacks: {{
                                label: function(context) {{
                                    return context.dataset.label + ': ' + context.parsed.y.toFixed(1) + '%';
                                }}
                            }}
                        }}
                    }},
                    scales: {{
                        x: {{
                            stacked: false,
                            title: {{
                                display: true,
                                text: 'Training Sessions'
                            }}
                        }},
                        y: {{
                            stacked: false,
                            title: {{
                                display: true,
                                text: 'Coverage (%)'
                            }},
                            min: 0,
                            max: 100
                        }}
                    }}
                }}
            }});
        }})();
        </script>
        
        """
    
    def _generate_anomaly_scatter(self, anomalies: Dict) -> str:
        """Generate scatter plot of anomaly detection confidence."""
        by_domain = anomalies.get('by_domain', {})
        if not by_domain:
            return ""
        
        # Collect data points for scatter plot
        scatter_data = []
        
        # Use dynamically loaded domain colors
        for domain, domain_anomalies in by_domain.items():
            color = self.domain_colors.get(domain.lower(), '#999999')
            for anom in domain_anomalies:  # Show ALL anomalies
                # Use confidence and severity as x,y coordinates
                confidence = anom.get('confidence', 0.75) * 100  # Default 75% if not provided
                severity_map = {'high': 100, 'medium': 50, 'low': 25}
                severity_score = severity_map.get(anom.get('severity', 'medium'), 50)
                
                scatter_data.append({
                    'x': confidence,
                    'y': severity_score,
                    'event': anom.get('event', 'Unknown'),
                    'explanation': anom.get('explanation', 'No details'),
                    'domain': domain,
                    'color': color
                })
        
        if not scatter_data:
            return ""
        
        # Group by domain for datasets
        datasets = {}
        for point in scatter_data:
            domain = point['domain']
            if domain not in datasets:
                datasets[domain] = {
                    'label': domain.upper(),
                    'data': [],
                    'backgroundColor': point['color'],
                    'pointRadius': 6,
                    'pointHoverRadius': 8
                }
            datasets[domain]['data'].append({
                'x': point['x'], 
                'y': point['y'],
                'event': point['event'],
                'explanation': point['explanation']
            })
        
        datasets_list = list(datasets.values())
        
        return f"""
        <div class="chart-container" style="margin-top: 25px;">
            <h3> Anomaly Detection Confidence Map</h3>
            <p style="color: #666;">Event anomalies plotted by confidence level and severity</p>
            <canvas id="anomalyScatterChart" style="max-height: 450px;"></canvas>
        </div>
        
        <script>
        (function() {{
            const ctx = document.getElementById('anomalyScatterChart').getContext('2d');
            new Chart(ctx, {{
                type: 'scatter',
                data: {{
                    datasets: {json.dumps(datasets_list)}
                }},
                options: {{
                    responsive: true,
                    plugins: {{
                        legend: {{
                            position: 'top'
                        }},
                        tooltip: {{
                            callbacks: {{
                                title: function(context) {{
                                    const point = context[0].raw;
                                    return point.event || 'Unknown Event';
                                }},
                                label: function(context) {{
                                    const point = context.raw;
                                    return [
                                        context.dataset.label + ' Domain',
                                        'Confidence: ' + context.parsed.x.toFixed(1) + '%',
                                        'Severity: ' + (context.parsed.y >= 75 ? 'HIGH' : context.parsed.y >= 40 ? 'MEDIUM' : 'LOW'),
                                        'Details: ' + (point.explanation || 'N/A')
                                    ];
                                }}
                            }}
                        }}
                    }},
                    scales: {{
                        x: {{
                            title: {{
                                display: true,
                                text: 'Confidence (%)'
                            }},
                            min: 0,
                            max: 100
                        }},
                        y: {{
                            title: {{
                                display: true,
                                text: 'Severity Score'
                            }},
                            min: 0,
                            max: 100,
                            ticks: {{
                                callback: function(value) {{
                                    if (value >= 75) return 'HIGH';
                                    if (value >= 40) return 'MEDIUM';
                                    return 'LOW';
                                }}
                            }}
                        }}
                    }}
                }}
            }});
        }})();
        </script>
        """
    
    def _generate_pattern_distribution_chart(self, training_history: Dict) -> str:
        """Generate stacked bar chart of pattern classification over time."""
        sessions = training_history.get('sessions', [])
        if len(sessions) < 2:
            return ""
        
        timestamps = []
        pattern_data = {
            'low_activity': [],
            'medium_activity': [],
            'high_activity': [],
            'full_toggle': []
        }
        
        # Get raw data directory (product-specific)
        if self.product_id:
            raw_data_dir = self.data_dir / 'raw_datasets' / self.product_id
        else:
            raw_data_dir = self.data_dir / 'raw_datasets'
            if not raw_data_dir.exists():
                raw_data_dir = self.data_dir / 'raw_data'  # Fallback
        
        if not raw_data_dir.exists():
            return ""
        
        # Load last 8 coverage files
        if self.product_id:
            coverage_files = sorted(raw_data_dir.glob('coverage_*.json'))[-8:]
        else:
            coverage_files = sorted(raw_data_dir.glob('*/coverage_*.json'))[-8:]
            if not coverage_files:
                coverage_files = sorted(raw_data_dir.glob('coverage_*.json'))[-8:]
        
        for coverage_file in coverage_files:
            try:
                with open(coverage_file, 'r') as f:
                    data = json.load(f)
                    
                # Extract timestamp from metadata
                metadata = data.get('metadata', {})
                timestamp = metadata.get('timestamp', '')[:10]  # YYYY-MM-DD
                if not timestamp:
                    continue
                    
                timestamps.append(timestamp)
                
                # Count events by activity pattern
                low = medium = high = full = 0
                
                coverage_results = data.get('coverage_results', {})
                domain_results = coverage_results.get('domain_results', {})
                
                for domain_info in domain_results.values():
                    # Process both active and inactive events
                    active_events = domain_info.get('active_events', [])
                    inactive_events = domain_info.get('inactive_events', [])
                    
                    for event in active_events:
                        total_count = event.get('total_activity', 0)
                        
                        if total_count < 1000:
                            low += 1
                        elif total_count < 10000:
                            medium += 1
                        elif total_count < 100000:
                            high += 1
                        else:
                            full += 1
                    
                    # Inactive events count as low activity
                    low += len(inactive_events)
                
                pattern_data['low_activity'].append(low)
                pattern_data['medium_activity'].append(medium)
                pattern_data['high_activity'].append(high)
                pattern_data['full_toggle'].append(full)
                
            except Exception as e:
                logger.debug(f"Could not extract patterns from {coverage_file}: {e}")
                # Append zeros for failed file
                pattern_data['low_activity'].append(0)
                pattern_data['medium_activity'].append(0)
                pattern_data['high_activity'].append(0)
                pattern_data['full_toggle'].append(0)
        
        # If no real data, return empty
        if not timestamps or all(sum(pattern_data[k]) == 0 for k in pattern_data):
            return ""
        
        datasets = [
            {'label': 'Low Activity', 'data': pattern_data['low_activity'], 'backgroundColor': '#dc3545'},
            {'label': 'Medium Activity', 'data': pattern_data['medium_activity'], 'backgroundColor': '#ffc107'},
            {'label': 'High Activity', 'data': pattern_data['high_activity'], 'backgroundColor': '#28a745'},
            {'label': 'Full Toggle', 'data': pattern_data['full_toggle'], 'backgroundColor': '#17a2b8'}
        ]
        
        return f"""
        <div class="chart-container" style="margin-top: 25px;">
            <h3> Pattern Classification Distribution</h3>
            <p style="color: #666;">Event behavior patterns across training sessions</p>
            <canvas id="patternDistributionChart" style="max-height: 400px;"></canvas>
        </div>
        
        <script>
        (function() {{
            const ctx = document.getElementById('patternDistributionChart').getContext('2d');
            new Chart(ctx, {{
                type: 'bar',
                data: {{
                    labels: {json.dumps(timestamps)},
                    datasets: {json.dumps(datasets)}
                }},
                options: {{
                    responsive: true,
                    plugins: {{
                        legend: {{
                            position: 'top'
                        }},
                        tooltip: {{
                            callbacks: {{
                                label: function(context) {{
                                    return context.dataset.label + ': ' + context.parsed.y + '%';
                                }}
                            }}
                        }}
                    }},
                    scales: {{
                        x: {{
                            stacked: true,
                            title: {{
                                display: true,
                                text: 'Training Sessions'
                            }}
                        }},
                        y: {{
                            stacked: true,
                            title: {{
                                display: true,
                                text: 'Event Percentage (%)'
                            }},
                            min: 0,
                            max: 100
                        }}
                    }}
                }}
            }});
        }})();
        </script>
        """
    
    def _generate_cluster_visualization(self, clusters: Dict) -> str:
        """Generate bubble chart visualization of event clusters."""
        cluster_summary = clusters.get('cluster_summary', [])
        if not cluster_summary:
            return ""
        
        # Create bubble data
        bubble_data = []
        colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f']
        
        for i, cluster in enumerate(cluster_summary[:8]):  # Max 8 clusters
            bubble_data.append({
                'x': cluster.get('avg_toggle_rate', 0) * 100,
                'y': cluster.get('avg_count', 0),
                'r': min(cluster.get('size', 1) * 2, 30),  # Bubble size
                'label': f"Cluster {cluster.get('cluster_id', i)}",
                'backgroundColor': colors[i % len(colors)]
            })
        
        return f"""
        <div class="chart-container" style="margin-top: 25px;">
            <h3> Event Clustering Visualization</h3>
            <p style="color: #666;">Event groups based on behavioral similarity (bubble size = cluster size)</p>
            <canvas id="clusterBubbleChart" style="max-height: 450px;"></canvas>
        </div>
        
        <script>
        (function() {{
            const ctx = document.getElementById('clusterBubbleChart').getContext('2d');
            const bubbleData = {json.dumps(bubble_data)};
            
            new Chart(ctx, {{
                type: 'bubble',
                data: {{
                    datasets: bubbleData.map(point => ({{
                        label: point.label,
                        data: [{{x: point.x, y: point.y, r: point.r}}],
                        backgroundColor: point.backgroundColor
                    }}))
                }},
                options: {{
                    responsive: true,
                    plugins: {{
                        legend: {{
                            position: 'right'
                        }},
                        tooltip: {{
                            callbacks: {{
                                label: function(context) {{
                                    const point = context.raw;
                                    return context.dataset.label + ': Toggle=' + point.x.toFixed(1) + '%, Avg Count=' + point.y.toFixed(0) + ', Size=' + Math.round(point.r/2);
                                }}
                            }}
                        }}
                    }},
                    scales: {{
                        x: {{
                            title: {{
                                display: true,
                                text: 'Average Toggle Rate (%)'
                            }},
                            min: 0,
                            max: 100
                        }},
                        y: {{
                            title: {{
                                display: true,
                                text: 'Average Event Count (log scale)'
                            }},
                            type: 'logarithmic'
                        }}
                    }}
                }}
            }});
        }})();
        </script>
        """
    
    def _generate_prediction_chart(self, predictions: Dict, training_history: Dict) -> str:
        """Generate chart comparing predicted vs actual coverage."""
        prediction_history = predictions.get('historical_predictions', [])
        if not prediction_history:
            return ""
        
        timestamps = []
        predicted = []
        actual = []
        
        for entry in prediction_history[-10:]:  # Last 10 predictions
            timestamps.append(entry.get('timestamp', '')[:10])
            predicted.append(entry.get('predicted_coverage', 0) * 100)
            actual.append(entry.get('actual_coverage', 0) * 100)
        
        return f"""
        <div class="chart-container" style="margin-top: 25px;">
            <h3> Coverage Prediction vs Actual</h3>
            <p style="color: #666;">ML model prediction accuracy over time</p>
            <canvas id="predictionChart" style="max-height: 400px;"></canvas>
        </div>
        
        <script>
        (function() {{
            const ctx = document.getElementById('predictionChart').getContext('2d');
            new Chart(ctx, {{
                type: 'line',
                data: {{
                    labels: {json.dumps(timestamps)},
                    datasets: [
                        {{
                            label: 'Predicted Coverage (%)',
                            data: {json.dumps(predicted)},
                            borderColor: '#FF9800',
                            backgroundColor: 'rgba(255, 152, 0, 0.1)',
                            borderDash: [5, 5],
                            tension: 0.4
                        }},
                        {{
                            label: 'Actual Coverage (%)',
                            data: {json.dumps(actual)},
                            borderColor: '#4CAF50',
                            backgroundColor: 'rgba(76, 175, 80, 0.1)',
                            tension: 0.4
                        }}
                    ]
                }},
                options: {{
                    responsive: true,
                    plugins: {{
                        legend: {{
                            position: 'top'
                        }},
                        tooltip: {{
                            callbacks: {{
                                label: function(context) {{
                                    return context.dataset.label + ': ' + context.parsed.y.toFixed(2) + '%';
                                }}
                            }}
                        }}
                    }},
                    scales: {{
                        y: {{
                            title: {{
                                display: true,
                                text: 'Coverage Percentage (%)'
                            }},
                            min: 0,
                            max: 100
                        }}
                    }}
                }}
            }});
        }})();
        </script>
        """


# ============================================================================
# NEW DASHBOARD ENHANCEMENT FUNCTIONS
# ============================================================================



def render_top_gaps_table(gaps: list, max_rows: int = 10, show_emon: bool = False, emon_commands: dict = None) -> str:
    """
    Render top coverage gaps table with workload recommendations.
    
    Args:
        gaps: List of gap dicts with keys: event_name, domain, toggle_rate, severity, recommended_workload, confidence
        max_rows: Maximum number of rows to display
        show_emon: Whether to show EMON command column with copy buttons
        emon_commands: Dict mapping event names to EMON commands
        
    Returns:
        HTML string with styled table
    """
    if not gaps:
        return """
        <div style="background: #d4edda; padding: 20px; border-radius: 6px; border-left: 4px solid #28a745; margin: 20px 0;">
            <h4 style="color: #155724; margin: 0 0 10px 0;"> No Critical Gaps Found!</h4>
            <p style="color: #155724; margin: 0;">All high-priority events are toggling. Excellent coverage!</p>
        </div>
"""
    
    emon_header = '<th style="padding: 12px; text-align: left; font-weight: 600; color: #495057;">EMON Command</th>' if show_emon else ''
    
    html = f"""
    <div style="background: white; padding: 25px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); margin: 20px 0;">
        <div style="max-height: 600px; overflow-y: auto; border: 1px solid #ddd; border-radius: 4px;">
            <table id="action-items-table" style="width: 100%; border-collapse: collapse; margin: 0;">
                <thead style="background: #f8f9fa; border-bottom: 2px solid #dee2e6; position: sticky; top: 0; z-index: 10;">
                    <tr>
                        <th style="padding: 12px; text-align: left; font-weight: 600; color: #495057; background: #f8f9fa;">Event</th>
                        <th style="padding: 12px; text-align: left; font-weight: 600; color: #495057; background: #f8f9fa;">Domain</th>
                        <th style="padding: 12px; text-align: center; font-weight: 600; color: #495057; background: #f8f9fa;">Toggle Rate</th>
                        <th style="padding: 12px; text-align: center; font-weight: 600; color: #495057; background: #f8f9fa;">Severity</th>
                        <th style="padding: 12px; text-align: left; font-weight: 600; color: #495057; background: #f8f9fa;">Recommended Workload</th>
                        {emon_header}
                    </tr>
                </thead>
                <tbody>
"""
    
    severity_colors = {
        'critical': '#d32f2f',
        'high': '#f57c00',
        'medium': '#fbc02d',
        'low': '#388e3c'
    }
    
    for i, gap in enumerate(gaps[:max_rows], 1):
        event_name = gap.get('event_name', 'Unknown')
        domain = gap.get('domain', 'Unknown')
        toggle_rate = gap.get('toggle_rate', 0)
        severity = gap.get('severity', 'medium').lower()
        recommended_workload = gap.get('recommended_workload', '')
        confidence = gap.get('confidence', 0)
        
        # Ensure confidence is numeric
        try:
            confidence = float(confidence) if confidence else 0
        except (ValueError, TypeError):
            confidence = 0
        
        severity_color = severity_colors.get(severity, '#999')
        
        # Add ML badge if this gap was ML-classified (has confidence data)
        ml_classified = gap.get('ml_classified', False)
        ml_badge = '<span style="background: #4caf50; color: white; padding: 2px 6px; border-radius: 3px; font-size: 0.7em; font-weight: 600;" title="Priority classified by ML model">[ML] ML</span>' if ml_classified else ''
        
        # Determine stress level from recommended workload
        stress_level = 'medium'  # default
        if recommended_workload:
            workload_lower = recommended_workload.lower()
            if 'idle' in workload_lower or 'no' in workload_lower:
                stress_level = 'idle'
            elif any(keyword in workload_lower for keyword in ['light', 'minimal', 'low']):
                stress_level = 'low'
            elif any(keyword in workload_lower for keyword in ['stress', 'heavy', 'intensive', 'prime95', 'linpack', 'memtest']):
                stress_level = 'stress'
            elif any(keyword in workload_lower for keyword in ['high', 'maximum', 'full']):
                stress_level = 'high'
            else:
                stress_level = 'medium'
        
        # Format workload with confidence badge - ONLY if we have real data
        if recommended_workload and recommended_workload.strip():
            # We have a real workload recommendation
            if confidence > 0:
                workload_html = f"""
                    <span style="font-weight: 600; color: #0071c5;">{recommended_workload}</span>
                    <span style="background: #e3f2fd; color: #1976d2; padding: 2px 8px; border-radius: 10px; font-size: 0.8em; margin-left: 5px;">
                        {confidence:.0f}% confident
                    </span>
"""
            else:
                workload_html = f'<span style="color: #666;">{recommended_workload}</span>'
        else:
            # No workload recommendation available - leave empty
            workload_html = '<span style="color: #999; font-style: italic;">—</span>'
        
        # EMON command column with copy button
        emon_cell = ''
        if show_emon and emon_commands:
            emon_cmd = emon_commands.get(event_name, '')
            if emon_cmd:
                # Escape quotes for JavaScript
                emon_cmd_escaped = emon_cmd.replace("'", "\\'").replace('"', '&quot;')
                emon_cell = f"""
                    <td style="padding: 10px;">
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <code style="background: #f5f5f5; padding: 4px 8px; border-radius: 3px; font-size: 0.85em; flex: 1; overflow-x: auto; white-space: nowrap;">
                                {emon_cmd[:50]}{'...' if len(emon_cmd) > 50 else ''}
                            </code>
                            <button onclick="copyEmonCommand('{emon_cmd_escaped}')" 
                                    style="padding: 6px 12px; background: #0071c5; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 0.85em; white-space: nowrap;">
                                 Copy
                            </button>
                        </div>
                    </td>
"""
            else:
                emon_cell = '<td style="padding: 10px; color: #999; font-style: italic;">—</td>'
        
        html += f"""
                <tr style="border-bottom: 1px solid #e0e0e0;" data-domain="{domain.lower()}" data-severity="{severity.lower()}" data-stress="{stress_level}">
                    <td style="padding: 10px;"><code style="background: #f5f5f5; padding: 2px 6px; border-radius: 3px; font-size: 0.9em;">{event_name}</code></td>
                    <td style="padding: 10px; color: #666;">{domain.upper()}</td>
                    <td style="padding: 10px; text-align: center;">
                        <span style="color: #d32f2f; font-weight: 600;">{toggle_rate:.1f}%</span>
                    </td>
                    <td style="padding: 10px; text-align: center;">
                        <div style="display: flex; align-items: center; justify-content: center; gap: 5px;">
                            <span style="background: {severity_color}; color: white; padding: 4px 10px; border-radius: 12px; font-size: 0.85em; font-weight: 600;">
                                {severity.upper()}
                            </span>
                            {ml_badge}
                        </div>
                    </td>
                    <td style="padding: 10px;">{workload_html}</td>
                    {emon_cell}
                </tr>
"""
    
    html += """
            </tbody>
        </table>
        </div>
    </div>
"""
    return html
def render_recommended_workloads(recommendations: list, max_items: int = 3) -> str:
    """
    Render recommended workloads box with confidence scores.
    
    Args:
        recommendations: List of dicts with keys: workload, confidence, gaps_addressed
        max_items: Maximum recommendations to show
        
    Returns:
        HTML string with workload recommendation cards
    """
    if not recommendations:
        return """
        <div style="background: #fff3cd; padding: 20px; border-radius: 6px; border-left: 4px solid #ffc107; margin: 20px 0;">
            <h4 style="color: #856404; margin: 0 0 10px 0;">[TIP] Workload Recommendations</h4>
            <p style="color: #856404; margin: 0;">ML models need more training data to generate workload recommendations. Run additional collections.</p>
        </div>
"""
    
    html = """
    <div style="background: white; padding: 25px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); margin: 20px 0;">
        <h4 style="color: #0071c5; margin: 0 0 15px 0;">[TIP] Recommended Workloads to Close Gaps</h4>
        <div style="display: grid; gap: 15px;">
"""
    
    for i, rec in enumerate(recommendations[:max_items], 1):
        workload = rec.get('workload', 'Unknown')
        confidence = rec.get('confidence', 0)
        gaps_addressed = rec.get('gaps_addressed', 0)
        
        # Confidence color
        if confidence >= 80:
            conf_color = '#28a745'
            conf_label = 'High'
        elif confidence >= 60:
            conf_color = '#ffc107'
            conf_label = 'Medium'
        else:
            conf_color = '#dc3545'
            conf_label = 'Low'
        
        html += f"""
            <div style="background: #f8f9fa; padding: 15px; border-radius: 6px; border-left: 4px solid {conf_color};">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                    <div>
                        <span style="font-size: 1.2em; font-weight: 600; color: #333;">#{i} {workload}</span>
                    </div>
                    <div style="text-align: right;">
                        <div style="font-size: 0.85em; color: #666;">Confidence</div>
                        <div style="font-size: 1.3em; font-weight: 700; color: {conf_color};">{confidence:.0f}%</div>
                    </div>
                </div>
                <div style="color: #666; font-size: 0.9em;">
                    <strong>Impact:</strong> Addresses {gaps_addressed} coverage gap{'' if gaps_addressed == 1 else 's'}
                </div>
            </div>
"""
    
    html += """
        </div>
    </div>
"""
    return html


def render_explain_panel(explanations: list) -> str:
    """
    Render ML explanation panel (SHAP-like rationale).
    
    Args:
        explanations: List of explanation strings or dicts with 'reason' and 'impact'
        
    Returns:
        HTML string with explanation panel
    """
    if not explanations:
        return ""
    
    html = """
    <div style="background: #e3f2fd; padding: 20px; border-radius: 6px; border-left: 4px solid #1976d2; margin: 20px 0;">
        <h4 style="color: #1565c0; margin: 0 0 15px 0;">[ML] ML Insight: Why is coverage at this level?</h4>
        <ul style="margin: 0; padding-left: 20px; color: #0d47a1; line-height: 1.8;">
"""
    
    for exp in explanations:
        if isinstance(exp, dict):
            reason = exp.get('reason', '')
            impact = exp.get('impact', '')
            html += f"            <li><strong>{reason}</strong>: {impact}</li>\n"
        else:
            html += f"            <li>{exp}</li>\n"
    
    html += """
        </ul>
    </div>
"""
    return html


def render_heatmap(matrix: dict, x_labels: list, y_labels: list, legend: dict, chart_id: str = None) -> str:
    """
    Render correlation heatmap with color-coded cells.
    
    Args:
        matrix: 2D dict or list of lists with correlation values
        x_labels: X-axis labels
        y_labels: Y-axis labels
        legend: Dict with 'strong', 'medium', 'weak' thresholds and colors
        chart_id: Optional unique chart ID
        
    Returns:
        HTML string with heatmap table
    """
    if not chart_id:
        chart_id = f"heatmap_{hash(str(matrix)) % 100000}"
    
    # Convert matrix to 2D list if dict
    if isinstance(matrix, dict):
        matrix_2d = []
        for y_label in y_labels:
            row = []
            for x_label in x_labels:
                row.append(matrix.get(y_label, {}).get(x_label, 0))
            matrix_2d.append(row)
    else:
        matrix_2d = matrix
    
    html = f"""
    <div id="{chart_id}" style="background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); margin: 20px 0; max-height: 600px; overflow-x: auto; overflow-y: auto;">
        <table style="width: 100%; border-collapse: collapse; font-size: 0.9em;">
            <thead>
                <tr style="background: #f8f9fa;">
                    <th style="padding: 10px; border: 1px solid #dee2e6; position: sticky; left: 0; top: 0; background: #f8f9fa; z-index: 2;"></th>
"""
    
    for x_label in x_labels:
        html += f'                    <th style="padding: 10px; border: 1px solid #dee2e6; text-align: center; position: sticky; top: 0; background: #f8f9fa; z-index: 1;">{x_label}</th>\n'
    
    html += """
                </tr>
            </thead>
            <tbody>
"""
    
    for i, y_label in enumerate(y_labels):
        html += f"""
                <tr>
                    <td style="padding: 10px; border: 1px solid #dee2e6; font-weight: 600; position: sticky; left: 0; background: #fff;">{y_label}</td>
"""
        
        for j, value in enumerate(matrix_2d[i]):
            # Determine color based on legend thresholds
            if value >= legend.get('strong_threshold', 0.7):
                bg_color = legend.get('strong_color', '#d32f2f')
                text_color = '#fff'
            elif value >= legend.get('medium_threshold', 0.4):
                bg_color = legend.get('medium_color', '#ffc107')
                text_color = '#000'
            else:
                bg_color = legend.get('weak_color', '#28a745')
                text_color = '#fff'
            
            html += f"""
                    <td style="padding: 10px; border: 1px solid #dee2e6; text-align: center; background: {bg_color}; color: {text_color}; font-weight: 600;">
                        {value:.2f}
                    </td>
"""
        
        html += "                </tr>\n"
    
    html += """
            </tbody>
        </table>
        <div style="margin-top: 15px; padding: 10px; background: #f8f9fa; border-radius: 4px; font-size: 0.85em;">
            <strong>Legend:</strong>
            <span style="margin-left: 10px; color: """ + legend.get('strong_color', '#d32f2f') + """;">⬛ Strong (≥""" + str(legend.get('strong_threshold', 0.7)) + """)</span>
            <span style="margin-left: 10px; color: """ + legend.get('medium_color', '#ffc107') + """;">⬛ Medium (""" + str(legend.get('medium_threshold', 0.4)) + """-""" + str(legend.get('strong_threshold', 0.7)) + """)</span>
            <span style="margin-left: 10px; color: """ + legend.get('weak_color', '#28a745') + """;">⬛ Weak (<""" + str(legend.get('medium_threshold', 0.4)) + """)</span>
        </div>
    </div>
"""
    return html


def render_line_chart(series_list: list, x_ticks: list, options: dict = None, chart_id: str = None) -> str:
    """
    Render multi-series line chart with Chart.js.
    
    Args:
        series_list: List of dicts with keys: label, data, color
        x_ticks: X-axis tick labels
        options: Optional Chart.js options override
        chart_id: Optional unique chart ID
        
    Returns:
        HTML string with line chart
    """
    import json
    
    if not chart_id:
        chart_id = f"lineChart_{hash(str(series_list)) % 100000}"
    
    # Default options
    default_options = {
        'responsive': True,
        'maintainAspectRatio': False,
        'plugins': {
            'legend': {'position': 'top'},
            'tooltip': {
                'mode': 'index',
                'intersect': False
            }
        },
        'scales': {
            'y': {
                'beginAtZero': True,
                'max': 100,
                'ticks': {
                    'callback': "function(value) { return value + '%'; }"
                }
            }
        }
    }
    
    if options:
        default_options.update(options)
    
    # Build datasets
    datasets = []
    for series in series_list:
        datasets.append({
            'label': series.get('label', 'Series'),
            'data': series.get('data', []),
            'borderColor': series.get('borderColor', series.get('color', '#0071c5')),
            'backgroundColor': series.get('backgroundColor', series.get('color', '#0071c5') + '33'),
            'tension': series.get('tension', 0.3),
            'fill': series.get('fill', False)
        })
    
    html = f"""
    <div style="background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); margin: 20px 0;">
        <canvas id="{chart_id}" style="max-height: 400px;"></canvas>
    </div>
    
    <script>
    (function() {{
        const ctx = document.getElementById('{chart_id}');
        if (ctx) {{
            new Chart(ctx, {{
                type: 'line',
                data: {{
                    labels: {json.dumps(x_ticks)},
                    datasets: {json.dumps(datasets)}
                }},
                options: {json.dumps(default_options)}
            }});
        }}
    }})();
    </script>
"""
    return html
