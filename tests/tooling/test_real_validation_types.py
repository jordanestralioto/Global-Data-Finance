"""Deterministic tests for validation case serialization."""

from __future__ import annotations

from os import sep
from pathlib import Path

import pytest

from scripts.real_validation_types import ValidationCase

pytestmark = pytest.mark.unit


def test_cvm_case_serializes_public_command_and_manifest() -> None:
    """CVM evidence names the public facade and all selected arguments."""
    case = ValidationCase(
        case_id='cvm-DFP-2024',
        source='cvm',
        year=2024,
        input_path='https://example.test/dfp.zip',
        output_root=str(Path(sep, 'tmp', 'cvm-output')),
        document='DFP',
        mode='cvm',
        url='https://example.test/dfp.zip',
    )

    assert case.command() == [
        'FundamentalStocksDataCVM.download',
        f'destination_path={Path(sep, "tmp", "cvm-output")}',
        'list_docs=[DFP]',
        'initial_year=2024',
        'last_year=2024',
        'automatic_extractor=True',
    ]
    assert case.to_manifest_dict()['caseId'] == 'cvm-DFP-2024'
