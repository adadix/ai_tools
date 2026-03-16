"""
Integration of Azure Storage with Silicon Coverage Analyzer

This module connects the coverage analyzer with Azure storage for:
- Centralized data repository
- Multi-SUT analysis
- Team collaboration
- Cloud-based ML training
"""

import logging
import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional

# Azure connector - will be imported when Azure SDKs are installed
try:
    from azure.storage.blob import BlobServiceClient
    from azure.data.tables import TableServiceClient
    AZURE_AVAILABLE = True
except ImportError:
    AZURE_AVAILABLE = False
    logging.warning("Azure SDK not available - install azure-storage-blob and azure-data-tables to enable Azure integration")

logger = logging.getLogger(__name__)


class AzureIntegration:
    """
    Integration layer between Silicon Coverage Analyzer and Azure Storage.
    
    Handles:
    - Report uploads (HTML, JSON, CSV)
    - Structured metrics push
    - ML data synchronization
    - Multi-SUT aggregation
    """
    
    def __init__(self, azure_config: Dict[str, Any]):
        """
        Initialize Azure integration.
        
        Args:
            azure_config: Azure configuration from azure_config.yaml
        """
        self.config = azure_config.get('azure_storage', {})
        self.multi_sut_config = azure_config.get('multi_sut', {})
        self.notifications_config = azure_config.get('notifications', {})
        
        self.enabled = self.config.get('enabled', False)
        self.connector = None
        
        if self.enabled:
            self._initialize_connector()
    
    def _initialize_connector(self):
        """Initialize Azure Storage connector."""
        try:
            if not AZURE_AVAILABLE:
                logger.error("Azure SDK not available")
                logger.info("Install: pip install azure-storage-blob azure-data-tables")
                self.enabled = False
                return
            
            # Get connection string from environment or config
            conn_string = os.getenv('AZURE_STORAGE_CONNECTION_STRING')
            if not conn_string:
                conn_string = self.config.get('connection_string')
            
            if not conn_string or conn_string.startswith('${'):
                logger.warning("Azure connection string not configured")
                logger.info("Set AZURE_STORAGE_CONNECTION_STRING environment variable")
                self.enabled = False
                return
            
            # Note: Full Azure connector implementation available when SDKs installed
            # For now, just validate connection string format
            if 'AccountName=' in conn_string and 'AccountKey=' in conn_string:
                logger.info("[OK] Azure Storage configuration valid")
                logger.info(f"   Container: {self.config.get('blob_container')}")
                logger.info(f"   Table: {self.config.get('table_name')}")
                logger.warning("   Azure upload requires azure-storage-blob and azure-data-tables packages")
            else:
                logger.error("Invalid Azure connection string format")
                self.enabled = False
            
        except Exception as e:
            logger.error(f"Failed to initialize Azure connector: {e}")
            self.enabled = False
    
    def upload_analysis_results(self, analysis_results: Dict[str, Any], 
                               sut_ip: str, 
                               report_paths: Dict[str, str]) -> Optional[Dict[str, str]]:
        """
        Upload complete analysis results to Azure.
        
        Args:
            analysis_results: Complete analysis results
            sut_ip: SUT IP address
            report_paths: Paths to generated report files
        
        Returns:
            dict: URLs of uploaded files, or None if disabled
        """
        if not self.enabled or not self.connector:
            logger.debug("Azure upload skipped (disabled)")
            return None
        
        try:
            upload_config = self.config.get('upload_components', {})
            
            # Prepare upload paths based on configuration
            upload_paths = {}
            if upload_config.get('html_report', True) and 'html' in report_paths:
                upload_paths['html'] = report_paths['html']
            if upload_config.get('json_data', True) and 'json' in report_paths:
                upload_paths['json'] = report_paths['json']
            if upload_config.get('csv_files', True) and 'csv' in report_paths:
                upload_paths['csv'] = report_paths['csv']
            
            # Upload dataset
            logger.info(f" Uploading analysis results to Azure for {sut_ip}...")
            urls = self.connector.upload_complete_dataset(
                analysis_results=analysis_results,
                sut_ip=sut_ip,
                report_paths=upload_paths
            )
            
            # Upload ML data if configured
            self._upload_ml_data(analysis_results)
            
            # Send notification if configured
            self._send_notification(analysis_results, sut_ip, urls)
            
            logger.info("[OK] Analysis results uploaded to Azure successfully")
            return urls
            
        except Exception as e:
            logger.error(f"Failed to upload analysis results to Azure: {e}")
            if self.notifications_config.get('alert_on_upload_failure', True):
                self._send_alert(f"Azure upload failed for {sut_ip}: {e}")
            return None
    
    def _upload_ml_data(self, analysis_results: Dict[str, Any]):
        """Upload ML training data and models if configured."""
        ml_config = self.config.get('ml_integration', {})
        
        if not ml_config.get('upload_raw_data', False) and \
           not ml_config.get('upload_models', False) and \
           not ml_config.get('upload_training_logs', False):
            return
        
        try:
            ml_data_dir = Path("C:/silicon_coverage_analyzer_data")
            if not ml_data_dir.exists():
                return
            
            # Upload training logs
            if ml_config.get('upload_training_logs', True):
                logs_dir = ml_data_dir / "training_logs"
                if logs_dir.exists():
                    for log_file in logs_dir.glob("*.json"):
                        self.connector.upload_json_data(
                            str(log_file),
                            blob_name=f"ml_data/training_logs/{log_file.name}"
                        )
                    logger.info("[OK] ML training logs uploaded to Azure")
            
            # Upload models (for sharing across SUTs)
            if ml_config.get('upload_models', False):
                models_dir = ml_data_dir / "models"
                if models_dir.exists():
                    for model_file in models_dir.glob("*.joblib"):
                        blob_client = self.connector.blob_service_client.get_blob_client(
                            container=self.connector.blob_container,
                            blob=f"ml_data/models/{model_file.name}"
                        )
                        with open(model_file, 'rb') as f:
                            blob_client.upload_blob(f, overwrite=True)
                    logger.info("[OK] ML models uploaded to Azure (shared across SUTs)")
            
            # Upload raw data (large - only if needed)
            if ml_config.get('upload_raw_data', False):
                raw_data_dir = ml_data_dir / "raw_data"
                if raw_data_dir.exists():
                    for data_file in raw_data_dir.glob("coverage_*.json"):
                        self.connector.upload_json_data(
                            str(data_file),
                            blob_name=f"ml_data/raw_data/{data_file.name}"
                        )
                    logger.info("[OK] ML raw data uploaded to Azure")
            
        except Exception as e:
            logger.error(f"Failed to upload ML data: {e}")
    
    def _send_notification(self, analysis_results: Dict[str, Any], 
                          sut_ip: str, 
                          urls: Dict[str, str]):
        """Send notification if configured."""
        if not self.notifications_config.get('enabled', False):
            return
        
        # Check if coverage is below threshold
        coverage = analysis_results.get('coverage', {})
        coverage_pct = coverage.get('overall_coverage_percentage', 0)
        threshold = self.notifications_config.get('coverage_threshold', 70.0)
        
        if coverage_pct < threshold and self.notifications_config.get('alert_on_low_coverage', True):
            message = f"[WARN] Low coverage detected on {sut_ip}: {coverage_pct:.1f}% (threshold: {threshold}%)"
            self._send_alert(message, urls)
    
    def _send_alert(self, message: str, urls: Optional[Dict[str, str]] = None):
        """Send alert notification (Teams, email, etc.)."""
        try:
            teams_webhook = self.notifications_config.get('teams_webhook', '')
            if teams_webhook:
                # Send to Microsoft Teams
                import requests
                payload = {
                    "text": message,
                    "sections": [
                        {
                            "activityTitle": "Silicon Coverage Analyzer Alert",
                            "facts": []
                        }
                    ]
                }
                
                if urls:
                    payload["sections"][0]["facts"].append({
                        "name": "HTML Report",
                        "value": urls.get('html', 'N/A')
                    })
                
                requests.post(teams_webhook, json=payload)
                logger.info(f" Alert sent to Teams: {message}")
            else:
                logger.warning(f"Alert: {message}")
                
        except Exception as e:
            logger.error(f"Failed to send alert: {e}")
    
    def get_sut_trends(self, sut_ip: str, days: int = 30) -> Optional[Dict[str, Any]]:
        """
        Get coverage trends for a SUT from Azure.
        
        Args:
            sut_ip: SUT IP address
            days: Number of days to look back
        
        Returns:
            dict: Trend data, or None if disabled
        """
        if not self.enabled or not self.connector:
            return None
        
        try:
            trends = self.connector.get_coverage_trends(sut_ip, days)
            return trends
        except Exception as e:
            logger.error(f"Failed to get SUT trends: {e}")
            return None
    
    def compare_suts(self, sut_ips: list) -> Optional[Dict[str, Any]]:
        """
        Compare coverage across multiple SUTs.
        
        Args:
            sut_ips: List of SUT IP addresses
        
        Returns:
            dict: Comparison data, or None if disabled
        """
        if not self.enabled or not self.connector:
            return None
        
        if not self.multi_sut_config.get('aggregate_analytics', True):
            logger.debug("Multi-SUT aggregation disabled")
            return None
        
        try:
            comparison = {}
            
            for sut_ip in sut_ips:
                runs = self.connector.list_coverage_runs(sut_ip, limit=10)
                if runs:
                    latest = runs[0]
                    comparison[sut_ip] = {
                        'coverage': latest.get('CoveragePercentage', 0),
                        'anomalies': latest.get('ML_AnomaliesDetected', 0),
                        'last_run': latest.get('Timestamp', 'Unknown')
                    }
            
            logger.info(f"[OK] Retrieved comparison data for {len(comparison)} SUTs")
            return comparison
            
        except Exception as e:
            logger.error(f"Failed to compare SUTs: {e}")
            return None


def integrate_azure(analyzer_instance, azure_config_path: str = "config/azure_config.yaml"):
    """
    Helper function to integrate Azure into existing analyzer.
    
    Args:
        analyzer_instance: SiliconCoverageAnalyzer instance
        azure_config_path: Path to azure_config.yaml
    
    Returns:
        AzureIntegration instance
    """
    import yaml
    
    try:
        with open(azure_config_path, 'r') as f:
            azure_config = yaml.safe_load(f)
        
        azure_integration = AzureIntegration(azure_config)
        
        if azure_integration.enabled:
            logger.info("[OK] Azure integration initialized")
        else:
            logger.info("[i] Azure integration disabled (configure config/azure_config.yaml)")
        
        return azure_integration
        
    except FileNotFoundError:
        logger.warning(f"Azure config not found: {azure_config_path}")
        logger.info("Create config/azure_config.yaml to enable Azure integration")
        return None
    except Exception as e:
        logger.error(f"Failed to integrate Azure: {e}")
        return None
