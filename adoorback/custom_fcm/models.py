from django.db import models
from fcm_django.models import FCMDevice

class CustomFCMDevice(FCMDevice):
    language = models.CharField(max_length=10, blank=True, null=True)
