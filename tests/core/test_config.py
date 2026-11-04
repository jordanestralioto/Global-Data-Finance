import pytest
from pydantic import ValidationError

pytestmark = pytest.mark.unit


def test_defaults_settings():
    from globaldatafinance.core.config import Settings

    settings = Settings()

    assert settings.network.timeout == 180
    assert settings.network.max_retries == 5
    assert settings.network.retry_backoff == 2.0
    assert settings.network.user_agent is None

    assert settings.debug is False


def test_env_overrides_construct_new_snapshot(monkeypatch):
    monkeypatch.setenv('DATAFINANCE_NETWORK_TIMEOUT', '60')

    from globaldatafinance.core.config import Settings

    settings = Settings()
    assert settings.network.timeout == 60


def test_network_settings_bounds_validation():
    from globaldatafinance.core.config import NetworkSettings

    with pytest.raises(ValidationError):
        NetworkSettings(timeout=10)

    with pytest.raises(ValidationError):
        NetworkSettings(max_retries=999)


@pytest.mark.unit
class TestSettingsScenarios:
    def test_scenarios_debug_flag(self):
        from globaldatafinance.core.config import Settings

        settings = Settings()
        assert hasattr(settings, 'debug')
        assert isinstance(settings.debug, bool)

    def test_scenarios_network_user_agent(self):
        from globaldatafinance.core.config import Settings

        settings = Settings()
        assert settings.network.user_agent is None

    def test_scenarios_network_user_agent_can_be_configured(self, monkeypatch):
        from globaldatafinance.core.config import NetworkSettings

        monkeypatch.setenv('DATAFINANCE_NETWORK_USER_AGENT', 'test-client/1.0')

        configured = NetworkSettings()

        assert configured.user_agent == 'test-client/1.0'

    def test_scenarios_network_retry_backoff_bounds(self):
        from globaldatafinance.core.config import NetworkSettings

        with pytest.raises(ValidationError):
            NetworkSettings(retry_backoff=0.05)
        with pytest.raises(ValidationError):
            NetworkSettings(retry_backoff=20.0)

    def test_scenarios_network_max_retries_bounds(self):
        from globaldatafinance.core.config import NetworkSettings

        with pytest.raises(ValidationError):
            NetworkSettings(max_retries=-1)
        with pytest.raises(ValidationError):
            NetworkSettings(max_retries=11)

    def test_scenarios_network_timeout_bounds(self):
        from globaldatafinance.core.config import NetworkSettings

        with pytest.raises(ValidationError):
            NetworkSettings(timeout=5)
        with pytest.raises(ValidationError):
            NetworkSettings(timeout=4000)


def test_settings_does_not_load_dotenv_implicitly(tmp_path, monkeypatch):
    """Settings must ignore a working-directory dotenv unless requested."""
    from globaldatafinance.core.config import Settings

    env_file = tmp_path / '.env'
    env_file.write_text(
        'DATAFINANCE_DEBUG=true\n'
        'DATAFINANCE_NETWORK_TIMEOUT=60\n'
        'unrelated_setting=value\n'
    )

    monkeypatch.chdir(tmp_path)
    for name in (
        'DATAFINANCE_DEBUG',
        'DATAFINANCE_NETWORK',
        'DATAFINANCE_NETWORK_TIMEOUT',
        'DATAFINANCE_NETWORK_MAX_RETRIES',
        'DATAFINANCE_NETWORK_RETRY_BACKOFF',
        'DATAFINANCE_NETWORK_USER_AGENT',
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings()

    assert settings.network.timeout == 180
    assert settings.debug is False
    assert Settings.model_config.get('env_file') is None
    assert Settings.model_config.get('env_file_encoding') is None


def test_settings_loads_dotenv_when_requested_explicitly(
    tmp_path, monkeypatch
):
    """Settings must support pydantic-settings' explicit dotenv override."""
    from globaldatafinance.core.config import Settings

    env_file = tmp_path / 'explicit.env'
    env_file.write_text(
        'DATAFINANCE_DEBUG=true\n'
        'DATAFINANCE_NETWORK={"timeout": 240, "max_retries": 4}\n',
        encoding='utf-8',
    )

    for name in (
        'DATAFINANCE_DEBUG',
        'DATAFINANCE_NETWORK',
        'DATAFINANCE_NETWORK_TIMEOUT',
        'DATAFINANCE_NETWORK_MAX_RETRIES',
        'DATAFINANCE_NETWORK_RETRY_BACKOFF',
        'DATAFINANCE_NETWORK_USER_AGENT',
    ):
        monkeypatch.delenv(name, raising=False)

    settings = Settings(_env_file=env_file)

    assert settings.debug is True
    assert settings.network.timeout == 240
    assert settings.network.max_retries == 4


def test_archive_and_unc_defaults_are_safe() -> None:
    """Global archive limits and the UNC allowlist start from safe defaults."""
    from globaldatafinance.core.config import Settings

    settings = Settings()

    assert settings.path_safety.allowed_unc_roots == ()
    assert isinstance(settings.path_safety.allowed_unc_roots, tuple)
    assert settings.archive.max_archive_bytes == 2 * 1024**3
    assert settings.archive.max_members == 10_000
    assert settings.archive.max_member_uncompressed_bytes == 2 * 1024**3
    assert settings.archive.max_total_uncompressed_bytes == 8 * 1024**3
    assert settings.archive.max_compression_ratio == 200.0
    assert not hasattr(settings, 'archive_safety')


def test_archive_and_unc_environment_values_are_typed(monkeypatch) -> None:
    """Configured archive caps and UNC roots are parsed without dotenv use."""
    from globaldatafinance.core.config import Settings

    monkeypatch.setenv('DATAFINANCE_ARCHIVE_MAX_MEMBERS', '7')
    monkeypatch.setenv('DATAFINANCE_ARCHIVE_MAX_COMPRESSION_RATIO', '17.5')
    monkeypatch.setenv(
        'DATAFINANCE_PATH_SAFETY_ALLOWED_UNC_ROOTS',
        '["\\\\\\\\fileserver\\\\finance\\\\trusted"]',
    )

    settings = Settings()

    assert settings.archive.max_members == 7
    assert settings.archive.max_compression_ratio == 17.5
    assert settings.path_safety.allowed_unc_roots == (
        r'\\fileserver\finance\trusted',
    )
    assert isinstance(settings.path_safety.allowed_unc_roots, tuple)


def test_path_safety_snapshot_copies_explicit_roots() -> None:
    """Explicit UNC roots are validated and detached from caller mutation."""
    from globaldatafinance.core.config import PathSafetySettings

    roots = [r'\\fileserver\finance\trusted']
    resolved_roots = PathSafetySettings.resolve_allowed_unc_roots(roots)
    roots.append(r'\\fileserver\finance\other')

    assert resolved_roots == (r'\\fileserver\finance\trusted',)


@pytest.mark.parametrize(
    ('settings_type', 'kwargs'),
    [
        ('ArchiveSafetySettings', {'max_members': 0}),
        (
            'ArchiveSafetySettings',
            {
                'max_member_uncompressed_bytes': 10,
                'max_total_uncompressed_bytes': 9,
            },
        ),
        ('PathSafetySettings', {'allowed_unc_roots': ['C:/safe']}),
        ('PathSafetySettings', {'allowed_unc_roots': [r'\\server\C$']}),
        (
            'PathSafetySettings',
            {'allowed_unc_roots': [r'\\server\share\trusted\..\other']},
        ),
    ],
)
def test_archive_and_unc_settings_reject_unsafe_values(
    settings_type: str, kwargs: dict[str, object]
) -> None:
    """Invalid resource limits and privilege-bearing UNC roots fail closed."""
    from globaldatafinance.core import config

    configured_type = getattr(config, settings_type)

    with pytest.raises(ValidationError):
        configured_type(**kwargs)


def test_settings_models_are_frozen() -> None:
    """Settings models must be immutable with frozen=True."""
    from globaldatafinance.core.config import (
        ArchiveSafetySettings,
        NetworkSettings,
        PathSafetySettings,
        Settings,
    )

    settings = Settings()
    with pytest.raises(ValidationError):
        settings.debug = True

    with pytest.raises(ValidationError):
        settings.network = NetworkSettings()

    network = NetworkSettings()
    with pytest.raises(ValidationError):
        network.timeout = 100

    path = PathSafetySettings()
    with pytest.raises(ValidationError):
        path.allowed_unc_roots = ()

    archive = ArchiveSafetySettings()
    with pytest.raises(ValidationError):
        archive.max_members = 5


def test_facade_instances_hold_independent_snapshots(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mutating environment after facade creation does not affect existing."""
    from globaldatafinance import FundamentalStocksDataCVM, HistoricalQuotesB3
    from globaldatafinance.core.config import NetworkSettings, Settings

    s1 = Settings(network=NetworkSettings(timeout=100))
    cvm1 = FundamentalStocksDataCVM(settings=s1)
    b31 = HistoricalQuotesB3(settings=s1)

    monkeypatch.setenv('DATAFINANCE_NETWORK_TIMEOUT', '200')

    cvm2 = FundamentalStocksDataCVM()
    b32 = HistoricalQuotesB3()

    assert cvm1.settings.network.timeout == 100
    assert b31.settings.network.timeout == 100
    assert cvm2.settings.network.timeout == 200
    assert b32.settings.network.timeout == 200
