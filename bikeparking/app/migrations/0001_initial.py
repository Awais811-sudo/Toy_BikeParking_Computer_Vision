# app/migrations/0001_initial.py
from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings
from django.utils import timezone


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='GuestUser',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('session_key', models.CharField(max_length=40)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.CreateModel(
            name='ParkingSlot',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('slot_number', models.CharField(max_length=10, unique=True)),
                ('is_occupied', models.BooleanField(default=False)),
                ('is_reserved', models.BooleanField(default=False)),
            ],
            options={
                'ordering': ['slot_number'],
            },
        ),
        migrations.CreateModel(
            name='MembershipPlan',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('stripe_price_id', models.CharField(max_length=100, unique=True)),
                ('price', models.DecimalField(decimal_places=2, max_digits=6)),
                ('interval', models.CharField(choices=[('month', 'Monthly'), ('year', 'Yearly'), ('one_time', 'One Time')], max_length=20)),
                ('description', models.TextField(blank=True)),
                ('is_active', models.BooleanField(default=True)),
                ('daily_free_parking_limit', models.IntegerField(default=1)),
            ],
            options={
                'ordering': ['price'],
            },
        ),
        migrations.CreateModel(
            name='UserMembership',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('stripe_customer_id', models.CharField(blank=True, max_length=255, null=True)),
                ('stripe_subscription_id', models.CharField(blank=True, max_length=255, null=True)),
                ('status', models.CharField(choices=[('active', 'Active'), ('canceled', 'Canceled'), ('past_due', 'Past Due'), ('unpaid', 'Unpaid'), ('trialing', 'Trialing'), ('incomplete', 'Incomplete'), ('incomplete_expired', 'Incomplete Expired')], default='incomplete', max_length=20)),
                ('current_period_start', models.DateTimeField(blank=True, null=True)),
                ('current_period_end', models.DateTimeField(blank=True, null=True)),
                ('cancel_at_period_end', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('last_reset_date', models.DateField(default=timezone.now)),
                ('free_parking_used_today', models.IntegerField(default=0)),
                ('total_parking_used', models.IntegerField(default=0)),
                ('plan', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='app.membershipplan')),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='membership', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddConstraint(
            model_name='usermembership',
            constraint=models.UniqueConstraint(fields=('user',), name='unique_user_membership'),
        ),
        migrations.CreateModel(
            name='UserProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('phone_number', models.CharField(blank=True, max_length=15, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='profile', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='UserActivityLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('action', models.CharField(choices=[('staff_created', 'Staff Created'), ('staff_updated', 'Staff Updated'), ('staff_deleted', 'Staff Deleted'), ('staff_password_reset', 'Staff Password Reset'), ('staff_status_changed', 'Staff Status Changed'), ('login', 'User Login'), ('logout', 'User Logout'), ('booking_created', 'Booking Created'), ('vehicle_entry', 'Vehicle Entry'), ('vehicle_exit', 'Vehicle Exit'), ('subscription_created', 'Subscription Created'), ('subscription_canceled', 'Subscription Canceled')], max_length=50)),
                ('details', models.TextField(blank=True)),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('user_agent', models.TextField(blank=True)),
                ('timestamp', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-timestamp'],
            },
        ),
        migrations.CreateModel(
            name='Ticket',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('vehicle_number', models.CharField(max_length=20)),
                ('entry_time', models.DateTimeField(auto_now_add=True)),
                ('exit_time', models.DateTimeField(blank=True, null=True)),
                ('duration', models.DurationField(blank=True, null=True)),
                ('fee_paid', models.BooleanField(default=False)),
                ('fee_amount', models.DecimalField(decimal_places=2, default=0.0, max_digits=8)),
                ('qr_code', models.ImageField(blank=True, upload_to='ticket_qr/')),
                ('is_free_parking', models.BooleanField(default=False)),
                ('booking', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='app.booking')),
                ('slot', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='tickets', to='app.parkingslot')),
            ],
            options={
                'ordering': ['-entry_time'],
            },
        ),
        migrations.CreateModel(
            name='SubscriptionPayment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('stripe_payment_intent_id', models.CharField(max_length=255, unique=True)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=10)),
                ('currency', models.CharField(default='pkr', max_length=3)),
                ('status', models.CharField(choices=[('succeeded', 'Succeeded'), ('processing', 'Processing'), ('requires_payment_method', 'Requires Payment Method'), ('canceled', 'Canceled')], max_length=30)),
                ('paid_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('membership', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='payments', to='app.usermembership')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='ParkingHistory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('vehicle_number', models.CharField(max_length=20)),
                ('action', models.CharField(choices=[('entered', 'Vehicle Entered'), ('exited', 'Vehicle Exited'), ('booked', 'Slot Booked'), ('cancelled', 'Booking Cancelled')], max_length=10)),
                ('timestamp', models.DateTimeField(auto_now_add=True)),
                ('duration', models.DurationField(blank=True, null=True)),
                ('is_prebooked', models.BooleanField(default=False)),
                ('is_free_parking', models.BooleanField(default=False)),
                ('booking', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='app.booking')),
                ('ticket', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='app.ticket')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-timestamp'],
            },
        ),
        migrations.CreateModel(
            name='EconomicsReport',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('vehicle_number', models.CharField(max_length=50)),
                ('amount', models.DecimalField(decimal_places=2, default=20.0, max_digits=10)),
                ('transaction_type', models.CharField(choices=[('entry_fee', 'Entry Fee'), ('booking_fee', 'Booking Fee'), ('subscription', 'Subscription'), ('subscription_renewal', 'Subscription Renewal'), ('other', 'Other')], default='entry_fee', max_length=20)),
                ('transaction_date', models.DateTimeField(auto_now_add=True)),
                ('is_paid', models.BooleanField(default=True)),
                ('payment_method', models.CharField(choices=[('cash', 'Cash'), ('stripe', 'Stripe'), ('digital', 'Digital Payment'), ('card', 'Card')], default='cash', max_length=20)),
                ('booking', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='app.booking')),
                ('subscription', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='app.usermembership')),
                ('ticket', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='app.ticket')),
            ],
            options={
                'ordering': ['-transaction_date'],
            },
        ),
        migrations.CreateModel(
            name='Booking',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('booking_id', models.CharField(blank=True, max_length=20, unique=True)),
                ('guest_id', models.CharField(blank=True, max_length=36)),
                ('vehicle_number', models.CharField(max_length=20)),
                ('vehicle_arrived', models.BooleanField(default=False)),
                ('booked_at', models.DateTimeField(auto_now_add=True)),
                ('start_time', models.DateTimeField()),
                ('guest_email', models.EmailField(blank=True, max_length=254, null=True)),
                ('guest_phone', models.CharField(blank=True, max_length=20, null=True)),
                ('end_time', models.DateTimeField(blank=True, null=True)),
                ('status', models.CharField(choices=[('confirmed', 'Confirmed'), ('active', 'Active'), ('expired', 'Expired'), ('cancelled', 'Cancelled'), ('completed', 'Completed')], default='confirmed', max_length=10)),
                ('qr_code', models.ImageField(blank=True, upload_to='qr_codes/')),
                ('booking_slip', models.FileField(blank=True, upload_to='booking_slips/')),
                ('is_free_booking', models.BooleanField(default=False)),
                ('slot', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='app.parkingslot')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-booked_at'],
            },
        ),
    ]