from fcm_django.api.rest_framework import FCMDeviceSerializer

from adoorback.adoorback import serializers

class CustomFCMDeviceSerializer(FCMDeviceSerializer):
    language = serializers.CharField(max_length=10, required=False)

    class Meta(FCMDeviceSerializer.Meta):
        fields = FCMDeviceSerializer.Meta.fields + ['language']

    def validate(self, attrs):
        attrs = super().validate(attrs)
        return attrs