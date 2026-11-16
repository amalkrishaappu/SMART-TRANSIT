from rest_framework import serializers
from django.utils import timezone
from .models import Route, BusStop, StudentLocationChangeRequest
from apps.fleet.models import StudentBusAssignment

class BusStopSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusStop
        fields = [
            'id', 'stop_name', 'stop_sequence', 'latitude', 'longitude',
            'scheduled_pickup_time', 'scheduled_drop_time'
        ]

class RouteSerializer(serializers.ModelSerializer):
    stops = BusStopSerializer(many=True, read_only=True)

    class Meta:
        model = Route
        fields = [
            'id', 'route_name', 'route_code', 'start_location', 'end_location',
            'total_distance_km', 'estimated_duration_mins', 'is_active', 'stops'
        ]

class StudentLocationChangeRequestSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.user.get_full_name', read_only=True)
    student_id_code = serializers.CharField(source='student.student_id', read_only=True)
    assigned_bus_number = serializers.CharField(source='assigned_bus.bus_number', read_only=True)
    assigned_route_code = serializers.CharField(source='assigned_route.route_code', read_only=True)
    assigned_route_name = serializers.CharField(source='assigned_route.route_name', read_only=True)
    current_pickup_name = serializers.CharField(source='current_pickup_stop.stop_name', read_only=True)
    current_drop_name = serializers.CharField(source='current_drop_stop.stop_name', read_only=True)
    requested_pickup_name = serializers.CharField(source='requested_pickup_stop.stop_name', read_only=True)
    requested_drop_name = serializers.CharField(source='requested_drop_stop.stop_name', read_only=True)
    reviewed_by_name = serializers.CharField(source='reviewed_by.get_full_name', read_only=True)

    class Meta:
        model = StudentLocationChangeRequest
        fields = [
            'id', 'student', 'student_name', 'student_id_code',
            'assigned_bus', 'assigned_bus_number',
            'assigned_route', 'assigned_route_code', 'assigned_route_name',
            'current_pickup_stop', 'current_pickup_name',
            'current_drop_stop', 'current_drop_name',
            'requested_pickup_stop', 'requested_pickup_name',
            'requested_drop_stop', 'requested_drop_name',
            'request_type', 'change_duration', 'reason',
            'effective_start_date', 'effective_end_date',
            'status', 'rejection_reason', 'administrator_remarks',
            'reviewed_by', 'reviewed_by_name', 'reviewed_at',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'student', 'assigned_bus', 'assigned_route',
            'current_pickup_stop', 'current_drop_stop',
            'status', 'rejection_reason', 'administrator_remarks',
            'reviewed_by', 'reviewed_at', 'created_at', 'updated_at'
        ]

    def validate(self, data):
        user = self.context['request'].user
        if not hasattr(user, 'student_profile'):
            raise serializers.ValidationError("Only registered students can submit location change requests.")

        student = user.student_profile
        try:
            assignment = StudentBusAssignment.objects.select_related(
                'bus', 'route', 'active_pickup_stop', 'active_drop_stop'
            ).get(student=student, status='ACTIVE')
        except StudentBusAssignment.DoesNotExist:
            raise serializers.ValidationError("You do not have an active bus assignment to request changes for.")

        # 1. Prevent duplicate pending requests
        existing_pending = StudentLocationChangeRequest.objects.filter(
            student=student,
            status='PENDING'
        ).exists()
        if existing_pending:
            raise serializers.ValidationError(
                "You already have a pending location change request. Please wait for administrator review or cancel it before submitting a new one."
            )

        request_type = data.get('request_type')
        requested_pickup = data.get('requested_pickup_stop')
        requested_drop = data.get('requested_drop_stop')

        # 2. Check requested stops according to request_type
        if request_type == 'PICKUP' and not requested_pickup:
            raise serializers.ValidationError({"requested_pickup_stop": "Please select a requested pickup stop."})
        elif request_type == 'DROP' and not requested_drop:
            raise serializers.ValidationError({"requested_drop_stop": "Please select a requested drop stop."})
        elif request_type == 'BOTH' and (not requested_pickup or not requested_drop):
            raise serializers.ValidationError("Both pickup and drop stops must be specified for 'BOTH' request type.")

        # 3. Route containment validation: Must belong to student's assigned route
        assigned_route = assignment.route
        if requested_pickup and requested_pickup.route_id != assigned_route.id:
            raise serializers.ValidationError(
                {"requested_pickup_stop": f"Selected pickup stop does not belong to your assigned route ({assigned_route.route_name})."}
            )
        if requested_drop and requested_drop.route_id != assigned_route.id:
            raise serializers.ValidationError(
                {"requested_drop_stop": f"Selected drop stop does not belong to your assigned route ({assigned_route.route_name})."}
            )

        # 4. Stop sequence validation: Pickup must precede Drop
        eff_pickup = requested_pickup if requested_pickup else assignment.active_pickup_stop
        eff_drop = requested_drop if requested_drop else assignment.active_drop_stop

        if eff_pickup.stop_sequence >= eff_drop.stop_sequence:
            raise serializers.ValidationError(
                f"Invalid stop sequence: Pickup stop '{eff_pickup.stop_name}' (Seq #{eff_pickup.stop_sequence}) "
                f"must precede drop stop '{eff_drop.stop_name}' (Seq #{eff_drop.stop_sequence}) along the route."
            )

        # 5. Date validation
        today = timezone.now().date()
        eff_start = data.get('effective_start_date')
        if eff_start and eff_start < today:
            raise serializers.ValidationError({"effective_start_date": "Effective start date cannot be in the past."})

        change_duration = data.get('change_duration')
        eff_end = data.get('effective_end_date')
        if change_duration == 'TEMPORARY':
            if not eff_end:
                raise serializers.ValidationError({"effective_end_date": "End date is required for temporary change requests."})
            if eff_end < eff_start:
                raise serializers.ValidationError({"effective_end_date": "Effective end date must be on or after start date."})

        # Inject context references
        data['student'] = student
        data['assigned_bus'] = assignment.bus
        data['assigned_route'] = assignment.route
        data['current_pickup_stop'] = assignment.active_pickup_stop
        data['current_drop_stop'] = assignment.active_drop_stop

        return data
