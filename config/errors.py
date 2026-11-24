from rest_framework.views import exception_handler as drf_exception_handler

from scheduling.exceptions import Conflict


def exception_handler(exc, context):
    """Give each refused state change a stable code beside its human message."""
    response = drf_exception_handler(exc, context)
    if response is not None and isinstance(exc, Conflict):
        response.data["code"] = exc.get_codes()
    return response
