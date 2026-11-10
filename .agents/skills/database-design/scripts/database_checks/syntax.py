"""Bounded token handling; no consumer code or database commands are run."""

from __future__ import annotations

import re
from dataclasses import dataclass

WORD = re.compile(r'[A-Za-z_\u0080-\uffff][\w$]*')
DOLLAR_QUOTE = re.compile(r'\$(?:[A-Za-z_]\w*)?\$')


class UnsupportedSyntax(ValueError):
    """The input cannot be interpreted within this tool's declared subset."""


@dataclass(frozen=True)
class Token:
    value: str
    kind: str
    line: int

    @property
    def keyword(self) -> str:
        return self.value.upper() if self.kind == 'word' else ''

    @property
    def identifier(self) -> str:
        if self.kind not in {'word', 'identifier'}:
            raise UnsupportedSyntax(f'Expected identifier at line {self.line}')
        return self.value.lower() if self.kind == 'word' else self.value


def quoted_end(source: str, start: int, closer: str) -> int:
    position = start + 1
    while position < len(source):
        if source[position] == closer:
            if position + 1 < len(source) and source[position + 1] == closer:
                position += 2
                continue
            return position + 1
        if source[position] == '\\' and closer == "'":
            position += 2
        else:
            position += 1
    raise UnsupportedSyntax('Unterminated quoted value')


def comment_end(source: str, start: int) -> int:
    position, depth = start + 2, 1
    while position < len(source):
        if source.startswith('/*', position):
            depth += 1
            position += 2
        elif source.startswith('*/', position):
            depth -= 1
            position += 2
            if depth == 0:
                return position
        else:
            position += 1
    raise UnsupportedSyntax('Unterminated block comment')


def tokenize(source: str, *, prisma: bool = False) -> list[Token]:
    tokens: list[Token] = []
    position, line = 0, 1
    while position < len(source):
        char = source[position]
        start = position
        if char.isspace():
            line += int(char == '\n')
            position += 1
            continue
        if source.startswith('//' if prisma else '--', position):
            end = source.find('\n', position)
            position = len(source) if end < 0 else end
            continue
        if source.startswith('/*', position):
            position = comment_end(source, position)
            line += source[start:position].count('\n')
            continue
        if char in {'"', "'", '`'} or (char == '[' and not prisma):
            closer = ']' if char == '[' else char
            position = quoted_end(source, position, closer)
            kind = 'literal' if char == "'" or prisma else 'identifier'
            value = source[start + 1 : position - 1].replace(
                closer * 2, closer
            )
        elif char == '$' and (match := DOLLAR_QUOTE.match(source, position)):
            delimiter = match.group()
            end = source.find(delimiter, match.end())
            if end < 0:
                raise UnsupportedSyntax('Unterminated dollar-quoted value')
            position, kind, value = end + len(delimiter), 'literal', ''
        elif match := WORD.match(source, position):
            position, kind, value = match.end(), 'word', match.group()
        else:
            position, kind, value = position + 1, 'symbol', char
        tokens.append(Token(value, kind, line))
        line += source[start:position].count('\n')
    return tokens


def grouped_end(tokens: list[Token], start: int) -> int:
    pairs = {'(': ')', '[': ']', '{': '}'}
    if start >= len(tokens) or tokens[start].value not in pairs:
        raise UnsupportedSyntax('Expected a delimited group')
    stack: list[str] = []
    for position in range(start, len(tokens)):
        token = tokens[position]
        if token.kind != 'symbol':
            continue
        if token.value in pairs:
            stack.append(pairs[token.value])
        elif token.value in pairs.values():
            if not stack or token.value != stack.pop():
                raise UnsupportedSyntax(
                    f'Unbalanced group at line {token.line}'
                )
            if not stack:
                return position
    raise UnsupportedSyntax('Unterminated group')


def split_top(tokens: list[Token], separator: str = ',') -> list[list[Token]]:
    result: list[list[Token]] = []
    start, position = 0, 0
    while position < len(tokens):
        token = tokens[position]
        if token.kind == 'symbol' and token.value in {'(', '[', '{'}:
            position = grouped_end(tokens, position) + 1
            continue
        if token.kind == 'symbol' and token.value == separator:
            if position > start:
                result.append(tokens[start:position])
            start = position + 1
        position += 1
    if start < len(tokens):
        result.append(tokens[start:])
    return result


def read_name(tokens: list[Token], start: int) -> tuple[tuple[str, ...], int]:
    if start >= len(tokens):
        raise UnsupportedSyntax('Expected an object name')
    parts = [tokens[start].identifier]
    position = start + 1
    while position < len(tokens) and tokens[position].value == '.':
        if position + 1 >= len(tokens):
            raise UnsupportedSyntax('Incomplete qualified name')
        parts.append(tokens[position + 1].identifier)
        position += 2
    return tuple(parts), position
