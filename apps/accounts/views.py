from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.db import transaction

from apps.accounts.models import User, StudentProfile, ParentProfile, DriverProfile
from apps.accounts.services import (
    find_parent_by_phone, issue_temporary_password, split_person_name, username_from_identifier,
)
from apps.fleet.models import Bus, StudentBusAssignment, DriverBusAssignment
from apps.routes.models import Route, BusStop, StudentLocationChangeRequest
from apps.notifications.models import Notification
from apps.notifications.services import send_notification

def home_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard-redirect')
    return redirect('login-view')

def login_register_view(request):
    """Sign-in only. Student and parent accounts are created by an administrator."""
    if request.user.is_authenticated:
        return redirect('dashboard-redirect')

    login_error = None

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            return redirect('dashboard-redirect')
        login_error = 'Invalid username or password. Please verify your credentials.'

    return render(request, 'auth/login.html', {
        'login_error': login_error,
    })

def logout_view(request):
    logout(request)
    return redirect('login-view')

@login_required
def dashboard_redirect_view(request):
    role = request.user.role
    if role == 'ADMIN' or request.user.is_superuser:
        return redirect('admin-bus-allotment')
    elif role == 'STUDENT':
        return redirect('student-location-request')
    elif role == 'DRIVER':
        return redirect('driver-manifest')
    elif role == 'PARENT':
        return redirect('parent-transport')
    return redirect('login-view')

# --- STUDENT VIEWS ---

@login_required
def student_location_request_view(request):
    if not hasattr(request.user, 'student_profile'):
        return redirect('dashboard-redirect')
    student = request.user.student_profile
    assignment = StudentBusAssignment.objects.select_related(
        'bus', 'route', 'active_pickup_stop', 'active_drop_stop',
        'permanent_pickup_stop', 'permanent_drop_stop'
    ).filter(student=student, status='ACTIVE').first()

    my_requests = StudentLocationChangeRequest.objects.filter(student=student).order_by('-created_at')
    available_stops = BusStop.objects.filter(route=assignment.route).order_by('stop_sequence') if assignment else []

    driver = assignment.bus.get_active_driver() if assignment else None
    context = {
        'student': student,
        'assignment': assignment,
        'driver': driver,
        'available_stops': available_stops,
        'my_requests': my_requests,
        'notifications': Notification.objects.filter(recipient=request.user).order_by('-created_at')[:5]
    }
    return render(request, 'student/location_change_request.html', context)

# --- ADMINISTRATOR VIEWS ---

@login_required
def admin_bus_allotment_view(request):
    """
    Administrator interface to view all registered students and allot/re-allot buses, routes, and stops.
    """
    if not request.user.is_admin_role():
        return redirect('dashboard-redirect')

    students = StudentProfile.objects.select_related(
        'user', 'preferred_route', 'preferred_pickup_stop', 'preferred_drop_stop'
    ).all().order_by('student_id')
    buses = Bus.objects.filter(status='ACTIVE')
    routes = Route.objects.filter(is_active=True).prefetch_related('stops')

    # Student roster with allotment information
    students_data = []
    for s in students:
        assignment = StudentBusAssignment.objects.select_related(
            'bus', 'route', 'active_pickup_stop', 'active_drop_stop'
        ).filter(student=s, status='ACTIVE').first()
        students_data.append({
            'profile': s,
            'assignment': assignment,
            'is_allotted': assignment is not None
        })

    filter_status = request.GET.get('filter', 'ALL')
    if filter_status == 'PENDING':
        students_data = [item for item in students_data if not item['is_allotted']]
    elif filter_status == 'ALLOTTED':
        students_data = [item for item in students_data if item['is_allotted']]

    counts = {
        'total': students.count(),
        'allotted': StudentBusAssignment.objects.filter(status='ACTIVE').count(),
        'pending': students.count() - StudentBusAssignment.objects.filter(status='ACTIVE').count(),
        'buses_count': buses.count(),
        'routes_count': routes.count(),
    }

    context = {
        'students_data': students_data,
        'buses': buses,
        'routes': routes,
        'counts': counts,
        'current_filter': filter_status
    }
    return render(request, 'admin/student_bus_allotment.html', context)

@login_required
@require_POST
def admin_allot_bus_action(request, student_id):
    """
    API endpoint for administrator to allot bus, route, and stops to a student.
    """
    if not request.user.is_admin_role():
        return JsonResponse({'detail': 'Administrator privileges required.'}, status=403)

    student = get_object_or_404(StudentProfile, id=student_id)
    bus_id = request.POST.get('bus_id')
    route_id = request.POST.get('route_id')
    pickup_stop_id = request.POST.get('pickup_stop_id')
    drop_stop_id = request.POST.get('drop_stop_id')

    if not (bus_id and route_id and pickup_stop_id and drop_stop_id):
        return JsonResponse({'detail': 'Please select Bus, Route, Pickup Stop, and Drop Stop.'}, status=400)

    bus = get_object_or_404(Bus, id=bus_id)
    route = get_object_or_404(Route, id=route_id)
    pickup_stop = get_object_or_404(BusStop, id=pickup_stop_id, route=route)
    drop_stop = get_object_or_404(BusStop, id=drop_stop_id, route=route)

    if pickup_stop.stop_sequence >= drop_stop.stop_sequence:
        return JsonResponse({'detail': 'Pickup stop sequence must come before drop stop sequence.'}, status=400)

    existing_assignment = StudentBusAssignment.objects.filter(student=student).first()
    moving_to_another_bus = not existing_assignment or existing_assignment.bus_id != bus.id or existing_assignment.status != 'ACTIVE'
    if moving_to_another_bus and bus.available_seats() <= 0:
        return JsonResponse({
            'detail': f'Bus {bus.bus_number} has reached maximum seating capacity ({bus.seating_capacity} seats). Available seats: 0.'
        }, status=400)

    if existing_assignment:
        assignment = existing_assignment
        assignment.bus = bus
        assignment.route = route
        assignment.permanent_pickup_stop = pickup_stop
        assignment.permanent_drop_stop = drop_stop
        assignment.active_pickup_stop = pickup_stop
        assignment.active_drop_stop = drop_stop
        assignment.is_temporary_active = False
        assignment.status = 'ACTIVE'
        assignment.save()
        action_verb = "updated"
    else:
        assignment = StudentBusAssignment.objects.create(
            student=student,
            bus=bus,
            route=route,
            permanent_pickup_stop=pickup_stop,
            permanent_drop_stop=drop_stop,
            active_pickup_stop=pickup_stop,
            active_drop_stop=drop_stop,
            is_temporary_active=False,
            status='ACTIVE'
        )
        action_verb = "allotted"

    # Send Notification to Student
    send_notification(
        recipient=student.user,
        title="Bus Allotment Confirmed",
        message=(
            f"Dear {student.user.first_name},\n\n"
            f"Your transportation has been {action_verb} by the college administrator:\n"
            f"• Assigned Bus: {bus.bus_number} ({bus.model_name})\n"
            f"• Route: {route.route_name} ({route.route_code})\n"
            f"• Scheduled Pickup: {pickup_stop.stop_name} at {pickup_stop.scheduled_pickup_time.strftime('%H:%M')} hrs\n"
            f"• Scheduled Drop: {drop_stop.stop_name} at {drop_stop.scheduled_drop_time.strftime('%H:%M')} hrs\n\n"
            f"You can now track your bus and view your route on your student dashboard."
        ),
        notification_type='ROUTE_CHANGE',
        priority='HIGH'
    )

    for parent in student.parents.select_related('user'):
        send_notification(
            recipient=parent.user,
            title=f"Bus assignment for {student.user.get_full_name()}",
            message=(
                f"The college administrator confirmed transportation for {student.user.get_full_name()} "
                f"({student.student_id}).\n"
                f"• Bus: {bus.bus_number}\n"
                f"• Route: {route.route_name} ({route.route_code})\n"
                f"• Pickup: {pickup_stop.stop_name} at {pickup_stop.scheduled_pickup_time.strftime('%H:%M')} hrs\n"
                f"• Drop: {drop_stop.stop_name} at {drop_stop.scheduled_drop_time.strftime('%H:%M')} hrs"
            ),
            notification_type='ROUTE_CHANGE',
            priority='HIGH'
        )

    return JsonResponse({
        'status': 'SUCCESS',
        'message': f'Bus {bus.bus_number} successfully {action_verb} to student {student.student_id} ({student.user.get_full_name()}).'
    })

@login_required
def admin_location_requests_view(request):
    if not request.user.is_admin_role():
        return redirect('dashboard-redirect')
    
    requests_qs = StudentLocationChangeRequest.objects.select_related(
        'student__user', 'assigned_bus', 'assigned_route',
        'current_pickup_stop', 'current_drop_stop',
        'requested_pickup_stop', 'requested_drop_stop',
        'reviewed_by'
    ).order_by('-created_at')

    status_filter = request.GET.get('status', 'ALL')
    if status_filter != 'ALL':
        filtered_requests = requests_qs.filter(status=status_filter)
    else:
        filtered_requests = requests_qs

    counts = {
        'total': requests_qs.count(),
        'pending': requests_qs.filter(status='PENDING').count(),
        'approved': requests_qs.filter(status='APPROVED').count(),
        'rejected': requests_qs.filter(status='REJECTED').count(),
    }

    context = {
        'requests': filtered_requests,
        'counts': counts,
        'current_filter': status_filter
    }
    return render(request, 'admin/location_requests_management.html', context)

# --- DRIVER VIEWS ---

@login_required
def driver_manifest_view(request):
    if not hasattr(request.user, 'driver_profile'):
        return redirect('dashboard-redirect')
    driver = request.user.driver_profile
    active_assignment = DriverBusAssignment.objects.select_related('bus').filter(driver=driver, is_active=True).first()
    
    bus = active_assignment.bus if active_assignment else None
    passengers = []
    route = None
    if bus:
        passengers = StudentBusAssignment.objects.select_related(
            'student__user', 'route', 'active_pickup_stop', 'active_drop_stop'
        ).filter(bus=bus, status='ACTIVE').order_by('active_pickup_stop__stop_sequence')
        if passengers.exists():
            route = passengers.first().route

    context = {
        'driver': driver,
        'bus': bus,
        'route': route,
        'passengers': passengers,
        'notifications': Notification.objects.filter(recipient=request.user).order_by('-created_at')[:5]
    }
    return render(request, 'driver/manifest.html', context)

# --- PARENT VIEWS ---

@login_required
def parent_transport_view(request):
    if not hasattr(request.user, 'parent_profile'):
        return redirect('dashboard-redirect')
    parent = request.user.parent_profile
    children = parent.students.all()
    
    children_assignments = []
    for child in children:
        assignment = StudentBusAssignment.objects.select_related(
            'bus', 'route', 'active_pickup_stop', 'active_drop_stop',
            'permanent_pickup_stop', 'permanent_drop_stop'
        ).filter(student=child, status='ACTIVE').first()
        driver = assignment.bus.get_active_driver() if assignment else None
        children_assignments.append({
            'child': child,
            'assignment': assignment,
            'driver': driver,
            'recent_requests': StudentLocationChangeRequest.objects.filter(student=child).order_by('-created_at')[:3]
        })

    context = {
        'parent': parent,
        'children_assignments': children_assignments,
        'notifications': Notification.objects.filter(recipient=request.user).order_by('-created_at')[:10]
    }
    return render(request, 'parent/transport.html', context)


def _admin_required(request):
    if not request.user.is_authenticated or not request.user.is_admin_role():
        return False
    return True


def _read_student_form(post):
    return {
        'first_name': post.get('first_name', '').strip(),
        'last_name': post.get('last_name', '').strip(),
        'student_id': post.get('student_id', '').strip(),
        'department': post.get('department', '').strip(),
        'academic_year': post.get('academic_year', '').strip(),
        'phone_number': post.get('phone_number', '').strip(),
        'guardian_name': post.get('guardian_name', '').strip(),
        'guardian_phone': post.get('guardian_phone', '').strip(),
        'home_address': post.get('home_address', '').strip(),
        'preferred_route_id': post.get('preferred_route_id', '').strip(),
        'preferred_pickup_stop_id': post.get('preferred_pickup_stop_id', '').strip(),
        'preferred_drop_stop_id': post.get('preferred_drop_stop_id', '').strip(),
        'issue_student_login': post.get('issue_student_login') == 'on',
        'issue_parent_login': post.get('issue_parent_login') == 'on',
    }


def _validate_student_form(data, existing_profile=None):
    errors = []
    required = [
        ('first_name', 'Student first name'),
        ('student_id', 'Admission number'),
        ('department', 'Department or course'),
        ('academic_year', 'Academic year or semester'),
        ('phone_number', 'Student phone number'),
        ('guardian_name', 'Parent or guardian name'),
        ('guardian_phone', 'Parent or guardian phone'),
        ('home_address', 'Address'),
        ('preferred_route_id', 'Preferred route'),
        ('preferred_pickup_stop_id', 'Preferred pickup location'),
        ('preferred_drop_stop_id', 'Preferred drop location'),
    ]
    for key, label in required:
        if not data.get(key):
            errors.append(f'{label} is required.')

    if len(data.get('phone_number', '')) > 20 or len(data.get('guardian_phone', '')) > 20:
        errors.append('Phone numbers must be 20 characters or fewer.')

    duplicate = StudentProfile.objects.filter(student_id__iexact=data['student_id'])
    if existing_profile:
        duplicate = duplicate.exclude(pk=existing_profile.pk)
    if data.get('student_id') and duplicate.exists():
        errors.append(f'Admission number "{data["student_id"]}" is already in the system.')

    route = pickup = drop = None
    if data.get('preferred_route_id') and data.get('preferred_pickup_stop_id') and data.get('preferred_drop_stop_id'):
        route = Route.objects.filter(id=data['preferred_route_id'], is_active=True).first()
        if not route:
            errors.append('Select an active route.')
        else:
            pickup = BusStop.objects.filter(id=data['preferred_pickup_stop_id'], route=route).first()
            drop = BusStop.objects.filter(id=data['preferred_drop_stop_id'], route=route).first()
            if not pickup or not drop:
                errors.append('Pickup and drop locations must be stops on the selected route.')
            elif pickup.stop_sequence >= drop.stop_sequence:
                errors.append('Preferred pickup must come before the preferred drop along the route.')
    return errors, route, pickup, drop


def _apply_profile_fields(profile, data, route, pickup, drop):
    profile.student_id = data['student_id']
    profile.department = data['department']
    profile.academic_year = data['academic_year']
    profile.emergency_contact = data['phone_number']
    profile.home_address = data['home_address']
    profile.guardian_name = data['guardian_name']
    profile.guardian_phone = data['guardian_phone']
    profile.preferred_route = route
    profile.preferred_pickup_stop = pickup
    profile.preferred_drop_stop = drop
    profile.save()
    profile.user.first_name = data['first_name']
    profile.user.last_name = data['last_name']
    profile.user.phone_number = data['phone_number']
    profile.user.save(update_fields=['first_name', 'last_name', 'phone_number'])


def _link_or_create_parent(student, data):
    """Link a guardian phone to an existing parent, or create a parent login."""
    existing = find_parent_by_phone(data['guardian_phone'])
    if existing:
        existing.students.add(student)
        return {
            'kind': 'parent',
            'action': 'linked',
            'name': existing.user.get_full_name(),
            'username': existing.user.username,
            'password': None,
        }

    first_name, last_name = split_person_name(data['guardian_name'])
    username = username_from_identifier(data['student_id'], prefix='parent_')
    parent_user = User.objects.create_user(
        username=username,
        password=None,
        first_name=first_name,
        last_name=last_name,
        role='PARENT',
        phone_number=data['guardian_phone'][:20],
    )
    parent_user.set_unusable_password()
    parent_user.must_change_password = False
    parent_user.save(update_fields=['password', 'must_change_password'])
    parent_profile = ParentProfile.objects.create(user=parent_user, relationship='Guardian')
    parent_profile.students.add(student)
    temporary_password = issue_temporary_password(parent_user)
    return {
        'kind': 'parent',
        'action': 'created',
        'name': parent_user.get_full_name(),
        'username': parent_user.username,
        'password': temporary_password,
    }


def _stash_credentials(request, entries):
    request.session['issued_credentials'] = entries
    request.session.modified = True


@login_required
def change_password_view(request):
    error = None
    if request.method == 'POST':
        current_password = request.POST.get('current_password', '')
        new_password = request.POST.get('new_password', '')
        confirm_password = request.POST.get('confirm_password', '')
        if not request.user.check_password(current_password):
            error = 'The current password is incorrect.'
        elif new_password != confirm_password:
            error = 'The new password and confirmation do not match.'
        elif current_password == new_password:
            error = 'Choose a password that is different from the temporary password.'
        else:
            try:
                validate_password(new_password, request.user)
            except ValidationError as exc:
                error = ' '.join(exc.messages)
            else:
                request.user.set_password(new_password)
                request.user.must_change_password = False
                request.user.save(update_fields=['password', 'must_change_password'])
                update_session_auth_hash(request, request.user)
                messages.success(request, 'Your password has been changed.')
                return redirect('dashboard-redirect')
    return render(request, 'auth/change_password.html', {
        'error': error,
        'forced': request.user.must_change_password,
    })


@login_required
def admin_student_management_view(request):
    if not _admin_required(request):
        return redirect('dashboard-redirect')

    form_data = None
    form_errors = []
    edit_profile = None
    edit_id = request.GET.get('edit')
    if edit_id:
        edit_profile = StudentProfile.objects.select_related('user').filter(id=edit_id).first()

    if request.method == 'POST':
        action = request.POST.get('action')
        if action in ('create_student', 'update_student'):
            form_data = _read_student_form(request.POST)
            existing = None
            if action == 'update_student':
                existing = get_object_or_404(StudentProfile, id=request.POST.get('profile_id'))
            form_errors, route, pickup, drop = _validate_student_form(form_data, existing)
            if not form_errors:
                issued = []
                with transaction.atomic():
                    if existing:
                        _apply_profile_fields(existing, form_data, route, pickup, drop)
                        student = existing
                    else:
                        username = username_from_identifier(form_data['student_id'])
                        new_user = User(
                            username=username,
                            first_name=form_data['first_name'],
                            last_name=form_data['last_name'],
                            role='STUDENT',
                            phone_number=form_data['phone_number'][:20],
                            must_change_password=False,
                        )
                        new_user.set_unusable_password()
                        new_user.save()
                        student = StudentProfile.objects.create(
                            user=new_user,
                            student_id=form_data['student_id'],
                            department=form_data['department'],
                            academic_year=form_data['academic_year'],
                            emergency_contact=form_data['phone_number'][:20],
                            home_address=form_data['home_address'],
                            guardian_name=form_data['guardian_name'],
                            guardian_phone=form_data['guardian_phone'][:20],
                            preferred_route=route,
                            preferred_pickup_stop=pickup,
                            preferred_drop_stop=drop,
                        )
                        send_notification(
                            recipient=new_user,
                            title='Transportation record created',
                            message=(
                                'The college transport office has entered your transportation record. '
                                'You can sign in after the administrator gives you a username and temporary password. '
                                'A bus is assigned only after the administrator confirms it.'
                            ),
                            notification_type='GENERAL',
                            priority='NORMAL',
                        )
                    if form_data['issue_student_login']:
                        temporary_password = issue_temporary_password(student.user)
                        issued.append({
                            'kind': 'student',
                            'action': 'created',
                            'name': student.user.get_full_name(),
                            'username': student.user.username,
                            'password': temporary_password,
                        })
                    if form_data['issue_parent_login']:
                        issued.append(_link_or_create_parent(student, form_data))
                if issued:
                    _stash_credentials(request, issued)
                messages.success(request, f'Student record saved for {student.user.get_full_name()} ({student.student_id}).')
                return redirect('admin-student-management')
            edit_profile = existing
        elif action == 'issue_student_login':
            student = get_object_or_404(StudentProfile, id=request.POST.get('profile_id'))
            temporary_password = issue_temporary_password(student.user)
            _stash_credentials(request, [{
                'kind': 'student',
                'action': 'reset',
                'name': student.user.get_full_name(),
                'username': student.user.username,
                'password': temporary_password,
            }])
            messages.success(request, f'Temporary password issued for {student.user.username}. It is shown once on this page.')
            return redirect('admin-student-management')
        elif action == 'issue_parent_login':
            student = get_object_or_404(StudentProfile, id=request.POST.get('profile_id'))
            if not student.guardian_name or not student.guardian_phone:
                messages.error(request, 'Enter a guardian name and phone on the student record before creating a parent login.')
                return redirect('admin-student-management')
            linked = student.parents.select_related('user').first()
            if linked:
                temporary_password = issue_temporary_password(linked.user)
                entry = {
                    'kind': 'parent',
                    'action': 'reset',
                    'name': linked.user.get_full_name(),
                    'username': linked.user.username,
                    'password': temporary_password,
                }
            else:
                entry = _link_or_create_parent(student, {
                    'guardian_name': student.guardian_name,
                    'guardian_phone': student.guardian_phone,
                    'student_id': student.student_id,
                })
            _stash_credentials(request, [entry])
            messages.success(request, 'Parent account updated. Any new temporary password is shown once on this page.')
            return redirect('admin-student-management')

    issued_credentials = request.session.pop('issued_credentials', [])
    if issued_credentials:
        request.session.modified = True

    students = StudentProfile.objects.select_related(
        'user', 'preferred_route', 'preferred_pickup_stop', 'preferred_drop_stop'
    ).prefetch_related('parents__user').order_by('student_id')
    routes = Route.objects.filter(is_active=True).prefetch_related('stops')

    return render(request, 'admin/student_management.html', {
        'students': students,
        'routes': routes,
        'form_data': form_data,
        'form_errors': form_errors,
        'edit_profile': edit_profile,
        'issued_credentials': issued_credentials,
    })
