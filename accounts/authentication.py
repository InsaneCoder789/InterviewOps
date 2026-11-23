from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed


def expires_at(token):
    return token.created + timedelta(hours=settings.TOKEN_TTL_HOURS)


class ExpiringTokenAuthentication(TokenAuthentication):
    """Reject tokens older than TOKEN_TTL_HOURS. Age counts from creation, not last use."""

    def authenticate_credentials(self, key):
        user, token = super().authenticate_credentials(key)
        if expires_at(token) <= timezone.now():
            raise AuthenticationFailed("Token has expired.")
        return user, token
