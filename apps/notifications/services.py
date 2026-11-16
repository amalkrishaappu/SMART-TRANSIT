from .models import Notification

def send_notification(recipient, title, message, notification_type='GENERAL', priority='NORMAL', metadata=None):
    return Notification.objects.create(
        recipient=recipient,
        title=title,
        message=message,
        notification_type=notification_type,
        priority=priority,
        metadata=metadata or {}
    )

def notify_location_change_approved(req):
    student_user = req.student.user
    student_name = student_user.get_full_name() or student_user.username
    bus_no = req.assigned_bus.bus_number
    duration_str = req.get_change_duration_display()
    eff_date = req.effective_start_date.strftime('%d %B %Y')

    # Build description of the change
    changes_desc = []
    if req.requested_pickup_stop:
        changes_desc.append(f"Previous Pickup: {req.current_pickup_stop.stop_name}\nNew Pickup: {req.requested_pickup_stop.stop_name}")
    if req.requested_drop_stop:
        changes_desc.append(f"Previous Drop: {req.current_drop_stop.stop_name}\nNew Drop: {req.requested_drop_stop.stop_name}")
    
    change_text = "\n".join(changes_desc)
    
    # 1. Notify Student
    student_msg = (
        f"Transportation Update: Your location change request for {bus_no} has been APPROVED by the administrator.\n\n"
        f"{change_text}\n"
        f"Duration: {duration_str}\n"
        f"Effective Date: {eff_date}"
    )
    send_notification(
        recipient=student_user,
        title="Location Change Request Approved",
        message=student_msg,
        notification_type='LOCATION_CHANGE_APPROVED',
        priority='HIGH',
        metadata={'request_id': req.id}
    )

    # 2. Notify Linked Parent(s)
    parent_msg = (
        f"Transportation Update: Your child {student_name}, assigned to {bus_no}, has received approval for a location change.\n\n"
        f"{change_text}\n"
        f"Duration: {duration_str}\n"
        f"Effective Date: {eff_date}\n\n"
        f"This change has been approved by the college transport administrator."
    )
    for parent in req.student.parents.all():
        send_notification(
            recipient=parent.user,
            title=f"Transport Update for {student_name}",
            message=parent_msg,
            notification_type='LOCATION_CHANGE_APPROVED',
            priority='HIGH',
            metadata={'request_id': req.id, 'student_id': req.student.id}
        )

    # 3. Notify Assigned Driver(s)
    driver_assignments = req.assigned_bus.driver_assignments.filter(is_active=True)
    driver_msg = (
        f"Passenger Route Update for {bus_no}:\n"
        f"Student: {student_name} ({req.student.student_id})\n"
        f"{change_text}\n"
        f"Effective: {eff_date} ({duration_str})"
    )
    for da in driver_assignments:
        send_notification(
            recipient=da.driver.user,
            title="Passenger Location Change Notice",
            message=driver_msg,
            notification_type='LOCATION_CHANGE_APPROVED',
            priority='NORMAL',
            metadata={'request_id': req.id, 'bus_id': req.assigned_bus.id}
        )

def notify_location_change_rejected(req, rejection_reason):
    student_user = req.student.user
    bus_no = req.assigned_bus.bus_number
    
    student_msg = (
        f"Your location change request for {bus_no} has been REJECTED by the administrator.\n\n"
        f"Reason for rejection:\n\"{rejection_reason}\"\n\n"
        f"Your current pickup ({req.current_pickup_stop.stop_name}) and drop ({req.current_drop_stop.stop_name}) locations remain unchanged."
    )
    send_notification(
        recipient=student_user,
        title="Location Change Request Rejected",
        message=student_msg,
        notification_type='LOCATION_CHANGE_REJECTED',
        priority='HIGH',
        metadata={'request_id': req.id}
    )
