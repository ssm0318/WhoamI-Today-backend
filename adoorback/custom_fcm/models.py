from fcm_django.models import AbstractFCMDevice
from django.db import models

class CustomFCMDevice(AbstractFCMDevice):
    language = models.CharField(max_length=10, blank=True, null=True)
