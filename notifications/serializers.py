from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    email = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = [
            "id",
            "kind",
            "status",
            "recipient",
            "email",
            "booking",
            "invitation",
            "attempts",
            "available_at",
            "sent_at",
            "last_error",
            "created_at",
        ]

    def get_email(self, notification):
        owner = notification.recipient or notification.invitation
        return owner.email if owner else ""
