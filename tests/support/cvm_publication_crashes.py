"""Interrupt the real CVM extractor after its first journal promotion."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

from globaldatafinance.brazil.cvm.fundamental_stocks_data import (
    transaction,
    transaction_io,
)
from globaldatafinance.brazil.cvm.fundamental_stocks_data.extract import (
    ParquetExtractorAdapterCVM,
)
from globaldatafinance.macro_infra.transactional_publication.types import (
    JOURNAL_NAME,
)
from tests.support.publication_crashes import CRASH_EXIT


class CrashAtJournal(transaction_io.CvmTransactionFileOperations):
    """Keep real leased filesystem operations until the process exits."""

    def replace(self, source: Path, destination: Path) -> None:
        """Exit with a private journal before the public manifest exists."""
        super().replace(source, destination)
        if destination.name == JOURNAL_NAME:
            os._exit(CRASH_EXIT)


if __name__ == '__main__':
    with patch.object(
        transaction, 'CvmTransactionFileOperations', CrashAtJournal
    ):
        ParquetExtractorAdapterCVM().extract(sys.argv[1], sys.argv[2])
