import traceback

from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework import status
from .models import CustomFCMDevice
from .serializers import CustomFCMDeviceSerializer 
from rest_framework.permissions import IsAuthenticated

from adoorback.utils.alerts import send_msg_to_slack
from adoorback.settings import LANGUAGE_CODE, LANGUAGES
from adoorback.utils.validators import adoor_exception_handler


class CustomFCMDeviceViewSet(viewsets.ModelViewSet):
    queryset = CustomFCMDevice.objects.all()
    serializer_class = CustomFCMDeviceSerializer
    permission_classes = [IsAuthenticated]

    def get_exception_handler(self):
        return adoor_exception_handler

    def __get_language_from_request(self, request):
        accept_language = request.META.get('HTTP_ACCEPT_LANGUAGE', '')
        lang = accept_language.split(',')[0].split('-')[0].strip().lower() if accept_language else 'en'
        if lang not in dict(LANGUAGES):  # 예: 'fr' 같은 미지원 언어 필터링
            lang = LANGUAGE_CODE
        return lang

    def update_device(self, device, data, language):
        serializer = self.get_serializer(device, data=data, partial=True)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        device.language = language
        device.save()
        return serializer

    def create(self, request, *args, **kwargs):
        try:
            current_user = self.request.user
            language = self.__get_language_from_request(request)
            registration_id = request.data.get('registration_id')
            
            # Check for existing device with same registration_id
            existing_device = CustomFCMDevice.objects.filter(registration_id=registration_id).first()
            # If found a device with the same registration_id - update it to current user
            if existing_device:
                # If device belongs to a different user, update the user to current_user
                if existing_device.user_id != current_user.id:
                    print(f"Device previously belonged to user {existing_device.user_id}, updating to {current_user.id}")
                
                # Update the device with current user and other data
                existing_device.user_id = current_user.id
                serializer = self.update_device(existing_device, request.data, language)
                return Response(serializer.data, status=status.HTTP_200_OK)
            
            # Create new device if no existing device found
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)
            device = serializer.instance
            device.language = language
            device.user_id = current_user.id
            device.save()
            headers = self.get_success_headers(serializer.data)
            return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
        except Exception as e:
            error_message = str(e)
            stack_trace = traceback.format_exc()
            send_msg_to_slack(
                text=f"🚨 예외 발생\n```{stack_trace}```",
                level="ERROR"
            )
            return Response({"error": error_message}, status=status.HTTP_400_BAD_REQUEST)
