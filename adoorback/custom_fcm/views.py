from django.views import View
from django.http import JsonResponse
from .models import CustomFCMDevice

class FCMRegisterView(View):
    def post(self, request, *args, **kwargs):
        registration_id = request.POST.get('registration_id')
        language = request.POST.get('language', 'en')

        device, created = CustomFCMDevice.objects.get_or_create(
            registration_id=registration_id,
            defaults={'language': language, 'user': request.user if request.user.is_authenticated else None}
        )
        if not created:
            device.language = language
            device.save()

        return JsonResponse({'status': 'success', 'message': 'FCM registered with language setting'})