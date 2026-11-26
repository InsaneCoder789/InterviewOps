from django.core.management.base import BaseCommand, CommandError

from notifications.health import queue_health


class Command(BaseCommand):
    help = "Exit with an error if mail is waiting too long. For a monitor or cron job."

    def add_arguments(self, parser):
        parser.add_argument("--max-age", type=int, default=600, help="seconds")
        parser.add_argument("--max-failed", type=int, default=0)

    def handle(self, *args, max_age, max_failed, **options):
        health = queue_health()
        summary = " ".join(f"{key}={value}" for key, value in health.items())
        if health["oldest_due_seconds"] > max_age or health["failed"] > max_failed:
            raise CommandError(f"Notification queue unhealthy: {summary}")
        self.stdout.write(f"ok {summary}")
