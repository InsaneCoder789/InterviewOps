"""The worker as a real process, talking to a real (local, fake) SMTP server."""

import os
import signal
import socketserver
import subprocess
import sys
import threading
import time
from datetime import timedelta
from pathlib import Path
from urllib.parse import quote

from django.db import connection
from django.test import TransactionTestCase
from django.utils import timezone

from notifications.models import Notification
from scheduling import services

from .base import Factory

ROOT = Path(__file__).resolve().parent.parent


class Mailbox(socketserver.ThreadingTCPServer):
    """Just enough SMTP. `stall` makes it accept the data and then never answer."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self):
        super().__init__(("127.0.0.1", 0), Conversation)
        self.messages = []
        self.stall = threading.Event()
        self.stalled = threading.Event()
        self.release = threading.Event()


class Conversation(socketserver.StreamRequestHandler):
    def reply(self, line):
        self.wfile.write(line.encode() + b"\r\n")

    def handle(self):
        self.reply("220 test")
        while line := self.rfile.readline():
            command = line.strip().upper()
            if command.startswith(b"DATA"):
                self.reply("354 go")
                body = []
                while (part := self.rfile.readline()) not in (b".\r\n", b""):
                    body.append(part)
                if self.server.stall.is_set():
                    self.server.stalled.set()
                    self.server.release.wait(30)
                    return
                self.server.messages.append(b"".join(body).decode())
                self.reply("250 stored")
            elif command.startswith(b"QUIT"):
                self.reply("221 bye")
                return
            else:
                self.reply("250 ok")


def wait_until(condition, seconds=20):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.05)
    return False


class WorkerProcessTests(Factory, TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.mailbox = Mailbox()
        threading.Thread(target=self.mailbox.serve_forever, daemon=True).start()
        self.addCleanup(self.mailbox.server_close)
        self.addCleanup(self.mailbox.shutdown)
        self.addCleanup(self.mailbox.release.set)
        services.book_slot(student=self.user("student"), slot_id=self.slot(self.mentor()).pk)

    def start_worker(self, *arguments, **overrides):
        db = connection.settings_dict
        credentials = f"{quote(db['USER'])}:{quote(db['PASSWORD'])}"
        url = f"postgresql://{credentials}@{db['HOST']}:{db['PORT']}/{db['NAME']}"
        env = {
            **os.environ,
            "DJANGO_DEBUG": "1",
            "DATABASE_URL": url,
            "EMAIL_BACKEND": "django.core.mail.backends.smtp.EmailBackend",
            "EMAIL_HOST": "127.0.0.1",
            "EMAIL_PORT": str(self.mailbox.server_address[1]),
            "EMAIL_USE_TLS": "0",
            **overrides,
        }
        process = subprocess.Popen(
            [sys.executable, "manage.py", "send_notifications", *arguments],
            cwd=ROOT,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        self.addCleanup(process.stdout.close)
        self.addCleanup(process.wait)
        self.addCleanup(process.kill)
        return process

    def sent(self):
        return Notification.objects.filter(status="sent").count()

    def test_delivers_over_smtp_and_stops_cleanly_on_sigterm(self):
        worker = self.start_worker("--interval", "0.1")
        self.assertTrue(wait_until(lambda: self.sent() == 2), "confirmations not sent")
        self.assertEqual(len(self.mailbox.messages), 2)
        self.assertIn("Subject: Booked: mock interview", self.mailbox.messages[0])
        worker.send_signal(signal.SIGTERM)
        output, _ = worker.communicate(timeout=20)
        self.assertEqual(worker.returncode, 0, output)
        self.assertIn("notification_worker_stopped", output)
        self.assertNotIn("student@example.test", output)

    def test_a_worker_killed_mid_send_is_recovered_by_the_next_one(self):
        self.mailbox.stall.set()
        worker = self.start_worker("--once")
        self.assertTrue(self.mailbox.stalled.wait(20), "no send started")
        worker.kill()
        worker.wait(timeout=10)
        stuck = Notification.objects.get(status="sending")
        self.assertEqual(stuck.attempts, 1)
        self.mailbox.stall.clear()
        self.mailbox.release.set()
        # Nothing is lost: once the lease runs out, another worker sends it.
        Notification.objects.filter(pk=stuck.pk).update(
            available_at=timezone.now() - timedelta(seconds=1)
        )
        self.start_worker("--once").communicate(timeout=30)
        stuck.refresh_from_db()
        self.assertEqual((stuck.status, stuck.attempts), ("sent", 2))
        self.assertEqual(self.sent(), 2)

    def test_unreachable_mail_server_schedules_a_retry(self):
        output, _ = self.start_worker("--once", EMAIL_PORT="1").communicate(timeout=30)
        row = Notification.objects.filter(attempts=1).first()
        self.assertEqual(row.status, "pending")
        self.assertGreater(row.available_at, timezone.now())
        self.assertNotIn("example.test", output)

    def test_refuses_a_zero_interval(self):
        worker = self.start_worker("--interval", "0")
        output, _ = worker.communicate(timeout=20)
        self.assertNotEqual(worker.returncode, 0)
        self.assertIn("greater than zero", output)
