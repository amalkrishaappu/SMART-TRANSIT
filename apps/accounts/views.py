from django.shortcuts import render, redirect
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from apps.accounts.models import User, StudentProfile, ParentProfile, DriverProfile
from apps.fleet.models import Bus, StudentBusAssignment, DriverBusAssignment
from apps.routes.models import Route, BusStop, StudentLocationChangeRequest
from apps.notifications.models import Notification

def home_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard-redirect')
    return redirect('login-view')

def login_view(request):
    error = None
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            return redirect('dashboard-redirect')
        else:
            error = 'Invalid username or password.'
    return render(request, 'auth/login.html', {'error': error})

def logout_view(request):
    logout(request)
    return redirect('login-view')

@login_required
def dashboard_redirect_view(request):
    role = request.user.role
    if role == 'ADMIN' or request.user.is_superuser:
        return redirect('admin-location-requests')
    elif role == 'STUDENT':
        return redirect('student-location-request')
    elif role == 'DRIVER':
        return redirect('driver-manifest')
    elif role == 'PARENT':
        return redirect('parent-transport')
    return redirect('login-view')

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

    context = {
        'student': student,
        'assignment': assignment,
        'available_stops': available_stops,
        'my_requests': my_requests,
        'notifications': Notification.objects.filter(recipient=request.user).order_by('-created_at')[:5]
    }
    return render(request, 'student/location_change_request.html', context)

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
        children_assignments.append({
            'child': child,
            'assignment': assignment,
            'recent_requests': StudentLocationChangeRequest.objects.filter(student=child).order_by('-created_at')[:3]
        })

    context = {
        'parent': parent,
        'children_assignments': children_assignments,
        'notifications': Notification.objects.filter(recipient=request.user).order_by('-created_at')[:10]
    }
    return render(request, 'parent/transport.html', context)
