"""Unit tests for ProcessingModeEnumB3."""

import pytest

from globaldatafinance.brazil.b3_data.historical_quotes.processing import (
    ProcessingModeEnumB3,
)

pytestmark = pytest.mark.unit


class TestProcessingModeEnumB3:
    def test_fast_mode_value(self):
        assert ProcessingModeEnumB3.FAST.value == 'fast'
        assert ProcessingModeEnumB3.FAST == 'fast'

    def test_slow_mode_value(self):
        assert ProcessingModeEnumB3.SLOW.value == 'slow'
        assert ProcessingModeEnumB3.SLOW == 'slow'

    def test_enum_has_exactly_two_members(self):
        assert list(ProcessingModeEnumB3) == [
            ProcessingModeEnumB3.FAST,
            ProcessingModeEnumB3.SLOW,
        ]

    def test_inherits_from_str(self):
        assert isinstance(ProcessingModeEnumB3.FAST, str)
        assert isinstance(ProcessingModeEnumB3.SLOW, str)

    def test_can_access_by_value(self):
        assert ProcessingModeEnumB3('fast') == ProcessingModeEnumB3.FAST
        assert ProcessingModeEnumB3('slow') == ProcessingModeEnumB3.SLOW

    def test_invalid_value_raises_error(self):
        with pytest.raises(ValueError):
            ProcessingModeEnumB3('invalid')

    def test_case_sensitive_comparison(self):
        assert ProcessingModeEnumB3.FAST != 'FAST'
        assert ProcessingModeEnumB3.SLOW != 'SLOW'
