from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    my_assignment_details,
    available_route_stops,
    StudentLocationChangeRequestViewSet
)

router = DefaultRouter()
router.register(r'location-requests', StudentLocationChangeRequestViewSet, basename='location-request')

urlpatterns = [
    path('my-assignment-details/', my_assignment_details, name='my-assignment-details'),
    path('<int:route_id>/available-stops/', available_route_stops, name='available-route-stops'),
    path('', include(router.urls)),
]
