from django import forms
from django.utils import timezone
from datetime import timedelta
from .models import Booking, ParkingSlot
import datetime
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.forms import UserChangeForm
from django.contrib.auth import get_user_model
User = get_user_model()



class SignUpForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput)
    confirm_password = forms.CharField(widget=forms.PasswordInput)

    class Meta:
        model = User
        fields = ['username', 'email', 'password']

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")

        if password1 and len(password1) < 8:
            raise forms.ValidationError("Password must be at least 8 characters long.")

        if password1 and password2 and password1 != password2:
            raise forms.ValidationError("Passwords do not match.")

        return cleaned_data




class BookingForm(forms.ModelForm):
    class Meta:
        model = Booking
        fields = ['vehicle_number', 'start_time', 'end_time', 'guest_email', 'guest_phone']
        widgets = {
            'start_time': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
            'end_time': forms.DateTimeInput(attrs={'type': 'datetime-local'}),
        }
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        if not self.user or not self.user.is_authenticated:
            self.fields['guest_email'].required = True
            self.fields['guest_phone'].required = True
    
    def clean(self):
        cleaned_data = super().clean()
        start_time = cleaned_data.get('start_time')
        end_time = cleaned_data.get('end_time')
        
        if start_time and end_time:
            if start_time < timezone.now():
                raise forms.ValidationError("Start time cannot be in the past")
            if end_time <= start_time:
                raise forms.ValidationError("End time must be after start time")
            if (end_time - start_time) > datetime.timedelta(hours=24):
                raise forms.ValidationError("Maximum booking duration is 24 hours")
        
        return cleaned_data





class AdminManualEntryForm(forms.Form):
    ACTION_CHOICES = [
        ('entered', 'Vehicle Entry'),
        ('exited', 'Vehicle Exit'),
    ]
    
    vehicle_number = forms.CharField(
        max_length=20,
        required=True,
        label="Vehicle Number",
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    action = forms.ChoiceField(
        choices=ACTION_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    booking_id = forms.IntegerField(
        required=False,
        label="Booking ID (if pre-booked)",
        widget=forms.NumberInput(attrs={'class': 'form-control'})
    )

class ManualEntryForm(forms.Form):
    vehicle_number = forms.CharField(
        max_length=20,
        required=True,
        label="Vehicle Number",
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

class AdminManualEntryForm(forms.Form):
    vehicle_number = forms.CharField(max_length=20)
    action = forms.ChoiceField(choices=[('entered', 'Entered'), ('exited', 'Exited')])
    booking_id = forms.IntegerField(required=False)


class UserProfileForm(UserChangeForm):
    password = None  # Remove the password field
    
    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name')


from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django import forms

class StaffCreationForm(UserCreationForm):
    email = forms.EmailField(required=True, widget=forms.EmailInput(attrs={
        'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500',
        'placeholder': 'staff@example.com'
    }))
    first_name = forms.CharField(required=False, widget=forms.TextInput(attrs={
        'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500',
        'placeholder': 'First Name'
    }))
    last_name = forms.CharField(required=False, widget=forms.TextInput(attrs={
        'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500',
        'placeholder': 'Last Name'
    }))
    is_superuser = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs={
        'class': 'h-4 w-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500'
    }))
    
    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 'is_superuser', 'password1', 'password2')
        
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500',
                'placeholder': 'Username'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['password1'].widget.attrs.update({
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500',
            'placeholder': 'Password'
        })
        self.fields['password2'].widget.attrs.update({
            'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500',
            'placeholder': 'Confirm Password'
        })
    
    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']
        user.is_staff = True  # Always set is_staff to True for staff members
        user.is_superuser = self.cleaned_data.get('is_superuser', False)
        
        if commit:
            user.save()
        return user

class StaffEditForm(forms.ModelForm):
    email = forms.EmailField(required=True, widget=forms.EmailInput(attrs={
        'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500',
        'placeholder': 'staff@example.com'
    }))
    first_name = forms.CharField(required=False, widget=forms.TextInput(attrs={
        'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500',
        'placeholder': 'First Name'
    }))
    last_name = forms.CharField(required=False, widget=forms.TextInput(attrs={
        'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500',
        'placeholder': 'Last Name'
    }))
    is_superuser = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs={
        'class': 'h-4 w-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500'
    }))
    is_active = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs={
        'class': 'h-4 w-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500'
    }))
    
    class Meta:
        model = User
        fields = ('username', 'email', 'first_name', 'last_name', 'is_superuser', 'is_active')
        
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500',
                'placeholder': 'Username'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Ensure staff flag is always True for staff members
        self.instance.is_staff = True