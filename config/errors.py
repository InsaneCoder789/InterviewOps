from django.http import JsonResponse
from django.views import defaults
from rest_framework.views import exception_handler as drf_exception_handler

from scheduling.exceptions import Conflict


def exception_handler(exc, context):
    """Give each refused state change a stable code beside its human message."""
    response = drf_exception_handler(exc, context)
    if response is not None and isinstance(exc, Conflict):
        response.data["code"] = exc.get_codes()
    return response


def not_found(request, exception):
    if request.path.startswith("/api/"):
        return JsonResponse({"detail": "Not found."}, status=404)
    return defaults.page_not_found(request, exception)


def server_error(request):
    if request.path.startswith("/api/"):
        return JsonResponse({"detail": "Server error."}, status=500)
    return defaults.server_error(request)
