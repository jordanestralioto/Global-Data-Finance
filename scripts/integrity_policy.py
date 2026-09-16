"""Read and validate one-use test-integrity policy entries from Git state."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path

from scripts.git_changes import read_git_file
from scripts.patch_hashes import file_patch_hashes
from scripts.test_selector import replacement_test_exists

_POLICY_NAMES = ('.test-deletions.json', '.test-integrity-policy.json')
_ASSERTION_POLICY = '.test-integrity-policy.json'
_DELETED_FILE_RE = re.compile(r'(?m)^--- a/(.+)\n\+\+\+ /dev/null(?:\n|$)')
_SHA256_RE = re.compile(r'^[0-9a-f]{64}$')


class _DuplicatePolicyKey(ValueError):
    """Signal duplicate JSON keys instead of silently accepting the last."""


def _object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Build a JSON object while rejecting duplicate keys."""
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicatePolicyKey(f'duplicate key {key!r}')
        result[key] = value
    return result


def _read_policy_document(
    policy_name: str,
    repo_root: Path | None,
    revision_range: str | None,
) -> tuple[dict[str, object], list[str]]:
    """Read one policy from the exact Git state selected by the checker."""
    content = read_git_file(
        policy_name, repo_root=repo_root, revision_range=revision_range
    )
    if content is None:
        return {}, []
    try:
        parsed = json.loads(content, object_pairs_hook=_object_pairs)
    except (OSError, json.JSONDecodeError, _DuplicatePolicyKey) as error:
        return {}, [
            f'{policy_name}: [TEST_POLICY] invalid JSON policy: {error}'
        ]
    if not isinstance(parsed, dict):
        return {}, [
            f'{policy_name}: [TEST_POLICY] policy root must be an object'
        ]
    return parsed, []


def read_policy_entries(
    policy_name: str,
    repo_root: Path | None = None,
    revision_range: str | None = None,
    section: str = 'allowed_deletions',
) -> dict[str, object]:
    """Read one policy section from the inspected Git state.

    Deletion policies use a path-to-reason object; assertion-reduction policies
    use a list of structured entries returned as a path-to-entry mapping.
    """
    data, _ = _read_policy_document(policy_name, repo_root, revision_range)
    allowed = data.get(section)
    if section == 'allowed_assertion_reductions':
        if not isinstance(allowed, list):
            return {}
        entries: dict[str, object] = {}
        for entry in allowed:
            if isinstance(entry, dict) and isinstance(entry.get('path'), str):
                entries[entry['path']] = entry
        return entries
    if not isinstance(allowed, dict):
        return {}
    return {str(path): reason for path, reason in allowed.items()}


def _has_reason(value: object) -> bool:
    """Return whether a deletion authorization has a concrete reason."""
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        reason = value.get('reason')
        return isinstance(reason, str) and bool(reason.strip())
    return False


def _assertion_entry_is_complete(
    entry: object,
    file_path: str,
    expected_hash: str | None,
    is_test_file: Callable[[str], bool],
    repo_root: Path | None = None,
    revision_range: str | None = None,
) -> bool:
    """Check the minimum fields required for one reduction authorization."""
    if not isinstance(entry, dict):
        return False
    entry_path = entry.get('path')
    if (
        entry_path != file_path
        or not isinstance(entry_path, str)
        or not _is_relative_test_path(entry_path, is_test_file)
    ):
        return False
    digest = entry.get('diff_sha256')
    if (
        not isinstance(digest, str)
        or _SHA256_RE.fullmatch(digest) is None
        or digest != expected_hash
    ):
        return False
    reason = entry.get('reason')
    if not isinstance(reason, str) or not reason.strip():
        return False
    replacement_ids = entry.get('replacement_test_ids')
    if not isinstance(replacement_ids, list) or not replacement_ids:
        return False
    normalized_ids: set[str] = set()
    for replacement_id in replacement_ids:
        if not isinstance(replacement_id, str):
            return False
        _, separator, selector = replacement_id.partition('::')
        if (
            not separator
            or not selector.strip()
            or replacement_id in normalized_ids
            or not replacement_test_exists(
                replacement_id,
                is_test_file,
                repo_root=repo_root,
                revision_range=revision_range,
            )
        ):
            return False
        normalized_ids.add(replacement_id)
    return True


def _is_relative_test_path(
    file_path: str, is_test_file: Callable[[str], bool]
) -> bool:
    """Validate a policy path as a relative repository test path."""
    path = Path(file_path)
    return (
        not path.is_absolute()
        and '..' not in path.parts
        and is_test_file(file_path)
    )


def is_test_deletion_approved(
    file_path: str,
    repo_root: Path | None = None,
    revision_range: str | None = None,
) -> bool:
    """Check whether a test deletion has a reason in inspected Git policy."""
    for policy_name in _POLICY_NAMES:
        reason = read_policy_entries(
            policy_name, repo_root=repo_root, revision_range=revision_range
        ).get(file_path)
        if _has_reason(reason):
            return True
    return False


def is_assertion_reduction_approved(
    file_path: str,
    diff_sha256: str | None,
    is_test_file: Callable[[str], bool],
    repo_root: Path | None = None,
    revision_range: str | None = None,
) -> bool:
    """Check one exact, structured, hash-bound reduction authorization."""
    data, _ = _read_policy_document(
        _ASSERTION_POLICY, repo_root, revision_range
    )
    entries = data.get('allowed_assertion_reductions')
    if not isinstance(entries, list) or diff_sha256 is None:
        return False
    matches = [
        entry
        for entry in entries
        if isinstance(entry, dict) and entry.get('path') == file_path
    ]
    return len(matches) == 1 and _assertion_entry_is_complete(
        matches[0],
        file_path,
        diff_sha256,
        is_test_file,
        repo_root=repo_root,
        revision_range=revision_range,
    )


def stale_deletion_policy_errors(
    diff_text: str,
    is_test_file: Callable[[str], bool],
    repo_root: Path | None = None,
    revision_range: str | None = None,
) -> list[str]:
    """Return diagnostics for deletion policy entries absent from the diff."""
    deleted_paths = {
        match.group(1)
        for match in _DELETED_FILE_RE.finditer(diff_text)
        if is_test_file(match.group(1))
    }
    errors: list[str] = []
    for policy_name in _POLICY_NAMES:
        data, parse_errors = _read_policy_document(
            policy_name, repo_root, revision_range
        )
        errors.extend(parse_errors)
        allowed = data.get('allowed_deletions')
        if allowed is None:
            continue
        if not isinstance(allowed, dict):
            errors.append(
                f'{policy_name}: [TEST_POLICY] allowed_deletions must be '
                'an object'
            )
            continue
        for file_path, reason in allowed.items():
            if not isinstance(file_path, str) or not is_test_file(file_path):
                errors.append(
                    f'{policy_name}: [TEST_POLICY] invalid deletion path '
                    f'{file_path!r}'
                )
            elif not _has_reason(reason):
                errors.append(
                    f'{policy_name}: [TEST_POLICY] deletion authorization '
                    f'for {file_path!r} has no reason'
                )
            elif file_path not in deleted_paths:
                errors.append(
                    f'{policy_name}: [TEST_POLICY] stale deletion '
                    f'authorization for {file_path!r}; remove it or delete '
                    'that test in the inspected Git diff.'
                )
    return errors


def _assertion_policy_entry_errors(
    entry: object,
    index: int,
    hashes: dict[str, str],
    reduced_paths: set[str],
    seen_paths: set[str],
    is_test_file: Callable[[str], bool],
    repo_root: Path | None,
    revision_range: str | None,
) -> list[str]:
    """Validate one structured assertion-reduction policy entry."""
    prefix = f'{_ASSERTION_POLICY}: [TEST_POLICY] entry {index}'
    if not isinstance(entry, dict):
        return [f'{prefix} must be an object']

    file_path = entry.get('path')
    if not isinstance(file_path, str) or not _is_relative_test_path(
        file_path, is_test_file
    ):
        return [f'{prefix} has an invalid test path']

    errors: list[str] = []
    if file_path in seen_paths:
        errors.append(
            f'{_ASSERTION_POLICY}: [TEST_POLICY] duplicate reduction '
            f'authorization for {file_path!r}'
        )
    seen_paths.add(file_path)

    if not _assertion_entry_is_complete(
        entry,
        file_path,
        hashes.get(file_path),
        is_test_file,
        repo_root=repo_root,
        revision_range=revision_range,
    ):
        errors.append(
            f'{prefix} for {file_path!r} is incomplete or its '
            'diff_sha256 does not match the inspected patch'
        )
    if file_path not in reduced_paths:
        errors.append(
            f'{_ASSERTION_POLICY}: [TEST_POLICY] stale assertion '
            f'reduction authorization for {file_path!r}; the current '
            'diff does not reduce assertions in that file'
        )
    return errors


def assertion_reduction_policy_errors(
    diff_text: str,
    reduced_paths: set[str],
    is_test_file: Callable[[str], bool],
    repo_root: Path | None = None,
    revision_range: str | None = None,
) -> list[str]:
    """Validate one-use assertion authorizations against the current diff."""
    data, parse_errors = _read_policy_document(
        _ASSERTION_POLICY, repo_root, revision_range
    )
    errors = list(parse_errors)
    if 'allowed_reductions' in data:
        errors.append(
            f'{_ASSERTION_POLICY}: [TEST_POLICY] allowed_reductions is not '
            'a valid assertion-reduction authorization; use '
            'allowed_assertion_reductions with a hash-bound entry'
        )

    entries = data.get('allowed_assertion_reductions')
    if entries is None:
        return errors
    if not isinstance(entries, list):
        errors.append(
            f'{_ASSERTION_POLICY}: [TEST_POLICY] '
            'allowed_assertion_reductions must be an array of objects'
        )
        return errors

    hashes = file_patch_hashes(diff_text)
    seen_paths: set[str] = set()
    for index, entry in enumerate(entries):
        errors.extend(
            _assertion_policy_entry_errors(
                entry,
                index,
                hashes,
                reduced_paths,
                seen_paths,
                is_test_file,
                repo_root,
                revision_range,
            )
        )

    missing = reduced_paths - seen_paths
    for file_path in sorted(missing):
        errors.append(
            f'{file_path}: [TEST_POLICY] assertion reduction requires a '
            'hash-bound allowed_assertion_reductions entry'
        )
    return errors


def test_integrity_policy_errors(
    diff_text: str,
    reduced_paths: set[str],
    is_test_file: Callable[[str], bool],
    repo_root: Path | None = None,
    revision_range: str | None = None,
) -> list[str]:
    """Validate deletion and assertion policies for one Git inspection."""
    errors = stale_deletion_policy_errors(
        diff_text,
        is_test_file,
        repo_root=repo_root,
        revision_range=revision_range,
    )
    errors.extend(
        assertion_reduction_policy_errors(
            diff_text,
            reduced_paths,
            is_test_file,
            repo_root=repo_root,
            revision_range=revision_range,
        )
    )
    return errors
