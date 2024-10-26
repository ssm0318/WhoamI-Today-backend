from django.db import models

# Create your models here.
class TranslateResponse(models.Model):
    translated_text = models.TextField(blank=True)
    detectedSourceLanguage = models.TextField()
