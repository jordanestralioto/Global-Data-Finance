"""Centralized configuration module for global Global-Data-Finance settings.

This module provides type-safe, validated configuration management
with support for environment variables and default values.

ONLY contains truly global configurations that apply across all data sources
(CVM, B3, SEC, etc.). Source-specific configs remain in their respective
domains.

Note: For logging configuration, use the
globaldatafinance.core.logging_config module directly.

Example:
    >>> from globaldatafinance.core.config import Settings
    >>> settings = Settings()
    >>> print(settings.network.timeout)
    180
    >>> # Override via environment variable
    >>> # export DATAFINANCE_NETWORK_TIMEOUT=600
"""

from collections.abc import Sequence
from pathlib import PureWindowsPath

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_GIBIBYTE = 1024**3


class NetworkSettings(BaseSettings):
    """Global network configuration for HTTP requests."""

    timeout: int = Field(
        default=180,
        ge=30,
        le=3600,
        description='Default timeout for HTTP requests in seconds',
    )

    max_retries: int = Field(
        default=5,
        ge=0,
        le=10,
        description=(
            'Maximum number of additional retry attempts after the first '
            'request'
        ),
    )

    retry_backoff: float = Field(
        default=2.0,
        ge=0.1,
        le=10.0,
        description='Backoff multiplier for retries (exponential backoff)',
    )

    user_agent: str | None = Field(
        default=None,
        description='Optional user agent header for HTTP requests',
    )

    model_config = SettingsConfigDict(
        env_prefix='DATAFINANCE_NETWORK_',
        case_sensitive=False,
        extra='ignore',
        frozen=True,
    )


class PathSafetySettings(BaseSettings):
    """Global allowlist configuration for caller-provided UNC destinations."""

    allowed_unc_roots: tuple[str, ...] = Field(
        default_factory=tuple,
        description=(
            'JSON list of trusted UNC roots allowed as caller destinations'
        ),
    )

    model_config = SettingsConfigDict(
        env_prefix='DATAFINANCE_PATH_SAFETY_',
        case_sensitive=False,
        extra='ignore',
        frozen=True,
    )

    @field_validator('allowed_unc_roots', mode='before')
    @classmethod
    def validate_allowed_unc_roots(
        cls, roots: Sequence[str] | None
    ) -> tuple[str, ...]:
        """Require absolute, non-administrative UNC roots in the allowlist."""
        if roots is None:
            return ()
        normalized_roots: list[str] = []
        for root in roots:
            if not isinstance(root, str):
                raise ValueError('Each allowed UNC root must be a UNC path')
            unc_path = PureWindowsPath(root)
            if not unc_path.drive.startswith('\\\\'):
                raise ValueError('Each allowed UNC root must be a UNC path')
            if not unc_path.is_absolute():
                raise ValueError('Each allowed UNC root must be absolute')
            if '..' in unc_path.parts:
                raise ValueError(
                    'Allowed UNC roots cannot contain parent components'
                )
            share_name = unc_path.drive.rsplit('\\', maxsplit=1)[-1]
            if share_name.rstrip(' .').endswith('$'):
                raise ValueError('Administrative UNC shares cannot be allowed')
            normalized_roots.append(str(unc_path))
        return tuple(normalized_roots)

    @classmethod
    def resolve_allowed_unc_roots(
        cls, roots: Sequence[str] | None = None
    ) -> tuple[str, ...]:
        """Return a validated immutable UNC-root snapshot."""
        if roots is None:
            return cls().allowed_unc_roots
        return cls(allowed_unc_roots=tuple(roots)).allowed_unc_roots


class ArchiveSafetySettings(BaseSettings):
    """Bounded limits applied before and while consuming ZIP archives."""

    max_archive_bytes: int = Field(
        default=2 * _GIBIBYTE,
        ge=1,
        le=32 * _GIBIBYTE,
        description='Maximum compressed ZIP archive size in bytes',
    )
    max_members: int = Field(
        default=10_000,
        ge=1,
        le=100_000,
        description='Maximum number of ZIP members',
    )
    max_member_uncompressed_bytes: int = Field(
        default=2 * _GIBIBYTE,
        ge=1,
        le=32 * _GIBIBYTE,
        description='Maximum uncompressed size of one ZIP member in bytes',
    )
    max_total_uncompressed_bytes: int = Field(
        default=8 * _GIBIBYTE,
        ge=1,
        le=64 * _GIBIBYTE,
        description='Maximum total uncompressed ZIP payload in bytes',
    )
    max_compression_ratio: float = Field(
        default=200.0,
        gt=0.0,
        le=10_000.0,
        description='Maximum allowed ZIP member expansion ratio',
    )

    model_config = SettingsConfigDict(
        env_prefix='DATAFINANCE_ARCHIVE_',
        case_sensitive=False,
        extra='ignore',
        frozen=True,
    )

    @model_validator(mode='after')
    def validate_cross_field_limits(self) -> 'ArchiveSafetySettings':
        """Reject a total archive limit smaller than one allowed member."""
        if (
            self.max_total_uncompressed_bytes
            < self.max_member_uncompressed_bytes
        ):
            raise ValueError(
                'max_total_uncompressed_bytes must be at least '
                'max_member_uncompressed_bytes'
            )
        return self


class Settings(BaseSettings):
    """Main settings container for global configurations.

    Contains only truly global settings. Source-specific configurations
    (CVM, B3, SEC) remain in their respective domain modules.

    Note: Logging configuration has moved to
    globaldatafinance.core.logging_config.
    """

    network: NetworkSettings = Field(default_factory=NetworkSettings)
    path_safety: PathSafetySettings = Field(default_factory=PathSafetySettings)
    archive: ArchiveSafetySettings = Field(
        default_factory=ArchiveSafetySettings
    )

    debug: bool = Field(
        default=False, description='Enable debug mode globally'
    )

    model_config = SettingsConfigDict(
        env_prefix='DATAFINANCE_',
        case_sensitive=False,
        extra='ignore',
        frozen=True,
    )
