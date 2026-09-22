# B3 Operational Practices

Recommendations for predictable historical extraction runs and bounded-memory
consumption of the resulting Parquet artifacts.

______________________________________________________________________

## Best Practices

### 1. Harness Fast Mode for Extensive Datasets

```python
from globaldatafinance import HistoricalQuotesB3

b3 = HistoricalQuotesB3()
# ✅ Highly recommended for processing extensive historical ranges
result = b3.extract(
    path_of_docs="/data/cotahist",
    assets_list=["ações"],
    initial_year=1986,  # Complete historical depth
    processing_mode="fast",
)
```

### 2. Segment Output Files by Asset Category

```python
from globaldatafinance import HistoricalQuotesB3

b3 = HistoricalQuotesB3()
# ✅ Recommended: generate segmented parquet artifacts per asset category
for asset in ["ações", "etf", "opções"]:
    result = b3.extract(
        path_of_docs="/data/cotahist",
        assets_list=[asset],
        initial_year=2023,
        output_filename=f"{asset}_2023",
    )
```

### 3. Monitor Free Filesystem Capacity

```python
import shutil

stats = shutil.disk_usage("/data")
free_gb = stats.free / (1024**3)

if free_gb < 5:
    print(f"⚠️  Low storage detected: {free_gb:.2f} GB available")
    # Toggle processing_mode="slow" or process narrowed annual chunks
else:
    pass
```

## Next Steps

- 📄 **[CVM Documents](cvm-docs.md)** - Guide to downloading CVM regulatory financial statements
- 💻 **[Practical Examples](examples.md)** - Explore actionable quantitative analytics workflows
- 🔧 **[API Reference](../reference/b3-api.md)** - Review comprehensive structural API definitions
- ❓ **[FAQ](faq.md)** - Answers to common installation and architectural inquiries

!!! tip "Analytical Best Practice"
    For large analysis jobs, consume Parquet in PyArrow batches to bound memory.
    Polars can be installed separately by consumers who prefer it as a
    downstream reader.
