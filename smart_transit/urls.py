from django.contrib import admin
from django.urls import path, include
from apps.accounts.views import (
    home_view, login_register_view, logout_view, dashboard_redirect_view,
    student_location_request_view, admin_bus_allotment_view, admin_allot_bus_action,
    admin_location_requests_view, driver_manifest_view, parent_transport_view,
    admin_student_management_view, change_password_view,
)
from apps.routes.views import (
    admin_fleet_routes_view, admin_add_bus_action, admin_delete_bus_action,
    admin_assign_driver_action, admin_add_driver_action,
    admin_add_route_action, admin_delete_route_action,
    admin_add_stop_action, admin_delete_stop_action
)

urlpatterns = [
    path('django-admin/', admin.site.urls),
    path('', home_view, name='home'),
    path('login/', login_register_view, name='login-view'),
    path('logout/', logout_view, name='logout-view'),
    path('account/change-password/', change_password_view, name='change-password'),
    path('dashboard/', dashboard_redirect_view, name='dashboard-redirect'),

    # Student Dashboard
    path('student/location-request/', student_location_request_view, name='student-location-request'),

    # Administrator Dashboards
    path('admin/students/', admin_student_management_view, name='admin-student-management'),
    path('admin/fleet-routes/', admin_fleet_routes_view, name='admin-fleet-routes'),
    path('admin/bus-allotment/', admin_bus_allotment_view, name='admin-bus-allotment'),
    path('admin/allot-bus/<int:student_id>/', admin_allot_bus_action, name='admin-allot-bus-action'),
    path('admin/location-requests/', admin_location_requests_view, name='admin-location-requests'),

    # Fleet, Driver & Route Management Actions
    path('admin/buses/add/', admin_add_bus_action, name='admin-add-bus'),
    path('admin/buses/<int:bus_id>/delete/', admin_delete_bus_action, name='admin-delete-bus'),
    path('admin/buses/<int:bus_id>/assign-driver/', admin_assign_driver_action, name='admin-assign-driver'),
    path('admin/drivers/add/', admin_add_driver_action, name='admin-add-driver'),
    path('admin/routes/add/', admin_add_route_action, name='admin-add-route'),
    path('admin/routes/<int:route_id>/delete/', admin_delete_route_action, name='admin-delete-route'),
    path('admin/routes/<int:route_id>/stops/add/', admin_add_stop_action, name='admin-add-stop'),
    path('admin/stops/<int:stop_id>/delete/', admin_delete_stop_action, name='admin-delete-stop'),

    # Driver & Parent Portals
    path('driver/manifest/', driver_manifest_view, name='driver-manifest'),
    path('parent/transport/', parent_transport_view, name='parent-transport'),

    # REST APIs
    path('api/v1/routes/', include('apps.routes.urls')),
    path('api/v1/', include('apps.notifications.urls')),
]
