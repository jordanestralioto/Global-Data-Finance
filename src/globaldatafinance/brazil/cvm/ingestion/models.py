"""Results shared by CVM archive ingestion operations."""

from dataclasses import dataclass, field


@dataclass
class DownloadResultCVM:
    """Aggregated result of a CVM download run."""

    successful_downloads: list[str] = field(default_factory=list)
    failed_downloads: dict[str, str] = field(default_factory=dict)
    elapsed_time: float = 0.0
    _success_set: set[str] = field(default_factory=set, init=False, repr=False)

    def __post_init__(self) -> None:
        """Build the private set used to deduplicate successful downloads."""
        self._success_set = set(self.successful_downloads)

    @property
    def success_count_downloads(self) -> int:
        """Return the number of successful downloads."""
        return len(self.successful_downloads)

    @property
    def error_count_downloads(self) -> int:
        """Return the number of failed downloads."""
        return len(self.failed_downloads)

    def has_errors(self) -> bool:
        """Return ``True`` when at least one download failed."""
        return self.error_count_downloads > 0

    def add_success_downloads(self, item: str) -> None:
        """Record a successful download once."""
        if item not in self._success_set:
            self.successful_downloads.append(item)
            self._success_set.add(item)

    def add_error_downloads(self, item: str, error: str) -> None:
        """Record the error associated with a failed download."""
        self.failed_downloads[item] = error

    def __str__(self) -> str:
        """Return a concise summary of the download result."""
        return (
            f'DownloadResultCVM(success={self.success_count_downloads}, '
            f'errors={self.error_count_downloads})'
        )
