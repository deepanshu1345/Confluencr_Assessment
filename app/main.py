from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.db.database import init_db_pool, close_db_pool
from app.core.exceptions import (
    AccountNotFoundError,
    DuplicateReferenceError,
    InsufficientFundsError,
)
from app.routes import accounts, transactions, transfers


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize DB pool & create tables
    await init_db_pool()
    yield
    # Shutdown: Close DB pool connections
    await close_db_pool()


app = FastAPI(
    title="Transaction Ledger API",
    description="A simplified transaction ledger system for account management and transactions.",
    version="0.1.0",
    lifespan=lifespan,
)


# Centralized exception handlers for 400 Bad Request
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = exc.errors()
    details = []
    for err in errors:
        loc = " -> ".join(str(l) for l in err.get("loc", []))
        msg = err.get("msg", "Invalid value")
        details.append(f"{loc}: {msg}")

    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "error": "Bad Request",
            "message": "Invalid payload: " + (details[0] if details else "Request validation failed"),
            "details": details,
        },
    )


@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "error": "Bad Request",
            "message": str(exc),
        },
    )


def _error(code: int, error: str, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=code, content={"error": error, "message": str(exc)})


@app.exception_handler(AccountNotFoundError)
async def account_not_found_handler(request: Request, exc: AccountNotFoundError) -> JSONResponse:
    return _error(status.HTTP_404_NOT_FOUND, "Not Found", exc)


@app.exception_handler(InsufficientFundsError)
async def insufficient_funds_handler(request: Request, exc: InsufficientFundsError) -> JSONResponse:
    return _error(status.HTTP_400_BAD_REQUEST, "Insufficient Funds", exc)


@app.exception_handler(DuplicateReferenceError)
async def duplicate_reference_handler(request: Request, exc: DuplicateReferenceError) -> JSONResponse:
    return _error(status.HTTP_409_CONFLICT, "Conflict", exc)


_HTTP_ERROR_NAMES = {
    404: "Not Found",
    405: "Method Not Allowed",
}


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    # Unknown routes and unsupported methods (e.g. PUT/DELETE on transactions)
    # use the same error shape as every other response.
    error = _HTTP_ERROR_NAMES.get(exc.status_code, "Error")
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": error, "message": str(exc.detail)},
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Never leak internals; the database transaction has already rolled back.
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "Internal Server Error", "message": "An unexpected error occurred"},
    )


# Register routes
app.include_router(accounts.router, prefix="/api/v1")
app.include_router(transactions.router, prefix="/api/v1")
app.include_router(transfers.router, prefix="/api/v1")


@app.get("/", tags=["Root"])
async def root():
    return {
        "message": "Welcome to the Transaction Ledger API",
        "docs_url": "/docs",
        "accounts_url": "/api/v1/accounts",
    }
