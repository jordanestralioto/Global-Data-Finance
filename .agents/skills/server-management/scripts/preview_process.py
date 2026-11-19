"""Keep a stable reference to a preview process while inspecting or stopping it."""

from __future__ import annotations

import contextlib
import ctypes
import errno
import os
import signal
import subprocess
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROC = Path('/proc')
# <linux/pidfd.h>: signal the group that the pidfd's process leads (6.9+).
PIDFD_SIGNAL_PROCESS_GROUP = 4
SendSignal = Callable[..., None]


@dataclass(frozen=True)
class ProcessHandle:
    identity: str
    terminate: Callable[[], None]


def _linux_stat(pid: int) -> list[bytes]:
    """Return the `/proc/<pid>/stat` fields that follow the command name."""
    try:
        stat = (PROC / str(pid) / 'stat').read_bytes()
    except FileNotFoundError as exc:
        raise ProcessLookupError(f'process {pid} is unavailable') from exc
    end = stat.rfind(b')')
    return stat[end + 2 :].split() if end >= 0 else []


def _linux_identity(pid: int) -> tuple[str, int]:
    """Return the start identity of `pid` and its process group."""
    boot_file = PROC / 'sys/kernel/random/boot_id'
    boot_id = boot_file.read_text(encoding='ascii').strip()
    fields = _linux_stat(pid)
    if not boot_id or len(fields) < 20 or fields[0] in {b'Z', b'X', b'x'}:
        raise ProcessLookupError(f'process {pid} is unavailable')
    start_ticks = fields[19].decode('ascii')
    return f'linux:{boot_id}:{start_ticks}', int(fields[2])


def _group_of(pid: int) -> int | None:
    with contextlib.suppress(OSError, IndexError, ValueError):
        return int(_linux_stat(pid)[2])
    return None


def _open_members(pgid: int, pidfd_open: Callable[[int], int]) -> list[int]:
    """Open a pidfd for each other process whose group is `pgid`.

    The group is read again once the pidfd is open. A pidfd signal reaches its
    process only while it keeps the PID it was opened on, so a signaled member
    was in `pgid` at that second read.
    """
    members: list[int] = []
    for entry in PROC.iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        if pid == pgid or _group_of(pid) != pgid:
            continue
        try:
            member = pidfd_open(pid)
        except OSError:
            continue
        if _group_of(pid) == pgid:
            members.append(member)
        else:
            os.close(member)
    return members


def _terminate_members(
    pgid: int,
    leader_fd: int,
    pidfd_open: Callable[[int], int],
    send_signal: SendSignal,
) -> None:
    """Signal the group one pidfd at a time, for kernels before Linux 6.9."""
    members = _open_members(pgid, pidfd_open)
    try:
        # While the leader exists, no other group can take the number `pgid`,
        # so every member read above belonged to this group. If the leader is
        # gone, this raises ProcessLookupError before any process is signaled.
        send_signal(leader_fd, 0)
        for descriptor in (leader_fd, *members):
            with contextlib.suppress(ProcessLookupError):
                send_signal(descriptor, signal.SIGTERM)
    finally:
        for member in members:
            os.close(member)


@contextmanager
def _open_linux(pid: int) -> Iterator[ProcessHandle]:
    pidfd_open = getattr(os, 'pidfd_open', None)
    send_signal = getattr(signal, 'pidfd_send_signal', None)
    if pidfd_open is None or send_signal is None:
        raise OSError('safe preview control requires Linux pidfd support')
    descriptor = pidfd_open(pid)
    try:
        identity, group = _linux_identity(pid)

        def terminate() -> None:
            if group != pid:
                # Not a group leader: only this process belongs to the preview.
                send_signal(descriptor, signal.SIGTERM)
                return
            # The server behind `npm` -> `sh` keeps the port when only the
            # leader is signaled. Every signal goes through a pidfd: once
            # this group is gone, its numeric ID can name an unrelated group.
            try:
                send_signal(
                    descriptor,
                    signal.SIGTERM,
                    None,
                    PIDFD_SIGNAL_PROCESS_GROUP,
                )
            except OSError as exc:
                if exc.errno != errno.EINVAL:
                    raise
                _terminate_members(pid, descriptor, pidfd_open, send_signal)

        yield ProcessHandle(identity, terminate)
    finally:
        os.close(descriptor)


class _FileTime(ctypes.Structure):
    _fields_ = [
        ('low', ctypes.c_uint32),
        ('high', ctypes.c_uint32),
    ]


def _windows_last_error() -> int:
    ctypes_any: Any = ctypes
    return int(ctypes_any.get_last_error())


def _windows_creation_time(kernel32: Any, handle: object) -> str:
    creation = _FileTime()
    exit_time = _FileTime()
    kernel_time = _FileTime()
    user_time = _FileTime()
    get_times = kernel32.GetProcessTimes
    get_times.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(_FileTime),
        ctypes.POINTER(_FileTime),
        ctypes.POINTER(_FileTime),
        ctypes.POINTER(_FileTime),
    ]
    get_times.restype = ctypes.c_int
    if not get_times(
        handle,
        ctypes.byref(creation),
        ctypes.byref(exit_time),
        ctypes.byref(kernel_time),
        ctypes.byref(user_time),
    ):
        raise OSError(_windows_last_error(), 'GetProcessTimes failed')
    return f'windows:{(creation.high << 32) | creation.low}'


@contextmanager
def _open_windows(pid: int) -> Iterator[ProcessHandle]:
    ctypes_any: Any = ctypes
    kernel32 = ctypes_any.WinDLL('kernel32', use_last_error=True)
    open_process = kernel32.OpenProcess
    open_process.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    open_process.restype = ctypes.c_void_p
    handle = open_process(0x00101000, 0, pid)
    if not handle:
        error = _windows_last_error()
        if error in (87, 1168):
            raise ProcessLookupError(f'process {pid} is unavailable')
        raise OSError(error, 'OpenProcess failed')
    try:
        wait = kernel32.WaitForSingleObject
        wait.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        wait.restype = ctypes.c_uint32
        state = wait(handle, 0)
        if state == 0:
            raise ProcessLookupError(f'process {pid} is not running')
        if state != 258:
            raise OSError(_windows_last_error(), 'WaitForSingleObject failed')
        identity = _windows_creation_time(kernel32, handle)

        def terminate() -> None:
            # The open handle prevents this PID from being reused by taskkill.
            result = subprocess.run(
                ['taskkill', '/F', '/T', '/PID', str(pid)],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode:
                raise OSError(f'taskkill failed: {result.stderr.strip()}')

        yield ProcessHandle(identity, terminate)
    finally:
        close = kernel32.CloseHandle
        close.argtypes = [ctypes.c_void_p]
        close.restype = ctypes.c_int
        close(handle)


@contextmanager
def open_process(pid: int) -> Iterator[ProcessHandle]:
    if pid <= 1:
        raise ProcessLookupError(f'invalid process ID: {pid}')
    if sys.platform == 'linux':
        with _open_linux(pid) as process:
            yield process
    elif sys.platform == 'win32':
        with _open_windows(pid) as process:
            yield process
    else:
        raise OSError('safe preview control is unavailable on this platform')


def capture_identity(pid: int) -> str:
    with open_process(pid) as process:
        return process.identity
