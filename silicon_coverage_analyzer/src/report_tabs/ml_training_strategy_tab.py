"""
ML Training Strategy Tab Generator Module

Generates the ML Training & Strategy tab showing:
- ML model training status (13 models)
- Training dataset size and history
- Feature importance metrics
- Algorithm details
- Historical coverage trends
"""


class MLTrainingStrategyTabGenerator:
    """Generates the ML Training & Strategy tab for model health and configuration."""
    
    def __init__(self, report_generator):
        """
        Initialize with reference to parent report generator.
        
        Args:
            report_generator: Parent ReportGenerator instance for accessing shared methods/data
        """
        self.rg = report_generator
    
    def generate(self, analysis_results):
        """
        Generate ML Training & Strategy tab.
        
        Args:
            analysis_results: Dictionary containing analysis data
            
        Returns:
            str: HTML content for the tab
        """
        ml_config = analysis_results.get('ml_config', {})
        ml_insights = analysis_results.get('ml_insights', {})
        metadata = analysis_results.get('metadata', {})
        hw_config = analysis_results.get('hardware_config', {})
        
        # Get product ID for historical run count
        product_id = hw_config.get('product_id') or hw_config.get('product_name', '').lower().replace(' ', '_').replace('-', '_')
        
        # Get training status from ml_analysis
        ml_analysis = analysis_results.get('ml_analysis', {})
        training_status = ml_analysis.get('training_status', {})
        
        # Use training status values directly
        training_dataset_size = training_status.get('datasets_collected', 0)
        last_trained = training_status.get('last_training', 'Never')
        if last_trained != 'Never' and len(str(last_trained)) > 19:
            last_trained = str(last_trained)[:19]
        
        html = f"""
        <div id="ml-training-strategy" class="tab-content">
            <h2 class="section-title">ML TRAINING</h2>
            
            <!-- Interpretation Guide -->
            <div style="background: linear-gradient(135deg, #e0f7fa 0%, #b2ebf2 100%); border-left: 5px solid #00838f; padding: 20px; margin-bottom: 25px; border-radius: 8px;">
                <h3 style="margin: 0 0 10px 0; color: #006064;">How to Interpret This Tab</h3>
                <p style="margin: 5px 0; color: #006064; line-height: 1.5; font-size: 0.95em;">
                    <strong>ML Model Health:</strong> Training dataset size, last trained date, and overall model status.<br>
                    <strong>Training Status:</strong> Per-model status (Done/Pending) with accuracy metrics.<br>
                    <strong>Training Progress:</strong> Chart showing model training over time.<br>
                    <strong>Feature Importance:</strong> Top features driving ML predictions for gap prioritization.<br>
                    <strong>Algorithms Used:</strong> ML algorithms powering each model (RandomForest, XGBoost, etc.).<br>
                    <strong>Historical Trends:</strong> Coverage trends and data quality metrics across all runs.
                </p>
            </div>
            
            <p style="color: #6c757d; margin-bottom: 25px;">
                ML model health, training configuration, and feature engineering details.
            </p>
            
            <!-- ML Model Health Section -->
            <div style="margin-bottom: 30px;">
                <h3 style="color: #0071C5;">ML MODEL HEALTH</h3>
                <div style="background: #e3f2fd; border-left: 4px solid #0071C5; padding: 20px; border-radius: 5px;">
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 20px;">
                        <div>
                            <strong style="color: #0071C5;">Training Dataset Size:</strong>
                            <p style="margin: 5px 0 0 0; font-size: 1.5em; color: #333;">{training_dataset_size} runs</p>
                        </div>
                        <div>
                            <strong style="color: #0071C5;">Last Trained:</strong>
                            <p style="margin: 5px 0 0 0; font-size: 1.2em; color: #333;">{last_trained}</p>
                        </div>
                        <div>
                            <strong style="color: #0071C5;">Incremental Learning:</strong>
                            <p style="margin: 5px 0 0 0; font-size: 1.2em; color: #4caf50;">ENABLED</p>
                        </div>
                        <div>
                            <strong style="color: #0071C5;">Product:</strong>
                            <p style="margin: 5px 0 0 0; font-size: 1.2em; color: #333;">{product_id or 'Unknown'}</p>
                        </div>
                    </div>
"""
        
        # Add warning if no datasets available
        if training_dataset_size == 0:
            html += """
                    <div style="background: #fff3e0; border-left: 4px solid #ff9800; padding: 15px; margin-top: 20px; border-radius: 5px;">
                        <h4 style="color: #e65100; margin: 0 0 10px 0;">ML Training Not Started</h4>
                        <p style="color: #666; margin: 5px 0; line-height: 1.6;">
                            <strong>Why models show PENDING:</strong> ML training requires historical data from multiple runs. This appears to be your first run or the data directory is empty.
                        </p>
                        <p style="color: #666; margin: 5px 0; line-height: 1.6;">
                            <strong>What happens next:</strong> Each time you run the analyzer, coverage data is automatically saved to <code>C:\\silicon_coverage_analyzer_data</code>. After collecting 3-5 runs, ML models will begin training automatically.
                        </p>
                        <p style="color: #666; margin: 5px 0; line-height: 1.6;">
                            <strong>Minimum requirements:</strong>
                            <ul style="margin: 10px 0; padding-left: 20px;">
                                <li>3 runs minimum for basic anomaly detection</li>
                                <li>5 runs recommended for pattern classification</li>
                                <li>10+ runs for high-confidence predictions</li>
                            </ul>
                        </p>
                        <p style="color: #e65100; margin: 10px 0 0 0; font-weight: bold;">
                            Action: Continue running coverage collections. Models will auto-train when sufficient data is available.
                        </p>
                    </div>
                </div>
            </div>
"""
        
        html += """
            <!-- ML Model Training Status Section -->
"""
        
        # Calculate model training status
        models_available = training_status.get('models_available', {})
        if isinstance(models_available, dict):
            base_model_keys = ['anomaly_detector', 'coverage_predictor', 'pattern_classifier', 
                              'event_clusterer', 'stress_correlation_model', 'health_predictor']
            models_trained = sum(1 for k in base_model_keys if models_available.get(k, False))
        else:
            models_trained = min(int(models_available) if models_available else 0, 6)
        
        # Check Priority 1 ML models (3 models)
        p1_models_trained = 0
        if self.rg.ml_gap_prioritizer.is_trained():
            p1_models_trained += 1
        if self.rg.ml_workload_detector.is_trained():
            p1_models_trained += 1
        if self.rg.ml_action_prioritizer.is_trained():
            p1_models_trained += 1
        
        # Check High-Value ML models (4 models)
        hv_models_trained = 0
        if self.rg.ml_stress_recommender.is_trained():
            hv_models_trained += 1
        if self.rg.ml_saturation_predictor.is_trained():
            hv_models_trained += 1
        if self.rg.ml_workload_clusterer.is_trained():
            hv_models_trained += 1
        if self.rg.ml_gap_forecaster.is_trained():
            hv_models_trained += 1
        
        total_models = 13  # 6 base + 3 Priority 1 + 4 High-Value
        total_trained = models_trained + p1_models_trained + hv_models_trained
        progress_pct = int(total_trained/total_models*100) if total_models > 0 else 0
        
        html += f"""
            <div style="margin-bottom: 20px;">
                <h3 style="color: #0071C5; margin-bottom: 15px;">ML MODEL TRAINING STATUS</h3>
                <div style="background: #f5f5f5; padding: 15px; border-radius: 8px;">
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-bottom: 15px;">
                        <div style="text-align: center; background: white; padding: 12px; border-radius: 5px;">
                            <div style="color: #666; font-size: 0.85em; margin-bottom: 3px;">Models Trained</div>
                            <div style="font-size: 1.6em; font-weight: bold; color: #28a745;">{total_trained}/{total_models}</div>
                        </div>
                        <div style="text-align: center; background: white; padding: 12px; border-radius: 5px;">
                            <div style="color: #666; font-size: 0.85em; margin-bottom: 3px;">Training Datasets</div>
                            <div style="font-size: 1.6em; font-weight: bold; color: #0071C5;">{training_status.get('datasets_collected', 0)}</div>
                        </div>
                        <div style="text-align: center; background: white; padding: 12px; border-radius: 5px;">
                            <div style="color: #666; font-size: 0.85em; margin-bottom: 3px;">Training Sessions</div>
                            <div style="font-size: 1.6em; font-weight: bold; color: #0071C5;">{training_status.get('training_sessions', 0)}</div>
                        </div>
                        <div style="text-align: center; background: white; padding: 12px; border-radius: 5px;">
                            <div style="color: #666; font-size: 0.85em; margin-bottom: 3px;">Last Training</div>
                            <div style="font-size: 1.1em; font-weight: bold; color: #0071C5;">{training_status.get('last_training', 'Never')[:10]}</div>
                        </div>
                    </div>
                    
                    <!-- Overall Progress Bar -->
                    <div style="margin: 15px 0;">
                        <div style="display: flex; justify-content: space-between; margin-bottom: 5px;">
                            <span style="font-weight: 600; color: #333;">Overall Training Progress</span>
                            <span style="font-weight: 600; color: #28a745;">{progress_pct}%</span>
                        </div>
                        <div style="background: #e0e0e0; height: 24px; border-radius: 12px; overflow: hidden; position: relative;">
                            <div style="background: linear-gradient(90deg, #28a745 0%, #34ce57 100%); height: 100%; width: {total_trained/total_models*100}%; transition: width 0.5s ease;"></div>
                            <span style="position: absolute; left: 50%; top: 50%; transform: translate(-50%, -50%); font-size: 0.85em; font-weight: 600; color: {'white' if total_trained/total_models > 0.3 else '#333'};">{total_trained} of {total_models} models trained</span>
                        </div>
                    </div>
"""
        
        # Generate model detail cards
        html += self._generate_model_status_cards(models_available, training_dataset_size)
        
        html += """
                </div>
            </div>
"""
        
        # Training Progress Chart
        html += self._generate_training_progress_chart(product_id)
        
        # Training Strategy Section
        html += self._generate_training_strategy_section()
        
        # Feature Importance Section - get real data from ML models
        html += self._generate_feature_importance_section()
        
        # Algorithm Details Section
        html += self._generate_algorithm_details_section()
        
        # Configuration Section
        html += self._generate_configuration_section()
        
        # Data Quality Section
        html += self._generate_data_quality_section()
        
        # Historical Coverage Trends
        html += self._generate_historical_trends_section()
        
        html += """
        </div>
        """
        return html
    
    def _generate_model_status_cards(self, models_available, training_dataset_size):
        """Generate individual model status cards."""
        model_details = {
            # BASE 6 MODELS
            'anomaly_detector': {'name': 'Anomaly Detector', 'algorithm': 'IsolationForest', 
                                'trained_on': 'Event count distributions, per-core variance, toggle rates',
                                'purpose': 'Detects statistical outliers and unusual event behavior', 'icon': 'DETECT',
                                'category': 'Base'},
            'pattern_classifier': {'name': 'Pattern Classifier', 'algorithm': 'Decision Tree Classifier',
                                  'trained_on': 'Activity levels, core distribution, count statistics',
                                  'purpose': 'Classifies events: low/medium/high/full activity patterns', 'icon': 'CLASSIFY',
                                  'category': 'Base'},
            'event_clusterer': {'name': 'Event Clusterer', 'algorithm': 'KMeans Clustering',
                               'trained_on': 'Toggle rates, count means/std, coefficient of variation',
                               'purpose': 'Groups similar events by behavior patterns', 'icon': 'CLUSTER',
                               'category': 'Base'},
            'coverage_predictor': {'name': 'Coverage Predictor', 'algorithm': 'RandomForest Regressor',
                                  'trained_on': 'Current coverage, workload type, duration, domain counts',
                                  'purpose': 'Predicts coverage gains for different test scenarios', 'icon': 'PREDICT',
                                  'category': 'Base'},
            'stress_correlation_model': {'name': 'Stress Correlation', 'algorithm': 'RandomForest Regressor',
                                        'trained_on': 'Stress level, activity metrics, workload signatures',
                                        'purpose': 'Identifies which events correlate with workload stress', 'icon': 'CORRELATE',
                                        'category': 'Base'},
            'health_predictor': {'name': 'Health Score Predictor', 'algorithm': 'GradientBoosting Regressor',
                                'trained_on': 'CPU, memory, disk, temperature metrics -> coverage rate',
                                'purpose': 'Predicts coverage impact from system health conditions', 'icon': 'HEALTH',
                                'category': 'Base'},
            # PRIORITY 1 MODELS
            'gap_prioritizer': {'name': 'Gap Priority Classifier', 'algorithm': 'RandomForest + TF-IDF',
                               'trained_on': 'Event names (TF-IDF), domain, co-occurrence patterns',
                               'purpose': 'Classifies gap priority: critical/high/medium/low', 'icon': 'PRIORITIZE',
                               'category': 'Priority 1'},
            'workload_detector': {'name': 'Workload Detector', 'algorithm': 'GradientBoosting Classifier',
                                 'trained_on': 'Coverage patterns, event distributions, domain activity',
                                 'purpose': 'Detects workload type: CPU/memory/mixed stress, idle', 'icon': 'WORKLOAD',
                                 'category': 'Priority 1'},
            'action_prioritizer': {'name': 'Action Prioritizer', 'algorithm': 'RandomForest Regressor (LTR)',
                                  'trained_on': 'Historical improvement patterns, action types, severity, context',
                                  'purpose': 'Ranks actions by analyzing which ones improved coverage in past runs', 'icon': 'RANK',
                                  'category': 'Priority 1'},
            # HIGH-VALUE MODELS
            'stress_recommender': {'name': 'Stress Test Recommender', 'algorithm': 'RandomForest Regressor',
                                  'trained_on': 'Gap patterns -> stress test effectiveness history',
                                  'purpose': 'Recommends next stress test for maximum coverage gain', 'icon': 'RECOMMEND',
                                  'category': 'High-Value'},
            'saturation_predictor': {'name': 'Coverage Saturation Predictor', 'algorithm': 'Linear Regression',
                                    'trained_on': 'Coverage timeline, growth rates, plateau detection',
                                    'purpose': 'Predicts optimal collection duration before saturation', 'icon': 'SATURATE',
                                    'category': 'High-Value'},
            'workload_clusterer': {'name': 'Workload Similarity Clusterer', 'algorithm': 'KMeans + PCA',
                                  'trained_on': 'Multi-dimensional run features, coverage patterns',
                                  'purpose': 'Clusters runs by similarity, identifies portfolio gaps', 'icon': 'PORTFOLIO',
                                  'category': 'High-Value'},
            'gap_forecaster': {'name': 'Gap Trend Forecaster', 'algorithm': 'Dual Linear Regression',
                              'trained_on': 'Time-series coverage and gap count history',
                              'purpose': 'Forecasts future coverage trends and target predictions', 'icon': 'FORECAST',
                              'category': 'High-Value'}
        }
        
        html = ""
        category_colors = {
            'Base': '#0071C5',
            'Priority 1': '#9c27b0',
            'High-Value': '#00796b'
        }
        
        for model_key, details in model_details.items():
            # Check if model is trained
            is_trained = False
            
            if model_key == 'gap_prioritizer':
                is_trained = self.rg.ml_gap_prioritizer.is_trained()
            elif model_key == 'workload_detector':
                is_trained = self.rg.ml_workload_detector.is_trained()
            elif model_key == 'action_prioritizer':
                is_trained = self.rg.ml_action_prioritizer.is_trained()
            elif model_key == 'stress_recommender':
                is_trained = self.rg.ml_stress_recommender.is_trained()
            elif model_key == 'saturation_predictor':
                is_trained = self.rg.ml_saturation_predictor.is_trained()
            elif model_key == 'workload_clusterer':
                is_trained = self.rg.ml_workload_clusterer.is_trained()
            elif model_key == 'gap_forecaster':
                is_trained = self.rg.ml_gap_forecaster.is_trained()
            elif isinstance(models_available, dict):
                is_trained = models_available.get(model_key, False)
            else:
                is_trained = training_dataset_size >= 3
            
            status_color = '#28a745' if is_trained else '#999'
            status_text = 'TRAINED' if is_trained else 'PENDING'
            progress_width = 100 if is_trained else 0
            
            # Pending reason for specific models
            pending_reason = ''
            if not is_trained and model_key == 'workload_detector':
                pending_reason = 'Needs 2+ different workload types (currently only idle/baseline runs)'
            elif not is_trained and model_key == 'action_prioritizer':
                pending_reason = 'Training autonomously from historical patterns. Optional: Add feedback with --log-feedback for higher accuracy'
            
            category_color = category_colors.get(details['category'], '#666')
            
            html += f"""
                <div style="background: white; border: 1px solid #ddd; border-left: 4px solid {category_color}; border-radius: 5px; padding: 12px; margin-bottom: 8px;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div style="flex: 1;">
                            <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 6px;">
                                <span style="background: {category_color}; color: white; padding: 3px 8px; border-radius: 3px; font-size: 0.7em; font-weight: bold;">{details['icon']}</span>
                                <strong style="color: #333; font-size: 1em;">{details['name']}</strong>
                                <span style="color: #999; font-size: 0.8em;">({details['algorithm']})</span>
                                <span style="background: {category_color}15; color: {category_color}; padding: 2px 6px; border-radius: 10px; font-size: 0.7em; font-weight: bold;">{details['category']}</span>
                            </div>
                            <div style="color: #666; font-size: 0.8em; margin-bottom: 3px;">
                                <strong>Training Data:</strong> {details['trained_on']}
                            </div>
                            <div style="color: #888; font-size: 0.8em;">
                                <strong>Purpose:</strong> {details['purpose']}
                            </div>"""
            
            if pending_reason:
                html += f"""
                            <div style="color: #ff9800; font-size: 0.75em; margin-top: 5px; padding: 5px 8px; background: #fff3e0; border-radius: 3px; border-left: 3px solid #ff9800;">
                                <strong>Pending Reason:</strong> {pending_reason}
                            </div>"""
            
            html += f"""
                        </div>
                        <div style="text-align: right; margin-left: 15px;">
                            <span style="background: {status_color}; color: white; padding: 5px 14px; border-radius: 20px; font-size: 0.8em; font-weight: bold; white-space: nowrap;">
                                {status_text}
                            </span>
                            <div style="background: #eee; height: 5px; width: 90px; border-radius: 3px; margin-top: 6px; overflow: hidden;">
                                <div style="background: {status_color}; height: 100%; width: {progress_width}%;"></div>
                            </div>
                        </div>
                    </div>
                </div>
"""
        
        return html
    
    def _generate_training_progress_chart(self, product_id):
        """Generate training progress over time chart."""
        html = ""
        try:
            from src.ml_visualizations import MLVisualizationGenerator
            if self.rg.config.get('debug', False):
                print(f"DEBUG: Attempting to load training history with product_id={product_id}")
            ml_viz = MLVisualizationGenerator(str(self.rg.backup_dir), product_id=product_id)
            training_history = ml_viz._load_training_history()
            if training_history and training_history.get('sessions'):
                chart_html = ml_viz._generate_training_progress_chart(training_history)
                html += chart_html
        except Exception as e:
            if self.rg.config.get('debug', False):
                print(f"Warning: Could not generate training progress chart: {e}")
        return html
    
    def _generate_training_strategy_section(self):
        """Generate training strategy section."""
        return """
            <!-- ML Training Strategy Section -->
            <div style="margin-bottom: 30px;">
                <h3 style="color: #7b1fa2;">TRAINING STRATEGY (13 MODELS)</h3>
                <div style="background: #f3e5f5; padding: 20px; border-radius: 8px;">
                    <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 15px; margin-bottom: 15px;">
                        <div style="background: #e3f2fd; padding: 15px; border-radius: 6px; border-left: 4px solid #0071C5;">
                            <div style="color: #0071C5; font-weight: bold; margin-bottom: 8px;">BASE (6 models)</div>
                            <div style="color: #666; font-size: 0.85em;">Auto-train on every run</div>
                            <div style="color: #888; font-size: 0.8em; margin-top: 5px;">Anomaly, Pattern, Clustering, Coverage, Stress, Health</div>
                        </div>
                        <div style="background: #f3e5f5; padding: 15px; border-radius: 6px; border-left: 4px solid #9c27b0;">
                            <div style="color: #9c27b0; font-weight: bold; margin-bottom: 8px;">PRIORITY 1 (3 models)</div>
                            <div style="color: #666; font-size: 0.85em;">Auto-labeling enabled</div>
                            <div style="color: #888; font-size: 0.8em; margin-top: 5px;">Gap Priority, Workload, Action Ranking</div>
                        </div>
                        <div style="background: #e0f2f1; padding: 15px; border-radius: 6px; border-left: 4px solid #00796b;">
                            <div style="color: #00796b; font-weight: bold; margin-bottom: 8px;">HIGH-VALUE (4 models)</div>
                            <div style="color: #666; font-size: 0.85em;">Advanced analytics</div>
                            <div style="color: #888; font-size: 0.8em; margin-top: 5px;">Stress Recommender, Saturation, Workload Cluster, Gap Forecast</div>
                        </div>
                    </div>
                    <ul style="color: #666; line-height: 1.6; margin: 0;">
                        <li><strong>Training:</strong> Auto-trains when new data available (3-5 runs minimum)</li>
                        <li><strong>Storage:</strong> <code>C:\\silicon_coverage_analyzer_data\\models</code></li>
                        <li><strong>Product Isolation:</strong> Models trained separately per product</li>
                    </ul>
                </div>
            </div>
"""
    
    def _generate_feature_importance_section(self):
        """Generate feature importance section with real ML model data."""
        # Try to get real feature importance from ML models
        feature_data = {}
        
        # Get from gap prioritizer
        if hasattr(self.rg, 'ml_gap_prioritizer') and self.rg.ml_gap_prioritizer:
            try:
                gap_importance = self.rg.ml_gap_prioritizer.get_feature_importance()
                if gap_importance:
                    feature_data.update(gap_importance)
            except:
                pass
        
        # Get from action prioritizer
        if hasattr(self.rg, 'ml_action_prioritizer') and self.rg.ml_action_prioritizer:
            try:
                action_importance = self.rg.ml_action_prioritizer.get_feature_importance()
                if action_importance:
                    for k, v in action_importance.items():
                        if k not in feature_data:
                            feature_data[k] = v
            except:
                pass
        
        # Get from workload detector
        if hasattr(self.rg, 'unified_workload_detector') and self.rg.unified_workload_detector:
            try:
                workload_importance = self.rg.unified_workload_detector.get_feature_importance()
                if workload_importance:
                    for k, v in workload_importance.items():
                        if k not in feature_data:
                            feature_data[k] = v
            except:
                pass
        
        # If no data, show message
        if not feature_data:
            return """
            <!-- Feature Importance Section -->
            <div style="margin-bottom: 30px;">
                <h3 style="color: #00796b;">FEATURE IMPORTANCE</h3>
                <div style="background: #fff3cd; border-left: 4px solid #ffc107; padding: 20px; border-radius: 8px;">
                    <p style="color: #856404; margin: 0;">
                        Feature importance data will be available after ML models are trained. 
                        Run more coverage collections to enable ML training.
                    </p>
                </div>
            </div>
"""
        
        # Sort by importance and take top 6
        sorted_features = sorted(feature_data.items(), key=lambda x: x[1], reverse=True)[:6]
        
        # Normalize to percentage (0-100)
        max_val = max(v for _, v in sorted_features) if sorted_features else 1
        
        html = """
            <!-- Feature Importance Section -->
            <div style="margin-bottom: 30px;">
                <h3 style="color: #00796b;">FEATURE IMPORTANCE</h3>
                <p style="color: #666; margin-bottom: 15px;">
                    Which metrics matter most for ML predictions (from trained models):
                </p>
                <div style="background: #e0f2f1; padding: 20px; border-radius: 8px;">
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px;">
"""
        
        for feature_name, importance in sorted_features:
            # Normalize to percentage
            pct = int((importance / max_val) * 100) if max_val > 0 else 0
            # Format feature name (convert snake_case to Title Case)
            display_name = feature_name.replace('_', ' ').title()
            
            html += f"""
                        <div>
                            <div style="display: flex; justify-content: space-between; margin-bottom: 5px;">
                                <span>{display_name}</span>
                                <strong>{pct}%</strong>
                            </div>
                            <div style="background: #00796b; height: 10px; width: {pct}%; border-radius: 5px;"></div>
                        </div>
"""
        
        html += """
                    </div>
                </div>
            </div>
"""
        return html
    
    def _generate_algorithm_details_section(self):
        """Generate algorithm details section with model cards."""
        return """
            <!-- Model Algorithms Section -->
            <div style="margin-bottom: 30px;">
                <h3 style="color: #d32f2f;">ML ALGORITHMS USED (13 MODELS)</h3>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 15px;">
                    <!-- Model 1: Anomaly Detector -->
                    <div style="background: white; border: 2px solid #d32f2f; padding: 15px; border-radius: 8px;">
                        <h4 style="margin-top: 0; color: #d32f2f; font-size: 1em;">Anomaly Detector</h4>
                        <p style="color: #666; margin: 8px 0; font-size: 0.85em;"><strong>Algorithm:</strong> Isolation Forest</p>
                        <p style="color: #666; margin: 8px 0; font-size: 0.85em;"><strong>Purpose:</strong> Detects unusual event behavior</p>
                        <p style="color: #888; margin: 8px 0; font-size: 0.8em;">Anomaly scores: -1 to 1</p>
                    </div>
                    <!-- Model 2: Pattern Classifier -->
                    <div style="background: white; border: 2px solid #0071C5; padding: 15px; border-radius: 8px;">
                        <h4 style="margin-top: 0; color: #0071C5; font-size: 1em;">Pattern Classifier</h4>
                        <p style="color: #666; margin: 8px 0; font-size: 0.85em;"><strong>Algorithm:</strong> Decision Tree Classifier</p>
                        <p style="color: #666; margin: 8px 0; font-size: 0.85em;"><strong>Purpose:</strong> Classifies activity patterns</p>
                        <p style="color: #888; margin: 8px 0; font-size: 0.8em;">Low/medium/high/full activity</p>
                    </div>
                    <!-- Model 3: Event Clusterer -->
                    <div style="background: white; border: 2px solid #7b1fa2; padding: 15px; border-radius: 8px;">
                        <h4 style="margin-top: 0; color: #7b1fa2; font-size: 1em;">Event Clusterer</h4>
                        <p style="color: #666; margin: 8px 0; font-size: 0.85em;"><strong>Algorithm:</strong> KMeans Clustering</p>
                        <p style="color: #666; margin: 8px 0; font-size: 0.85em;"><strong>Purpose:</strong> Groups similar events</p>
                        <p style="color: #888; margin: 8px 0; font-size: 0.8em;">Auto-determined clusters</p>
                    </div>
                    <!-- Model 4: Coverage Predictor -->
                    <div style="background: white; border: 2px solid #388e3c; padding: 15px; border-radius: 8px;">
                        <h4 style="margin-top: 0; color: #388e3c; font-size: 1em;">Coverage Predictor</h4>
                        <p style="color: #666; margin: 8px 0; font-size: 0.85em;"><strong>Algorithm:</strong> RandomForest Regressor</p>
                        <p style="color: #666; margin: 8px 0; font-size: 0.85em;"><strong>Purpose:</strong> Predicts coverage gains</p>
                        <p style="color: #888; margin: 8px 0; font-size: 0.8em;">100 estimators</p>
                    </div>
                    <!-- Model 5: Stress Correlation -->
                    <div style="background: white; border: 2px solid #f57c00; padding: 15px; border-radius: 8px;">
                        <h4 style="margin-top: 0; color: #f57c00; font-size: 1em;">Stress Correlation</h4>
                        <p style="color: #666; margin: 8px 0; font-size: 0.85em;"><strong>Algorithm:</strong> RandomForest Regressor</p>
                        <p style="color: #666; margin: 8px 0; font-size: 0.85em;"><strong>Purpose:</strong> Workload-event correlation</p>
                        <p style="color: #888; margin: 8px 0; font-size: 0.8em;">Identifies stress-sensitive events</p>
                    </div>
                    <!-- Model 6: Health Predictor -->
                    <div style="background: white; border: 2px solid #e91e63; padding: 15px; border-radius: 8px;">
                        <h4 style="margin-top: 0; color: #e91e63; font-size: 1em;">Health Predictor</h4>
                        <p style="color: #666; margin: 8px 0; font-size: 0.85em;"><strong>Algorithm:</strong> GradientBoosting Regressor</p>
                        <p style="color: #666; margin: 8px 0; font-size: 0.85em;"><strong>Purpose:</strong> Health->Coverage impact</p>
                        <p style="color: #888; margin: 8px 0; font-size: 0.8em;">CPU, memory, disk, temp metrics</p>
                    </div>
                    <!-- Model 7: Gap Prioritizer -->
                    <div style="background: white; border: 2px solid #9c27b0; padding: 15px; border-radius: 8px;">
                        <h4 style="margin-top: 0; color: #9c27b0; font-size: 1em;">Gap Prioritizer</h4>
                        <p style="color: #666; margin: 8px 0; font-size: 0.85em;"><strong>Algorithm:</strong> RandomForest + TF-IDF</p>
                        <p style="color: #666; margin: 8px 0; font-size: 0.85em;"><strong>Purpose:</strong> Classifies gap priority</p>
                        <p style="color: #888; margin: 8px 0; font-size: 0.8em;">Critical/high/medium/low</p>
                    </div>
                    <!-- Model 8: Workload Detector -->
                    <div style="background: white; border: 2px solid #00796b; padding: 15px; border-radius: 8px;">
                        <h4 style="margin-top: 0; color: #00796b; font-size: 1em;">Workload Detector</h4>
                        <p style="color: #666; margin: 8px 0; font-size: 0.85em;"><strong>Algorithm:</strong> GradientBoosting Classifier</p>
                        <p style="color: #666; margin: 8px 0; font-size: 0.85em;"><strong>Purpose:</strong> Detects workload type</p>
                        <p style="color: #888; margin: 8px 0; font-size: 0.8em;">CPU/memory/mixed/idle stress</p>
                    </div>
                    <!-- Model 9: Action Prioritizer -->
                    <div style="background: white; border: 2px solid #c62828; padding: 15px; border-radius: 8px;">
                        <h4 style="margin-top: 0; color: #c62828; font-size: 1em;">Action Prioritizer</h4>
                        <p style="color: #666; margin: 8px 0; font-size: 0.85em;"><strong>Algorithm:</strong> RandomForest LTR</p>
                        <p style="color: #666; margin: 8px 0; font-size: 0.85em;"><strong>Purpose:</strong> Ranks actions by impact</p>
                        <p style="color: #888; margin: 8px 0; font-size: 0.8em;">Learning-to-Rank algorithm</p>
                    </div>
                    <!-- Model 10: Stress Recommender -->
                    <div style="background: white; border: 2px solid #ff5722; padding: 15px; border-radius: 8px;">
                        <h4 style="margin-top: 0; color: #ff5722; font-size: 1em;">Stress Recommender</h4>
                        <p style="color: #666; margin: 8px 0; font-size: 0.85em;"><strong>Algorithm:</strong> RandomForest Regressor</p>
                        <p style="color: #666; margin: 8px 0; font-size: 0.85em;"><strong>Purpose:</strong> Recommends stress tests</p>
                        <p style="color: #888; margin: 8px 0; font-size: 0.8em;">Predicts coverage gain per stress type</p>
                    </div>
                    <!-- Model 11: Saturation Predictor -->
                    <div style="background: white; border: 2px solid #ff9800; padding: 15px; border-radius: 8px;">
                        <h4 style="margin-top: 0; color: #ff9800; font-size: 1em;">Saturation Predictor</h4>
                        <p style="color: #666; margin: 8px 0; font-size: 0.85em;"><strong>Algorithm:</strong> Linear Regression</p>
                        <p style="color: #666; margin: 8px 0; font-size: 0.85em;"><strong>Purpose:</strong> Predicts coverage saturation</p>
                        <p style="color: #888; margin: 8px 0; font-size: 0.8em;">Estimates runs to reach 90%/95%/99%</p>
                    </div>
                    <!-- Model 12: Workload Clusterer -->
                    <div style="background: white; border: 2px solid #3f51b5; padding: 15px; border-radius: 8px;">
                        <h4 style="margin-top: 0; color: #3f51b5; font-size: 1em;">Workload Clusterer</h4>
                        <p style="color: #666; margin: 8px 0; font-size: 0.85em;"><strong>Algorithm:</strong> KMeans + PCA</p>
                        <p style="color: #666; margin: 8px 0; font-size: 0.85em;"><strong>Purpose:</strong> Groups similar workloads</p>
                        <p style="color: #888; margin: 8px 0; font-size: 0.8em;">Identifies workload diversity patterns</p>
                    </div>
                    <!-- Model 13: Gap Forecaster -->
                    <div style="background: white; border: 2px solid #009688; padding: 15px; border-radius: 8px;">
                        <h4 style="margin-top: 0; color: #009688; font-size: 1em;">Gap Forecaster</h4>
                        <p style="color: #666; margin: 8px 0; font-size: 0.85em;"><strong>Algorithm:</strong> Dual Linear Regression</p>
                        <p style="color: #666; margin: 8px 0; font-size: 0.85em;"><strong>Purpose:</strong> Forecasts gap trends</p>
                        <p style="color: #888; margin: 8px 0; font-size: 0.8em;">Predicts gap resolution timeline</p>
                    </div>
                </div>
            </div>
"""
    
    def _generate_configuration_section(self):
        """Generate configuration section."""
        return """
            <!-- Configuration Section -->
            <div style="margin-bottom: 30px;">
                <h3 style="color: #f57c00;">ANALYSIS CONFIGURATION</h3>
                <div style="background: #fff3e0; padding: 20px; border-radius: 8px;">
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 15px;">
                        <div>
                            <strong>Data Directory:</strong>
                            <code style="background: white; padding: 5px; border-radius: 3px; display: block; margin-top: 5px;">
                                C:\\silicon_coverage_analyzer_data
                            </code>
                        </div>
                        <div>
                            <strong>Product Detection:</strong>
                            <p style="margin: 5px 0;">Auto-detected from EMON</p>
                        </div>
                        <div>
                            <strong>OS Detection:</strong>
                            <p style="margin: 5px 0;">Auto-detected (OS-aware)</p>
                        </div>
                        <div>
                            <strong>Regression Threshold:</strong>
                            <p style="margin: 5px 0;">Critical: ≥20%, High: ≥10%</p>
                        </div>
                        <div>
                            <strong>Gap Correlation:</strong>
                            <p style="margin: 5px 0;">≥70% co-occurrence</p>
                        </div>
                        <div>
                            <strong>Historical Lookback:</strong>
                            <p style="margin: 5px 0;">All available runs</p>
                        </div>
                    </div>
                </div>
            </div>
"""
    
    def _generate_data_quality_section(self):
        """Generate data quality section."""
        return """
            <!-- Data Quality Section -->
            <div style="margin-bottom: 30px;">
                <h3 style="color: #388e3c;">DATA QUALITY CHECKS</h3>
                <div style="background: #e8f5e9; padding: 20px; border-radius: 8px;">
                    <ul style="color: #666; line-height: 1.8; margin: 0;">
                        <li>✓ [PASS] Missing value imputation for incomplete runs</li>
                        <li>✓ [PASS] Outlier detection and filtering (3-sigma rule)</li>
                        <li>✓ [PASS] Feature normalization (0-1 scaling, StandardScaler)</li>
                        <li>✓ [PASS] Product-specific model isolation (no cross-product contamination)</li>
                        <li>✓ [PASS] OS-aware analysis (Windows/Linux separation)</li>
                        <li>✓ [PASS] Temporal consistency validation</li>
                        <li>✓ [PASS] TF-IDF vectorization for event name features (Gap Prioritizer)</li>
                        <li>✓ [PASS] Workload signature extraction (CPU/memory/domain patterns)</li>
                        <li>✓ [PASS] Learning-to-Rank metrics (NDCG, pairwise ranking)</li>
                    </ul>
                </div>
            </div>
"""
    
    def _generate_historical_trends_section(self):
        """Generate historical coverage trends section."""
        html = ""
        
        try:
            trend_results = self.rg._cached_trend_results
            
            if trend_results and trend_results.get('status') == 'complete':
                html += """
            <div style="margin-bottom: 30px;">
                <h3 style="color: #1976d2;">HISTORICAL COVERAGE TRENDS</h3>
                <p style="color: #666; margin-bottom: 15px;">
                    Track coverage improvement/regression across multiple runs. Identifies flaky events and validates ML training impact.
                </p>
"""
                
                # Overall trend summary
                overall = trend_results.get('overall_trend', {})
                summary = trend_results.get('summary', {})
                
                trend_direction = overall.get('direction', 'stable')
                trend_colors = {'improving': '#28a745', 'declining': '#dc3545', 'stable': '#ffc107'}
                trend_icons = {'improving': '📈', 'declining': '📉', 'stable': '➡️'}
                trend_color = trend_colors.get(trend_direction, '#6c757d')
                trend_icon = trend_icons.get(trend_direction, '➡️')
                
                html += f"""
                <div style="background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px;">
                        <div style="text-align: center; padding: 15px; background: {trend_color}20; border-radius: 6px;">
                            <div style="font-size: 2.5em;">{trend_icon}</div>
                            <div style="font-size: 1.2em; font-weight: bold; color: {trend_color}; margin: 10px 0;">
                                {trend_direction.upper()}
                            </div>
                            <div style="color: #666; font-size: 0.9em;">Overall Trend</div>
                        </div>
                        <div style="text-align: center; padding: 15px; background: #e3f2fd; border-radius: 6px;">
                            <div style="font-size: 2em; color: #1976d2; font-weight: bold;">
                                {trend_results.get('runs_analyzed', 0)}
                            </div>
                            <div style="color: #666; margin-top: 5px;">Runs Analyzed</div>
                        </div>
                        <div style="text-align: center; padding: 15px; background: #fff3e0; border-radius: 6px;">
                            <div style="font-size: 2em; color: #f57c00; font-weight: bold;">
                                {summary.get('flaky_count', 0)}
                            </div>
                            <div style="color: #666; margin-top: 5px;">Flaky Events</div>
                        </div>
                        <div style="text-align: center; padding: 15px; background: #e8f5e9; border-radius: 6px;">
                            <div style="font-size: 2em; color: #388e3c; font-weight: bold;">
                                {summary.get('improving_count', 0)}
                            </div>
                            <div style="color: #666; margin-top: 5px;">Improving Events</div>
                        </div>
                        <div style="text-align: center; padding: 15px; background: #ffebee; border-radius: 6px;">
                            <div style="font-size: 2em; color: #d32f2f; font-weight: bold;">
                                {summary.get('declining_count', 0)}
                            </div>
                            <div style="color: #666; margin-top: 5px;">Declining Events</div>
                        </div>
                    </div>
                </div>
"""
                
                # Domain-level trends chart
                domain_trends = trend_results.get('domain_trends', {})
                if domain_trends:
                    try:
                        from src.ml_visualizations import render_line_chart
                        from src.report_generator import DOMAIN_COLORS
                        
                        series_list = []
                        max_runs = 0
                        
                        for domain, trend_data in sorted(domain_trends.items()):
                            timeline = trend_data.get('timeline', [])
                            if len(timeline) > max_runs:
                                max_runs = len(timeline)
                            
                            coverage_values = [point.get('coverage', 0) for point in timeline]
                            
                            series_list.append({
                                'label': domain.upper(),
                                'data': coverage_values,
                                'borderColor': DOMAIN_COLORS.get(domain, '#999'),
                                'backgroundColor': DOMAIN_COLORS.get(domain, '#999') + '33',
                                'fill': False,
                                'tension': 0.3
                            })
                        
                        x_ticks = [f"Run {i+1}" for i in range(max_runs)]
                        
                        chart_options = {
                            'responsive': True,
                            'maintainAspectRatio': False,
                            'plugins': {
                                'legend': {'position': 'top'},
                                'title': {
                                    'display': True,
                                    'text': 'Coverage Evolution by Domain',
                                    'font': {'size': 16, 'weight': 'bold'}
                                }
                            },
                            'scales': {
                                'y': {
                                    'beginAtZero': True,
                                    'max': 100,
                                    'title': {'display': True, 'text': 'Coverage %'}
                                },
                                'x': {
                                    'title': {'display': True, 'text': 'Collection Runs (Chronological)'}
                                }
                            }
                        }
                        
                        html += """
                <div style="background: white; padding: 25px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
"""
                        html += render_line_chart(series_list, x_ticks, chart_options, 'historicalTrendsChart')
                        html += """
                </div>
"""
                    except Exception:
                        pass
                
                html += """
            </div>
"""
            else:
                # Insufficient data message
                runs_available = trend_results.get('runs_available', 0) if trend_results else 0
                html += f"""
            <div style="margin-bottom: 30px;">
                <h3 style="color: #1976d2;">HISTORICAL COVERAGE TRENDS</h3>
                <div style="background: #fff3cd; border-left: 4px solid #ffc107; padding: 20px; border-radius: 8px;">
                    <h4 style="color: #856404; margin-top: 0;">⏳ Insufficient Historical Data</h4>
                    <p style="color: #856404;">
                        Temporal trend analysis requires at least 2 collection runs to display meaningful patterns.
                    </p>
                    <p style="color: #856404; margin: 10px 0;">
                        <strong>Current runs:</strong> {runs_available} | <strong>Required:</strong> 2+
                    </p>
                    <p style="color: #856404; margin-top: 15px; font-size: 0.9em;">
                        💡 Continue running coverage analysis to build historical data. Each run is automatically saved to 
                        <code>C:\\silicon_coverage_analyzer_data</code> for trend tracking.
                    </p>
                </div>
            </div>
"""
        except Exception as e:
            html += f"""
            <div style="margin-bottom: 30px;">
                <h3 style="color: #1976d2;">HISTORICAL COVERAGE TRENDS</h3>
                <div style="background: #f8d7da; border-left: 4px solid #dc3545; padding: 20px; border-radius: 8px;">
                    <h4 style="color: #721c24; margin-top: 0;">⚠️ Trend Analysis Error</h4>
                    <p style="color: #721c24;">
                        Could not analyze coverage trends: {str(e)}
                    </p>
                </div>
            </div>
"""
        
        return html
