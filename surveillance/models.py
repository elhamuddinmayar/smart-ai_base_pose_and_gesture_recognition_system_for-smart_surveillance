from django.db import models
from django.utils import timezone
import os
from django.contrib.auth.models import User

# SecurityProfile model to extend the default User model with additional fields specific to security personnel, including role, badge number, and emergency contact information for better management of user profiles within the surveillance system
class SecurityProfile(models.Model):
    ROLE_CHOICES = [
        ('operator',   'Surveillance Operator'),
        ('supervisor', 'Shift Supervisor'),
        ('admin',      'System Administrator'),
    ]
    user              = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    profile_picture   = models.ImageField(upload_to='profiles/security/', default='profiles/default.png')
    badge_number      = models.CharField(max_length=20, unique=True)
    role              = models.CharField(max_length=20, choices=ROLE_CHOICES, default='operator')
    emergency_contact = models.CharField(max_length=100)
    is_on_duty        = models.BooleanField(default=False)

    #__str__ method for better representation in admin and other interfaces
    def __str__(self):
        return f"{self.badge_number} - {self.user.username}"

# TargetPerson model to store information about individuals of interest with fields for personal details, crime information, and a reference to the user who uploaded the target for better tracking and management within the system
class TargetPerson(models.Model):
    GENDER_CHOICES  = [('M', 'Male'),
                       ('F', 'Female'),
                       ('O', 'Other')]
    
    MARITAL_CHOICES = [
        ('Single', 'Single'),
        ('Married', 'Married'),
        ('Divorced', 'Divorced'),
        ('Widowed', 'Widowed'),
    ]
    
    name           = models.CharField(max_length=100)
    last_name      = models.CharField(max_length=100, default='N/A')
    father_name    = models.CharField(max_length=100, default='N/A')
    image          = models.ImageField(upload_to='targets/')
    age            = models.IntegerField(default=0)
    gender         = models.CharField(max_length=1, choices=GENDER_CHOICES, default='M')
    place_of_birth = models.CharField(max_length=255, default='N/A')
    marital_status = models.CharField(max_length=20, choices=MARITAL_CHOICES, default='Single')
    job            = models.CharField(max_length=100, default='N/A')
    tazkira_number = models.CharField(max_length=50, unique=True, null=True, blank=True)
    phone_number   = models.CharField(max_length=20, default='0000000000')
    address        = models.TextField(default='N/A')
    crime          = models.CharField(max_length=255, default='None')
    description    = models.TextField(blank=True, default='')
    created_at     = models.DateTimeField(auto_now_add=True)
    is_found       = models.BooleanField(default=False)
    expires_at     = models.DateTimeField(null=True, blank=True)
    uploaded_by    = models.ForeignKey(
        User, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='uploaded_targets'
    )

    def __str__(self):
        return f"{self.name} {self.last_name} ({self.tazkira_number})"
    
    # Override delete method to remove image file from storage when a TargetPerson is deleted
    def delete(self, *args, **kwargs):
        if self.image:
            try:
                if os.path.isfile(self.image.path):
                    os.remove(self.image.path)
            except Exception:
                pass
        super().delete(*args, **kwargs)

# DetectionEvent model to log each detection with details and verification workflow fields for supervisors to review and verify detections 
class DetectionEvent(models.Model):
    ACTION_CHOICES = [
        ('Normal',        'Normal'),
        ('FALL DETECTED', 'Fall Detected'),
        ('HAND WAVING',   'Hand Waving'),
    ]

    # Verification workflow statuses
    VERIFY_CHOICES = [
        ('unreviewed',  'Unreviewed'),
        ('pending',     'Pending Review'),
        ('approved',    'Approved'),
        ('rejected',    'Rejected'),
    ]

    timestamp           = models.DateTimeField(default=timezone.now, db_index=True)
    person_count        = models.PositiveIntegerField(default=0)
    action              = models.CharField(max_length=50, choices=ACTION_CHOICES, default='Normal')
    matched_target      = models.ForeignKey(TargetPerson, on_delete=models.SET_NULL,null=True, blank=True, related_name='detection_events')
    matched_target_name = models.CharField(max_length=200, blank=True, default='')
    frame_snapshot      = models.ImageField(upload_to='snapshots/', null=True, blank=True)
    camera              = models.ForeignKey('camera.Camera', on_delete=models.SET_NULL,null=True, blank=True, related_name='detection_events')
    verification_status = models.CharField(max_length=20, choices=VERIFY_CHOICES, default='unreviewed', db_index=True)
    verified_by         = models.ForeignKey(User, on_delete=models.SET_NULL,null=True, blank=True, related_name='verified_events')
    verified_at         = models.DateTimeField(null=True, blank=True)
    verification_note   = models.TextField(blank=True, default='')
    # Which assignment triggered this (so we know who to notify)
    related_assignment  = models.ForeignKey('TargetAssignment', on_delete=models.SET_NULL,null=True, blank=True, related_name='detection_events')

    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        cam = f" | {self.camera.name}" if self.camera else ''
        return f"[{self.timestamp:%Y-%m-%d %H:%M:%S}] {self.person_count} person(s) | {self.action}{cam}"

# TargetAssignment model to manage assignments of targets to security personnel with status tracking and notes for communication between supervisors and operators
class TargetAssignment(models.Model):
    STATUS_CHOICES = [
        ('pending',      'Pending'),
        ('acknowledged', 'Acknowledged'),
        ('passed_back',  'Passed Back'),
        ('closed',       'Closed'),
    ]
    target      = models.ForeignKey(TargetPerson, on_delete=models.CASCADE, related_name='assignments')
    assigned_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='assignments_given')
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='assignments_received')
    status      = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    note        = models.TextField(blank=True, default='')
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.target.name} → {self.assigned_to} [{self.status}]"

# Notification model to manage notifications for security personnel with different types and related entities for better communication and alerting within the system
class Notification(models.Model):
    TYPE_CHOICES = [

        ('assignment',   'New Assignment'),
        ('pass_back',    'Passed Back to You'),
        ('detection',    'Target Detected'),
        ('verification', 'Verification Required'),
        ('approved',     'Detection Approved'),
        ('rejected',     'Detection Rejected'),
        ('system',       'System Alert'),
        ('assignment', 'New Assignment'),
        ('pass_back',  'Passed Back to You'),
        ('detection',  'Target Detected'),
        ('system',     'System Alert'),

    ]
    
    recipient            = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    notification_type    = models.CharField(max_length=20, choices=TYPE_CHOICES, default='system')
    title                = models.CharField(max_length=200)
    message              = models.TextField()
    is_read              = models.BooleanField(default=False)
    related_assignment   = models.ForeignKey(TargetAssignment, on_delete=models.SET_NULL,null=True, blank=True, related_name='notifications')
    related_event        = models.ForeignKey(DetectionEvent, on_delete=models.SET_NULL,null=True, blank=True, related_name='notifications')
    created_at           = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"→ {self.recipient.username}: {self.title}"