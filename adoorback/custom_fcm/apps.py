from django.apps import AppConfig
import os

class CustomFCMDeviceConfig(AppConfig):
    name = 'custom_fcm'
    default_auto_field = 'django.db.models.BigAutoField'
    # Needed to fix path finding issues in production deployment environment
    path = os.path.dirname(os.path.abspath(__file__))

