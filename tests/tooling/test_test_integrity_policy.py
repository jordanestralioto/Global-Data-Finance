"""Regression tests for hash-bound test-integrity authorizations."""

from pathlib import Path

import pytest

from tests.tooling.test_local_quality_gates import (
    TEST_INTEGRITY,
    initialize_git_repository,
    run_gate,
    run_git,
    stage_assertion_reduction_policy,
    staged_test_patch_hash,
)

pytestmark = pytest.mark.unit


def test_test_integrity_accepts_one_exact_hash_bound_reduction(
    tmp_path: Path,
) -> None:
    """A structured authorization must match the complete staged patch."""
    initialize_git_repository(tmp_path)
    test_file = tmp_path / 'tests' / 'test_guarded.py'
    test_file.parent.mkdir()
    test_file.write_text(
        'def test_guarded() -> None:\n    assert 1 == 1\n    assert 2 == 2\n',
        encoding='utf-8',
    )
    run_git(tmp_path, 'add', '--', 'tests/test_guarded.py')
    run_git(tmp_path, 'commit', '--quiet', '-m', 'baseline')

    test_file.write_text(
        'def test_guarded() -> None:\n    assert 1 == 1\n',
        encoding='utf-8',
    )
    run_git(tmp_path, 'add', '--', 'tests/test_guarded.py')
    digest = staged_test_patch_hash(tmp_path)
    stage_assertion_reduction_policy(
        tmp_path,
        entries=[
            {
                'path': 'tests/test_guarded.py',
                'diff_sha256': digest,
                'replacement_test_ids': [
                    'tests/test_guarded.py::test_guarded'
                ],
                'reason': 'The assertion is covered by the replacement test.',
            }
        ],
    )

    result = run_gate(TEST_INTEGRITY, tmp_path)

    assert result.returncode == 0, result.stderr


def test_test_integrity_rejects_an_authorization_for_an_altered_patch(
    tmp_path: Path,
) -> None:
    """Changing a reduction after approval invalidates its recorded hash."""
    initialize_git_repository(tmp_path)
    test_file = tmp_path / 'tests' / 'test_guarded.py'
    test_file.parent.mkdir()
    test_file.write_text(
        'def test_guarded() -> None:\n    assert 1 == 1\n    assert 2 == 2\n',
        encoding='utf-8',
    )
    run_git(tmp_path, 'add', '--', 'tests/test_guarded.py')
    run_git(tmp_path, 'commit', '--quiet', '-m', 'baseline')

    test_file.write_text(
        'def test_guarded() -> None:\n    assert 1 == 1\n',
        encoding='utf-8',
    )
    run_git(tmp_path, 'add', '--', 'tests/test_guarded.py')
    digest = staged_test_patch_hash(tmp_path)
    stage_assertion_reduction_policy(
        tmp_path,
        entries=[
            {
                'path': 'tests/test_guarded.py',
                'diff_sha256': digest,
                'replacement_test_ids': [
                    'tests/test_guarded.py::test_guarded'
                ],
                'reason': 'The assertion is covered by the replacement test.',
            }
        ],
    )

    test_file.write_text(
        'def test_guarded() -> None:\n    assert 1 == 2\n',
        encoding='utf-8',
    )
    run_git(tmp_path, 'add', '--', 'tests/test_guarded.py')

    result = run_gate(TEST_INTEGRITY, tmp_path)

    assert result.returncode == 1
    assert 'diff_sha256' in result.stderr


def test_test_integrity_rejects_an_inline_reduction_approval(
    tmp_path: Path,
) -> None:
    """Inline comments cannot bypass a hash-bound authorization."""
    initialize_git_repository(tmp_path)
    test_file = tmp_path / 'tests' / 'test_guarded.py'
    test_file.parent.mkdir()
    test_file.write_text(
        'def test_guarded() -> None:\n    assert 1 == 1\n    assert 2 == 2\n',
        encoding='utf-8',
    )
    run_git(tmp_path, 'add', '--', 'tests/test_guarded.py')
    run_git(tmp_path, 'commit', '--quiet', '-m', 'baseline')

    test_file.write_text(
        'def test_guarded() -> None:\n'
        '    assert 1 == 1\n'
        '    # allow-assertion-reduction: misleading approval\n',
        encoding='utf-8',
    )
    run_git(tmp_path, 'add', '--', 'tests/test_guarded.py')

    result = run_gate(TEST_INTEGRITY, tmp_path)

    assert result.returncode == 1
    assert '[TEST_INTEGRITY]' in result.stderr


def test_test_integrity_rejects_a_nonexistent_replacement_selector(
    tmp_path: Path,
) -> None:
    """A hash match is insufficient when the replacement test is fictional."""
    initialize_git_repository(tmp_path)
    test_file = tmp_path / 'tests' / 'test_guarded.py'
    test_file.parent.mkdir()
    test_file.write_text(
        'def test_guarded() -> None:\n    assert 1 == 1\n    assert 2 == 2\n',
        encoding='utf-8',
    )
    run_git(tmp_path, 'add', '--', 'tests/test_guarded.py')
    run_git(tmp_path, 'commit', '--quiet', '-m', 'baseline')

    test_file.write_text(
        'def test_guarded() -> None:\n    assert 1 == 1\n',
        encoding='utf-8',
    )
    run_git(tmp_path, 'add', '--', 'tests/test_guarded.py')
    digest = staged_test_patch_hash(tmp_path)
    stage_assertion_reduction_policy(
        tmp_path,
        entries=[
            {
                'path': 'tests/test_guarded.py',
                'diff_sha256': digest,
                'replacement_test_ids': [
                    'tests/test_guarded.py::test_missing'
                ],
                'reason': 'The replacement test is intentionally invalid.',
            }
        ],
    )

    result = run_gate(TEST_INTEGRITY, tmp_path)

    assert result.returncode == 1
    assert 'incomplete' in result.stderr


def test_test_integrity_rejects_legacy_reduction_alias(
    tmp_path: Path,
) -> None:
    """Legacy path-to-reason aliases cannot authorize assertion loss."""
    initialize_git_repository(tmp_path)
    test_file = tmp_path / 'tests' / 'test_guarded.py'
    test_file.parent.mkdir()
    test_file.write_text(
        'def test_guarded() -> None:\n    assert 1 == 1\n    assert 2 == 2\n',
        encoding='utf-8',
    )
    run_git(tmp_path, 'add', '--', 'tests/test_guarded.py')
    run_git(tmp_path, 'commit', '--quiet', '-m', 'baseline')
    test_file.write_text(
        'def test_guarded() -> None:\n    assert 1 == 1\n',
        encoding='utf-8',
    )
    run_git(tmp_path, 'add', '--', 'tests/test_guarded.py')
    stage_assertion_reduction_policy(
        tmp_path,
        entries=[],
        alias={'tests/test_guarded.py': 'legacy reason'},
    )

    result = run_gate(TEST_INTEGRITY, tmp_path)

    assert result.returncode == 1
    assert 'allowed_reductions is not' in result.stderr


def test_test_integrity_rejects_incomplete_reduction_authorization(
    tmp_path: Path,
) -> None:
    """Hash, reason, and replacement test IDs are all required fields."""
    initialize_git_repository(tmp_path)
    test_file = tmp_path / 'tests' / 'test_guarded.py'
    test_file.parent.mkdir()
    test_file.write_text(
        'def test_guarded() -> None:\n    assert 1 == 1\n    assert 2 == 2\n',
        encoding='utf-8',
    )
    run_git(tmp_path, 'add', '--', 'tests/test_guarded.py')
    run_git(tmp_path, 'commit', '--quiet', '-m', 'baseline')
    test_file.write_text(
        'def test_guarded() -> None:\n    assert 1 == 1\n',
        encoding='utf-8',
    )
    run_git(tmp_path, 'add', '--', 'tests/test_guarded.py')
    stage_assertion_reduction_policy(
        tmp_path,
        entries=[
            {
                'path': 'tests/test_guarded.py',
                'diff_sha256': '0' * 64,
                'reason': 'Missing replacement test identity.',
            }
        ],
    )

    result = run_gate(TEST_INTEGRITY, tmp_path)

    assert result.returncode == 1
    assert 'incomplete' in result.stderr


def test_test_integrity_rejects_duplicate_and_stale_reduction_entries(
    tmp_path: Path,
) -> None:
    """Each authorization is one-use: duplicate and unrelated entries fail."""
    initialize_git_repository(tmp_path)
    test_file = tmp_path / 'tests' / 'test_guarded.py'
    test_file.parent.mkdir()
    test_file.write_text(
        'def test_guarded() -> None:\n    assert 1 == 1\n    assert 2 == 2\n',
        encoding='utf-8',
    )
    run_git(tmp_path, 'add', '--', 'tests/test_guarded.py')
    run_git(tmp_path, 'commit', '--quiet', '-m', 'baseline')
    test_file.write_text(
        'def test_guarded() -> None:\n    assert 1 == 1\n',
        encoding='utf-8',
    )
    run_git(tmp_path, 'add', '--', 'tests/test_guarded.py')
    digest = staged_test_patch_hash(tmp_path)
    entry = {
        'path': 'tests/test_guarded.py',
        'diff_sha256': digest,
        'replacement_test_ids': ['tests/test_guarded.py::test_guarded'],
        'reason': 'The assertion is covered by the replacement test.',
    }
    stale_entry = {
        'path': 'tests/test_other.py',
        'diff_sha256': '0' * 64,
        'replacement_test_ids': ['tests/test_guarded.py::test_guarded'],
        'reason': 'This entry is not for the current patch.',
    }
    stage_assertion_reduction_policy(
        tmp_path, entries=[entry, entry, stale_entry]
    )

    result = run_gate(TEST_INTEGRITY, tmp_path)

    assert result.returncode == 1
    assert 'duplicate reduction authorization' in result.stderr
    assert 'stale assertion reduction' in result.stderr
