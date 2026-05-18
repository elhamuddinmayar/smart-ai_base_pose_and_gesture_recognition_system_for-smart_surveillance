import os
import io
from datetime import timedelta
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User, Group
from django.core.exceptions import PermissionDenied
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.conf import settings
from django.db import models
from django.http import JsonResponse, HttpResponse
from django.shortcuts import redirect, render, get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext as _
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import ( SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage, HRFlowable)
from reportlab.lib.enums import TA_CENTER
from .forms import UserRegistrationForm, LoginForm, TargetPersonForm, UserUpdateForm
from .models import (TargetPerson, SecurityProfile, DetectionEvent,TargetAssignment, Notification)



""" 
1:import os : This imports the os module, which provides a way of using operating system dependent functionality. In this code, it is used for handling file paths and operations related to file storage.
2:import io : This imports the io module, which provides the Python interfaces to stream handling. In this code, it is used for creating in-memory byte streams, particularly for generating PDF files without saving them to disk.
3:from datetime import timedelta : This imports the timedelta class from the datetime module. timedelta is used to represent a duration, the difference between two dates or times. In this code, it is used for calculating expiration times for targets and other time-based operations.
4:from django.contrib import messages : This imports the messages framework from Django, which allows you to store messages in one request and retrieve them for display in a subsequent request. In this code, it is used to provide feedback to users after actions such as form submissions or target assignments.
5:from django.contrib.admin.views.decorators import staff_member_required : This imports the staff_member_required decorator, which is used to restrict access to views to users who are marked as staff members in the Django admin. In this code, it is used to protect certain views that should only be accessible by staff.
6:from django.contrib.auth import authenticate, login, logout : This imports the authenticate, login, and logout functions from Django's authentication framework. These functions are used to handle user authentication and session management in the application.
7:from django.contrib.auth.decorators import login_required, user_passes_test : This imports the login_required and user_passes_test decorators. login_required is used to ensure that a view can only be accessed by authenticated users, while user_passes_test allows you to specify a custom test function to determine if a user has access to a view.
8:from django.contrib.auth.models import User, Group : This imports the User and Group models from Django's authentication system. The User model represents users in the application, while the Group model allows for grouping users and assigning permissions.
9:from django.core.exceptions import PermissionDenied : This imports the PermissionDenied exception, which can be raised when a user does not have permission to access a particular view or perform a certain action.
10:from django.core.mail import send_mail : This imports the send_mail function, which is used to send email messages. In this code, it is used to send notifications to users when certain events occur, such as target assignments or detection verifications.
11:from django.core.paginator import Paginator : This imports the Paginator class, which is used to paginate querysets. In this code, it is used to paginate lists of targets, detection events, and notifications for better user experience.
12:from django.conf import settings : This imports the settings object, which contains the configuration for the Django project. It is used in this code to access settings such as email configuration and file storage paths.
13:from django.db import models : This imports the models module, which is used to define database models in Django. In this code, it is used to interact with the database models defined in the application.
14:from django.http import JsonResponse, HttpResponse, Http404 : This imports the JsonResponse, HttpResponse, and Http404 classes. JsonResponse is used to return JSON responses from views, HttpResponse is used to return standard HTTP responses, and Http404 is raised when a requested resource is not found.
15:from django.shortcuts import redirect, render, get_object_or_404 : This imports the redirect, render, and get_object_or_404 functions. redirect is used to redirect users to a different URL, render is used to render templates with context data, and get_object_or_404 is used to retrieve an object from the database or raise a 404 error if it does not exist.
16:from django.utils import timezone : This imports the timezone module, which provides utilities for working with time zones. In this code, it is used to handle date and time operations in a timezone-aware manner.
17:from django.utils.translation import gettext as _ : This imports the gettext function for internationalization. It allows you to mark strings for translation in the application, making it easier to support multiple languages.
18:from asgiref.sync import async_to_sync : This imports the async_to_sync function, which is used to call asynchronous functions from synchronous code. In this code, it is used to send notifications through Django Channels.
19:from channels.layers import get_channel_layer : This imports the get_channel_layer function, which is used to get the channel layer for sending messages in Django Channels. In this code, it is used to send real-time notifications to users.
20:from reportlab.lib import colors : This imports the colors module from ReportLab, which provides a set of predefined colors that can be used in PDF generation.
21:from reportlab.lib.pagesizes import A4 : This imports the A4 page size definition from ReportLab, which is used to set the page size for generated PDF documents.
22:from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle : This imports functions for working with styles in ReportLab. getSampleStyleSheet provides a set of predefined styles, while ParagraphStyle allows you to define custom styles for paragraphs in the PDF.
23:from reportlab.lib.units import cm : This imports the cm unit from ReportLab, which is used to specify measurements in centimeters when generating PDFs.
24:from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage, HRFlowable) : This imports various classes from ReportLab's platypus module, which are used to build PDF documents. SimpleDocTemplate is used to create a PDF document template, Paragraph is used for text content, Spacer is used to add space between elements, Table and TableStyle are used to create and style tables, Image is used to include images in the PDF, and HRFlowable is used to add horizontal rules.
25:from reportlab.lib.enums import TA_CENTER : This imports the TA_CENTER constant, which is used to specify center alignment for text in ReportLab.
26:from .forms import UserRegistrationForm, LoginForm, TargetPersonForm, UserUpdateForm : This imports form classes defined in the forms.py file of the application. These forms are used for user registration, login, target person management, and user profile updates.
27:from .models import (TargetPerson, SecurityProfile, DetectionEvent, TargetAssignment, Notification) : This imports the database models defined in the models.py file of the application. These models represent the core entities in the application, such as target persons, detection events, assignments, and notifications.
"""


#   Role helpers 
# These functions check the role of the user to control access to certain views and features. They are used in conjunction with decorators like @user_passes_test to restrict access based on user roles (admin, supervisor, operator). The functions check if the user is authenticated and then verify their role either through the is_superuser flag or a custom profile attribute.
def is_admin(user):
    if not user.is_authenticated:
        return False
    return user.is_superuser or (
        hasattr(user, 'profile') and user.profile.role == 'admin'
    )

# A more general check for privileged staff (admin or supervisor)
def is_privileged_staff(user):
    return user.is_authenticated and (
        user.is_superuser or (
            hasattr(user, 'profile') and user.profile.role in ['admin', 'supervisor']
        )
    )

# Check if user is an operator
def is_operator(user):
    return user.is_authenticated and (
        hasattr(user, 'profile') and user.profile.role == 'operator'
    )


# ── Notification push ─────────────────────────────────────────────────────────
# This helper function creates a notification in the database, sends a real-time update via Django Channels, and optionally sends an email to the recipient. It is used throughout the views to notify users of important events such as target assignments and detection verifications.
def _push_notification(recipient, notification_type, title, message, assignment=None, event=None):
    #we are creating object in database
    notif = Notification.objects.create(
        recipient=recipient,
        notification_type=notification_type,
        title=title,
        message=message,
        related_assignment=assignment,
        related_event=event,
    )
    #for live update to push notifiaction we have to work in channel
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        f"user_{recipient.id}",
        {
            "type":              "send_notification",
            "notification_id":   notif.id,
            "notification_type": notification_type,
            "title":             title,
            "message":           message,
            "created_at":        notif.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        }
    )
    #if someone was out of system the operator can send email to him
    if recipient.email:
        try:
            send_mail(
                subject=f"[Butterfly] {title}",
                message=message,
                from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@butterfly.local'),
                recipient_list=[recipient.email],
                fail_silently=True,
            )
        except Exception as e:
            print(f"[Notification] Email error: {e}")

    return notif


# ── Core pages ────────────────────────────────────────────────────────────────


# The dashboard view aggregates various pieces of data to provide an overview of the system's status. It shows recent detection events, counts of different types of detections, pending verifications, recent assignments, and notifications. The data is scoped based on the user's role, ensuring that supervisors and operators only see relevant information.
@login_required
def dashboard(request):
    from django.utils import timezone
    # from django.db models import Count, Q: This imports the Count and Q classes from Django's database models module. Count is used for aggregating counts of records in querysets, while Q is used for building complex queries with OR and AND conditions. In this code, they are used to calculate counts of detection events and to filter querysets based on certain conditions.
    from django.db.models import Count, Q
    
    now  = timezone.now()
    user = request.user
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # ── Targets (non-expired) ─────────────────────────────────────────────
    targets = TargetPerson.objects.filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))

    # ── Detection events scoped by role ──────────────────────────────────
    events_qs = DetectionEvent.objects.select_related('matched_target', 'camera').order_by('-timestamp')

    if is_admin(user):
        scoped_events = events_qs
    elif hasattr(user, 'profile') and user.profile.role == 'supervisor':
        scoped_events = events_qs.filter(
            matched_target__isnull=False,
            matched_target__uploaded_by=user
        )
    elif hasattr(user, 'profile') and user.profile.role == 'operator':
        scoped_events = events_qs.filter(related_assignment__assigned_to=user)
    else:
        scoped_events = events_qs.none()

    recent_events = scoped_events[:20]

    # ── Detection breakdown counts ────────────────────────────────────────
    total_events       = scoped_events.count()
    normal_count       = scoped_events.filter(action='Normal').count()
    fall_count         = scoped_events.filter(action='FALL DETECTED').count()
    wave_count         = scoped_events.filter(action='HAND WAVING').count()
    target_match_count = scoped_events.filter(matched_target__isnull=False).count()

    # ── Verification status counts ────────────────────────────────────────
    approved_count   = scoped_events.filter(verification_status='approved').count()
    pending_count    = scoped_events.filter(verification_status='pending').count()
    rejected_count   = scoped_events.filter(verification_status='rejected').count()
    unreviewed_count = scoped_events.filter(verification_status='unreviewed').count()
    total_verif      = max(1, total_events)

    def pct(n): return round((n / total_verif) * 100)

    # ── Today's events count ─────────────────────────────────────────────
    today_detections = scoped_events.filter(timestamp__gte=today_start).count()

    # ── Pending verifications (for the queue panel) ───────────────────────
    pv_qs = DetectionEvent.objects.filter(verification_status='pending').select_related('matched_target', 'camera')
    if not is_admin(user):
        pv_qs = pv_qs.filter(matched_target__uploaded_by=user)
    pending_events    = pv_qs.order_by('-timestamp')[:6]
    pending_verif_count = pv_qs.count()

    # ── Recent assignments ────────────────────────────────────────────────
    from .models import TargetAssignment
    if is_admin(user):
        recent_assignments = TargetAssignment.objects.select_related('target', 'assigned_to', 'assigned_by').order_by('-created_at')[:5]
    elif hasattr(user, 'profile') and user.profile.role == 'supervisor':
        recent_assignments = TargetAssignment.objects.filter(assigned_by=user).select_related('target', 'assigned_to').order_by('-created_at')[:5]
    else:
        recent_assignments = TargetAssignment.objects.filter(assigned_to=user).select_related('target', 'assigned_by').order_by('-created_at')[:5]

    # ── Recent notifications ──────────────────────────────────────────────
    recent_notifications = Notification.objects.filter(recipient=user).order_by('-created_at')[:6]
    unread_count = Notification.objects.filter(recipient=user, is_read=False).count()
    
    # ── Sparkline data (last 20 hours of event counts) ────────────────────
    from django.utils.timezone import timedelta
    spark_data = []
    for h in range(19, -1, -1):
        h_start = now - timedelta(hours=h+1)
        h_end   = now - timedelta(hours=h)
        c = scoped_events.filter(timestamp__gte=h_start, timestamp__lt=h_end).count()
        spark_data.append(c)

    return render(request, 'surveillance/dashboard.html', {
        # Core
        'targets':            targets,
        'is_admin':           is_admin(user),
        'recent_events':      recent_events,

        # Breakdown counts
        'normal_count':       normal_count,
        'fall_count':         fall_count,
        'wave_count':         wave_count,
        'target_match_count': target_match_count,

        # Verification breakdown
        'approved_count':   approved_count,
        'pending_count':    pending_count,
        'rejected_count':   rejected_count,
        'unreviewed_count': unreviewed_count,
        'approved_pct':   pct(approved_count),
        'pending_pct':    pct(pending_count),
        'rejected_pct':   pct(rejected_count),
        'unreviewed_pct': pct(unreviewed_count),

        # Panels
        'pending_events':       pending_events,
        'pending_verif_count':  pending_verif_count,
        'recent_assignments':   recent_assignments,
        'recent_notifications': recent_notifications,
        'today_detections':     today_detections,
        'unread_count':         unread_count,

        # Sparkline (comma-separated for JS template literal)
        'spark_data': ','.join(map(str, spark_data)),
    })
    
    
@login_required
def home(request):
    unread_count = Notification.objects.filter(
        recipient=request.user, is_read=False
    ).count()
    return render(request, 'surveillance/home.html', {
        'is_admin':    is_admin(request.user),
        'unread_count': unread_count,
    })


# ── Target management — scoped by role ───────────────────────────────────────

@login_required
@user_passes_test(is_privileged_staff, login_url='home')
def target_management(request):
    user    = request.user
    base_qs = TargetPerson.objects.all().order_by('-id')
    targets = base_qs if is_admin(user) else base_qs.filter(uploaded_by=user)

    return render(request, 'surveillance/target_management.html', {
        'targets':  targets,
        'is_admin': is_admin(user),
    })


@login_required
def target_registration(request):
    if request.method == 'POST':
        form = TargetPersonForm(request.POST, request.FILES)
        if form.is_valid():
            target = form.save(commit=False)
            target.uploaded_by = request.user  # <-- critical
            target.save()
            return redirect('target_management')
    else:
        form = TargetPersonForm()
    return render(request, 'surveillance/target_registration.html', {'form': form})

@login_required
def target_detail(request, pk):
    target = get_object_or_404(TargetPerson, pk=pk)

    # Block access if not admin AND not the supervisor who uploaded it
    if not is_admin(request.user) and not is_privileged_staff(request.user):
        return redirect('target_management')

    if is_privileged_staff(request.user) and not is_admin(request.user):
        # Supervisor can only see their own uploaded targets
        if target.uploaded_by != request.user:
            return redirect('target_management')

    assignments = TargetAssignment.objects.filter(target=target).select_related(
        'assigned_to', 'assigned_by'
    ).order_by('-created_at')

    operators = User.objects.filter(
        profile__role='operator'
    ).select_related('profile')

    return render(request, 'surveillance/target_management_details.html', {
        'target':      target,
        'assignments': assignments,
        'operators':   operators,
        'is_admin':    is_admin(request.user),
    })



@login_required
@user_passes_test(is_privileged_staff, login_url='home')
def upload_target(request):
    if request.method == 'POST':
        form = TargetPersonForm(request.POST, request.FILES)
        if form.is_valid():
            target             = form.save(commit=False)
            target.uploaded_by = request.user

            duration = request.POST.get('duration')
            now      = timezone.now()
            durations = {
                "1h":  timedelta(hours=1),
                "12h": timedelta(hours=12),
                "1d":  timedelta(days=1),
                "7d":  timedelta(days=7),
            }
            if duration in durations:
                target.expires_at = now + durations[duration]
            elif duration == "custom":
                custom_date = request.POST.get('custom_date')
                if custom_date:
                    try:
                        target.expires_at = timezone.make_aware(
                            timezone.datetime.fromisoformat(custom_date)
                        )
                    except ValueError:
                        pass

            target.save()
            messages.success(request, f"Subject '{target.name}' successfully enrolled.")
            return redirect('target_management')
        else:
            for field, errors in form.errors.items():
                messages.error(request, f"{field}: {errors[0]}")
            return render(request, 'surveillance/target_management_registration.html', {
                'form': form, 'is_admin': True,
            })
    return redirect('target_registration')


# ── Assignment workflow ───────────────────────────────────────────────────────

@login_required
@user_passes_test(is_privileged_staff, login_url='home')
def assign_target(request, target_pk):
    if request.method != 'POST':
        return redirect('target_management')

    target      = get_object_or_404(TargetPerson, pk=target_pk)
    operator_id = request.POST.get('operator_id')
    note        = request.POST.get('note', '')
    operator    = get_object_or_404(User, pk=operator_id)

    if not is_admin(request.user) and target.uploaded_by != request.user:
        messages.error(request, "You can only assign targets you uploaded.")
        return redirect('target_management')

    assignment = TargetAssignment.objects.create(
        target=target,
        assigned_by=request.user,
        assigned_to=operator,
        note=note,
        status='pending',
    )

    _push_notification(
        recipient=operator,
        notification_type='assignment',
        title=f"New target assigned: {target.name}",
        message=(
            f"You have been assigned to monitor '{target.name} {target.last_name}'.\n"
            f"Assigned by: {request.user.get_full_name() or request.user.username}\n"
            f"Note: {note or 'None'}"
        ),
        assignment=assignment,
    )

    messages.success(request, f"Target '{target.name}' assigned to {operator.username}.")
    return redirect('target_management')


@login_required
def pass_back_target(request, assignment_pk):
    assignment = get_object_or_404(
        TargetAssignment, pk=assignment_pk, assigned_to=request.user
    )
    assignment.status = 'passed_back'
    assignment.save()

    uploader = assignment.target.uploaded_by
    if uploader:
        _push_notification(
            recipient=uploader,
            notification_type='pass_back',
            title=f"Update on target: {assignment.target.name}",
            message=(
                f"Operator {request.user.username} has passed back the target "
                f"'{assignment.target.name} {assignment.target.last_name}'.\n"
                f"Assignment ID: #{assignment.pk}"
            ),
            assignment=assignment,
        )

    messages.success(request, "Target passed back to the original uploader.")
    return redirect('operator_assignments')


@login_required
def operator_assignments(request):
    """
    Operators see their own assignments.
    Admins/supervisors can also view this for reference.
    """
    assignments = TargetAssignment.objects.filter(
        assigned_to=request.user
    ).select_related('target', 'assigned_by').order_by('-created_at')

    return render(request, 'surveillance/operator_assignments.html', {
        'assignments': assignments,
        'is_admin':    is_admin(request.user),
    })


@login_required
def acknowledge_assignment(request, assignment_pk):
    assignment = get_object_or_404(
        TargetAssignment, pk=assignment_pk, assigned_to=request.user
    )
    assignment.status = 'acknowledged'
    assignment.save()
    return JsonResponse({'status': 'ok'})


# ── Verification workflow ─────────────────────────────────────────────────────

@login_required
@user_passes_test(is_privileged_staff, login_url='home')
def pending_verifications(request):
    """
    Admin/supervisor sees all detection events that need verification.
    Supervisor sees only those linked to targets they uploaded.
    """
    user = request.user
    qs   = DetectionEvent.objects.filter(
        verification_status='pending'
    ).select_related('matched_target', 'camera', 'related_assignment__assigned_to')

    if not is_admin(user):
        qs = qs.filter(matched_target__uploaded_by=user)

    return render(request, 'surveillance/pending_verifications.html', {
        'events':   qs.order_by('-timestamp'),
        'is_admin': is_admin(user),
    })


@login_required
@user_passes_test(is_privileged_staff, login_url='home')
def verify_detection(request, event_pk):
    """
    POST: admin/supervisor approves or rejects a detection event.
    Payload: { action: 'approve'|'reject', note: str }
    Then notifies the operator who reported it.
    """
    if request.method != 'POST':
        return redirect('pending_verifications')

    event  = get_object_or_404(DetectionEvent, pk=event_pk)
    action = request.POST.get('action')
    note   = request.POST.get('note', '')

    if action not in ('approve', 'reject'):
        messages.error(request, "Invalid action.")
        return redirect('pending_verifications')

    # Guard: supervisor can only verify targets they uploaded
    if not is_admin(request.user):
        if event.matched_target and event.matched_target.uploaded_by != request.user:
            messages.error(request, "You can only verify detections of targets you uploaded.")
            return redirect('pending_verifications')

    event.verification_status = 'approved' if action == 'approve' else 'rejected'
    event.verified_by         = request.user
    event.verified_at         = timezone.now()
    event.verification_note   = note
    event.save(update_fields=[
        'verification_status', 'verified_by', 'verified_at', 'verification_note'
    ])

    # Notify the operator who submitted this detection
    assignment = event.related_assignment
    if assignment and assignment.assigned_to:
        operator = assignment.assigned_to
        if action == 'approve':
            notif_type = 'approved'
            title      = f"Detection approved: {event.matched_target_name}"
            msg        = (
                f"Your detection of '{event.matched_target_name}' has been APPROVED by "
                f"{request.user.get_full_name() or request.user.username}.\n"
                f"Note: {note or 'None'}\n"
                f"You may now export the PDF report."
            )
        else:
            notif_type = 'rejected'
            title      = f"Detection rejected: {event.matched_target_name}"
            msg        = (
                f"Your detection of '{event.matched_target_name}' was REJECTED by "
                f"{request.user.get_full_name() or request.user.username}.\n"
                f"Note: {note or 'None'}"
            )

        _push_notification(
            recipient=operator,
            notification_type=notif_type,
            title=title,
            message=msg,
            assignment=assignment,
            event=event,
        )

    label = "approved" if action == 'approve' else "rejected"
    messages.success(request, f"Detection event #{event_pk} {label}.")
    return redirect('pending_verifications')


# ── PDF export ────────────────────────────────────────────────────────────────

def _build_detection_pdf(event: DetectionEvent) -> bytes:
    """
    Build a professional A4 PDF for an approved detection event using ReportLab.
    Contains: target info table, detection metadata, snapshot image.
    """
    buffer = io.BytesIO()
    doc    = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2*cm, leftMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
    )
    styles   = getSampleStyleSheet()
    elements = []

    # ── Title block ──────────────────────────────────────────────────────────
    title_style = ParagraphStyle(
        'CustomTitle', parent=styles['Title'],
        fontSize=20, textColor=colors.HexColor('#1a1a2e'),
        spaceAfter=4,
    )
    sub_style = ParagraphStyle(
        'SubTitle', parent=styles['Normal'],
        fontSize=10, textColor=colors.grey,
        alignment=TA_CENTER, spaceAfter=16,
    )
    elements.append(Paragraph("BUTTERFLY SURVEILLANCE SYSTEM", title_style))
    elements.append(Paragraph("OFFICIAL DETECTION REPORT", sub_style))
    elements.append(HRFlowable(width="100%", thickness=2,
                                color=colors.HexColor('#1a1a2e'), spaceAfter=16))

    # ── Status banner ────────────────────────────────────────────────────────
    status_color = colors.HexColor('#1e7e34') if event.verification_status == 'approved' \
                   else colors.HexColor('#c0392b')
    status_label = event.get_verification_status_display().upper()
    banner_data  = [[Paragraph(
        f'<font color="white"><b>STATUS: {status_label}</b></font>',
        ParagraphStyle('Banner', parent=styles['Normal'],
                       fontSize=12, alignment=TA_CENTER)
    )]]
    banner_table = Table(banner_data, colWidths=[17*cm])
    banner_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), status_color),
        ('ROWBACKGROUNDS', (0,0), (-1,-1), [status_color]),
        ('TOPPADDING', (0,0), (-1,-1), 8),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('ROUNDEDCORNERS', [4]),
    ]))
    elements.append(banner_table)
    elements.append(Spacer(1, 16))

    # ── Target information ───────────────────────────────────────────────────
    target = event.matched_target
    elements.append(Paragraph("SUBJECT INFORMATION",
                               ParagraphStyle('SectionHead', parent=styles['Heading2'],
                                              textColor=colors.HexColor('#1a1a2e'),
                                              fontSize=13, spaceAfter=8)))

    if target:
        info_data = [
            ["Full Name",       f"{target.name} {target.last_name}"],
            ["Father's Name",   target.father_name],
            ["Date of Birth",   f"Age: {target.age}"],
            ["Gender",          target.get_gender_display()],
            ["Place of Birth",  target.place_of_birth],
            ["Marital Status",  target.marital_status],
            ["Occupation",      target.job],
            ["Tazkira No.",     target.tazkira_number or "N/A"],
            ["Phone",           target.phone_number],
            ["Address",         target.address],
            ["Crime/Charge",    target.crime],
            ["Description",     target.description or "N/A"],
        ]
    else:
        info_data = [["Name", event.matched_target_name]]

    label_style = ParagraphStyle('Label', parent=styles['Normal'],
                                  fontSize=9, textColor=colors.grey)
    value_style = ParagraphStyle('Value', parent=styles['Normal'],
                                  fontSize=10, textColor=colors.black)

    table_data = [[
        Paragraph(row[0], label_style),
        Paragraph(str(row[1]), value_style)
    ] for row in info_data]

    info_table = Table(table_data, colWidths=[5*cm, 12*cm])
    info_table.setStyle(TableStyle([
        ('BACKGROUND',   (0, 0), (0, -1), colors.HexColor('#f0f0f0')),
        ('GRID',         (0, 0), (-1,-1), 0.5, colors.HexColor('#cccccc')),
        ('TOPPADDING',   (0, 0), (-1,-1), 5),
        ('BOTTOMPADDING',(0, 0), (-1,-1), 5),
        ('LEFTPADDING',  (0, 0), (-1,-1), 8),
        ('RIGHTPADDING', (0, 0), (-1,-1), 8),
        ('VALIGN',       (0, 0), (-1,-1), 'TOP'),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 16))

    # ── Detection metadata ───────────────────────────────────────────────────
    elements.append(Paragraph("DETECTION DETAILS",
                               ParagraphStyle('SectionHead', parent=styles['Heading2'],
                                              textColor=colors.HexColor('#1a1a2e'),
                                              fontSize=13, spaceAfter=8)))

    camera_name = event.camera.name if event.camera else "Unknown"
    location    = event.camera.location if event.camera else "Unknown"
    verifier    = event.verified_by.get_full_name() or event.verified_by.username \
                  if event.verified_by else "N/A"
    verified_at = event.verified_at.strftime("%Y-%m-%d %H:%M:%S") \
                  if event.verified_at else "N/A"
    operator    = "N/A"
    if event.related_assignment and event.related_assignment.assigned_to:
        op = event.related_assignment.assigned_to
        operator = op.get_full_name() or op.username

    det_data = [
        ["Detection Time", event.timestamp.strftime("%Y-%m-%d %H:%M:%S")],
        ["Camera",         camera_name],
        ["Location",       location],
        ["Action",         event.action],
        ["Person Count",   str(event.person_count)],
        ["Detected By",    f"Operator: {operator}"],
        ["Verified By",    verifier],
        ["Verified At",    verified_at],
        ["Verifier Note",  event.verification_note or "None"],
    ]
    det_table_data = [[
        Paragraph(row[0], label_style),
        Paragraph(str(row[1]), value_style)
    ] for row in det_data]

    det_table = Table(det_table_data, colWidths=[5*cm, 12*cm])
    det_table.setStyle(TableStyle([
        ('BACKGROUND',   (0, 0), (0, -1), colors.HexColor('#f0f0f0')),
        ('GRID',         (0, 0), (-1,-1), 0.5, colors.HexColor('#cccccc')),
        ('TOPPADDING',   (0, 0), (-1,-1), 5),
        ('BOTTOMPADDING',(0, 0), (-1,-1), 5),
        ('LEFTPADDING',  (0, 0), (-1,-1), 8),
        ('RIGHTPADDING', (0, 0), (-1,-1), 8),
        ('VALIGN',       (0, 0), (-1,-1), 'TOP'),
    ]))
    elements.append(det_table)
    elements.append(Spacer(1, 16))

    # ── Target reference photo ───────────────────────────────────────────────
    photos_added = False
    elements.append(Paragraph("EVIDENCE PHOTOS",
                               ParagraphStyle('SectionHead', parent=styles['Heading2'],
                                              textColor=colors.HexColor('#1a1a2e'),
                                              fontSize=13, spaceAfter=8)))

    photo_row = []

    # Reference photo (target registration image)
    if target and target.image:
        try:
            ref_path = target.image.path
            if os.path.isfile(ref_path):
                ref_img = RLImage(ref_path, width=7*cm, height=7*cm)
                ref_img.hAlign = 'CENTER'
                photo_row.append([Paragraph("Reference Photo", sub_style), ref_img])
                photos_added = True
        except Exception as e:
            print(f"[PDF] Reference photo error: {e}")

    # Capture snapshot from detection event
    if event.frame_snapshot:
        try:
            snap_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'media', str(event.frame_snapshot)
            )
            if os.path.isfile(snap_path):
                snap_img = RLImage(snap_path, width=7*cm, height=7*cm)
                snap_img.hAlign = 'CENTER'
                photo_row.append([Paragraph("Capture Snapshot", sub_style), snap_img])
                photos_added = True
        except Exception as e:
            print(f"[PDF] Snapshot error: {e}")

    if photo_row:
        # Build a two-column photo table
        col_data = [[item[0] for item in photo_row],
                    [item[1] for item in photo_row]]
        col_widths = [8.5*cm] * len(photo_row)
        photo_table = Table(
            [[photo_row[i][1] for i in range(len(photo_row))],
             [photo_row[i][0] for i in range(len(photo_row))]],
            colWidths=col_widths
        )
        photo_table.setStyle(TableStyle([
            ('ALIGN',   (0,0), (-1,-1), 'CENTER'),
            ('VALIGN',  (0,0), (-1,-1), 'MIDDLE'),
            ('TOPPADDING',   (0,0), (-1,-1), 4),
            ('BOTTOMPADDING',(0,0), (-1,-1), 4),
        ]))
        elements.append(photo_table)
    else:
        elements.append(Paragraph("No photos available.", styles['Normal']))

    elements.append(Spacer(1, 20))
    elements.append(HRFlowable(width="100%", thickness=1,
                                color=colors.HexColor('#cccccc'), spaceAfter=8))

    # ── Footer ───────────────────────────────────────────────────────────────
    footer_style = ParagraphStyle('Footer', parent=styles['Normal'],
                                   fontSize=8, textColor=colors.grey,
                                   alignment=TA_CENTER)
    generated_at = timezone.now().strftime("%Y-%m-%d %H:%M:%S")
    elements.append(Paragraph(
        f"Generated by Butterfly Surveillance System · {generated_at} · CONFIDENTIAL",
        footer_style
    ))

    doc.build(elements)
    return buffer.getvalue()


@login_required
def export_detection_pdf(request, event_pk):
    """
    Export a single detection event as PDF.
    Rules:
      - Operator: can only export events from their own assignments, only if approved
      - Supervisor: can export events of targets they uploaded, only if approved
      - Admin: can export any event
    """
    event = get_object_or_404(
        DetectionEvent.objects.select_related(
            'matched_target', 'camera', 'verified_by',
            'related_assignment__assigned_to', 'related_assignment__assigned_by'
        ),
        pk=event_pk
    )
    user = request.user

    # Permission check
    if is_admin(user):
        pass  # full access
    elif is_privileged_staff(user):
        if event.matched_target and event.matched_target.uploaded_by != user:
            raise PermissionDenied("You can only export detections of your targets.")
        if event.verification_status != 'approved':
            messages.error(request, "PDF export is only available for approved detections.")
            return redirect('pending_verifications')
    else:
        # Operator
        assignment = event.related_assignment
        if not assignment or assignment.assigned_to != user:
            raise PermissionDenied("You can only export detections from your own assignments.")
        if event.verification_status != 'approved':
            messages.error(request, "PDF export is only available after admin/supervisor approval.")
            return redirect('operator_assignments')

    pdf_bytes = _build_detection_pdf(event)
    target_name = event.matched_target_name or "unknown"
    filename = f"detection_{target_name.replace(' ', '_')}_{event.pk}.pdf"

    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@login_required
@user_passes_test(is_privileged_staff, login_url='home')
def export_target_pdf(request, target_pk):
    """
    Export full target dossier as PDF (admin/supervisor by target name/last_name).
    Includes all detection events for this target.
    """
    target = get_object_or_404(TargetPerson, pk=target_pk)
    user   = request.user

    if not is_admin(user) and target.uploaded_by != user:
        raise PermissionDenied("You can only export targets your uploaded.")

    buffer = io.BytesIO()
    doc    = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=2*cm, leftMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
    )
    styles   = getSampleStyleSheet()
    elements = []

    title_style = ParagraphStyle('T', parent=styles['Title'],
                                  fontSize=18, textColor=colors.HexColor('#1a1a2e'),
                                  spaceAfter=4)
    sub_style   = ParagraphStyle('S', parent=styles['Normal'],
                                  fontSize=10, textColor=colors.grey,
                                  alignment=TA_CENTER, spaceAfter=12)
    label_style = ParagraphStyle('L', parent=styles['Normal'],
                                  fontSize=9, textColor=colors.grey)
    value_style = ParagraphStyle('V', parent=styles['Normal'],
                                  fontSize=10, textColor=colors.black)

    elements.append(Paragraph("BUTTERFLY SURVEILLANCE SYSTEM", title_style))
    elements.append(Paragraph("TARGET PERSON DOSSIER", sub_style))
    elements.append(HRFlowable(width="100%", thickness=2,
                                color=colors.HexColor('#1a1a2e'), spaceAfter=12))

    # Target photo
    if target.image:
        try:
            img_path = target.image.path
            if os.path.isfile(img_path):
                t_img = RLImage(img_path, width=5*cm, height=5*cm)
                t_img.hAlign = 'RIGHT'
                elements.append(t_img)
        except Exception:
            pass

    # Target info
    info_rows = [
        ["Full Name",      f"{target.name} {target.last_name}"],
        ["Father's Name",  target.father_name],
        ["Age",            str(target.age)],
        ["Gender",         target.get_gender_display()],
        ["Place of Birth", target.place_of_birth],
        ["Marital Status", target.marital_status],
        ["Occupation",     target.job],
        ["Tazkira No.",    target.tazkira_number or "N/A"],
        ["Phone",          target.phone_number],
        ["Address",        target.address],
        ["Crime/Charge",   target.crime],
        ["Description",    target.description or "N/A"],
        ["Registered At",  target.created_at.strftime("%Y-%m-%d %H:%M:%S")],
        ["Status",         "FOUND" if target.is_found else "ACTIVE"],
    ]
    tbl = Table(
        [[Paragraph(r[0], label_style), Paragraph(str(r[1]), value_style)] for r in info_rows],
        colWidths=[5*cm, 12*cm]
    )
    tbl.setStyle(TableStyle([
        ('BACKGROUND',    (0,0), (0,-1), colors.HexColor('#f0f0f0')),
        ('GRID',          (0,0), (-1,-1), 0.5, colors.HexColor('#cccccc')),
        ('TOPPADDING',    (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
        ('LEFTPADDING',   (0,0), (-1,-1), 8),
        ('RIGHTPADDING',  (0,0), (-1,-1), 8),
        ('VALIGN',        (0,0), (-1,-1), 'TOP'),
    ]))
    elements.append(tbl)
    elements.append(Spacer(1, 16))

    # Detection events
    elements.append(Paragraph("DETECTION HISTORY",
                               ParagraphStyle('SH', parent=styles['Heading2'],
                                              textColor=colors.HexColor('#1a1a2e'),
                                              fontSize=13, spaceAfter=8)))

    events = DetectionEvent.objects.filter(
        matched_target=target
    ).select_related('camera').order_by('-timestamp')

    if events.exists():
        ev_header = [
            Paragraph("Timestamp", label_style),
            Paragraph("Camera", label_style),
            Paragraph("Action", label_style),
            Paragraph("Status", label_style),
        ]
        ev_rows = [ev_header] + [[
            Paragraph(e.timestamp.strftime("%Y-%m-%d %H:%M"), value_style),
            Paragraph(e.camera.name if e.camera else "N/A", value_style),
            Paragraph(e.action, value_style),
            Paragraph(e.get_verification_status_display(), value_style),
        ] for e in events]

        ev_table = Table(ev_rows, colWidths=[5*cm, 4.5*cm, 4*cm, 3.5*cm])
        ev_table.setStyle(TableStyle([
            ('BACKGROUND',    (0,0), (-1,0), colors.HexColor('#1a1a2e')),
            ('TEXTCOLOR',     (0,0), (-1,0), colors.white),
            ('GRID',          (0,0), (-1,-1), 0.5, colors.HexColor('#cccccc')),
            ('ROWBACKGROUNDS',(0,1), (-1,-1),
             [colors.white, colors.HexColor('#f8f8f8')]),
            ('TOPPADDING',    (0,0), (-1,-1), 5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
            ('LEFTPADDING',   (0,0), (-1,-1), 6),
        ]))
        elements.append(ev_table)
    else:
        elements.append(Paragraph("No detections recorded.", styles['Normal']))

    elements.append(Spacer(1, 20))
    elements.append(HRFlowable(width="100%", thickness=1,
                                color=colors.HexColor('#cccccc'), spaceAfter=8))
    elements.append(Paragraph(
        f"Generated by Butterfly Surveillance System · "
        f"{timezone.now().strftime('%Y-%m-%d %H:%M:%S')} · CONFIDENTIAL",
        ParagraphStyle('Footer', parent=styles['Normal'],
                        fontSize=8, textColor=colors.grey, alignment=TA_CENTER)
    ))

    doc.build(elements)

    filename = f"target_{target.name}_{target.last_name}_{target.pk}.pdf"
    response = HttpResponse(buffer.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


# ── Notifications ─────────────────────────────────────────────────────────────

@login_required
def notifications_list(request):
    notifs = Notification.objects.filter(
        recipient=request.user
    ).order_by('-created_at')[:50]
    Notification.objects.filter(
        recipient=request.user, is_read=False
    ).update(is_read=True)
    return render(request, 'surveillance/notifications.html', {
        'notifications': notifs,
        'is_admin':      is_admin(request.user),
    })


@login_required
def unread_notification_count(request):
    count = Notification.objects.filter(
        recipient=request.user, is_read=False
    ).count()
    return JsonResponse({'count': count})


# ── Detection history ─────────────────────────────────────────────────────────

@login_required
def detection_history(request):
    user = request.user

    qs = DetectionEvent.objects.select_related(
        'matched_target', 'camera'
    ).order_by('-timestamp')

    # ── Role scoping (unchanged) ──────────────────────────────────────────────
    if is_admin(user):
        pass
    elif hasattr(user, 'profile') and user.profile.role == 'operator':
        qs = qs.filter(related_assignment__assigned_to=user)
    elif hasattr(user, 'profile') and user.profile.role == 'supervisor':
        from django.db.models import Q
        qs = qs.filter(
            matched_target__isnull=False,
            matched_target__uploaded_by=user
        )
    else:
        qs = qs.none()

    # ── Filters from GET params ───────────────────────────────────────────────
    action_filter  = request.GET.get('action', '')
    target_filter  = request.GET.get('target', '')   # 'yes' | 'no' | ''
    verif_filter   = request.GET.get('verif', '')
    camera_filter  = request.GET.get('camera', '')
    date_from      = request.GET.get('date_from', '')
    date_to        = request.GET.get('date_to', '')
    sort_by        = request.GET.get('sort', '-timestamp')
    search_query   = request.GET.get('q', '')

    if action_filter:
        qs = qs.filter(action=action_filter)

    if target_filter == 'yes':
        qs = qs.filter(matched_target__isnull=False)
    elif target_filter == 'no':
        qs = qs.filter(matched_target__isnull=True)

    if verif_filter:
        qs = qs.filter(verification_status=verif_filter)

    if camera_filter:
        qs = qs.filter(camera_id=camera_filter)

    if date_from:
        try:
            from django.utils.dateparse import parse_date
            d = parse_date(date_from)
            if d:
                qs = qs.filter(timestamp__date__gte=d)
        except Exception:
            pass

    if date_to:
        try:
            from django.utils.dateparse import parse_date
            d = parse_date(date_to)
            if d:
                qs = qs.filter(timestamp__date__lte=d)
        except Exception:
            pass

    if search_query:
        from django.db.models import Q
        qs = qs.filter(
            Q(matched_target_name__icontains=search_query) |
            Q(camera__name__icontains=search_query) |
            Q(camera__location__icontains=search_query)
        )

    # ── Sorting ───────────────────────────────────────────────────────────────
    SORT_OPTIONS = {
        '-timestamp':         '-timestamp',
        'timestamp':          'timestamp',
        'action':             'action',
        '-action':            '-action',
        '-person_count':      '-person_count',
        'person_count':       'person_count',
        'verification_status':'verification_status',
    }
    qs = qs.order_by(SORT_OPTIONS.get(sort_by, '-timestamp'))

    # ── Camera list for filter dropdown ──────────────────────────────────────
    from camera.models import Camera
    all_cameras = Camera.objects.all().order_by('name')

    # ── Stats for the active filter set ──────────────────────────────────────
    total_count  = qs.count()
    fall_count   = qs.filter(action='FALL DETECTED').count()
    wave_count   = qs.filter(action='HAND WAVING').count()
    target_count = qs.filter(matched_target__isnull=False).count()

    paginator = Paginator(qs, 25)
    page      = paginator.get_page(request.GET.get('page'))

    # Preserve all GET params except 'page' for pagination links
    get_params = request.GET.copy()
    get_params.pop('page', None)

    return render(request, 'surveillance/detection_history.html', {
        'page_obj':      page,
        'is_admin':      is_admin(user),
        'all_cameras':   all_cameras,
        # active filter values (to re-populate form)
        'f_action':      action_filter,
        'f_target':      target_filter,
        'f_verif':       verif_filter,
        'f_camera':      camera_filter,
        'f_date_from':   date_from,
        'f_date_to':     date_to,
        'f_sort':        sort_by,
        'f_q':           search_query,
        # stats
        'total_count':   total_count,
        'fall_count':    fall_count,
        'wave_count':    wave_count,
        'target_count':  target_count,
        # for pagination links
        'get_params':    get_params.urlencode(),
    })
# ── User / account management

@login_required
@user_passes_test(is_admin, login_url='home')
def account_manage(request):
    query     = request.GET.get('q', '')
    sort_type = request.GET.get('sort', '-date_joined')

    users_list = User.objects.select_related('profile').filter(
        models.Q(username__icontains=query) | models.Q(email__icontains=query)
    )
    sort_map = {
        'name_asc':        'username',
        'name_desc':       '-username',
        'date_old':        'date_joined',
        'date_new':        '-date_joined',
        'rank_admin':      ['-is_staff', 'username'],
        'rank_obs':        ['is_staff', 'username'],
        'role_supervisor': ['-profile__role', 'username'],
        'role_operator':   ['profile__role', 'username'],
    }
    order = sort_map.get(sort_type, '-date_joined')
    if isinstance(order, list):
        users_list = users_list.order_by(*order)
    else:
        users_list = users_list.order_by(order)

    paginator  = Paginator(users_list, 6)
    users      = paginator.get_page(request.GET.get('page'))
    is_filtered = bool(query or sort_type not in ['-date_joined', 'date_new'])

    return render(request, 'surveillance/account_manage.html', {
        'users':        users,
        'query':        query,
        'current_sort': sort_type,
        'is_admin':     True,
        'is_filtered':  is_filtered,
    })


@login_required
@user_passes_test(is_admin, login_url='home')
def delete_user(request, user_id):
    if request.user.id == user_id:
        messages.error(request, "CRITICAL: You cannot terminate your own access.")
        return redirect('account_manage')
    user_to_delete = get_object_or_404(User, id=user_id)
    username       = user_to_delete.username
    user_to_delete.delete()
    messages.success(request, f"User '{username}' has been removed from the system.")
    return redirect('account_manage')


@login_required
@user_passes_test(is_admin, login_url='home')
def toggle_admin_role(request, user_id):
    user_to_mod = get_object_or_404(User, id=user_id)
    admin_group, _ = Group.objects.get_or_create(name='Admin')
    if user_to_mod.groups.filter(name='Admin').exists():
        user_to_mod.groups.remove(admin_group)
        user_to_mod.is_staff = False
        messages.info(request, f"Access Level: Observer - {user_to_mod.username}")
    else:
        user_to_mod.groups.add(admin_group)
        user_to_mod.is_staff = True
        messages.success(request, f"Access Level: Admin - {user_to_mod.username}")
    user_to_mod.save()
    return redirect('account_manage')


def register(request):
    if request.method == 'POST':
        user_form = UserRegistrationForm(request.POST, request.FILES)
        if user_form.is_valid():
            new_user = user_form.save(commit=False)
            new_user.set_password(user_form.cleaned_data['password'])
            new_user.save()
            SecurityProfile.objects.create(
                user=new_user,
                badge_number=user_form.cleaned_data['badge_number'],
                profile_picture=user_form.cleaned_data.get('profile_picture'),
                role=user_form.cleaned_data['role'],
                emergency_contact=user_form.cleaned_data['emergency_contact'],
            )
            messages.success(request, f'Security Profile for {new_user.username} Initialized!')
            return redirect("login")
    else:
        user_form = UserRegistrationForm()
    return render(request, 'registration/register.html', {'user_form': user_form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('home')
    if request.method == 'POST':
        form = LoginForm(request.POST)
        if form.is_valid():
            identifier = form.cleaned_data.get('identifier')
            password   = form.cleaned_data.get('password')
            user_obj   = User.objects.filter(email=identifier).first()
            username   = user_obj.username if user_obj else identifier
            user       = authenticate(request, username=username, password=password)
            if user is not None:
                login(request, user)
                messages.success(request, 'Access Granted.')
                return redirect('home')
            else:
                messages.error(request, 'Invalid Credentials.')
    else:
        form = LoginForm()
    return render(request, 'registration/login.html', {'form': form})


def log_out_view(request):
    logout(request)
    messages.info(request, "Session Terminated.")
    return redirect("login")


@login_required
def account_detail(request, user_id):
    target_user = get_object_or_404(User, id=user_id)
    if not request.user.is_superuser and request.user.id != target_user.id:
        raise PermissionDenied("You do not have permission to view this profile.")
    return render(request, 'surveillance/account_manage_details.html', {
        'target_user': target_user,
        'profile':     target_user.profile,
    })


@staff_member_required
def account_update(request, pk):
    target_user = get_object_or_404(User, id=pk)
    profile     = target_user.profile

    if request.method == 'POST':
        form = UserUpdateForm(request.POST, request.FILES, instance=target_user)
        if form.is_valid():
            form.save()
            profile.badge_number       = form.cleaned_data['badge_number']
            profile.role               = form.cleaned_data['role']
            profile.emergency_contact  = form.cleaned_data['emergency_contact']
            if form.cleaned_data.get('profile_picture'):
                profile.profile_picture = form.cleaned_data['profile_picture']
            profile.save()
            messages.success(request, _("Profile updated successfully."))
            return redirect('account_detail', user_id=target_user.id)
    else:
        initial_data = {
            'badge_number':      profile.badge_number,
            'role':              profile.role,
            'emergency_contact': profile.emergency_contact,
        }
        form = UserUpdateForm(instance=target_user, initial=initial_data)

    return render(request, 'surveillance/account_update.html', {
        'form':        form,
        'target_user': target_user,
        'profile':     profile,
    })