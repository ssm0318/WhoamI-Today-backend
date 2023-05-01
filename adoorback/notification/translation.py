from modeltranslation.translator import translator, TranslationOptions
from .models import Notification

class NotificationTranslationOptions(TranslationOptions):
    fields = ('message',)
    required_languages = ('ko', 'en',)

translator.register(Notification, NotificationTranslationOptions)
