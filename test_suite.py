import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smart_transit.settings')
django.setup()

from django.test import Client
from django.utils import timezone
from datetime import timedelta, date
from apps.accounts.models import User, StudentProfile
from apps.fleet.models import Bus, StudentBusAssignment
from apps.routes.models import Route, BusStop, StudentLocationChangeRequest
from apps.notifications.models import Notification
from apps.routes.tasks import revert_expired_temporary_requests

def run_tests():
    print("=" * 60)
    print("RUNNING COMPREHENSIVE AUTOMATED VERIFICATION SUITE")
    print("=" * 60)

    client = Client()

    # -------------------------------------------------------------
    # TEST 1: New Student Registration (Name, Year, Department, etc.)
    # -------------------------------------------------------------
    print("\n[TEST 1] Registering New Student (Rahul K, CS, 2nd Year)...")
    reg_data = {
        'action': 'register_student',
        'first_name': 'Rahul',
        'last_name': 'Krishna',
        'username': 'rahul_k',
        'email': 'rahul@college.edu',
        'phone_number': '+91 98471 99887',
        'student_id': 'STU-2026-088',
        'department': 'Computer Science & Engineering',
        'academic_year': '2nd Year',
        'password': 'password123',
        'password_confirm': 'password123'
    }
    res = client.post('/login/', reg_data, follow=True)
    assert res.status_code == 200, f"Registration failed with code {res.status_code}"

    new_student = StudentProfile.objects.filter(student_id='STU-2026-088').first()
    assert new_student is not None, "StudentProfile not found in database!"
    assert new_student.user.first_name == 'Rahul'
    assert new_student.department == 'Computer Science & Engineering'
    assert new_student.academic_year == '2nd Year'
    print("✓ TEST 1 PASSED: Student registered successfully.")

    # -------------------------------------------------------------
    # TEST 2: Student Login Before Allotment (Pending Allotment View)
    # -------------------------------------------------------------
    print("\n[TEST 2] Verifying Student Dashboard Before Bus Allotment...")
    login_success = client.login(username='rahul_k', password='password123')
    assert login_success, "Student login failed!"

    res = client.get('/student/location-request/')
    assert res.status_code == 200
    assert "Bus Assignment Pending Administrator Allotment" in res.content.decode('utf-8')
    client.logout()
    print("✓ TEST 2 PASSED: Pending allotment banner accurately displayed for unallotted student.")

    # -------------------------------------------------------------
    # TEST 3: Administrator Login & Bus Allotment
    # -------------------------------------------------------------
    print("\n[TEST 3] Admin Logging In & Allotting BUS-05 to Rahul...")
    admin_login = client.login(username='admin', password='admin123')
    assert admin_login, "Admin login failed!"

    # Fetch bus, route, and stops
    bus5 = Bus.objects.get(bus_number='BUS-05')
    route1 = Route.objects.get(route_code='RT-01')
    stop_pickup = route1.stops.get(stop_sequence=2) # Tana Junction
    stop_drop = route1.stops.get(stop_sequence=6)   # College Main Gate

    allot_data = {
        'bus_id': bus5.id,
        'route_id': route1.id,
        'pickup_stop_id': stop_pickup.id,
        'drop_stop_id': stop_drop.id
    }
    res = client.post(f'/admin/allot-bus/{new_student.id}/', allot_data)
    assert res.status_code == 200, f"Allotment failed: {res.content}"

    assignment = StudentBusAssignment.objects.filter(student=new_student).first()
    assert assignment is not None
    assert assignment.bus == bus5
    assert assignment.active_pickup_stop == stop_pickup
    assert assignment.active_drop_stop == stop_drop
    print(f"✓ TEST 3 PASSED: Bus {bus5.bus_number} allotted to {new_student.student_id} (Pickup: {stop_pickup.stop_name}).")

    # -------------------------------------------------------------
    # TEST 4: Student Dashboard After Allotment
    # -------------------------------------------------------------
    print("\n[TEST 4] Student Logging In After Bus Allotment...")
    client.logout()
    client.login(username='rahul_k', password='password123')
    res = client.get('/student/location-request/')
    assert res.status_code == 200
    page_html = res.content.decode('utf-8')
    assert "BUS-05" in page_html
    assert "Tana Junction" in page_html
    assert "College Main Gate" in page_html
    assert "Route Stops Visualizer" in page_html
    print("✓ TEST 4 PASSED: Student dashboard activated with live bus and route stops!")

    # -------------------------------------------------------------
    # TEST 5: Student Submits Pickup Location Change Request
    # -------------------------------------------------------------
    print("\n[TEST 5] Student Submitting Location Change Request (to Railway Station Stop)...")
    stop_target_pickup = route1.stops.get(stop_sequence=3) # Railway Station Stop
    tomorrow = (timezone.now() + timedelta(days=1)).date()
    next_week = (timezone.now() + timedelta(days=7)).date()

    req_payload = {
        'request_type': 'PICKUP',
        'change_duration': 'TEMPORARY',
        'effective_start_date': tomorrow.isoformat(),
        'effective_end_date': next_week.isoformat(),
        'requested_pickup_stop': stop_target_pickup.id,
        'reason': 'Staying at relative home near Railway Station for 1 week exam preparation'
    }
    res = client.post('/api/v1/routes/location-requests/', req_payload, content_type='application/json')
    assert res.status_code == 201, f"Failed to submit location request: {res.content}"
    loc_req_id = res.json()['id']
    print(f"✓ TEST 5 PASSED: Location change request #{loc_req_id} submitted with status PENDING.")

    # -------------------------------------------------------------
    # TEST 6: Prevent Duplicate Pending Request
    # -------------------------------------------------------------
    print("\n[TEST 6] Testing Duplicate Pending Request Prevention...")
    res_dup = client.post('/api/v1/routes/location-requests/', req_payload, content_type='application/json')
    assert res_dup.status_code == 400, "Duplicate request should have been rejected!"
    print("✓ TEST 6 PASSED: Duplicate pending request successfully blocked (HTTP 400).")

    # -------------------------------------------------------------
    # TEST 7: Administrator Review & Approval
    # -------------------------------------------------------------
    print("\n[TEST 7] Administrator Approving Request #{loc_req_id}...")
    client.logout()
    client.login(username='admin', password='admin123')

    res_approve = client.post(f'/api/v1/routes/location-requests/{loc_req_id}/approve/', {
        'admin_remarks': 'Approved as per college travel guidelines.'
    }, content_type='application/json')
    assert res_approve.status_code == 200, f"Approval failed: {res_approve.content}"

    assignment.refresh_from_db()
    assert assignment.active_pickup_stop == stop_target_pickup, "Active pickup stop not updated!"
    assert assignment.is_temporary_active is True
    print(f"✓ TEST 7 PASSED: Request approved! Active pickup updated to {assignment.active_pickup_stop.stop_name}.")

    # -------------------------------------------------------------
    # TEST 8: Driver Manifest Visibility
    # -------------------------------------------------------------
    print("\n[TEST 8] Checking Driver Manifest for Approved Stop Change...")
    client.logout()
    client.login(username='driver1', password='driver123')
    res_driver = client.get('/driver/manifest/')
    assert res_driver.status_code == 200
    driver_html = res_driver.content.decode('utf-8')
    assert "Railway Station Stop" in driver_html
    assert "Approved Temp Change" in driver_html
    print("✓ TEST 8 PASSED: Driver manifest reflects approved stop update and duration tag.")

    # -------------------------------------------------------------
    # TEST 9: Auto-Expiry and Baseline Restoration
    # -------------------------------------------------------------
    print("\n[TEST 9] Simulating Expiration of Temporary Change...")
    loc_req = StudentLocationChangeRequest.objects.get(id=loc_req_id)
    # Simulate past date
    loc_req.effective_end_date = date.today() - timedelta(days=1)
    loc_req.save()

    reverted = revert_expired_temporary_requests()
    assert reverted >= 1, "Expiry utility did not revert expired request!"

    assignment.refresh_from_db()
    assert assignment.active_pickup_stop == assignment.permanent_pickup_stop
    assert assignment.is_temporary_active is False
    print(f"✓ TEST 9 PASSED: Expired temporary change reverted cleanly to permanent baseline: {assignment.active_pickup_stop.stop_name}.")

    print("\n" + "=" * 60)
    print("ALL 9 WORKFLOW AND INTEGRATION TESTS PASSED WITH 100% SUCCESS!")
    print("=" * 60)

if __name__ == '__main__':
    run_tests()
