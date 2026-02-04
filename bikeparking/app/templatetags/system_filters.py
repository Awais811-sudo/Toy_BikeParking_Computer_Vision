# Create a new file: app/templatetags/system_filters.py
from django import template

register = template.Library()

@register.filter
def get_event_type(log):
    """Determine event type from log action"""
    action = log.action.lower()
    
    # Authentication events
    if any(word in action for word in ['login', 'logout', 'password', 'auth', 'authenticate', 'reset']):
        return 'auth'
    
    # Security events
    if any(word in action for word in ['security', 'failed', 'attempt', 'unauthorized', 'block', 'suspicious']):
        return 'security'
    
    # System events
    if any(word in action for word in ['system', 'startup', 'shutdown', 'restart', 'service', 'clear', 'export']):
        return 'system'
    
    # Administrative events
    if any(word in action for word in ['admin', 'create', 'update', 'delete', 'user', 'profile', 'staff', 'permission']):
        return 'admin'
    
    # Database events
    if any(word in action for word in ['database', 'backup', 'restore', 'migration', 'cleanup', 'delete']):
        return 'database'
    
    # Performance events
    if any(word in action for word in ['performance', 'slow', 'timeout', 'resource', 'memory', 'cpu']):
        return 'performance'
    
    # Integration events
    if any(word in action for word in ['api', 'integration', 'webhook', 'sync', 'external', 'stripe', 'payment']):
        return 'integration'
    
    # Default to application
    return 'application'

@register.filter
def get_severity(log):
    """Determine severity level from log action"""
    action = log.action.lower()
    
    # Critical events
    if any(word in action for word in ['critical', 'emergency', 'fatal', 'panic']):
        return 'critical'
    
    # Error events
    if any(word in action for word in ['error', 'exception', 'failed', 'crash', 'broken', 'denied']):
        return 'error'
    
    # Warning events
    if any(word in action for word in ['warning', 'alert', 'caution', 'attention']):
        return 'warning'
    
    # Default to info
    return 'info'

@register.filter
def get_status(log):
    """Determine status from log action"""
    action = log.action.lower()
    
    # Failed status
    if any(word in action for word in ['failed', 'error', 'rejected', 'denied', 'blocked', 'invalid']):
        return 'failed'
    
    # Pending status
    if any(word in action for word in ['pending', 'waiting', 'processing', 'queued']):
        return 'pending'
    
    # Default to success
    return 'success'

@register.filter
def truncate_details(details, length=100):
    """Truncate details text"""
    if len(details) > length:
        return details[:length] + '...'
    return details