"""Domain exceptions raised while validating B3 historical quote inputs."""


class B3Error(Exception):
    """Base class for all B3 domain exceptions."""


class InvalidFirstYear(B3Error):
    """Raised when the first requested year is outside the supported range."""

    def __init__(self, minimal_first_year: int, current_year: int):
        """Describe the supported lower and upper year boundaries."""
        super().__init__(
            'Invalid first year. You must provide an integer value greater '
            f'than or equal to {minimal_first_year} year and less than or '
            f'equal to {current_year}.'
        )


class InvalidLastYear(B3Error):
    """Raised when the last requested year is outside the supported range."""

    def __init__(self, first_year: int, current_year: int):
        """Describe the first requested year and current upper boundary."""
        super().__init__(
            'Invalid last year. You must provide an integer value greater '
            f'than or equal to the {first_year} year and less than or equal '
            f'to {current_year}.'
        )


class InvalidAssetsName(B3Error):
    """Raised when an asset selection contains unsupported names."""

    def __init__(
        self, assets_list: list[str], list_available_assets: list[str]
    ):
        """Describe requested names and available asset classes."""
        super().__init__(
            f'Invalid assets names: {assets_list}. Assets must be a list of '
            f'strings and one of: {list_available_assets}.'
        )


class EmptyAssetListError(B3Error):
    """Raised when extraction receives no asset classes."""

    def __init__(self, message: str = 'Asset list cannot be empty.'):
        """Initialize the error with a caller-facing validation message."""
        super().__init__(message)


class InvalidProcessingMode(B3Error):
    """Raised when the extraction mode is not ``fast`` or ``slow``."""

    def __init__(self, mode: str, valid_modes: list[str]):
        """Describe the invalid mode and accepted alternatives."""
        super().__init__(
            f"Invalid processing_mode '{mode}'. Must be one of: {valid_modes}"
        )


class InvalidOutputFilename(B3Error):
    """Raised when the output name is not a safe Parquet basename."""

    def __init__(self, message: str):
        """Initialize the error with the filename validation reason."""
        super().__init__(f'Invalid output filename: {message}')
