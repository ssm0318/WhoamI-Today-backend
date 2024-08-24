from fcm_django.models import FCMDevice
from django.db import models

class CustomFCMDevice(FCMDevice):
    language = models.CharField(max_length=10, blank=True, null=True)

    class Meta:
        proxy = False