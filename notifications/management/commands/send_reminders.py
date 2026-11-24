from .send_notifications import Command as SendNotifications


class Command(SendNotifications):
    help = "Old name for send_notifications."
