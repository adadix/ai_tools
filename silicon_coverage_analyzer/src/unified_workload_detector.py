"""
Unified Workload Detector - Single Source of Truth

Consolidates all workload detection methods into one authoritative detector
with clear confidence scores and detection method transparency.

Detection Priority:
1. Process Detection (90% confidence) - Direct OS process monitoring
2. ML Pattern Detection (75% confidence) - Machine learning based on event patterns
3. Heuristic Detection (60% confidence) - Rule-based fallback

Author: Intel Corporation
Date: December 2025
"""

import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class WorkloadDetectionResult:
    """Result of workload detection with full transparency."""
    workload: str
    confidence: float
    method: str  # 'process', 'ml_pattern', 'heuristic'
    evidence: List[str]
    alternative_detections: List[Dict[str, Any]]  # Other possible workloads
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'workload': self.workload,
            'confidence': self.confidence,
            'method': self.method,
            'evidence': self.evidence,
            'alternative_detections': self.alternative_detections
        }


class UnifiedWorkloadDetector:
    """
    Unified workload detector that consolidates all detection methods.
    
    This is the SINGLE SOURCE OF TRUTH for workload detection.
    Replaces fragmented logic across multiple modules.
    """
    
    def __init__(self, ml_detector=None, stress_tracker=None):
        """
        Initialize unified detector.
        
        Args:
            ml_detector: Optional MLWorkloadDetector instance
            stress_tracker: Optional StressTracker instance
        """
        self.ml_detector = ml_detector
        self.stress_tracker = stress_tracker
        
        # Known stress process patterns
        self.process_patterns = {
            'memicals': {
                'names': ['memicals', 'memicals.exe', 'Memicals'],
                'workload': 'Memicals (Intel Memory Stress)',
                'confidence': 95
            },
            'mlc': {
                'names': ['mlc', 'mlc.exe', 'Memory Latency Checker'],
                'workload': 'MLC (Intel Memory Latency Checker)',
                'confidence': 95
            },
            'sandstone': {
                'names': ['sandstone', 'sandstone.exe'],
                'workload': 'Sandstone (Intel Instruction Validation)',
                'confidence': 95
            },
            'memrunner': {
                'names': ['memrunner', 'memrunner.exe'],
                'workload': 'MemRunner (Intel Memory Stress)',
                'confidence': 95
            },
            'supercollider': {
                'names': ['supercollider', 'super_collider', 'supercollider.exe'],
                'workload': 'SuperCollider (Intel Multi-Component Stress)',
                'confidence': 95
            },
            'stressapptest': {
                'names': ['stressapptest', 'stressapptest.exe'],
                'workload': 'StressAppTest',
                'confidence': 90
            },
            'prime95': {
                'names': ['prime95', 'prime95.exe', 'mprime'],
                'workload': 'Prime95 (CPU Stress)',
                'confidence': 90
            },
            'linpack': {
                'names': ['linpack', 'xlinpack', 'linpack.exe'],
                'workload': 'Linpack (FP Math Stress)',
                'confidence': 90
            },
            'memtest': {
                'names': ['memtest', 'memtest86', 'memtester'],
                'workload': 'MemTest (Memory Stress)',
                'confidence': 90
            },
            'stress-ng': {
                'names': ['stress-ng', 'stress'],
                'workload': 'Stress-NG (Linux Multi-Stress)',
                'confidence': 90
            },
            'stream': {
                'names': ['stream', 'stream.exe'],
                'workload': 'Stream (Memory Bandwidth)',
                'confidence': 90
            }
        }
    
    def detect(self, coverage: Dict, metadata: Dict) -> WorkloadDetectionResult:
        """
        Detect workload using priority cascade.
        
        Args:
            coverage: Coverage data with event statistics
            metadata: Run metadata including process info
            
        Returns:
            WorkloadDetectionResult with full transparency
        """
        all_detections = []
        
        # Priority 1: Process Detection (Most Reliable)
        process_result = self._detect_from_processes(metadata)
        if process_result:
            all_detections.append(process_result)
            if process_result['confidence'] >= 85:
                return WorkloadDetectionResult(
                    workload=process_result['workload'],
                    confidence=process_result['confidence'],
                    method='process',
                    evidence=process_result['evidence'],
                    alternative_detections=all_detections[1:] if len(all_detections) > 1 else []
                )
        
        # Priority 2: ML Pattern Detection (Trained Models)
        if self.ml_detector and hasattr(self.ml_detector, 'is_trained') and self.ml_detector.is_trained():
            ml_result = self._detect_from_ml(coverage)
            if ml_result:
                all_detections.append(ml_result)
                if ml_result['confidence'] >= 75:
                    return WorkloadDetectionResult(
                        workload=ml_result['workload'],
                        confidence=ml_result['confidence'],
                        method='ml_pattern',
                        evidence=ml_result['evidence'],
                        alternative_detections=all_detections[1:] if len(all_detections) > 1 else []
                    )
        
        # Priority 3: Heuristic Detection (Fallback)
        heuristic_result = self._detect_from_heuristics(coverage)
        all_detections.append(heuristic_result)
        
        # Return best detection (highest confidence)
        best = max(all_detections, key=lambda x: x['confidence']) if all_detections else None
        
        if best:
            return WorkloadDetectionResult(
                workload=best['workload'],
                confidence=best['confidence'],
                method=best['method'],
                evidence=best['evidence'],
                alternative_detections=[d for d in all_detections if d != best]
            )
        
        # Ultimate fallback
        return WorkloadDetectionResult(
            workload='Unknown',
            confidence=0,
            method='none',
            evidence=['No workload detected by any method'],
            alternative_detections=[]
        )
    
    def _detect_from_processes(self, metadata: Dict) -> Optional[Dict]:
        """Detect workload from running processes."""
        processes = metadata.get('running_processes', [])
        workload_type = metadata.get('workload_type', '').lower()
        stress_confidence = metadata.get('stress_confidence', 0)
        
        # Check process list
        for process in processes:
            process_name = process.lower() if isinstance(process, str) else str(process).lower()
            for pattern_key, pattern_info in self.process_patterns.items():
                if any(name.lower() in process_name for name in pattern_info['names']):
                    return {
                        'workload': pattern_info['workload'],
                        'confidence': max(pattern_info['confidence'], stress_confidence),
                        'method': 'process',
                        'evidence': [f'Process detected: {process}']
                    }
        
        # Check metadata workload_type (from stress_detection.primary_stress)
        if workload_type and workload_type != 'unknown':
            # Map common stress type labels
            workload_label = workload_type.title()
            if 'memory' in workload_type.lower():
                workload_label = 'Memory Stress'
            elif 'cpu' in workload_type.lower():
                workload_label = 'CPU Stress'
            elif 'memicals' in workload_type.lower():
                workload_label = 'Memicals (Intel Memory Stress)'
            elif 'intel' in workload_type.lower():
                workload_label = workload_type  # Keep Intel tool labels
                
            return {
                'workload': workload_label,
                'confidence': max(85, stress_confidence),
                'method': 'process',
                'evidence': [f'Workload type from stress detection: {workload_type}']
            }
        
        return None
    
    def _detect_from_ml(self, coverage: Dict) -> Optional[Dict]:
        """Detect workload using ML model."""
        try:
            result = self.ml_detector.detect_workload(coverage)
            
            if result and result.get('workload') != 'unknown':
                return {
                    'workload': result['workload'],
                    'confidence': result.get('confidence', 0),
                    'method': 'ml_pattern',
                    'evidence': [
                        f"ML model prediction based on event activation patterns",
                        f"Training data: {result.get('training_samples', 0)} runs"
                    ]
                }
        except Exception as e:
            logger.warning(f"ML detection failed: {e}")
        
        return None
    
    def _detect_from_heuristics(self, coverage: Dict) -> Dict:
        """Detect workload using simple heuristics (fallback)."""
        domain_results = coverage.get('domain_results', {})
        
        # Memory-intensive heuristic
        memory_domains = ['imc', 'cha', 'upi']
        memory_coverage = sum(
            domain_results.get(d, {}).get('coverage_percentage', 0)
            for d in memory_domains if d in domain_results
        ) / len(memory_domains) if memory_domains else 0
        
        # CPU-intensive heuristic
        cpu_domains = ['core', 'p-core', 'e-core']
        cpu_coverage = sum(
            domain_results.get(d, {}).get('coverage_percentage', 0)
            for d in cpu_domains if d in domain_results
        ) / len([d for d in cpu_domains if d in domain_results]) if any(d in domain_results for d in cpu_domains) else 0
        
        # Determine workload type
        if memory_coverage > cpu_coverage + 20:
            workload = 'Memory Stress (Inferred)'
            confidence = 65
            evidence = [f'High memory domain activity ({memory_coverage:.1f}% avg coverage)']
        elif cpu_coverage > memory_coverage + 20:
            workload = 'CPU Stress (Inferred)'
            confidence = 65
            evidence = [f'High CPU domain activity ({cpu_coverage:.1f}% avg coverage)']
        elif memory_coverage > 30 and cpu_coverage > 30:
            workload = 'Mixed Workload (Inferred)'
            confidence = 60
            evidence = [f'Balanced activity: CPU {cpu_coverage:.1f}%, Memory {memory_coverage:.1f}%']
        else:
            workload = 'Light/Idle (Inferred)'
            confidence = 50
            evidence = ['Low overall activity across domains']
        
        return {
            'workload': workload,
            'confidence': confidence,
            'method': 'heuristic',
            'evidence': evidence
        }
