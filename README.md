# Toy_BikeParking_Computer_Vision
Note:
Due to size limits, trained YOLO models are not included.
Run `train.py` to generate `best_model.pt`.

🚲 BikeSecure – AI-Powered Bike Parking System
BikeSecure is a smart bike parking management system built with Django that helps manage bike entry, exit, booking, and parking availability efficiently.
The system supports role-based access, manual and AI-assisted tracking, and real-time parking status.
✨ Features
🔐 User Roles
Admin
Manage staff accounts
View parking logs and system activity
Monitor total occupancy and availability
Staff
Manual bike entry and exit
View currently parked vehicles
🏍️ Parking Management
No fixed slot selection – bikes park in any available slot
Real-time list of currently parked bikes
Entry & exit tracking with timestamps
Guest and authenticated user parking
📅 Booking System
Slot reservation support
Pre-booking limit rule
Only 30% of total slots can be pre-booked
If 60% of slots are occupied or reserved, pre-booking is disabled
Booking confirmation and validation
📊 Dashboard
Admin & staff dashboards
Live parking status
Logs and activity tracking
Clean sidebar + topbar UI
🛠️ Tech Stack
Backend: Django (Python)
Database: PostgreSQL
Frontend: HTML, CSS, Bootstrap
Authentication: Django Auth (Role-based)
Architecture: MVC / MVT
AI (Optional/Future):
License plate or bike detection
Automated entry/exit recognition