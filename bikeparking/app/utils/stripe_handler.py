import stripe
from django.conf import settings
from django.urls import reverse

stripe.api_key = settings.STRIPE_SECRET_KEY

class StripeHandler:
    def __init__(self):
        self.stripe = stripe
    
    def create_customer(self, user, token=None):
        """Create or get Stripe customer"""
        try:
            # Check if customer already exists
            if hasattr(user, 'membership') and user.membership.stripe_customer_id:
                customer = self.stripe.Customer.retrieve(
                    user.membership.stripe_customer_id
                )
                return customer
            
            # Create new customer
            customer_data = {
                'email': user.email,
                'name': user.get_full_name() or user.username,
                'metadata': {
                    'user_id': user.id,
                    'username': user.username
                }
            }
            
            if token:
                customer_data['source'] = token
            
            customer = self.stripe.Customer.create(**customer_data)
            return customer
            
        except Exception as e:
            print(f"Error creating customer: {str(e)}")
            return None
    
    def create_checkout_session(self, price_id, user, request):
        """Create Stripe Checkout Session"""
        try:
            success_url = request.build_absolute_uri(
                reverse('membership_success')
            ) + "?session_id={CHECKOUT_SESSION_ID}"
            
            cancel_url = request.build_absolute_uri(
                reverse('membership_cancel')
            )
            
            # Get or create customer
            customer = self.create_customer(user)
            
            session_data = {
                'customer': customer.id if customer else None,
                'success_url': success_url,
                'cancel_url': cancel_url,
                'payment_method_types': ['card'],
                'mode': 'subscription',
                'line_items': [{
                    'price': price_id,
                    'quantity': 1,
                }],
                'metadata': {
                    'user_id': user.id
                },
                'allow_promotion_codes': True,
            }
            
            # If no customer, use customer_email instead
            if not customer:
                session_data['customer_email'] = user.email
                del session_data['customer']
            
            checkout_session = self.stripe.checkout.Session.create(**session_data)
            return checkout_session
            
        except Exception as e:
            print(f"Error creating checkout session: {str(e)}")
            return None
    
    def get_subscription(self, subscription_id):
        """Retrieve subscription details"""
        try:
            subscription = self.stripe.Subscription.retrieve(
                subscription_id,
                expand=['customer', 'plan.product']
            )
            return subscription
        except Exception as e:
            print(f"Error getting subscription: {str(e)}")
            return None
    
    def cancel_subscription(self, subscription_id):
        """Cancel subscription"""
        try:
            subscription = self.stripe.Subscription.delete(subscription_id)
            return subscription
        except Exception as e:
            print(f"Error canceling subscription: {str(e)}")
            return None
    
    def handle_webhook_event(self, payload, sig_header):
        """Handle webhook events"""
        try:
            event = self.stripe.Webhook.construct_event(
                payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
            )
            return event
        except Exception as e:
            print(f"Webhook error: {str(e)}")
            return None