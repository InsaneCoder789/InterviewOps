from zoneinfo import available_timezones

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from .models import Invitation, Profile, User


def check_password_strength(password, user, field="password"):
    try:
        validate_password(password, user)
    except DjangoValidationError as exc:
        raise serializers.ValidationError({field: exc.messages}) from exc


def password_field():
    return serializers.CharField(write_only=True, max_length=128, trim_whitespace=False)


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "username", "email", "role", "is_active"]
        read_only_fields = fields


class RegisterSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(
        validators=[UniqueValidator(User.objects.all(), lookup="iexact")]
    )
    password = serializers.CharField(write_only=True, max_length=128, trim_whitespace=False)

    class Meta:
        model = User
        # No "role": public sign-up always creates a student.
        fields = ["id", "username", "email", "password"]

    def validate_email(self, value):
        return value.lower()

    def validate(self, attrs):
        check_password_strength(
            attrs["password"], User(username=attrs["username"], email=attrs["email"]))
        return attrs

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class StatusSerializer(serializers.Serializer):
    is_active = serializers.BooleanField(required=True)

    def validate(self, attrs):
        if "is_active" not in self.initial_data:
            raise serializers.ValidationError({"is_active": ["This field is required."]})
        return attrs


class RoleSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["role"]
        extra_kwargs = {"role": {"required": True}}


class InvitationSerializer(serializers.ModelSerializer):
    status = serializers.CharField(read_only=True)

    class Meta:
        model = Invitation
        fields = ["id", "email", "role", "status", "invited_by", "created_at", "expires_at",
                  "accepted_at", "accepted_by", "revoked_at"]
        read_only_fields = [f for f in fields if f not in ("email", "role")]
        # Re-inviting is allowed; the service replaces the open invitation.
        validators = []


class AcceptInvitationSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=500)
    username = serializers.CharField(max_length=150, validators=[User.username_validator])
    password = password_field()


def check_new_account(username, email, password):
    if User.objects.filter(username=username).exists():
        raise serializers.ValidationError(
            {"username": ["A user with that username already exists."]})
    check_password_strength(password, User(username=username, email=email))


class PasswordChangeSerializer(serializers.Serializer):
    current_password = password_field()
    new_password = password_field()


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField(max_length=64)
    token = serializers.CharField(max_length=128)
    password = password_field()


class TagListField(serializers.ListField):
    """Short labels, trimmed, lower-cased and without repeats, so they can be matched."""

    def __init__(self, **kwargs):
        super().__init__(child=serializers.CharField(max_length=60), **kwargs)

    def to_internal_value(self, data):
        values = super().to_internal_value(data)
        unique = list(dict.fromkeys(value.lower() for value in values))
        if len(unique) > 15:
            raise serializers.ValidationError("Use at most 15 entries.")
        return unique


class ProfileSerializer(serializers.ModelSerializer):
    user = serializers.IntegerField(source="user_id", read_only=True)
    username = serializers.CharField(source="user.username", read_only=True)
    role = serializers.CharField(source="user.role", read_only=True)
    target_roles = TagListField(required=False)
    topics = TagListField(required=False)

    class Meta:
        model = Profile
        # No email address: other members see profiles.
        fields = ["user", "username", "role", "display_name", "headline", "bio",
                  "experience_level", "target_roles", "topics", "timezone"]

    def validate_timezone(self, value):
        if value not in available_timezones():
            raise serializers.ValidationError("Use an IANA name such as Asia/Kolkata.")
        return value
