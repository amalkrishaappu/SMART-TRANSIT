from django.db import models
from apps.accounts.models import StudentProfile, DriverProfile

class Bus(models.Model):
    STATUS_CHOICES = [
        ('ACTIVE', 'Active in Service'),
        ('MAINTENANCE', 'Under Maintenance'),
        ('BREAKDOWN', 'Vehicle Breakdown'),
        ('STANDBY', 'Standby / Reserve'),
    ]

    bus_number = models.CharField(max_length=50, unique=True, db_index=True)
    registration_number = models.CharField(max_length=50, unique=True)
    seating_capacity = models.PositiveIntegerField(default=45)
    model_name = models.CharField(max_length=100, default='Ashok Leyland Viking')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE')
    created_at = models.DateTimeField(auto_now_add=True)

    def current_occupancy_count(self):
        return self.student_assignments.filter(status='ACTIVE').count()

    def available_seats(self):
        return max(0, self.seating_capacity - self.current_occupancy_count())

    def get_active_driver(self):
        da = self.driver_assignments.filter(is_active=True).select_related('driver__user').first()
        return da.driver if da else None

    def __str__(self):
        return f"{self.bus_number} ({self.registration_number}) - Cap: {self.seating_capacity}"


class DriverBusAssignment(models.Model):
    driver = models.ForeignKey(DriverProfile, on_delete=models.CASCADE, related_name='bus_assignments')
    bus = models.ForeignKey(Bus, on_delete=models.CASCADE, related_name='driver_assignments')
    is_active = models.BooleanField(default=True)
    assigned_date = models.DateField(auto_now_add=True)

    def __str__(self):
        return f"{self.driver} -> {self.bus.bus_number}"


class StudentBusAssignment(models.Model):
    STATUS_CHOICES = [
        ('ACTIVE', 'Active'),
        ('INACTIVE', 'Inactive'),
        ('SUSPENDED', 'Suspended'),
    ]

    student = models.OneToOneField(StudentProfile, on_delete=models.CASCADE, related_name='bus_assignment')
    bus = models.ForeignKey(Bus, on_delete=models.PROTECT, related_name='student_assignments')
    route = models.ForeignKey('routes.Route', on_delete=models.PROTECT, related_name='student_assignments')

    # Baseline permanent stops
    permanent_pickup_stop = models.ForeignKey(
        'routes.BusStop', on_delete=models.PROTECT, related_name='permanent_pickup_students'
    )
    permanent_drop_stop = models.ForeignKey(
        'routes.BusStop', on_delete=models.PROTECT, related_name='permanent_drop_students'
    )

    # Currently effective stops (reflecting active approved temporary/permanent changes)
    active_pickup_stop = models.ForeignKey(
        'routes.BusStop', on_delete=models.PROTECT, related_name='active_pickup_students'
    )
    active_drop_stop = models.ForeignKey(
        'routes.BusStop', on_delete=models.PROTECT, related_name='active_drop_students'
    )

    is_temporary_active = models.BooleanField(default=False)
    temporary_end_date = models.DateField(null=True, blank=True)
    active_request = models.ForeignKey(
        'routes.StudentLocationChangeRequest',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='active_assignments'
    )

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.student.student_id} assigned to {self.bus.bus_number} on {self.route.route_code}"
