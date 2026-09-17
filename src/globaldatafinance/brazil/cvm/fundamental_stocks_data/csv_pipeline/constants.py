"""Fixed CVM CSV dialect, null, and inference constants."""

from __future__ import annotations

import re
from itertools import product

NULL_TOKENS = frozenset(
    {
        '',
        '#N/A',
        '#N/A N/A',
        '#NA',
        '-1.#IND',
        '-1.#QNAN',
        '-NaN',
        '-nan',
        '1.#IND',
        '1.#QNAN',
        '<NA>',
        'N/A',
        'NA',
        'NULL',
        'NaN',
        'None',
        'n/a',
        'nan',
        'null',
    }
)
CP1252_UNDEFINED = frozenset({0x81, 0x8D, 0x8F, 0x90, 0x9D})
CP1252_DEFINED_RANGE = frozenset(range(0x80, 0xA0)) - CP1252_UNDEFINED
INTEGER = re.compile(r'^-?\d+$')
FLOAT = re.compile(
    r'^[+-]?(?:(?:\d+\.\d*|\d*\.\d+)(?:[eE][+-]?\d+)?|\d+[eE][+-]?\d+)$'
)
ROW_GROUP_SIZE = 50_000
TRUE_VALUES = tuple(
    ''.join(characters)
    for characters in product(
        *((character.lower(), character.upper()) for character in 'true')
    )
)
FALSE_VALUES = tuple(
    ''.join(characters)
    for characters in product(
        *((character.lower(), character.upper()) for character in 'false')
    )
)
