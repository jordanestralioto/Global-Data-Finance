"""Format user-facing messages for B3 historical quote extraction."""

from typing import Any, cast

from ..types import ExtractionResultB3


class HistoricalQuotesResultFormatter:
    """Formats and generates messages for historical quotes extraction results.

    This class is responsible for:
    - Generating user-friendly messages from extraction results
    - Determining success/failure status
    - Formatting statistics and summaries

    This follows Single Responsibility Principle by moving presentation
    logic out of the Use Case layer.
    """

    @staticmethod
    def generate_message(result: dict[str, Any]) -> str:
        """Generate a user-friendly message from extraction results.

        Args:
            result: Dictionary containing extraction results with keys:
                   - error_count (int): Number of errors
                   - total_records (int): Total records extracted
                   - success_count (int): Number of successful files
                   - total_files (int): Total files processed
                   - output_file (str): Path to output file

        Returns:
            Formatted message string describing the extraction results
        """
        if HistoricalQuotesResultFormatter.determine_success(result):
            return (
                f'Successfully extracted {result["total_records"]:,} records '
                f'from {result["success_count"]} files. '
                f'Saved to: {result["output_file"]}'
            )
        else:
            return (
                f'Extraction completed with errors. '
                f'Processed {result["success_count"]}/'
                f'{result["total_files"]} files. '
                f'Extracted {result["total_records"]:,} records. '
                f'Errors: {result["error_count"]}'
            )

    @staticmethod
    def determine_success(result: dict[str, Any]) -> bool:
        """Determine if extraction was successful based on error count.

        Args:
            result: Dictionary containing extraction results

        Returns:
            True if no errors occurred, False otherwise
        """
        integrity = result.get('integrity')
        if isinstance(integrity, dict):
            return (
                integrity.get('status') == 'passed'
                and integrity.get('selection_complete') is True
                and not integrity.get('missing_years')
            )
        return bool(result.get('error_count', 0) == 0)

    @staticmethod
    def enrich_result(result: dict[str, Any]) -> ExtractionResultB3:
        """Enrich extraction result with success flag and message.

        This method adds presentation-layer information to the result
        dictionary returned by the extraction service and narrows it to the
        public :class:`ExtractionResultB3` contract.

        Args:
            result: Raw extraction result from service layer

        Returns:
            Enriched result with 'success' and 'message' fields, typed as the
            public ``ExtractionResultB3`` contract.
        """
        result['success'] = HistoricalQuotesResultFormatter.determine_success(
            result
        )
        result['message'] = HistoricalQuotesResultFormatter.generate_message(
            result
        )
        return cast(ExtractionResultB3, result)
