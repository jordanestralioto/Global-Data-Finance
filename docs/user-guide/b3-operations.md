# Boas práticas B3

Recomendações para executar extrações históricas com previsibilidade e consumir
os artefatos Parquet com uso controlado de recursos.

______________________________________________________________________

## Boas Práticas

### 1. Use Modo Fast para Grandes Volumes

```python
from globaldatafinance import HistoricalQuotesB3

b3 = HistoricalQuotesB3()
# ✅ Recomendado para grandes volumes
result = b3.extract(
    path_of_docs="/data/cotahist",
    assets_list=["ações"],
    initial_year=1986,  # 23+ anos
    processing_mode="fast",
)
```

### 2. Separe Extrações por Classe de Ativo

```python
from globaldatafinance import HistoricalQuotesB3

b3 = HistoricalQuotesB3()
# ✅ Recomendado: arquivos separados por classe
for asset in ["ações", "etf", "opções"]:
    result = b3.extract(
        path_of_docs="/data/cotahist",
        assets_list=[asset],
        initial_year=2023,
        output_filename=f"{asset}_2023",
    )
```

### 3. Verifique Espaço em Disco

```python
import shutil

stats = shutil.disk_usage("/data")
free_gb = stats.free / (1024**3)

if free_gb < 5:
    print(f"⚠️  Pouco espaço: {free_gb:.2f} GB")
    # Use modo slow ou processe menos anos
else:
    # Prosseguir normalmente
    pass
```

______________________________________________________________________

## Próximos Passos

- 📄 **[Documentos CVM](cvm-docs.md)** - Aprenda a baixar documentos CVM
- 💻 **[Exemplos Práticos](examples.md)** - Veja casos de uso completos
- 🔧 **[API Reference](../reference/b3-api.md)** - Documentação técnica detalhada
- ❓ **[FAQ](faq.md)** - Perguntas frequentes

______________________________________________________________________

!!! tip "Dica de Análise"
    Após extrair para Parquet, use leitura em batches com PyArrow para limitar a
    memória de análises grandes. Polars pode ser instalado separadamente por
    consumidores que o prefiram como leitor downstream.
