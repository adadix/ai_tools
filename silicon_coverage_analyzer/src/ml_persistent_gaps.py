"""
ML Persistent Gaps Analyzer

Analyzes all historical coverage data to identify events that have
NEVER toggled across all stress test runs.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)


def generate_persistent_gaps_analysis(data_directory, product_id: str = None) -> str:
    """
    Analyze all historical data to find events that have NEVER toggled 
    across all stress runs, grouped by domain.
    
    Args:
        data_directory: Path to ML data directory (str or Path)
        product_id: Optional product identifier for product-specific analysis
        
    Returns:
        str: HTML content with persistent gaps analysis
    """
    try:
        # Convert to Path if string
        if isinstance(data_directory, str):
            data_directory = Path(data_directory)
        
        # Use product-specific directory if available
        if product_id:
            raw_data_dir = data_directory / 'raw_datasets' / product_id
        else:
            # Try new structure first, fallback to old
            raw_data_dir = data_directory / 'raw_datasets'
            if not raw_data_dir.exists():
                raw_data_dir = data_directory / 'raw_data'
        
        if not raw_data_dir.exists():
            return ""
        
        # Collect all coverage data files (including subdirectories if no product specified)
        if product_id:
            coverage_files = sorted(raw_data_dir.glob('coverage_*.json'))
        else:
            # If no product specified, collect from all product subdirectories
            coverage_files = sorted(raw_data_dir.glob('*/coverage_*.json'))
            if not coverage_files:
                # Fallback to old structure
                coverage_files = sorted(raw_data_dir.glob('coverage_*.json'))
        
        if not coverage_files:
            return ""
        
        # Track events that are consistently inactive across ALL runs
        # Structure: {domain: {event_name: [inactive_count, total_count]}}
        event_tracking = {}
        total_runs = 0
        
        for coverage_file in coverage_files:
            try:
                with open(coverage_file, 'r') as f:
                    data = json.load(f)
                
                total_runs += 1
                domain_results = data.get('coverage_results', {}).get('domain_results', {})
                
                for domain, domain_data in domain_results.items():
                    if domain not in event_tracking:
                        event_tracking[domain] = {}
                    
                    # Track active events
                    active_events = domain_data.get('active_events', [])
                    active_event_names = {e.get('event') for e in active_events if isinstance(e, dict)}
                    
                    # Track inactive events
                    inactive_events = domain_data.get('inactive_events', [])
                    for event in inactive_events:
                        if isinstance(event, dict):
                            event_name = event.get('event', 'Unknown')
                            status = event.get('status', 'unknown')
                            
                            # Only track truly inactive events (not unavailable/error)
                            if status in ['no_activity', 'low_activity']:
                                if event_name not in event_tracking[domain]:
                                    event_tracking[domain][event_name] = [0, 0]
                                event_tracking[domain][event_name][0] += 1  # Inactive count
                                event_tracking[domain][event_name][1] += 1  # Total count
                    
                    # Also track events that were active (so we know they CAN toggle)
                    for event_name in active_event_names:
                        if event_name not in event_tracking[domain]:
                            event_tracking[domain][event_name] = [0, 0]
                        # Inactive count stays 0, but increment total
                        event_tracking[domain][event_name][1] += 1
            
            except Exception as e:
                logger.warning(f"Error processing {coverage_file}: {e}")
                continue
        
        if total_runs == 0:
            return ""
        
        # Find events that have NEVER been active (100% inactive rate)
        persistent_gaps = {}
        for domain, events in event_tracking.items():
            persistent_gaps[domain] = []
            for event_name, counts in events.items():
                # counts is a list [inactive_count, total_count]
                # Debug: check what type counts actually is
                if not isinstance(counts, list) or len(counts) != 2:
                    logger.warning(f"Unexpected counts format for {event_name} in {domain}: {counts} (type: {type(counts)})")
                    continue
                
                # Ensure they're integers (in case loaded from JSON as strings)
                try:
                    inactive_count = int(counts[0]) if counts[0] is not None else 0
                    total_count = int(counts[1]) if counts[1] is not None else 0
                except (ValueError, TypeError) as e:
                    logger.warning(f"Invalid counts for {event_name} in {domain}: counts[0]={counts[0]} (type={type(counts[0])}), counts[1]={counts[1]} (type={type(counts[1])}), error: {e}")
                    continue
                
                if total_count > 0:
                    try:
                        inactive_rate = (inactive_count / total_count) * 100
                    except TypeError as div_err:
                        logger.error(f"Division error for {event_name} in {domain}: inactive_count={inactive_count} (type={type(inactive_count).__name__}), total_count={total_count} (type={type(total_count).__name__}), error: {div_err}")
                        continue
                    
                    if inactive_rate == 100.0:  # Never toggled
                        persistent_gaps[domain].append({
                            'event': event_name,
                            'runs_tested': total_count,
                            'inactive_rate': inactive_rate
                        })
            
            # Sort by event name
            persistent_gaps[domain].sort(key=lambda x: x['event'])
        
        # Generate HTML
        html = f"""
        <div class="chart-container">
            <h3 style="color: #0071c5; margin-bottom: 10px;">[HIGH] Persistent Coverage Gaps</h3>
            <p style="color: #6c757d; margin-bottom: 15px;">
                Events that have <strong>NEVER toggled</strong> across all {total_runs} historical runs
            </p>
        """
        
        # Generate tables for each domain
        for domain in sorted(persistent_gaps.keys()):
            gaps = persistent_gaps[domain]
            if not gaps:
                continue
            
            gap_count = len(gaps)
            # Add data-domain attribute for filtering
            html += f"""
            <div class="persistent-gap-domain" data-domain="{domain}" style="margin-bottom: 25px; border: 1px solid #dee2e6; border-radius: 8px; padding: 15px; background: #f8f9fa;">
                <h4 style="color: #495057; margin-top: 0;">
                    {domain.upper()} Domain
                    <span style="background: #dc3545; color: white; padding: 3px 10px; border-radius: 12px; font-size: 12px; margin-left: 10px;">
                        {gap_count} never toggled
                    </span>
                </h4>
                <div style="max-height: 300px; overflow-y: auto;">
                    <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
                        <thead>
                            <tr style="background: #e9ecef; position: sticky; top: 0;">
                                <th style="text-align: left; padding: 8px; border: 1px solid #dee2e6;">Event Name</th>
                                <th style="text-align: center; padding: 8px; border: 1px solid #dee2e6;">Runs Tested</th>
                                <th style="text-align: center; padding: 8px; border: 1px solid #dee2e6;">Status</th>
                            </tr>
                        </thead>
                        <tbody>
            """
            
            for gap in gaps:
                event_name = gap['event']
                runs_tested = gap['runs_tested']
                
                html += f"""
                            <tr>
                                <td style="padding: 6px 8px; border: 1px solid #dee2e6; font-family: monospace; font-size: 12px;">
                                    {event_name}
                                </td>
                                <td style="text-align: center; padding: 6px 8px; border: 1px solid #dee2e6;">
                                    {runs_tested}
                                </td>
                                <td style="text-align: center; padding: 6px 8px; border: 1px solid #dee2e6;">
                                    <span style="background: #dc3545; color: white; padding: 2px 8px; border-radius: 10px; font-size: 11px;">
                                        NEVER ACTIVE
                                    </span>
                                </td>
                            </tr>
                """
            
            html += """
                        </tbody>
                    </table>
                </div>
            </div>
            """
        
        # Summary statistics
        total_gaps = sum(len(gaps) for gaps in persistent_gaps.values())
        if total_gaps > 0:
            html += f"""
            <div style="background: #fff3cd; border: 1px solid #ffc107; border-radius: 8px; padding: 15px; margin-top: 15px;">
                <strong> Summary:</strong>
                <ul style="margin: 10px 0 0 0; padding-left: 20px;">
                    <li><strong>{total_gaps} events</strong> have never toggled across all {total_runs} historical runs</li>
                    <li><strong>Recommendation:</strong> These events may require:
                        <ul>
                            <li>Different workload types (e.g., memory-intensive, I/O-bound, FP-heavy)</li>
                            <li>Specific hardware configurations or power states</li>
                            <li>Investigation to determine if they're expected to be inactive</li>
                        </ul>
                    </li>
                </ul>
            </div>
            """
        else:
            html += """
            <div style="background: #d1ecf1; border: 1px solid #0dcaf0; border-radius: 8px; padding: 15px;">
                <strong>[OK] Excellent!</strong> All tested events have toggled at least once across the collected runs.
            </div>
            """
        
        html += """
        </div>
        """
        
        return html
        
    except Exception as e:
        logger.error(f"Error generating persistent gaps analysis: {e}")
        return ""
