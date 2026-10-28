# Transaction Ledger API

A FastAPI-based transaction ledger system for account management and financial transactions.

## Project Structure

```text
├── app/
│   ├── main.py           # Starts the FastAPI application
│   ├── routes/           # API endpoints (URLs and HTTP methods)
│   │   └── accounts.py   # Account creation and management APIs
│   ├── services/         # Business logic and database processing
│   │   └── account_service.py
│   ├── models/           # Database models and structure
│   │   └── account.py
│   ├── schemas/          # Request and response validation using Pydantic
│   │   └── account.py
│   ├── db/               # Database connection and session management
│   │   └── database.py
│   └── core/             # Configuration and settings
│       └── config.py
│
├── tests/                # Automated tests (pytest)
├── scripts/              # Manual scripts
├── .env                  # Environment variables and secrets (never commit)
├── requirements.txt      # Python dependencies
├── Dockerfile            # Instructions to build the Docker image
└── README.md             # Project setup and documentation
```

## Getting Started

### 1. Prerequisites
- Python 3.14+
- PostgreSQL running locally

### 2. Environment Variables
Copy `.env.example` to `.env` and edit it:
```env
PROJECT_NAME="Transaction Ledger API"
DATABASE_URL="postgresql://user@localhost:5432/app_db"
```

### 3. Installation & Run
```bash
# Install dependencies
uv sync
# Or: pip install -r requirements.txt

# Run tests
uv run pytest

# Run the server
uvicorn app.main:app --reload
# Or: uv run uvicorn app.main:app --reload
```

- **Swagger Documentation**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **Health / Root Endpoint**: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)
