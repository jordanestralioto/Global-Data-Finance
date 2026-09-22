# Exemplos Práticos

Esta página apresenta exemplos completos e práticos de uso do Global-Data-Finance em cenários reais.

______________________________________________________________________

## Exemplo 1: Download Completo de DFP

Baixar demonstrações financeiras padronizadas de empresas brasileiras.

```python
from globaldatafinance import FundamentalStocksDataCVM

# Criar cliente
cvm = FundamentalStocksDataCVM()

# Download de DFP com extração automática
cvm.download(
    destination_path="/home/usuario/dados_financeiros/dfp",
    list_docs=["DFP"],
    initial_year=2020,
    last_year=2023,
    automatic_extractor=True  # Converte os arquivos baixados para Parquet
)

print("✓ Download e extração concluídos!")
```

______________________________________________________________________

## Exemplo 2: Extração de Ações e ETFs

Extrair cotações históricas de ações e ETFs com alto desempenho nos mercados à
vista (010) e fracionário (020).

```python
from globaldatafinance import HistoricalQuotesB3
import time

# Criar cliente
b3 = HistoricalQuotesB3()

# Medir tempo de execução
start_time = time.time()

# Extrair dados
result = b3.extract(
    path_of_docs="/home/usuario/cotahist",
    assets_list=["ações", "etf"],
    initial_year=2021,
    last_year=2023,
    destination_path="/home/usuario/cotacoes",
    output_filename="acoes_etf_2021_2023",
    processing_mode="fast"
)

elapsed = time.time() - start_time

# Exibir resultados
if result['success']:
    print(f"✓ Extração concluída em {elapsed:.2f}s")
    print(f"  Registros: {result['total_records']:,}")
    print(f"  Throughput: {result['total_records']/elapsed:,.0f} registros/s")
    print(f"  Arquivo: {result['output_file']}")
```

______________________________________________________________________

## Exemplo 3: Pipeline Completo

Pipeline completo de download CVM e extração B3.

```python
from globaldatafinance import FundamentalStocksDataCVM, HistoricalQuotesB3
import os


# Diretórios
base_dir = "/home/usuario/dados_financeiros"
cvm_dir = os.path.join(base_dir, "cvm")
cotahist_dir = os.path.join(base_dir, "cotahist")
output_dir = os.path.join(base_dir, "processado")

# === ETAPA 1: Download CVM ===
print("=" * 60)
print("ETAPA 1: Download de Documentos CVM")
print("=" * 60)

cvm = FundamentalStocksDataCVM()
cvm.download(
    destination_path=cvm_dir,
    list_docs=["DFP", "ITR"],
    initial_year=2022,
    last_year=2023,
    automatic_extractor=True
)

# === ETAPA 2: Extração B3 ===
print("\n" + "=" * 60)
print("ETAPA 2: Extração de Cotações B3")
print("=" * 60)

b3 = HistoricalQuotesB3()
result = b3.extract(
    path_of_docs=cotahist_dir,
    assets_list=["ações", "etf"],
    initial_year=2022,
    last_year=2023,
    destination_path=output_dir,
    output_filename="cotacoes_2022_2023"
)

# === RESUMO ===
print("\n" + "=" * 60)
print("RESUMO FINAL")
print("=" * 60)
print(f"✓ Pipeline concluído!")
print(f"✓ Dados CVM salvos em: {cvm_dir}")
print(f"✓ Cotações B3 salvas em: {result['output_file']}")
```

______________________________________________________________________

## Exemplo 4: Análise com Pandas

Analisar dados extraídos usando Pandas. Pandas é uma dependência downstream
opcional e deve ser instalado separadamente:

```bash
python -m pip install pandas
```

```python
import pandas as pd
from globaldatafinance import HistoricalQuotesB3

# 1. Extrair dados
b3 = HistoricalQuotesB3()
result = b3.extract(
    path_of_docs="/data/cotahist",
    assets_list=["ações"],
    initial_year=2023,
    output_filename="acoes_2023"
)

# 2. Carregar Parquet
df = pd.read_parquet(result['output_file'])

# 3. Análises básicas
print("=" * 60)
print("ANÁLISE DE DADOS")
print("=" * 60)

print(f"\nTotal de registros: {len(df):,}")
print(f"Período: {df['data_pregao'].min()} a {df['data_pregao'].max()}")
print(f"Ativos únicos: {df['ticker'].nunique()}")

# Top 10 ativos por volume
top_volume = df.groupby('ticker')['volume_total'].sum().nlargest(10)
print("\nTop 10 ativos por volume:")
for ticker, volume in top_volume.items():
    print(f"  {ticker}: R$ {volume/1e9:.2f}B")

# Estatísticas de preço
print(f"\nEstatísticas de preço de fechamento:")
print(df['preco_fechamento'].describe())
```

______________________________________________________________________

## Exemplo 5: Processamento em Batches com PyArrow

Usar PyArrow para processar Parquet em batches com memória limitada.

```python
import pyarrow.compute as pc
import pyarrow.parquet as pq
from globaldatafinance import HistoricalQuotesB3

# Extrair dados
b3 = HistoricalQuotesB3()
result = b3.extract(
    path_of_docs="/data/cotahist",
    assets_list=["ações"],
    initial_year=2020,
    last_year=2023
)

# Projetar e filtrar sem carregar o arquivo inteiro
parquet = pq.ParquetFile(result['output_file'])
for batch in parquet.iter_batches(
    batch_size=200_000,
    columns=['ticker', 'preco_minimo', 'preco_maximo'],
):
    petr4 = batch.filter(pc.equal(batch.column('ticker'), 'PETR4'))
    if petr4.num_rows:
        print(petr4)
```

______________________________________________________________________

## Exemplo 6: Automação com Script

Script completo para automação de downloads.

```python
#!/usr/bin/env python3
"""
Script de automação para download e processamento de dados financeiros.
"""

import argparse
import sys
from pathlib import Path
from globaldatafinance import FundamentalStocksDataCVM, HistoricalQuotesB3

def main():
    parser = argparse.ArgumentParser(description="Download dados financeiros")
    parser.add_argument("--tipo", choices=["cvm", "b3", "ambos"], required=True)
    parser.add_argument("--destino", type=str, required=True)
    parser.add_argument("--ano-inicial", type=int, default=2022)
    parser.add_argument("--ano-final", type=int, default=2023)
    parser.add_argument("--verbose", action="store_true")

    args = parser.parse_args()

    # Criar diretório de destino
    dest_path = Path(args.destino)
    dest_path.mkdir(parents=True, exist_ok=True)

    try:
        if args.tipo in ["cvm", "ambos"]:
            print("Baixando documentos CVM...")
            cvm = FundamentalStocksDataCVM()
            cvm.download(
                destination_path=str(dest_path / "cvm"),
                list_docs=["DFP", "ITR"],
                initial_year=args.ano_inicial,
                last_year=args.ano_final,
                automatic_extractor=True
            )

        if args.tipo in ["b3", "ambos"]:
            print("Extraindo cotações B3...")
            b3 = HistoricalQuotesB3()
            result = b3.extract(
                path_of_docs=str(dest_path / "cotahist"),
                assets_list=["ações", "etf"],
                initial_year=args.ano_inicial,
                last_year=args.ano_final,
                destination_path=str(dest_path / "cotacoes")
            )

            if result['success']:
                print(f"✓ Extraídos {result['total_records']:,} registros")

        print("✓ Processamento concluído!")
        return 0

    except Exception as e:
        print(f"✗ Erro: {e}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
```

**Uso**:

```bash
# Download apenas CVM
python script.py --tipo cvm --destino /data --ano-inicial 2022

# Download apenas B3
python script.py --tipo b3 --destino /data --ano-inicial 2020 --ano-final 2023

# Download de ambos
python script.py --tipo ambos --destino /data --verbose
```

______________________________________________________________________

## Exemplo 7: Integração com Jupyter Notebook

Usar Global-Data-Finance em notebooks Jupyter para análise interativa.

!!! note "Dependências Opcionais"

    Pandas e as bibliotecas de visualização utilizadas neste exemplo
    (`matplotlib`, `seaborn`) são dependências externas opcionais:

    ```bash
    python -m pip install pandas matplotlib seaborn
    ```

```ipython
# Célula 1: Imports e configuração
from globaldatafinance import HistoricalQuotesB3
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

sns.set_style("darkgrid")
%matplotlib inline

# Célula 2: Extrair dados
b3 = HistoricalQuotesB3()
result = b3.extract(
    path_of_docs="/data/cotahist",
    assets_list=["ações"],
    initial_year=2023
)

# Célula 3: Carregar e filtrar
df = pd.read_parquet(result['output_file'])
petr4 = df[df['ticker'] == 'PETR4']

# Célula 4: Visualizar
plt.figure(figsize=(14, 6))
plt.plot(petr4['data_pregao'], petr4['preco_fechamento'])
plt.title('PETR4 - Preço de Fechamento (2023)', fontsize=16)
plt.xlabel('Data')
plt.ylabel('Preço (R$)')
plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.show()

# Célula 5: Análise de volume
plt.figure(figsize=(14, 6))
plt.bar(petr4['data_pregao'], petr4['volume_total'] / 1e6, alpha=0.7)
plt.title('PETR4 - Volume Negociado (2023)', fontsize=16)
plt.xlabel('Data')
plt.ylabel('Volume (Milhões R$)')
plt.tight_layout()
plt.show()
```

______________________________________________________________________

## Próximos Passos

- 📄 **[Documentos CVM](cvm-docs.md)** - Guia detalhado da API CVM
- 📈 **[Cotações B3](b3-docs.md)** - Guia detalhado da API B3
- ❓ **[FAQ](faq.md)** - Perguntas frequentes
- 🔧 **[Uso Avançado](../dev-guide/advanced-usage.md)** - Técnicas avançadas
