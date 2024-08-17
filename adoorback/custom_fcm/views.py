from fcm_django.api.rest_framework import FCMDeviceAuthorizedViewSet
from rest_framework.response import Response
from rest_framework import status
from fcm_django.models import FCMDevice

class CustomFCMDeviceViewSet(FCMDeviceAuthorizedViewSet):
    
    def __get_language_from_request(self, request):
        accept_language = request.META.get('HTTP_ACCEPT_LANGUAGE', '')
        return accept_language.split(',')[0].split('-')[0] if accept_language else 'en'

    def update_device(self, device, data, language):
        serializer = self.get_serializer(device, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        device.language = language
        device.save()
        return serializer

    def create(self, request, *args, **kwargs):
        language = self.__get_language_from_request(request)
        registration_id = request.data.get('registration_id')
        existing_device = FCMDevice.objects.filter(registration_id=registration_id).first()

        if existing_device:
            # Update existing device
            serializer = self.update_device(existing_device, request.data, language)
            return Response(serializer.data, status=status.HTTP_200_OK)
        else:
            # Create new device
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)
            device = serializer.instance
            device.language = language
            device.save()
            headers = self.get_success_headers(serializer.data)
            return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
