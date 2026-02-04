document.addEventListener('DOMContentLoaded', function() {
    // Mock users for demo
    const mockUsers = [
        { id: '1', name: 'Admin User', email: 'admin@smartpark.pk', password: 'admin123', role: 'admin' },
        { id: '2', name: 'Customer User', email: 'customer@example.com', password: 'customer123', role: 'customer' }
    ];
    
    // Login form functionality
    const loginForm = document.getElementById('loginForm');
    const loginButton = document.getElementById('loginButton');
    
    if (loginForm) {
        loginForm.addEventListener('submit', function(e) {
            e.preventDefault();
            
            // Get form values
            const email = document.getElementById('email').value;
            const password = document.getElementById('password').value;
            
            // Reset error messages
            document.getElementById('emailError').textContent = '';
            document.getElementById('passwordError').textContent = '';
            
            // Validate form
            let isValid = true;
            
            if (!email) {
                document.getElementById('emailError').textContent = 'Email is required';
                isValid = false;
            } else if (!/\S+@\S+\.\S+/.test(email)) {
                document.getElementById('emailError').textContent = 'Please enter a valid email address';
                isValid = false;
            }
            
            if (!password) {
                document.getElementById('passwordError').textContent = 'Password is required';
                isValid = false;
            } else if (password.length < 6) {
                document.getElementById('passwordError').textContent = 'Password must be at least 6 characters';
                isValid = false;
            }
            
            if (isValid) {
                // Show loading state
                loginButton.textContent = 'Logging in...';
                loginButton.disabled = true;
                
                // Simulate API call
                setTimeout(function() {
                    // Check credentials
                    const user = mockUsers.find(u => u.email === email && u.password === password);
                    
                    if (user) {
                        // Store user in localStorage
                        localStorage.setItem('user', JSON.stringify({
                            id: user.id,
                            name: user.name,
                            email: user.email,
                            role: user.role
                        }));
                        
                        // Show success toast
                        showToast('Login Successful', 'Welcome back to SmartPark!');
                        
                        // Redirect to dashboard
                        setTimeout(function() {
                            window.location.href = 'dashboard.html';
                        }, 1000);
                    } else {
                        // Show error
                        showToast('Login Failed', 'Invalid email or password. Please try again.', 'error');
                        
                        // Reset button
                        loginButton.textContent = 'Login';
                        loginButton.disabled = false;
                    }
                }, 1500);
            }
        });
    }
    
    // Register form functionality (if present)
    const registerForm = document.getElementById('registerForm');
    const registerButton = document.getElementById('registerButton');
    
    if (registerForm) {
        registerForm.addEventListener('submit', function(e) {
            e.preventDefault();
            
            // Get form values
            const name = document.getElementById('name').value;
            const email = document.getElementById('email').value;
            const password = document.getElementById('password').value;
            const confirmPassword = document.getElementById('confirmPassword').value;
            
            // Reset error messages
            document.getElementById('nameError').textContent = '';
            document.getElementById('emailError').textContent = '';
            document.getElementById('passwordError').textContent = '';
            document.getElementById('confirmPasswordError').textContent = '';
            
            // Validate form
            let isValid = true;
            
            if (!name) {
                document.getElementById('nameError').textContent = 'Name is required';
                isValid = false;
            } else if (name.length < 2) {
                document.getElementById('nameError').textContent = 'Name must be at least 2 characters';
                isValid = false;
            }
            
            if (!email) {
                document.getElementById('emailError').textContent = 'Email is required';
                isValid = false;
            } else if (!/\S+@\S+\.\S+/.test(email)) {
                document.getElementById('emailError').textContent = 'Please enter a valid email address';
                isValid = false;
            }
            
            if (!password) {
                document.getElementById('passwordError').textContent = 'Password is required';
                isValid = false;
            } else if (password.length < 6) {
                document.getElementById('passwordError').textContent = 'Password must be at least 6 characters';
                isValid = false;
            }
            
            if (!confirmPassword) {
                document.getElementById('confirmPasswordError').textContent = 'Please confirm your password';
                isValid = false;
            } else if (password !== confirmPassword) {
                document.getElementById('confirmPasswordError').textContent = 'Passwords do not match';
                isValid = false;
            }
            
            if (isValid) {
                // Show loading state
                registerButton.textContent = 'Creating account...';
                registerButton.disabled = true;
                
                // Simulate API call
                setTimeout(function() {
                    // Create new user
                    const newUser = {
                        id: Math.random().toString(36).substring(2, 9),
                        name: name,
                        email: email,
                        role: 'customer'
                    };
                    
                    // Store user in localStorage
                    localStorage.setItem('user', JSON.stringify(newUser));
                    
                    // Show success toast
                    showToast('Registration Successful', 'Your account has been created. Welcome to SmartPark!');
                    
                    // Redirect to dashboard
                    setTimeout(function() {
                        window.location.href = 'dashboard.html';
                    }, 1000);
                }, 1500);
            }
        });
    }
    
    // Toast notification
    function showToast(title, message, type = 'success') {
        const toast = document.getElementById('toast');
        const toastTitle = document.querySelector('.toast-title');
        const toastMessage = document.querySelector('.toast-message');
        
        toastTitle.textContent = title;
        toastMessage.textContent = message;
        
        if (type === 'error') {
            toast.style.borderLeft = '4px solid var(--danger)';
        } else {
            toast.style.borderLeft = '4px solid var(--primary)';
        }
        
        toast.style.display = 'block';
        
        // Auto hide after 5 seconds
        setTimeout(function() {
            toast.style.display = 'none';
        }, 5000);
    }
});