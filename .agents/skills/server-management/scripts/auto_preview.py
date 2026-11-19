#!/usr/bin/env python3
"""Manage a local preview server without signaling an unrelated process.

Manages (start/stop/status) the local development server for previewing the application.
Each action prints one JSON result and exits 1 when its status is `error`.

Usage:
    python .agents/skills/server-management/scripts/auto_preview.py start [port]
    python .agents/skills/server-management/scripts/auto_preview.py stop
    python .agents/skills/server-management/scripts/auto_preview.py status
"""

import argparse
import contextlib
import json
import os
import subprocess
from pathlib import Path

from preview_process import capture_identity, open_process

AGENT_DIR = Path('.agents')
PID_FILE = AGENT_DIR / 'preview.pid'
META_FILE = AGENT_DIR / 'preview.json'
LOG_FILE = AGENT_DIR / 'preview.log'


def get_project_root() -> Path:
    return Path().resolve()


def is_preview_process(pid: int, expected_identity: str | None) -> bool:
    if not expected_identity:
        return False
    try:
        with open_process(pid) as process:
            return process.identity == expected_identity
    except ProcessLookupError:
        return False


def cleanup_state() -> None:
    for path in (PID_FILE, META_FILE):
        with contextlib.suppress(OSError):
            if path.exists():
                path.unlink()


def get_start_command(root: Path) -> list[str] | None:
    pkg_file = root / 'package.json'
    if not pkg_file.exists():
        return None

    try:
        with open(pkg_file, encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):  # ValueError: invalid JSON or UTF-8.
        return None

    if not isinstance(data, dict):
        return None

    scripts = data.get('scripts', {})
    if not isinstance(scripts, dict):
        return None

    if 'dev' in scripts:
        return ['npm', 'run', 'dev']
    if 'start' in scripts:
        return ['npm', 'start']
    return None


def _read_saved_preview() -> tuple[int | None, str | None, int]:
    pid: int | None = None
    port = 3000
    identity: str | None = None

    if META_FILE.exists():
        # ValueError covers both invalid JSON and bytes that are not UTF-8.
        with contextlib.suppress(OSError, ValueError):
            meta = json.loads(META_FILE.read_text(encoding='utf-8'))
            if isinstance(meta, dict):
                if type(meta.get('pid')) is int:
                    pid = meta['pid']
                if type(meta.get('port')) is int:
                    port = meta['port']
                if isinstance(meta.get('processIdentity'), str):
                    identity = meta['processIdentity']

    if pid is None and PID_FILE.exists():
        with contextlib.suppress(ValueError, OSError):
            pid = int(PID_FILE.read_text().strip())

    return pid, identity, port


def _report(action: str, status: str, **details: object) -> int:
    """Print one JSON result for the agent and return the exit code."""
    print(json.dumps({'action': action, 'status': status, **details}))
    return 1 if status == 'error' else 0


def start_server(port: int = 3000) -> int:
    try:
        capture_identity(os.getpid())
    except OSError as exc:
        return _report(
            'start',
            'error',
            diagnostic=f'Safe preview control is unavailable: {exc}',
        )

    saved_pid, saved_identity, _ = _read_saved_preview()
    if saved_pid is not None and saved_identity:
        try:
            if is_preview_process(saved_pid, saved_identity):
                return _report('start', 'already_running', pid=saved_pid)
        except OSError as exc:
            return _report(
                'start',
                'error',
                pid=saved_pid,
                diagnostic=f'Cannot inspect existing preview: {exc}',
            )
    if PID_FILE.exists() or META_FILE.exists():
        cleanup_state()

    root = get_project_root()
    cmd = get_start_command(root)

    if not cmd:
        return _report(
            'start',
            'error',
            diagnostic="No 'dev' or 'start' script found in package.json",
        )

    env = os.environ.copy()
    env['PORT'] = str(port)

    try:
        AGENT_DIR.mkdir(parents=True, exist_ok=True)
        # A separate session makes the preview a process-group leader, so
        # stop can reach the server spawned behind npm. Windows ignores it.
        with open(LOG_FILE, 'w', encoding='utf-8') as log:
            process = subprocess.Popen(
                cmd,
                cwd=str(root),
                stdout=log,
                stderr=log,
                env=env,
                start_new_session=True,
            )
    except OSError as exc:
        return _report(
            'start', 'error', diagnostic=f'Could not launch preview: {exc}'
        )

    try:
        identity = capture_identity(process.pid)
        metadata = {
            'pid': process.pid,
            'processIdentity': identity,
            'port': port,
        }
        PID_FILE.write_text(f'{process.pid}\n')
        META_FILE.write_text(json.dumps(metadata, indent=2) + '\n')
    except OSError as exc:
        diagnostic = f'Could not track preview process: {exc}'
        if process.poll() is None:
            try:
                process.terminate()
            except OSError as stop_exc:
                diagnostic += (
                    f'; terminating PID {process.pid} also failed, so it '
                    f'may still be running: {stop_exc}'
                )
        cleanup_state()
        return _report(
            'start', 'error', pid=process.pid, diagnostic=diagnostic
        )

    return _report(
        'start',
        'started',
        pid=process.pid,
        port=port,
        requested_url=f'http://localhost:{port}',
        log=str(LOG_FILE),
    )


def stop_server() -> int:
    if not PID_FILE.exists() and not META_FILE.exists():
        return _report(
            'stop', 'not_running', diagnostic='No preview state was found.'
        )

    pid, identity, _ = _read_saved_preview()

    if pid is None or pid <= 1 or not identity:
        cleanup_state()
        return _report(
            'stop',
            'not_running',
            diagnostic=(
                'Saved state had no verifiable process; it was cleared '
                'without signaling any process.'
            ),
        )

    try:
        with open_process(pid) as process:
            if process.identity != identity:
                cleanup_state()
                return _report(
                    'stop',
                    'not_running',
                    pid=pid,
                    diagnostic=(
                        f'PID {pid} belongs to another process; the state '
                        'was cleared without signaling it.'
                    ),
                )
            process.terminate()
    except ProcessLookupError:
        cleanup_state()
        return _report(
            'stop',
            'not_running',
            pid=pid,
            diagnostic='Process was not running.',
        )
    except OSError as exc:
        return _report(
            'stop',
            'error',
            pid=pid,
            diagnostic=f'Could not safely stop preview: {exc}',
        )

    cleanup_state()
    return _report('stop', 'stopped', pid=pid)


def status_server() -> int:
    pid, identity, port = _read_saved_preview()
    running = False

    if pid is not None and identity:
        try:
            running = is_preview_process(pid, identity)
        except OSError as exc:
            return _report(
                'status',
                'error',
                pid=pid,
                diagnostic=f'Cannot inspect preview status: {exc}',
            )
        if not running:
            cleanup_state()
    elif PID_FILE.exists() or META_FILE.exists():
        cleanup_state()

    if not running:
        return _report('status', 'stopped')
    return _report(
        'status',
        'running',
        pid=pid,
        requested_url=f'http://localhost:{port}',
        log=str(LOG_FILE),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description='Start, stop or inspect the local preview server.'
    )
    parser.add_argument('action', choices=['start', 'stop', 'status'])
    parser.add_argument('port', nargs='?', type=int, default=3000)
    args = parser.parse_args(argv)

    if args.action == 'start':
        return start_server(args.port)
    if args.action == 'stop':
        return stop_server()
    return status_server()


if __name__ == '__main__':
    raise SystemExit(main())
