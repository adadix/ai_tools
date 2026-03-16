"""
Platform & Product Insights Tab Generator Module

Generates the Platform & Product Insights tab comparing coverage across:
- Different platforms (Windows vs Linux)
- Different products (Arrow Lake, Wildcat Lake, etc.)
- Matrix view combining both dimensions
"""


class PlatformProductInsightsTabGenerator:
    """Generates the Platform & Product Insights tab for cross-platform/product comparison."""
    
    def __init__(self, report_generator):
        """
        Initialize with reference to parent report generator.
        
        Args:
            report_generator: Parent ReportGenerator instance for accessing shared methods/data
        """
        self.rg = report_generator
    
    def _load_platform_comparison_data(self, analysis_results):
        """Load platform comparison data from PlatformGapComparison."""
        try:
            from src.platform_gap_comparison import PlatformGapComparison
            platform_cmp = PlatformGapComparison(self.rg.config)
            
            # Get current OS from analysis results
            current_os = analysis_results.get('metadata', {}).get('os_type', 'unknown').lower()
            if 'win' in current_os:
                current_os = 'windows'
            elif 'linux' in current_os:
                current_os = 'linux'
            else:
                current_os = 'windows'  # default
            
            # Get gap results for comparison
            gap_results = {'gaps': analysis_results.get('gaps', {})}
            
            # Get product_id for filtering
            product_id = self.rg._get_product_id(analysis_results)
            
            return platform_cmp.compare_platforms(gap_results, current_os, product_id)
        except Exception as e:
            return {'status': 'error', 'message': str(e)}
    
    def _load_product_comparison_data(self):
        """Load product comparison data from MLAnalysisReporter."""
        try:
            from src.ml_client import MLClient
            from src.ml_analysis_reporter import MLAnalysisReporter
            ml_client = MLClient(self.rg.config)
            
            if ml_client.local_models_available:
                reporter = MLAnalysisReporter(ml_client)
                product_comparison = reporter.generate_cross_product_comparison()
                
                if not isinstance(product_comparison, dict):
                    return {'status': 'error', 'message': 'Invalid response from product comparison'}
                elif product_comparison.get('status') in ['error', 'no_data', 'insufficient_data', 'no_ml']:
                    return product_comparison
                elif product_comparison.get('status') == 'success':
                    product_comparison['status'] = 'complete'
                    return product_comparison
                elif 'products' not in product_comparison and product_comparison.get('status') not in ['complete', 'success']:
                    return {'status': 'no_data', 'message': 'No product data available yet'}
                return product_comparison
            else:
                return {'status': 'no_ml', 'message': 'ML models not yet trained - scikit-learn may be missing'}
        except ImportError as e:
            return {'status': 'error', 'message': f'ML modules not available: {str(e)}'}
        except Exception as e:
            return {'status': 'error', 'message': f'{type(e).__name__}: {str(e)}'}
    
    def _extract_current_platform_data(self, analysis_results):
        """Extract platform data from the current run."""
        # Get current OS - check multiple locations
        os_info = analysis_results.get('metadata', {}).get('os_info', {})
        if not os_info:
            os_info = analysis_results.get('os_info', {})
        
        current_os = os_info.get('os_type', 'unknown').lower() if os_info else 'unknown'
        if not current_os or current_os == 'unknown':
            current_os = analysis_results.get('metadata', {}).get('os_type', 'unknown').lower()
        
        if 'win' in current_os:
            current_os = 'Windows'
        elif 'linux' in current_os:
            current_os = 'Linux'
        else:
            current_os = 'Unknown'
        
        # Coverage data can be under 'coverage_results' (saved JSON) or 'coverage' (live run)
        coverage_results = analysis_results.get('coverage_results', {})
        if not coverage_results:
            coverage_results = analysis_results.get('coverage', {})
        
        # Extract overall stats from coverage_results
        total_coverage = coverage_results.get('activity_coverage', 0)
        total_events = coverage_results.get('total_events_tested', 0)
        active_events = coverage_results.get('active_events', 0)
        
        # If still no data, try to calculate from domain_results
        domain_results = coverage_results.get('domain_results', {})
        domain_breakdown = {}
        
        # If we didn't get totals from top level, calculate from domains
        if total_events == 0 and domain_results:
            for domain_name, domain_data in domain_results.items():
                if isinstance(domain_data, dict):
                    d_active = len(domain_data.get('active_events', []))
                    d_inactive = len(domain_data.get('inactive_events', []))
                    d_total = d_active + d_inactive
                    d_cov = (d_active / d_total * 100) if d_total > 0 else 0
                    
                    domain_breakdown[domain_name] = {
                        'coverage_pct': d_cov,
                        'active': d_active,
                        'total': d_total
                    }
                    total_events += d_total
                    active_events += d_active
            
            if total_events > 0:
                total_coverage = (active_events / total_events) * 100
        else:
            # Use domain_results for breakdown - check multiple key names
            for domain_name, domain_data in domain_results.items():
                if isinstance(domain_data, dict):
                    # Try different key names for coverage percentage
                    domain_cov = (
                        domain_data.get('coverage_pct') or 
                        domain_data.get('activity_rate') or  # Historical data format
                        domain_data.get('coverage_percentage') or
                        0
                    )
                    # Convert to percentage if it's a ratio (0-1)
                    if 0 < domain_cov <= 1:
                        domain_cov = domain_cov * 100
                    
                    domain_active = domain_data.get('active', len(domain_data.get('active_events', [])))
                    domain_inactive = len(domain_data.get('inactive_events', []))
                    domain_total = domain_data.get('total', domain_data.get('total_tested', domain_active + domain_inactive))
                    
                    domain_breakdown[domain_name] = {
                        'coverage_pct': domain_cov,
                        'active': domain_active,
                        'total': domain_total
                    }
        
        # Get product name from hardware_config
        hw_config = analysis_results.get('hardware_config', {})
        if not hw_config:
            hw_config = analysis_results.get('metadata', {}).get('hardware_config', {})
        
        product_name = (
            hw_config.get('product_name') or
            hw_config.get('product_id') or
            analysis_results.get('product_id') or
            'Unknown Product'
        )
        
        return {
            'os': current_os,
            'coverage': total_coverage,
            'events': total_events,
            'active_events': active_events,
            'domains': domain_breakdown,
            'product': product_name
        }
    
    def generate(self, analysis_results):
        """
        Generate Platform & Product Insights tab - Cross-platform and cross-product analysis.
        
        Args:
            analysis_results: Dictionary containing analysis data
            
        Returns:
            str: HTML content for the tab
        """
        # Load data dynamically like the original method
        platform_comparison = self._load_platform_comparison_data(analysis_results)
        product_comparison = self._load_product_comparison_data()
        current_platform_data = self._extract_current_platform_data(analysis_results)
        
        # Check if we have meaningful data - must have actual data, not just a success status
        # PlatformGapComparison returns 'comparison' not 'platforms'
        has_platform_data = (
            platform_comparison.get('status') not in ['error', 'no_data', 'insufficient_data'] and 
            (bool(platform_comparison.get('comparison')) or platform_comparison.get('status') in ['complete', 'single_platform', 'insufficient_data'])
        )
        has_product_data = (
            product_comparison.get('status') in ['complete', 'success'] and 
            bool(product_comparison.get('products'))
        )
        # Current data is valid if we have coverage > 0 or any events or any domain data
        has_current_data = (
            current_platform_data.get('coverage', 0) > 0 or 
            current_platform_data.get('events', 0) > 0 or 
            bool(current_platform_data.get('domains'))
        )
        
        html = """
        <div id="platform-product-insights" class="tab-content">
            <h2 class="section-title">PLATFORM & PRODUCT INSIGHTS</h2>
            
            <!-- Interpretation Guide -->
            <div style="background: linear-gradient(135deg, #e0f7fa 0%, #b2ebf2 100%); border-left: 5px solid #00838f; padding: 20px; margin-bottom: 25px; border-radius: 8px;">
                <h3 style="margin: 0 0 10px 0; color: #006064;">How to Interpret This Tab</h3>
                <p style="margin: 5px 0; color: #006064; line-height: 1.5; font-size: 0.95em;">
                    <strong>Current Run:</strong> Platform-specific coverage data from this collection (Windows/Linux).<br>
                    <strong>Historical Platform Comparison:</strong> Windows vs Linux coverage differences across all runs.<br>
                    <strong>Product Comparison:</strong> Coverage differences between silicon products (e.g., Arrowlake-S).<br>
                    <strong>Matrix View:</strong> Product × Platform grid showing coverage and gap counts.<br>
                    <strong>Key Insight:</strong> Identify platform-specific gaps and architecture blind spots to target.
                </p>
            </div>
"""
        
        # Show current run data even without historical data
        if has_current_data:
            html += self._generate_current_run_section(current_platform_data, analysis_results)
        
        if not has_platform_data and not has_product_data:
            # No historical data - show message and close tab
            if not has_current_data:
                html += """
            <div style="background: #fff3cd; border-left: 6px solid #ffc107; padding: 25px; border-radius: 10px;">
                <h3 style="color: #856404; margin-top: 0;">Historical Data Required</h3>
                <p style="color: #856404;">
                    Platform and product comparison requires historical data from multiple runs. Continue running coverage collections
                    to populate this analysis section. Data is automatically aggregated from 
                    <code>C:\\silicon_coverage_analyzer_data</code>.
                </p>
            </div>
"""
            html += """
        </div>
"""
            return html
        
        # Sub-tab navigation (only if we have historical data)
        if has_platform_data or has_product_data:
            html += """
            <div style="margin-bottom: 25px;">
                <div style="display: flex; gap: 10px; border-bottom: 2px solid #e0e0e0; padding-bottom: 10px;">
                    <button onclick="showInsightSubTab('platform')" id="btn-platform" class="insight-tab-btn active" 
                            style="padding: 10px 20px; border: none; background: #0071C5; color: white; border-radius: 5px 5px 0 0; cursor: pointer; font-weight: bold;">
                        Platform Comparison
                    </button>
                    <button onclick="showInsightSubTab('product')" id="btn-product" class="insight-tab-btn"
                            style="padding: 10px 20px; border: none; background: #e0e0e0; color: #333; border-radius: 5px 5px 0 0; cursor: pointer;">
                        Product Comparison
                    </button>
                    <button onclick="showInsightSubTab('matrix')" id="btn-matrix" class="insight-tab-btn"
                            style="padding: 10px 20px; border: none; background: #e0e0e0; color: #333; border-radius: 5px 5px 0 0; cursor: pointer;">
                        Matrix View
                    </button>
                </div>
            </div>
            
            <script>
            function showInsightSubTab(tabName) {
                document.querySelectorAll('.insight-subtab').forEach(el => el.style.display = 'none');
                document.getElementById('subtab-' + tabName).style.display = 'block';
                document.querySelectorAll('.insight-tab-btn').forEach(btn => {
                    btn.style.background = '#e0e0e0';
                    btn.style.color = '#333';
                });
                document.getElementById('btn-' + tabName).style.background = '#0071C5';
                document.getElementById('btn-' + tabName).style.color = 'white';
            }
            </script>
"""
            
            # Platform Comparison Sub-tab
            html += self._generate_platform_comparison_section(platform_comparison)
            
            # Product Comparison Sub-tab
            html += self._generate_product_comparison_section(product_comparison)
            
            # Matrix View Sub-tab
            html += self._generate_matrix_view_section(platform_comparison, product_comparison)
        
        html += """
        </div>
        """
        return html
    
    def _generate_current_run_section(self, current_data, analysis_results):
        """Generate section showing current run's platform data."""
        os_name = current_data.get('os', 'Unknown')
        coverage = current_data.get('coverage', 0)
        events = current_data.get('events', 0)
        product = current_data.get('product', 'Unknown')
        domains = current_data.get('domains', {})
        
        # OS-specific styling
        if os_name == 'Windows':
            os_color = '#0071C5'
            os_gradient = 'linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%)'
            os_icon = '🪟'
        else:
            os_color = '#7b1fa2'
            os_gradient = 'linear-gradient(135deg, #f3e5f5 0%, #e1bee7 100%)'
            os_icon = '🐧'
        
        html = f"""
            <div style="margin-bottom: 30px;">
                <h3 style="color: {os_color}; margin-bottom: 20px;">CURRENT RUN - {os_name.upper()} PLATFORM</h3>
                
                <div style="background: {os_gradient}; padding: 25px; border-radius: 12px; border-left: 6px solid {os_color}; box-shadow: 0 4px 15px rgba(0,0,0,0.1);">
                    <div style="display: flex; align-items: center; gap: 15px; margin-bottom: 20px;">
                        <span style="font-size: 2.5em;">{os_icon}</span>
                        <div>
                            <h4 style="margin: 0; color: {os_color}; font-size: 1.4em;">{os_name.upper()}</h4>
                            <div style="color: #666; font-size: 0.9em;">Product: {product}</div>
                        </div>
                    </div>
                    
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 20px;">
                        <div style="background: white; padding: 20px; border-radius: 8px; text-align: center;">
                            <div style="font-size: 2.5em; font-weight: bold; color: {os_color};">{coverage:.1f}%</div>
                            <div style="color: #666; font-size: 0.9em;">Total Coverage</div>
                        </div>
                        <div style="background: white; padding: 20px; border-radius: 8px; text-align: center;">
                            <div style="font-size: 2.5em; font-weight: bold; color: {os_color};">{events:,}</div>
                            <div style="color: #666; font-size: 0.9em;">Total Events</div>
                        </div>
                        <div style="background: white; padding: 20px; border-radius: 8px; text-align: center;">
                            <div style="font-size: 2.5em; font-weight: bold; color: {os_color};">{len(domains)}</div>
                            <div style="color: #666; font-size: 0.9em;">Active Domains</div>
                        </div>
                    </div>
"""
        
        # Domain breakdown if available
        if domains:
            html += """
                    <div style="background: white; padding: 15px; border-radius: 8px;">
                        <h5 style="margin: 0 0 15px 0; color: #333;">Domain Coverage Breakdown:</h5>
                        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px;">
"""
            for domain_name, domain_info in sorted(domains.items()):
                domain_cov = domain_info.get('coverage_pct', 0) if isinstance(domain_info, dict) else 0
                if domain_cov >= 80:
                    bar_color = '#28a745'
                elif domain_cov >= 50:
                    bar_color = '#ffc107'
                else:
                    bar_color = '#dc3545'
                
                html += f"""
                            <div style="background: #f8f9fa; padding: 10px; border-radius: 6px;">
                                <div style="display: flex; justify-content: space-between; margin-bottom: 5px;">
                                    <span style="font-weight: 600; font-size: 0.85em; color: #333;">{domain_name.upper()}</span>
                                    <span style="font-weight: bold; color: {bar_color};">{domain_cov:.1f}%</span>
                                </div>
                                <div style="background: #e0e0e0; height: 8px; border-radius: 4px; overflow: hidden;">
                                    <div style="background: {bar_color}; height: 100%; width: {domain_cov}%;"></div>
                                </div>
                            </div>
"""
            html += """
                        </div>
                    </div>
"""
        
        html += """
                </div>
                
                <div style="background: #d1ecf1; border-left: 4px solid #17a2b8; padding: 15px; border-radius: 8px; margin-top: 15px;">
                    <p style="color: #0c5460; margin: 0; font-size: 0.9em;">
                        <strong>💡 Tip:</strong> Run coverage analysis on both Windows and Linux to enable cross-platform comparison. 
                        Historical data is automatically saved to <code>C:\\silicon_coverage_analyzer_data</code> for trend analysis.
                    </p>
                </div>
            </div>
"""
        return html
    
    def _generate_platform_comparison_section(self, platform_comparison):
        """Generate platform comparison sub-tab content using PlatformGapComparison data structure."""
        status = platform_comparison.get('status', 'error')
        
        html = """
            <div id="subtab-platform" class="insight-subtab" style="display: block;">
                <h3 style="color: #0071C5; margin-bottom: 20px;">HISTORICAL PLATFORM COMPARISON (Windows vs Linux)</h3>
"""
        
        # Handle insufficient data or single platform case
        if status in ['insufficient_data', 'single_platform']:
            current_platform = platform_comparison.get('current_platform', 'unknown').title()
            html += f"""
                <div style="background: linear-gradient(135deg, #fff3cd 0%, #ffe8a1 100%); border-left: 6px solid #ffc107; padding: 30px; border-radius: 10px;">
                    <h3 style="color: #856404; margin-top: 0; display: flex; align-items: center; gap: 12px;">
                        ⚡ Need More Platform Data
                    </h3>
                    <p style="color: #856404; font-size: 1.05em; margin-bottom: 20px;">
                        Cross-platform comparison requires data from both Windows and Linux systems.
                        Currently only <strong>{current_platform}</strong> data is available.
                    </p>
                    <div style="background: white; padding: 20px; border-radius: 8px; margin-top: 15px;">
                        <strong style="color: #333;">How to Enable:</strong>
                        <ol style="margin: 15px 0; padding-left: 25px; color: #555; line-height: 1.8;">
                            <li>Run silicon coverage analysis on a <strong>Windows</strong> system</li>
                            <li>Run silicon coverage analysis on a <strong>Linux</strong> system (same hardware)</li>
                            <li>Return to this tab to see platform-specific insights</li>
                        </ol>
                    </div>
                </div>
            </div>
"""
            return html
        
        # Handle complete comparison
        if status == 'complete':
            summary = platform_comparison.get('summary', {})
            current_platform = platform_comparison.get('current_platform', 'unknown').title()
            other_platform = platform_comparison.get('other_platform', 'unknown').title()
            platform_specific = platform_comparison.get('platform_specific', {})
            recommendations = platform_comparison.get('recommendations', [])
            
            # Extract dataset counts for statistical validity warning
            comp_data = platform_comparison.get('comparison', {})
            dataset_counts = comp_data.get('dataset_counts', {})
            current_dataset_count = dataset_counts.get(current_platform.lower(), 0)
            other_dataset_count = dataset_counts.get(other_platform.lower(), 0)
            
            # Calculate imbalance ratio
            if current_dataset_count > 0 and other_dataset_count > 0:
                imbalance_ratio = max(current_dataset_count, other_dataset_count) / min(current_dataset_count, other_dataset_count)
            else:
                imbalance_ratio = 0
            
            # Data Flow Visualization
            total_current_gaps = summary.get('total_gaps_current', 0)
            total_other_gaps = summary.get('total_gaps_other', 0)
            common_gaps = summary.get('common_gaps', 0)
            
            html += f"""
                <div style="background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%); border-radius: 12px; padding: 25px; margin-bottom: 30px; box-shadow: 0 4px 12px rgba(40,167,69,0.2);">
                    <h4 style="color: #1b5e20; margin-top: 0; margin-bottom: 20px; display: flex; align-items: center; gap: 10px;">
                        🔬 Platform Data Analysis - Live View
                    </h4>
"""
            
            # Add statistical validity warning if imbalance detected
            if imbalance_ratio >= 3.0:
                under_tested = current_platform if current_dataset_count < other_dataset_count else other_platform
                over_tested = current_platform if current_dataset_count > other_dataset_count else other_platform
                under_count = dataset_counts.get(under_tested.lower(), 0)
                over_count = dataset_counts.get(over_tested.lower(), 0)
                
                html += f"""
                    <div style="background: linear-gradient(135deg, #fff3cd 0%, #ffe8a1 100%); border: 3px solid #ffc107; border-radius: 10px; padding: 20px; margin-bottom: 20px;">
                        <div style="display: flex; align-items: start; gap: 15px;">
                            <div style="font-size: 2em;">⚠️</div>
                            <div style="flex: 1;">
                                <h4 style="margin: 0 0 10px 0; color: #856404; font-size: 1.2em;">Statistical Warning: Unbalanced Sample Sizes</h4>
                                <p style="margin: 0 0 10px 0; color: #856404; font-size: 0.95em;">
                                    <strong>{over_tested}</strong> has been tested <strong>{imbalance_ratio:.1f}x more</strong> than {under_tested} 
                                    ({over_count} datasets vs {under_count} datasets).
                                </p>
                            </div>
                        </div>
                    </div>
"""
            
            html += f"""
                    <div style="background: white; padding: 20px; border-radius: 8px; border-left: 4px solid #28a745; margin-bottom: 15px;">
                        <div style="font-family: 'Courier New', monospace; font-size: 0.9em; color: #2e7d32; line-height: 2;">
                            <div><strong>1. OS Detection:</strong> metadata['os_type'] → <span style="color: #d84315;">"{current_platform.lower()}"</span> vs <span style="color: #d84315;">"{other_platform.lower()}"</span></div>
                            <div><strong>2. Gap Segregation:</strong> gaps_by_os[os_type][domain] → {total_current_gaps} ({current_platform}) vs {total_other_gaps} ({other_platform})</div>
                            <div><strong>3. Set Operations:</strong> set.intersection(gaps_windows, gaps_linux) → <strong>{common_gaps}</strong> common gaps</div>
                            <div><strong>4. Unique Detection:</strong> gaps_{current_platform.lower()} - common → <strong>{summary.get('current_only_gaps', 0)}</strong> {current_platform}-only gaps</div>
                        </div>
                    </div>
                    <div style="text-align: center; padding: 15px; background: rgba(255,255,255,0.7); border-radius: 8px;">
                        <div style="font-size: 0.9em; color: #1b5e20; font-weight: 600;">
                            <strong>2</strong> Platforms Analyzed | 
                            <strong>{total_current_gaps + total_other_gaps}</strong> Total Gaps | 
                            <strong>{common_gaps}</strong> Common Gaps | 
                            <strong>{summary.get('current_only_gaps', 0) + summary.get('other_only_gaps', 0)}</strong> Platform-Specific
                        </div>
                    </div>
                </div>
                
                <!-- Platform Overview Cards -->
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 25px; margin-bottom: 30px;">
                    <!-- Current Platform Card -->
                    <div style="background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%); border: 3px solid #0071C5; border-radius: 12px; padding: 30px;">
                        <div style="text-align: center;">
                            <div style="font-size: 1.5em; margin-bottom: 10px;">🪟</div>
                            <h3 style="color: #0071C5; margin: 0 0 5px 0; font-size: 1.8em;">{current_platform}</h3>
                            <div style="font-size: 0.85em; color: #0071C5; margin-bottom: 15px; font-weight: 600;">
                                {current_dataset_count} Dataset{"s" if current_dataset_count != 1 else ""} Tested
                            </div>
                            <div style="background: white; border-radius: 8px; padding: 20px; margin-bottom: 15px;">
                                <div style="font-size: 0.85em; color: #666; margin-bottom: 5px;">TOTAL GAPS</div>
                                <div style="font-size: 3em; font-weight: bold; color: #0071C5;">{summary.get('total_gaps_current', 0)}</div>
                            </div>
                            <div style="background: white; border-radius: 8px; padding: 15px;">
                                <div style="font-size: 0.85em; color: #666; margin-bottom: 5px;">PLATFORM-SPECIFIC GAPS</div>
                                <div style="font-size: 2em; font-weight: bold; color: #dc3545;">{summary.get('current_only_gaps', 0)}</div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Other Platform Card -->
                    <div style="background: linear-gradient(135deg, #f3e5f5 0%, #e1bee7 100%); border: 3px solid #7b1fa2; border-radius: 12px; padding: 30px;">
                        <div style="text-align: center;">
                            <div style="font-size: 1.5em; margin-bottom: 10px;">🐧</div>
                            <h3 style="color: #7b1fa2; margin: 0 0 5px 0; font-size: 1.8em;">{other_platform}</h3>
                            <div style="font-size: 0.85em; color: #7b1fa2; margin-bottom: 15px; font-weight: 600;">
                                {other_dataset_count} Dataset{"s" if other_dataset_count != 1 else ""} Tested
                            </div>
                            <div style="background: white; border-radius: 8px; padding: 20px; margin-bottom: 15px;">
                                <div style="font-size: 0.85em; color: #666; margin-bottom: 5px;">TOTAL GAPS</div>
                                <div style="font-size: 3em; font-weight: bold; color: #7b1fa2;">{summary.get('total_gaps_other', 0)}</div>
                            </div>
                            <div style="background: white; border-radius: 8px; padding: 15px;">
                                <div style="font-size: 0.85em; color: #666; margin-bottom: 5px;">PLATFORM-SPECIFIC GAPS</div>
                                <div style="font-size: 2em; font-weight: bold; color: #dc3545;">{summary.get('other_only_gaps', 0)}</div>
                            </div>
                        </div>
                    </div>
                </div>
"""
            
            # Recommendations section
            if recommendations:
                html += """
                <div style="background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%); border-radius: 10px; padding: 20px; margin-bottom: 20px;">
                    <h4 style="color: #1b5e20; margin: 0 0 15px 0;">📋 Platform-Specific Recommendations</h4>
                    <ul style="margin: 0; padding-left: 20px; color: #2e7d32;">
"""
                for rec in recommendations[:5]:  # Top 5 recommendations
                    # Handle both dict and string recommendations
                    if isinstance(rec, dict):
                        title = rec.get('title', '')
                        description = rec.get('description', '')
                        impact = rec.get('impact', 'medium')
                        impact_color = '#dc3545' if impact == 'high' else '#ffc107' if impact == 'medium' else '#28a745'
                        rec_text = f"<strong style='color: {impact_color};'>{title}</strong>: {description}"
                    else:
                        rec_text = str(rec)
                    html += f"<li style='margin-bottom: 8px;'>{rec_text}</li>"
                html += """
                    </ul>
                </div>
"""
            
            # Detailed Gaps Section
            html += self._generate_detailed_gaps_section(platform_comparison, current_platform, other_platform)
            
            html += """
            </div>
"""
            return html
        
        # Default fallback for no data
        html += """
                <div style="background: #d1ecf1; border-left: 4px solid #17a2b8; padding: 20px; border-radius: 8px;">
                    <p style="color: #0c5460; margin: 0;">
                        No historical platform comparison data available yet. Run coverage analysis on both Windows and Linux to enable this comparison.
                    </p>
                </div>
            </div>
"""
        return html
    
    def _generate_detailed_gaps_section(self, platform_comparison, current_platform, other_platform):
        """Generate detailed gaps breakdown section."""
        html = ""
        
        comparison = platform_comparison.get('comparison', {})
        platform_specific = platform_comparison.get('platform_specific', {})
        
        # Get gap lists
        common_gaps = comparison.get('common_gaps', [])
        current_only_gaps = platform_specific.get('current_only', [])
        other_only_gaps = platform_specific.get('other_only', [])
        
        # Only show if we have gaps to display
        if not common_gaps and not current_only_gaps and not other_only_gaps:
            return html
        
        html += """
                <div style="margin-top: 30px;">
                    <h4 style="color: #333; margin-bottom: 20px; display: flex; align-items: center; gap: 10px;">
                        🔍 Detailed Gap Analysis
                        <span style="font-size: 0.7em; font-weight: normal; color: #666;">(Click to expand/collapse)</span>
                    </h4>
"""
        
        # Common Gaps Section (affects both platforms - highest priority)
        if common_gaps:
            # Group by domain
            gaps_by_domain = {}
            for gap in common_gaps:
                domain = gap.get('domain', 'unknown') if isinstance(gap, dict) else 'unknown'
                if domain not in gaps_by_domain:
                    gaps_by_domain[domain] = []
                gaps_by_domain[domain].append(gap)
            
            html += f"""
                    <details style="margin-bottom: 20px;" open>
                        <summary style="cursor: pointer; background: linear-gradient(135deg, #fff3cd 0%, #ffe8a1 100%); padding: 15px 20px; border-radius: 8px; border-left: 5px solid #ffc107; font-weight: 600; color: #856404; display: flex; align-items: center; gap: 10px;">
                            <span style="font-size: 1.2em;">⚠️</span>
                            Common Gaps (Both Platforms) - {len(common_gaps)} gaps
                            <span style="margin-left: auto; font-size: 0.85em; font-weight: normal;">Highest Priority - Fix these first!</span>
                        </summary>
                        <div style="background: #fffbf0; padding: 20px; border-radius: 0 0 8px 8px; border: 1px solid #ffc107; border-top: none;">
                            <p style="color: #856404; margin: 0 0 15px 0; font-size: 0.9em;">
                                These gaps appear on <strong>both Windows and Linux</strong>. Fixing them improves coverage across all platforms.
                            </p>
"""
            
            for domain, gaps in sorted(gaps_by_domain.items()):
                html += f"""
                            <div style="margin-bottom: 15px;">
                                <div style="background: #ffc107; color: #333; padding: 8px 15px; border-radius: 6px 6px 0 0; font-weight: 600; text-transform: uppercase; font-size: 0.85em;">
                                    {domain} ({len(gaps)} gaps)
                                </div>
                                <div style="background: white; border: 1px solid #ffc107; border-top: none; border-radius: 0 0 6px 6px; max-height: 200px; overflow-y: auto;">
                                    <table style="width: 100%; border-collapse: collapse; font-size: 0.85em;">
                                        <thead style="background: #f8f9fa; position: sticky; top: 0;">
                                            <tr>
                                                <th style="padding: 8px 12px; text-align: left; border-bottom: 1px solid #dee2e6;">Event Name</th>
                                                <th style="padding: 8px 12px; text-align: center; border-bottom: 1px solid #dee2e6; width: 100px;">Occurrences</th>
                                                <th style="padding: 8px 12px; text-align: left; border-bottom: 1px solid #dee2e6;">Category</th>
                                            </tr>
                                        </thead>
                                        <tbody>
"""
                for gap in gaps[:20]:  # Limit to 20 per domain
                    event = gap.get('event', 'Unknown') if isinstance(gap, dict) else str(gap)
                    occurrences = gap.get('occurrences', 1) if isinstance(gap, dict) else 1
                    category = gap.get('category', '-') if isinstance(gap, dict) else '-'
                    html += f"""
                                            <tr style="border-bottom: 1px solid #f0f0f0;">
                                                <td style="padding: 8px 12px; font-family: monospace; font-size: 0.9em; color: #d84315;">{event}</td>
                                                <td style="padding: 8px 12px; text-align: center;">{occurrences}</td>
                                                <td style="padding: 8px 12px; color: #666;">{category}</td>
                                            </tr>
"""
                if len(gaps) > 20:
                    html += f"""
                                            <tr style="background: #f8f9fa;">
                                                <td colspan="3" style="padding: 8px 12px; text-align: center; color: #666; font-style: italic;">
                                                    ... and {len(gaps) - 20} more gaps in {domain}
                                                </td>
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
                    </details>
"""
        
        # Current Platform (Windows) Only Gaps
        if current_only_gaps:
            gaps_by_domain = {}
            for gap in current_only_gaps:
                domain = gap.get('domain', 'unknown') if isinstance(gap, dict) else 'unknown'
                if domain not in gaps_by_domain:
                    gaps_by_domain[domain] = []
                gaps_by_domain[domain].append(gap)
            
            html += f"""
                    <details style="margin-bottom: 20px;">
                        <summary style="cursor: pointer; background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%); padding: 15px 20px; border-radius: 8px; border-left: 5px solid #0071C5; font-weight: 600; color: #0071C5; display: flex; align-items: center; gap: 10px;">
                            <span style="font-size: 1.2em;">🪟</span>
                            {current_platform}-Only Gaps - {len(current_only_gaps)} gaps
                            <span style="margin-left: auto; font-size: 0.85em; font-weight: normal;">Platform-specific issues</span>
                        </summary>
                        <div style="background: #f0f7ff; padding: 20px; border-radius: 0 0 8px 8px; border: 1px solid #0071C5; border-top: none;">
                            <p style="color: #0071C5; margin: 0 0 15px 0; font-size: 0.9em;">
                                These gaps appear <strong>only on {current_platform}</strong>. May indicate Windows driver/OS limitations.
                            </p>
"""
            
            for domain, gaps in sorted(gaps_by_domain.items()):
                html += f"""
                            <div style="margin-bottom: 15px;">
                                <div style="background: #0071C5; color: white; padding: 8px 15px; border-radius: 6px 6px 0 0; font-weight: 600; text-transform: uppercase; font-size: 0.85em;">
                                    {domain} ({len(gaps)} gaps)
                                </div>
                                <div style="background: white; border: 1px solid #0071C5; border-top: none; border-radius: 0 0 6px 6px; max-height: 200px; overflow-y: auto;">
                                    <table style="width: 100%; border-collapse: collapse; font-size: 0.85em;">
                                        <thead style="background: #f8f9fa; position: sticky; top: 0;">
                                            <tr>
                                                <th style="padding: 8px 12px; text-align: left; border-bottom: 1px solid #dee2e6;">Event Name</th>
                                                <th style="padding: 8px 12px; text-align: center; border-bottom: 1px solid #dee2e6; width: 100px;">Occurrences</th>
                                                <th style="padding: 8px 12px; text-align: left; border-bottom: 1px solid #dee2e6;">Reason</th>
                                            </tr>
                                        </thead>
                                        <tbody>
"""
                for gap in gaps[:20]:
                    event = gap.get('event', 'Unknown') if isinstance(gap, dict) else str(gap)
                    occurrences = gap.get('occurrences', 1) if isinstance(gap, dict) else 1
                    reason = gap.get('explanation', gap.get('reason', '-')) if isinstance(gap, dict) else '-'
                    html += f"""
                                            <tr style="border-bottom: 1px solid #f0f0f0;">
                                                <td style="padding: 8px 12px; font-family: monospace; font-size: 0.9em; color: #0071C5;">{event}</td>
                                                <td style="padding: 8px 12px; text-align: center;">{occurrences}</td>
                                                <td style="padding: 8px 12px; color: #666; font-size: 0.85em;">{reason}</td>
                                            </tr>
"""
                if len(gaps) > 20:
                    html += f"""
                                            <tr style="background: #f8f9fa;">
                                                <td colspan="3" style="padding: 8px 12px; text-align: center; color: #666; font-style: italic;">
                                                    ... and {len(gaps) - 20} more gaps in {domain}
                                                </td>
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
                    </details>
"""
        
        # Other Platform (Linux) Only Gaps
        if other_only_gaps:
            gaps_by_domain = {}
            for gap in other_only_gaps:
                domain = gap.get('domain', 'unknown') if isinstance(gap, dict) else 'unknown'
                if domain not in gaps_by_domain:
                    gaps_by_domain[domain] = []
                gaps_by_domain[domain].append(gap)
            
            html += f"""
                    <details style="margin-bottom: 20px;">
                        <summary style="cursor: pointer; background: linear-gradient(135deg, #f3e5f5 0%, #e1bee7 100%); padding: 15px 20px; border-radius: 8px; border-left: 5px solid #7b1fa2; font-weight: 600; color: #7b1fa2; display: flex; align-items: center; gap: 10px;">
                            <span style="font-size: 1.2em;">🐧</span>
                            {other_platform}-Only Gaps - {len(other_only_gaps)} gaps
                            <span style="margin-left: auto; font-size: 0.85em; font-weight: normal;">Platform-specific issues</span>
                        </summary>
                        <div style="background: #faf5fc; padding: 20px; border-radius: 0 0 8px 8px; border: 1px solid #7b1fa2; border-top: none;">
                            <p style="color: #7b1fa2; margin: 0 0 15px 0; font-size: 0.9em;">
                                These gaps appear <strong>only on {other_platform}</strong>. May indicate Linux kernel/driver limitations or different event naming.
                            </p>
                            
                            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 15px;">
"""
            
            # Sort domains by gap count (most gaps first)
            sorted_domains = sorted(gaps_by_domain.items(), key=lambda x: len(x[1]), reverse=True)
            
            for domain, gaps in sorted_domains:
                html += f"""
                                <div>
                                    <div style="background: #7b1fa2; color: white; padding: 8px 15px; border-radius: 6px 6px 0 0; font-weight: 600; text-transform: uppercase; font-size: 0.85em; display: flex; justify-content: space-between;">
                                        <span>{domain}</span>
                                        <span>{len(gaps)} gaps</span>
                                    </div>
                                    <div style="background: white; border: 1px solid #7b1fa2; border-top: none; border-radius: 0 0 6px 6px; max-height: 250px; overflow-y: auto;">
                                        <table style="width: 100%; border-collapse: collapse; font-size: 0.8em;">
                                            <thead style="background: #f8f9fa; position: sticky; top: 0;">
                                                <tr>
                                                    <th style="padding: 6px 10px; text-align: left; border-bottom: 1px solid #dee2e6;">Event</th>
                                                    <th style="padding: 6px 10px; text-align: center; border-bottom: 1px solid #dee2e6; width: 50px;">#</th>
                                                </tr>
                                            </thead>
                                            <tbody>
"""
                for gap in gaps[:15]:  # Show top 15 per domain
                    event = gap.get('event', 'Unknown') if isinstance(gap, dict) else str(gap)
                    occurrences = gap.get('occurrences', 1) if isinstance(gap, dict) else 1
                    # Truncate long event names
                    event_display = event if len(event) <= 45 else event[:42] + '...'
                    html += f"""
                                                <tr style="border-bottom: 1px solid #f0f0f0;" title="{event}">
                                                    <td style="padding: 6px 10px; font-family: monospace; font-size: 0.85em; color: #7b1fa2;">{event_display}</td>
                                                    <td style="padding: 6px 10px; text-align: center; color: #666;">{occurrences}</td>
                                                </tr>
"""
                if len(gaps) > 15:
                    html += f"""
                                                <tr style="background: #f8f9fa;">
                                                    <td colspan="2" style="padding: 6px 10px; text-align: center; color: #666; font-style: italic; font-size: 0.8em;">
                                                        +{len(gaps) - 15} more
                                                    </td>
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
                        </div>
                    </details>
"""
        
        html += """
                </div>
"""
        return html
    
    def _generate_product_comparison_section(self, product_comparison):
        """Generate product comparison sub-tab content matching the original implementation."""
        status = product_comparison.get('status', 'no_data')
        products = product_comparison.get('products', {})
        
        html = """
            <div id="subtab-product" class="insight-subtab" style="display: none;">
                <h3 style="color: #7b1fa2; margin-bottom: 20px;">PRODUCT COMPARISON</h3>
"""
        
        # Handle no ML models available or insufficient data
        if status in ['no_ml', 'no_data', 'insufficient_data'] or not products:
            html += """
                <div style="background: linear-gradient(135deg, #fff3cd 0%, #ffe8a1 100%); border-left: 6px solid #ffc107; padding: 30px; border-radius: 10px;">
                    <h3 style="color: #856404; margin-top: 0; display: flex; align-items: center; gap: 12px;">
                        <span style="font-size: 1.8em;">📊</span>
                        Need More Product Data
                    </h3>
                    <p style="color: #856404; font-size: 1.05em; margin-bottom: 20px;">
                        Product comparison requires ML models trained on data from at least 2 different Intel products.
                    </p>
                    <div style="background: white; padding: 20px; border-radius: 8px; margin-top: 15px;">
                        <strong style="color: #333;">How to Enable:</strong>
                        <ol style="margin: 15px 0; padding-left: 25px; color: #555; line-height: 1.8;">
                            <li>Run coverage analysis on <strong>Product 1</strong> (e.g., Intel Client Platform)</li>
                            <li>Run coverage analysis on <strong>Product 2</strong> (e.g., Intel Server Platform)</li>
                            <li>ML models will automatically train and compare products</li>
                        </ol>
                    </div>
                </div>
            </div>
"""
            return html
        
        # Status is complete - show product cards
        num_products = len(products)
        common_analysis = product_comparison.get('common_analysis', {})
        unique_analysis = product_comparison.get('unique_analysis', {})
        
        # Product Cards
        html += f"""
                <div style="display: grid; grid-template-columns: repeat({min(num_products, 3)}, 1fr); gap: 20px; margin-bottom: 30px;">
"""
        
        product_colors = ['#0071C5', '#7b1fa2', '#f39c12', '#28a745', '#dc3545']
        product_icons = ['[1]', '[2]', '[3]', '[4]', '[5]']
        
        for idx, (product_id, product_info) in enumerate(products.items()):
            color = product_colors[idx % len(product_colors)]
            icon = product_icons[idx % len(product_icons)]
            
            # Get product details - handle both old and new data structures
            product_name = product_info.get('product_name', product_id)
            cpu_family = product_info.get('cpu_family', 'Intel Product')
            total_domains = product_info.get('total_domains', 0)
            total_events = product_info.get('total_events', 0)
            datasets_analyzed = product_info.get('datasets_analyzed', product_info.get('total_runs', 0))
            os_coverage = product_info.get('os_coverage', {})
            os_types = list(os_coverage.keys()) if os_coverage else product_info.get('os_tested', [])
            
            html += f"""
                    <div style="background: white; border: 3px solid {color}; border-radius: 12px; padding: 25px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); position: relative;">
                        <div style="position: absolute; top: 10px; right: 15px; background: {color}; color: white; padding: 4px 10px; border-radius: 12px; font-size: 0.75em; font-weight: 600;">
                            ID: {product_id}
                        </div>
                        <div style="text-align: center; margin-bottom: 20px;">
                            <div style="font-size: 2.5em; margin-bottom: 10px;">{icon}</div>
                            <h4 style="color: {color}; margin: 0 0 5px 0; font-size: 1.3em;">{product_name}</h4>
                            <div style="font-size: 0.9em; color: #6c757d; margin-bottom: 8px;">{cpu_family}</div>
"""
            
            if os_types:
                html += """
                            <div style="display: flex; justify-content: center; gap: 8px; margin-top: 8px;">
"""
                for os_type in os_types:
                    os_display = os_type.title() if isinstance(os_type, str) else str(os_type)
                    html += f"""
                                <div style="background: #e3f2fd; padding: 4px 12px; border-radius: 12px; font-size: 0.85em; color: #0071C5; font-weight: 600;">
                                    {os_display}
                                </div>
"""
                html += """
                            </div>
"""
            
            html += f"""
                        </div>
                        <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px;">
                            <div style="text-align: center; padding: 12px; background: #f8f9fa; border-radius: 6px;">
                                <div style="font-size: 0.7em; color: #666; margin-bottom: 5px; font-weight: 600;">DOMAINS</div>
                                <div style="font-size: 1.8em; font-weight: bold; color: {color};">{total_domains}</div>
                            </div>
                            <div style="text-align: center; padding: 12px; background: #f8f9fa; border-radius: 6px;">
                                <div style="font-size: 0.7em; color: #666; margin-bottom: 5px; font-weight: 600;">EVENTS</div>
                                <div style="font-size: 1.8em; font-weight: bold; color: {color};">{total_events}</div>
                            </div>
                            <div style="text-align: center; padding: 12px; background: #f8f9fa; border-radius: 6px;">
                                <div style="font-size: 0.7em; color: #666; margin-bottom: 5px; font-weight: 600;">RUNS</div>
                                <div style="font-size: 1.8em; font-weight: bold; color: #28a745;">{datasets_analyzed}</div>
                            </div>
                        </div>
                    </div>
"""
        
        html += """
                </div>
"""
        
        # Common Domains section
        common_domains = common_analysis.get('domains', {})
        if common_domains.get('count', 0) > 0:
            html += f"""
                <div style="background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%); border-left: 6px solid #28a745; padding: 25px; border-radius: 10px; margin-bottom: 30px;">
                    <h3 style="color: #1b5e20; margin-top: 0; display: flex; align-items: center; gap: 12px;">
                        <span style="font-size: 1.5em;">✅</span>
                        Common Domains Across All Products
                    </h3>
                    <p style="color: #2e7d32; font-size: 1.05em; margin-bottom: 15px;">
                        {common_domains['count']} domain(s) present in all {num_products} product(s)
                    </p>
                    <div style="display: flex; flex-wrap: wrap; gap: 10px;">
"""
            for domain in common_domains.get('list', []):
                html += f"""
                        <div style="background: #28a745; color: white; padding: 10px 18px; border-radius: 20px; font-size: 0.95em; font-weight: 600;">
                            {domain.upper()}
                        </div>
"""
            html += """
                    </div>
                </div>
"""
        
        # Unique Domains (Architectural Differences) section
        if unique_analysis and any(unique_analysis.values()):
            html += """
                <div style="background: linear-gradient(135deg, #fff3e0 0%, #ffe0b2 100%); border-left: 6px solid #ff9800; padding: 25px; border-radius: 10px; margin-bottom: 30px;">
                    <h3 style="color: #e65100; margin-top: 0; display: flex; align-items: center; gap: 12px;">
                        <span style="font-size: 1.5em;">🔬</span>
                        Unique Architectural Features
                    </h3>
                    <p style="color: #ef6c00; font-size: 1.05em; margin-bottom: 20px;">
                        Product-specific PMU domains not found in other products.
                    </p>
                    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px;">
"""
            
            for idx, (product_id, unique_domains) in enumerate(unique_analysis.items()):
                if unique_domains and unique_domains.get('domains'):
                    color = product_colors[idx % len(product_colors)]
                    product_name = products.get(product_id, {}).get('product_name', product_id)
                    
                    html += f"""
                        <div style="background: white; padding: 20px; border-radius: 8px; border-top: 4px solid {color};">
                            <div style="font-weight: 700; color: {color}; margin-bottom: 15px; font-size: 1.15em; display: flex; align-items: center; justify-content: space-between;">
                                <span>{product_name}</span>
                                <span style="background: {color}; color: white; padding: 5px 12px; border-radius: 20px; font-size: 0.7em;">
                                    {len(unique_domains['domains'])} Unique
                                </span>
                            </div>
                            <div style="display: flex; flex-wrap: wrap; gap: 8px;">
"""
                    for domain in unique_domains['domains'][:6]:
                        html += f"""
                                <div style="background: {color}22; color: {color}; padding: 8px 14px; border-radius: 16px; font-size: 0.85em; font-weight: 600; border: 2px solid {color};">
                                    {domain.upper()}
                                </div>
"""
                    if len(unique_domains['domains']) > 6:
                        html += f"""
                                <div style="background: #f8f9fa; color: #666; padding: 8px 14px; border-radius: 16px; font-size: 0.85em; font-weight: 600; border: 2px dashed #dee2e6;">
                                    +{len(unique_domains['domains']) - 6} more
                                </div>
"""
                    html += """
                            </div>
                        </div>
"""
            
            html += """
                    </div>
                </div>
"""
        
        html += """
            </div>
"""
        return html
    
    def _generate_matrix_view_section(self, platform_comparison, product_comparison):
        """Generate matrix view sub-tab content."""
        html = """
            <div id="subtab-matrix" class="insight-subtab" style="display: none;">
                <h3 style="color: #00796b; margin-bottom: 20px;">MATRIX VIEW: PRODUCT × PLATFORM</h3>
                
                <div style="background: #d1ecf1; border-left: 6px solid #17a2b8; padding: 25px; border-radius: 10px;">
                    <h4 style="color: #0c5460; margin-top: 0;">Building Matrix Data</h4>
                    <p style="color: #0c5460; margin: 0;">
                        Matrix view shows best when you have multiple products tested on both Windows and Linux.
                        Continue running coverage analysis on different product/OS combinations to populate this view.
                    </p>
                </div>
            </div>
"""
        return html
