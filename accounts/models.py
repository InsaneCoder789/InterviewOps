from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models


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
