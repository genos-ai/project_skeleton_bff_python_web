# Data Directory

Runtime data and artifacts. Not tracked in git (except `.gitkeep` files).

## Structure

| Folder | Purpose |
|--------|---------|
| `logs/` | Application logs |
| `cache/` | Temporary/cached files |

## Guidelines

- **logs/**: Application logs, rotated automatically
- **cache/**: Temporary files, safe to delete

All contents are gitignored except `.gitkeep` placeholder files.
