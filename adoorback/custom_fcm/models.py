from django.db import models
from fcm_django.models import AbstractFCMDevice

class CustomFCMDevice(AbstractFCMDevice):
    language = models.CharField(max_length=10, blank=True, null=True)

    class Meta(AbstractFCMDevice.Meta):
        abstract = False