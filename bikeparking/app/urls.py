from django.urls import path
from .views import *
from django.contrib.auth.views import LogoutView
from django.contrib.auth import views as auth_views
urlpatterns = [
    # User URLs

    path('signup/', signup_view, name='signup'),
    path('login/', login_view, name='login'),
    path('logout/', logout_view, name='logout'),
    path('guest-login/', guest_login_view, name='guest_login'),

    path('', home, name='home'),
    path('book/', book_slot, name='book_slot'),
    path('booking/confirmation/<int:booking_id>/', booking_confirmation, name='booking_confirmation'),
    path('profile/', profile, name='profile'),
    path('my-bookings/', my_bookings, name='my_bookings'),

    path('booking-availability/', get_booking_availability_api, name='booking_availability_api'),
    path('booking/<int:booking_id>/expire/', expire_booking, name='expire_booking'),
    path('booking/<int:booking_id>/complete/', complete_booking, name='complete_booking'),

    path('check-vehicle-status/', check_vehicle_status, name='check_vehicle_status'),
    path('check-slots/', check_slots, name='check_slots'),
    path('api/check-availability/', check_availability, name='check_availability'),
    path('dashboard/parking-logs/', parking_logs, name='parking_logs'),
    path('dashboard/login/', dashboard_login, name='dashboard_login'),
    path('dashboard/manual-entry/', admin_manual_entry, name='admin_manual_entry'),    
    path('dashboard/', admin_dashboard, name='admin_dashboard'),
    path('dashboard/ticket-history/', ticket_history, name='ticket_history'),    
    path('dashboard/logout/', custom_logout, name='dashboard_logout'),
    path('dashboard/bookings/', booking_history, name='booking_history'),
    path('dashboard/settings/', settings_view, name='settings'),
    path('admin/password_change/', auth_views.PasswordChangeView.as_view(), name='password_change'),
    path('admin/password_change/done/', auth_views.PasswordChangeDoneView.as_view(), name='password_change_done'),
    path("camera_feed/", camera_feed, name="camera_feed"),
    path("get_detected_slot/", get_detected_slot, name="get_detected_slot"),
    path('api/parking-metrics/', get_parking_metrics, name='get_parking_metrics'),
    path('dashboard/create/', create_booking, name='create_booking'),
    path('api/check-booking/', check_booking, name='check_booking'),
    path('get-slot-data/', get_slot_data, name='get_slot_data'),
    path('generate-receipt/<int:ticket_id>/', generate_receipt_pdf, name='generate_receipt'),
    path('api/ticket/<int:ticket_id>/', get_ticket_details, name='get_ticket_details'),
    path('check-vehicle-status/', check_vehicle_status, name='check_vehicle_status'),

    path('economics/', economics_dashboard, name='economics_dashboard'),
    path('economics/report/', economics_report, name='economics_report'),
    path('economics/export/', export_economics_csv, name='export_economics_csv'),
    path('economics/summary/', economics_summary_api, name='economics_summary_api'),

    # Membership URLs
    path('create-payment-intent/', create_payment_intent, name='create_payment_intent'),
    path('payment-success/', payment_success, name='payment_success'),
    path('payment-cancelled/', payment_cancelled, name='payment_cancelled'),
    path('webhook/stripe/', stripe_webhook, name='stripe_webhook'),
    

    
    # Staff List
    path('staff/', staff_list, name='staff_list'),
    
    # Create New Staff
    path('staff/create/', create_staff, name='create_staff'),
    
    # Edit Staff
    path('staff/<int:user_id>/edit/', edit_staff, name='edit_staff'),
    
    # Staff Details
    path('staff/<int:user_id>/detail/', staff_detail, name='staff_detail'),
    
    # Toggle Staff Status (Active/Inactive)
    path('staff/<int:user_id>/toggle-status/', toggle_staff_status, name='toggle_staff_status'),
    
    # Delete Staff
    path('staff/<int:user_id>/delete/', delete_staff, name='delete_staff'),
    
    # Export Staff to CSV
    path('staff/export-csv/', export_staff_csv, name='export_staff_csv'),
    
    
    path('economics/recent-transactions/', recent_transactions_api, name='recent_transactions_api'),
    path('debug/', debug_economics_data, name='debug_view'),
    path('user-logs/', system_logs, name='user_logs'),
    path('admin/system-logs/export/', export_system_logs_csv, name='export_system_logs_csv'),
    path('admin/system-logs/clear/', clear_old_system_logs, name='clear_old_system_logs'),
]