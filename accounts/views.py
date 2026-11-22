import logging

from django.db import IntegrityError, transaction
from rest_framework import generics, status
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

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

    def perform_create(self, serializer):
        try:
            with transaction.atomic():
                serializer.save()
        except IntegrityError as exc:
            # Two sign-ups can both pass the uniqueness check; the database decides.
            raise ValidationError({"detail": "Username or email already in use."}) from exc


class LoginView(ObtainAuthToken):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth"


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
