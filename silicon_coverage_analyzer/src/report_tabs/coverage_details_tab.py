"""
Coverage Details Tab Generator Module

Generates the Coverage Details tab for the HTML report.
Contains unified coverage views, hottest events, and domain breakdowns.
"""

import json
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

# Domain colors for charts
DOMAIN_COLORS = {
    'core': '#0071C5',
    'uncore': '#388e3c',
    'p-core': '#0071C5',
    'e-core': '#7b1fa2',
    'atom': '#7b1fa2',
    'gpu': '#ff5722',
    'gt': '#ff5722',
    'memory': '#00bcd4',
    'io': '#795548',
    'pcie': '#795548',
    'unknown': '#9e9e9e'
}


class CoverageDetailsTabGenerator:
    """Generates the Coverage Details tab content."""
    
    def __init__(self, report_generator):
        """
        Initialize with reference to parent ReportGenerator.
        
        Args:
            report_generator: Parent ReportGenerator instance
        """
        self.rg = report_generator
    
    def generate(self, analysis_results: Dict[str, Any]) -> str:
        """
        Generate Coverage Details tab HTML.
        
        Args:
            analysis_results: Full analysis results
            
        Returns:
            HTML string for the coverage details tab
        """
        coverage = analysis_results.get('coverage', {})
        
        # Ensure categories are loaded
        hw_config = analysis_results.get('hardware_config', {})
        product_id = hw_config.get('product_id') or hw_config.get('product_name', '').lower().replace(' ', '_').replace('-', '_')
        if not self.rg.instruction_categories_loaded and product_id:
            self.rg._load_instruction_categories(product_id)
        
        # Generate domain options
        domain_results = coverage.get('domain_results', {})
        domain_options = self._generate_domain_options(domain_results)
        
        # Build HTML
        html = self._generate_header(domain_options)
        
        # Quick stats
        gaps_analysis = analysis_results.get('gaps', {})
        ml_analysis = analysis_results.get('ml_analysis', {})
        html += self._generate_quick_stats(coverage, gaps_analysis, ml_analysis, domain_results)
        
        # Unified chart and JavaScript
        html += self._generate_unified_charts(coverage, gaps_analysis, ml_analysis)
        
        # Real-time insights
        html += self._generate_realtime_insights(coverage, gaps_analysis, ml_analysis)
        
        # All events visualization
        all_events = self._collect_all_events(coverage)
        html += self._generate_all_events_chart(all_events)
        
        # Hottest events table
        html += self._generate_hottest_events_table(all_events)
        
        # Domain breakdown
        html += self._generate_domain_breakdown(coverage)
        
        html += """
            </div>
        </div>
        """
        
        return html
    
    def _generate_domain_options(self, domain_results: Dict) -> str:
        """Generate domain filter options HTML."""
        options = '<option value="all">All Domains</option>\n'
        for domain in sorted(domain_results.keys()):
            domain_display = domain.upper().replace('_', ' ')
            options += f'                    <option value="{domain.lower()}">{domain_display}</option>\n'
        return options
    
    def _generate_header(self, domain_options: str) -> str:
        """Generate header section with interpretation guide."""
        return f"""
        <div id="coverage-details" class="tab-content">
            <h2 class="section-title">Coverage Details</h2>
            
            <!-- Interpretation Guide -->
            <div style="background: linear-gradient(135deg, #ffeaa7 0%, #fdcb6e 100%); border-left: 5px solid #e17055; padding: 20px; margin-bottom: 25px; border-radius: 8px;">
                <h3 style="margin: 0 0 10px 0; color: #d63031;">How to Interpret This Tab</h3>
                <p style="margin: 5px 0; color: #d63031; line-height: 1.5; font-size: 0.95em;">
                    <strong>Unified Coverage View:</strong> Interactive charts with Overview/By Domain/Gaps Focus modes and search.<br>
                    <strong>Real-Time Insights:</strong> Live coverage quality metrics and event distribution analysis.<br>
                    <strong>Active Events:</strong> All events that toggled during collection, sorted by activity level.<br>
                    <strong>Hottest Events:</strong> Top performers across all domains indicating workload characteristics.<br>
                    <strong>Domain Breakdown:</strong> Per-domain coverage with bar charts, active/inactive event lists.
                </p>
            </div>
            
            <!-- Unified Coverage View -->
            <div style="background: white; padding: 25px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); margin-bottom: 30px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                    <h3 style="margin: 0; color: #0071C5;">Unified Coverage View</h3>
                    <div style="display: flex; gap: 10px; align-items: center;">
                        <button onclick="switchCoverageView('overview')" id="view-btn-overview" class="view-mode-btn" style="padding: 8px 16px; background: #0071C5; color: white; border: none; border-radius: 6px; cursor: pointer; font-weight: 600;">Overview</button>
                        <button onclick="switchCoverageView('domains')" id="view-btn-domains" class="view-mode-btn" style="padding: 8px 16px; background: #e0e0e0; color: #333; border: none; border-radius: 6px; cursor: pointer; font-weight: 600;">By Domain</button>
                        <button onclick="switchCoverageView('gaps')" id="view-btn-gaps" class="view-mode-btn" style="padding: 8px 16px; background: #e0e0e0; color: #333; border: none; border-radius: 6px; cursor: pointer; font-weight: 600;">Gaps Focus</button>
                        
                        <select id="domain-filter-unified" onchange="filterUnifiedView()" style="padding: 8px; border: 1px solid #ccc; border-radius: 4px; min-width: 150px;">
{domain_options}                        </select>
                        
                        <input type="text" id="event-search" placeholder="Search events..." oninput="searchEvents()" style="padding: 8px 12px; border: 1px solid #ccc; border-radius: 6px; width: 200px;">
                        <button onclick="clearEventSearch()" style="padding: 8px 12px; background: #6c757d; color: white; border: none; border-radius: 6px; cursor: pointer;">Clear</button>
                    </div>
                </div>
                
                <div id="search-results-container" style="display: none; margin-bottom: 20px; padding: 15px; background: #e3f2fd; border-radius: 8px; border: 2px solid #0071C5;"></div>
"""
    
    def _generate_quick_stats(self, coverage: Dict, gaps_analysis: Dict, 
                              ml_analysis: Dict, domain_results: Dict) -> str:
        """Generate quick statistics section."""
        # Get flaky events from ML analysis
        flaky_events_list = []
        if ml_analysis:
            event_trends = ml_analysis.get('event_trends', {})
            if isinstance(event_trends, dict):
                flaky_events_list = event_trends.get('flaky', [])
        
        # Get active events count
        active_events_count = coverage.get('active_events', 0)
        if active_events_count == 0:
            active_events_count = sum(
                len(stats.get('active_events', []))
                for stats in domain_results.values()
            )
        
        total_domains_count = len(domain_results)
        gap_events_count = len(gaps_analysis.get('non_toggling_events', []))
        flaky_events_count = len(flaky_events_list)
        
        return f"""
                <div id="unified-view-overview" class="unified-view-container">
                    <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin-bottom: 15px;">
                        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px;">
                            <div style="text-align: center; padding: 15px; background: white; border-radius: 6px;">
                                <div style="font-size: 2em; font-weight: bold; color: #28a745;">{active_events_count}</div>
                                <div style="color: #666; margin-top: 5px;">Active Events</div>
                            </div>
                            <div style="text-align: center; padding: 15px; background: white; border-radius: 6px;">
                                <div style="font-size: 2em; font-weight: bold; color: #dc3545;">{gap_events_count}</div>
                                <div style="color: #666; margin-top: 5px;">Gap Events</div>
                            </div>
                            <div style="text-align: center; padding: 15px; background: white; border-radius: 6px;">
                                <div style="font-size: 2em; font-weight: bold; color: #ffc107;">{flaky_events_count}</div>
                                <div style="color: #666; margin-top: 5px;">Flaky Events</div>
                            </div>
                            <div style="text-align: center; padding: 15px; background: white; border-radius: 6px;">
                                <div style="font-size: 2em; font-weight: bold; color: #0071C5;">{total_domains_count}</div>
                                <div style="color: #666; margin-top: 5px;">PMU Domains</div>
                            </div>
                        </div>
                    </div>
                    
                    <canvas id="unifiedCoverageChart" style="max-height: 400px;"></canvas>
                    
                    <div style="margin-top: 15px; padding: 15px; background: #e3f2fd; border-radius: 6px; border-left: 4px solid #0071C5;">
                        <strong style="color: #01579b;">How to Use:</strong>
                        <ul style="margin: 10px 0 0 20px; color: #01579b; line-height: 1.8;">
                            <li><strong>Overview:</strong> See all events together (green = active, red = gaps, yellow = flaky)</li>
                            <li><strong>By Domain:</strong> Filter to specific PMU domains for focused analysis</li>
                            <li><strong>Gaps Focus:</strong> Show only untested events requiring attention</li>
                            <li><strong>Search:</strong> Type event name to find specific counters instantly</li>
                        </ul>
                    </div>
                </div>
                
                <div id="unified-view-domains" class="unified-view-container" style="display: none;">
                    <div id="domain-view-instructions" style="color: #666; margin-bottom: 15px;">
                        <strong>Select a domain</strong> from the dropdown above to see domain-specific coverage breakdown.
                    </div>
                    <div id="domain-specific-content">
                        <canvas id="domainSpecificChart" style="max-height: 400px;"></canvas>
                    </div>
                    <div id="domain-event-list" style="display: none; margin-top: 20px;"></div>
                </div>
                
                <div id="unified-view-gaps" class="unified-view-container" style="display: none;">
                    <p style="color: #dc3545; font-weight: 600; margin-bottom: 15px;">
                        ● Showing only untested events (gaps). These events never toggled during collection.
                    </p>
                    <canvas id="gapsOnlyChart" style="max-height: 400px;"></canvas>
                </div>
"""
    
    def _generate_unified_charts(self, coverage: Dict, gaps_analysis: Dict, ml_analysis: Dict) -> str:
        """Generate unified chart JavaScript."""
        # Get flaky events
        flaky_events_list = []
        if ml_analysis:
            event_trends = ml_analysis.get('event_trends', {})
            if isinstance(event_trends, dict):
                flaky_events_list = event_trends.get('flaky', [])
        
        # Prepare data for charts
        all_events_data = [
            {
                'event': evt.get('event', 'Unknown'),
                'domain': domain,
                'status': 'active',
                'activity': evt.get('total_activity', 0)
            }
            for domain, stats in coverage.get('domain_results', {}).items()
            for evt in stats.get('active_events', [])
        ]
        
        gap_events_data = [
            {
                'event': evt.get('event', 'Unknown'),
                'domain': evt.get('domain', 'unknown'),
                'status': 'gap'
            }
            for evt in gaps_analysis.get('non_toggling_events', [])
        ]
        
        flaky_events_data = [
            {
                'event': evt.get('event', 'Unknown'),
                'domain': evt.get('domain', 'unknown'),
                'status': 'flaky',
                'flake_rate': evt.get('flake_rate', 0)
            }
            for evt in flaky_events_list
        ]
        
        return f"""
                <script>
                    const unifiedCoverageData = {{
                        allEvents: {json.dumps(all_events_data)},
                        gapEvents: {json.dumps(gap_events_data)},
                        flakyEvents: {json.dumps(flaky_events_data)},
                        domainColors: {json.dumps(DOMAIN_COLORS)}
                    }};
                    
                    let unifiedChart, domainChart, gapsChart;
                    
                    window.addEventListener('load', function() {{
                        if (typeof Chart === 'undefined') return;
                        const coverageTab = document.getElementById('coverage-details');
                        if (coverageTab && coverageTab.classList.contains('active')) {{
                            initUnifiedCharts();
                        }}
                    }});
                    
                    function initUnifiedCharts() {{
                        const canvas = document.getElementById('unifiedCoverageChart');
                        if (!canvas) return;
                        
                        if (unifiedChart) {{ unifiedChart.destroy(); unifiedChart = null; }}
                        if (gapsChart) {{ gapsChart.destroy(); gapsChart = null; }}
                        
                        const overviewCtx = canvas.getContext('2d');
                        const allData = [...unifiedCoverageData.allEvents, ...unifiedCoverageData.gapEvents, ...unifiedCoverageData.flakyEvents];
                        
                        const groupedByDomain = {{}};
                        allData.forEach(evt => {{
                            if (!groupedByDomain[evt.domain]) {{
                                groupedByDomain[evt.domain] = {{ active: 0, gap: 0, flaky: 0 }};
                            }}
                            groupedByDomain[evt.domain][evt.status]++;
                        }});
                        
                        const domains = Object.keys(groupedByDomain);
                        unifiedChart = new Chart(overviewCtx, {{
                            type: 'bar',
                            data: {{
                                labels: domains.map(d => d.toUpperCase()),
                                datasets: [
                                    {{ label: 'Active Events', data: domains.map(d => groupedByDomain[d].active), backgroundColor: '#28a745', borderColor: '#1e7e34', borderWidth: 1 }},
                                    {{ label: 'Gap Events', data: domains.map(d => groupedByDomain[d].gap), backgroundColor: '#dc3545', borderColor: '#c82333', borderWidth: 1 }},
                                    {{ label: 'Flaky Events', data: domains.map(d => groupedByDomain[d].flaky), backgroundColor: '#ffc107', borderColor: '#e0a800', borderWidth: 1 }}
                                ]
                            }},
                            options: {{
                                responsive: true,
                                plugins: {{
                                    title: {{ display: true, text: 'Event Coverage by Domain', font: {{ size: 16, weight: 'bold' }} }},
                                    tooltip: {{
                                        callbacks: {{
                                            footer: function(context) {{
                                                const domain = domains[context[0].dataIndex];
                                                const total = groupedByDomain[domain].active + groupedByDomain[domain].gap + groupedByDomain[domain].flaky;
                                                return 'Coverage: ' + ((groupedByDomain[domain].active / total) * 100).toFixed(1) + '%';
                                            }}
                                        }}
                                    }}
                                }},
                                scales: {{ x: {{ stacked: true }}, y: {{ stacked: true, beginAtZero: true }} }}
                            }}
                        }});
                        
                        // Gaps Only Chart
                        const gapsCtx = document.getElementById('gapsOnlyChart').getContext('2d');
                        const gapsByDomain = {{}};
                        unifiedCoverageData.gapEvents.forEach(evt => {{
                            if (!gapsByDomain[evt.domain]) gapsByDomain[evt.domain] = 0;
                            gapsByDomain[evt.domain]++;
                        }});
                        
                        const gapDomains = Object.keys(gapsByDomain);
                        gapsChart = new Chart(gapsCtx, {{
                            type: 'bar',
                            data: {{
                                labels: gapDomains.map(d => d.toUpperCase()),
                                datasets: [{{ label: 'Gap Events', data: gapDomains.map(d => gapsByDomain[d]), backgroundColor: '#dc3545', borderWidth: 2 }}]
                            }},
                            options: {{
                                responsive: true,
                                plugins: {{ title: {{ display: true, text: 'Untested Events by Domain', color: '#dc3545' }} }},
                                scales: {{ y: {{ beginAtZero: true }} }}
                            }}
                        }});
                    }}
                    
                    function switchCoverageView(mode) {{
                        document.querySelectorAll('.view-mode-btn').forEach(btn => {{
                            btn.style.background = '#e0e0e0';
                            btn.style.color = '#333';
                        }});
                        document.getElementById('view-btn-' + mode).style.background = '#0071C5';
                        document.getElementById('view-btn-' + mode).style.color = 'white';
                        
                        document.querySelectorAll('.unified-view-container').forEach(c => c.style.display = 'none');
                        document.getElementById('unified-view-' + mode).style.display = 'block';
                        
                        if (mode === 'domains') renderDomainSpecificChart();
                        if (typeof showToast === 'function') showToast('Switched to ' + mode + ' view');
                    }}
                    
                    function renderDomainSpecificChart() {{
                        const domain = document.getElementById('domain-filter-unified').value;
                        const instructionsDiv = document.getElementById('domain-view-instructions');
                        const eventListDiv = document.getElementById('domain-event-list');
                        
                        if (domain === 'all') {{
                            instructionsDiv.style.display = 'block';
                            eventListDiv.style.display = 'none';
                            return;
                        }}
                        
                        instructionsDiv.style.display = 'none';
                        
                        const domainEvents = unifiedCoverageData.allEvents.filter(e => e.domain.toLowerCase() === domain);
                        const domainGaps = unifiedCoverageData.gapEvents.filter(e => e.domain.toLowerCase() === domain);
                        const domainFlaky = unifiedCoverageData.flakyEvents.filter(e => e.domain.toLowerCase() === domain);
                        
                        const ctx = document.getElementById('domainSpecificChart').getContext('2d');
                        if (domainChart) domainChart.destroy();
                        
                        const total = domainEvents.length + domainGaps.length + domainFlaky.length;
                        const coveragePercent = total > 0 ? ((domainEvents.length / total) * 100).toFixed(1) : 0;
                        
                        domainChart = new Chart(ctx, {{
                            type: 'doughnut',
                            data: {{
                                labels: ['Active (' + domainEvents.length + ')', 'Gaps (' + domainGaps.length + ')', 'Flaky (' + domainFlaky.length + ')'],
                                datasets: [{{ data: [domainEvents.length, domainGaps.length, domainFlaky.length], backgroundColor: ['#28a745', '#dc3545', '#ffc107'] }}]
                            }},
                            options: {{
                                responsive: true,
                                plugins: {{
                                    title: {{ display: true, text: domain.toUpperCase() + ' - ' + coveragePercent + '% Coverage' }},
                                    legend: {{ position: 'bottom' }}
                                }}
                            }}
                        }});
                        
                        eventListDiv.innerHTML = generateDomainEventList(domain, domainEvents, domainGaps);
                        eventListDiv.style.display = 'block';
                    }}
                    
                    function generateDomainEventList(domain, active, gaps) {{
                        let html = '<h4>' + domain.toUpperCase() + ' Events</h4>';
                        html += '<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px;">';
                        html += '<div style="background: #d4edda; padding: 15px; border-radius: 8px;"><h5 style="color: #155724;">Active (' + active.length + ')</h5>';
                        html += '<div style="max-height: 200px; overflow-y: auto; font-family: monospace; font-size: 0.85em;">';
                        active.slice(0, 20).forEach(e => html += '<div style="padding: 2px 0;">' + e.event + '</div>');
                        if (active.length > 20) html += '<div style="color: #666;">+' + (active.length - 20) + ' more...</div>';
                        html += '</div></div>';
                        html += '<div style="background: #f8d7da; padding: 15px; border-radius: 8px;"><h5 style="color: #721c24;">Gaps (' + gaps.length + ')</h5>';
                        html += '<div style="max-height: 200px; overflow-y: auto; font-family: monospace; font-size: 0.85em;">';
                        gaps.slice(0, 20).forEach(e => html += '<div style="padding: 2px 0;">' + e.event + '</div>');
                        if (gaps.length > 20) html += '<div style="color: #666;">+' + (gaps.length - 20) + ' more...</div>';
                        html += '</div></div></div>';
                        return html;
                    }}
                    
                    function filterUnifiedView() {{
                        const domain = document.getElementById('domain-filter-unified').value;
                        if (domain !== 'all') {{
                            switchCoverageView('domains');
                            renderDomainSpecificChart();
                        }} else {{
                            switchCoverageView('overview');
                        }}
                    }}
                    
                    function searchEvents() {{
                        const searchTerm = document.getElementById('event-search').value.toLowerCase();
                        const resultsDiv = document.getElementById('search-results-container');
                        
                        if (searchTerm.length === 0) {{ resultsDiv.style.display = 'none'; return; }}
                        
                        const domainFilter = document.getElementById('domain-filter-unified').value;
                        let allSearchable = [
                            ...unifiedCoverageData.allEvents.map(e => ({{...e, type: 'active'}})),
                            ...unifiedCoverageData.gapEvents.map(e => ({{...e, type: 'gap'}})),
                            ...unifiedCoverageData.flakyEvents.map(e => ({{...e, type: 'flaky'}}))
                        ];
                        
                        if (domainFilter !== 'all') {{
                            allSearchable = allSearchable.filter(e => e.domain.toLowerCase() === domainFilter);
                        }}
                        
                        const matches = allSearchable.filter(e => e.event.toLowerCase().includes(searchTerm));
                        
                        if (matches.length > 0) {{
                            let html = '<div style="font-weight: bold; margin-bottom: 10px;">Found ' + matches.length + ' matching events:</div>';
                            html += '<table style="width: 100%; border-collapse: collapse;"><thead><tr style="background: #f5f5f5;"><th style="padding: 8px; text-align: left;">Event</th><th style="padding: 8px;">Domain</th><th style="padding: 8px;">Status</th></tr></thead><tbody>';
                            matches.slice(0, 50).forEach(evt => {{
                                const color = evt.type === 'active' ? '#28a745' : evt.type === 'gap' ? '#dc3545' : '#ffc107';
                                const label = evt.type === 'active' ? 'Active' : evt.type === 'gap' ? 'Gap' : 'Flaky';
                                html += '<tr><td style="padding: 8px; font-family: monospace;">' + evt.event + '</td><td style="padding: 8px;">' + evt.domain.toUpperCase() + '</td><td style="padding: 8px; text-align: center;"><span style="background: ' + color + '; color: white; padding: 2px 8px; border-radius: 10px;">' + label + '</span></td></tr>';
                            }});
                            html += '</tbody></table>';
                            resultsDiv.innerHTML = html;
                        }} else {{
                            resultsDiv.innerHTML = '<div style="color: #dc3545; text-align: center;">No events found matching "' + searchTerm + '"</div>';
                        }}
                        resultsDiv.style.display = 'block';
                    }}
                    
                    function clearEventSearch() {{
                        document.getElementById('event-search').value = '';
                        document.getElementById('search-results-container').style.display = 'none';
                    }}
                </script>
            </div>
"""
    
    def _collect_all_events(self, coverage: Dict) -> List[Dict]:
        """Collect and sort all events by activity."""
        all_events = []
        for domain, stats in coverage.get('domain_results', {}).items():
            for event in stats.get('active_events', []):
                event['domain'] = domain
                all_events.append(event)
        all_events.sort(key=lambda x: x.get('total_activity', 0), reverse=True)
        return all_events
    
    def _generate_all_events_chart(self, all_events: List[Dict]) -> str:
        """Generate all events scatter plot."""
        all_events_json = json.dumps([
            {'event': evt.get('event', 'Unknown'), 'domain': evt.get('domain', 'unknown'),
             'total': evt.get('total_activity', 0), 'index': i}
            for i, evt in enumerate(all_events[:100])
        ])
        
        return f"""
            <div class="coverage-card" style="margin-bottom: 30px;">
                <h3 class="section-title">ALL ACTIVE EVENTS BY DOMAIN</h3>
                <p style="color: #6c757d; margin-bottom: 20px;">Interactive visualization of active events grouped by domain.</p>
                <canvas id="allEventsChart" style="max-height: 500px;"></canvas>
            </div>
            
            <script>
            (function() {{
                const ctx = document.getElementById('allEventsChart').getContext('2d');
                const allEventsData = {all_events_json};
                const domainColors = {json.dumps(DOMAIN_COLORS)};
                
                const domainGroups = {{}};
                allEventsData.forEach(e => {{
                    if (!domainGroups[e.domain]) domainGroups[e.domain] = [];
                    domainGroups[e.domain].push({{ x: e.index, y: e.total, event: e.event, domain: e.domain }});
                }});
                
                const datasets = Object.keys(domainGroups).map(domain => ({{
                    label: domain.toUpperCase(),
                    data: domainGroups[domain],
                    backgroundColor: domainColors[domain] || '#999',
                    borderColor: domainColors[domain] || '#999',
                    pointRadius: 6,
                    pointHoverRadius: 8
                }}));
                
                window.addEventListener('load', function() {{
                    if (typeof Chart === 'undefined') return;
                    new Chart(ctx, {{
                        type: 'scatter',
                        data: {{ datasets: datasets }},
                        options: {{
                            responsive: true,
                            maintainAspectRatio: false,
                            plugins: {{
                                legend: {{ display: true, position: 'top' }},
                                tooltip: {{
                                    callbacks: {{
                                        label: function(context) {{
                                            const point = context.raw;
                                            return ['Event: ' + point.event, 'Domain: ' + point.domain.toUpperCase(), 'Activity: ' + point.y.toLocaleString()];
                                        }}
                                    }}
                                }}
                            }},
                            scales: {{
                                y: {{ beginAtZero: true, type: 'logarithmic', title: {{ display: true, text: 'Activity Count' }} }},
                                x: {{ title: {{ display: true, text: 'Event Index' }}, ticks: {{ display: false }} }}
                            }}
                        }}
                    }});
                }});
            }})();
            </script>
"""
    
    def _generate_hottest_events_table(self, all_events: List[Dict]) -> str:
        """Generate hottest events table."""
        html = """
            <div class="coverage-card" style="margin-bottom: 50px;">
                <h3 class="section-title">HOTTEST EVENTS ACROSS ALL DOMAINS</h3>
                <p style="color: #6c757d; margin-bottom: 20px;">Top events sorted by total activity count.</p>
                <div style="max-height: 600px; overflow-y: auto; border: 1px solid #ddd; border-radius: 4px;">
                <table class="event-table" id="hottest-events-table" style="margin: 0;">
                    <thead style="position: sticky; top: 0; background: white; z-index: 10;">
                        <tr>
                            <th>Rank</th>
                            <th>Event Name</th>
                            <th>Domain</th>
                            <th>Total Activity</th>
                            <th>Avg/Core</th>
                        </tr>
                    </thead>
                    <tbody>
"""
        
        for i, event in enumerate(all_events[:100], 1):
            domain = event.get('domain', 'Unknown')
            html += f"""
                        <tr data-domain="{domain.lower()}">
                            <td><strong>{i}</strong></td>
                            <td class="counter-detail">{event.get('event', 'Unknown')}</td>
                            <td>{domain.upper()}</td>
                            <td>{event.get('total_activity', 0):,}</td>
                            <td>{event.get('avg_core_count', 0):.1f}</td>
                        </tr>
"""
        
        html += """
                    </tbody>
                </table>
                </div>
            </div>
"""
        return html
    
    def _generate_domain_breakdown(self, coverage: Dict) -> str:
        """Generate per-domain breakdown section."""
        html = """
            <div>
                <h3 class="section-title">Domain-Level Coverage Breakdown</h3>
                <p style="color: #6c757d; margin-bottom: 20px;">Per-domain event coverage details.</p>
"""
        
        for domain, stats in coverage.get('domain_results', {}).items():
            active_events = stats.get('active_events', [])
            if not active_events:
                continue
            
            unit_short, unit_long = self.rg._get_domain_unit_name(domain)
            domain_safe = domain.replace('-', '_').replace(' ', '_')
            domain_color = DOMAIN_COLORS.get(domain, '#333')
            
            events_json = json.dumps([
                {
                    'event': evt.get('event', 'Unknown'),
                    'per_core_counts': evt.get('per_core_counts', []),
                    'total': evt.get('total_activity', 0)
                } for evt in active_events
            ])
            
            html += f"""
                <div class="coverage-card domain-section" data-domain="{domain.lower()}" style="margin-bottom: 30px;">
                    <h4 style="color: {domain_color};">{domain.upper()} Domain</h4>
                    <p><strong>Total Active Events:</strong> {len(active_events)}</p>
                    
                    <div style="margin: 20px 0;">
                        <label for="eventSelect_{domain_safe}" style="font-weight: bold; margin-right: 10px;">Select Event:</label>
                        <select id="eventSelect_{domain_safe}" onchange="updateEventChart_{domain_safe}()" style="padding: 8px; border: 1px solid #ddd; border-radius: 4px; min-width: 300px;">
                            <option value="">-- Select an Event --</option>
"""
            
            for i, event in enumerate(active_events):
                html += f'                            <option value="{i}">{event.get("event", "Unknown")}</option>\n'
            
            html += f"""
                        </select>
                    </div>
                    
                    <div id="chartContainer_{domain_safe}" style="display: none; margin: 20px 0;">
                        <canvas id="eventChart_{domain_safe}" style="max-height: 300px;"></canvas>
                    </div>
                    
                    <script>
                    (function() {{
                        const eventsData_{domain_safe} = {events_json};
                        let chart_{domain_safe} = null;
                        
                        window.updateEventChart_{domain_safe} = function() {{
                            const selectEl = document.getElementById('eventSelect_{domain_safe}');
                            const chartContainer = document.getElementById('chartContainer_{domain_safe}');
                            const selectedIndex = selectEl.value;
                            
                            if (selectedIndex === '') {{ chartContainer.style.display = 'none'; return; }}
                            
                            chartContainer.style.display = 'block';
                            const eventData = eventsData_{domain_safe}[selectedIndex];
                            const ctx = document.getElementById('eventChart_{domain_safe}').getContext('2d');
                            
                            if (chart_{domain_safe}) chart_{domain_safe}.destroy();
                            
                            chart_{domain_safe} = new Chart(ctx, {{
                                type: 'bar',
                                data: {{
                                    labels: eventData.per_core_counts.map((_, i) => '{unit_long} ' + i),
                                    datasets: [{{ label: 'Count', data: eventData.per_core_counts, backgroundColor: '{domain_color}' }}]
                                }},
                                options: {{
                                    responsive: true,
                                    plugins: {{ title: {{ display: true, text: eventData.event + ' - Per-{unit_long} Distribution' }}, legend: {{ display: false }} }},
                                    scales: {{ y: {{ beginAtZero: true }} }}
                                }}
                            }});
                        }};
                    }})();
                    </script>
                    
                    <div style="max-height: 500px; overflow-y: auto; border: 1px solid #ddd; border-radius: 4px; margin-top: 20px;">
                    <table class="event-table" style="margin: 0;">
                        <thead style="position: sticky; top: 0; background: white;">
                            <tr><th>Event Name</th><th>Total</th><th>Avg/{unit_long}</th><th>Max/{unit_long}</th><th>Active</th></tr>
                        </thead>
                        <tbody>
"""
            
            for event in active_events:
                html += f"""
                            <tr>
                                <td class="counter-detail">{event.get('event', 'Unknown')}</td>
                                <td>{event.get('total_activity', 0):,}</td>
                                <td>{event.get('avg_core_count', 0):.1f}</td>
                                <td>{event.get('max_core_count', 0):,}</td>
                                <td>{event.get('active_cores', 0)}</td>
                            </tr>
"""
            
            html += """
                        </tbody>
                    </table>
                    </div>
                </div>
"""
        
        html += """
            </div>
"""
        return html

    def _generate_realtime_insights(self, coverage_results: Dict, gaps: Dict, ml_analysis: Dict) -> str:
        """Generate real-time coverage insights from current run data."""
        html = """
        <div class="chart-container" style="margin-top: 25px;">
            <h3 style="color: #0071C5;">Real-Time Coverage Insights</h3>
            <p style="color: #6c757d; margin-bottom: 20px;">
                Analysis from current test run
            </p>
        """
        
        # Calculate insights from current run
        domain_results = coverage_results.get('domain_results', {})
        total_active = coverage_results.get('active_events', 0)
        total_inactive = coverage_results.get('inactive_events', 0)
        
        # Find best and worst domains
        domain_stats = []
        for domain, data in domain_results.items():
            activity_rate = data.get('activity_rate', 0)
            domain_stats.append({
                'domain': domain,
                'rate': activity_rate,
                'active': len(data.get('active_events', [])),
                'inactive': len(data.get('inactive_events', []))
            })
        
        domain_stats.sort(key=lambda x: x['rate'], reverse=True)
        best_domains = domain_stats[:3] if len(domain_stats) >= 3 else domain_stats
        worst_domains = domain_stats[-3:] if len(domain_stats) >= 3 else []
        worst_domains.reverse()
        
        # Get critical gaps
        non_toggling = gaps.get('non_toggling_events', [])
        critical_gaps = [e for e in non_toggling if e.get('category') == 'CRITICAL'][:5]
        
        html += """
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(350px, 1fr)); gap: 20px; margin-top: 15px;">
        """
        
        # Best Performing Domains
        if best_domains:
            html += """
                <div style="background: #d4edda; border: 1px solid #c3e6cb; border-radius: 8px; padding: 15px;">
                    <h4 style="color: #155724; margin-top: 0;">Top Performing Domains</h4>
                    <ul style="margin: 5px 0; padding-left: 20px; color: #155724;">
            """
            for d in best_domains:
                html += f"""
                        <li><strong>{d['domain'].upper()}:</strong> {d['rate']:.1f}% ({d['active']}/{d['active']+d['inactive']} events)</li>
                """
            html += """
                    </ul>
                </div>
            """
        
        # Worst Performing Domains
        if worst_domains:
            html += """
                <div style="background: #f8d7da; border: 1px solid #f5c6cb; border-radius: 8px; padding: 15px;">
                    <h4 style="color: #721c24; margin-top: 0;">Needs Attention</h4>
                    <ul style="margin: 5px 0; padding-left: 20px; color: #721c24;">
            """
            for d in worst_domains:
                html += f"""
                        <li><strong>{d['domain'].upper()}:</strong> {d['rate']:.1f}% ({d['active']}/{d['active']+d['inactive']} events)</li>
                """
            html += """
                    </ul>
                </div>
            """
        
        html += """
            </div>
        """
        
        # Critical Gaps Section
        if critical_gaps:
            html += f"""
            <div style="background: #fff3cd; border: 1px solid #ffc107; border-radius: 8px; padding: 15px; margin-top: 15px;">
                <h4 style="color: #856404; margin-top: 0;"> Top {len(critical_gaps)} Critical Coverage Gaps</h4>
                <table style="width: 100%; border-collapse: collapse; font-size: 13px;">
                    <thead>
                        <tr style="background: #ffe4a1;">
                            <th style="text-align: left; padding: 8px; border: 1px solid #ffc107;">Event Name</th>
                            <th style="text-align: center; padding: 8px; border: 1px solid #ffc107;">Domain</th>
                            <th style="text-align: center; padding: 8px; border: 1px solid #ffc107;">Reason</th>
                        </tr>
                    </thead>
                    <tbody>
            """
            
            for gap in critical_gaps:
                event_name = gap.get('event', 'Unknown')
                domain = gap.get('domain', 'Unknown')
                reason = gap.get('reason', 'No activity detected')
                
                html += f"""
                        <tr>
                            <td style="padding: 6px 8px; border: 1px solid #ffc107; font-family: monospace; font-size: 12px;">
                                {event_name}
                            </td>
                            <td style="text-align: center; padding: 6px 8px; border: 1px solid #ffc107;">
                                {domain.upper()}
                            </td>
                            <td style="text-align: center; padding: 6px 8px; border: 1px solid #ffc107; color: #721c24;">
                                {reason}
                            </td>
                        </tr>
                """
            
            html += """
                    </tbody>
                </table>
            </div>
            """
        
        # Workload Recommendations
        html += """
            <div style="background: #d1ecf1; border: 1px solid #bee5eb; border-radius: 8px; padding: 15px; margin-top: 15px;">
                <h4 style="color: #0c5460; margin-top: 0;">Workload Recommendations</h4>
                <p style="color: #0c5460; margin: 10px 0;">
                    To improve coverage, consider running these workload types:
                </p>
                <ul style="margin: 5px 0; padding-left: 20px; color: #0c5460;">
        """
        
        # Generate workload recommendations based on gaps
        if any('power' in d['domain'].lower() for d in worst_domains):
            html += """
                    <li><strong>Power State Workloads:</strong> Idle/sleep tests, C-state transitions</li>
            """
        if any('ncu' in d['domain'].lower() or 'cbo' in d['domain'].lower() for d in worst_domains):
            html += """
                    <li><strong>Uncore Intensive:</strong> Memory bandwidth tests, cache-heavy workloads</li>
            """
        if any('imc' in d['domain'].lower() for d in worst_domains):
            html += """
                    <li><strong>Memory Stress:</strong> STREAM benchmark, memory latency tests</li>
            """
        
        html += """
                    <li><strong>Multi-Component:</strong> SuperCollider, stress-ng (all components)</li>
                    <li><strong>Duration Variance:</strong> Short burst (30s), Medium (5m), Long (15m+)</li>
                </ul>
            </div>
        """
        
        html += """
        </div>
        """
        
        return html