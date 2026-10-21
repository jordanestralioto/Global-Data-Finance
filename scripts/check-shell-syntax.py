#!/usr/bin/env python3
"""Validate staged or ranged Bash and POSIX shell scripts without mutation."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

if __package__ in {None, ''}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.git_changes import (
    GitInspectionError,
    get_changed_paths,
    read_git_file,
)
from scripts.process_runner import ProcessRunnerError, run_process

SHELL_SUFFIXES = frozenset({'.bash', '.sh'})
SHELL_INTERPRETERS = frozenset({'bash', 'sh', 'dash'})


class ShellInspectionError(RuntimeError):
    """Raised when a shell script cannot be inspected safely."""


def shell_command(path: str, content: str) -> tuple[str, ...] | None:
    """Return the fixed shell syntax command when the path is applicable."""
    suffix = Path(path).suffix.lower()
    first_line = content.splitlines()[0].strip() if content else ''
    shebang_parts = (
        first_line[2:].split() if first_line.startswith('#!') else []
    )
    interpreter_parts = [
        Path(part).name
        for part in shebang_parts
        if Path(part).name in SHELL_INTERPRETERS
    ]
    interpreter = interpreter_parts[-1] if interpreter_parts else ''

    if suffix not in SHELL_SUFFIXES and not interpreter:
        return None
    if interpreter == 'bash' or suffix == '.bash':
        return ('bash', '-n')
    return ('sh', '-n')


def staged_shell_files(
    revision_range: str | None = None,
) -> list[tuple[str, str, tuple[str, ...]]]:
    """Return changed shell files with the exact Git content to validate."""
    files: list[tuple[str, str, tuple[str, ...]]] = []
    for path in get_changed_paths(revision_range=revision_range):
        content = read_git_file(
            path,
            revision_range=revision_range,
            encoding_errors='surrogateescape',
        )
        if content is None:
            raise ShellInspectionError(
                f'Changed shell candidate is absent from inspected Git state: '
                f'{path}'
            )
        command = shell_command(path, content)
        if command is not None:
            files.append((path, content, command))
    return files


def validate_shell_file(
    path: str,
    content: str,
    command: tuple[str, ...],
) -> str | None:
    """Return a diagnostic when the chosen shell reports a syntax error."""
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='w',
            encoding='utf-8',
            errors='surrogateescape',
            suffix=Path(path).suffix or '.sh',
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            temporary_file.write(content)
        result = run_process(
            [*command, str(temporary_path)],
            check=False,
            cwd=temporary_path.parent,
            encoding_errors='surrogateescape',
        )
    except (OSError, UnicodeError, ProcessRunnerError) as err:
        command_text = ' '.join(command)
        raise ShellInspectionError(
            f'Unable to prepare or execute {command_text} for {path}: {err}'
        ) from err
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except (OSError, UnicodeError, ProcessRunnerError) as err:
                raise ShellInspectionError(
                    f'Unable to remove temporary shell validation file: {err}'
                ) from err

    if result.returncode == 0:
        return None

    details = (result.stderr or result.stdout).strip()
    if temporary_path is not None:
        details = details.replace(str(temporary_path), path)
    return f'{path}: [SYNTAX] {" ".join(command)} failed: {details}'


def main() -> int:
    """Run the staged or ranged shell syntax gate."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--range',
        dest='revision_range',
        help=(
            'Inspect an explicit Git A..B or A...B range instead of the index.'
        ),
    )
    args = parser.parse_args()

    try:
        files = staged_shell_files(args.revision_range)
        if not files:
            scope = (
                'revision range'
                if args.revision_range
                else 'staged shell files'
            )
            print(f'SKIP [SHELL_SYNTAX]: No {scope} to inspect.')
            return 0

        errors = [
            error
            for path, content, command in files
            if (error := validate_shell_file(path, content, command))
            is not None
        ]
    except (GitInspectionError, ShellInspectionError) as err:
        print(f'ERROR [SHELL_SYNTAX]: {err}', file=sys.stderr)
        return 2

    if errors:
        print(
            'FAIL [SHELL_SYNTAX]: Invalid shell syntax:',
            file=sys.stderr,
        )
        for error in errors:
            print(f'  • {error}', file=sys.stderr)
        print(
            '\nResolution: Fix the shell syntax and rerun the matching '
            'shell -n command.',
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
