from django.contrib.auth.models import AbstractUser, UserManager
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.utils import timezone


class InterviewUserManager(UserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault("role", "admin")
        return super().create_superuser(username, email, password, **extra_fields)


class User(AbstractUser):
    class Role(models.TextChoices):
        STUDENT = "student"
        MENTOR = "mentor"
        ADMIN = "admin"

    email = models.EmailField(unique=True)
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.STUDENT)

    objects = InterviewUserManager()

    REQUIRED_FIELDS = ["email"]

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(role__in=["student", "mentor", "admin"]),
                name="user_role_valid",
            )
        ]


class Invitation(models.Model):
    email = models.EmailField()
    role = models.CharField(max_length=10, choices=User.Role.choices)
    # Part of the signed token; changing or revoking the row invalidates the link.
    nonce = models.CharField(max_length=32)
    invited_by = models.ForeignKey(User, models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    accepted_by = models.ForeignKey(
        User, models.PROTECT, null=True, blank=True, related_name="+")
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["email"],
                condition=models.Q(accepted_at__isnull=True, revoked_at__isnull=True),
                name="invitation_one_open_per_email",
            )
        ]

    @property
    def status(self):
        if self.accepted_at:
            return "accepted"
        if self.revoked_at:
            return "revoked"
        return "expired" if self.expires_at <= timezone.now() else "pending"

    def is_pending(self):
        return self.status == "pending"


class Profile(models.Model):
    class Level(models.TextChoices):
        STUDENT = "student"
        ENTRY = "entry"
        MID = "mid"
        SENIOR = "senior"

    user = models.OneToOneField(User, models.CASCADE, primary_key=True, related_name="profile")
    display_name = models.CharField(max_length=80, blank=True)
    headline = models.CharField(max_length=120, blank=True)
    bio = models.TextField(max_length=2000, blank=True)
    experience_level = models.CharField(max_length=10, choices=Level.choices, blank=True)
    # For a student: roles aimed for and topics to practise. For a mentor: topics offered.
    target_roles = ArrayField(models.CharField(max_length=60), default=list, blank=True)
    topics = ArrayField(models.CharField(max_length=60), default=list, blank=True)
    timezone = models.CharField(max_length=64, default="UTC")
    updated_at = models.DateTimeField(auto_now=True)
