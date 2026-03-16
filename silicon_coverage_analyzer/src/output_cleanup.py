"""
Output Directory Cleanup Utility

INTEL CONFIDENTIAL - INTERNAL USE ONLY

Automatically removes old CSV/JSON/HTML output files to prevent disk space issues.
"""

import os
import logging
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


class OutputCleanup:
    """Manages cleanup of old output files."""
    
    def __init__(self, output_dir: str = "output", retention_days: int = 30):
        """
        Initialize output cleanup manager.
        
        Args:
            output_dir: Path to output directory
            retention_days: Number of days to retain files (default: 30)
        """
        self.output_dir = Path(output_dir)
        self.retention_days = retention_days
        logger.info(f"Output cleanup initialized: {retention_days} day retention")
    
    def cleanup_old_files(self, file_patterns: list = None, dry_run: bool = False) -> dict:
        """
        Remove files older than retention period.
        
        Args:
            file_patterns: List of glob patterns to match (e.g., ['*.csv', '*.json'])
            dry_run: If True, only report what would be deleted without actually deleting
            
        Returns:
            dict: Statistics about cleanup operation
        """
        if file_patterns is None:
            file_patterns = [
                'detailed_events_*.csv',
                'domain_summary_*.csv',
                'gap_analysis_*.csv',
                'workload_recommendations_*.csv',
                'silicon_coverage_analysis_*.json',
                'silicon_coverage_analysis_*.html'
            ]
        
        cutoff_date = datetime.now() - timedelta(days=self.retention_days)
        stats = {
            'total_scanned': 0,
            'total_deleted': 0,
            'total_size_freed': 0,
            'files_deleted': []
        }
        
        if not self.output_dir.exists():
            logger.warning(f"Output directory does not exist: {self.output_dir}")
            return stats
        
        logger.info(f"Scanning for files older than {cutoff_date.strftime('%Y-%m-%d')}")
        
        for pattern in file_patterns:
            for file_path in self.output_dir.glob(pattern):
                if not file_path.is_file():
                    continue
                
                stats['total_scanned'] += 1
                file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                
                if file_mtime < cutoff_date:
                    file_size = file_path.stat().st_size
                    file_age_days = (datetime.now() - file_mtime).days
                    
                    if dry_run:
                        logger.info(f"[DRY RUN] Would delete: {file_path.name} (age: {file_age_days} days, size: {file_size:,} bytes)")
                    else:
                        try:
                            file_path.unlink()
                            stats['total_deleted'] += 1
                            stats['total_size_freed'] += file_size
                            stats['files_deleted'].append({
                                'name': file_path.name,
                                'age_days': file_age_days,
                                'size_bytes': file_size
                            })
                            logger.info(f"Deleted: {file_path.name} (age: {file_age_days} days)")
                        except Exception as e:
                            logger.error(f"Failed to delete {file_path.name}: {e}")
        
        if not dry_run and stats['total_deleted'] > 0:
            size_mb = stats['total_size_freed'] / (1024 * 1024)
            logger.info(f"Cleanup complete: {stats['total_deleted']} files deleted, {size_mb:.2f} MB freed")
        elif dry_run:
            logger.info(f"[DRY RUN] Would delete {stats['total_deleted']} files")
        
        return stats
    
    def get_directory_stats(self) -> dict:
        """
        Get statistics about output directory.
        
        Returns:
            dict: Directory statistics
        """
        if not self.output_dir.exists():
            return {'error': 'Directory does not exist'}
        
        stats = {
            'total_files': 0,
            'total_size': 0,
            'file_types': {},
            'oldest_file': None,
            'newest_file': None
        }
        
        oldest_time = None
        newest_time = None
        
        for file_path in self.output_dir.rglob('*'):
            if not file_path.is_file():
                continue
            
            stats['total_files'] += 1
            file_size = file_path.stat().st_size
            stats['total_size'] += file_size
            
            # Track by extension
            ext = file_path.suffix or 'no_extension'
            if ext not in stats['file_types']:
                stats['file_types'][ext] = {'count': 0, 'size': 0}
            stats['file_types'][ext]['count'] += 1
            stats['file_types'][ext]['size'] += file_size
            
            # Track oldest/newest
            file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
            if oldest_time is None or file_mtime < oldest_time:
                oldest_time = file_mtime
                stats['oldest_file'] = {'name': file_path.name, 'date': file_mtime.strftime('%Y-%m-%d')}
            if newest_time is None or file_mtime > newest_time:
                newest_time = file_mtime
                stats['newest_file'] = {'name': file_path.name, 'date': file_mtime.strftime('%Y-%m-%d')}
        
        stats['total_size_mb'] = stats['total_size'] / (1024 * 1024)
        return stats
    
    def auto_cleanup_if_needed(self, max_size_mb: float = 500, max_files: int = 1000) -> Optional[dict]:
        """
        Automatically cleanup if directory exceeds limits.
        
        Args:
            max_size_mb: Maximum directory size in MB before cleanup
            max_files: Maximum number of files before cleanup
            
        Returns:
            dict: Cleanup stats if cleanup was performed, None otherwise
        """
        stats = self.get_directory_stats()
        
        if stats.get('error'):
            return None
        
        total_size_mb = stats.get('total_size_mb', 0)
        total_files = stats.get('total_files', 0)
        
        if total_size_mb > max_size_mb or total_files > max_files:
            logger.warning(f"Output directory exceeds limits (size: {total_size_mb:.1f}MB/{max_size_mb}MB, files: {total_files}/{max_files})")
            logger.info("Starting automatic cleanup...")
            return self.cleanup_old_files(dry_run=False)
        
        return None


if __name__ == "__main__":
    # CLI usage
    import argparse
    
    parser = argparse.ArgumentParser(description='Clean up old output files')
    parser.add_argument('--days', type=int, default=30, help='Retention period in days (default: 30)')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be deleted without deleting')
    parser.add_argument('--stats', action='store_true', help='Show directory statistics')
    parser.add_argument('--output-dir', default='output', help='Output directory path')
    
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    
    cleanup = OutputCleanup(output_dir=args.output_dir, retention_days=args.days)
    
    if args.stats:
        stats = cleanup.get_directory_stats()
        print(f"\nOutput Directory Statistics:")
        print(f"  Total files: {stats['total_files']}")
        print(f"  Total size: {stats['total_size_mb']:.2f} MB")
        print(f"  Oldest file: {stats['oldest_file']['name']} ({stats['oldest_file']['date']})")
        print(f"  Newest file: {stats['newest_file']['name']} ({stats['newest_file']['date']})")
        print(f"\n  File types:")
        for ext, data in stats['file_types'].items():
            print(f"    {ext}: {data['count']} files ({data['size'] / (1024*1024):.2f} MB)")
    else:
        results = cleanup.cleanup_old_files(dry_run=args.dry_run)
        print(f"\nCleanup Results:")
        print(f"  Files scanned: {results['total_scanned']}")
        print(f"  Files deleted: {results['total_deleted']}")
        if not args.dry_run and results['total_deleted'] > 0:
            print(f"  Space freed: {results['total_size_freed'] / (1024*1024):.2f} MB")
