#!/usr/bin/env python3
"""
ML-Based Workload Similarity Clusterer

Clusters validation runs by workload similarity to identify:
- Redundant testing (similar runs)
- Coverage gaps between workload types
- Representative runs for each workload cluster

Uses event patterns, instruction mix, and system metrics for clustering.

Author: Intel Corporation
Date: December 2025
"""

import json
import pickle
import yaml
from pathlib import Path
from typing import Dict, List, Tuple, Any
from datetime import datetime
from collections import defaultdict
import numpy as np

from .config_utils import get_ml_domains

try:
    from sklearn.cluster import KMeans, DBSCAN
    from sklearn.preprocessing import StandardScaler
    from sklearn.decomposition import PCA
    from sklearn.metrics import silhouette_score
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    print("[WARNING] scikit-learn not available. Workload clustering unavailable.")


class MLWorkloadClusterer:
    """ML-based workload similarity clustering."""
    
    def __init__(self, data_dir: str = "C:\\silicon_coverage_analyzer_data"):
        """Initialize workload clusterer."""
        self.data_dir = Path(data_dir)
        self.models_dir = self.data_dir / "models" / "workload_clusterer"
        self.models_dir.mkdir(parents=True, exist_ok=True)
        
        self.model = None
        self.scaler = None
        self.pca = None
        self.feature_names = []
        
        # Clustering parameters
        self.n_clusters = 5  # Default number of clusters
        self.min_cluster_size = 2
        
        # Load trained model if exists
        self._load_model()
    
    def _load_model(self):
        """Load trained model from disk."""
        model_path = self.models_dir / "workload_clusterer.pkl"
        scaler_path = self.models_dir / "workload_scaler.pkl"
        pca_path = self.models_dir / "workload_pca.pkl"
        
        if model_path.exists() and scaler_path.exists():
            try:
                with open(model_path, 'rb') as f:
                    self.model = pickle.load(f)
                with open(scaler_path, 'rb') as f:
                    self.scaler = pickle.load(f)
                if pca_path.exists():
                    with open(pca_path, 'rb') as f:
                        self.pca = pickle.load(f)
                
                print(f"[ML] Loaded workload clusterer from {model_path}")
                return True
            except Exception as e:
                print(f"[WARNING] Could not load workload clusterer: {e}")
                self.model = None
        return False
    
    def is_trained(self) -> bool:
        """Check if model is trained."""
        return self.model is not None
    
    def get_model_info(self) -> Dict[str, Any]:
        """Get model information and status."""
        if not self.model:
            return {'status': 'untrained'}
        
        return {
            'status': 'trained',
            'algorithm': 'KMeans Clustering',
            'num_clusters': self.n_clusters,
            'features_used': len(self.feature_names)
        }
    
    def cluster_workloads(self, historical_runs: List[Dict]) -> Dict[str, Any]:
        """
        Cluster historical runs by workload similarity.
        
        Args:
            historical_runs: List of run data
            
        Returns:
            Clustering results with analysis
        """
        if not SKLEARN_AVAILABLE:
            return {'status': 'error', 'message': 'scikit-learn not available'}
        
        if len(historical_runs) < 5:
            return {'status': 'insufficient_data',
                   'message': f'Need at least 5 runs (have {len(historical_runs)})'}
        
        # Extract features from runs
        features_list = []
        run_metadata = []
        
        for run in historical_runs:
            features = self._extract_workload_features(run)
            if features:
                features_list.append(list(features.values()))
                run_metadata.append({
                    'timestamp': run.get('timestamp', 'Unknown'),
                    'workload': run.get('metadata', {}).get('workload', 'unknown'),
                    'coverage': run.get('coverage_results', run.get('coverage', {})).get(
                        'activity_coverage',
                        run.get('coverage_results', run.get('coverage', {})).get('overall_coverage_percentage', 0)
                    )
                })
                
                if not self.feature_names:
                    self.feature_names = list(features.keys())
        
        if len(features_list) < 5:
            return {'status': 'insufficient_samples',
                   'message': f'Could not extract features from enough runs'}
        
        X = np.array(features_list)
        
        # Scale features
        if not self.scaler:
            self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X)
        
        # Dimensionality reduction for visualization
        if not self.pca:
            self.pca = PCA(n_components=min(3, X_scaled.shape[1]))
        X_pca = self.pca.fit_transform(X_scaled)
        
        # Determine optimal number of clusters
        optimal_k = self._find_optimal_clusters(X_scaled, max_k=min(len(X_scaled)//2, 8))
        self.n_clusters = optimal_k
        
        # Cluster
        if not self.model:
            self.model = KMeans(n_clusters=self.n_clusters, random_state=42, n_init=10)
        
        cluster_labels = self.model.fit_predict(X_scaled)
        
        # Calculate silhouette score
        if len(set(cluster_labels)) > 1:
            sil_score = silhouette_score(X_scaled, cluster_labels)
        else:
            sil_score = 0.0
        
        # Organize runs by cluster
        clusters = self._organize_clusters(cluster_labels, run_metadata, X_pca)
        
        # Identify coverage gaps between clusters
        cluster_gaps = self._identify_cluster_gaps(clusters, historical_runs)
        
        # Find representative runs for each cluster
        representatives = self._find_cluster_representatives(clusters, X_scaled, cluster_labels)
        
        return {
            'status': 'complete',
            'num_clusters': self.n_clusters,
            'num_runs': len(historical_runs),
            'silhouette_score': float(sil_score),
            'clusters': clusters,
            'cluster_gaps': cluster_gaps,
            'representatives': representatives,
            'summary': self._generate_cluster_summary(clusters)
        }
    
    def _extract_workload_features(self, run: Dict) -> Dict[str, float]:
        """Extract features characterizing workload."""
        features = {}
        
        coverage = run.get('coverage_results', run.get('coverage', {}))
        metadata = run.get('metadata', {})
        
        # Coverage metrics
        features['coverage_pct'] = coverage.get('activity_coverage',
                                               coverage.get('overall_coverage_percentage', 0))
        features['active_events'] = coverage.get('active_events', 0)
        features['inactive_events'] = coverage.get('inactive_events', 0)
        
        # Load domain list from config or use defaults
        domain_list = self._get_ml_domains('workload_clusterer')
        
        # Domain distribution
        domain_results = coverage.get('domain_results', {})
        for domain in domain_list:
            if domain in domain_results:
                features[f'{domain}_activity'] = domain_results[domain].get('activity_rate', 0)
            else:
                features[f'{domain}_activity'] = 0
        
        # Instruction mix (if available)
        instruction_mix = metadata.get('instruction_mix', {})
        for instr_type in ['FP_SIMD', 'Integer', 'Memory', 'Branch']:
            features[f'instr_{instr_type}'] = instruction_mix.get(instr_type, 0)
        
        # Health metrics (if available)
        health_metrics = metadata.get('health_metrics', {})
        features['avg_cpu_usage'] = health_metrics.get('cpu_usage_avg', 0)
        features['avg_memory_usage'] = health_metrics.get('memory_usage_avg', 0)
        features['avg_temperature'] = health_metrics.get('cpu_temp_avg', 0)
        
        # Workload intensity indicators
        features['collection_duration'] = metadata.get('duration_seconds', 0) / 60  # minutes
        
        return features
    
    def _find_optimal_clusters(self, X: np.ndarray, max_k: int = 8) -> int:
        """Find optimal number of clusters using elbow method."""
        if len(X) < 6:
            return 2
        
        inertias = []
        K_range = range(2, min(max_k + 1, len(X)))
        
        for k in K_range:
            kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
            kmeans.fit(X)
            inertias.append(kmeans.inertia_)
        
        # Find elbow point (largest decrease in inertia)
        if len(inertias) < 2:
            return 2
        
        deltas = np.diff(inertias)
        elbow_idx = np.argmax(np.abs(deltas)) + 2  # +2 because we start at k=2
        
        return min(elbow_idx, max_k)
    
    def _organize_clusters(self, labels: np.ndarray, run_metadata: List[Dict],
                          X_pca: np.ndarray) -> List[Dict]:
        """Organize runs into clusters."""
        clusters = []
        
        for cluster_id in range(self.n_clusters):
            cluster_runs = []
            cluster_coords = []
            
            for i, label in enumerate(labels):
                if label == cluster_id:
                    run_info = run_metadata[i].copy()
                    run_info['pca_coords'] = X_pca[i].tolist()
                    cluster_runs.append(run_info)
                    cluster_coords.append(X_pca[i])
            
            if cluster_runs:
                # Calculate cluster characteristics
                avg_coverage = np.mean([r['coverage'] for r in cluster_runs])
                workload_types = [r['workload'] for r in cluster_runs]
                dominant_workload = max(set(workload_types), key=workload_types.count)
                
                # Calculate cluster center in PCA space
                center = np.mean(cluster_coords, axis=0)
                
                clusters.append({
                    'cluster_id': int(cluster_id),
                    'size': len(cluster_runs),
                    'runs': cluster_runs,
                    'avg_coverage': float(avg_coverage),
                    'dominant_workload': dominant_workload,
                    'workload_diversity': len(set(workload_types)),
                    'center': center.tolist()
                })
        
        return clusters
    
    def _identify_cluster_gaps(self, clusters: List[Dict], historical_runs: List[Dict]) -> Dict[str, Any]:
        """Identify coverage gaps between clusters."""
        gaps = {
            'underrepresented_workloads': [],
            'low_coverage_clusters': [],
            'missing_combinations': []
        }
        
        # Find underrepresented clusters
        avg_cluster_size = np.mean([c['size'] for c in clusters])
        for cluster in clusters:
            if cluster['size'] < avg_cluster_size / 2:
                gaps['underrepresented_workloads'].append({
                    'cluster_id': cluster['cluster_id'],
                    'workload': cluster['dominant_workload'],
                    'current_runs': cluster['size'],
                    'recommendation': f"Run more {cluster['dominant_workload']} workloads"
                })
        
        # Find low coverage clusters
        overall_avg_coverage = np.mean([c['avg_coverage'] for c in clusters])
        for cluster in clusters:
            if cluster['avg_coverage'] < overall_avg_coverage - 5:
                gaps['low_coverage_clusters'].append({
                    'cluster_id': cluster['cluster_id'],
                    'workload': cluster['dominant_workload'],
                    'avg_coverage': cluster['avg_coverage'],
                    'gap': overall_avg_coverage - cluster['avg_coverage'],
                    'recommendation': f"Improve {cluster['dominant_workload']} coverage"
                })
        
        return gaps
    
    def _find_cluster_representatives(self, clusters: List[Dict], X: np.ndarray,
                                     labels: np.ndarray) -> List[Dict]:
        """Find representative run for each cluster (closest to centroid)."""
        representatives = []
        
        for cluster in clusters:
            cluster_id = cluster['cluster_id']
            cluster_indices = np.where(labels == cluster_id)[0]
            
            if len(cluster_indices) == 0:
                continue
            
            # Get cluster centroid
            centroid = self.model.cluster_centers_[cluster_id]
            
            # Find closest run to centroid
            min_dist = float('inf')
            rep_idx = cluster_indices[0]
            
            for idx in cluster_indices:
                dist = np.linalg.norm(X[idx] - centroid)
                if dist < min_dist:
                    min_dist = dist
                    rep_idx = idx
            
            # Get representative run info
            rep_run = cluster['runs'][np.where(cluster_indices == rep_idx)[0][0]]
            
            representatives.append({
                'cluster_id': cluster_id,
                'timestamp': rep_run['timestamp'],
                'workload': rep_run['workload'],
                'coverage': rep_run['coverage'],
                'distance_to_center': float(min_dist)
            })
        
        return representatives
    
    def _get_ml_domains(self, model_name: str) -> List[str]:
        """Load domain list from config for specific ML model."""
        return get_ml_domains(model_name, ['p-core', 'e-core', 'uncore', 'core', 'atom'])
    
    def _generate_cluster_summary(self, clusters: List[Dict]) -> Dict[str, Any]:
        """Generate summary of clustering results."""
        total_runs = sum(c['size'] for c in clusters)
        workload_types = set()
        
        for cluster in clusters:
            workload_types.add(cluster['dominant_workload'])
        
        return {
            'total_runs': total_runs,
            'num_clusters': len(clusters),
            'unique_workloads': len(workload_types),
            'largest_cluster_size': max([c['size'] for c in clusters]) if clusters else 0,
            'smallest_cluster_size': min([c['size'] for c in clusters]) if clusters else 0,
            'coverage_range': {
                'min': min([c['avg_coverage'] for c in clusters]) if clusters else 0,
                'max': max([c['avg_coverage'] for c in clusters]) if clusters else 0,
                'avg': np.mean([c['avg_coverage'] for c in clusters]) if clusters else 0
            }
        }
    
    def train_from_history(self, historical_runs: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Train clustering model from historical runs.
        
        Args:
            historical_runs: List of historical run data
            
        Returns:
            Training metrics
        """
        # Clustering is unsupervised - training happens in cluster_workloads()
        # This method just validates we have enough data
        
        if not SKLEARN_AVAILABLE:
            return {'status': 'error', 'message': 'scikit-learn not available'}
        
        if len(historical_runs) < 5:
            return {'status': 'insufficient_data',
                   'message': f'Need at least 5 runs (have {len(historical_runs)})'}
        
        # Perform clustering to "train"
        result = self.cluster_workloads(historical_runs)
        
        if result['status'] != 'complete':
            return result
        
        # Save model
        self._save_model()
        
        return {
            'status': 'success',
            'model': 'KMeans',
            'num_clusters': self.n_clusters,
            'training_samples': len(historical_runs),
            'silhouette_score': result.get('silhouette_score', 0)
        }
    
    def _save_model(self):
        """Save trained model to disk."""
        try:
            with open(self.models_dir / "workload_clusterer.pkl", 'wb') as f:
                pickle.dump(self.model, f)
            with open(self.models_dir / "workload_scaler.pkl", 'wb') as f:
                pickle.dump(self.scaler, f)
            if self.pca:
                with open(self.models_dir / "workload_pca.pkl", 'wb') as f:
                    pickle.dump(self.pca, f)
        except Exception as e:
            print(f"[WARNING] Could not save workload clusterer: {e}")
