import logging
import time
import uuid

logger = logging.getLogger("interviewops.request")


class RequestLogMiddleware:
    """One line per request. Never logs bodies, query strings or auth headers."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = uuid.uuid4().hex[:12]
        started = time.monotonic()
        response = self.get_response(request)
        user = getattr(request, "user", None)
        logger.info(
            "request_id=%s method=%s path=%r status=%s user_id=%s duration_ms=%.1f",
            request_id,
            request.method,
            request.path,
            response.status_code,
            getattr(user, "pk", None),
            (time.monotonic() - started) * 1000,
        )
        response["X-Request-ID"] = request_id
        return response
