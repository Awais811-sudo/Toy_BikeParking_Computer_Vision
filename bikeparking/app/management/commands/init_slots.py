from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from app.models import ParkingSlot
from django.db import transaction

class Command(BaseCommand):
    help = 'Initialize parking system with admin user and slots'

    def handle(self, *args, **options):
        with transaction.atomic():
            # Delete all existing slots first
            ParkingSlot.objects.all().delete()
            self.stdout.write("Deleted all existing parking slots")
            
            # Create admin user if doesn't exist
            admin, created = User.objects.get_or_create(
                username='admin',
                defaults={
                    'email': 'admin@parking.com',
                    'is_staff': True,
                    'is_superuser': True
                }
            )
            if created:
                admin.set_password('admin123')
                admin.save()
                self.stdout.write("Created admin user")
            else:
                self.stdout.write("Admin user already exists")
            
            # Create parking slots
            slots_to_create = []
            for i in range(1, 11):
                slots_to_create.append(
                    ParkingSlot(
                        slot_number=f"A{i}",
                        is_occupied=False,
                        is_reserved=False
                    )
                )
            
            # Bulk create all slots at once
            ParkingSlot.objects.bulk_create(slots_to_create)
            self.stdout.write(f"Created {len(slots_to_create)} parking slots")
            
            self.stdout.write(
                self.style.SUCCESS('\nSuccessfully initialized parking system\n') +
                'Admin credentials: username=admin, password=admin123\n' +
                'Parking slots: A1 through A10 created'
            )