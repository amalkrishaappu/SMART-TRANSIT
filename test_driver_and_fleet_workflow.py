import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smart_transit.settings')
django.setup()

from django.test import Client
from apps.accounts.models import User, DriverProfile, StudentProfile
from apps.fleet.models import Bus, DriverBusAssignment, StudentBusAssignment
from apps.routes.models import Route, BusStop

def test_complete_fleet_and_driver_flow():
    print("=" * 65)
    print("TESTING DYNAMIC FLEET, DRIVER ASSIGNMENT & REAL DATA WORKFLOW")
    print("=" * 65)

    client = Client()

    # 1. Admin login
    print("\n[STEP 1] Administrator Login...")
    admin_login = client.login(username='admin', password='admin123')
    assert admin_login, "Admin login failed!"
    print("✓ Administrator logged in successfully.")

    # 2. Admin adds a new bus
    print("\n[STEP 2] Admin adding Bus 'BUS-01' dynamically...")
    res = client.post('/admin/buses/add/', {
        'bus_number': 'BUS-01',
        'registration_number': 'KL-08-CC-1122',
        'seating_capacity': '45',
        'model_name': 'Tata Starbus Ultra'
    }, follow=True)
    assert res.status_code == 200
    bus = Bus.objects.filter(bus_number='BUS-01').first()
    assert bus is not None, "Bus was not created in database!"
    print(f"✓ Bus created: {bus.bus_number} ({bus.registration_number}) - Capacity: {bus.seating_capacity}")

    # 3. Admin onboards a new driver
    print("\n[STEP 3] Admin onboarding Driver 'Suresh Kumar'...")
    res = client.post('/admin/drivers/add/', {
        'first_name': 'Suresh',
        'last_name': 'Kumar',
        'license_number': 'KL-45-2018-00912',
        'phone_number': '+91 98460 11223',
        'experience_years': '8',
        'username': 'driver_suresh',
        'password': 'driverpassword123'
    }, follow=True)
    assert res.status_code == 200
    driver = DriverProfile.objects.filter(license_number='KL-45-2018-00912').first()
    assert driver is not None, "Driver profile not found!"
    print(f"✓ Driver onboarded: {driver.user.get_full_name()} (License: {driver.license_number})")

    # 4. Admin assigns driver to BUS-01
    print("\n[STEP 4] Admin assigning Driver to BUS-01...")
    res = client.post(f'/admin/buses/{bus.id}/assign-driver/', {
        'driver_id': driver.id
    }, follow=True)
    assert res.status_code == 200
    bus.refresh_from_db()
    active_driver = bus.get_active_driver()
    assert active_driver == driver, "Driver was not linked to bus!"
    print(f"✓ Driver {active_driver.user.get_full_name()} officially assigned to {bus.bus_number}.")

    # 5. Check Fleet page shows assigned driver name
    print("\n[STEP 5] Verifying Driver name is visible in Fleet table...")
    res_fleet = client.get('/admin/fleet-routes/')
    assert res_fleet.status_code == 200
    fleet_html = res_fleet.content.decode('utf-8')
    assert "Suresh Kumar" in fleet_html, "Driver name not found in Fleet table!"
    assert "KL-45-2018-00912" in fleet_html, "Driver license not found in Fleet table!"
    print("✓ Fleet table displays assigned driver name and license plate number.")

    # 6. Admin creates a Route & adds Stops
    print("\n[STEP 6] Admin creating Route RT-01 and adding Stops...")
    client.post('/admin/routes/add/', {
        'route_code': 'RT-01',
        'route_name': 'Irinjalakuda – College Main Campus Line',
        'start_location': 'Irinjalakuda Town',
        'end_location': 'College Main Gate',
        'total_distance_km': '24.5',
        'estimated_duration_mins': '55'
    }, follow=True)
    route = Route.objects.filter(route_code='RT-01').first()
    assert route is not None

    # Add 3 sequenced stops
    client.post(f'/admin/routes/{route.id}/stops/add/', {
        'stop_name': 'Irinjalakuda Town Hub',
        'stop_sequence': '1',
        'scheduled_pickup_time': '07:30',
        'scheduled_drop_time': '17:30',
        'latitude': '10.3428',
        'longitude': '76.2086'
    }, follow=True)

    client.post(f'/admin/routes/{route.id}/stops/add/', {
        'stop_name': 'Railway Station Stop',
        'stop_sequence': '2',
        'scheduled_pickup_time': '07:50',
        'scheduled_drop_time': '17:10',
        'latitude': '10.3620',
        'longitude': '76.2240'
    }, follow=True)

    client.post(f'/admin/routes/{route.id}/stops/add/', {
        'stop_name': 'College Main Gate',
        'stop_sequence': '3',
        'scheduled_pickup_time': '08:30',
        'scheduled_drop_time': '16:30',
        'latitude': '10.3850',
        'longitude': '76.2460'
    }, follow=True)

    assert route.stops.count() == 3
    print(f"✓ Route {route.route_code} created with {route.stops.count()} sequenced stops.")

    # 7. Student registers
    print("\n[STEP 7] Student 'Amal Varghese' self-registering...")
    client.logout()
    res_reg = client.post('/login/', {
        'action': 'register_student',
        'first_name': 'Amal',
        'last_name': 'Varghese',
        'academic_year': '3rd Year',
        'department': 'Computer Science & Engineering',
        'student_id': 'STU-2026-001',
        'phone_number': '+91 98470 12345',
        'username': 'amal_v',
        'email': 'amal@college.edu',
        'password': 'studentpass123',
        'password_confirm': 'studentpass123'
    }, follow=True)
    assert res_reg.status_code == 200
    student = StudentProfile.objects.filter(student_id='STU-2026-001').first()
    assert student is not None
    print(f"✓ Student registered: {student.user.get_full_name()} ({student.student_id})")

    # 8. Admin allots bus to Amal
    print("\n[STEP 8] Admin allotting BUS-01 and Route RT-01 to Amal...")
    client.login(username='admin', password='admin123')
    stop1 = route.stops.get(stop_sequence=1)
    stop3 = route.stops.get(stop_sequence=3)
    client.post(f'/admin/allot-bus/{student.id}/', {
        'bus_id': bus.id,
        'route_id': route.id,
        'pickup_stop_id': stop1.id,
        'drop_stop_id': stop3.id
    })
    assignment = StudentBusAssignment.objects.filter(student=student).first()
    assert assignment is not None
    assert assignment.bus == bus
    print(f"✓ Assignment saved: {student.student_id} allotted {bus.bus_number} (Pickup: {stop1.stop_name}).")

    # 9. Driver logs in and sees Amal in manifest
    print("\n[STEP 9] Driver Suresh logging in to view passenger manifest...")
    client.logout()
    driver_login = client.login(username='driver_suresh', password='driverpassword123')
    assert driver_login, "Driver login failed!"
    res_manifest = client.get('/driver/manifest/')
    assert res_manifest.status_code == 200
    manifest_html = res_manifest.content.decode('utf-8')
    assert "BUS-01" in manifest_html, "Bus number not on driver console!"
    assert "Amal Varghese" in manifest_html, "Student Amal not in driver manifest!"
    assert "Irinjalakuda Town Hub" in manifest_html, "Pickup stop not in manifest!"
    print("✓ Driver console accurately displays BUS-01, assigned route, and passenger Amal Varghese!")

    print("\n" + "=" * 65)
    print("ALL TESTS PASSED: DYNAMIC FLEET & DRIVER ASSIGNMENT FULLY VERIFIED")
    print("=" * 65)

if __name__ == '__main__':
    test_complete_fleet_and_driver_flow()
