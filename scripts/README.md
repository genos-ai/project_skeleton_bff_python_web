# Scripts

This directory contains utility scripts for development and operations.

## Guidelines

- Scripts in this directory are the **only** place where helper/wrapper scripts are permitted
- Each script should have a clear, single purpose
- All scripts must include `--verbose` and `--debug` options
- Document usage in docstrings or comments

## Naming Convention

- Use lowercase with underscores: `script_name.py`
- Prefix with category when applicable:
  - `db_` - Database scripts
  - `deploy_` - Deployment scripts
  - `dev_` - Development utilities
  - `test_` - Testing utilities

## Example Script Structure

```python
#!/usr/bin/env python3
"""
Script description.

Usage:
    python scripts/script_name.py --option value
"""

import click

@click.command()
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose output')
@click.option('--debug', is_flag=True, help='Enable debug output')
def main(verbose: bool, debug: bool):
    """Script entry point."""
    # Implementation
    pass

if __name__ == '__main__':
    main()
```
