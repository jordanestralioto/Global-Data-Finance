"""Structural Inspector Script.

Implementation of the 'structural-inspector' skill for the Antigravity Agent.
"""

import argparse
import csv
import json
import os
from pathlib import Path
from typing import Any

import polars


class StructuralInspector:
    """Skill implementation: structural-inspector.

    Path: .agents/skills/structural-inspector/scripts/inspector.py
    Standard: Google Antigravity Skill Protocol (2026)
    """

    def inspect(self, file_path: str) -> dict[str, Any]:
        path = Path(file_path)
        if not path.exists():
            return {'error': f'File not found: {file_path}'}

        size_bytes = path.stat().st_size
        extension = path.suffix.lower()

        meta = {
            'file': path.name,
            'path': str(path.absolute()),
            'size_bytes': size_bytes,
            'size_mb': round(size_bytes / (1024 * 1024), 2),
            'format': extension.replace('.', ''),
            'encoding': None,
            'delimiter': None,
        }

        try:
            if extension == '.csv' or extension == '.txt':
                return self._inspect_csv(path, meta)
            if extension == '.parquet':
                return self._inspect_parquet(path, meta)
            if extension in ['.xlsx', '.xls']:
                return self._inspect_excel(path, meta)
            return {
                'error': f'Unsupported format: {extension}',
                'meta': meta,
            }
        except (
            OSError,
            ValueError,
            csv.Error,
            polars.exceptions.PolarsError,
        ) as e:
            return {'error': str(e), 'meta': meta}

    def _inspect_csv(self, path: Path, meta: dict[str, Any]) -> dict[str, Any]:
        try:
            with open(path, 'rb') as f:
                # Sniffing maior para garantir detecção de delimitadores em arquivos largos
                raw_head = f.read(20000)

            # Detecção de Encoding Robusta
            encoding = 'utf-8'
            try:
                raw_head.decode('utf-8')
            except UnicodeDecodeError:
                encoding = (
                    'latin1'  # Fallback para arquivos regulatórios legados
                )

            meta['encoding'] = encoding
            text_head = raw_head.decode(encoding)

            # Sniffer aprimorado
            try:
                dialect = csv.Sniffer().sniff(text_head)
                delimiter = dialect.delimiter
            except csv.Error:
                counts = {
                    sep: text_head.count(sep) for sep in [';', ',', '\t', '|']
                }
                delimiter = max(counts, key=lambda k: counts[k])

            meta['delimiter'] = delimiter

            # Polars Scan com inferência de tipo agressiva
            # Em 2026, scan_csv é o motor de busca primário
            lz = polars.scan_csv(
                path,
                encoding='utf8' if encoding == 'utf-8' else 'utf8-lossy',
                separator=delimiter,
                infer_schema_length=1000,  # Aumentado para precisão
                ignore_errors=True,
                truncate_ragged_lines=True,  # Estabilidade para arquivos corrompidos
            )

            return self._build_report(lz, meta)

        except (
            OSError,
            ValueError,
            csv.Error,
            polars.exceptions.PolarsError,
        ) as e:
            return {
                'error': f'CSV Hunter-Inspection failed: {e!s}',
                'meta': meta,
            }

    def _build_report(
        self,
        lz: polars.LazyFrame,
        meta: dict[str, Any],
        is_sample: bool = False,
    ) -> dict[str, Any]:
        schema = lz.collect_schema()

        # Sampling inteligente: Head + Tail para detectar se o final do arquivo muda de padrão
        df_sample = polars.concat([lz.head(1000), lz.tail(1000)]).collect()
        total_rows = df_sample.height

        columns_report = []
        for name, dtype in schema.items():
            col_data = df_sample[name]
            n_unique = col_data.n_unique()
            null_count = col_data.null_count()
            unique_ratio = n_unique / total_rows if total_rows > 0 else 0

            suggestion = None
            dtype_str = str(dtype)

            # Inteligência de Tradução (The Hunter)
            if dtype_str == 'String':
                # 1. Sugestão de Categorical (Otimização de Memória)
                if unique_ratio < 0.15 and n_unique < 100:
                    suggestion = 'OPTIMIZE: Convert to Categorical (High compression potential)'

                # 2. Detecção de Datas ocultas em Strings (Essencial para Finanças)
                sample_val = str(col_data[0]) if total_rows > 0 else ''
                if (
                    any(char in sample_val for char in ['-', '/'])
                    and len(sample_val) >= 8
                ):
                    suggestion = 'PARSE: Potential DateTime string detected'

            # 3. Detecção de Inteiros que poderiam ser menores (SmallInt)
            elif dtype_str in ['Int64', 'Float64']:
                if col_data.max() < 32767 and col_data.min() > -32768:
                    suggestion = 'OPTIMIZE: Downcast to Int16'

            columns_report.append(
                {
                    'column': name,
                    'type': dtype_str,
                    'stats': {
                        'unique_sample': n_unique,
                        'null_rate': round(null_count / total_rows, 4)
                        if total_rows > 0
                        else 0,
                        'cardinality': round(unique_ratio, 4),
                    },
                    'insight': suggestion,
                }
            )

        return {
            'meta': meta,
            'schema_blueprint': columns_report,
            'engine_assessment': {
                'strategy': 'Lazy Scan + Predicate Pushdown',
                'recommended_n_threads': os.cpu_count(),
                'estimated_read_speed': 'High (Zero-copy)',
                'source_is_sample': is_sample,
            },
        }

    def _inspect_parquet(
        self, path: Path, meta: dict[str, Any]
    ) -> dict[str, Any]:
        lz = polars.scan_parquet(path)
        return self._build_report(lz, meta)

    def _inspect_excel(
        self, path: Path, meta: dict[str, Any]
    ) -> dict[str, Any]:
        # Excel is not fully lazy in Polars yet, `read_excel` is eager but optimized with Calamine.
        # We will read with limit just to inspector
        # Note: Polars uses `read_excel` which loads a sheet.
        try:
            # We try to read a small amount if possible, but read_excel reads the sheet.
            # Using 'python-calamine' engine is much faster.
            df = polars.read_excel(
                path, engine='calamine', read_options={'n_rows': 1000}
            )
            lz = df.lazy()
            return self._build_report(lz, meta, is_sample=True)
        except (
            ImportError,
            OSError,
            ValueError,
            polars.exceptions.PolarsError,
        ) as e:
            return {
                'error': f'Excel inspection failed: {e!s}',
                'meta': meta,
            }


def main() -> None:
    parser = argparse.ArgumentParser(description='Structural Inspector')
    parser.add_argument(
        '--path', required=True, help='Path to the file to inspect'
    )
    args = parser.parse_args()

    inspector = StructuralInspector()
    report = inspector.inspect(args.path)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
