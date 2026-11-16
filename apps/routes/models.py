from django.db import models
from apps.accounts.models import StudentProfile, User

class Route(models.Model):
    route_name = models.CharField(max_length=150, db_index=True)
    route_code = models.CharField(max_length=50, unique=True, db_index=True)
    start_location = models.CharField(max_length=150)
    end_location = models.CharField(max_length=150)
    total_distance_km = models.DecimalField(max_digits=6, decimal_places=2, default=24.50)
    estimated_duration_mins = models.PositiveIntegerField(default=55)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.route_code}: {self.route_name}"


class BusStop(models.Model):
    route = models.ForeignKey(Route, on_delete=models.CASCADE, related_name='stops')
    stop_name = models.CharField(max_length=150)
    stop_sequence = models.PositiveIntegerField()
    latitude = models.DecimalField(max_digits=10, decimal_places=8)
    longitude = models.DecimalField(max_digits=11, decimal_places=8)
    scheduled_pickup_time = models.TimeField()
    scheduled_drop_time = models.TimeField()

    class Meta:
        ordering = ['stop_sequence']
        unique_together = ('route', 'stop_sequence')

    def __str__(self):
        return f"{self.route.route_code} [Stop #{self.stop_sequence}] {self.stop_name}"


class StudentLocationChangeRequest(models.Model):
    REQUEST_TYPE_CHOICES = [
        ('PICKUP', 'Change Pickup Location Only'),
        ('DROP', 'Change Drop Location Only'),
        ('BOTH', 'Change Both Pickup & Drop Locations'),
    ]

    DURATION_CHOICES = [
        ('TEMPORARY', 'Temporary Change'),
        ('PERMANENT', 'Permanent Change'),
    ]

    STATUS_CHOICES = [
        ('PENDING', 'Pending Admin Review'),
        ('APPROVED', 'Approved & Active'),
        ('REJECTED', 'Rejected'),
        ('CANCELLED', 'Cancelled by Student'),
        ('EXPIRED', 'Expired (Temporary reverted)'),
    ]

    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE, related_name='location_requests')
    assigned_bus = models.ForeignKey('fleet.Bus', on_delete=models.PROTECT, related_name='location_requests')
    assigned_route = models.ForeignKey(Route, on_delete=models.PROTECT, related_name='location_requests')

    # Current stops at submission time
    current_pickup_stop = models.ForeignKey(
        BusStop, on_delete=models.PROTECT, related_name='current_pickup_requests'
    )
    current_drop_stop = models.ForeignKey(
        BusStop, on_delete=models.PROTECT, related_name='current_drop_requests'
    )

    # Requested stops
    requested_pickup_stop = models.ForeignKey(
        BusStop, on_delete=models.PROTECT, null=True, blank=True, related_name='requested_pickup_requests'
    )
    requested_drop_stop = models.ForeignKey(
        BusStop, on_delete=models.PROTECT, null=True, blank=True, related_name='requested_drop_requests'
    )

    request_type = models.CharField(max_length=10, choices=REQUEST_TYPE_CHOICES)
    change_duration = models.CharField(max_length=15, choices=DURATION_CHOICES, default='TEMPORARY')
    reason = models.TextField()

    effective_start_date = models.DateField()
    effective_end_date = models.DateField(null=True, blank=True)

    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='PENDING', db_index=True)
    rejection_reason = models.TextField(null=True, blank=True)
    administrator_remarks = models.TextField(null=True, blank=True)

    reviewed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_location_requests'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['student', 'status']),
            models.Index(fields=['assigned_route', 'status']),
        ]

    def __str__(self):
        return f"Req #{self.id} [{self.get_request_type_display()}] by {self.student.student_id} ({self.status})"
