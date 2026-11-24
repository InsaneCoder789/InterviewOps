import logging

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .authentication import expires_at
from .models import User
from .permissions import IsAdminRole
from .serializers import RegisterSerializer, RoleSerializer, UserSerializer

logger = logging.getLogger("interviewops.accounts")


class RegisterView(generics.CreateAPIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"
    serializer_class = RegisterSerializer

    def create(self, request, *args, **kwargs):
        if not settings.ALLOW_REGISTRATION:
            return Response(
                {"detail": "Registration is closed.", "code": "registration_closed"},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        try:
            with transaction.atomic():
                serializer.save()
        except IntegrityError as exc:
            # Two sign-ups can both pass the uniqueness check; the database decides.
            raise ValidationError({"detail": "Username or email already in use."}) from exc


class LoginView(ObtainAuthToken):
    # A stale token left in the client must not stop its owner signing in again.
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        with transaction.atomic():
            # Two logins at once must not both replace an expired token.
            User.objects.select_for_update(no_key=True).get(pk=user.pk)
            token = Token.objects.filter(user=user).first()
            if token and expires_at(token) <= timezone.now():
                token.delete()
                token = None
            token = token or Token.objects.create(user=user)
        return Response({"token": token.key, "expires_at": expires_at(token)})

    def get_authenticate_header(self, request):
        return "Token"


class LogoutView(APIView):
    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(generics.RetrieveAPIView):
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user


class UserListView(generics.ListAPIView):
    permission_classes = [IsAdminRole]
    serializer_class = UserSerializer
    queryset = User.objects.all()
    filterset_fields = ["role"]


class UserRoleView(APIView):
    permission_classes = [IsAdminRole]

    def patch(self, request, pk):
        from scheduling.services import change_role

        serializer = RoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = change_role(actor=request.user, user_id=pk, role=serializer.validated_data["role"])
        return Response(UserSerializer(user).data)
