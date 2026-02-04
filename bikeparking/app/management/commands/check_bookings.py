from django.core.management.base import BaseCommand
from app.models import Booking  # Update with your app and model
from django.utils import timezone

class Command(BaseCommand):
    help = 'Check and update booking statuses'

    def handle(self, *args, **kwargs):
        active_bookings = Booking.objects.filter(status='active')
        for booking in active_bookings:
            booking.check_status()
        self.stdout.write(self.style.SUCCESS(f'{active_bookings.count()} bookings checked.'))