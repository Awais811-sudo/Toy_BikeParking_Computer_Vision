from django.db import models
from django.core.files import File
from io import BytesIO
import qrcode
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.contrib.auth import get_user_model
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.utils import ImageReader
from django.db.models.signals import post_save
from django.dispatch import receiver
User = get_user_model()
from datetime import timedelta


class GuestUser(models.Model):
    session_key = models.CharField(max_length=40)
    created_at = models.DateTimeField(auto_now_add=True)

class ParkingSlot(models.Model):
    slot_number = models.CharField(max_length=10, unique=True)
    is_occupied = models.BooleanField(default=False)
    is_reserved = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['slot_number']
        verbose_name = 'Parking Slot'
        verbose_name_plural = 'Parking Slots'
    
    def __str__(self):
        status = "Reserved" if self.is_reserved else "Occupied" if self.is_occupied else "Available"
        return f"Slot {self.slot_number} ({status})"
    
    def clean(self):
        if self.is_occupied and self.is_reserved:
            raise ValidationError("Slot cannot be both occupied and reserved at the same time")
    
    def release_slot(self):
        """Release the slot by marking it as available"""
        self.is_occupied = False
        self.is_reserved = False
        self.save()
    
    def reserve_slot(self):
        """Reserve the slot for booking"""
        if not self.is_occupied:
            self.is_reserved = True
            self.save()
            return True
        return False
    
    def occupy_slot(self):
        """Mark slot as occupied (vehicle parked)"""
        self.is_occupied = True
        self.is_reserved = False  # Remove reservation when occupied
        self.save()
        return True

class Booking(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
        ('completed', 'Completed'),
    ]
    booking_id = models.CharField(max_length=20, unique=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    guest_id = models.CharField(max_length=36)  # For UUID storage
    slot = models.ForeignKey(ParkingSlot, on_delete=models.SET_NULL, null=True)
    vehicle_number = models.CharField(max_length=20)
    vehicle_arrived = models.BooleanField(default=False)  
    booked_at = models.DateTimeField(auto_now_add=True)
    start_time = models.DateTimeField()
    guest_email = models.EmailField(null=True, blank=True)
    guest_phone = models.CharField(max_length=20, null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')
    qr_code = models.ImageField(upload_to='qr_codes/', blank=True)
    booking_slip = models.FileField(upload_to='booking_slips/', blank=True)

    def confirm_booking(self):
        if self.slot and not self.slot.is_occupied and not self.slot.is_reserved:
            self.slot.is_reserved = True
            self.slot.save()
            self.status = 'confirmed'
            self.save()
            return True
        return False

    class Meta:
        ordering = ['-booked_at']
        verbose_name = 'Booking'
        verbose_name_plural = 'Bookings'
    
    def __str__(self):
        return f"Booking #{self.id} - {self.vehicle_number} ({self.get_status_display()})"
    
    def is_active(self):
        now = timezone.now()
        return self.start_time <= now <= self.end_time and self.status == 'confirmed'
    
    def save(self, *args, **kwargs):
        # Update slot status when booking is confirmed
        if self.status == 'confirmed':
            self.slot.is_reserved = True
            self.slot.save()
        super().save(*args, **kwargs)

    @classmethod
    def find_active_booking_for_vehicle(cls, vehicle_number):
        """Find active booking for a vehicle number"""
        return cls.objects.filter(
            vehicle_number__iexact=vehicle_number.strip(),
            status__in=['confirmed', 'active']
        ).first()
    
    def generate_qr_code(self):
        """Generate QR code for the booking"""
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(f"Booking:{self.id}|Vehicle:{self.vehicle_number}")
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        
        filename = f'booking_{self.id}_qr.png'
        self.qr_code.save(filename, File(buffer), save=False)
        buffer.close()
    
    def generate_booking_slip(self):
        """Generate PDF booking slip"""
        buffer = BytesIO()

        try:
            # Create PDF document
            pdf = canvas.Canvas(buffer, pagesize=letter)

            # Set document metadata
            pdf.setTitle(f"Parking Booking #{self.id}")

            # Add header
            pdf.setFont("Helvetica-Bold", 16)
            pdf.drawString(100, 750, "Parking Booking Confirmation")

            # Prepare booking details
            booking_date = self.booked_at.strftime('%Y-%m-%d %H:%M') if self.booked_at else 'N/A'
            valid_from = self.start_time.strftime('%Y-%m-%d %H:%M') if self.start_time else 'N/A'
            valid_until = self.end_time.strftime('%Y-%m-%d %H:%M') if self.end_time else 'N/A'
            slot_number = self.slot.slot_number if self.slot else 'Not assigned'

            # Add booking details
            pdf.setFont("Helvetica", 12)
            details = [
                (f"Booking ID: #{self.id}", 100, 720),
                (f"Vehicle Number: {self.vehicle_number}", 100, 700),
                (f"Parking Slot: {slot_number}", 100, 680),
                (f"Booking Date: {booking_date}", 100, 660),
                (f"Valid From: {valid_from}", 100, 640),
                (f"Valid Until: {valid_until}", 100, 620),
            ]

            for text, x, y in details:
                pdf.drawString(x, y, text)

            # Add QR code if it exists
            if self.qr_code:
                qr_img = ImageReader(self.qr_code)
                pdf.drawImage(qr_img, 100, 500, width=150, height=150)

            pdf.showPage()
            pdf.save()

            # Save to model
            filename = f'booking_{self.id}_slip.pdf'
            self.booking_slip.save(filename, File(buffer), save=False)

        except Exception as e:
            raise Exception(f"Failed to generate booking slip: {str(e)}")
        finally:
            buffer.close()
    
    def check_status(self):
        """Check and update booking status"""
        now = timezone.now()

        if self.status in ['cancelled', 'expired', 'completed']:
            return self.status

        if self.slot:
            # Auto cancel if user didn't arrive within 30 minutes of start_time
            grace_period = self.start_time + timedelta(minutes=30)
            if not self.vehicle_arrived and now > grace_period:  # Use vehicle_arrived
                self.status = 'cancelled'
                self.slot.release_slot()
                self.save()
                return self.status

            # Auto mark as completed if vehicle is parked during valid time
            if self.vehicle_arrived and self.start_time <= now <= self.end_time:  # Use vehicle_arrived
                self.status = 'completed'
                self.save()
                return self.status

            # Mark as expired if booking time is over and slot was used
            if now > self.end_time and self.slot.is_occupied:
                self.status = 'expired'
                self.slot.is_reserved = False
                self.slot.save()
                self.save()
                return self.status

            # Free the slot if time is over and never used
            if now > self.end_time and not self.slot.is_occupied:
                self.status = 'cancelled'
                self.slot.release_slot()
                self.save()
                return self.status

        return self.status

    def save(self, *args, **kwargs):
        is_new = not self.pk

        if is_new:
            self.generate_qr_code()
            self.generate_booking_slip()

            if not self.booking_id:
                last = Booking.objects.order_by('-id').first()
                next_id = last.id + 1 if last else 1
                self.booking_id = f"BOOK-{timezone.now().year}-{next_id:04d}"

            # Reserve slot
            if self.slot and not self.slot.is_occupied and not self.slot.is_reserved:
                self.slot.is_reserved = True
                self.slot.save()

        super().save(*args, **kwargs)
    
    def cancel(self):
        """Cancel the booking"""
        self.status = 'cancelled'
        if self.slot:
            self.slot.release_slot()
        self.save()

class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    phone_number = models.CharField(max_length=15, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username}'s Profile"

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    instance.profile.save()

class Ticket(models.Model):
    slot = models.ForeignKey(ParkingSlot, on_delete=models.SET_NULL, null=True, blank=True,related_name='tickets')
    booking = models.ForeignKey(Booking, on_delete=models.SET_NULL, null=True, blank=True)
    vehicle_number = models.CharField(max_length=20)
    entry_time = models.DateTimeField(auto_now_add=True)
    exit_time = models.DateTimeField(null=True, blank=True)
    duration = models.DurationField(null=True, blank=True)
    fee_paid = models.BooleanField(default=False)
    fee_amount = models.DecimalField(max_digits=8, decimal_places=2, default=0.00)
    qr_code = models.ImageField(upload_to='ticket_qr/', blank=True)
    
    class Meta:
        ordering = ['-entry_time']
        verbose_name = 'Ticket'
        verbose_name_plural = 'Tickets'
    
    def __str__(self):
        return f"Ticket #{self.id} - {self.vehicle_number}"
    
    def generate_qr_code(self):
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(f"Ticket:{self.id}|Vehicle:{self.vehicle_number}")
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        filename = f'ticket_{self.id}_qr.png'
        self.qr_code.save(filename, File(buffer), save=False)
        buffer.close()
    
    def save(self, *args, **kwargs):
        if not self.pk:  # Only on creation
            self.generate_qr_code()
        super().save(*args, **kwargs)
    
    def calculate_fee(self):
        """Calculate parking fee based on duration"""
        if not self.exit_time:
            return 0.00
        
        duration = self.exit_time - self.entry_time
        hours = duration.total_seconds() / 3600
        
        # Basic pricing model - $2 for first hour, $1 for each additional hour
        base_fee = 2.00  # First hour
        additional_hours = max(0, hours - 1)
        additional_fee = additional_hours * 1.00
        
        return round(base_fee + additional_fee, 2)
    
    def save(self, *args, **kwargs):
        # Generate QR code on creation
        if not self.pk or not self.qr_code:
            self.generate_qr_code()
        
        # Calculate duration and fee when exiting
        if self.exit_time and not self.duration:
            self.duration = self.exit_time - self.entry_time
            self.fee_amount = self.calculate_fee()
            
            # Mark booking as completed if associated with one
            if self.booking:
                self.booking.status = 'completed'
                self.booking.save()
        
        super().save(*args, **kwargs)
    
    def mark_exited(self):
        """Mark the ticket as exited with current time"""
        if not self.exit_time:
            self.exit_time = timezone.now()
            self.save()

class ParkingHistory(models.Model):
    ACTION_CHOICES = [
        ('entered', 'Vehicle Entered'),
        ('exited', 'Vehicle Exited'),
        ('booked', 'Slot Booked'),
        ('cancelled', 'Booking Cancelled'),
    ]
    
    vehicle_number = models.CharField(max_length=20)
    action = models.CharField(max_length=10, choices=ACTION_CHOICES)
    timestamp = models.DateTimeField(auto_now_add=True)
    duration = models.DurationField(null=True, blank=True)
    is_prebooked = models.BooleanField(default=False)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    ticket = models.ForeignKey(Ticket, on_delete=models.SET_NULL, null=True, blank=True)
    booking = models.ForeignKey(Booking, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        ordering = ['-timestamp']
        verbose_name = 'Parking History'
        verbose_name_plural = 'Parking Histories'
        indexes = [
            models.Index(fields=['vehicle_number']),
            models.Index(fields=['timestamp']),
        ]
    
    def __str__(self):
        return f"{self.vehicle_number} - {self.get_action_display()} at {self.timestamp}"
    
    @classmethod
    def log_entry(cls, vehicle_number, user=None, ticket=None, booking=None):
        """Log a vehicle entry"""
        return cls.objects.create(
            vehicle_number=vehicle_number,
            action='entered',
            user=user,
            ticket=ticket,
            booking=booking,
            is_prebooked=booking is not None
        )
    
    @classmethod
    def log_exit(cls, vehicle_number, user=None, ticket=None):
        """Log a vehicle exit"""
        return cls.objects.create(
            vehicle_number=vehicle_number,
            action='exited',
            user=user,
            ticket=ticket
        )
    
class EconomicsReport(models.Model):
    vehicle_number = models.CharField(max_length=20)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=20.00)
    transaction_type = models.CharField(max_length=20, choices=[
        ('entry_fee', 'Entry Fee'),
        ('booking_fee', 'Booking Fee'),
        ('other', 'Other')
    ], default='entry_fee')
    transaction_date = models.DateTimeField(auto_now_add=True)
    ticket = models.ForeignKey('Ticket', on_delete=models.SET_NULL, null=True, blank=True)
    booking = models.ForeignKey('Booking', on_delete=models.SET_NULL, null=True, blank=True)
    is_paid = models.BooleanField(default=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    payment_method = models.CharField(max_length=20, default='cash', choices=[
        ('cash', 'Cash'),
        ('digital', 'Digital Payment'),
        ('card', 'Card')
    ])
    
    class Meta:
        ordering = ['-transaction_date']
    
    def __str__(self):
        return f"{self.vehicle_number} - PKR {self.amount} - {self.transaction_date.strftime('%Y-%m-%d %H:%M')}"
    

class MembershipPlan(models.Model):
    name = models.CharField(max_length=100)
    stripe_price_id = models.CharField(max_length=100, unique=True)
    price = models.DecimalField(max_digits=6, decimal_places=2)
    interval = models.CharField(max_length=20, choices=[
        ('month', 'Monthly'),
        ('year', 'Yearly'),
        ('one_time', 'One Time')
    ])
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['price']
    
    def __str__(self):
        return f"{self.name} (${self.price}/{self.interval})"

class UserMembership(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('canceled', 'Canceled'),
        ('past_due', 'Past Due'),
        ('unpaid', 'Unpaid'),
        ('trialing', 'Trialing'),
        ('incomplete', 'Incomplete'),
        ('incomplete_expired', 'Incomplete Expired'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='membership')
    stripe_customer_id = models.CharField(max_length=255, blank=True, null=True)
    stripe_subscription_id = models.CharField(max_length=255, blank=True, null=True)
    plan = models.ForeignKey(MembershipPlan, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='incomplete')
    current_period_start = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)
    cancel_at_period_end = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    free_entries_used_today = models.IntegerField(default=0)
    last_free_entry_date = models.DateField(null=True, blank=True)
    subscription_start_date = models.DateTimeField(null=True, blank=True)
    subscription_end_date = models.DateTimeField(null=True, blank=True)
    
    @property
    def is_active(self):
        if self.status == 'active' and self.current_period_end:
            return self.current_period_end > timezone.now()
        return False
    @property
    def has_free_entry_available(self):
        """Check if user has free entry available for today"""
        from django.utils import timezone
        
        today = timezone.now().date()
        
        # Reset counter if it's a new day
        if self.last_free_entry_date != today:
            self.free_entries_used_today = 0
            self.last_free_entry_date = today
            self.save()
        
        # Subscribers get one free entry per day
        return self.status == 'active' and self.free_entries_used_today < 1
    
    def use_free_entry(self):
        """Mark one free entry as used"""
        from django.utils import timezone
        
        today = timezone.now().date()
        
        if self.last_free_entry_date != today:
            self.free_entries_used_today = 0
            self.last_free_entry_date = today
        
        if self.free_entries_used_today < 1:
            self.free_entries_used_today += 1
            self.save()
            return True
        return False
    
    @property
    def can_subscribe_again(self):
        """Check if user can subscribe to a new plan"""
        # User can only subscribe if:
        # 1. They have no active subscription OR
        # 2. Their subscription is about to end (within 7 days) OR
        # 3. Their subscription is canceled
        
        if not self.status == 'active':
            return True
            
        if self.cancel_at_period_end:
            return True
            
        # Check if subscription ends within 7 days
        from django.utils import timezone
        if self.current_period_end:
            days_remaining = (self.current_period_end - timezone.now()).days
            return days_remaining <= 7
            
        return False
    
    def save(self, *args, **kwargs):
        # Set subscription dates when status becomes active
        if self.status == 'active' and not self.subscription_start_date:
            from django.utils import timezone
            self.subscription_start_date = timezone.now()
            
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.username} - {self.get_status_display()}"
    

class UserActivityLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    action = models.CharField(max_length=255)
    details = models.TextField(blank=True)
    ip_address = models.CharField(max_length=45, blank=True)
    user_agent = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-timestamp']
    
    def __str__(self):
        if self.user:
            return f"{self.user.username} - {self.action} - {self.timestamp}"
        return f"Anonymous - {self.action} - {self.timestamp}"
    
    @property
    def has_free_entry_available(self):
        """Check if user has free entry available for today"""
        from django.utils import timezone
        
        today = timezone.now().date()
        
        # Only check if subscription is active
        if self.status != 'active':
            return False
        
        # Reset counter if it's a new day
        if self.last_free_entry_date != today:
            self.free_entries_used_today = 0
            self.last_free_entry_date = today
            self.save()
        
        return self.free_entries_used_today < 1
    
    def use_free_entry(self):
        """Mark one free entry as used"""
        from django.utils import timezone
        
        today = timezone.now().date()
        
        # Only allow if subscription is active
        if self.status != 'active':
            return False
        
        # Reset counter if it's a new day
        if self.last_free_entry_date != today:
            self.free_entries_used_today = 0
            self.last_free_entry_date = today
        
        if self.free_entries_used_today < 1:
            self.free_entries_used_today += 1
            self.save()
            return True
        return False
    