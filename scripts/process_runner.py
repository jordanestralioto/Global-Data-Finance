"""Run the small, allowlisted command set used by repository quality gates."""

from __future__ import annotations

import shlex
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

ProcessResult = subprocess.CompletedProcess[str]

ALLOWED_EXECUTABLES = frozenset({'bash', 'git', 'python', 'sh', 'uv'})
PYTHON_EXECUTABLE = 'python'


class ProcessRunnerError(RuntimeError):
    """Raised when an allowlisted command cannot be executed safely."""


class UnsupportedExecutableError(ProcessRunnerError):
    """Raised when a command requests an executable outside the allowlist."""


class ExecutableResolutionError(ProcessRunnerError):
    """Raised when an allowlisted executable is not available on ``PATH``."""


def resolve_executable(executable: str) -> str:
    """Resolve one permitted executable to an explicit executable path.

    Args:
        executable: Short executable name accepted by the quality-gate policy.

    Returns:
        The absolute interpreter path for Python or the ``PATH`` resolution for
        another allowlisted executable.

    Raises:
        UnsupportedExecutableError: If ``executable`` is not allowlisted.
        ExecutableResolutionError: If an allowlisted executable is unavailable.
    """
    if executable not in ALLOWED_EXECUTABLES:
        allowed = ', '.join(sorted(ALLOWED_EXECUTABLES))
        raise UnsupportedExecutableError(
            f'Executable {executable!r} is not permitted; allowed: {allowed}'
        )
    if executable == PYTHON_EXECUTABLE:
        return sys.executable

    resolved = shutil.which(executable)
    if resolved is None:
        raise ExecutableResolutionError(
            f'Unable to resolve allowlisted executable {executable!r} on PATH'
        )
    return resolved


def run_process(
    command: Sequence[str],
    *,
    cwd: Path,
    check: bool = True,
    capture_output: bool = True,
    env: Mapping[str, str] | None = None,
    encoding_errors: str = 'strict',
) -> ProcessResult:
    """Run an allowlisted command without invoking a shell.

    Args:
        command: Argument sequence whose first item is the executable name.
        cwd: Explicit working directory for the child process.
        check: Raise ``ProcessRunnerError`` when the command exits non-zero.
        capture_output: Capture standard output and standard error when true.
        env: Optional environment variables for the child process.
        encoding_errors: UTF-8 error handler used to decode captured output.

    Returns:
        The completed process result, including its return code and output.

    Raises:
        ProcessRunnerError: If the command is invalid, cannot start, or fails
            while ``check`` is true.
    """
    if not command:
        raise ProcessRunnerError('A command must contain an executable.')
    if any(not isinstance(argument, str) for argument in command):
        raise ProcessRunnerError('Command arguments must all be strings.')

    executable = resolve_executable(command[0])
    resolved_command = [executable, *command[1:]]
    command_text = shlex.join(command)
    try:
        return subprocess.run(
            resolved_command,
            cwd=cwd,
            env=env,
            capture_output=capture_output,
            check=check,
            encoding='utf-8',
            errors=encoding_errors,
            shell=False,
            text=True,
        )
    except subprocess.CalledProcessError as err:
        details = (err.stderr or err.stdout or str(err)).strip()
        raise ProcessRunnerError(
            f'Command {command_text} failed with exit code {err.returncode} '
            f'in {cwd}: {details}'
        ) from err
    except (
        subprocess.SubprocessError,
        OSError,
        UnicodeError,
        ValueError,
    ) as err:
        raise ProcessRunnerError(
            f'Unable to execute {command_text} in {cwd}: {err}'
        ) from err
