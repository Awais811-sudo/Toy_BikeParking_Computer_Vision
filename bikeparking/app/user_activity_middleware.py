# Create a new file: middleware/user_activity_middleware.py
import json
from django.utils import timezone
from .models import UserActivityLog

class UserActivityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Skip tracking for certain paths
        exclude_paths = ['/admin/', '/static/', '/media/', '/favicon.ico']
        
        if not any(request.path.startswith(path) for path in exclude_paths):
            # Log user activity after response is processed
            response = self.get_response(request)
            
            if request.user.is_authenticated:
                try:
                    # Extract action from request
                    action = self._get_action_from_request(request)
                    
                    if action:  # Only log if there's an action to log
                        UserActivityLog.objects.create(
                            user=request.user,
                            action=action,
                            details=self._get_request_details(request),
                            ip_address=self._get_client_ip(request),
                            user_agent=request.META.get('HTTP_USER_AGENT', '')
                        )
                except Exception as e:
                    print(f"Error logging user activity: {e}")
            
            return response
        
        return self.get_response(request)
    
    def _get_action_from_request(self, request):
        """Extract action from request based on URL and method"""
        action_map = {
            'POST': {
                '/login/': 'User logged in',
                '/logout/': 'User logged out',
                '/signup/': 'User registered',
                '/book-slot/': 'Booked parking slot',
                '/admin/manual-entry/': 'Manual vehicle entry/exit',
                '/admin/create-booking/': 'Created booking',
            },
            'GET': {
                '/profile/': 'Viewed profile',
                '/my-bookings/': 'Viewed bookings',
                '/admin/dashboard/': 'Accessed admin dashboard',
                '/admin/booking-history/': 'Viewed booking history',
                '/admin/ticket-history/': 'Viewed ticket history',
                '/admin/parking-logs/': 'Viewed parking logs',
                '/admin/economics/': 'Viewed economics dashboard',
                '/admin/users/': 'Viewed users page',
                '/admin/user-logs/': 'Viewed user logs',
            }
        }
        
        for path, action in action_map.get(request.method, {}).items():
            if request.path.startswith(path):
                return action
        
        # Default actions
        if request.method == 'POST':
            return 'Performed POST action'
        elif request.method == 'GET':
            return 'Viewed page'
        
        return None
    
    def _get_request_details(self, request):
        """Get request details for logging"""
        details = {
            'path': request.path,
            'method': request.method,
        }
        
        # Add POST data (excluding sensitive information)
        if request.method == 'POST':
            post_data = dict(request.POST)
            # Remove sensitive fields
            sensitive_fields = ['password', 'csrfmiddlewaretoken', 'secret_key']
            for field in sensitive_fields:
                if field in post_data:
                    post_data[field] = '[REDACTED]'
            details['post_data'] = post_data
        
        return json.dumps(details)
    
    def _get_client_ip(self, request):
        """Get client IP address"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip