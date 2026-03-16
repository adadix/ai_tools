#!/usr/bin/env python3
"""
Gap Detector Module

INTEL CONFIDENTIAL - INTERNAL USE ONLY

Detects coverage gaps and identifies non-toggling EMON events that indicate
areas where silicon is not being exercised during testing.
"""

try:
    from src.ml_client import MLClient
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False
    # ML client not available - will use statistical analysis only

class GapDetector:
    """Detects and analyzes coverage gaps in silicon testing."""
    
    def __init__(self, config):
        self.config = config
        self.thresholds = config.get('coverage_thresholds', {
            'good': 80,
            'warning': 50,
            'critical': 20
        })
        # Use same threshold as collector for consistency
        self.min_activity = config.get('min_activity_threshold', 100)
        
        # Initialize ML client for advanced anomaly detection
        self.ml_client = None
        self.debug = config.get('debug', False)
        if ML_AVAILABLE and config.get('ml_api', {}).get('enabled', False):
            try:
                self.ml_client = MLClient(config)
                if self.ml_client.local_models_available and self.debug:
                    print("[ML] [OK] ML-powered anomaly detection enabled")
            except Exception as e:
                if self.debug:
                    print(f"[ML] [WARN] ML client initialization failed: {e}")
                self.ml_client = None
        
    def classify_coverage_level(self, percentage):
        """Classify coverage level based on percentage."""
        if percentage >= self.thresholds['good']:
            return 'good'
        elif percentage >= self.thresholds['warning']:
            return 'warning'
        elif percentage >= self.thresholds['critical']:
            return 'poor'
        else:
            return 'critical'
    
    def identify_non_toggling_events(self, coverage_results):
        """Identify events that are not toggling (indicating coverage gaps)."""
        non_toggling_events = []
        
        # Handle both data structure formats
        domain_results_key = 'domains_analyzed' if 'domains_analyzed' in coverage_results else 'domain_results'
        
        if domain_results_key not in coverage_results:
            return non_toggling_events
        
        for domain, domain_result in coverage_results[domain_results_key].items():
            if not domain_result.get('success', True):
                continue
                
            # Add inactive events to non-toggling list
            for inactive_event in domain_result.get('inactive_events', []):
                event_status = inactive_event.get('status', 'low_activity')
                total_activity = inactive_event.get('total_activity', 0)
                
                # Determine reason based on status
                if event_status == 'event_not_exists':
                    reason = 'event_not_exists'
                elif event_status == 'not_found':
                    reason = 'not_found'
                elif event_status == 'no_file':
                    reason = 'no_file'
                elif total_activity == 0:
                    reason = 'no_activity'
                else:
                    reason = 'low_activity'
                
                # Estimate priority for ML training
                priority = self._estimate_gap_priority(
                    inactive_event['event'], 
                    domain, 
                    reason,
                    'functional' if 'INST_RETIRED' in inactive_event['event'] else 'performance'
                )
                
                non_toggling_events.append({
                    'domain': domain,
                    'event': inactive_event['event'],
                    'event_name': inactive_event['event'],  # Alias for ML training
                    'total_activity': total_activity,
                    'reason': reason,
                    'status': event_status,
                    'gap_type': 'functional' if 'INST_RETIRED' in inactive_event['event'] else 'performance',
                    'priority': priority  # Add priority for ML training
                })
        
        return non_toggling_events
    
    def analyze_domain_gaps(self, domain_results, coverage_results):
        """Analyze gaps per domain."""
        domain_gaps = {}
        
        # Handle both data structure formats
        domain_coverage_key = 'domain_coverage' if 'domain_coverage' in coverage_results else 'domain_results'
        
        for domain, domain_data in domain_results.items():
            if not domain_data.get('available'):
                domain_gaps[domain] = {
                    'status': 'unavailable',
                    'gap_type': 'infrastructure',
                    'severity': 'critical',
                    'total_events': 0,
                    'tested_events': 0,
                    'coverage_percentage': 0
                }
                continue
            
            coverage_data = coverage_results.get(domain_coverage_key, {}).get(domain, {})
            
            # Handle both 'coverage_percentage' and 'activity_rate'
            coverage_percentage = coverage_data.get('coverage_percentage', coverage_data.get('activity_rate', 0))
            
            total_events = domain_data.get('total_events', len(domain_data.get('events', [])))
            tested_events = coverage_data.get('total_tested', 0)
            
            # Calculate testing gap
            testing_gap = total_events - tested_events
            testing_coverage = (tested_events / total_events * 100) if total_events > 0 else 0
            
            domain_gaps[domain] = {
                'status': 'analyzed',
                'total_events': total_events,
                'tested_events': tested_events,
                'untested_events': testing_gap,
                'testing_coverage_percentage': testing_coverage,
                'activity_coverage_percentage': coverage_percentage,
                'overall_coverage': min(testing_coverage, coverage_percentage),
                'gap_type': self._determine_gap_type(domain, coverage_percentage),
                'severity': self.classify_coverage_level(coverage_percentage)
            }
        
        return domain_gaps
    
    def _determine_gap_type(self, domain, coverage_percentage):
        """Determine the type of gap based on domain and coverage."""
        domain_lower = domain.lower()
        
        # Use pattern matching for future-proof domain detection
        if any(x in domain_lower for x in ['core', 'atom', 'cpu']):
            if coverage_percentage < 50:
                return 'core_functionality'
            else:
                return 'performance_features'
        elif any(x in domain_lower for x in ['imc', 'mc', 'memory', 'hbm', 'ddr']):
            return 'memory_subsystem'
        elif any(x in domain_lower for x in ['cbo', 'cha', 'llc', 'cache']):
            return 'cache_subsystem'
        elif any(x in domain_lower for x in ['ncu', 'upi', 'mesh', 'm3upi']):
            return 'interconnect_subsystem'
        elif any(x in domain_lower for x in ['cbo', 'cha']):
            return 'cache_coherency'
        elif any(x in domain_lower for x in ['ncu', 'upi', 'mesh']):
            return 'interconnect'
        elif 'power' in domain_lower:
            return 'power_management'
        else:
            return 'specialized_unit'
    
    def _estimate_gap_priority(self, event_name: str, domain: str, reason: str, gap_type: str) -> str:
        """
        Estimate gap priority for ML training.
        Returns: 'critical', 'high', 'medium', or 'low'
        """
        # Critical: Functional gaps in core domains
        if gap_type == 'functional':
            domain_lower = domain.lower()
            if any(x in domain_lower for x in ['core', 'atom', 'cpu']):
                return 'critical'
            else:
                return 'high'
        
        # High: Core domain performance gaps
        domain_lower = domain.lower()
        if any(x in domain_lower for x in ['core', 'atom', 'cpu']):
            return 'high'
        
        # Medium: Memory/cache subsystem gaps
        if any(x in domain_lower for x in ['imc', 'mc', 'memory', 'cbo', 'cha', 'cache']):
            return 'medium'
        
        # Low: Events that don't exist (not actionable)
        if reason in ['event_not_exists', 'not_found', 'no_file']:
            return 'low'
        
        # Default to medium
        return 'medium'
    
    def identify_critical_gaps(self, domain_gaps, non_toggling_events):
        """Identify critical gaps that need immediate attention."""
        critical_gaps = []
        
        # Domain-level critical gaps
        for domain, gap_data in domain_gaps.items():
            if gap_data['severity'] == 'critical':
                critical_gaps.append({
                    'type': 'domain_coverage',
                    'domain': domain,
                    'coverage': gap_data.get('overall_coverage', 0),
                    'gap_type': gap_data['gap_type'],
                    'impact': 'high',
                    'recommendation': self._get_domain_recommendation(domain, gap_data)
                })
        
        # Event-level critical gaps
        functional_gaps = [e for e in non_toggling_events if e['gap_type'] == 'functional']
        if len(functional_gaps) > 10:  # Many functional events not toggling
            critical_gaps.append({
                'type': 'functional_coverage',
                'affected_events': len(functional_gaps),
                'domains': list(set(e['domain'] for e in functional_gaps)),
                'impact': 'high',
                'recommendation': 'Review test workload to ensure basic functionality is being exercised'
            })
        
        return critical_gaps
    
    def _get_domain_recommendation(self, domain, gap_data):
        """Get recommendation for addressing domain gaps."""
        gap_type = gap_data['gap_type']
        
        recommendations = {
            'core_functionality': 'Add workloads that exercise basic CPU instructions and operations',
            'performance_features': 'Include performance-intensive workloads to activate advanced features',
            'memory_subsystem': 'Add memory-intensive workloads with various access patterns',
            'cache_coherency': 'Include multi-threaded workloads with shared memory access',
            'interconnect': 'Add workloads that stress inter-core communication',
            'power_management': 'Include power state transitions and DVFS testing',
            'specialized_unit': 'Investigate specific unit requirements and add targeted tests'
        }
        
        return recommendations.get(gap_type, 'Review domain-specific testing requirements')
    
    def generate_gap_summary(self, domain_gaps, non_toggling_events, critical_gaps):
        """Generate summary of all identified gaps."""
        total_domains = len(domain_gaps)
        critical_domains = len([d for d in domain_gaps.values() if d.get('severity') == 'critical'])
        
        return {
            'summary': {
                'total_domains_analyzed': total_domains,
                'critical_coverage_domains': critical_domains,
                'total_non_toggling_events': len(non_toggling_events),
                'critical_gaps_identified': len(critical_gaps)
            },
            'coverage_distribution': {
                'good': len([d for d in domain_gaps.values() if d.get('severity') == 'good']),
                'warning': len([d for d in domain_gaps.values() if d.get('severity') == 'warning']),
                'poor': len([d for d in domain_gaps.values() if d.get('severity') == 'poor']),
                'critical': critical_domains
            },
            'gap_types': {
                'functional': len([e for e in non_toggling_events if e['gap_type'] == 'functional']),
                'performance': len([e for e in non_toggling_events if e['gap_type'] == 'performance'])
            }
        }
    
    def detect_ml_anomalies(self, coverage_results, context=None):
        """Detect anomalies using ML if available."""
        if not self.ml_client or not self.ml_client.local_models_available:
            return {}
        
        ml_anomalies = {}
        
        try:
            # Get domain results
            domain_results_key = 'domains_analyzed' if 'domains_analyzed' in coverage_results else 'domain_results'
            
            if domain_results_key not in coverage_results:
                return {}
            
            # Run ML anomaly detection for each domain
            for domain, domain_result in coverage_results[domain_results_key].items():
                if not domain_result.get('success', True):
                    continue
                
                # Prepare event data for ML analysis
                event_data = {}
                for event_info in domain_result.get('active_events', []):
                    event_name = event_info.get('event')
                    event_data[event_name] = {
                        'total': event_info.get('total_activity', 0),
                        'per_core': event_info.get('per_core', {})
                    }
                
                if event_data:
                    # Call ML API for anomaly detection
                    anomalies = self.ml_client.detect_anomalies(event_data, domain, context)
                    if anomalies:
                        ml_anomalies[domain] = anomalies
                        if self.debug:
                            print(f"[ML] Found {len(anomalies)} anomalies in {domain}")
            
            return ml_anomalies
            
        except Exception as e:
            if self.debug:
                print(f"[ML] Error in anomaly detection: {e}")
            return {}
    
    def analyze_gaps(self, domain_results, coverage_results, context=None):
        """Perform comprehensive gap analysis with optional ML enhancement."""
        # Identify non-toggling events
        non_toggling_events = self.identify_non_toggling_events(coverage_results)
        
        # Analyze domain-level gaps
        domain_gaps = self.analyze_domain_gaps(domain_results, coverage_results)
        
        # Identify critical gaps
        critical_gaps = self.identify_critical_gaps(domain_gaps, non_toggling_events)
        
        # ML-powered anomaly detection (if enabled)
        ml_anomalies = self.detect_ml_anomalies(coverage_results, context)
        
        # Generate summary
        gap_summary = self.generate_gap_summary(domain_gaps, non_toggling_events, critical_gaps)
        
        return {
            'non_toggling_events': non_toggling_events,
            'domain_gaps': domain_gaps,
            'critical_gaps': critical_gaps,
            'gap_summary': gap_summary,
            'ml_anomalies': ml_anomalies  # New: ML-detected anomalies
        }