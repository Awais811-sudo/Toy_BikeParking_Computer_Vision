# In signals.py
from django.db.models.signals import pre_save
from django.dispatch import receiver
from .models import Booking

@receiver(pre_save, sender=Booking)
def handle_booking_expiry(sender, instance, **kwargs):
    if instance.pk:  # Existing instance
        original = sender.objects.get(pk=instance.pk)
        if original.is_active and not instance.is_active:
            # Booking was cancelled
            instance.slot.is_reserved = False
            instance.slot.save()