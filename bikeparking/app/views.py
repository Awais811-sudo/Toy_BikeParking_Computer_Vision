from django.shortcuts import render, redirect, get_object_or_404, HttpResponse
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils import timezone
from django.urls import reverse 
from datetime import timedelta, datetime
from .models import ParkingSlot, Booking, Ticket, ParkingHistory, EconomicsReport, UserActivityLog, UserMembership, MembershipPlan
from .forms import *
from django.contrib import messages
import cv2
from django.http import StreamingHttpResponse
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.http import StreamingHttpResponse, JsonResponse
from django.contrib.auth.forms import AuthenticationForm
import uuid
from django.views.decorators.http import require_GET
from django.db import transaction
from django.contrib.auth import authenticate, login, logout
from django.contrib.admin.views.decorators import staff_member_required
from .models import GuestUser
from django.core.paginator import Paginator
from django.db.models import Q, Sum, Count
import csv
from django.utils.dateparse import parse_date
from django.views.decorators.csrf import csrf_exempt
from ultralytics import YOLO
import cv2
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
import re
from django.utils import timezone
from datetime import date
import json
import stripe
from django.views.decorators.http import require_POST
from django.conf import settings

# ==============================
# CONFIGURATION
# ==============================
BOOKING_EXPIRY_MINUTES = 15
TOTAL_SLOTS = 26

# ===== ADD THESE NEW CONFIGURATIONS =====
MAX_BOOKABLE_SLOTS_PERCENT = 30  # Only 30% of slots can be booked
MAX_OCCUPANCY_FOR_BOOKING_PERCENT = 60  # Disable booking when 60% occupied
# ========================================

# Calculate actual numbers from percentages
MAX_BOOKABLE_SLOTS = int(TOTAL_SLOTS * MAX_BOOKABLE_SLOTS_PERCENT / 100)
MAX_OCCUPANCY_FOR_BOOKING = int(TOTAL_SLOTS * MAX_OCCUPANCY_FOR_BOOKING_PERCENT / 100)

# Initialize 26 parking slots if they don't exist
def initialize_parking_slots():
    if ParkingSlot.objects.count() == 0:
        slots = []
        for i in range(1, TOTAL_SLOTS + 1):
            slots.append(ParkingSlot(slot_number=str(i)))
        ParkingSlot.objects.bulk_create(slots)
        print(f"✅ Created {TOTAL_SLOTS} parking slots")

# Call this function when the app starts
initialize_parking_slots()

# ==============================
# GLOBAL VARIABLES FOR SLOT DETECTION
# ==============================

parking_metrics_cache = {
    'total_slots': TOTAL_SLOTS,
    'available_slots': TOTAL_SLOTS,
    'occupied_slots': 0,
    'reserved_slots': 0,
    'occupancy_rate': 0,
    'slots': [],
    'last_updated': timezone.now(),
    'update_interval': 5  
}
# YOLO Model initialization
try:
    model = YOLO("../runs/detect/train/weights/best.pt")
    print("✅ YOLOv8 model loaded successfully.")
except Exception as e:
    print(f"❌ Error loading YOLOv8 model: {e}")
    model = None

latest_detection_data = {
    'detected_slot': None,
    'bike_count': 0,
    'available_slots': TOTAL_SLOTS,
    'occupied_slots': 0,
    'total_slots': TOTAL_SLOTS,
    'last_updated': timezone.now()
}

# ==============================
# SLOT DETECTION OPTIMIZATION - 5 SECOND TIMER
# ==============================

def update_parking_metrics():
    """Update parking metrics with 5-second interval and caching"""
    global parking_metrics_cache
    
    # Check if we need to update (5-second interval)
    time_since_last_update = (timezone.now() - parking_metrics_cache['last_updated']).total_seconds()
    if time_since_last_update < parking_metrics_cache['update_interval']:
        return  # Don't update if less than 5 seconds have passed
    
    try:
        # Get all parking slots
        parking_slots = ParkingSlot.objects.all()
        
        # Calculate metrics
        total_slots = parking_slots.count()
        occupied_slots = parking_slots.filter(is_occupied=True).count()
        reserved_slots = parking_slots.filter(is_reserved=True, is_occupied=False).count()
        available_slots = total_slots - (occupied_slots + reserved_slots)
        
        # Calculate occupancy rate
        occupancy_rate = round((occupied_slots / total_slots) * 100) if total_slots > 0 else 0
        
        # Get individual slot status for updating the grid
        slots_data = list(ParkingSlot.objects.values('slot_number', 'is_occupied', 'is_reserved').order_by('slot_number'))
        
        # Convert to the format expected by the frontend
        formatted_slots = []
        for slot in slots_data:
            if slot['is_occupied']:
                status = "Occupied"
            elif slot['is_reserved']:
                status = "Reserved"
            else:
                status = "Available"
            formatted_slots.append({
                'number': slot['slot_number'],
                'status': status
            })
        
        # Update cache with new data
        parking_metrics_cache.update({
            'total_slots': total_slots,
            'available_slots': available_slots,
            'occupied_slots': occupied_slots,
            'reserved_slots': reserved_slots,
            'occupancy_rate': occupancy_rate,
            'slots': formatted_slots,
            'last_updated': timezone.now()  # Update the timestamp
        })
        
        print(f"🔄 Parking metrics updated at {timezone.now().strftime('%H:%M:%S')} - Available: {available_slots}, Occupied: {occupied_slots}")
        
    except Exception as e:
        print(f"Error updating parking metrics: {e}")

def get_cached_parking_metrics():
    """Get cached parking metrics with automatic 5-second update if needed"""
    # Always check and update if 5 seconds have passed
    update_parking_metrics()
    return parking_metrics_cache



# ==============================
# DECORATORS
# ==============================

def staff_required(view_func):
    return user_passes_test(lambda u: u.is_staff)(view_func)

# ==============================
# AUTHENTICATION & CORE VIEWS
# ==============================

@login_required
def profile(request):
    now = timezone.now()
    
    # Get user's bookings with status handling
    bookings = Booking.objects.filter(user=request.user).order_by('-booked_at')
    
    # Process expired bookings
    for booking in bookings:
        if (
            booking.status == 'confirmed' and 
            booking.start_time + timedelta(minutes=BOOKING_EXPIRY_MINUTES) < now and
            not booking.vehicle_arrived
        ):
            booking.status = 'expired'
            if booking.slot:
                booking.slot.is_reserved = False
                booking.slot.save()
            booking.save()
    
    context = {
        'bookings': bookings,
        'now': now,
    }
    return render(request, 'user/profile.html', context)

def home(request):
    """Home view for guest and logged-in users"""
    guest_id = generate_guest_id(request)
    
    # Process expired bookings
    process_expired_bookings()
    
    # Get booking availability
    booking_availability = get_booking_availability()
    
    response = render(request, 'user/home.html', {
        'guest_id': guest_id,
        'MAX_BOOKABLE_SLOTS': MAX_BOOKABLE_SLOTS,
        'MAX_OCCUPANCY_FOR_BOOKING_PERCENT': MAX_OCCUPANCY_FOR_BOOKING_PERCENT,
        'booking_availability': booking_availability,
    })

    if 'guest_id' not in request.COOKIES:
        response.set_cookie('guest_id', guest_id, max_age=30*24*60*60)

    return response

def signup_view(request):
    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.set_password(form.cleaned_data['password'])
            user.save()
            login(request, user)
            return redirect('home')
    else:
        form = SignUpForm()
    return render(request, 'user/signup.html', {'form': form})

def login_view(request):
    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            return redirect('home')
    else:
        form = AuthenticationForm()
    return render(request, 'user/login.html', {'form': form})

def logout_view(request):
    logout(request)
    return redirect('home')

def guest_login_view(request):
    if not request.session.session_key:
        request.session.create()
    session_key = request.session.session_key
    GuestUser.objects.get_or_create(session_key=session_key)
    request.session['guest_user'] = True
    return redirect('home')

def generate_guest_id(request):
    """Generate or retrieve a unique guest ID from cookies."""
    guest_id = request.COOKIES.get('guest_id')
    if not guest_id:
        guest_id = str(uuid.uuid4())
    return guest_id

# ==============================
# VEHICLE NUMBER VALIDATION
# ==============================

def validate_vehicle_number_server(vehicle_number):
    """
    Server-side validation for vehicle numbers
    """
    # Remove spaces and convert to uppercase
    cleaned = re.sub(r'\s+', '', vehicle_number).upper()
    
    # Check length
    if len(cleaned) > 10:
        return False, "Vehicle number cannot exceed 10 characters"
    
    # Check for at least one alphabet and one numeric
    if not re.search(r'[A-Z]', cleaned) or not re.search(r'[0-9]', cleaned):
        return False, "Vehicle number must contain at least one letter and one number"
    
    # Check for valid characters (only alphanumeric)
    if not re.match(r'^[A-Z0-9]+$', cleaned):
        return False, "Vehicle number can only contain letters and numbers"
    
    return True, cleaned

# ==============================
# BOOKING SYSTEM
# ==============================

@csrf_exempt
def book_slot(request):
    """Handle slot booking with dynamic availability and limits"""
    if request.method == 'POST':
        response_data = {}
        
        try:
            # Get form data
            vehicle_number = request.POST.get('vehicle_number')
            guest_email = request.POST.get('guest_email')
            guest_phone = request.POST.get('guest_phone')
            
            # Server-side vehicle number validation
            is_valid, validation_result = validate_vehicle_number_server(vehicle_number)
            if not is_valid:
                response_data['success'] = False
                response_data['errors'] = {
                    'vehicle_number': [validation_result]
                }
                return JsonResponse(response_data)
            
            # Use cleaned vehicle number
            cleaned_vehicle_number = validation_result
            
            # ===== ADD BOOKING AVAILABILITY CHECK =====
            booking_availability = get_booking_availability()
            if not booking_availability['booking_enabled']:
                response_data['success'] = False
                response_data['errors'] = {
                    '__all__': [f'Booking is temporarily disabled. {booking_availability["booking_disabled_reason"]}']
                }
                return JsonResponse(response_data)
            
            if booking_availability['available_for_booking'] <= 0:
                response_data['success'] = False
                response_data['errors'] = {
                    '__all__': [f'No slots available for booking. Maximum {MAX_BOOKABLE_SLOTS} slots can be booked.']
                }
                return JsonResponse(response_data)
            # ==========================================
            
            # Validate data - Remove time validation since we're using current time
            errors = {}
            if not cleaned_vehicle_number:
                errors['vehicle_number'] = ['Vehicle number is required']
            
            if not request.user.is_authenticated:
                if not guest_email:
                    errors['guest_email'] = ['Email is required for guest bookings']
                if not guest_phone:
                    errors['guest_phone'] = ['Phone number is required for guest bookings']
            
            if errors:
                response_data['success'] = False
                response_data['errors'] = errors
                return JsonResponse(response_data)
            
            # Set times automatically (current time + 30 minutes expiry)
            start_time_dt = timezone.now()
            end_time_dt = start_time_dt + timedelta(minutes=BOOKING_EXPIRY_MINUTES)
            
            # Find available slot
            slot = find_available_slot(start_time_dt, end_time_dt)
            
            if not slot:
                response_data['success'] = False
                response_data['errors'] = {'__all__': ['No available parking slots']}
                return JsonResponse(response_data)
            
            # Create booking
            booking = Booking.objects.create(
                user=request.user if request.user.is_authenticated else None,
                slot=slot,
                vehicle_number=cleaned_vehicle_number,
                start_time=start_time_dt,
                end_time=end_time_dt,
                guest_email=guest_email,
                guest_phone=guest_phone,
                status='confirmed'
            )
            
            # Reserve the slot
            slot.is_reserved = True
            slot.save()
            
            # Update cache immediately after booking
            update_parking_metrics()
            
            response_data['success'] = True
            response_data['redirect_url'] = reverse('booking_confirmation', args=[booking.id])
            return JsonResponse(response_data)
            
        except Exception as e:
            response_data['success'] = False
            response_data['errors'] = {'__all__': [str(e)]}
            return JsonResponse(response_data, status=500)
    
    return JsonResponse({'success': False, 'errors': {'__all__': ['Invalid request method']}}, status=400)

def validate_booking_data(request, vehicle_number, start_time, end_time, user):
    """Validate booking data"""
    errors = {}
    
    if not vehicle_number:
        errors['vehicle_number'] = ['Vehicle number is required']
    
    if not start_time:
        errors['start_time'] = ['Start time is required']
    else:
        try:
            start_dt = datetime.strptime(start_time, '%Y-%m-%dT%H:%M')
            if timezone.make_aware(start_dt) < timezone.now():
                errors['start_time'] = ['Start time cannot be in the past']
        except ValueError:
            errors['start_time'] = ['Invalid start time format']

    if not end_time:
        errors['end_time'] = ['End time is required']
    else:
        try:
            end_dt = datetime.strptime(end_time, '%Y-%m-%dT%H:%M')
            if start_time and end_dt <= datetime.strptime(start_time, '%Y-%m-%dT%H:%M'):
                errors['end_time'] = ['End time must be after start time']
        except ValueError:
            errors['end_time'] = ['Invalid end time format']

    if not user.is_authenticated:
        if not request.POST.get('guest_email'):
            errors['guest_email'] = ['Email is required for guest bookings']
        if not request.POST.get('guest_phone'):
            errors['guest_phone'] = ['Phone number is required for guest bookings']
    
    return errors

def find_available_slot(start_time, end_time):
    """Find available slot considering existing bookings and booking limits"""
    # Get booking availability
    booking_availability = get_booking_availability()
    
    # If booking is disabled or no slots available for booking, return None
    if not booking_availability['booking_enabled'] or booking_availability['available_for_booking'] <= 0:
        return None
    
    # Get all slots
    all_slots = ParkingSlot.objects.all()
    
    # Find slots that are not occupied and don't have conflicting bookings
    available_slots = []
    for slot in all_slots:
        if slot.is_occupied:
            continue
            
        # Check for conflicting bookings
        conflicting_booking = Booking.objects.filter(
            slot=slot,
            status__in=['confirmed', 'active'],
            start_time__lt=end_time,
            end_time__gt=start_time
        ).exists()
        
        if not conflicting_booking:
            available_slots.append(slot)
    
    return available_slots[0] if available_slots else None

def process_expired_bookings():
    """Process bookings that have expired"""
    now = timezone.now()
    expired_bookings = Booking.objects.filter(
        status='confirmed',
        start_time__lte=now - timedelta(minutes=BOOKING_EXPIRY_MINUTES),
        vehicle_arrived=False
    )
    
    for booking in expired_bookings:
        booking.status = 'expired'
        if booking.slot:
            booking.slot.is_reserved = False
            booking.slot.save()
        booking.save()
    
    # Update cache after processing expired bookings
    update_parking_metrics()

@login_required
def booking_confirmation(request, booking_id):
    booking = get_object_or_404(Booking, id=booking_id)
    return render(request, 'user/userconfirmation.html', {'booking': booking})

@login_required
def my_bookings(request):
    now = timezone.now()
    process_expired_bookings()
    
    # Get user's bookings
    bookings = Booking.objects.filter(user=request.user).order_by('-booked_at')
    
    # Calculate statistics
    total_bookings = bookings.count()
    active_bookings = bookings.filter(status='active').count()
    completed_bookings = bookings.filter(status='completed').count()
    expired_bookings = bookings.filter(status='expired').count()
    
    # If no explicit expired status, calculate based on end_time
    if expired_bookings == 0:
        expired_bookings = bookings.filter(
            status='active', 
            end_time__lt=timezone.now()
        ).count()
    
    # Pagination
    paginator = Paginator(bookings, 10)  # 10 bookings per page
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'total_bookings': total_bookings,
        'active_bookings': active_bookings,
        'completed_bookings': completed_bookings,
        'expired_bookings': expired_bookings,
        'now': now,
    }
    return render(request, 'user/list.html', context)

def get_booking_availability():
    """Check if booking is allowed based on current occupancy"""
    try:
        # Use cached metrics for better performance (5-second interval)
        metrics = get_cached_parking_metrics()
        
        total_slots = metrics['total_slots']
        occupied_slots = metrics['occupied_slots']
        reserved_slots = metrics['reserved_slots']
        
        # Calculate current occupancy percentage
        current_occupancy_percent = (occupied_slots / total_slots) * 100 if total_slots > 0 else 0
        
        # Check if we've reached the maximum occupancy for booking
        booking_disabled = current_occupancy_percent >= MAX_OCCUPANCY_FOR_BOOKING_PERCENT
        
        # Calculate available slots for booking
        total_booked_slots = reserved_slots
        available_for_booking = MAX_BOOKABLE_SLOTS - total_booked_slots
        
        return {
            'booking_enabled': not booking_disabled,
            'available_for_booking': max(0, available_for_booking),
            'max_bookable_slots': MAX_BOOKABLE_SLOTS,
            'current_booked_slots': total_booked_slots,
            'current_occupancy_percent': round(current_occupancy_percent, 1),
            'max_occupancy_for_booking': MAX_OCCUPANCY_FOR_BOOKING_PERCENT,
            'booking_disabled_reason': 'Maximum occupancy reached' if booking_disabled else None,
            'total_slots': total_slots,
            'available_slots': metrics['available_slots'],
            'occupied_slots': occupied_slots,
            'last_updated': metrics['last_updated'].isoformat()  # Include timestamp
        }
    except Exception as e:
        print(f"Error checking booking availability: {e}")
        return {
            'booking_enabled': False,
            'available_for_booking': 0,
            'max_bookable_slots': MAX_BOOKABLE_SLOTS,
            'current_booked_slots': 0,
            'current_occupancy_percent': 0,
            'max_occupancy_for_booking': MAX_OCCUPANCY_FOR_BOOKING_PERCENT,
            'booking_disabled_reason': 'System error',
            'total_slots': TOTAL_SLOTS,
            'available_slots': 0,
            'occupied_slots': 0
        }

def can_make_booking():
    """Check if a new booking can be made"""
    availability = get_booking_availability()
    return availability['booking_enabled'] and availability['available_for_booking'] > 0

@login_required
@staff_member_required
def get_booking_availability_api(request):
    """API endpoint for booking availability data"""
    try:
        availability = get_booking_availability()
        return JsonResponse(availability)
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e),
            'booking_enabled': False,
            'available_for_booking': 0,
            'current_booked_slots': 0,
            'max_bookable_slots': MAX_BOOKABLE_SLOTS
        }, status=500)

def expire_booking(request, booking_id):
    """Mark a booking as expired"""
    booking = get_object_or_404(Booking, id=booking_id)
    
    if booking.status == 'active':
        booking.status = 'expired'
        booking.save()
        messages.success(request, f'Booking #{booking.id} has been marked as expired.')
    else:
        messages.error(request, f'Cannot expire booking #{booking.id}. It is not active.')
    
    return redirect('booking_history')

def complete_booking(request, booking_id):
    """Mark a booking as completed"""
    booking = get_object_or_404(Booking, id=booking_id)
    
    if booking.status == 'active':
        booking.status = 'completed'
        booking.save()
        messages.success(request, f'Booking #{booking.id} has been marked as completed.')
    else:
        messages.error(request, f'Cannot complete booking #{booking.id}. It is not active.')
    
    return redirect('booking_history')

# ==============================
# CAMERA & DETECTION SYSTEM
# ==============================



camera = cv2.VideoCapture(0)  # GLOBAL CAMERA INSTANCE

def generate_frames():
    """Capture frames from webcam and run YOLO detection"""
    global latest_detection_data

    if not camera.isOpened():
        print("⚠️ Webcam not found.")
        return

    while True:
        ret, frame = camera.read()
        if not ret:
            continue   # Don't break → keeps feed alive after refresh

        try:
            if model:
                results = model.predict(source=frame, conf=0.5, verbose=False)

                bike_count = 0
                slot_count = 0
                occupied_slots_count = 0

                for box in results[0].boxes:
                    cls = int(box.cls[0])
                    label = model.names[cls]
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    conf = float(box.conf[0])

                    color_map = {
                        "bike": (0, 255, 0),
                        "slot": (255, 255, 0),
                        "occupied": (255, 0, 0),
                        "empty": (0, 255, 255),
                        "others": (255, 0, 255),
                    }
                    color = color_map.get(label.lower(), (255, 255, 255))

                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 3)
                    cv2.rectangle(frame, (x1, y1 - 25), (x1 + 150, y1), color, -1)
                    cv2.putText(frame, f"{label} {conf:.2f}", (x1 + 5, y1 - 5),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 2)

                    if "bike" in label.lower() or "occupied" in label.lower():
                        occupied_slots_count += 1
                        bike_count += 1
                    elif "slot" in label.lower() or "empty" in label.lower():
                        slot_count += 1

                metrics = get_cached_parking_metrics()
                
                latest_detection_data = {
                    'detected_slot': f"Slots: {slot_count}",
                    'bike_count': bike_count,
                    'slot_count': slot_count,
                    'occupied_slots': metrics['occupied_slots'],
                    'available_slots': metrics['available_slots'],
                    'total_slots': metrics['total_slots'],
                    'timestamp': timezone.now().isoformat()
                }

        except Exception as e:
            print(f"Detection error: {e}")

        cv2.putText(frame, f"Available: {latest_detection_data['available_slots']} | Occupied: {latest_detection_data['occupied_slots']}", 
                   (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

        ret, jpeg = cv2.imencode(".jpg", frame)
        if not ret:
            continue

        yield (b"--frame\r\n"
               b"Content-Type: image/jpeg\r\n\r\n" + jpeg.tobytes() + b"\r\n\r\n")

def camera_feed(request):
    """Stream live video feed to browser"""
    return StreamingHttpResponse(generate_frames(),
                                 content_type="multipart/x-mixed-replace; boundary=frame")

def get_detected_slot(request):
    """Return current detected slot data combined with database metrics"""
    global latest_detection_data
    
    # Use cached metrics for stability
    metrics = get_cached_parking_metrics()
    
    response_data = {
        'detected_slot': latest_detection_data.get('detected_slot', 'None'),
        'bike_count': latest_detection_data.get('bike_count', 0),
        'available_slots': metrics['available_slots'],
        'occupied_slots': metrics['occupied_slots'],
        'total_slots': metrics['total_slots'],
        'timestamp': timezone.now().isoformat()
    }
    
    return JsonResponse(response_data)

def get_parking_metrics(request):
    """API endpoint to get real-time parking metrics with 5-second cache"""
    try:
        # Use cached metrics for better performance and stability (5-second interval)
        metrics = get_cached_parking_metrics()
        
        response_data = {
            'total_slots': metrics['total_slots'],
            'available_slots': metrics['available_slots'],
            'occupied_slots': metrics['occupied_slots'],
            'occupancy_rate': metrics['occupancy_rate'],
            'slots': metrics['slots'],
            'timestamp': metrics['last_updated'].isoformat(),
            'cache_interval': '5 seconds',
            'status': 'success'
        }
        
        return JsonResponse(response_data)
        
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e),
            'total_slots': TOTAL_SLOTS,
            'available_slots': 0,
            'occupied_slots': 0,
            'occupancy_rate': 0,
            'slots': [],
        }, status=500)

# ==============================
# ADMIN DASHBOARD & MANAGEMENT
# ==============================

@login_required
@staff_member_required
def admin_dashboard(request):
    """Main admin dashboard view"""
    process_expired_bookings()
    
    # Use cached metrics for better performance
    metrics = get_cached_parking_metrics()
    
    # Get economics data
    today_revenue = EconomicsReport.objects.filter(
        transaction_date__date=timezone.now().date(),
        is_paid=True
    ).aggregate(total=Sum('amount'))['total'] or 0
    
    total_revenue = EconomicsReport.objects.filter(is_paid=True).aggregate(
        total=Sum('amount')
    )['total'] or 0
    
    # Format slots for template using cached data
    formatted_slots = []
    for slot_data in metrics['slots']:
        if slot_data['status'] == "Occupied":
            status_class = "bg-red-100 text-red-800 border-red-300"
            icon_color = "text-red-600"
        elif slot_data['status'] == "Reserved":
            status_class = "bg-yellow-100 text-yellow-800 border-yellow-300"
            icon_color = "text-yellow-600"
        else:
            status_class = "bg-green-100 text-green-800 border-green-300"
            icon_color = "text-green-600"
        
        formatted_slots.append({
            'slot_number': slot_data['number'],
            'status': slot_data['status'],
            'status_class': status_class,
            'icon_color': icon_color,
            'is_occupied': slot_data['status'] == "Occupied",
            'is_reserved': slot_data['status'] == "Reserved"
        })
    
    # Get recent activity
    recent_entries = ParkingHistory.objects.filter(
        timestamp__date=timezone.now().date()
    ).order_by('-timestamp')[:10]
    
    # Get active bookings
    active_bookings = Booking.objects.filter(status='confirmed')[:10]
    
    context = {
        'slots': formatted_slots,
        'total_slots': metrics['total_slots'],
        'occupied_slots': metrics['occupied_slots'],
        'available_slots': metrics['available_slots'],
        'reserved_slots': metrics['reserved_slots'],
        'occupancy_rate': metrics['occupancy_rate'],
        'active_bookings': active_bookings,
        'recent_entries': recent_entries,
        'booking_expiry_minutes': BOOKING_EXPIRY_MINUTES,
        'today_revenue': today_revenue,
        'total_revenue': total_revenue,
    }
    
    return render(request, 'dashboard/admin_dashboard.html', context)

@login_required
@staff_member_required
def get_slot_data(request):
    """API endpoint to get current slot data"""
    try:
        # Use cached metrics for better performance
        metrics = get_cached_parking_metrics()
        
        return JsonResponse({
            'total_slots': metrics['total_slots'],
            'occupied_slots': metrics['occupied_slots'],
            'reserved_slots': metrics['reserved_slots'],
            'current_booked_slots': metrics['reserved_slots'],  # Reserved slots are booked
            'available_slots': metrics['available_slots']
        })
    except Exception as e:
        return JsonResponse({
            'error': str(e),
            'total_slots': TOTAL_SLOTS,
            'occupied_slots': 0,
            'reserved_slots': 0,
            'current_booked_slots': 0,
            'available_slots': TOTAL_SLOTS
        })

def mark_vehicle_arrived(self):
    """Mark vehicle as arrived and update booking status"""
    if not self.vehicle_arrived:
        self.vehicle_arrived = True
        self.status = 'completed'
        
        # Release the slot reservation since vehicle has arrived
        if self.slot:
            self.slot.is_reserved = False  # Remove reservation
            self.slot.is_occupied = True   # Mark as occupied
            self.slot.save()
        
        self.save()
        
        # Update cache immediately
        update_parking_metrics()
        
        return True
    return False

@login_required
@staff_member_required
@csrf_exempt
def admin_manual_entry(request):
    """Manual entry page for recording vehicle entries and exits"""
    if request.method == 'POST':
        try:
            vehicle_number = request.POST.get('vehicle_number', '').strip()
            action = request.POST.get('action', '').strip()
            booking_id = request.POST.get('booking_id', '').strip()
            timestamp_str = request.POST.get('timestamp', '').strip()
            
            print(f"Processing manual {action} for vehicle: {vehicle_number}")
            print(f"Booking ID received: '{booking_id}'")
            print(f"Timestamp received: '{timestamp_str}'")
            print(f"All POST data: {dict(request.POST)}")
            
            # Validate required fields
            if not vehicle_number:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Vehicle number is required.'
                }, status=400)
            
            if not action or action not in ['entry', 'exit']:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Valid action (entry/exit) is required.'
                }, status=400)
            
            # Server-side vehicle number validation
            is_valid, validation_result = validate_vehicle_number_server(vehicle_number)
            if not is_valid:
                return JsonResponse({
                    'status': 'error',
                    'message': validation_result
                }, status=400)
            
            # Use cleaned vehicle number
            cleaned_vehicle_number = validation_result
            
            # Parse timestamp if provided, otherwise use current time
            if timestamp_str:
                try:
                    from datetime import datetime
                    timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                    if timezone.is_naive(timestamp):
                        timestamp = timezone.make_aware(timestamp)
                except (ValueError, TypeError):
                    timestamp = timezone.now()
            else:
                timestamp = timezone.now()
            
            if action == 'entry':
                # Process vehicle entry
                result = process_manual_entry(cleaned_vehicle_number, booking_id, request.user, timestamp)
                
                return JsonResponse({
                    'status': 'success',
                    'message': f'Vehicle {cleaned_vehicle_number} entry recorded successfully in Slot {result["slot_number"]}!',
                    'action': 'entry',
                    'slot_number': result['slot_number'],
                    'ticket_id': result.get('ticket_id'),
                    'receipt_number': result.get('receipt_number'),
                    'economic_record_id': result.get('economic_record_id')
                })
            
            elif action == 'exit':
                # Process vehicle exit
                result = process_manual_exit(cleaned_vehicle_number, request.user, timestamp)
                
                return JsonResponse({
                    'status': 'success',
                    'message': f'Vehicle {cleaned_vehicle_number} exit recorded successfully!',
                    'action': 'exit'
                })
                
        except ValueError as e:
            print(f"ValueError in admin_manual_entry: {str(e)}")
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            }, status=400)
        except Exception as e:
            print(f"Unexpected error in admin_manual_entry: {str(e)}")
            import traceback
            traceback.print_exc()
            return JsonResponse({
                'status': 'error',
                'message': f'An unexpected error occurred: {str(e)}'
            }, status=500)
    
    # GET request - render the manual entry page
    today = timezone.now().date()
    recent_entries = ParkingHistory.objects.filter(
        timestamp__date=today
    ).order_by('-timestamp')[:10]
    
    active_bookings = Booking.objects.filter(status='confirmed')[:10]
    
    context = {
        'recent_entries': recent_entries,
        'active_bookings': active_bookings,
    }
    
    return render(request, 'dashboard/manual_entry.html', context)

@require_GET
def check_vehicle_status(request):
    """Check if a vehicle is already parked"""
    vehicle_number = request.GET.get('vehicle_number', '').strip()
    
    if not vehicle_number:
        return JsonResponse({
            'is_parked': False,
            'message': 'Vehicle number required'
        }, status=400)
    
    # Check if vehicle has an active ticket (not exited yet)
    active_ticket = Ticket.objects.filter(
        vehicle_number__iexact=vehicle_number,
        exit_time__isnull=True  # Vehicle hasn't exited yet
    ).first()
    
    if active_ticket:
        return JsonResponse({
            'is_parked': True,
            'vehicle_number': vehicle_number,
            'slot_number': active_ticket.slot.slot_number if active_ticket.slot else 'Unknown',
            'entry_time': active_ticket.entry_time.isoformat(),
            'message': f'Vehicle {vehicle_number} is already parked in Slot {active_ticket.slot.slot_number}'
        })
    else:
        return JsonResponse({
            'is_parked': False,
            'vehicle_number': vehicle_number,
            'message': 'Vehicle is not currently parked'
        })

def process_manual_entry(vehicle_number, booking_id, user, timestamp):
    """Process manual vehicle entry with receipt generation and economic tracking"""
    try:
        with transaction.atomic():
            slot = None
            booking = None
            
            print(f"Processing entry for vehicle: {vehicle_number}")
            print(f"Booking ID provided: '{booking_id}'")
            print(f"Processing user: {user.username}")
            
            # Check if vehicle already has an active ticket (not exited yet)
            active_ticket = Ticket.objects.filter(
                vehicle_number__iexact=vehicle_number.strip(),
                exit_time__isnull=True  # Vehicle hasn't exited yet
            ).first()
            
            if active_ticket:
                raise ValueError(f"Vehicle {vehicle_number} is already parked in Slot {active_ticket.slot.slot_number}. Please exit the vehicle first.")
            
            # Check for active booking
            active_bookings = Booking.objects.filter(
                vehicle_number__iexact=vehicle_number.strip(),
                status__in=['confirmed', 'active']
            )
            
            if active_bookings.exists():
                booking = active_bookings.first()
                print(f"Found active booking: {booking.id} for vehicle {vehicle_number}")
                slot = booking.slot
                
                if slot and slot.is_occupied:
                    raise ValueError(f"Booked slot {slot.slot_number} is already occupied")
            
            elif booking_id and booking_id.strip():
                try:
                    booking = Booking.objects.get(id=booking_id, status__in=['confirmed', 'active'])
                    slot = booking.slot
                    if slot and slot.is_occupied:
                        raise ValueError(f"Booked slot {slot.slot_number} is already occupied")
                except Booking.DoesNotExist:
                    raise ValueError("Invalid booking ID or booking is not active")
            
            if not slot:
                slot = ParkingSlot.objects.filter(
                    is_occupied=False,
                    is_reserved=False
                ).first()
                if not slot:
                    raise ValueError("No available parking slots")
            
            # Occupy the slot
            slot.is_occupied = True
            slot.is_reserved = False
            slot.save()
            
            # Update booking if exists
            if booking:
                booking.vehicle_arrived = True
                booking.status = 'active'
                booking.save()
            
            # ===== FIX: ALWAYS PASS THE STAFF USER =====
            # For manual entries by staff, always use the staff user
            entry_user = user  # This is the staff user processing the entry
            print(f"Using staff user for economic record: {entry_user.username}")
            # ============================================
            
            # Create ticket (this will generate QR code automatically)
            ticket = Ticket.objects.create(
                vehicle_number=vehicle_number,
                slot=slot,
                booking=booking,
                entry_time=timestamp
            )
            
            # ===== CRITICAL FIX: Pass is_paid parameter =====
            economic_record = create_economic_record(
            vehicle_number=vehicle_number,
            amount=30.00,
            transaction_type='entry_fee',
            ticket=ticket,
            booking=booking,
            payment_method='cash',
            user=entry_user,
            is_paid=True
        )

            
            print(f"DEBUG: Created economic record: {economic_record.id if economic_record else 'None'}")
            if economic_record:
                print(f"DEBUG: Economic record ID: {economic_record.id}")
                print(f"DEBUG: Amount: Rs {economic_record.amount}")
                print(f"DEBUG: Type: {economic_record.transaction_type}")
                print(f"DEBUG: Paid: {economic_record.is_paid}")
                print(f"DEBUG: User: {economic_record.user.username if economic_record.user else 'None'}")
            else:
                print(f"DEBUG: FAILED to create economic record!")
            
            # Create history record
            ParkingHistory.objects.create(
                vehicle_number=vehicle_number,
                action='entered',
                timestamp=timestamp,
                booking=booking,
                is_prebooked=booking is not None,
                user=entry_user
            )
            
            # Update cache immediately
            update_parking_metrics()
            
            return {
                'slot_number': slot.slot_number, 
                'booking_id': booking.id if booking else None,
                'ticket_id': ticket.id,
                'receipt_number': f"R{ticket.id:05d}.2",  # Generate receipt number from ticket ID
                'economic_record_id': economic_record.id if economic_record else None
            }
            
    except Exception as e:
        print(f"Error in process_manual_entry: {str(e)}")
        import traceback
        traceback.print_exc()
        raise ValueError(str(e))
       
def process_manual_exit(vehicle_number, user, timestamp):
    """Process manual vehicle exit"""
    try:
        with transaction.atomic():
            # Find active ticket
            ticket = Ticket.objects.filter(
                vehicle_number=vehicle_number,
                exit_time__isnull=True
            ).first()
            
            if not ticket:
                raise ValueError("No active entry found for this vehicle")
            
            # Set exit time
            ticket.exit_time = timestamp
            ticket.save()
            
            # Free up the slot
            if ticket.slot:
                ticket.slot.is_occupied = False
                ticket.slot.save()
            
            # Update booking if exists
            if ticket.booking:
                ticket.booking.status = 'completed'
                ticket.booking.save()
            
            # Create simple history record with only basic fields
            ParkingHistory.objects.create(
                vehicle_number=vehicle_number,
                action='exited',
                timestamp=timestamp
            )
            
            # Update cache immediately
            update_parking_metrics()
            
            return {}
            
    except Exception as e:
        raise ValueError(f"An error occurred during exit: {str(e)}")

# ==============================
# DASHBOARD AUTHENTICATION
# ==============================

def dashboard_login(request):
    """Admin dashboard login view"""
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        
        if user is not None and (user.is_staff or user.is_superuser):
            login(request, user)
            return redirect('admin_dashboard')
        else:
            messages.error(request, 'Invalid admin credentials')
            return redirect('dashboard_login')
    
    # GET request - show login form
    return render(request, 'dashboard/login.html')

def custom_logout(request):
    """Custom logout for admin dashboard"""
    logout(request)
    return redirect('dashboard_login')

# ==============================
# QUICK BOOKING (ADMIN)
# ==============================

@login_required
@staff_member_required
def create_booking(request):
    """Admin quick booking creation"""
    current_time = timezone.now()
    expire_time = current_time + timedelta(minutes=BOOKING_EXPIRY_MINUTES)
    
    if request.method == 'POST':
        vehicle_number = request.POST.get('vehicle_number')
        
        # Server-side validation
        is_valid, validation_result = validate_vehicle_number_server(vehicle_number)
        if not is_valid:
            messages.error(request, validation_result)
            return render(request, 'dashboard/create_booking.html', {
                'current_time': current_time,
                'expire_time': expire_time,
            })
        
        # Use cleaned vehicle number
        cleaned_vehicle_number = validation_result
        
        if not cleaned_vehicle_number:
            messages.error(request, 'Vehicle number is required')
            return render(request, 'dashboard/create_booking.html', {
                'current_time': current_time,
                'expire_time': expire_time,
            })
        
        try:
            with transaction.atomic():
                # Check booking availability first
                booking_availability = get_booking_availability()
                if not booking_availability['booking_enabled']:
                    messages.error(request, f'Booking is temporarily disabled. {booking_availability["booking_disabled_reason"]}')
                    return render(request, 'dashboard/create_booking.html', {
                        'current_time': current_time,
                        'expire_time': expire_time,
                    })
                
                if booking_availability['available_for_booking'] <= 0:
                    messages.error(request, f'No slots available for booking. Maximum {MAX_BOOKABLE_SLOTS} slots can be booked.')
                    return render(request, 'dashboard/create_booking.html', {
                        'current_time': current_time,
                        'expire_time': expire_time,
                    })
                
                # Find available slot
                slot = ParkingSlot.objects.filter(
                    is_occupied=False,
                    is_reserved=False
                ).first()
                
                if not slot:
                    messages.error(request, 'No available parking slots')
                    return render(request, 'dashboard/create_booking.html', {
                        'current_time': current_time,
                        'expire_time': expire_time,
                    })
                
                # Create booking
                booking = Booking.objects.create(
                    vehicle_number=cleaned_vehicle_number,
                    start_time=current_time,
                    end_time=expire_time,
                    status='confirmed',
                    slot=slot,
                    user=request.user,
                    vehicle_arrived=False
                )
                
                # Reserve the slot
                slot.is_reserved = True
                slot.save()
                
                # Update cache immediately
                update_parking_metrics()
                
                messages.success(request, f'Booking created successfully! Slot {slot.slot_number} assigned.')
                return redirect('booking_history')
                
        except Exception as e:
            messages.error(request, f'Error creating booking: {str(e)}')
            return render(request, 'dashboard/create_booking.html', {
                'current_time': current_time,
                'expire_time': expire_time,
            })
    
    return render(request, 'dashboard/create_booking.html', {
        'current_time': current_time,
        'expire_time': expire_time,
    })

# ==============================
# HISTORY & REPORTS
# ==============================

@login_required
@staff_member_required
def booking_history(request):
    """View all bookings with filtering"""
    bookings = Booking.objects.all().order_by('-booked_at')
    
    # Filter by status
    status_filter = request.GET.get('status')
    if status_filter:
        bookings = bookings.filter(status=status_filter)
    
    # Search functionality
    search_query = request.GET.get('search')
    if search_query:
        bookings = bookings.filter(
            Q(vehicle_number__icontains=search_query) |
            Q(guest_email__icontains=search_query) |
            Q(guest_phone__icontains=search_query) |
            Q(user__username__icontains=search_query)
        )
    
    # Date filtering
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    if date_from:
        bookings = bookings.filter(booked_at__date__gte=date_from)
    if date_to:
        bookings = bookings.filter(booked_at__date__lte=date_to)
    
    # Calculate stats for ALL bookings (not filtered)
    all_bookings = Booking.objects.all()
    total_bookings = all_bookings.count()
    active_bookings = all_bookings.filter(status='active').count()
    completed_bookings = all_bookings.filter(status='completed').count()
    expired_bookings = all_bookings.filter(status='expired').count()
    
    # If no explicit expired status, calculate expired based on end_time
    if not expired_bookings:
        from django.utils import timezone
        expired_bookings = all_bookings.filter(
            status='active', 
            end_time__lt=timezone.now()
        ).count()
    
    # Pagination
    paginator = Paginator(bookings, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'bookings': page_obj,
        'page_obj': page_obj,
        'status_choices': Booking.STATUS_CHOICES,
        'current_status': status_filter,
        'search_query': search_query,
        'date_from': date_from,
        'date_to': date_to,
        # Stats for the cards
        'total_bookings': total_bookings,
        'active_bookings': active_bookings,
        'completed_bookings': completed_bookings,
        'expired_bookings': expired_bookings,
    }
    
    return render(request, 'dashboard/booking_history.html', context)

@login_required
@staff_member_required
def ticket_history(request):
    """Ticket history view"""
    tickets = Ticket.objects.select_related('slot', 'booking').order_by('-entry_time')
    
    search_query = request.GET.get('search', '')
    if search_query:
        tickets = tickets.filter(
            Q(vehicle_number__icontains=search_query) |
            Q(slot__slot_number__icontains=search_query)
        )
    
    paginator = Paginator(tickets, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'search_query': search_query,
    }
    
    return render(request, 'dashboard/ticket_history.html', context)

@login_required
@staff_member_required
def parking_logs(request):
    """Parking history logs with filters"""
    logs = ParkingHistory.objects.all().order_by('-timestamp')

    # Get filters from GET parameters
    search_query = request.GET.get('search', '').strip()
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    # Apply search filter
    if search_query:
        logs = logs.filter(
            Q(vehicle_number__icontains=search_query) |
            Q(action__icontains=search_query)
        )

    # Apply date range filter
    if date_from:
        try:
            date_from_obj = datetime.datetime.strptime(date_from, '%Y-%m-%d')
            logs = logs.filter(timestamp__date__gte=date_from_obj)
        except ValueError:
            pass

    if date_to:
        try:
            date_to_obj = datetime.datetime.strptime(date_to, '%Y-%m-%d')
            logs = logs.filter(timestamp__date__lte=date_to_obj)
        except ValueError:
            pass

    # Pagination
    paginator = Paginator(logs, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # =================== ADD THESE STATISTICS ===================
    
    # 1. Total logs (based on current filters)
    total_logs = logs.count()
    
    # 2. Today's logs (unfiltered - all logs from today)
    today = timezone.now().date()
    today_logs = ParkingHistory.objects.filter(
        timestamp__date=today
    ).count()
    
    # 3. Recent actions distribution (unfiltered - all logs)
    recent_actions = ParkingHistory.objects.values('action')\
        .annotate(count=Count('action'))\
        .order_by('-count')[:5]  # Get top 5 actions
    
    # ============================================================

    return render(request, 'dashboard/parking_logs.html', {
        'page_obj': page_obj,
        'search_query': search_query,
        'date_from': date_from,
        'date_to': date_to,
        # ========== ADD THESE TO CONTEXT ==========
        'total_logs': total_logs,
        'today_logs': today_logs,
        'recent_actions': recent_actions,
        # ==========================================
    })

@login_required
def get_ticket_details(request, ticket_id):
    """API endpoint to get ticket details"""
    try:
        ticket = Ticket.objects.get(id=ticket_id)
        
        ticket_data = {
            'id': ticket.id,
            'vehicle_number': ticket.vehicle_number,
            'slot_number': ticket.slot.slot_number if ticket.slot else None,
            'entry_time': ticket.entry_time.isoformat(),
            'exit_time': ticket.exit_time.isoformat() if ticket.exit_time else None,
            'duration': str(ticket.duration) if ticket.duration else None,
            'fee_amount': str(ticket.fee_amount),
            'fee_paid': ticket.fee_paid,
            'qr_code': ticket.qr_code.url if ticket.qr_code else None,
            'booking': {
                'id': ticket.booking.id,
                'status': ticket.booking.status,
            } if ticket.booking else None
        }
        
        return JsonResponse({
            'status': 'success',
            'ticket': ticket_data
        })
        
    except Ticket.DoesNotExist:
        return JsonResponse({
            'status': 'error',
            'message': 'Ticket not found'
        }, status=404)
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)

# ==============================
# SETTINGS & EXPORTS
# ==============================

@login_required
@staff_member_required
def settings_view(request):
    """Admin settings view"""
    if request.method == 'POST':
        form = UserProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Your settings have been updated!')
            return redirect('settings')
    else:
        form = UserProfileForm(instance=request.user)

    context = {
        'form': form,
    }
    return render(request, 'dashboard/settings.html', context)

@login_required
@staff_member_required
def export_tickets(request):
    """Export tickets to CSV"""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="tickets.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['ID', 'Vehicle', 'Slot', 'Entry Time', 'Exit Time', 'Duration', 'Status'])
    
    tickets = Ticket.objects.all().order_by('-entry_time')
    for ticket in tickets:
        duration = (ticket.exit_time - ticket.entry_time) if ticket.exit_time else (timezone.now() - ticket.entry_time)
        writer.writerow([
            ticket.id,
            ticket.vehicle_number,
            ticket.slot.slot_number if ticket.slot else '-',
            ticket.entry_time.strftime("%Y-%m-%d %H:%M"),
            ticket.exit_time.strftime("%Y-%m-%d %H:%M") if ticket.exit_time else '-',
            str(duration),
            'Completed' if ticket.exit_time else 'Active'
        ])
    
    return response

# ==============================
# UTILITY VIEWS
# ==============================

def check_slots(request):
    """API endpoint to check slot availability"""
    # Use cached metrics for better performance
    metrics = get_cached_parking_metrics()
    return JsonResponse({'slots': metrics['slots']})

@require_GET
def check_availability(request):
    """Check slot availability for given time range"""
    try:
        available_slots = ParkingSlot.objects.filter(
            is_occupied=False,
            is_reserved=False
        )
        
        return JsonResponse({
            'available_slots': [
                {'slot_number': slot.slot_number} 
                for slot in available_slots
            ]
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

def check_booking(request):
    """API endpoint to check for active bookings"""
    vehicle_number = request.GET.get('vehicle_number', '').strip()
    
    if not vehicle_number:
        return JsonResponse({'error': 'Vehicle number required'}, status=400)
    
    booking = Booking.find_active_booking_for_vehicle(vehicle_number)
    
    if booking:
        return JsonResponse({
            'booking_exists': True,
            'booking_id': booking.id,
            'slot_number': booking.slot.slot_number if booking.slot else 'Not assigned',
            'status': booking.status,
            'start_time': booking.start_time.isoformat(),
            'end_time': booking.end_time.isoformat() if booking.end_time else None
        })
    else:
        return JsonResponse({
            'booking_exists': False
        })

@login_required
@staff_member_required
def generate_receipt_pdf(request, ticket_id):
    """Generate PDF receipt from Ticket model"""
    try:
        ticket = Ticket.objects.get(id=ticket_id)
        
        # Create PDF response
        response = HttpResponse(content_type='application/pdf')
        response['Content-Disposition'] = f'inline; filename="receipt_{ticket.id}.pdf"'
        
        # Create PDF
        p = canvas.Canvas(response, pagesize=letter)
        width, height = letter
        
        # Set up coordinates
        x = 1 * inch
        current_y = height - 1 * inch
        
        # Header
        p.setFont("Helvetica-Bold", 12)
        p.drawString(x, current_y, "BikePark Manager")
        current_y -= 0.2 * inch
        
        p.setFont("Helvetica", 10)
        p.drawString(x, current_y, f"iPad7/{ticket.id}-Manager")
        current_y -= 0.2 * inch
        p.drawString(x, current_y, f"Receipt R{ticket.id:05d}.2")
        current_y -= 0.2 * inch
        p.drawString(x, current_y, f"{ticket.entry_time.strftime('%Y-%m-%d, %I:%M %p')}")
        current_y -= 0.2 * inch
        
        # Separator line
        p.line(x, current_y, 7.5 * inch, current_y)
        current_y -= 0.2 * inch
        
        # Vehicle and Slot info
        p.drawString(x, current_y, "=" * 40)
        current_y -= 0.2 * inch
        p.drawString(x, current_y, f"Vehicle: {ticket.vehicle_number}")
        current_y -= 0.2 * inch
        p.drawString(x, current_y, f"Slot: {ticket.slot.slot_number if ticket.slot else 'N/A'}")
        current_y -= 0.2 * inch
        p.drawString(x, current_y, "=" * 40)
        current_y -= 0.2 * inch
        
        # Entry details
        p.drawString(x, current_y, "ENTRY RECEIPT")
        current_y -= 0.2 * inch
        p.drawString(x, current_y, "Payment due on exit")
        current_y -= 0.2 * inch
        
        # Separator
        p.line(x, current_y, 7.5 * inch, current_y)
        current_y -= 0.2 * inch
        
        # Footer
        p.drawString(x, current_y, "VAT:123456")
        current_y -= 0.2 * inch
        p.drawString(x, current_y, "Thank you for your patronage!")
        current_y -= 0.2 * inch
        p.drawString(x, current_y, "BikePark Manager v1.0")
        
        p.showPage()
        p.save()
        
        return response
        
    except Ticket.DoesNotExist:
        return HttpResponse("Ticket not found", status=404)

# ==============================
# ECONOMICS SYSTEM
# ==============================

# In utils.py or at the top of your views.py


def create_economic_record(
    vehicle_number=None,
    amount=30.00,
    transaction_type='entry_fee',
    ticket=None,
    booking=None,
    payment_method='cash',
    user=None,
    subscription_payment=None,  # Keep parameter but don't pass to model if field doesn't exist
    is_paid=None
):
    """Create an economic record for financial tracking"""
    
    # Check if user has subscription and free entry available
    free_entry = False
    entry_user = None
    
    # For subscription payments, skip free entry logic
    if transaction_type not in ['subscription_payment', 'subscription_renewal']:
        if user and user.is_authenticated:
            try:
                if hasattr(user, 'membership'):
                    membership = user.membership
                    
                    # Only check for free entries on entry_fee transactions
                    if transaction_type == 'entry_fee':
                        # Check if user has active subscription
                        if membership.status == 'active':
                            today = timezone.now().date()
                            
                            # Reset counter if it's a new day
                            if membership.last_free_entry_date != today:
                                membership.free_entries_used_today = 0
                                membership.last_free_entry_date = today
                                membership.save()
                            
                            # Check if free entry is available
                            if membership.free_entries_used_today < 1:
                                membership.free_entries_used_today += 1
                                membership.save()
                                
                                amount = 0
                                transaction_type = 'free_entry'
                                payment_method = 'free'
                                free_entry = True
                                entry_user = user
                                
                        else:
                            print(f"DEBUG: Membership not active. Status: {membership.status}")
                else:
                    print(f"DEBUG: User {user.username} has no membership")
                    
            except Exception as e:
                print(f"DEBUG: Error checking membership: {e}")
                import traceback
                traceback.print_exc()
        else:
            print(f"DEBUG: No user or user not authenticated")
    
    try:
        # Determine if the transaction is paid
        if is_paid is None:
            is_paid = (not free_entry and transaction_type not in ['free_entry'])
        
        # Create the economic record with only existing fields
        economic_record = EconomicsReport.objects.create(
            vehicle_number=vehicle_number,
            amount=amount,
            transaction_type=transaction_type,
            ticket=ticket,
            booking=booking,
            payment_method=payment_method,
            is_paid=is_paid,
            user=entry_user if free_entry else user
            # Don't include subscription_payment if the field doesn't exist
        )
        
        print(f"✅ Created economic record:")
        print(f"   ID: {economic_record.id}")
        print(f"   Amount: Rs {amount}")
        print(f"   Type: {transaction_type}")
        print(f"   Paid: {is_paid}")
        print(f"   User: {economic_record.user.username if economic_record.user else 'None'}")
        print(f"   Vehicle: {vehicle_number}")
        
        return economic_record
        
    except Exception as e:
        print(f"❌ Error creating economic record: {e}")
        import traceback
        traceback.print_exc()
        
        # Try alternative approach if the first one fails
        try:
            print("Trying alternative creation method...")
            
            # Create with minimal required fields
            economic_record = EconomicsReport(
                vehicle_number=vehicle_number,
                amount=amount,
                transaction_type=transaction_type,
                payment_method=payment_method,
                is_paid=is_paid,
                user=entry_user if free_entry else user
            )
            
            # Set optional fields if they exist
            if ticket:
                economic_record.ticket = ticket
            if booking:
                economic_record.booking = booking
            
            economic_record.save()
            
            print(f"✅ Created economic record via alternative method: {economic_record.id}")
            return economic_record
            
        except Exception as e2:
            print(f"❌ Alternative method also failed: {e2}")
            return None
              
def create_subscription_economic_record(subscription_payment):
    """Create economic record for subscription payment"""
    try:
        # Get user from subscription
        customer = subscription_payment.subscription.customer
        user = customer.user if hasattr(customer, 'user') else None
        
        # Determine transaction type
        transaction_type = 'subscription_payment'
        if subscription_payment.payment_type == 'renewal':
            transaction_type = 'subscription_renewal'
        
        # Create economic record without subscription_payment field
        economic_record = create_economic_record(
            vehicle_number=None,  # No vehicle for subscription payments
            amount=subscription_payment.amount,
            transaction_type=transaction_type,
            payment_method=subscription_payment.payment_method,
            user=user,
            is_paid=(subscription_payment.status == 'completed')
        )
        
        return economic_record
    except Exception as e:
        print(f"Error creating subscription economic record: {e}")
        return None
       
@login_required
@staff_member_required
def economics_dashboard(request):
    """Economics overview dashboard"""
    try:
        # Calculate totals including subscription payments
        total_revenue = EconomicsReport.objects.filter(is_paid=True).aggregate(
            total=Sum('amount')
        )['total'] or 0
        
        # Separate calculations for different transaction types
        entry_fee_revenue = EconomicsReport.objects.filter(
            is_paid=True,
            transaction_type__in=['entry_fee', 'free_entry']
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        booking_fee_revenue = EconomicsReport.objects.filter(
            is_paid=True,
            transaction_type='booking_fee'
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        subscription_revenue = EconomicsReport.objects.filter(
            is_paid=True,
            transaction_type__in=['subscription_payment', 'subscription_renewal']
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        today = timezone.now().date()
        today_revenue = EconomicsReport.objects.filter(
            is_paid=True,
            transaction_date__date=today
        ).aggregate(total=Sum('amount'))['total'] or 0
        
        # Get ALL transactions for pagination
        all_transactions = EconomicsReport.objects.select_related(
            'ticket', 'booking', 'user'
        ).order_by('-transaction_date')
        
        # Paginate all transactions
        paginator = Paginator(all_transactions, 10)  # 10 per page
        page_number = request.GET.get('page', 1)
        
        try:
            page_obj = paginator.page(page_number)
        except PageNotAnInteger:
            page_obj = paginator.page(1)
        except EmptyPage:
            page_obj = paginator.page(paginator.num_pages)
        
        # Count transactions by type
        transaction_count_by_type = {
            'entry_fee': EconomicsReport.objects.filter(
                transaction_type__in=['entry_fee', 'free_entry']
            ).count(),
            'booking_fee': EconomicsReport.objects.filter(
                transaction_type='booking_fee'
            ).count(),
            'subscription': EconomicsReport.objects.filter(
                transaction_type__in=['subscription_payment', 'subscription_renewal']
            ).count(),
        }
        
        today_count = EconomicsReport.objects.filter(
            transaction_date__date=today
        ).count()
        
        context = {
            'total_revenue': total_revenue,
            'today_revenue': today_revenue,
            'entry_fee_revenue': entry_fee_revenue,
            'booking_fee_revenue': booking_fee_revenue,
            'subscription_revenue': subscription_revenue,
            'page_obj': page_obj,  # This contains paginated transactions
            'transaction_count': EconomicsReport.objects.count(),
            'transaction_count_by_type': transaction_count_by_type,
            'today_count': today_count,
        }
        
        return render(request, 'dashboard/economics_dashboard.html', context)
        
    except Exception as e:
        print(f"ERROR in economics_dashboard: {e}")
        import traceback
        traceback.print_exc()
        return HttpResponse(f"Error: {e}")
@login_required
@staff_member_required
def economics_report(request):
    """Detailed economics report with filtering"""
    transactions = EconomicsReport.objects.select_related('ticket', 'booking').order_by('-transaction_date')  # Changed to transaction_date
    
    # Apply filters
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    transaction_type = request.GET.get('transaction_type')
    
    if date_from:
        transactions = transactions.filter(transaction_date__date__gte=date_from)  # Changed to transaction_date
    if date_to:
        transactions = transactions.filter(transaction_date__date__lte=date_to)  # Changed to transaction_date
    if transaction_type:
        transactions = transactions.filter(transaction_type=transaction_type)
    
    # Calculate filtered totals
    filtered_total = transactions.aggregate(total=Sum('amount'))['total'] or 0
    filtered_count = transactions.count()
    
    # Pagination
    paginator = Paginator(transactions, 25)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'filtered_total': filtered_total,
        'filtered_count': filtered_count,
        'date_from': date_from,
        'date_to': date_to,
        'transaction_type': transaction_type,
        'transaction_types': EconomicsReport._meta.get_field('transaction_type').choices,
    }
    
    return render(request, 'dashboard/economics_report.html', context)

@login_required
@staff_member_required
def export_economics_csv(request):
    """Export economics data to CSV"""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="economics_report.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['ID', 'Type', 'Details', 'Amount (PKR)', 'Transaction Type', 
                    'Payment Method', 'Customer/Vehicle', 'Email', 'Transaction Date', 'Status'])
    
    transactions = EconomicsReport.objects.select_related('user', 'subscription_payment').all().order_by('-transaction_date')  # Changed to transaction_date
    
    for transaction in transactions:
        # Determine details based on transaction type
        if transaction.transaction_type in ['subscription_payment', 'subscription_renewal']:
            details = "Subscription Payment"
            customer_info = transaction.user.get_full_name() if transaction.user else "N/A"
            email = transaction.user.email if transaction.user else "N/A"
        else:
            details = transaction.vehicle_number or "N/A"
            customer_info = transaction.user.username if transaction.user else "N/A"
            email = transaction.user.email if transaction.user else "N/A"
        
        writer.writerow([
            transaction.id,
            'Subscription' if transaction.transaction_type in ['subscription_payment', 'subscription_renewal'] else 'Vehicle',
            details,
            transaction.amount,
            transaction.get_transaction_type_display(),
            transaction.get_payment_method_display(),
            customer_info,
            email,
            transaction.transaction_date.strftime("%Y-%m-%d %H:%M"),  # Changed to transaction_date
            'Paid' if transaction.is_paid else 'Pending'
        ])
    
    return response

@login_required
@staff_member_required
def economics_summary_api(request):
    """API endpoint for economics summary data"""
    try:
        # Today's stats
        today = timezone.now().date()
        today_stats = EconomicsReport.objects.filter(
            transaction_date__date=today,  # Changed to transaction_date
            is_paid=True
        ).aggregate(
            total=Sum('amount'),
            count=Count('id')
        )
        
        # Weekly stats
        week_ago = today - timedelta(days=7)
        weekly_stats = EconomicsReport.objects.filter(
            transaction_date__date__gte=week_ago,  # Changed to transaction_date
            is_paid=True
        ).aggregate(
            total=Sum('amount'),
            count=Count('id')
        )
        
        # Monthly stats
        month_ago = today - timedelta(days=30)
        monthly_stats = EconomicsReport.objects.filter(
            transaction_date__date__gte=month_ago,  # Changed to transaction_date
            is_paid=True
        ).aggregate(
            total=Sum('amount'),
            count=Count('id')
        )
        
        return JsonResponse({
            'status': 'success',
            'today': {
                'revenue': float(today_stats['total'] or 0),
                'transactions': today_stats['count'] or 0
            },
            'weekly': {
                'revenue': float(weekly_stats['total'] or 0),
                'transactions': weekly_stats['count'] or 0
            },
            'monthly': {
                'revenue': float(monthly_stats['total'] or 0),
                'transactions': monthly_stats['count'] or 0
            },
            'all_time': {
                'revenue': float(EconomicsReport.objects.filter(is_paid=True).aggregate(total=Sum('amount'))['total'] or 0),
                'transactions': EconomicsReport.objects.count()
            }
        })
        
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        }, status=500)
        
@login_required
@staff_member_required
def recent_transactions_api(request):
    """API endpoint for recent transactions (for AJAX if needed)"""
    try:
        page = int(request.GET.get('page', 1))
        per_page = int(request.GET.get('per_page', 10))
        
        transactions = EconomicsReport.objects.select_related(
            'ticket', 'booking', 'user'
        ).order_by('-transaction_date')
        
        paginator = Paginator(transactions, per_page)
        
        try:
            page_obj = paginator.page(page)
        except PageNotAnInteger:
            page_obj = paginator.page(1)
        except EmptyPage:
            page_obj = paginator.page(paginator.num_pages)
        
        data = []
        for t in page_obj:
            is_subscription = t.transaction_type in ['subscription_payment', 'subscription_renewal']
            
            data.append({
                "id": t.id,
                "vehicle_number": t.vehicle_number,
                "amount": float(t.amount),
                "transaction_type": t.transaction_type,
                "transaction_type_display": t.get_transaction_type_display()
                    if hasattr(t, 'get_transaction_type_display')
                    else t.transaction_type.replace('_', ' ').title(),
                "payment_method_display": t.payment_method.title()
                    if t.payment_method else "—",
                "transaction_date": t.transaction_date.isoformat(),
                "is_subscription": is_subscription,
                "user_name": t.user.username if t.user else None,
                "customer_name": t.user.get_full_name() if (is_subscription and t.user) else None,
                "customer_email": t.user.email if (is_subscription and t.user) else None,
                "is_paid": t.is_paid,
            })
        
        return JsonResponse({
            "status": "success",
            "transactions": data,
            "current_page": page_obj.number,
            "total_pages": paginator.num_pages,
            "total_count": paginator.count,
            "has_previous": page_obj.has_previous(),
            "has_next": page_obj.has_next(),
            "previous_page": page_obj.previous_page_number() if page_obj.has_previous() else None,
            "next_page": page_obj.next_page_number() if page_obj.has_next() else None,
        })
        
    except Exception as e:
        return JsonResponse({
            "status": "error",
            "message": str(e)
        }, status=500)
    
# ==============================
# STRIPE INTEGRATION
# ==============================






stripe.api_key = settings.STRIPE_SECRET_KEY

@login_required
@require_POST
@csrf_exempt
def create_payment_intent(request):
    """
    Create a Stripe Checkout Session for subscription payment
    """
    try:
        data = json.loads(request.body)
        amount = int(data['amount'])
        plan_type = data['plan_type']
        
        # Check if user already has active subscription
        try:
            if hasattr(request.user, 'membership'):
                membership = request.user.membership
                if membership.status == 'active' and not membership.cancel_at_period_end:
                    return JsonResponse({
                        'error': 'You already have an active subscription.'
                    }, status=400)
        except Exception as e:
            # User has no membership, allow subscription
            pass
        
        # Get plan from database based on plan_type
        try:
            if plan_type == 'monthly':
                plan = MembershipPlan.objects.get(name='Monthly Parking Plan')
            elif plan_type == 'yearly':
                plan = MembershipPlan.objects.get(name='Yearly Parking Plan')
            else:
                return JsonResponse({'error': 'Invalid plan type'}, status=400)
            
            price_id = plan.stripe_price_id
        except MembershipPlan.DoesNotExist:
            # If plan doesn't exist in database, create it dynamically
            if plan_type == 'monthly':
                # Create monthly price dynamically
                price = stripe.Price.create(
                    unit_amount=80000,
                    currency='pkr',
                    recurring={'interval': 'month'},
                    product_data={'name': 'Monthly Parking Plan'},
                )
                price_id = price.id
                
                # Save to database
                MembershipPlan.objects.create(
                    name='Monthly Parking Plan',
                    stripe_price_id=price_id,
                    price=800,
                    interval='month',
                    description='Monthly subscription for bike parking'
                )
            elif plan_type == 'yearly':
                # Create yearly price dynamically
                price = stripe.Price.create(
                    unit_amount=800000,
                    currency='pkr',
                    recurring={'interval': 'year'},
                    product_data={'name': 'Yearly Parking Plan'},
                )
                price_id = price.id
                
                # Save to database
                MembershipPlan.objects.create(
                    name='Yearly Parking Plan',
                    stripe_price_id=price_id,
                    price=8000,
                    interval='year',
                    description='Yearly subscription for bike parking'
                )
            else:
                return JsonResponse({'error': 'Invalid plan type'}, status=400)
        
        # Create or get Stripe customer
        customer_id = None
        try:
            if hasattr(request.user, 'membership') and request.user.membership.stripe_customer_id:
                customer_id = request.user.membership.stripe_customer_id
            else:
                customer = stripe.Customer.create(
                    email=request.user.email,
                    name=request.user.get_full_name() or request.user.username,
                    metadata={'user_id': request.user.id}
                )
                customer_id = customer.id
        except Exception as e:
            print(f"Error creating Stripe customer: {e}")
            # Continue without customer for now
        
        # Build absolute URLs
        base_url = request.build_absolute_uri('/').rstrip('/')
        
        # Create Checkout Session
        session = stripe.checkout.Session.create(
            customer=customer_id,
            payment_method_types=['card'],
            line_items=[{
                'price': price_id,
                'quantity': 1,
            }],
            mode='subscription',
            success_url=f"{base_url}/payment-success/?session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{base_url}/payment-cancelled/",
            metadata={
                'user_id': request.user.id,
                'plan_type': plan_type
            },
            subscription_data={
                'metadata': {
                    'user_id': request.user.id,
                    'plan_type': plan_type
                }
            }
        )
        
        # Store session ID in user session
        request.session['stripe_session_id'] = session.id
        
        return JsonResponse({
            'sessionId': session.id,
            'url': session.url
        })
        
    except stripe.error.StripeError as e:
        print(f"Stripe error: {str(e)}")
        return JsonResponse({'error': str(e)}, status=400)
    except Exception as e:
        print(f"Server error: {str(e)}")
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def payment_success(request):
    """
    Handle successful subscription payment
    """
    try:
        session_id = request.GET.get('session_id') or request.session.get('stripe_session_id')
        
        if not session_id:
            return render(request, 'user/payment_error.html', {
                'error': 'No payment session found'
            })
        
        # Retrieve the session
        session = stripe.checkout.Session.retrieve(session_id)
        
        # Get plan type
        plan_type = session.metadata.get('plan_type', 'monthly')
        
        # Create or update UserMembership
        membership, created = UserMembership.objects.get_or_create(
            user=request.user
        )
        
        # Update basic fields
        if session.customer:
            membership.stripe_customer_id = session.customer
        
        if session.subscription:
            membership.stripe_subscription_id = session.subscription
        
        membership.status = 'active'
        membership.subscription_start_date = timezone.now()
        
        # Set period dates and plan price based on plan type
        if plan_type == 'monthly':
            membership.current_period_end = timezone.now() + timedelta(days=30)
            plan_price = 800
        elif plan_type == 'yearly':
            membership.current_period_end = timezone.now() + timedelta(days=365)
            plan_price = 8000
        else:
            # Default to monthly if unknown
            membership.current_period_end = timezone.now() + timedelta(days=30)
            plan_price = 800
        
        # Get or create MembershipPlan
        if plan_type == 'monthly':
            plan, _ = MembershipPlan.objects.get_or_create(
                name='Monthly Parking Plan',
                defaults={'price': 800, 'interval': 'month'}
            )
        else:
            plan, _ = MembershipPlan.objects.get_or_create(
                name='Yearly Parking Plan',
                defaults={'price': 8000, 'interval': 'year'}
            )
        
        membership.plan = plan
        membership.save()
        
        # ===== CREATE SUBSCRIPTION ECONOMICS RECORD =====
        try:
            economic_record = create_economic_record(
                vehicle_number=f"SUBSCRIPTION-{request.user.id}",
                amount=plan_price,
                transaction_type='subscription_payment',
                payment_method='card',
                user=request.user,
                is_paid=True
            )
            
            if economic_record:
                print(f"✅ Subscription payment recorded:")
                print(f"   ID: {economic_record.id}")
                print(f"   Amount: Rs {plan_price}")
                print(f"   Type: {economic_record.transaction_type}")
                print(f"   User: {request.user.username}")
            else:
                print(f"❌ Failed to create subscription economics record")
                
        except Exception as e:
            print(f"❌ Error recording subscription payment: {e}")
            import traceback
            traceback.print_exc()
        # ================================================
        
        # Clear session
        if 'stripe_session_id' in request.session:
            del request.session['stripe_session_id']
        
        context = {
            'amount': plan_price,
            'plan_type': plan_type,
            'payment_status': 'succeeded'
        }
        
        return render(request, 'user/payment_success.html', context)
        
    except Exception as e:
        print(f"Error in payment_success: {e}")
        import traceback
        traceback.print_exc()
        return render(request, 'user/payment_error.html', {
            'error': f"Payment successful but there was an error updating your account. Contact support with this code: {session_id}"
        })
    
def payment_cancelled(request):
    """
    Handle cancelled payment
    """
    # Clear any session data
    if 'stripe_session_id' in request.session:
        del request.session['stripe_session_id']
        
    return render(request, 'user/payment_cancelled.html')

@csrf_exempt
@require_POST
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')
    
    print(f"Webhook received! Headers: {dict(request.META)}")
    print(f"Payload length: {len(payload)}")
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
        print(f"✅ Webhook verified! Event type: {event['type']}")
        
    except ValueError as e:
        print(f"❌ Invalid payload: {e}")
        return HttpResponse(status=400)
    except stripe.error.SignatureVerificationError as e:
        print(f"❌ Invalid signature: {e}")
        return HttpResponse(status=400)
    except Exception as e:
        print(f"❌ Other error: {e}")
        return HttpResponse(status=400)
    
    # Handle the event
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        print(f"✅ Checkout completed! Session ID: {session['id']}")
        print(f"   Customer: {session.get('customer')}")
        print(f"   Subscription: {session.get('subscription')}")
        print(f"   Payment status: {session.get('payment_status')}")
        
    elif event['type'] == 'customer.subscription.created':
        subscription = event['data']['object']
        print(f"✅ Subscription created! ID: {subscription['id']}")
        print(f"   Status: {subscription['status']}")
        
    elif event['type'] == 'customer.subscription.updated':
        subscription = event['data']['object']
        print(f"📝 Subscription updated! ID: {subscription['id']}")
        print(f"   Status: {subscription['status']}")
        
    elif event['type'] == 'customer.subscription.deleted':
        subscription = event['data']['object']
        print(f"🗑️ Subscription deleted! ID: {subscription['id']}")
        
    else:
        print(f"ℹ️ Unhandled event type: {event['type']}")
    
    return HttpResponse(status=200)

def handle_subscription_update(subscription):
    """Update UserMembership when subscription changes"""
    try:
        membership = UserMembership.objects.get(
            stripe_subscription_id=subscription.id
        )
        
        membership.status = subscription.status
        membership.current_period_start = datetime.fromtimestamp(
            subscription.current_period_start
        )
        membership.current_period_end = datetime.fromtimestamp(
            subscription.current_period_end
        )
        membership.cancel_at_period_end = subscription.cancel_at_period_end
        membership.save()
        
    except UserMembership.DoesNotExist:
        pass

def handle_subscription_cancellation(subscription):
    """Handle subscription cancellation"""
    try:
        membership = UserMembership.objects.get(
            stripe_subscription_id=subscription.id
        )
        
        membership.status = 'canceled'
        membership.save()
        
    except UserMembership.DoesNotExist:
        pass


def safe_from_timestamp(timestamp):
    """Safely convert timestamp to datetime, return None if invalid"""
    if timestamp:
        try:
            return datetime.fromtimestamp(timestamp)
        except (TypeError, ValueError):
            return None
    return None


# ==============================
# STAFF MANAGEMENT (ADMIN)
# ==============================

@login_required
@staff_member_required
def staff_list(request):
    """View and manage staff members"""
    # Get all staff members (is_staff=True)
    staff_members = User.objects.filter(is_staff=True).order_by('-date_joined')
    
    # Search functionality
    search_query = request.GET.get('search', '')
    if search_query:
        staff_members = staff_members.filter(
            Q(username__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query)
        )
    
    # Filter by status
    status_filter = request.GET.get('status', '')
    if status_filter == 'active':
        staff_members = staff_members.filter(is_active=True)
    elif status_filter == 'inactive':
        staff_members = staff_members.filter(is_active=False)
    
    # Filter by role
    role_filter = request.GET.get('role', '')
    if role_filter == 'superuser':
        staff_members = staff_members.filter(is_superuser=True)
    elif role_filter == 'staff':
        staff_members = staff_members.filter(is_superuser=False)
    
    # Sorting
    sort_by = request.GET.get('sort', 'newest')
    if sort_by == 'oldest':
        staff_members = staff_members.order_by('date_joined')
    elif sort_by == 'name':
        staff_members = staff_members.order_by('first_name', 'last_name')
    elif sort_by == 'username':
        staff_members = staff_members.order_by('username')
    else:  # newest
        staff_members = staff_members.order_by('-date_joined')
    
    # Calculate statistics
    total_staff = User.objects.filter(is_staff=True).count()
    active_staff = User.objects.filter(is_staff=True, is_active=True).count()
    superusers = User.objects.filter(is_superuser=True).count()
    
    # Get recent staff additions (last 30 days)
    thirty_days_ago = timezone.now() - timedelta(days=30)
    recent_additions = User.objects.filter(
        is_staff=True,
        date_joined__gte=thirty_days_ago
    ).count()
    
    # Get recent staff for display
    recent_staff = User.objects.filter(is_staff=True).order_by('-date_joined')[:5]
    
    # Pagination
    paginator = Paginator(staff_members, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'total_staff': total_staff,
        'active_staff': active_staff,
        'superusers': superusers,
        'recent_additions': recent_additions,
        'recent_staff': recent_staff,
        'search_query': search_query,
        'status_filter': status_filter,
        'role_filter': role_filter,
        'sort_by': sort_by,
    }
    
    return render(request, 'dashboard/staff_list.html', context)

@login_required
@staff_member_required
def create_staff(request):
    """Create new staff member"""
    if request.method == 'POST':
        form = StaffCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, f'Staff member {user.username} created successfully!')
            
            # Log this action
            UserActivityLog.objects.create(
                user=request.user,
                action='staff_created',
                details=json.dumps({
                    'staff_username': user.username,
                    'staff_email': user.email,
                    'is_superuser': user.is_superuser,
                    'created_by': request.user.username
                }),
                ip_address=request.META.get('REMOTE_ADDR', ''),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
            
            return redirect('staff_list')
    else:
        form = StaffCreationForm()
    
    context = {
        'form': form,
        'title': 'Add New Staff Member'
    }
    return render(request, 'dashboard/create_staff.html', context)

@login_required
@staff_member_required
def edit_staff(request, user_id):
    """Edit staff member"""
    user = get_object_or_404(User, id=user_id, is_staff=True)
    
    if request.method == 'POST':
        form = StaffEditForm(request.POST, instance=user)
        if form.is_valid():
            user = form.save()
            messages.success(request, f'Staff member {user.username} updated successfully!')
            
            # Log this action
            UserActivityLog.objects.create(
                user=request.user,
                action='staff_updated',
                details=json.dumps({
                    'staff_username': user.username,
                    'updated_by': request.user.username
                }),
                ip_address=request.META.get('REMOTE_ADDR', ''),
                user_agent=request.META.get('HTTP_USER_AGENT', '')
            )
            
            return redirect('staff_list')
    else:
        form = StaffEditForm(instance=user)
    
    context = {
        'form': form,
        'title': f'Edit Staff Member: {user.username}',
        'user': user
    }
    return render(request, 'dashboard/create_staff.html', context)

@login_required
@staff_member_required
def toggle_staff_status(request, user_id):
    """Toggle staff active status"""
    user = get_object_or_404(User, id=user_id, is_staff=True)
    
    # Prevent self-deactivation
    if user == request.user:
        messages.error(request, 'You cannot deactivate your own account!')
        return redirect('staff_list')
    
    user.is_active = not user.is_active
    user.save()
    
    status = 'activated' if user.is_active else 'deactivated'
    messages.success(request, f'Staff member {user.username} {status} successfully!')
    
    # Log this action
    UserActivityLog.objects.create(
        user=request.user,
        action='staff_status_changed',
        details=json.dumps({
            'staff_username': user.username,
            'new_status': status,
            'changed_by': request.user.username
        }),
        ip_address=request.META.get('REMOTE_ADDR', ''),
        user_agent=request.META.get('HTTP_USER_AGENT', '')
    )
    
    return redirect('staff_list')

@login_required
@staff_member_required
def delete_staff(request, user_id):
    """Delete staff member"""
    user = get_object_or_404(User, id=user_id, is_staff=True)
    
    # Prevent self-deletion
    if user == request.user:
        messages.error(request, 'You cannot delete your own account!')
        return redirect('staff_list')
    
    # Prevent deletion of superusers by non-superusers
    if user.is_superuser and not request.user.is_superuser:
        messages.error(request, 'Only superusers can delete other superusers!')
        return redirect('staff_list')
    
    if request.method == 'POST':
        username = user.username
        user.delete()
        messages.success(request, f'Staff member {username} deleted successfully!')
        
        # Log this action
        UserActivityLog.objects.create(
            user=request.user,
            action='staff_deleted',
            details=json.dumps({
                'staff_username': username,
                'deleted_by': request.user.username
            }),
            ip_address=request.META.get('REMOTE_ADDR', ''),
            user_agent=request.META.get('HTTP_USER_AGENT', '')
        )
        
        return redirect('staff_list')
    
    context = {
        'user': user,
        'title': 'Confirm Staff Deletion'
    }
    return render(request, 'dashboard/confirm_delete.html', context)

@login_required
@staff_member_required
def staff_detail(request, user_id):
    """View detailed staff information"""
    staff = get_object_or_404(User, id=user_id, is_staff=True)
    
    # Get staff statistics
    staff_logs = UserActivityLog.objects.filter(user=staff).count()
    staff_recent_logs = UserActivityLog.objects.filter(user=staff).order_by('-timestamp')[:10]
    
    # Get activity distribution
    activity_distribution = UserActivityLog.objects.filter(user=staff).values('action').annotate(
        count=Count('id')
    ).order_by('-count')[:5]
    
    context = {
        'staff': staff,
        'staff_logs': staff_logs,
        'staff_recent_logs': staff_recent_logs,
        'activity_distribution': activity_distribution,
    }
    
    return render(request, 'dashboard/staff_detail.html', context)

@login_required
@staff_member_required
def export_staff_csv(request):
    """Export staff list to CSV"""
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="staff_list.csv"'
    
    writer = csv.writer(response)
    writer.writerow(['ID', 'Username', 'Email', 'First Name', 'Last Name', 
                     'Is Superuser', 'Is Active', 'Last Login', 'Date Joined'])
    
    staff_members = User.objects.filter(is_staff=True).order_by('username')
    
    for staff in staff_members:
        writer.writerow([
            staff.id,
            staff.username,
            staff.email,
            staff.first_name,
            staff.last_name,
            'Yes' if staff.is_superuser else 'No',
            'Yes' if staff.is_active else 'No',
            staff.last_login.strftime("%Y-%m-%d %H:%M:%S") if staff.last_login else 'Never',
            staff.date_joined.strftime("%Y-%m-%d %H:%M:%S")
        ])
    
    return response

# ==============================
# SYSTEM LOGS (ADMIN)
# ==============================

@login_required
@staff_member_required
def system_logs(request):
    """View system activity logs using UserActivityLog"""
    logs = UserActivityLog.objects.all().order_by('-timestamp')
    
    # Search functionality
    search_query = request.GET.get('search', '')
    if search_query:
        logs = logs.filter(
            Q(action__icontains=search_query) |
            Q(details__icontains=search_query) |
            Q(ip_address__icontains=search_query) |
            Q(user__username__icontains=search_query) |
            Q(user__first_name__icontains=search_query) |
            Q(user__last_name__icontains=search_query)
        )
    
    # Filter by user
    user_id = request.GET.get('user_id')
    if user_id and user_id != '':
        logs = logs.filter(user_id=user_id)
    
    # Filter by date range
    date_from = request.GET.get('date_from')
    date_to = request.GET.get('date_to')
    
    if date_from:
        logs = logs.filter(timestamp__date__gte=date_from)
    if date_to:
        logs = logs.filter(timestamp__date__lte=date_to)
    
    # Get all users for filter dropdown
    all_users = User.objects.filter(
        Q(is_staff=True) | Q(is_superuser=True) | Q(useractivitylog__isnull=False)
    ).distinct().order_by('username')
    
    # Get statistics
    total_logs = logs.count()
    today_logs = UserActivityLog.objects.filter(
        timestamp__date=timezone.now().date()
    ).count()
    
    # Error logs (detected by severity)
    error_logs = logs.filter(
        Q(action__icontains='error') |
        Q(action__icontains='failed') |
        Q(action__icontains='exception') |
        Q(action__icontains='critical') |
        Q(action__icontains='denied')
    ).count()
    
    # Unique users
    unique_users = logs.values('user').distinct().count()
    
    # Event type distribution (using template filter logic)
    event_distribution = []
    event_categories = ['auth', 'security', 'system', 'admin', 'database', 'performance', 'integration', 'application']
    
    for event_type in event_categories:
        # Count based on action keywords
        count = 0
        if event_type == 'auth':
            count = logs.filter(
                Q(action__icontains='login') |
                Q(action__icontains='logout') |
                Q(action__icontains='password') |
                Q(action__icontains='auth')
            ).count()
        elif event_type == 'security':
            count = logs.filter(
                Q(action__icontains='security') |
                Q(action__icontains='failed') |
                Q(action__icontains='attempt') |
                Q(action__icontains='unauthorized') |
                Q(action__icontains='block')
            ).count()
        elif event_type == 'system':
            count = logs.filter(
                Q(action__icontains='system') |
                Q(action__icontains='clear') |
                Q(action__icontains='export') |
                Q(action__icontains='maintenance')
            ).count()
        elif event_type == 'admin':
            count = logs.filter(
                Q(action__icontains='admin') |
                Q(action__icontains='staff') |
                Q(action__icontains='reset') |
                Q(action__icontains='permission')
            ).count()
        elif event_type == 'database':
            count = logs.filter(
                Q(action__icontains='database') |
                Q(action__icontains='delete') |
                Q(action__icontains='clean')
            ).count()
        elif event_type == 'performance':
            count = logs.filter(
                Q(action__icontains='performance') |
                Q(action__icontains='slow') |
                Q(action__icontains='timeout')
            ).count()
        elif event_type == 'integration':
            count = logs.filter(
                Q(action__icontains='api') |
                Q(action__icontains='stripe') |
                Q(action__icontains='payment') |
                Q(action__icontains='webhook')
            ).count()
        else:  # application
            count = logs.exclude(
                Q(action__icontains='login') |
                Q(action__icontains='logout') |
                Q(action__icontains='security') |
                Q(action__icontains='system') |
                Q(action__icontains='admin') |
                Q(action__icontains='database') |
                Q(action__icontains='performance') |
                Q(action__icontains='integration')
            ).count()
        
        if count > 0:
            event_distribution.append({
                'event_type': event_type,
                'count': count
            })
    
    # Pagination
    paginator = Paginator(logs, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'total_logs': total_logs,
        'today_logs': today_logs,
        'error_logs': error_logs,
        'unique_users': unique_users,
        'all_users': all_users,
        'search_query': search_query,
        'selected_user': user_id,
        'date_from': date_from,
        'date_to': date_to,
        'event_distribution': event_distribution,
    }
    
    return render(request, 'dashboard/user_logs.html', context)

@login_required
@staff_member_required
def export_system_logs_csv(request):
    """Export system logs to CSV"""
    import csv
    from django.http import HttpResponse
    
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="system_logs.csv"'
    
    writer = csv.writer(response)
    writer.writerow([
        'ID', 'Timestamp', 'Event Type', 'Severity', 'User', 
        'Username', 'Action', 'Details', 'IP Address', 'User Agent'
    ])
    
    logs = UserActivityLog.objects.all().order_by('-timestamp')
    
    for log in logs:
        # Determine event type and severity from action
        action_lower = log.action.lower()
        
        # Event type detection
        event_type = 'Application'
        if any(word in action_lower for word in ['login', 'logout', 'password', 'auth']):
            event_type = 'Authentication'
        elif any(word in action_lower for word in ['security', 'failed', 'attempt', 'unauthorized']):
            event_type = 'Security'
        elif any(word in action_lower for word in ['system', 'clear', 'export', 'maintenance']):
            event_type = 'System'
        elif any(word in action_lower for word in ['admin', 'staff', 'reset', 'permission']):
            event_type = 'Administrative'
        elif any(word in action_lower for word in ['database', 'delete', 'clean']):
            event_type = 'Database'
        elif any(word in action_lower for word in ['performance', 'slow', 'timeout']):
            event_type = 'Performance'
        elif any(word in action_lower for word in ['api', 'stripe', 'payment', 'webhook']):
            event_type = 'Integration'
        
        # Severity detection
        severity = 'Info'
        if any(word in action_lower for word in ['critical', 'fatal']):
            severity = 'Critical'
        elif any(word in action_lower for word in ['error', 'failed', 'exception']):
            severity = 'Error'
        elif any(word in action_lower for word in ['warning', 'alert']):
            severity = 'Warning'
        
        writer.writerow([
            log.id,
            log.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            event_type,
            severity,
            log.user.get_full_name() if log.user else 'Anonymous',
            log.user.username if log.user else '',
            log.action,
            log.details[:500] if log.details else '',
            log.ip_address or '',
            log.user_agent or ''
        ])
    
    return response

@login_required
@staff_member_required
def clear_old_system_logs(request):
    """Clear system logs older than specified days"""
    if request.method == 'POST':
        days = int(request.POST.get('days', 30))
        
        cutoff_date = timezone.now() - timedelta(days=days)
        
        # Delete old logs
        deleted_count, _ = UserActivityLog.objects.filter(
            timestamp__lt=cutoff_date
        ).delete()
        
        # Log this action
        UserActivityLog.objects.create(
            user=request.user,
            action=f'Cleared system logs older than {days} days',
            details=json.dumps({
                'deleted_count': deleted_count,
                'cutoff_date': cutoff_date.isoformat(),
                'cleared_by': request.user.username
            }),
            ip_address=request.META.get('REMOTE_ADDR', ''),
            user_agent=request.META.get('HTTP_USER_AGENT', '')
        )
        
        messages.success(request, f'Cleared {deleted_count} system logs older than {days} days.')
        return redirect('system_logs')
    
    return render(request, 'dashboard/clear_system_logs.html')


# ==============================
# Debugging Views
# ==============================


@login_required
@staff_member_required
def debug_economics_data(request):
    """Debug view to check economics data"""
    # Get all economics records
    all_records = EconomicsReport.objects.all().order_by('-transaction_date')
    
    # Get latest 10 records
    latest_records = all_records[:10]
    
    # Print debug info
    print(f"Total economics records: {all_records.count()}")
    print(f"Latest records:")
    for record in latest_records:
        print(f"  ID: {record.id}, Amount: {record.amount}, Type: {record.transaction_type}, User: {record.user.username if record.user else 'None'}, Paid: {record.is_paid}")
    
    # Check if new manual entries are being created
    recent_manual_entries = all_records.filter(
        transaction_type='entry_fee',
        transaction_date__gte=timezone.now() - timedelta(hours=1)
    )
    
    print(f"Manual entries in last hour: {recent_manual_entries.count()}")
    
    context = {
        'total_records': all_records.count(),
        'latest_records': latest_records,
        'recent_manual_entries': recent_manual_entries,
    }
    
    return render(request, 'dashboard/debug_economics.html', context)

# Add this debug view to see EconomicsReport model fields
@login_required
@staff_member_required
def check_economics_model(request):
    """Check EconomicsReport model fields"""
    from django.db import connection
    from django.apps import apps
    
    model = apps.get_model('app', 'EconomicsReport')
    fields = [f.name for f in model._meta.get_fields()]
    
    # Also check database columns
    with connection.cursor() as cursor:
        cursor.execute("PRAGMA table_info(app_economicsreport)")
        columns = cursor.fetchall()
    
    context = {
        'fields': fields,
        'columns': columns,
    }
    
    return render(request, 'dashboard/check_model.html', context)

