# middleware.py
from django.shortcuts import redirect
from django.contrib import messages
from django.utils import timezone
from app.models import UserMembership
class SubscriptionCheckMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Skip for non-authenticated users
        if not request.user.is_authenticated:
            return self.get_response(request)
        
        # Check if trying to access subscription pages
        if request.path.startswith('/create-payment-intent/') or \
           'subscribe' in request.path.lower():
            
            try:
                membership = request.user.membership
                
                if not membership.can_subscribe_again:
                    messages.error(
                        request, 
                        "You already have an active subscription. You can subscribe again 7 days before your current subscription ends."
                    )
                    return redirect('home')
                    
            except UserMembership.DoesNotExist:
                # User has no membership yet, allow subscription
                pass
        
        return self.get_response(request)