"""Keep a stable reference to a preview process while inspecting or stopping it."""

from __future__ import annotations

import ctypes
import os
import signal
import subprocess
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ProcessHandle:
    identity: str
    terminate: Callable[[], None]


def _linux_identity(pid: int) -> str:
    boot_id = (
        Path('/proc/sys/kernel/random/boot_id')
        .read_text(encoding='ascii')
        .strip()
    )
    try:
        stat = Path(f'/proc/{pid}/stat').read_bytes()
    except FileNotFoundError as exc:
        raise ProcessLookupError(f'process {pid} is unavailable') from exc
    end = stat.rfind(b')')
    fields = stat[end + 2 :].split() if end >= 0 else []
    if not boot_id or len(fields) < 20 or fields[0] in {b'Z', b'X', b'x'}:
        raise ProcessLookupError(f'process {pid} is unavailable')
    start_ticks = fields[19].decode('ascii')
    return f'linux:{boot_id}:{start_ticks}'


@contextmanager
def _open_linux(pid: int) -> Iterator[ProcessHandle]:
    pidfd_open = getattr(os, 'pidfd_open', None)
    send_signal = getattr(signal, 'pidfd_send_signal', None)
    if pidfd_open is None or send_signal is None:
        raise OSError('safe preview control requires Linux pidfd support')
    descriptor = pidfd_open(pid)
    try:
        identity = _linux_identity(pid)
        yield ProcessHandle(
            identity,
            lambda: send_signal(descriptor, signal.SIGTERM),
        )
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
