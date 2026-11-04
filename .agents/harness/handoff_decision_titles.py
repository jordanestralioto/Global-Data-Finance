"""Bind qualified semantic report titles to their exact declared design headings."""

from __future__ import annotations

import re

DECISION_RE = re.compile(r'^###\s+D\d+[:.]\s+(.+)$', re.I)


def normalize_mapping_items(
    design: str, raw: object, key: str
) -> list[dict[str, object]]:
    items = raw if isinstance(raw, list) else []
    aliases = {
        line.removeprefix('### ').strip(): match.group(1)
        for line in design.splitlines()
        if key == 'decision' and (match := DECISION_RE.match(line))
    }
    return [
        {**item, key: aliases.get(str(item.get(key)), item.get(key))}
        for item in items
        if isinstance(item, dict)
    ]
