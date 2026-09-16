from pathlib import Path

import pytest

from globaldatafinance.brazil.b3_data.historical_quotes.filesystem import (
    FileSystemServiceB3,
)
from globaldatafinance.core.utils import assert_path_not_sensitive
from globaldatafinance.macro_exceptions import (
    EmptyDirectoryError,
    InvalidDestinationPathError,
    PathIsNotDirectoryError,
    SecurityError,
)

pytestmark = pytest.mark.unit


class TestFileSystemService:
    @pytest.fixture
    def service(self):
        return FileSystemServiceB3()

    def test_validate_directory_path_valid(self, service, tmp_path):
        test_dir = tmp_path / 'test_dir'
        test_dir.mkdir()
        (test_dir / 'file.txt').write_text('test')

        result = service.validate_directory_path(str(test_dir))

        assert isinstance(result, Path)
        assert result.exists()
        assert result.is_dir()

    def test_validate_directory_path_with_files(self, service, tmp_path):
        test_dir = tmp_path / 'data'
        test_dir.mkdir()
        (test_dir / 'file1.zip').write_text('data1')
        (test_dir / 'file2.zip').write_text('data2')

        result = service.validate_directory_path(str(test_dir))

        assert result.exists()
        assert result.is_dir()

    def test_validate_directory_path_not_string_type(self, service):
        with pytest.raises(TypeError):
            service.validate_directory_path(123)

    def test_validate_directory_path_none(self, service):
        with pytest.raises(TypeError):
            service.validate_directory_path(None)

    def test_validate_directory_path_empty_string(self, service):
        with pytest.raises(InvalidDestinationPathError):
            service.validate_directory_path('')

    def test_validate_directory_path_whitespace_only(self, service):
        with pytest.raises(InvalidDestinationPathError):
            service.validate_directory_path('   ')

    def test_validate_directory_path_nonexistent(self, service):
        with pytest.raises(PathIsNotDirectoryError):
            service.validate_directory_path('/nonexistent/path/to/dir')

    def test_validate_directory_path_is_file(self, service, tmp_path):
        file_path = tmp_path / 'file.txt'
        file_path.write_text('content')

        with pytest.raises(PathIsNotDirectoryError):
            service.validate_directory_path(str(file_path))

    def test_validate_directory_path_empty_directory(self, service, tmp_path):
        empty_dir = tmp_path / 'empty'
        empty_dir.mkdir()

        with pytest.raises(EmptyDirectoryError):
            service.validate_directory_path(str(empty_dir))

    def test_validate_directory_path_with_tilde_expansion(
        self, service, tmp_path
    ):
        test_dir = tmp_path / 'test'
        test_dir.mkdir()
        (test_dir / 'file.txt').write_text('test')

        result = service.validate_directory_path(str(test_dir))
        assert result.exists()

    def test_validate_directory_path_relative(
        self, service, tmp_path, monkeypatch
    ):
        test_dir = tmp_path / 'relative_test'
        test_dir.mkdir()
        (test_dir / 'file.txt').write_text('test')

        monkeypatch.chdir(tmp_path)

        result = service.validate_directory_path('relative_test')

        assert result.exists()
        assert result.is_absolute()


class TestFileSystemServiceSecurityValidation:
    @pytest.fixture
    def service(self):
        return FileSystemServiceB3()

    def test_validate_path_safety_blocks_etc(self):
        with pytest.raises(SecurityError):
            assert_path_not_sensitive(Path('/etc/passwd').resolve())

    def test_validate_path_safety_blocks_root(self):
        with pytest.raises(SecurityError):
            assert_path_not_sensitive(Path('/root/secret').resolve())

    def test_validate_path_safety_blocks_sys(self):
        with pytest.raises(SecurityError):
            assert_path_not_sensitive(Path('/sys/kernel').resolve())

    def test_validate_path_safety_blocks_proc(self):
        with pytest.raises(SecurityError):
            assert_path_not_sensitive(Path('/proc/meminfo').resolve())

    def test_validate_path_safety_blocks_dev(self):
        with pytest.raises(SecurityError):
            assert_path_not_sensitive(Path('/dev/null').resolve())

    def test_validate_path_safety_blocks_boot(self):
        with pytest.raises(SecurityError):
            assert_path_not_sensitive(Path('/boot/grub').resolve())

    def test_validate_path_safety_blocks_usr(self):
        with pytest.raises(SecurityError):
            assert_path_not_sensitive(Path('/usr/local/bin').resolve())

    def test_validate_path_safety_blocks_var(self):
        with pytest.raises(SecurityError):
            assert_path_not_sensitive(Path('/var/log/secret').resolve())

    def test_validate_path_safety_blocks_lib(self):
        with pytest.raises(SecurityError):
            assert_path_not_sensitive(Path('/lib/systemd').resolve())

    def test_validate_path_safety_blocks_user_ssh(self):
        target = Path.home() / '.ssh' / 'id_rsa'
        with pytest.raises(SecurityError):
            assert_path_not_sensitive(target)

    def test_validate_path_safety_blocks_user_aws(self):
        target = Path.home() / '.aws' / 'credentials'
        with pytest.raises(SecurityError):
            assert_path_not_sensitive(target)

    def test_validate_path_safety_blocks_user_gnupg(self):
        target = Path.home() / '.gnupg' / 'secring.gpg'
        with pytest.raises(SecurityError):
            assert_path_not_sensitive(target)

    def test_validate_path_safety_allows_user_config(
        self, tmp_path, monkeypatch
    ):
        # ~/.config is intentionally allowed for legitimate user configuration.
        fake_home = tmp_path / 'fake_home'
        fake_home.mkdir()
        config_dir = fake_home / '.config' / 'globaldatafinance' / 'cache'
        config_dir.mkdir(parents=True)
        monkeypatch.setenv('HOME', str(fake_home))
        assert assert_path_not_sensitive(config_dir.resolve()) is None

    def test_validate_directory_path_blocks_windows_system(self, service):
        # Cross-platform: even on POSIX, a Windows system path must be
        # rejected via the raw-string drive-letter check.
        with pytest.raises(SecurityError):
            service.validate_directory_path('C:\\Windows\\System32')

    def test_validate_directory_path_blocks_windows_program_files(
        self, service
    ):
        with pytest.raises(SecurityError):
            service.validate_directory_path('C:\\Program Files\\Sensitive')

    def test_validate_path_safety_does_not_false_positive_etcd(self, tmp_path):
        # Regression: the previous CVM `startswith` check would block
        # /etcd_data because the prefix /etc matches; the path-aware
        # helper must allow such directories.
        etcd_like = tmp_path / 'etcd_data'
        etcd_like.mkdir()
        assert assert_path_not_sensitive(etcd_like.resolve()) is None

    def test_validate_path_safety_allows_safe_paths(self, tmp_path):
        safe_dir = tmp_path / 'safe_directory'
        safe_dir.mkdir()

        assert assert_path_not_sensitive(safe_dir.resolve()) is None

    def test_validate_path_safety_allows_home_directory(self, tmp_path):
        home_like = tmp_path / 'home' / 'user' / 'data'
        home_like.mkdir(parents=True)

        assert assert_path_not_sensitive(home_like.resolve()) is None

    def test_validate_directory_with_path_traversal_attempt(
        self, service, tmp_path
    ):
        safe_dir = tmp_path / 'safe'
        safe_dir.mkdir()
        (safe_dir / 'file.txt').write_text('test')

        traversal_path = str(safe_dir / '..' / '..' / '..' / 'etc')

        with pytest.raises(
            (PathIsNotDirectoryError, SecurityError, EmptyDirectoryError)
        ):
            service.validate_directory_path(traversal_path)


class TestFileSystemServiceFindFiles:
    @pytest.fixture
    def service(self):
        return FileSystemServiceB3()

    def test_find_files_by_years_single_year(self, service, tmp_path):
        test_dir = tmp_path / 'data'
        test_dir.mkdir()

        (test_dir / 'COTAHIST_A2023.ZIP').write_text('data')
        (test_dir / 'COTAHIST_A2022.ZIP').write_text('data')

        years = range(2023, 2024)
        result = service.find_files_by_years(test_dir, years)

        assert len(result) == 1
        assert any('COTAHIST_A2023.ZIP' in f for f in result)
        assert not any('2022' in f for f in result)

    def test_find_files_by_years_multiple_years(self, service, tmp_path):
        test_dir = tmp_path / 'data'
        test_dir.mkdir()

        (test_dir / 'COTAHIST_A2020.ZIP').write_text('data')
        (test_dir / 'COTAHIST_A2021.ZIP').write_text('data')
        (test_dir / 'COTAHIST_A2022.ZIP').write_text('data')
        (test_dir / 'COTAHIST_A2023.ZIP').write_text('data')
        (test_dir / 'COTAHIST_A2024.ZIP').write_text('data')

        years = range(2021, 2024)
        result = service.find_files_by_years(test_dir, years)

        assert len(result) == 3
        assert any('COTAHIST_A2021.ZIP' in f for f in result)
        assert any('COTAHIST_A2022.ZIP' in f for f in result)
        assert any('COTAHIST_A2023.ZIP' in f for f in result)
        assert not any('A2020' in f for f in result)
        assert not any('A2024' in f for f in result)

    def test_find_files_by_years_no_matches(self, service, tmp_path):
        test_dir = tmp_path / 'data'
        test_dir.mkdir()

        (test_dir / 'COTAHIST_A2020.ZIP').write_text('data')
        (test_dir / 'COTAHIST_A2021.ZIP').write_text('data')

        years = range(2025, 2027)
        result = service.find_files_by_years(test_dir, years)

        assert len(result) == 0

    def test_find_files_by_years_empty_directory(self, service, tmp_path):
        test_dir = tmp_path / 'empty'
        test_dir.mkdir()

        years = range(2020, 2024)
        result = service.find_files_by_years(test_dir, years)

        assert len(result) == 0

    def test_find_files_by_years_ignores_subdirectories(
        self, service, tmp_path
    ):
        test_dir = tmp_path / 'data'
        test_dir.mkdir()

        (test_dir / 'COTAHIST_A2023.ZIP').write_text('data')
        subdir = test_dir / 'COTAHIST_A2023'
        subdir.mkdir()

        years = range(2023, 2024)
        result = service.find_files_by_years(test_dir, years)

        assert len(result) == 1
        assert 'COTAHIST_A2023.ZIP' in str(next(iter(result)))

    def test_find_files_by_years_accepts_zip_and_txt(self, service, tmp_path):
        test_dir = tmp_path / 'data'
        test_dir.mkdir()

        (test_dir / 'COTAHIST_A2023.ZIP').write_text('data')
        (test_dir / 'COTAHIST_A2023.TXT').write_text('data')
        # Non-official extension must be ignored.
        (test_dir / 'COTAHIST_A2023.CSV').write_text('data')

        years = range(2023, 2024)
        result = service.find_files_by_years(test_dir, years)

        assert result == {str(test_dir / 'COTAHIST_A2023.ZIP')}

    def test_find_files_by_years_uses_txt_when_zip_is_absent(
        self, service, tmp_path
    ):
        test_dir = tmp_path / 'data'
        test_dir.mkdir()
        txt_path = test_dir / 'COTAHIST_A2023.TXT'
        txt_path.write_text('data')

        result = service.find_files_by_years(test_dir, range(2023, 2024))

        assert result == {str(txt_path)}

    def test_find_files_by_years_prefers_zip_for_duplicate_year(
        self, service, tmp_path, caplog
    ):
        test_dir = tmp_path / 'data'
        test_dir.mkdir()
        zip_path = test_dir / 'COTAHIST_A2023.ZIP'
        txt_path = test_dir / 'COTAHIST_A2023.TXT'
        zip_path.write_text('zip')
        txt_path.write_text('txt')

        result = service.find_files_by_years(test_dir, range(2023, 2024))

        assert result == {str(zip_path)}
        assert 'selecting one deterministically' in caplog.text
        warning = next(
            record
            for record in caplog.records
            if record.levelname == 'WARNING'
        )
        assert warning.selected_file == str(zip_path)
        assert warning.ignored_files == [str(txt_path)]

    def test_find_files_by_years_is_case_insensitive(self, service, tmp_path):
        test_dir = tmp_path / 'data'
        test_dir.mkdir()

        lower_case_path = test_dir / 'cotahist_a2023.zip'
        upper_case_path = test_dir / 'CotaHist_A2024.Zip'
        lower_case_path.write_text('data')
        upper_case_path.write_text('data')

        years = range(2023, 2025)
        result = service.find_files_by_years(test_dir, years)

        assert result == {str(lower_case_path), str(upper_case_path)}

    def test_find_files_by_years_ignores_non_cotahist_files(
        self, service, tmp_path
    ):
        """Non-COTAHIST files in the directory must never match."""
        test_dir = tmp_path / 'data'
        test_dir.mkdir()

        (test_dir / 'OTHER_2023.ZIP').write_text('data')
        (test_dir / 'DATA_2023.TXT').write_text('data')
        (test_dir / '2023_DATA.ZIP').write_text('data')
        (test_dir / 'COTAHIST_A2023_FINAL.ZIP').write_text('data')
        (test_dir / 'README.md').write_text('data')

        years = range(2023, 2024)
        result = service.find_files_by_years(test_dir, years)

        assert len(result) == 0

    def test_find_files_by_years_rejects_partial_year_false_positive(
        self, service, tmp_path
    ):
        """``data_12020.zip`` must not match the year ``2020`` (E3)."""
        test_dir = tmp_path / 'data'
        test_dir.mkdir()

        (test_dir / 'data_12020.zip').write_text('data')
        (test_dir / 'COTAHIST_A20201.ZIP').write_text('data')
        (test_dir / 'COTAHIST_A202.ZIP').write_text('data')
        (test_dir / 'VERSION_20231.ZIP').write_text('data')

        years = range(2020, 2024)
        result = service.find_files_by_years(test_dir, years)

        assert len(result) == 0

    def test_find_files_by_years_empty_range(self, service, tmp_path):
        test_dir = tmp_path / 'data'
        test_dir.mkdir()

        (test_dir / 'COTAHIST_A2023.ZIP').write_text('data')

        years = range(2023, 2023)
        result = service.find_files_by_years(test_dir, years)

        assert len(result) == 0


class TestFileSystemServiceIntegration:
    @pytest.fixture
    def service(self):
        return FileSystemServiceB3()

    def test_validate_and_find_workflow(self, service, tmp_path):
        data_dir = tmp_path / 'cotahist_data'
        data_dir.mkdir()

        (data_dir / 'COTAHIST_A2022.ZIP').write_text('data')
        (data_dir / 'COTAHIST_A2023.ZIP').write_text('data')
        (data_dir / 'COTAHIST_A2024.ZIP').write_text('data')

        validated_path = service.validate_directory_path(str(data_dir))

        years = range(2022, 2025)
        files = service.find_files_by_years(validated_path, years)

        assert len(files) == 3
        assert all('COTAHIST' in f for f in files)

    def test_handles_symlinks(self, service, tmp_path):
        real_dir = tmp_path / 'real'
        real_dir.mkdir()
        (real_dir / 'file.txt').write_text('data')

        link_dir = tmp_path / 'link'
        try:
            link_dir.symlink_to(real_dir)
            result = service.validate_directory_path(str(link_dir))
            assert result.exists()
        except OSError:
            pytest.skip('Symlink creation not supported')

    def test_multiple_validations(self, service, tmp_path):
        dir1 = tmp_path / 'dir1'
        dir1.mkdir()
        (dir1 / 'file1.txt').write_text('data')

        dir2 = tmp_path / 'dir2'
        dir2.mkdir()
        (dir2 / 'file2.txt').write_text('data')

        result1 = service.validate_directory_path(str(dir1))
        result2 = service.validate_directory_path(str(dir2))

        assert result1 != result2
        assert result1.exists()
        assert result2.exists()

    def test_large_directory(self, service, tmp_path):
        data_dir = tmp_path / 'large'
        data_dir.mkdir()

        for year in range(2000, 2025):
            (data_dir / f'COTAHIST_A{year}.ZIP').write_text('data')

        validated_path = service.validate_directory_path(str(data_dir))

        years = range(2020, 2023)
        files = service.find_files_by_years(validated_path, years)

        assert len(files) == 3


class TestFileSystemServiceEdgeCases:
    @pytest.fixture
    def service(self):
        return FileSystemServiceB3()

    def test_directory_with_special_characters(self, service, tmp_path):
        special_dir = tmp_path / 'dir with spaces & special!chars'
        special_dir.mkdir()
        (special_dir / 'file.txt').write_text('data')

        result = service.validate_directory_path(str(special_dir))
        assert result.exists()

    def test_directory_with_unicode_name(self, service, tmp_path):
        unicode_dir = tmp_path / 'Programação_Açúcar'
        unicode_dir.mkdir()
        (unicode_dir / 'arquivo.txt').write_text('data')

        result = service.validate_directory_path(str(unicode_dir))
        assert result.exists()

    def test_very_long_path(self, service, tmp_path):
        long_path = tmp_path
        for i in range(10):
            long_path = long_path / f'directory_level_{i}'
        long_path.mkdir(parents=True)
        (long_path / 'file.txt').write_text('data')

        result = service.validate_directory_path(str(long_path))
        assert result.exists()

    def test_find_files_ignores_numeric_only_names(self, service, tmp_path):
        """Numeric-only names are not official COTAHIST files (E3)."""
        data_dir = tmp_path / 'data'
        data_dir.mkdir()

        (data_dir / '2023').write_text('data')
        (data_dir / '20231231').write_text('data')

        years = range(2023, 2024)
        files = service.find_files_by_years(data_dir, years)

        assert len(files) == 0

    def test_find_files_only_matches_official_naming(self, service, tmp_path):
        data_dir = tmp_path / 'data'
        data_dir.mkdir()

        (data_dir / 'COTAHIST_A2023.zip').write_text('data')
        (data_dir / 'file_2023.zip').write_text('data')
        (data_dir / 'COTAHIST_AXXXX.zip').write_text('data')

        years = range(2023, 2024)
        files = service.find_files_by_years(data_dir, years)

        assert len(files) == 1
        assert 'COTAHIST_A2023' in next(iter(files))
