#!/usr/bin/env python3
"""Manage a local preview server without signaling an unrelated process.

Manages (start/stop/status) the local development server for previewing the application.

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
import sys
from pathlib import Path

from preview_process import capture_identity, open_process

AGENT_DIR = Path('.agents')
PID_FILE = AGENT_DIR / 'preview.pid'
META_FILE = AGENT_DIR / 'preview.json'
LOG_FILE = AGENT_DIR / 'preview.log'
INFO_ICON = '\N{INFORMATION SOURCE}\N{VARIATION SELECTOR-16}'


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
    except (OSError, json.JSONDecodeError):
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
        with contextlib.suppress(OSError, json.JSONDecodeError):
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


def start_server(port: int = 3000) -> None:
    try:
        capture_identity(os.getpid())
    except OSError as exc:
        print(f'❌ Safe preview control is unavailable: {exc}')
        raise SystemExit(1) from exc

    saved_pid, saved_identity, _ = _read_saved_preview()
    if saved_pid is not None and saved_identity:
        try:
            if is_preview_process(saved_pid, saved_identity):
                print(f'⚠️  Preview already running (PID: {saved_pid})')
                return
        except OSError as exc:
            print(f'❌ Cannot inspect existing preview: {exc}')
            raise SystemExit(1) from exc
    if PID_FILE.exists() or META_FILE.exists():
        cleanup_state()

    root = get_project_root()
    cmd = get_start_command(root)

    if not cmd:
        print("❌ No 'dev' or 'start' script found in package.json")
        sys.exit(1)

    AGENT_DIR.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env['PORT'] = str(port)

    print(f'🚀 Starting preview on port {port}...')

    with open(LOG_FILE, 'w', encoding='utf-8') as log:
        process = subprocess.Popen(
            cmd,
            cwd=str(root),
            stdout=log,
            stderr=log,
            env=env,
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
        if process.poll() is None:
            process.terminate()
        cleanup_state()
        print(f'❌ Could not track preview process: {exc}')
        raise SystemExit(1) from exc

    print(f'✅ Preview started! (PID: {process.pid})')
    print(f'   Logs: {LOG_FILE}')
    print(f'   URL: http://localhost:{port}')


def stop_server() -> None:
    if not PID_FILE.exists() and not META_FILE.exists():
        print(f'{INFO_ICON}  No preview server found.')
        return

    pid, identity, _ = _read_saved_preview()

    if pid is None or pid <= 1 or not identity:
        print(f'{INFO_ICON}  No verifiable preview process found.')
        cleanup_state()
        return

    try:
        with open_process(pid) as process:
            if process.identity != identity:
                print(
                    f'⚠️  PID {pid} belongs to another process. '
                    'Refusing to terminate it.'
                )
                cleanup_state()
                return
            process.terminate()
    except ProcessLookupError:
        print(f'{INFO_ICON}  Process was not running.')
        cleanup_state()
        return
    except OSError as exc:
        print(f'❌ Could not safely stop preview: {exc}')
        return

    cleanup_state()
    print(f'🛑 Preview stopped (PID: {pid})')


def status_server() -> None:
    pid, identity, port = _read_saved_preview()
    running = False

    if pid is not None and identity:
        try:
            running = is_preview_process(pid, identity)
        except OSError as exc:
            print(f'❌ Cannot inspect preview status: {exc}')
            return
        if not running:
            cleanup_state()
            pid = None
    elif PID_FILE.exists() or META_FILE.exists():
        cleanup_state()
        pid = None

    url = f'http://localhost:{port}' if running else 'Unknown'

    print('\n=== Preview Status ===')
    if running:
        print('✅ Status: Running')
        print(f'🔢 PID: {pid}')
        print(f'🌐 URL: {url}')
        print(f'📝 Logs: {LOG_FILE}')
    else:
        print('⚪ Status: Stopped')
    print('===================\n')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['start', 'stop', 'status'])
    parser.add_argument('port', nargs='?', default='3000')

    args = parser.parse_args()

    if args.action == 'start':
        start_server(int(args.port))
    elif args.action == 'stop':
        stop_server()
    elif args.action == 'status':
        status_server()


if __name__ == '__main__':
    main()
