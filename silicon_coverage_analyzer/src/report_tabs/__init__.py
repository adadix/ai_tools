"""
Report Tabs Module

Contains modular tab generators for the HTML report.
Each tab is in its own file for easier maintenance.
"""

from .executive_tab import ExecutiveTabGenerator
from .action_items_tab import ActionItemsTabGenerator
from .coverage_details_tab import CoverageDetailsTabGenerator
from .workload_health_tab import WorkloadHealthTabGenerator
from .platform_product_insights_tab import PlatformProductInsightsTabGenerator
from .ml_training_strategy_tab import MLTrainingStrategyTabGenerator

__all__ = [
    'ExecutiveTabGenerator',
    'ActionItemsTabGenerator',
    'CoverageDetailsTabGenerator',
    'WorkloadHealthTabGenerator',
    'PlatformProductInsightsTabGenerator',
    'MLTrainingStrategyTabGenerator',
]
