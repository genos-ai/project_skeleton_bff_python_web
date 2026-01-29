# Data Directory

This directory contains all data files for the project.

## Structure

| Folder | Purpose | Git Tracked |
|--------|---------|-------------|
| `raw/` | Original downloaded data (market data, price feeds) | No |
| `processed/` | Cleaned and transformed data | No |
| `external/` | Third-party reference data | No |
| `cache/` | Temporary processing files | No |
| `samples/` | Small sample datasets for testing | Yes (keep < 10MB) |

## Guidelines

### What to Put Where

- **raw/**: Untouched source data. Never modify files here.
- **processed/**: Output of data pipelines. Can be regenerated from raw.
- **external/**: Data from external sources (lookup tables, reference data).
- **cache/**: Temporary files during processing. Safe to delete.
- **samples/**: Small representative datasets for unit/integration tests.

### File Formats

Recommended formats:
- **Parquet**: Columnar data (time series, OHLCV)
- **CSV**: Simple tabular data, human-readable
- **JSON**: Configuration, metadata
- **Pickle**: Python objects (use sparingly, not portable)

### Naming Convention

```
{source}_{asset}_{timeframe}_{start}_{end}.parquet

Examples:
- binance_btcusdt_1h_20230101_20231231.parquet
- yahoo_spy_1d_20200101_20231231.parquet
```

### Size Management

- Files > 100MB should be in `.gitignore`
- Use `samples/` for test data (keep total < 50MB)
- Consider Git LFS for medium files (10-100MB) if needed
- Large datasets: Document download scripts in `scripts/`

### Regenerating Data

If data needs to be regenerated:
1. Check `scripts/` for download/processing scripts
2. See `docs/` for data pipeline documentation
3. Raw data should be downloadable from source
