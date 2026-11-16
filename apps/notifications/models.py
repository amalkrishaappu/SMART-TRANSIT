from django.db import models
from apps.accounts.models import User

class Notification(models.Model):
    NOTIFICATION_TYPE_CHOICES = [
        ('LOCATION_CHANGE_APPROVED', 'Location Change Approved'),
        ('LOCATION_CHANGE_REJECTED', 'Location Change Rejected'),
        ('GEOFENCE_APPROACH', 'Bus Approaching Pickup Point'),
        ('STOP_ARRIVAL', 'Bus Reached Stop'),
        ('BOARDING_CONFIRMED', 'Student Boarded Bus'),
        ('EXIT_CONFIRMED', 'Student Exited Bus'),
        ('BUS_DELAY', 'Bus Delay Notice'),
        ('ROUTE_CHANGE', 'Route Update'),
        ('EMERGENCY_ALERT', 'Emergency SOS Alert'),
        ('GENERAL', 'General Announcement'),
    ]

    PRIORITY_CHOICES = [
        ('LOW', 'Low'),
        ('NORMAL', 'Normal'),
        ('HIGH', 'High'),
        ('CRITICAL', 'Critical Alert'),
    ]

    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=200)
    message = models.TextField()
    notification_type = models.CharField(max_length=30, choices=NOTIFICATION_TYPE_CHOICES, default='GENERAL')
    priority = models.CharField(max_length=15, choices=PRIORITY_CHOICES, default='NORMAL')
    is_read = models.BooleanField(default=False, db_index=True)
    metadata = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.priority}] {self.title} to {self.recipient.username}"
