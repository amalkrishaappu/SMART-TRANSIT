from django.core.management.base import BaseCommand
from datetime import time
from apps.accounts.models import User, StudentProfile, ParentProfile, DriverProfile
from apps.fleet.models import Bus, DriverBusAssignment, StudentBusAssignment
from apps.routes.models import Route, BusStop

class Command(BaseCommand):
    help = 'Seeds initial test data for Smart College Transportation Management System'

    def handle(self, *args, **options):
        self.stdout.write("Seeding transportation management database...")

        # 1. Administrator
        admin_user, _ = User.objects.get_or_create(
            username='admin',
            defaults={
                'first_name': 'Chief',
                'last_name': 'Administrator',
                'email': 'admin@college.edu',
                'role': 'ADMIN',
                'is_staff': True,
                'is_superuser': True
            }
        )
        admin_user.set_password('admin123')
        admin_user.save()
        self.stdout.write(self.style.SUCCESS("✓ Admin user created (admin / admin123)"))

        # 2. Driver
        driver_user, _ = User.objects.get_or_create(
            username='driver1',
            defaults={
                'first_name': 'Suresh',
                'last_name': 'Kumar',
                'email': 'suresh.driver@college.edu',
                'role': 'DRIVER',
                'phone_number': '+91 98460 77889'
            }
        )
        driver_user.set_password('driver123')
        driver_user.save()

        driver_profile, _ = DriverProfile.objects.get_or_create(
            user=driver_user,
            defaults={
                'license_number': 'KL-45-2018-00912',
                'experience_years': 8,
                'is_active_duty': True
            }
        )
        self.stdout.write(self.style.SUCCESS("✓ Driver created (driver1 / driver123)"))

        # 3. Student (Amal)
        student_user, _ = User.objects.get_or_create(
            username='student1',
            defaults={
                'first_name': 'Amal',
                'last_name': 'Varghese',
                'email': 'amal.varghese@college.edu',
                'role': 'STUDENT',
                'phone_number': '+91 98471 22334'
            }
        )
        student_user.set_password('student123')
        student_user.save()

        student_profile, _ = StudentProfile.objects.get_or_create(
            user=student_user,
            defaults={
                'student_id': 'STU-2026-005',
                'department': 'Computer Science & Engineering',
                'academic_year': '3rd Year B.Tech',
                'emergency_contact': '+91 98470 12345',
                'home_address': 'Varghese Villa, Irinjalakuda P.O., Thrissur'
            }
        )
        self.stdout.write(self.style.SUCCESS("✓ Student created: Amal (student1 / student123)"))

        # 4. Parent
        parent_user, _ = User.objects.get_or_create(
            username='parent1',
            defaults={
                'first_name': 'Joseph',
                'last_name': 'Varghese',
                'email': 'parent.joseph@college.edu',
                'role': 'PARENT',
                'phone_number': '+91 98470 12345'
            }
        )
        parent_user.set_password('parent123')
        parent_user.save()

        parent_profile, _ = ParentProfile.objects.get_or_create(
            user=parent_user,
            defaults={'relationship': 'Father'}
        )
        parent_profile.students.add(student_profile)
        self.stdout.write(self.style.SUCCESS("✓ Parent created: Joseph linked to Amal (parent1 / parent123)"))

        # 5. Buses
        bus5, _ = Bus.objects.get_or_create(
            bus_number='BUS-05',
            defaults={
                'registration_number': 'KL-08-AX-5544',
                'seating_capacity': 45,
                'model_name': 'Ashok Leyland Viking',
                'status': 'ACTIVE'
            }
        )

        bus12, _ = Bus.objects.get_or_create(
            bus_number='BUS-12',
            defaults={
                'registration_number': 'KL-08-BZ-1212',
                'seating_capacity': 50,
                'model_name': 'Tata Starbus',
                'status': 'ACTIVE'
            }
        )
        self.stdout.write(self.style.SUCCESS("✓ Fleet Buses created (BUS-05, BUS-12)"))

        # 6. Driver-to-Bus assignment
        DriverBusAssignment.objects.get_or_create(
            driver=driver_profile,
            bus=bus5,
            defaults={'is_active': True}
        )

        # 7. Routes & Stops
        # Route 1: Irinjalakuda – College
        route1, _ = Route.objects.get_or_create(
            route_code='RT-01',
            defaults={
                'route_name': 'Irinjalakuda – College Campus Express',
                'start_location': 'Irinjalakuda Town',
                'end_location': 'College Main Gate',
                'total_distance_km': 22.40,
                'estimated_duration_mins': 60,
                'is_active': True
            }
        )

        stops_data_r1 = [
            (1, 'Irinjalakuda Town', 10.3428, 76.2086, time(7, 30), time(17, 30)),
            (2, 'Tana Junction', 10.3541, 76.2155, time(7, 40), time(17, 20)),
            (3, 'Railway Station Stop', 10.3620, 76.2240, time(7, 50), time(17, 10)),
            (4, 'Christ College Junction', 10.3705, 76.2312, time(8, 5), time(16, 55)),
            (5, 'Potta Ashram', 10.3789, 76.2395, time(8, 15), time(16, 45)),
            (6, 'College Main Gate', 10.3850, 76.2460, time(8, 30), time(16, 30)),
        ]

        created_stops_r1 = []
        for seq, name, lat, lng, p_time, d_time in stops_data_r1:
            stop, _ = BusStop.objects.get_or_create(
                route=route1,
                stop_sequence=seq,
                defaults={
                    'stop_name': name,
                    'latitude': lat,
                    'longitude': lng,
                    'scheduled_pickup_time': p_time,
                    'scheduled_drop_time': d_time
                }
            )
            created_stops_r1.append(stop)

        # Route 2: Thrissur City – College (For testing out-of-route isolation)
        route2, _ = Route.objects.get_or_create(
            route_code='RT-02',
            defaults={
                'route_name': 'Thrissur City – College Line',
                'start_location': 'Thrissur Swaraj Round',
                'end_location': 'College Main Gate',
                'total_distance_km': 26.80,
                'estimated_duration_mins': 65,
                'is_active': True
            }
        )

        stops_data_r2 = [
            (1, 'Swaraj Round North', 10.5276, 76.2144, time(7, 15), time(17, 45)),
            (2, 'Ollur Junction', 10.4682, 76.2410, time(7, 35), time(17, 25)),
            (3, 'Pudukkad Center', 10.4215, 76.2550, time(7, 55), time(17, 5)),
            (4, 'College South Gate', 10.3840, 76.2450, time(8, 30), time(16, 30)),
        ]
        for seq, name, lat, lng, p_time, d_time in stops_data_r2:
            BusStop.objects.get_or_create(
                route=route2,
                stop_sequence=seq,
                defaults={
                    'stop_name': name,
                    'latitude': lat,
                    'longitude': lng,
                    'scheduled_pickup_time': p_time,
                    'scheduled_drop_time': d_time
                }
            )
        self.stdout.write(self.style.SUCCESS("✓ Routes and Stops created (RT-01 and RT-02)"))

        # 8. Fixed Bus Assignment for Amal
        # Bus: BUS-05, Route: RT-01
        # Pickup: Irinjalakuda Town (Stop #1)
        # Drop: College Main Gate (Stop #6)
        pickup_stop = created_stops_r1[0]
        drop_stop = created_stops_r1[5]

        assignment, created = StudentBusAssignment.objects.get_or_create(
            student=student_profile,
            defaults={
                'bus': bus5,
                'route': route1,
                'permanent_pickup_stop': pickup_stop,
                'permanent_drop_stop': drop_stop,
                'active_pickup_stop': pickup_stop,
                'active_drop_stop': drop_stop,
                'is_temporary_active': False,
                'status': 'ACTIVE'
            }
        )
        if not created:
            assignment.bus = bus5
            assignment.route = route1
            assignment.permanent_pickup_stop = pickup_stop
            assignment.permanent_drop_stop = drop_stop
            assignment.active_pickup_stop = pickup_stop
            assignment.active_drop_stop = drop_stop
            assignment.is_temporary_active = False
            assignment.save()

        self.stdout.write(self.style.SUCCESS(
            f"✓ Student Bus Assignment created: {student_profile.student_id} -> {bus5.bus_number} "
            f"on {route1.route_name} (Pickup: {pickup_stop.stop_name}, Drop: {drop_stop.stop_name})"
        ))

        self.stdout.write(self.style.SUCCESS("=== Database seeding completed successfully! ==="))
