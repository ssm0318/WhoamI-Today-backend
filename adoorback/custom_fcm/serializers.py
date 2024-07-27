from rest_framework import serializers
from .models import CustomFCMDevice

class CustomFCMDeviceSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomFCMDevice
        fields = ['registration_id', 'language', 'user']