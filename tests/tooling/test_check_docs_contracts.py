"""Tests for the documentation contract checker."""

from __future__ import annotations

import importlib
import importlib.util
import runpy
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

CHECKER_PATH = (
    Path(__file__).resolve().parents[2] / 'scripts' / 'check-docs-contracts.py'
)
REPOSITORY_ROOT = CHECKER_PATH.parents[1]


def load_checker() -> ModuleType:
    """Load the doc checker module from its script path."""
    scripts_directory = str(CHECKER_PATH.parent)
    added_scripts_directory = scripts_directory not in sys.path
    if added_scripts_directory:
        sys.path.insert(0, scripts_directory)

    try:
        spec = importlib.util.spec_from_file_location(
            'check_docs_contracts', CHECKER_PATH
        )
        if spec is None or spec.loader is None:
            raise AssertionError(f'Unable to load checker from {CHECKER_PATH}')

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if added_scripts_directory:
            sys.path.remove(scripts_directory)


@pytest.fixture(scope='module')
def checker() -> Any:
    """Return the loaded documentation contract checker module."""
    return load_checker()


@pytest.mark.unit
def test_cli_entrypoint_validates_current_documentation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Checker's command-line entrypoint must validate the current corpus."""
    monkeypatch.syspath_prepend(str(CHECKER_PATH.parent))

    with pytest.raises(SystemExit) as raised:
        runpy.run_path(str(CHECKER_PATH), run_name='__main__')

    assert raised.value.code == 0


@pytest.mark.unit
def test_detect_signature_without_colon(checker: Any) -> None:
    """Checker must flag method signatures missing trailing colons."""
    code = 'def download(self, destination: str) -> DownloadResultCVM'
    errors = checker.check_python_blocks(Path('test.md'), 10, 'python', code)
    assert any(
        'missing trailing colon' in err or 'SyntaxError' in err
        for err in errors
    )


@pytest.mark.unit
def test_detect_missing_path_of_docs_in_b3_call(checker: Any) -> None:
    """Checker must flag B3 calls missing path or asset arguments."""
    code = """
from globaldatafinance import HistoricalQuotesB3
b3 = HistoricalQuotesB3()
result = b3.extract(initial_year=2023)
"""
    errors = checker.check_python_blocks(Path('test.md'), 1, 'python', code)
    assert any(
        'b3.extract() call missing path_of_docs' in err for err in errors
    )


@pytest.mark.unit
def test_detect_b3_call_without_context(checker: Any) -> None:
    """Checker must flag B3 calls without their documented context."""
    code = """
result = b3.extract(
    path_of_docs="/data/cotahist",
    assets_list=["ações"],
    initial_year=2023
)
"""
    errors = checker.check_python_blocks(Path('test.md'), 1, 'python', code)
    assert any(
        'without HistoricalQuotesB3 import or instantiation' in err
        for err in errors
    )


@pytest.mark.unit
def test_detect_disallowed_method_and_attribute(checker: Any) -> None:
    """Checker must flag calls to disallowed methods."""
    code = """
adapter.download_files(tasks)
"""
    errors = checker.check_python_blocks(Path('test.md'), 1, 'python', code)
    assert any('disallowed attribute or method used' in err for err in errors)


@pytest.mark.unit
def test_detect_direct_call_to_disallowed_symbol(checker: Any) -> None:
    """Checker must flag direct calls to disallowed symbols."""
    code = """
download_files()
"""
    errors = checker.check_python_blocks(Path('test.md'), 1, 'python', code)
    assert any('disallowed function called directly' in err for err in errors)


@pytest.mark.unit
def test_detect_nonexistent_import(checker: Any) -> None:
    """Checker must flag imports of non-existent or disallowed symbols."""
    code = """
from globaldatafinance.macro_exceptions import GlobalDataFinanceError
"""
    errors = checker.check_python_blocks(Path('test.md'), 1, 'python', code)
    assert any(
        'disallowed symbol imported' in err or 'not found' in err
        for err in errors
    )


@pytest.mark.unit
def test_ast_node_checks_accumulate_combined_block_findings(
    checker: Any,
) -> None:
    """Independent AST facts must be retained when they share one block."""
    code = """
from globaldatafinance import HistoricalQuotesB3
from globaldatafinance.macro_exceptions import GlobalDataFinanceError

b3 = HistoricalQuotesB3()
b3.download_files([])
b3.extract(path_of_docs="/data")
"""

    errors = checker.check_python_blocks(Path('test.md'), 1, 'python', code)

    assert any('disallowed symbol imported' in error for error in errors)
    assert any(
        'disallowed attribute or method used' in error for error in errors
    )
    assert any(
        'missing path_of_docs or assets_list' in error for error in errors
    )


@pytest.mark.unit
def test_known_import_inventory_points_to_importable_attributes(
    checker: Any,
) -> None:
    """Every documented import allowlist entry must exist in its module."""
    for module_name, symbol_names in checker.KNOWN_IMPORTS.items():
        module = importlib.import_module(module_name)
        for symbol_name in symbol_names:
            assert hasattr(module, symbol_name), (
                f'{module_name}.{symbol_name} is not importable'
            )


@pytest.mark.unit
def test_accept_valid_python_block(checker: Any) -> None:
    """Checker must accept valid Python blocks and signatures."""
    code = """
from globaldatafinance import HistoricalQuotesB3

b3 = HistoricalQuotesB3()
result = b3.extract(
    path_of_docs="/data/cotahist",
    assets_list=["ações"],
    initial_year=2023
)
"""
    errors = checker.check_python_blocks(Path('test.md'), 1, 'python', code)
    assert errors == []


@pytest.mark.unit
def test_reject_python_magic_in_python_fence_but_accept_ipython(
    checker: Any,
) -> None:
    """Checker must keep notebook magics out of raw Python fences."""
    errors = checker.check_python_blocks(
        Path('test.md'), 1, 'python', '%matplotlib inline'
    )
    assert any('SyntaxError' in error for error in errors)
    assert (
        checker.check_python_blocks(
            Path('test.md'), 1, 'ipython', '%matplotlib inline'
        )
        == []
    )


@pytest.mark.unit
def test_accept_pycon_and_repl_blocks(checker: Any) -> None:
    """Checker must accept pycon and REPL blocks without AST evaluation."""
    code = (
        '>>> from globaldatafinance import HistoricalQuotesB3\\n'
        '>>> b3 = HistoricalQuotesB3()'
    )
    errors = checker.check_python_blocks(Path('test.md'), 1, 'pycon', code)
    assert errors == []


@pytest.mark.unit
def test_accept_valid_4space_admonition(checker: Any) -> None:
    """Checker must accept admonitions with 4-space indented bodies."""
    content = """
!!! info "Notice"
    This is properly indented by four spaces.
    Second line of admonition.
"""
    errors = checker.check_markdown_formatting(Path('test.md'), content)
    assert errors == []


@pytest.mark.unit
def test_accept_admonition_with_blank_lines(checker: Any) -> None:
    """Checker must accept admonitions with separated paragraphs."""
    content = """
!!! info "Notice"
    First paragraph of notice.

    Second paragraph of notice properly indented.
"""
    errors = checker.check_markdown_formatting(Path('test.md'), content)
    assert errors == []


@pytest.mark.unit
def test_accept_admonition_ending_at_eof(checker: Any) -> None:
    """Checker must accept an indented admonition that ends at EOF."""
    content = '!!! info "Notice"\n    Body without a trailing newline.'

    assert checker.check_markdown_formatting(Path('test.md'), content) == []


@pytest.mark.unit
def test_accept_structural_terminator_after_admonition(checker: Any) -> None:
    """A Markdown heading after a blank line must end the admonition."""
    content = '!!! info "Notice"\n    Body.\n\n## Next section\n'

    assert checker.check_markdown_formatting(Path('test.md'), content) == []


@pytest.mark.unit
def test_reject_empty_admonition_at_eof(checker: Any) -> None:
    """An admonition with no body must retain its empty-block diagnostic."""
    content = '!!! info "Notice"\n\n'

    errors = checker.check_markdown_formatting(Path('test.md'), content)

    assert any('empty admonition block' in error for error in errors)


@pytest.mark.unit
def test_reject_unindented_admonition_body(checker: Any) -> None:
    """Checker must reject admonitions with an unindented body line."""
    content = """
!!! info "Notice"
This body line is not indented and breaks rendering.
"""
    errors = checker.check_markdown_formatting(Path('test.md'), content)
    assert any(
        'unindented line inside admonition body' in err for err in errors
    )


@pytest.mark.unit
def test_reject_unindented_second_paragraph_in_admonition(
    checker: Any,
) -> None:
    """Checker must reject an unindented second admonition paragraph."""
    content = """
!!! info "Example"
    First paragraph.

Unindented second paragraph.
"""
    errors = checker.check_markdown_formatting(Path('test.md'), content)
    assert any(
        'unindented line inside admonition body' in err for err in errors
    )


@pytest.mark.unit
def test_reject_4backtick_fences(checker: Any) -> None:
    """Checker must reject 4-backtick blocks in standard documentation."""
    content = """
````python
def test():
    pass
````
"""
    errors = checker.check_markdown_formatting(Path('test.md'), content)
    assert any('4-backtick fence found' in err for err in errors)


@pytest.mark.unit
def test_check_bilingual_parity_and_alignment(
    checker: Any, tmp_path: Path
) -> None:
    """Checker must verify bilingual parity and H2 section alignment."""
    docs = tmp_path / 'docs'
    docs.mkdir()
    (docs / 'guide.md').write_text(
        '# Guia\n\n## Seção 1\n\n## Seção 2\n', encoding='utf-8'
    )

    # Missing .en.md
    errors = checker.check_bilingual_parity(docs)
    assert len(errors) == 1
    assert 'missing English counterpart' in errors[0]

    # Add .en.md with H2 count mismatch
    (docs / 'guide.en.md').write_text(
        '# Guide\n\n## Section 1\n', encoding='utf-8'
    )
    errors = checker.check_bilingual_parity(docs)
    assert len(errors) == 1
    assert 'H2 section count mismatch' in errors[0]

    # Correct H2 count
    (docs / 'guide.en.md').write_text(
        '# Guide\n\n## Section 1\n\n## Section 2\n', encoding='utf-8'
    )
    assert checker.check_bilingual_parity(docs) == []


@pytest.mark.unit
@pytest.mark.parametrize(
    'relative_path',
    [
        'internal/draft.md',
        'internal/sabatina/draft.md',
        'internal/sabatina/draft.en.md',
    ],
)
def test_local_internal_documents_are_excluded_from_all_contract_checks(
    checker: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    relative_path: str,
) -> None:
    """Local drafts need neither translations nor valid published examples."""
    docs = tmp_path / 'docs'
    draft = docs / relative_path
    draft.parent.mkdir(parents=True)
    draft.write_text(
        '# Draft\n\n````text\nDraft\n````\n\n```python\ndef broken(\n```\n',
        encoding='utf-8',
    )
    (docs / 'guide.md').write_text('# Guia\n', encoding='utf-8')
    (docs / 'guide.en.md').write_text('# Guide\n', encoding='utf-8')
    monkeypatch.setattr(checker, 'DOCS_DIR', docs)

    assert checker.main() == 0


@pytest.mark.unit
@pytest.mark.parametrize(
    'relative_path',
    [
        'internal-guide/guide.md',
        'user-guide/internal.md',
        'user-guide/internal/guide.md',
    ],
)
def test_internal_exclusion_preserves_checks_on_other_documentation_paths(
    checker: Any,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    relative_path: str,
) -> None:
    """Similar names outside docs/internal must retain all contract checks."""
    docs = tmp_path / 'docs'
    page = docs / relative_path
    page.parent.mkdir(parents=True)
    page.write_text('```python\ndef broken(\n```\n', encoding='utf-8')
    monkeypatch.setattr(checker, 'DOCS_DIR', docs)

    assert checker.main() == 1
    output = capsys.readouterr().out
    assert 'missing English counterpart' in output
    assert 'SyntaxError in python code block' in output


@pytest.mark.unit
def test_root_readme_is_in_corpus_without_bilingual_parity_requirement(
    checker: Any, tmp_path: Path
) -> None:
    """A root README needs no README.en.md counterpart."""
    (tmp_path / 'README.md').write_text('# Root\n', encoding='utf-8')
    docs = tmp_path / 'docs'
    docs.mkdir()

    assert tmp_path / 'README.md' in checker.documentation_files(tmp_path)
    assert (
        REPOSITORY_ROOT / 'examples' / 'README.md'
        in checker.documentation_files(REPOSITORY_ROOT)
    )
    assert checker.check_bilingual_parity(docs) == []


@pytest.mark.unit
@pytest.mark.parametrize(
    'relative',
    [
        'examples/README.md',
        'src/globaldatafinance/brazil/b3_data/historical_quotes/README.md',
    ],
)
def test_readme_translations_are_checked_for_presence_and_alignment(
    checker: Any, tmp_path: Path, relative: str
) -> None:
    """Module and example translations cannot escape the native doc gate."""
    portuguese = tmp_path / relative
    english = portuguese.with_name('README.en.md')
    portuguese.parent.mkdir(parents=True)
    portuguese.write_text('# PT\n\n## COTAHIST ZIP TXT\n', encoding='utf-8')

    errors = checker.check_bilingual_readmes(tmp_path)
    assert any('missing English counterpart' in error for error in errors)

    english.write_text('# EN\n', encoding='utf-8')
    errors = checker.check_bilingual_readmes(tmp_path)
    assert any('H2 section count mismatch' in error for error in errors)
    assert any('COTAHIST' in error for error in errors)

    english.write_text('# EN\n\n## COTAHIST ZIP TXT\n', encoding='utf-8')
    assert checker.check_bilingual_readmes(tmp_path) == []
    assert english in checker.documentation_files(tmp_path)

    portuguese.unlink()
    errors = checker.check_bilingual_readmes(tmp_path)
    assert any('missing Portuguese counterpart' in error for error in errors)


@pytest.mark.unit
def test_check_file_contracts(checker: Any) -> None:
    """Checker must validate file-specific contract guarantees."""
    # Non-semantic logging content
    assert (
        checker.check_file_contracts(
            Path('logging-system.md'), 'just text without python block'
        )
        != []
    )
    assert (
        checker.check_file_contracts(
            Path('logging-system.md'), "```python\nlogger.info('test')\n```"
        )
        != []
    )

    # Semantic logging content
    semantic_logging = """
```python
logger.info("ok", extra={"file_target": "data.csv"})
```
"""
    assert (
        checker.check_file_contracts(
            Path('logging-system.md'), semantic_logging
        )
        == []
    )

    assert checker.check_file_contracts(Path('b3-docs.md'), 'incomplete') != []
    valid_b3 = (
        'The API accepts COTAHIST_A2023.ZIP or COTAHIST_A2023.TXT. 010 020'
    )
    assert checker.check_file_contracts(Path('b3-docs.md'), valid_b3) == []

    assert checker.check_file_contracts(Path('faq.md'), 'incomplete') != []
    valid_faq = (
        '| **fast** | 429,88 MiB |\n'
        '| **slow** | 331,11 MiB |\n'
        '[Benchmark](../dev-guide/benchmarks.md)'
    )
    assert checker.check_file_contracts(Path('faq.md'), valid_faq) == []
    assert (
        checker.check_file_contracts(
            Path('faq.md'), valid_faq.replace('331,11 MiB', 'unmeasured')
        )
        != []
    )
    assert (
        checker.check_file_contracts(
            Path('faq.md'), valid_faq.replace('benchmarks.md', 'other.md')
        )
        != []
    )
    assert (
        checker.check_file_contracts(
            Path('faq.en.md'),
            valid_faq.replace('benchmarks.md', 'benchmarks.en.md'),
        )
        == []
    )
    assert checker.check_file_contracts(Path('faq.en.md'), valid_faq) != []


@pytest.mark.unit
def test_canonical_b3_signature_defaults_follow_source(checker: Any) -> None:
    """Canonical B3 API defaults must stay synchronized with source."""
    path = REPOSITORY_ROOT / 'docs/reference/b3-api.md'
    content = path.read_text(encoding='utf-8')
    altered = content.replace(
        '    output_filename: str = "cotahist_extracted"',
        '    output_filename: str = "different_default"',
        1,
    )

    errors = checker.check_file_contracts(path, altered)

    assert any(
        'extract signature default for `output_filename`' in error
        for error in errors
    )


@pytest.mark.unit
def test_canonical_b3_signature_requires_all_source_parameters(
    checker: Any,
) -> None:
    """Canonical B3 API docs must expose every source signature parameter."""
    path = REPOSITORY_ROOT / 'docs/reference/b3-api.md'
    content = path.read_text(encoding='utf-8')
    altered = content.replace('    verbose: bool = True,\n', '', 1)

    errors = checker.check_file_contracts(path, altered)

    assert any(
        'parameter names/order do not match source' in error
        for error in errors
    )


@pytest.mark.unit
def test_canonical_b3_signature_must_be_present(checker: Any) -> None:
    """Canonical B3 API docs must include a discoverable extract method."""
    path = REPOSITORY_ROOT / 'docs/reference/b3-api.md'
    content = path.read_text(encoding='utf-8')
    altered = content.replace('def extract(', 'def renamed_extract(', 1)

    errors = checker.check_file_contracts(path, altered)

    assert any(
        'must include the HistoricalQuotesB3.extract signature' in error
        for error in errors
    )


@pytest.mark.unit
def test_canonical_result_fields_are_checked_against_source(
    checker: Any,
) -> None:
    """The B3 checker must report a missing result field."""
    path = REPOSITORY_ROOT / 'docs/reference/b3-api.md'
    content = path.read_text(encoding='utf-8')
    altered = content.replace(
        '- `elapsed_time: float`', '- `duration: float`', 1
    )

    errors = checker.check_file_contracts(path, altered)

    assert any(
        'ExtractionResultB3 must document `elapsed_time`' in error
        for error in errors
    )


@pytest.mark.unit
def test_cvm_api_rejects_nonexistent_exception_names(checker: Any) -> None:
    """The CVM API checker must reject exception names absent from source."""
    path = REPOSITORY_ROOT / 'docs/reference/cvm-api.md'
    content = path.read_text(encoding='utf-8')
    altered = f'{content}\n`InvalidCVMResponseError`\n'

    errors = checker.check_file_contracts(path, altered)

    assert any('InvalidCVMResponseError' in error for error in errors)


@pytest.mark.unit
@pytest.mark.parametrize(
    'relative_path',
    [
        'docs/reference/b3-api.md',
        'docs/reference/b3-api.en.md',
        'docs/dev-guide/api-reference.md',
        'docs/dev-guide/api-reference.en.md',
    ],
)
def test_b3_api_docs_enforce_v2_catalog_contract(
    checker: Any, relative_path: str
) -> None:
    """Both translations require content equivalence and explicit gaps."""
    path = REPOSITORY_ROOT / relative_path
    content = path.read_text(encoding='utf-8')
    assert checker.check_file_contracts(path, content) == []
    altered = content.replace('idênticos', 'diferentes', 1).replace(
        'identical', 'different', 1
    )
    assert altered != content

    errors = checker.check_file_contracts(path, altered)

    assert any('identical contents before selecting ZIP' in e for e in errors)


@pytest.mark.unit
def test_b3_api_docs_reject_obsolete_empty_directory_exception(
    checker: Any,
) -> None:
    """The former empty-directory exception claim contradicts v2 coverage."""
    path = REPOSITORY_ROOT / 'docs/reference/b3-api.en.md'
    content = path.read_text(encoding='utf-8')
    altered = content + '\nAn empty directory raises EmptyDirectoryError.\n'

    errors = checker.check_file_contracts(path, altered)

    assert any(
        'missing-year failure with zero resolved files' in e for e in errors
    )


@pytest.mark.unit
def test_b3_contract_distinguishes_official_zip_from_api_support(
    checker: Any,
) -> None:
    """Checker must distinguish official ZIP downloads from TXT support."""
    valid = (
        'Official B3 downloads use COTAHIST_A2023.ZIP. '
        'The API accepts COTAHIST_A2023.ZIP or COTAHIST_A2023.TXT.'
    )
    assert checker.check_file_contracts(Path('README.md'), valid) == []

    errors = checker.check_file_contracts(
        Path('README.md'), 'The B3 API accepts only COTAHIST_A2023.ZIP files.'
    )
    assert any('must not claim ZIP-only support' in error for error in errors)

    errors = checker.check_file_contracts(
        Path('README.md'),
        'The B3 API accepts only COTAHIST_A2023.ZIP files, not TXT files.',
    )
    assert any('must not claim ZIP-only support' in error for error in errors)

    errors = checker.check_file_contracts(
        Path('examples/README.md'), 'B3 API documentation is incomplete.'
    )
    assert any('must name COTAHIST_A inputs' in error for error in errors)


@pytest.mark.unit
def test_b3_asset_semantics_follow_source_tpmerc_mapping(checker: Any) -> None:
    """Checker must reject spot-only claims for stock aliases."""
    assert ('ações', ('010', '020')) in (
        checker.SOURCE_CONTRACTS.b3_asset_tpmerc_codes
    )
    valid = (
        'The API accepts COTAHIST_A2023.ZIP or COTAHIST_A2023.TXT and '
        'filters stock records across spot and fractional markets.'
    )
    assert (
        checker.check_file_contracts(
            Path('docs/user-guide/quickstart.en.md'), valid
        )
        == []
    )

    multiline_valid = (
        'The stock class is filtered across the spot market (010) and the\n'
        'fractional market (020).'
    )
    assert (
        checker.check_public_b3_asset_semantics(
            Path('docs/user-guide/quickstart.en.md'),
            multiline_valid,
            checker.SOURCE_CONTRACTS,
        )
        == []
    )

    errors = checker.check_file_contracts(
        Path('docs/user-guide/quickstart.en.md'),
        'The API accepts COTAHIST_A2023.ZIP or COTAHIST_A2023.TXT and '
        'filters exclusively for spot market stocks.',
    )
    assert any(
        'must not describe mapped stock/ETF aliases as spot-only' in error
        for error in errors
    )


@pytest.mark.unit
def test_checker_rejects_nonexistent_test_module_commands(
    checker: Any,
) -> None:
    """Checker must not advertise a test module absent from the repository."""
    content = """
```bash
uv run python -m tests.perf.benchmark_runner
```
"""
    errors = checker.check_file_contracts(
        Path('docs/dev-guide/benchmarks.md'), content
    )
    assert any(
        'documented test module does not exist' in error for error in errors
    )


@pytest.mark.unit
def test_checker_rejects_inaccurate_internal_b3_object_contract(
    checker: Any,
) -> None:
    """Checker must protect low-level B3 ownership and path semantics."""
    content = """
DocsToExtractorB3 encapsula e valida parâmetros de configuração.
AvailableAssetsServiceB3 faz validação de nomes de ativos (tickers).
InvalidAssetsName: ticker fornecido não segue o padrão esperado.
documents_to_download: Nomes exatos dos arquivos COTAHIST.

```python
config = DocsToExtractorB3(
    documents_to_download={'COTAHIST_A2023.ZIP'},
)
```
"""
    errors = checker.check_file_contracts(
        Path(
            'src/globaldatafinance/brazil/b3_data/historical_quotes/README.md'
        ),
        content,
    )
    assert any(
        'DocsToExtractorB3 must be documented' in error for error in errors
    )
    assert any('not individual tickers' in error for error in errors)
    assert any('bare filenames' in error for error in errors)
    assert any('resolved absolute paths' in error for error in errors)


@pytest.mark.unit
def test_b3_contract_does_not_treat_internal_cvm_readme_as_root(
    checker: Any,
) -> None:
    """Checker must not apply root B3 rules to the unrelated CVM README."""
    errors = checker.check_file_contracts(
        Path(
            'src/globaldatafinance/brazil/cvm/'
            'fundamental_stocks_data/README.md'
        ),
        'incomplete',
    )

    assert errors == []


@pytest.mark.unit
def test_bilingual_contract_markers_are_aligned(
    checker: Any, tmp_path: Path
) -> None:
    """Checker must detect a marker present in only one translation."""
    pt_file = tmp_path / 'guide.md'
    en_file = tmp_path / 'guide.en.md'
    pt_file.write_text(
        '# Guia\n\n## B3\n\nCOTAHIST ZIP TXT\n', encoding='utf-8'
    )
    en_file.write_text('# Guide\n\n## B3\n\nCOTAHIST ZIP\n', encoding='utf-8')

    errors = checker.check_bilingual_parity(tmp_path)

    assert any("contract marker 'TXT'" in error for error in errors)


@pytest.mark.unit
def test_logging_file_target_keyword_is_semantically_valid(
    checker: Any,
) -> None:
    """Checker must accept file_target in logging helper arguments."""
    content = """
```python
with log_execution_time(logger, "write output", file_target="data.parquet"):
    write_output()
```
"""
    assert (
        checker.check_file_contracts(Path('logging-system.md'), content) == []
    )


@pytest.mark.unit
def test_logging_reserved_filename_and_syntax_errors_are_reported(
    checker: Any,
) -> None:
    """Checker must reject reserved filename and malformed logging blocks."""
    reserved = """
```python
logger.info("bad", extra={"filename": "data.csv", "file_target": "data.csv"})
```
"""
    errors = checker.check_file_contracts(Path('logging-system.md'), reserved)
    assert any('reserved logging key filename' in error for error in errors)

    direct_keyword = """
```python
log_with_context(logger, filename="bad.csv", file_target="data.csv")
```
"""
    errors = checker.check_file_contracts(
        Path('logging-system.md'), direct_keyword
    )
    assert any('reserved logging key filename' in error for error in errors)

    malformed = """
```python
logger.info(
```
"""
    errors = checker.check_file_contracts(Path('logging-system.md'), malformed)
    assert any(
        'SyntaxError in logging code block' in error for error in errors
    )
