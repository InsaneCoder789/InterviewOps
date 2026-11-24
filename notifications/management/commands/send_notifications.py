import logging
import signal
import threading

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections

from notifications.delivery import process_due

logger = logging.getLogger("interviewops.notifications")


class Command(BaseCommand):
    help = "Send due emails. Runs until stopped unless --once is given."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--interval", type=float, default=15)

    def handle(self, *args, once, interval, **options):
        if not settings.DEBUG and settings.EMAIL_BACKEND.endswith("console.EmailBackend"):
            # Printing would mark mail as sent and put addresses in the logs.
            raise CommandError("Configure EMAIL_BACKEND: the console backend is for DEBUG only.")
        if once:
            self.stdout.write(f"Processed {process_due()} message(s).")
            return
        stop = threading.Event()
        for signum in (signal.SIGINT, signal.SIGTERM):
            signal.signal(signum, lambda *_: stop.set())
        logger.info("notification_worker_started interval_s=%s", interval)
        while not stop.is_set():
            close_old_connections()
            try:
                handled = process_due(should_stop=stop.is_set)
            except Exception:
                logger.exception("notification_worker_error")
                handled = 0
            if not handled:
                stop.wait(interval)
        logger.info("notification_worker_stopped")
