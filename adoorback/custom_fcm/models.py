from django.db import models
from fcm_django.models import FCMDevice

FCMDevice.add_to_class('language', models.CharField(max_length=10, blank=True, null=True))
