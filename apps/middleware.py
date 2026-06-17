"""
FastAPI middleware for request correlation IDs and request/response logging.

Uses stdlib only. Integrates with logging_config.py via contextvars.
"""

import time
import uuid
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from apps.logging_config import set_request_context, clear_request_context

logger = logging.getLogger("studio_api.http")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Per-request middleware that:
    1. Generates/inherits a request ID (X-Request-ID header)
    2. Binds request_id + endpoint into contextvars so all log calls include them
    3. Logs method, path, status, duration_ms on completion
    4. Adds X-Request-ID to response headers
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        # Accept client-provided ID or generate a short UUID hex
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        endpoint = request.url.path

        clear_request_context()
        set_request_context(request_id=request_id, endpoint=endpoint)

        start = time.monotonic()
        response: Response = await call_next(request)
        duration_ms = round((time.monotonic() - start) * 1000)

        logger.info(
            "request_completed method=%s status=%s duration_ms=%d",
            request.method,
            response.status_code,
            duration_ms,
        )

        response.headers["X-Request-ID"] = request_id
        return response
