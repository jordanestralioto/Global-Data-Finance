#!/usr/bin/env python3
"""Measure how often a skill triggers for labeled queries via `claude -p`.

Each query runs in a fresh headless Claude Code session restricted to the
`Skill` and `Read` tools. Only an installed personal or project skill is
measured, and only when every installed copy has the same frontmatter. A run
counts as triggered when the main conversation calls the Skill tool with the
exact skill name or reads the SKILL.md that the bare name runs, through any
path that resolves to that file. A read of another copy, such as a nested
`apps/web:deploy`, is another command's. A run without a trigger is valid only
when the client reports a result without error and exits with code 0. A query
with any errored run is an error, not a rate over the remaining runs. The
report records the path and frontmatter hash of the measured copy. Exit codes:
0 when every query passes, 1 when a query fails and 2 when a run errors or the
input is invalid.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DESCRIPTION = 'Measure skill trigger rates for labeled queries.'
CLIENT = 'claude-code'
TAIL_LINES = 5


@dataclass(frozen=True)
class RunOutcome:
    """Result of one headless run; `triggered` is None when it errored."""

    triggered: bool | None
    model: str | None = None
    error: str | None = None


RunOnce = Callable[[str], RunOutcome]


def _walk(node: object) -> Iterator[dict[str, Any]]:
    stack = [node]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            yield current
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)


def is_skill_call(block: dict[str, Any], skill: str, target: str) -> bool:
    """Match the exact name or a read of `target`, the measured real path."""
    if block.get('type') != 'tool_use':
        return False
    payload = block.get('input')
    if not isinstance(payload, dict):
        return False
    if block.get('name') == 'Skill':
        # `apps/web:deploy` or `plugin:deploy` is another skill than `deploy`.
        return payload.get('skill') == skill
    if block.get('name') == 'Read':
        path = payload.get('file_path')
        return isinstance(path, str) and os.path.realpath(path) == target
    return False


def scan_event(
    event: object, skill: str, target: str
) -> tuple[bool, str | None]:
    """Return whether the event triggers the skill and any reported model."""
    if not isinstance(event, dict):
        return False, None
    if event.get('type') == 'system' and event.get('subtype') == 'init':
        model = event.get('model')
        return False, model if isinstance(model, str) else None
    if event.get('type') != 'assistant' or event.get('parent_tool_use_id'):
        return False, None
    message = event.get('message')
    hits = (is_skill_call(block, skill, target) for block in _walk(message))
    return any(hits), None


def build_command(
    claude_bin: str, tools: str, budget: float, model: str | None
) -> list[str]:
    command = [
        claude_bin,
        '-p',
        '--output-format',
        'stream-json',
        '--verbose',
        '--no-session-persistence',
        '--permission-prompts',
        'none',
        '--tools',
        tools,
        '--max-budget-usd',
        f'{budget:g}',
    ]
    if model:
        command += ['--model', model]
    return command


def _send(proc: subprocess.Popen[str], query: str) -> None:
    if proc.stdin is None:
        return
    try:
        proc.stdin.write(query)
        proc.stdin.close()
    except BrokenPipeError:
        # The client exited before reading the prompt; its output says why.
        return


def _stop(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is None:
        proc.terminate()
    if proc.stdout is not None:
        proc.stdout.close()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def run_claude_once(
    command: list[str],
    query: str,
    skill: str,
    target: str,
    timeout: float,
    cwd: Path,
) -> RunOutcome:
    """Run one session, stopping as soon as the trigger is observed."""
    try:
        proc = subprocess.Popen(
            command,
            cwd=cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8',
        )
    except OSError as exc:
        return RunOutcome(None, error=f'cannot start client: {exc}')
    expired = threading.Event()

    def _expire() -> None:
        expired.set()
        proc.kill()

    timer = threading.Timer(timeout, _expire)
    timer.start()
    model: str | None = None
    result: dict[str, Any] | None = None
    tail: list[str] = []
    try:
        _send(proc, query)
        for line in proc.stdout or ():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                tail = [*tail, line.strip()][-TAIL_LINES:]
                continue
            hit, seen = scan_event(event, skill, target)
            model = model or seen
            if hit:
                return RunOutcome(True, model)
            if isinstance(event, dict) and event.get('type') == 'result':
                result = event
        # Without a trigger, the run counts only once the client exits cleanly.
        proc.wait()
    finally:
        timer.cancel()
        _stop(proc)
    if expired.is_set():
        return RunOutcome(None, model, f'timed out after {timeout:g}s')
    if result is None or result.get('is_error') or proc.returncode != 0:
        detail = ' | '.join([f'exit code {proc.returncode}', *tail])
        return RunOutcome(None, model, f'run did not complete: {detail}')
    return RunOutcome(False, model)


def measure(
    item: dict[str, Any], runs: int, threshold: float, run_once: RunOnce
) -> dict[str, Any]:
    outcomes = [run_once(item['query']) for _ in range(runs)]
    valid = [outcome for outcome in outcomes if outcome.triggered is not None]
    errors = [outcome.error for outcome in outcomes if outcome.error]
    record: dict[str, Any] = {
        'query': item['query'],
        'should_trigger': item['should_trigger'],
        'runs': runs,
        'valid_runs': len(valid),
        'triggers': sum(bool(outcome.triggered) for outcome in valid),
        'errors': errors,
        'models': sorted({o.model for o in outcomes if o.model}),
    }
    if len(valid) < runs:
        # A rate over the surviving runs would hide the failed sessions.
        return {**record, 'trigger_rate': None, 'status': 'error'}
    rate = record['triggers'] / len(valid)
    passed = rate > threshold if item['should_trigger'] else rate < threshold
    status = 'pass' if passed else 'fail'
    return {**record, 'trigger_rate': round(rate, 4), 'status': status}


def load_queries(path: Path, split: str | None) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(data, list) or not all(
        isinstance(item, dict)
        and isinstance(item.get('query'), str)
        and isinstance(item.get('should_trigger'), bool)
        for item in data
    ):
        raise ValueError(
            'expected a list of {query, should_trigger}; run validate_evals.py'
        )
    return [
        item for item in data if split is None or item.get('split') == split
    ]


def frontmatter(skill_md: Path) -> str:
    text = skill_md.read_text(encoding='utf-8')
    parts = text.split('---', 2)
    return parts[1] if text.startswith('---') and len(parts) == 3 else text


def installed_copies(skill: str, cwd: Path) -> list[Path]:
    """List the copies of `skill` that Claude Code loads when started in `cwd`.

    The personal copy comes first, then the project copies from the repository
    root down to `cwd`. The first one keeps the bare name.
    """
    personal = os.environ.get('CLAUDE_CONFIG_DIR') or Path.home() / '.claude'
    chain = [cwd.resolve(), *cwd.resolve().parents]
    top = next((i for i, d in enumerate(chain) if (d / '.git').exists()), 0)
    roots = [Path(personal), *(d / '.claude' for d in chain[top::-1])]
    candidates = (root / 'skills' / skill / 'SKILL.md' for root in roots)
    return [path for path in candidates if path.is_file()]


def resolve_skill_md(skill: str, cwd: Path, given: Path | None) -> Path:
    """Return the copy that the bare name runs, refusing an unclear identity.

    `given`, when set, must match it, such as a source file that should
    already be projected.
    """
    copies = installed_copies(skill, cwd)
    if not copies:
        raise ValueError(
            f'{skill} is not installed in the personal skills directory or in'
            f' a .claude/skills directory from {cwd} up to the repository root'
        )
    blocks = {frontmatter(path) for path in copies}
    if len(blocks) > 1:
        # Which copy Claude invokes then depends on precedence and context.
        listed = ', '.join(str(path) for path in copies)
        raise ValueError(f'installed copies of {skill} differ: {listed}')
    if given is not None and frontmatter(given) not in blocks:
        raise ValueError(
            f'{given} differs from the copy the client loads: {copies[0]}'
        )
    name = rf'^name:\s*[\'"]?{re.escape(skill)}[\'"]?\s*$'
    if not re.search(name, frontmatter(copies[0]), re.MULTILINE):
        raise ValueError(f'{copies[0]} does not declare name: {skill}')
    return copies[0]


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=DESCRIPTION)
    parser.add_argument('--skill', required=True)
    parser.add_argument('--triggers', type=Path, required=True)
    parser.add_argument('--split', choices=('train', 'validation'))
    parser.add_argument('--runs', type=int, default=3)
    parser.add_argument('--threshold', type=float, default=0.5)
    parser.add_argument('--model')
    parser.add_argument('--max-budget-usd', type=float, default=0.5)
    parser.add_argument('--timeout', type=float, default=300.0)
    parser.add_argument('--tools', default='Skill,Read')
    parser.add_argument('--claude-bin', default='claude')
    parser.add_argument('--cwd', type=Path, default=Path.cwd())
    parser.add_argument('--skill-md', type=Path)
    parser.add_argument('--output', type=Path)
    return parser.parse_args(argv)


def _fail(message: str) -> int:
    sys.stderr.write(f'error: {message}\n')
    return 2


def _claude_runner(args: argparse.Namespace, skill_md: Path) -> RunOnce:
    command = build_command(
        args.claude_bin, args.tools, args.max_budget_usd, args.model
    )
    # Equal frontmatter does not merge commands: a nested copy stays a
    # separate `dir:name` command even when its description matches.
    target = os.path.realpath(skill_md)

    def _run(query: str) -> RunOutcome:
        return run_claude_once(
            command, query, args.skill, target, args.timeout, args.cwd
        )

    return _run


def main(
    argv: list[str] | None = None, run_once: RunOnce | None = None
) -> int:
    args = _parse_args(argv)
    if args.runs < 1 or not 0 < args.threshold < 1:
        return _fail('--runs must be >= 1 and --threshold between 0 and 1')
    try:
        queries = load_queries(args.triggers, args.split)
        skill_md = resolve_skill_md(args.skill, args.cwd, args.skill_md)
        digest = hashlib.sha256(frontmatter(skill_md).encode('utf-8'))
    except (OSError, ValueError) as exc:
        return _fail(str(exc))
    if not queries:
        return _fail('no queries selected')
    runner = run_once or _claude_runner(args, skill_md)
    started = datetime.now(UTC).isoformat(timespec='seconds')
    results = []
    for index, item in enumerate(queries, start=1):
        record = measure(item, args.runs, args.threshold, runner)
        results.append(record)
        sys.stderr.write(f'[{index}/{len(queries)}] {record["status"]}\n')
    statuses = [record['status'] for record in results]
    report = {
        'skill': args.skill,
        'client': CLIENT,
        'models': sorted({m for record in results for m in record['models']}),
        'skill_md': str(skill_md),
        'frontmatter_sha256': digest.hexdigest(),
        'split': args.split,
        'runs_per_query': args.runs,
        'threshold': args.threshold,
        'started_at': started,
        'summary': {
            status: statuses.count(status)
            for status in ('pass', 'fail', 'error')
        },
        'results': results,
    }
    text = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
    if args.output is not None:
        args.output.write_text(text, encoding='utf-8')
    sys.stdout.write(text)
    if 'error' in statuses:
        return 2
    return 1 if 'fail' in statuses else 0


if __name__ == '__main__':
    raise SystemExit(main())
