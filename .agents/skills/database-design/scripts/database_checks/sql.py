"""Interpret explicit SQL declarations, without simulating a live catalog."""

from __future__ import annotations

from .model import Column, Entity, Index, Interpretation, Operation
from .syntax import (
    Token,
    UnsupportedSyntax,
    grouped_end,
    read_name,
    split_top,
    tokenize,
)

COLUMN_CLAUSES = {
    'PRIMARY',
    'FOREIGN',
    'UNIQUE',
    'REFERENCES',
    'NOT',
    'NULL',
    'DEFAULT',
    'CHECK',
    'CONSTRAINT',
    'COLLATE',
    'GENERATED',
    'IDENTITY',
    'COMMENT',
    'AUTO_INCREMENT',
}


def outer_positions(tokens: list[Token]) -> list[int]:
    positions: list[int] = []
    position = 0
    while position < len(tokens):
        positions.append(position)
        if tokens[position].kind == 'symbol' and tokens[position].value == '(':
            position = grouped_end(tokens, position) + 1
        else:
            position += 1
    return positions


def column_names(tokens: list[Token], start: int) -> tuple[str, ...]:
    end = grouped_end(tokens, start)
    names: list[str] = []
    for piece in split_top(tokens[start + 1 : end]):
        if not piece or any(
            t.keyword not in {'ASC', 'DESC'} for t in piece[1:]
        ):
            raise UnsupportedSyntax(
                'Expression/opclass index needs native inspection'
            )
        names.append(piece[0].identifier)
    if not names:
        raise UnsupportedSyntax('Empty column group')
    return tuple(names)


def constraint(entity: Entity, tokens: list[Token]) -> bool:
    if tokens[0].keyword == 'CONSTRAINT':
        tokens = tokens[2:]
    if not tokens:
        raise UnsupportedSyntax('Incomplete constraint')
    kind = tokens[0].keyword
    if kind == 'CHECK':
        return True
    if kind not in {'PRIMARY', 'UNIQUE', 'FOREIGN'}:
        return False
    start = next(
        (i for i, token in enumerate(tokens) if token.value == '('), -1
    )
    if start < 0:
        raise UnsupportedSyntax('Constraint without column group')
    columns = column_names(tokens, start)
    if kind == 'PRIMARY':
        entity.primary_key = columns
        entity.indexes.append(columns)
    elif kind == 'UNIQUE':
        entity.indexes.append(columns)
    else:
        entity.foreign_keys.append(columns)
    return True


def column(entity: Entity, tokens: list[Token]) -> None:
    if len(tokens) < 2:
        raise UnsupportedSyntax('Column without type')
    name = tokens[0].identifier
    positions = outer_positions(tokens[1:])
    boundary = next(
        (i + 1 for i in positions if tokens[i + 1].keyword in COLUMN_CLAUSES),
        len(tokens),
    )
    type_name = ' '.join(token.value for token in tokens[1:boundary])
    if not type_name:
        raise UnsupportedSyntax('Column without an explicit type')
    entity.columns.append(Column(name, type_name, tokens[0].line))
    keywords = [tokens[i + 1].keyword for i in positions if i + 1 >= boundary]
    if 'PRIMARY' in keywords:
        entity.primary_key = (name,)
        entity.indexes.append((name,))
    if 'UNIQUE' in keywords:
        entity.indexes.append((name,))
    if 'REFERENCES' in keywords:
        entity.foreign_keys.append((name,))


def skip_words(tokens: list[Token], start: int, words: tuple[str, ...]) -> int:
    actual = tuple(
        token.keyword for token in tokens[start : start + len(words)]
    )
    return start + len(words) if actual == words else start


def table_statement(tokens: list[Token], start: int) -> Entity:
    start = skip_words(tokens, start, ('IF', 'NOT', 'EXISTS'))
    name, position = read_name(tokens, start)
    end = grouped_end(tokens, position)
    entity = Entity(name, tokens[0].line)
    for piece in split_top(tokens[position + 1 : end]):
        if constraint(entity, piece):
            continue
        if piece[0].keyword in {'CONSTRAINT', 'EXCLUDE', 'LIKE'}:
            raise UnsupportedSyntax(
                'Inherited/exclusion definition needs native inspection'
            )
        column(entity, piece)
    if not entity.columns:
        raise UnsupportedSyntax('No explicit table columns interpreted')
    suffix = [token.keyword for token in tokens[end + 1 :]]
    if any(word in {'AS', 'INHERITS', 'PARTITION'} for word in suffix):
        raise UnsupportedSyntax(
            'Derived/partitioned tables need native inspection'
        )
    return entity


def index_statement(tokens: list[Token], start: int) -> Index:
    start = skip_words(tokens, start, ('CONCURRENTLY',))
    start = skip_words(tokens, start, ('IF', 'NOT', 'EXISTS'))
    if start < len(tokens) and tokens[start].keyword != 'ON':
        _, start = read_name(tokens, start)
    if start >= len(tokens) or tokens[start].keyword != 'ON':
        raise UnsupportedSyntax('Index without ON')
    start = skip_words(tokens, start + 1, ('ONLY',))
    name, position = read_name(tokens, start)
    method = 'btree'
    if position < len(tokens) and tokens[position].keyword == 'USING':
        if position + 1 >= len(tokens):
            raise UnsupportedSyntax('Index without access method')
        method, position = tokens[position + 1].value.lower(), position + 2
    columns = column_names(tokens, position)
    end = grouped_end(tokens, position)
    partial = any(token.keyword == 'WHERE' for token in tokens[end + 1 :])
    return Index(name, columns, tokens[0].line, partial, method)


def create_statement(tokens: list[Token], result: Interpretation) -> None:
    start = 1
    modifiers = {'GLOBAL', 'LOCAL', 'TEMP', 'TEMPORARY', 'UNLOGGED', 'UNIQUE'}
    while start < len(tokens) and tokens[start].keyword in modifiers:
        start += 1
    kind = tokens[start].keyword if start < len(tokens) else ''
    if kind == 'TABLE':
        result.entities.append(table_statement(tokens, start + 1))
    elif kind == 'INDEX':
        result.indexes.append(index_statement(tokens, start + 1))
    elif kind != 'SCHEMA':
        raise UnsupportedSyntax(
            'CREATE object outside the supported table/index subset'
        )


def alter_action(
    entity: Entity, tokens: list[Token], result: Interpretation
) -> None:
    words = [tokens[i].keyword for i in outer_positions(tokens)]
    if tokens[0].keyword == 'ADD':
        start = skip_words(tokens, 1, ('COLUMN',))
        start = skip_words(tokens, start, ('IF', 'NOT', 'EXISTS'))
        body = tokens[start:]
        if not body:
            raise UnsupportedSyntax('Incomplete ADD clause')
        if not constraint(entity, body):
            column(entity, body)
            if 'NOT' in words and 'NULL' in words:
                result.operations.append(
                    Operation('add-required-column', tokens[0].line)
                )
        return
    if tokens[0].keyword == 'DROP':
        kind = 'drop-column'
        if words[1:2] in (['CONSTRAINT'], ['CHECK']) or words[1:3] in (
            ['PRIMARY', 'KEY'],
            ['FOREIGN', 'KEY'],
        ):
            kind = 'drop-constraint'
        elif words[1:2] in (['INDEX'], ['KEY']):
            kind = 'drop-index'
        if 'DEFAULT' in words or 'NOT' in words:
            raise UnsupportedSyntax(
                'Default/nullability removal needs native inspection'
            )
        result.operations.append(Operation(kind, tokens[0].line))
    elif 'RENAME' in words:
        result.operations.append(Operation('rename', tokens[0].line))
    elif words[-3:] == ['SET', 'NOT', 'NULL']:
        result.operations.append(Operation('set-not-null', tokens[0].line))
    elif tokens[0].keyword == 'ALTER' and 'TYPE' in words:
        result.operations.append(Operation('change-type', tokens[0].line))
    else:
        raise UnsupportedSyntax('ALTER action needs native inspection')


def alter_statement(tokens: list[Token], result: Interpretation) -> None:
    start = skip_words(tokens, 2, ('IF', 'EXISTS'))
    start = skip_words(tokens, start, ('ONLY',))
    name, start = read_name(tokens, start)
    entity = Entity(name, tokens[0].line, definition=False)
    for action in split_top(tokens[start:]):
        alter_action(entity, action, result)
    if entity.columns or entity.indexes or entity.foreign_keys:
        result.entities.append(entity)


def interpret_statement(tokens: list[Token], result: Interpretation) -> None:
    verb = tokens[0].keyword
    if verb == 'CREATE':
        create_statement(tokens, result)
    elif verb == 'ALTER' and len(tokens) > 1 and tokens[1].keyword == 'TABLE':
        alter_statement(tokens, result)
    elif verb == 'TRUNCATE' or (
        verb == 'DROP'
        and len(tokens) > 1
        and tokens[1].keyword in {'TABLE', 'SCHEMA'}
    ):
        result.operations.append(Operation('drop-data', tokens[0].line))
    elif verb == 'DROP' and len(tokens) > 1 and tokens[1].keyword == 'INDEX':
        result.operations.append(Operation('drop-index', tokens[0].line))
    elif verb not in {'BEGIN', 'COMMIT', 'ROLLBACK', 'SET', 'PRAGMA'}:
        raise UnsupportedSyntax('Statement outside the supported DDL subset')


def interpret(content: str) -> Interpretation:
    result = Interpretation()
    try:
        statements = split_top(tokenize(content), ';')
    except UnsupportedSyntax as exc:
        result.unverified.append(str(exc))
        return result
    result.statements_seen = len(statements)
    for tokens in statements:
        try:
            interpret_statement(tokens, result)
        except UnsupportedSyntax as exc:
            result.unverified.append(f'Line {tokens[0].line}: {exc}')
        else:
            result.statements_checked += 1
    return result
