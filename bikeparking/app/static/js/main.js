document.addEventListener('DOMContentLoaded', function() {
    // Mobile menu toggle
    const menuToggle = document.querySelector('.menu-toggle');
    const nav = document.querySelector('.nav');
    
    if (menuToggle) {
        menuToggle.addEventListener('click', function() {
            nav.classList.toggle('active');
        });
    }
    
    // Reservation modal functionality
    const reserveButtons = document.querySelectorAll('.reserve-btn');
    const reservationModal = document.getElementById('reservationModal');
    const closeModal = document.querySelector('.close-modal');
    const reservationForm = document.getElementById('reservationForm');
    const reserveButton = document.getElementById('reserveButton');
    
    // Set reservation times
    const reservationTimeEl = document.getElementById('reservationTime');
    const expiryTimeEl = document.getElementById('expiryTime');
    
    function updateReservationTimes() {
        const now = new Date();
        const reservationTime = new Date(now.getTime() + 30 * 60000); // 30 minutes from now
        const expiryTime = new Date(reservationTime.getTime() + 30 * 60000); // 30 minutes after reservation
        
        reservationTimeEl.textContent = formatTime(reservationTime);
        expiryTimeEl.textContent = formatTime(expiryTime);
    }
    
    function formatTime(date) {
        let hours = date.getHours();
        const minutes = date.getMinutes();
        const ampm = hours >= 12 ? 'PM' : 'AM';
        
        hours = hours % 12;
        hours = hours ? hours : 12; // the hour '0' should be '12'
        
        const formattedMinutes = minutes < 10 ? '0' + minutes : minutes;
        
        return hours + ':' + formattedMinutes + ' ' + ampm;
    }
    
    // Open modal
    if (reserveButtons.length > 0) {
        reserveButtons.forEach(button => {
            button.addEventListener('click', function(e) {
                e.preventDefault();
                reservationModal.style.display = 'block';
                document.body.style.overflow = 'hidden'; // Prevent scrolling
                updateReservationTimes();
            });
        });
    }
    
    // Close modal
    if (closeModal) {
        closeModal.addEventListener('click', function() {
            reservationModal.style.display = 'none';
            document.body.style.overflow = 'auto'; // Enable scrolling
        });
    }
    
    // Close modal when clicking outside
    window.addEventListener('click', function(e) {
        if (e.target === reservationModal) {
            reservationModal.style.display = 'none';
            document.body.style.overflow = 'auto'; // Enable scrolling
        }
    });
    
    // Form validation
    if (reservationForm) {
        reservationForm.addEventListener('submit', function(e) {
            e.preventDefault();
            
            // Get form values
            const vehicleType = document.getElementById('vehicleType').value;
            const licensePlate = document.getElementById('licensePlate').value;
            const cnic = document.getElementById('cnic').value;
            
            // Reset error messages
            document.getElementById('vehicleTypeError').textContent = '';
            document.getElementById('licensePlateError').textContent = '';
            document.getElementById('cnicError').textContent = '';
            
            // Validate form
            let isValid = true;
            
            if (!vehicleType) {
                document.getElementById('vehicleTypeError').textContent = 'Please select a vehicle type';
                isValid = false;
            }
            
            if (!licensePlate) {
                document.getElementById('licensePlateError').textContent = 'License plate is required';
                isValid = false;
            } else if (licensePlate.length > 10) {
                document.getElementById('licensePlateError').textContent = 'License plate cannot exceed 10 characters';
                isValid = false;
            }
            
            if (!cnic) {
                document.getElementById('cnicError').textContent = 'CNIC is required';
                isValid = false;
            } else if (cnic.length < 13) {
                document.getElementById('cnicError').textContent = 'CNIC must be at least 13 digits';
                isValid = false;
            } else if (cnic.length > 15) {
                document.getElementById('cnicError').textContent = 'CNIC cannot exceed 15 characters';
                isValid = false;
            } else if (!/^[0-9-]+$/.test(cnic)) {
                document.getElementById('cnicError').textContent = 'CNIC can only contain numbers and hyphens';
                isValid = false;
            }
            
            if (isValid) {
                // Show loading state
                reserveButton.textContent = 'Processing...';
                reserveButton.disabled = true;
                
                // Simulate API call
                setTimeout(function() {
                    // Hide modal
                    reservationModal.style.display = 'none';
                    document.body.style.overflow = 'auto'; // Enable scrolling
                    
                    // Reset form
                    reservationForm.reset();
                    reserveButton.textContent = 'Reserve Slot Now';
                    reserveButton.disabled = false;
                    
                    // Show success toast
                    showToast('Reservation Successful!', `Your slot has been reserved at Emporium Mall, Lahore for ${reservationTimeEl.textContent}. Please arrive before ${expiryTimeEl.textContent}.`);
                }, 1500);
            }
        });
    }
    
    // Toast notification
    const toast = document.getElementById('toast');
    const toastTitle = document.querySelector('.toast-title');
    const toastMessage = document.querySelector('.toast-message');
    const toastClose = document.querySelector('.toast-close');
    
    function showToast(title, message) {
        toastTitle.textContent = title;
        toastMessage.textContent = message;
        toast.style.display = 'block';
        
        // Auto hide after 5 seconds
        setTimeout(function() {
            toast.style.display = 'none';
        }, 5000);
    }
    
    if (toastClose) {
        toastClose.addEventListener('click', function() {
            toast.style.display = 'none';
        });
    }
});