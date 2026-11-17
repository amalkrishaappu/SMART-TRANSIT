from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from django.utils import timezone
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.http import JsonResponse
from django.contrib import messages
from django.db import transaction

from .models import Route, BusStop, StudentLocationChangeRequest
from .serializers import RouteSerializer, BusStopSerializer, StudentLocationChangeRequestSerializer
from apps.accounts.models import User, DriverProfile
from apps.fleet.models import Bus, StudentBusAssignment, DriverBusAssignment
from apps.notifications.services import notify_location_change_approved, notify_location_change_rejected, send_notification

# --- REST APIS ---

@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def my_assignment_details(request):
    """
    Returns the student's assigned bus, route, and currently active pickup/drop stops.
    """
    if not hasattr(request.user, 'student_profile'):
        return Response({'detail': 'User is not a student.'}, status=status.HTTP_400_BAD_REQUEST)

    student = request.user.student_profile
    try:
        assignment = StudentBusAssignment.objects.select_related(
            'bus', 'route', 'active_pickup_stop', 'active_drop_stop',
            'permanent_pickup_stop', 'permanent_drop_stop'
        ).get(student=student, status='ACTIVE')
    except StudentBusAssignment.DoesNotExist:
        return Response({'detail': 'No active bus assignment found.'}, status=status.HTTP_404_NOT_FOUND)

    stops = BusStop.objects.filter(route=assignment.route).order_by('stop_sequence')

    return Response({
        'student_id': student.student_id,
        'student_name': request.user.get_full_name(),
        'bus_number': assignment.bus.bus_number,
        'bus_model': assignment.bus.model_name,
        'route_id': assignment.route.id,
        'route_code': assignment.route.route_code,
        'route_name': assignment.route.route_name,
        'current_pickup': {
            'id': assignment.active_pickup_stop.id,
            'name': assignment.active_pickup_stop.stop_name,
            'sequence': assignment.active_pickup_stop.stop_sequence,
            'time': assignment.active_pickup_stop.scheduled_pickup_time.strftime('%H:%M'),
            'lat': float(assignment.active_pickup_stop.latitude),
            'lng': float(assignment.active_pickup_stop.longitude),
        },
        'current_drop': {
            'id': assignment.active_drop_stop.id,
            'name': assignment.active_drop_stop.stop_name,
            'sequence': assignment.active_drop_stop.stop_sequence,
            'time': assignment.active_drop_stop.scheduled_drop_time.strftime('%H:%M'),
            'lat': float(assignment.active_drop_stop.latitude),
            'lng': float(assignment.active_drop_stop.longitude),
        },
        'is_temporary_active': assignment.is_temporary_active,
        'temporary_end_date': assignment.temporary_end_date,
        'available_stops': BusStopSerializer(stops, many=True).data
    })


@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def available_route_stops(request, route_id):
    route = get_object_or_404(Route, id=route_id, is_active=True)
    stops = route.stops.all().order_by('stop_sequence')
    return Response(BusStopSerializer(stops, many=True).data)


class StudentLocationChangeRequestViewSet(viewsets.ModelViewSet):
    serializer_class = StudentLocationChangeRequestSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        queryset = StudentLocationChangeRequest.objects.select_related(
            'student__user', 'assigned_bus', 'assigned_route',
            'current_pickup_stop', 'current_drop_stop',
            'requested_pickup_stop', 'requested_drop_stop',
            'reviewed_by'
        )

        if user.is_admin_role():
            status_filter = self.request.query_params.get('status')
            if status_filter:
                queryset = queryset.filter(status=status_filter.upper())
            return queryset
        elif hasattr(user, 'student_profile'):
            return queryset.filter(student=user.student_profile)
        elif hasattr(user, 'parent_profile'):
            children = user.parent_profile.students.all()
            return queryset.filter(student__in=children)
        elif hasattr(user, 'driver_profile'):
            assigned_buses = [da.bus for da in user.driver_profile.bus_assignments.filter(is_active=True)]
            return queryset.filter(assigned_bus__in=assigned_buses, status='APPROVED')
        return queryset.none()

    def perform_create(self, serializer):
        serializer.save()

    @action(detail=True, methods=['post', 'delete'])
    def cancel(self, request, pk=None):
        req_obj = self.get_object()
        user = request.user

        if not hasattr(user, 'student_profile') or req_obj.student != user.student_profile:
            return Response({'detail': 'You can only cancel your own requests.'}, status=status.HTTP_403_FORBIDDEN)

        if req_obj.status != 'PENDING':
            return Response(
                {'detail': f'Cannot cancel request with status {req_obj.status}. Only PENDING requests can be cancelled.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        req_obj.status = 'CANCELLED'
        req_obj.save()
        return Response({'status': 'CANCELLED', 'message': 'Request cancelled successfully.'})

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        if not request.user.is_admin_role():
            return Response({'detail': 'Only administrators can approve location change requests.'}, status=status.HTTP_403_FORBIDDEN)

        req_obj = self.get_object()
        if req_obj.status != 'PENDING':
            return Response(
                {'detail': f'Cannot approve request with status {req_obj.status}. Only PENDING requests can be approved.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            assignment = StudentBusAssignment.objects.get(student=req_obj.student, status='ACTIVE')
        except StudentBusAssignment.DoesNotExist:
            return Response({'detail': 'Active bus assignment for student not found.'}, status=status.HTTP_404_NOT_FOUND)

        admin_remarks = request.data.get('admin_remarks', '').strip()

        if req_obj.change_duration == 'PERMANENT':
            if req_obj.requested_pickup_stop:
                assignment.permanent_pickup_stop = req_obj.requested_pickup_stop
                assignment.active_pickup_stop = req_obj.requested_pickup_stop
            if req_obj.requested_drop_stop:
                assignment.permanent_drop_stop = req_obj.requested_drop_stop
                assignment.active_drop_stop = req_obj.requested_drop_stop
            assignment.is_temporary_active = False
            assignment.temporary_end_date = None
            assignment.active_request = None
        else: # TEMPORARY
            if req_obj.requested_pickup_stop:
                assignment.active_pickup_stop = req_obj.requested_pickup_stop
            if req_obj.requested_drop_stop:
                assignment.active_drop_stop = req_obj.requested_drop_stop
            assignment.is_temporary_active = True
            assignment.temporary_end_date = req_obj.effective_end_date
            assignment.active_request = req_obj

        assignment.save()

        req_obj.status = 'APPROVED'
        req_obj.administrator_remarks = admin_remarks
        req_obj.reviewed_by = request.user
        req_obj.reviewed_at = timezone.now()
        req_obj.save()

        notify_location_change_approved(req_obj)

        return Response({
            'status': 'APPROVED',
            'message': 'Request approved successfully. Student assignment and passenger manifests have been updated.',
            'request': StudentLocationChangeRequestSerializer(req_obj, context={'request': request}).data
        })

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        if not request.user.is_admin_role():
            return Response({'detail': 'Only administrators can reject location change requests.'}, status=status.HTTP_403_FORBIDDEN)

        req_obj = self.get_object()
        if req_obj.status != 'PENDING':
            return Response(
                {'detail': f'Cannot reject request with status {req_obj.status}. Only PENDING requests can be rejected.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        rejection_reason = request.data.get('rejection_reason', '').strip()
        if not rejection_reason:
            return Response(
                {'rejection_reason': 'A clear rejection reason is mandatory when rejecting a location change request.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        req_obj.status = 'REJECTED'
        req_obj.rejection_reason = rejection_reason
        req_obj.administrator_remarks = request.data.get('admin_remarks', '').strip()
        req_obj.reviewed_by = request.user
        req_obj.reviewed_at = timezone.now()
        req_obj.save()

        notify_location_change_rejected(req_obj, rejection_reason)

        return Response({
            'status': 'REJECTED',
            'message': 'Request rejected. Assignments remain unchanged.',
            'request': StudentLocationChangeRequestSerializer(req_obj, context={'request': request}).data
        })


# --- ADMINISTRATOR DYNAMIC FLEET & ROUTE MANAGEMENT VIEWS ---

@login_required
def admin_fleet_routes_view(request):
    """
    Dedicated management interface for the Administrator to add/manage Buses, Drivers, Routes, and Stops dynamically.
    """
    if not request.user.is_admin_role():
        return redirect('dashboard-redirect')

    buses = Bus.objects.prefetch_related('driver_assignments__driver__user', 'student_assignments').all().order_by('bus_number')
    routes = Route.objects.prefetch_related('stops').all().order_by('route_code')
    drivers = DriverProfile.objects.select_related('user').all().order_by('user__first_name')

    return render(request, 'admin/fleet_routes_management.html', {
        'buses': buses,
        'routes': routes,
        'drivers': drivers
    })

@login_required
@require_POST
def admin_add_bus_action(request):
    if not request.user.is_admin_role():
        return JsonResponse({'detail': 'Unauthorized'}, status=403)

    bus_number = request.POST.get('bus_number', '').strip().upper()
    registration_number = request.POST.get('registration_number', '').strip().upper()
    seating_capacity = request.POST.get('seating_capacity', '').strip()
    model_name = request.POST.get('model_name', '').strip() or 'College Bus'

    if not (bus_number and registration_number and seating_capacity):
        messages.error(request, 'Bus Number, Registration Plate, and Seating Capacity are required.')
        return redirect('admin-fleet-routes')

    if Bus.objects.filter(bus_number=bus_number).exists():
        messages.error(request, f'Bus Number "{bus_number}" already exists.')
        return redirect('admin-fleet-routes')

    if Bus.objects.filter(registration_number=registration_number).exists():
        messages.error(request, f'Registration "{registration_number}" already exists.')
        return redirect('admin-fleet-routes')

    try:
        Bus.objects.create(
            bus_number=bus_number,
            registration_number=registration_number,
            seating_capacity=int(seating_capacity),
            model_name=model_name,
            status='ACTIVE'
        )
        messages.success(request, f'Bus "{bus_number}" added successfully to the fleet.')
    except Exception as e:
        messages.error(request, f'Error adding bus: {str(e)}')

    return redirect('admin-fleet-routes')

@login_required
@require_POST
def admin_delete_bus_action(request, bus_id):
    if not request.user.is_admin_role():
        return JsonResponse({'detail': 'Unauthorized'}, status=403)
    bus = get_object_or_404(Bus, id=bus_id)
    if bus.student_assignments.filter(status='ACTIVE').exists():
        messages.error(request, f'Cannot delete {bus.bus_number}: Active students are assigned to this bus.')
    else:
        bus_no = bus.bus_number
        bus.delete()
        messages.success(request, f'Bus "{bus_no}" deleted successfully.')
    return redirect('admin-fleet-routes')

@login_required
@require_POST
def admin_assign_driver_action(request, bus_id):
    """
    Administrator assigns or reassigns an official driver to a bus.
    """
    if not request.user.is_admin_role():
        return JsonResponse({'detail': 'Unauthorized'}, status=403)

    bus = get_object_or_404(Bus, id=bus_id)
    driver_id = request.POST.get('driver_id')

    if not driver_id:
        # Clear current assignment
        bus.driver_assignments.filter(is_active=True).update(is_active=False)
        messages.info(request, f'Driver assignment cleared for {bus.bus_number}.')
        return redirect('admin-fleet-routes')

    driver = get_object_or_404(DriverProfile, id=driver_id)

    with transaction.atomic():
        # Deactivate previous driver assignments for this bus
        DriverBusAssignment.objects.filter(bus=bus, is_active=True).update(is_active=False)
        # Deactivate any previous bus assignments for this driver (1 active bus per driver)
        DriverBusAssignment.objects.filter(driver=driver, is_active=True).update(is_active=False)

        # Create active assignment
        DriverBusAssignment.objects.create(
            driver=driver,
            bus=bus,
            is_active=True
        )

        # Send in-app notification to driver
        send_notification(
            recipient=driver.user,
            title="Official Bus Assignment Duty",
            message=(
                f"Dear {driver.user.get_full_name()},\n\n"
                f"You have been officially assigned as the designated driver for {bus.bus_number} "
                f"({bus.model_name}, Plate: {bus.registration_number}).\n\n"
                f"Please log in to your Driver Console to view your assigned passenger manifest and trip details."
            ),
            notification_type='GENERAL',
            priority='HIGH'
        )

    messages.success(request, f'Driver "{driver.user.get_full_name()}" assigned successfully to {bus.bus_number}.')
    return redirect('admin-fleet-routes')

@login_required
@require_POST
def admin_add_driver_action(request):
    """
    Administrator onboards a new driver directly.
    """
    if not request.user.is_admin_role():
        return JsonResponse({'detail': 'Unauthorized'}, status=403)

    first_name = request.POST.get('first_name', '').strip()
    last_name = request.POST.get('last_name', '').strip()
    username = request.POST.get('username', '').strip()
    license_number = request.POST.get('license_number', '').strip().upper()
    phone_number = request.POST.get('phone_number', '').strip()
    experience_years = request.POST.get('experience_years', '5').strip()
    password = request.POST.get('password', '').strip()

    if not (first_name and username and license_number and password):
        messages.error(request, 'Driver Name, Username, License Number, and Password are required.')
        return redirect('admin-fleet-routes')

    if User.objects.filter(username__iexact=username).exists():
        messages.error(request, f'Username "{username}" is already taken.')
        return redirect('admin-fleet-routes')

    if DriverProfile.objects.filter(license_number__iexact=license_number).exists():
        messages.error(request, f'License Number "{license_number}" is already registered.')
        return redirect('admin-fleet-routes')

    try:
        with transaction.atomic():
            driver_user = User.objects.create_user(
                username=username,
                password=password,
                first_name=first_name,
                last_name=last_name,
                role='DRIVER',
                phone_number=phone_number
            )
            DriverProfile.objects.create(
                user=driver_user,
                license_number=license_number,
                experience_years=int(experience_years or 5),
                is_active_duty=True
            )
        messages.success(request, f'Driver "{first_name} {last_name}" onboarded successfully! (Username: {username})')
    except Exception as e:
        messages.error(request, f'Error adding driver: {str(e)}')

    return redirect('admin-fleet-routes')

@login_required
@require_POST
def admin_add_route_action(request):
    if not request.user.is_admin_role():
        return JsonResponse({'detail': 'Unauthorized'}, status=403)

    route_code = request.POST.get('route_code', '').strip().upper()
    route_name = request.POST.get('route_name', '').strip()
    start_location = request.POST.get('start_location', '').strip()
    end_location = request.POST.get('end_location', '').strip() or 'College Main Gate'
    total_distance_km = request.POST.get('total_distance_km', '25.0')
    estimated_duration_mins = request.POST.get('estimated_duration_mins', '60')

    if not (route_code and route_name and start_location):
        messages.error(request, 'Route Code, Route Name, and Start Location are required.')
        return redirect('admin-fleet-routes')

    if Route.objects.filter(route_code=route_code).exists():
        messages.error(request, f'Route Code "{route_code}" already exists.')
        return redirect('admin-fleet-routes')

    try:
        Route.objects.create(
            route_code=route_code,
            route_name=route_name,
            start_location=start_location,
            end_location=end_location,
            total_distance_km=float(total_distance_km or 25.0),
            estimated_duration_mins=int(estimated_duration_mins or 60),
            is_active=True
        )
        messages.success(request, f'Route "{route_code}: {route_name}" created successfully.')
    except Exception as e:
        messages.error(request, f'Error creating route: {str(e)}')

    return redirect('admin-fleet-routes')

@login_required
@require_POST
def admin_delete_route_action(request, route_id):
    if not request.user.is_admin_role():
        return JsonResponse({'detail': 'Unauthorized'}, status=403)
    route = get_object_or_404(Route, id=route_id)
    if route.student_assignments.filter(status='ACTIVE').exists():
        messages.error(request, f'Cannot delete {route.route_code}: Students are currently assigned to this route.')
    else:
        code = route.route_code
        route.delete()
        messages.success(request, f'Route "{code}" and its stops deleted.')
    return redirect('admin-fleet-routes')

@login_required
@require_POST
def admin_add_stop_action(request, route_id):
    if not request.user.is_admin_role():
        return JsonResponse({'detail': 'Unauthorized'}, status=403)

    route = get_object_or_404(Route, id=route_id)
    stop_name = request.POST.get('stop_name', '').strip()
    stop_sequence = request.POST.get('stop_sequence', '').strip()
    scheduled_pickup_time = request.POST.get('scheduled_pickup_time', '').strip()
    scheduled_drop_time = request.POST.get('scheduled_drop_time', '').strip()
    latitude = request.POST.get('latitude', '').strip() or '10.3500'
    longitude = request.POST.get('longitude', '').strip() or '76.2200'

    if not (stop_name and stop_sequence and scheduled_pickup_time and scheduled_drop_time):
        messages.error(request, 'Stop Name, Sequence Number, and Scheduled Times are required.')
        return redirect('admin-fleet-routes')

    seq = int(stop_sequence)
    if BusStop.objects.filter(route=route, stop_sequence=seq).exists():
        messages.error(request, f'Stop Sequence #{seq} already exists on this route. Please use a unique sequence.')
        return redirect('admin-fleet-routes')

    try:
        BusStop.objects.create(
            route=route,
            stop_name=stop_name,
            stop_sequence=seq,
            latitude=float(latitude),
            longitude=float(longitude),
            scheduled_pickup_time=scheduled_pickup_time,
            scheduled_drop_time=scheduled_drop_time
        )
        messages.success(request, f'Stop "#{seq}: {stop_name}" added to route {route.route_code}.')
    except Exception as e:
        messages.error(request, f'Error adding stop: {str(e)}')

    return redirect('admin-fleet-routes')

@login_required
@require_POST
def admin_delete_stop_action(request, stop_id):
    if not request.user.is_admin_role():
        return JsonResponse({'detail': 'Unauthorized'}, status=403)
    stop = get_object_or_404(BusStop, id=stop_id)
    route = stop.route
    stop_name = stop.stop_name
    stop.delete()
    messages.success(request, f'Stop "{stop_name}" removed from route {route.route_code}.')
    return redirect('admin-fleet-routes')
