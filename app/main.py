
import logging
import re
import time
import uuid

from fastapi import FastAPI, Request

from app.core.loggin import configure_logging
from app.core.request_context import (
    set_request_id,
    reset_request_id,
)
from app.services.search.client import check_search_connection

configure_logging()

logger = logging.getLogger("enterprise-ai")

app = FastAPI(
    title="Enterprise AI Intelligence Platform",
    version="0.1.0",
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    incoming_id = request.headers.get("X-Request-ID")

    # Accept only safe, bounded request identifiers.
    if incoming_id and re.fullmatch(r"[A-Za-z0-9._-]{1,128}", incoming_id):
        request_id = incoming_id
    else:
        request_id = str(uuid.uuid4())

    token = set_request_id(request_id)
    request.state.request_id = request_id
    start_time = time.perf_counter()

    logger.info(
        "request_started",
        extra={
            "event": "request_started",
            "method": request.method,
            "path": request.url.path,
        },
    )

    try:
        response = await call_next(request)

        response.headers["X-Request-ID"] = request_id

        logger.info(
            "request_completed",
            extra={
                "event": "request_completed",
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round(
                    (time.perf_counter() - start_time) * 1000,
                    2,
                ),
            },
        )

        return response

    except Exception:
        logger.exception(
            "request_failed",
            extra={
                "event": "request_failed",
                "method": request.method,
                "path": request.url.path,
                "duration_ms": round(
                    (time.perf_counter() - start_time) * 1000,
                    2,
                ),
            },
        )
        raise

    finally:
        reset_request_id(token)


@app.get("/api/v1/health")
def health_check(request: Request):
    return {
        "status": "healthy",
        "service": "enterprise-ai",
        "request_id": request.state.request_id,
    }


@app.get("/api/v1/health/azure-search")
def azure_search_health():
    try:
        result = check_search_connection()
        return {
            "status": "healthy",
            "azure_search": result,
        }
    except Exception:
        logger.exception("Azure Search health check failed")
        return {
            "status": "unhealthy",
            "azure_search": {
                "connected": False,
            },
        }
