"""
ML Training Manual Controls
Provides engineers with manual control over ML model training, dataset export, and diagnostics.
"""

import json
import csv
import os
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path


class MLTrainingController:
    """
    Centralized controller for manual ML model training operations.
    Gives engineers explicit control over when models train, view diagnostics, and export datasets.
    """
    
    def __init__(self, ml_models: Dict[str, Any], data_dir: str = "output/ml_training_data"):
        """
        Initialize ML Training Controller.
        
        Args:
            ml_models: Dictionary of all ML model instances keyed by name
            data_dir: Directory for storing exported datasets and logs
        """
        self.models = ml_models
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Model metadata for better diagnostics
        self.model_info = {
            'gap_prioritizer': {
                'display_name': 'Gap Prioritizer',
                'description': 'Ranks coverage gaps by validation impact',
                'min_samples': 10,
                'data_source': 'gap_analysis'
            },
            'workload_detector': {
                'display_name': 'Workload Detector',
                'description': 'Classifies workload type from event patterns',
                'min_samples': 20,
                'data_source': 'event_coverage'
            },
            'coverage_predictor': {
                'display_name': 'Coverage Predictor',
                'description': 'Predicts coverage improvements from changes',
                'min_samples': 15,
                'data_source': 'historical_coverage'
            },
            'flake_detector': {
                'display_name': 'Flake Detector',
                'description': 'Identifies flaky events from variance patterns',
                'min_samples': 25,
                'data_source': 'event_stability'
            },
            'domain_health': {
                'display_name': 'Domain Health Analyzer',
                'description': 'Assesses PMU domain reliability',
                'min_samples': 12,
                'data_source': 'domain_metrics'
            },
            'stress_correlation': {
                'display_name': 'Stress Correlation Analyzer',
                'description': 'Correlates stress level with event activity',
                'min_samples': 15,
                'data_source': 'stress_metrics'
            },
            'workload_optimizer': {
                'display_name': 'Workload Optimizer',
                'description': 'Suggests optimal workload for coverage',
                'min_samples': 18,
                'data_source': 'workload_coverage'
            },
            'event_recommender': {
                'display_name': 'Event Recommender',
                'description': 'Recommends high-value events to test',
                'min_samples': 20,
                'data_source': 'event_importance'
            },
            'coverage_anomaly': {
                'display_name': 'Coverage Anomaly Detector',
                'description': 'Detects unusual coverage patterns',
                'min_samples': 30,
                'data_source': 'coverage_history'
            },
            'resource_predictor': {
                'display_name': 'Resource Usage Predictor',
                'description': 'Predicts system resource requirements',
                'min_samples': 15,
                'data_source': 'resource_metrics'
            },
            'test_duration_predictor': {
                'display_name': 'Test Duration Predictor',
                'description': 'Estimates test execution time',
                'min_samples': 12,
                'data_source': 'test_durations'
            },
            'platform_classifier': {
                'display_name': 'Platform Classifier',
                'description': 'Classifies platform from event signatures',
                'min_samples': 8,
                'data_source': 'platform_signatures'
            },
            'regression_detector': {
                'display_name': 'Regression Detector',
                'description': 'Identifies coverage regressions',
                'min_samples': 20,
                'data_source': 'regression_data'
            }
        }
    
    def trigger_training(self, model_name: str, force: bool = False) -> Dict[str, Any]:
        """
        Force immediate training for a specific ML model.
        
        Args:
            model_name: Name of the model to train
            force: If True, train even if normally wouldn't (use with caution)
        
        Returns:
            Dictionary with training result status and details
        """
        if model_name not in self.models:
            return {
                'status': 'error',
                'message': f'Model "{model_name}" not found',
                'available_models': list(self.models.keys())
            }
        
        model = self.models[model_name]
        info = self.model_info.get(model_name, {})
        
        # Check if model has training capability
        if not hasattr(model, 'train'):
            return {
                'status': 'error',
                'message': f'Model "{model_name}" does not support training',
                'model_type': type(model).__name__
            }
        
        # Get training data availability
        try:
            if hasattr(model, 'has_enough_data'):
                has_data = model.has_enough_data()
            else:
                has_data = True  # Assume true if method doesn't exist
            
            if not has_data and not force:
                needed = info.get('min_samples', 'unknown')
                current = self._get_available_samples(model)
                return {
                    'status': 'insufficient_data',
                    'message': f'Not enough training data for {info.get("display_name", model_name)}',
                    'samples_needed': needed,
                    'samples_available': current,
                    'recommendation': f'Collect {needed - current} more samples or use force=True to train anyway'
                }
            
            # Perform training
            training_start = datetime.now()
            if force:
                print(f"[WARN]  FORCE TRAINING: {info.get('display_name', model_name)} (data may be insufficient)")
            
            result = model.train()
            training_duration = (datetime.now() - training_start).total_seconds()
            
            # Log training event
            self._log_training_event(model_name, result, training_duration, forced=force)
            
            return {
                'status': 'success',
                'message': f'Successfully trained {info.get("display_name", model_name)}',
                'model_name': model_name,
                'training_duration_seconds': training_duration,
                'accuracy': result.get('accuracy', 'N/A'),
                'samples_used': result.get('samples_used', 'N/A'),
                'forced': force,
                'timestamp': datetime.now().isoformat()
            }
        
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Training failed: {str(e)}',
                'model_name': model_name,
                'error_type': type(e).__name__
            }
    
    def export_training_dataset(self, model_name: str, format: str = 'csv') -> Dict[str, Any]:
        """
        Export training dataset for inspection/debugging.
        
        Args:
            model_name: Name of the model whose data to export
            format: Export format ('csv', 'json')
        
        Returns:
            Dictionary with export status and file path
        """
        if model_name not in self.models:
            return {
                'status': 'error',
                'message': f'Model "{model_name}" not found'
            }
        
        model = self.models[model_name]
        info = self.model_info.get(model_name, {})
        
        # Get training data
        try:
            if hasattr(model, 'get_training_data'):
                data = model.get_training_data()
            elif hasattr(model, 'training_data'):
                data = model.training_data
            else:
                return {
                    'status': 'error',
                    'message': f'Model "{model_name}" does not expose training data'
                }
            
            if not data:
                return {
                    'status': 'warning',
                    'message': 'No training data available to export',
                    'samples': 0
                }
            
            # Export to file
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'{model_name}_training_data_{timestamp}.{format}'
            filepath = self.data_dir / filename
            
            if format == 'csv':
                self._export_to_csv(data, filepath)
            elif format == 'json':
                self._export_to_json(data, filepath)
            else:
                return {
                    'status': 'error',
                    'message': f'Unsupported format: {format}',
                    'supported_formats': ['csv', 'json']
                }
            
            return {
                'status': 'success',
                'message': f'Exported {len(data)} samples to {filename}',
                'filepath': str(filepath),
                'format': format,
                'samples': len(data),
                'model_name': model_name,
                'display_name': info.get('display_name', model_name)
            }
        
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Export failed: {str(e)}',
                'error_type': type(e).__name__
            }
    
    def reset_model(self, model_name: str, confirm: bool = False) -> Dict[str, Any]:
        """
        Clear trained model and start fresh.
        
        Args:
            model_name: Name of the model to reset
            confirm: Must be True to actually reset (safety check)
        
        Returns:
            Dictionary with reset status
        """
        if not confirm:
            return {
                'status': 'warning',
                'message': 'Reset not confirmed. Set confirm=True to proceed.',
                'warning': 'This will delete the trained model and all learned parameters!'
            }
        
        if model_name not in self.models:
            return {
                'status': 'error',
                'message': f'Model "{model_name}" not found'
            }
        
        model = self.models[model_name]
        info = self.model_info.get(model_name, {})
        
        try:
            if hasattr(model, 'reset'):
                model.reset()
            elif hasattr(model, 'clear'):
                model.clear()
            elif hasattr(model, 'model'):
                model.model = None  # Clear sklearn model
            else:
                return {
                    'status': 'error',
                    'message': f'Model "{model_name}" does not support reset operation'
                }
            
            # Log reset event
            self._log_training_event(model_name, {'action': 'reset'}, 0, forced=False)
            
            return {
                'status': 'success',
                'message': f'Successfully reset {info.get("display_name", model_name)}',
                'model_name': model_name,
                'next_steps': 'Run trigger_training() to train fresh model with current data'
            }
        
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Reset failed: {str(e)}',
                'error_type': type(e).__name__
            }
    
    def get_training_diagnostics(self) -> Dict[str, Dict[str, Any]]:
        """
        Get comprehensive training readiness diagnostics for all models.
        
        Returns:
            Dictionary of model diagnostics keyed by model name
        """
        diagnostics = {}
        
        for model_name, model in self.models.items():
            info = self.model_info.get(model_name, {})
            
            try:
                # Check if model is trained
                is_trained = False
                if hasattr(model, 'is_trained'):
                    is_trained = model.is_trained()
                elif hasattr(model, 'model') and model.model is not None:
                    is_trained = True
                
                # Get sample counts
                samples_available = self._get_available_samples(model)
                samples_needed = info.get('min_samples', 10)
                
                # Get last training time
                last_trained = None
                if hasattr(model, 'get_last_training_time'):
                    last_trained = model.get_last_training_time()
                elif hasattr(model, 'last_trained'):
                    last_trained = model.last_trained
                
                # Get accuracy
                accuracy = None
                if is_trained:
                    if hasattr(model, 'get_accuracy'):
                        accuracy = model.get_accuracy()
                    elif hasattr(model, 'accuracy'):
                        accuracy = model.accuracy
                
                # Determine status
                if is_trained:
                    status = '[OK] TRAINED'
                elif samples_available >= samples_needed:
                    status = '[WARN] READY TO TRAIN'
                else:
                    status = f'[FAIL] NEEDS DATA ({samples_available}/{samples_needed})'
                
                diagnostics[model_name] = {
                    'display_name': info.get('display_name', model_name),
                    'description': info.get('description', 'N/A'),
                    'status': status,
                    'trained': is_trained,
                    'samples_available': samples_available,
                    'samples_needed': samples_needed,
                    'samples_deficit': max(0, samples_needed - samples_available),
                    'ready_to_train': samples_available >= samples_needed,
                    'last_trained': last_trained.isoformat() if last_trained and hasattr(last_trained, 'isoformat') else str(last_trained),
                    'accuracy': f'{accuracy:.2%}' if accuracy else 'N/A',
                    'data_source': info.get('data_source', 'N/A')
                }
            
            except Exception as e:
                diagnostics[model_name] = {
                    'display_name': info.get('display_name', model_name),
                    'status': '[WARN] ERROR',
                    'error': str(e)
                }
        
        return diagnostics
    
    def get_training_logs(self, model_name: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get recent training log entries.
        
        Args:
            model_name: Filter to specific model (None for all)
            limit: Maximum number of log entries to return
        
        Returns:
            List of training log entries (most recent first)
        """
        log_file = self.data_dir / 'training_log.json'
        
        if not log_file.exists():
            return []
        
        try:
            with open(log_file, 'r') as f:
                logs = json.load(f)
            
            # Filter by model if specified
            if model_name:
                logs = [log for log in logs if log.get('model_name') == model_name]
            
            # Sort by timestamp (most recent first) and limit
            logs.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            return logs[:limit]
        
        except Exception as e:
            return [{'error': f'Failed to read training logs: {str(e)}'}]
    
    # Private helper methods
    
    def _get_available_samples(self, model) -> int:
        """Get count of available training samples."""
        if hasattr(model, 'get_available_samples'):
            return model.get_available_samples()
        elif hasattr(model, 'training_data') and model.training_data:
            return len(model.training_data)
        return 0
    
    def _export_to_csv(self, data: List[Dict], filepath: Path):
        """Export data to CSV format."""
        if not data:
            return
        
        keys = data[0].keys()
        with open(filepath, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(data)
    
    def _export_to_json(self, data: List[Dict], filepath: Path):
        """Export data to JSON format."""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    
    def _log_training_event(self, model_name: str, result: Dict, duration: float, forced: bool):
        """Log training event to persistent log file."""
        log_file = self.data_dir / 'training_log.json'
        
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'model_name': model_name,
            'display_name': self.model_info.get(model_name, {}).get('display_name', model_name),
            'action': result.get('action', 'train'),
            'duration_seconds': duration,
            'forced': forced,
            'accuracy': result.get('accuracy'),
            'samples_used': result.get('samples_used')
        }
        
        # Read existing logs
        logs = []
        if log_file.exists():
            try:
                with open(log_file, 'r') as f:
                    logs = json.load(f)
            except:
                logs = []
        
        # Append new entry
        logs.append(log_entry)
        
        # Keep only last 500 entries
        logs = logs[-500:]
        
        # Write back
        with open(log_file, 'w') as f:
            json.dump(logs, f, indent=2)
