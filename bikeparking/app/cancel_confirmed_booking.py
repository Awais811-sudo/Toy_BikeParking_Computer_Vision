# In a custom management command (e.g. cancel_unconfirmed_bookings.py)
from django.utils import timezone
from app.models import Booking
from datetime import timedelta

def run():
    threshold = timezone.now() - timedelta(seconds=30)
    expired = Booking.objects.filter(status='active', start_time__lt=threshold)
    for booking in expired:
        booking.status = 'cancelled'
        booking.save()
