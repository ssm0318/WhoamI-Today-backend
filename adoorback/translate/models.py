from django.db import models

# Create your models here.
class TranslateResponse(models.Model):
    translatedText = models.TextField(blank=True)
    detectedSourceLanguage = models.TextField()
