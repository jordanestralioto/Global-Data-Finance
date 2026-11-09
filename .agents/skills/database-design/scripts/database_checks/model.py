"""Data exchanged by portable schema discovery, interpretation and triage."""

from __future__ import annotations

from dataclasses import dataclass, field

Name = tuple[str, ...]


@dataclass
class Column:
    name: str
    type_name: str
    line: int


@dataclass
class Entity:
    name: Name
    line: int
    columns: list[Column] = field(default_factory=list)
    primary_key: tuple[str, ...] = ()
    foreign_keys: list[tuple[str, ...]] = field(default_factory=list)
    indexes: list[tuple[str, ...]] = field(default_factory=list)
    definition: bool = True


@dataclass
class Index:
    table: Name
    columns: tuple[str, ...]
    line: int
    partial: bool = False
    method: str = 'btree'


@dataclass
class Operation:
    kind: str
    line: int


@dataclass
class Interpretation:
    entities: list[Entity] = field(default_factory=list)
    indexes: list[Index] = field(default_factory=list)
    operations: list[Operation] = field(default_factory=list)
    unverified: list[str] = field(default_factory=list)
    statements_seen: int = 0
    statements_checked: int = 0

    @property
    def units_checked(self) -> int:
        return len(self.entities) + len(self.indexes) + len(self.operations)


@dataclass
class Finding:
    category: str
    severity: str
    summary: str
    line: int
    evidence: str
    recommendation: str


@dataclass
class FileReview:
    path: str
    format: str
    coverage: str = 'unsupported'
    units_checked: int = 0
    statements_seen: int = 0
    statements_checked: int = 0
    findings: list[Finding] = field(default_factory=list)
    unverified: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
