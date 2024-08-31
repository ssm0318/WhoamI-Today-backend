from django.apps import AppConfig
import os

class CustomFCMDeviceConfig(AppConfig):
    name = 'custom_fcm'
    default_auto_field = 'django.db.models.BigAutoField'
    # 실배포 환경에서 제대로 된 path를 찾지 못하는 문제를 위해 필요
    path = os.path.dirname(os.path.abspath(__file__))

