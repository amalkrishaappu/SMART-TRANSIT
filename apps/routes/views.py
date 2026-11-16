from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.response import Response
from django.utils import timezone
from django.shortcuts import get_object_or_404

from .models import Route, BusStop, StudentLocationChangeRequest
from .serializers import RouteSerializer, BusStopSerializer, StudentLocationChangeRequestSerializer
from apps.fleet.models import StudentBusAssignment
from apps.notifications.services import notify_location_change_approved, notify_location_change_rejected

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

    # All stops along the assigned route
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
    """
    Returns available stops for a given route.
    """
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
            # Parent can view requests for linked children
            children = user.parent_profile.students.all()
            return queryset.filter(student__in=children)
        elif hasattr(user, 'driver_profile'):
            # Driver can view requests for their assigned bus
            assigned_buses = [da.bus for da in user.driver_profile.bus_assignments.filter(is_active=True)]
            return queryset.filter(assigned_bus__in=assigned_buses, status='APPROVED')
        return queryset.none()

    def perform_create(self, serializer):
        serializer.save()

    @action(detail=True, methods=['post', 'delete'])
    def cancel(self, request, pk=None):
        """
        Allows student to cancel their own pending request.
        """
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
        """
        Administrator approves a pending location change request.
        """
        if not request.user.is_admin_role():
            return Response({'detail': 'Only administrators can approve location change requests.'}, status=status.HTTP_403_FORBIDDEN)

        req_obj = self.get_object()
        if req_obj.status != 'PENDING':
            return Response(
                {'detail': f'Cannot approve request with status {req_obj.status}. Only PENDING requests can be approved.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Operational check: Retrieve active assignment
        try:
            assignment = StudentBusAssignment.objects.get(student=req_obj.student, status='ACTIVE')
        except StudentBusAssignment.DoesNotExist:
            return Response({'detail': 'Active bus assignment for student not found.'}, status=status.HTTP_404_NOT_FOUND)

        admin_remarks = request.data.get('admin_remarks', '').strip()

        # Update assignment according to duration
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

        # Mark request as approved
        req_obj.status = 'APPROVED'
        req_obj.administrator_remarks = admin_remarks
        req_obj.reviewed_by = request.user
        req_obj.reviewed_at = timezone.now()
        req_obj.save()

        # Send automated notifications to Student, Parent, and Driver
        notify_location_change_approved(req_obj)

        return Response({
            'status': 'APPROVED',
            'message': 'Request approved successfully. Student assignment and passenger manifests have been updated.',
            'request': StudentLocationChangeRequestSerializer(req_obj, context={'request': request}).data
        })

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        """
        Administrator rejects a pending location change request with mandatory rejection reason.
        """
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

        # Notify student about rejection
        notify_location_change_rejected(req_obj, rejection_reason)

        return Response({
            'status': 'REJECTED',
            'message': 'Request rejected. Assignments remain unchanged.',
            'request': StudentLocationChangeRequestSerializer(req_obj, context={'request': request}).data
        })
