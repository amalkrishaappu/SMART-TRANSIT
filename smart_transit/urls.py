from django.contrib import admin
from django.urls import path, include
from apps.accounts.views import (
    home_view, login_view, logout_view, dashboard_redirect_view,
    student_location_request_view, admin_location_requests_view,
    driver_manifest_view, parent_transport_view
)

urlpatterns = [
    path('django-admin/', admin.site.urls),
    path('', home_view, name='home'),
    path('login/', login_view, name='login-view'),
    path('logout/', logout_view, name='logout-view'),
    path('dashboard/', dashboard_redirect_view, name='dashboard-redirect'),

    # Role Dashboards
    path('student/location-request/', student_location_request_view, name='student-location-request'),
    path('admin/location-requests/', admin_location_requests_view, name='admin-location-requests'),
    path('driver/manifest/', driver_manifest_view, name='driver-manifest'),
    path('parent/transport/', parent_transport_view, name='parent-transport'),

    # REST APIs
    path('api/v1/routes/', include('apps.routes.urls')),
    path('api/v1/', include('apps.notifications.urls')),
]
