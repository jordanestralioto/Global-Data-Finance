"""Read declared Prisma keys/indexes/relations, including multiline attributes."""

from __future__ import annotations

from .model import Column, Entity, Interpretation
from .syntax import Token, UnsupportedSyntax, grouped_end, split_top, tokenize


def entries(tokens: list[Token]) -> list[list[Token]]:
    result: list[list[Token]] = []
    start, position = 0, 0
    while position < len(tokens):
        if (
            position > start
            and tokens[position].line > tokens[position - 1].line
        ):
            result.append(tokens[start:position])
            start = position
        if tokens[position].value in {'(', '['}:
            position = grouped_end(tokens, position) + 1
        else:
            position += 1
    if start < len(tokens):
        result.append(tokens[start:])
    return result


def grouped_names(tokens: list[Token], start: int) -> tuple[str, ...]:
    end = grouped_end(tokens, start)
    parts = split_top(tokens[start + 1 : end])
    if not parts or any(not part or part[0].kind != 'word' for part in parts):
        raise UnsupportedSyntax('Invalid Prisma field group')
    return tuple(part[0].value for part in parts)


def first_list(tokens: list[Token]) -> tuple[str, ...]:
    start = next(
        (i for i, token in enumerate(tokens) if token.value == '['), -1
    )
    if start < 0:
        raise UnsupportedSyntax('Prisma key/index without field list')
    return grouped_names(tokens, start)


def attributes(tokens: list[Token]) -> list[tuple[str, list[Token]]]:
    result: list[tuple[str, list[Token]]] = []
    position = 0
    while position < len(tokens) - 1:
        if tokens[position].value != '@':
            position += 1
            continue
        position += 1
        name = tokens[position].value
        position += 1
        if position < len(tokens) and tokens[position].value == '(':
            end = grouped_end(tokens, position)
            result.append((name, tokens[position + 1 : end]))
            position = end + 1
        else:
            result.append((name, []))
    return result


def model_attribute(entity: Entity, tokens: list[Token]) -> None:
    if len(tokens) < 3:
        raise UnsupportedSyntax('Incomplete Prisma model attribute')
    name = tokens[2].value
    if name in {'id', 'unique', 'index'}:
        if any(token.value == 'where' for token in tokens):
            raise UnsupportedSyntax(
                'Conditional Prisma index needs native inspection'
            )
        columns = first_list(tokens)
        entity.indexes.append(columns)
        if name == 'id':
            entity.primary_key = columns
    elif name == 'ignore':
        raise UnsupportedSyntax('Ignored Prisma model needs native inspection')


def model_field(entity: Entity, tokens: list[Token]) -> None:
    if len(tokens) < 2 or tokens[0].kind != 'word' or tokens[1].kind != 'word':
        raise UnsupportedSyntax('Unrecognized Prisma field declaration')
    name, type_name = tokens[0].value, tokens[1].value
    if len(tokens) > 2 and tokens[2].value == '[':
        type_name += '[]'
    entity.columns.append(Column(name, type_name, tokens[0].line))
    for attribute, arguments in attributes(tokens[2:]):
        if attribute in {'id', 'unique'}:
            entity.indexes.append((name,))
            if attribute == 'id':
                entity.primary_key = (name,)
        if attribute == 'relation':
            for position, token in enumerate(arguments[:-2]):
                if (
                    token.value == 'fields'
                    and arguments[position + 1].value == ':'
                ):
                    entity.foreign_keys.append(
                        grouped_names(arguments, position + 2)
                    )
                    break


def model(tokens: list[Token], name: Token) -> Entity:
    entity = Entity((name.value,), name.line)
    for entry in entries(tokens):
        if [token.value for token in entry[:2]] == ['@', '@']:
            model_attribute(entity, entry)
        else:
            model_field(entity, entry)
    fields = {field.name for field in entity.columns}
    referenced = {name for key in entity.foreign_keys for name in key}
    if not fields or not referenced <= fields:
        raise UnsupportedSyntax(
            'Prisma model/relation fields were not fully interpreted'
        )
    return entity


def interpret(content: str) -> Interpretation:
    result = Interpretation()
    try:
        tokens = tokenize(content, prisma=True)
        position = 0
        while position < len(tokens):
            start = position
            if (
                position + 2 >= len(tokens)
                or tokens[position + 2].value != '{'
            ):
                raise UnsupportedSyntax('Expected a Prisma declaration block')
            end = grouped_end(tokens, position + 2)
            body = tokens[position + 3 : end]
            kind = tokens[start].value
            result.statements_seen += 1
            try:
                if kind == 'model':
                    result.entities.append(model(body, tokens[start + 1]))
                elif kind not in {'generator', 'datasource', 'enum'}:
                    raise UnsupportedSyntax(
                        'Prisma declaration needs native inspection'
                    )
                if kind == 'datasource' and any(
                    t.value == 'mongodb' for t in body
                ):
                    raise UnsupportedSyntax(
                        'MongoDB schema needs native inspection'
                    )
            except UnsupportedSyntax as exc:
                result.unverified.append(f'Line {tokens[start].line}: {exc}')
            else:
                result.statements_checked += 1
            position = end + 1
    except UnsupportedSyntax as exc:
        result.unverified.append(str(exc))
    return result
