from rest_framework import serializers
from .models import CustomFCMDevice

class CustomFCMDeviceSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomFCMDevice
        fields = '__all__'  
