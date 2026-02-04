# app/admin.py
from django.contrib import admin
from .models import Booking, ParkingSlot, Ticket, ParkingHistory

class ParkingSlotAdmin(admin.ModelAdmin):
    list_display = ('slot_number', 'get_status', 'is_occupied', 'is_reserved', 'get_reserved_until')
    list_filter = ('is_occupied', 'is_reserved')
    search_fields = ('slot_number',)
    ordering = ('slot_number',)
    
    def get_status(self, obj):
        if obj.is_occupied:
            return "Occupied"
        elif obj.is_reserved:
            return "Reserved"
        return "Available"
    get_status.short_description = 'Status'
    
    def get_reserved_until(self, obj):
        return obj.reserved_until if obj.is_reserved else "N/A"
    get_reserved_until.short_description = 'Reserved Until'
    get_reserved_until.admin_order_field = 'reserved_until'

class BookingAdmin(admin.ModelAdmin):
    list_display = ('id', 'vehicle_number', 'get_slot', 'get_user', 'start_time', 'end_time', 'status', 'booked_at')
    list_filter = ('status', 'start_time', 'slot')
    search_fields = ('vehicle_number', 'guest_email', 'guest_phone', 'slot__slot_number')
    readonly_fields = ('booked_at', 'qr_code', 'booking_slip')
    date_hierarchy = 'start_time'
    ordering = ('-start_time',)
    
    def get_slot(self, obj):
        return obj.slot.slot_number if obj.slot else "Not assigned"
    get_slot.short_description = 'Slot'
    
    def get_user(self, obj):
        if obj.user:
            return obj.user.username
        return f"Guest ({obj.guest_email or 'no email'})"
    get_user.short_description = 'User'

class TicketAdmin(admin.ModelAdmin):
    list_display = ('id', 'vehicle_number', 'get_booking', 'entry_time', 'exit_time', 'duration', 'fee_paid')
    list_filter = ('fee_paid', 'entry_time')
    search_fields = ('vehicle_number', 'booking__id')
    readonly_fields = ('entry_time', 'qr_code')
    
    def get_booking(self, obj):
        if obj.booking:
            return f"Booking #{obj.booking.id}"
        return "No booking"
    get_booking.short_description = 'Booking'

class ParkingHistoryAdmin(admin.ModelAdmin):
    list_display = ('id', 'vehicle_number', 'action', 'get_user', 'timestamp', 'is_prebooked')
    list_filter = ('action', 'is_prebooked', 'timestamp')
    search_fields = ('vehicle_number', 'user__username')
    date_hierarchy = 'timestamp'
    
    def get_user(self, obj):
        if obj.user:
            return obj.user.username
        return "System"
    get_user.short_description = 'User'

# Register your models with the custom admin classes
admin.site.register(ParkingSlot, ParkingSlotAdmin)
admin.site.register(Booking, BookingAdmin)
admin.site.register(Ticket, TicketAdmin)
admin.site.register(ParkingHistory, ParkingHistoryAdmin)