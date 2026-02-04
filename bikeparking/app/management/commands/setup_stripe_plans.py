# app/management/commands/setup_stripe_plans.py
from django.core.management.base import BaseCommand
from django.conf import settings
import stripe

try:
    from app.models import MembershipPlan
except ImportError:
    from models import MembershipPlan

stripe.api_key = settings.STRIPE_SECRET_KEY


class Command(BaseCommand):
    help = 'Setup Stripe products and prices for parking plans'
    
    def handle(self, *args, **kwargs):
        # Check if Stripe API key is set
        if not stripe.api_key:
            self.stdout.write(self.style.ERROR('Stripe API key not found in settings'))
            return
        
        try:
            self.stdout.write('Setting up Stripe plans...')
            
            plans = [
                {
                    'name': 'Monthly Parking Plan',
                    'description': 'Monthly subscription for bike parking',
                    'price': 800,
                    'unit_amount': 80000,
                    'interval': 'month',
                    'recurring': {'interval': 'month'}
                },
                {
                    'name': 'Yearly Parking Plan', 
                    'description': 'Yearly subscription for bike parking (2 months free!)',
                    'price': 8000,
                    'unit_amount': 800000,
                    'interval': 'year',
                    'recurring': {'interval': 'year'}
                },
                {
                    'name': 'Pay Per Use',
                    'description': 'Flexible daily parking',
                    'price': 50,
                    'unit_amount': 5000,
                    'interval': 'one_time',
                    'recurring': None
                }
            ]
            
            for plan_data in plans:
                self.stdout.write(f"Creating {plan_data['name']}...")
                
                # Create product in Stripe
                product = stripe.Product.create(
                    name=plan_data['name'],
                    description=plan_data['description']
                )
                
                # Create price in Stripe
                if plan_data['interval'] == 'one_time':
                    price = stripe.Price.create(
                        unit_amount=plan_data['unit_amount'],
                        currency='pkr',
                        product=product.id,
                    )
                else:
                    price = stripe.Price.create(
                        unit_amount=plan_data['unit_amount'],
                        currency='pkr',
                        recurring=plan_data['recurring'],
                        product=product.id,
                    )
                
                # Create or update in database
                plan, created = MembershipPlan.objects.update_or_create(
                    name=plan_data['name'],
                    defaults={
                        'stripe_price_id': price.id,
                        'price': plan_data['price'],
                        'interval': plan_data['interval'],
                        'description': plan_data['description'],
                        'is_active': True
                    }
                )
                
                if created:
                    self.stdout.write(self.style.SUCCESS(f"Created: {plan.name} (Price ID: {plan.stripe_price_id})"))
                else:
                    self.stdout.write(self.style.SUCCESS(f"Updated: {plan.name} (Price ID: {plan.stripe_price_id})"))
            
            self.stdout.write(self.style.SUCCESS('\nAll plans created successfully!'))
            
            # Display all plans
            self.stdout.write('\n' + '='*50)
            self.stdout.write('AVAILABLE PLANS:')
            self.stdout.write('='*50)
            
            for plan in MembershipPlan.objects.all():
                self.stdout.write(f"""
{plan.name}:
  Price: Rs {plan.price}/{plan.interval}
  Stripe Price ID: {plan.stripe_price_id}
  Active: {'✅' if plan.is_active else '❌'}
                """)
                
        except stripe.error.StripeError as e:
            self.stdout.write(self.style.ERROR(f'Stripe Error: {str(e)}'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error: {str(e)}'))