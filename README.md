# BFF Python Web Application

Backend-for-Frontend skeleton template with Python (FastAPI) backend and React (Vite) frontend.

## Architecture

This project follows the BFF (Backend-for-Frontend) pattern:

- **Backend**: Python 3.12+ with FastAPI
- **Frontend**: React with Vite, TypeScript, Tailwind CSS
- **Database**: PostgreSQL with SQLAlchemy (async)
- **Cache/Queue**: Redis with Taskiq

See [Architecture Standards](docs/04-references/architecture-standards/00-overview.md) for complete documentation.

## Project Structure

```
.
├── config/                 # Configuration files
│   ├── .env.example       # Environment variables template
│   └── settings/          # YAML configuration files
├── docs/                   # Documentation
├── modules/
│   ├── backend/           # FastAPI backend
│   │   ├── api/           # HTTP endpoints
│   │   ├── core/          # Shared utilities
│   │   ├── models/        # Database models
│   │   ├── repositories/  # Data access layer
│   │   ├── schemas/       # Pydantic schemas
│   │   ├── services/      # Business logic
│   │   └── tasks/         # Background tasks
│   └── frontend/          # React frontend
│       └── src/
├── tests/                  # Test suite
├── scripts/                # Utility scripts
└── data/                   # Runtime data (logs, cache, uploads)
```

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 20+
- PostgreSQL 16+
- Redis 7+

### Backend Setup

Using **uv** (recommended for web apps - see [environment management](docs/04-references/architecture-standards/13-development-workflow.md#python-environment-management)):

```bash
# Install uv (one-time)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create environment and install
uv venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
uv pip install -r requirements.txt

# Configure environment
cp config/.env.example config/.env
# Edit config/.env with your settings

# Run backend
uvicorn modules.backend.main:app --reload --port 8000
```

### Frontend Setup

```bash
cd modules/frontend
npm install
npm run dev
```

### Access Points

| Service | URL |
|---------|-----|
| Backend API | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |
| Frontend | http://localhost:5173 |

## Development

### Code Quality

```bash
# Format
black modules/backend tests
isort modules/backend tests

# Lint
flake8 modules/backend tests

# Type check
mypy modules/backend
```

### Testing

```bash
# Run all tests
pytest

# With coverage
pytest --cov=modules/backend

# Specific markers
pytest -m unit
pytest -m integration
```

## Architecture Standards

This project follows documented architecture standards:

- [Core Principles](docs/04-references/architecture-standards/01-core-principles.md)
- [Backend Architecture](docs/04-references/architecture-standards/03-backend-architecture.md)
- [Python Coding Standards](docs/04-references/architecture-standards/10-python-coding-standards.md)
- [Frontend Architecture](docs/04-references/architecture-standards/07-frontend-architecture.md)
- [TypeScript Standards](docs/04-references/architecture-standards/11-typescript-coding-standards.md)

## License

[Add license here]
