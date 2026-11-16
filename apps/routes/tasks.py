from django.utils import timezone
from .models import StudentLocationChangeRequest
from apps.fleet.models import StudentBusAssignment
from apps.notifications.services import send_notification

def revert_expired_temporary_requests():
    """
    Checks all approved temporary location change requests whose effective_end_date has passed.
    Reverts student's active pickup/drop assignment back to their permanent baseline.
    """
    today = timezone.now().date()
    expired_requests = StudentLocationChangeRequest.objects.filter(
        status='APPROVED',
        change_duration='TEMPORARY',
        effective_end_date__lt=today
    )

    reverted_count = 0
    for req in expired_requests:
        try:
            assignment = StudentBusAssignment.objects.get(student=req.student)
            # Revert to permanent stops
            assignment.active_pickup_stop = assignment.permanent_pickup_stop
            assignment.active_drop_stop = assignment.permanent_drop_stop
            assignment.is_temporary_active = False
            assignment.temporary_end_date = None
            assignment.active_request = None
            assignment.save()

            req.status = 'EXPIRED'
            req.save()
            reverted_count += 1

            # Notify student
            student_user = req.student.user
            send_notification(
                recipient=student_user,
                title="Temporary Stop Change Ended",
                message=(
                    f"Your temporary stop change period for {req.assigned_bus.bus_number} has concluded. "
                    f"Your pickup point has reverted to {assignment.permanent_pickup_stop.stop_name} "
                    f"and drop point to {assignment.permanent_drop_stop.stop_name}."
                ),
                notification_type='LOCATION_CHANGE_APPROVED',
                priority='NORMAL'
            )
        except StudentBusAssignment.DoesNotExist:
            req.status = 'EXPIRED'
            req.save()

    return reverted_count
