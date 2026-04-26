from django.db import models
from django.core.validators import MinLengthValidator


class AdoorTimestampedModel(models.Model):
    class Meta:
        abstract = True

    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    updated_at = models.DateTimeField(auto_now=True)


class AdoorModel(AdoorTimestampedModel):
    class Meta:
        abstract = True

    content = models.TextField(validators=[MinLengthValidator(1, "content length must be greater than 1")])

    def __str__(self):
        return self.content


class Mission(AdoorTimestampedModel):
    MISSION_TYPE_CHOICES = [
        ('song', 'Song'),
        ('question', 'Question'),
        ('text', 'Text'),
        ('compliment', 'Compliment'),
    ]

    prompt = models.TextField()
    type = models.CharField(max_length=20, choices=MISSION_TYPE_CHOICES)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return self.prompt
