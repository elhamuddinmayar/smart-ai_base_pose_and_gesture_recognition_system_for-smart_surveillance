from django import forms
from django.contrib.auth.models import User
from .models import TargetPerson, SecurityProfile
import re

""" 
1:UserRegistrationForm: A form for registering new security personnel. It extends ModelForm based on Django's built-in User model, but also includes additional fields for the SecurityProfile (badge number, role, profile picture, emergency contact). It has custom validation to ensure unique badge numbers and valid phone formats.
2:LoginForm: A simple form for user authentication, allowing login via either username or email.
3:TargetPersonForm: A ModelForm for creating and updating TargetPerson records. It includes custom widgets for better UX and validation for fields like age and phone number.
4:UserUpdateForm: Similar to UserRegistrationForm but intended for updating existing user profiles. It allows changing the user's name, email, badge number, role, emergency contact, and profile picture, with appropriate validation.
5: The forms use Bootstrap classes for styling and include HTML5 validation attributes to enhance the user experience. Custom clean methods ensure that data integrity is maintained according to the application's requirements.

"""

class UserRegistrationForm(forms.ModelForm):
    password = forms.CharField(
        label='Password',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'minlength': '8',
            'autocomplete': 'new-password',
        })
    )
    password2 = forms.CharField(
        label='Repeat password',
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'minlength': '8',
            'autocomplete': 'new-password',
        })
    )
    
    badge_number = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'e.g. SEC-001',
            'maxlength': '20',
            'pattern': r'[A-Za-z0-9\-]{2,20}',
            'title': 'Letters, numbers and hyphens only (2–20 characters)',
        })
    )
    profile_picture = forms.ImageField(
        required=False,
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': 'image/*',
        })
    )
    role = forms.ChoiceField(
        choices=[
            ('operator',   'Surveillance Operator'),
            ('supervisor', 'Shift Supervisor'),
            ('admin',      'System Administrator'),
        ],
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    emergency_contact = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'type': 'tel',
            'placeholder': '+93 7XX XXX XXXX  or  07XXXXXXXX',
            'pattern': r'[\+0-9\s\-]{7,20}',
            'title': 'Afghanistan phone: +937XXXXXXXX, 00937XXXXXXXX or 07XXXXXXXX',
            'maxlength': '25',
        })
    )
    # The Meta class defines which model this form is based on and which fields to include. It also specifies custom widgets for better styling and user experience
    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email']
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'form-control',
                'maxlength': '150',
                'pattern': r'[\w.@+\-]+',
                'title': 'Letters, digits and @/./+/-/_ only',
            }),
            'first_name': forms.TextInput(attrs={
                'class': 'form-control',
                'maxlength': '150',
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'form-control',
                'maxlength': '150',
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'maxlength': '254',
                'autocomplete': 'email',
            }),
        }

    def clean_badge_number(self):
        badge = self.cleaned_data.get('badge_number')
        if SecurityProfile.objects.filter(badge_number=badge).exists():
            raise forms.ValidationError('This badge number is already assigned to another officer.')
        return badge

    def clean_emergency_contact(self):
        phone = self.cleaned_data.get('emergency_contact')
        clean_phone = re.sub(r'[\s\-]', '', phone)
        pattern = r'^(\+93|0093|0)7[0-9]{8}$'
        if not re.match(pattern, clean_phone):
            raise forms.ValidationError(
                "Invalid Afghanistan phone number. Use: +937XXXXXXXX, 00937XXXXXXXX, or 07XXXXXXXX"
            )
        return clean_phone

    def clean_password2(self):
        cd = self.cleaned_data
        if 'password' in cd and 'password2' in cd:
            if cd['password'] != cd['password2']:
                raise forms.ValidationError("Passwords don't match.")
        return cd['password2']

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError('Email already in use.')
        return email


class LoginForm(forms.Form):
    identifier = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Username or Email',
            'maxlength': '254',
            'autocomplete': 'username',
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Password',
            'autocomplete': 'current-password',
        })
    )


class TargetPersonForm(forms.ModelForm):
    class Meta:
        model = TargetPerson
        fields = [
            'name', 'last_name', 'father_name', 'image',
            'age', 'gender', 'place_of_birth', 'marital_status', 'job',
            'tazkira_number', 'phone_number', 'address',
            'crime', 'description'
        ]

        widgets = {
            # ── Text fields ──────────────────────────────────────────────────
            'name': forms.TextInput(attrs={
                'placeholder': 'First Name',
                'maxlength': '100',
            }),
            'last_name': forms.TextInput(attrs={
                'placeholder': 'Surname',
                'maxlength': '100',
            }),
            'father_name': forms.TextInput(attrs={
                'placeholder': "Father's Name",
                'maxlength': '100',
            }),
            'place_of_birth': forms.TextInput(attrs={
                'placeholder': 'City / Province',
                'maxlength': '255',
            }),
            'job': forms.TextInput(attrs={
                'placeholder': 'Occupation',
                'maxlength': '100',
            }),

            # ── Numeric fields ───────────────────────────────────────────────
            # age: IntegerField → type="number" with sensible bounds
            'age': forms.NumberInput(attrs={
                'placeholder': '0',
                'min': '0',
                'max': '120',
                'step': '1',
            }),

            # ── ID / reference fields ────────────────────────────────────────
            'tazkira_number': forms.TextInput(attrs={
                'placeholder': 'National ID Number',
                'maxlength': '50',
                'pattern': r'[0-9A-Za-z\-]{3,50}',
                'title': 'Numbers, letters and hyphens (3–50 characters)',
            }),

            # ── Phone ────────────────────────────────────────────────────────
            # type="tel" lets mobile browsers show the numeric dial-pad
            'phone_number': forms.TextInput(attrs={
                'type': 'tel',
                'placeholder': '+93 7XX XXX XXXX  or  07XXXXXXXX',
                'maxlength': '25',
                'pattern': r'[\+0-9\s\-]{7,25}',
                'title': 'Phone number (digits, +, spaces and hyphens allowed)',
            }),

            # ── Textarea fields ──────────────────────────────────────────────
            'address': forms.Textarea(attrs={
                'rows': 2,
                'placeholder': 'Current Residence',
                'maxlength': '1000',
            }),
            'description': forms.Textarea(attrs={
                'rows': 3,
                'placeholder': 'Detailed case notes…',
                'maxlength': '5000',
            }),
            'crime': forms.TextInput(attrs={
                'placeholder': 'Charge / Offence',
                'maxlength': '255',
            }),
        }
    # The __init__ method is overridden to add a common CSS class to all fields for consistent styling. Custom clean methods are defined for age and phone number to ensure data validity according to the application's requirements.
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.update({'class': 'cyber-input'})

    def clean_age(self):
        age = self.cleaned_data.get('age')
        if age is not None and (age < 0 or age > 120):
            raise forms.ValidationError('Age must be between 0 and 120.')
        return age

    def clean_phone_number(self):
        phone = self.cleaned_data.get('phone_number', '')
        # Strip formatting so we can validate the raw digits
        cleaned = re.sub(r'[\s\-]', '', phone)
        if cleaned and not re.match(r'^[\+0-9]{7,20}$', cleaned):
            raise forms.ValidationError('Enter a valid phone number (digits, +, spaces, hyphens).')
        return phone


class UserUpdateForm(forms.ModelForm):
    badge_number = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'maxlength': '20',
            'pattern': r'[A-Za-z0-9\-]{2,20}',
            'title': 'Letters, numbers and hyphens (2–20 characters)',
        })
    )
    role = forms.ChoiceField(
        choices=SecurityProfile.ROLE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    emergency_contact = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'type': 'tel',
            'placeholder': '+93 7XX XXX XXXX  or  07XXXXXXXX',
            'pattern': r'[\+0-9\s\-]{7,20}',
            'title': 'Afghanistan phone: +937XXXXXXXX, 00937XXXXXXXX or 07XXXXXXXX',
            'maxlength': '25',
        })
    )
    profile_picture = forms.ImageField(
        required=False,
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': 'image/*',
        })
    )

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email']
        widgets = {
            'first_name': forms.TextInput(attrs={
                'class': 'form-control',
                'maxlength': '150',
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'form-control',
                'maxlength': '150',
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'maxlength': '254',
            }),
        }

    def clean_emergency_contact(self):
        phone = self.cleaned_data.get('emergency_contact', '')
        clean_phone = re.sub(r'[\s\-]', '', phone)
        pattern = r'^(\+93|0093|0)7[0-9]{8}$'
        if clean_phone and not re.match(pattern, clean_phone):
            raise forms.ValidationError(
                "Invalid Afghanistan phone number. Use: +937XXXXXXXX, 00937XXXXXXXX, or 07XXXXXXXX"
            )
        return phone