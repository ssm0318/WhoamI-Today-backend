from django.apps import AppConfig

class CustomFcmConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'custom_fcm'

    def ready(self):
        import custom_fcm.models