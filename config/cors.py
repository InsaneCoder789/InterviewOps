from django.conf import settings
from django.http import HttpResponse
from django.utils.cache import patch_vary_headers

PREFIXES = ("/api/", "/health/")
EXPOSED_HEADERS = "Retry-After, X-Request-ID"
ALLOWED_METHODS = "GET, POST, PATCH, OPTIONS"
ALLOWED_HEADERS = "Authorization, Content-Type"


class CorsMiddleware:
    """Let the listed browser origins call the API.

    No wildcard and no credentials: the API authenticates with a header that the
    client sets itself, never with cookies.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.path.startswith(PREFIXES):
            return self.get_response(request)
        origin = request.headers.get("Origin")
        allowed = origin in settings.CORS_ALLOWED_ORIGINS
        preflight = (
            request.method == "OPTIONS" and "Access-Control-Request-Method" in request.headers
        )
        if allowed and preflight:
            # A preflight carries no token, so it is answered before authentication.
            response = HttpResponse(status=204)
            response["Access-Control-Allow-Methods"] = ALLOWED_METHODS
            response["Access-Control-Allow-Headers"] = ALLOWED_HEADERS
            response["Access-Control-Max-Age"] = "600"
        else:
            response = self.get_response(request)
        patch_vary_headers(response, ["Origin"])
        if allowed:
            response["Access-Control-Allow-Origin"] = origin
            response["Access-Control-Expose-Headers"] = EXPOSED_HEADERS
        return response
