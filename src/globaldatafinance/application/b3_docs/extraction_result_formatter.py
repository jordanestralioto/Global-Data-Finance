"""Formatter for extraction results display.

This module provides formatted output for B3 historical quotes extraction
results, making it easy for users to understand extraction outcomes.
"""

from typing import Any


class ExtractionResultFormatter:
    """Formats extraction results for user-friendly display.

    Provides colored, organized output showing:
    - Extraction summary
    - Success/error statistics
    - Output file location
    - Record counts
    - Error details if any
    """

    # ANSI color codes
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    RESET = '\033[0m'

    def __init__(self, use_colors: bool = True):
        """Initialize the formatter.

        Args:
            use_colors: Whether to use ANSI colors in output (default: True)
        """
        self.use_colors = use_colors

    def _colorize(self, text: str, color: str) -> str:
        """Apply color to text if colors are enabled."""
        if self.use_colors:
            return f'{color}{text}{self.RESET}'
        return text

    def print_result(self, result: dict[str, Any]) -> None:
        """Print formatted extraction results.

        Args:
            result: Dictionary containing extraction results with keys:
                   - success (bool)
                   - message (str)
                   - total_files (int)
                   - success_count (int)
                   - error_count (int)
                   - total_records (int)
                   - output_file (str)
                   - errors (dict[str, str]) - always present, possibly empty
                   - assets (list)
                   - processing_mode (str)
                   - elapsed_time (float)
        """
        title = self._colorize(
            '📊 B3 Historical Quotes Extraction', self.BOLD + self.CYAN
        )
        print(f'\n{title}')
        print(
            '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━'
        )

        # Status
        if result.get('success', False):
            status_text = '✓ Extraction completed successfully!'
            status_color = self.GREEN
        else:
            status_text = '✗ Extraction completed with errors!'
            status_color = (
                self.YELLOW if result.get('error_count', 0) > 0 else self.RED
            )

        print(f'{self._colorize(status_text, self.BOLD + status_color)}')

        # Summary
        print(f'\n{self._colorize("📈 Summary:", self.BOLD + self.BLUE)}')

        # Files processed
        success_count = result.get('success_count', 0)
        print(f'  • Processed files: {success_count}')

        # Total records
        total_records = result.get('total_records', 0)
        print(f'  • Total records: {total_records:,}')

        # Assets
        assets = result.get('assets', [])
        assets_str = (
            ', '.join(assets) if isinstance(assets, list) else str(assets)
        )
        print(f'  • Asset classes: {assets_str}')

        # Processing mode
        print(
            f'  • Processing mode: {result.get("processing_mode", "unknown")}'
        )

        # Elapsed time
        elapsed = result.get('elapsed_time', 0)
        print(f'  • Elapsed time: {elapsed:.1f}s')

        # Output file
        if 'output_file' in result:
            output_label = self._colorize(
                '💾 Generated file:', self.BOLD + self.BLUE
            )
            print(f'\n{output_label}')
            print(f'  {result["output_file"]}')

        # Error details
        if result.get('error_count', 0) > 0 and 'errors' in result:
            print(
                f'\n{self._colorize("⚠️ Error details:", self.BOLD + self.RED)}'
            )
            errors = result['errors']
            if isinstance(errors, dict):
                for file_path, error_msg in errors.items():
                    print(f'  • {file_path}')
                    print(
                        f'    {self._colorize("Error:", self.RED)} {error_msg}'
                    )
            else:
                for error in errors:
                    print(f'  • {error}')
