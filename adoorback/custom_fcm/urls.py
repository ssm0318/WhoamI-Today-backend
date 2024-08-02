from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CustomFCMDeviceViewSet

router = DefaultRouter()
router.register(r'devices', CustomFCMDeviceViewSet)

urlpatterns = [
    path('', include(router.urls)),
]