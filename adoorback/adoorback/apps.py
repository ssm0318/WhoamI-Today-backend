from django.apps import AppConfig


class AdoorbackConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'adoorback'

    def ready(self):
        from tracking.models import Visitor
        Visitor._meta.get_field("session_key").max_length = 255
