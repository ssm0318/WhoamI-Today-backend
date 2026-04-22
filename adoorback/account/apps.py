from django.apps import AppConfig


class AccountConfig(AppConfig):
    name = 'account'
    default_auto_field = 'django.db.models.AutoField'

    def ready(self):
        from . import signals  # noqa: F401
